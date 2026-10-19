#!/usr/bin/env bash
# Full deploy: tests, Lambda package, terraform apply (interactive), site upload.
# Requires AWS_PROFILE=deadlock-tracker with an active `aws login` session.
set -euo pipefail
cd "$(dirname "$0")/.."

uv run pytest -q
tools/build_lambda.sh
terraform -chdir=infra init -backend-config=backend.hcl -input=false
terraform -chdir=infra apply
tools/deploy_site.sh
