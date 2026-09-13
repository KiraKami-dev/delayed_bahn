#!/usr/bin/env bash
# Run a trip-delay checkpoint live on an Apple silicon laptop (MPS) behind the team app.
#
#   trip/run_local.sh setup <dir> <checkpoint.pt> <september test parquet>
#   trip/run_local.sh start <dir>
#
# setup builds a Python 3.12 environment in <dir> (the training pins minus the CUDA packages),
# caches the base model and the OpenTSLM start checkpoint, copies the checkpoint and the
# September rows, and builds the PWA. start serves the model on MODEL_PORT (default 8502) and the
# team backend with the PWA on PORT (default 8000), forwarding POST /api/predict to the model.
#
# Default: v7 text, 2k steps (bucket key models/db-trip-delay-v7-text-2k.pt) with
# september_v7_test.parquet. Its prompt carries XGBoost's forecast, so the xgb_* columns stay.
# For an unstacked model such as final-v2-text, set DROP_XGB=1 at setup so its prompt matches
# training. PROMPT_MODE (default text) must be the mode the checkpoint was trained with.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(git -C "$HERE" rev-parse --show-toplevel)"
MODEL_PORT="${MODEL_PORT:-8502}"
PORT="${PORT:-8000}"
PROMPT_MODE="${PROMPT_MODE:-text}"
MODEL_ID="${MODEL_ID:-OpenTSLM db-trip-delay v7-text (2k, local MPS)}"

case "${1:-}" in
  setup)
    dir="${2:?usage: run_local.sh setup <dir> <checkpoint.pt> <september test parquet>}"
    checkpoint="${3:?checkpoint.pt missing}"
    september="${4:?september test parquet missing}"
    mkdir -p "$dir/model" "$dir/data"
    grep -v -E '^(#|cuda-|uv==)' "$HERE/nebius/requirements.txt" > "$dir/requirements-mac.txt"
    [ -x "$dir/.venv/bin/python" ] || uv venv --python 3.12 "$dir/.venv"
    uv pip install --python "$dir/.venv/bin/python" torch==2.14.0 -r "$dir/requirements-mac.txt"
    "$dir/.venv/bin/python" - <<'PY'
from huggingface_hub import hf_hub_download, snapshot_download
snapshot_download("unsloth/Llama-3.2-3B")
hf_hub_download("OpenTSLM/llama-3.2-3b-m4-sp", "model_checkpoint.pt")
PY
    cp "$checkpoint" "$dir/model/checkpoint.pt"
    DROP_XGB="${DROP_XGB:-0}" "$dir/.venv/bin/python" - "$september" "$dir/data/september_test.parquet" <<'PY'
import os
import sys
import pandas as pd
frame = pd.read_parquet(sys.argv[1])
drop = [c for c in frame.columns if c == "__index_level_0__" or (os.environ["DROP_XGB"] == "1" and c.startswith("xgb_"))]
frame.drop(columns=drop).to_parquet(sys.argv[2])
print(f"{len(frame)} September rows, dropped {drop or 'nothing'}")
PY
    npm --prefix "$ROOT/app/frontend" ci --no-audit --no-fund
    npm --prefix "$ROOT/app/frontend" run build
    ;;
  start)
    dir="${2:?usage: run_local.sh start <dir>}"
    "$dir/.venv/bin/python" "$HERE/serve.py" --examples "$dir/data/september_test.parquet" \
      --checkpoint "$dir/model/checkpoint.pt" --prompt-mode "$PROMPT_MODE" --device mps \
      --model-id "$MODEL_ID" --port "$MODEL_PORT" &
    model_pid=$!
    trap 'kill "$model_pid" 2>/dev/null' EXIT
    until curl -s -m 2 "http://127.0.0.1:$MODEL_PORT/health" > /dev/null; do
      kill -0 "$model_pid" 2>/dev/null || { echo "model server exited"; exit 1; }
      sleep 2
    done
    # Live inference takes about a second per leg; the backend's default 8 s timeout is too tight.
    PORT="$PORT" PREDICT_URL="http://127.0.0.1:$MODEL_PORT/" PREDICT_TIMEOUT_MS="${PREDICT_TIMEOUT_MS:-60000}" \
      node "$ROOT/app/backend/src/server.js"
    ;;
  *)
    sed -n 2,16p "$0"
    exit 1
    ;;
esac
