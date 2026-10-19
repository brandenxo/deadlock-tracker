# Data contract

Enforced by `pipeline/contract.py`, `pipeline/curate.py`, `pipeline/sql/curate.sql`,
`pipeline/coverage.py` and `pipeline/summary.py`.

## What we read: `match_player`, 13 of ~150 columns

| Column | Manifest type | Used as | Notes |
|---|---|---|---|
| match_id | UInt64 | BIGINT | values ≥ 2^63 stop the run instead of wrapping |
| start_time | DateTime | epoch seconds, UTC | its UTC date is the match's day |
| duration_s | UInt32 | INTEGER | 1 s to 4 h counts toward average length |
| match_mode | Enum8 | label | Ranked or Unranked |
| game_mode | Enum8 | label | Normal |
| winning_team | Enum8 | label | Team0 or Team1 |
| match_outcome | Enum8 | label | TeamWin |
| not_scored | Nullable(Bool) | BOOLEAN | `true` excludes the match |
| player_slot | UInt32 | INTEGER | with match_id, identifies a row |
| team | Enum8 | label | Team0 or Team1 |
| hero_id | UInt8 | INTEGER | 0 = missing |
| won | Bool | check only | compared with `team = winning_team`; disagreements are counted |
| created_at | DateTime | epoch seconds | when the source ingested the row; newest wins in dedup |

`account_id` is never read. Any change to these manifest types stops the run before
anything is downloaded.

The physical Parquet encoding isn't documented. The real files hold enums as `VARCHAR`
labels and times as `TIMESTAMP WITH TIME ZONE` (see `source-notes.md`). Curation also
accepts integer codes and integer epochs, and stops the run on anything else.

## Rules

- **Dedup:** one row per (match_id, player_slot), newest `created_at` wins. If two
  *different* rows share the newest `created_at`, the whole match is excluded
  (`ambiguous_duplicate`): we can't tell which is right.
- **Eligible match:** passes every check, in this order (the first failure is the
  reason recorded): ambiguous_duplicate, conflicting_match_fields, unknown_enum_value,
  ineligible_game_mode, ineligible_match_mode, not_team_win, no_playing_winner,
  not_scored, unexpected_team, incomplete_roster (not exactly 6 per team), missing_hero.
- **Winner:** `won` in the curated tables is `team = winning_team`, not the source's
  row flag.
- **Covered date:** the held raw objects reach the end of the UTC day plus a 24-hour
  settle lag, with at most 30 minutes missing in total. Only covered dates are published.
  Allowed gaps are reported per day in `coverage.gap_minutes_by_date`.
- **Validation (before publishing):** for every covered day, appearances = 12 × matches
  and wins = 6 × matches; fewer than 1% of matches may have unknown enum values. Any
  failure publishes nothing.

## Metrics (computed in the browser from additive daily counters)

- **Win rate** = Σ wins / Σ appearances over the selected dates. Never a mean of daily rates.
- **Pick rate** = Σ matches with the hero / Σ eligible matches.
- **Average length** = Σ duration of valid-duration appearances / their count.
- **Tier** = from the 95% Wilson interval of the win rate, for heroes with ≥ 100 games.
- **Match mode filter:** each sum is over the chosen mode's rows; "All matches" sums both.
- A zero denominator is shown as "—", never 0%.

## `data/summary.json` (schema_version 2)

Schema 2 splits every counter by `match_mode` (`Ranked` or `Unranked`): `daily_matches`
has one row per (date, mode), and `hero_daily` one per (date, mode, hero). Validation
checks 12 appearances and 6 wins per match for each mode separately. The dashboard still
reads schema 1, which has no `match_mode`, and hides the mode toggle for it.

Abbreviated from a local run over real data on 2026-10-19 (one day, one hero shown):

```json
{
  "schema_version": 2,
  "built_at": "2026-10-19T15:05:31Z",
  "source": { "manifest_version": 860, "manifest_generated_at": "2026-10-19T14:15:54Z" },
  "coverage": {
    "settle_lag_hours": 24.0,
    "status_by_date": { "2026-10-16": "partial", "2026-10-17": "covered", "2026-10-18": "partial", "...": "..." },
    "covered_dates": ["2026-10-17"],
    "gap_minutes_by_date": { "2026-10-17": 8 }
  },
  "players_per_team": 6,
  "daily_matches": [
    { "date": "2026-10-17", "match_mode": "Ranked", "eligible_matches": 18084 },
    { "date": "2026-10-17", "match_mode": "Unranked", "eligible_matches": 80856 }
  ],
  "hero_daily": [
    { "date": "2026-10-17", "match_mode": "Ranked", "hero_id": 1, "appearances": 6937, "wins": 3383,
      "duration_sum_s": 15050426, "duration_count": 6937, "matches_with_hero": 6937 },
    { "date": "2026-10-17", "match_mode": "Unranked", "hero_id": 1, "appearances": 25598, "wins": 12848,
      "duration_sum_s": 56665290, "duration_count": 25598, "matches_with_hero": 25598 }
  ],
  "heroes": { "1": { "name": "Infernus", "type": "marksman", "image": "https://assets-bucket.deadlock-api.com/..." } },
  "excluded_matches": { "incomplete_roster": 113, "ineligible_game_mode": 20311,
                        "ineligible_match_mode": 1380, "no_playing_winner": 2, "not_scored": 21 },
  "quality": { "source_rows": 5340636, "won_flag_disagreements": 0 }
}
```

`heroes` maps each `hero_id` in `hero_daily` (as a string) to its name, role and portrait
URL, or to `{"name": "Hero <id>", "type": null, "image": null}` when the hero list was
unavailable.

## Curated Parquet (for Athena)

Defined for Athena in `infra/athena.tf`; the columns there must match `CURATED_TABLES` in
`pipeline/curate.py`. Every date in the window is written, including partial ones, so
filter on `summary.json`'s `covered_dates` when a query needs complete days.

- `curated/matches/match_date_utc=<D>/part-0.parquet`: match_id, start_time, duration_s,
  duration_valid, winning_team, match_mode.
- `curated/participants/match_date_utc=<D>/part-0.parquet`: match_id, player_slot, team,
  hero_id, won (derived as team = winning_team).
