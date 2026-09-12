# app/agents

The AI/agent pipeline layer — detection, RAG, whatever the challenge needs.

How to run just this folder standalone, once dependencies are chosen:

```bash
cd app/agents
pip install -e .
python -m agents.main   # or whatever entrypoint the team sets up
```

Feature folders live in `src/features/`, one per agent/pipeline
capability, same naming pattern as `frontend`/`backend`. Copy
`src/features/_TEMPLATE/` to start a new one.

Owner: see `../../team-setup/state/owners.md` (decided fresh per event,
not fixed here).
