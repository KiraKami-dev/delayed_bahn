# 08 — Pitch Sync

Paste this at hour zero to create the six slide slots, and again any time
the pipeline advances to refresh them. The reason the presentation stops
being an afterthought.

## Reads

- `team-setup/state/00-reveal-capture/reveals/*.md` — problem, in the partner's own words.
- `team-setup/state/02-demo-script/demo-script.md` — this IS slide 3.
- `team-setup/state/03-contract-freeze/architecture.mmd` — this IS slide 4.
- `team-setup/state/decisions.md` — current (non-superseded) decisions, for the Q&A cheat sheet.
- `team-setup/state/event.json` — `submission_format`, `pitch_length_minutes`.

## Writes

- A deck outline (six slides) — write to wherever the team keeps the deck; if nowhere yet, write to `team-setup/state/06-polish-and-pitch/deck-outline.md`.
- A Q&A cheat sheet in the same location.

## Instructions for the agent

Maintain exactly six fixed slide slots, filled continuously as the pipeline
advances — never written once at the end:

1. **Problem** — from the reveal notes, in the partner's own words.
2. **Insight** — the team's angle on the problem, one line.
3. **Live demo** — is `demo-script.md`, verbatim, shot by shot. Do not write a separate demo description.
4. **How it works** — derived from `architecture.mmd`, plain language over the diagram.
5. **Why this team** — pull from `team.json` backgrounds, framed for this specific challenge.
6. **What's next** — one or two lines, forward-looking, not a feature backlog dump.

Adapt to `submission_format`:
- `live_pitch` — add speaker notes per slide.
- `video` — add a shot list and a voiceover script instead of speaker notes.
- `both` — produce both.
- `unknown` — produce speaker notes AND a shot list, so either format is ready.

Generate the **Q&A cheat sheet** from `decisions.md`'s current (non-superseded)
decisions only — check every decision for a later `supersedes` line before
including it. One line per decision area, so whoever is not presenting can
answer for their own area without accidentally defending a reversed call.

## Done when

All six slots are filled with content traceable to a source file (not
invented), the format-appropriate notes/shot-list exist, and the Q&A sheet
reflects only currently-live decisions.
