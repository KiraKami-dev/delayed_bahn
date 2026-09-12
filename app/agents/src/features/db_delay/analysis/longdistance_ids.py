"""What identifies a long-distance service in the dataset, and which key predicts best?"""

import duckdb

c = duckdb.connect()
c.execute("INSTALL httpfs; LOAD httpfs;")
RAW = (
    "https://huggingface.co/datasets/piebro/deutsche-bahn-data/resolve/main/raw_data/"
    "year=2026/month=9/day=12/date_2026-09-12_hour_12_13_14_15_16.parquet"
)
print("raw columns:", [row[0] for row in c.execute(f"DESCRIBE SELECT * FROM read_parquet('{RAW}')").fetchall()])
print(
    "raw api_name counts:",
    c.execute(f"SELECT api_name, count(*) FROM read_parquet('{RAW}') GROUP BY 1").fetchall(),
)
# Print one whole <s> stop element for an ICE, from a planned timetable and from a change feed.
for api in ("plan", "fchg", "rchg"):
    row = c.execute(
        f"""SELECT url, response_data FROM read_parquet('{RAW}')
        WHERE api_name ILIKE '%{api}%' AND response_data LIKE '%c="ICE"%' LIMIT 1"""
    ).fetchone()
    if row is None:
        print(f"no {api} response with an ICE")
        continue
    url, body = row
    at = body.find('c="ICE"')
    start = body.rfind("<s ", 0, at)
    end = body.find("</s>", at)
    print(f"\n{api} url: {url}\n{body[start:end + 4][:1500]}")

c.execute(
    """CREATE TABLE s AS SELECT station_name, train_type, train_number, line_number, final_destination_station AS dest,
      train_line_ride_id AS ride, train_line_station_num AS num, time, (delay_in_min >= 6)::INT AS late,
      day(time) AS d
    FROM read_parquet('data/raw/data-2026-08.parquet')
    WHERE train_type IN ('ICE', 'IC', 'EC') AND delay_in_min IS NOT NULL
      AND NOT coalesce(arrival_is_canceled, false) AND NOT coalesce(departure_is_canceled, false)"""
)
print("processed ICE sample:", c.execute("select * from s where train_type = 'ICE' limit 3").fetchall())
print(
    "ride id: distinct days per ride, distinct train numbers per ride:",
    c.execute(
        """select avg(nd), max(nd), avg(nt), max(nt) from
        (select ride, count(distinct d) nd, count(distinct train_number) nt from s group by 1)"""
    ).fetchone(),
)
print(
    "train number: distinct destinations per number (avg, share > 1):",
    c.execute(
        """select avg(n), avg((n > 1)::int) from
        (select train_type, train_number, count(distinct dest) n from s group by 1, 2)"""
    ).fetchone(),
)

# Route key: origin (lowest stop index on that run and day) plus final destination.
c.execute(
    """CREATE TABLE o AS SELECT ride, d, arg_min(station_name, num) origin FROM s GROUP BY 1, 2"""
)
c.execute("CREATE TABLE t AS SELECT s.*, o.origin FROM s JOIN o USING (ride, d)")
KEYS = {
    "station": "station_name",
    "type x station": "train_type || '|' || station_name",
    "type x destination x station": "train_type || '|' || dest || '|' || station_name",
    "route (origin->dest) x station": "train_type || '|' || origin || '|' || dest || '|' || station_name",
    "train number": "train_type || '|' || train_number",
    "train number x station": "train_type || '|' || train_number || '|' || station_name",
}
print("\nLong-distance only, out-of-sample Brier skill (fit 1-15, score 17-31, <10 obs -> global):")
p0 = c.execute("select avg(late) from t where d <= 15").fetchone()[0]
for name, key in KEYS.items():
    skill, coverage = c.execute(
        f"""with tr as (select {key} k, avg(late) p, count(*) n from t where d <= 15 group by 1),
        te as (select {key} k, late y from t where d >= 17)
        select 1 - avg(power(y - case when tr.n >= 10 then tr.p else {p0} end, 2)) / avg(power(y - {p0}, 2)),
               avg(coalesce((tr.n >= 10)::int, 0))
        from te left join tr using (k)"""
    ).fetchone()
    print(f"  {name:32s} skill={skill:.3f} coverage={coverage:.2f}")
