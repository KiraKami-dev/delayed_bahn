#!/usr/bin/env bash
# Mirror what serve_route.py needs from the error404-db-route bucket into app/agents/data/db-route:
# the scored forecasts of one run (no checkpoint) and the registry of one profile.
#
#   bash fetch_serving_data.sh                 # route-2k / quarter (the bake-off winner)
#   bash fetch_serving_data.sh route-2k season
#
# Credentials come from the repo-root .env (NEBIUS_S3_ACCESS_KEY_ID / NEBIUS_S3_SECRET_ACCESS_KEY,
# the db-route-s3 service-account key from `nebius iam v2 access-key list`). awscli runs via uvx.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(git -C "$HERE" rev-parse --show-toplevel)"
TAG="${1:-route-2k}"; PROFILE="${2:-quarter}"
BUCKET="${NEBIUS_BUCKET:-error404-db-route}"
DEST="${DATA_DIR:-$ROOT/app/agents/data/db-route}"
while IFS='=' read -r key value; do
  case "$key" in NEBIUS_S3_ENDPOINT|NEBIUS_S3_ACCESS_KEY_ID|NEBIUS_S3_SECRET_ACCESS_KEY) export "$key=$value" ;; esac
done < "$ROOT/.env"
: "${NEBIUS_S3_ACCESS_KEY_ID:?set NEBIUS_S3_ACCESS_KEY_ID in the root .env}"
: "${NEBIUS_S3_SECRET_ACCESS_KEY:?set NEBIUS_S3_SECRET_ACCESS_KEY in the root .env}"
ENDPOINT="${NEBIUS_S3_ENDPOINT:-https://storage.eu-north1.nebius.cloud}"
REGION="$(sed -E 's#https://storage\.([^.]+)\..*#\1#' <<< "$ENDPOINT")"
s3() { AWS_ACCESS_KEY_ID="$NEBIUS_S3_ACCESS_KEY_ID" AWS_SECRET_ACCESS_KEY="$NEBIUS_S3_SECRET_ACCESS_KEY" uvx --from awscli aws --endpoint-url "$ENDPOINT" --region "$REGION" s3 "$@"; }
mkdir -p "$DEST"
s3 sync "s3://$BUCKET/runs/$TAG/$PROFILE" "$DEST/runs/$TAG/$PROFILE" --exclude "*.pt"
s3 sync "s3://$BUCKET/registry/error404/db-route-$PROFILE" "$DEST/registry/error404/db-route-$PROFILE"
mkdir -p "$DEST/cache"
s3 cp "s3://$BUCKET/cache/cancellation_rates.json" "$DEST/cache/cancellation_rates.json"   # measured P(cancelled) per service (build_cancellation_rates.py)
du -sh "$DEST"
