"""Source schema expectations, enum decoding, and match eligibility rules.

Names, types and enum codes mirror the match_player schema in manifest v629
(checked 2026-10-12). The Parquet encoding of enums isn't documented: files may hold
integer codes or label strings, so curation handles both and rejects anything else.
"""

TABLE = "match_player"

# Columns kept from match_player (~150 total). account_id is intentionally absent;
# nothing here is per-player.
SOURCE_COLUMNS = [
    "match_id",
    "start_time",
    "duration_s",
    "match_mode",
    "game_mode",
    "winning_team",
    "match_outcome",
    "not_scored",
    "player_slot",
    "team",
    "hero_id",
    "won",
    "created_at",
]

ENUMS = {
    "match_mode": {
        0: "Invalid",
        1: "Unranked",
        2: "PrivateLobby",
        3: "CoopBot",
        4: "Ranked",
        5: "ServerTest",
        6: "Tutorial",
        7: "HeroLabs",
        8: "NewPlayerPlacement",
    },
    "game_mode": {
        0: "Invalid",
        1: "Normal",
        2: "OneVsOneTest",
        3: "Sandbox",
        4: "StreetBrawl",
        5: "ExploreNYC",
        6: "Internal",
    },
    "winning_team": {0: "Team0", 1: "Team1", 16: "Spectator"},
    "team": {0: "Team0", 1: "Team1", 16: "Spectator"},
    "match_outcome": {0: "TeamWin", 1: "Error", 2: "Draw"},
}
ENUM_COLUMNS = list(ENUMS)
UNKNOWN_LABEL = "UNKNOWN"


def _enum_type(column: str) -> str:
    pairs = ", ".join(f"'{label}' = {code}" for code, label in ENUMS[column].items())
    return f"Enum8({pairs})"


# Exact manifest type strings for the kept columns. Any mismatch aborts the run before
# downloads start; a changed type means the meaning may have changed too.
EXPECTED_MANIFEST_TYPES = {
    "match_id": "UInt64",
    "start_time": "DateTime",
    "duration_s": "UInt32",
    "match_mode": _enum_type("match_mode"),
    "game_mode": _enum_type("game_mode"),
    "winning_team": _enum_type("winning_team"),
    "match_outcome": _enum_type("match_outcome"),
    "not_scored": "Nullable(Bool)",
    "player_slot": "UInt32",
    "team": _enum_type("team"),
    "hero_id": "UInt8",
    "won": "Bool",
    "created_at": "DateTime",
}

# Eligibility. Team size comes from observed data (row counts are mostly multiples
# of 12), not from documentation.
PLAYERS_PER_TEAM = 6
MIN_VALID_DURATION_S = 1
MAX_VALID_DURATION_S = 4 * 60 * 60  # only gates the avg-length metric

# Source ids are UInt64 but curated tables use BIGINT; larger ids fail loudly.
MAX_MATCH_ID = 2**63 - 1

# Rebuild window and day-completeness rules.
WINDOW_DAYS = 7
# Late rows keep arriving after midnight. Measured 2026-10-17: 83% of matches complete
# 6 h after the day ended, 99.8% after 24 h (docs/source-notes.md).
SETTLE_LAG_S = 24 * 60 * 60
MAX_COVERAGE_GAP_S = 30 * 60  # total source hole allowed per day
MAX_UNKNOWN_ENUM_SHARE = 0.01  # above this, assume the codes changed
