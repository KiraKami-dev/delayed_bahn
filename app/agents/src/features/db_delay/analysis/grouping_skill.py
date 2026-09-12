"""Measure which aggregation predicts per-stop lateness out of sample (Aug 2026)."""

import time

import duckdb

c = duckdb.connect()
c.execute(
    """CREATE TABLE s AS SELECT station_name, train_type, train_number, line_number,
      train_line_ride_id AS ride, train_line_station_num AS num, time,
      delay_in_min AS delay, (delay_in_min >= 6)::INT AS late, day(time) AS d, hour(time) AS h
    FROM read_parquet('data/raw/data-2026-08.parquet')
    WHERE NOT coalesce(arrival_is_canceled, false) AND NOT coalesce(departure_is_canceled, false)
      AND delay_in_min IS NOT NULL"""
)
print("rows, late share:", c.execute("select count(*), avg(late) from s").fetchone())

t = time.time()
n = c.execute(
    "select count(*) from (select station_name, date_trunc('hour', time), avg(delay), count(*) from s group by 1, 2)"
).fetchone()
print("hourly agg, all stations:", n, round(time.time() - t, 1), "s")

print(
    "stations total / >=24 / >=100 / >=300 / >=1000 stops per day:",
    c.execute(
        """with x as (select station_name, count(*) / 31.0 pd from s group by 1)
        select count(*), sum((pd >= 24)::int), sum((pd >= 100)::int), sum((pd >= 300)::int),
               sum((pd >= 1000)::int) from x"""
    ).fetchone(),
)
print(
    "share of stops in top 300 / top 1000 stations:",
    c.execute(
        """with x as (select station_name, count(*) n from s group by 1),
        r as (select n, row_number() over (order by n desc) rk from x)
        select sum(n) filter (where rk <= 300) / sum(n), sum(n) filter (where rk <= 1000) / sum(n) from r"""
    ).fetchone(),
)
print(
    "line_number null share by type:",
    c.execute(
        "select train_type, count(*), round(avg((line_number is null)::int), 3) from s "
        "where train_type in ('ICE', 'IC', 'EC', 'RE', 'S') group by 1 order by 2 desc"
    ).fetchall(),
)
print(
    "train_number x station pairs, share running >= 20 days:",
    c.execute(
        """with x as (select train_type, train_number, station_name, count(distinct d) ndays from s group by 1, 2, 3)
        select count(*), avg((ndays >= 20)::int) from x"""
    ).fetchone(),
)

KEYS = {
    "station": "station_name",
    "station x hour": "station_name || '|' || h",
    "train_type": "train_type",
    "station x type": "station_name || '|' || train_type",
    "station x type x hour": "station_name || '|' || train_type || '|' || h",
    "line": "train_type || '|' || coalesce(line_number, 'NA')",
    "line x station": "train_type || '|' || coalesce(line_number, 'NA') || '|' || station_name",
    "line x station x hour": "train_type || '|' || coalesce(line_number, 'NA') || '|' || station_name || '|' || h",
    "train number": "train_type || '|' || train_number",
    "train number x station": "train_type || '|' || train_number || '|' || station_name",
}

print("\nOut-of-sample Brier skill, late >= 6 min (fit days 1-15, score 17-31, <10 obs -> global):")
for name, key in KEYS.items():
    t = time.time()
    skill, coverage = c.execute(
        f"""with tr as (select {key} k, avg(late) p, count(*) n from s where d <= 15 group by 1),
        g as (select avg(late) p0 from s where d <= 15),
        te as (select {key} k, late y from s where d >= 17)
        select 1 - avg(power(y - case when tr.n >= 10 then tr.p else g.p0 end, 2)) / avg(power(y - g.p0, 2)),
               avg(coalesce((tr.n >= 10)::int, 0))
        from te left join tr using (k) cross join g"""
    ).fetchone()
    print(f"  {name:26s} skill={skill:.3f} coverage={coverage:.2f} ({time.time() - t:.0f}s)")

for j in (1, 3, 8):
    skill, n = c.execute(
        f"""with p as (
            select a.late y, a.d, least(greatest(b.delay, 0), 40) // 3 bucket
            from s a join s b on a.ride = b.ride and b.num = a.num - {j}
              and b.time between a.time - interval 8 hour and a.time),
        tr as (select bucket, avg(y) p from p where d <= 15 group by 1),
        g as (select avg(late) p0 from s where d <= 15)
        select 1 - avg(power(y - coalesce(tr.p, g.p0), 2)) / avg(power(y - g.p0, 2)), count(*)
        from p left join tr using (bucket) cross join g where p.d >= 17"""
    ).fetchone()
    print(f"  live: delay {j} stop(s) earlier on the same run   skill={skill:.3f} n={n}")
