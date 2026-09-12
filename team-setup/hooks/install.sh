#!/usr/bin/env bash
# hack-os hooks: install.sh
# Copies post-commit and pre-push into .git/hooks and makes the harness
# prompt-submit hooks executable. Idempotent — safe to re-run. Backs up any
# pre-existing non-hack-os hook once, before overwriting.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
GIT_HOOKS_DIR="$(git -C "$ROOT" rev-parse --git-path hooks 2>/dev/null)" || exit 1
case "$GIT_HOOKS_DIR" in /*) ;; *) GIT_HOOKS_DIR="$ROOT/$GIT_HOOKS_DIR" ;; esac
if [ -n "$(git -C "$ROOT" config --get core.hooksPath 2>/dev/null || true)" ]; then
  echo "hack-os hooks: custom hooksPath preserved; ask its owner to integrate hooks explicitly" >&2
  exit 1
fi
mkdir -p "$GIT_HOOKS_DIR" || exit 1
FAILED=0

install_hook() {
  local name="$1"
  local src="$SCRIPT_DIR/$name"
  local dest="$GIT_HOOKS_DIR/$name"

  if [ ! -f "$src" ]; then
    echo "hack-os hooks: WARN — $src missing, skipping $name" >&2
    FAILED=1
    return
  fi
  if [ -L "$dest" ]; then
    echo "hack-os hooks: existing symlink $name preserved; integrate manually" >&2
    FAILED=1
    return
  fi
  if [ -f "$dest" ]; then
    if cmp -s "$src" "$dest"; then
      echo "hack-os hooks: $name already current" >&2
      return
    fi
    if ! grep -q "hack-os git hook" "$dest" 2>/dev/null; then
      echo "hack-os hooks: existing $name preserved; ask its owner to integrate manually" >&2
      FAILED=1
      return
    fi
    cp -p "$dest" "$dest.hackos-backup-$(date +%Y%m%d%H%M%S)-$$" || { FAILED=1; return; }
  fi
  if cp "$src" "$dest" && chmod +x "$dest"; then
    echo "hack-os hooks: installed $name" >&2
  else
    echo "hack-os hooks: could not install $name" >&2
    FAILED=1
  fi
}

install_hook post-commit
install_hook pre-push

# Harness prompt-submit hooks are invoked directly by .claude/settings.json
# and Codex's hooks.json, not copied into .git/hooks — just make them
# executable here so both harnesses can run them.
for f in claude-session-start.sh claude-prompt-submit.sh codex-prompt-submit.sh; do
  if [ -f "$SCRIPT_DIR/$f" ]; then
    chmod +x "$SCRIPT_DIR/$f"
    echo "hack-os hooks: $f ready" >&2
  else
    echo "hack-os hooks: WARN — $f missing" >&2
  fi
done

echo "hack-os hooks: install finished; prompt capture remains disabled unless explicitly opted in" >&2
exit "$FAILED"
