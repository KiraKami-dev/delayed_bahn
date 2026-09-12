"""Gather several months of rail data and split it with leakage controls.

Splits along two axes at once, because either alone is easy to fool. Stations
held out never appear in training, and the test period starts a full context
window after training ends so no window straddles the boundary.
"""

from __future__ import annotations

import datetime as dt
import pickle
from pathlib import Path

import duckdb

from extract import extract
from timef import build
from timef_bridge import rows_from_timef
from windows import CONTEXT_HOURS, HORIZON_HOURS

MONTHS = ("2026-06", "2026-07", "2026-08")
FIRST_HOUR = dt.datetime(2026, 6, 1)
N_HOURS = (30 + 31 + 31) * 24
N_STATIONS = 40
HOLDOUT_EVERY = 5          # every fifth station is never seen in training
TRAIN_ENDS_AT_HOUR = 1560  # windows must finish by here to count as training
EMBARGO_HOURS = CONTEXT_HOURS


def gather(con: duckdb.DuckDBPyConnection) -> None:
    """Build one hourly table spanning every month in :data:`MONTHS`."""
    extract(con, MONTHS[-1], N_STATIONS)  # rank stations once, on the most recent month
    # extract() rebuilds top_stations each call, so pin the ranking before looping;
    # a station set that drifts per month would leave whole months missing per station.
    con.execute("CREATE OR REPLACE TABLE keep AS SELECT station_name FROM top_stations")
    con.execute("CREATE OR REPLACE TABLE hourly_all AS SELECT * FROM hourly")
    for month in MONTHS[:-1]:
        extract(con, month, N_STATIONS)
        con.execute(
            "INSERT INTO hourly_all SELECT h.* FROM hourly h "
            "WHERE h.station_name IN (SELECT station_name FROM keep)"
        )
    con.execute("CREATE OR REPLACE TABLE hourly AS SELECT * FROM hourly_all "
                "WHERE station_name IN (SELECT station_name FROM keep)")


def cell_of(record) -> tuple[bool, str]:
    """Return whether the station is held out, and which period the window sits in."""
    start = int(record.record_id.rsplit("-", 1)[1])
    if start + CONTEXT_HOURS + HORIZON_HOURS <= TRAIN_ENDS_AT_HOUR:
        period = "early"
    elif start >= TRAIN_ENDS_AT_HOUR + EMBARGO_HOURS:
        period = "late"
    else:
        period = "embargo"
    return record.subject_ids[0] in HOLDOUT, period


def main(out_dir: Path) -> None:
    """Gather, convert, split and write everything the training script needs."""
    con = duckdb.connect()
    gather(con)
    dataset = build(con, FIRST_HOUR, N_HOURS)
    stations = sorted({r.subject_ids[0] for r in dataset.records})
    global HOLDOUT
    HOLDOUT = set(stations[::HOLDOUT_EVERY])
    print(f"{len(dataset.records)} records, {len(dataset.tasks)} tasks, "
          f"{len(stations)} stations, {len(HOLDOUT)} held out")

    def assign(record, task):
        unseen, period = cell_of(record)
        if period == "embargo":
            return None
        if unseen or period == "late":
            return "test"
        # Seen stations in the training period are the memorization ceiling. Keep a
        # slice of them out of training so that cell can actually be measured.
        index = int(record.record_id.rsplit("-", 1)[1])
        if index % 13 == 0:
            return "test"
        return "validation" if index % 11 == 0 else "train"

    buckets = rows_from_timef(dataset, assign)

    def eval_cell(unseen_wanted: bool, period_wanted: str):
        rows = []
        by_id = {r.record_id: r for r in dataset.records}
        for row in buckets["test"]:
            unseen, period = cell_of(by_id[row["record_id"]])
            if unseen == unseen_wanted and period == period_wanted:
                rows.append(row)
        return rows

    cells = {
        "seen_early": eval_cell(False, "early"),
        "seen_late": eval_cell(False, "late"),
        "unseen_early": eval_cell(True, "early"),
        "unseen_late": eval_cell(True, "late"),
    }
    print({k: len(v) for k, v in buckets.items()})
    print("eval cells:", {k: len(v) for k, v in cells.items()})
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "splits.pkl").open("wb") as handle:
        pickle.dump({"buckets": buckets, "cells": cells, "holdout": sorted(HOLDOUT)}, handle)
    print("wrote", out_dir / "splits.pkl")


HOLDOUT: set[str] = set()

if __name__ == "__main__":
    import sys
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "data"))
