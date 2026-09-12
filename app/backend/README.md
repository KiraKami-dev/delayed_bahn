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
- `src/features/pwa-shell/` — serves the built PWA from `app/frontend/dist` and the seed journey.
- `src/features/share-parser/` — DB Navigator share text → `Journey`.
- `src/features/delay-prediction/` — per-leg delay forecasts chained into a plan-fail probability.
- `src/features/recommendation/` — advice, leave-home-by time, re-routes after a missed change.
- `src/features/causes/` — delay-cause families per station.

## Product endpoints

| Method | Path | Body → Response |
|---|---|---|
| GET | `/api/health` | → `{ ok: true, ... }` |
| GET | `/api/seed/demo` | → seed `Journey` (RB 16 Nürnberg → München, S 8 → Flughafen) |
| POST | `/api/journeys/parse` | `{ text }` → `Journey`; 400 no connection, 422 link-only |
| POST | `/api/predict` | `Journey` → `Prediction` (+ `distribution`, `quantiles`, `pCancel` per leg) |
| POST | `/api/recommend` | `{ journey, prediction, doorToStationMin?, acceptableRisk? }` → `Recommendation` (+ `leaveHomeBy`) |
| POST | `/api/reroute` | `{ journey, missedLegIndex }` → `{ station, options[], best, advice }` |
| GET | `/api/causes?eva=` | → cause families, top causes, 7-day sparkline |

Any other path serves the PWA (`STATIC_DIR`, default `app/frontend/dist`) with an
SPA fallback, so `/share?text=...` loads the app. Env knobs are listed in the
root `.env.example` (`PORT`, `CORS_ORIGIN`, `STATIC_DIR`, `PREDICT_URL`, ...).

```bash
npm --prefix ../frontend run build && npm run dev   # then open http://localhost:8000
```

Owner: see `../../team-setup/state/owners.md` (decided fresh per event,
not fixed here).
