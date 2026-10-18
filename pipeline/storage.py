"""One small storage interface, two backends: a local directory and an S3 bucket.

The pipeline relies on one S3 property: a single PutObject is atomic, so a reader of
data/summary.json sees either the old file or the new one, never half of each.
"""

from __future__ import annotations

import os
from pathlib import Path


class LocalStore:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if key.startswith("/") or ".." in key.split("/"):
            raise ValueError(f"unsafe key: {key!r}")
        return self.root / key

    def put_bytes(self, key: str, data: bytes, content_type: str = "", cache_control: str = ""):
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f".{target.name}.tmp")
        tmp.write_bytes(data)
        os.replace(tmp, target)  # atomic, like an S3 put

    def get_bytes(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise KeyError(key)
        return path.read_bytes()

    def upload_file(self, key: str, path: Path) -> None:
        self.put_bytes(key, Path(path).read_bytes())

    def download_file(self, key: str, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.get_bytes(key))

    def list_keys(self, prefix: str) -> list[str]:
        keys = (p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file())
        return sorted(k for k in keys if k.startswith(prefix) and "/." not in f"/{k}")

    def delete_keys(self, keys: list[str]) -> None:
        for key in keys:
            self._path(key).unlink(missing_ok=True)


class S3Store:
    def __init__(self, bucket: str, client=None):
        if client is None:
            import boto3  # lazy: local runs never need AWS configuration

            client = boto3.client("s3")
        self.bucket = bucket
        self.s3 = client

    def put_bytes(self, key: str, data: bytes, content_type: str = "", cache_control: str = ""):
        extra = {"ContentType": content_type} if content_type else {}
        if cache_control:
            extra["CacheControl"] = cache_control
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=data, **extra)

    def get_bytes(self, key: str) -> bytes:
        try:
            return self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except self.s3.exceptions.NoSuchKey:
            raise KeyError(key) from None

    def upload_file(self, key: str, path: Path) -> None:
        self.s3.upload_file(str(path), self.bucket, key)

    def download_file(self, key: str, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.s3.download_file(self.bucket, key, str(path))

    def list_keys(self, prefix: str) -> list[str]:
        keys = []
        for page in self.s3.get_paginator("list_objects_v2").paginate(
            Bucket=self.bucket, Prefix=prefix
        ):
            keys.extend(obj["Key"] for obj in page.get("Contents", []))
        return sorted(keys)

    def delete_keys(self, keys: list[str]) -> None:
        for start in range(0, len(keys), 1000):  # DeleteObjects takes at most 1,000 keys
            batch = [{"Key": k} for k in keys[start : start + 1000]]
            self.s3.delete_objects(Bucket=self.bucket, Delete={"Objects": batch, "Quiet": True})
