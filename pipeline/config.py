"""Settings read from DT_* environment variables, with local-friendly defaults.
Lambda's values are set in infra/lambda.tf. No secrets live here."""

from __future__ import annotations

import os
from dataclasses import dataclass

from pipeline import contract


def _int(env: dict, name: str, default: int) -> int:
    raw = env.get(name, "")
    try:
        return int(raw) if raw else default
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc


@dataclass(frozen=True)
class Settings:
    manifest_url: str = "https://data.deadlock-api.com/v1/manifest.json"
    source_base_url: str = "https://data.deadlock-api.com"
    heroes_url: str = "https://api.deadlock-api.com/v1/assets/heroes"
    download_cap_bytes: int = 300 * 1_000_000
    window_days: int = contract.WINDOW_DAYS
    settle_lag_s: int = contract.SETTLE_LAG_S
    max_gap_s: int = contract.MAX_COVERAGE_GAP_S
    bucket: str = ""  # "" means use the local store

    @classmethod
    def from_env(cls, env: dict | None = None) -> Settings:
        env = dict(os.environ if env is None else env)
        default = cls()
        return cls(
            manifest_url=env.get("DT_MANIFEST_URL", default.manifest_url),
            source_base_url=env.get("DT_SOURCE_BASE_URL", default.source_base_url),
            heroes_url=env.get("DT_HEROES_URL", default.heroes_url),
            download_cap_bytes=_int(env, "DT_DOWNLOAD_CAP_MB", 300) * 1_000_000,
            window_days=_int(env, "DT_WINDOW_DAYS", contract.WINDOW_DAYS),
            settle_lag_s=_int(env, "DT_SETTLE_LAG_HOURS", contract.SETTLE_LAG_S // 3600) * 3600,
            max_gap_s=_int(env, "DT_MAX_GAP_MINUTES", contract.MAX_COVERAGE_GAP_S // 60) * 60,
            bucket=env.get("DT_BUCKET", ""),
        )
