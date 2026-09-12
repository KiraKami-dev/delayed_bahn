"""Score a run's saved predictions per task, not per answer type.

The training script groups both classification tasks together, which hides the
fact that the binary comparison and the 24-way peak-hour question have very
different difficulty and very different baselines. This reads the prediction
files a run already wrote, so it needs no GPU and no regeneration.
"""

from __future__ import annotations

import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

CELLS = ("seen_early", "seen_late", "unseen_early", "unseen_late")
HOUR_RE = re.compile(r"^\d{2}$")


def task_of(record: dict) -> str:
    """Name the task a prediction record belongs to, from the shape of its target."""
    if record["task"] == "ScalarPredictionTask":
        return "forecast"
    return "peak" if HOUR_RE.match(record["target"]) else "comparison"


def score_cell(records: list[dict]) -> dict:
    """Score one cell, splitting the three tasks and giving each its own baseline."""
    grouped: dict[str, list[dict]] = {}
    for record in records:
        grouped.setdefault(task_of(record), []).append(record)
    out: dict[str, dict] = {}
    for name, rows in grouped.items():
        parsed = [r for r in rows if r["predicted"] is not None]
        entry = {"n": len(rows), "parse_rate": round(len(parsed) / len(rows), 3)}
        if name == "forecast":
            errors = []
            for r in parsed:
                try:
                    errors.append(abs(float(r["predicted"]) - float(r["target"])))
                except ValueError:
                    continue
            if errors:
                entry |= {
                    "mae": round(statistics.fmean(errors), 3),
                    "median_ae": round(statistics.median(errors), 3),
                }
        else:
            majority = Counter(r["target"] for r in rows).most_common(1)[0]
            hits = sum(1 for r in rows if r["predicted"] == r["target"])
            entry |= {
                "accuracy": round(hits / len(rows), 3),
                "majority_baseline": round(majority[1] / len(rows), 3),
                "accuracy_when_parsed": round(
                    sum(1 for r in parsed if r["predicted"] == r["target"]) / len(parsed), 3
                )
                if parsed
                else None,
            }
        out[name] = entry
    return out


def main(run_dir: Path) -> None:
    """Print and save a per-task table for every cell the run produced."""
    # The forecast baseline needs the input series, which predictions do not carry,
    # so lift it from the run's own metrics file when that exists.
    baselines: dict = {}
    metrics_path = run_dir / "metrics.json"
    if metrics_path.exists():
        baselines = json.loads(metrics_path.read_text()).get("cells", {})
    report = {}
    for cell in CELLS:
        path = run_dir / f"predictions_{cell}.jsonl"
        if not path.exists():
            continue
        records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        scored = score_cell(records)
        cell_baseline = baselines.get(cell, {})
        if "forecast" in scored and "baseline_mae" in cell_baseline:
            scored["forecast"]["baseline_mae"] = cell_baseline["baseline_mae"]
            scored["forecast"]["baseline_median_ae"] = cell_baseline["baseline_median_ae"]
        report[cell] = scored
    for cell, tasks in report.items():
        print(f"\n{cell}")
        for name, entry in sorted(tasks.items()):
            print(f"  {name:<11} " + "  ".join(f"{k}={v}" for k, v in entry.items()))
    (run_dir / "metrics_per_task.json").write_text(json.dumps(report, indent=2))
    print("\nwrote", run_dir / "metrics_per_task.json")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "out/run2"))
