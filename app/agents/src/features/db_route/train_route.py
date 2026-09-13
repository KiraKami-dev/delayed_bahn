"""Fine-tune the trip-delay TSLM recipe on the db-route TimeNet datasets, one profile per GPU.

This is Jonas's training recipe (``db_delay/trip``: OpenTSLM-SoftPrompt on Llama-3.2-3B from the
published ``OpenTSLM/llama-3.2-3b-m4-sp`` encoder, LoRA on, a minute-distribution readout after
``Answer:``) pointed at our data instead of his. Nothing about the model is changed except that
``compute_loss`` no longer refuses an answer that is not a whole number of minutes: our records
carry four tasks, and the late/on-time, cause-family and traveller-sentence answers train as plain
token cross-entropy while the departure-delay task keeps his CRPS term on the minute token.

Multi-GPU is by profile, not by data parallelism: the backend launches a multi-GPU preset under
``torchrun``, and rank *i* trains profile *i* of ``--profiles`` on ``cuda:i`` with identical
steps, seed, batch and loss. The bake-off is the job. ``--profiles week`` on a one-GPU preset runs
a single profile the same way.

Inputs come from the bucket mount: ``/outputs/code/db_route.tar.gz`` (this repo's agents code) and
``/outputs/registry`` (the built TimeF datasets). Results go back with byte writes only under
``/outputs/runs/<tag>/<profile>/`` -- the mount refuses rename/chmod/utime.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import sys
import tarfile
import time
import types
from pathlib import Path

import numpy as np

OUT = Path(os.environ.get("NEBIUS_OUTPUT_DIR", "/outputs"))
CODE = Path(os.environ.get("ROUTE_CODE", "/workspace/code"))
HF_HOME = Path(os.environ.get("HF_HOME", "/workspace/hf"))
PROFILE_IDS = {"week": "S", "quarter": "M", "season": "L", "multiscale": "XM"}
CELLS = ("val", "test_seen_entity", "test", "test_seen_time")
LEAKY = {"attributed_share", "artifact_bundle_sha", "split", "split_cell", "recency_weight"}


def log(rank: int, msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}][rank {rank}] {msg}", flush=True)


def wait_for(marker: Path, what: str, rank: int, minutes: int = 40) -> None:
    for _ in range(minutes * 6):
        if marker.exists():
            return
        time.sleep(10)
    raise SystemExit(f"rank {rank}: gave up waiting for {what}")


def stage(rank: int, tarball: Path) -> None:
    """Rank 0 unpacks the code and warms the model cache; the others wait on a marker."""
    marker = CODE / ".ready"
    if rank == 0:
        CODE.mkdir(parents=True, exist_ok=True)
        with tarfile.open(tarball) as tar:
            tar.extractall(CODE)
        from huggingface_hub import hf_hub_download, snapshot_download  # noqa: PLC0415

        snapshot_download("unsloth/Llama-3.2-3B")
        hf_hub_download("OpenTSLM/llama-3.2-3b-m4-sp", "model_checkpoint.pt")
        marker.touch()
    else:
        wait_for(marker, "rank 0's staging", rank)
    features = CODE / "app" / "agents" / "src" / "features"
    for p in (features / "db_route", features / "db_delay" / "trip"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))


def copy_tree_bytes(src: Path, dst: Path) -> int:
    n = 0
    for root, _dirs, files in os.walk(src):
        rel = Path(root).relative_to(src)
        (dst / rel).mkdir(parents=True, exist_ok=True)
        for name in files:
            shutil.copyfile(Path(root) / name, dst / rel / name)
            n += 1
    return n


# --- samples ----------------------------------------------------------------


def caption_stats(captions: list[str]) -> list[float]:
    """The pre-normalisation mean and std the bridge writes into every caption: the level, for the baselines."""
    out: list[float] = []
    for text in captions:
        m = re.search(r"mean (-?[\d.]+) and std (-?[\d.]+)", text)
        out += [float(m.group(1)), float(m.group(2))] if m else [0.0, 0.0]
    return out


def build_rows(dataset, bridge) -> list[dict]:
    """Every (record, task) as a training sample with the fields the loop and the scorer need."""
    options: dict[str, set[str]] = {}
    for record in dataset.records:
        if bridge.annotation_map(record).get("split") != "train":
            continue
        for task in dataset.tasks_for(record):
            if type(task).__name__ == "ClassificationTask":
                options.setdefault(getattr(task, "target_schema", ""), set()).add(str(task.target))
    menus = {schema: tuple(sorted(values)) for schema, values in options.items()}

    rows: list[dict] = []
    for record in dataset.records:
        ann = bridge.annotation_map(record)
        scalars = {k: float(v) for k, v in ann.items()
                   if isinstance(v, (int, float)) and not isinstance(v, bool) and k not in LEAKY}
        for task in dataset.tasks_for(record):
            kind = type(task).__name__
            target = task.target
            y = None
            if kind == "ScalarPredictionTask":
                y = float(target)
                target = int(min(999, max(0, round(y))))  # one token: the readout's alphabet is 0..999
            proxy = types.SimpleNamespace(target=target, rationale=getattr(task, "rationale", None))
            row = bridge.BridgeRow(record, proxy)
            menu = menus.get(getattr(task, "target_schema", ""), ()) if kind == "ClassificationTask" else ()
            sample = bridge.build_sample(row, eos_token="", label_options=menu)
            sample["prefix"] = sample["answer"].rsplit(" Answer:", 1)[0] + " Answer:"
            sample.update(
                kind=kind, y=y, target_text=str(target), record_id=str(record.record_id),
                split=str(ann.get("split")), cell=str(ann.get("split_cell", ann.get("split"))),
                features=[*scalars.values(), *caption_stats(sample["time_series_text"])],
                feature_names=[*scalars.keys()] + [f"cap{i}" for i in range(2 * len(sample["time_series_text"]))],
            )
            rows.append(sample)
    return rows


def strip(sample: dict) -> dict:
    """Only the keys OpenTSLM's collate and the model read."""
    return {k: sample[k] for k in ("pre_prompt", "time_series_text", "time_series", "post_prompt", "answer", "prefix")}


# --- model ------------------------------------------------------------------


def make_model_class(TripTSLM, torch, F):
    class RouteTSLM(TripTSLM):
        """TripTSLM whose loss accepts any answer; the minute term applies where there is a minute."""

        def compute_loss(self, batch):
            eos = self.tokenizer.eos_token_id
            answers = [self.encode(s["answer"]) + [eos] for s in batch]
            embeds, mask, starts = self._assemble(batch, answers)
            hidden, head = self._hidden_and_head(embeds, mask)
            rows, cols, targets, num_rows, num_cols, num_targets = [], [], [], [], [], []
            for i, ids in enumerate(answers):
                minute_answer = len(ids) >= 3 and ids[-3] == self.space_id and ids[-2] in self.id_to_minute
                for j, token in enumerate(ids):
                    col = starts[i] + j - 1
                    at_minute = minute_answer and j == len(ids) - 2
                    if at_minute and self.loss_mode != "plain":
                        num_rows.append(i); num_cols.append(col); num_targets.append(self.id_to_minute[token])
                    if not (at_minute and self.loss_mode == "soft_crps"):
                        rows.append(i); cols.append(col); targets.append(token)
            dev = self.device
            logits = head(hidden[torch.tensor(rows, device=dev), torch.tensor(cols, device=dev)]).float()
            loss = F.cross_entropy(logits, torch.tensor(targets, device=dev))
            parts = {"token_ce": loss.item()}
            if num_rows:
                sel = head(hidden[torch.tensor(num_rows, device=dev), torch.tensor(num_cols, device=dev)]).float()
                y = torch.tensor(num_targets, device=dev, dtype=torch.float32)[:, None]
                cdf = torch.softmax(sel[:, self.minute_ids], dim=-1).cumsum(dim=-1)
                crps = ((cdf - (self.minutes[None] >= y).float()) ** 2).sum(dim=-1).mean()
                loss = loss + self.crps_weight * crps
                parts["crps"] = crps.item()
            self.last_parts = parts
            return loss

    return RouteTSLM


def lr_factor(step: int, warmup: int, total: int) -> float:
    if step < warmup:
        return (step + 1) / warmup
    progress = min(1.0, (step - warmup) / max(1, total - warmup))
    return 0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * progress))


# --- scoring ----------------------------------------------------------------


def score_scalar(y: np.ndarray, q: np.ndarray, probs: np.ndarray, metrics) -> dict:
    median = q[:, 9]  # LEVELS[9] == 0.5
    late_true = y >= 5
    p_late = probs[:, 5:].sum(axis=1) / probs.sum(axis=1)
    return {
        "n": int(len(y)),
        "median_error": float(np.abs(median - y).mean()),
        "crps": float(metrics.crps_from_quantiles(y, q).mean()),
        "coverage_10_90": float(((y >= q[:, 1]) & (y <= q[:, 17])).mean()),
        "width_10_90": float((q[:, 17] - q[:, 1]).mean()),
        "brier_late5": float(((p_late - late_true) ** 2).mean()),
        "late5_rate": float(late_true.mean()),
    }


def baselines(train: list[dict], cell_rows: list[dict]) -> dict:
    """Persistence (the entity's eight-week habit) and gradient boosting on the same scalars."""
    y = np.array([r["y"] for r in cell_rows])
    out: dict = {"n": int(len(y))}
    names = train[0]["feature_names"]
    idx = names.index("habit_median_delay_8w") if "habit_median_delay_8w" in names else None
    if idx is not None:
        habit = np.array([r["features"][idx] for r in cell_rows])
        out["persistence_median_error"] = float(np.abs(habit - y).mean())
    try:
        import xgboost as xgb  # noqa: PLC0415

        X = np.array([r["features"] for r in train]); Y = np.array([r["y"] for r in train])
        Xc = np.array([r["features"] for r in cell_rows])
        model = xgb.XGBRegressor(objective="reg:absoluteerror", n_estimators=400, max_depth=6,
                                 learning_rate=0.05, subsample=0.8, colsample_bytree=0.8, n_jobs=8)
        model.fit(X, Y)
        out["xgboost_median_error"] = float(np.abs(model.predict(Xc) - y).mean())
        qs = {}
        for level in (0.1, 0.5, 0.9):
            m = xgb.XGBRegressor(objective="reg:quantileerror", quantile_alpha=level, n_estimators=300,
                                 max_depth=6, learning_rate=0.05, subsample=0.8, n_jobs=8)
            m.fit(X, Y); qs[level] = m.predict(Xc)
        out["xgboost_coverage_10_90"] = float(((y >= qs[0.1]) & (y <= qs[0.9])).mean())
    except Exception as exc:  # noqa: BLE001
        out["xgboost_error"] = str(exc)[:200]
    return out


# --- main -------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profiles", default="week,quarter,season,multiscale")
    ap.add_argument("--registry", default=str(OUT / "registry"))
    ap.add_argument("--tag", default=os.environ.get("RUN_TAG", "route"))
    ap.add_argument("--steps", type=int, default=2000)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--eval-batch-size", type=int, default=16)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--lr-encoder", type=float, default=2e-4)
    ap.add_argument("--loss-mode", default="plain_crps", choices=["plain", "plain_crps", "soft_crps"])
    ap.add_argument("--eval-limit", type=int, default=600, help="scalar rows scored per cell")
    ap.add_argument("--generate", type=int, default=64, help="classification rows generated per cell")
    ap.add_argument("--save-every", type=int, default=500)
    ap.add_argument("--max-hours", type=float, default=2.5)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--grad-checkpointing", action="store_true")
    args = ap.parse_args()

    rank = int(os.environ.get("LOCAL_RANK", "0"))
    profiles = [p for p in args.profiles.split(",") if p]
    if rank >= len(profiles):
        print(f"rank {rank}: no profile assigned, exiting", flush=True)
        return 0
    profile = profiles[rank]
    os.environ.setdefault("HF_HOME", str(HF_HOME))
    stage(rank, OUT / "code" / "db_route.tar.gz")

    import torch  # noqa: PLC0415
    import torch.nn.functional as F  # noqa: PLC0415
    from opentslm.model_config import PATCH_SIZE  # noqa: PLC0415
    from opentslm.time_series_datasets.util import extend_time_series_to_match_patch_size_and_aggregate  # noqa: PLC0415
    from timenet.client import TimeNet  # noqa: PLC0415

    import bridge  # noqa: PLC0415  (db_route)
    import metrics  # noqa: PLC0415  (db_delay/trip)
    from model import START_CHECKPOINT, TripTSLM  # noqa: PLC0415  (db_delay/trip)

    torch.cuda.set_device(rank)
    device = f"cuda:{rank}"
    torch.manual_seed(args.seed)
    rng = np.random.default_rng(args.seed)
    local = Path("/workspace/results") / profile
    local.mkdir(parents=True, exist_ok=True)

    dataset_id = f"error404/db-route-{profile}"
    t = time.time()
    dataset = TimeNet(args.registry).load(dataset_id)
    rows = build_rows(dataset, bridge)
    train = [r for r in rows if r["split"] == "train"]
    by_cell = {c: [r for r in rows if r["cell"] == c] for c in CELLS}
    log(rank, f"{dataset_id}: {len(rows)} samples, train {len(train)}, "
              + ", ".join(f"{c} {len(v)}" for c, v in by_cell.items()) + f" ({time.time() - t:.0f}s)")

    RouteTSLM = make_model_class(TripTSLM, torch, F)
    model = RouteTSLM.from_opentslm_checkpoint(START_CHECKPOINT, loss_mode=args.loss_mode, device=device)
    if not model.lora_enabled:
        model.enable_lora()
    if args.grad_checkpointing:
        model.llm.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})

    def collate(batch: list[dict]) -> list[dict]:
        batch = [strip(s) for s in batch]
        return extend_time_series_to_match_patch_size_and_aggregate(batch, patch_size=PATCH_SIZE)

    # -- train
    total, warmup = args.steps, max(10, int(0.03 * args.steps))
    groups = [{"params": list(model.encoder.parameters()) + list(model.projector.parameters()), "lr": args.lr_encoder},
              {"params": model.get_lora_parameters(), "lr": args.lr}]
    base = [g["lr"] for g in groups]
    opt = torch.optim.AdamW(groups, weight_decay=1e-2)
    trainable = [p for g in groups for p in g["params"]]
    model.train()
    started, step, window, skipped, run_log = time.time(), 0, [], 0, []
    order = rng.permutation(len(train))
    cursor = 0
    while step < total and time.time() - started < args.max_hours * 3600:
        if cursor + args.batch_size > len(order):
            order, cursor = rng.permutation(len(train)), 0
        batch = collate([train[i] for i in order[cursor:cursor + args.batch_size]])
        cursor += args.batch_size
        for g, b in zip(opt.param_groups, base):
            g["lr"] = b * lr_factor(step, warmup, total)
        try:
            loss = model.compute_loss(batch)
            loss.backward()
        except torch.OutOfMemoryError:
            opt.zero_grad(set_to_none=True); torch.cuda.empty_cache(); skipped += 1
            log(rank, f"skipped an OOM batch ({skipped} so far)")
            continue
        torch.nn.utils.clip_grad_norm_(trainable, 1.0)
        opt.step(); opt.zero_grad(set_to_none=True)
        window.append({"loss": float(loss)} | model.last_parts)
        step += 1
        if step % 25 == 0:
            mean = {k: round(float(np.mean([w[k] for w in window if k in w])), 4) for k in window[-1]}
            el = time.time() - started
            log(rank, f"{profile} step {step}/{total} {mean} {el:.0f}s ({el / step:.2f}s/step)")
            run_log.append({"step": step, "seconds": round(el, 1)} | mean); window = []
        if step % args.save_every == 0:
            model.store_to_file(str(local / "checkpoint.pt"))
    model.store_to_file(str(local / "checkpoint.pt"))
    log(rank, f"{profile}: trained {step} steps in {time.time() - started:.0f}s, {skipped} skipped")

    # -- evaluate
    model.eval()
    results: dict = {"profile": profile, "dataset_id": dataset_id, "steps": step, "args": vars(args), "cells": {}}
    train_scalar = [r for r in train if r["kind"] == "ScalarPredictionTask"]
    for cell, cell_rows in by_cell.items():
        scalar = [r for r in cell_rows if r["kind"] == "ScalarPredictionTask"]
        if not scalar:
            continue
        if len(scalar) > args.eval_limit:
            scalar = [scalar[i] for i in sorted(rng.choice(len(scalar), args.eval_limit, replace=False))]
        probs = []
        with torch.no_grad():
            for i in range(0, len(scalar), args.eval_batch_size):
                batch = collate(scalar[i:i + args.eval_batch_size])
                try:
                    out = model.predict_distribution(batch)
                except torch.OutOfMemoryError:
                    torch.cuda.empty_cache()
                    out = {"probs": torch.cat([model.predict_distribution([s])["probs"] for s in batch])}
                probs.append(out["probs"].float().cpu().numpy())
        probs_np = np.concatenate(probs).astype(np.float64)
        q = metrics.quantiles_from_distribution(probs_np)
        y = np.array([r["y"] for r in scalar])
        entry = {"tslm": score_scalar(y, q, probs_np, metrics), "baselines": baselines(train_scalar, scalar)}
        np.savez_compressed(local / f"scalar_{cell}.npz", y=y, quantiles=q,
                            record_id=np.array([r["record_id"] for r in scalar]))
        # classification tasks: generate and parse
        for kind in ("ClassificationTask",):
            cls_rows = [r for r in cell_rows if r["kind"] == kind]
            if not cls_rows or not args.generate:
                continue
            pick = [cls_rows[i] for i in sorted(rng.choice(len(cls_rows), min(args.generate, len(cls_rows)), replace=False))]
            hits, majority = 0, {}
            for r in [x for x in train if x["kind"] == kind]:
                majority[r["target_text"]] = majority.get(r["target_text"], 0) + 1
            with torch.no_grad():
                for i in range(0, len(pick), 8):
                    chunk = pick[i:i + 8]
                    texts = model.generate_answers(collate(chunk), max_new_tokens=48)
                    for r, text in zip(chunk, texts):
                        answer = text.rsplit("Answer:", 1)[-1].strip().split()[0].strip(".") if "Answer:" in text else ""
                        hits += answer == r["target_text"]
            top = max(majority, key=majority.get) if majority else ""
            entry["classification"] = {"n": len(pick), "accuracy": hits / len(pick),
                                       "majority_class_accuracy": sum(r["target_text"] == top for r in pick) / len(pick)}
        results["cells"][cell] = entry
        log(rank, f"{profile} {cell}: {json.dumps(entry)}")
    results["train_log"] = run_log
    (local / "metrics.json").write_text(json.dumps(results, indent=2))
    dest = OUT / "runs" / args.tag / profile
    n = copy_tree_bytes(local, dest)
    log(rank, f"{profile}: copied {n} files to {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
