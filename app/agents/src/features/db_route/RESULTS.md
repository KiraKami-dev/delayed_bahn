# Results: the S/M/L/XM bake-off on all-Germany data

2,000 steps, batch 8, `plain_crps`, seed 0, one H100 per profile (`train_route.py`, jobs `route-2k-*-v3`, 13 Sep 2026 02:50–03:58 UTC).
Median error / CRPS in minutes on the departure-delay task, 600 scored rows per cell (all rows where a cell is smaller).
GBM = scikit-learn histogram gradient boosting on the same information (per-series mean/std/last/max + scalar annotations), quantile heads for CRPS.
Persistence = the context mean of the entity's own delay series (this service at this station where the profile carries it, else this service group), a point forecast. Route history = the empirical quantiles of that same series.
Blend = one weight on the TSLM quantiles fitted on `val` by CRPS. Classification = generated-answer accuracy on 64 rows (late/on-time and cause family together) vs the majority class.

| profile | cell | n | TSLM | GBM | persistence | route history | blend (w) | train-median | classif. / majority |
|---|---|---:|---|---|---:|---|---|---:|---|
| week | val | 470 | 2.24 / 1.76 | 2.09 / 1.62 | 2.38 | 2.78 / 2.06 | 2.06 / 1.62 (0.15) | 2.85 | 0.67 / 0.33 |
| week | test_seen_entity | 600 | 1.90 / 1.46 | 1.77 / 1.36 | 2.02 | 2.53 / 1.80 | 1.76 / 1.36 (0.15) | 2.64 | 0.66 / 0.38 |
| week | test | 501 | 2.51 / 1.91 | 2.36 / 1.87 | 2.52 | 3.07 / 2.22 | 2.37 / 1.86 (0.15) | 3.08 | 0.73 / 0.34 |
| week | test_seen_time | 600 | 2.02 / 1.56 | 1.94 / 1.49 | 2.15 | 2.74 / 1.97 | 1.93 / 1.48 (0.15) | 2.77 | 0.69 / 0.44 |
| quarter | val | 427 | 1.83 / 1.43 | 1.79 / 1.39 | 1.80 | 2.17 / 1.63 | 1.78 / 1.38 (0.30) | 2.69 | 0.75 / 0.39 |
| quarter | test_seen_entity | 600 | 1.69 / 1.32 | 1.61 / 1.25 | 1.71 | 2.02 / 1.53 | 1.61 / 1.25 (0.30) | 2.56 | 0.72 / 0.30 |
| quarter | test | 462 | 1.82 / 1.37 | 1.82 / 1.37 | 1.84 | 2.10 / 1.56 | 1.79 / 1.35 (0.30) | 2.60 | 0.73 / 0.38 |
| quarter | test_seen_time | 600 | 1.54 / 1.19 | 1.46 / 1.11 | 1.58 | 2.14 / 1.53 | 1.45 / 1.11 (0.30) | 2.59 | 0.73 / 0.28 |
| season | val | 469 | 1.91 / 1.49 | 1.84 / 1.42 | 1.90 | 2.12 / 1.58 | 1.83 / 1.41 (0.20) | 2.82 | 0.75 / 0.38 |
| season | test_seen_entity | 600 | 1.91 / 1.46 | 1.85 / 1.42 | 1.90 | 2.00 / 1.49 | 1.84 / 1.41 (0.20) | 3.00 | 0.78 / 0.38 |
| season | test | 501 | 1.98 / 1.50 | 1.90 / 1.48 | 2.02 | 2.05 / 1.55 | 1.89 / 1.46 (0.20) | 2.78 | 0.70 / 0.45 |
| season | test_seen_time | 600 | 1.72 / 1.30 | 1.61 / 1.23 | 1.73 | 1.90 / 1.43 | 1.62 / 1.22 (0.20) | 2.80 | 0.64 / 0.38 |
| multiscale | val | 471 | 2.27 / 1.74 | 2.02 / 1.57 | 2.37 | 2.79 / 2.06 | 2.03 / 1.57 (0.00) | 2.85 | 0.77 / 0.30 |
| multiscale | test_seen_entity | 600 | 2.19 / 1.64 | 2.00 / 1.55 | 2.22 | 2.81 / 1.98 | 2.00 / 1.55 (0.00) | 2.92 | 0.70 / 0.30 |
| multiscale | test | 506 | 2.43 / 1.87 | 2.36 / 1.83 | 2.51 | 3.06 / 2.21 | 2.33 / 1.83 (0.00) | 3.07 | 0.62 / 0.41 |
| multiscale | test_seen_time | 600 | 1.90 / 1.46 | 1.73 / 1.36 | 2.27 | 2.75 / 2.00 | 1.73 / 1.36 (0.00) | 2.70 | 0.64 / 0.38 |

## Reading

- **At 2k steps nobody is far from persistence.** On unseen trains the TSLM beats the entity's own context mean by 0.00–0.08 min and the GBM by 0.04–0.16; the distributional route-history baseline is clearly worse (its quantiles are too wide). The 12k grid is the test of whether training longer opens a real gap; the seed runs give its noise floor.

- **Quarter (6 h × 60 d) wins every cell.** Lowest error on both held-out cells and the smallest seen→unseen gap (0.13 min); week (7 d hourly) memorises — 0.6 min worse on unseen trains than on seen ones.
- **Multiscale does not add.** The plan's additivity question (does long history help *on top of* the week?) gets a no at this budget: second-worst on every cell. Caveat: it carries 2.8× the encoder tokens of the others and saw the identical 16k samples, so a fixed step budget under-trains the largest input.
- **The TSLM ties the tabular baseline on unseen trains** (quarter/test: 1.820 vs 1.816, CRPS 1.370 vs 1.374) and trails it by ~0.08 min on seen trains at 2k steps — the regime the literature predicts (RIDE: XGBoost within 4% of the best deep model) and what the trip-delay work found before its 12k-step runs.
- **The blend is the best forecast on every cell**, and the TSLM's fitted share rises with profile quality: 0.15 (week) → 0.20 (season) → 0.30 (quarter).
- **Publish `test` (unseen trains and weeks) as the headline and the gap to `test_seen_entity` as the memorisation estimate.** `test_seen_time` is optimistic by construction and is reported, not headlined.
- Everything is ~30% under the naive train-median baseline; 10–90% coverage sits at 0.70–0.80 against a 0.80 target, so the distributions are slightly narrow.

Artifacts: `s3://error404-db-route/runs/route-2k/<profile>/{metrics.json, checkpoint.pt, scalar_<cell>.npz}`; local baselines/blend in `baselines_local.json` beside them.

## Training budget: steps are passes over the data, and 12k is nineteen of them

Same registry (`/outputs/registry`, all Germany), same recipe (batch 8, lr 1e-4 / encoder 2e-4, `plain_crps`), seed 0 unless stated; one H100 per run, 13 Sep 2026 07:26–10:50 CEST. Quarter profile, unseen trains and weeks (`test`, 462 rows), median error / CRPS in minutes, coverage of the 10–90% range (target 0.80). GBM on the same rows: 1.82 / 1.37; persistence (entity's own context mean): 1.84.

| steps | passes over train | seed | TSLM | coverage | blend w/ GBM |
|---:|---:|---|---|---:|---|
| 2,000 | 3 | 0 | 1.82 / 1.37 | 0.75 | 1.79 / 1.35 |
| 2,000 | 3 | 1 | 1.83 / 1.38 | 0.74 | 1.79 / 1.36 |
| 2,000 | 3 | 2 | 1.81 / 1.36 | 0.76 | 1.79 / 1.35 |
| 3,000 | 5 | 0 | 1.81 / 1.37 | 0.74 | 1.79 / 1.35 |
| 4,000 | 6 | 0 | 1.85 / 1.42 | 0.69 | 1.80 / 1.37 |
| 6,000 | 9 | 0 | 1.83 / 1.46 | 0.58 | 1.77 / 1.36 |
| 12,000 | 19 | 0 | 2.10 / 1.90 | 0.26 | GBM alone |
| 12,000 | 19 | 1 | 2.07 / 1.86 | 0.25 | GBM alone |
| 12,000 | 19 | 2 | 2.13 / 1.89 | 0.26 | GBM alone |
| 12,000, `plain` loss | 19 | 0 | 2.17 / 1.90 | 0.23 | GBM alone |
| 12,000, caption-only (series zeroed) | 19 | 0 | 2.25 / 1.98 | 0.24 | GBM alone |
| 12,000, lr ×2 | 19 | 0 | 2.25 / 2.03 | 0.21 | GBM alone |
| 12,000, all rows scored | 19 | 0 | 2.19 / 1.87 | 0.30 | GBM alone |

Week and season at 12k collapse the same way: week 2.82 / 2.49 (2k: 2.51 / 1.91), season 2.12 / 1.94 (2k: 1.98 / 1.50), coverage 0.18–0.26. The six-region registry at 12k (different rows) scores 2.53 / 2.36.

### Reading

- **The knee is between three and six passes.** 2k and 3k steps are indistinguishable (seed spread 0.02 CRPS); 4k is slightly worse; 6k loses calibration; 12k loses everything: median error +0.3 min, CRPS +0.5, and the 80% range covers a quarter of outcomes. Training loss fell from 0.24 to 0.09 over the same range. That is memorisation of ~5,200 training records, not learning.
- **The step count was copied from a corpus sixty times larger.** Jonas's 12k steps on 300k examples is a third of one pass. The right budget is a function of the record count: two to four passes, or better, a checkpoint chosen by validation CRPS (v3 trainer, `--save-every 250 --val-rows 300`).
- **At the right budget the TSLM matches gradient boosting and persistence on unseen trains** (1.81–1.83 vs 1.82 vs 1.84) and the blend is the best forecast on every cell (1.79 / 1.35). The 12k ablations (plain loss, caption-only, lr ×2) are all measured in the overfit regime and rank only each other: series still carry ~0.1 CRPS over caption-only there, plain ≈ plain+CRPS, higher lr worse.
- **Serving:** the app runs on `r2k-q-s2-blend` (seed 2 at 2k, blended with GBM, weight 0.20), every held-out row scored.

Artifacts: `s3://error404-db-route/runs/<tag>/quarter/`, tags `r2k-q-s{1,2}`, `r3k-q`, `r4k-q`, `r6k-q`, `r6k-q-full`, `r12k-q-{s0,s1,s2,plain,caponly,six,lr2x,full}`, `r12k-w`, `r12k-l` and their `-full` twins; local baselines in `baselines_local.json` beside each.

### Validation-selected checkpoint (v3 trainer, run `v3-q-valsel`)

Quarter, 3,000 steps, a save every 250 steps scored on 300 validation rows, the best checkpoint by validation CRPS evaluated on every held-out row. Validation curve (CRPS): 1.52 · 1.42 · **1.37** (step 750) · 1.48 · 1.42 · 1.39 · 1.43 · 1.42 · 1.43 · 1.42 · 1.37 · 1.44 (step 3,000). Selected step 750.

| cell | n | TSLM | coverage |
|---|---:|---|---:|
| val | 427 | 1.85 / 1.42 | 0.75 |
| test_seen_entity | 1,134 | 1.74 / 1.33 | 0.75 |
| test | 462 | 1.85 / 1.38 | 0.73 |
| test_seen_time | 3,015 | 1.69 / 1.31 | 0.77 |

Level with the 2k seeds on every cell, reached at step 750 (about one pass over the data) with a quarter of their compute; not better. Selection by validation is the guard against the 12k collapse, not a source of accuracy on this corpus.
