#!/usr/bin/env bash
# Run a trip-delay checkpoint live on an Apple silicon laptop (MPS) behind the team app.
# The model files (checkpoint, September rows, xgb/) are not in Git: see "Model files" in trip/README.md.
#
#   trip/run_local.sh setup <dir> <checkpoint.pt> <september test parquet> [<training examples parquet>]
#   trip/run_local.sh start <dir>
#
# setup builds a Python 3.12 environment in <dir> (the training pins minus the CUDA packages, plus
# xgboost), caches the base model and the OpenTSLM start checkpoint, copies the checkpoint and the
# September rows, and builds the PWA. With the training examples it also refits the statistical
# forecast once (live_xgb.py), which live examples need. start serves the model on MODEL_PORT
# (default 8502) and the team backend with the PWA on PORT (default 8000).
#
# Live data: when <dir>/xgb exists, legs without a recorded trip are built from the DB Timetables
# API (live.py) with DB_CLIENT_ID and DB_API_KEY from ENV_FILE (default: the repo root's .env),
# at most CALLS_PER_MINUTE (default 55) calls per minute.
#
# Default: the embedding model, split mode on v7 after 6k steps (bucket key models/db-trip-delay-v7-split-6k.pt) with
# september_v7_test.parquet. Its prompt carries XGBoost's forecast, so the xgb_* columns stay.
# For an unstacked model such as final-v2-text, set DROP_XGB=1 at setup so its prompt matches
# training. PROMPT_MODE (default split) must be the mode the checkpoint was trained with: text for
# the submitted text model (models/db-trip-delay-final.pt).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(git -C "$HERE" rev-parse --show-toplevel)"
MODEL_PORT="${MODEL_PORT:-8502}"
PORT="${PORT:-8000}"
PROMPT_MODE="${PROMPT_MODE:-split}"
MODEL_ID="${MODEL_ID:-OpenTSLM db-trip-delay v7 split (6k, embeddings, local MPS)}"

# xgboost needs an OpenMP runtime; torch ships one, so no system install is needed.
torch_lib() {
  "$1/.venv/bin/python" -c "import os, torch; print(os.path.join(os.path.dirname(torch.__file__), 'lib'))"
}

case "${1:-}" in
  setup)
    dir="${2:?usage: run_local.sh setup <dir> <checkpoint.pt> <september test parquet> [<training examples parquet>]}"
    checkpoint="${3:?checkpoint.pt missing}"
    september="${4:?september test parquet missing}"
    examples="${5:-}"
    mkdir -p "$dir/model" "$dir/data"
    grep -v -E '^(#|cuda-|uv==)' "$HERE/nebius/requirements.txt" > "$dir/requirements-mac.txt"
    [ -x "$dir/.venv/bin/python" ] || uv venv --python 3.12 "$dir/.venv"
    uv pip install --python "$dir/.venv/bin/python" torch==2.14.0 xgboost -r "$dir/requirements-mac.txt"
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
    if [ -n "$examples" ]; then
      DYLD_LIBRARY_PATH="$(torch_lib "$dir")" "$dir/.venv/bin/python" "$HERE/live_xgb.py" --examples "$examples" \
        --out "$dir/xgb" --check "$dir/data/september_test.parquet"
    fi
    npm --prefix "$ROOT/app/frontend" ci --no-audit --no-fund
    npm --prefix "$ROOT/app/frontend" run build
    ;;
  start)
    dir="${2:?usage: run_local.sh start <dir>}"
    live_args=()
    if [ -d "$dir/xgb" ]; then
      live_args=(--xgb "$dir/xgb" --env "${ENV_FILE:-$ROOT/.env}" --calls-per-minute "${CALLS_PER_MINUTE:-55}")
      if [ "${OFFLINE:-0}" = 1 ]; then
        live_args+=(--offline)  # no API calls at all: offline estimates from the stored runs
      fi
    fi
    DYLD_LIBRARY_PATH="$(torch_lib "$dir")" "$dir/.venv/bin/python" "$HERE/serve.py" \
      --examples "$dir/data/september_test.parquet" --checkpoint "$dir/model/checkpoint.pt" \
      --prompt-mode "$PROMPT_MODE" --device mps --model-id "$MODEL_ID" --port "$MODEL_PORT" \
      ${live_args[@]+"${live_args[@]}"} &
    model_pid=$!
    trap 'kill "$model_pid" 2>/dev/null' EXIT
    until curl -s -m 2 "http://127.0.0.1:$MODEL_PORT/health" > /dev/null; do
      kill -0 "$model_pid" 2>/dev/null || { echo "model server exited"; exit 1; }
      sleep 2
    done
    # A cold live leg needs 15 to 40 API calls and waits when the minute's budget is spent.
    # CAUSES_URL (default: the db_route server on :8501 when it answers) keeps the "Why" tab on the
    # per-station cause families of the route model instead of the bundled fixture.
    causes_url="${CAUSES_URL:-}"
    if [ -z "$causes_url" ] && curl -s -m 2 "http://127.0.0.1:8501/health" > /dev/null; then
      causes_url="http://127.0.0.1:8501/causes"
    fi
    # PREDICT_FALLBACK_URL: the route model answers the legs this model can only average (no recorded
    # or live trip). Default: the db_route relay/serve_route server on :8503, else :8501, when up.
    fallback_url="${PREDICT_FALLBACK_URL:-}"
    for port in 8503 8501; do
      [ -n "$fallback_url" ] && break
      curl -s -m 2 "http://127.0.0.1:$port/health" > /dev/null && fallback_url="http://127.0.0.1:$port/predict"
    done
    PORT="$PORT" PREDICT_URL="http://127.0.0.1:$MODEL_PORT/" PREDICT_TIMEOUT_MS="${PREDICT_TIMEOUT_MS:-120000}" \
      CAUSES_URL="$causes_url" PREDICT_FALLBACK_URL="$fallback_url" node "$ROOT/app/backend/src/server.js"
    ;;
  *)
    sed -n 2,21p "$0"
    exit 1
    ;;
esac
