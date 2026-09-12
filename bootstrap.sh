#!/usr/bin/env bash
# hack-os bootstrap.sh
# One command, under two minutes, idempotent, safe to re-run. Guarantees
# tooling parity across teammates using different agent harnesses
# (spec Part 2 rule 3, Part 4.0). Prints a pass/warn line for every piece
# of tooling this repo depends on, then a final summary table.
#
# Auto mode: triggered by --auto, or automatically whenever stdin is not a
# TTY (an agent's shell tool, a hook, a pipe). Infers identity/harness
# instead of blocking on `read`/`select`, so a Claude Code or Codex session
# can run this unattended on first launch (see AGENTS.md step 0). A human
# running this directly in a real terminal still gets the interactive
# prompts exactly as before.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT" || exit 1

AUTO=0
if [ "${1:-}" = "--auto" ] || [ ! -t 0 ]; then
  AUTO=1
fi

STATE_DIR="team-setup/state"
RESULTS=()   # each entry: "LABEL|PASS|detail" or "LABEL|WARN|detail"

record() {
  RESULTS+=("$1|$2|$3")
  if [ "$2" = "PASS" ]; then
    echo "  [ok]   $1 — $3"
  else
    echo "  [warn] $1 — $3"
  fi
}

echo "hack-os bootstrap — starting"
echo ""

# 1. Prerequisites -----------------------------------------------------
echo "1/10 checking prerequisites"
if command -v git >/dev/null 2>&1; then
  record "git" "PASS" "$(git --version)"
else
  record "git" "WARN" "git not found — this repo needs git, install it and re-run"
fi

HAVE_PY3=0
if command -v python3 >/dev/null 2>&1; then
  HAVE_PY3=1
  record "python3" "PASS" "$(python3 --version 2>&1)"
else
  record "python3" "WARN" "python3 not found — dashboard unavailable; the markdown-only layer still works"
fi
echo ""

# 2. Git hooks -----------------------------------------------------------
echo "2/10 installing git hooks"
if [ -x team-setup/hooks/install.sh ]; then
  if bash team-setup/hooks/install.sh; then
    record "git hooks" "PASS" "local hooks installed or already current"
  else
    record "git hooks" "WARN" "installation incomplete; existing hooks preserved, review installer output"
  fi
else
  record "git hooks" "WARN" "team-setup/hooks/install.sh missing or not executable"
fi
echo ""

# 3. entire.io CLI ---------------------------------------------------------
# Optional session linking is not installed or required by bootstrap.
# No network calls, git remote changes, or pushes run during setup.
echo "3/10 optional session tools"
record "session tools" "PASS" "not required; no downloads, prompt capture, or external telemetry installed"
echo ""

# 4. App stack detection ---------------------------------------------------
echo "4/10 detecting product stack in app/"

for manifest in app/*/package.json app/*/pyproject.toml app/*/pom.xml app/*/Cargo.toml app/*/go.mod; do
  [ -f "$manifest" ] && echo "  -> found $manifest (may be a placeholder; no dependencies installed)"
done
record "product setup" "PASS" "separate from coordination bootstrap; follow the chosen stack's README after ownership is assigned"
echo ""

# 5. Name -----------------------------------------------------------------
echo "5/10 identifying you"
NAME=""
NAMES=()
if [ "$AUTO" = "1" ] && [ -f ".hackos-user" ]; then
  IFS= read -r NAME < .hackos-user || true
fi
if [ "$HAVE_PY3" = "1" ]; then
  while IFS= read -r candidate; do
    [ -n "$candidate" ] && NAMES+=("$candidate")
  done < <(python3 - "$STATE_DIR/team.json" <<'PYEOF'
import json, sys
try:
    with open(sys.argv[1]) as f:
        for member in json.load(f).get("members", []):
            print(member["name"])
except (OSError, ValueError, KeyError):
    print("hack-os: roster unavailable; identity remains unconfirmed", file=sys.stderr)
PYEOF
  )
fi
if [ "$AUTO" = "0" ] && [ "${#NAMES[@]}" -gt 0 ]; then
  echo "  Pick your name from team.json (including on a rerun):"
  select PICK in "${NAMES[@]}"; do
    if [ -n "$PICK" ]; then NAME="$PICK"; break; fi
  done
elif [ -z "$NAME" ] && [ "$HAVE_PY3" = "1" ]; then
  NAME="$(python3 - "$STATE_DIR/team.json" "$(git config user.name 2>/dev/null || true)" <<'PYEOF'
import json, sys
try:
    with open(sys.argv[1]) as f:
        members = json.load(f).get("members", [])
    matches = [m["name"] for m in members if sys.argv[2].casefold() in
               [n.casefold() for n in [m["name"], *m.get("git_names", [])]]]
    print(matches[0] if len(matches) == 1 else "unconfirmed")
except (OSError, ValueError, KeyError):
    print("unconfirmed")
PYEOF
  )"
fi
NAME="${NAME:-unconfirmed}"
MATCHED=0
for candidate in "${NAMES[@]}"; do
  [ "$candidate" = "$NAME" ] && MATCHED=1
done
if [ "$MATCHED" = "1" ]; then
  record "identity" "PASS" "$NAME matches team.json; run interactively to correct it"
else
  record "identity" "WARN" "$NAME is not a unique roster match; no ownership inferred. Run ./bootstrap.sh interactively."
fi
echo ""

# 6. Harness ---------------------------------------------------------------
echo "6/10 confirming your harness"
HARNESS_ON_FILE=""
if [ "$HAVE_PY3" = "1" ] && [ -f "$STATE_DIR/team.json" ]; then
  HARNESS_ON_FILE="$(python3 - "$STATE_DIR/team.json" "$NAME" <<'PYEOF'
import json, sys
try:
    with open(sys.argv[1]) as f:
        members = json.load(f).get("members", [])
    print(next((m.get("harness", "") for m in members if m.get("name") == sys.argv[2]), ""))
except (OSError, ValueError):
    pass
PYEOF
  )"
fi

HARNESS_AUTO_DETECTED=0
if [ "$AUTO" = "1" ]; then
  if [ -f .hackos-user ]; then
    HARNESS="$(sed -n '2p' .hackos-user)"
    HDETAIL="kept existing local harness"
  elif [ -n "${CLAUDECODE:-}" ] || [ -n "${CLAUDE_CODE_SESSION_ID:-}" ]; then
    HARNESS="claude-code"
    HDETAIL="auto-detected from Claude Code's own env vars"
  elif [ -n "${CODEX_SANDBOX_NETWORK_DISABLED:-}" ] || [ -n "${CODEX_HOME:-}" ]; then
    HARNESS="codex"
    HDETAIL="auto-detected from Codex's own env vars"
  elif [ -n "$HARNESS_ON_FILE" ]; then
    HARNESS="$HARNESS_ON_FILE"
    HDETAIL="kept from team.json (no harness env var seen)"
  else
    HARNESS="unconfirmed"
    HDETAIL="not detected; run bootstrap interactively"
  fi
  HARNESS_AUTO_DETECTED=1
  echo "  auto-detected harness: $HARNESS ($HDETAIL)"
else
  echo "  1) claude-code"
  echo "  2) codex"
  read -r -p "  Which harness do you run? [1/2]: " HCHOICE
  case "$HCHOICE" in
    2) HARNESS="codex" ;;
    *) HARNESS="claude-code" ;;
  esac
fi

if [ "$HARNESS" != "claude-code" ] && [ "$HARNESS" != "codex" ]; then
  record "harness" "WARN" "unconfirmed or unsupported harness; shared AGENTS.md still works"
elif [ -n "$HARNESS_ON_FILE" ] && [ "$HARNESS_ON_FILE" != "$HARNESS" ]; then
  record "harness" "WARN" "team.json says $NAME runs $HARNESS_ON_FILE, you selected $HARNESS — mismatch flagged, not silently overwritten. Fix team.json or re-run and pick correctly."
elif [ "$HARNESS_AUTO_DETECTED" = "1" ]; then
  record "harness" "PASS" "$HARNESS auto-detected for $NAME — re-run './bootstrap.sh' yourself to confirm interactively"
else
  record "harness" "PASS" "$HARNESS confirmed for $NAME"
fi
if [ "$AUTO" = "0" ] || [ ! -f .hackos-user ]; then
  umask 077
  { printf '%s\n' "$NAME"; printf '%s\n' "$HARNESS"; } > .hackos-user || record "identity file" "WARN" "could not save local identity"
fi
echo ""

# 7. Detect installed agent CLI + print next steps -------------------------
echo "7/10 harness-specific next steps"
if [ "$HARNESS" = "claude-code" ]; then
  if command -v claude >/dev/null 2>&1; then
    record "claude CLI" "PASS" "found on PATH"
  else
    record "claude CLI" "WARN" "not found on PATH — install Claude Code first"
  fi
  echo "  -> AGENTS.md is the shared procedure; SessionStart is optional"
  echo "  -> prompt capture and agent teams are off by default"
  echo "  -> approve/authenticate only optional MCP servers you actually need"
else
  if command -v codex >/dev/null 2>&1; then
    record "codex CLI" "PASS" "found on PATH"
  else
    record "codex CLI" "WARN" "not found on PATH — install Codex first"
  fi
  echo "  -> no plugin or prompt hook is required"
  echo "  -> optional harness-specific tools are verified separately on your installed version"
  echo "  -> AGENTS.md is read automatically by Codex, no extra step needed"
fi
echo ""

# 8. MCP reminder ------------------------------------------------------------
echo "8/10 MCP authentication reminder"
echo "  MCP connections are per-person OAuth and are NOT inherited from cloning"
echo "  this repo. Each teammate authenticates individually. Do this the day"
echo "  before the event if needed. Optional servers, not onboarding requirements:"
echo "  Servers configured in .mcp.json:"
if [ -f ".mcp.json" ] && [ "$HAVE_PY3" = "1" ]; then
  python3 -c "
import json
try:
    with open('.mcp.json') as f:
        data = json.load(f)
    for name in data.get('mcpServers', {}):
        print('   -', name)
except Exception:
    pass
"
  record "MCP config" "PASS" ".mcp.json present, see servers listed above"
else
  record "MCP config" "WARN" ".mcp.json missing or python3 unavailable to list it"
fi
echo ""

# 9. Dashboard -----------------------------------------------------------
echo "9/10 dashboard"
echo "  -> new UI: npm --prefix team-setup/board/web ci (once), then npm --prefix team-setup/board/web run dev"
echo "  -> built UI or no-install fallback: python3 team-setup/board/serve.py"
echo "  The API and UI use the same repository state; no product dependencies are installed here."
if [ "$HAVE_PY3" = "1" ]; then
  record "dashboard API" "PASS" "Python runtime available; start the server to verify readiness"
else
  record "dashboard API" "WARN" "python3 unavailable — use the markdown files in state/ directly"
fi
if [ -f team-setup/board/web/dist/index.html ]; then
  record "dashboard UI" "PASS" "built frontend available for the Python server"
else
  record "dashboard UI" "WARN" "frontend not built; use the npm commands above for the new workspace"
fi
echo ""

# 10. Summary ---------------------------------------------------------------
echo "10/10 summary"
echo "-----------------------------------------------------------------"
printf "%-16s %-6s %s\n" "CHECK" "STATUS" "DETAIL"
for r in "${RESULTS[@]}"; do
  IFS='|' read -r label status detail <<< "$r"
  printf "%-16s %-6s %s\n" "$label" "$status" "$detail"
done
echo "-----------------------------------------------------------------"

if [ "$HAVE_PY3" = "1" ] && [ -f "$STATE_DIR/pipeline.json" ]; then
  python3 -c "
import json
try:
    with open('$STATE_DIR/pipeline.json') as f:
        p = json.load(f)
    with open('$STATE_DIR/event.json') as f:
        event = json.load(f)
    if event.get('mode') == 'example' or ('mode' not in event and 'WORKED EXAMPLE' in event.get('_comment', '')) or not event.get('event_name'):
        print('No active event; fictional examples are inactive. Initialize only after approval.')
        raise SystemExit(0)
    cur = p.get('current_stage')
    for s in p.get('stages', []):
        if s.get('id') == cur:
            print('Current stage: {} ({})'.format(cur, s.get('owner', '?')))
            break
    else:
        print('Current stage: {}'.format(cur))
except Exception as e:
    print('Could not read pipeline.json:', e)
"
else
  echo "Current stage: unknown (pipeline.json unreadable)"
fi

echo ""
if [ "$AUTO" = "1" ]; then
  echo "hack-os bootstrap — done (ran in auto mode: identity/harness were"
  echo "inferred, not confirmed by a human). Two things still need you"
  echo "directly, no agent can do these: approve/authenticate each MCP"
  echo "server your harness prompts for, and set your own personal API"
  echo "keys — see team-setup/playbooks/mcp-setup.md. Re-run"
  echo "'./bootstrap.sh' yourself in a real terminal anytime to confirm or"
  echo "fix identity interactively."
else
  echo "hack-os bootstrap — done. Screenshot the table above and share it with"
  echo "the team as your 'fully set up' confirmation. See"
  echo "team-setup/playbooks/new-event-setup.md for the dry run this feeds into."
fi
exit 0
