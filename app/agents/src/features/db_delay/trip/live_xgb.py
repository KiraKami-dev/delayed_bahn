"""The statistical forecast the stacked model reads, kept on disk for live examples.

baselines.py fits XGBoost on the training split and saves only its predictions, so the v7 models
that wrote the xgb_* columns no longer exist. This refits them the same way (same features,
hyper-parameters and early stopping on validation), saves the three boosters with the category
vocabulary, and adds the xgb_* columns to any frame of examples.

    python trip/live_xgb.py --examples data/trip/examples_v7.parquet --out out/trip/xgb_v7 \\
        --check data/trip/september_v7_test.parquet
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

sys.path.insert(0, str(Path(__file__).parent))

import baselines  # noqa: E402
import metrics  # noqa: E402
import stack  # noqa: E402


def fit(examples: str, out: Path, n_estimators: int) -> None:
    """Fit the quantile, late and cancellation models and save them."""
    df = pd.read_parquet(examples)
    train = df[df["split"] == "train"].reset_index(drop=True)
    val = df[df["split"] == "validation"].reset_index(drop=True)
    categories = {col: sorted(train[col].astype(str).unique()) for col in baselines.CATEGORICAL}
    x_train, x_val = baselines.features(train, categories), baselines.features(val, categories)
    ok_train, ok_val = baselines.runs_mask(train), baselines.runs_mask(val)
    y_train, y_val = train["target_minutes"], val["target_minutes"]
    common = {"tree_method": "hist", "n_estimators": n_estimators, "learning_rate": 0.05, "max_depth": 8,
              "min_child_weight": 20, "subsample": 0.8, "colsample_bytree": 0.8, "early_stopping_rounds": 50,
              "n_jobs": -1}
    started = time.time()
    quantile = xgb.XGBRegressor(objective="reg:quantileerror", quantile_alpha=metrics.LEVELS, **common)
    quantile.fit(x_train[ok_train], y_train[ok_train], eval_set=[(x_val[ok_val], y_val[ok_val])], verbose=False)
    late = xgb.XGBClassifier(objective="binary:logistic", **common)
    late.fit(x_train[ok_train], (y_train[ok_train] >= metrics.LATE_MINUTES).astype(int),
             eval_set=[(x_val[ok_val], (y_val[ok_val] >= metrics.LATE_MINUTES).astype(int))], verbose=False)
    cancel = xgb.XGBClassifier(objective="binary:logistic", **common)
    cancel.fit(x_train, train["cancelled"].astype(int), eval_set=[(x_val, val["cancelled"].astype(int))], verbose=False)
    out.mkdir(parents=True, exist_ok=True)
    quantile.save_model(out / "quantile.json")
    late.save_model(out / "late.json")
    cancel.save_model(out / "cancel.json")
    (out / "features.json").write_text(json.dumps({"categories": categories, "columns": list(x_train.columns)}, indent=1))
    print(f"fitted in {time.time() - started:.0f}s; best iterations: quantile {quantile.best_iteration}, "
          f"late {late.best_iteration}, cancel {cancel.best_iteration}", flush=True)


class Forecast:
    """The saved models, answering with the xgb_* columns."""

    def __init__(self, directory: Path):
        spec = json.loads((directory / "features.json").read_text())
        self.categories, self.columns = spec["categories"], spec["columns"]
        self.quantile = xgb.XGBRegressor()
        self.quantile.load_model(directory / "quantile.json")
        self.late, self.cancel = xgb.XGBClassifier(), xgb.XGBClassifier()
        self.late.load_model(directory / "late.json")
        self.cancel.load_model(directory / "cancel.json")

    def columns_for(self, frame: pd.DataFrame) -> pd.DataFrame:
        """xgb_median, xgb_q10, xgb_q90, xgb_p_late, xgb_p_cancel for every row."""
        x = baselines.features(frame, self.categories)[self.columns]
        q = np.sort(np.clip(self.quantile.predict(x), 0, baselines.metrics_max()), axis=1)
        values = np.column_stack([q[:, metrics.MEDIAN], q[:, metrics.LOW], q[:, metrics.HIGH],
                                  self.late.predict_proba(x)[:, 1], self.cancel.predict_proba(x)[:, 1]])
        return pd.DataFrame(values, columns=stack.COLUMNS, index=frame.index)


def main() -> None:
    """Fit and save, then compare with the xgb_* columns an examples file already carries."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--examples", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--n-estimators", type=int, default=1500)
    parser.add_argument("--check", help="an examples file with xgb_* columns to compare against")
    parser.add_argument("--skip-fit", action="store_true")
    args = parser.parse_args()

    out = Path(args.out)
    if not args.skip_fit:
        fit(args.examples, out, args.n_estimators)
    if args.check:
        frame = pd.read_parquet(args.check)
        mine = Forecast(out).columns_for(frame)
        for col in stack.COLUMNS:
            a, b = mine[col].to_numpy(), frame[col].to_numpy(dtype=np.float64)
            print(f"{col}: correlation {np.corrcoef(a, b)[0, 1]:.3f}, mean absolute difference {np.abs(a - b).mean():.3f}")


if __name__ == "__main__":
    main()
