"""Assemble, validate and publish data/summary.json.

Only sums are stored (wins, appearances, ...), never rates: the dashboard adds them up
across the chosen days and divides once, which weights each day by its games.

Validation happens before the single atomic write, so a failed run leaves the
previous summary untouched.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from pipeline import contract
from pipeline.curate import Curation
from pipeline.heroes import heroes_for

SUMMARY_KEY = "data/summary.json"
SCHEMA_VERSION = 1


class ValidationFailed(Exception):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def build_summary(
    *,
    built_at: datetime,
    manifest,
    coverage: dict[str, str],
    curation: Curation,
    settle_lag_s: int,
    known_heroes: dict[int, dict],
    missing_s: dict[str, int] | None = None,
) -> dict:
    covered = sorted(d for d, s in coverage.items() if s == "covered")
    # Allowed upstream holes on covered days, in whole minutes (rounded up).
    gaps = missing_s or {}
    gap_minutes = {d: -(-gaps[d] // 60) for d in covered if gaps.get(d, 0) > 0}
    hero_daily = [r for r in curation.hero_daily if r["date"] in covered]
    excluded: dict[str, int] = {}
    for d in covered:
        for reason, n in curation.exclusions.get(d, {}).items():
            excluded[reason] = excluded.get(reason, 0) + n
    return {
        "schema_version": SCHEMA_VERSION,
        "built_at": built_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": {
            "manifest_version": manifest.version,
            "manifest_generated_at": manifest.generated_at,
        },
        "coverage": {
            "settle_lag_hours": settle_lag_s / 3600,
            "status_by_date": coverage,
            "covered_dates": covered,
            "gap_minutes_by_date": gap_minutes,
        },
        "players_per_team": contract.PLAYERS_PER_TEAM,
        "daily_matches": [
            {"date": d, "eligible_matches": curation.daily_matches.get(d, 0)} for d in covered
        ],
        "hero_daily": hero_daily,
        "heroes": heroes_for({r["hero_id"] for r in hero_daily}, known_heroes),
        "excluded_matches": dict(sorted(excluded.items())),
        "quality": {
            "source_rows": curation.source_rows,
            "won_flag_disagreements": curation.won_flag_disagreements,
        },
    }


def validate(summary: dict, curation: Curation, players_per_team: int) -> None:
    """Raise ValidationFailed if the totals don't add up."""
    problems = []
    matches = {r["date"]: r["eligible_matches"] for r in summary["daily_matches"]}
    for d, n in matches.items():
        if n == 0:
            problems.append(f"{d}: covered but has no eligible matches")
        rows = [r for r in summary["hero_daily"] if r["date"] == d]
        apps = sum(r["appearances"] for r in rows)
        wins = sum(r["wins"] for r in rows)
        # Two full teams and one winner per match fix both totals exactly.
        if apps != n * 2 * players_per_team:
            problems.append(f"{d}: {apps} appearances for {n} matches")
        if wins != n * players_per_team:
            problems.append(f"{d}: {wins} wins for {n} matches")
    unknown = sum(v.get("unknown_enum_value", 0) for v in curation.exclusions.values())
    total = sum(curation.daily_matches.values()) + sum(
        n for v in curation.exclusions.values() for n in v.values()
    )
    if total and unknown / total > contract.MAX_UNKNOWN_ENUM_SHARE:
        problems.append(f"{unknown} of {total} matches have unknown enum values")
    if problems:
        raise ValidationFailed(problems)


def publish(store, summary: dict) -> None:
    body = (json.dumps(summary, separators=(",", ":"), sort_keys=True) + "\n").encode()
    # 60 s cache: fresh enough for hourly updates, still absorbs traffic bursts.
    store.put_bytes(SUMMARY_KEY, body, "application/json", cache_control="public, max-age=60")
