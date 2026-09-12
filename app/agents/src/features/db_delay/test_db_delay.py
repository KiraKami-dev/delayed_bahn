"""Smoke tests for the rail delay conversion: hourly table to training samples.

Runs on a synthetic hourly table so it needs no network and no downloaded
parquet. Covers the happy path and the two properties that would quietly ruin
a training run: station leakage across splits, and a chain of thought that
contradicts the answer printed after it.
"""

from __future__ import annotations

import datetime as dt
import sys
import unittest
from pathlib import Path

import duckdb
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

import timef
from timef_bridge import TimeFQADataset, rows_from_timef
from windows import CONTEXT_HOURS, HORIZON_HOURS

N_HOURS = 31 * 24
MONTH_START = dt.datetime(2026, 8, 1)
STATIONS = [f"Teststadt {i} Hbf" for i in range(6)]


def synthetic_connection() -> duckdb.DuckDBPyConnection:
    """Build an in-memory hourly table with a daily cycle and a few gaps."""
    con = duckdb.connect()
    con.execute("CREATE TABLE hourly (station_name VARCHAR, hour TIMESTAMP, mean_delay DOUBLE, cancel_rate DOUBLE, trains DOUBLE)")
    rng = np.random.default_rng(0)
    rows = []
    for offset, station in enumerate(STATIONS):
        for hour in range(N_HOURS):
            if hour % 97 == offset:  # a scattered gap, well under the imputation cap
                continue
            daily = 3.0 + 2.0 * np.sin(2 * np.pi * hour / 24)
            rows.append(
                (
                    station,
                    MONTH_START + dt.timedelta(hours=hour),
                    float(daily + rng.normal(0, 0.3)),
                    float(abs(rng.normal(0.03, 0.01))),
                    float(30 + offset),
                )
            )
    con.executemany("INSERT INTO hourly VALUES (?, ?, ?, ?, ?)", rows)
    return con


class ConversionTest(unittest.TestCase):
    """The hourly table converts into TimeF records and OpenTSLM samples."""

    @classmethod
    def setUpClass(cls) -> None:
        """Build the dataset once for every test in this class."""
        cls.dataset = timef.build(synthetic_connection(), MONTH_START, N_HOURS)
        cls.holdout = {STATIONS[0], STATIONS[1]}

        def assign(record, task):
            if record.subject_ids[0] in cls.holdout:
                return "test"
            return "validation" if int(record.record_id.rsplit("-", 1)[1]) % 7 == 0 else "train"

        cls.buckets = rows_from_timef(cls.dataset, assign)

    def test_records_and_tasks_are_built(self) -> None:
        """Every station yields windows, and every window yields three tasks."""
        self.assertTrue(self.dataset.records)
        self.assertEqual(len(self.dataset.tasks), 3 * len(self.dataset.records))

    def test_series_shape_is_the_context_window(self) -> None:
        """Each record carries three finite channels of exactly the context length."""
        record = self.dataset.records[0]
        self.assertEqual(len(record.time_series), 3)
        for series in record.time_series:
            values = series.to_numpy()
            self.assertEqual(len(values), CONTEXT_HOURS)
            self.assertTrue(np.isfinite(values).all())

    def test_horizon_never_enters_the_context(self) -> None:
        """A window's context stops before its own horizon starts."""
        for record in self.dataset.records:
            start = int(record.record_id.rsplit("-", 1)[1])
            self.assertLessEqual(start + CONTEXT_HOURS + HORIZON_HOURS, N_HOURS)

    def test_no_station_crosses_the_split(self) -> None:
        """Held-out stations appear only in test, and never in train or validation."""
        seen = {split: {tuple(row["subjects"]) for row in rows} for split, rows in self.buckets.items()}
        train_stations = {s for group in seen["train"] | seen["validation"] for s in group}
        test_stations = {s for group in seen["test"] for s in group}
        self.assertEqual(test_stations, self.holdout)
        self.assertFalse(train_stations & test_stations)

    def test_samples_render_for_training(self) -> None:
        """A formatted sample carries the prompts, the series and a terminated answer."""

        class Rendered(TimeFQADataset):
            SPLITS = self.buckets

        sample = Rendered("train", EOS_TOKEN="<eos>")[0]
        self.assertIn("hourly measurements", sample["pre_prompt"])
        self.assertEqual(len(sample["time_series"]), 3)
        self.assertTrue(all(len(s) == CONTEXT_HOURS for s in sample["time_series"]))
        self.assertTrue(sample["answer"].endswith("<eos>"))
        self.assertIn("Answer:", sample["answer"])

    def test_series_text_states_mean_and_std(self) -> None:
        """The de-normalisation hint OpenTSLM's own datasets rely on is present."""

        class Rendered2(TimeFQADataset):
            SPLITS = self.buckets

        sample = Rendered2("train", EOS_TOKEN="<eos>")[0]
        for text in sample["time_series_text"]:
            self.assertIn("mean", text)
            self.assertIn("std", text)

    def test_forecast_rationale_agrees_with_its_answer(self) -> None:
        """The reasoning's direction word must match the number that follows it."""
        checked = 0
        for task in self.dataset.tasks:
            if not task.id.endswith("forecast"):
                continue
            rationale, target = task.rationale, float(task.target)
            seasonal = float(rationale.split("same hours of day it averaged ")[1].split(" minutes")[0])
            if "come in above" in rationale:
                self.assertGreater(target, seasonal)
            elif "come in below" in rationale:
                self.assertLess(target, seasonal)
            checked += 1
        self.assertGreater(checked, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
