#!/usr/bin/env bash
# hack-os scripts: snapshot.sh
# Tags the current commit as a known-good demo state. Teams break a
# working demo late in an event with no way back -- this is one line of
# git and enormous insurance.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 1

if ! command -v git >/dev/null 2>&1; then
  echo "hack-os snapshot: git not found" >&2
  exit 1
fi

if [ -n "$(git status --porcelain --untracked-files=normal)" ]; then
  echo "hack-os snapshot: working tree is not clean; commit intended demo changes first. No tag created." >&2
  exit 1
fi
if [ "${1:-}" != "--confirm-demo" ]; then
  echo "Run the demo smoke, then use snapshot.sh --confirm-demo to tag this clean commit." >&2
  exit 2
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "hack-os snapshot: Python required to verify smoke evidence; no tag created" >&2
  exit 1
fi
if ! python3 - <<'PYEOF'
import importlib.util
spec = importlib.util.spec_from_file_location("board", "team-setup/board/serve.py")
board = importlib.util.module_from_spec(spec)
spec.loader.exec_module(board)
smoke = board.get_smoke_last() or {}
raise SystemExit(0 if smoke.get("ok") and smoke.get("clean") and smoke.get("head") == board.git_output("rev-parse", "HEAD") else 1)
PYEOF
then
  echo "hack-os snapshot: run a passing smoke on this clean commit first; no tag created" >&2
  exit 1
fi
STAMP="$(date -u +%Y%m%d-%H%M%S)"
TAG="demo-ok-$STAMP"

ERR_OUTPUT="$(git tag "$TAG" 2>&1)"
if [ $? -ne 0 ]; then
  echo "$ERR_OUTPUT" >&2
  exit 1
fi

echo "Tagged current commit as: $TAG"
echo "To restore this state later, run:"
echo "  team-setup/scripts/restore.sh $TAG --confirm-restore"
echo "The restore opens a separate worktree; it does not overwrite your current work."
