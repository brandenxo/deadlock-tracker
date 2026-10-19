"""Lambda entry point for the hourly scheduled run (infra/schedule.tf).

Errors are logged and re-raised so the invocation counts as failed and trips the
alarm. The last published summary stays up; the next scheduled run retries.
"""

from __future__ import annotations

from pipeline.config import Settings
from pipeline.run import log, run_once
from pipeline.source import SourceClient
from pipeline.storage import S3Store


def handler(event, context):
    settings = Settings.from_env()
    try:
        return run_once(
            settings,
            S3Store(settings.bucket),
            SourceClient(settings.source_base_url, settings.manifest_url),
        )
    except Exception as exc:
        log("run_failed", error_class=type(exc).__name__, error=str(exc))
        raise
