#!/usr/bin/env bash
# Build the web app, sync it to the site bucket, and invalidate index.html.
# Requires Node, an applied infra/, and AWS_PROFILE=deadlock-tracker with a live login.
set -euo pipefail
cd "$(dirname "$0")/.."

(cd web && npm ci && npm run build)
site=$(terraform -chdir=infra output -raw site_bucket)
dist=$(terraform -chdir=infra output -raw distribution_id)

# Content-hashed filenames, safe to cache indefinitely.
aws s3 sync web/dist/assets "s3://$site/assets" --delete \
  --cache-control "public, max-age=31536000, immutable"
# Unhashed files (index.html etc.) revalidate every time. data/ is excluded so a local
# web/public/data summary can't leak into the deployed site.
aws s3 sync web/dist "s3://$site" --delete --exclude "assets/*" --exclude "data/*" \
  --cache-control "no-cache"
aws cloudfront create-invalidation --distribution-id "$dist" --paths "/index.html" >/dev/null

echo "dashboard: $(terraform -chdir=infra output -raw dashboard_url)"
