#!/usr/bin/env bash
# hack-os scripts: extract-story.sh
# Turns local Git history (without any shared change or prompt log)
# into a readable build timeline with T+ offsets, for the "how we built it"
# slide and the team's own retrospective.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 1

STATE_DIR="team-setup/state"
CHANGES_LOG="$STATE_DIR/log/changes.jsonl"

if command -v python3 >/dev/null 2>&1; then
  python3 - <<'PYEOF'
import importlib.util
spec = importlib.util.spec_from_file_location("board", "team-setup/board/serve.py")
board = importlib.util.module_from_spec(spec)
spec.loader.exec_module(board)
print("# Build Story\n\nGenerated from local Git history (latest 100 commits); not inferred current work.\n")
for entry in reversed(board.git_activity()):
    print("- [{}] {} — {} ({})".format(entry.get("t_offset") or entry["timestamp"], entry["message"], entry["author"], entry["sha"][:10]))
PYEOF
  exit $?
fi

echo "hack-os extract-story: Python unavailable; using plain git log without event offsets" >&2
if ! command -v git >/dev/null 2>&1; then
  echo "hack-os extract-story: git not found either, nothing to extract" >&2
  exit 0
fi

echo "# Build Story"
echo ""
echo "Generated from \`git log\` (changes.jsonl was empty)."
echo ""
git log --reverse --pretty=format:'- **%ad** %s — %an' --date=format:'%Y-%m-%d %H:%M'
echo ""
