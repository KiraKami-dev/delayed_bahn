"""Baselines for trip delay: persistence, key history and gradient-boosted quantiles.

Each baseline returns 19 quantiles of the arrival delay, P(cancelled) and
P(late), scored by :mod:`metrics` exactly like the language model.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

import metrics

NUMERIC = [
    "current_delay", "max_delay_so_far", "delay_change_3", "run_len", "lead_minutes", "stops_ahead",
    "arr_hour", "arr_weekday", "hist_n", "hist_cancel_share", "hist_median", "hist_p90", "hist_mean",
    "hist_days", "station_late_3h", "station_late_24h", "station_late_72h", "station_stops_24h",
    "network_late_3h", "network_late_24h", "network_late_72h",
]
# Columns that newer builds add; used when the frame has them, so old and new builds both score.
OPTIONAL_NUMERIC = ["prev_n", "prev_last", "prev_mean", "prev_gap_last", "hist_median_long", "hist_p90_long",
                    "hist_median_7", "station_late_same_hour", "network_late_same_hour",
                    "same_train_days", "same_train_gain_median", "same_train_gain_median_7", "same_train_expected",
                    "corridor_n", "corridor_gain_mean", "corridor_gain_last"]
CATEGORICAL = ["cls", "train_type", "hist_level"]
Prediction = tuple[np.ndarray, np.ndarray, np.ndarray | None]


def runs_mask(frame: pd.DataFrame) -> np.ndarray:
    """True where the train reached the target stop."""
    return ~frame["cancelled"].to_numpy(dtype=bool)


def lead_group(frame: pd.DataFrame) -> pd.Series:
    """Lead-time bucket crossed with before or after departure."""
    lead = pd.cut(frame["lead_minutes"], metrics.LEAD_BINS, labels=metrics.LEAD_LABELS).astype(str)
    return lead + np.where(frame["pre_departure"], " | pre", " | running")


def class_cancel_rate(train: pd.DataFrame, frame: pd.DataFrame) -> np.ndarray:
    """P(cancelled) as the training cancellation rate of the train's class."""
    rates = train.groupby("cls")["cancelled"].mean()
    return frame["cls"].map(rates).fillna(train["cancelled"].mean()).to_numpy(dtype=np.float64)


def persistence(train: pd.DataFrame, frames: dict[str, pd.DataFrame]) -> dict[str, Prediction]:
    """The current delay carries to the target, spread by training residuals per lead bucket."""
    ok = runs_mask(train)
    residual = train.loc[ok, "target_minutes"] - train.loc[ok, "current_delay"]
    groups = lead_group(train.loc[ok])
    table = residual.groupby(groups).quantile(list(metrics.LEVELS)).unstack()
    fallback = np.quantile(residual, metrics.LEVELS)
    out = {}
    for name, frame in frames.items():
        spread = table.reindex(lead_group(frame)).to_numpy(dtype=np.float64)
        spread = np.where(np.isnan(spread), fallback, spread)
        q = np.clip(frame["current_delay"].to_numpy(dtype=np.float64)[:, None] + spread, 0, metrics_max())
        out[name] = (q, class_cancel_rate(train, frame), None)
    return out


def history(train: pd.DataFrame, frames: dict[str, pd.DataFrame]) -> dict[str, Prediction]:
    """Quantiles of the key's last 30 days; the class distribution when no key has enough data."""
    ok = runs_mask(train)
    class_q = train.loc[ok].groupby("cls")["target_minutes"].quantile(list(metrics.LEVELS)).unstack()
    out = {}
    for name, frame in frames.items():
        series = np.stack(frame["hist_series"].to_numpy()).astype(np.float64)
        q = np.quantile(series, metrics.LEVELS, axis=1).T
        missing = (frame["hist_level"] == "none").to_numpy()
        q[missing] = class_q.reindex(frame.loc[missing, "cls"]).to_numpy(dtype=np.float64)
        rate = class_cancel_rate(train, frame)
        p_cancel = np.where(missing, rate, 0.5 * rate + 0.5 * frame["hist_cancel_share"].to_numpy(dtype=np.float64))
        out[name] = (q, p_cancel, None)
    return out


def metrics_max() -> int:
    """Upper clip for predicted minutes."""
    return 999


def features(frame: pd.DataFrame, categories: dict[str, list[str]]) -> pd.DataFrame:
    """Tabular features, categories encoded with the training vocabulary."""
    x = frame[NUMERIC + [c for c in OPTIONAL_NUMERIC if c in frame.columns]].astype(np.float64).copy()
    for col in CATEGORICAL:
        x[col] = pd.Categorical(frame[col], categories=categories[col]).codes
    x["pre_departure"] = frame["pre_departure"].astype(np.float64)
    return x


def gradient_boosting(train: pd.DataFrame, frames: dict[str, pd.DataFrame], n_estimators: int) -> dict[str, Prediction]:
    """XGBoost: a 19-quantile regressor, a late classifier and a cancellation classifier."""
    categories = {col: sorted(train[col].astype(str).unique()) for col in CATEGORICAL}
    val = frames["validation"]
    x_train, x_val = features(train, categories), features(val, categories)
    ok_train, ok_val = runs_mask(train), runs_mask(val)
    common = {"tree_method": "hist", "n_estimators": n_estimators, "learning_rate": 0.05, "max_depth": 8,
              "min_child_weight": 20, "subsample": 0.8, "colsample_bytree": 0.8, "early_stopping_rounds": 50,
              "n_jobs": 32}

    quantile = xgb.XGBRegressor(objective="reg:quantileerror", quantile_alpha=metrics.LEVELS, **common)
    quantile.fit(x_train[ok_train], train.loc[ok_train, "target_minutes"],
                 eval_set=[(x_val[ok_val], val.loc[ok_val, "target_minutes"])], verbose=False)
    late = xgb.XGBClassifier(objective="binary:logistic", **common)
    late.fit(x_train[ok_train], (train.loc[ok_train, "target_minutes"] >= metrics.LATE_MINUTES).astype(int),
             eval_set=[(x_val[ok_val], (val.loc[ok_val, "target_minutes"] >= metrics.LATE_MINUTES).astype(int))],
             verbose=False)
    cancel = xgb.XGBClassifier(objective="binary:logistic", **common)
    cancel.fit(x_train, train["cancelled"].astype(int), eval_set=[(x_val, val["cancelled"].astype(int))], verbose=False)
    print(f"xgboost best iterations: quantile {quantile.best_iteration}, late {late.best_iteration}, "
          f"cancel {cancel.best_iteration}", flush=True)

    out = {}
    for name, frame in frames.items():
        x = features(frame, categories)
        q = np.sort(np.clip(quantile.predict(x), 0, metrics_max()), axis=1)
        out[name] = (q, cancel.predict_proba(x)[:, 1], late.predict_proba(x)[:, 1])
    return out


def main() -> None:
    """Fit every baseline, score validation and test, write metrics and predictions."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--examples", default="data/trip/examples.parquet")
    parser.add_argument("--out", default="out/trip/baselines")
    parser.add_argument("--n-estimators", type=int, default=1500)
    parser.add_argument("--extra-examples", help="another examples file whose test split is scored as 'forward' "
                        "with the models fitted here, e.g. the September set")
    args = parser.parse_args()

    started = time.time()
    df = pd.read_parquet(args.examples)
    train = df[df["split"] == "train"].reset_index(drop=True)
    frames = {s: df[df["split"] == s].reset_index(drop=True) for s in ("validation", "test")}
    if args.extra_examples:
        extra = pd.read_parquet(args.extra_examples)
        frames["forward"] = extra[extra["split"] == "test"].reset_index(drop=True)
    print({s: len(f) for s, f in frames.items()} | {"train": len(train)}, flush=True)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict[str, dict]] = {split: {} for split in frames}
    for model, fit in (
        ("persistence", lambda: persistence(train, frames)),
        ("key history", lambda: history(train, frames)),
        ("xgboost", lambda: gradient_boosting(train, frames, args.n_estimators)),
    ):
        predictions = fit()
        for split, (q, p_cancel, p_late) in predictions.items():
            results[split][model] = metrics.evaluate(frames[split], q, p_cancel, p_late)
            np.savez_compressed(out_dir / f"{model.replace(' ', '_')}_{split}.npz", example_id=frames[split]["example_id"],
                                quantiles=q, p_cancel=p_cancel, p_late=q[:, 0] * np.nan if p_late is None else p_late)
        print(f"[{time.time() - started:5.0f}s] {model} done", flush=True)

    (out_dir / "metrics.json").write_text(json.dumps(results, indent=2))
    for split in frames:
        print(f"\n## {split}\n" + metrics.to_markdown(results[split]))


if __name__ == "__main__":
    main()
