"""AWS Lambda entry point, invoked hourly by EventBridge Scheduler (infra/schedule.tf).

Any exception fails the invocation, which the Lambda Errors alarm emails about. The
previous summary keeps serving, and the next hourly run is the retry.
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
