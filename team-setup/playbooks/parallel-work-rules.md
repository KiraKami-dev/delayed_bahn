# Parallel Work Rules

- Use one branch/worktree per independent writer. Across machines, Git
  commits must still be pushed, integrated and pulled; worktrees are not sync.
- `event.json` names the authoritative coordination branch and maintainer.
  Everyone proposes updates; the maintainer integrates accepted records.
- Before a new task or checkpoint, inspect dirty files, fetch the agreed
  remote, safely integrate the coordination branch, then tell the running
  agent to reread decisions, owners, task and contract. Do not auto-stash,
  discard changes or resolve another person's conflicts.
- Local dashboards show local snapshots. Cached upstream counts and last-fetch
  metadata do not establish current remote freshness, especially offline.
- Ownership covers feature folders AND shared wiring, manifests and lockfiles.
  Check directory and task owners. Helpers need an explicit delegated boundary;
  they do not redirect the owner's scope. Background is not an assignment.
- Mock missing dependencies against the agreed real contract. Sample contracts
  and sample ownership are inactive, never product requirements.
- Integrate at agreed checkpoints, not only at the final integration gate.
  A complete task board is not proof that the demo works end to end.
- Record approved contract changes and supersessions explicitly. Reread them
  before the next substantial edit, even within an existing agent session.
- Dashboard stale-write checks protect local edits; Git handles cross-machine
  conflicts. Do not directly edit a file while the dashboard is writing it.
- Agent teams are off by default and optional. If enabled deliberately, split
  only within your own ownership; one human remains accountable. Check usage
  in the provider's actual usage tools, not the smoke/snapshot panel.
- No shared prompt log is required. Recent committed activity is evidence of
  recorded changes, not a claim about what a teammate is currently doing.
