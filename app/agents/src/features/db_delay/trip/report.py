"""Score every model on exactly the same examples and write one comparison report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

import metrics

COLUMNS = ["example_id", "split", "target_minutes", "cancelled", "lead_minutes", "cls", "pre_departure"]


def load_predictions(path: str) -> dict[str, np.ndarray]:
    """Arrays saved by the baselines or the training script."""
    with np.load(path) as data:
        return {key: data[key] for key in data.files if key != "probs"}


def main() -> None:
    """Intersect example ids across models, score them, write JSON and Markdown."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--examples", default="data/trip/examples.parquet")
    parser.add_argument("--split", default="test")
    parser.add_argument("--model", action="append", required=True, help="name=path/to/predictions.npz")
    parser.add_argument("--out", default="out/trip/report")
    args = parser.parse_args()

    frame = pd.read_parquet(args.examples, columns=COLUMNS)
    frame = frame[frame["split"] == args.split].set_index("example_id")
    predictions = {}
    for spec in args.model:
        name, path = spec.split("=", 1)
        if Path(path).exists():
            predictions[name] = load_predictions(path)
        else:
            print(f"skipping {name}: {path} does not exist")
    common = sorted(set.intersection(*[set(p["example_id"].tolist()) for p in predictions.values()]))
    ids = np.array(common)
    subset = frame.loc[ids].reset_index()
    print(f"scoring {len(predictions)} models on {len(ids)} shared {args.split} examples")

    results = {}
    for name, pred in predictions.items():
        order = pd.Series(np.arange(len(pred["example_id"])), index=pred["example_id"]).loc[ids].to_numpy()
        p_late = pred["p_late"][order]
        results[name] = metrics.evaluate(subset, pred["quantiles"][order], pred["p_cancel"][order],
                                         None if np.isnan(p_late).all() else p_late)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{args.split}_metrics.json").write_text(json.dumps(results, indent=2))
    groups = list(next(iter(results.values())).keys())
    sections = [f"# Trip delay: {args.split} split, {len(ids)} shared examples\n",
                "Lower is better except coverage, which should be close to 0.80.\n"]
    for group in groups:
        sections.append(f"## {group}\n\n{metrics.to_markdown(results, group)}\n")
    (out_dir / f"{args.split}_report.md").write_text("\n".join(sections))
    print("\n".join(sections[:4]))


if __name__ == "__main__":
    main()
