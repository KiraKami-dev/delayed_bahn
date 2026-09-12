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
