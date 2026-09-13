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
| XGBoost retrained with previous trains (v2 data) | 3.654 | 2.937 | |
| TSLM, text, v2 data, 2k | 3.616 | 2.889 | -0.048 vs XGBoost-v2 (-0.121 to +0.010) |
| TSLM, text + encoder, v2 data, 2k | 3.603 | 2.877 | -0.060 vs XGBoost-v2 (-0.130 to -0.005) real |
| Lead-time blend, text + plain, 2k | 3.618 | 2.901 | -0.070 (-0.127 to -0.030) real |
| Lead-time blend, text + encoder, v2 data | | | -0.049 vs XGBoost-v2 (-0.100 to -0.015) real |

### 5.2 All 93,738 test examples

| Model | Median error | CRPS | vs XGBoost (CRPS) |
|---|---|---|---|
| XGBoost | 3.462 | 2.759 | |
| XGBoost, v2 data | 3.413 | 2.723 | |
| TSLM, plain loss, encoder, 2k | 3.477 | 2.774 | +0.015 |
| Lead-time blend of that with XGBoost | 3.427 | 2.731 | -0.028 (-0.039 to -0.019) real; median error -0.035 |
| TSLM, original recipe, 12k (30,000 of the test) | 3.434 | 2.754 | XGBoost on the same 30,000: 3.469 / 2.765; median error real |
| Final: text + encoder, plain loss, 12k | *pending, about 04:35* | | |
| Final: text, plain loss, 24k | *pending, about 05:05* | | |
| Final A: text, v2 data, plain + CRPS, 12k | *pending, about 05:30* | | |
| Final B: text + encoder, v3 data, plain + CRPS, 12k | *pending, about 06:30* | | |

### 5.3 By lead time (full test, TSLM plain 2k vs XGBoost)

| Lead time | Examples | TSLM median error | XGBoost median error | CRPS difference |
|---|---|---|---|---|
| up to 15 min | 36,556 | 0.991 | 1.072 | -0.055, real |
| beyond 30 min | | | | +0.076, XGBoost better |

The TSLM is the better model close to arrival, where the live delays at the last stops dominate;
XGBoost is better far out, where the forecast rests on base rates. That is why the blend weights
follow the lead time: about 90% TSLM within 15 minutes, 10 to 35% further out
(`trip/combine.py`, weights fitted on validation only).

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
| Finals | *pending* | | |

The shape found on June to August holds out of time: alone, a 2,000-step TSLM is behind the
tabular model overall and ahead in the last quarter hour; blended by lead time with weights that
never saw September, it beats XGBoost.

## 6. What the ablations established

Each experiment changes one ingredient against a named partner on the shared 5,000 examples;
details and intervals in `DESIGN.md` section 16.

- **Exact-minute loss beats soft targets** (-0.041 CRPS, -0.069 to -0.011). Soft targets blur the
  distribution; the cross-entropy on the exact minute lets the model keep it sharp, and adding a
  CRPS term (`plain_crps`) rewards near misses through a proper score instead. It is the loss of
  the final runs.
- **Writing the series into the prompt beats the time-series encoder** (-0.057, -0.090 to -0.026),
  and the encoder adds nothing on top of the text on the original data. Eleven encoder-side
  changes (raw scale, series-reading curriculum, 720-point series, a pretrained or random start,
  a five-times faster encoder, training the encoder alone) all land within noise of the encoder
  baseline or below it. With the richer v2 data the text-plus-encoder model is the best 2,000-step
  run, 0.013 ahead of text alone (inside the noise).
- **More training keeps helping** (2k to 5k: -0.024 CRPS for text); the long runs are the finals.
- **Richer data helps both sides equally:** the previous trains on the route improve XGBoost by
  0.036 and the TSLM by 0.018 on the full test, and the TSLM keeps its edge against the retrained
  baseline.
- **Multi-scale history summaries** (90-day and 7-day medians, same-hour lateness) improve
  validation but not test.
- **Calibration is already good:** temperature and Platt re-scaling chosen on validation leave the
  minute distribution as it is; only P(cancelled) benefits from mostly following XGBoost in the
  blend.

## 7. Limits, stated plainly

- A single 2,000-step TSLM does not beat XGBoost across the board; the wins are within 15 minutes
  of arrival and through the lead-time blend. Whether a 12,000-step TSLM wins alone on the full
  test is what the final runs answer.
- The encoder, the part of OpenTSLM built for time series, is not where the gain comes from on
  this data; the language model reading the numbers as text is.
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
