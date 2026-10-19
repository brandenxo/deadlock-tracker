#!/usr/bin/env bash
# Build build/pipeline.zip for AWS Lambda (Python 3.12, x86_64).
# Works on macOS and Windows/WSL too: uv downloads the Linux wheel for DuckDB instead of
# the one for your laptop. boto3 is not packaged; the Lambda runtime already has it.
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
