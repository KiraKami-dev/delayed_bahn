# 01 — Challenge Triage

Paste this after every track's reveal file is captured, before the team
votes on which challenge to build.

## Reads

- Every file in `team-setup/state/00-reveal-capture/reveals/` (except `_TEMPLATE.md`).
- `team-setup/state/00-reveal-capture/rubric.md`.
- `team-setup/state/team.json` — for background context on known team gaps, never as a hard rule.

## Writes

- Nothing directly. Produces a ranked recommendation for the team to discuss and vote on; the human decision gets written to `team-setup/state/01-challenge-pick/challenge.md` and `decisions.md` separately (that's the challenge-pick gate, not this prompt).

## Instructions for the agent

Score every captured track on exactly three axes, 1-5 each:

1. **Demoable in 90 seconds** — can a working, visually clear demo exist for this by the polish gate, given the team's background and the time budget in `event.json`.
2. **Shipped-before fit** — has this team (per `team.json` backgrounds) built something structurally similar before, at any hackathon or project.
3. **Rubric fit** — how directly does this track's problem map onto the captured rubric criteria.

For each track, output: the three scores, one sentence of reasoning per
score, a total, and any known team gap that would need active mitigation
(for example, no one has deep data-science background and this track is
analytics-heavy — say so plainly, do not paper over it).

Handle both selection formats found in the reveal files:
- **Single pick** — rank all tracks, recommend the top one, name the runner-up.
- **Ranked list submission** — produce the full ranked order the team should submit, not just a single winner.

If a reveal file marks selection format as `unknown`, produce both: a single
top recommendation and a full ranked order, so the team is ready either way.

## Done when

Every captured track has three scored axes with reasoning, a ranked
recommendation exists, and known team gaps are named explicitly rather than
implied.
