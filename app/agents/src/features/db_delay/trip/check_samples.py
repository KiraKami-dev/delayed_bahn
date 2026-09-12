"""Render every example and check answer tokens, so an unattended run cannot crash on data."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from transformers import AutoTokenizer

sys.path.insert(0, str(Path(__file__).parent))

import prompts  # noqa: E402
from model import BASE_LLM, MAX_MINUTES  # noqa: E402

TEXT_COLUMNS = ["origin", "dest", "first_station", "j_station", "k_station", "train_type", "train_number", "line_number"]


def main(path: str, token_sample: int) -> int:
    """Render all rows; tokenize a sample; report problems and prompt lengths."""
    df = pd.read_parquet(path)
    print("null counts:", {c: int(df[c].isna().sum()) for c in TEXT_COLUMNS})
    print("via lists with a missing name:",
          int(df["via"].map(lambda v: v is not None and any(not isinstance(x, str) for x in v)).sum()))

    started = time.time()
    problems = []
    for i in range(len(df)):
        row = df.iloc[i]
        try:
            prompts.sample(row)
        except Exception as error:  # report every failure instead of stopping at the first
            problems.append((int(row["example_id"]), repr(error)))
    print(f"rendered {len(df)} examples in {time.time() - started:.0f}s, failures: {len(problems)}", problems[:5])

    tok = AutoTokenizer.from_pretrained(BASE_LLM)
    space, cancel = tok.convert_tokens_to_ids("Ġ"), tok.convert_tokens_to_ids("Ġcancelled")
    minute_ids = {tok.convert_tokens_to_ids(str(m)) for m in range(MAX_MINUTES + 1)}
    subset = df.sample(n=min(token_sample, len(df)), random_state=0)
    lengths, bad = [], []
    for i in range(len(subset)):
        row = subset.iloc[i]
        s = prompts.sample(row)
        answer = tok.encode(s["answer"], add_special_tokens=False)
        prefix = tok.encode(s["prefix"], add_special_tokens=False)
        ok = answer == prefix + [cancel] if row["cancelled"] else (answer[:-1] == prefix + [space] and answer[-1] in minute_ids)
        if not ok:
            bad.append(int(row["example_id"]))
        texts = [s["pre_prompt"], s["post_prompt"], *s["time_series_text"]]
        lengths.append(len(answer) + sum(len(tok.encode(t)) for t in texts))
    print(f"token structure checked on {len(subset)}: {len(bad)} bad", bad[:5])
    print("text tokens per sample (plus 72 series tokens) p50/p90/p99/max:",
          np.percentile(lengths, [50, 90, 99]).round().tolist(), max(lengths))
    return 1 if problems or bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "data/trip/examples.parquet", 30000))
