"""Remote source addressing and the one DuckDB connection helper.

Everything reads ``piebro/deutsche-bahn-data`` over HTTPS with DuckDB's httpfs
extension. The resolve endpoint serves byte ranges (verified: ``accept-ranges:
bytes``), so a query that touches five columns of a 595 MB monthly file moves
only the pages behind those columns. Nothing is downloaded.
"""

from __future__ import annotations

import datetime as dt
from typing import Iterator

import duckdb

HF_DATASET = "piebro/deutsche-bahn-data"
HF_BASE = f"https://huggingface.co/datasets/{HF_DATASET}/resolve/main"
PROCESSED_BASE = f"{HF_BASE}/monthly_processed_data"
RAW_BASE = f"{HF_BASE}/raw_data"

LICENSE = "CC-BY-4.0"
ATTRIBUTION = "Deutsche Bahn AG, via piebro/deutsche-bahn-data"

# Coverage, from the dataset card: the ~100 busiest stations from 2024-07, then
# all stations from 2025-11-02. That expansion is a step change in the
# observation basis, which is why every aggregate is pinned to a fixed station
# universe -- see station_universe.py.
COVERAGE_START = dt.date(2024, 7, 1)
BASIS_EXPANSION_DATE = dt.date(2025, 11, 2)

# A rail service day starts in the small hours, not at midnight: a train that
# departs 23:23 and arrives 00:29 is one run. Grouping on the calendar date
# splits it in two and leaves duplicate stop numbers within a "run". Measured
# over 2026-08-04..06: calendar date gives 99.5% of runs a clean strictly
# increasing stop sequence, the 3-hour offset gives 100.0%.
SERVICE_DAY_OFFSET_HOURS = 3
SERVICE_DATE_SQL = f"CAST(time - INTERVAL {SERVICE_DAY_OFFSET_HOURS} HOUR AS DATE)"

# `line_number` is blank for 100% of ICE, IC, EC, ECE, RJ, NJ and TGV rows
# (measured on 2026-08) while `final_destination_station` is populated for
# 100% of every type. So the service-group key cannot be the line number.
# 4,048 distinct groups in one month -- dense enough for a per-group series.
SERVICE_GROUP_SQL = "train_type || ' -> ' || final_destination_station"


def month_url(month: str) -> str:
    """URL of one processed monthly file. ``month`` is ``YYYY-MM``."""
    return f"{PROCESSED_BASE}/data-{month}.parquet"


def months_between(start: str, end: str) -> list[str]:
    """Inclusive list of ``YYYY-MM`` strings from ``start`` to ``end``."""
    y, m = (int(p) for p in start.split("-"))
    ey, em = (int(p) for p in end.split("-"))
    out: list[str] = []
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def raw_day_glob(day: dt.date) -> str:
    """Glob matching every hourly raw partition file for one calendar day.

    Partitions are named by the scrape window, and a run that starts late in the
    day lands in a file named for the following date, so callers that need a
    whole service day should read both days and filter.
    """
    return f"{RAW_BASE}/year={day.year}/month={day.month}/day={day.day}/*.parquet"


def raw_days(start: dt.date, end: dt.date) -> Iterator[str]:
    """Globs for every day in ``[start, end]``."""
    day = start
    while day <= end:
        yield raw_day_glob(day)
        day += dt.timedelta(days=1)


def connect(threads: int | None = None, memory_limit: str | None = None) -> duckdb.DuckDBPyConnection:
    """A DuckDB connection with httpfs loaded and HTTP retries turned up.

    The retry settings matter: a 26-month extraction issues tens of thousands of
    range requests, and the Hugging Face CDN will occasionally drop one. Without
    retries a single 503 twelve hours in kills the whole build.
    """
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute("SET http_retries = 5;")
    con.execute("SET http_retry_backoff = 2;")
    con.execute("SET http_keep_alive = true;")
    if threads is not None:
        con.execute(f"SET threads = {threads};")
    if memory_limit is not None:
        con.execute(f"SET memory_limit = '{memory_limit}';")
    return con
