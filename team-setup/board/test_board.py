#!/usr/bin/env python3
import importlib.util
import json
import os
import shutil
from pathlib import Path
import socketserver
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("board", Path(__file__).with_name("serve.py"))
board = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(board)


class CoordinationSmoke(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hackos-smoke-")
        self.root = Path(self.temp.name)
        self.state = self.root / "team-setup/state"
        self.state.mkdir(parents=True)
        (self.root / "team-setup/board").mkdir()
        self.original = board.ROOT, board.STATE_DIR, board.TASKS_PATH
        board.ROOT, board.STATE_DIR = str(self.root), str(self.state)
        board.TASKS_PATH = str(self.root / "team-setup/board/tasks.json")
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        self.event = {"mode": "active", "event_name": "Smoke fixture", "build_starts": "2026-01-01T10:00:00+00:00",
                      "submission_deadline": "2026-01-01T22:00:00+00:00", "submit_target_offset_hours": -2}
        board.write_json(str(self.state / "event.json"), self.event)
        board.write_json(str(self.state / "team.json"), {"members": [{"name": "Tester", "harness": "codex"}]})
        board.write_json(str(self.state / "pipeline.json"), {"current_stage": "contract-freeze", "stages": [
            {"id": "contract-freeze", "status": "in_progress", "window_start_pct": 3, "window_end_pct": 7},
            {"id": "parallel-build", "status": "pending", "window_start_pct": 7, "window_end_pct": 55},
            {"id": "polish-and-pitch", "status": "pending", "window_start_pct": 65, "window_end_pct": 90}]})
        board.write_json(board.TASKS_PATH, {"tasks": []})
        board.write_json(str(self.state / "research.json"), {"research": []})
        for name in ("ideas.md", "decisions.md"):
            board.write_text(str(self.state / name), "# " + name + "\n")
        board.write_text(str(self.state / "owners.md"), "| Directory | Owner | Harness |\n|---|---|---|\n| app/frontend | Tester | codex |\n")
        board.write_text(str(self.state / "03-contract-freeze/contract.md"), "# Real contract\nDemo interface\n")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        env = dict(os.environ, GIT_AUTHOR_NAME="Tester", GIT_AUTHOR_EMAIL="tester@example.invalid",
                   GIT_COMMITTER_NAME="Tester", GIT_COMMITTER_EMAIL="tester@example.invalid")
        subprocess.run(["git", "commit", "-qm", "coordination smoke fixture"], cwd=self.root, env=env, check=True)
        self.server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), board.Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        self.thread.start()
        self.url = "http://127.0.0.1:" + str(self.server.server_address[1])
        self.key_patch = patch.object(board.notes_intake, "load_openai_key", return_value=None)
        self.key_patch.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.key_patch.stop()
        board.ROOT, board.STATE_DIR, board.TASKS_PATH = self.original
        self.temp.cleanup()

    def request(self, path, data=None, revision=None, headers=None, raw=None):
        body = raw if raw is not None else (json.dumps(data).encode() if data is not None else None)
        request_headers = {}
        if body is not None:
            request_headers = {"Content-Type": "application/json", "X-Hackos-Token": board.CSRF_TOKEN,
                               "If-Match": revision or board.state_revision()}
        request_headers.update(headers or {})
        req = urllib.request.Request(self.url + path, data=body, headers=request_headers)
        try:
            response = urllib.request.urlopen(req, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            payload = response.read()
            return response.status, json.loads(payload) if payload else {}

    def post(self, path, data):
        status, result = self.request(path, data)
        self.assertEqual(status, 200, result)
        self.assertTrue(result["ok"], result)
        return result

    def copy_setup(self):
        source = Path(self.original[0])
        files = ["bootstrap.sh", ".gitignore", "team-setup/board/serve.py", "team-setup/board/notes-intake.py"]
        files += [str(p.relative_to(source)) for directory in ("team-setup/scripts", "team-setup/hooks")
                  for p in (source / directory).iterdir() if p.is_file()]
        for relative in files:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / relative, target)

    def run_script(self, path, *args, env=None):
        result = subprocess.run(["bash", str(self.root / path), *args], cwd=self.root,
                                env=env, input="", capture_output=True, text=True, timeout=20)
        return result

    def test_bootstrap_is_local_idempotent_and_worktree_aware(self):
        self.copy_setup()
        (self.root / ".hackos-user").write_text("Tester\ncodex\n")
        for _ in range(3):
            result = self.run_script("bootstrap.sh", "--auto")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("curl -fsSL", result.stdout)
            self.assertEqual((self.root / ".hackos-user").read_text(), "Tester\ncodex\n")
        self.assertTrue((self.root / ".git/hooks/post-commit").exists())
        self.assertFalse(list((self.root / ".git/hooks").glob("*.hackos-backup-*")))
        for harness in ("claude", "codex"):
            result = self.run_script("team-setup/hooks/" + harness + "-prompt-submit.sh",
                                     env=dict(os.environ, HACKOS_CAPTURE_PROMPTS="0"))
            self.assertEqual(result.returncode, 0)
        self.assertFalse((self.root / ".git/hackos-prompts.jsonl").exists())
        worktree = self.root / "worktree"
        subprocess.run(["git", "worktree", "add", "--detach", str(worktree), "HEAD"], cwd=self.root, check=True, capture_output=True)
        shutil.copytree(self.root / "team-setup/hooks", worktree / "team-setup/hooks")
        result = subprocess.run(["bash", str(worktree / "team-setup/hooks/install.sh")], cwd=worktree, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        custom = self.root / ".git/hooks/pre-push"
        custom.write_text("#!/bin/sh\nexit 0\n")
        result = self.run_script("team-setup/hooks/install.sh")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(custom.read_text(), "#!/bin/sh\nexit 0\n")

    def test_new_event_requires_confirmation_and_preserves_all_state(self):
        self.copy_setup()
        before = {str(p.relative_to(self.state)): p.read_bytes() for p in self.state.rglob("*") if p.is_file()}
        config = self.root / "input-event.json"
        config.write_text(json.dumps(self.event))
        denied = self.run_script("team-setup/scripts/new-event.sh", "--from-json", str(config))
        self.assertEqual(denied.returncode, 2)
        self.assertFalse((self.state / "archive").exists())
        for _ in range(2):
            result = self.run_script("team-setup/scripts/new-event.sh", "--from-json", str(config), "--confirm-reset")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        archives = list((self.state / "archive").rglob("manifest.json"))
        self.assertEqual(len(archives), 2)
        first = next(p.parent for p in archives if "03-contract-freeze/contract.md" in json.loads(p.read_text())
                     and json.loads(p.read_text())["03-contract-freeze/contract.md"] == board.hashlib.sha256(before["03-contract-freeze/contract.md"]).hexdigest())
        for name, contents in before.items():
            self.assertEqual((first / "state" / name).read_bytes(), contents)
        self.assertEqual(board.read_json(board.TASKS_PATH, {})["tasks"], [])
        self.assertIn("unassigned", (self.state / "owners.md").read_text())
        self.assertEqual(self.request("/api/state")[1]["pipeline"]["stages"][0]["status"], "pending")

    def test_smoke_snapshot_restore_and_failing_push_check(self):
        self.copy_setup()
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        env = dict(os.environ, GIT_AUTHOR_NAME="Tester", GIT_AUTHOR_EMAIL="tester@example.invalid",
                   GIT_COMMITTER_NAME="Tester", GIT_COMMITTER_EMAIL="tester@example.invalid")
        subprocess.run(["git", "commit", "-qm", "coordination script fixtures"], cwd=self.root, env=env, check=True)
        self.assertEqual(self.run_script("team-setup/scripts/smoke.sh", env=dict(env, SMOKE_COMMAND="", SMOKE_HEALTH_URL="")).returncode, 1)
        self.assertEqual(self.run_script("team-setup/scripts/snapshot.sh", "--confirm-demo").returncode, 1)
        smoke = self.run_script("team-setup/scripts/smoke.sh", env=dict(env, SMOKE_COMMAND="true", SMOKE_HEALTH_URL=""))
        self.assertEqual(smoke.returncode, 0, smoke.stdout + smoke.stderr)
        snapshot = self.run_script("team-setup/scripts/snapshot.sh", "--confirm-demo")
        self.assertEqual(snapshot.returncode, 0, snapshot.stdout + snapshot.stderr)
        tag = board.git_output("tag", "-l", "demo-ok-*")
        self.assertEqual(self.run_script("team-setup/scripts/restore.sh", tag).returncode, 2)
        before = board.git_output("rev-parse", "HEAD")
        dirty = self.root / "uncommitted.txt"
        dirty.write_text("keep my work")
        restored = self.run_script("team-setup/scripts/restore.sh", tag, "--confirm-restore")
        self.assertEqual(restored.returncode, 0, restored.stdout + restored.stderr)
        self.assertEqual(board.git_output("rev-parse", "HEAD"), before)
        self.assertEqual(dirty.read_text(), "keep my work")
        backend = self.root / "app/backend"
        backend.mkdir(parents=True)
        (backend / "pyproject.toml").write_text("")
        (backend / "demo.py").write_text("invalid python !!!")
        result = self.run_script("team-setup/hooks/pre-push")
        self.assertEqual(result.returncode, 0)
        self.assertIn("WARNING", result.stderr)
        created = Path(restored.stdout.split("Restored demo in separate worktree: ", 1)[1].splitlines()[0])
        shutil.rmtree(created)

    def test_pm_can_configure_workspace_without_resetting_records(self):
        original = (self.state / "03-contract-freeze/contract.md").read_text()
        self.event["event_name"] = ""
        board.write_json(str(self.state / "event.json"), self.event)
        self.post("/api/event", {"event": {"event_name": "Team workspace", "venue": "", "tracks": ["Track one"]}})
        state = self.request("/api/state")[1]
        self.assertEqual(state["event"]["event_name"], "Team workspace")
        self.assertEqual(state["team"]["members"][0]["name"], "Tester")
        self.assertEqual((self.state / "03-contract-freeze/contract.md").read_text(), original)
        self.assertEqual(self.request("/api/event", {"event": {"build_starts": "tomorrow"}})[0], 400)

    def test_document_editor_respects_freeze_and_retains_notes(self):
        self.post("/api/docs", {"key": "challenge", "content": "# Problem\nA real project brief.\n"})
        self.assertTrue(self.request("/api/docs")[1]["challenge"]["editable"])
        self.post("/api/stage", {})
        self.assertFalse(self.request("/api/docs")[1]["contract"]["editable"])
        self.assertEqual(self.request("/api/docs", {"key": "contract", "content": "Changed"})[0], 409)
        self.assertEqual(self.request("/api/docs", {"key": "../../outside", "content": "Changed"})[0], 400)
        notes = self.post("/api/notes", {"text": "Planning discussion\nKeep the raw transcript."})
        meetings = self.request("/api/state")[1]["meetings"]
        self.assertEqual(len(meetings), 1)
        self.assertEqual(self.request("/api/meetings/" + meetings[0]["id"])[1]["text"], "Planning discussion\nKeep the raw transcript.")
        self.assertTrue((self.root / notes["meeting_file"]).exists())

    def test_optional_key_is_local_only_and_never_returned(self):
        self.event["event_name"] = ""
        board.write_json(str(self.state / "event.json"), self.event)
        key = "sk-test-not-a-real-key-0123456789"
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            result = self.post("/api/settings/openai", {"key": key})
        self.assertNotIn(key, json.dumps(result))
        self.assertEqual((self.root / ".hackos-openai-key").read_text(), key)
        self.assertEqual((self.root / ".hackos-openai-key").stat().st_mode & 0o777, 0o600)
        self.assertNotIn(key, json.dumps(self.request("/api/state")[1]))

    def test_transcript_confirmation_only_applies_selected_items(self):
        extraction = {"ok": True, "decisions": [{"text": "Choose scope", "who": "Tester"}],
                      "ideas": [{"text": "Keep exploring", "who": "Tester"}], "tasks": [], "flagged": []}
        with patch.object(board.notes_intake, "structure_meeting_notes", return_value=extraction):
            preview = self.post("/api/notes", {"text": "Discuss options", "structure": True})
        result = self.post("/api/notes/confirm", {"preview_id": preview["preview_id"], "selection": {"decisions": [], "ideas": [0], "tasks": []}})
        self.assertEqual(result["decisions_written"], 0)
        self.assertEqual(result["ideas_written"], 1)

    def test_example_state_is_inactive_and_preserved(self):
        self.event.update(mode="example")
        board.write_json(str(self.state / "event.json"), self.event)
        before = board.read_text(str(self.state / "03-contract-freeze/contract.md"))
        state = self.request("/api/state")[1]
        self.assertTrue(state["example_mode"])
        self.assertEqual(state["tasks"], [])
        self.assertIsNone(state["pipeline"]["current_stage"])
        self.assertIsNone(state["contract_drift"])
        self.assertEqual(self.request("/api/docs")[1]["contract"]["content"], "")
        self.assertEqual(self.request("/api/ideas", {"idea": "new", "who": "Tester"})[0], 409)
        self.assertEqual(board.read_text(str(self.state / "03-contract-freeze/contract.md")), before)

    def test_gates_fit_before_target_with_timezone(self):
        for hours in (12, 48):
            start = datetime(2026, 1, 1, 10, tzinfo=timezone(timedelta(hours=2)))
            self.event.update(build_starts=start.isoformat(), submission_deadline=(start + timedelta(hours=hours)).isoformat())
            board.write_json(str(self.state / "event.json"), self.event)
            view = self.request("/api/state")[1]["pipeline"]
            target = datetime.fromisoformat(view["countdown"]["submit_target"])
            self.assertEqual(target, start + timedelta(hours=hours - 2))
            for stage in view["stages"]:
                self.assertLessEqual(datetime.fromisoformat(stage["resolved_end"]), target)
        self.event["build_starts"] = "2026-01-01T10:00"
        board.write_json(str(self.state / "event.json"), self.event)
        self.assertIsNone(self.request("/api/state")[1]["pipeline"]["countdown"]["submit_target"])

    def test_save_conflict_validation_and_origin_protection(self):
        old = board.state_revision()
        task = {"id": "t-test", "title": "Demo task", "status": "backlog", "depends_on": [], "sub_owners": []}
        self.post("/api/tasks", {"tasks": [task]})
        self.assertEqual(self.request("/api/tasks", {"tasks": []}, revision=old)[0], 409)
        self.assertEqual(self.request("/api/tasks", {"tasks": "invalid"})[0], 400)
        self.assertEqual(self.request("/api/tasks", raw=b"{")[0], 400)
        self.assertEqual(self.request("/api/tasks", {"tasks": []}, headers={"X-Hackos-Token": "wrong"})[0], 403)
        self.assertEqual(self.request("/api/tasks", {"tasks": []}, headers={"Origin": "https://untrusted.invalid"})[0], 403)
        self.assertEqual(self.request("/api/state", headers={"Host": "untrusted.invalid"})[0], 403)
        self.assertEqual(self.request("/serve.py")[0], 404)
        self.assertEqual(self.request("/tasks.json")[0], 404)
        self.assertEqual(board.read_json(board.TASKS_PATH, {})["tasks"][0]["id"], "t-test")

    def test_stable_ids_promotion_and_supersession(self):
        with patch.object(board, "now_t_plus", return_value="T+00:01"):
            one = self.post("/api/ideas", {"idea": "First idea", "who": "Tester"})
            two = self.post("/api/ideas", {"idea": "Second idea", "who": "Tester"})
        self.assertNotEqual(one["id"], two["id"])
        self.assertEqual(self.request("/api/ideas/status", {"timestamp": "T+00:01", "status": "exploring"})[0], 400)
        decision = self.post("/api/decision", {"decision": "Adopt first", "who": "Tester", "promotes_idea": one["id"]})
        state = self.request("/api/state")[1]
        self.assertEqual([i["status"] for i in state["ideas"]], ["adopted", "raised"])
        self.assertEqual(state["decisions"][0]["promotes_idea"], one["id"])
        before = board.read_text(str(self.state / "decisions.md"))
        replacement = self.post("/api/decision", {"decision": "Change direction", "who": "Tester", "supersedes": decision["id"]})
        self.assertTrue(board.read_text(str(self.state / "decisions.md")).startswith(before))
        self.assertEqual(self.request("/api/state")[1]["decisions"][0]["superseded_by"], replacement["id"])
        self.assertEqual(self.request("/api/ideas/status", {"id": two["id"], "status": "adopted"})[0], 400)

    def test_legacy_records_keep_text_and_resolve_to_stable_ids(self):
        decisions = "# Decisions\n\n- [T+00:02] Original choice — Tester — original reason\n\n"
        ideas = "# Ideas\n\n- [T+00:01] Legacy idea — Tester — status: raised\n"
        board.write_text(str(self.state / "decisions.md"), decisions)
        board.write_text(str(self.state / "ideas.md"), ideas)
        state = self.request("/api/state")[1]
        legacy_id = state["ideas"][0]["id"]
        self.post("/api/ideas/status", {"id": legacy_id, "status": "exploring"})
        self.assertEqual(self.request("/api/state")[1]["ideas"][0]["id"], legacy_id)
        self.post("/api/decision", {"decision": "New choice", "who": "Tester", "supersedes": "T+00:02"})
        self.assertTrue((self.state / "decisions.md").read_text().startswith(decisions))
        self.assertEqual(self.request("/api/ideas/status", {"timestamp": "T+00:01", "status": "discarded"})[0], 200)

    def test_explicit_remote_check_preserves_last_success_on_failure(self):
        path = board.runtime_path("remote-check.json")
        original = board.git_output
        with patch.object(board, "git_output", side_effect=lambda *args: "origin" if args == ("remote",) else original(*args)):
            with patch.object(board.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)):
                with patch.object(board, "runtime_path", return_value=path):
                    self.assertTrue(board.check_remote("origin"))
            first = board.read_json(path, {})
            with patch.object(board.subprocess, "run", side_effect=subprocess.TimeoutExpired("git", 30)):
                with patch.object(board, "runtime_path", return_value=path):
                    self.assertFalse(board.check_remote("origin"))
            second = board.read_json(path, {})
        self.assertFalse(second["ok"])
        self.assertEqual(second["last_success_at"], first["last_success_at"])

    def test_transaction_recovers_after_partial_write(self):
        idea = self.post("/api/ideas", {"idea": "Recover me", "who": "Tester"})
        original = board.write_text
        def fail_decision(path, text):
            if path == str(self.state / "decisions.md"):
                raise OSError("simulated interrupted write")
            return original(path, text)
        with patch.object(board, "write_text", side_effect=fail_decision):
            self.assertEqual(self.request("/api/decision", {"decision": "Adopt", "who": "Tester", "promotes_idea": idea["id"]})[0], 503)
        state = self.request("/api/state")[1]
        self.assertEqual(state["ideas"][0]["status"], "adopted")
        self.assertEqual(state["decisions"][0]["promotes_idea"], idea["id"])
        self.assertFalse(os.path.exists(board.runtime_path("transaction.json")))

    def test_notes_offline_and_confirmed_preview_are_idempotent(self):
        raw = "  Meeting notes\nPreserve spacing.\n"
        result = self.post("/api/notes", {"text": raw, "structure": True})
        self.assertIn("warning", result)
        self.assertEqual((self.root / result["meeting_file"]).read_text(), raw)
        extraction = {"ok": True, "decisions": [{"text": "Choose demo", "who": "Tester"}],
                      "ideas": [{"text": "Possible follow-up", "who": "Tester"}],
                      "tasks": [{"title": "Wire demo", "owner": "Tester"}], "flagged": []}
        with patch.object(board.notes_intake, "structure_meeting_notes", return_value=extraction):
            preview = self.post("/api/notes", {"text": raw, "structure": True})
        self.assertEqual(self.request("/api/state")[1]["decisions"], [])
        result = self.post("/api/notes/confirm", {"preview_id": preview["preview_id"]})
        self.assertEqual(result["tasks_written"], 1)
        self.post("/api/notes/confirm", {"preview_id": preview["preview_id"]})
        self.assertEqual(len(self.request("/api/state")[1]["tasks"]), 1)
        self.assertEqual(self.request("/api/notes/confirm", {"decisions": extraction["decisions"]})[0], 400)
        replay = self.post("/api/notes", {"text": raw, "structure": True})
        self.assertIn("already confirmed", replay["warning"])
        self.assertEqual(len(self.request("/api/state")[1]["tasks"]), 1)

    def test_research_is_evidence_based_and_keeps_raw_summary(self):
        result = self.post("/api/research", {"summary": "  It is not implemented, but might work.\n"})
        self.assertEqual(result["entry"]["viability"], "untested")
        self.assertTrue(result["entry"]["summary"].startswith("  "))
        payload = {"id": result["entry"]["id"], "viability": "implemented", "confirmed_by": "Tester"}
        self.assertEqual(self.request("/api/research/override", payload)[0], 400)
        payload["evidence"] = "Measured demo smoke at commit abc"
        self.post("/api/research/override", payload)
        self.assertTrue(self.request("/api/state")[1]["research"][0]["override"])

    def test_git_activity_freeze_and_freshness_are_not_inferred(self):
        state = self.request("/api/state")[1]
        self.assertEqual(state["commits"][0]["source"], "git log")
        self.assertIn("team-setup/state/event.json", state["commits"][0]["files"])
        self.assertIsNone(state["freshness"]["last_fetch_at"])
        self.assertNotIn("latest_prompt", self.request("/api/focus")[1]["focus"][0])
        self.post("/api/stage", {})
        self.assertFalse(self.request("/api/state")[1]["contract_drift"])
        board.write_text(str(self.state / "03-contract-freeze/contract.md"), "Changed real contract\n")
        self.assertTrue(self.request("/api/state")[1]["contract_drift"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
