# Owners

Who owns which directory, and which harness they run. Cross-cutting — spans
every pipeline stage. Reassignable anytime from the dashboard (POST
/api/owners) or by hand-editing this file; both are equally correct, this
is not an append-only log like decisions.md. Agents check this before
editing any file under app/ (AGENTS.md rule 3).

Also names who plays each per-event gate role referenced in pipeline.json
(facilitator, contract-freeze lead, integration coordinator, feature-freeze
caller, polish-and-pitch lead). These roles are decided fresh per event,
same as directory ownership — nothing here is fixed by background.

## Directory ownership

| Directory | Owner | Harness |
|---|---|---|
| app/frontend | | |
| app/backend | | |
| app/agents | | |
| app/shared | generated — no owner, see app/shared/README.md | - |

## Feature ownership (app/*/src/features/<name>)

| Feature | Owner | Sub-owners |
|---|---|---|

## Gate roles

| Role | Person |
|---|---|
| reveal-capture scouts | |
| challenge-pick facilitator | |
| contract-freeze lead | |
| integration coordinator | |
| feature-freeze caller | |
| polish-and-pitch lead | |

## Per-person background reference

Read the current roster, harnesses, and backgrounds from `team.json`.
Do not duplicate roster entries or infer event ownership from background.
