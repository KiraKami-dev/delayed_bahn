# 04 — Integration Check

Paste this at every gate, and any time two people's work is about to merge.
The difference between a fifteen-minute integration and a six-hour one.

## Reads

- `team-setup/state/03-contract-freeze/contract.md` — the frozen source of truth.
- The actual code in `app/frontend`, `app/backend`, `app/agents` on the branch(es) being checked.

## Writes

- A report to `team-setup/state/04-integration/` (create a dated file, e.g. `check-T+HH-MM.md`) listing every mismatch found.

## Instructions for the agent

1. Re-read `contract.md` in full.
2. For each branch or worktree under review, check every place the code
   implements a contract type or endpoint. Diff the actual shape against
   the frozen shape.
3. Report every mismatch, grouped by severity:
   - **Blocking** — a type/field mismatch that will break integration (wrong field name, wrong type, missing required field).
   - **Warning** — an extra field, a looser type than specified, something that works but drifted.
   - **Note** — contract-compliant but worth flagging (e.g. a mock still in use where real data should be wired in).
4. If a mismatch looks like it needs the contract itself to change, do not
   silently "fix" the contract — flag it per AGENTS.md rule 4 (contract
   change requires explicit stop + human sign-off) and stop there.
5. Write the report to `state/04-integration/check-<T+offset>.md`.

## Done when

Every branch under review has a report with zero unaddressed Blocking
items, or an explicit human decision to accept a Blocking item and move on.
