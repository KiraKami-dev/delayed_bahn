"""Cancellation rates per service group and per train type, from the hourly line cache.

The departure-delay model says nothing about cancellations, and a flat guess made every
comfortable journey land on the same number. ``cache/hourly_line.parquet`` (facts.py) counts
cancelled stop events per service group and hour, so the rate is measured, not assumed:

    python build_cancellation_rates.py --cache app/agents/data/db-route/cache/hourly_line.parquet \
        --out app/agents/data/db-route/cache/cancellation_rates.json --days 90

Writes ``{window, services: {"RE -> Ulm Hbf": {rate, n}}, types: {"RE": {rate, n}}, overall}``;
serve_route.py reads it on start and reports the rate and its support in every leg's sources.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

MIN_OBS = 200  # a service needs this many observed stops in the window before its own rate is trusted


def train_type(service_group: str) -> str:
    m = re.match(r"\s*([A-Za-zäöü]+)", service_group or "")
    return m.group(1).upper() if m else ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--days", type=int, default=90)
    args = ap.parse_args()

    df = pd.read_parquet(args.cache, columns=["service_group", "hour", "n_obs", "n_cancelled"])
    end = df["hour"].max()
    start = end - pd.Timedelta(days=args.days)
    df = df[df["hour"] > start]
    by_service = df.groupby("service_group")[["n_obs", "n_cancelled"]].sum()
    by_service = by_service[by_service["n_obs"] >= MIN_OBS]
    df["type"] = df["service_group"].map(train_type)
    by_type = df.groupby("type")[["n_obs", "n_cancelled"]].sum()
    by_type = by_type[by_type["n_obs"] >= MIN_OBS]
    total = df[["n_obs", "n_cancelled"]].sum()

    def table(frame: pd.DataFrame) -> dict:
        return {k: {"rate": round(float(r["n_cancelled"] / r["n_obs"]), 4), "n": int(r["n_obs"])} for k, r in frame.iterrows()}

    payload = {
        "source": "cache/hourly_line.parquet (facts.py), stop events with a cancelled arrival or departure",
        "window": {"start": str(start.date()), "end": str(end.date()), "days": args.days},
        "overall": {"rate": round(float(total["n_cancelled"] / total["n_obs"]), 4), "n": int(total["n_obs"])},
        "services": table(by_service),
        "types": table(by_type),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    print(f"{len(payload['services'])} services, {len(payload['types'])} train types, overall {payload['overall']['rate']:.2%} "
          f"of {payload['overall']['n']:,} stops cancelled, {payload['window']['start']}..{payload['window']['end']} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
