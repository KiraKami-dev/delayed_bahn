# 05 — Decision Log

## Reads

Read `AGENTS.md`, the active event, `team-setup/state/decisions.md`, and
`team-setup/state/ideas.md`. Examples are not accepted decisions.

## Writes

Append accepted decisions to `team-setup/state/decisions.md`. For promotion,
update the linked idea's status in the same recoverable operation. Use the
dashboard for multi-file promotion, or coordinate direct edits explicitly
while no dashboard writer is active.

## Instructions

1. Confirm this is a human-approved commitment, not a raised idea.
2. Generate a unique ID with `uuid.uuid4().hex`; write:
   `- [d-<uuid>] [T+HH:MM] <decision> — <who decided> — <reason>`.
3. To reverse an earlier decision, append ` — supersedes [d-<id>]` using its
   stable ID. Never edit the earlier line. Check whether it was already replaced.
4. To adopt an idea, append ` — promotes [i-<id>]` and change only that idea's
   status to adopted. Do not attribute the decision to the idea's author unless
   they actually decided it. Discarded ideas remain in the log.
5. Legacy timestamp-only lines remain readable; their IDs are exposed by the
   dashboard. Never guess a link if multiple records share a timestamp.
6. Sync accepted records through the coordination branch. Tell affected running
   agents to reread them; a local file update is not a team notification.

## Done when

The current decision, its provenance and any replacement/promotion links are
unambiguous, original records are preserved, and the sync handoff is explicit.
