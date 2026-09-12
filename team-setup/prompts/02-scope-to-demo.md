# 02 — Scope to Demo

Paste this right after `challenge.md` is written and locked. Writes the
90-second demo script BEFORE any feature list — the script IS the spec.

## Reads

- `team-setup/state/01-challenge-pick/challenge.md`.
- `team-setup/state/00-reveal-capture/rubric.md` and the relevant reveal file.
- `team-setup/state/event.json` — for `submission_format` (a video submission needs shots that read well on video, not just live).

## Writes

- `team-setup/state/02-demo-script/demo-script.md` — FROZEN once written.
- `team-setup/state/02-demo-script/not-building.md`.

## Instructions for the agent

1. Write the demo script FIRST, shot by shot, exactly 90 seconds, as a
   table: time range, shot name, what's on screen. Nothing goes in this
   script that the team cannot realistically build and demo live (or
   record, if `submission_format` is `video`) by the polish gate.
2. Only after the script is written, derive the minimum build list: every
   piece of UI, data, or logic that must exist for something to appear on
   screen at each shot. This becomes the seed for task cards in
   `board/tasks.json` (done separately, on the dashboard or by hand).
3. Everything else the team discussed or was tempted to build — write
   explicitly to `not-building.md`, one line each, so scope creep has a
   named place to be rejected against instead of silently creeping back in.
4. Once `demo-script.md` is written, it is frozen (AGENTS.md rule 5). Any
   later change to it needs the same explicit-stop-and-confirm treatment as
   a contract change.

## Done when

`demo-script.md` has a complete shot-by-shot table covering exactly 90
seconds, and every feature discussed but excluded appears by name in
`not-building.md`.
