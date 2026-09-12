# app/

The actual product. Everything under `../team-setup/` is coordination, not
code — this is where the hackathon build lives.

- **`frontend/`** — whatever UI framework this event's stack picks.
- **`backend/`** — whatever backend language/framework this event's stack picks.
- **`agents/`** — the AI/agent pipeline layer (detection, RAG, whatever the
  challenge needs).
- **`shared/`** — generated from `../team-setup/state/03-contract-freeze/contract.md`.
  Never hand-edited — see `shared/README.md`.

Inside each of `frontend/`, `backend/`, `agents/`: one folder per feature
under `src/features/`, not a `components/`/`routes/`/`models/` split at the
top level. Copy `src/features/_TEMPLATE/` to start a new feature. Feature
names should match 1:1 across layers where a feature spans them (e.g.
`frontend/src/features/<feature-name>/` and `backend/src/features/<feature-name>/`
are the same feature, two halves).

Who owns which folder is decided fresh per event and lives only in
`../team-setup/state/owners.md` — not here, and not fixed by this template.

## Running everything together

Backend is Node ≥ 22 with zero dependencies; frontend and agents stacks are
still placeholders. Current run commands:

```bash
(cd app/backend && npm run dev) &        # http://localhost:8000/api/health
cd app/backend && npm run train -- doctor   # Nebius GPU training setup check
```

GPU training runs on Nebius Serverless AI jobs via
`backend/src/features/training-jobs/` (see its README). Once the other
folders have real dependencies filled in, extend this — e.g.:

```bash
# example once a Next.js + FastAPI + Python-agents stack is chosen:
(cd app/frontend && npm run dev) &
(cd app/backend && npm run dev) &
(cd app/agents && python -m agents.main) &
```

`bootstrap.sh` detects whatever is actually in these three folders and
installs dependencies accordingly — it never assumes a stack.
