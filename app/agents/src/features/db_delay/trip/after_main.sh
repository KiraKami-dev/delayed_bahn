#!/usr/bin/env bash
# Replaces the rest of run_overnight.sh once the ablations moved to Nebius: wait for the main
# training process to finish (it evaluates itself), write the report, then log the final "done"
# line that run_forward_eval.sh waits for. Usage: bash trip/after_main.sh <main training pid>
# Expects the devbox layout described in run_overnight.sh.
set -u
cd "$(dirname "$0")/.."
PY=.venv/bin/python
MAIN_PID=${1:?usage: after_main.sh <main training pid>}
BASE=out/trip/baselines_5000

while kill -0 "$MAIN_PID" 2>/dev/null; do sleep 30; done
echo "$(date -u +%FT%TZ) main run finished" >> out/trip/queue.log
$PY trip/report.py --out out/trip/report \
  --model "persistence=$BASE/persistence_test.npz" \
  --model "key history=$BASE/key_history_test.npz" \
  --model "xgboost=$BASE/xgboost_test.npz" \
  --model "tslm soft+crps=out/trip/tslm_soft_crps/tslm_test.npz" > out/trip/report.log 2>&1
echo "$(date -u +%FT%TZ) done" >> out/trip/queue.log
