"""Write trip examples as a TimeF dataset: four series, annotations and two tasks per record.

Each record's relative zero is local midnight 30 days before the prediction moment. The daily
history starts there; the two hourly series start 72 hours before the hour of the prediction
moment. The run's delays sit on an ordinal axis, because they follow stops, not a clock.

Records and annotations are materialised; the tasks are streamed (``set_task_stream``), because
``add_tasks`` re-collects every registered task and record id on each call, which makes a
record-by-record export quadratic in the number of examples.
"""

from __future__ import annotations

import argparse
import sys
import time
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from timenet.dataset import TimeFDataset, TimeSeries
from timenet.dataset.axis import OrdinalAxis, RegularAxis
from timenet.types import (Annotation, ClassificationTask, DataSource, DatasetMetadata, ScalarPredictionTask, Task,
                           TimeSeriesSpec, ureg)

sys.path.insert(0, str(Path(__file__).parent))

import prompts  # noqa: E402

TZ = ZoneInfo("Europe/Berlin")
HISTORY_DAYS = 30
SERIES_HOURS = 72
DAY = Fraction(1, 86_400)
HOUR = Fraction(1, 3_600)
CARD = Path(__file__).parent / "timenet_connector" / "dataset.yaml"
SOURCE = DataSource(
    data_source_type="operational-record",
    name="Deutsche Bahn timetable scrape",
    provider="piebro/deutsche-bahn-data",
)
SPECS = {
    "run_departure_delay": TimeSeriesSpec(spec_type="run-departure-delay", name="Departure delay at each stop so far",
                                          unit_value=ureg.minute, data_source=SOURCE),
    "history_daily_median_delay": TimeSeriesSpec(spec_type="history-arrival-delay", name="Daily median arrival delay, last 30 days",
                                                 unit_value=ureg.minute, data_source=SOURCE),
    "station_late_share": TimeSeriesSpec(spec_type="station-late-share", name="Hourly share of late stops at the target station",
                                         unit_value=ureg.dimensionless, data_source=SOURCE),
    "network_late_share": TimeSeriesSpec(spec_type="network-late-share", name="Hourly share of late stops for the train class",
                                         unit_value=ureg.dimensionless, data_source=SOURCE),
}
ANNOTATED = ("split", "cls", "train_type", "train_number", "origin", "dest", "k_station", "hist_level",
             "pre_departure", "lead_minutes", "stops_ahead", "current_delay")
TASK_TYPES = (ClassificationTask, ScalarPredictionTask)


def _check_record_refs_without_scan(self: TimeFDataset, task: Task) -> None:
    """TimeNet rebuilds the set of every record id for each streamed task, even for task types
    that carry no record references; that makes the write quadratic. Skip the scan for those."""
    if type(task).refs.record_id_fields:
        _check_record_refs_original(self, task)


_check_record_refs_original = TimeFDataset._check_record_refs
TimeFDataset._check_record_refs = _check_record_refs_without_scan  # type: ignore[method-assign]


def record_id(row: pd.Series) -> str:
    """The record id of one example."""
    return f"trip-{int(row['example_id'])}"


def plain(value):
    """A cell as a plain Python scalar that TimeF annotations accept."""
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and np.isnan(value):
        return None
    return value


def add_example(dataset: TimeFDataset, row: pd.Series) -> None:
    """Append one example as a record with its series and annotations; the tasks are streamed."""
    rid = record_id(row)
    t0 = pd.Timestamp(row["t0"])
    zero = (t0.normalize() - pd.Timedelta(days=HISTORY_DAYS)).to_pydatetime()
    hourly_start = int((t0.floor("h") - pd.Timedelta(hours=SERIES_HOURS) - pd.Timestamp(zero)) / pd.Timedelta(hours=1))
    parts = [
        ("history_daily_median_delay", row["hist_series"], RegularAxis.from_rate_hz(DAY)),
        ("station_late_share", row["station_series"], RegularAxis(period_us=RegularAxis.from_rate_hz(HOUR).period_us,
                                                                  start_index=hourly_start)),
        ("network_late_share", row["network_series"], RegularAxis(period_us=RegularAxis.from_rate_hz(HOUR).period_us,
                                                                  start_index=hourly_start)),
    ]
    run = prompts.as_list(row["run_delays"])
    if run:  # before departure there is no stop yet, so the record has no run series
        parts.insert(0, ("run_departure_delay", run, OrdinalAxis()))
    series = tuple(
        TimeSeries.from_values(np.asarray(values, dtype=np.float32), spec=SPECS[signal], signal=signal,
                               time_axis=axis, source_id=rid, time_series_id=f"{rid}-{signal}")
        for signal, values, axis in parts
    )
    record = dataset.add_record(time_series=series, subject_ids=(prompts.train_label(row),), record_id=rid,
                                start_time=zero.replace(tzinfo=TZ))
    # TimeF rejects an annotation without a value, so fields the scrape lost are left out.
    values = {key: plain(row[key]) for key in ANNOTATED}
    annotations = [Annotation(key=key, value=value, id=f"{rid}-{key}") for key, value in values.items() if value is not None]
    annotations += [
        Annotation(key="prediction_moment", value=t0.isoformat(), id=f"{rid}-t0"),
        Annotation(key="planned_arrival", value=pd.Timestamp(row["k_arr_pt"]).isoformat(), id=f"{rid}-arr"),
    ]
    record.add_annotations(annotations)


def example_tasks(row: pd.Series) -> list[Task]:
    """The tasks of one example, attached to its record: cancellation, and the delay when it runs."""
    rid = record_id(row)
    stop = prompts.name(row["k_station"])
    tasks: list[Task] = [ClassificationTask(prompt=f"Will the train be cancelled at {stop}?",
                                            target="cancelled" if row["cancelled"] else "runs",
                                            target_schema="cancelled|runs", id=f"{rid}-cancelled")]
    if not row["cancelled"]:
        tasks.append(ScalarPredictionTask(prompt=f"How many minutes late will the train arrive at {stop}?",
                                          target=float(row["target_minutes"]), unit="minute",
                                          target_name="arrival_delay_minutes", rationale=prompts.rationale(row),
                                          id=f"{rid}-delay"))
    for task in tasks:  # streamed tasks carry their record ids themselves
        task.record_ids = (rid,)
    return tasks


def to_timef(frame: pd.DataFrame, metadata: DatasetMetadata) -> TimeFDataset:
    """Convert a frame of built examples into a TimeF dataset with streamed tasks."""
    dataset = TimeFDataset(metadata=metadata)
    for i in range(len(frame)):
        add_example(dataset, frame.iloc[i])

    def tasks():
        # The writer iterates the source more than once, so build the tasks afresh each time.
        for i in range(len(frame)):
            yield from example_tasks(frame.iloc[i])

    dataset.set_task_stream(TASK_TYPES, tasks)
    return dataset


def verify(path: Path) -> dict:
    """Open a written version, run TimeNet's integrity check, and count what it holds."""
    from timenet.reader.reader import TimeFReader
    from timenet.registry.version import DatasetVersion

    with TimeFReader(DatasetVersion.open_local(path)) as reader:
        reader.verify()
        tasks = reader.tasks() if callable(reader.tasks) else reader.tasks
        records = sum(1 for _ in reader.iter_records())
        metadata = reader.metadata() if callable(reader.metadata) else reader.metadata
    return {"dataset_id": metadata.dataset_id, "version": str(metadata.dataset_version),
            "records": records, "tasks": len(tasks)}


def main() -> None:
    """Export built examples to TimeF and read the result back."""
    from timenet.writer.writer import TimeFWriter

    parser = argparse.ArgumentParser()
    parser.add_argument("--examples", default="data/trip/examples.parquet")
    parser.add_argument("--out", default="out/trip/timef")
    parser.add_argument("--split", choices=["train", "validation", "test"])
    parser.add_argument("--limit", type=int)
    parser.add_argument("--verify-only", help="a written version directory to check instead of exporting")
    args = parser.parse_args()
    if args.verify_only:
        print("verified:", verify(Path(args.verify_only)))
        return

    frame = pd.read_parquet(args.examples)
    if args.split:
        frame = frame[frame["split"] == args.split]
    if args.limit:
        frame = frame.sample(n=min(args.limit, len(frame)), random_state=0)
    started = time.time()
    dataset = to_timef(frame.reset_index(drop=True), DatasetMetadata.from_yaml(CARD))
    converted = time.time() - started
    dataset.derive_schema()
    root = Path(args.out)
    with TimeFWriter(root, dataset) as writer:
        writer.write()
    path = root / dataset.metadata.dataset_id / str(dataset.metadata.dataset_version)
    print(f"converted {len(frame)} examples in {converted:.1f}s, wrote {path} in {time.time() - started - converted:.1f}s")
    print(f"in memory: {len(dataset.records)} records, {sum(1 for _ in dataset.iter_tasks())} tasks streamed")
    print("verified:", verify(path))


if __name__ == "__main__":
    main()
