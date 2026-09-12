# New Event Setup

1. Update the roster in `team-setup/state/team.json`. Product roles are not
   inherited from background or fictional examples.
2. Name a coordination maintainer and authoritative branch. Stop other state
   writers, then run `team-setup/scripts/new-event.sh`. Confirm RESET only
   after reading its archive/reset description. It preserves previous state
   and tasks, initializes blank records, and leaves ownership unassigned.
3. Assign real owners for features, shared wiring, manifests and gate roles.
   Set event timestamps with timezone offsets. Unknown fields may stay blank.
4. Each person runs `./bootstrap.sh` on their actual machine. Check roster
   identity and hook warnings. Existing third-party hooks are never replaced.
5. Start `python3 team-setup/board/serve.py`. Confirm examples are inactive
   before initialization and the newly initialized event is blank and coherent.
6. Optional MCPs, plugins and agent teams are not prerequisites. Authenticate
   only tools you actually need, per person, before the event.
7. Run `python3 team-setup/board/test_board.py`, then the rehearsal below.

## Mandatory team rehearsal

Use a separate disposable repository, not an ongoing event's state.

1. Create the repo from the template and bootstrap every actual machine.
2. Invent a challenge; run reveal capture, selection and demo scoping.
3. Freeze a real contract; assign independent worktrees and ownership.
4. Build one end-to-end happy path, using mocks at ownership boundaries.
5. Record and sync an accepted decision. Verify fresh Claude Code and Codex
   sessions agree on current decision, owner and task. Explicitly refresh an
   already-running session too; a new Git commit alone does not refresh it.
6. Exercise two stale dashboard tabs: the second save must retain its draft,
   not overwrite the first. Save notes with AI unavailable; raw text survives.
7. Integrate, run the configured product smoke, commit intended work, rerun
   smoke on clean HEAD, then snapshot with `--confirm-demo`.
8. Restore the snapshot with `--confirm-restore`: it must create a separate
   worktree, leaving ongoing work unchanged. Deploy and perform the demo.
9. Check seed data, offline fallback, six slide slots and backup recording.
10. Fix the failures. The rehearsal, not bootstrap's summary, proves parity.
