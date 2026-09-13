"""Show what a trained db-route model actually says: prompt, generated text, truth, for held-out rows.

Runs on one GPU with the same staging as train_route.py; loads a checkpoint written by it
(``--checkpoint``, default the quarter run in the bucket) and generates for a handful of rows from
one split cell. Prints everything to the job log so a reader can judge the rationale, the answer
format and the minute distribution side by side.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import numpy as np

OUT = Path(os.environ.get("NEBIUS_OUTPUT_DIR", "/outputs"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="quarter")
    ap.add_argument("--checkpoint", default=str(OUT / "runs" / "route-2k" / "quarter" / "checkpoint.pt"))
    ap.add_argument("--registry", default=str(OUT / "registry"))
    ap.add_argument("--cell", default="test")
    ap.add_argument("--per-kind", type=int, default=6)
    ap.add_argument("--max-new-tokens", type=int, default=96)
    args = ap.parse_args()

    sys.path.insert(0, str(Path(__file__).parent))
    import train_route as T  # noqa: PLC0415

    T.stage(0, OUT / "code" / "db_route.tar.gz")
    import torch  # noqa: PLC0415
    import torch.nn.functional as F  # noqa: PLC0415
    from opentslm.model_config import PATCH_SIZE  # noqa: PLC0415
    from opentslm.time_series_datasets.util import extend_time_series_to_match_patch_size_and_aggregate  # noqa: PLC0415
    from timenet.client import TimeNet  # noqa: PLC0415

    import bridge  # noqa: PLC0415
    import metrics  # noqa: PLC0415
    from model import START_CHECKPOINT, TripTSLM  # noqa: PLC0415

    dataset = TimeNet(args.registry).load(f"error404/db-route-{args.profile}")
    rows = [r for r in T.build_rows(dataset, bridge) if r["cell"] == args.cell]
    rng = np.random.default_rng(0)
    picked = []
    for kind in ("ScalarPredictionTask", "ClassificationTask", "AnswerTask"):
        pool = [r for r in rows if r["kind"] == kind]
        picked += [pool[i] for i in sorted(rng.choice(len(pool), min(args.per_kind, len(pool)), replace=False))]

    RouteTSLM = T.make_model_class(TripTSLM, torch, F)
    model = RouteTSLM.from_opentslm_checkpoint(START_CHECKPOINT, loss_mode="plain_crps", device="cuda")
    if not model.lora_enabled:
        model.enable_lora()
    model.load_from_file(args.checkpoint)
    model.eval()

    def collate(batch):
        return extend_time_series_to_match_patch_size_and_aggregate([T.strip(s) for s in batch], patch_size=PATCH_SIZE)

    print("=" * 100, flush=True)
    with torch.no_grad():
        for i in range(0, len(picked), 4):
            chunk = picked[i:i + 4]
            texts = model.generate_answers(collate(chunk), max_new_tokens=args.max_new_tokens)
            dist = None
            if all(r["kind"] == "ScalarPredictionTask" for r in chunk):
                dist = model.predict_distribution(collate(chunk))["probs"].float().cpu().numpy()
            for j, (r, text) in enumerate(zip(chunk, texts)):
                head = r["pre_prompt"].split("\n")[1] if "\n" in r["pre_prompt"] else r["pre_prompt"][:200]
                print(f"[{r['kind']}]  record {r['record_id']}  ({len(r['time_series'])} series)")
                print(f"  QUESTION : {head.strip()}")
                if r["post_prompt"].startswith("Possible answers"):
                    print(f"  OPTIONS  : {r['post_prompt'].split(chr(10))[0]}")
                print(f"  MODEL    : {text.strip()!r}")
                print(f"  TRUTH    : {r['answer'].strip()!r}")
                if dist is not None:
                    q = metrics.quantiles_from_distribution(dist[j:j + 1])[0]
                    print(f"  DISTRIB  : median {q[9]:.0f} min, 10-90% range {q[1]:.0f}-{q[17]:.0f} min, P(>=5 min late) {dist[j][5:].sum() / dist[j].sum():.0%}   (true {r['y']:.1f} min)")
                print("-" * 100, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
