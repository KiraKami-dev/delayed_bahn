"""Delay distribution, and whether the full stop pattern beats origin x destination (Aug 2026)."""

import duckdb

c = duckdb.connect()
c.execute(
    """CREATE TABLE a AS SELECT station_name, train_type, final_destination_station AS dest,
      train_line_ride_id AS ride, train_line_station_num AS num, time, delay_in_min AS delay,
      coalesce(arrival_is_canceled, false) OR coalesce(departure_is_canceled, false) AS cancelled,
      day(time) AS d,
      CASE WHEN train_type IN ('ICE', 'IC', 'EC') THEN 'long-distance' ELSE 'other' END AS cls
    FROM read_parquet('data/raw/data-2026-08.parquet') WHERE train_type <> 'Bus'"""
)

print("delay_in_min distribution (non-cancelled):")
for cls in ("long-distance", "other"):
    row = c.execute(
        f"""select count(*), min(delay), avg((delay < 0)::int), quantile_cont(delay, [0.5, 0.75, 0.9, 0.95, 0.99]),
                   avg((delay > 60)::int), avg((delay > 120)::int), max(delay),
                   (select avg(cancelled::int) from a where cls = '{cls}')
        from a where cls = '{cls}' and not cancelled and delay is not null"""
    ).fetchone()
    print(f"  {cls}: n={row[0]} min={row[1]} share<0={row[2]:.3f} p50/75/90/95/99={row[3]} "
          f"share>60={row[4]:.4f} share>120={row[5]:.4f} max={row[6]} cancelled_share={row[7]:.3f}")

# Stop pattern per run and day, built from every stop including cancelled ones, so the
# key does not smuggle in which stops were cancelled.
c.execute(
    """CREATE TABLE rd AS SELECT ride, d, string_agg(station_name, '>' ORDER BY num) pattern,
      arg_min(station_name, num) origin FROM a GROUP BY ride, d"""
)
c.execute(
    """CREATE TABLE s AS SELECT a.*, rd.pattern, rd.origin, (a.delay >= 6)::INT late
    FROM a JOIN rd USING (ride, d) WHERE NOT a.cancelled AND a.delay IS NOT NULL"""
)
print(
    "distinct patterns per ride id within the month (avg, share > 1):",
    c.execute("select avg(n), avg((n > 1)::int) from (select ride, count(distinct pattern) n from rd group by 1)").fetchone(),
)

KEYS = {
    "type x station": "train_type || '|' || station_name",
    "origin x dest x station": "train_type || '|' || origin || '|' || dest || '|' || station_name",
    "full stop pattern x station": "pattern || '|' || station_name",
    "ride id x station": "ride || '|' || station_name",
}
for cls in ("long-distance", "other"):
    print(f"\n{cls}: out-of-sample Brier skill, late >= 6 (fit 1-15, score 17-31)")
    p0 = c.execute(f"select avg(late) from s where cls = '{cls}' and d <= 15").fetchone()[0]
    for name, key in KEYS.items():
        skill, coverage = c.execute(
            f"""with tr as (select {key} k, avg(late) p, count(*) n from s where cls = '{cls}' and d <= 15 group by 1),
            te as (select {key} k, late y from s where cls = '{cls}' and d >= 17)
            select 1 - avg(power(y - case when tr.n >= 10 then tr.p else {p0} end, 2)) / avg(power(y - {p0}, 2)),
                   avg(coalesce((tr.n >= 10)::int, 0))
            from te left join tr using (k)"""
        ).fetchone()
        print(f"  {name:30s} skill={skill:.3f} coverage={coverage:.2f}")
    keys = list(KEYS.values())
    joins = "\n".join(
        f"left join (select {k} k{i}, avg(late) p{i}, count(*) n{i} from s where cls = '{cls}' and d <= 15 group by 1) t{i} on t{i}.k{i} = te.k{i}"
        for i, k in ((2, keys[2]), (1, keys[1]), (0, keys[0]))
    )
    skill = c.execute(
        f"""with te as (select {keys[0]} k0, {keys[1]} k1, {keys[2]} k2, late y from s where cls = '{cls}' and d >= 17)
        select 1 - avg(power(y - coalesce(case when n2 >= 10 then p2 end, case when n1 >= 10 then p1 end,
                                          case when n0 >= 10 then p0 end, {p0}), 2)) / avg(power(y - {p0}, 2))
        from te {joins}"""
    ).fetchone()[0]
    print(f"  {'fallback pattern>od>type':30s} skill={skill:.3f} coverage=1.00")
