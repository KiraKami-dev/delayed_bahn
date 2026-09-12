# AGENTS.md — hack-os shared agent instructions

Single source of truth for every coding harness. `CLAUDE.md` points here.
Read this whole file once per session. These rules govern product work;
explicitly requested maintenance of hack-os itself is not constrained by
an example product's demo script or contract.

## 1. Boot sequence and freshness

If `.hackos-user` is absent, run `./bootstrap.sh --auto` once. Bootstrap is
local-only: no downloads, product dependency installs, git config changes,
or credentials. Missing tools warn; markdown remains usable. Identity not
matched to the roster is unconfirmed: ask the human, never assume ownership.
MCP authentication and personal API keys are optional, per-person setup.

Read `team-setup/state/event.json` first. `mode: example`, or a legacy
`_comment` containing `WORKED EXAMPLE` without an explicit mode, means NO
active event. Say "No active event; fictional examples are inactive."
A blank `event_name` also means no active event, regardless of mode; report
"No event configured" and do not load placeholder state as requirements.
Do not load fictional challenges, contracts, owners, tasks, or decisions as
requirements. Never silently initialize or reset an event.
The distributed template keeps event records and shared session logs empty.
Keep the reusable roster in `team.json`; assign product roles fresh per event.

For an active event, read in order:
1. `team-setup/state/pipeline.json`
2. `team-setup/state/decisions.md` — identify current, non-superseded decisions.
3. `team-setup/state/owners.md`
4. `team-setup/board/tasks.json` — identify the relevant task and accountable owner.
5. `team-setup/state/01-challenge-pick/challenge.md`
6. `team-setup/state/02-demo-script/demo-script.md`
7. `team-setup/state/02-demo-script/not-building.md`
8. `team-setup/state/03-contract-freeze/contract.md`
Load `ideas.md`, `research.json`, and supporting notes when relevant.
Any document marked `WORKED EXAMPLE` is illustrative, never active scope.

State the active stage, your confirmed ownership, current task/decisions,
and whether the real contract is frozen. Missing information is unknown,
not permission to invent assignments or implement fictional requirements.

Before a new task or substantial edit, reread decisions, ownership, the
relevant task and contract. After a teammate reports a change, refresh even
in a running session. A dashboard refresh does not refresh an agent's mind.

Git is explicit synchronization, not live collaboration. `event.json`
names the coordination branch and maintainer. The maintainer integrates
accepted state changes there; teammates fetch and safely integrate before
new work and at checkpoints. Never auto-pull into a dirty worktree, discard
changes, auto-stash, or resolve another person's conflicts. Show local HEAD,
uncommitted coordination edits, and remote freshness as unknown until checked.
Offline work uses a local snapshot, never a claimed live team state.

## 2. Hackathon mode

- Write smoke tests for the demo happy path and coordination data safety.
- Do not add unit tests for unrelated product code or refactor working code.
- No speculative abstractions, new dashboards, providers, or services.
- Core storage/API stays Python 3 stdlib plus Git. The dashboard UI uses
  Vite, React, Tailwind and shadcn/ui in `team-setup/board/web/`; its Node
  dependencies are separate from whichever product stack the team chooses.
- Optional MCPs, plugins, prompt logging, and agent teams are not prerequisites.
- Vendored skills are optional; these repository rules override their workflow
  defaults. A skill does not authorize unrequested installs, data uploads,
  extra agents, destructive commands, or changes to system security controls.

## 3. Ownership rule

Before editing, check `team-setup/state/owners.md` and the owning task in
`team-setup/board/tasks.json`. Do not edit another person's assigned files.
A sub-owner helps within an explicitly delegated boundary; they do not
redirect scope. Name owners for shared wiring, manifests and lockfiles too.
Ownership is per event, not inferred from background. Use one branch/worktree
per independent writer; worktrees alone do not sync different machines.
Reassignments and delegation must be explicit and synced before work starts.
Avoid direct file editing while a dashboard write touches the same records.

## 4. Contract rule

The real `team-setup/state/03-contract-freeze/contract.md` freezes when that
gate completes. Code against it and mock missing dependencies. A required
contract change needs explicit human approval and a recorded decision.
`app/shared/` is generated from the agreed contract, never independently
patched. No sample schema, endpoint, or product stack is a requirement.

## 5. Scope rule

Product work must support the real demo script, including required setup,
seed data, deployment, accessibility and failure recovery. Ask before adding
features absent from it. Maintain `not-building.md`. Keep the deck current;
protect polish and submission time. Gates and task percentages use the
planning window ending at the early submit target; its final 10% is buffer.

## 6. Idea rule

A thought is not a decision. Record it in `team-setup/state/ideas.md` as
raised, then exploring, adopted or discarded. Only status changes in place;
original text and author remain. New lines use globally unique IDs:
`- [i-<uuid>] [T+HH:MM] <idea> — <raised by> — status: raised`
Use IDs for links; elapsed timestamps are display labels, not identifiers.
Legacy timestamp-only records remain readable. Ambiguous links need a human.

## 7. Decision rule

After an accepted direction change, append to `team-setup/state/decisions.md`:
`- [d-<uuid>] [T+HH:MM] <decision> — <who decided> — <reason>`
Never rewrite history. Append ` — supersedes [d-<uuid>]` to replace a decision.
Append ` — promotes [i-<uuid>]` when adopting an idea and update its status in
one recoverable operation. Check later supersessions before building.
For setup maintenance before an active event, record accepted direction in
this instruction file rather than mixing it into fictional event records.

## 8. Evidence and safety

AI assessments are advisory. Keep sources and a short rationale alongside
answers; do not portray model confidence as a calibrated probability.
Research is untested without evidence or human confirmation. Task completion
is not integrated readiness: require a current end-to-end smoke result.
Recent Git commits show recorded activity, not inferred current work.

Git hooks warn and exit zero. Explicit commands return truthful failures.
Reject malformed or stale writes, retain drafts, and never claim a failed
save succeeded. Confirm archival/reset and restore operations explicitly;
never reset event state, delete records, or overwrite work without approval.
No prompt capture by default. Keep secrets and runtime caches out of Git.

## 9. Commits and verification

Small present-tense commits identify the demo step or coordination outcome.
Never commit or push unless requested. Do not amend other people's work.
Run `python3 team-setup/board/test_board.py` for coordination smoke checks,
`for f in bootstrap.sh team-setup/hooks/* team-setup/scripts/*.sh; do bash -n "$f" || exit 1; done` for shell syntax, and `node --check team-setup/board/app.js` when Node is available.
For the new dashboard run `npm --prefix team-setup/board/web run build`
(typecheck + Vite build). `npm --prefix team-setup/board/web run dev` starts
both the local API and UI. Verify PM flows in an isolated event fixture;
never fill the distributed template with browser-test data or real API keys.
Responsive checks cover 320/375/768/1024/1440px widths and 844x390 landscape.
Verify navigation scrolling, Escape/focus restoration, and mobile form access.
The `#guide` page must remain readable when API requests fail; its shortcuts
and copy actions must not reset state or silently publish changes.
Product checks use `team-setup/scripts/smoke.sh`; unconfigured is not a pass.
A clean snapshot plus passing smoke is required before calling a demo ready.
