#!/usr/bin/env bash
# hack-os git hook: claude-prompt-submit
# Wired as a Claude Code UserPromptSubmit hook via .claude/settings.json.
# Disabled by default; explicit opt-in writes only a private local log.
# Not used by the activity panel or shared memory — never blocks, never
# modifies the prompt, always exits 0. This hook observes, it does not gate.
set -u
[ "${HACKOS_CAPTURE_PROMPTS:-0}" = "1" ] || exit 0
umask 077

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

if ! command -v python3 >/dev/null 2>&1; then
  exit 0
fi

INPUT="$(cat 2>/dev/null || true)"

HACKOS_ROOT="$ROOT" HACKOS_INPUT="$INPUT" HACKOS_HARNESS="claude-code" \
python3 - <<'PYEOF' 2>/dev/null
import json, os, subprocess
from datetime import datetime

root = os.environ.get("HACKOS_ROOT", ".")
state_dir = os.path.join(root, "team-setup", "state")
raw = os.environ.get("HACKOS_INPUT", "")

# Claude Code sends UserPromptSubmit input as JSON on stdin with a "prompt" field.
prompt_text = raw
try:
    payload = json.loads(raw)
    if isinstance(payload, dict):
        prompt_text = payload.get("prompt", raw)
except Exception:
    pass


def t_plus(build_starts):
    if not build_starts:
        return None
    try:
        start = datetime.fromisoformat(build_starts)
    except Exception:
        return None
    delta = datetime.now(start.tzinfo) - start
    total_minutes = int(delta.total_seconds() // 60)
    sign = "-" if total_minutes < 0 else "+"
    total_minutes = abs(total_minutes)
    return "T{}{:02d}:{:02d}".format(sign, total_minutes // 60, total_minutes % 60)


author = ""
try:
    with open(os.path.join(root, ".hackos-user")) as f:
        author = f.readline().strip()
except Exception:
    pass

event = {}
try:
    with open(os.path.join(state_dir, "event.json")) as f:
        event = json.load(f)
except Exception:
    pass

stage = None
try:
    with open(os.path.join(state_dir, "pipeline.json")) as f:
        stage = json.load(f).get("current_stage")
except Exception:
    pass

entry = {
    "timestamp": datetime.now().isoformat(timespec="seconds"),
    "t_offset": t_plus(event.get("build_starts")),
    "author": author,
    "harness": os.environ.get("HACKOS_HARNESS", ""),
    "prompt": prompt_text,
    "stage": stage,
}

try:
    local_path = subprocess.check_output(["git", "rev-parse", "--git-path", "hackos-prompts.jsonl"], cwd=root, text=True).strip()
    log_path = os.path.join(root, local_path)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")
except Exception:
    pass
PYEOF

exit 0
