#!/usr/bin/env bash
# Learning curve on the side: score saved checkpoints of the running main model on 300 validation
# examples, on the CPU so the training GPU is untouched. Usage: bash trip/learning_curve.sh 2000 4000 8000
# Expects the devbox layout described in run_overnight.sh.
set -u
cd "$(dirname "$0")/.."
PY=.venv/bin/python
LOG=out/trip/tslm_soft_crps.log
CKPT=out/trip/tslm_soft_crps/checkpoint.pt
CURVE=out/trip/learning_curve.md

last_step() { grep "^step" "$LOG" | tail -1 | sed -E 's#^step ([0-9]+)/.*#\1#'; }

for target in "$@"; do
  # The checkpoint is rewritten every 1000 steps: wait until the log is past the target and
  # the file has been quiet for a minute, so it is neither older nor half-written.
  until [ "$(last_step)" -ge $((target + 25)) ] 2>/dev/null && [ $(( $(date +%s) - $(stat -c %Y "$CKPT") )) -ge 60 ]; do
    grep -q "training stopped" "$LOG" 2>/dev/null && break
    sleep 30
  done
  dir=out/trip/early_step$target
  mkdir -p "$dir"
  cp "$CKPT" "$dir/checkpoint.pt"
  CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=16 $PY trip/train.py --eval-only --device cpu --resume "$dir/checkpoint.pt" \
    --val-limit 300 --splits validation --generate 0 --workers 2 --eval-batch-size 8 --out "$dir" > "$dir/eval.log" 2>&1
  models=(--model "xgboost=out/trip/baselines/xgboost_validation.npz")
  for d in out/trip/early_step*/; do
    d=${d%/}
    [ -f "$d/tslm_validation.npz" ] && models+=(--model "tslm step ${d#out/trip/early_step}=$d/tslm_validation.npz")
  done
  $PY trip/report.py --split validation --out out/trip/learning_curve "${models[@]}" > /dev/null 2>&1
  # The section is a heading, a blank line and the table; stop at the next heading, not the blank line.
  awk '/^## overall/{f=1} /^## / && !/^## overall/{f=0} f' out/trip/learning_curve/validation_report.md > "$CURVE"
  echo "$(date -u +%FT%TZ) learning curve step $target done" >> out/trip/queue.log
done
