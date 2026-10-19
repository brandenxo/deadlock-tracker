#!/usr/bin/env bash
# Package build/pipeline.zip for the python3.12 x86_64 Lambda runtime.
# uv fetches DuckDB's manylinux wheel, so this works from macOS without Docker.
# boto3 is omitted because the runtime provides it.
set -euo pipefail
cd "$(dirname "$0")/.."

rm -rf build && mkdir -p build/lambda
duckdb_pin=$(uv export --locked --no-dev --no-hashes --no-emit-project | grep '^duckdb==')
uv pip install --quiet --target build/lambda --link-mode copy \
  --python-version 3.12 --python-platform x86_64-manylinux_2_28 "$duckdb_pin"

cp -r pipeline build/lambda/
find build/lambda -name __pycache__ -prune -exec rm -rf {} +
(cd build/lambda && python3 -m zipfile -c ../pipeline.zip ./*)
echo "built build/pipeline.zip ($(du -h build/pipeline.zip | cut -f1))"
