#!/usr/bin/env bash
# Move job inputs and results between this machine and the Nebius bucket over the S3 API.
#
#   bash sync_bucket.sh upload <examples.parquet>     package trip/ and upload data and code
#   bash sync_bucket.sh results <run tag> <local dir> download logs and predictions of a run
#   bash sync_bucket.sh ls                            list the bucket
#
# Credentials come from the repo-root .env: NEBIUS_S3_ENDPOINT, NEBIUS_S3_ACCESS_KEY_ID and
# NEBIUS_S3_SECRET_ACCESS_KEY (a service-account access key; only tenant admins can create one).
# The AWS CLI runs through uvx, so nothing is installed globally.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
TRIP="$(dirname "$HERE")"
ROOT="$(git -C "$HERE" rev-parse --show-toplevel)"
BUCKET="${NEBIUS_BUCKET:-jonas-trip-delay}"

while IFS='=' read -r key value; do
  case "$key" in NEBIUS_S3_ENDPOINT|NEBIUS_S3_ACCESS_KEY_ID|NEBIUS_S3_SECRET_ACCESS_KEY) export "$key=$value" ;; esac
done < "$ROOT/.env"
ENDPOINT="${NEBIUS_S3_ENDPOINT:-https://storage.eu-north1.nebius.cloud}"
REGION="$(sed -E 's#https://storage\.([^.]+)\..*#\1#' <<< "$ENDPOINT")"

s3() {
  : "${NEBIUS_S3_ACCESS_KEY_ID:?set NEBIUS_S3_ACCESS_KEY_ID in the root .env}"
  : "${NEBIUS_S3_SECRET_ACCESS_KEY:?set NEBIUS_S3_SECRET_ACCESS_KEY in the root .env}"
  AWS_ACCESS_KEY_ID="$NEBIUS_S3_ACCESS_KEY_ID" AWS_SECRET_ACCESS_KEY="$NEBIUS_S3_SECRET_ACCESS_KEY" \
    uvx --from awscli aws --endpoint-url "$ENDPOINT" --region "$REGION" s3 "$@"
}

case "${1:-}" in
  upload)
    examples="${2:?usage: sync_bucket.sh upload <examples.parquet>}"
    staging="$(mktemp -d)"
    trap 'rm -rf "$staging"' EXIT
    COPYFILE_DISABLE=1 tar --exclude '__pycache__' --exclude '.DS_Store' -czf "$staging/trip.tar.gz" -C "$(dirname "$TRIP")" trip
    s3 cp "$examples" "s3://$BUCKET/data/examples.parquet"
    s3 cp "$staging/trip.tar.gz" "s3://$BUCKET/code/trip.tar.gz"
    s3 cp "$HERE/requirements.txt" "s3://$BUCKET/code/requirements.txt"
    s3 ls --recursive "s3://$BUCKET/"
    ;;
  results)
    tag="${2:?usage: sync_bucket.sh results <run tag> <local dir>}"
    dest="${3:?usage: sync_bucket.sh results <run tag> <local dir>}"
    s3 sync "s3://$BUCKET/runs/$tag" "$dest" --exclude "*checkpoint.pt"
    ;;
  ls)
    s3 ls --recursive "s3://$BUCKET/"
    ;;
  cat)
    s3 cp "s3://$BUCKET/${2:?usage: sync_bucket.sh cat <object key>}" -
    ;;
  *)
    sed -n '2,9p' "$0"
    exit 1
    ;;
esac
