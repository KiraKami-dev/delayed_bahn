# Feature: delay-prediction

`POST /api/predict` `Journey` -> `Prediction` (contract) plus additive per-leg
`distribution` (5 bins incl. cancelled), `quantiles` (p10/p50/p90) and `pCancel`.
Serves demo shot 0:30 "per-train delay, chained".

- `connection.js` -- JS port of `app/agents/src/features/db_delay/trip/connection.py` (change and journey probabilities).
- `backends/mock.js` -- deterministic fat-tailed prior by train class x hour x duration (`modelId: mock-prior-v1`, confidence low).
- `backends/http.js` -- forwards to `PREDICT_URL` (the Python model server); falls back to the mock and records `fallbackFrom`.
- Model server contract: `POST {legs:[{trainId, arrival:{probs[], pCancel}, departure?, reasoning?, sources?}], modelId?, confidence?}`.
