"""Post-hoc improvements fitted on validation only, then scored on test.

1. Recalibrate the TSLM's P(cancelled) with Platt scaling: sigmoid(a * logit(p) + b).
2. Blend TSLM and XGBoost: average their quantile functions with weight w, and their
   P(late) and P(cancelled) with the same kind of weight, each chosen by validation score.

    python trip/combine.py --run out/trip/eval_step5000
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

import metrics

COLUMNS = ["example_id", "split", "target_minutes", "cancelled", "lead_minutes", "cls", "pre_departure"]
WEIGHTS = np.round(np.arange(0.0, 1.01, 0.05), 2)
EPS = 1e-4


def load(path: Path) -> dict[str, np.ndarray]:
    """Saved predictions without the (large) full distributions."""
    with np.load(path) as data:
        return {key: data[key] for key in data.files if key != "probs"}


def aligned(pred: dict[str, np.ndarray], ids: np.ndarray) -> dict[str, np.ndarray]:
    """Arrays reordered to the given example ids."""
    order = pd.Series(np.arange(len(pred["example_id"])), index=pred["example_id"]).loc[ids].to_numpy()
    return {key: value[order] for key, value in pred.items() if key != "example_id"}


def log_loss(p: np.ndarray, y: np.ndarray) -> float:
    """Binary log loss with clipping."""
    p = np.clip(p, EPS, 1 - EPS)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())


def platt(p: np.ndarray, a: float, b: float) -> np.ndarray:
    """sigmoid(a * logit(p) + b)."""
    p = np.clip(p, EPS, 1 - EPS)
    return 1 / (1 + np.exp(-(a * np.log(p / (1 - p)) + b)))


def fit_platt(p: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Grid search for the Platt parameters with the lowest log loss."""
    grid = [(a, b) for a in np.arange(0.25, 3.01, 0.05) for b in np.arange(-3.0, 3.01, 0.1)]
    return min(grid, key=lambda ab: log_loss(platt(p, *ab), y))


def split_data(run: Path, baselines: Path, examples: pd.DataFrame, split: str):
    """TSLM and XGBoost predictions on the examples both scored, with their rows."""
    tslm = load(run / f"tslm_{split}.npz")
    xgb = load(baselines / f"xgboost_{split}.npz")
    ids = np.array(sorted(set(tslm["example_id"].tolist()) & set(xgb["example_id"].tolist())))
    frame = examples.set_index("example_id").loc[ids].reset_index()
    return aligned(tslm, ids), aligned(xgb, ids), frame


def blend(tslm: dict, xgb: dict, w: float, wc: float, cancel: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Quantile average with weight w on the TSLM; P(cancelled) average with weight wc."""
    q = np.sort(w * tslm["quantiles"] + (1 - w) * xgb["quantiles"], axis=1)
    p_late = w * tslm["p_late"] + (1 - w) * xgb["p_late"]
    p_cancel = wc * cancel + (1 - wc) * xgb["p_cancel"]
    return q, p_late, p_cancel


def main() -> None:
    """Fit on validation, report test, save the blended predictions."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, help="directory with tslm_validation.npz and tslm_test.npz")
    parser.add_argument("--baselines", default="out/trip/baselines_5000")
    parser.add_argument("--examples", default="data/trip/examples.parquet")
    args = parser.parse_args()

    run, baselines = Path(args.run), Path(args.baselines)
    examples = pd.read_parquet(args.examples, columns=COLUMNS)
    v_tslm, v_xgb, v_frame = split_data(run, baselines, examples, "validation")
    v_runs = ~v_frame["cancelled"].to_numpy(dtype=bool)
    v_y = np.nan_to_num(v_frame["target_minutes"].to_numpy(dtype=np.float64))
    v_cancel = v_frame["cancelled"].to_numpy(dtype=np.float64)

    a, b = fit_platt(v_tslm["p_cancel"], v_cancel)
    v_cal = platt(v_tslm["p_cancel"], a, b)

    def val_crps(w: float) -> float:
        q = np.sort(w * v_tslm["quantiles"] + (1 - w) * v_xgb["quantiles"], axis=1)
        return float(metrics.crps_from_quantiles(v_y[v_runs], q[v_runs]).mean())

    w = min(WEIGHTS, key=val_crps)
    wc = min(WEIGHTS, key=lambda c: log_loss(c * v_cal + (1 - c) * v_xgb["p_cancel"], v_cancel))
    fitted = {"platt_a": round(float(a), 3), "platt_b": round(float(b), 3), "quantile_weight_tslm": float(w),
              "cancel_weight_tslm": float(wc), "validation_crps_by_weight": {float(k): round(val_crps(k), 4) for k in WEIGHTS}}
    print("fitted on validation:", {k: v for k, v in fitted.items() if k != "validation_crps_by_weight"})

    t_tslm, t_xgb, t_frame = split_data(run, baselines, examples, "test")
    t_cal = platt(t_tslm["p_cancel"], a, b)
    q, p_late, p_cancel = blend(t_tslm, t_xgb, w, wc, t_cal)
    results = {
        "xgboost": metrics.evaluate(t_frame, t_xgb["quantiles"], t_xgb["p_cancel"], t_xgb["p_late"]),
        "tslm": metrics.evaluate(t_frame, t_tslm["quantiles"], t_tslm["p_cancel"], t_tslm["p_late"]),
        "tslm, cancel recalibrated": metrics.evaluate(t_frame, t_tslm["quantiles"], t_cal, t_tslm["p_late"]),
        f"blend (w={w}, cancel w={wc})": metrics.evaluate(t_frame, q, p_cancel, p_late),
    }
    np.savez_compressed(run / "blend_test.npz", example_id=t_frame["example_id"].to_numpy(), quantiles=q,
                        p_cancel=p_cancel, p_late=p_late)
    (run / "combine.json").write_text(json.dumps({"fitted": fitted, "test": results}, indent=2))
    for group in ("overall", "lead <=15 min", "lead 30-60 min", "before departure", "long-distance"):
        print(f"\n## test, {group}\n" + metrics.to_markdown(results, group))


if __name__ == "__main__":
    main()
