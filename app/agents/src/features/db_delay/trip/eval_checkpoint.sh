#!/usr/bin/env bash
# Evaluate a checkpoint of the running main model on the GPU next to training, then compare it
# with the baselines on the same examples. Waits until the log is past the step and the checkpoint
# has been quiet for a minute. Usage: bash trip/eval_checkpoint.sh 5000 [val_limit] [test_limit]
# Expects the devbox layout described in run_overnight.sh.
set -u
cd "$(dirname "$0")/.."
PY=.venv/bin/python
STEP=${1:?usage: eval_checkpoint.sh <step> [val_limit] [test_limit]}
VAL=${2:-3000}
TEST=${3:-5000}
LOG=out/trip/tslm_soft_crps.log
CKPT=out/trip/tslm_soft_crps/checkpoint.pt
DIR=out/trip/eval_step$STEP
BASE=out/trip/baselines_5000

last_step() { grep "^step" "$LOG" | tail -1 | sed -E 's#^step ([0-9]+)/.*#\1#'; }
until [ "$(last_step)" -ge $((STEP + 25)) ] 2>/dev/null && [ $(( $(date +%s) - $(stat -c %Y "$CKPT") )) -ge 60 ]; do
  sleep 20
done

mkdir -p "$DIR"
cp "$CKPT" "$DIR/checkpoint.pt"
echo "$(date -u +%FT%TZ) eval step $STEP started" >> out/trip/eval.log
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True $PY trip/train.py --eval-only --resume "$DIR/checkpoint.pt" \
  --val-limit "$VAL" --test-limit "$TEST" --generate 16 --workers 4 --eval-batch-size 16 --out "$DIR" > "$DIR/eval.log" 2>&1
echo "$(date -u +%FT%TZ) eval step $STEP exit $?" >> out/trip/eval.log
for split in validation test; do
  $PY trip/report.py --split "$split" --out "$DIR/report" \
    --model "persistence=$BASE/persistence_$split.npz" \
    --model "key history=$BASE/key_history_$split.npz" \
    --model "xgboost=$BASE/xgboost_$split.npz" \
    --model "tslm step $STEP=$DIR/tslm_$split.npz" >> "$DIR/eval.log" 2>&1
done
echo "$(date -u +%FT%TZ) eval step $STEP report written" >> out/trip/eval.log
