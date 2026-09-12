#!/usr/bin/env bash
# hack-os scripts: restore.sh
# Lists snapshot tags (demo-ok-*), or restores a chosen one if given as an
# argument.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 1

if ! command -v git >/dev/null 2>&1; then
  echo "hack-os restore: git not found" >&2
  exit 1
fi

TAGS="$(git tag -l 'demo-ok-*' --sort=-creatordate)"

if [ -z "${1:-}" ]; then
  if [ -z "$TAGS" ]; then
    echo "No snapshot tags found. Run team-setup/scripts/snapshot.sh first."
    exit 0
  fi
  echo "Snapshot tags (newest first):"
  echo "$TAGS"
  echo ""
  echo "Usage: team-setup/scripts/restore.sh <tag>"
  exit 0
fi

TAG="$1"
if ! echo "$TAGS" | grep -qx "$TAG"; then
  echo "hack-os restore: '$TAG' is not a known demo-ok-* tag." >&2
  echo "Known tags:" >&2
  echo "$TAGS" >&2
  exit 1
fi

if [ "${2:-}" != "--confirm-restore" ]; then
  echo "This will create a separate detached demo worktree; your current files and branch stay untouched."
  echo "Run: team-setup/scripts/restore.sh $TAG --confirm-restore"
  exit 2
fi
DEST="$(dirname "$ROOT")/$(basename "$ROOT")-restore-$TAG-$$"
if [ -e "$DEST" ]; then
  echo "hack-os restore: destination already exists; nothing changed" >&2
  exit 1
fi
git worktree add --detach "$DEST" "refs/tags/$TAG" || exit 1
echo "Restored demo in separate worktree: $DEST"
echo "Current worktree and branch unchanged. Follow app/README.md in the restored worktree to run it."
