# app/backend

Node ≥ 22, **no npm dependencies** (built-in `http`, `fetch`, `crypto`).

```bash
cd app/backend
cp ../../.env.example ../../.env && ln -s ../../.env .env   # single team env at the repo root; already carries the eu-north1 4x L40S default
npm run dev                     # API on http://localhost:8000  (GET /api/health)
npm test                        # offline smoke tests
npm run train -- doctor         # check Nebius auth/project/subnet
npm run train -- smoke          # real nvidia-smi job on one L40S (~$0.10, ~5 min)
```

Feature folders live in `src/features/`, one per feature, matching
`app/frontend/src/features/` names 1:1 where a feature spans both. Copy
`src/features/_TEMPLATE/` to start a new one.

- `src/features/training-jobs/` — submit/track GPU training runs on Nebius
  Serverless AI jobs. Full usage guide in its README.

Owner: see `../../team-setup/state/owners.md` (decided fresh per event,
not fixed here).
