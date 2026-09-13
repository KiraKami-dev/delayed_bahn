"""The run list: every H100 job as the train.py command it ran, with its scores where they exist.

Reads the job specs written by job_spec.py (or the older hand-written ones) and, when a results
directory holds ``<tag>/<run>/metrics.json`` pulled with ``sync_bucket.sh results``, the
validation and test scores. Prints Markdown.

    python trip/nebius/run_list.py --specs path/to/specs --results path/to/results > trip/RUNS.md
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

# The named runs of run_ablations.sh, as the arguments they add to train.py.
NAMED = {
    "main": "",
    "plain_ce": "--loss-mode plain",
    "plain_ce_lr2x": "--loss-mode plain --lr 2e-4 --lr-encoder 4e-4",
    "text_only": "--text-only --grad-checkpointing",
    "ecg_sp_start": "--start-checkpoint OpenTSLM/llama-3.2-3b-ecg-sp",
    "random_encoder": "--start-checkpoint none",
}


def env_of(spec: dict) -> dict[str, str]:
    """The job environment as a dict, whichever shape the spec uses."""
    env = spec.get("env") or {}
    if isinstance(env, list):
        env = {item["name"]: item["value"] for item in env}
    return {k: str(v) for k, v in env.items()}


def command(env: dict[str, str]) -> str:
    """The train.py invocation the runner built from the environment."""
    runs = env.get("RUNS", "custom")
    extra = env.get("CUSTOM_ARGS", "") if runs == "custom" else NAMED.get(runs, "")
    parts = [f"--max-steps {env.get('STEPS', '2000')}", f"--val-limit {env.get('VAL_LIMIT', '3000')}",
             f"--test-limit {env.get('TEST_LIMIT', '5000')}", f"--generate {env.get('GENERATE', '16')}"]
    if extra:
        parts.append(extra)
    return "python trip/train.py " + " ".join(parts)


def scores(results: Path | None, env: dict[str, str]) -> tuple[str, str]:
    """Validation and test 'median error / CRPS' from metrics.json, or blanks."""
    if results is None:
        return "", ""
    path = results / env.get("RUN_TAG", "") / env.get("RUNS", "custom") / "metrics.json"
    if not path.exists():
        return "", ""
    data = json.loads(path.read_text())
    out = []
    for split in ("validation", "test"):
        overall = (data.get(split) or {}).get("overall") or {}
        out.append(f"{overall['mae_median']:.3f} / {overall['crps']:.3f}" if "crps" in overall else "")
    return out[0], out[1]


def main() -> None:
    """Print the Markdown table."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--specs", required=True, help="directory of job-*.json specs")
    parser.add_argument("--results", default=None, help="directory with <tag>/<run>/metrics.json")
    args = parser.parse_args()
    results = Path(args.results) if args.results else None

    rows = []
    for path in sorted(Path(args.specs).glob("job-*.json")):
        spec = json.loads(path.read_text())
        env = env_of(spec)
        val, test = scores(results, env)
        examples = env.get("EXAMPLES", "data/examples.parquet")
        rows.append((spec.get("name", path.stem), examples.replace("data/", ""), env.get("STEPS", "2000"), command(env), val, test))

    print("# Runs on Nebius H100 jobs\n")
    print("Every job ran `trip/nebius/run_ablations.sh` on one H100 with the examples file named in the")
    print("`Examples` column mounted as `data/trip/examples.parquet`, and the command below inside it.")
    print("Scores are `median error / CRPS` in minutes on the job's validation and test subsets (lower is")
    print("better); the test subset is the same 5,000 examples for every 2,000- and 5,000-step run and")
    print("the full 93,738 for the long runs (`--test-limit 0`). Blends, bootstraps and the September")
    print("forward test are computed afterwards on the devbox with `combine.py`, `bootstrap.py` and")
    print("`apply_blend.py`; see DESIGN.md section 16.\n")
    print("| Job | Examples | Steps | Command | Validation | Test |")
    print("|---|---|---|---|---|---|")
    for name, examples, steps, cmd, val, test in rows:
        print(f"| {name} | {examples} | {steps} | `{cmd}` | {val} | {test} |")


if __name__ == "__main__":
    main()
