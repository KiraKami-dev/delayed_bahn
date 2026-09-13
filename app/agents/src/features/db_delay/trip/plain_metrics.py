"""Errors in minutes that an audience reads at a glance, for several models on the same examples.

CRPS scores the whole distribution but means little outside forecasting. This reports, for the
predicted median of each model: the average and the typical (median) miss in minutes, the share of
trains predicted within 1, 2 and 5 minutes, the bias (positive: predicted too late) with the spread
of the error, and how often the true delay falls inside the 10 to 90% range (80% is honest).
Only examples every model scored are used; cancelled trains are left out, as in the metrics.

    python trip/plain_metrics.py --examples data/trip/examples_v7.parquet \
        --model "XGBoost=out/trip/baselines_v7/xgboost_test.npz" \
        --model "TSLM=out/trip/ablations/v7-text/tslm_test.npz" --by cls
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import metrics

LOW, HIGH = 1, 17  # the 10% and 90% levels among the 19 quantiles
LEADS = [(0, 15, "up to 15 min"), (15, 30, "15 to 30 min"), (30, 60, "30 to 60 min"),
         (60, 120, "1 to 2 h"), (120, np.inf, "over 2 h")]


def load(spec: str) -> tuple[str, pd.Series, np.ndarray]:
    """Name, example ids and quantiles from a ``name=path.npz`` argument."""
    name, path = spec.split("=", 1)
    with np.load(path) as data:
        return name, pd.Series(data["example_id"]), data["quantiles"]


def summary(y: np.ndarray, q: np.ndarray) -> dict[str, float]:
    """Plain error figures of one model on one group of examples."""
    error = q[:, metrics.MEDIAN] - y
    miss = np.abs(error)
    return {
        "average miss (min)": miss.mean(),
        "typical miss (min)": np.median(miss),
        "within 1 min": (miss <= 1).mean(),
        "within 2 min": (miss <= 2).mean(),
        "within 5 min": (miss <= 5).mean(),
        "bias (min)": error.mean(),
        "spread (min)": error.std(),
        "in 10-90% range": ((y >= q[:, LOW]) & (y <= q[:, HIGH])).mean(),
    }


def table(title: str, y: np.ndarray, models: dict[str, np.ndarray]) -> str:
    """One markdown table: a row per model, a column per figure."""
    rows = {name: summary(y, q) for name, q in models.items()}
    columns = list(next(iter(rows.values())))
    lines = [f"### {title} ({len(y):,} trains)", "", "| Model | " + " | ".join(columns) + " |",
             "|---|" + "---|" * len(columns)]
    for name, row in rows.items():
        cells = [f"{100 * v:.0f}%" if c.startswith(("within", "in ")) else f"{v:+.2f}" if c.startswith("bias")
                 else f"{v:.2f}" for c, v in row.items()]
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def main() -> None:
    """Print the tables: overall, by lead time, and optionally by train class."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", action="append", required=True, help="name=path.npz, repeatable")
    parser.add_argument("--examples", default="data/trip/examples.parquet")
    parser.add_argument("--by", choices=["lead", "cls"], action="append", default=None,
                        help="extra breakdowns; lead time is always included")
    args = parser.parse_args()

    loaded = [load(spec) for spec in args.model]
    shared = set(loaded[0][1])
    for _, ids, _ in loaded[1:]:
        shared &= set(ids)
    frame = pd.read_parquet(args.examples, columns=["example_id", "target_minutes", "cancelled", "lead_minutes", "cls"])
    frame = frame[frame["example_id"].isin(shared) & ~frame["cancelled"]].reset_index(drop=True)
    y = frame["target_minutes"].to_numpy(dtype=np.float64)
    models = {}
    for name, ids, quantiles in loaded:
        row_of = pd.Series(np.arange(len(ids)), index=ids.to_numpy())
        models[name] = quantiles[row_of.loc[frame["example_id"]].to_numpy()]

    print(table("All trains", y, models))
    for low, high, label in LEADS:
        keep = ((frame["lead_minutes"] > low) | (low == 0)) & (frame["lead_minutes"] <= high)
        if keep.any():
            print(table(f"Planned arrival {label} away", y[keep], {n: q[keep.to_numpy()] for n, q in models.items()}))
    if args.by and "cls" in args.by:
        for cls, group in frame.groupby("cls"):
            keep = frame["cls"].eq(cls).to_numpy()
            print(table(f"{cls} trains", y[keep], {n: q[keep] for n, q in models.items()}))


if __name__ == "__main__":
    main()
