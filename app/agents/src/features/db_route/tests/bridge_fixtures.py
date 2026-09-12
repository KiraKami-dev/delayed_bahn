"""Offline synthetic fixtures for the bridge and validator tests.

Everything here builds real ``timenet`` objects in memory -- a real
``TimeFDataset`` with real ``Record``s, ``TimeSeries`` and ``ClassificationTask``s
-- so the bridge and the validator are exercised against the actual types they
will meet in production, not against dicts that happen to have the right keys.
The one thing the fixtures fake is *where the data came from*.

A plain module rather than ``conftest``: that is the convention the sibling
suites already use (``tests/fixtures.py``), and importing helpers from a
conftest only works when pytest happens to have put ``tests/`` on ``sys.path``
first, which depends on which files the run collects.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

# The feature modules import each other flat (`from causes import ...`, see
# facts.py), so the feature directory has to be on the path rather than treated
# as a package. The tests directory goes on too, so sibling helpers import by name.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from profiles import Layer, TimelineProfile  # noqa: E402


timenet_types = pytest.importorskip("timenet.types")
timenet_dataset = pytest.importorskip("timenet.dataset")
timenet_axis = pytest.importorskip("timenet.dataset.axis")

Annotation = timenet_types.Annotation
ClassificationTask = timenet_types.ClassificationTask
DatasetMetadata = timenet_types.DatasetMetadata
Domain = timenet_types.Domain
License = timenet_types.License
TimeSeriesSpec = timenet_types.TimeSeriesSpec
Version = timenet_types.Version
ureg = timenet_types.ureg
TimeFDataset = timenet_dataset.TimeFDataset
TimeSeries = timenet_dataset.TimeSeries
RegularAxis = timenet_axis.RegularAxis

# One shared spec across several signals, on purpose: this is exactly the
# situation that makes captioning from `spec.name` wrong, and the fixture has to
# reproduce it or the caption test proves nothing.
DELAY_SPEC = TimeSeriesSpec(spec_type="delay", name="Delay", unit_value=ureg.minute)
SHARE_SPEC = TimeSeriesSpec(spec_type="share", name="Share", unit_value=ureg.dimensionless)

N_STEPS = 24
"""Divisible by 4, so the fixture obeys the same no-padding rule as production
while staying small enough that a whole test suite runs in a second."""

TINY = TimelineProfile(
    "TINY",
    "test/tiny",
    (Layer("week", "1 hour", N_STEPS, ("service_delay", "station_delay")),),
)
"""A two-signal, one-layer profile. Real ``Layer``/``TimelineProfile`` objects, so
the frozen validation in ``profiles.py`` still applies to the fixture."""


def daily_cycle(n: int = N_STEPS, *, shift: int = 0, level: float = 4.0, amp: float = 2.0) -> np.ndarray:
    """A rush-hour-shaped hourly signal, optionally phase-shifted.

    ``shift`` is the whole point: shifting one of a pair by one step is the
    synthetic form of a station/line timezone desynchronisation, which is what
    the phase check is for.
    """
    t = (np.arange(n) + shift) * 2.0 * np.pi / 24.0
    return level + amp * np.sin(t) + 0.3 * np.sin(2.0 * t)


def series(values, signal: str, *, layer: str = "week", spec=DELAY_SPEC) -> TimeSeries:
    """One series whose ``source_id`` carries the layer id.

    That is the ``caption:<layer>/<signal>`` spelling the bridge looks up second,
    and it is how a multi-scale record keeps three ``service_delay`` series
    distinguishable.
    """
    return TimeSeries.from_values(
        np.asarray(values, dtype=np.float32),
        spec=spec,
        signal=signal,
        source_id=layer,
        time_series_id=f"{layer}/{signal}",
        time_axis=RegularAxis.from_rate_hz(1),
    )


def make_dataset(dataset_id: str = "test/tiny") -> TimeFDataset:
    return TimeFDataset(
        metadata=DatasetMetadata(
            dataset_id=dataset_id,
            dataset_version=Version(0, 1, 0),
            name="Tiny",
            description="Synthetic offline fixture.",
            license=License.CC_BY_4_0,
            domains=(Domain.GENERAL,),
        )
    )


def add_sample(  # noqa: PLR0913
    dataset: TimeFDataset,
    record_id: str,
    *,
    split: str = "train",
    entity: str = "S8 -> Munich Ost @ Muenchen Ost",
    anchor: str = "2026-06-01",
    split_cell: str = "cell-0",
    bundle_sha: str = "sha-aaa",
    target: str = "minor",
    rationale: str = "The mean delay over the window is 4.0 minutes and works are active on 3 days.",
    slots: dict | None = None,
    imputed_fraction: float = 0.02,
    station_values=None,
    service_values=None,
    captions: bool = True,
    pre_prompt_context: str | None = "This is the S8 calling at Muenchen Ost on 2026-06-01.",
):
    """One record plus its classification task, wired the way the builder must wire it."""
    station = daily_cycle() if station_values is None else np.asarray(station_values, dtype=float)
    service = (
        daily_cycle(level=6.0, amp=2.5) if service_values is None
        else np.asarray(service_values, dtype=float)
    )
    record = dataset.add_record(
        record_id=record_id,
        time_series=(
            series(service, "service_delay"),
            series(station, "station_delay"),
        ),
    )
    annotations = [
        Annotation(key="split", value=split),
        Annotation(key="split_cell", value=split_cell),
        Annotation(key="entity", value=entity),
        Annotation(key="anchor", value=anchor),
        Annotation(key="artifact_bundle_sha", value=bundle_sha),
        Annotation(key="imputed_fraction", value=imputed_fraction),
        Annotation(
            key="rationale_slots",
            value=slots if slots is not None else {"mean_delay": 4.0, "works_days": 3},
        ),
    ]
    if captions:
        annotations += [
            Annotation(key="caption:week/service_delay", value="The mean delay of this service"),
            Annotation(key="caption:week/station_delay", value="The mean delay at this station"),
        ]
    if pre_prompt_context:
        annotations.append(Annotation(key="pre_prompt_context", value=pre_prompt_context))
    record.add_annotations(annotations)

    task = dataset.add_task(
        record,
        ClassificationTask(
            record_ids=(record.record_id,),
            prompt="How late will this service be next week?",
            target=target,
            rationale=rationale,
        ),
    )
    return record, task


# --- DuckDB source fixtures --------------------------------------------------

duckdb = pytest.importorskip("duckdb")

_EVENT_COLUMNS = (
    "id VARCHAR, train_line_ride_id VARCHAR, stop_number INTEGER, station_name VARCHAR, "
    "time TIMESTAMP, planned_time TIMESTAMP, actual_time TIMESTAMP, delay_in_min INTEGER"
)


def events_connection(rows):
    """An in-memory ``events`` table with the processed-parquet column names.

    The source checks take a connection and a relation name precisely so they can
    be pointed at this instead of at 26 months over HTTPS: same SQL, no network.
    """
    con = duckdb.connect()
    con.execute(f"CREATE TABLE events ({_EVENT_COLUMNS})")
    con.executemany(
        "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [tuple(r) for r in rows]
    )
    return con


def event_row(  # noqa: PLR0913
    ride: str,
    stop: int,
    when,
    *,
    station: str = "Muenchen Ost",
    delay: int = 3,
    stop_id: str | None = None,
    planned=None,
    actual=None,
):
    import datetime as dt

    planned = planned if planned is not None else when
    actual = actual if actual is not None else when + dt.timedelta(minutes=delay)
    return (
        stop_id or f"{ride}-{when:%y%m%d%H%M}-{stop}",
        ride,
        stop,
        station,
        when,
        planned,
        actual,
        delay,
    )
