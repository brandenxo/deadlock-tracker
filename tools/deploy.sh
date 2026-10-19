#!/usr/bin/env bash
# Everything, in order: test, package the Lambda, apply Terraform, upload the site.
# Terraform shows its plan and asks before it changes anything in AWS.
# Needs: export AWS_PROFILE=deadlock-tracker, and a current `aws login` session.
set -euo pipefail
cd "$(dirname "$0")/.."

uv run pytest -q
tools/build_lambda.sh
terraform -chdir=infra init -backend-config=backend.hcl -input=false
terraform -chdir=infra apply
tools/deploy_site.sh
