# Evaluation: trip-delay forecasts against the baselines

How the fine-tuned time-series language model (TSLM) was scored, what it was scored against, and
what the numbers say. Every number below is produced by the scripts named in the last section; the
run-by-run detail is in `DESIGN.md` section 16 and the command of every job in `trip/RUNS.md`.
Times are Zurich. Rows marked *pending* are filled in as the last jobs finish.

## 1. The task being scored

One example is one train at one prediction moment with one target stop: given everything known at
that moment, forecast the arrival delay at the target stop in whole minutes, and the chance that
the train is cancelled. The forecast is a full distribution over minutes (read off the model's
next-token probabilities, one token per minute), from which the median, a 10 to 90% range and
P(late by 6 minutes or more) follow. A connection's chance of being made is derived from two such
distributions (`trip/connection.py`).

## 2. Data and splits

- **Source:** public DB timetable and change feeds, November 2025 to August 2026, processed into
  298,430 examples (`trip/build.py`). Every input is computed from records timestamped before the
  prediction moment; the target comes from the final arrival record. `test_build.py` checks the
  cutoffs.
- **Time split, no shuffling:** train before 1 May 2026 (174,070), validation May (30,622), test
  June to August (93,738). Hyper-parameters, blend weights and calibration were chosen on
  validation only.
- **Shared 5,000-example test subset:** every 2,000- and 5,000-step run is scored on the same
  5,000 test examples (`--test-limit 5000`, fixed seed), so runs compare like for like. Long runs
  are scored on all 93,738.
- **September forward set:** after the training data was frozen, the September 2026 feeds were
  scraped (last change feed 12 September, 19:50 local) and built with the same code
  (`forward.parquet`, 21,982 test examples from 1 September on; 10,000 scored). No model or blend
  weight was fitted on it. It is the honest "future" test.
- **Dataset variants:** `examples_v2`/`v3` add the arrival delays of the previous trains of the
  same type towards the same destination at the stop (up to five, within six hours, arrived before
  the prediction moment). Baselines are retrained on the same columns whenever a model uses them,
  so the comparison never rests on the TSLM seeing more data.

## 3. Metrics

All in minutes, lower is better, computed by `trip/metrics.py` on trips that ran (cancelled trips
count only in the cancellation metrics).

| Metric | What it measures |
|---|---|
| Median error (MAE of the median) | Distance between the distribution's median and the true delay |
| CRPS | Quality of the whole distribution: 19 quantiles (5% to 95%), pinball loss averaged; the standard proper score for probabilistic forecasts (Gneiting and Raftery 2007) |
| Coverage and width of the 10 to 90% range | Whether the range contains the truth about 80% of the time, and how wide it is |
| Brier score, late | Calibration of P(delay ≥ 6 min) |
| Log loss, cancelled | Calibration of P(cancelled) |

Every score is also broken down by train class (S-Bahn, regional, long-distance) and by lead time
(up to 15, 15 to 30, 30 to 60, 60 to 120, more than 120 minutes before the planned arrival).

**Significance.** Two models are compared with a paired bootstrap (`trip/bootstrap.py`): the
shared examples are resampled 2,000 times, both models are scored on each resample, and the 95%
interval of the difference is reported. A difference whose interval excludes zero is called real;
one that straddles zero is reported as "no clear difference". Two identical trainings of the same
recipe differ by 0.006 CRPS on the 5,000 examples, which is the noise floor for single runs.

## 4. Baselines

| Baseline | Inputs |
|---|---|
| Persistence | The current delay carries to the target stop; cancellation from the route's history |
| Route history | The route's 30-day delay distribution at the stop |
| XGBoost | Gradient-boosted trees (quantile, late and cancellation models) on the same engineered features the TSLM reads: current delay and trend, route history at three scales, station and network lateness over 3, 24 and 72 hours, lead time, stops ahead, train class and type, hour and weekday, and where present the previous trains on the route |

XGBoost is the one to beat: same information, a strong tabular learner, no language model.

## 5. Results

### 5.1 Shared 5,000 test examples (June to August)

Median error / CRPS. "Partner" names the run each experiment is compared with.

| Model | Median error | CRPS | vs XGBoost (CRPS, 95% interval) |
|---|---|---|---|
| Persistence | 3.990 | 3.316 | +0.345 |
| Route history | 5.873 | 4.999 | |
| XGBoost | 3.698 | 2.971 | |
| TSLM, original recipe (soft targets, encoder), 2k steps | 3.711 | 2.994 | +0.023 |
| TSLM, plain loss, encoder, 2k | 3.702 | 2.954 | -0.018 (-0.073 to +0.030) |
| TSLM, plain loss, encoder, 5k | 3.678 | 2.923 | -0.048 |
| TSLM, text input, plain loss, 2k | 3.635 | 2.907 | -0.064 (-0.137 to -0.005) real |
| TSLM, text input, plain + CRPS loss, 2k | 3.621 | 2.903 | |
| TSLM, text input, plain loss, 5k | 3.614 | 2.883 | |
| TSLM, encoder only, plain + CRPS loss, 12k | 3.602 | 2.889 | -0.082 (-0.137 to -0.041) real; within 15 min -0.112, beyond 30 min -0.072, both real |
| XGBoost retrained with previous trains (v2 data) | 3.654 | 2.937 | |
| TSLM, text, v2 data, 2k | 3.616 | 2.889 | -0.048 vs XGBoost-v2 (-0.121 to +0.010) |
| TSLM, text + encoder, v2 data, 2k | 3.603 | 2.877 | -0.060 vs XGBoost-v2 (-0.130 to -0.005) real |
| Lead-time blend, text + plain, 2k | 3.618 | 2.901 | -0.070 (-0.127 to -0.030) real |
| Lead-time blend, text + encoder, v2 data | | | -0.049 vs XGBoost-v2 (-0.100 to -0.015) real |
| TSLM, text with XGBoost's forecast in the prompt (stacked, v4 data), 2k | 3.573 | 2.860 | -0.075 vs XGBoost-v3 (-0.116 to -0.044) real; within 15 min -0.086, beyond 30 min -0.085, both real |

### 5.2 All 93,738 test examples

| Model | Median error | CRPS | vs XGBoost (CRPS) |
|---|---|---|---|
| XGBoost | 3.462 | 2.759 | |
| XGBoost, v2 data | 3.413 | 2.723 | |
| TSLM, plain loss, encoder, 2k | 3.477 | 2.774 | +0.015 |
| Lead-time blend of that with XGBoost | 3.427 | 2.731 | -0.028 (-0.039 to -0.019) real; median error -0.035 |
| TSLM, original recipe, 12k (30,000 of the test) | 3.434 | 2.754 | XGBoost on the same 30,000: 3.469 / 2.765; median error real |
| Final: text + encoder, plain loss, 12k | 3.397 | 2.699 | -0.060 (-0.073 to -0.048) real; median error -0.066 real; within 15 min -0.091 real; beyond 30 min -0.046 real; lead-time blend -0.067 |
| Final: text, plain loss, 24k | 3.374 | 2.680 | -0.079 (-0.091 to -0.067) real; median error -0.088 real; within 15 min -0.100 real; beyond 30 min -0.073 real; vs text + encoder 12k -0.019 real |
| Final A: text, v2 data, plain + CRPS, 12k | 3.322 | 2.644 | against XGBoost on the combined features (3.414 / 2.720): -0.076 (-0.088 to -0.065) real; median error -0.093 real; within 15 min -0.092 real; beyond 30 min -0.073 real; lead-time blend weight 1.0 |
| Final: stacked text, v4 data, plain + CRPS, 12k | 3.331 | 2.647 | against XGBoost on the combined features (3.414 / 2.720): -0.073 (-0.084 to -0.063) real; within 15 min -0.091 real; beyond 30 min -0.066 real; vs the unstacked text final +0.003, no difference |
| Candidate: stacked text, v7 data, plain + CRPS, 6k (30,000 of the test) | 3.224 | 2.560 | against XGBoost-v7 on the same examples: -0.074 (-0.097 to -0.055) real; median error -0.072 real; within 15 min -0.104 real; beyond 30 min -0.060 real |
| Split, v7 data, plain + CRPS, 6k (30,000 of the test) | 3.234 | 2.570 | against XGBoost-v7: -0.063 (-0.086 to -0.045) real; against the text candidate +0.010, real |
| Final: stacked text + encoder, v4 data, plain + CRPS, 12k | 3.327 | 2.646 | level with the stacked text final (2.647); XGBoost on the combined features 2.720 |
| XGBoost with the same-train and corridor series (v7) | 3.278 | 2.616 | the stronger baseline: both text finals trail it (+0.031 and +0.028, real) |
| Final B: text + encoder, v3 data, plain + CRPS, 12k | 3.319 | 2.643 | against XGBoost on the combined features: -0.077 (-0.089 to -0.066) real; within 15 min -0.093 real; beyond 30 min -0.073 real; vs the text final -0.001, no difference; vs XGBoost-v7 +0.027 |

### 5.3 By lead time

CRPS difference against the matching XGBoost (negative: the TSLM is better), full test unless
stated; every difference marked real has a 95% bootstrap interval that excludes zero.

| Model | Within 15 min | Beyond 30 min |
|---|---|---|
| First wave: plain loss, encoder, 2k (vs XGBoost) | -0.055, real | +0.076, XGBoost better |
| Text + encoder, plain loss, 12k (vs XGBoost) | -0.091, real | -0.046, real |
| Text, plain loss, 24k (vs XGBoost) | -0.100, real | -0.073, real |
| Text, combined data, 12k (vs XGBoost, combined features) | -0.092, real | -0.073, real |
| Text + encoder, combined data, 12k (vs XGBoost, combined features) | -0.093, real | -0.073, real |
| Stacked text, 12k (vs XGBoost, combined features) | -0.091, real | -0.066, real |
| Stacked text on the new series, 6k, 30,000 of the test (vs XGBoost-v7) | -0.104, real | -0.060, real |

The first 2,000-step model won only close to arrival, where the live delays at the last stops
dominate, and lost far out, where the forecast rests on base rates; blending by lead time
(`trip/combine.py`, weights fitted on validation) covered that. Longer training closed the gap:
every final wins at every lead time on its own, and the blend weights fitted on validation are
0.95 to 1.0 for the TSLM, so the blend no longer adds anything.

### 5.4 September forward test (10,000 examples, nothing fitted on them)

XGBoost here is the same model as above, trained on the May training split; only the examples
are new.

| Model | Median error | CRPS | vs XGBoost (CRPS) |
|---|---|---|---|
| Persistence | 3.640 | 2.986 | |
| XGBoost | 3.244 | 2.586 | |
| TSLM, original recipe, 12k | 3.257 | 2.611 | |
| TSLM, text, plain loss, 2k | 3.281 | 2.626 | +0.040 (+0.013 to +0.068); within 15 min -0.011 (-0.021 to -0.002) real; beyond 30 min +0.089 |
| Lead-time blend of that (weights from May) | 3.225 | 2.570 | -0.016 (-0.027 to -0.006) real |
| TSLM, text, plain + CRPS loss, 2k | 3.266 | 2.610 | +0.024; within 15 min -0.016 (-0.026 to -0.006) real |
| Lead-time blend of that | 3.230 | 2.573 | -0.013 (-0.022 to -0.005) real |
| TSLM, encoder only, plain + CRPS loss, 12k | 3.199 | 2.553 | -0.033 (-0.050 to -0.017) real; median error -0.045 real; within 15 min -0.038 real; May blend weights 1.0, nothing to add |
| TSLM, no series at all, plain + CRPS loss, 12k | 3.190 | 2.549 | -0.037 (-0.060 to -0.016) real; median error -0.054 real; within 15 min -0.036 real |
| Final: text + encoder, plain loss, 12k | 3.214 | 2.566 | -0.020 (-0.042 to +0.003); within 15 min -0.040 real; lead-time blend -0.031 (-0.048 to -0.015) real |

Second September set, built with the combined features (previous trains on the route) and the
statistical forecast: 10,000 of its 32,553 September examples; XGBoost retrained on those
features on May and scored on September. Not comparable with the table above (different
examples).

| Model | Median error | CRPS | vs XGBoost (CRPS) |
|---|---|---|---|
| Persistence | 3.057 | 2.493 | |
| XGBoost (combined features) | 2.745 | 2.175 | |
| TSLM, stacked, 2k | 2.689 | 2.136 | -0.039 (-0.076 to -0.015) real; median error -0.056 (-0.107 to -0.023) real; within 15 min -0.068 (-0.148 to -0.025) real |
| Lead-time blend of that (weights from May) | | | -0.040 (-0.075 to -0.019) real |
| TSLM, stacked, encoder only (no numbers in the text), 2k | 2.715 | 2.150 | -0.025 (-0.051 to -0.006) real; median error -0.030 real; within 15 min -0.055 real |
| TSLM, stacked, 5k | 2.741 | 2.161 | -0.014 (-0.058 to +0.019); within 15 min -0.086 real |
| Lead-time blend of that (weights from May) | | | -0.040 (-0.082 to -0.011) real |
| TSLM, text + encoder, combined data without the forecast, 2k | 2.711 | 2.148 | -0.028 (-0.072 to +0.005); within 15 min -0.071 (-0.160 to -0.023) real |
| Lead-time blend of that (weights from May) | | | -0.044 (-0.086 to -0.018) real |
| Final A: text, combined data, plain + CRPS, 12k (not stacked) | 2.669 | 2.106 | -0.070 (-0.111 to -0.041) real; median error -0.076 real; within 15 min -0.096 real |
| Stacked finals (12k) | *pending* | | |

Third September set, with the same-train and corridor series (`forward_v7`, same 10,000 examples);
XGBoost retrained on those features on May:

| Model | Median error | CRPS | vs XGBoost with the new series (CRPS) |
|---|---|---|---|
| TSLM, split (new series as series through the encoder; their summaries in the rationale), 2k | 2.543 | 2.023 | -0.040 (-0.080 to -0.015) real; median error -0.056 real; within 15 min -0.074 real |
| TSLM, no series (summaries in the rationale only), v7, 2k | 2.540 | 2.022 | -0.041 (-0.080 to -0.016) real; within 15 min -0.070 real: the same as split and text, so out of time too the gain is the rationale |
| TSLM, stacked text, v7, 2k | 2.542 | 2.019 | -0.044 (-0.085 to -0.019) real; median error -0.057 real; within 15 min -0.075 real |

The shape found on June to August holds out of time: alone, a 2,000-step TSLM is behind the
tabular model overall and ahead in the last quarter hour; blended by lead time with weights that
never saw September, it beats XGBoost.
On the combined-feature set the same holds for the model without the statistical forecast;
only the stacked model beats XGBoost alone out of time, so stacking is what carries it.

### 5.5 The same results in minutes

CRPS scores the whole distribution; these figures read the predicted median only
(`trip/plain_metrics.py`, cancelled trains left out). "Within 1 minute" means the forecast was
off by at most one minute. The range column should be near 80%.

Full test, 88,479 trains:

| Model | Average miss | Within 1 min | Within 2 min | Within 5 min | Bias | Truth inside 10 to 90% range |
|---|---|---|---|---|---|---|
| Persistence (delay carried forward) | 3.75 min | 62% | 72% | 86% | -2.17 | 84% |
| XGBoost, combined features | 3.41 min | 57% | 71% | 85% | -1.76 | 82% |
| XGBoost, plus same-train and corridor series | 3.28 min | 59% | 72% | 86% | -1.70 | 82% |
| TSLM, text final, 12k | 3.32 min | 65% | 75% | 87% | -1.80 | 90% |
| TSLM, stacked text final, 12k | 3.33 min | 65% | 74% | 86% | -1.57 | 89% |

Within 15 minutes of the planned arrival (36,556 trains): persistence 84% within one minute,
XGBoost 78% and 81%, both TSLM finals 86%.

The 5,000 shared test trains, by class (share within one minute / average miss):

| Model | S-Bahn | Regional | Long-distance |
|---|---|---|---|
| XGBoost, plus new series | 77% / 0.93 min | 72% / 1.58 min | 29% / 7.73 min |
| TSLM, text on the new series, 2k | 85% / 0.90 min | 79% / 1.56 min | 34% / 7.61 min |

- **The language model is right to the minute more often:** 65% against 57 to 59% over the full
  test, in every class and every lead-time bucket.
- **The average miss hides a heavy tail.** All models predict slightly too early on average and the
  spread of the error is 10 to 13 minutes for every one of them, driven by a few very long delays
  none of them foresees; the share within 1, 2 and 5 minutes is the honest summary.
- **Without fine-tuning** the same checkpoint on the same prompts misses by 3.55 minutes on average
  (it mostly repeats the XGBoost forecast in the prompt) but its distribution is far off: CRPS
  +0.347 against the trained model, and none of its generated answers is in the answer format.
- **Every run in the same figures:** `trip/MINUTES.md` (34 runs and baselines on the same 4,729
  test trains).
- **The TSLM's range is a little too wide** (88 to 90% of true delays inside the 10 to 90% range,
  against 82% for XGBoost): cautious rather than overconfident.

## 6. What the ablations established

Each experiment changes one ingredient against a named partner on the shared 5,000 examples;
details and intervals in `DESIGN.md` section 16.

- **Exact-minute loss beats soft targets** (-0.041 CRPS, -0.069 to -0.011). Soft targets blur the
  distribution; the cross-entropy on the exact minute lets the model keep it sharp, and adding a
  CRPS term (`plain_crps`) rewards near misses through a proper score instead. It is the loss of
  the final runs.
- **At 2,000 steps, writing the series into the prompt beats the time-series encoder** (-0.057,
  -0.090 to -0.026), and the encoder adds nothing on top of the text on the original data.
  Eleven encoder-side changes (raw scale, series-reading curriculum, 720-point series, a
  pretrained or random start, a five-times faster encoder, training the encoder alone or first)
  all land within noise of the encoder baseline or below it. With the richer v2 data the
  text-plus-encoder model is the best 2,000-step run, 0.013 ahead of text alone (inside the noise).
- **Given enough steps, the encoder path catches up.** Encoder only for 12,000 steps reaches the
  best validation score of all runs and beats XGBoost at every lead time on the shared test
  (-0.082 overall, -0.072 beyond 30 minutes), level with the text model at 5,000 steps (+0.006,
  -0.044 to +0.062), and beats XGBoost alone on the September set as well (-0.033). The series
  channel carries the same information as the text and needs about twice the training to extract
  it.
- **More training keeps helping** (2k to 5k: -0.024 CRPS for text); the long runs are the finals.
- **The statistical forecast as an input makes the TSLM win everywhere.** With XGBoost's own
  median, range and probabilities written into the prompt as one sentence (out-of-fold on the
  training split), the model corrects the tabular forecast: -0.075 CRPS on the shared test at
  every lead time, and -0.039 alone on September, out of time. The lead-time blend then has
  nothing to add (fitted weight 1.0).
- **Richer data helps both sides equally:** the previous trains on the route improve XGBoost by
  0.036 and the TSLM by 0.018 on the full test, and the TSLM keeps its edge against the retrained
  baseline.
- **Multi-scale history summaries** (90-day and 7-day medians, same-hour lateness) improve
  validation but not test.
- **Calibration is already good:** temperature and Platt re-scaling chosen on validation leave the
  minute distribution as it is; only P(cancelled) benefits from mostly following XGBoost in the
  blend.

## 7. Limits, stated plainly

- Without the statistical forecast in the prompt, a single 2,000-step TSLM does not beat XGBoost
  across the board; the wins are within 15 minutes of arrival and through the lead-time blend.
  With it, the 2,000-step model wins at every lead time and out of time; the 12,000-step finals
  say by how much.
- The encoder, the part of OpenTSLM built for time series, learns more slowly than the text
  channel on this data and adds nothing on top of it at 2,000 steps; at 12,000 steps alone it
  matches the text and beats the tabular baseline.
- Differences of 0.01 to 0.03 CRPS between single runs on 5,000 examples are inside the noise;
  only the full-test and bootstrap-backed claims above should be quoted.
- The September set is scraped from the live feeds and covers 12 days; its XGBoost partner was
  trained on the same May data as the TSLM, so neither side saw the summer.

## 8. Reproducing the numbers

```bash
# examples, baselines, shared metrics
python trip/build.py --raw data/raw --out data/trip/examples.parquet
python trip/baselines.py --examples data/trip/examples.parquet --out out/trip/baselines
# one TSLM run (an H100 job runs exactly this; see trip/RUNS.md for every job's arguments)
python trip/train.py --out out/trip/run --max-steps 2000 --loss-mode plain_crps --prompt-mode text --test-limit 5000
# blend weights on validation, scored on test; then the paired bootstrap
python trip/combine.py --run out/trip/run --baselines out/trip/baselines
python trip/bootstrap.py --a tslm=out/trip/run/tslm_test.npz --b xgb=out/trip/baselines/xgboost_test.npz
python trip/bootstrap.py --a blend=out/trip/run/blend_lead_test.npz --b xgb=out/trip/baselines/xgboost_test.npz --lead-max 15
# September forward test: XGBoost scored on the forward set, a checkpoint scored on it, May weights applied blind
python trip/baselines.py --examples data/trip/examples.parquet --out out/trip/baselines_forward --extra-examples data/trip/forward.parquet
python trip/train.py --eval-only --resume out/trip/run/checkpoint.pt --loss-mode plain_crps --prompt-mode text \
    --examples data/trip/forward.parquet --test-limit 10000 --generate 0 --out out/trip/forward_run
python trip/apply_blend.py --weights out/trip/run/combine.json --tslm out/trip/forward_run/tslm_test.npz \
    --xgb out/trip/baselines_forward/xgboost_forward.npz --examples data/trip/forward.parquet \
    --out out/trip/forward_run/blend_lead_test.npz
```
