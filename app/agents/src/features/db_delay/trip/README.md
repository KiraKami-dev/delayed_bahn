# trip

Per-trip arrival delay: one train run, one target stop, one prediction moment. Design and
results: `../DESIGN.md`.

| File | Does |
|---|---|
| `build.py` | Monthly parquet to leakage-safe examples (DuckDB) |
| `inspect_examples.py` | Sanity summaries and one rendered prompt |
| `check_samples.py` | Renders every example and checks answer tokens before an unattended run |
| `metrics.py` | Shared scoring: median error, CRPS, coverage, Brier, cancel log loss |
| `baselines.py` | Persistence, key history, XGBoost |
| `prompts.py` | Example to OpenTSLM sample; rationale from inputs only |
| `model.py` | OpenTSLM-SP wrapper: padding fix, minute-aware loss, distribution readout |
| `train.py` | Fine-tune from an OpenTSLM checkpoint, then evaluate. `--text-only` writes the series into the prompt as numbers (baseline without the encoder); `--start-checkpoint none` starts the encoder from random weights (ablation) |
| `learning_curve.sh` | Scores saved checkpoints of the running main model on 300 validation examples, on the CPU |
| `eval_checkpoint.sh` | Evaluates a saved checkpoint on the GPU next to training and reports it against the baselines |
| `after_main.sh` | Waits for the main run, writes the report and triggers the September evaluation |
| `calibrate.py` | Fits a temperature for the minute distribution on validation and applies it to test |
| `combine.py` | Recalibrates P(cancelled) and blends TSLM and XGBoost quantiles, weights fitted on validation |
| `bootstrap.py` | Paired bootstrap interval for the CRPS and median-error difference between two models |
| `nebius/setup_vm.sh` | One-time setup of a persistent GPU VM in the devbox layout |
| `nebius/compare_ablations.sh` | Pulls ablation results from the bucket and scores them against the baselines and the main run |
| `report.py` | Score every model on the same examples |
| `run_overnight.sh` | GPU queue: main run, report, plain cross-entropy ablation, report |
| `run_forward_eval.sh` | After the overnight queue: both checkpoints on the September forward set, report |
| `predict.py` | Traveller output for recorded trips and a change: typical delay, range, on-time chance |
| `connection.py` | Change and journey success probability from delay distributions and transfer times |
| `timef_export.py` | Built examples to a TimeF dataset (series, annotations, tasks), with read-back |
| `timenet_connector/` | TimeNet connector `error404/db-trip-delay`: download monthly files, build, convert |
| `test_build.py`, `test_metrics.py`, `test_model.py` | Smoke tests (synthetic data, tokenizer only) |

Run from a directory holding `.venv/`, `data/raw/data-YYYY-MM.parquet` and this folder as
`trip/`:

```bash
python trip/test_metrics.py && python trip/test_build.py && python trip/test_model.py
python trip/build.py                                  # data/trip/examples.parquet
python trip/inspect_examples.py
python trip/baselines.py                              # out/trip/baselines/
python trip/train.py --train-limit 400 --max-steps 30 --val-limit 48 --test-limit 48 --out out/trip/smoke
bash trip/run_overnight.sh                            # full runs and out/trip/report/
```

Needs `duckdb`, `pandas`, `pyarrow`, `xgboost`, `torch`, `transformers`, `peft` and
`opentslm`, plus one 48 GB GPU for training at batch 8.

## Final model

The submission checkpoint is **stacked text on the v7 examples, 6,000 steps**: the train's own
delays and the previous trains written into the prompt, plus one rationale sentence with the
same-train and corridor gains and XGBoost's out-of-fold forecast. Loss: exact minute plus CRPS.

| | |
|---|---|
| Checkpoint | bucket `models/db-trip-delay-final.pt` (same bytes as `models/db-trip-delay-v7-text-6k.pt`) |
| Base | `unsloth/Llama-3.2-3B` with the `OpenTSLM/llama-3.2-3b-m4-sp` start checkpoint, LoRA |
| Examples | `examples_v7.parquet` (298,430 examples; train November to April, validation May, test June to August) |
| Prompt mode | `text` |
| Test, 30,000 examples | median error 3.224, CRPS 2.560; against XGBoost with the same features -0.074 (-0.097 to -0.055) |
| September, 10,000 examples | median error 2.524, CRPS 2.001; against XGBoost -0.062 (-0.102 to -0.036) |

Rebuild and retrain:

```bash
python trip/build.py --out data/trip/examples_v7_base.parquet   # same-train and corridor series included
python trip/baselines.py --examples data/trip/examples_v7_base.parquet --out out/trip/baselines_v7f \
    --extra-examples data/trip/forward_v7_base.parquet
python trip/stack.py --examples data/trip/examples_v7_base.parquet --baselines out/trip/baselines_v7f \
    --out data/trip/examples_v7.parquet                           # out-of-fold forecasts on the training split
python trip/train.py --examples data/trip/examples_v7.parquet --max-steps 6000 --val-limit 3000 \
    --test-limit 30000 --generate 48 --loss-mode plain_crps --prompt-mode text --eval-batch-size 32
```

The September set (`forward_v7_base.parquet`) is built with the same code from the September feeds, see `run_forward_eval.sh`; its forecasts come from XGBoost
trained on May only (`stack.py --splits test --no-oof`). Every other run and its exact command is
in `RUNS.md`; the results are in `../EVALUATION.md` and `../DESIGN.md` section 16.

Serve it behind the app with `trip/serve.py --checkpoint <checkpoint> --prompt-mode text --examples
<v7 examples>` (live model), or with `--predictions` on saved September forecasts (no GPU).

## Model server for the app

`serve.py` answers the backend's `PREDICT_URL` contract: a journey in, one arrival-delay
distribution per leg out (`legs[].arrival.probs` over whole minutes, `pCancel`, a rationale and
sources). Each leg is matched to a recorded trip by train, target station and planned arrival, and
answered with the forecast the model made for that trip, either saved by `train.py`/`combine.py` or
computed live from a checkpoint on a GPU. A leg with no recorded trip gets the empirical
distribution of its train type, marked as `confidence: low` and "not a forecast", so a journey is
never dropped whole. An optional `now` in the body picks the forecast that was available at that
time; without it the last forecast before the planned arrival is used.

```bash
python trip/serve.py --examples data/trip/forward.parquet \
    --predictions out/trip/forward_text-plaincrps/blend_lead_test.npz \
                  out/trip/forward_text-plaincrps/tslm_test.npz --port 8501
# then, for the Node backend: PREDICT_URL=http://127.0.0.1:8501/ npm run dev
```

`GET /health` reports how many trips and saved forecasts are loaded; `test_serve.py` covers the
matching (train spellings, time zones, station name variants), the rebuilt distribution for
quantile-only prediction files, and the HTTP round trip.

On a laptop without the training environment, the precomputed mode needs only pandas, pyarrow
and numpy, so `uv` can run it in place with the September test rows and the saved forecasts
copied from the GPU box (about 17 MB together):

```bash
uv run --python 3.12 --with pandas --with pyarrow --with numpy python trip/serve.py \
    --examples september_test.parquet --predictions tslm_test.npz --port 8501
PREDICT_URL=http://127.0.0.1:8501/ node app/backend/src/server.js   # the team app, port 8000
```

Checked end to end: `POST /api/predict` on the team backend with two real September trains
returns the app's `Prediction` (expected delay, transfer-miss and plan-fail probabilities) from
our forecasts, with `fallbackFrom` unset and our rationale as the explanation.

## Demo: a traveller's connection

`predict.py` turns a trained checkpoint into the traveller view for recorded trips. With two
example ids it reads the first as the arriving train, the second as the connecting train at the
same station, and adds the chance of making the change from the two delay distributions and
the transfer times (`connection.py`). `demo/goettingen_connection.json` is the output for two
ICE trains meeting at Göttingen on the morning of 12 September 2026, forecast 14 and 29 minutes
before their planned arrivals from the September forward set (data the model never trained on):

```bash
python trip/predict.py --examples data/trip/forward.parquet \
    --checkpoint out/trip/ablations/plain_ce/plain_ce/checkpoint.pt \
    --example-ids 1117 45787 --buffer 19 --min-transfer 5
```

Each forecast carries a headline ("about +1 min, likely 0 to 5 min, 92% chance of arriving on
time"), the typical delay, the 10 to 90% range, P(on time), P(cancelled), the rationale built
from the inputs and, for recorded trips, what actually happened. Inference for a pair takes a
few seconds on one GPU once the model is loaded.
