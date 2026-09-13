#!/usr/bin/env bash
# September forward test of one finished run, in one command, on the devbox.
#
#   trip/forward_final.sh <run dir> <prompt mode> <examples> <forward examples> <baselines> <forward baselines>
#   trip/forward_final.sh out/trip/ablations/final-v3-both both data/trip/examples_v3.parquet \
#       data/trip/forward_v3.parquet out/trip/baselines_v3 out/trip/baselines_v3f
#
# The run directory holds checkpoint.pt and tslm_validation.npz from the job. Steps:
#   1. blend weights on the run's May validation against the matching XGBoost (combine.py),
#   2. the checkpoint scored on 10,000 September examples (train.py --eval-only),
#   3. the May weights applied blind to September (apply_blend.py),
#   4. paired bootstraps against XGBoost: alone, within 15 minutes, and the blend.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
PY=.venv/bin/python

RUN=$1; MODE=$2; EXAMPLES=$3; FORWARD=$4; BASE=$5; BASE_FWD=$6
LOSS=${LOSS:-plain_crps}
LIMIT=${LIMIT:-10000}
OUT="${RUN}_forward"
XGB_FWD="$BASE_FWD/xgboost_forward.npz"

echo "== blend weights on May validation"
$PY trip/combine.py --run "$RUN" --baselines "$BASE" --examples "$EXAMPLES" | grep -A 8 "## test, overall" || true

echo "== September, $LIMIT examples"
$PY trip/train.py --eval-only --resume "$RUN/checkpoint.pt" --loss-mode "$LOSS" --prompt-mode "$MODE" \
  --examples "$FORWARD" --val-limit 200 --test-limit "$LIMIT" --generate 0 --workers 6 --eval-batch-size 32 \
  --out "$OUT" > "$OUT.log" 2>&1
grep -E "^test " "$OUT.log" | cut -c1-200 || tail -3 "$OUT.log"

echo "== May weights applied blind to September"
$PY trip/apply_blend.py --weights "$RUN/combine.json" --tslm "$OUT/tslm_test.npz" --xgb "$XGB_FWD" \
  --examples "$FORWARD" --out "$OUT/blend_lead_test.npz"

echo "== bootstraps against XGBoost on September"
$PY trip/bootstrap.py --a tslm="$OUT/tslm_test.npz" --b xgb="$XGB_FWD" --examples "$FORWARD" | tail -3
$PY trip/bootstrap.py --a tslm="$OUT/tslm_test.npz" --b xgb="$XGB_FWD" --examples "$FORWARD" --lead-max 15 | tail -3
$PY trip/bootstrap.py --a blend="$OUT/blend_lead_test.npz" --b xgb="$XGB_FWD" --examples "$FORWARD" | tail -3
