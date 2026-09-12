#!/usr/bin/env bash
# Nebius job: four one-GPU trip-delay runs side by side on a 4x L40S node.
#
# The bucket mounted at /data is only read (code/trip.tar.gz, code/requirements.txt,
# data/examples.parquet). Bucket mounts may not allow overwriting or appending, so every run
# writes to local disk, prints its progress to the job log with a run prefix (visible with
# `nebius ai job logs <id> --follow`), and the results are copied to /data/runs/$RUN_TAG/ once,
# as new files, when the script exits.
set -uo pipefail

DATA=/data
for required in code/trip.tar.gz code/requirements.txt data/examples.parquet; do
  # Fail in seconds, not after the package install, when the bucket is not filled yet.
  [ -f "$DATA/$required" ] || { echo "missing $DATA/$required in the bucket"; exit 1; }
done
WORK=/workspace/trip-run
LOCAL=/workspace/results
OUT="$DATA/runs/${RUN_TAG:-ablations}"
STEPS=${STEPS:-2000}
VAL_LIMIT=${VAL_LIMIT:-3000}
TEST_LIMIT=${TEST_LIMIT:-5000}
GENERATE=${GENERATE:-16}
mkdir -p "$WORK" "$LOCAL"
cd "$WORK"

copy_results() {
  # New files under a fresh prefix only, so no mount has to overwrite or append.
  echo "$(date -u +%FT%TZ) copying results to $OUT"
  mkdir -p "$OUT" && cp -r "$LOCAL/." "$OUT/" && echo "$(date -u +%FT%TZ) results copied"
}
trap copy_results EXIT

export HF_HOME=/workspace/hf
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
nvidia-smi

# The CUDA runtime image is minimal: fetch curl, then uv, then a Python 3.12 environment
# pinned to the versions the devbox trained with (opentslm needs Python 3.12 or later).
# build-essential: Triton compiles GPU kernels at runtime and needs a C compiler.
apt-get update -qq && apt-get install -y -qq curl ca-certificates build-essential > /dev/null
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv venv --python 3.12 .venv
# torch comes from the CUDA 13.0 index, as on the devbox; the rest is pinned from its freeze.
uv pip install --python .venv/bin/python torch==2.14.0 torchvision==0.29.0 --index-url https://download.pytorch.org/whl/cu130
uv pip install --python .venv/bin/python -r "$DATA/code/requirements.txt"

tar -xzf "$DATA/code/trip.tar.gz"
mkdir -p data/trip
cp "$DATA/data/examples.parquet" data/trip/examples.parquet

# Download the base model and both checkpoints once, before four processes race for them.
.venv/bin/python - <<'PY'
from huggingface_hub import hf_hub_download, snapshot_download
snapshot_download("unsloth/Llama-3.2-3B")
for repo in ("OpenTSLM/llama-3.2-3b-m4-sp", "OpenTSLM/llama-3.2-3b-ecg-sp"):
    hf_hub_download(repo, "model_checkpoint.pt")
print("models cached")
PY

RUNS=${RUNS:-plain_ce text_only ecg_sp_start random_encoder}
NEXT_GPU=0

run() {
  local name=$1
  shift
  case " $RUNS " in *" $name "*) ;; *) return 0 ;; esac
  local gpu=$NEXT_GPU
  NEXT_GPU=$((NEXT_GPU + 1))
  mkdir -p "$LOCAL/$name"
  echo "$(date -u +%FT%TZ) $name starting on GPU $gpu"
  (
    CUDA_VISIBLE_DEVICES=$gpu .venv/bin/python -u trip/train.py --out "$LOCAL/$name" --max-steps "$STEPS" \
      --max-hours 4.5 --workers 6 --val-limit "$VAL_LIMIT" --test-limit "$TEST_LIMIT" --generate "$GENERATE" "$@" \
      2>&1 | tee "$LOCAL/$name/train.log" | sed -u "s/^/[$name] /"
    echo "$(date -u +%FT%TZ) $name exit ${PIPESTATUS[0]}" | tee -a "$LOCAL/status.log"
  ) &
}

# RUNS picks which of these a job runs; each selected run gets the next free GPU.
run main
run plain_ce --loss-mode plain
run plain_ce_lr2x --loss-mode plain --lr 2e-4 --lr-encoder 4e-4
run text_only --text-only --grad-checkpointing
run ecg_sp_start --start-checkpoint OpenTSLM/llama-3.2-3b-ecg-sp
run random_encoder --start-checkpoint none
# Anything else, without editing this file: RUNS=custom CUSTOM_ARGS="--loss-mode plain --lr 3e-4".
# shellcheck disable=SC2086
run custom ${CUSTOM_ARGS:-}
wait
echo "$(date -u +%FT%TZ) all runs finished" | tee -a "$LOCAL/status.log"
