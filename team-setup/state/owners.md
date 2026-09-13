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
| app/frontend | Akshat | Codex |
| app/backend | | |
| app/agents | | |
| app/shared | generated — no owner, see app/shared/README.md | - |

## Feature ownership (app/*/src/features/<name>)

| Feature | Owner | Sub-owners |
|---|---|---|
| training-jobs (backend, Nebius GPU jobs) | | |
| delay-prediction (backend/agents: model, inference endpoint) | | |
| recommendation (backend/agents: algorithm on top of delays) | | |
| share-parser (frontend: DB share text → journey) | | |
| pwa-shell (frontend: installable app, share target, UI) | Akshat | |
| data-pipeline (agents: Oct→Aug data cut, agentic workflow) | | |
| evaluation (agents: baseline vs fine-tuned chart) | | |

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

Akshat owns homepage wiring, frontend assets, frontend manifest/lockfile and frontend smoke checks for this redesign. Backend and generated shared types remain outside this delegation.
