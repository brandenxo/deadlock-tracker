"""Generate a fake source directory for offline development and tests.

Layout and quirks match the real data lake (manifest, hourly created_at deltas,
12 rows per match, late arrivals, duplicates, corrected winners). The numbers are
random and say nothing about the actual game.

Both plausible Parquet encodings are supported, since the real one isn't documented:
  "int"   - enums as UTINYINT codes, times as UINTEGER epoch seconds
  "label" - enums as VARCHAR labels, times as TIMESTAMP
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from pipeline import contract

# Ids from fixtures/heroes.json, so offline runs still get real names.
HERO_IDS = [6, 7, 10, 11, 12, 13, 14, 15, 19, 25, 27, 31, 35, 52, 64, 69]
COPRIME_STEPS = [1, 3, 5, 7, 9, 11, 13, 15]  # coprime with 16: each step cycles every slot
# Made-up per-hero bias (-1.2 to +1.2 points) so fake win rates aren't flat at 50%.
STRENGTH = {h: ((i * 7) % 13 - 6) * 0.002 for i, h in enumerate(HERO_IDS)}


@dataclass(frozen=True)
class SyntheticSpec:
    out_dir: Path
    start_epoch: int  # earliest match start
    hours: int  # span of match starts
    matches_per_hour: int = 40
    first_match_id: int = 114_000_000
    seed: float = 0.42
    encoding: str = "int"
    manifest_version: int = 900
    tail_hours: int = 6  # extra delta hours after the last start


def _stamp(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, UTC).strftime("%Y%m%dT%H%M%SZ")


def _enum_sql(column: str, encoding: str, value_sql: str) -> str:
    """Wrap a label-producing expression in the chosen physical encoding."""
    if encoding == "label":
        return f"{value_sql} AS {column}"
    codes = {label: code for code, label in contract.ENUMS[column].items()}
    whens = " ".join(f"WHEN '{label}' THEN {code}" for label, code in codes.items())
    return f"CAST(CASE {value_sql} {whens} END AS UTINYINT) AS {column}"


def _time_sql(column: str, encoding: str, value_sql: str) -> str:
    if encoding == "label":
        return f"CAST(to_timestamp({value_sql}) AT TIME ZONE 'UTC' AS TIMESTAMP) AS {column}"
    return f"CAST({value_sql} AS UINTEGER) AS {column}"


def generate(spec: SyntheticSpec) -> dict:
    """Write a manifest and delta Parquet files to spec.out_dir; return the manifest."""
    if spec.encoding not in ("int", "label"):
        raise ValueError("encoding must be 'int' or 'label'")
    con = duckdb.connect(config={"threads": 1})  # 1 thread keeps random() reproducible
    con.execute("SELECT setseed(?)", [spec.seed])
    n = spec.hours * spec.matches_per_hour
    span = spec.hours * 3600
    con.execute(
        f"""
        CREATE TABLE m AS
        SELECT
            i AS idx,
            CAST({spec.first_match_id} + i AS UBIGINT) AS match_id,
            CAST({spec.start_epoch} + floor(i * {span} / {n}) AS BIGINT) AS start_time,
            CAST(900 + floor(random() * 1800) AS INTEGER) AS duration_s,
            random() AS r_mode, random() AS r_outcome, random() AS r_win, random() AS r_lag,
            random() AS r_late, random() AS r_fix, random() AS r_drop, random() AS r_hero,
            random() AS r_step, random() AS r_score
        FROM range({n}) t(i)
        """
    )
    steps = "[" + ", ".join(str(s) for s in COPRIME_STEPS) + "]"
    hero_ids = "[" + ", ".join(str(h) for h in HERO_IDS) + "]"
    strengths = ", ".join(f"({h}, {s})" for h, s in STRENGTH.items())
    con.execute(
        f"""
        CREATE TABLE logical AS
        WITH base AS (
            SELECT m.*,
                CASE WHEN r_mode < 0.05 THEN 'StreetBrawl' ELSE 'Normal' END AS game_mode,
                CASE WHEN r_mode BETWEEN 0.05 AND 0.09 THEN 'PrivateLobby'
                     WHEN r_mode BETWEEN 0.09 AND 0.10 THEN 'CoopBot'
                     WHEN r_mode < 0.55 THEN 'Ranked' ELSE 'Unranked' END AS match_mode,
                CASE WHEN r_outcome < 0.02 THEN 'Error' ELSE 'TeamWin' END AS match_outcome,
                (r_score < 0.005) AS not_scored,
                -- ~30 min after the match ends usually, 1-3 days for 2% of rows
                CAST(start_time + duration_s + 120 + floor(-ln(1 - r_lag) * 1800)
                     + CASE WHEN r_late < 0.02 THEN 86400 + floor(r_late * 100 * 86400) ELSE 0 END
                     AS BIGINT) AS created_at,
                CAST(floor(r_hero * {len(HERO_IDS)}) AS INTEGER) AS hero_offset,
                list_extract({steps}, 1 + CAST(floor(r_step * {len(COPRIME_STEPS)}) AS INTEGER))
                    AS hero_step
            FROM m
        ),
        seated AS (
            SELECT b.*, s.slot AS player_slot,
                   CASE WHEN s.slot < 6 THEN 'Team0' ELSE 'Team1' END AS team,
                   list_extract({hero_ids}, 1 + ((hero_offset + s.slot * hero_step)
                                               % {len(HERO_IDS)})) AS hero_id
            FROM base b CROSS JOIN range(12) s(slot)
            WHERE NOT (r_drop < 0.01 AND s.slot = 11)          -- drop a player in 1% of matches
        ),
        edges AS (  -- strength difference, Team0 minus Team1
            SELECT match_id,
                   SUM(CASE team WHEN 'Team0' THEN st.strength ELSE -st.strength END) AS edge
            FROM seated JOIN (VALUES {strengths}) st(hero_id, strength) USING (hero_id)
            GROUP BY match_id
        ),
        players AS (
            SELECT seated.*,
                   CASE WHEN r_win < 0.5 + edge THEN 'Team0' ELSE 'Team1' END AS true_winner
            FROM seated JOIN edges USING (match_id)
        ),
        first_delivery AS (
            -- 1%: first delivered with the wrong winner, fixed in a later row.
            SELECT *, CASE WHEN r_fix < 0.01
                           THEN CASE true_winner WHEN 'Team0' THEN 'Team1' ELSE 'Team0' END
                           ELSE true_winner END AS winning_team
            FROM players
        ),
        corrections AS (
            SELECT * REPLACE (created_at + 7200 AS created_at), true_winner AS winning_team
            FROM players WHERE r_fix < 0.01
        ),
        duplicates AS (
            -- 1%: exact duplicate delivery (same created_at)
            SELECT *, true_winner AS winning_team FROM players
            WHERE r_fix >= 0.01 AND r_drop BETWEEN 0.5 AND 0.51
        )
        SELECT match_id, start_time, duration_s, match_mode, game_mode, winning_team,
               match_outcome, not_scored, player_slot, team, hero_id,
               (team = winning_team) AS won, created_at
        FROM (SELECT * FROM first_delivery
              UNION ALL SELECT * FROM corrections
              UNION ALL SELECT * FROM duplicates)
        """
    )
    extra = ", CAST(1000 + player_slot AS UINTEGER) AS account_id"  # ingest drops it
    select_physical = (
        ", ".join(
            [
                "match_id",
                _time_sql("start_time", spec.encoding, "start_time"),
                "CAST(duration_s AS UINTEGER) AS duration_s",
                _enum_sql("match_mode", spec.encoding, "match_mode"),
                _enum_sql("game_mode", spec.encoding, "game_mode"),
                _enum_sql("winning_team", spec.encoding, "winning_team"),
                _enum_sql("match_outcome", spec.encoding, "match_outcome"),
                "not_scored",
                "CAST(player_slot AS UINTEGER) AS player_slot",
                _enum_sql("team", spec.encoding, "team"),
                "CAST(hero_id AS UTINYINT) AS hero_id",
                "won",
                _time_sql("created_at", spec.encoding, "created_at"),
            ]
        )
        + extra
    )

    first_lo = (spec.start_epoch // 3600) * 3600
    # Treat this as "now" for the fake source; later rows don't exist yet.
    cutoff = ((spec.start_epoch + span) // 3600 + spec.tail_hours) * 3600
    delta_dir = spec.out_dir / "v1" / "tables" / "match_player" / "g2" / "delta"
    delta_dir.mkdir(parents=True, exist_ok=True)
    files = []
    lo = first_lo
    while lo < cutoff:
        hi = lo + 3600
        tmp = delta_dir / "tmp.parquet"
        con.execute(
            f"COPY (SELECT {select_physical} FROM logical WHERE created_at >= {lo} "
            f"AND created_at < {hi} ORDER BY match_id, player_slot) TO '{tmp.as_posix()}' "
            "(FORMAT parquet, COMPRESSION zstd)"
        )
        files.append(_register_delta(con, tmp, delta_dir, lo, hi))
        lo = hi
    manifest = {
        "_synthetic": "SYNTHETIC source generated by pipeline/synthetic.py",
        "format_version": 1,
        "version": spec.manifest_version,
        "generated_at": datetime.fromtimestamp(cutoff, UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "public_url": "synthetic",
        "last_fold_at": None,
        "tables": {
            "match_player": {
                "policy": "incremental",
                "status": "ready",
                "watermark": "created_at",
                "partition_expr": "intDiv(match_id, 1000000)",
                "generation": 2,
                "columns": [
                    {"name": c, "type": contract.EXPECTED_MANIFEST_TYPES[c]}
                    for c in contract.SOURCE_COLUMNS
                ]
                + [{"name": "account_id", "type": "UInt32", "comment": "steam id3"}],
                "watermark_hi": files[-1]["hi"] if files else None,
                "files": files,
            }
        },
    }
    (spec.out_dir / "v1").mkdir(parents=True, exist_ok=True)
    (spec.out_dir / "v1" / "manifest.json").write_text(json.dumps(manifest, indent=1))
    con.close()
    return manifest


def _register_delta(con, tmp: Path, delta_dir: Path, lo: int, hi: int, salt: str = "") -> dict:
    digest = hashlib.sha256(tmp.read_bytes() + salt.encode()).hexdigest()[:12]
    name = f"{_stamp(lo)}-{_stamp(hi)}-{digest}.parquet"
    final = delta_dir / name
    tmp.rename(final)
    rows_by_partition = dict(
        con.execute(
            "SELECT CAST(match_id // 1000000 AS VARCHAR), COUNT(*) FROM read_parquet(?) GROUP BY 1",
            [str(final)],
        ).fetchall()
    )
    rows = sum(rows_by_partition.values())
    return {
        "key": f"v1/tables/match_player/g2/delta/{name}",
        "kind": "delta",
        "generation": 2,
        "lo": lo,
        "hi": hi,
        "rows": rows,
        "bytes": final.stat().st_size,
        "rows_by_partition": rows_by_partition,
        "built_at": datetime.fromtimestamp(hi + 600, UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
