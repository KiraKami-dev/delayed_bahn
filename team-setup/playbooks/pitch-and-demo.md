# Pitch and Demo

Protect presentation time and prepare a reliable demo for each event.

## Who presents

Choose a presenter for the current event and record that assignment under
`polish-and-pitch` in `state/owners.md`. No presenter or product role is
preassigned by this template.

Keep the presenter informed throughout the event so they can explain what
was built and why. The rest of the team supports Q&A using
`08-pitch-sync.md`'s cheat sheet, built from current, non-superseded decisions.

## The deck is built in parallel from hour zero, never after

Six fixed slide slots exist from the start (`08-pitch-sync.md`), filled
continuously as the pipeline advances. There is no "build the deck at the
end" step in this system — if that's happening, something upstream didn't
run.

## Demo failure insurance list

Run through this before the `polish-and-pitch` gate ends, via
`07-demo-doctor.md`:

- **Seed script for deterministic data** — the demo never depends on live,
  unpredictable state.
- **Offline fallback path** — assume venue wifi will fail during the
  pitch. Have a path that works without it.
- **Backup video recorded** before the polish gate ends. Not "we'll record
  it if there's time" — this is a checked item, not a nice-to-have.
  Manual screen capture and voiceover are sufficient. For an optional
  automated video-production workflow, the team can evaluate
  [OpenMontage](https://github.com/calesthio/OpenMontage) separately.
  It is not vendored or installed by bootstrap; review its dependencies,
  generation-provider costs and data handling before use. It is never
  required by the demo-doctor checklist.
- **A `demo-ok-*` snapshot tag exists** after a clean-HEAD smoke pass
  (`scripts/snapshot.sh --confirm-demo`). Restore with
  `scripts/restore.sh <tag> --confirm-restore` into a separate detached
  worktree, leaving ongoing work untouched.

## Format adapts to `submission_format`

- `live_pitch` — speaker notes per slide, live demo runs from the actual
  deployed build.
- `video` — shot list and voiceover script instead of speaker notes; the
  demo shot is recorded, not live.
- `both` / `unknown` — prepare both; `08-pitch-sync.md` generates both by
  default when the format is unknown.
