# 03 — Contract Freeze

Paste this once the demo script and build list are settled, before anyone
starts parallel work.

## Reads

- `team-setup/state/02-demo-script/demo-script.md`.
- `team-setup/state/00-reveal-capture/reveals/*.md` — for partner SDK shapes that the contract needs to wrap.
- `team-setup/state/owners.md` — who owns which feature, so the contract is organized by feature the same way the codebase will be.

## Writes

- `team-setup/state/03-contract-freeze/contract.md` — FROZEN at this gate.
- `team-setup/state/03-contract-freeze/architecture.mmd` — a Mermaid diagram generated from the contract, renders natively on GitHub.
- Optionally scaffolds `app/shared/` from the contract (never hand-edited afterward — see `app/shared/README.md`).

## Instructions for the agent

1. From the demo script's build list, define the shared types and the full
   API surface every feature needs to cross a frontend/backend/agents
   boundary. Nothing more — do not model data that never appears in the demo.
2. Enforce the explainability default (AGENTS.md rule 8): any AI-produced
   answer or decision in the contract includes `reasoning`, `sources`, and
   `confidence` alongside the answer field, in the shared type itself.
3. For anything the contract depends on that does not exist yet (a
   partner's real API, a model not yet trained), generate a mock that
   matches the frozen shape exactly, so all teammates can build against
   it immediately without waiting on each other.
4. Generate `architecture.mmd` as a Mermaid `graph` showing each top-level
   `app/` folder and the data flow between them, derived directly from the
   contract's API surface — not hand-drawn.
5. State explicitly, in the output: "this contract is now frozen; changing
   it requires stopping the team and getting sign-off" (AGENTS.md rule 4).

## Done when

`contract.md` covers every type and endpoint the demo script's build list
needs, `architecture.mmd` renders and matches it, and mocks exist for
anything not yet real.
