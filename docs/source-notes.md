# Source notes

What's known about the [Deadlock API data dumps](https://deadlock-api.com/data-dumps),
how it was checked, and what's still open. Update the dates when you re-check.

## Known (from the public manifest)

- Public, no credentials. Manifest: `https://data.deadlock-api.com/v1/manifest.json`.
- `match_player` is incremental. Files are `base`, `residual` or hourly `delta`;
  deltas carry `lo`/`hi`, the `created_at` range they hold, in Unix epoch seconds.
- Object keys embed a build time and a hash, so a key names one immutable object.
- Match-level columns repeat on every player row (the table is denormalized).
- Upstream occasionally folds a few minutes of hourly files into its multi-GB base
  files, leaving a hole the deltas can't fill (8 minutes on 2026-10-17). That's why a
  covered day may be missing up to 30 minutes.

## Measured from real files (80 delta objects, 2026-10-16 15:15 to 2026-10-19 00:15 UTC)

Checked 2026-10-19 with DuckDB over `data/real/raw/objects/*/rows.parquet`.

- **Physical types:** enums (`match_mode`, `game_mode`, `winning_team`, `match_outcome`,
  `team`) are `VARCHAR` labels; `start_time` and `created_at` are
  `TIMESTAMP WITH TIME ZONE`; `match_id` is `UBIGINT`, `hero_id` `UTINYINT`. Identical in
  all 80 objects.
- **Rows split across files:** only 6 of 80 objects have a row count that's a multiple
  of 12, so a match's rows are often spread over several files. Dedup handles it.
- **Team size:** Normal matches have 6 players per team (762,483 team rosters). Street
  Brawl has 4, which is one reason it's excluded. Normal rosters with 1, 2 or 5 players
  also appear and are excluded as `incomplete_roster`.
- **`won` flag:** 0 disagreements with `team = winning_team` in the live summary
  (6.4M source rows).

## Late data: why the settle lag is 24 hours

Measured 2026-10-19 from all raw objects in S3 (96 deltas, 2026-10-16 15:15 to
2026-10-19 13:57 UTC). Counted: Normal, ranked or unranked matches with all 12 rows,
and when the last of those rows arrived.

| Complete by (after the day ends) | 2026-10-17 | 2026-10-18 |
|---|---|---|
| 6 h (the original settle lag) | 77.7% | ≥ 92.6% |
| 12 h | 83.2% | ≥ 97.9% |
| 24 h (the current settle lag) | 94.0% | not yet measurable |
| 36 h | 99.1% | not yet measurable |

Shares are of what had arrived by the end of the held data, about 38 h after 2026-10-17
ended and 14 h after 2026-10-18 ended. So they're upper bounds, and 2026-10-17 was still
gaining rows at 38 h.

Lateness varies a lot between days. With a 6-hour lag, a bad day was first published
about 22% short. Each run rebuilds the window, so published days are revised upward as
late rows arrive, but the first numbers were misleading. The lag is now 24 hours: the
dashboard's newest day is two days old, and on a bad day like 2026-10-17 the first
published count is about 6% short instead of 22%.

Rates (win, pick) are only unaffected by late rows if late matches look like on-time
ones. That hasn't been checked.

## Hero names

- `match_player` has only `hero_id`. Names, roles (`hero_type`) and portraits come from
  `https://api.deadlock-api.com/v1/assets/heroes`. The live summary resolved all 43
  heroes seen.
- `fixtures/heroes.json` holds 16 real heroes for offline work.

## Decisions

- Download only `delta` objects, newest first, under a per-run byte cap. Never `base`
  files (single base files are ~11 GB).
- Never read `account_id`.

## Still to check

| Question | How to check |
|---|---|
| Are late-arriving matches different (rank, mode, outcome)? | compare rates for on-time vs late matches on one day |
| Settle lag value | repeat the table above over more days, then set `DT_SETTLE_LAG_HOURS` |
| Terms of use, attribution, rate limits | ask the maintainers |
