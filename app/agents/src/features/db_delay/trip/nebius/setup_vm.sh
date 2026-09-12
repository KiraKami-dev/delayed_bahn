#!/usr/bin/env bash
# One-time setup of a persistent Nebius GPU VM for fast iteration, in the devbox layout:
#   ~/trip-dev/.venv, ~/trip-dev/trip/, ~/trip-dev/data/trip/examples.parquet, ~/trip-dev/out/trip/
# Run on the VM after copying trip.tar.gz, requirements.txt and examples.parquet to ~/incoming/.
set -euo pipefail

BASE=$HOME/trip-dev
IN=$HOME/incoming
mkdir -p "$BASE/data/trip" "$BASE/out/trip"
cd "$BASE"

nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
# Triton compiles GPU kernels at runtime and needs a C compiler.
command -v gcc > /dev/null || { sudo apt-get update -qq && sudo apt-get install -y -qq build-essential > /dev/null; }
command -v uv > /dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

[ -x .venv/bin/python ] || uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python torch==2.14.0 torchvision==0.29.0 --index-url https://download.pytorch.org/whl/cu130
uv pip install --python .venv/bin/python -r "$IN/requirements.txt" xgboost

tar -xzf "$IN/trip.tar.gz"
cp "$IN/examples.parquet" data/trip/examples.parquet

.venv/bin/python - <<'PY'
from huggingface_hub import hf_hub_download, snapshot_download
snapshot_download("unsloth/Llama-3.2-3B")
for repo in ("OpenTSLM/llama-3.2-3b-m4-sp", "OpenTSLM/llama-3.2-3b-ecg-sp"):
    hf_hub_download(repo, "model_checkpoint.pt")
import torch
print("models cached; cuda devices:", torch.cuda.device_count())
PY

.venv/bin/python trip/test_metrics.py
.venv/bin/python trip/test_model.py
echo "setup done in $BASE"
