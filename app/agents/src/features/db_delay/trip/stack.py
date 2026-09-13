"""Add the statistical forecast to the examples, so the language model can start from it.

For the training split the XGBoost forecast comes from 5-fold out-of-fold models (fitted on the
other folds), so the language model never sees a forecast that was fitted on the same trip. For
the other splits it comes from the model fitted on the whole training split, i.e. the saved
baseline predictions. The columns are xgb_median, xgb_q10, xgb_q90, xgb_p_late, xgb_p_cancel.

    python trip/stack.py --examples data/trip/examples_v3.parquet --baselines out/trip/baselines_v3 \\
        --out data/trip/examples_v4.parquet
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import xgboost as xgb

sys.path.insert(0, str(Path(__file__).parent))

import baselines  # noqa: E402
import metrics  # noqa: E402

FOLDS = 5
Q10, Q50, Q90 = metrics.LOW, metrics.MEDIAN, metrics.HIGH
COLUMNS = ["xgb_median", "xgb_q10", "xgb_q90", "xgb_p_late", "xgb_p_cancel"]


def fold_of(example_id: np.ndarray) -> np.ndarray:
    """A stable fold per example."""
    return (example_id.astype(np.int64) * 2654435761 % 2**32) % FOLDS


def out_of_fold(train: pd.DataFrame, n_estimators: dict[str, int]) -> np.ndarray:
    """Forecast columns for the training split, each fold predicted by a model that never saw it."""
    categories = {col: sorted(train[col].astype(str).unique()) for col in baselines.CATEGORICAL}
    x = baselines.features(train, categories)
    ok = baselines.runs_mask(train)
    y = train["target_minutes"].to_numpy(dtype=np.float64)
    folds = fold_of(train["example_id"].to_numpy())
    out = np.zeros((len(train), len(COLUMNS)))
    common = {"tree_method": "hist", "learning_rate": 0.05, "max_depth": 8, "min_child_weight": 20,
              "subsample": 0.8, "colsample_bytree": 0.8, "n_jobs": 40}
    for k in range(FOLDS):
        started = time.time()
        fit, hold = folds != k, folds == k
        quantile = xgb.XGBRegressor(objective="reg:quantileerror", quantile_alpha=metrics.LEVELS,
                                    n_estimators=n_estimators["quantile"], **common)
        quantile.fit(x[fit & ok], y[fit & ok])
        late = xgb.XGBClassifier(objective="binary:logistic", n_estimators=n_estimators["late"], **common)
        late.fit(x[fit & ok], (y[fit & ok] >= metrics.LATE_MINUTES).astype(int))
        cancel = xgb.XGBClassifier(objective="binary:logistic", n_estimators=n_estimators["cancel"], **common)
        cancel.fit(x[fit], train.loc[fit, "cancelled"].astype(int))
        q = np.sort(np.clip(quantile.predict(x[hold]), 0, baselines.metrics_max()), axis=1)
        out[hold, 0], out[hold, 1], out[hold, 2] = q[:, Q50], q[:, Q10], q[:, Q90]
        out[hold, 3] = late.predict_proba(x[hold])[:, 1]
        out[hold, 4] = cancel.predict_proba(x[hold])[:, 1]
        print(f"fold {k}: {hold.sum()} examples in {time.time() - started:.0f}s", flush=True)
    return out


def from_saved(frame: pd.DataFrame, path: Path) -> np.ndarray:
    """Forecast columns from a saved baseline prediction file, aligned to the frame."""
    with np.load(path) as data:
        order = pd.Series(np.arange(len(data["example_id"])), index=data["example_id"]).loc[frame["example_id"].to_numpy()].to_numpy()
        q, p_cancel, p_late = data["quantiles"][order], data["p_cancel"][order], data["p_late"][order]
    return np.column_stack([q[:, Q50], q[:, Q10], q[:, Q90], p_late, p_cancel])


def main() -> None:
    """Write the examples with the forecast columns."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--examples", required=True)
    parser.add_argument("--baselines", required=True, help="directory with xgboost_<split>.npz for the non-training splits")
    parser.add_argument("--out", required=True)
    parser.add_argument("--n-quantile", type=int, default=1500)
    parser.add_argument("--n-late", type=int, default=200)
    parser.add_argument("--n-cancel", type=int, default=250)
    parser.add_argument("--splits", nargs="*", default=["validation", "test"], help="splits with saved predictions")
    parser.add_argument("--no-oof", action="store_true", help="leave the training split without forecasts")
    args = parser.parse_args()

    frame = pd.read_parquet(args.examples)
    values = np.full((len(frame), len(COLUMNS)), np.nan)
    train = frame["split"] == "train"
    if train.any() and not args.no_oof:
        values[train.to_numpy()] = out_of_fold(frame[train].reset_index(drop=True),
                                               {"quantile": args.n_quantile, "late": args.n_late, "cancel": args.n_cancel})
    for split in args.splits:
        mask = (frame["split"] == split).to_numpy()
        if mask.any():
            values[mask] = from_saved(frame[mask], Path(args.baselines) / f"xgboost_{split}.npz")
    table = pq.read_table(args.examples)
    for i, col in enumerate(COLUMNS):
        table = table.append_column(col, pa.array(values[:, i]))
    pq.write_table(table, args.out)
    print(f"wrote {len(frame)} examples with {COLUMNS} to {args.out}; missing forecasts: {int(np.isnan(values[:, 0]).sum())}")


if __name__ == "__main__":
    main()
