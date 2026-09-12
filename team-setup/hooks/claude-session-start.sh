#!/usr/bin/env bash
# hack-os git hook: claude-session-start
# Bonus layer for teammates using Claude Code (spec 4.5, Part 2 rule
# 3) — wired as a SessionStart hook via .claude/settings.json. Injects the
# current stage, the caller's own ownership area, and the frozen contract
# into context. Degrades to a no-op if any file is missing. Nothing
# critical depends on this: other harnesses do not run this hook (AGENTS.md
# step 0 is the cross-harness backstop for the auto-bootstrap below), and
# AGENTS.md's boot sequence (section 1) covers the same ground for anyone
# reading it directly.
#
# First-launch auto-bootstrap: if .hackos-user doesn't exist yet, this
# person has never run setup on this machine. Kick off
# `bootstrap.sh --auto` in the background (non-interactive, infers
# identity/harness) so a brand-new teammate gets local Git hook checks.
# No downloads or product installs are run. Backgrounded and log-redirected
# so a slow network call never blocks session start; only fires once,
# since its own first act is writing .hackos-user.
set -u

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
STATE_DIR="$ROOT/team-setup/state"

FIRST_RUN=0
if [ ! -f "$ROOT/.hackos-user" ] && [ -f "$ROOT/bootstrap.sh" ]; then
  FIRST_RUN=1
  mkdir -p "$STATE_DIR/log" 2>/dev/null
  nohup bash "$ROOT/bootstrap.sh" --auto > "$STATE_DIR/log/bootstrap-auto.log" 2>&1 < /dev/null &
  disown 2>/dev/null || true
fi

if ! command -v python3 >/dev/null 2>&1; then
  exit 0
fi

HACKOS_ROOT="$ROOT" HACKOS_STATE_DIR="$STATE_DIR" HACKOS_FIRST_RUN="$FIRST_RUN" \
python3 - <<'PYEOF' 2>/dev/null
import json, os

root = os.environ.get("HACKOS_ROOT", ".")
state_dir = os.environ.get("HACKOS_STATE_DIR", "")

parts = []

try:
    with open(os.path.join(state_dir, "event.json")) as f:
        event = json.load(f)
except Exception:
    print("hack-os: event state unavailable; read AGENTS.md, do not assume product requirements.")
    raise SystemExit(0)

if event.get("mode") == "example" or ("mode" not in event and "WORKED EXAMPLE" in event.get("_comment", "")) or not event.get("event_name"):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext":
        "hack-os: No active event. Fictional examples are inactive, not requirements or ownership assignments. Read AGENTS.md. Do not reset state without approval."}}))
    raise SystemExit(0)

if os.environ.get("HACKOS_FIRST_RUN") == "1":
    parts.append(
        "hack-os: first launch on this machine — running './bootstrap.sh "
        "--auto' in the background now (log: team-setup/state/log/"
        "bootstrap-auto.log) to install local git hooks and "
        "auto-detect your identity. That does NOT cover MCP server "
        "approval/authentication or your personal API keys — those need "
        "you directly, see team-setup/playbooks/mcp-setup.md. Re-run "
        "./bootstrap.sh yourself anytime to confirm or fix identity."
    )

user = ""
try:
    with open(os.path.join(root, ".hackos-user")) as f:
        user = f.readline().strip()
except Exception:
    pass

stage = None
try:
    with open(os.path.join(state_dir, "pipeline.json")) as f:
        pipeline = json.load(f)
        stage = pipeline.get("current_stage")
except Exception:
    pass

if stage:
    parts.append("hack-os: current pipeline stage is '{}'.".format(stage))

if user:
    parts.append("hack-os: you are {} — check state/owners.md for your directory ownership before editing.".format(user))
    try:
        with open(os.path.join(state_dir, "owners.md")) as f:
            owners_text = f.read()
        for line in owners_text.splitlines():
            if "WORKED EXAMPLE" not in owners_text and user in [cell.strip() for cell in line.split("|")]:
                parts.append("hack-os owners.md match: " + line.strip())
    except Exception:
        pass

try:
    with open(os.path.join(state_dir, "03-contract-freeze", "contract.md")) as f:
        contract = f.read().strip()
    if contract and "WORKED EXAMPLE" not in contract:
        frozen = any(s.get("id") == "contract-freeze" and s.get("completed_at") for s in pipeline.get("stages", []))
        parts.append("hack-os: real contract is {}. Read team-setup/state/03-contract-freeze/contract.md in full before product work.".format("frozen" if frozen else "not yet frozen"))
except Exception:
    pass

if not parts:
    parts.append("hack-os: no event/pipeline state found yet. See AGENTS.md boot sequence.")

parts.append("hack-os: reread current decisions, owners, and your task before substantial work. Local files are a snapshot, not live team state; sync safely with the coordination branch.")
context = "\n\n".join(parts)

output = {
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": context,
    }
}

print(json.dumps(output))
PYEOF

exit 0
