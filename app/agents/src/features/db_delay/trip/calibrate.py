"""Post-hoc temperature calibration of the TSLM minute distribution.

A temperature T reshapes the distribution as p^(1/T), renormalised: T < 1 sharpens it. T is
chosen on validation examples by CRPS and then applied, unchanged, to test predictions. No
training is involved, so this takes seconds.

    python trip/calibrate.py --run out/trip/eval_step5000
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

import metrics

COLUMNS = ["example_id", "split", "target_minutes", "cancelled", "lead_minutes", "cls", "pre_departure"]
TEMPERATURES = np.round(np.arange(0.3, 1.51, 0.05), 2)


def load(run: Path, split: str) -> dict[str, np.ndarray]:
    """Predictions saved by train.py, including the full minute distribution."""
    with np.load(run / f"tslm_{split}.npz") as data:
        return {key: data[key] for key in data.files}


def reshape(probs: np.ndarray, temperature: float) -> np.ndarray:
    """p^(1/T), renormalised; computed in log space so tiny probabilities do not underflow."""
    logp = np.log(np.clip(probs.astype(np.float64), 1e-12, None)) / temperature
    logp -= logp.max(axis=1, keepdims=True)
    out = np.exp(logp)
    return out / out.sum(axis=1, keepdims=True)


def frame_for(examples: pd.DataFrame, ids: np.ndarray) -> pd.DataFrame:
    """Example rows in the order of the saved predictions."""
    return examples.set_index("example_id").loc[ids].reset_index()


def main() -> None:
    """Fit T on validation, apply it to test, save calibrated predictions and a comparison."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, help="directory with tslm_validation.npz and tslm_test.npz")
    parser.add_argument("--examples", default="data/trip/examples.parquet")
    args = parser.parse_args()

    run = Path(args.run)
    examples = pd.read_parquet(args.examples, columns=COLUMNS)
    val, test = load(run, "validation"), load(run, "test")
    val_frame = frame_for(examples, val["example_id"])
    y = np.nan_to_num(val_frame["target_minutes"].to_numpy(dtype=np.float64))
    runs = ~val_frame["cancelled"].to_numpy(dtype=bool)

    scores = {}
    for t in TEMPERATURES:
        q = metrics.quantiles_from_distribution(reshape(val["probs"][runs], t))
        scores[float(t)] = float(metrics.crps_from_quantiles(y[runs], q).mean())
    best = min(scores, key=scores.get)
    print(f"validation CRPS by temperature (best T={best}):", {k: round(v, 3) for k, v in scores.items()})

    results = {}
    for name, pred, frame in (("validation", val, val_frame), ("test", test, frame_for(examples, test["example_id"]))):
        for label, probs in (("raw", pred["probs"].astype(np.float64)), (f"T={best}", reshape(pred["probs"], best))):
            q = metrics.quantiles_from_distribution(probs)
            results.setdefault(name, {})[f"tslm {label}"] = metrics.evaluate(frame, q, pred["p_cancel"],
                                                                           metrics.late_from_distribution(probs))
        calibrated = reshape(pred["probs"], best)
        np.savez_compressed(run / f"tslm_calibrated_{name}.npz", example_id=pred["example_id"],
                            quantiles=metrics.quantiles_from_distribution(calibrated), p_cancel=pred["p_cancel"],
                            p_late=metrics.late_from_distribution(calibrated), probs=calibrated.astype(np.float16))
    (run / "calibration.json").write_text(json.dumps({"temperature": best, "validation_crps": scores,
                                                      "results": results}, indent=2))
    for name in ("validation", "test"):
        print(f"\n## {name}\n" + metrics.to_markdown(results[name]))


if __name__ == "__main__":
    main()
