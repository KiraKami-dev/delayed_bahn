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
root `.env.example` (`PORT`, `CORS_ORIGIN`, `STATIC_DIR`, `PREDICT_URL`, `CAUSES_URL`, ...).

## Real forecasts: the route model server

`/api/predict` and `/api/causes` answer from the fine-tuned db-route model when
`PREDICT_URL` and `CAUSES_URL` point at the Python route server
(`app/agents/src/features/db_route/serve_route.py`, needs only pandas/pyarrow/numpy).
Without them, or when that server is down, `/api/predict` serves the deterministic
mock prior (`modelId: mock-prior-v1`, `fallbackFrom` set) and `/api/causes` the
bundled fixture (`illustrative: true`), so the app never shows sample data unlabelled.

```bash
bash ../agents/src/features/db_route/fetch_serving_data.sh      # once: ~35 MB from the Nebius bucket (S3 key in the root .env)
../agents/src/features/db_route/serve_route.sh --port 8501       # model server: POST /predict, GET /causes?station=, GET /health
# root .env: PREDICT_URL=http://127.0.0.1:8501/predict  CAUSES_URL=http://127.0.0.1:8501/causes
npm --prefix ../frontend run build && npm run dev                 # then open http://localhost:8000
```

`GET /api/predict` replies carry `modelId: OpenTSLM db-route-quarter (route-2k)` and,
per leg, the recorded service and stop the forecast came from in the reasoning text.

## The fine-tuned trip model on a laptop

The db-train-model forecaster (v7 text, `app/agents/src/features/db_delay/trip/`) runs locally
in place of the route server: `trip/run_local.sh start <dir>` serves it on port 8502 and starts
this backend with `PREDICT_URL` pointing at it, with live DB data, offline estimates and
`POST /api/explain`. It needs model files that are not in Git; see "Model files (required)" in
`app/agents/src/features/db_delay/trip/README.md`.

Owner: see `../../team-setup/state/owners.md` (decided fresh per event,
not fixed here).

## Environment

- `DB_CLIENT_ID` / `DB_API_KEY` — DB API Marketplace "Timetables" credentials; power `GET /api/journeys/search` (direct trains for the PWA's Find my route) and the share-parser station lookup. Free plan: 60 requests/minute; plan files are cached 20 min.
