"""What we read from the source, how we decode it, and which matches count.

Column names, types and enum codes come from the match_player schema in the public
manifest (version 629, read 2026-10-12). How enums are physically stored in the
Parquet files (integer codes or label strings) is not documented, so curation accepts
both and rejects anything else.
"""

TABLE = "match_player"

# The 13 columns we project out of ~150. account_id is deliberately never read:
# hero-level stats need no player identity.
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


# The manifest's type string for every projected column. A run stops before downloading
# anything if the live manifest disagrees, instead of guessing at new semantics.
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

# Eligibility. 6 players per team is inferred from manifest row counts (mostly
# multiples of 12); check it against real files before trusting the numbers.
PLAYERS_PER_TEAM = 6
MIN_VALID_DURATION_S = 1
MAX_VALID_DURATION_S = 4 * 60 * 60  # sanity bound for the duration metric only

# Curated match_id is a signed BIGINT; the source is UInt64. Refuse, never wrap.
MAX_MATCH_ID = 2**63 - 1

# Window and coverage.
WINDOW_DAYS = 7
SETTLE_LAG_S = 6 * 60 * 60  # rows can arrive after a match ends; wait this long past a day
MAX_COVERAGE_GAP_S = 30 * 60  # holes in a day's source files tolerated before it's "partial"
MAX_UNKNOWN_ENUM_SHARE = 0.01  # more novelty than this means the source changed meaning
