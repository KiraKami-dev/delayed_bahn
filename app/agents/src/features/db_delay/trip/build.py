"""Build trip delay examples: one train run, one target stop, one prediction moment.

Every input is computed from data timestamped before the prediction moment t0:
the run's own departure delays up to its last departed stop, arrival delays at
the target stop on earlier days, and hourly late shares in the hours before t0.
The target is the arrival delay at the target stop in whole minutes, or cancelled.

Timestamps are German local time and stay naive. The window holds only the
29 March 2026 spring-forward gap, which shows up as one empty hour.
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass, field, replace
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

LONG_DISTANCE = ("ICE", "IC", "EC")
LATE_MINUTES = 6
MAX_MINUTES = 999
HISTORY_LEVELS = ("pattern", "route", "type")


@dataclass(frozen=True)
class Config:
    """Everything that shapes the example set."""

    files: tuple[str, ...]
    examples_per_class: dict[str, int] = field(
        default_factory=lambda: {"long-distance": 112_000, "regional": 128_000, "S-Bahn": 80_000}
    )
    history_days: int = 30
    history_min_obs: int = 10
    series_hours: int = 72
    pre_departure_permille: int = 200
    pre_departure_max_minutes: int = 120
    same_train_days: int = 28  # earlier days of the same train number between the start station and the target
    corridor_hours: int = 3  # other trains that left the start station this recently and already arrived
    corridor_trains: int = 8
    train_start: str = "2025-11-15"
    val_start: str = "2026-05-02"
    test_start: str = "2026-06-02"
    # Upstream fills a missing change time with the planned time, so stops after the last
    # scrape look punctual. For a partial month, drop targets at or after this moment.
    label_cutoff: str | None = None


def log(message: str, started: float) -> None:
    """Print a progress line with elapsed seconds."""
    print(f"[{time.time() - started:6.0f}s] {message}", flush=True)


def load_stops(con: duckdb.DuckDBPyConnection, cfg: Config) -> None:
    """Load every stop of every train into one table, with arrival and departure delays."""
    files = "[" + ", ".join(f"'{f}'" for f in cfg.files) + "]"
    long_distance = ", ".join(f"'{t}'" for t in LONG_DISTANCE)
    con.execute(
        f"""
        CREATE OR REPLACE TABLE stops AS
        SELECT regexp_replace(id, '-[0-9]+$', '') AS run,
               train_line_station_num AS num,
               station_name AS station,
               train_type, train_number, line_number,
               final_destination_station AS dest,
               CASE WHEN train_type IN ({long_distance}) THEN 'long-distance'
                    WHEN train_type = 'S' THEN 'S-Bahn' ELSE 'regional' END AS cls,
               arrival_planned_time AS arr_pt, arrival_change_time AS arr_ct,
               departure_planned_time AS dep_pt, departure_change_time AS dep_ct,
               coalesce(arrival_is_canceled, false) AS arr_canc,
               coalesce(departure_is_canceled, false) AS dep_canc,
               round(date_diff('second', arrival_planned_time, arrival_change_time) / 60.0)::INTEGER AS arr_delay,
               round(date_diff('second', departure_planned_time, departure_change_time) / 60.0)::INTEGER AS dep_delay,
               delay_in_min AS delay,
               coalesce(departure_change_time, arrival_change_time, departure_planned_time, arrival_planned_time)
                   AS event_time
        FROM read_parquet({files})
        WHERE train_type IS DISTINCT FROM 'Bus'
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE runs AS
        SELECT run, any_value(train_type) AS train_type, any_value(train_number) AS train_number,
               any_value(line_number) AS line_number, any_value(cls) AS cls, any_value(dest) AS dest,
               arg_min(station, num) AS origin,
               -- Train type is part of the pattern, so an RE and an S-Bahn on the same stations stay apart.
               hash(any_value(train_type) || ':' || string_agg(station, '>' ORDER BY num))::VARCHAR AS pattern,
               count(*) AS n_stops
        FROM stops GROUP BY run
        """
    )


def uniform(expr: str, salt: str) -> str:
    """SQL for a deterministic pseudo-random number in [0, 1) derived from ``expr``."""
    return f"((hash({expr} || '|{salt}') % 1000000)::DOUBLE / 1000000)"


def sample_examples(con: duckdb.DuckDBPyConnection, cfg: Config) -> None:
    """Pick runs per class, a target stop per run, and a prediction moment before it."""
    counts = dict(con.execute("SELECT cls, count(*) FROM runs WHERE n_stops >= 2 GROUP BY 1").fetchall())
    fractions = {cls: min(1.0, cfg.examples_per_class[cls] / max(counts.get(cls, 0), 1)) for cls in cfg.examples_per_class}
    print("runs per class:", counts, "sampling fractions:", {k: round(v, 4) for k, v in fractions.items()})
    cases = " ".join(f"WHEN '{cls}' THEN {frac}" for cls, frac in fractions.items())
    con.execute(
        f"""
        CREATE OR REPLACE TABLE sruns AS
        SELECT * FROM runs
        WHERE n_stops >= 2 AND {uniform('run', 'sample')} < CASE cls {cases} ELSE 0 END
        """
    )
    # Target: any stop with a planned arrival, i.e. not the origin.
    con.execute(
        """
        CREATE OR REPLACE TABLE tgt AS
        SELECT run, num AS k_num, station AS k_station, arr_pt AS k_arr_pt, arr_delay AS k_arr_delay, arr_canc AS k_canc
        FROM (
            SELECT s.*, row_number() OVER (PARTITION BY s.run ORDER BY hash(s.run || '|k|' || s.num)) AS rn
            FROM stops s SEMI JOIN sruns r ON s.run = r.run
            WHERE s.arr_pt IS NOT NULL AND (s.arr_canc OR s.arr_delay IS NOT NULL)
        ) WHERE rn = 1
        """
    )
    # Last departed stop before the target, chosen at random among the candidates.
    con.execute(
        """
        CREATE OR REPLACE TABLE cur AS
        SELECT run, j_num, j_station, j_dep_ct, j_delay FROM (
            SELECT s.run, s.num AS j_num, s.station AS j_station, s.dep_ct AS j_dep_ct, s.dep_delay AS j_delay,
                   row_number() OVER (PARTITION BY s.run ORDER BY hash(s.run || '|j|' || s.num)) AS rn
            FROM stops s JOIN tgt t ON s.run = t.run
            WHERE s.num < t.k_num AND s.dep_ct IS NOT NULL AND s.dep_delay IS NOT NULL AND NOT s.dep_canc
        ) WHERE rn = 1
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE TABLE ex AS
        WITH fd AS (
            SELECT s.run, min(s.num) AS first_num, arg_min(s.dep_pt, s.num) AS first_dep_pt,
                   arg_min(s.station, s.num) AS first_station
            FROM stops s SEMI JOIN sruns r ON s.run = r.run
            WHERE s.dep_pt IS NOT NULL GROUP BY s.run
        ),
        base AS (
            SELECT r.run, r.cls, r.train_type, r.train_number, r.line_number, r.origin, r.dest, r.pattern,
                   t.k_num, t.k_station, t.k_arr_pt, t.k_arr_delay, t.k_canc,
                   c.j_num, c.j_station, c.j_dep_ct, c.j_delay,
                   fd.first_num, fd.first_dep_pt, fd.first_station,
                   (c.j_num IS NULL OR hash(r.run || '|pre') % 1000 < {cfg.pre_departure_permille}) AS pre_departure
            FROM sruns r JOIN tgt t USING (run) JOIN fd USING (run) LEFT JOIN cur c USING (run)
            WHERE fd.first_num < t.k_num
        ),
        timed AS (
            SELECT *,
                   CASE WHEN pre_departure
                        THEN first_dep_pt - to_minutes((hash(run || '|lead') % {cfg.pre_departure_max_minutes + 1})::BIGINT)
                        ELSE j_dep_ct END AS t0
            FROM base
        )
        SELECT row_number() OVER (ORDER BY run) AS example_id, *,
               CASE WHEN t0 >= TIMESTAMP '{cfg.train_start}' AND t0 < TIMESTAMP '{cfg.val_start}' - INTERVAL 1 DAY THEN 'train'
                    WHEN t0 >= TIMESTAMP '{cfg.val_start}' AND t0 < TIMESTAMP '{cfg.test_start}' - INTERVAL 1 DAY THEN 'validation'
                    WHEN t0 >= TIMESTAMP '{cfg.test_start}' THEN 'test' END AS split
        FROM timed
        """
    )
    con.execute("DELETE FROM ex WHERE split IS NULL")
    if cfg.label_cutoff:
        con.execute(f"DELETE FROM ex WHERE k_arr_pt >= TIMESTAMP '{cfg.label_cutoff}' "
                    f"OR t0 >= TIMESTAMP '{cfg.label_cutoff}'")


START_STATION = "CASE WHEN e.pre_departure OR e.j_station IS NULL THEN e.first_station ELSE e.j_station END"


def attach_corridor(con: duckdb.DuckDBPyConnection, cfg: Config) -> None:
    """Delay gained between the start station and the target stop, by earlier runs of the same train
    number on previous days and by other trains that made that trip in the hours before t0.

    The start station is the first station before departure and the last departed station otherwise.
    A gain is the arrival delay at the target minus the departure delay at the start station. Every
    counted arrival happened strictly before t0: a late run from yesterday can arrive after it.
    """
    con.execute(
        f"""
        CREATE OR REPLACE TABLE ex_same AS
        WITH e AS (
            SELECT e.example_id, e.t0, e.train_type, e.train_number, e.k_station, {START_STATION} AS f_station
            FROM ex e
        ),
        starts AS (
            SELECT e.example_id, e.t0, e.k_station, a.run, a.num, a.dep_delay,
                   date_diff('day', CAST(a.dep_pt AS DATE), CAST(e.t0 AS DATE)) AS o
            FROM e JOIN stops a ON a.train_type = e.train_type AND a.train_number = e.train_number
                 AND a.station = e.f_station
            WHERE CAST(a.dep_pt AS DATE) < CAST(e.t0 AS DATE)
                  AND CAST(a.dep_pt AS DATE) >= CAST(e.t0 AS DATE) - {cfg.same_train_days}
                  AND a.dep_ct IS NOT NULL AND a.dep_ct < e.t0 AND a.dep_delay IS NOT NULL AND NOT a.dep_canc
        ),
        days AS (
            SELECT s.example_id, s.o, median(b.arr_delay - s.dep_delay) AS gain
            FROM starts s JOIN stops b ON b.run = s.run AND b.station = s.k_station AND b.num > s.num
            WHERE b.arr_ct IS NOT NULL AND b.arr_ct < s.t0 AND b.arr_delay IS NOT NULL AND NOT b.arr_canc
            GROUP BY ALL
        )
        SELECT example_id, list(gain ORDER BY o) AS gains, list(o ORDER BY o) AS offsets
        FROM days GROUP BY example_id
        """
    )
    # Departures bucketed by hour, so the corridor join matches on station and hour instead of
    # scanning every departure a busy station ever had.
    con.execute(
        """
        CREATE OR REPLACE TABLE dep_hour AS
        SELECT run, num, station, dep_ct, dep_delay, date_trunc('hour', dep_ct) AS hr
        FROM stops WHERE dep_ct IS NOT NULL AND dep_delay IS NOT NULL AND NOT dep_canc
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE TABLE ex_corr AS
        WITH e AS (
            SELECT e.example_id, e.run, e.t0, e.k_station, {START_STATION} AS f_station, date_trunc('hour', e.t0) - to_hours(t.h::BIGINT) AS hr
            FROM ex e CROSS JOIN range(0, {cfg.corridor_hours + 1}) t(h)
        ),
        starts AS (
            SELECT e.example_id, e.t0, e.k_station, a.run, a.num, a.dep_delay
            FROM e JOIN dep_hour a ON a.station = e.f_station AND a.hr = e.hr
            WHERE a.run <> e.run AND a.dep_ct >= e.t0 - to_hours({cfg.corridor_hours}) AND a.dep_ct < e.t0
        ),
        cand AS (
            SELECT s.example_id, b.arr_delay - s.dep_delay AS gain, b.arr_delay,
                   row_number() OVER (PARTITION BY s.example_id ORDER BY b.arr_ct DESC, s.run) AS rn
            FROM starts s JOIN stops b ON b.run = s.run AND b.station = s.k_station AND b.num > s.num
            WHERE b.arr_ct IS NOT NULL AND b.arr_ct < s.t0 AND b.arr_delay IS NOT NULL AND NOT b.arr_canc
        )
        SELECT example_id, list(gain ORDER BY rn DESC) AS gains, list(arr_delay ORDER BY rn DESC) AS arr_delays
        FROM cand WHERE rn <= {cfg.corridor_trains} GROUP BY example_id
        """
    )


def attach_sequences(con: duckdb.DuckDBPyConnection, cfg: Config) -> None:
    """Attach the run so far, key history, and station and network hours to every example."""
    con.execute(
        """
        CREATE OR REPLACE TABLE stop_plan AS
        SELECT run, num,
               date_diff('minute', dep_pt, lead(arr_pt) OVER (PARTITION BY run ORDER BY num)) AS run_next,
               date_diff('minute', arr_pt, dep_pt) AS dwell
        FROM stops
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE ex_run AS
        SELECT e.example_id, list(s.dep_delay ORDER BY s.num) AS run_delays,
               -- The planned trajectory alongside the delays: running time to the next stop, dwell,
               -- and planned minutes left to the target at each departure. Channels for the encoder.
               list(coalesce(sp.run_next, 0) ORDER BY s.num) AS run_plan_next,
               list(coalesce(sp.dwell, 0) ORDER BY s.num) AS run_plan_dwell,
               list(date_diff('minute', s.dep_pt, e.k_arr_pt) ORDER BY s.num) AS run_plan_left
        FROM ex e JOIN stops s ON s.run = e.run LEFT JOIN stop_plan sp ON sp.run = s.run AND sp.num = s.num
        WHERE NOT e.pre_departure AND s.num <= e.j_num AND s.dep_ct IS NOT NULL
              AND s.dep_delay IS NOT NULL AND NOT s.dep_canc AND s.dep_ct <= e.t0
        GROUP BY e.example_id
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE ex_prev AS
        WITH cand AS (
            -- Trains of the same type towards the same destination that were due at the target
            -- stop in the six hours before ours and had actually arrived by the prediction moment.
            SELECT e.example_id, s.arr_delay, date_diff('minute', s.arr_pt, e.k_arr_pt) AS gap,
                   row_number() OVER (PARTITION BY e.example_id ORDER BY s.arr_pt DESC) AS rn
            FROM ex e JOIN stops s ON s.station = e.k_station AND s.train_type = e.train_type
                 AND coalesce(s.dest, '') = coalesce(e.dest, '') AND s.run <> e.run
            WHERE s.arr_pt < e.k_arr_pt AND s.arr_pt >= e.k_arr_pt - INTERVAL 6 HOUR
                  AND s.arr_ct IS NOT NULL AND s.arr_ct <= e.t0 AND NOT s.arr_canc AND s.arr_delay IS NOT NULL
        )
        SELECT example_id, list(arr_delay ORDER BY gap DESC) AS prev_arr_delays, list(gap ORDER BY gap DESC) AS prev_gaps
        FROM cand WHERE rn <= 5 GROUP BY example_id
        """
    )
    attach_corridor(con, cfg)
    con.execute(
        """
        CREATE OR REPLACE TABLE ex_via AS
        SELECT e.example_id, list(s.station ORDER BY s.num) AS via
        FROM ex e JOIN stops s ON s.run = e.run
        WHERE s.num > coalesce(CASE WHEN e.pre_departure THEN NULL ELSE e.j_num END, e.first_num) AND s.num < e.k_num
        GROUP BY e.example_id
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE arr_day AS
        SELECT s.station, s.train_type, r.pattern, s.train_type || '|' || r.origin || '|' || coalesce(r.dest, '') AS route,
               CAST(s.arr_pt AS DATE) AS day, greatest(s.arr_delay, 0) AS d, s.arr_canc AS canc
        FROM stops s JOIN runs r USING (run)
        WHERE s.arr_pt IS NOT NULL AND (s.arr_canc OR s.arr_delay IS NOT NULL)
        """
    )
    ex_keys = {"pattern": "e.pattern", "route": "e.train_type || '|' || e.origin || '|' || coalesce(e.dest, '')", "type": "e.train_type"}
    day_keys = {"pattern": "pattern", "route": "route", "type": "train_type"}
    for level in HISTORY_LEVELS:
        con.execute(
            f"""
            CREATE OR REPLACE TABLE h_{level} AS
            SELECT {day_keys[level]} AS key, station, day,
                   median(d) FILTER (WHERE NOT canc) AS med,
                   count(*) FILTER (WHERE NOT canc) AS n,
                   count(*) FILTER (WHERE canc) AS nc
            FROM arr_day GROUP BY ALL
            """
        )
        con.execute(
            f"""
            CREATE OR REPLACE TABLE ex_h_{level} AS
            WITH days AS (
                SELECT e.example_id, e.k_station AS station, {ex_keys[level]} AS key,
                       CAST(e.t0 AS DATE) - t.o::INTEGER AS day, t.o
                FROM ex e CROSS JOIN range(1, {cfg.history_days + 1}) t(o)
            )
            SELECT days.example_id, list(h.med ORDER BY days.o) AS med,
                   sum(coalesce(h.n, 0)) AS n_obs, sum(coalesce(h.nc, 0)) AS n_canc
            FROM days LEFT JOIN h_{level} h ON h.key = days.key AND h.station = days.station AND h.day = days.day
            GROUP BY days.example_id
            """
        )
    con.execute(
        f"""
        CREATE OR REPLACE TABLE st_hour AS
        SELECT station, date_trunc('hour', event_time) AS hr, avg((delay >= {LATE_MINUTES})::DOUBLE) AS late, count(*) AS n
        FROM stops WHERE NOT arr_canc AND NOT dep_canc GROUP BY ALL
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE TABLE cls_hour AS
        SELECT cls, date_trunc('hour', event_time) AS hr, avg((delay >= {LATE_MINUTES})::DOUBLE) AS late, count(*) AS n
        FROM stops WHERE NOT arr_canc AND NOT dep_canc GROUP BY ALL
        """
    )
    for name, table, key in (("st", "st_hour", "station"), ("nw", "cls_hour", "cls")):
        ex_key = "e.k_station" if key == "station" else "e.cls"
        con.execute(
            f"""
            CREATE OR REPLACE TABLE ex_{name} AS
            WITH hrs AS (
                SELECT e.example_id, {ex_key} AS key, date_trunc('hour', e.t0) - to_hours(t.o::BIGINT) AS hr, t.o
                FROM ex e CROSS JOIN range(1, {cfg.series_hours + 1}) t(o)
            )
            SELECT hrs.example_id, list(h.late ORDER BY hrs.o) AS late, list(coalesce(h.n, 0) ORDER BY hrs.o) AS n
            FROM hrs LEFT JOIN {table} h ON h.{key} = hrs.key AND h.hr = hrs.hr
            GROUP BY hrs.example_id
            """
        )


def fixed(table: pa.Table, column: str, length: int) -> np.ndarray:
    """Turn a fixed-length list column into a float array of shape (rows, length), nulls as NaN."""
    flat = table[column].combine_chunks().flatten()
    values = flat.to_numpy(zero_copy_only=False).astype(np.float64)
    return values.reshape(-1, length)


def weighted_share(late: np.ndarray, counts: np.ndarray, hours: int) -> np.ndarray:
    """Late share over the most recent ``hours`` columns, weighted by stop counts."""
    lt = np.nan_to_num(late[:, -hours:])
    n = counts[:, -hours:]
    total = n.sum(axis=1)
    return np.where(total > 0, (lt * n).sum(axis=1) / np.maximum(total, 1), 0.0)


def assemble(con: duckdb.DuckDBPyConnection, cfg: Config) -> pa.Table:
    """Join everything, choose the history level, and compute tabular features."""
    columns = ["example_id", "split", "run", "cls", "train_type", "train_number", "line_number", "origin", "dest",
               "first_station", "j_station", "k_station", "k_num", "j_num", "first_num", "t0", "k_arr_pt",
               "k_arr_delay", "k_canc", "pre_departure"]
    select = ", ".join(f"e.{c}" for c in columns)
    level_cols = ", ".join(
        f"h_{lv}.med AS med_{lv}, h_{lv}.n_obs AS n_{lv}, h_{lv}.n_canc AS c_{lv}" for lv in HISTORY_LEVELS
    )
    table = con.execute(
        f"""
        SELECT {select}, r.run_delays, r.run_plan_next, r.run_plan_dwell, r.run_plan_left, v.via,
               p.prev_arr_delays, p.prev_gaps, {level_cols},
               st.late AS st_late, st.n AS st_n, nw.late AS nw_late, nw.n AS nw_n,
               sm.gains AS same_gains, sm.offsets AS same_offsets, co.gains AS corr_gains, co.arr_delays AS corr_arr
        FROM ex e
        LEFT JOIN ex_run r USING (example_id) LEFT JOIN ex_via v USING (example_id)
        {' '.join(f'JOIN ex_h_{lv} h_{lv} USING (example_id)' for lv in HISTORY_LEVELS)}
        JOIN ex_st st USING (example_id) JOIN ex_nw nw USING (example_id)
        LEFT JOIN ex_prev p USING (example_id)
        LEFT JOIN ex_same sm USING (example_id) LEFT JOIN ex_corr co USING (example_id)
        ORDER BY example_id
        """
    ).to_arrow_table()
    rows = table.num_rows
    out = {c: table[c] for c in columns}

    # History: first level with enough observations; oldest day first.
    chosen = np.full((rows, cfg.history_days), np.nan)
    level = np.array(["none"] * rows, dtype=object)
    n_obs = np.zeros(rows)
    n_canc = np.zeros(rows)
    for lv in reversed(HISTORY_LEVELS):  # most specific last, so it wins
        med = fixed(table, f"med_{lv}", cfg.history_days)[:, ::-1]
        n = table[f"n_{lv}"].to_numpy(zero_copy_only=False).astype(np.float64)
        c = table[f"c_{lv}"].to_numpy(zero_copy_only=False).astype(np.float64)
        ok = n >= cfg.history_min_obs
        chosen[ok] = med[ok]
        level[ok] = lv
        n_obs[ok] = n[ok]
        n_canc[ok] = c[ok]
    # The 30-day statistics keep their meaning when the history window is longer; the longer
    # window and the last week are separate columns, so the prompt can speak of several scales.
    recent = chosen[:, -min(30, cfg.history_days):]
    with np.errstate(all="ignore"):
        hist_median = np.nan_to_num(np.nanmedian(recent, axis=1))
        hist_p90 = np.nan_to_num(np.nanpercentile(recent, 90, axis=1))
        hist_mean = np.nan_to_num(np.nanmean(recent, axis=1))
        hist_median_long = np.nan_to_num(np.nanmedian(chosen, axis=1))
        hist_p90_long = np.nan_to_num(np.nanpercentile(chosen, 90, axis=1))
        hist_median_7 = np.nanmedian(chosen[:, -7:], axis=1)
    hist_median_7 = np.where(np.isnan(hist_median_7), hist_median, hist_median_7)
    hist_days = np.isfinite(chosen).sum(axis=1)
    filled = pd.DataFrame(chosen).ffill(axis=1).to_numpy()
    filled = np.where(np.isnan(filled), hist_median[:, None], filled)

    st_late = fixed(table, "st_late", cfg.series_hours)[:, ::-1]
    st_n = fixed(table, "st_n", cfg.series_hours)[:, ::-1]
    nw_late = fixed(table, "nw_late", cfg.series_hours)[:, ::-1]
    nw_n = fixed(table, "nw_n", cfg.series_hours)[:, ::-1]

    def same_hour_share(late: np.ndarray, n: np.ndarray) -> np.ndarray:
        """Share of late stops at the planned arrival's hour of day, over the whole hourly window.

        The series ends with the hour before the prediction moment, so the column of hour h sits
        at offsets (t0 hour - h) mod 24 from the end, and every 24 hours before that."""
        t0_hour = pd.to_datetime(table["t0"].to_pandas()).dt.hour.to_numpy()
        arr_hour = pd.to_datetime(table["k_arr_pt"].to_pandas()).dt.hour.to_numpy()
        hours = late.shape[1]
        offsets = (t0_hour - 1 - arr_hour) % 24  # index from the end of the series
        idx = np.arange(hours)[None, :]
        mask = ((hours - 1 - idx) % 24) == offsets[:, None]
        weights = np.where(mask & np.isfinite(late), n, 0.0)
        return np.where(weights.sum(axis=1) > 0, np.nansum(late * weights, axis=1) / np.maximum(weights.sum(axis=1), 1), 0.0)

    run_delays = table["run_delays"].to_pylist()
    prev = [list(d) if d else [] for d in table["prev_arr_delays"].to_pylist()]
    prev_gaps = [list(d) if d else [] for d in table["prev_gaps"].to_pylist()]
    prev_n = np.array([len(d) for d in prev], dtype=np.float64)
    prev_last = np.array([d[-1] if d else 0.0 for d in prev], dtype=np.float64)
    prev_mean = np.array([float(np.mean(d)) if d else 0.0 for d in prev], dtype=np.float64)
    prev_gap_last = np.array([g[-1] if g else 0.0 for g in prev_gaps], dtype=np.float64)
    current = np.array([d[-1] if d else 0 for d in run_delays], dtype=np.float64)
    max_so_far = np.array([max(d) if d else 0 for d in run_delays], dtype=np.float64)
    change3 = np.array([d[-1] - d[max(0, len(d) - 4)] if d else 0 for d in run_delays], dtype=np.float64)
    run_len = np.array([len(d) if d else 0 for d in run_delays], dtype=np.float64)

    # Same train number on earlier days: one gain per day, oldest first, gaps forward-filled like the history.
    days = cfg.same_train_days
    same = np.full((rows, days), np.nan)
    gains = table["same_gains"].combine_chunks()
    lengths = gains.value_lengths().fill_null(0).to_numpy(zero_copy_only=False)
    row_idx = np.repeat(np.arange(rows), lengths)
    offsets = table["same_offsets"].combine_chunks().flatten().to_numpy(zero_copy_only=False).astype(np.int64)
    same[row_idx, days - offsets] = gains.flatten().to_numpy(zero_copy_only=False).astype(np.float64)
    same_days = np.isfinite(same).sum(axis=1)
    with np.errstate(all="ignore"):
        same_median = np.nanmedian(same, axis=1)
        same_median_7 = np.nanmedian(same[:, -7:], axis=1)
    same_median_7 = np.where(np.isnan(same_median_7), same_median, same_median_7)
    same_filled = pd.DataFrame(same).ffill(axis=1).to_numpy()
    same_filled = np.where(np.isnan(same_filled), np.nan_to_num(same_median)[:, None], same_filled)
    # Other trains on the corridor that already arrived: the latest few, oldest arrival first.
    corr = [list(d) if d else [] for d in table["corr_gains"].to_pylist()]
    corr_arr = [list(d) if d else [] for d in table["corr_arr"].to_pylist()]
    corr_n = np.array([len(d) for d in corr], dtype=np.float64)
    corr_mean = np.array([float(np.mean(d)) if d else np.nan for d in corr], dtype=np.float64)
    corr_last = np.array([float(d[-1]) if d else np.nan for d in corr], dtype=np.float64)

    t0 = pd.to_datetime(table["t0"].to_pandas())
    arr = pd.to_datetime(table["k_arr_pt"].to_pandas())
    pre = table["pre_departure"].to_numpy(zero_copy_only=False)
    j_num = table["j_num"].to_pandas().to_numpy(dtype=np.float64, na_value=np.nan)
    first_num = table["first_num"].to_numpy(zero_copy_only=False).astype(np.float64)
    k_num = table["k_num"].to_numpy(zero_copy_only=False).astype(np.float64)
    from_num = np.where(pre | np.isnan(j_num), first_num, j_num)
    raw_delay = table["k_arr_delay"].to_pandas().to_numpy(dtype=np.float64, na_value=np.nan)
    cancelled = table["k_canc"].to_numpy(zero_copy_only=False)

    out |= {
        "run_delays": pa.array([[float(x) for x in d] if d else [] for d in run_delays], type=pa.list_(pa.float32())),
        "run_plan_next": pa.array([[float(x) for x in d] if d else [] for d in table["run_plan_next"].to_pylist()], type=pa.list_(pa.float32())),
        "run_plan_dwell": pa.array([[float(x) for x in d] if d else [] for d in table["run_plan_dwell"].to_pylist()], type=pa.list_(pa.float32())),
        "run_plan_left": pa.array([[float(x) for x in d] if d else [] for d in table["run_plan_left"].to_pylist()], type=pa.list_(pa.float32())),
        "prev_arr_delays": pa.array([[float(x) for x in d] for d in prev], type=pa.list_(pa.float32())),
        "prev_gaps": pa.array([[float(x) for x in g] for g in prev_gaps], type=pa.list_(pa.float32())),
        "prev_n": pa.array(prev_n),
        "prev_last": pa.array(prev_last),
        "prev_mean": pa.array(prev_mean),
        "prev_gap_last": pa.array(prev_gap_last),
        "same_train_gains": pa.FixedSizeListArray.from_arrays(pa.array(same_filled.astype(np.float32).ravel()), days),
        "same_train_days": pa.array(same_days.astype(np.float64)),
        "same_train_gain_median": pa.array(same_median),
        "same_train_gain_median_7": pa.array(same_median_7),
        "same_train_expected": pa.array(np.clip(current + same_median, 0, None)),
        "corridor_gains": pa.array([[float(x) for x in d] for d in corr], type=pa.list_(pa.float32())),
        "corridor_arr_delays": pa.array([[float(x) for x in d] for d in corr_arr], type=pa.list_(pa.float32())),
        "corridor_n": pa.array(corr_n),
        "corridor_gain_mean": pa.array(corr_mean),
        "corridor_gain_last": pa.array(corr_last),
        "via": table["via"],
        "hist_series": pa.FixedSizeListArray.from_arrays(pa.array(filled.astype(np.float32).ravel()), cfg.history_days),
        "station_series": pa.FixedSizeListArray.from_arrays(pa.array(np.nan_to_num(st_late).astype(np.float32).ravel()), cfg.series_hours),
        "network_series": pa.FixedSizeListArray.from_arrays(pa.array(np.nan_to_num(nw_late).astype(np.float32).ravel()), cfg.series_hours),
        "hist_level": pa.array(level.astype(str)),
        "hist_n": pa.array(n_obs),
        "hist_cancel_share": pa.array(np.where(n_obs + n_canc > 0, n_canc / np.maximum(n_obs + n_canc, 1), 0.0)),
        "hist_median": pa.array(hist_median),
        "hist_p90": pa.array(hist_p90),
        "hist_median_long": pa.array(hist_median_long),
        "hist_p90_long": pa.array(hist_p90_long),
        "hist_median_7": pa.array(hist_median_7),
        "hist_window_days": pa.array(np.full(rows, cfg.history_days)),
        "station_late_same_hour": pa.array(same_hour_share(st_late, st_n)),
        "network_late_same_hour": pa.array(same_hour_share(nw_late, nw_n)),
        "hist_mean": pa.array(hist_mean),
        "hist_days": pa.array(hist_days.astype(np.float64)),
        "current_delay": pa.array(current),
        "max_delay_so_far": pa.array(max_so_far),
        "delay_change_3": pa.array(change3),
        "run_len": pa.array(run_len),
        "lead_minutes": pa.array(((arr - t0).dt.total_seconds() / 60.0).to_numpy()),
        "stops_ahead": pa.array(k_num - from_num),
        "arr_hour": pa.array(arr.dt.hour.to_numpy().astype(np.float64)),
        "arr_weekday": pa.array(arr.dt.weekday.to_numpy().astype(np.float64)),
        "station_late_3h": pa.array(weighted_share(st_late, st_n, 3)),
        "station_late_24h": pa.array(weighted_share(st_late, st_n, 24)),
        "station_late_72h": pa.array(weighted_share(st_late, st_n, 72)),
        "station_stops_24h": pa.array(st_n[:, -24:].sum(axis=1)),
        "network_late_3h": pa.array(weighted_share(nw_late, nw_n, 3)),
        "network_late_24h": pa.array(weighted_share(nw_late, nw_n, 24)),
        "network_late_72h": pa.array(weighted_share(nw_late, nw_n, 72)),
        "target_minutes": pa.array(np.where(cancelled, np.nan, np.clip(np.nan_to_num(raw_delay), 0, MAX_MINUTES))),
        "cancelled": pa.array(cancelled),
    }
    return pa.table(out)


def build(cfg: Config, out_path: Path, threads: int | None = None) -> pa.Table:
    """Run the whole pipeline and write the examples to parquet."""
    started = time.time()
    con = duckdb.connect()
    if threads:
        con.execute(f"SET threads = {threads}")
    load_stops(con, cfg)
    log(f"stops loaded: {con.execute('SELECT count(*) FROM stops').fetchone()[0]:,}", started)
    sample_examples(con, cfg)
    log(f"examples sampled: {con.execute('SELECT split, cls, count(*) FROM ex GROUP BY ALL ORDER BY ALL').fetchall()}", started)
    attach_sequences(con, cfg)
    log("sequences attached", started)
    table = assemble(con, cfg)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, out_path)
    log(f"wrote {table.num_rows:,} examples to {out_path}", started)
    return table


def main() -> None:
    """Build from the monthly processed files in a directory."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", default="data/raw")
    parser.add_argument("--out", default="data/trip/examples.parquet")
    parser.add_argument("--months", nargs="*", default=[
        "2025-11", "2025-12", "2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08",
    ])
    parser.add_argument("--scale", type=float, default=1.0, help="multiply the per-class example targets")
    parser.add_argument("--train-start")
    parser.add_argument("--val-start")
    parser.add_argument("--test-start")
    parser.add_argument("--label-cutoff", help="drop targets planned at or after this local time")
    parser.add_argument("--series-hours", type=int, help="length of the hourly station and network series (default 72)")
    parser.add_argument("--history-days", type=int, help="length of the daily route history (default 30)")
    args = parser.parse_args()
    files = tuple(str(Path(args.raw) / f"data-{m}.parquet") for m in args.months)
    base = Config(files=files)
    overrides = {key: value for key, value in {"train_start": args.train_start, "val_start": args.val_start,
                 "test_start": args.test_start, "label_cutoff": args.label_cutoff}.items() if value}
    if args.series_hours:
        overrides["series_hours"] = args.series_hours
    if args.history_days:
        overrides["history_days"] = args.history_days
    cfg = replace(base, examples_per_class={k: int(v * args.scale) for k, v in base.examples_per_class.items()},
                  **overrides)
    build(cfg, Path(args.out))


if __name__ == "__main__":
    main()
