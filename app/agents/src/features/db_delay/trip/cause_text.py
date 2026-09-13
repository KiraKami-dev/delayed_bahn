"""Add one delay-cause sentence to built examples, from IRIS cause codes and disruption notices.

The cause shards come from `db_route/remote_extract.py` (one parquet per day with `stop_id`,
`codes`, `families`, and one with notices). Cause codes carry no timestamp and are the archived
final state of a stop, so only stops that were already passed at the prediction moment `t0` count:

- earlier stops of the same train, up to the last departed stop `j` (never the target stop);
- other trains at the target station whose planned and actual time lie in the 3 hours before t0.

A notice counts only if it was issued at or before t0, its validity window covers the planned
arrival at the target stop, and it was attached to a stop at the target station passed before t0.
The sentence lands in the `cause_text` column, which `prompts.rationale` appends; empty when nothing.

    python trip/cause_text.py --examples data/trip/examples_v4.parquet --raw data/raw \\
        --shards causes_out/db_route --out data/trip/examples_v6.parquet
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

FAMILY_TEXT = {
    "knock_on": "knock-on delay",
    "technical": "technical fault",
    "works": "construction work",
    "weather": "weather",
    "staff": "staff shortage",
    "external": "incident on the line",
}
STATION_HOURS = 3
NOTICE_ATTACH_HOURS = 24


def counted(families: list[str], counts: list[int]) -> str:
    """'knock-on delay (3x), technical fault' ordered by count."""
    pairs = sorted(zip(counts, families), key=lambda p: (-p[0], p[1]))[:3]
    return ", ".join(FAMILY_TEXT.get(f, f) + (f" ({n}x)" if n > 1 else "") for n, f in pairs)


def build(examples: Path, raw: Path, shards: Path, out: Path, threads: int) -> None:
    started = time.time()
    con = duckdb.connect()
    con.execute(f"SET threads = {threads}")
    con.execute("SET preserve_insertion_order = false")
    months = sorted(str(p) for p in raw.glob("data-*.parquet"))
    con.execute(f"""
        CREATE TABLE ex AS SELECT example_id, split, run, j_num, pre_departure, k_station, k_arr_pt, t0
        FROM read_parquet('{examples}')""")
    con.execute(f"""
        CREATE TABLE codes AS
        SELECT stop_id, list_distinct(flatten(list(families))) AS fams
        FROM read_parquet('{shards}/causes/all/*.parquet')
        WHERE len(families) > 0 GROUP BY stop_id""")
    print(f"stops with cause codes: {con.execute('SELECT count(*) FROM codes').fetchone()[0]:,}", flush=True)
    notices = pq.read_table(str(shards / "notices" / "all")).to_pandas()
    for col in ("valid_from", "valid_to", "issued_at"):
        notices[col] = notices[col].dt.tz_convert("Europe/Berlin").dt.tz_localize(None)
    notices = notices.drop_duplicates("notice_id").explode("stop_ids").rename(columns={"stop_ids": "stop_id"})
    con.register("notices_df", notices)
    con.execute("CREATE TABLE notice_stops AS SELECT * FROM notices_df")
    print(f"notice attachments: {len(notices):,}", flush=True)
    # Station and times of every stop that carries a code or a notice.
    con.execute(f"""
        CREATE TABLE st AS
        SELECT id AS stop_id, regexp_replace(id, '-[0-9]+$', '') AS run,
               any_value(train_line_station_num) AS num, any_value(station_name) AS station,
               max(coalesce(arrival_planned_time, departure_planned_time)) AS pt,
               max(coalesce(arrival_change_time, departure_change_time,
                            arrival_planned_time, departure_planned_time)) AS ct
        FROM read_parquet({months})
        WHERE id IN (SELECT stop_id FROM codes UNION SELECT stop_id FROM notice_stops)
        GROUP BY id""")
    con.execute("CREATE TABLE sc AS SELECT st.*, codes.fams FROM st JOIN codes USING (stop_id)")
    print(f"located stops: {con.execute('SELECT count(*) FROM sc').fetchone()[0]:,} "
          f"({time.time() - started:.0f}s)", flush=True)

    same_run = con.execute("""
        WITH hits AS (
            SELECT e.example_id, unnest(sc.fams) AS fam
            FROM ex e JOIN sc ON sc.run = e.run
            WHERE NOT e.pre_departure AND sc.num <= e.j_num AND sc.pt <= e.t0 AND sc.ct <= e.t0)
        SELECT example_id, list(fam ORDER BY fam) AS fams, list(n ORDER BY fam) AS counts
        FROM (SELECT example_id, fam, count(*) AS n FROM hits GROUP BY ALL) GROUP BY example_id""").df()
    station = con.execute(f"""
        WITH hits AS (
            SELECT DISTINCT example_id, other, fam FROM (
                SELECT e.example_id, sc.run AS other, unnest(sc.fams) AS fam
                FROM ex e JOIN sc ON sc.station = e.k_station
                WHERE sc.run <> e.run AND sc.pt < e.t0 AND sc.ct < e.t0
                  AND sc.ct >= e.t0 - INTERVAL {STATION_HOURS} HOUR))
        SELECT example_id, list(fam) AS fams, count(DISTINCT other) AS trains
        FROM hits GROUP BY example_id""").df()
    notice = con.execute(f"""
        SELECT e.example_id, list(DISTINCT n.category) AS cats
        FROM ex e
        JOIN st ON st.station = e.k_station AND st.run <> e.run AND st.pt < e.t0 AND st.ct < e.t0
               AND st.ct >= e.t0 - INTERVAL {NOTICE_ATTACH_HOURS} HOUR
        JOIN notice_stops n ON n.stop_id = st.stop_id
        WHERE n.issued_at IS NOT NULL AND n.issued_at <= e.t0
          AND n.valid_from <= e.k_arr_pt AND n.valid_to >= e.k_arr_pt AND n.category IS NOT NULL
        GROUP BY e.example_id""").df()
    print(f"joined ({time.time() - started:.0f}s)", flush=True)

    ex = con.execute("SELECT example_id, split FROM ex").df()
    text = {i: [] for i in ex.example_id}
    for row in same_run.itertuples():
        text[row.example_id].append(f"Earlier stops of this train report: {counted(list(row.fams), list(row.counts))}.")
    for row in station.itertuples():
        # One entry per (train, family), so the counts are trains per family.
        agg: dict[str, int] = {}
        for f in row.fams:
            agg[f] = agg.get(f, 0) + 1
        trains = int(row.trains)
        text[row.example_id].append(
            f"In the last {STATION_HOURS} hours {trains} other train{'s' if trains > 1 else ''} at this station "
            f"reported causes: {counted(list(agg), list(agg.values()))}.")
    for row in notice.itertuples():
        cats = sorted(c for c in row.cats if c)[:2]
        if cats:
            text[row.example_id].append(f"A disruption notice covers this station at the planned arrival: {', '.join(cats)}.")
    ex["cause_text"] = [" ".join(text[i]) for i in ex.example_id]
    ex["has"] = ex.cause_text.str.len() > 0
    ex["same_run"] = ex.example_id.isin(same_run.example_id)
    ex["station"] = ex.example_id.isin(station.example_id)
    ex["notice"] = ex.example_id.isin(notice.example_id)
    print(ex.groupby("split")[["has", "same_run", "station", "notice"]].mean().round(3).to_string())
    print(ex.loc[ex.has, "cause_text"].sample(5, random_state=0).to_string())

    table = pq.read_table(examples)
    order = pd.Series(ex.cause_text.values, index=ex.example_id.values)
    ids = table.column("example_id").to_numpy()
    table = table.append_column("cause_text", pa.array(order.loc[ids].tolist(), pa.string()))
    pq.write_table(table, out, compression="zstd")
    print(f"wrote {out} ({time.time() - started:.0f}s)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--examples", type=Path, default=Path("data/trip/examples_v4.parquet"))
    parser.add_argument("--raw", type=Path, default=Path("data/raw"))
    parser.add_argument("--shards", type=Path, required=True, help="directory holding causes/all and notices/all")
    parser.add_argument("--out", type=Path, default=Path("data/trip/examples_v6.parquet"))
    parser.add_argument("--threads", type=int, default=12)
    args = parser.parse_args()
    build(args.examples, args.raw, args.shards, args.out, args.threads)


if __name__ == "__main__":
    main()
