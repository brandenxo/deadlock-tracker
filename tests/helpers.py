"""Fixtures and builders used across test modules."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import duckdb

from pipeline.synthetic import SyntheticSpec, generate

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
FIXTURE = FIXTURES / "small_rows.csv"
HEROES_FIXTURE = FIXTURES / "heroes.json"
FIXTURE_PLAYERS_PER_TEAM = 2  # 2v2 keeps hand-checked totals small


def load_fixture(con: duckdb.DuckDBPyConnection, path: Path = FIXTURE) -> None:
    """Populate source_rows from fixtures/small_rows.csv (already canonical types)."""
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE source_rows AS
        SELECT CAST(match_id AS BIGINT) AS match_id,
               CAST(epoch(CAST(start_time AS TIMESTAMPTZ)) AS BIGINT) AS start_time,
               CAST(duration_s AS INTEGER) AS duration_s,
               match_mode, game_mode, winning_team, match_outcome,
               CAST(NULLIF(not_scored, '') AS BOOLEAN) AS not_scored,
               CAST(player_slot AS INTEGER) AS player_slot,
               team,
               CAST(hero_id AS INTEGER) AS hero_id,
               CAST(NULLIF(won, '') AS BOOLEAN) AS won,
               CAST(epoch(CAST(created_at AS TIMESTAMPTZ)) AS BIGINT) AS created_at
        FROM read_csv('{path.as_posix()}', header = true, all_varchar = true)
        """
    )


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


START = utc("2026-10-05T00:00:00")
NOW = utc("2026-10-07T06:30:00")  # Oct 5 and 6 are complete at this point


def make_source(root: Path, **overrides) -> dict:
    """Fake source with 48 h of matches from 2026-10-05 00:00 UTC."""
    spec = SyntheticSpec(
        out_dir=root,
        start_epoch=int(START.timestamp()),
        **{"hours": 48, "matches_per_hour": 6, **overrides},
    )
    return generate(spec)


def delta_paths(root: Path) -> list[Path]:
    return sorted((root / "v1/tables/match_player/g2/delta").glob("*.parquet"))
