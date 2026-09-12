# Hour Zero Protocol

The timeboxed decision procedure for reveals and the pick. Hard stop: if
the team is still debating with 15 minutes left before build start, **take
the highest-scoring track and move.** A good decision made late is worse
than a good-enough decision made on time.

## If tracks are revealed on the day (`tracks_known_in_advance: false`)

1. **Scout split** — one person per track, per `state/owners.md`, pair up
   on the largest track. Each scout pastes
   `team-setup/prompts/00-reveal-capture.md` into their agent the moment
   their track's briefing starts.
2. **Regroup** — all scouts back in one room within the window set by
   `event.json`'s `reveal_window`. Each reads their captured reveal file
   aloud, verbatim sections only, no editorializing yet.
3. **Triage** — paste `01-challenge-triage.md` once every reveal file
   exists. Get the ranked recommendation on screen for everyone to see.
4. **Vote** — the facilitator named in `owners.md` runs a fast vote.
   15-minute hard stop before `event.json`'s `build_starts`. If still
   deadlocked at the stop, take the top-scored track.
5. **Lock it** — write `state/01-challenge-pick/challenge.md`, log the
   decision in `decisions.md`. No reopening (AGENTS.md rule 5's scope
   discipline starts here).

## If tracks are published in advance (`tracks_known_in_advance: true`)

Run this entire protocol **before the event**, on your own schedule —
`team_formation_deadline` in `event.json` is your effective hour zero for
this gate. The build window itself starts later, exactly as configured;
nothing else about the protocol changes, only when it runs.

## Both variants

- Verbatim matters (see `00-reveal-capture.md`) — partner engineers often
  sit on the judging panel, and their exact words are the strongest signal
  you have for what would impress them.
- Known team gaps get named out loud during triage, not discovered at
  hour 20.
