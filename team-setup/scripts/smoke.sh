#!/usr/bin/env bash
# hack-os scripts: smoke.sh
# Stack-agnostic happy-path check. NEVER wired into a blocking hook --
# exits non-zero on failure so a human or CI step can act on it, but
# nothing in this repo treats that exit code as a gate (spec Part 2 rule 1).
#
# ============================ EDIT ME ONCE ================================
# Fill this in once the team picks a stack on the day. Leave commands blank
# to skip that check. Examples are commented out below.
SMOKE_HEALTH_URL="${SMOKE_HEALTH_URL:-}"            # e.g. "http://localhost:3000/api/health"
SMOKE_COMMAND="${SMOKE_COMMAND:-}"                # e.g. "cd app/backend && npm run smoke"
SMOKE_EXPECTED_TEXT="${SMOKE_EXPECTED_TEXT:-}"          # optional: text that must appear in the health response
# Example filled-in config for a Next.js + FastAPI stack:
#   SMOKE_HEALTH_URL="http://localhost:8000/health"
#   SMOKE_COMMAND="curl -sf http://localhost:3000 > /dev/null"
#   SMOKE_EXPECTED_TEXT="ok"
# ============================================================================
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 1

STATE_DIR="team-setup/state"
SMOKE_HEAD="$(git rev-parse HEAD 2>/dev/null || true)"
SMOKE_DIRTY="$(git status --porcelain -- app 2>/dev/null || true)"
export SMOKE_HEAD SMOKE_DIRTY
OK=1
DETAIL=""

if [ -n "$SMOKE_HEALTH_URL" ]; then
  if command -v curl >/dev/null 2>&1; then
    RESPONSE="$(curl --max-time 20 -sf "$SMOKE_HEALTH_URL" 2>&1)"
    if [ $? -ne 0 ]; then
      OK=0
      DETAIL="health URL unreachable: $SMOKE_HEALTH_URL"
    elif [ -n "$SMOKE_EXPECTED_TEXT" ] && ! echo "$RESPONSE" | grep -q "$SMOKE_EXPECTED_TEXT"; then
      OK=0
      DETAIL="health response missing expected text '$SMOKE_EXPECTED_TEXT'"
    else
      DETAIL="health check passed"
    fi
  else
    OK=0
    DETAIL="curl not found, cannot check SMOKE_HEALTH_URL"
  fi
fi

if [ -n "$SMOKE_COMMAND" ]; then
  if eval "$SMOKE_COMMAND"; then
    DETAIL="${DETAIL:+$DETAIL; }smoke command passed"
  else
    OK=0
    DETAIL="${DETAIL:+$DETAIL; }smoke command failed: $SMOKE_COMMAND"
  fi
fi

if [ -z "$SMOKE_HEALTH_URL" ] && [ -z "$SMOKE_COMMAND" ]; then
  DETAIL="smoke.sh not configured yet -- edit the EDIT ME block at the top of this file"
  OK=0
fi

if [ "$OK" = "1" ]; then
  echo "hack-os smoke: PASS — $DETAIL"
else
  echo "hack-os smoke: FAIL — $DETAIL" >&2
fi

if command -v python3 >/dev/null 2>&1; then
  HACKOS_OK="$OK" HACKOS_DETAIL="$DETAIL" HACKOS_STATE_DIR="$STATE_DIR" python3 - <<'PYEOF' 2>/dev/null
import importlib.util, os
from datetime import datetime, timezone

spec = importlib.util.spec_from_file_location("board", "team-setup/board/serve.py")
board = importlib.util.module_from_spec(spec)
spec.loader.exec_module(board)
result = {
    "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "head": os.environ.get("SMOKE_HEAD"),
    "clean": not os.environ.get("SMOKE_DIRTY") and board.git_output("status", "--porcelain", "--", "app") == ""
             and board.git_output("rev-parse", "HEAD") == os.environ.get("SMOKE_HEAD"),
    "t_offset": board.t_plus(board.load_event().get("build_starts")),
    "ok": os.environ.get("HACKOS_OK") == "1",
    "detail": os.environ.get("HACKOS_DETAIL", ""),
}
try:
    board.write_json(board.runtime_path("smoke-last.json"), result)
except (OSError, ValueError):
    print("hack-os smoke: could not save local smoke evidence")
PYEOF
fi

if [ "$OK" = "1" ]; then
  exit 0
else
  exit 1
fi
