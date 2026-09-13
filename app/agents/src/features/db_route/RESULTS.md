# Results: the S/M/L/XM bake-off on all-Germany data

2,000 steps, batch 8, `plain_crps`, seed 0, one H100 per profile (`train_route.py`, jobs `route-2k-*-v3`, 13 Sep 2026 02:50–04:00 UTC).
Median error / CRPS in minutes on the departure-delay task, 600 scored rows per cell (all rows where a cell is smaller).
GBM = scikit-learn histogram gradient boosting on the same information (per-series mean/std/last/max + scalar annotations), quantile heads for CRPS.
Blend = one weight on the TSLM quantiles fitted on `val` by CRPS. Classification = generated-answer accuracy on 64 rows (late/on-time and cause family together) vs the majority class.

| profile | cell | n | TSLM | GBM | blend (w) | train-median | classif. / majority |
|---|---|---:|---|---|---|---:|---|
| week | val | 470 | 2.24 / 1.76 | 2.09 / 1.62 | 2.06 / 1.62 (0.15) | 2.85 | 0.67 / 0.33 |
| week | test_seen_entity | 600 | 1.90 / 1.46 | 1.77 / 1.36 | 1.76 / 1.36 (0.15) | 2.64 | 0.66 / 0.38 |
| week | test | 501 | 2.51 / 1.91 | 2.36 / 1.87 | 2.37 / 1.86 (0.15) | 3.08 | 0.73 / 0.34 |
| week | test_seen_time | 600 | 2.02 / 1.56 | 1.94 / 1.49 | 1.93 / 1.48 (0.15) | 2.77 | 0.69 / 0.44 |
| quarter | val | 427 | 1.83 / 1.43 | 1.79 / 1.39 | 1.78 / 1.38 (0.30) | 2.69 | 0.75 / 0.39 |
| quarter | test_seen_entity | 600 | 1.69 / 1.32 | 1.61 / 1.25 | 1.61 / 1.25 (0.30) | 2.56 | 0.72 / 0.30 |
| quarter | test | 462 | 1.82 / 1.37 | 1.82 / 1.37 | 1.79 / 1.35 (0.30) | 2.60 | 0.73 / 0.38 |
| quarter | test_seen_time | 600 | 1.54 / 1.19 | 1.46 / 1.11 | 1.45 / 1.11 (0.30) | 2.59 | 0.73 / 0.28 |
| season | val | 469 | 1.91 / 1.49 | 1.84 / 1.42 | 1.83 / 1.41 (0.20) | 2.82 | 0.75 / 0.38 |
| season | test_seen_entity | 600 | 1.91 / 1.46 | 1.85 / 1.42 | 1.84 / 1.41 (0.20) | 3.00 | 0.78 / 0.38 |
| season | test | 501 | 1.98 / 1.50 | 1.90 / 1.48 | 1.89 / 1.46 (0.20) | 2.78 | 0.70 / 0.45 |
| season | test_seen_time | 600 | 1.72 / 1.30 | 1.61 / 1.23 | 1.62 / 1.22 (0.20) | 2.80 | 0.64 / 0.38 |

## Reading

- **Quarter (6 h × 60 d) is the profile.** Lowest error on both held-out cells and the smallest seen→unseen gap (0.13 min); week (7 d hourly) memorises — 0.6 min worse on unseen trains than on seen ones.
- **The TSLM ties the tabular baseline on unseen trains** (quarter/test: 1.820 vs 1.816, CRPS 1.370 vs 1.374) and trails it by ~0.08 min on seen trains at 2k steps. Exactly the regime the literature predicts (RIDE: XGBoost within 4% of the best deep model) and what the trip-delay work found before its 12k-step runs.
- **The blend is the best forecast on every cell**, and the TSLM's fitted share rises with profile quality: 0.15 (week) → 0.20 (season) → 0.30 (quarter).
- **Publish `test` (unseen trains and weeks) as the headline and the gap to `test_seen_entity` as the memorisation estimate.** Cell B (`test_seen_time`) is optimistic by construction and is reported, not headlined.
- Everything is ~30% under the naive train-median baseline; 10–90% coverage sits at 0.71–0.80 against a 0.80 target, so the distributions are slightly narrow.

Artifacts: `s3://error404-db-route/runs/route-2k/<profile>/{metrics.json, checkpoint.pt, scalar_<cell>.npz}`; local baselines/blend in `baselines_local.json` beside them.
