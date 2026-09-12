# 07 — Demo Doctor

Paste this at the start of the polish-and-pitch gate to verify the current
event's demo and identify failures before presentation time.

## Reads

- `team-setup/state/02-demo-script/demo-script.md`.
- The running product (frontend/backend/agents), as it actually exists right now.
- `team-setup/scripts/snapshot.sh` tags, via `git tag -l 'demo-ok-*'`.

## Writes

- A pass/fail report, appended to `team-setup/state/06-polish-and-pitch/` as a dated file (e.g. `demo-doctor-T+HH-MM.md`).

## Instructions for the agent

Walk `demo-script.md` shot by shot, step by step, and verify, for each:

1. **Seed data exists** — the exact data the shot depends on is present and deterministic (not "usually works," actually present right now).
2. **The deploy is live** — whatever URL/build the demo will run from is reachable and current.
3. **A backup video has been recorded** — check for a recorded artifact; if none exists, flag this as the single highest-priority item, since venue wifi failing during the pitch is the assumed default (see `playbooks/pitch-and-demo.md`).
4. **A snapshot tag exists** — a `demo-ok-*` git tag exists at or after the point the current demo path was last verified working.

Report pass/fail per item, per shot, plainly. Do not soften a fail into a
"minor issue" — this report exists specifically to surface what the team
would otherwise discover live, on stage.

## Done when

Every shot in the demo script has a pass/fail verdict on all four checks,
and every fail has a named owner and a target time to fix it before the
submit target (not the real deadline — see `event.json`'s
`submit_target_offset_hours`).
