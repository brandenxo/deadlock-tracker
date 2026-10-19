"""Turn stored raw rows into clean, typed tables and daily hero counters.

Steps: read all held rows.parquet files as one relation (columns matched by name),
coerce each column to one canonical type (files may encode enums/times differently),
run sql/curate.sql, then drop anything whose UTC match date is outside the window.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import duckdb

from pipeline import contract
from pipeline.source import UnsupportedSchema

SQL_FILE = Path(__file__).resolve().parent / "sql" / "curate.sql"
INTEGER_TYPES = {
    "TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT",
    "UTINYINT", "USMALLINT", "UINTEGER", "UBIGINT", "UHUGEINT",
}  # fmt: skip


def connect(workdir: Path) -> duckdb.DuckDBPyConnection:
    """Open DuckDB with writable dirs under workdir and extension auto-install off."""
    (workdir / "duckdb_tmp").mkdir(parents=True, exist_ok=True)
    config = {
        "home_directory": str(workdir),  # HOME isn't writable on Lambda
        "temp_directory": str(workdir / "duckdb_tmp"),  # spill target
        "autoload_known_extensions": False,
        "autoinstall_known_extensions": False,
    }
    # DuckDB defaults to 80% of RAM, which left the 3 GB function ~150 MB from an OOM
    # kill. 60% leaves room for Python; larger windows spill to disk instead.
    lambda_mb = os.environ.get("AWS_LAMBDA_FUNCTION_MEMORY_SIZE")
    if lambda_mb:
        config["memory_limit"] = f"{int(lambda_mb) * 6 // 10}MB"
    return duckdb.connect(config=config)


# --- loading and type normalization ----------------------------------------------------


def _base(duckdb_type: str) -> str:
    return duckdb_type.split("(")[0].upper()


def _epoch(column: str, t: str) -> str:
    if _base(t) in INTEGER_TYPES:
        return f'CAST("{column}" AS BIGINT)'
    if _base(t).startswith("TIMESTAMP"):
        return f'CAST(epoch("{column}") AS BIGINT)'  # naive timestamps are UTC
    raise UnsupportedSchema(f"{column}: unsupported type {t}")


def _enum(column: str, t: str) -> str:
    mapping = contract.ENUMS[column]
    if _base(t) in INTEGER_TYPES:
        whens = " ".join(f"WHEN {code} THEN '{label}'" for code, label in mapping.items())
        return f"CASE \"{column}\" {whens} ELSE '{contract.UNKNOWN_LABEL}' END"
    if _base(t) in ("VARCHAR", "ENUM"):
        labels = ", ".join(f"'{label}'" for label in mapping.values())
        return (
            f'CASE WHEN CAST("{column}" AS VARCHAR) IN ({labels}) '
            f"THEN CAST(\"{column}\" AS VARCHAR) ELSE '{contract.UNKNOWN_LABEL}' END"
        )
    raise UnsupportedSchema(f"{column}: unsupported type {t}")


def _bool(column: str, t: str) -> str:
    if _base(t) == "BOOLEAN":
        return f'"{column}"'
    if _base(t) in INTEGER_TYPES:
        return f'("{column}" <> 0)'
    raise UnsupportedSchema(f"{column}: unsupported type {t}")


def normalize_sql(types: dict[str, str]) -> str:
    """Build the SELECT list that maps raw_rows' physical types to canonical ones."""
    exprs = {
        "match_id": 'CAST("match_id" AS BIGINT)',
        "start_time": _epoch("start_time", types["start_time"]),
        "duration_s": 'CAST("duration_s" AS INTEGER)',
        "not_scored": _bool("not_scored", types["not_scored"]),
        "player_slot": 'CAST("player_slot" AS INTEGER)',
        "hero_id": 'CAST("hero_id" AS INTEGER)',
        "won": _bool("won", types["won"]),
        "created_at": _epoch("created_at", types["created_at"]),
    }
    for column in contract.ENUM_COLUMNS:
        exprs[column] = _enum(column, types[column])
    return ",\n    ".join(f"{exprs[c]} AS {c}" for c in contract.SOURCE_COLUMNS)


def load_raw(con: duckdb.DuckDBPyConnection, paths: list[Path]) -> None:
    """Load the given Parquet files into a normalized source_rows table."""
    if not paths:
        con.execute(
            "CREATE OR REPLACE TEMP TABLE source_rows (match_id BIGINT, start_time BIGINT, "
            "duration_s INTEGER, match_mode VARCHAR, game_mode VARCHAR, winning_team VARCHAR, "
            "match_outcome VARCHAR, not_scored BOOLEAN, player_slot INTEGER, team VARCHAR, "
            "hero_id INTEGER, won BOOLEAN, created_at BIGINT)"
        )
        return
    # DuckDB views can't bind parameters. Paths are our own, but quotes are escaped anyway.
    files = ", ".join("'" + p.as_posix().replace("'", "''") + "'" for p in paths)
    con.execute(
        f"CREATE OR REPLACE TEMP VIEW raw_rows AS "
        f"SELECT * FROM read_parquet([{files}], union_by_name = true)"
    )
    types = dict(con.execute("SELECT column_name, column_type FROM (DESCRIBE raw_rows)").fetchall())
    max_id = con.execute("SELECT MAX(match_id) FROM raw_rows").fetchone()[0]
    if max_id is not None and max_id > contract.MAX_MATCH_ID:
        raise UnsupportedSchema(f"match_id {max_id} does not fit in BIGINT")
    con.execute(
        f"CREATE OR REPLACE TEMP TABLE source_rows AS SELECT {normalize_sql(types)} FROM raw_rows"
    )


# --- curation ----------------------------------------------------------------------------


def run_sql(con: duckdb.DuckDBPyConnection, players_per_team: int) -> None:
    """Execute sql/curate.sql statement by statement over source_rows."""
    params = {
        "players_per_team": players_per_team,
        "min_dur": contract.MIN_VALID_DURATION_S,
        "max_dur": contract.MAX_VALID_DURATION_S,
    }
    # Strip comment lines so "$name" in prose isn't bound as a parameter. Naive ';'
    # splitting is fine because no string literal in the file contains one.
    lines = [ln for ln in SQL_FILE.read_text().splitlines() if not ln.lstrip().startswith("--")]
    for statement in filter(None, (s.strip() for s in "\n".join(lines).split(";"))):
        used = {k: v for k, v in params.items() if f"${k}" in statement}
        con.execute(statement, used or None)


@dataclass
class Curation:
    source_rows: int
    hero_daily: list[dict]  # one row per (date, match_mode, hero)
    daily_matches: dict[str, dict[str, int]]  # date -> match_mode -> eligible match count
    exclusions: dict[str, dict[str, int]]  # date -> reason -> match count
    won_flag_disagreements: int


def _rows(con, sql: str) -> list[dict]:
    cursor = con.execute(sql)
    names = [d[0] for d in cursor.description]
    return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]


def curate(
    con: duckdb.DuckDBPyConnection,
    window: list[str],
    players_per_team: int = contract.PLAYERS_PER_TEAM,
) -> Curation:
    source_rows = con.execute("SELECT COUNT(*) FROM source_rows").fetchone()[0]
    run_sql(con, players_per_team)
    con.execute(
        "CREATE OR REPLACE TEMP TABLE window_dates AS SELECT unnest(?::DATE[]) AS d", [window]
    )
    for table in ("curated_matches", "curated_participants", "match_exclusions", "hero_daily"):
        con.execute(f"DELETE FROM {table} WHERE match_date_utc NOT IN (SELECT d FROM window_dates)")

    exclusions: dict[str, dict[str, int]] = {}
    for row in _rows(
        con,
        "SELECT strftime(match_date_utc, '%Y-%m-%d') AS d, reason, COUNT(*) AS n "
        "FROM match_exclusions GROUP BY ALL ORDER BY ALL",
    ):
        exclusions.setdefault(row["d"], {})[row["reason"]] = row["n"]
    daily_matches: dict[str, dict[str, int]] = {}
    for row in _rows(
        con,
        "SELECT strftime(match_date_utc, '%Y-%m-%d') AS d, match_mode, COUNT(*) AS n "
        "FROM curated_matches GROUP BY ALL ORDER BY ALL",
    ):
        daily_matches.setdefault(row["d"], {})[row["match_mode"]] = row["n"]
    return Curation(
        source_rows=source_rows,
        hero_daily=_rows(
            con,
            "SELECT strftime(match_date_utc, '%Y-%m-%d') AS date, match_mode, hero_id, "
            "appearances, wins, duration_sum_s, duration_count, matches_with_hero "
            "FROM hero_daily ORDER BY 1, 2, 3",
        ),
        daily_matches=daily_matches,
        exclusions=exclusions,
        won_flag_disagreements=con.execute(
            "SELECT COUNT(*) FROM curated_participants WHERE won_flag_disagrees"
        ).fetchone()[0],
    )


CURATED_TABLES = {
    "matches": "SELECT match_id, start_time, duration_s, duration_valid, winning_team, "
    "match_mode, match_date_utc FROM curated_matches",
    "participants": "SELECT match_id, player_slot, team, hero_id, won, match_date_utc "
    "FROM curated_participants",
}


def write_curated(con: duckdb.DuckDBPyConnection, out_dir: Path) -> list[Path]:
    """Write curated tables as out_dir/<table>/match_date_utc=YYYY-MM-DD/part-0.parquet.

    The date-partitioned layout is what Athena expects for ad-hoc SQL."""
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    for table, select in CURATED_TABLES.items():
        con.execute(
            f"COPY ({select} ORDER BY match_id) TO '{(out_dir / table).as_posix()}' "
            "(FORMAT parquet, COMPRESSION zstd, PARTITION_BY (match_date_utc), "
            "FILENAME_PATTERN 'part-{i}', OVERWRITE_OR_IGNORE true)"
        )
    return sorted(out_dir.rglob("*.parquet"))
