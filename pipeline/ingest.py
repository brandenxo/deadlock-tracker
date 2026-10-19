"""Download new source objects and store the kept columns under raw/.

    raw/manifests/v<version>-<sha12>.json   manifest as fetched, for debugging
    raw/objects/<id>/rows.parquet           kept columns, original source types
    raw/objects/<id>/provenance.json        written last; its presence = complete

<id> hashes the source key. Source keys are immutable, so a key we already hold never
needs fetching again. Overlapping rows across objects are fine; curation dedups them.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from pipeline import contract
from pipeline.source import Manifest, SourceClient, SourceFile, UnsupportedSchema

OBJECTS_PREFIX = "raw/objects/"


@dataclass(frozen=True)
class Provenance:
    source_key: str
    lo: int
    hi: int
    manifest_version: int
    rows: int
    bytes: int
    source_types: dict
    fetched_at: str


def object_id(source_key: str) -> str:
    return hashlib.sha256(source_key.encode()).hexdigest()[:20]


def rows_key(source_key: str) -> str:
    return f"{OBJECTS_PREFIX}{object_id(source_key)}/rows.parquet"


def save_manifest(store, raw: bytes, manifest: Manifest) -> None:
    store.put_bytes(f"raw/manifests/v{manifest.version}-{manifest.sha256[:12]}.json", raw)


def held_objects(store) -> list[Provenance]:
    """Provenance for every fully stored object."""
    return [
        Provenance(**json.loads(store.get_bytes(key)))
        for key in store.list_keys(OBJECTS_PREFIX)
        if key.endswith("/provenance.json")
    ]


def project_columns(source: Path, out: Path) -> tuple[int, dict]:
    """Write contract.SOURCE_COLUMNS (unconverted) to out; return (row count, types)."""
    con = duckdb.connect()
    try:
        types = dict(
            con.execute(
                "SELECT column_name, column_type FROM (DESCRIBE SELECT * FROM read_parquet(?))",
                [str(source)],
            ).fetchall()
        )
        missing = [c for c in contract.SOURCE_COLUMNS if c not in types]
        if missing:
            raise UnsupportedSchema(f"{source.name}: missing columns {missing}")
        columns = ", ".join(f'"{c}"' for c in contract.SOURCE_COLUMNS)
        out.parent.mkdir(parents=True, exist_ok=True)
        con.execute(
            f"COPY (SELECT {columns} FROM read_parquet(?)) TO '{out.as_posix()}' "
            "(FORMAT parquet, COMPRESSION zstd)",
            [str(source)],
        )
        rows = con.execute("SELECT COUNT(*) FROM read_parquet(?)", [str(out)]).fetchone()[0]
        return rows, {c: types[c] for c in contract.SOURCE_COLUMNS}
    finally:
        con.close()


def ingest(
    manifest: Manifest,
    files: list[SourceFile],
    client: SourceClient,
    store,
    workdir: Path,
    cap_bytes: int,
) -> tuple[list[Provenance], int]:
    """Fetch, trim and store each file; return (provenance list, bytes downloaded)."""
    remaining = cap_bytes
    stored = []
    for f in files:
        oid = object_id(f.key)
        download = workdir / "download" / f"{oid}.parquet"
        projected = workdir / "projected" / f"{oid}.parquet"
        remaining -= client.download(f, download, max_bytes=remaining)
        try:
            rows, types = project_columns(download, projected)
        finally:
            download.unlink(missing_ok=True)  # full source files are never kept
        prov = Provenance(
            source_key=f.key,
            lo=f.lo,
            hi=f.hi,
            manifest_version=manifest.version,
            rows=rows,
            bytes=f.bytes,
            source_types=types,
            fetched_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        store.upload_file(rows_key(f.key), projected)
        store.put_bytes(f"{OBJECTS_PREFIX}{oid}/provenance.json", json.dumps(asdict(prov)).encode())
        projected.unlink(missing_ok=True)
        stored.append(prov)
    return stored, cap_bytes - remaining
