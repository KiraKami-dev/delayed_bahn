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

Stack isn't chosen yet in this template, so there's no single command
until the team picks one. Once `frontend/package.json`,
`backend/package.json` (or `pyproject.toml`/`pom.xml`), and
`agents/pyproject.toml` have real dependencies filled in, add the actual
run command here — e.g.:

```bash
# example once a Next.js + FastAPI + Python-agents stack is chosen:
(cd app/frontend && npm run dev) &
(cd app/backend && npm run dev) &
(cd app/agents && python -m agents.main) &
```

`bootstrap.sh` detects whatever is actually in these three folders and
installs dependencies accordingly — it never assumes a stack.
