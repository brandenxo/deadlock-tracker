-- Dedup, filter and aggregate match_player rows into per-day hero counters.
-- Reads:   source_rows, already normalized by pipeline/curate.py:
--          match_id BIGINT, start_time/created_at BIGINT (UTC epoch seconds),
--          enums as labels ('UNKNOWN' when unrecognized),
--          not_scored/won BOOLEAN, player_slot/hero_id/duration_s INTEGER.
-- Params:  $players_per_team, $min_dur, $max_dur.
-- Writes:  curated_matches, curated_participants, match_exclusions, hero_daily.

-- Dedup: keep the latest created_at per (match_id, player_slot).
CREATE OR REPLACE TEMP TABLE ranked_rows AS
SELECT *,
       ROW_NUMBER() OVER w AS rn,
       MAX(created_at) OVER (PARTITION BY match_id, player_slot) AS newest_created_at
FROM source_rows
WINDOW w AS (PARTITION BY match_id, player_slot ORDER BY created_at DESC);

-- A tie on the latest created_at between rows that differ can't be resolved.
CREATE OR REPLACE TEMP TABLE ambiguous_matches AS
SELECT DISTINCT match_id
FROM (
    SELECT DISTINCT match_id, player_slot, start_time, duration_s, match_mode, game_mode,
           winning_team, match_outcome, not_scored, team, hero_id, won
    FROM ranked_rows
    WHERE created_at = newest_created_at
)
GROUP BY match_id, player_slot
HAVING COUNT(*) > 1;

CREATE OR REPLACE TEMP TABLE deduped AS
SELECT * EXCLUDE (rn, newest_created_at) FROM ranked_rows WHERE rn = 1;

-- Per-match facts needed by the exclusion rules.
CREATE OR REPLACE TEMP TABLE match_checks AS
SELECT
    match_id,
    COUNT(DISTINCT (start_time, duration_s, match_mode, game_mode, winning_team,
                    match_outcome, not_scored)) AS match_field_variants,
    ANY_VALUE(start_time)    AS start_time,
    ANY_VALUE(duration_s)    AS duration_s,
    ANY_VALUE(match_mode)    AS match_mode,
    ANY_VALUE(game_mode)     AS game_mode,
    ANY_VALUE(winning_team)  AS winning_team,
    ANY_VALUE(match_outcome) AS match_outcome,
    BOOL_OR(not_scored IS TRUE) AS any_not_scored,
    BOOL_OR('UNKNOWN' IN (match_mode, game_mode, winning_team, match_outcome, team))
        AS any_unknown_enum,
    COUNT(*) FILTER (WHERE team = 'Team0') AS team0_rows,
    COUNT(*) FILTER (WHERE team = 'Team1') AS team1_rows,
    COUNT(*) FILTER (WHERE team NOT IN ('Team0', 'Team1')) AS other_team_rows,
    COUNT(*) FILTER (WHERE hero_id IS NULL OR hero_id = 0) AS missing_hero_rows
FROM deduped
GROUP BY match_id;

-- Checks run in order and the first hit is recorded, so reasons never double count.
CREATE OR REPLACE TABLE match_exclusions AS
SELECT match_id, start_time,
       CAST(to_timestamp(start_time) AT TIME ZONE 'UTC' AS DATE) AS match_date_utc,
       reason
FROM (
    SELECT c.match_id, c.start_time,
        CASE
            WHEN a.match_id IS NOT NULL THEN 'ambiguous_duplicate'
            WHEN c.match_field_variants > 1 THEN 'conflicting_match_fields'
            WHEN c.any_unknown_enum THEN 'unknown_enum_value'
            WHEN c.game_mode <> 'Normal' THEN 'ineligible_game_mode'
            WHEN c.match_mode NOT IN ('Unranked', 'Ranked') THEN 'ineligible_match_mode'
            WHEN c.match_outcome <> 'TeamWin' THEN 'not_team_win'
            WHEN c.winning_team NOT IN ('Team0', 'Team1') THEN 'no_playing_winner'
            WHEN c.any_not_scored THEN 'not_scored'
            WHEN c.other_team_rows > 0 THEN 'unexpected_team'
            WHEN c.team0_rows <> $players_per_team OR c.team1_rows <> $players_per_team
                THEN 'incomplete_roster'
            WHEN c.missing_hero_rows > 0 THEN 'missing_hero'
        END AS reason
    FROM match_checks c
    LEFT JOIN ambiguous_matches a USING (match_id)
)
WHERE reason IS NOT NULL;

-- Clean tables: curated_matches has one row per match,
-- curated_participants one per (match_id, player_slot).
CREATE OR REPLACE TABLE curated_matches AS
SELECT
    c.match_id,
    c.start_time,
    CAST(to_timestamp(c.start_time) AT TIME ZONE 'UTC' AS DATE) AS match_date_utc,
    c.duration_s,
    (c.duration_s BETWEEN $min_dur AND $max_dur) AS duration_valid,
    c.winning_team,
    c.match_mode                                  -- kept for ad-hoc ranked/unranked queries
FROM match_checks c
WHERE c.match_id NOT IN (SELECT match_id FROM match_exclusions);

CREATE OR REPLACE TABLE curated_participants AS
SELECT
    d.match_id,
    d.player_slot,
    d.team,
    d.hero_id,
    (d.team = m.winning_team) AS won,             -- from the match winner, not the row flag
    (d.won IS DISTINCT FROM (d.team = m.winning_team)) AS won_flag_disagrees,
    m.match_date_utc                              -- duplicated for date partitioning
FROM deduped d
JOIN curated_matches m USING (match_id);          -- N:1 join, no row fan-out

-- Daily per-hero sums. Rates are derived later, never stored.
CREATE OR REPLACE TABLE hero_daily AS
SELECT
    m.match_date_utc,
    p.hero_id,
    COUNT(*)                                                    AS appearances,
    COUNT(*) FILTER (WHERE p.won)                               AS wins,
    COALESCE(SUM(m.duration_s) FILTER (WHERE m.duration_valid), 0) AS duration_sum_s,
    COUNT(*) FILTER (WHERE m.duration_valid)                    AS duration_count,
    COUNT(DISTINCT p.match_id)                                  AS matches_with_hero
FROM curated_participants p
JOIN curated_matches m USING (match_id)
GROUP BY m.match_date_utc, p.hero_id;
