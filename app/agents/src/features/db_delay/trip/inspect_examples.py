"""Summaries of the built examples, to sanity-check the data before training."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

import prompts  # noqa: E402


def main(path: str) -> None:
    """Print counts, distributions, NaN columns and one rendered prompt."""
    df = pd.read_parquet(path)
    running = df[~df["pre_departure"]]
    ok = df[~df["cancelled"]]
    print("examples per split and class:\n", df.groupby(["split", "cls"]).size().unstack(), "\n")
    print("history level share per class:\n", pd.crosstab(df["cls"], df["hist_level"], normalize="index").round(3), "\n")
    print("cancel rate per class:\n", df.groupby("cls")["cancelled"].mean().round(4), "\n")
    print("target quantiles per class (not cancelled):\n",
          ok.groupby("cls")["target_minutes"].quantile([0.5, 0.75, 0.9, 0.99]).unstack(), "\n")
    print("pre-departure share:", round(float(df["pre_departure"].mean()), 3))
    print("lead minutes quantiles:", df["lead_minutes"].quantile([0.01, 0.1, 0.5, 0.9, 0.99]).round(1).to_dict())
    print("negative lead share:", round(float((df["lead_minutes"] < 0).mean()), 4))
    print("stops ahead quantiles:", df["stops_ahead"].quantile([0.1, 0.5, 0.9]).to_dict())
    print("run length quantiles (running):", running["run_len"].quantile([0.1, 0.5, 0.9]).to_dict())
    both = running[~running["cancelled"]]
    print("corr(current delay, target) while running:", round(float(np.corrcoef(both["current_delay"], both["target_minutes"])[0, 1]), 3))
    numeric = df.select_dtypes("number")
    print("numeric columns with NaN:", {c: int(numeric[c].isna().sum()) for c in numeric.columns if numeric[c].isna().any()})
    print("prediction moment range per split:\n", df.groupby("split")["t0"].agg(["min", "max"]), "\n")
    print("mean late shares: station 3h", round(float(df["station_late_3h"].mean()), 3),
          "network 3h", round(float(df["network_late_3h"].mean()), 3))
    series = np.stack(df["station_series"].to_numpy())
    print("station series finite:", bool(np.isfinite(series).all()), "max", float(series.max()))

    row = df[(df["split"] == "test") & (~df["pre_departure"]) & (df["cls"] == "long-distance")].iloc[0]
    sample = prompts.sample(row)
    print("\n--- rendered sample ---")
    print(sample["pre_prompt"])
    for text, values in zip(sample["time_series_text"], sample["time_series"]):
        print(f"{text} [{len(values)} values] {np.round(values[:6], 2).tolist()}")
    print(sample["post_prompt"])
    print(sample["answer"])


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/trip/examples.parquet")
