"""A full pipeline run. Works against LocalStore or S3Store unchanged.

    manifest -> schema check -> capped download of new deltas -> rebuild the window
    from every held object -> coverage -> curated Parquet -> hero names -> summary
    -> validate -> publish

The window is recomputed from raw each time rather than patched. It's only seconds of
work, and the output then depends only on what's held, not on run history (retries,
failures, duplicate deliveries).

Runs must not overlap. Lambda enforces that with reserved concurrency 1; locally it's
up to you.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from pipeline import contract, coverage, curate, heroes, ingest, summary
from pipeline.config import Settings
from pipeline.source import (
    SourceClient,
    SourceError,
    check_schema,
    parse_manifest,
    plan_ingest,
)

CURATED_PREFIX = "curated/"


def log(event: str, **fields) -> None:
    """Print a single-line JSON event (queryable in Logs Insights)."""
    print(json.dumps({"event": event, **fields}, default=str), flush=True)


def run_once(
    settings: Settings,
    store,
    client: SourceClient,
    now: datetime | None = None,
    workdir: Path | None = None,
    players_per_team: int = contract.PLAYERS_PER_TEAM,
) -> dict:
    now = now or datetime.now(UTC)
    started = time.monotonic()
    own_workdir = workdir is None
    workdir = workdir or Path(tempfile.mkdtemp(prefix="deadlock-"))
    try:
        # Manifest: what the source offers now.
        raw_manifest = client.fetch_manifest()
        manifest = parse_manifest(raw_manifest)
        check_schema(manifest, contract.TABLE, contract.EXPECTED_MANIFEST_TYPES)
        ingest.save_manifest(store, raw_manifest, manifest)

        # Fetch whatever we don't have yet.
        dates = coverage.window_dates(int(now.timestamp()), settings.window_days)
        window_start = coverage.day_start(dates[0])
        held = {p.source_key for p in ingest.held_objects(store)}
        plan = plan_ingest(
            manifest, contract.TABLE, held, settings.download_cap_bytes, window_start
        )
        new, downloaded = ingest.ingest(
            manifest, plan.to_download, client, store, workdir, settings.download_cap_bytes
        )
        log("ingested", new_objects=len(new), bytes=downloaded, deferred=len(plan.skipped_for_cap))

        # Recompute the window from all held objects that overlap it.
        objects = [p for p in ingest.held_objects(store) if p.hi > window_start]
        paths = []
        for p in objects:
            path = workdir / "raw" / f"{ingest.object_id(p.source_key)}.parquet"
            store.download_file(ingest.rows_key(p.source_key), path)
            paths.append(path)
        con = curate.connect(workdir)
        curate.load_raw(con, paths)
        intervals = [(p.lo, p.hi) for p in objects]
        status = coverage.classify(intervals, dates, settings.settle_lag_s, settings.max_gap_s)
        missing = coverage.missing_seconds(intervals, dates, settings.settle_lag_s)
        result = curate.curate(con, [d.isoformat() for d in dates], players_per_team)

        # Names are optional; log and continue on failure.
        try:
            known = heroes.parse_heroes(
                client.fetch_small(settings.heroes_url, heroes.HEROES_MAX_BYTES)
            )
        except (SourceError, ValueError, TypeError) as exc:
            log("heroes_unavailable", error=str(exc))
            known = {}

        # Validate before any write, so a bad run publishes nothing.
        doc = summary.build_summary(
            built_at=now,
            manifest=manifest,
            coverage=status,
            curation=result,
            settle_lag_s=settings.settle_lag_s,
            known_heroes=known,
            missing_s=missing,
        )
        summary.validate(doc, result, players_per_team)
        replace_curated(store, con, workdir / "curated")
        summary.publish(store, doc)

        outcome = {
            "manifest_version": manifest.version,
            "new_objects": len(new),
            "bytes_downloaded": downloaded,
            "objects_used": len(objects),
            "source_rows": result.source_rows,
            "covered_dates": doc["coverage"]["covered_dates"],
            "seconds": round(time.monotonic() - started, 2),
        }
        log("published", **outcome)
        return outcome
    finally:
        if own_workdir:
            shutil.rmtree(workdir, ignore_errors=True)


def replace_curated(store, con, out_dir: Path) -> None:
    """Sync curated/ to this run's output, deleting dates that aged out."""
    new_keys = set()
    for path in curate.write_curated(con, out_dir):
        key = CURATED_PREFIX + path.relative_to(out_dir.resolve()).as_posix()
        store.upload_file(key, path)
        new_keys.add(key)
    store.delete_keys([k for k in store.list_keys(CURATED_PREFIX) if k not in new_keys])
