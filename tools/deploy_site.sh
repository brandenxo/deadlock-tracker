#!/usr/bin/env bash
# Build the dashboard and upload it to the site bucket, then tell CloudFront that
# index.html changed. Needs: AWS CLI logged in (AWS_PROFILE=deadlock-tracker), Node,
# and a terraform-applied infra/.
set -euo pipefail
cd "$(dirname "$0")/.."

(cd web && npm ci && npm run build)
site=$(terraform -chdir=infra output -raw site_bucket)
dist=$(terraform -chdir=infra output -raw distribution_id)

# Hashed asset names change whenever their content does, so they can be cached forever.
aws s3 sync web/dist/assets "s3://$site/assets" --delete \
  --cache-control "public, max-age=31536000, immutable"
# index.html (and anything else unhashed) must be re-checked on every visit. data/ is
# skipped: a local demo summary in web/public/data must never reach the site bucket.
aws s3 sync web/dist "s3://$site" --delete --exclude "assets/*" --exclude "data/*" \
  --cache-control "no-cache"
aws cloudfront create-invalidation --distribution-id "$dist" --paths "/index.html" >/dev/null

echo "dashboard: $(terraform -chdir=infra output -raw dashboard_url)"
