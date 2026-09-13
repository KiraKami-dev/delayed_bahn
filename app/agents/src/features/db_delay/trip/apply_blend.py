"""Apply blend weights fitted elsewhere to another set of predictions, e.g. the forward test.

The weights come from a combine.json written by combine.py on the validation split of the
training data; nothing is fitted here, so the forward examples stay untouched by fitting.

    python trip/apply_blend.py --weights out/trip/ablations/text_plain/combine.json \\
        --tslm out/trip/forward_text-plain/tslm_test.npz --xgb out/trip/baselines_forward/xgboost_forward.npz \\
        --examples data/trip/forward.parquet --out out/trip/forward_text-plain/blend_lead_test.npz
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from combine import aligned, blend, lead_weights, load, platt


def main() -> None:
    """Blend and save."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--weights", required=True, help="combine.json with the fitted weights")
    parser.add_argument("--tslm", required=True)
    parser.add_argument("--xgb", required=True)
    parser.add_argument("--examples", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    fitted = json.loads(Path(args.weights).read_text())["fitted"]
    tslm, xgb = load(Path(args.tslm)), load(Path(args.xgb))
    ids = np.array(sorted(set(tslm["example_id"].tolist()) & set(xgb["example_id"].tolist())))
    frame = pd.read_parquet(args.examples, columns=["example_id", "lead_minutes"]).set_index("example_id").loc[ids].reset_index()
    tslm, xgb = aligned(tslm, ids), aligned(xgb, ids)
    cancel = platt(tslm["p_cancel"], fitted["platt_a"], fitted["platt_b"])
    q, p_late, p_cancel = blend(tslm, xgb, lead_weights(frame, fitted["quantile_weight_tslm_by_lead"]),
                                fitted["cancel_weight_tslm"], cancel)
    np.savez_compressed(args.out, example_id=ids, quantiles=q, p_cancel=p_cancel, p_late=p_late)
    print(f"blended {len(ids)} examples with weights {fitted['quantile_weight_tslm_by_lead']} -> {args.out}")


if __name__ == "__main__":
    main()
