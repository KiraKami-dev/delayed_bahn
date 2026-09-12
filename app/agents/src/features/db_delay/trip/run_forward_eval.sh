#!/usr/bin/env bash
# After the overnight queue: score both TSLM checkpoints on the September forward set, then report.
# Expects the devbox layout described in run_overnight.sh. Waits until the overnight queue is done,
# the forward examples exist, and the baselines have scored them.
set -u
cd "$(dirname "$0")/.."
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
PY=.venv/bin/python
FORWARD=data/trip/forward.parquet
BASE=out/trip/baselines_forward

# Match only run_overnight.sh's final "<timestamp> done" line: other scripts log "... step N done".
until grep -qE "^[0-9T:-]+Z done$" out/trip/queue.log 2>/dev/null && [ -f "$FORWARD" ] && [ -f "$BASE/xgboost_forward.npz" ]; do
  sleep 60
done

for run in soft_crps plain; do
  [ -f "out/trip/tslm_$run/checkpoint.pt" ] || continue
  echo "$(date -u +%FT%TZ) forward eval $run" >> out/trip/queue.log
  $PY trip/train.py --eval-only --resume "out/trip/tslm_$run/checkpoint.pt" --loss-mode "$run" \
    --examples "$FORWARD" --val-limit 200 --test-limit 10000 --generate 0 --workers 6 \
    --out "out/trip/tslm_${run}_forward" > "out/trip/tslm_${run}_forward.log" 2>&1
  status=$?  # capture before any command substitution resets it
  echo "$(date -u +%FT%TZ) forward eval $run exit $status" >> out/trip/queue.log
done

$PY trip/report.py --examples "$FORWARD" --split test --out out/trip/report_forward \
  --model "persistence=$BASE/persistence_forward.npz" \
  --model "key history=$BASE/key_history_forward.npz" \
  --model "xgboost=$BASE/xgboost_forward.npz" \
  --model "tslm soft+crps=out/trip/tslm_soft_crps_forward/tslm_test.npz" \
  --model "tslm plain ce=out/trip/tslm_plain_forward/tslm_test.npz" > out/trip/report_forward.log 2>&1
echo "$(date -u +%FT%TZ) forward report done" >> out/trip/queue.log
