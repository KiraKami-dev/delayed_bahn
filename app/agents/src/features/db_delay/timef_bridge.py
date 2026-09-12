"""Feed any TimeF dataset into OpenTSLM training.

OpenTSLM does not depend on TimeNet: its requirements name neither the package
nor the format, and each of its dataset classes loads its own source directly.
So nothing here reads a TimeF dataset into a training set, and this module is
that missing piece. It is deliberately generic: it reads TimeF records, series
and tasks, and knows nothing about rail.

The formatting follows the convention OpenTSLM's own chain-of-thought datasets
use. Each series is z-normalised and its mean and standard deviation are stated
in the text, so the model can recover real units. The answer is the rationale
with the target appended, because the base class takes the whole answer string
from one field.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Literal

import numpy as np
from opentslm.prompt.text_time_series_prompt import TextTimeSeriesPrompt
from opentslm.time_series_datasets.QADataset import QADataset

MIN_STD = 1e-6
Row = dict[str, Any]
SplitName = Literal["train", "validation", "test"]


def rows_from_timef(dataset, assign_split: Callable[[Any, Any], SplitName | None]) -> dict[str, list[Row]]:
    """Flatten a TimeF dataset into one row per task, bucketed by split.

    Args:
        dataset: A built ``TimeFDataset``.
        assign_split: Called with a record and a task. Returns the split the pair
            belongs to, or None to drop it. This is where leakage control lives:
            hold stations and time ranges apart here, not downstream.

    Returns:
        A mapping from split name to its rows.
    """
    by_id = {record.record_id: record for record in dataset.records}
    buckets: dict[str, list[Row]] = {"train": [], "validation": [], "test": []}
    for task in dataset.tasks:
        for record_id in task.record_ids:
            record = by_id.get(record_id)
            if record is None:
                continue
            split = assign_split(record, task)
            if split is None:
                continue
            buckets[split].append(
                {
                    "record_id": record_id,
                    "subjects": record.subject_ids,
                    "series": [(s.signal, s.to_numpy()) for s in record.time_series],
                    "spec_names": {s.signal: s.spec.name for s in record.time_series},
                    "units": {s.signal: str(s.spec.unit_value) for s in record.time_series},
                    "prompt": task.prompt or "",
                    "target": task.target,
                    "rationale": task.rationale or "",
                    "task_type": type(task).__name__,
                }
            )
    return buckets


def format_target(target: Any) -> str:
    """Render a task target as the string the model has to produce."""
    if isinstance(target, float):
        return f"{target:.2f}"
    return str(target)


class TimeFQADataset(QADataset):
    """An OpenTSLM training set backed by a TimeF dataset.

    Subclasses set :attr:`SPLITS` before construction. The base class caches the
    formatted splits on the class, so build the buckets first and construct after.
    """

    SPLITS: dict[str, list[Row]] = {}

    def _load_splits(self) -> tuple[Sequence[Row], Sequence[Row], Sequence[Row]]:
        """Return the train, validation and test rows prepared by :func:`rows_from_timef`."""
        if not self.SPLITS:
            raise RuntimeError("Set SPLITS on the subclass before constructing it")
        return self.SPLITS["train"], self.SPLITS["validation"], self.SPLITS["test"]

    def _get_pre_prompt(self, row: Row) -> str:
        """Describe the situation and the channels before the series arrive."""
        subject = ", ".join(row["subjects"]) or row["record_id"]
        channels = ", ".join(
            f"{row['spec_names'][signal].lower()} in {row['units'][signal]}" for signal, _ in row["series"]
        )
        return (
            f"You are given hourly measurements for {subject} covering one week, "
            f"in this order: {channels}. Each series is normalised; its mean and "
            f"standard deviation are given so you can recover real units."
        )

    def _get_post_prompt(self, row: Row) -> str:
        """State the question, then ask for the reasoning."""
        return f"{row['prompt']}\nRationale:"

    def _get_answer(self, row: Row) -> str:
        """Return the chain of thought with the target appended, as the base class expects."""
        rationale = row["rationale"].strip()
        answer = format_target(row["target"])
        return f"{rationale} Answer: {answer}" if rationale else f"Answer: {answer}"

    def _get_text_time_series_prompt_list(self, row: Row) -> list[TextTimeSeriesPrompt]:
        """Z-normalise every series and state its mean and standard deviation in the text."""
        prompts = []
        for signal, values in row["series"]:
            series = np.asarray(values, dtype=np.float64)
            mean = float(series.mean())
            std = max(float(series.std()), MIN_STD)
            normalised = (series - mean) / std
            if not np.isfinite(normalised).all():
                raise ValueError(f"non-finite values in {row['record_id']} / {signal}")
            label = row["spec_names"][signal]
            prompts.append(
                TextTimeSeriesPrompt(
                    f"{label}, it has mean {mean:.4f} and std {std:.4f}:", normalised.tolist()
                )
            )
        return prompts
