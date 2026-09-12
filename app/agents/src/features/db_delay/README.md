# db_delay

German rail delay as a time-series language modelling task.

```
extract.py       monthly parquet over HTTPS -> hourly per-station table (DuckDB)
windows.py       hourly table -> context windows + targets computed from the horizon
timef.py         windows -> TimeFDataset (records, annotations, TimeNet tasks)
timef_bridge.py  any TimeFDataset -> OpenTSLM training samples   <- generic, not rail-specific
test_db_delay.py smoke tests on synthetic data, no network needed
```

Run the tests: `python test_db_delay.py`. Needs `timenet[build]`, `timenet-connectors`,
`opentslm` and `duckdb` on Python 3.12.

## Why per station and not per train run

A single run visits ten to thirty stops at irregular spacing. A patch encoder has
nothing to grip there, and a baseline that lists the numbers as text would match it.
A station's hourly curve is dense and strongly seasonal, so the temporal model earns
its place. The measured daily cycle runs from about 2 minutes at 06:00 to about 6.5
in the evening, with a second overnight peak.

## Why the bridge exists

OpenTSLM does not depend on TimeNet. Its requirements name neither, and each of its
dataset classes loads its own source directly, so no path existed from a TimeF
dataset into training. `timef_bridge.py` is that path and knows nothing about rail:
it reads records, series and tasks, so any TimeF dataset can train an OpenTSLM model.

## Known limits

- One month gives too few windows for a time-based split once a context week and an
  embargo are removed. The station split works today; the time axis needs two or
  three months, which costs about ten seconds of extraction each.
- Timestamps are read as Europe/Berlin. August has no transition, so a single-month
  build is safe. Crossing late October needs an explicit DST fold policy.
- The six-hour target has a heavy right tail, so report median absolute error next to
  the mean.
