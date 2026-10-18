from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

USER_AGENT = "deadlock-tracker/0.1 (+personal project; hero aggregates only)"
MANIFEST_MAX_BYTES = 20_000_000
CHUNK = 1024 * 1024


# --- manifest ------------------------------------------------------------------------


class UnsupportedSchema(Exception):
    """The source no longer matches the data contract. Stop rather than guess."""


@dataclass(frozen=True)
class SourceFile:
    key: str
    kind: str  # snapshot | base | residual | delta
    rows: int
    bytes: int
    lo: int | None  # created_at range [lo, hi), epoch seconds (deltas only)
    hi: int | None


@dataclass(frozen=True)
class Manifest:
    version: int
    generated_at: str
    tables: dict
    sha256: str  # identity of the exact bytes we read

    def files(self, table: str) -> list[SourceFile]:
        return [
            SourceFile(
                f["key"],
                f["kind"],
                int(f["rows"]),
                int(f["bytes"]),
                f.get("lo"),
                f.get("hi"),
            )
            for f in self.tables[table].get("files", [])
        ]


def parse_manifest(raw: bytes) -> Manifest:
    doc = json.loads(raw)
    if doc.get("format_version") != 1:
        raise UnsupportedSchema(f"manifest format_version {doc.get('format_version')!r}")
    return Manifest(
        version=int(doc["version"]),
        generated_at=doc["generated_at"],
        tables=doc["tables"],
        sha256=hashlib.sha256(raw).hexdigest(),
    )


def check_schema(manifest: Manifest, table: str, expected: dict[str, str]) -> None:
    actual = {c["name"]: c["type"] for c in manifest.tables[table].get("columns", [])}
    problems = [
        f"{name}: expected {want!r}, got {actual.get(name)!r}"
        for name, want in expected.items()
        if actual.get(name) != want
    ]
    if problems:
        raise UnsupportedSchema(f"{table}: " + "; ".join(problems))


@dataclass(frozen=True)
class IngestPlan:
    to_download: list[SourceFile]
    skipped_for_cap: list[SourceFile]
    planned_bytes: int


def plan_ingest(
    manifest: Manifest,
    table: str,
    held_keys: set[str],
    cap_bytes: int,
    window_start: int,
) -> IngestPlan:
    """Pick delta files to download this run.

    Pick files in the window that are not already held, newest first, until the next
    one would exceed the cap. Older files wait for the next run.
    """
    wanted = [
        f
        for f in manifest.files(table)
        if f.kind == "delta" and f.hi is not None and f.hi > window_start and f.key not in held_keys
    ]
    wanted.sort(key=lambda f: (f.hi, f.key), reverse=True)

    chosen: list[SourceFile] = []
    total = 0
    for i, source_file in enumerate(wanted):
        if total + source_file.bytes > cap_bytes:
            return IngestPlan(chosen, wanted[i:], total)
        chosen.append(source_file)
        total += source_file.bytes
    return IngestPlan(chosen, [], total)


# --- HTTP ----------------------------------------------------------------------------


class SourceError(Exception):
    pass


class SourceClient:
    """Stream objects with a byte cap and bounded retries.

    This client uses only the standard library. urllib understands file:// URLs, so
    tests can point it at a synthetic directory.
    """

    def __init__(
        self,
        base_url: str,
        manifest_url: str,
        attempts: int = 3,
        sleep=time.sleep,
    ):
        self.base_url = base_url.rstrip("/")
        self.manifest_url = manifest_url
        self.attempts = attempts
        self._sleep = sleep

    def fetch_manifest(self) -> bytes:
        return self.fetch_small(self.manifest_url, MANIFEST_MAX_BYTES)

    def fetch_small(self, url: str, max_bytes: int) -> bytes:
        """GET a small document whole, refusing anything too big."""

        def read(response) -> bytes:
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise SourceError(f"{url}: larger than {max_bytes} bytes")
            return body

        return self._with_retries(url, read)

    def download(self, source_file: SourceFile, dest: Path, max_bytes: int) -> int:
        """Write one object to dest, enforcing the byte cap and manifest size."""

        def stream(response) -> int:
            total = 0
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("wb") as out:
                while chunk := response.read(CHUNK):
                    total += len(chunk)
                    if total > max_bytes:
                        raise SourceError(f"{source_file.key}: exceeded download cap")
                    out.write(chunk)
            if total != source_file.bytes:
                raise SourceError(
                    f"{source_file.key}: got {total} bytes, manifest says {source_file.bytes}"
                )
            return total

        try:
            return self._with_retries(f"{self.base_url}/{source_file.key}", stream)
        except BaseException:
            dest.unlink(missing_ok=True)  # never leave a partial file behind
            raise

    def _with_retries(self, url: str, consume):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        error: Exception | None = None
        for attempt in range(self.attempts):
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    return consume(response)
            except urllib.error.HTTPError as exc:
                if exc.code < 500 and exc.code != 429:
                    raise SourceError(f"{url}: HTTP {exc.code}") from exc
                error = exc
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                error = exc
            if attempt + 1 < self.attempts:
                self._sleep(2 * 2**attempt)
        raise SourceError(f"{url}: failed after {self.attempts} attempts: {error}")
