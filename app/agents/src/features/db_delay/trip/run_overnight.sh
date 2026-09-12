#!/usr/bin/env bash
# Unattended queue on the GPU box: main model, report, plain cross-entropy ablation, report.
# Expects the devbox layout: this directory as trip/ next to .venv/, data/trip/ and out/trip/.
set -u
cd "$(dirname "$0")/.."
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
PY=.venv/bin/python
STEPS=${STEPS:-12000}
BASELINES=out/trip/baselines_5000
[ -f "$BASELINES/metrics.json" ] || BASELINES=out/trip/baselines

report() {
  $PY trip/report.py --out out/trip/report \
    --model "persistence=$BASELINES/persistence_test.npz" \
    --model "key history=$BASELINES/key_history_test.npz" \
    --model "xgboost=$BASELINES/xgboost_test.npz" \
    --model "tslm soft+crps=out/trip/tslm_soft_crps/tslm_test.npz" \
    --model "tslm plain ce=out/trip/tslm_plain/tslm_test.npz" > out/trip/report.log 2>&1
}

echo "$(date -u +%FT%TZ) main run" >> out/trip/queue.log
$PY trip/train.py --loss-mode soft_crps --max-steps "$STEPS" --max-hours 3.5 --workers 6 \
  --out out/trip/tslm_soft_crps > out/trip/tslm_soft_crps.log 2>&1
status=$?  # capture before any command substitution resets it
echo "$(date -u +%FT%TZ) main run exit $status" >> out/trip/queue.log
report

echo "$(date -u +%FT%TZ) ablation run" >> out/trip/queue.log
$PY trip/train.py --loss-mode plain --max-steps "$STEPS" --max-hours 3.5 --workers 6 \
  --out out/trip/tslm_plain > out/trip/tslm_plain.log 2>&1
status=$?
echo "$(date -u +%FT%TZ) ablation run exit $status" >> out/trip/queue.log
report
echo "$(date -u +%FT%TZ) done" >> out/trip/queue.log
