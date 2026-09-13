"""Invariants of the re-bucketing path, against synthetic in-memory fact tables.

Offline on purpose. The real cache at ~/.cache/db_route/ is a 26-month
extraction that is still running, and none of the properties tested here are
properties of Deutsche Bahn -- they are properties of the arithmetic. A fixture
lets each one be checked against a number computed by hand.

The fixture is three DuckDB tables with the exact column set facts.py writes,
built from a deterministic hourly generator over 140 days -- enough to fill the
season layer's 120-day window with room in front of it.

Run: python tests/test_resample.py   (or under pytest, which collects it too)
"""

from __future__ import annotations

import datetime as dt
import sys
import unittest
from pathlib import Path

import numpy as np

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import profiles  # noqa: E402
import resample  # noqa: E402
from profiles import PROFILES, QUARTER, SEASON, WEEK  # noqa: E402
from resample import EntityKey, FactCache  # noqa: E402

FACT_COLUMNS = (
    "sum_delay",
    "n_obs",
    "n_cancelled",
    "n_attributed",
    "sum_delay_attributed",
    "sum_delay_works",
    "sum_delay_weather",
    "sum_delay_technical",
    "sum_delay_knock_on",
    "sum_delay_staff",
)

STATION = "München Hbf"
OTHER_STATION = "Pullach"
SERVICE = "S -> Wolfratshausen"
KEY = EntityKey(SERVICE, STATION)

# 140 days of history ending the night before the anchor. SEASON needs 120.
ANCHOR = dt.date(2026, 6, 1)
HISTORY_DAYS = 140
START = dt.datetime(2026, 6, 1) - dt.timedelta(days=HISTORY_DAYS)

RELATIONS = {grain: table for grain, table in resample.FACT_TABLES.items()}


def _row(hour: dt.datetime, n_obs: int, mean_delay: float, **overrides) -> dict:
    """One fact row. Sums are derived from a count and a mean, as facts.py does."""
    sum_delay = n_obs * mean_delay
    attributed = overrides.pop("sum_delay_attributed", round(0.4 * sum_delay, 6))
    row = {
        "hour": hour,
        "sum_delay": sum_delay,
        "n_obs": n_obs,
        "n_cancelled": overrides.pop("n_cancelled", 0),
        "n_attributed": overrides.pop("n_attributed", max(1, n_obs // 3)),
        "sum_delay_attributed": attributed,
        "sum_delay_works": overrides.pop("sum_delay_works", round(0.25 * attributed, 6)),
        "sum_delay_weather": overrides.pop("sum_delay_weather", round(0.15 * attributed, 6)),
        "sum_delay_technical": overrides.pop("sum_delay_technical", round(0.2 * attributed, 6)),
        "sum_delay_knock_on": overrides.pop("sum_delay_knock_on", round(0.3 * attributed, 6)),
        "sum_delay_staff": overrides.pop("sum_delay_staff", round(0.1 * attributed, 6)),
    }
    row.update(overrides)
    return row


def _hourly(seed: float, *, skip: set[dt.datetime] | None = None) -> list[dict]:
    """A dense hourly series with a rush-hour shape, so nothing is degenerate."""
    skip = skip or set()
    rows = []
    for i in range(HISTORY_DAYS * 24):
        hour = START + dt.timedelta(hours=i)
        if hour in skip:
            continue
        hour_of_day = hour.hour
        rush = 1.0 + 0.8 * np.sin(2 * np.pi * (hour_of_day - 6) / 24.0)
        rows.append(
            _row(
                hour,
                n_obs=int(4 + 8 * max(rush, 0.1)),
                mean_delay=round(seed * rush + 0.01 * (i % 7), 4),
                n_cancelled=1 if i % 53 == 0 else 0,
            )
        )
    return rows


def _create(con: duckdb.DuckDBPyConnection, table: str, keys: dict[str, list[str]],
            rows: list[dict]) -> None:
    """Materialise one fact table with its key columns prepended."""
    columns = list(keys) + ["hour"] + list(FACT_COLUMNS)
    payload = {c: [] for c in columns}
    n_keys = len(next(iter(keys.values())))
    for k in range(n_keys):
        for row in rows:
            for name, values in keys.items():
                payload[name].append(values[k])
            for c in columns[len(keys):]:
                payload[c].append(row[c])
    con.register(f"_{table}_src", __import__("pyarrow").table(payload))
    con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM _{table}_src")


def fixture_connection(
    *, station_rows=None, line_rows=None, pair_rows=None
) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    _create(con, "hourly_station", {"station": [STATION, OTHER_STATION]},
            station_rows if station_rows is not None else _hourly(4.0))
    _create(con, "hourly_line", {"service_group": [SERVICE]},
            line_rows if line_rows is not None else _hourly(3.0))
    _create(con, "hourly_pair", {"service_group": [SERVICE], "station": [STATION]},
            pair_rows if pair_rows is not None else _hourly(5.0))
    return con


class TestUnbiasedRebucketing(unittest.TestCase):
    """The reason facts.py stores sums and counts instead of means.

    This is the single most important test in the module: every other invariant
    is about shape, and this one is about the numbers being right.
    """

    def test_six_hour_bucket_is_count_weighted(self):
        # One 6-hour bucket, two populated hours with wildly different traffic.
        # 4 trains at 20 min = 80 min; 400 trains at 2 min = 800 min.
        # Count-weighted:  880 / 404 = 2.178...
        # Mean of means:  (20 + 2) / 2 = 11.0  -- 5x too high, and biased towards
        # the hour when almost nothing was running.
        base = dt.datetime(2026, 5, 31, 0, 0)  # last 6h bucket before the anchor
        rows = [_row(base + dt.timedelta(hours=18), 4, 20.0),
                _row(base + dt.timedelta(hours=20), 400, 2.0)]
        con = fixture_connection(station_rows=rows, line_rows=rows, pair_rows=rows)
        cache = FactCache(con=con, relations=RELATIONS)

        layer = QUARTER
        first = resample.bucket_index(dt.datetime(2026, 6, 1), layer.bucket_seconds)
        values, present = cache.series("station_delay", layer, KEY, first - layer.n_steps)

        self.assertTrue(present[-1], "the final bucket holds both hours")
        self.assertAlmostEqual(float(values[-1]), 880.0 / 404.0, places=9)
        self.assertNotAlmostEqual(float(values[-1]), 11.0, places=3)

    def test_daily_bucket_is_count_weighted(self):
        """Same arithmetic one layer coarser -- one code path, not two."""
        base = dt.datetime(2026, 5, 31, 0, 0)
        rows = [_row(base + dt.timedelta(hours=2), 4, 20.0),
                _row(base + dt.timedelta(hours=21), 400, 2.0)]
        con = fixture_connection(station_rows=rows, line_rows=rows, pair_rows=rows)
        cache = FactCache(con=con, relations=RELATIONS)
        first = resample.bucket_index(dt.datetime(2026, 6, 1), SEASON.bucket_seconds)
        values, _ = cache.series("station_delay", SEASON, KEY, first - SEASON.n_steps)
        self.assertAlmostEqual(float(values[-1]), 880.0 / 404.0, places=9)


class TestShapeAndEndpoint(unittest.TestCase):
    def setUp(self):
        self.con = fixture_connection()
        self.cache = FactCache(con=self.con, relations=RELATIONS)

    def test_every_series_has_exactly_n_steps(self):
        for profile_id, prof in PROFILES.items():
            window = self.cache.window(KEY, ANCHOR, prof)
            expected = {(l.layer_id, s) for l in prof.layers for s in l.signals}
            self.assertEqual(set(window.values), expected, profile_id)
            for layer in prof.layers:
                for signal in layer.signals:
                    array = window.values[(layer.layer_id, signal)]
                    self.assertEqual(array.shape, (layer.n_steps,),
                                     f"{profile_id}/{layer.layer_id}/{signal}")
                    self.assertEqual(array.dtype, np.float32)

    def test_window_ends_at_the_anchor_and_excludes_the_travel_day(self):
        for layer in (WEEK, QUARTER, SEASON):
            starts = resample.bucket_starts(layer, ANCHOR)
            t0 = np.datetime64(dt.datetime(2026, 6, 1), "s")
            self.assertEqual(starts[-1], t0 - np.timedelta64(layer.bucket_seconds, "s"))
            self.assertEqual(starts[0],
                             t0 - np.timedelta64(layer.n_steps * layer.bucket_seconds, "s"))
            self.assertLess(starts[-1], t0, "context must not reach into the travel day")

    def test_last_value_is_the_last_bucket_before_t0(self):
        """Not just the right length -- the right end."""
        marker = dt.datetime(2026, 5, 31, 23, 0)
        rows = _hourly(4.0)
        rows = [r for r in rows if r["hour"] != marker]
        rows.append(_row(marker, 10, 99.0))
        con = fixture_connection(station_rows=rows)
        cache = FactCache(con=con, relations=RELATIONS)
        window = cache.window(KEY, ANCHOR, PROFILES["S"])
        self.assertAlmostEqual(float(window.values[("week", "station_delay")][-1]), 99.0,
                               places=4)


class TestPhaseAlignment(unittest.TestCase):
    """Index i has a fixed hour-of-day. The free inductive bias, checked exactly."""

    def test_buckets_are_evenly_spaced_from_the_anchor(self):
        for layer in (WEEK, QUARTER, SEASON):
            starts = resample.bucket_starts(layer, ANCHOR)
            deltas = np.diff(starts).astype("timedelta64[s]").astype(np.int64)
            self.assertTrue(np.all(deltas == layer.bucket_seconds), layer.layer_id)

    def test_index_modulo_gives_the_position_in_the_day(self):
        for layer in (WEEK, QUARTER, SEASON):
            per_day = 86400 // layer.bucket_seconds
            self.assertEqual(layer.n_steps % per_day, 0,
                             f"{layer.layer_id}: n_steps must be whole days for phase to hold")
            starts = resample.bucket_starts(layer, ANCHOR)
            seconds = (starts - starts.astype("datetime64[D]")).astype(
                "timedelta64[s]").astype(np.int64)
            slot = seconds // layer.bucket_seconds
            self.assertTrue(np.array_equal(slot, np.arange(layer.n_steps) % per_day),
                            layer.layer_id)

    def test_alignment_is_identical_across_anchors(self):
        """Different travel days, same phase -- what makes one global grid legal."""
        for offset in (0, 1, 7, 33, 180):
            anchor = ANCHOR - dt.timedelta(days=offset)
            starts = resample.bucket_starts(QUARTER, anchor)
            hours = starts.astype("datetime64[h]").astype(object)
            self.assertTrue(all(h.hour % 6 == 0 for h in hours), offset)
            self.assertEqual(hours[0].hour, hours[0 % 4].hour)

    def test_non_midnight_anchor_is_rejected(self):
        with self.assertRaises(ValueError):
            resample.bucket_index(dt.datetime(2026, 6, 1, 3, 0), 21600)


class TestGaps(unittest.TestCase):
    def test_gap_is_interpolated_and_reported(self):
        missing = {dt.datetime(2026, 5, 30, 10, 0), dt.datetime(2026, 5, 30, 11, 0)}
        rows = _hourly(4.0, skip=missing)
        con = fixture_connection(station_rows=rows)
        cache = FactCache(con=con, relations=RELATIONS)
        window = cache.window(KEY, ANCHOR, PROFILES["S"])

        present = window.present[("week", "station_delay")]
        starts = window.bucket_starts["week"]
        holes = np.flatnonzero(~present)
        self.assertEqual(len(holes), 2)
        self.assertEqual(
            {starts[i].astype("datetime64[s]").astype(object) for i in holes}, missing)

        self.assertAlmostEqual(window.imputed_fraction[("week", "station_delay")],
                               2 / WEEK.n_steps, places=12)

        values = window.values[("week", "station_delay")]
        left, right = holes[0] - 1, holes[-1] + 1
        expected = np.interp([holes[0], holes[1]], [left, right],
                             [values[left], values[right]])
        np.testing.assert_allclose(values[holes], expected, rtol=1e-5)
        self.assertTrue(np.all(np.isfinite(values)))

    def test_throughput_gaps_are_zero_not_interpolated(self):
        missing = {dt.datetime(2026, 5, 30, 3, 0)}
        rows = _hourly(4.0, skip=missing)
        con = fixture_connection(station_rows=rows)
        cache = FactCache(con=con, relations=RELATIONS)
        window = cache.window(KEY, ANCHOR, PROFILES["S"])
        hole = int(np.flatnonzero(~window.present[("week", "station_throughput")])[0])
        self.assertEqual(float(window.values[("week", "station_throughput")][hole]), 0.0)
        # and a quiet hour must not spend the imputation budget
        self.assertTrue(window.within_imputation_budget)

    def test_pair_grain_is_structurally_sparse_at_the_week_layer(self):
        """Why `service_at_station_delay` lives at the coarse layers only.

        A realistic S-Bahn pair: trains 05:00-22:59, nothing overnight. The
        overnight hours are not missing data, they are the timetable -- and at
        hourly resolution they put the pair channel at 6/24 imputed on a record
        with nothing whatever wrong with it. Re-bucketed to six hours every
        bucket of the day has a train in it and the same channel is dense.
        That is the measurement behind dropping the channel from WEEK.
        """
        pair_rows = [r for r in _hourly(5.0) if 5 <= r["hour"].hour < 23]
        con = fixture_connection(pair_rows=pair_rows)
        cache = FactCache(con=con, relations=RELATIONS)

        self.assertNotIn("service_at_station_delay", PROFILES["S"].layers[0].signals)

        hourly = profiles.WEEK.with_signals(
            ("service_at_station_delay", "station_throughput", "service_throughput")
        )
        probe = profiles.TimelineProfile("T", "test/hourly-pair", (hourly,))
        window = cache.window(KEY, ANCHOR, probe)
        pair_fraction = window.imputed_fraction[("week", "service_at_station_delay")]
        self.assertAlmostEqual(pair_fraction, 6 / 24, places=6)
        self.assertGreater(pair_fraction, resample.MAX_IMPUTED_FRACTION["station"])

        coarse = cache.window(KEY, ANCHOR, PROFILES["M"])
        self.assertAlmostEqual(
            coarse.imputed_fraction[("quarter", "service_at_station_delay")], 0.0, places=6
        )
        # the station channel, over the same hours, is fine -- so a single max
        # across channels is what would have failed, not the data
        self.assertEqual(window.imputed_fraction[("week", "station_throughput")], 0.0)
        self.assertTrue(np.all(np.isfinite(
            window.values[("week", "service_at_station_delay")])))

    def test_unknown_entity_is_fully_imputed_and_rejected(self):
        con = fixture_connection()
        cache = FactCache(con=con, relations=RELATIONS)
        window = cache.window(EntityKey("nonesuch", "nowhere"), ANCHOR, PROFILES["S"])
        self.assertEqual(set(window.worst_imputed_fraction.values()), {1.0})
        self.assertFalse(window.within_imputation_budget)
        self.assertIn("imputed", window.reject_reason())
        for array in window.values.values():
            self.assertTrue(np.all(np.isfinite(array)))

    def test_zero_denominator_counts_as_missing_not_zero(self):
        """No attributed minutes is no share, not a share of zero."""
        rows = _hourly(4.0)
        target = dt.datetime(2026, 5, 30, 9, 0)
        for row in rows:
            if row["hour"] == target:
                row["sum_delay_attributed"] = 0.0
                row["sum_delay_works"] = 0.0
        con = fixture_connection(station_rows=rows)
        cache = FactCache(con=con, relations=RELATIONS)
        window = cache.window(KEY, ANCHOR, PROFILES["S"])
        starts = window.bucket_starts["week"]
        idx = int(np.flatnonzero(starts == np.datetime64(target, "s"))[0])
        self.assertFalse(window.present[("week", "works_share")][idx])
        self.assertTrue(window.present[("week", "station_delay")][idx],
                        "the bucket itself was observed; only the share was undefined")


class TestDerivedSignals(unittest.TestCase):
    def test_share_weights_minutes_not_events(self):
        """Two buckets, same works event count, very different works minutes."""
        base = dt.datetime(2026, 5, 31, 0, 0)
        rows = [
            _row(base + dt.timedelta(hours=1), 10, 5.0,
                 n_attributed=2, sum_delay_attributed=50.0, sum_delay_works=40.0,
                 sum_delay_weather=10.0, sum_delay_technical=0.0,
                 sum_delay_knock_on=0.0, sum_delay_staff=0.0),
        ]
        con = fixture_connection(station_rows=rows)
        cache = FactCache(con=con, relations=RELATIONS)
        first = resample.bucket_index(dt.datetime(2026, 6, 1), SEASON.bucket_seconds)
        works, present = cache.series("works_share", SEASON, KEY, first - SEASON.n_steps)
        self.assertTrue(present[-1])
        self.assertAlmostEqual(float(works[-1]), 40.0 / 50.0, places=9)
        # 2 attributed events out of 10 observations -- the event-weighted answer
        # would have been 0.2, which is not what a share of minutes means.
        attributed, _ = cache.series("attributed_share", SEASON, KEY, first - SEASON.n_steps)
        self.assertAlmostEqual(float(attributed[-1]), 0.2, places=9)

    def test_signal_names_match_the_frozen_contract(self):
        declared = set(profiles.SIGNALS) | set(profiles.CAUSE_SIGNALS)
        self.assertTrue(declared <= set(resample.SIGNAL_SPECS),
                        sorted(declared - set(resample.SIGNAL_SPECS)))
        for prof in PROFILES.values():
            for layer in prof.layers:
                for signal in layer.signals:
                    self.assertIn(signal, resample.SIGNAL_SPECS,
                                  f"{prof.profile_id}/{layer.layer_id}")

    def test_grains_are_distinct(self):
        """service / station / pair must not collapse onto one another."""
        con = fixture_connection()
        cache = FactCache(con=con, relations=RELATIONS)
        window = cache.window(KEY, ANCHOR, PROFILES["M"])
        service = window.values[("quarter", "service_delay")]
        station = window.values[("quarter", "station_delay")]
        pair = window.values[("quarter", "service_at_station_delay")]
        self.assertFalse(np.allclose(service, station))
        self.assertFalse(np.allclose(station, pair))
        # fixture seeds: line 3.0, station 4.0, pair 5.0, same rush shape
        self.assertLess(float(service.mean()), float(station.mean()))
        self.assertLess(float(station.mean()), float(pair.mean()))


class TestGuards(unittest.TestCase):
    def test_is_degenerate_catches_a_constant_series(self):
        self.assertTrue(resample.is_degenerate(np.zeros(120, dtype=np.float32)))
        self.assertTrue(resample.is_degenerate(np.full(120, 0.37, dtype=np.float32)))
        self.assertFalse(resample.is_degenerate(
            np.linspace(0.0, 1.0, 120, dtype=np.float32)))
        jitter = np.zeros(120, dtype=np.float32)
        jitter[0] = 1e-9
        self.assertTrue(resample.is_degenerate(jitter), "below the z-score floor")

    def test_flat_cancel_rate_is_a_quiet_week_not_a_reject(self):
        """The realistic case: a station that never cancels anything."""
        rows = [r | {"n_cancelled": 0} for r in _hourly(4.0)]
        con = fixture_connection(station_rows=rows)
        cache = FactCache(con=con, relations=RELATIONS)
        window = cache.window(KEY, ANCHOR, PROFILES["S"])
        # A flat cancellation rate is a week with no cancellations, not a
        # defect; only a flat delay channel disqualifies the record.
        self.assertNotIn(("week", "station_cancel_rate"), window.degenerate_channels)
        self.assertTrue(resample.is_degenerate(window.values[("week", "station_cancel_rate")]))
        self.assertIsNone(window.reject_reason())

    def test_flat_delay_channel_still_rejects(self):
        """A service whose mean delay never moves did not run; that record must not exist."""
        rows = [r | {"sum_delay": 0.0} for r in _hourly(3.0)]
        con = fixture_connection(line_rows=rows)
        cache = FactCache(con=con, relations=RELATIONS)
        window = cache.window(KEY, ANCHOR, PROFILES["S"])
        self.assertIn(("week", "service_delay"), window.degenerate_channels)
        self.assertIsNotNone(window.reject_reason())

    def test_non_finite_raises_rather_than_propagating(self):
        rows = _hourly(4.0)
        rows[-1] = dict(rows[-1], sum_delay=float("nan"))
        con = fixture_connection(station_rows=rows)
        cache = FactCache(con=con, relations=RELATIONS)
        with self.assertRaises(ValueError) as caught:
            cache.window(KEY, ANCHOR, PROFILES["S"])
        self.assertIn("non-finite", str(caught.exception))

    def test_entity_and_anchor_coercion(self):
        self.assertEqual(resample.resolve_entity((SERVICE, STATION)), KEY)

        class Record:
            service_group = SERVICE
            station = STATION
            travel_date = ANCHOR

        self.assertEqual(resample.resolve_entity(Record()), KEY)
        self.assertEqual(resample.anchor_midnight(Record()), dt.datetime(2026, 6, 1))

        class AnchorsAnchor:  # anchors.Anchor spells the field `anchor`
            anchor = ANCHOR

        self.assertEqual(resample.anchor_midnight(AnchorsAnchor()),
                         dt.datetime(2026, 6, 1))
        self.assertEqual(resample.anchor_midnight(dt.datetime(2026, 6, 1, 17, 4)),
                         dt.datetime(2026, 6, 1))
        with self.assertRaises(TypeError):
            resample.resolve_entity(object())


class TestOneCodePathForEveryProfile(unittest.TestCase):
    def test_all_four_profiles_from_one_fixture(self):
        con = fixture_connection()
        cache = FactCache(con=con, relations=RELATIONS)
        windows = {pid: cache.window(KEY, ANCHOR, prof) for pid, prof in PROFILES.items()}

        self.assertEqual(len(windows), 4)
        for pid, window in windows.items():
            prof = PROFILES[pid]
            self.assertEqual(len(window.values), prof.n_series, pid)
            for (layer_id, signal), array in window.values.items():
                layer = next(l for l in prof.layers if l.layer_id == layer_id)
                self.assertEqual(len(array), layer.n_steps)
                self.assertTrue(np.all(np.isfinite(array)))

        # XM is S+M+L stacked: the shared layers must be bit-identical, or the
        # additivity test is comparing different data rather than more of it.
        for pid, layer_id in (("S", "week"), ("M", "quarter"), ("L", "season")):
            for (lid, signal), array in windows[pid].values.items():
                if lid != layer_id or (lid, signal) not in windows["XM"].values:
                    continue
                np.testing.assert_array_equal(array, windows["XM"].values[(lid, signal)],
                                              f"{pid} vs XM at {lid}/{signal}")

        # ...and the panels were built once, not once per profile: 3 grains x 3
        # buckets is the ceiling, and only the coarse layers touch the pair grain.
        self.assertLessEqual(len(cache._panels), 9)
        self.assertEqual(sorted(cache._panels), [
            ("line", "1 day"), ("line", "1 hour"), ("line", "6 hours"),
            ("pair", "1 day"), ("pair", "6 hours"),
            ("station", "1 day"), ("station", "1 hour"), ("station", "6 hours"),
        ])

    def test_bucket_literal_is_the_only_per_profile_difference(self):
        """The SQL template carries no profile-specific text."""
        source = (Path(__file__).resolve().parents[1] / "resample.py").read_text()
        for token in ("week", "quarter", "season", "'S'", '"S"', "XM"):
            self.assertNotIn(f"layer_id == {token}", source)
        self.assertEqual(source.count("_BUCKET_SQL = "), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
