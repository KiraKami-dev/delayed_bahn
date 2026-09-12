#!/usr/bin/env python3
"""hack-os dashboard server.

Local, file-backed, writable. The API uses only Python 3 standard-library
modules. Serves the built Vite UI when present, or the legacy static assets
and a JSON API backed by team-setup/state/ and team-setup/board/tasks.json.
Git synchronizes machines; revision checks protect concurrent local saves.
Mutations require a local origin, token and current revision. Multi-file
writes use a recoverable local journal; unsafe recovery retains all files.
Examples stay inactive until an explicitly confirmed event initialization.

Run: python3 team-setup/board/serve.py [port]
"""
import contextlib
import fcntl
import hashlib
import http.server
import importlib.util
import json
import math
import os
import re
import secrets
import socketserver
import subprocess
import sys
import tempfile
import urllib.parse
import uuid
from datetime import datetime, timedelta, timezone

BOARD_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(BOARD_DIR, "..", ".."))
STATE_DIR = os.path.join(ROOT, "team-setup", "state")
TASKS_PATH = os.path.join(BOARD_DIR, "tasks.json")
CSRF_TOKEN = secrets.token_urlsafe(32)

# notes-intake.py has a hyphen in its name, load it by path instead of `import`.
_spec = importlib.util.spec_from_file_location("notes_intake", os.path.join(BOARD_DIR, "notes-intake.py"))
notes_intake = importlib.util.module_from_spec(_spec)
try:
    _spec.loader.exec_module(notes_intake)
except Exception as e:
    notes_intake = None
    print("hack-os board: notes-intake.py failed to load ({}), notes/research endpoints degrade to a plain warning".format(e), file=sys.stderr)


# --- small file helpers, every one fails soft ------------------------------

def read_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, data):
    write_text(path, json.dumps(data, indent=2, allow_nan=False) + "\n")


def read_text(path, default=""):
    try:
        with open(path) as f:
            return f.read()
    except Exception:
        return default


def write_text(path, text):
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".hackos-write-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def append_line(text, line):
    return text + ("" if not text or text.endswith("\n") else "\n") + line.rstrip("\n") + "\n"


def append_text(path, line):
    write_text(path, append_line(read_text(path), line))


def git_output(*args):
    try:
        result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                                text=True, timeout=5)
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def runtime_path(name):
    path = git_output("rev-parse", "--git-path", "hackos-" + name)
    if not path:
        raise ValueError("Git metadata unavailable; use markdown until Git is available")
    return os.path.abspath(os.path.join(ROOT, path))


@contextlib.contextmanager
def state_lock():
    with open(runtime_path("board.lock"), "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            recover_transaction()
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def recover_transaction():
    path = runtime_path("transaction.json")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        transaction = json.load(f)
    for change in transaction:
        target = os.path.realpath(os.path.join(ROOT, change["path"]))
        runtime_dir = os.path.realpath(os.path.dirname(runtime_path("preview-")))
        setup_dir = os.path.realpath(os.path.join(ROOT, "team-setup"))
        is_preview = os.path.dirname(target) == runtime_dir and re.fullmatch(r"hackos-(?:preview|meeting)-[a-f0-9]{32}\.json", os.path.basename(target))
        if os.path.commonpath([target, setup_dir]) != setup_dir and not is_preview:
            raise ValueError("Invalid recovery path; retained transaction for manual review")
        current = read_text(target, None)
        if current not in (change["before"], change["after"]):
            raise ValueError("Recovery conflicts with a direct file edit; retained journal for manual review")
    for change in transaction:
        write_text(os.path.join(ROOT, change["path"]), change["after"])
    os.unlink(path)


def commit_files(updates):
    transaction = [{"path": os.path.relpath(path, ROOT), "before": read_text(path, None),
                    "after": text} for path, text in updates.items()]
    write_json(runtime_path("transaction.json"), transaction)
    recover_transaction()


def state_revision():
    paths = [TASKS_PATH] + [os.path.join(STATE_DIR, name) for name in (
        "event.json", "team.json", "pipeline.json", "owners.md", "decisions.md",
        "ideas.md", "research.json", *DOC_PATHS.values())]
    digest = hashlib.sha256()
    for path in sorted(set(paths)):
        digest.update(os.path.relpath(path, ROOT).encode())
        digest.update(b"\0")
        digest.update(read_text(path, "<missing>").encode())
        digest.update(b"\0")
    return digest.hexdigest()


def example_mode(event=None):
    event = event if event is not None else read_json(os.path.join(STATE_DIR, "event.json"), {})
    return event.get("mode") == "example" or (
        "mode" not in event and "WORKED EXAMPLE" in event.get("_comment", ""))


def load_event():
    event = require_json(os.path.join(STATE_DIR, "event.json"), {})
    return {"mode": "example"} if example_mode(event) else event


def active_text(path):
    text = read_text(path)
    return "" if example_mode() or "WORKED EXAMPLE" in text[:1000] else text


def active_json(path, default):
    data = require_json(path, default)
    return default if example_mode() or data.get("_example") else data


def new_id(prefix):
    return prefix + "-" + uuid.uuid4().hex


def one_line(value, name, default=""):
    value = default if value is None else value
    if not isinstance(value, str) or "\n" in value or "\r" in value or " — " in value:
        raise ValueError(name + " must be one line without the record delimiter ' — '")
    return value.strip()


def require_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("expected an object")
        return data
    except FileNotFoundError:
        return default
    except (ValueError, OSError):
        raise ValueError("Cannot overwrite unreadable file: " + os.path.relpath(path, ROOT))


def validate_tasks(tasks):
    if not isinstance(tasks, list) or any(not isinstance(t, dict) for t in tasks):
        raise ValueError("tasks must be an array of objects")
    ids = [t.get("id") for t in tasks]
    if any(not isinstance(i, str) or not i for i in ids) or len(ids) != len(set(ids)):
        raise ValueError("task IDs must be unique nonempty strings")
    for task in tasks:
        if not isinstance(task.get("title"), str) or not task["title"].strip():
            raise ValueError("each task needs a title")
        if task.get("status") not in ("backlog", "building", "integrating", "demo-ready"):
            raise ValueError("invalid task status")
        for field in ("sub_owners", "depends_on"):
            if not isinstance(task.get(field, []), list) or any(not isinstance(x, str) for x in task.get(field, [])):
                raise ValueError(field + " must be an array of strings")
        if task["id"] in task.get("depends_on", []):
            raise ValueError("a task cannot depend on itself")
        target = task.get("target_time")
        if target and (not isinstance(target, str) or not re.fullmatch(r"T\+(?:100|\d{1,2})(?:\.\d+)?%", target)
                       or float(target[2:-1]) > 100):
            raise ValueError("target_time must be T+0% through T+100%")
    return tasks


def git_activity():
    output = git_output("log", "-100", "--format=%x1e%H%x1f%aI%x1f%an%x1f%s", "--name-only", "--root") or ""
    event = load_event()
    entries = []
    for chunk in output.split("\x1e"):
        lines = chunk.strip().splitlines()
        if not lines:
            continue
        fields = lines[0].split("\x1f", 3)
        if len(fields) != 4:
            continue
        sha, timestamp, author, message = fields
        entries.append({"sha": sha, "timestamp": timestamp, "author": author,
                        "message": message, "files": [f for f in lines[1:] if f],
                        "t_offset": t_plus(event.get("build_starts"), datetime.fromisoformat(timestamp)),
                        "source": "git log"})
    return entries


def freshness():
    branch = git_output("branch", "--show-current")
    upstream = git_output("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    delta = git_output("rev-list", "--left-right", "--count", "HEAD...@{upstream}") if upstream else None
    ahead, behind = (map(int, delta.split()) if delta else (None, None))
    remote_checked = None
    fetch_path = git_output("rev-parse", "--git-path", "FETCH_HEAD")
    if fetch_path:
        try:
            remote_checked = datetime.fromtimestamp(os.path.getmtime(os.path.join(ROOT, fetch_path)), timezone.utc).isoformat()
        except OSError:
            pass
    dirty = git_output("status", "--porcelain", "--", "team-setup/state", "team-setup/board/tasks.json")
    remote_check = read_json(runtime_path("remote-check.json"), {})
    return {"remote_check": remote_check, "head": git_output("rev-parse", "HEAD"), "branch": branch, "upstream": upstream,
            "ahead": ahead, "behind": behind, "last_fetch_at": remote_checked,
            "remote_freshness": "unknown until an explicit successful fetch",
            "local_changes": dirty.splitlines() if dirty else [],
            "coordination_branch": load_event().get("coordination_branch", "main"),
            "coordination_maintainer": load_event().get("coordination_maintainer") or "unassigned"}


def parse_date(value):
    date = datetime.fromisoformat((value or "").replace("Z", "+00:00"))
    if date.tzinfo is None:
        raise ValueError("Event timestamps need a timezone offset, e.g. +02:00")
    return date


def planning_times(event):
    start = parse_date(event.get("build_starts"))
    deadline = parse_date(event.get("submission_deadline"))
    offset = event.get("submit_target_offset_hours")
    offset = -2 if offset is None else float(offset)
    if not math.isfinite(offset) or offset >= 0:
        raise ValueError("Submit target offset must be negative")
    target = deadline + timedelta(hours=offset)
    if not start < target < deadline:
        raise ValueError("Submit target must be after build start and before the real deadline")
    return start, target, deadline


def read_jsonl(path):
    out = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        pass
    return out


def t_plus(build_starts, at=None):
    if not build_starts:
        return None
    try:
        start = datetime.fromisoformat(build_starts)
    except Exception:
        return None
    now = at or datetime.now(start.tzinfo)
    if (now.tzinfo is None) != (start.tzinfo is None):
        return None
    delta = now - start
    total_minutes = int(delta.total_seconds() // 60)
    sign = "-" if total_minutes < 0 else "+"
    total_minutes = abs(total_minutes)
    return "T{}{:02d}:{:02d}".format(sign, total_minutes // 60, total_minutes % 60)


def now_t_plus():
    return t_plus(load_event().get("build_starts")) or "T+00:00"


def get_snapshot_tags():
    """Local git tag list, no network -- git is already a hard dependency."""
    try:
        out = subprocess.run(
            ["git", "tag", "-l", "demo-ok-*", "--sort=-creatordate"],
            cwd=ROOT, capture_output=True, text=True, timeout=5,
        )
        return [t for t in out.stdout.splitlines() if t.strip()]
    except Exception:
        return []


def get_smoke_last():
    try:
        return read_json(runtime_path("smoke-last.json"), None)
    except ValueError:
        return None


def current_sleep_shift(sleep_rota):
    """window is 'HH:MM-HH:MM', compared against wall-clock time of day."""
    now = datetime.now().time()
    for shift in sleep_rota or []:
        window = shift.get("window") or ""
        if "-" not in window:
            continue
        start_s, end_s = window.split("-", 1)
        try:
            start_t = datetime.strptime(start_s.strip(), "%H:%M").time()
            end_t = datetime.strptime(end_s.strip(), "%H:%M").time()
        except Exception:
            continue
        if start_t <= end_t:
            active = start_t <= now <= end_t
        else:
            active = now >= start_t or now <= end_t  # wraps past midnight
        if active:
            return shift
    return None


# --- state paths for the read-only doc panel -------------------------------

DOC_PATHS = {
    "challenge": "01-challenge-pick/challenge.md",
    "demo_script": "02-demo-script/demo-script.md",
    "not_building": "02-demo-script/not-building.md",
    "contract": "03-contract-freeze/contract.md",
    "architecture": "03-contract-freeze/architecture.mmd",
    "partner_notes": "partner-notes.md",
}


def document_lock(key):
    if key == "architecture":
        return "Generated from the contract by the owning agent"
    gate = {"contract": "contract-freeze", "demo_script": "demo-script", "not_building": "demo-script", "challenge": "challenge-pick"}.get(key)
    pipeline = read_json(os.path.join(STATE_DIR, "pipeline.json"), {})
    stage = next((s for s in pipeline.get("stages", []) if s.get("id") == gate), {})
    return "Frozen at the {} gate; an approved change must go through the owning agent".format(gate) if stage.get("completed_at") or stage.get("status") == "done" else ""


def meeting_records():
    if example_mode():
        return []
    directory = os.path.join(STATE_DIR, "meetings")
    records = []
    if not os.path.isdir(directory):
        return records
    for name in os.listdir(directory):
        path = os.path.join(directory, name)
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,180}\.(?:md|txt)", name) or os.path.islink(path) or not os.path.isfile(path):
            continue
        text = read_text(path)
        records.append({"id": name, "title": next((line.strip("# ")[:90] for line in text.splitlines() if line.strip()), "Untitled meeting"),
                        "excerpt": text[:180], "created_at": datetime.fromtimestamp(os.path.getmtime(path), timezone.utc).isoformat()})
    return sorted(records, key=lambda r: r["created_at"], reverse=True)[:50]


def ai_status():
    configured = bool(notes_intake and notes_intake.load_openai_key())
    return {"configured": configured, "available": notes_intake is not None,
            "source": "environment" if os.environ.get("OPENAI_API_KEY") else "local" if configured else "none"}


# --- pipeline resolution ----------------------------------------------------

def resolve_pct_time(build_starts, submission_deadline, pct):
    if pct is None:
        return None
    try:
        start = parse_date(build_starts)
        end = parse_date(submission_deadline)
        pct = float(pct)
        if end <= start or not 0 <= pct <= 100:
            return None
        return (start + (end - start) * (pct / 100.0)).isoformat(timespec="seconds")
    except (TypeError, ValueError):
        return None


def build_pipeline_view():
    event = load_event()
    pipeline = require_json(os.path.join(STATE_DIR, "pipeline.json"), {"current_stage": None, "stages": []})
    inactive = example_mode() or not event.get("event_name")
    countdown = {"submit_target": None, "real_deadline": None, "buffer_starts": None,
                 "seconds_to_submit_target": None, "seconds_to_real_deadline": None}
    warning = None
    try:
        start, target, deadline = planning_times(event)
        now = datetime.now(timezone.utc)
        countdown.update({"submit_target": target.isoformat(), "real_deadline": deadline.isoformat(),
                          "buffer_starts": (start + (target - start) * .9).isoformat(),
                          "seconds_to_submit_target": (target - now).total_seconds(),
                          "seconds_to_real_deadline": (deadline - now).total_seconds()})
    except (TypeError, ValueError, OverflowError) as error:
        warning = "Configure timezone-aware build/deadline timestamps and an early submit target. " + str(error)
    stages = []
    for stage in pipeline.get("stages", []):
        s = dict(stage)
        if inactive:
            s.update(status="pending", started_at=None, completed_at=None)
        s["resolved_start"] = resolve_pct_time(event.get("build_starts"), countdown["submit_target"], stage.get("window_start_pct"))
        s["resolved_end"] = resolve_pct_time(event.get("build_starts"), countdown["submit_target"], stage.get("window_end_pct"))
        if stage.get("pre_build"):
            s["schedule_note"] = "Before the event" if event.get("tracks_known_in_advance") else "Before build starts"
            s["resolved_end"] = event.get("build_starts") or None
        stages.append(s)
    return {"current_stage": None if inactive else pipeline.get("current_stage"),
            "stages": stages, "countdown": countdown, "warning": warning}


# --- decisions.md / ideas.md parsing ---------------------------------------

DECISION_RE = re.compile(
    r"^- (?:\[(?P<id>d-[\w-]+)\] )?\[(?P<ts>T[+-]\d{2,}:\d{2})\] (?P<body>.+?) — (?P<who>[^—]+?) — (?P<reason>.*?)"
    r"(?: — supersedes \[(?P<supersedes>[^\]]+)\])?(?: — promotes \[(?P<promotes>[^\]]+)\])?$"
)
IDEA_RE = re.compile(
    r"^- (?:\[(?P<id>i-[\w-]+)\] )?\[(?P<ts>T[+-]\d{2,}:\d{2})\] (?P<body>.+?) — (?:raised by )?(?P<who>[^—]+?) — status: (?P<status>\w+)$"
)


def record_id(match, prefix):
    stable = "|".join(match.group(field) for field in ("ts", "body", "who"))
    return match.group("id") or prefix + "-legacy-" + hashlib.sha256(stable.encode()).hexdigest()[:24]


def resolve_reference(entries, reference):
    matches = [e for e in entries if reference in (e["id"], e["timestamp"])]
    if len(matches) != 1:
        raise ValueError("Reference missing or ambiguous; use a unique record ID: " + str(reference))
    return matches[0]


def parse_decisions(text):
    entries = []
    for line in text.splitlines():
        m = DECISION_RE.match(line.strip())
        if m:
            entries.append({
                "id": record_id(m, "d"),
                "promotes_idea": m.group("promotes"),
                "timestamp": m.group("ts"),
                "decision": m.group("body").strip(),
                "who": m.group("who").strip(),
                "reason": m.group("reason").strip(),
                "supersedes": m.group("supersedes"),
                "raw": line.strip(),
            })
    superseded_by = {}
    for index, entry in enumerate(entries):
        if entry["supersedes"]:
            try:
                previous = resolve_reference(entries[:index], entry["supersedes"])
                superseded_by[previous["id"]] = entry["id"]
            except ValueError:
                entry["link_warning"] = "Unresolved or ambiguous supersession"
    for entry in entries:
        entry["superseded_by"] = superseded_by.get(entry["id"])
    return entries


def parse_ideas(text):
    entries = []
    for line in text.splitlines():
        m = IDEA_RE.match(line.strip())
        if m:
            entries.append({
                "id": record_id(m, "i"),
                "timestamp": m.group("ts"),
                "idea": m.group("body").strip(),
                "who": m.group("who").strip(),
                "status": m.group("status").strip(),
                "raw": line.strip(),
            })
    return entries


# --- focus panel (spec 4.9) --------------------------------------------------

def build_focus_view():
    changes = git_activity()
    team = read_json(os.path.join(STATE_DIR, "team.json"), {"members": []})
    focus = []
    matched = set()
    for member in team.get("members", []):
        names = [member["name"], *member.get("git_names", [])]
        commits = [c for c in changes if c["author"] in names]
        matched.update(names)
        focus.append({"person": member["name"], "commits": commits[:3], "source": "git log"})
    for name in sorted({c["author"] for c in changes} - matched):
        focus.append({"person": name, "commits": [c for c in changes if c["author"] == name][:3],
                      "source": "git log", "unmapped_author": True})
    return focus


# --- owners.md rewriting -----------------------------------------------------

def rewrite_owner_row(owners_text, table_key_col_value, new_owner, new_sub_owners=None):
    """Plain rewrite of one row's Owner (and optionally Sub-owners) cell in
    whichever markdown table contains a row starting with the given first
    cell. Not append-only -- reassigning ownership is routine (spec 4.4)."""
    lines = owners_text.splitlines()
    out = []
    changed = False
    table = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            table = None
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if cells[0] in ("Directory", "Feature", "Role", "Person"):
                table = cells[0] if cells[0] != "Person" else None
            elif table and len(cells) >= 2 and cells[0] == table_key_col_value:
                if changed:
                    raise ValueError("Ownership key appears more than once; clarify the mapping first")
                cells[1] = new_owner
                if table == "Feature" and new_sub_owners is not None and len(cells) >= 3:
                    cells[2] = ", ".join(new_sub_owners)
                line = "| " + " | ".join(cells) + " |"
                changed = True
        out.append(line)
    return "\n".join(out) + ("\n" if owners_text.endswith("\n") else ""), changed


# --- request handler ---------------------------------------------------------

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BOARD_DIR, **kwargs)

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, fmt, *args):
        sys.stderr.write("hack-os board: " + (fmt % args) + "\n")

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        super().end_headers()

    def _trusted_request(self):
        port = self.server.server_address[1]
        hosts = {"127.0.0.1:" + str(port), "localhost:" + str(port)}
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        return host in hosts and (not origin or origin == "http://" + host)

    def _send_json(self, obj, status=200):
        if isinstance(obj, dict):
            obj.setdefault("revision", state_revision())
        body = json.dumps(obj, indent=2, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self):
        if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            raise ValueError("Content-Type must be application/json")
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not 0 < length <= 1024 * 1024:
            raise ValueError("Request body must be between 1 byte and 1 MiB")
        def invalid_constant(value):
            raise ValueError("Non-finite JSON numbers are not supported")
        result = json.loads(self.rfile.read(length).decode("utf-8"), parse_constant=invalid_constant)
        if not isinstance(result, dict):
            raise ValueError("Request body must be an object")
        return result

    # ---- GET -----------------------------------------------------------

    def do_GET(self):
        if not self._trusted_request():
            return self._send_json({"ok": False, "error": "Untrusted host or origin"}, 403)
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        if parsed.path.startswith("/api/"):
            try:
                with state_lock():
                    if parsed.path == "/api/state":
                        return self._get_state()
                    if parsed.path == "/api/docs":
                        return self._get_docs()
                    if parsed.path == "/api/focus":
                        return self._send_json({"focus": build_focus_view()})
                    if parsed.path.startswith("/api/meetings/"):
                        name = parsed.path.removeprefix("/api/meetings/")
                        record = next((m for m in meeting_records() if m["id"] == name), None)
                        if record:
                            return self._send_json({**record, "text": read_text(os.path.join(STATE_DIR, "meetings", name))})
                return self._send_json({"ok": False, "error": "Unknown endpoint"}, 404)
            except (ValueError, OSError, TypeError, KeyError, AttributeError):
                return self._send_json({"ok": False, "error": "State unreadable or recovery pending; files retained for review"}, 503)
        return self._serve_static(parsed.path)

    def _serve_static(self, path, head=False):
        built = os.path.join(BOARD_DIR, "web", "dist")
        if path in ("/", "/index.html", "/favicon.svg") and os.path.isfile(os.path.join(built, "index.html")):
            directory, relative = built, "favicon.svg" if path == "/favicon.svg" else "index.html"
        elif path.startswith("/assets/") and re.fullmatch(r"/assets/[A-Za-z0-9_./-]+\.(?:js|css|svg|woff2|png)", path):
            directory, relative = built, path.lstrip("/")
        elif path in ("/", "/index.html", "/legacy", "/legacy/", "/app.js", "/style.css"):
            directory, relative = BOARD_DIR, path.lstrip("/") if path in ("/app.js", "/style.css") else "index.html"
        else:
            self._send_json({"ok": False, "error": "Not found"}, 404)
            return
        target = os.path.realpath(os.path.join(directory, relative))
        if os.path.commonpath([target, os.path.realpath(directory)]) != os.path.realpath(directory) or not os.path.isfile(target):
            self._send_json({"ok": False, "error": "Not found"}, 404)
            return
        self.directory, self.path = directory, "/" + relative
        return super().do_HEAD() if head else super().do_GET()

    def do_HEAD(self):
        if not self._trusted_request():
            self.send_response(403)
            self.end_headers()
            return
        return self._serve_static(urllib.parse.urlparse(self.path).path, head=True)

    def _get_state(self):
        event = load_event()
        pipeline_view = build_pipeline_view()
        tasks = active_json(TASKS_PATH, {"tasks": []})
        validate_tasks(tasks.get("tasks", []))
        decisions = parse_decisions(active_text(os.path.join(STATE_DIR, "decisions.md")))
        ideas = parse_ideas(active_text(os.path.join(STATE_DIR, "ideas.md")))
        research = active_json(os.path.join(STATE_DIR, "research.json"), {"research": []})
        owners_text = active_text(os.path.join(STATE_DIR, "owners.md"))
        changes = git_activity()
        for task in tasks.get("tasks", []):
            target = task.get("target_time") or ""
            match = re.fullmatch(r"T\+(\d+(?:\.\d+)?)%", target)
            task["resolved_target"] = resolve_pct_time(event.get("build_starts"), pipeline_view["countdown"]["submit_target"], float(match[1])) if match else None

        # contract drift: any change to contract.md after the contract-freeze
        # stage's completed_at
        drift = None
        freeze = next((s for s in pipeline_view["stages"] if s.get("id") == "contract-freeze"), {})
        if not example_mode() and freeze.get("completed_at") and freeze.get("contract_sha256"):
            contract = active_text(os.path.join(STATE_DIR, DOC_PATHS["contract"]))
            drift = hashlib.sha256(contract.encode()).hexdigest() != freeze["contract_sha256"]

        files_last_hour = []
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
            for c in changes:
                ts = c.get("timestamp")
                try:
                    if ts and datetime.fromisoformat(ts) >= cutoff:
                        files_last_hour.append(c)
                except Exception:
                    pass
        except Exception:
            pass

        self._send_json({
            "event": event,
            "workspace_id": hashlib.sha256(os.path.realpath(ROOT).encode()).hexdigest()[:16],
            "team": read_json(os.path.join(STATE_DIR, "team.json"), {"members": []}),
            "meetings": meeting_records(),
            "ai": ai_status(),
            "example_mode": example_mode(),
            "csrf_token": CSRF_TOKEN,
            "freshness": freshness(),
            "event_is_blank": not bool(event.get("event_name")),
            "pipeline": pipeline_view,
            "tasks": tasks.get("tasks", []),
            "decisions": decisions,
            "ideas": ideas,
            "research": research.get("research", []),
            "owners_raw": owners_text,
            "commits": changes[:100],
            "files_last_hour": files_last_hour,
            "sleep_rota": event.get("sleep_rota", []),
            "current_sleep_shift": current_sleep_shift(event.get("sleep_rota", [])),
            "contract_drift": drift,
            "snapshot_tags": get_snapshot_tags(),
            "smoke_last": None if example_mode() else get_smoke_last(),
            "smoke_current": self._smoke_current(),
        })

    def _smoke_current(self):
        smoke = get_smoke_last() or {}
        return bool(not example_mode() and smoke.get("ok") and smoke.get("clean")
                    and smoke.get("head") == git_output("rev-parse", "HEAD")
                    and git_output("status", "--porcelain", "--", "app") == "")

    def _get_docs(self):
        out = {}
        for key, rel in DOC_PATHS.items():
            text = active_text(os.path.join(STATE_DIR, rel))
            content = re.sub(r"<!--.*?-->", "", text, flags=re.S).strip()
            if key == "architecture":
                content = re.sub(r"(?m)^\s*(?:%%.*|(?:graph|flowchart)\s+\w+\s*)$", "", content).strip()
            locked = document_lock(key)
            out[key] = {"content": text if content else "", "not_written_yet": not bool(content),
                        "editable": not bool(locked), "locked_reason": locked}
        self._send_json(out)

    # ---- POST ------------------------------------------------------------

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        routes = {
            "/api/event": self._post_event,
            "/api/docs": self._post_doc,
            "/api/settings/openai": self._post_openai_key,
            "/api/tasks": self._post_tasks,
            "/api/stage": self._post_stage,
            "/api/decision": self._post_decision,
            "/api/owners": self._post_owners,
            "/api/ideas": self._post_ideas,
            "/api/ideas/status": self._post_ideas_status,
            "/api/research": self._post_research,
            "/api/research/override": self._post_research_override,
            "/api/notes": self._post_notes,
            "/api/notes/confirm": self._post_notes_confirm,
        }
        handler = routes.get(parsed.path)
        if not handler:
            return self._send_json({"ok": False, "error": "unknown endpoint"}, 404)
        if not self._trusted_request() or not secrets.compare_digest(self.headers.get("X-Hackos-Token", ""), CSRF_TOKEN):
            return self._send_json({"ok": False, "error": "Untrusted request; refresh the local dashboard"}, 403)
        try:
            body = self._read_json_body()
            with state_lock():
                setup_route = parsed.path in ("/api/event", "/api/settings/openai")
                if (example_mode() and parsed.path != "/api/settings/openai") or (not load_event().get("event_name") and not setup_route):
                    return self._send_json({"ok": False, "error": "Set up your workspace first. Existing examples require the confirmed new-event setup."}, 409)
                if parsed.path != "/api/settings/openai" and any("WORKED EXAMPLE" in read_text(os.path.join(STATE_DIR, name))[:1000]
                       for name in ("decisions.md", "ideas.md", "owners.md", *DOC_PATHS.values())):
                    return self._send_json({"ok": False, "error": "Example records remain; use confirmed new-event setup to archive them before saving real state."}, 409)
                if self.headers.get("If-Match") != state_revision():
                    return self._send_json({"ok": False, "error": "State changed since this draft loaded. Refresh, review, and retry; draft retained."}, 409)
                for path in (TASKS_PATH, os.path.join(STATE_DIR, "research.json"), os.path.join(STATE_DIR, "pipeline.json")):
                    require_json(path, {})
                return handler(body)
        except ValueError as error:
            return self._send_json({"ok": False, "error": str(error)}, 400)
        except (OSError, TypeError, KeyError, AttributeError):
            return self._send_json({"ok": False, "error": "Save failed; input retained. Check state files and any pending recovery journal."}, 503)

    def _post_event(self, body):
        fields = body.get("event")
        allowed = {"event_name", "venue", "build_starts", "submission_deadline", "submit_target_offset_hours",
                   "tracks", "partners", "tracks_known_in_advance", "submission_format", "pitch_length_minutes",
                   "coordination_branch", "coordination_maintainer"}
        if not isinstance(fields, dict) or set(fields) - allowed:
            raise ValueError("Unknown workspace configuration fields")
        path = os.path.join(STATE_DIR, "event.json")
        event = {**require_json(path, {}), **fields}
        if not one_line(event.get("event_name"), "Workspace name"):
            raise ValueError("Give this workspace a name")
        for name in ("event_name", "venue", "coordination_branch", "coordination_maintainer"):
            if name in event:
                event[name] = one_line(event[name], name)
        for name in ("tracks", "partners"):
            if not isinstance(event.get(name, []), list) or any(not isinstance(v, str) for v in event.get(name, [])):
                raise ValueError(name + " must be a list of names")
        offset = event.get("submit_target_offset_hours", -2)
        if not isinstance(offset, (int, float)) or not math.isfinite(offset) or offset >= 0:
            raise ValueError("The early submission offset must be a negative number of hours")
        for name in ("build_starts", "submission_deadline"):
            if event.get(name):
                parse_date(event[name])
        if event.get("build_starts") and event.get("submission_deadline"):
            planning_times(event)
        if event.get("submission_format", "unknown") not in ("unknown", "live_pitch", "video", "both"):
            raise ValueError("Invalid submission format")
        pitch = event.get("pitch_length_minutes")
        if pitch is not None and (not isinstance(pitch, (int, float)) or not 0 < pitch <= 180):
            raise ValueError("Pitch length must be between 0 and 180 minutes")
        members = read_json(os.path.join(STATE_DIR, "team.json"), {}).get("members", [])
        if event.get("coordination_maintainer") and event["coordination_maintainer"] not in [m["name"] for m in members]:
            raise ValueError("Choose a coordinator from your team")
        event["mode"] = "active"
        event.setdefault("event_id", uuid.uuid4().hex)
        write_json(path, event)
        self._send_json({"ok": True})

    def _post_doc(self, body):
        key, content = body.get("key"), body.get("content")
        if not isinstance(key, str) or key not in DOC_PATHS or not isinstance(content, str):
            raise ValueError("Choose a valid document and supply text content")
        locked = document_lock(key)
        if locked:
            return self._send_json({"ok": False, "error": locked}, 409)
        write_text(os.path.join(STATE_DIR, DOC_PATHS[key]), content)
        self._send_json({"ok": True})

    def _post_openai_key(self, body):
        if os.environ.get("OPENAI_API_KEY"):
            return self._send_json({"ok": False, "error": "The key is supplied by the environment. Change it there and restart the server."}, 409)
        key = body.get("key")
        if not isinstance(key, str) or not re.fullmatch(r"sk-[A-Za-z0-9_-]{16,400}", key.strip()):
            raise ValueError("Enter a valid OpenAI API key. Its value is never included in responses or logs.")
        write_text(os.path.join(ROOT, ".hackos-openai-key"), key.strip())
        self._send_json({"ok": True, "warning": "Key stored on this machine only. It will be used when you request an AI preview."})

    def _post_tasks(self, body):
        tasks = validate_tasks(body.get("tasks"))
        for task in tasks:
            task.pop("resolved_target", None)
        write_json(TASKS_PATH, {"tasks": tasks})
        self._send_json({"ok": True, "tasks": tasks})

    def _post_stage(self, body):
        path = os.path.join(STATE_DIR, "pipeline.json")
        pipeline = read_json(path, {"current_stage": None, "stages": []})
        stages = pipeline.get("stages", [])
        ids = [s["id"] for s in stages]
        target = body.get("stage_id")
        current = pipeline.get("current_stage")

        if target is None:
            if current in ids:
                idx = ids.index(current)
                target = ids[idx + 1] if idx + 1 < len(ids) else current
            else:
                target = ids[0] if ids else None

        if target not in ids:
            raise ValueError("Unknown stage")
        if current in ids and target != current and ids.index(target) != ids.index(current) + 1:
            raise ValueError("Advance one stage at a time; record a decision before changing the pipeline directly")
        now_offset = datetime.now(timezone.utc).isoformat()
        for s in stages:
            if s["id"] == current and (s["id"] != target or current == ids[-1]):
                s["status"] = "done"
                s["completed_at"] = now_offset
                if current == "contract-freeze":
                    contract = active_text(os.path.join(STATE_DIR, DOC_PATHS["contract"]))
                    if not re.sub(r"<!--.*?-->", "", contract, flags=re.S).strip():
                        raise ValueError("Write the real contract before freezing it")
                    s["contract_sha256"] = hashlib.sha256(contract.encode()).hexdigest()
                    s["freeze_commit"] = git_output("rev-parse", "HEAD")
            elif s["id"] == target:
                s["status"] = "in_progress"
                if not s.get("started_at"):
                    s["started_at"] = now_offset

        pipeline["current_stage"] = target
        write_json(path, pipeline)
        self._send_json({"ok": True, "current_stage": target})

    def _post_decision(self, body):
        decision = one_line(body.get("decision"), "decision")
        who = one_line(body.get("who"), "who")
        reason = one_line(body.get("reason"), "reason") or "reason not recorded"
        if not decision or not who:
            raise ValueError("decision and who are required")
        path = os.path.join(STATE_DIR, "decisions.md")
        original = active_text(path)
        entries = parse_decisions(original)
        ts, rid = now_t_plus(), new_id("d")
        line = "- [{}] [{}] {} — {} — {}".format(rid, ts, decision, who, reason)
        updates = {}
        if body.get("supersedes"):
            previous = resolve_reference(entries, body["supersedes"])
            if previous.get("superseded_by"):
                raise ValueError("That decision was already superseded; reference the current decision")
            line += " — supersedes [{}]".format(previous["id"])
        if body.get("promotes_idea"):
            ideas_path = os.path.join(STATE_DIR, "ideas.md")
            text = active_text(ideas_path)
            idea = resolve_reference(parse_ideas(text), body["promotes_idea"])
            if idea["status"] in ("adopted", "discarded"):
                raise ValueError("Only a raised or exploring idea can be promoted")
            line += " — promotes [{}]".format(idea["id"])
            updates[ideas_path] = text.replace(idea["raw"], re.sub(r"status: \w+$", "status: adopted", idea["raw"]), 1)
        updates[path] = append_line(original, line)
        commit_files(updates)
        self._send_json({"ok": True, "line": line, "timestamp": ts, "id": rid})

    def _post_owners(self, body):
        path = os.path.join(STATE_DIR, "owners.md")
        text = active_text(path)
        key = one_line(body.get("key"), "key")
        owner = one_line(body.get("owner"), "owner")
        members = read_json(os.path.join(STATE_DIR, "team.json"), {}).get("members", [])
        member = next((m for m in members if m.get("name") == owner), None)
        if not key or (owner and not member) or "|" in key or "|" in owner or key == "app/shared":
            raise ValueError("Select an assignable directory/feature/role and a person from team.json")
        sub_owners = body.get("sub_owners")
        if sub_owners is not None and (not isinstance(sub_owners, list) or any(s not in [m["name"] for m in members] for s in sub_owners)):
            raise ValueError("Sub-owners must belong to the roster")
        new_text, changed = rewrite_owner_row(text, key, owner, sub_owners)
        if key.startswith("app/"):
            new_text = re.sub(r"(?m)^(\| " + re.escape(key) + r" \| " + re.escape(owner) + r" \| )[^|]*(\|)$",
                              lambda m: m[1] + (member.get("harness", "-") if member else "-") + " " + m[2], new_text)
        if not changed:
            return self._send_json({"ok": False, "error": "no matching row found for '{}'".format(key)})
        write_text(path, new_text)
        self._send_json({"ok": True, "key": key, "owner": owner})

    def _post_ideas(self, body):
        idea = one_line(body.get("idea"), "idea")
        who = one_line(body.get("who"), "who")
        if not idea or not who:
            raise ValueError("idea and who are required")
        ts, rid = now_t_plus(), new_id("i")
        line = "- [{}] [{}] {} — {} — status: raised".format(rid, ts, idea, who)
        append_text(os.path.join(STATE_DIR, "ideas.md"), line)
        self._send_json({"ok": True, "line": line, "timestamp": ts, "id": rid})

    def _set_idea_status(self, reference, status):
        path = os.path.join(STATE_DIR, "ideas.md")
        text = active_text(path)
        idea = resolve_reference(parse_ideas(text), reference)
        if idea["status"] == "adopted":
            raise ValueError("An adopted idea is historical; supersede its decision instead")
        replacement = re.sub(r"status: \w+$", "status: " + status, idea["raw"])
        write_text(path, text.replace(idea["raw"], replacement, 1))
        return True

    def _post_ideas_status(self, body):
        status = body.get("status")
        if status not in ("raised", "exploring", "discarded"):
            raise ValueError("Use decision promotion to adopt; otherwise choose raised, exploring, or discarded")
        self._set_idea_status(body.get("id") or body.get("timestamp"), status)
        self._send_json({"ok": True})

    def _post_research(self, body):
        summary = body.get("summary")
        logged_by = one_line(body.get("logged_by"), "logged_by") or "unassigned"
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError("summary is required")
        path = os.path.join(STATE_DIR, "research.json")
        data = require_json(path, {"research": []})
        entry = {"id": new_id("r"), "logged_by": logged_by, "topic": summary.splitlines()[0][:80],
                 "summary": summary, "viability": "untested", "viability_reasoning": "No confirmed evidence recorded",
                 "linked_idea": None, "spawned_idea": None, "linked_mvp": body.get("linked_mvp"),
                 "logged_at": now_t_plus(), "override": False, "auto_source": "unassessed"}
        if body.get("linked_idea"):
            entry["linked_idea"] = resolve_reference(parse_ideas(active_text(os.path.join(STATE_DIR, "ideas.md"))), body["linked_idea"])["id"]
        data["research"].append(entry)
        write_json(path, data)
        warning = None
        if body.get("assess") and notes_intake:
            classification = notes_intake.classify_research(summary)
            entry["assessment"] = classification
            entry["auto_source"] = "openai" if classification.get("ok") else "unassessed"
            warning = None if classification.get("ok") else "AI assessment unavailable; raw finding saved as untested"
            write_json(path, data)
        self._send_json({"ok": True, "entry": entry, "warning": warning})

    def _post_research_override(self, body):
        rid = body.get("id")
        path = os.path.join(STATE_DIR, "research.json")
        data = read_json(path, {"research": []})
        found = False
        if body.get("viability") not in ("untested", "feasible", "not-viable", "implemented"):
            raise ValueError("Invalid viability")
        if not one_line(body.get("confirmed_by"), "confirmed_by"):
            raise ValueError("Record who confirmed this assessment")
        if body.get("viability") == "implemented" and not body.get("evidence"):
            raise ValueError("Implemented requires evidence, such as a commit or smoke result")
        if body.get("linked_idea"):
            body["linked_idea"] = resolve_reference(parse_ideas(active_text(os.path.join(STATE_DIR, "ideas.md"))), body["linked_idea"])["id"]
        for r in data["research"]:
            if r.get("id") == rid:
                for field in ("viability", "viability_reasoning", "linked_idea", "linked_mvp", "confirmed_by", "evidence"):
                    if field in body:
                        r[field] = body[field]
                if r.get("linked_idea"):
                    r["spawned_idea"] = None
                r["override"] = True
                found = True
        if not found:
            return self._send_json({"ok": False, "error": "research id not found"})
        write_json(path, data)
        self._send_json({"ok": True})

    def _post_notes(self, body):
        text = body.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text is required")
        digest = hashlib.sha256(text.encode()).hexdigest()
        meeting_file = os.path.join(STATE_DIR, "meetings", "notes-{}.md".format(digest))
        if not os.path.exists(meeting_file):
            write_text(meeting_file, text)
        result = {"ok": True, "decisions": [], "tasks": [], "ideas": [], "flagged": [],
                  "meeting_file": os.path.relpath(meeting_file, ROOT)}
        if body.get("structure"):
            event = load_event()
            event_key = event.get("event_id") or json.dumps([event.get("event_name"), event.get("build_starts")])
            receipt_id = uuid.uuid5(uuid.NAMESPACE_URL, event_key + digest).hex
            receipt_path = runtime_path("meeting-" + receipt_id + ".json")
            if read_json(receipt_path, {}).get("ok"):
                result["warning"] = "These exact notes were already confirmed for this event; no duplicate records written"
                return self._send_json(result)
            extraction = notes_intake.structure_meeting_notes(text) if notes_intake else {"ok": False}
            if extraction.get("ok"):
                result.update(extraction)
                preview_id = uuid.uuid4().hex
                preview = {"revision": state_revision(), "result": extraction,
                           "source": digest, "receipt_id": receipt_id, "confirmed": False}
                write_json(runtime_path("preview-" + preview_id + ".json"), preview)
                result["preview_id"] = preview_id
            else:
                result["warning"] = "AI unavailable or invalid response; raw notes saved, nothing auto-classified"
        self._send_json(result)

    def _post_notes_confirm(self, body):
        """Writes a previously-previewed structuring result. Not itself
        listed as a numbered endpoint in the spec, but required by 4.12's
        confirm/discard flow -- reuses the same append logic as
        /api/decision, /api/ideas, /api/tasks so there is exactly one
        implementation of each write, never a second path."""
        preview_id = body.get("preview_id", "")
        if not isinstance(preview_id, str) or not re.fullmatch(r"[a-f0-9]{32}", preview_id):
            raise ValueError("A server-generated preview ID is required")
        preview_path = runtime_path("preview-" + preview_id + ".json")
        preview = require_json(preview_path, {})
        if preview.get("confirmed"):
            return self._send_json(preview["receipt"])
        if preview.get("revision") != state_revision():
            return self._send_json({"ok": False, "error": "State changed since extraction; raw notes retained. Generate a new preview."}, 409)
        extraction = dict(preview["result"])
        selection = body.get("selection")
        if selection is not None:
            if not isinstance(selection, dict) or set(selection) != {"decisions", "ideas", "tasks"}:
                raise ValueError("Select entries from each preview section")
            for bucket, indexes in selection.items():
                if not isinstance(indexes, list) or any(type(i) is not int or i < 0 or i >= len(extraction.get(bucket, [])) for i in indexes):
                    raise ValueError("Invalid preview selection")
                extraction[bucket] = [extraction[bucket][i] for i in sorted(set(indexes))]
            if not any(extraction[bucket] for bucket in selection):
                raise ValueError("Select at least one item to apply")
        updates = {}
        counts = {"ok": True, "decisions_written": 0, "ideas_written": 0, "tasks_written": 0}
        for bucket, prefix, filename in (("decisions", "d", "decisions.md"), ("ideas", "i", "ideas.md")):
            path = os.path.join(STATE_DIR, filename)
            text = active_text(path)
            for item in extraction.get(bucket, []):
                value = one_line(item.get("text"), "extracted text")
                who = one_line(item.get("who"), "extracted author") or "unassigned"
                identity = prefix + "-" + uuid.uuid5(uuid.NAMESPACE_URL, preview["source"] + bucket + value).hex
                if "[" + identity + "]" in text:
                    continue
                tail = "status: raised" if bucket == "ideas" else "from meeting notes " + preview["source"][:12]
                text = append_line(text, "- [{}] [{}] {} — {} — {}".format(identity, now_t_plus(), value, who, tail))
                counts[bucket + "_written"] += 1
            updates[path] = text
        tasks_data = require_json(TASKS_PATH, {"tasks": []})
        for task in extraction.get("tasks", []):
            title = one_line(task.get("title"), "task title")
            identity = "t-" + uuid.uuid5(uuid.NAMESPACE_URL, preview["source"] + "tasks" + title).hex
            if any(t.get("id") == identity for t in tasks_data["tasks"]):
                continue
            tasks_data["tasks"].append({"id": identity, "title": title, "status": "backlog",
                "owner": task.get("owner"), "sub_owners": task.get("sub_owners", []),
                "depends_on": [], "target_time": task.get("target_time"), "mvp": task.get("mvp"),
                "stage": task.get("stage"), "notes": "from meeting notes " + preview["source"][:12]})
            counts["tasks_written"] += 1
        validate_tasks(tasks_data["tasks"])
        updates[TASKS_PATH] = json.dumps(tasks_data, indent=2) + "\n"
        preview.update(confirmed=True, receipt=counts)
        updates[preview_path] = json.dumps(preview, indent=2) + "\n"
        if preview.get("receipt_id"):
            updates[runtime_path("meeting-" + preview["receipt_id"] + ".json")] = json.dumps(counts) + "\n"
        commit_files(updates)
        self._send_json(counts)


def check_remote(remote):
    if remote.startswith("-") or remote not in (git_output("remote") or "").splitlines():
        raise ValueError("Choose a configured Git remote by name")
    path = runtime_path("remote-check.json")
    check = read_json(path, {})
    try:
        result = subprocess.run(["git", "fetch", "--no-tags", remote], cwd=ROOT, capture_output=True,
                                timeout=30, env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
        ok = result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        ok = False
    check.update(remote=remote, attempted_at=datetime.now(timezone.utc).isoformat(), ok=ok)
    if ok:
        check["last_success_at"] = check["attempted_at"]
        check["last_success_remote"] = remote
    write_json(path, check)
    return ok


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--check-remote":
        if len(sys.argv) != 3:
            raise SystemExit("Usage: serve.py --check-remote <configured-remote-name>")
        try:
            ok = check_remote(sys.argv[2])
        except ValueError as error:
            raise SystemExit(str(error))
        print("Remote refs fetched; inspect and integrate safely." if ok else "Remote check failed; check network/authentication manually. Local state unchanged.")
        raise SystemExit(0 if ok else 1)
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8420
    with socketserver.ThreadingTCPServer(("127.0.0.1", port), Handler) as httpd:
        httpd.daemon_threads = True
        print("hack-os board: serving at http://127.0.0.1:{}/".format(port))
        if os.path.isfile(os.path.join(BOARD_DIR, "web", "dist", "index.html")):
            print("hack-os board: serving the React workspace; legacy fallback available at /legacy")
        else:
            print("hack-os board: legacy fallback active. Build the new UI: npm --prefix team-setup/board/web run build")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nhack-os board: stopped")


if __name__ == "__main__":
    main()
