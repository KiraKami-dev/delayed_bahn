"""Paired bootstrap: is model A really better than model B on the same examples?

Resamples example ids with replacement and reports the mean difference (A minus B) in CRPS and
median error with a 95% interval. An interval that excludes zero is a difference the test set
supports; one that straddles zero is not. Cancelled examples are excluded, as in the metrics.

    python trip/bootstrap.py --a "blend=out/trip/eval_step5000/blend_test.npz" \
        --b "xgboost=out/trip/baselines_5000/xgboost_test.npz"
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import metrics

RESAMPLES = 2000


def load(spec: str) -> tuple[str, pd.DataFrame, np.ndarray]:
    """Name, example ids with their row numbers, and quantiles from a ``name=path.npz`` argument."""
    name, path = spec.split("=", 1)
    with np.load(path) as data:
        frame = pd.DataFrame({"example_id": data["example_id"]})
        quantiles = data["quantiles"]
    return name, frame.assign(row=np.arange(len(frame))), quantiles


def main() -> None:
    """Print the bootstrap intervals of A minus B."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--a", required=True, help="name=path.npz of the candidate")
    parser.add_argument("--b", required=True, help="name=path.npz of the reference")
    parser.add_argument("--examples", default="data/trip/examples.parquet")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    name_a, ids_a, q_a = load(args.a)
    name_b, ids_b, q_b = load(args.b)
    shared = ids_a.merge(ids_b, on="example_id", suffixes=("_a", "_b"))
    examples = pd.read_parquet(args.examples, columns=["example_id", "target_minutes", "cancelled"])
    shared = shared.merge(examples, on="example_id")
    shared = shared[~shared["cancelled"]]
    y = shared["target_minutes"].to_numpy(dtype=np.float64)
    qa, qb = q_a[shared["row_a"].to_numpy()], q_b[shared["row_b"].to_numpy()]

    diffs = {
        "crps": metrics.crps_from_quantiles(y, qa) - metrics.crps_from_quantiles(y, qb),
        "mae_median": np.abs(y - qa[:, metrics.MEDIAN]) - np.abs(y - qb[:, metrics.MEDIAN]),
    }
    rng = np.random.default_rng(args.seed)
    draws = rng.integers(0, len(y), size=(RESAMPLES, len(y)))
    print(f"{name_a} minus {name_b} on {len(y)} shared examples that ran ({RESAMPLES} resamples):")
    for metric, d in diffs.items():
        means = d[draws].mean(axis=1)
        low, high = np.percentile(means, [2.5, 97.5])
        verdict = "better" if high < 0 else "worse" if low > 0 else "no clear difference"
        print(f"  {metric}: {d.mean():+.4f} (95% interval {low:+.4f} to {high:+.4f}) -> {name_a} {verdict}")


if __name__ == "__main__":
    main()
