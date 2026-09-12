# 00 — Reveal Capture

Paste this whole file into any agent (Claude Code, Codex, or a plain chat
model) the moment a challenge track is revealed. The highest-value prompt in
this library — reveal briefings are the one window where information is
genuinely scarce and the team is usually split across rooms.

## Reads

- `team-setup/state/event.json` — for `tracks` (how many reveal files to expect) and `tracks_known_in_advance`.
- `team-setup/state/00-reveal-capture/reveals/_TEMPLATE.md` — the structure to fill.

## Writes

- One new file per track: `team-setup/state/00-reveal-capture/reveals/<track-name>.md`, copied from `_TEMPLATE.md`.
- `team-setup/state/00-reveal-capture/rubric.md`, if judging criteria was given as a separate document.

## Instructions for the agent

You are capturing a live challenge reveal, verbatim. I will paste or dictate
what was just said/shown. Do the following:

1. Copy `_TEMPLATE.md` in `team-setup/state/00-reveal-capture/reveals/` to
   `<track-name>.md`, using the exact track name from the reveal (or from
   `event.json`'s `tracks` list if it matches).
2. Fill every section of the template:
   - **Problem statement** — verbatim. Do not paraphrase or summarize.
   - **Judging criteria** — verbatim, or "see rubric.md" if given separately.
   - **What the partner engineer said is hard** — their actual words where possible.
   - **SDK / sandbox / dataset / credits handed to us** — exact names, URLs, keys, limits.
   - **Constraints on what we may use** — anything explicitly disallowed.
   - **What would impress this specific partner** — one line, your read of the room.
   - **Selection format** — is this a single pick or a ranked list; is submission live pitch, video, or both. Both are routinely unknown until the day — capture what was actually said, or mark `unknown` rather than guessing.
3. If judging criteria applies across all tracks, write it once to
   `team-setup/state/00-reveal-capture/rubric.md` instead of duplicating it
   per track file.
4. Do not editorialize, score, or recommend anything in this step — that is
   `01-challenge-triage.md`. This step only captures.

## Done when

Every track in `event.json`'s `tracks` list has a filled reveal file, and
`rubric.md` has the judging criteria captured verbatim (or a per-track note
that it lives inside that track's reveal file instead).
