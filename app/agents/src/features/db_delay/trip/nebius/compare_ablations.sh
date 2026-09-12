#!/usr/bin/env bash
# Pull the H100 ablation results from the bucket to this machine, copy them to the GPU box, and
# score every model on the validation and test examples they share. Run from the repo, where the
# root .env holds the bucket key; the key never leaves this machine.
#
#   bash compare_ablations.sh <ssh host> <remote project dir> [run tag prefix] [eval dir]
#   e.g. bash compare_ablations.sh devbox Jonas/db_delay_tslm h100b- out/trip/eval_step5000
set -euo pipefail

HOST=${1:?usage: compare_ablations.sh <ssh host> <remote project dir> [run tag prefix] [eval dir]}
REMOTE=${2:?usage: compare_ablations.sh <ssh host> <remote project dir> [run tag prefix] [eval dir]}
PREFIX=${3:-h100b-}
EVAL=${4:-out/trip/eval_step5000}
HERE="$(cd "$(dirname "$0")" && pwd)"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

RUNS=(text_only plain_ce ecg_sp_start random_encoder)
for run in "${RUNS[@]}"; do
  bash "$HERE/sync_bucket.sh" results "$PREFIX$run" "$STAGE/$run" > /dev/null || echo "no results yet for $run"
done
rsync -az "$STAGE/" "$HOST:$REMOTE/out/trip/ablations/"

ssh "$HOST" "cd $REMOTE && for split in validation test; do
  models=(--model \"persistence=out/trip/baselines_5000/persistence_\$split.npz\"
          --model \"key history=out/trip/baselines_5000/key_history_\$split.npz\"
          --model \"xgboost=out/trip/baselines_5000/xgboost_\$split.npz\"
          --model \"tslm main step 5000=$EVAL/tslm_\$split.npz\")
  for run in ${RUNS[*]}; do
    f=out/trip/ablations/\$run/\$run/tslm_\$split.npz
    [ -f \"\$f\" ] && models+=(--model \"ablation \$run=\$f\")
  done
  .venv/bin/python trip/report.py --split \$split --out out/trip/ablations/report \"\${models[@]}\" > /dev/null
  echo \"=== \$split\"
  awk '/^## overall/{f=1; next} /^## /{f=0} f' out/trip/ablations/report/\${split}_report.md
done"
