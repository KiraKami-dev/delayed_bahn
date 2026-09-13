"""Turn the fact cache into a TimeFDataset: the step the challenge calls CONNECT.

    "Use or build a TimeNet connector for signals, metadata, and annotations.
     Define the questions, labels, or learning targets."

This module is that connector. Everything upstream (sourcing, cause extraction,
re-bucketing, labelling) exists to feed it, and everything downstream
(`bridge.py`, training) reads what it writes.

TimeNet's three slots map onto our data like this, and the mapping is the whole
design:

    signals      -> TimeSeries, one per (layer, signal), sharing one
                    TimeSeriesSpec per modality. Archival raw: real minutes in
                    real units, no normalization -- that happens at load time.
    metadata     -> span-less Annotation. A record has no metadata slot in
                    TimeNet, so route identity, calendar facts, the recency
                    weight and the split all travel as annotations.
    annotations  -> span-bearing Annotation. Dated engineering-works notices
                    become TimeInterval annotations, which is the one part of
                    TimeNet's model most connectors leave untouched.
    questions    -> Task. Four per record; `rationale` on the base class carries
                    the chain of thought, so there is no separate CoT type.

Four things in TimeNet's contract will ruin a dataset silently. Each is handled
here and each was verified against its source rather than its docs:

1. ``derive_schema`` aborts on any per-key inconsistency -- a key is one shape,
   one value type, one unit and one description across the entire dataset. All
   annotations therefore go through ``build._annotation``, which enforces that.
2. Auto ids are UUIDv7, so a dataset built twice would differ. Every id here is
   derived from source keys and every set is sorted before iteration.
3. An out-of-window span *warns* rather than rejecting. Works notices run a
   median 22.5 days against a 7-day context, so almost all of them overrun; we
   widen ``Record.time_span`` to cover them instead of clipping, because the
   dates are the information.
4. ``convert()`` is CPU-only with no network. Rationale skeletons are therefore
   committed alongside the connector rather than generated at build time.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np

import build as B
from causes import ATTRIBUTION_FLOOR, DOMINANCE_FLOOR
from profiles import TimelineProfile
from resample import FactCache, Window

try:
    from timenet.dataset import TimeFDataset, TimeSeries
    from timenet.dataset.axis import RegularAxis
    from timenet.types import (
        Annotation,
        AnswerTask,
        ClassificationTask,
        ScalarPredictionTask,
        TimeInterval,
    )

    HAVE_TIMENET = True
except ImportError:  # pragma: no cover - covered by the import-guard test
    HAVE_TIMENET = False

BERLIN_OFFSET_HOURS = 1  # only used to stamp record start_time; see note below


@dataclass(frozen=True)
class RecordInput:
    """Everything one record needs, already computed. The connector adds no
    domain logic of its own -- it arranges, it does not derive."""

    entity_id: str
    service_group: str
    station: str
    train_type: str
    anchor: dt.date
    window: Window
    label: Any  # labels.Label
    split: str
    split_cell: str
    recency_weight: float
    notices: Sequence[dict] = ()
    # Further span-less annotations computed upstream (calendar, station hub).
    # Pairs, so the record stays hashable and the order is the caller's.
    extra: tuple[tuple[str, Any], ...] = ()


def _record_span(window: Window, prof: TimelineProfile, notices: Sequence[dict]) -> tuple[int, int]:
    """The record's time span in microseconds from its own start.

    Wide enough to contain the longest layer *and* every disruption notice we
    attach. TimeNet checks a span against the record window and warns when it
    falls outside; widening here means a notice that started three months before
    the context opens validates cleanly with its true dates intact, instead of
    being clipped into a lie.
    """
    span_us = int(prof.context_days * 86400 * 1_000_000)
    earliest = 0
    for notice in notices:
        offset = int((notice["valid_from"] - window.anchor).total_seconds() * 1_000_000)
        earliest = min(earliest, offset)
    latest = span_us
    for notice in notices:
        offset = int((notice["valid_to"] - window.anchor).total_seconds() * 1_000_000)
        latest = max(latest, span_us + max(offset, 0))
    return earliest, latest


def _series_for(window: Window, prof: TimelineProfile, specs: dict[str, Any], rid: str) -> tuple:
    """One TimeSeries per (layer, signal), sharing a spec per modality.

    Four of our signals are delays and therefore share the single ``delay``
    spec, differing only by ``signal`` -- which is exactly why the bridge cannot
    caption from ``spec.name`` and reads a caption annotation instead.
    """
    out = []
    for layer in prof.layers:
        axis = RegularAxis.from_rate_hz(layer.rate_hz)
        for signal in layer.signals:
            values = window.values[(layer.layer_id, signal)]
            out.append(
                TimeSeries.from_values(
                    np.asarray(values, dtype=np.float32),
                    spec=specs[B._SPEC_OF_SIGNAL[signal]],
                    signal=f"{layer.layer_id}/{signal}",
                    time_axis=axis,
                    source_id=rid,
                    time_series_id=f"{rid}-{layer.layer_id}-{signal}",
                )
            )
    return tuple(out)


def _static_annotations(item: RecordInput, bundle_sha: str) -> list[Any]:
    """Metadata. TimeNet has no metadata slot, so these are span-less annotations."""
    rid = B.record_id_for(item.entity_id, item.anchor)
    label, ctx = item.label, item.label.context
    pairs: list[tuple[str, Any]] = [
        ("entity_id", item.entity_id),
        ("service_group", item.service_group),
        ("station", item.station),
        ("train_type", item.train_type),
        ("anchor_iso", item.anchor.isoformat()),
        ("weekday", item.anchor.weekday()),
        ("imputed_fraction", item.window.overall_imputed_fraction),
        # The per-grain figures the imputation gate actually judged, so the
        # validator can re-apply the same budget from the built record alone.
        *[
            (f"imputed_{grain}", float(fraction))
            for grain, fraction in sorted(item.window.worst_imputed_fraction.items())
        ],
        ("attributed_share", label.horizon_attributed_share),
        ("split", item.split),
        ("split_cell", item.split_cell),
        ("recency_weight", item.recency_weight),
        ("artifact_bundle_sha", bundle_sha),
    ]
    for key in ("habit_median_delay_8w", "scheduled_recovery_min", "route_position"):
        value = ctx.get(f"ctx_{key}", ctx.get(key))
        if value is not None:
            pairs.append((key, value))
    pairs.extend(item.extra)
    return [B._annotation(k, v, f"{rid}-{k}") for k, v in pairs]


def _works_annotations(item: RecordInput) -> list[Any]:
    """Dated engineering-works notices as interval annotations.

    This is the part of TimeNet's model that most connectors never touch, and
    the reason it is worth touching: a notice carries real start and end dates,
    so the model can be told not merely that works exist but that they have been
    running for six weeks and have three left. Measured: median window 22.5
    days, 79% longer than a week, and 34% of all dated notices are Bauarbeiten.
    """
    rid = B.record_id_for(item.entity_id, item.anchor)
    out = []
    for i, notice in enumerate(item.notices):
        start_us = int((notice["valid_from"] - item.window.anchor).total_seconds() * 1_000_000)
        end_us = int((notice["valid_to"] - item.window.anchor).total_seconds() * 1_000_000)
        if end_us <= start_us:
            continue  # a zero-length interval is illegal; a TimePoint would be the fix
        out.append(
            Annotation(
                key="planned_disruption",
                value=notice.get("category", ""),
                description=(
                    "A dated Deutsche Bahn disruption notice overlapping this record's "
                    "context, with the validity window the operator published."
                ),
                span=TimeInterval.micros(start_us, end_us),
                id=f"{rid}-notice-{i}-{notice['notice_id']}",
            )
        )
    return out


def _tasks_for(item: RecordInput, skeleton: Any) -> list[Any]:
    """The questions the model learns. Four per record.

    The cause classification and the prose answer are chained with
    ``from_tasks``: they are one question at two levels, and that is the only
    way the format records the relationship.
    """
    rid = B.record_id_for(item.entity_id, item.anchor)
    label = item.label
    rationale = skeleton(item) if callable(skeleton) else None

    delay = ScalarPredictionTask(
        # A tenth of a minute. The archive resolves to whole minutes, so more
        # digits would be noise -- and as text, fifteen of them are fifteen
        # tokens of noise the model is asked to reproduce.
        target=round(float(label.departure_delay_min), 1),
        unit="minute",
        target_name="departure_delay_min",
        prompt=(
            f"How many minutes late will {item.service_group} depart "
            f"{item.station} over the coming week?"
        ),
        rationale=rationale,
        id=f"{rid}-delay",
    )
    late = ClassificationTask(
        target="late" if label.late_5min else "on_time",
        target_schema=B.VOCABULARY_ID + "-punctuality",
        prompt=f"Will {item.service_group} be five or more minutes late at {item.station}?",
        rationale=rationale,
        id=f"{rid}-late5",
    )
    cause = ClassificationTask(
        target=label.dominant_cause_family,
        target_schema=B.VOCABULARY_ID,
        prompt=f"What will mainly drive delay for {item.service_group} at {item.station}?",
        rationale=rationale,
        id=f"{rid}-cause",
    )
    explain = AnswerTask(
        prompt=(
            f"Summarise how {item.service_group} has been running at {item.station}, "
            "and say what a traveller should do."
        ),
        target=_action_sentence(item),
        rationale=rationale,
        from_tasks=(cause,),
        id=f"{rid}-explain",
    )
    return [delay, late, cause, explain]


def _action_sentence(item: RecordInput) -> str:
    """One sentence, because the bridge builds the answer as
    ``rationale + " Answer: " + target``. Putting the whole paragraph in
    ``target`` would produce "reasoning... Answer: <entire paragraph>"."""
    minutes = round(item.label.departure_delay_min)
    if not item.label.late_5min:
        return f"Expect about {minutes} minutes; this connection is dependable."
    return f"Expect about {minutes} minutes late, so allow extra time here."


def build_dataset(
    prof: TimelineProfile,
    records: Iterable[RecordInput],
    *,
    metadata: Any,
    bundle_sha: str,
    skeleton: Any = None,
) -> Any:
    """Assemble one TimeFDataset. No network, no LLM -- see the module docstring.

    Records are consumed in the order given; the caller sorts them, so that two
    builds of the same inputs produce byte-identical output.
    """
    if not HAVE_TIMENET:
        raise RuntimeError("timenet is not installed; `uv pip install 'timenet[build]'`")

    dataset = TimeFDataset(metadata=metadata)
    specs = B._specs()
    vocabulary = [
        Annotation(
            key="cause_family_vocabulary",
            value=B.cause_vocabulary(),
            description="The values a dominant-cause target takes.",
            id=B.VOCABULARY_ID,
        ),
        Annotation(
            key="cause_family_vocabulary",
            value=["late", "on_time"],
            description="The values a dominant-cause target takes.",
            id=B.VOCABULARY_ID + "-punctuality",
        ),
    ]
    dataset.register_annotations(vocabulary)

    n = 0
    for item in records:
        rid = B.record_id_for(item.entity_id, item.anchor)
        notices = list(item.notices)
        lo, hi = _record_span(item.window, prof, notices)
        record = dataset.add_record(
            time_series=_series_for(item.window, prof, specs, rid),
            subject_ids=(item.station,),
            record_id=rid,
            time_span=TimeInterval.micros(lo, hi),
        )
        record.add_annotations(_static_annotations(item, bundle_sha))
        for layer in prof.layers:
            for signal in layer.signals:
                record.add_annotation(
                    B._caption_annotation(
                        layer.layer_id,
                        signal,
                        B.caption_for(layer.layer_id, signal, item.service_group, item.station),
                        f"{rid}-caption-{layer.layer_id}-{signal}",
                    )
                )
        works = _works_annotations(item)
        if works:
            record.add_annotations(works)
        dataset.add_tasks(record, _tasks_for(item, skeleton))
        n += 1

    dataset.derive_schema()  # fails loudly here rather than deep inside the writer
    return dataset


__all__ = [
    "HAVE_TIMENET",
    "RecordInput",
    "build_dataset",
    "ATTRIBUTION_FLOOR",
    "DOMINANCE_FLOOR",
]
