"""Curation results compared with hand-computed expectations.

fixtures/small_rows.csv holds nine 2v2 matches across two UTC days; each targets a
single rule (duplicate rows, a corrected winner, an errored match, ...). The expected
numbers were derived manually, independent of the SQL.
"""

import duckdb
import pytest

from pipeline import curate
from pipeline.source import UnsupportedSchema
from tests.helpers import FIXTURE_PLAYERS_PER_TEAM, delta_paths, load_fixture, make_source

DAYS = ["2026-10-10", "2026-10-11"]

# hero_id -> (appearances, wins, duration_sum_s, duration_count, matches_with_hero)
HAND_TOTALS = {
    6: (6, 5, 10200, 5, 6),  # Abrams
    15: (6, 3, 10200, 5, 6),  # Bebop
    13: (4, 0, 7800, 4, 4),  # Haze
    14: (6, 3, 10200, 5, 6),  # Holliday
    11: (2, 1, 2400, 1, 2),  # Dynamo
}


@pytest.fixture
def con(tmp_path):
    con = curate.connect(tmp_path)
    load_fixture(con)
    return con


@pytest.fixture
def result(con):
    return curate.curate(con, DAYS, FIXTURE_PLAYERS_PER_TEAM)


def totals(hero_daily):
    out = {}
    for r in hero_daily:
        t = out.setdefault(r["hero_id"], [0, 0, 0, 0, 0])
        for i, k in enumerate(
            ["appearances", "wins", "duration_sum_s", "duration_count", "matches_with_hero"]
        ):
            t[i] += r[k]
    return {h: tuple(v) for h, v in out.items()}


def test_counters_equal_hand_calculation(result):
    assert totals(result.hero_daily) == HAND_TOTALS
    assert result.daily_matches == {"2026-10-10": 2, "2026-10-11": 4}


def test_each_excluded_match_gets_its_first_failing_reason(con, result):
    excluded = dict(con.execute("SELECT match_id, reason FROM match_exclusions").fetchall())
    assert excluded == {
        1006: "not_team_win",
        1007: "incomplete_roster",
        1009: "ineligible_match_mode",
    }


def test_duplicates_collapse_and_corrections_win(con, result):
    # 1003/slot 0 arrives twice; 1005 arrives again with a corrected winner.
    assert con.execute("SELECT COUNT(*) FROM curated_participants").fetchone()[0] == 24
    winner = con.execute(
        "SELECT winning_team FROM curated_matches WHERE match_id = 1005"
    ).fetchone()[0]
    assert winner == "Team0"
    assert result.won_flag_disagreements == 0


def test_late_evening_match_is_bucketed_by_utc_start_date(con, result):
    day = con.execute(
        "SELECT strftime(match_date_utc, '%Y-%m-%d') FROM curated_matches WHERE match_id = 1002"
    ).fetchone()[0]
    assert day == "2026-10-10"  # 23:30 start, arrived after midnight


def test_ambiguous_duplicate_excludes_the_whole_match(tmp_path):
    con = curate.connect(tmp_path)
    load_fixture(con)
    # Conflicting rows with identical key and created_at: no way to pick one.
    con.execute(
        "INSERT INTO source_rows SELECT * REPLACE (7 AS hero_id) FROM source_rows "
        "WHERE match_id = 1001 AND player_slot = 0"
    )
    curate.curate(con, DAYS, FIXTURE_PLAYERS_PER_TEAM)
    reasons = dict(con.execute("SELECT match_id, reason FROM match_exclusions").fetchall())
    assert reasons[1001] == "ambiguous_duplicate"


def test_joining_participants_before_counting_inflates_matches(con, result):
    """Guard against fan-out: COUNT(*) over the joined rows gives players, not matches."""
    wrong = con.execute(
        "SELECT COUNT(*) FROM curated_matches JOIN curated_participants USING (match_id)"
    ).fetchone()[0]
    right = con.execute("SELECT COUNT(*) FROM curated_matches").fetchone()[0]
    assert (right, wrong) == (6, 24)


def test_window_drops_dates_outside_it(con):
    result = curate.curate(con, ["2026-10-11"], FIXTURE_PLAYERS_PER_TEAM)
    assert set(result.daily_matches) == {"2026-10-11"}


def test_both_physical_encodings_give_identical_counters(tmp_path):
    outputs = []
    for encoding in ("int", "label"):
        make_source(tmp_path / encoding, encoding=encoding)
        con = curate.connect(tmp_path / f"w-{encoding}")
        curate.load_raw(con, delta_paths(tmp_path / encoding))
        outputs.append(curate.curate(con, ["2026-10-05", "2026-10-06"]).hero_daily)
    assert outputs[0] and outputs[0] == outputs[1]


def test_unsupported_physical_type_stops_the_run(tmp_path):
    path = tmp_path / "bad.parquet"
    duckdb.sql(
        "COPY (SELECT 1::UBIGINT AS match_id, 1.5::DOUBLE AS start_time,"
        " 1::UINTEGER AS duration_s,"
        " 'Ranked' AS match_mode, 'Normal' AS game_mode, 'Team0' AS winning_team,"
        " 'TeamWin' AS match_outcome, false AS not_scored, 0::UINTEGER AS player_slot,"
        " 'Team0' AS team, 1::UTINYINT AS hero_id, true AS won, 1::UINTEGER AS created_at)"
        f" TO '{path}' (FORMAT parquet)"
    )
    with pytest.raises(UnsupportedSchema, match="start_time"):
        curate.load_raw(curate.connect(tmp_path), [path])


def test_match_id_too_large_for_bigint_is_rejected(tmp_path):
    make_source(tmp_path / "src", first_match_id=2**63, hours=1)
    with pytest.raises(UnsupportedSchema, match="BIGINT"):
        curate.load_raw(curate.connect(tmp_path / "w"), delta_paths(tmp_path / "src"))
