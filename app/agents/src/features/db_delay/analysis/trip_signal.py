"""Does history add to live delay, and how long is a run? (Aug 2026)."""

import duckdb

c = duckdb.connect()
c.execute(
    """CREATE TABLE s AS SELECT station_name, train_type, line_number, train_line_ride_id AS ride,
      train_line_station_num AS num, time, delay_in_min AS delay, (delay_in_min >= 6)::INT AS late,
      day(time) AS d
    FROM read_parquet('data/raw/data-2026-08.parquet')
    WHERE NOT coalesce(arrival_is_canceled, false) AND NOT coalesce(departure_is_canceled, false)
      AND delay_in_min IS NOT NULL"""
)
print(
    "stops per run p10/median/p90 by class:",
    c.execute(
        """with r as (select ride, date_trunc('day', min(time)) run_day, any_value(train_type) tt, count(*) n
                      from s group by ride, date_trunc('day', time))
        select case when tt in ('ICE','IC','EC') then 'long-distance' when tt = 'S' then 'S-Bahn' else 'regional' end,
               quantile_cont(n, 0.1), median(n), quantile_cont(n, 0.9), count(*)
        from r group by 1"""
    ).fetchall(),
)

GROUP = "a.train_type || '|' || coalesce(a.line_number, 'NA') || '|' || a.station_name"
for j in (1, 3, 8):
    c.execute(
        f"""CREATE OR REPLACE TABLE p AS
        select a.late y, a.d, (least(greatest(b.delay, 0), 40) // 3)::VARCHAR bucket, {GROUP} g
        from s a join s b on a.ride = b.ride and b.num = a.num - {j}
          and b.time between a.time - interval 8 hour and a.time"""
    )
    p0 = c.execute("select avg(y) from p where d <= 15").fetchone()[0]
    live = c.execute(
        f"""with tr as (select bucket, avg(y) p from p where d <= 15 group by 1)
        select 1 - avg(power(y - coalesce(tr.p, {p0}), 2)) / avg(power(y - {p0}, 2))
        from p left join tr using (bucket) where d >= 17"""
    ).fetchone()[0]
    both = c.execute(
        f"""with fb as (select bucket, avg(y) p from p where d <= 15 group by 1),
        tr as (select bucket, g, avg(y) p, count(*) n from p where d <= 15 group by 1, 2)
        select 1 - avg(power(y - coalesce(case when tr.n >= 10 then tr.p end, fb.p, {p0}), 2))
                 / avg(power(y - {p0}, 2))
        from p left join tr using (bucket, g) left join fb using (bucket) where d >= 17"""
    ).fetchone()[0]
    print(f"j={j}: live only skill={live:.3f}   live + line x station skill={both:.3f}")
