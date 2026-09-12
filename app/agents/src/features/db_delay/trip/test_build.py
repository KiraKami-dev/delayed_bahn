"""Smoke tests for the trip example builder on a synthetic timetable.

Two services run the same three stations every day. The delay at the last stop
encodes the day, so a test can tell exactly which day a history value came from.
Covers the happy path and the leakage properties that would quietly ruin training.
"""

from __future__ import annotations

import datetime as dt
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

import build  # noqa: E402

FIRST_DAY = dt.date(2025, 11, 1)
N_DAYS = 242  # through 30 June 2026, so train, validation and test all exist
STATIONS = ["Astadt Hbf", "Bdorf", "Cstadt Hbf"]
SERVICES = (("111", "ICE", "771", 8, 0), ("-222", "RE", "4711", 9, 100))  # ride, type, number, hour, offset


def last_stop_delay(day_index: int, offset: int) -> int:
    """Delay at the final stop on a given day; unique per day and per service."""
    return day_index % 50 + offset


def synthetic_parquet(path: Path) -> None:
    """Write a monthly-file-shaped parquet with two daily services."""
    rows = []
    for day in range(N_DAYS):
        date = FIRST_DAY + dt.timedelta(days=day)
        for ride, train_type, number, hour, offset in SERVICES:
            start = dt.datetime.combine(date, dt.time(hour, 0))
            for num, station in enumerate(STATIONS, start=1):
                planned = start + dt.timedelta(hours=num - 1)
                delay = {1: 1, 2: 3, 3: last_stop_delay(day, offset)}[num]
                arr_pt = None if num == 1 else planned
                arr_ct = None if num == 1 else planned + dt.timedelta(minutes=delay)
                dep_pt = None if num == 3 else planned + dt.timedelta(minutes=2)
                dep_ct = None if num == 3 else dep_pt + dt.timedelta(minutes=delay)
                rows.append(
                    {
                        "station_name": station, "xml_station_name": station, "eva": f"800000{num}",
                        "train_number": number, "line_number": None if train_type == "ICE" else "RE1",
                        "final_destination_station": STATIONS[-1], "delay_in_min": delay,
                        "time": dep_ct or arr_ct, "arrival_is_canceled": False, "departure_is_canceled": False,
                        "train_type": train_type, "train_line_ride_id": ride, "train_line_station_num": num,
                        "arrival_planned_time": arr_pt, "arrival_change_time": arr_ct,
                        "departure_planned_time": dep_pt, "departure_change_time": dep_ct,
                        "id": f"{ride}-{start:%y%m%d%H%M}-{num}",
                    }
                )
    pd.DataFrame(rows).to_parquet(path)


class BuildTest(unittest.TestCase):
    """The builder produces leakage-safe examples from a synthetic timetable."""

    @classmethod
    def setUpClass(cls) -> None:
        """Build the examples once for every test."""
        cls.tmp = tempfile.TemporaryDirectory()
        src = Path(cls.tmp.name) / "data-synthetic.parquet"
        synthetic_parquet(src)
        cfg = build.Config(
            files=(str(src),),
            examples_per_class={"long-distance": 10_000, "regional": 10_000, "S-Bahn": 10_000},
        )
        cls.df = build.build(cfg, Path(cls.tmp.name) / "examples.parquet", threads=2).to_pandas()

    @classmethod
    def tearDownClass(cls) -> None:
        """Remove the temporary directory."""
        cls.tmp.cleanup()

    def test_every_split_is_populated(self) -> None:
        """Train, validation and test all receive examples."""
        self.assertEqual(set(self.df["split"]), {"train", "validation", "test"})

    def test_no_prediction_moment_in_a_gap_day(self) -> None:
        """The day before validation and the day before test are dropped."""
        days = pd.to_datetime(self.df["t0"]).dt.date
        self.assertNotIn(dt.date(2026, 5, 1), set(days))
        self.assertNotIn(dt.date(2026, 6, 1), set(days))
        self.assertTrue((pd.to_datetime(self.df["t0"]) >= pd.Timestamp("2025-11-15")).all())

    def test_history_uses_only_earlier_days_and_keeps_train_types_apart(self) -> None:
        """At pattern level, the most recent history value is yesterday's delay of the same service."""
        rows = self.df[(self.df["k_station"] == STATIONS[-1]) & (self.df["hist_level"] == "pattern")]
        self.assertGreater(len(rows), 100)
        for _, row in rows.iterrows():
            day = (pd.Timestamp(row["t0"]).date() - FIRST_DAY).days
            offset = 0 if row["train_type"] == "ICE" else 100
            self.assertEqual(float(row["hist_series"][-1]), float(last_stop_delay(day - 1, offset)))

    def test_run_so_far_stops_at_the_last_departed_stop(self) -> None:
        """Departure delays up to the current stop only, empty before departure."""
        for _, row in self.df.iterrows():
            delays = list(row["run_delays"])
            if row["pre_departure"]:
                self.assertEqual(delays, [])
            elif row["j_station"] == STATIONS[1]:
                self.assertEqual(delays, [1.0, 3.0])
            else:
                self.assertEqual(delays, [1.0])
            self.assertLess(pd.Timestamp(row["t0"]), pd.Timestamp(row["k_arr_pt"]) + pd.Timedelta(hours=2))

    def test_targets_are_arrival_minutes(self) -> None:
        """Targets match the synthetic arrival delay and stay inside 0..999."""
        for _, row in self.df.iterrows():
            day = (pd.Timestamp(row["k_arr_pt"]).date() - FIRST_DAY).days
            offset = 0 if row["train_type"] == "ICE" else 100
            expected = 3 if row["k_station"] == STATIONS[1] else last_stop_delay(day, offset)
            self.assertEqual(row["target_minutes"], expected)
        self.assertFalse(self.df["cancelled"].any())

    def test_series_have_fixed_lengths(self) -> None:
        """History, station and network series have the configured lengths."""
        self.assertTrue((self.df["hist_series"].map(len) == 30).all())
        self.assertTrue((self.df["station_series"].map(len) == 72).all())
        self.assertTrue(np.isfinite(np.stack(self.df["network_series"].to_numpy())).all())


if __name__ == "__main__":
    unittest.main()
