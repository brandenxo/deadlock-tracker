# deadlock-tracker

[![ci](https://github.com/brandenxo/deadlock-tracker/actions/workflows/ci.yml/badge.svg)](https://github.com/brandenxo/deadlock-tracker/actions/workflows/ci.yml)

**Live:** https://deadlock-tracker.brandenrivera.com

Hourly hero statistics for Valve's *Deadlock*. A small Python pipeline pulls new match data
from the public [deadlock-api.com](https://deadlock-api.com) data lake and aggregates it
with DuckDB. It publishes one JSON summary that a static React dashboard (**Hero Ledger**)
reads.

The pipeline only stores per-hero aggregates. Player identifiers (`account_id`) are
dropped at ingest and never stored.

```
data.deadlock-api.com ──▶ Lambda (Python + DuckDB) ──▶ S3 data bucket ──┐
  manifest + hourly         hourly via EventBridge     raw/  curated/   │
  Parquet deltas            Scheduler                  data/summary.json│
                                                                         ▼
                                     browser ◀── CloudFront ◀── S3 site bucket (React app)
```

There are no servers and no API: the dashboard is static files plus one JSON file that
the pipeline rewrites every hour. The cleaned Parquet can also be queried with Athena.

## Design decisions

- **The manifest is the only source of truth.** Source files get replaced and compacted,
  so the pipeline never lists a folder. It downloads only hourly `delta` files it doesn't
  hold yet, and never the multi-gigabyte `base` files.
- **Rebuild, don't patch.** Every run rebuilds the 7-day window from all held raw files.
  That takes seconds and gives the same answer however earlier runs went.
- **Only covered days.** A day is published once the held files span all of it plus a
  24-hour settle lag, because a measured 6% to 22% of a day's matches arrive later than
  6 hours (see [docs/source-notes.md](docs/source-notes.md)). The newest day shown is
  therefore two days old.
- **Rates from counts.** The summary stores additive daily counts, and the browser sums
  the selected days and divides once.
- **Tiers from confidence.** Tiers come from the 95% Wilson interval, so 52% over 200
  games isn't ranked like 52% over 20,000.
- **Validate, then publish.** Every counted match must have two full teams and one
  winner, or the run fails and the last good summary keeps serving.
- **No overlapping runs, no locks.** Lambda reserved concurrency is 1.
- **No player data.** `account_id` is never read.

## The dashboard

For any range of fully covered days in the last 7, the dashboard shows each hero's:

- **Win rate**, with a 95% Wilson interval.
- **Pick rate**: the share of eligible matches that included the hero.
- **Average match length.**
- **Tier** (S–D), assigned from the Wilson interval rather than the raw win rate. That way a
  hero with 60 games and a lucky streak doesn't outrank one with 60,000. Heroes need at
  least 100 games to get a tier.
- **Daily trend chart.**

You can filter by hero role and by match mode (all, ranked or unranked; about 18% of
eligible matches are ranked). A banner warns when the data is more than 3 hours old, and
the page names any days that contain a small upstream data gap.

## How a run works

Every run follows the same sequence (`pipeline/run.py`):

1. **Manifest.** Fetch the source manifest and check the `match_player` schema against
   `pipeline/contract.py`. If any column type differs, the run stops before downloading
   anything.
2. **Ingest.** Download delta files that aren't held yet, newest first, up to a byte cap
   (300 MB by default). Keep only the 13 columns the pipeline needs and store them under
   `raw/objects/<id>/` with a provenance receipt. Files that don't fit under the cap wait
   for a later run.
3. **Rebuild the window.** Recompute the whole 7-day window from every held object rather
   than patching the previous result. Output then depends only on the data held, not on
   past retries or duplicate deliveries.
4. **Curate** (`pipeline/sql/curate.sql`):
   - Deduplicate to the latest row per `(match_id, player_slot)`.
   - Exclude ineligible matches, recording the first reason that applies. Reasons include
     non-Normal game mode, private, bot or test lobbies, draws, unscored matches, rosters
     that aren't 6v6, unknown enum codes, and ambiguous duplicates.
   - Produce daily per-hero sums, split by match mode (ranked or unranked). Wins come
     from the match's winning team, not the per-row `won` flag.
5. **Coverage.** Rows for a match keep arriving after its day ends. Each UTC day is
   therefore judged over the day plus a 24-hour settle lag. A day is published only if the
   held data reaches the end of that span with at most 30 minutes missing in total.
   Partial days are withheld because an undercounted day can look plausible.
6. **Validate.** Every covered day must satisfy `appearances = 12 × matches` and
   `wins = 6 × matches` for each match mode, and unknown enum values must stay under 1% of matches. If any
   check fails, the run publishes nothing and the previous summary stays up.
7. **Publish.** Replace the date-partitioned Parquet under `curated/`, then write
   `data/summary.json` atomically.

Hero names, roles and portraits come from the Deadlock API's hero list. That lookup is
optional: if it fails, the dashboard shows `Hero <id>` instead.

`data/summary.json` holds sums only, never rates. The dashboard adds up the selected days
and match modes and divides once, so each day counts in proportion to its number of games.

## Repository layout

```
pipeline/       Python pipeline (source client, ingest, curate, coverage, summary, CLI, Lambda handler)
pipeline/sql/   curate.sql: dedup, exclusions, daily hero counters
tests/          pytest suite (moto for S3)
fixtures/       hero list, manifest excerpt and sample rows for tests and offline runs
web/            Vite + React 19 + Recharts dashboard
infra/          Terraform: S3, CloudFront (OAC), Lambda, scheduler, alarms, budget, Athena, optional domain
tools/          build_lambda.sh, deploy_site.sh, deploy.sh
docs/           data-contract.md (columns, rules, metrics), source-notes.md (what was verified)
.github/        CI: Python, web and Terraform checks on every push
```

## Continuous integration

`.github/workflows/ci.yml` runs three jobs on every push to `main` and on every pull
request. None of them needs AWS credentials.

- **python:** ruff lint and format check, pytest (including the mocked-S3 end-to-end
  run), then building the Lambda zip and importing it in a clean interpreter on Linux.
- **web:** Vitest, then the production build, which includes the TypeScript check.
- **terraform:** `terraform fmt -check` and `terraform validate`, with no backend and no
  apply.

## Local development

**Prerequisites:** [uv](https://docs.astral.sh/uv/), Python 3.12 (uv will fetch it), and
Node ≥ 22.12 with npm ≥ 11.

```sh
uv sync                    # Python deps, including dev tools
uv run pytest -q           # tests
uv run ruff check .        # lint
uv run ruff format .       # format
```

### Run the pipeline offline

The `synth` command writes a fake source directory. It has the same layout and quirks as
the real data lake (hourly deltas, late rows, duplicates, corrected winners), but the
numbers are random.

```sh
uv run python -m pipeline.cli synth --out data/synth --start 2026-10-05T00 --hours 48
uv run python -m pipeline.cli run --source data/synth --now 2026-10-07T06:30:00Z
```

Offline runs use `fixtures/heroes.json` for hero names. Add `--encoding label` to `synth`
to test the alternative Parquet encoding, which stores enums as strings and times as
timestamps.

### Run against the real source

```sh
uv run python -m pipeline.cli run                  # default 300 MB cap
uv run python -m pipeline.cli run --cap-mb 1000    # fill the window faster
```

Results go to `data/local/` (change this with `--data-dir`), and the summary is written
to `data/local/data/summary.json`. Don't run two pipeline runs at the same time against
the same data directory. Lambda prevents overlapping runs, but locally that's up to you.

### Run the dashboard

```sh
mkdir -p web/public/data
cp data/local/data/summary.json web/public/data/
cd web && npm ci && npm run dev
```

Other web scripts: `npm test` (Vitest), `npm run typecheck`, `npm run build`.

### Configuration

Settings are read from `DT_*` environment variables (`pipeline/config.py`). The defaults
match production, so a local run needs none of them. `.env.example` lists them, and no
secrets are involved.

| Variable | Default | Meaning |
| --- | --- | --- |
| `DT_MANIFEST_URL` | `https://data.deadlock-api.com/v1/manifest.json` | Source manifest |
| `DT_SOURCE_BASE_URL` | `https://data.deadlock-api.com` | Base URL for source files |
| `DT_HEROES_URL` | `https://api.deadlock-api.com/v1/assets/heroes` | Hero names and portraits |
| `DT_DOWNLOAD_CAP_MB` | `300` | Most a single run downloads |
| `DT_WINDOW_DAYS` | `7` | Days kept and shown |
| `DT_SETTLE_LAG_HOURS` | `24` | How long after midnight a day keeps receiving rows |
| `DT_MAX_GAP_MINUTES` | `30` | Total source gap allowed on a published day |
| `DT_BUCKET` | *(empty)* | S3 data bucket; empty means local storage |

## Deploying to AWS

Everything runs in `us-east-2`, apart from the ACM certificate for an optional custom
domain, which CloudFront requires to be in `us-east-1`. The commands below assume
`AWS_PROFILE=deadlock-tracker` with an active `aws login` session, plus Terraform, uv
and Node.

**1. One-time setup.**

- Create the Terraform state bucket. The commands are in `infra/backend.hcl.example`.
- Copy `infra/backend.hcl.example` to `infra/backend.hcl` and
  `infra/terraform.tfvars.example` to `infra/terraform.tfvars`, then fill both in. Both
  copies are gitignored.
- Set `alert_email` in `terraform.tfvars` and confirm the SNS subscription email when it
  arrives.

**2. Deploy.**

```sh
tools/deploy.sh
```

This runs the tests and builds `build/pipeline.zip` (it fetches DuckDB's manylinux wheel,
so no Docker is needed). It then runs an interactive `terraform apply` and uploads the
site. `tools/deploy_site.sh` on its own rebuilds and uploads just the frontend.

**3. First run.** The hourly schedule starts disabled. Invoke the function once by hand
and check that it publishes:

```sh
aws lambda invoke --function-name deadlock-tracker-pipeline out.json && cat out.json
```

The first runs fill the 7-day window in 300 MB steps, so a few manual invokes, or a
larger `download_cap_mb` for a while, will get the dashboard populated sooner.

**4. Enable the schedule.** Set `schedule_enabled = true` in `terraform.tfvars` and apply
again. The function then runs at :45 past every hour. That is about 10 minutes after
upstream's hourly file usually appears in the manifest.

**Custom domain (optional).** Set `domain_name` and apply. Then add the CNAME from the
`dns_validation_records` output at your DNS provider (with any proxying turned off). The
apply waits for that record to validate the certificate. Finally, point the domain's
CNAME at the `cloudfront_domain` output. See `infra/domain.tf`.

### What gets created

- **Data bucket** (private):
  - `raw/`: trimmed source objects, deleted 3 days after they leave the window.
  - `curated/`: date-partitioned Parquet for ad-hoc SQL (e.g. Athena).
  - `data/summary.json`
- **Site bucket** (private): the Vite build.
- **CloudFront** with Origin Access Control: serves `/` from the site bucket and `/data/*`
  from the data bucket, under one hostname so the app needs no CORS. It also adds security
  headers and a strict CSP.
- **Lambda** `deadlock-tracker-pipeline`: 3 GB memory, 10 min timeout, 4 GB ephemeral
  storage. Reserved concurrency is 1, so runs never overlap. Failed runs aren't retried,
  because the next hourly run does the same work.
- **EventBridge Scheduler**: runs the Lambda hourly.
- **Monitoring**: an SNS email topic, and two alarms. One fires on any failed run. The
  other fires after 3 hours with no runs, and exists only while the schedule is enabled.
- **Athena** (`infra/athena.tf`): a Glue database with `matches` and `participants`
  tables over `curated/`, using partition projection so new days are queryable without a
  crawler. It also creates a workgroup that stops any query after 1 GiB scanned, and three
  saved queries.
- **Budget**: an email alert at 50% of actual spend and 100% of forecast spend
  (default $10/month). It only sends email; it doesn't stop anything.

### Ad-hoc SQL with Athena

In the Athena console, choose the `deadlock-tracker` workgroup and the
`deadlock_tracker` database. Then open **Saved queries**:

- `hero-win-rates-last-7-days`: recomputes the dashboard's main number independently.
- `ranked-vs-unranked-win-rate`: per-hero win rate split by match mode. The dashboard
  doesn't show this.
- `match-length-by-day`: median match length per day.

As a cross-check, matches per day from Athena should equal `daily_matches` in
`summary.json` for covered days:

```sh
QID=$(aws athena start-query-execution --work-group deadlock-tracker \
  --query-execution-context Database=deadlock_tracker \
  --query-string "SELECT match_date_utc, COUNT(*) AS matches FROM matches GROUP BY 1 ORDER BY 1" \
  --query QueryExecutionId --output text)
sleep 5 && aws athena get-query-results --query-execution-id "$QID" --output table
```

### Operations

- Each run logs one JSON event per line. The saved Logs Insights query
  `deadlock-tracker/runs` lists recent `published`, `run_failed` and `heroes_unavailable`
  events.
- A failed run leaves the last good summary up. The dashboard's staleness banner appears
  once the summary is more than 3 hours old.
- Schema drift (`UnsupportedSchema`) means upstream changed a column type or enum. Review
  the change and update `pipeline/contract.py` before the pipeline will run again.

## Stack

- **Pipeline:** Python 3.12, DuckDB, boto3
- **Dashboard:** React 19, TypeScript, Vite, Recharts
- **AWS (Terraform):** S3, Lambda, EventBridge Scheduler, CloudFront, ACM, CloudWatch,
  SNS, Glue, Athena
- **Quality:** pytest, moto, Vitest, Testing Library, Ruff, GitHub Actions

## Data source

Match data and hero assets come from [deadlock-api.com](https://deadlock-api.com). This is
an unofficial personal project and isn't affiliated with Valve. The source's Parquet enum
encoding isn't documented, so the pipeline accepts both integer codes and string labels
and rejects anything else.
