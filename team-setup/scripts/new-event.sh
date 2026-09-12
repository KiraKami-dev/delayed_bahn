#!/usr/bin/env bash
# hack-os scripts: new-event.sh
# Interactive setup for a new hackathon. Fills state/event.json, resets
# pipeline.json stages to pending, clears state/ back to blank templates,
# and archives the PREVIOUS event's state under state/archive/<slug>/ first
# -- so this is what makes the repo reusable rather than single-use
# Roster is preserved; previous ownership is archived and reset to unassigned.
set -eu

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 1
STATE_DIR="team-setup/state"

if ! command -v python3 >/dev/null 2>&1; then
  echo "hack-os new-event: Python 3 unavailable; no files changed." >&2
  exit 1
fi

# --- archive previous event, if one exists -------------------------------
CONFIG=""
CONFIRMED=0
if [ "${1:-}" = "--from-json" ]; then
  CONFIG="${2:-}"
  if [ -z "$CONFIG" ] || [ "${3:-}" != "--confirm-reset" ]; then
    echo "Usage: new-event.sh --from-json <event-config> --confirm-reset" >&2
    echo "Archives ALL previous state and tasks, then initializes blank active state and unassigned owners." >&2
    exit 2
  fi
  CONFIRMED=1
elif [ "$#" -gt 0 ] || [ ! -t 0 ]; then
  echo "Run interactively, or provide --from-json <event-config> --confirm-reset. No files changed." >&2
  exit 2
fi

# --- prompt for event.json fields -----------------------------------------
if [ "$CONFIRMED" = "0" ]; then
  echo "Stop other writers first. This archives all current state, tasks, and ownership; resets assignments; preserves the roster."
  read -r -p "Type RESET to approve this exact archive-and-initialize operation: " ANSWER
  [ "$ANSWER" = "RESET" ] || { echo "Cancelled; nothing changed."; exit 2; }
  read -r -p "Event name: " HACKOS_EVENT_NAME
  read -r -p "Venue: " HACKOS_VENUE
  read -r -p "Build starts (ISO 8601 with timezone, or blank): " HACKOS_BUILD_STARTS
  read -r -p "Submission deadline (ISO 8601 with timezone, or blank): " HACKOS_SUBMISSION_DEADLINE
  read -r -p "Submit target offset hours [-2]: " HACKOS_SUBMIT_OFFSET
  read -r -p "Tracks (comma-separated): " HACKOS_TRACKS_RAW
  read -r -p "Tracks published in advance? [y/N]: " HACKOS_TRACKS_KNOWN
  read -r -p "Reveal window (blank if unknown): " HACKOS_REVEAL_WINDOW
  read -r -p "Team formation deadline (ISO 8601 with timezone, or blank): " HACKOS_TEAM_FORMATION_DEADLINE
  read -r -p "Submission format [unknown/live_pitch/video/both]: " HACKOS_SUBMISSION_FORMAT
  read -r -p "Pitch length in minutes (blank if unknown): " HACKOS_PITCH_LEN
  read -r -p "Partners (comma-separated): " HACKOS_PARTNERS_RAW
  read -r -p "Credits provider: " HACKOS_CREDITS_PROVIDER
  read -r -p "Credits amount: " HACKOS_CREDITS_AMOUNT
  read -r -p "Authoritative coordination branch [main]: " HACKOS_COORDINATION_BRANCH
  read -r -p "Coordination maintainer (roster name, or blank): " HACKOS_COORDINATION_MAINTAINER
  export HACKOS_EVENT_NAME HACKOS_VENUE HACKOS_BUILD_STARTS HACKOS_SUBMISSION_DEADLINE HACKOS_SUBMIT_OFFSET
  export HACKOS_TRACKS_RAW HACKOS_TRACKS_KNOWN HACKOS_REVEAL_WINDOW HACKOS_TEAM_FORMATION_DEADLINE
  export HACKOS_SUBMISSION_FORMAT HACKOS_PITCH_LEN HACKOS_PARTNERS_RAW HACKOS_CREDITS_PROVIDER HACKOS_CREDITS_AMOUNT
  export HACKOS_COORDINATION_BRANCH HACKOS_COORDINATION_MAINTAINER
fi

# --- reset pipeline.json stages to pending ---------------------------------
# --- clear state back to blank templates (owners.md, team.json untouched) --
python3 - "$CONFIG" <<'PYEOF'
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import uuid
from datetime import datetime, timezone

root = Path.cwd()
spec = importlib.util.spec_from_file_location("board", root / "team-setup/board/serve.py")
board = importlib.util.module_from_spec(spec)
spec.loader.exec_module(board)
state = root / "team-setup/state"
tasks = root / "team-setup/board/tasks.json"

def field(name, default=""):
    return os.environ.get("HACKOS_" + name) or default

def csv(name):
    return [x.strip() for x in field(name).split(",") if x.strip()]

try:
    if sys.argv[1]:
        with open(sys.argv[1]) as f:
            event = json.load(f)
    else:
        event = {"event_name": field("EVENT_NAME"), "venue": field("VENUE"),
            "build_starts": field("BUILD_STARTS"), "submission_deadline": field("SUBMISSION_DEADLINE"),
            "submit_target_offset_hours": float(field("SUBMIT_OFFSET", "-2")),
            "tracks": csv("TRACKS_RAW"), "tracks_known_in_advance": field("TRACKS_KNOWN").lower() in ("y", "yes"),
            "reveal_window": field("REVEAL_WINDOW"), "team_formation_deadline": field("TEAM_FORMATION_DEADLINE"),
            "submission_format": field("SUBMISSION_FORMAT", "unknown"),
            "pitch_length_minutes": float(field("PITCH_LEN")) if field("PITCH_LEN") else None,
            "partners": csv("PARTNERS_RAW"), "credits": {"provider": field("CREDITS_PROVIDER"), "amount": field("CREDITS_AMOUNT")},
            "sleep_rota": [], "coordination_branch": field("COORDINATION_BRANCH", "main"),
            "coordination_maintainer": field("COORDINATION_MAINTAINER")}
    if not isinstance(event, dict):
        raise ValueError("event config must be an object")
    event["mode"] = "active"
    event["event_id"] = uuid.uuid4().hex
    event.setdefault("coordination_branch", "main")
    event.setdefault("coordination_maintainer", "")
    event.pop("_comment", None)
    for name in ("build_starts", "submission_deadline", "team_formation_deadline"):
        if event.get(name):
            board.parse_date(event[name])
    if event.get("build_starts") and event.get("submission_deadline"):
        board.planning_times(event)
    if event.get("submission_format", "unknown") not in ("unknown", "live_pitch", "video", "both"):
        raise ValueError("invalid submission format")
    with board.state_lock():
        team = board.require_json(str(state / "team.json"), {"members": []})
        members = [m["name"] for m in team.get("members", [])]
        if event["coordination_maintainer"] and event["coordination_maintainer"] not in members:
            raise ValueError("coordination maintainer must be in team.json")
        pipeline = copy.deepcopy(board.require_json(str(state / "pipeline.json"), {}))
        for stage in pipeline.get("stages", []):
            stage.update(status="pending", started_at=None, completed_at=None)
            stage.pop("contract_sha256", None)
            stage.pop("freeze_commit", None)
        pipeline["current_stage"] = pipeline.get("stages", [{}])[0].get("id")
        pipeline["time_basis"] = "build_starts to submit_target; final 10% is buffer"
        previous_tasks = tasks.read_text() if tasks.exists() else None
        previous = {}
        for path in state.rglob("*"):
            if path.is_symlink():
                raise ValueError("State contains a symlink; review it before archival")
            if path.is_file():
                previous[str(path.relative_to(state))] = hashlib.sha256(path.read_bytes()).hexdigest()
        staging = root / "team-setup" / (".hackos-event-" + event["event_id"])
        staging.mkdir(mode=0o700)
        archive = staging / "archive" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + event["event_id"][:8])
        archive.mkdir(parents=True)
        board.write_json(str(archive / "manifest.json"), previous)
        if previous_tasks is not None:
            board.write_text(str(archive / "tasks.json"), previous_tasks)
            if (archive / "tasks.json").read_text() != previous_tasks:
                raise OSError("Task archive verification failed")
        board.write_json(str(staging / "event.json"), event)
        board.write_json(str(staging / "team.json"), team)
        board.write_json(str(staging / "pipeline.json"), pipeline)
        board.write_json(str(staging / "research.json"), {"research": []})
        blanks = {
            "decisions.md": "# Decisions\n\nAppend accepted decisions using stable d- IDs; see AGENTS.md.\n",
            "ideas.md": "# Ideas\n\nRecord raised ideas using stable i- IDs; see AGENTS.md.\n",
            "partner-notes.md": "",
            "00-reveal-capture/rubric.md": "",
            "00-reveal-capture/reveals/_TEMPLATE.md": (state / "00-reveal-capture/reveals/_TEMPLATE.md").read_text() if (state / "00-reveal-capture/reveals/_TEMPLATE.md").exists() else "# Track reveal\n\nProblem, rubric, constraints, resources: capture verbatim.\n",
            "01-challenge-pick/challenge.md": "<!-- Chosen track + problem statement (verbatim). Frozen once written. -->\n",
            "02-demo-script/demo-script.md": "<!-- The 90-second demo, shot by shot. FROZEN once written. -->\n",
            "02-demo-script/not-building.md": "<!-- Explicit out-of-scope list, derived from demo-script.md. -->\n",
            "03-contract-freeze/contract.md": "<!-- Shared types + API surface. FROZEN at this gate. -->\n",
            "03-contract-freeze/architecture.mmd": "%% Mermaid diagram, generated from contract.md.\n",
            "04-integration/.gitkeep": "", "05-feature-freeze/.gitkeep": "", "06-polish-and-pitch/.gitkeep": "",
            "meetings/.gitkeep": "", "log/.gitkeep": ""}
        owner_rows = "# Owners\n\n## Directory ownership\n\n| Directory | Owner | Harness |\n|---|---|---|\n"
        for name in ("frontend", "backend", "agents"):
            owner_rows += "| app/{} | unassigned | - |\n".format(name)
        owner_rows += "| app/shared | generated | - |\n\n## Feature ownership\n\n| Feature | Owner | Sub-owners |\n|---|---|---|\n"
        owner_rows += "\n## Gate roles\n\n| Role | Person |\n|---|---|\n"
        for role in ("reveal-capture scouts", "challenge-pick facilitator", "contract-freeze lead", "integration coordinator", "feature-freeze caller", "polish-and-pitch lead"):
            owner_rows += "| {} | unassigned |\n".format(role)
        blanks["owners.md"] = owner_rows
        for name, text in blanks.items():
            board.write_text(str(staging / name), text)
        moved = False
        try:
            os.replace(state, archive / "state")
            moved = True
            for name, digest in previous.items():
                if hashlib.sha256((archive / "state" / name).read_bytes()).hexdigest() != digest:
                    raise OSError("State archive verification failed")
            board.write_json(str(tasks), {"tasks": []})
            os.replace(staging, state)
        except BaseException:
            if moved and not state.exists():
                os.replace(archive / "state", state)
            if previous_tasks is not None:
                board.write_text(str(tasks), previous_tasks)
            raise
        print("Initialized blank active event; ownership is unassigned.")
        print("Verified previous state and tasks preserved at:", state / archive.relative_to(staging))
        print("Older archives remain inside that previous state, unchanged. Commit and sync only after reviewing the diff.")
except (OSError, ValueError, KeyError, TypeError) as error:
    print("hack-os new-event: failed; retained existing data and any staging archive for review:", error, file=sys.stderr)
    raise SystemExit(1)
PYEOF
