"""A minimal OpenTSLM fine-tune on the rail delay dataset, with baselines.

Trains the time-series encoder and projector while the language model stays
frozen, then scores the four leakage cells against baselines that see the same
numbers. The point is a working end-to-end run, not a competitive result.
"""

from __future__ import annotations

import argparse
import json
import pickle
import re
import statistics
import time
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from opentslm.model.llm.OpenTSLMSP import OpenTSLMSP
from opentslm.model_config import PATCH_SIZE
from opentslm.time_series_datasets.util import (
    extend_time_series_to_match_patch_size_and_aggregate,
)
from torch.utils.data import DataLoader

from timef_bridge import TimeFQADataset

ANSWER_RE = re.compile(r"Answer:\s*([-\w.]+)")


def make_dataset(rows: list[dict], eos: str, name: str):
    """Wrap one bucket of rows as an OpenTSLM dataset under a fresh class."""
    namespace = {"SPLITS": {"train": rows, "validation": rows, "test": rows}}
    return type(name, (TimeFQADataset,), namespace)("train", EOS_TOKEN=eos)


def collate(batch):
    """Pad every series up to a whole number of patches."""
    return extend_time_series_to_match_patch_size_and_aggregate(batch, patch_size=PATCH_SIZE)


def parse_answer(text: str) -> str | None:
    """Pull the answer token out of a generated rationale."""
    match = ANSWER_RE.search(text or "")
    return match.group(1) if match else None


def score(rows: list[dict], predictions: list[str | None]) -> dict:
    """Score predictions per task type, alongside a baseline that sees the same series."""
    abs_err, base_err, cls_hits, cls_base_hits, cls_n = [], [], 0, 0, 0
    majority = Counter(
        str(r["target"]) for r in rows if r["task_type"] == "ClassificationTask"
    ).most_common(1)
    majority_label = majority[0][0] if majority else None
    for row, predicted in zip(rows, predictions, strict=True):
        if row["task_type"] == "ScalarPredictionTask":
            context_mean = float(np.asarray(row["series"][0][1]).mean())
            base_err.append(abs(context_mean - float(row["target"])))
            try:
                abs_err.append(abs(float(predicted) - float(row["target"])))
            except (TypeError, ValueError):
                abs_err.append(abs(float(row["target"])))  # unparseable counts as predicting zero
        else:
            cls_n += 1
            cls_hits += int(str(predicted) == str(row["target"]))
            cls_base_hits += int(majority_label == str(row["target"]))
    out: dict = {"n": len(rows)}
    if abs_err:
        out |= {
            "forecast_mae": round(statistics.fmean(abs_err), 3),
            "forecast_median_ae": round(statistics.median(abs_err), 3),
            "baseline_mae": round(statistics.fmean(base_err), 3),
            "baseline_median_ae": round(statistics.median(base_err), 3),
        }
    if cls_n:
        out |= {
            "class_accuracy": round(cls_hits / cls_n, 3),
            "majority_baseline": round(cls_base_hits / cls_n, 3),
            "class_n": cls_n,
        }
    return out


@torch.no_grad()
def evaluate(model, rows: list[dict], eos: str, limit: int, batch_size: int, max_new_tokens: int = 120) -> tuple[dict, list]:
    """Generate on a capped sample of rows and score it."""
    sample = rows[:limit]
    if not sample:
        return {"n": 0}, []
    loader = DataLoader(
        make_dataset(sample, eos, "EvalSet"), batch_size=batch_size, shuffle=False, collate_fn=collate
    )
    generated: list[str] = []
    for batch in loader:
        generated.extend(model.generate(batch, max_new_tokens=max_new_tokens))
    predictions = [parse_answer(text) for text in generated]
    records = [
        {"target": str(r["target"]), "predicted": p, "task": r["task_type"], "output": g[:300]}
        for r, p, g in zip(sample, predictions, generated, strict=True)
    ]
    return score(sample, predictions), records


def main() -> None:
    """Run the fine-tune and write metrics, predictions and a checkpoint."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/splits.pkl")
    parser.add_argument("--out", default="out")
    parser.add_argument("--llm-id", default="google/gemma-3-270m")
    parser.add_argument("--max-steps", type=int, default=400)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--eval-batch-size", type=int, default=8)
    parser.add_argument("--eval-limit", type=int, default=96)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--lora", action="store_true", help="also adapt the language model")
    parser.add_argument("--max-new-tokens", type=int, default=120)
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(args.data, "rb") as handle:
        prepared = pickle.load(handle)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"device={device} llm={args.llm_id}", flush=True)
    model = OpenTSLMSP(llm_id=args.llm_id, device=device)
    if args.lora:
        # Without this the language model is frozen and never learns the answer
        # format, so it emits fluent text that no scorer can parse.
        model.enable_lora()
    eos = model.get_eos_token()

    train_rows = prepared["buckets"]["train"]
    train_loader = DataLoader(
        make_dataset(train_rows, eos, "TrainSet"),
        batch_size=args.batch_size,
        shuffle=True,
        collate_fn=collate,
    )
    trainable = [p for p in model.parameters() if p.requires_grad]
    print(f"trainable params: {sum(p.numel() for p in trainable):,}", flush=True)
    optimizer = torch.optim.AdamW(trainable, lr=args.lr, weight_decay=1e-2)

    print("--- before training ---", flush=True)
    before, _ = evaluate(model, prepared["cells"]["unseen_late"], eos, args.eval_limit, args.eval_batch_size, args.max_new_tokens)
    print(json.dumps(before), flush=True)

    model.train()
    started, step, losses = time.time(), 0, []
    while step < args.max_steps:
        for batch in train_loader:
            loss = model.compute_loss(batch)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(trainable, 1.0)
            optimizer.step()
            optimizer.zero_grad(set_to_none=True)
            losses.append(float(loss))
            step += 1
            if step % 25 == 0:
                print(f"step {step}/{args.max_steps} loss {statistics.fmean(losses[-25:]):.4f} "
                      f"({time.time() - started:.0f}s)", flush=True)
            if step >= args.max_steps:
                break
    train_seconds = time.time() - started
    model.eval()

    results = {
        "llm_id": args.llm_id,
        "lora": args.lora,
        "steps": step,
        "train_seconds": round(train_seconds, 1),
        "final_loss": round(statistics.fmean(losses[-25:]), 4),
        "held_out_stations": prepared["holdout"],
        "before_training_unseen_late": before,
        "cells": {},
    }
    for name, rows in prepared["cells"].items():
        metrics, records = evaluate(model, rows, eos, args.eval_limit, args.eval_batch_size, args.max_new_tokens)
        results["cells"][name] = metrics
        print(name, json.dumps(metrics), flush=True)
        with (out_dir / f"predictions_{name}.jsonl").open("w") as handle:
            for record in records:
                handle.write(json.dumps(record) + "\n")

    (out_dir / "metrics.json").write_text(json.dumps(results, indent=2))
    model.store_to_file(str(out_dir / "checkpoint.pt"))
    print("wrote", out_dir / "metrics.json", "and checkpoint.pt", flush=True)


if __name__ == "__main__":
    main()
