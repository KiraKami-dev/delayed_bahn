"""The fact cache: everything the network side produces, once.

**This module is a frozen contract.** Its three tables are what every profile
re-buckets from, so the schema below is the interface the rest of the pipeline
codes against.

Two rules shape it.

**Store sums and counts, never means.** Re-bucketing a mean-of-means across
hours with different train counts is biased -- an hour with 4 trains would weigh
as much as one with 400. Every coarser bucket is ``sum(sum_delay)/sum(n_obs)``,
which is only possible if the finest grain keeps both. This is why the cache is
hourly and additive rather than pre-averaged.

**Pin the observation basis.** piebro covers ~100 stations from 2024-07 and
*all* stations from 2025-11-02. An aggregate over "whatever was observed"
therefore steps on that date -- more stations, and minor halts have a different
delay profile than a Hbf -- and a 60- or 180-day series straddling it would
carry a manufactured regime change straight into training. Every aggregate here
is restricted to a station universe pinned once over the whole period.

Work is sharded by day and skips completed days, so the long extraction is
resumable: a dropped CDN request eight hours in costs one day, not the run.
"""

from __future__ import annotations

import argparse
import concurrent.futures as futures
import datetime as dt
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Sequence

import pyarrow as pa
import pyarrow.parquet as pq

from causes import SERIES_FAMILIES, parse_stops
from sources import (
    HF_DATASET,
    PROCESSED_BASE,
    RAW_BASE,
    SERVICE_DATE_SQL,
    SERVICE_GROUP_SQL,
    connect,
    month_url,
    months_between,
)

HF_TREE_API = f"https://huggingface.co/api/datasets/{HF_DATASET}/tree/main"

# S-Bahn plus the regional operators around Munich. Long-distance types are
# excluded on purpose: an ICE calling at Munich Hbf would drag Hamburg into the
# catchment.
LOCAL_TRAIN_TYPES = "('S','RB','RE','M','BRB','ag','DPN','ALX')"

# --- the contract -----------------------------------------------------------
# hourly_station(station, hour, sum_delay, n_obs, n_cancelled, n_attributed,
#                sum_delay_works, sum_delay_weather, sum_delay_technical,
#                sum_delay_knock_on, sum_delay_staff, sum_delay_attributed)
# hourly_line   (service_group, hour, ...same columns...)
# hourly_pair   (service_group, station, hour, ...same columns...)
#
# `hourly_pair` is what makes `service_at_station_delay` possible -- the specific
# habit of this train at this stop, which is rank 4 on the predictor list and the
# one channel a station-level or line-level aggregate cannot express.

_FAMILY_COLS = tuple(f"sum_delay_{f}" for f in SERIES_FAMILIES)
FACT_COLUMNS: tuple[str, ...] = (
    "sum_delay",
    "n_obs",
    "n_cancelled",
    "n_attributed",
    "sum_delay_attributed",
    *_FAMILY_COLS,
)


def _http_json(url: str, retries: int = 4) -> list[dict]:
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=90) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            if attempt == retries - 1:
                raise
            time.sleep(2**attempt)
    return []


def raw_files_for_day(day: dt.date) -> list[str]:
    """Resolve one day's raw partition files.

    DuckDB cannot glob a plain HTTP path -- there is no directory listing to
    expand -- so the file list comes from the Hub tree API and is passed to
    ``read_parquet`` explicitly.
    """
    listing = _http_json(f"{HF_TREE_API}/raw_data/year={day.year}/month={day.month}/day={day.day}")
    return [
        f"https://huggingface.co/datasets/{HF_DATASET}/resolve/main/{entry['path']}"
        for entry in listing
        if entry.get("type") == "file" and entry["path"].endswith(".parquet")
    ]


def _sql_list(urls: list[str]) -> str:
    return "[" + ",".join(f"'{u}'" for u in urls) + "]"


# Named commuter regions. A region is a seed pattern matched against station
# names, plus a one-hop expansion along local operators only -- see
# build_catchment for why both halves are needed.
#
# Operators differ by region: BRB and ag are Bavarian, NWB and ERB run in NRW,
# ODEG around Berlin. Listing them per region keeps the hop local instead of
# following a national operator across the country.
REGIONS: dict[str, dict[str, object]] = {
    "munich": {
        "seed": "%münchen%",
        "operators": ("S", "RB", "RE", "M", "BRB", "ag", "DPN", "ALX"),
    },
    "berlin": {
        "seed": "%berlin%",
        "operators": ("S", "RB", "RE", "ODEG", "NEB", "DPN"),
    },
    "hamburg": {
        "seed": "%hamburg%",
        "operators": ("S", "RB", "RE", "AKN", "erx", "DPN"),
    },
    "cologne": {
        "seed": "%köln%",
        "operators": ("S", "RB", "RE", "NWB", "ERB", "VIA", "DPN"),
    },
    "frankfurt": {
        "seed": "%frankfurt%",
        "operators": ("S", "RB", "RE", "HLB", "VIA", "DPN"),
    },
    "stuttgart": {
        "seed": "%stuttgart%",
        "operators": ("S", "RB", "RE", "GAB", "AVG", "DPN"),
    },
}


def build_catchment(
    month: str,
    out: Path,
    *,
    regions: Sequence[str] = ("munich",),
    source: str | None = None,
) -> list[str]:
    """A commuter catchment, as EVA numbers, for one or more named regions.

    Getting the boundary right takes both halves. Name-matching "München" alone
    finds 49 stations and misses the S-Bahn branches -- the S7 runs through
    Pullach, Baierbrunn and Wolfratshausen, none of which carry the city name.
    Expanding one network hop from any München station overshoots the other way,
    following ICE services all the way to Hamburg. So: one hop, but only along
    S-Bahn and regional operators, which is the commuter network rather than
    everywhere a long-distance train from the city happens to go.

    Measured for Munich on 2026-08: 552 stations, 1.79M stop events/month, 23.4%
    at or over 5 minutes late, and 3,683 (service, station) pairs seen on 20+
    days -- against a target of ~3,000 entities.

    Passing several regions unions their catchments and deduplicates, which is
    how the corpus grows without touching anything downstream: every stage after
    this reads a station list and does not care how it was drawn.
    """
    unknown = [r for r in regions if r not in REGIONS]
    if unknown:
        raise ValueError(f"unknown region(s) {unknown}; known: {sorted(REGIONS)}")

    events = source or f"read_parquet('{month_url(month)}')"
    con = connect(threads=4)
    try:
        con.execute("SET enable_progress_bar=false;")
        con.execute(f"CREATE VIEW m AS SELECT *, {SERVICE_GROUP_SQL} AS sg FROM {events}")
        per_region: dict[str, list[str]] = {}
        rows: list[tuple[str, str]] = []
        for region in regions:
            cfg = REGIONS[region]
            operators = "(" + ",".join(f"'{o}'" for o in cfg["operators"]) + ")"
            found = con.execute(
                f"""
                WITH seeded AS (
                  SELECT DISTINCT station_name FROM m WHERE station_name ILIKE '{cfg["seed"]}'
                ),
                local_services AS (
                  SELECT DISTINCT sg FROM m JOIN seeded USING (station_name)
                  WHERE train_type IN {operators}
                ),
                region AS (SELECT DISTINCT station_name FROM m JOIN local_services USING (sg))
                SELECT DISTINCT e.eva, e.station_name
                FROM m e JOIN region r ON r.station_name = e.station_name
                WHERE e.eva IS NOT NULL
                ORDER BY 1
                """
            ).fetchall()
            per_region[region] = sorted({name for _, name in found})
            rows.extend(found)
            print(f"  {region}: {len({e for e, _ in found})} EVAs, "
                  f"{len(per_region[region])} stations", flush=True)
    finally:
        con.close()

    evas = sorted({eva for eva, _ in rows})
    stations = sorted({name for _, name in rows})
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "rule": "one network hop from a seed station, via local operators only",
                "regions": list(regions),
                "reference_month": month,
                "n_evas": len(evas),
                "n_stations": len(stations),
                "per_region_stations": {r: len(v) for r, v in per_region.items()},
                "evas": evas,
                "stations": stations,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    print(f"catchment: {len(evas)} EVAs over {len(stations)} stations "
          f"({', '.join(regions)}) -> {out}", flush=True)
    return evas


def catchment_fingerprint(evas: Sequence[str] | None) -> str:
    """Short hash of the EVA set a cause shard was extracted for.

    Shards are cached per day, and a day already extracted is skipped. That is
    what makes a long run resumable -- and it is also a trap: widening the
    catchment leaves the old, narrower shards in place, so five sixths of the
    corpus would silently carry no causes at all. Keying the directory on the
    EVA set means a different catchment simply misses the cache instead.
    """
    if not evas:
        return "all"
    digest = hashlib.sha256(",".join(sorted(evas)).encode()).hexdigest()
    return f"{len(evas)}-{digest[:8]}"


def shard_dirs(cache_dir: Path, evas: Sequence[str] | None) -> tuple[Path, Path]:
    fp = catchment_fingerprint(evas)
    return cache_dir / "causes" / fp, cache_dir / "notices" / fp


def extract_day_causes(
    day: dt.date, cache_dir: Path, *, evas: list[str] | None = None, force: bool = False
) -> dict:
    """Project one day of raw IRIS XML down to causes and dated notices.

    The XML never lands on disk: it is fetched, projected, and dropped.

    ``evas`` is the reason this is affordable. The raw ``url`` column ends in the
    station's EVA number, so the catchment can be filtered *before* touching
    ``response_data`` -- and response_data is essentially all of the bytes.
    Measured on 2026-08-04: unfiltered is 23,947 rows and 584 MB; the Munich
    catchment is a tenth of that. Nationwide the run takes 3.6 hours, filtered
    it takes minutes.
    """
    causes_dir, notices_dir = shard_dirs(cache_dir, evas)
    causes_path = causes_dir / f"{day.isoformat()}.parquet"
    notices_path = notices_dir / f"{day.isoformat()}.parquet"
    if causes_path.exists() and notices_path.exists() and not force:
        return {"day": day.isoformat(), "status": "cached"}

    started = time.time()
    urls = raw_files_for_day(day)
    if not urls:
        return {"day": day.isoformat(), "status": "missing"}

    where = "api_name LIKE '%fchg%' AND response_data LIKE '%<m %'"
    if evas:
        in_list = "(" + ",".join(f"'{e}'" for e in evas) + ")"
        where += f" AND regexp_extract(url, '([0-9]+)$', 1) IN {in_list}"
    con = connect(threads=2)
    try:
        con.execute("SET enable_progress_bar=false;")
        rows = con.execute(
            f"SELECT response_data FROM read_parquet({_sql_list(urls)}) WHERE {where}"
        ).fetchall()
    finally:
        con.close()

    stop_ids: list[str] = []
    stop_codes: list[list[int]] = []
    stop_families: list[list[str]] = []
    seen_notices: dict[str, tuple] = {}
    notice_stops: dict[str, list[str]] = defaultdict(list)

    for (xml,) in rows:
        day_causes, day_notices = parse_stops(xml)
        for stop in day_causes:
            stop_ids.append(stop.stop_id)
            stop_codes.append(list(stop.codes))
            stop_families.append(list(stop.families))
        for notice in day_notices:
            # One notice reaches ~55 stops; keep it once and record where it landed.
            seen_notices.setdefault(
                notice.notice_id,
                (
                    notice.category,
                    notice.valid_from,
                    notice.valid_to,
                    notice.priority,
                    notice.issued_at,
                ),
            )
            notice_stops[notice.notice_id].append(notice.stop_id)

    causes_path.parent.mkdir(parents=True, exist_ok=True)
    notices_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.table(
            {
                "stop_id": pa.array(stop_ids, pa.string()),
                "codes": pa.array(stop_codes, pa.list_(pa.int16())),
                "families": pa.array(stop_families, pa.list_(pa.string())),
            }
        ),
        causes_path,
        compression="zstd",
    )
    ids = sorted(seen_notices)
    pq.write_table(
        pa.table(
            {
                "notice_id": pa.array(ids, pa.string()),
                "category": pa.array([seen_notices[i][0] for i in ids], pa.string()),
                "valid_from": pa.array([seen_notices[i][1] for i in ids], pa.timestamp("us", tz="UTC")),
                "valid_to": pa.array([seen_notices[i][2] for i in ids], pa.timestamp("us", tz="UTC")),
                "priority": pa.array([seen_notices[i][3] for i in ids], pa.int8()),
                "issued_at": pa.array([seen_notices[i][4] for i in ids], pa.timestamp("us", tz="UTC")),
                "stop_ids": pa.array([sorted(set(notice_stops[i])) for i in ids], pa.list_(pa.string())),
            }
        ),
        notices_path,
        compression="zstd",
    )
    return {
        "day": day.isoformat(),
        "status": "built",
        "cause_stops": len(stop_ids),
        "notices": len(ids),
        "seconds": round(time.time() - started, 1),
    }


def extract_range(
    start: dt.date,
    end: dt.date,
    cache_dir: Path,
    *,
    evas: list[str] | None = None,
    workers: int = 8,
    force: bool = False,
) -> None:
    """Shard the cause extraction across days.

    Days are independent and skip-if-present, so widening the range or adding
    workers needs no coordination, and an interrupted run resumes where it left off.
    """
    days = [start + dt.timedelta(days=i) for i in range((end - start).days + 1)]
    causes_dir, notices_dir = shard_dirs(cache_dir, evas)
    print(f"shards -> {causes_dir}", flush=True)
    todo = [
        d
        for d in days
        if force
        or not (
            (causes_dir / f"{d.isoformat()}.parquet").exists()
            and (notices_dir / f"{d.isoformat()}.parquet").exists()
        )
    ]
    print(
        f"cause extraction: {len(days)} days in range, {len(todo)} to build, {workers} workers",
        flush=True,
    )
    built = cached = missing = 0
    started = time.time()
    with futures.ThreadPoolExecutor(max_workers=workers) as pool:
        pending = {
            pool.submit(extract_day_causes, d, cache_dir, evas=evas, force=force): d for d in todo
        }
        for done in futures.as_completed(pending):
            day = pending[done]
            try:
                result = done.result()
            except Exception as exc:  # one bad day must not kill a 790-day run
                print(f"  [fail] {day}: {type(exc).__name__}: {exc}", flush=True)
                continue
            status = result["status"]
            built += status == "built"
            cached += status == "cached"
            missing += status == "missing"
            if status == "built":
                n = built + cached + missing
                rate = (time.time() - started) / max(built, 1)
                remaining = (len(todo) - n) * rate / 60
                print(
                    f"  [{n}/{len(todo)}] {result['day']}  "
                    f"{result['cause_stops']:>7,} cause stops  {result['notices']:>4} notices  "
                    f"{result['seconds']:>5.1f}s  (~{remaining:.0f} min left)",
                    flush=True,
                )
    print(f"done: {built} built, {cached} cached, {missing} missing", flush=True)


def build_station_universe(months: list[str], out: Path, *, top_n: int = 400) -> list[str]:
    """Pin the station set, once, over the whole period.

    A station qualifies only if it is present in *every* month, which is what
    excludes the cohort that appears on 2025-11-02 and would otherwise put a step
    in every long series. Ranked by traffic and capped.
    """
    con = connect()
    try:
        per_month = []
        for month in months:
            rows = con.execute(
                f"SELECT station_name, count(*) AS n FROM read_parquet('{month_url(month)}') "
                "GROUP BY 1"
            ).fetchall()
            per_month.append({name: n for name, n in rows})
            print(f"  {month}: {len(rows):,} stations", flush=True)
    finally:
        con.close()

    present_everywhere = set(per_month[0])
    for counts in per_month[1:]:
        present_everywhere &= set(counts)
    totals = {s: sum(m.get(s, 0) for m in per_month) for s in present_everywhere}
    universe = sorted(totals, key=lambda s: (-totals[s], s))[:top_n]

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "months": months,
                "rule": "present in every month; ranked by total stop events; capped",
                "why": (
                    "piebro widens from ~100 stations to all stations on 2025-11-02. "
                    "An aggregate over whatever was observed steps on that date, so the "
                    "basis is pinned instead."
                ),
                "n_stations": len(universe),
                "stations": universe,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    print(f"station universe: {len(universe)} stations -> {out}", flush=True)
    return universe


def _agg_select(keys: str) -> str:
    """The one aggregation used for every grain. Sums and counts only."""
    families = ",\n       ".join(
        f"sum(CASE WHEN list_contains(c.families, '{f}') THEN e.delay_in_min ELSE 0 END) "
        f"AS sum_delay_{f}"
        for f in SERIES_FAMILIES
    )
    return f"""
SELECT {keys},
       date_trunc('hour', e.time)                                        AS hour,
       sum(e.delay_in_min)                                               AS sum_delay,
       count(*)                                                          AS n_obs,
       sum(CASE WHEN e.arrival_is_canceled OR e.departure_is_canceled
                THEN 1 ELSE 0 END)                                       AS n_cancelled,
       count(c.stop_id)                                                  AS n_attributed,
       sum(CASE WHEN c.stop_id IS NOT NULL THEN e.delay_in_min ELSE 0 END)
                                                                         AS sum_delay_attributed,
       {families}
FROM events e
LEFT JOIN causes c ON c.stop_id = e.id
GROUP BY ALL
"""


def available_months(months: list[str]) -> list[str]:
    """Drop months piebro has not published yet.

    The monthly files appear after the month closes, so a range ending in the
    current month 404s. Checking is one HEAD request each and turns a crash
    fourteen minutes into the join into a line of output.
    """
    listing = _http_json(f"{HF_TREE_API}/monthly_processed_data")
    published = {
        entry["path"].rsplit("data-", 1)[-1].removesuffix(".parquet")
        for entry in listing
        if entry.get("type") == "file"
    }
    keep = [m for m in months if m in published]
    missing = [m for m in months if m not in published]
    if missing:
        print(f"  not published yet, skipping: {', '.join(missing)}", flush=True)
    return keep


def month_sources(months: list[str], cache_dir: Path) -> list[str]:
    """Local monthly files where they exist, remote URLs otherwise.

    The fact join reads most columns of most rows, so streaming buys nothing
    over a one-time download -- and the repeated range requests earned an HTTP
    429 from the Hub. `getmonths` mirrors the files under `monthly/`; anything
    missing falls back to the URL so a partial mirror still builds.
    """
    local_dir = cache_dir / "monthly"
    out = []
    for month in months:
        local = local_dir / f"data-{month}.parquet"
        out.append(str(local) if local.exists() and local.stat().st_size > 1_000_000
                   else month_url(month))
    n_local = sum(1 for u in out if not u.startswith("http"))
    print(f"months: {n_local} local, {len(out) - n_local} remote", flush=True)
    return out


def build_facts(months: list[str], universe: list[str], cache_dir: Path) -> None:
    """Join events to causes and write the three hourly fact tables."""
    months = available_months(months)
    if not months:
        raise SystemExit("no published months in the requested range")
    con = connect(memory_limit="8GB")
    try:
        con.execute(
            "CREATE TEMP TABLE universe (station_name VARCHAR)"
        )
        con.executemany("INSERT INTO universe VALUES (?)", [(s,) for s in universe])

        cause_files = sorted((cache_dir / "causes").rglob("*.parquet"))
        if not cause_files:
            raise SystemExit(
                f"no cause shards in {cache_dir / 'causes'} -- run `facts.py causes` first"
            )
        # DuckDB refuses a prepared parameter inside CREATE VIEW, so the file
        # lists are inlined rather than bound.
        con.execute(
            f"CREATE TEMP VIEW causes AS SELECT * FROM read_parquet("
            f"{_sql_list([str(p) for p in cause_files])})"
        )
        print(f"causes: {len(cause_files)} day shards", flush=True)

        urls = month_sources(months, cache_dir)
        con.execute(
            f"""
            CREATE TEMP VIEW events AS
            SELECT e.*, {SERVICE_GROUP_SQL} AS service_group, {SERVICE_DATE_SQL} AS service_date
            FROM read_parquet({_sql_list(urls)}) e
            SEMI JOIN universe u ON u.station_name = e.station_name
            """
        )

        for name, keys in (
            ("hourly_station", "e.station_name AS station"),
            ("hourly_line", "e.service_group AS service_group"),
            ("hourly_pair", "e.service_group AS service_group, e.station_name AS station"),
        ):
            out = cache_dir / f"{name}.parquet"
            started = time.time()
            con.execute(
                f"COPY ({_agg_select(keys)}) TO '{out}' (FORMAT PARQUET, COMPRESSION ZSTD)"
            )
            n = con.execute(f"SELECT count(*) FROM read_parquet('{out}')").fetchone()[0]
            print(f"  {name}: {n:,} rows in {time.time()-started:.0f}s -> {out}", flush=True)
    finally:
        con.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the db_route fact cache.")
    parser.add_argument("stage", choices=("catchment", "causes", "universe", "facts", "all"))
    parser.add_argument("--start", default="2025-03-01", help="first day for cause extraction")
    parser.add_argument("--end", default="2026-08-31", help="last day for cause extraction")
    parser.add_argument("--months", default="", help="YYYY-MM,YYYY-MM range for the fact tables")
    parser.add_argument("--cache", default="data/facts", type=Path)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--top-n", type=int, default=400)
    parser.add_argument("--regions", default="munich",
                        help="comma-separated: " + ",".join(sorted(REGIONS)))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    start = dt.date.fromisoformat(args.start)
    end = dt.date.fromisoformat(args.end)
    months = (
        months_between(*args.months.split(","))
        if args.months
        else months_between(start.strftime("%Y-%m"), end.strftime("%Y-%m"))
    )
    args.cache.mkdir(parents=True, exist_ok=True)
    universe_path = args.cache / "station_universe.json"

    catchment_path = args.cache / "catchment_evas.json"
    if args.stage in ("catchment", "all") or (
        args.stage == "causes" and not catchment_path.exists()
    ):
        build_catchment(months[-1], catchment_path, regions=tuple(args.regions.split(',')))
    if args.stage in ("causes", "all"):
        evas = json.loads(catchment_path.read_text())["evas"]
        extract_range(
            start, end, args.cache, evas=evas, workers=args.workers, force=args.force
        )
    if args.stage in ("universe", "all"):
        build_station_universe(months, universe_path, top_n=args.top_n)
    if args.stage in ("facts", "all"):
        if not universe_path.exists():
            build_station_universe(months, universe_path, top_n=args.top_n)
        universe = json.loads(universe_path.read_text())["stations"]
        build_facts(months, universe, args.cache)
    return 0


if __name__ == "__main__":
    sys.exit(main())
