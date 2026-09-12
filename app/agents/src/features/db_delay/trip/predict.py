"""Replay the traveller output for recorded trips: typical delay, likely range, chance of being on time.

Give one or more example ids from a built examples file. With exactly two ids, the first is read
as the arriving train and the second as the connecting train at the change station, and the
chance of making the change is added. The connecting train's departure delay is approximated by
its predicted arrival delay at that stop.

    python trip/predict.py --checkpoint out/trip/tslm_soft_crps/checkpoint.pt --example-ids 123 456
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

import metrics  # noqa: E402
import prompts  # noqa: E402
from connection import TrainForecast, change_probability  # noqa: E402
from model import START_CHECKPOINT, TripTSLM  # noqa: E402
from train import collate  # noqa: E402


def summary(row: pd.Series, probs: np.ndarray, p_cancel: float) -> dict:
    """The traveller view of one forecast, next to what actually happened."""
    q = metrics.quantiles_from_distribution(probs[None])[0]
    on_time = float(np.cumsum(probs)[metrics.LATE_MINUTES - 1]) * (1 - p_cancel)
    median, low, high = int(q[metrics.MEDIAN]), int(q[metrics.LOW]), int(q[metrics.HIGH])
    return {
        "example_id": int(row["example_id"]),
        "train": prompts.train_label(row),
        "target_stop": prompts.name(row["k_station"]),
        "planned_arrival": str(row["k_arr_pt"]),
        "headline": f"about +{median} min, likely {low} to {high} min, {on_time:.0%} chance of arriving on time",
        "typical_delay_minutes": median,
        "likely_range_minutes": [low, high],
        "p_on_time": round(on_time, 3),
        "p_cancelled": round(float(p_cancel), 3),
        "rationale": prompts.rationale(row),
        "actual": prompts.target_text(row),
    }


def main() -> None:
    """Load a trained checkpoint, forecast the chosen examples, print JSON."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--examples", default="data/trip/examples.parquet")
    parser.add_argument("--checkpoint", required=True, help="checkpoint.pt written by train.py")
    parser.add_argument("--start-checkpoint", default=START_CHECKPOINT)
    parser.add_argument("--example-ids", type=int, nargs="+", required=True)
    parser.add_argument("--buffer", type=float, default=8.0, help="planned minutes between the two trains")
    parser.add_argument("--min-transfer", type=float, default=5.0, help="minutes needed to change")
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()

    frame = pd.read_parquet(args.examples)
    rows = frame.set_index("example_id").loc[args.example_ids].reset_index()
    model = TripTSLM.from_opentslm_checkpoint(args.start_checkpoint, device=args.device)
    if not model.lora_enabled:
        model.enable_lora()
    model.load_from_file(args.checkpoint)
    model.eval()

    out = model.predict_distribution(collate([prompts.sample(row) for _, row in rows.iterrows()]))
    probs = out["probs"].float().cpu().numpy()
    p_cancel = out["p_cancel"].float().cpu().numpy()
    result = {"forecasts": [summary(row, probs[i], float(p_cancel[i])) for i, (_, row) in enumerate(rows.iterrows())]}
    if len(rows) == 2:
        arriving = TrainForecast(probs[0], float(p_cancel[0]))
        departing = TrainForecast(probs[1], float(p_cancel[1]))
        p_change = change_probability(arriving, departing, args.buffer, args.min_transfer)
        result["change"] = {"planned_buffer_minutes": args.buffer, "min_transfer_minutes": args.min_transfer,
                            "p_change_works": round(p_change, 3),
                            "headline": f"{p_change:.0%} chance of making the change"}
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
