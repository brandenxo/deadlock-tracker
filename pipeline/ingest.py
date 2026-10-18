"""Copy the columns we need from new source objects into our raw store.

    raw/manifests/v<version>-<sha12>.json   exact manifest bytes, for debugging later
    raw/objects/<id>/rows.parquet           13 projected columns, source types kept
    raw/objects/<id>/provenance.json        written LAST: marks the object complete

<id> is a hash of the source key. Keys name immutable objects, so "have we got this
key?" is all the bookkeeping we need. Holding the same rows twice is harmless:
curation deduplicates rows on (match_id, player_slot).
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
    """Every complete raw object (one with provenance.json)."""
    return [
        Provenance(**json.loads(store.get_bytes(key)))
        for key in store.list_keys(OBJECTS_PREFIX)
        if key.endswith("/provenance.json")
    ]


def project_columns(source: Path, out: Path) -> tuple[int, dict]:
    """Keep only contract.SOURCE_COLUMNS, in the source's own types. Returns (rows, types)."""
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
    """Download, project and store each file. Returns (new objects, bytes downloaded)."""
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
            download.unlink(missing_ok=True)  # never keep whole source objects
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
