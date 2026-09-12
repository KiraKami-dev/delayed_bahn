"""Write a Nebius job spec for one trip-delay run, always injecting the runner from disk.

A spec copied from an older job carries the runner it was built with, so a change to
run_ablations.sh is silently missing from jobs built that way. This takes an existing spec only
for the parts that do not change (image, platform, bucket volume) and fills in the rest.

    python job_spec.py --template path/to/any-job.json --tag h100-text-plain \
        --custom-args="--loss-mode plain --prompt-mode text --grad-checkpointing" > job.json

The equals sign matters: without it argparse reads the train.py flags as its own.
"""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

RUNNER = Path(__file__).with_name("run_ablations.sh")


def main() -> None:
    """Print the spec as JSON."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", required=True, help="an existing spec: image, platform and volume are kept")
    parser.add_argument("--tag", required=True, help="RUN_TAG; results land under runs/<tag>/ in the bucket")
    parser.add_argument("--name", help="job name; default jonas-<tag>")
    parser.add_argument("--runs", default="custom", help="RUNS selector of run_ablations.sh")
    parser.add_argument("--custom-args", default="", help="train.py arguments for the custom run")
    parser.add_argument("--steps", type=int, default=2000)
    parser.add_argument("--val-limit", type=int, default=3000)
    parser.add_argument("--test-limit", type=int, default=5000)
    parser.add_argument("--generate", type=int, default=16)
    parser.add_argument("--timeout", default="2h")
    args = parser.parse_args()

    spec = json.loads(Path(args.template).read_text())
    spec["name"] = args.name or f"jonas-{args.tag}"
    spec["timeout"] = args.timeout
    spec["env"] = {"RUN_TAG": args.tag, "RUNS": args.runs, "STEPS": str(args.steps), "VAL_LIMIT": str(args.val_limit),
                   "TEST_LIMIT": str(args.test_limit), "GENERATE": str(args.generate), "CUSTOM_ARGS": args.custom_args}
    spec["injectedFiles"] = [{"containerPath": "/workspace/run_ablations.sh",
                              "content": base64.b64encode(RUNNER.read_bytes()).decode()}]
    print(json.dumps(spec, indent=2))


if __name__ == "__main__":
    main()
