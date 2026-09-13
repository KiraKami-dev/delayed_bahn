# Training the db-route datasets

The recipe is `db_delay/trip` (Jonas): OpenTSLM-SoftPrompt on Llama-3.2-3B from the published
`OpenTSLM/llama-3.2-3b-m4-sp` encoder, LoRA on, a minute-distribution readout after `Answer:`.
`train_route.py` points it at our TimeF registry through `bridge.py`; the loss accepts our three
non-minute tasks as plain cross-entropy. One profile per GPU.

## Environment: why it is not the PyTorch image

`opentslm` needs Python ≥ 3.12; `pytorch/pytorch:*-runtime` images ship 3.11, so every job on
them dies at `pip install`. Use the bare CUDA image and build the venv in `--setup`, exactly as
`trip/nebius/run_ablations.sh` does — `nebius_setup_train.sh` is that step and
`requirements_train.txt` is Jonas's devbox freeze plus `timenet`, `timenet-connectors`, `pytz`,
`xgboost`. The requirements file is read from the bucket (`code/requirements_train.txt`), not
injected, because the backend would otherwise run it through the image's system pip.

## Submit (one job per profile; H100 NVLink = `gpu-h100-sxm`)

```bash
SC=…/scratchpad  # or anywhere; the two files are in this folder
for p in week quarter season multiscale; do
  npm --prefix app/backend run -s train -- submit --name route-2k-$p \
    --script $PWD/app/agents/src/features/db_route/train_route.py \
    --image nvidia/cuda:13.1.1-runtime-ubuntu24.04 \
    --setup "$(cat app/agents/src/features/db_route/nebius_setup_train.sh)" \
    --platform gpu-h100-sxm --preset 1gpu-16vcpu-200gb \
    --output storagebucket-e0016098467606655017642 --timeout 4h --disk-gib 100 \
    --env RUN_TAG=route-2k --env HF_HOME=/workspace/hf \
    -- --profiles $p --grad-checkpointing --steps 2000 --tag route-2k
done
```

A multi-GPU preset runs the same script under `torchrun`, with rank *i* → profile *i* of
`--profiles`; the 4×L40S preset would not provision tonight, the 1-GPU H100 preset did in under a
minute. Inputs: `code/db_route.tar.gz` and `registry/` in the bucket. Outputs:
`runs/<tag>/<profile>/{metrics.json, checkpoint.pt, scalar_<cell>.npz}`.

## Serving the results to the app

`serve_route.py` turns a finished run into the model server the Node backend expects
(`PREDICT_URL`, `CAUSES_URL`): it loads the profile's registry (records, annotations, the
six-hourly series) and the run's `scalar_<cell>.npz`, matches each journey leg to a recorded
(service group, station) and answers with the model's held-out minute distribution, that stop's
recorded history when the model did not score it, or a class prior -- each labelled as such in the
reply. `GET /causes?station=` reads the station's cause-share series for the seven days before its
latest travel date. No torch, no checkpoint: pandas, pyarrow and numpy.

```bash
bash fetch_serving_data.sh route-2k quarter   # ~35 MB from the bucket into app/agents/data/db-route (S3 key in the root .env)
./serve_route.sh --port 8501                  # POST /predict, GET /causes?station=, GET /health
```

## What gets scored

Per split cell (`val`, `test_seen_entity`, `test`, `test_seen_time`): median error, CRPS,
10–90% coverage and width, Brier for late ≥ 5 min — for the TSLM's minute distribution, the
eight-week habit as persistence, and an XGBoost on the same scalar annotations and caption levels.
`test_seen_entity` (known trains, unseen weeks) is the deployment number; `test` (unseen trains
and weeks) is the generalisation diagnostic. Classification tasks report generated-answer accuracy
against the majority class on a subsample.

## Live serving: the model answers every request on the GPU

`serve_live.py` is `serve_route.py` with the checkpoint loaded: each matched record gets a fresh
forward pass (≈50–90 ms on one H100) instead of the stored `scalar_<cell>.npz` quantiles, so all
10,204 recorded (service group, station) rows are forecastable, not only the 2,089 held-out ones.
A Nebius job has no ingress, so requests travel through the bucket: `relay_proxy.py` on the laptop
speaks the serve_route HTTP contract on `:8502` and writes each request to
`live/<name>/requests/<id>.json`; the job answers under `responses/` (≈0.6–1 s round trip). When
the job's `heartbeat.txt` is stale or it stays silent for 6 s, the proxy answers from the local
`serve_route.py` on `:8501` and suffixes `modelId` with `(precomputed fallback: …)`.

```bash
# once: the training tarball plus the current db_route/*.py -> code/db_route_live.tar.gz in the bucket
D=app/agents/src/features/db_route
npm --prefix app/backend run -s train -- submit --name live-route-quarter \
  --script $PWD/$D/serve_live.py --inject $PWD/$D/train_route.py:/workspace/train_route.py \
  --image nvidia/cuda:13.1.1-runtime-ubuntu24.04 --setup "$(cat $D/nebius_setup_train.sh)" \
  --platform gpu-h100-sxm --preset 1gpu-16vcpu-200gb \
  --output storagebucket-e0016098467606655017642 --timeout 8h --disk-gib 100 --env HF_HOME=/workspace/hf \
  -- --profile quarter --tag route-2k --name live-route-quarter
uv run --no-project --with boto3 python $D/relay_proxy.py --port 8502 --timeout 6     # laptop
PREDICT_URL=http://127.0.0.1:8502/predict CAUSES_URL=http://127.0.0.1:8501/causes node app/backend/src/server.js
```

Setup takes about eight minutes (torch, the Llama-3.2-3B base, 79 s of dataset rows). The bucket
mount is an object store: an emptied folder disappears (both sides keep a `.keep` object), there is
no rename, and overwriting means unlink then write. `--tunnel` adds a Cloudflare quick tunnel and
publishes the URL to `serve/<name>/url.txt` if a public endpoint is wanted instead.
