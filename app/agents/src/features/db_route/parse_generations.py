"""Turn a generate_route.py job log into generations.json next to the run's forecasts.

generate_route.py prints what the trained model actually says for held-out rows, but only to the
Nebius job log. That log is the only copy, and it expires with the job, so this script fixes it in
the bucket layout the app serves from:

    nebius ai job logs aijob-e00jes935bm0n0hvam --since 3h --tail 1000 > generate.log
    python parse_generations.py generate.log --run app/agents/data/db-route/runs/route-2k/quarter

writes ``<run>/generations.json`` (and copies the log beside it): one entry per sample with the
record id, the task kind, the answer options, the model's generated text, the ground truth and,
for the minute task, the summarised distribution. serve_route.py picks the file up on start.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

HEADER = re.compile(r"\[(ScalarPredictionTask|ClassificationTask|AnswerTask)\]\s+record (\S+)\s+\((\d+) series\)")
FIELD = re.compile(r"^\s*(QUESTION|OPTIONS|MODEL|TRUTH|DISTRIB)\s*:\s?(.*)$")
STAMP = re.compile(r"^\[[^\]]*\]\s?")  # the CLI's leading timestamp
ANSWER = re.compile(r"^'?Answer:\s*(.*?)'?$")


def clean_answer(text: str) -> str:
    m = ANSWER.match(text.strip())
    return (m.group(1) if m else text).strip().strip("'").strip()


def parse(lines: list[str]) -> list[dict]:
    out: list[dict] = []
    current: dict | None = None
    for raw in lines:
        line = STAMP.sub("", raw.rstrip("\n"))
        h = HEADER.search(line)
        if h:
            current = {"kind": h.group(1), "recordId": h.group(2), "series": int(h.group(3))}
            out.append(current)
            continue
        if current is None:
            continue
        f = FIELD.match(line)
        if not f:
            continue
        key, value = f.group(1), f.group(2).strip()
        if key == "QUESTION" and value:
            current["question"] = value
        elif key == "OPTIONS":
            m = re.search(r"Possible answers are:\s*(.*?)\.?$", value)
            current["options"] = [o.strip() for o in (m.group(1) if m else value).split(",") if o.strip()]
        elif key == "MODEL":
            current["model"] = clean_answer(value)
        elif key == "TRUTH":
            current["truth"] = clean_answer(value)
        elif key == "DISTRIB":
            current["distribution"] = value
            m = re.search(r"median (\d+) min, 10-90% range (\d+)-(\d+) min, P\(>=5 min late\) (\d+)%\s+\(true ([\d.]+) min\)", value)
            if m:
                current["quantiles"] = {"p10": int(m.group(2)), "p50": int(m.group(1)), "p90": int(m.group(3))}
                current["pLate5"] = int(m.group(4)) / 100
                current["actualMinutes"] = float(m.group(5))
    return [e for e in out if "model" in e]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("log", type=Path)
    ap.add_argument("--run", type=Path, required=True, help="the run folder holding metrics.json and scalar_*.npz")
    ap.add_argument("--job", default="", help="job id, recorded for provenance")
    args = ap.parse_args()
    entries = parse(args.log.read_text(encoding="utf-8", errors="replace").splitlines())
    if not entries:
        raise SystemExit(f"no generations found in {args.log}")
    args.run.mkdir(parents=True, exist_ok=True)
    payload = {"source": "generate_route.py job log", "job": args.job, "log": args.log.name, "count": len(entries), "samples": entries}
    (args.run / "generations.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    if args.log.resolve() != (args.run / "generate.log").resolve():
        shutil.copyfile(args.log, args.run / "generate.log")
    kinds = {}
    for e in entries:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    print(f"{len(entries)} generations -> {args.run / 'generations.json'}  {kinds}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
