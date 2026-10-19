"""Command-line entry point for local runs.

uv run python -m pipeline.cli synth --out data/synth --start 2026-10-05T00 --hours 48
uv run python -m pipeline.cli run --source data/synth --now 2026-10-07T06:30:00Z
uv run python -m pipeline.cli run                       # live source, default cap
"""

from __future__ import annotations

import argparse
import dataclasses
from datetime import UTC, datetime
from pathlib import Path

from pipeline.config import Settings
from pipeline.run import run_once
from pipeline.source import SourceClient
from pipeline.storage import LocalStore
from pipeline.synthetic import SyntheticSpec, generate

FIXTURE_HEROES = Path(__file__).resolve().parent.parent / "fixtures" / "heroes.json"


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="pipeline.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    synth = sub.add_parser("synth", help="write a SYNTHETIC source directory")
    synth.add_argument("--out", type=Path, required=True)
    synth.add_argument("--start", type=_utc, required=True, help="first match start, UTC")
    synth.add_argument("--hours", type=int, default=48)
    synth.add_argument("--matches-per-hour", type=int, default=12)
    synth.add_argument("--encoding", choices=["int", "label"], default="int")

    run = sub.add_parser("run", help="run the pipeline once into a local data directory")
    run.add_argument("--source", type=Path, help="synthetic source dir (default: real source)")
    run.add_argument("--data-dir", type=Path, default=Path("data/local"))
    run.add_argument("--now", type=_utc, help="pretend the current time is this (UTC)")
    run.add_argument("--cap-mb", type=int, help="download cap for this run")

    args = parser.parse_args(argv)
    if args.command == "synth":
        spec = SyntheticSpec(
            out_dir=args.out,
            start_epoch=int(args.start.timestamp()),
            hours=args.hours,
            matches_per_hour=args.matches_per_hour,
            encoding=args.encoding,
        )
        manifest = generate(spec)
        print(f"wrote {len(manifest['tables']['match_player']['files'])} delta files to {args.out}")
        return

    settings = Settings.from_env()
    if args.cap_mb:
        settings = dataclasses.replace(settings, download_cap_bytes=args.cap_mb * 1_000_000)
    if args.source:
        # No hero API offline; fall back to the bundled fixture list.
        base = args.source.resolve().as_uri()
        client = SourceClient(base, f"{base}/v1/manifest.json")
        settings = dataclasses.replace(settings, heroes_url=FIXTURE_HEROES.as_uri())
    else:
        client = SourceClient(settings.source_base_url, settings.manifest_url)
    run_once(settings, LocalStore(args.data_dir), client, now=args.now)
    print(f"summary: {args.data_dir / 'data' / 'summary.json'}")


if __name__ == "__main__":
    main()
