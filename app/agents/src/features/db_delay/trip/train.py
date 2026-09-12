"""Fine-tune the trip TSLM from an OpenTSLM checkpoint and score it with the shared metrics."""

from __future__ import annotations

import argparse
import json
import math
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from opentslm.model_config import PATCH_SIZE
from opentslm.time_series_datasets.util import extend_time_series_to_match_patch_size_and_aggregate
from torch.utils.data import DataLoader, Dataset

import metrics
import prompts
from model import START_CHECKPOINT, TripTSLM

ANSWER_RE = re.compile(r"Answer:\s*(cancelled|\d+)")


class TripDataset(Dataset):
    """Formats examples lazily, so large splits cost no upfront time."""

    def __init__(self, frame: pd.DataFrame, mode: str = "series"):
        self.frame = frame.reset_index(drop=True)
        self.mode = mode

    def __len__(self) -> int:
        return len(self.frame)

    def __getitem__(self, index: int) -> dict:
        return prompts.sample(self.frame.iloc[index], mode=self.mode)


def collate(batch: list[dict]) -> list[dict]:
    """Pad each sample's series to a whole number of patches; text-only samples have none."""
    if not any(sample["time_series"] for sample in batch):
        return batch
    return extend_time_series_to_match_patch_size_and_aggregate(batch, patch_size=PATCH_SIZE)


def loader(frame: pd.DataFrame, batch_size: int, shuffle: bool, workers: int, mode: str = "series") -> DataLoader:
    """A DataLoader over formatted samples."""
    return DataLoader(TripDataset(frame, mode), batch_size=batch_size, shuffle=shuffle, collate_fn=collate,
                      num_workers=workers, persistent_workers=False)


def subsample(frame: pd.DataFrame, limit: int | None, seed: int) -> pd.DataFrame:
    """A seeded random subset, or everything when no limit is set."""
    if not limit or limit >= len(frame):
        return frame.reset_index(drop=True)
    return frame.sample(n=limit, random_state=seed).reset_index(drop=True)


def learning_rate_factor(step: int, warmup: int, total: int) -> float:
    """Linear warmup, then cosine decay to a tenth."""
    if step < warmup:
        return (step + 1) / warmup
    progress = min(1.0, (step - warmup) / max(1, total - warmup))
    return 0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * progress))


def evaluate_split(model: TripTSLM, frame: pd.DataFrame, batch_size: int, workers: int, out_dir: Path, name: str,
                   mode: str = "series") -> dict:
    """Read the distribution for every example, score it, and save predictions."""
    probs, p_cancel, leak_decide, leak_minute = [], [], [], []
    started = time.time()
    for step, batch in enumerate(loader(frame, batch_size, False, workers, mode)):
        try:
            out = model.predict_distribution(batch)
        except torch.OutOfMemoryError:
            # A batch of unusually long prompts: score it one example at a time instead.
            torch.cuda.empty_cache()
            parts = [model.predict_distribution([sample]) for sample in batch]
            out = {key: torch.cat([part[key] for part in parts]) for key in parts[0]}
        probs.append(out["probs"].to(torch.float16).cpu().numpy())
        p_cancel.append(out["p_cancel"].cpu().numpy())
        leak_decide.append(out["leak_decide"].cpu().numpy())
        leak_minute.append(out["leak_minute"].cpu().numpy())
        if step % 50 == 0:
            print(f"  eval {name}: {min((step + 1) * batch_size, len(frame))}/{len(frame)} ({time.time() - started:.0f}s)", flush=True)
    probs_np = np.concatenate(probs).astype(np.float64)
    q = metrics.quantiles_from_distribution(probs_np)
    p_late = metrics.late_from_distribution(probs_np)
    pc = np.concatenate(p_cancel)
    result = metrics.evaluate(frame, q, pc, p_late)
    result["overall"] |= {"mean_leak_decide": float(np.concatenate(leak_decide).mean()),
                          "mean_leak_minute": float(np.concatenate(leak_minute).mean())}
    np.savez_compressed(out_dir / f"tslm_{name}.npz", example_id=frame["example_id"].to_numpy(), quantiles=q,
                        p_cancel=pc, p_late=p_late, probs=probs_np.astype(np.float16))
    return result


def generation_check(model: TripTSLM, frame: pd.DataFrame, batch_size: int, out_dir: Path, mode: str = "series") -> dict:
    """Generate rationale and answer freely on a few examples and compare with the readout."""
    records = []
    for batch_rows in [frame.iloc[i:i + batch_size] for i in range(0, len(frame), batch_size)]:
        samples = collate([prompts.sample(row, mode=mode) for _, row in batch_rows.iterrows()])
        for (_, row), text in zip(batch_rows.iterrows(), model.generate_answers(samples)):
            match = ANSWER_RE.search(text)
            records.append({"example_id": int(row["example_id"]), "target": prompts.target_text(row),
                            "parsed": match.group(1) if match else None, "output": text[-600:]})
    parsed = [r for r in records if r["parsed"] is not None]
    numeric = [r for r in parsed if r["parsed"] != prompts.CANCELLED and r["target"] != prompts.CANCELLED]
    with (out_dir / "generations.jsonl").open("w") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")
    return {"n": len(records), "parse_rate": len(parsed) / max(1, len(records)),
            "mae_generated": float(np.mean([abs(int(r["parsed"]) - int(r["target"])) for r in numeric])) if numeric else None}


def main() -> None:
    """Train within a time budget, then evaluate on validation and test."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--examples", default="data/trip/examples.parquet")
    parser.add_argument("--out", default="out/trip/tslm")
    parser.add_argument("--loss-mode", default="soft_crps", choices=["soft_crps", "plain", "plain_crps"])
    parser.add_argument("--start-checkpoint", default=START_CHECKPOINT)
    parser.add_argument("--resume", help="a checkpoint.pt written by this script")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--eval-batch-size", type=int, default=24)
    parser.add_argument("--lr", type=float, default=1e-4, help="LoRA learning rate")
    parser.add_argument("--lr-encoder", type=float, default=2e-4)
    parser.add_argument("--epochs", type=float, default=1.0)
    parser.add_argument("--max-steps", type=int)
    parser.add_argument("--max-hours", type=float, default=3.0)
    parser.add_argument("--train-limit", type=int)
    parser.add_argument("--val-limit", type=int, default=3000)
    parser.add_argument("--test-limit", type=int, default=30000)
    parser.add_argument("--generate", type=int, default=48)
    parser.add_argument("--save-every", type=int, default=1000)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--eval-only", action="store_true")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--splits", default="validation,test", help="which splits to evaluate after training")
    parser.add_argument("--prompt-mode", choices=prompts.MODES, default="series",
                        help="series through the encoder, as numbers in the text (no encoder), or both")
    parser.add_argument("--text-only", action="store_true", help="same as --prompt-mode text")
    parser.add_argument("--grad-checkpointing", action="store_true",
                        help="recompute activations in the backward pass; fits the longer text-only prompts in 48 GB")
    args = parser.parse_args()
    mode = "text" if args.text_only else args.prompt_mode

    torch.manual_seed(args.seed)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(args.examples)
    train = subsample(df[df["split"] == "train"], args.train_limit, args.seed).sample(frac=1.0, random_state=args.seed)
    val = subsample(df[df["split"] == "validation"], args.val_limit, args.seed)
    test = subsample(df[df["split"] == "test"], args.test_limit, args.seed)
    print(f"train {len(train)}, validation {len(val)}, test {len(test)}", flush=True)

    if args.start_checkpoint == "none":  # ablation: encoder and projector from random initialisation
        model = TripTSLM(loss_mode=args.loss_mode, device=args.device)
    else:
        model = TripTSLM.from_opentslm_checkpoint(args.start_checkpoint, loss_mode=args.loss_mode, device=args.device)
    if not model.lora_enabled:  # a checkpoint that ships adapters has enabled it already
        model.enable_lora()
    if args.resume:
        model.load_from_file(args.resume)
    if args.grad_checkpointing:
        # Non-reentrant, so gradients still reach LoRA when the inputs themselves need no gradient.
        model.llm.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})

    log = {"args": vars(args), "steps": []}
    if not args.eval_only:
        total = args.max_steps or int(args.epochs * len(train) / args.batch_size)
        warmup = max(10, int(0.03 * total))
        groups = [
            {"params": list(model.encoder.parameters()) + list(model.projector.parameters()), "lr": args.lr_encoder},
            {"params": model.get_lora_parameters(), "lr": args.lr},
        ]
        base_lrs = [g["lr"] for g in groups]
        optimizer = torch.optim.AdamW(groups, weight_decay=1e-2)
        trainable = [p for g in groups for p in g["params"]]
        model.train()
        started, step, window, skipped = time.time(), 0, [], 0
        stop = False
        while not stop:
            for batch in loader(train, args.batch_size, True, args.workers, mode):
                for group, base in zip(optimizer.param_groups, base_lrs):
                    group["lr"] = base * learning_rate_factor(step, warmup, total)
                try:
                    loss = model.compute_loss(batch)
                    loss.backward()
                except torch.OutOfMemoryError:
                    # Skip a batch of unusually long prompts rather than lose an unattended run.
                    optimizer.zero_grad(set_to_none=True)
                    loss = None
                    torch.cuda.empty_cache()
                    skipped += 1
                    print(f"skipped a batch after running out of memory ({skipped} so far)", flush=True)
                    continue
                torch.nn.utils.clip_grad_norm_(trainable, 1.0)
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)
                window.append({"loss": float(loss)} | model.last_parts)
                step += 1
                if step % 25 == 0:
                    mean = {k: round(float(np.mean([w[k] for w in window if k in w])), 4) for k in window[-1]}
                    elapsed = time.time() - started
                    print(f"step {step}/{total} {mean} {elapsed:.0f}s ({elapsed / step:.2f}s/step)", flush=True)
                    log["steps"].append({"step": step, "seconds": round(elapsed, 1)} | mean)
                    window = []
                if step % args.save_every == 0:
                    model.store_to_file(str(out_dir / "checkpoint.pt"))
                if step >= total or time.time() - started > args.max_hours * 3600:
                    stop = True
                    break
        model.store_to_file(str(out_dir / "checkpoint.pt"))
        log["train_seconds"] = round(time.time() - started, 1)
        log["train_steps"] = step
        log["skipped_batches"] = skipped
        print(f"training stopped after {step} steps", flush=True)

    model.eval()
    results = {}
    for name, frame in (("validation", val), ("test", test)):
        if name in args.splits.split(","):
            results[name] = evaluate_split(model, frame, args.eval_batch_size, args.workers, out_dir, name, mode)
            print(name, json.dumps(results[name]["overall"]), flush=True)
    if args.generate and "test" in args.splits.split(","):
        log["generation_check"] = generation_check(model, test.head(args.generate), 8, out_dir, mode)
        print("generation", json.dumps(log["generation_check"]), flush=True)
    (out_dir / "metrics.json").write_text(json.dumps(results, indent=2))
    (out_dir / "train_log.json").write_text(json.dumps(log, indent=2))


if __name__ == "__main__":
    main()
