"""Build a TimeF dataset of German rail delay from the hourly station table."""

from __future__ import annotations

import datetime as dt
from fractions import Fraction
from zoneinfo import ZoneInfo

import numpy as np

from timenet.dataset import TimeFDataset, TimeSeries
from timenet.dataset.axis import RegularAxis
from timenet.types import (
    Annotation,
    ClassificationTask,
    DataSource,
    DatasetMetadata,
    ScalarPredictionTask,
    TimeSeriesSpec,
    ureg,
)

from windows import CHANNELS, CONTEXT_HOURS, build_windows, impute
from windows import rationale_for_comparison, rationale_for_forecast, rationale_for_peak

HOURLY = RegularAxis.from_rate_hz(Fraction(1, 3600))
# The scrape records German local time: the monthly files break on local month
# boundaries, not UTC ones. August has no DST transition, so a single-month
# build is safe. Extending across late October needs an explicit fold policy.
TZ = ZoneInfo("Europe/Berlin")
SOURCE = DataSource(
    data_source_type="operational-record",
    name="Deutsche Bahn timetable scrape",
    provider="piebro/deutsche-bahn-data",
)
SPECS = {
    "mean_delay": TimeSeriesSpec(
        spec_type="delay", name="Mean delay", unit_value=ureg.minute, data_source=SOURCE
    ),
    "cancel_rate": TimeSeriesSpec(
        spec_type="cancellation-rate",
        name="Cancellation rate",
        unit_value=ureg.dimensionless,
        data_source=SOURCE,
    ),
    "trains": TimeSeriesSpec(
        spec_type="throughput", name="Trains per hour", unit_value=ureg.dimensionless, data_source=SOURCE
    ),
}


def metadata() -> DatasetMetadata:
    """Return the dataset card for this build."""
    return DatasetMetadata(
        dataset_id="error404/db-delay-hourly",
        dataset_version="0.1.0",
        name="German rail hourly station delay",
        description=(
            "Hourly mean delay, cancellation rate and train count per German station, "
            "windowed into one-week contexts with forecast, comparison and peak-hour targets."
        ),
        license="CC-BY-4.0",
        domains=("transport",),
        tags=("rail", "delay", "forecasting", "qa"),
        source_url="https://huggingface.co/datasets/piebro/deutsche-bahn-data",
    )


def grids_from_duckdb(con, month_start: dt.datetime, n_hours: int):
    """Read the hourly table and lay each station out on a complete hourly grid.

    Args:
        con: An open DuckDB connection holding the ``hourly`` table.
        month_start: The first hour of the month.
        n_hours: How many hours the month spans.

    Yields:
        One ``(station, grid, present)`` triple per station.
    """
    rows = con.execute(
        "SELECT station_name, hour, mean_delay, cancel_rate, trains FROM hourly ORDER BY 1, 2"
    ).fetchall()
    by_station: dict[str, list] = {}
    for station, hour, *values in rows:
        by_station.setdefault(station, []).append((hour, values))
    for station, entries in by_station.items():
        grid = {name: np.zeros(n_hours, dtype=np.float64) for name in CHANNELS}
        present = np.zeros(n_hours, dtype=bool)
        for hour, values in entries:
            index = int((hour - month_start).total_seconds() // 3600)
            if not 0 <= index < n_hours:
                continue
            present[index] = True
            for name, value in zip(CHANNELS, values, strict=True):
                grid[name][index] = value
        filled = {
            name: impute(grid[name], present, "zero" if name == "trains" else "interpolate")
            for name in CHANNELS
        }
        yield station, filled, present


def build(con, month_start: dt.datetime, n_hours: int) -> TimeFDataset:
    """Convert the hourly table into a TimeF dataset with one record per window."""
    dataset = TimeFDataset(metadata=metadata())
    for station, grid, present in grids_from_duckdb(con, month_start, n_hours):
        for window in build_windows(station, grid, present):
            slug = f"{station.replace(' ', '-').lower()}-{window.start_index:04d}"
            series = tuple(
                TimeSeries.from_values(
                    window.context[name].astype(np.float32),
                    spec=SPECS[name],
                    signal=name,
                    time_axis=HOURLY,
                    source_id=station,
                    time_series_id=f"{slug}-{name}",
                )
                for name in CHANNELS
            )
            record = dataset.add_record(
                time_series=series,
                subject_ids=(station,),
                record_id=slug,
                start_time=(month_start + dt.timedelta(hours=window.start_index)).replace(tzinfo=TZ),
            )
            record.add_annotations(
                [
                    Annotation(key="station", value=station, id=f"{slug}-station"),
                    Annotation(key="imputed_fraction", value=round(window.imputed_fraction, 4), id=f"{slug}-imp"),
                    Annotation(key="context_hours", value=CONTEXT_HOURS, id=f"{slug}-ctx"),
                ]
            )
            dataset.add_tasks(
                record,
                [
                    ScalarPredictionTask(
                        prompt=f"What is the mean delay in minutes at {station} over the next six hours?",
                        target=round(window.next_6h_mean_delay, 3),
                        unit="minute",
                        target_name="next_6h_mean_delay",
                        rationale=rationale_for_forecast(window),
                        id=f"{slug}-forecast",
                    ),
                    ClassificationTask(
                        prompt=f"Will the next day at {station} be worse than the past week's average?",
                        target="worse" if window.worse_than_context else "not_worse",
                        target_schema="worse|not_worse",
                        rationale=rationale_for_comparison(window),
                        id=f"{slug}-comparison",
                    ),
                    ClassificationTask(
                        prompt=f"At which hour of the coming day does delay peak at {station}?",
                        target=f"{window.peak_hour_of_next_day:02d}",
                        target_schema="00..23",
                        rationale=rationale_for_peak(window, window.horizon_delay),
                        id=f"{slug}-peak",
                    ),
                ],
            )
    return dataset
