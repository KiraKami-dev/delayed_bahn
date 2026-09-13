"""Assemble a TimeFDataset: where the fact cache, the labels and TimeNet meet.

This is the integrator. Every other module has one job and a clean contract;
this one knows how all of them fit together, which is why it is not delegated.

Four things in TimeNet's contract will silently ruin a dataset if you get them
wrong, all verified against its source rather than its docs:

1. **``derive_schema`` aborts the build on any per-key inconsistency.** The
   descriptor is ``(key, annotation_type, value_type, unit, description)`` and
   two annotations sharing a key with any differing component raise. So
   ``value=3`` on one record and ``value=3.0`` on another kills the build; a key
   used span-less on one record and with a span on another kills the build. A
   key is one shape, forever. Hence ``_ANNOTATION_SPEC`` below: every key is
   declared once with its caster and its description, and nothing writes an
   annotation any other way.

2. **Auto-generated ids are UUIDv7** -- timestamped and random -- so a dataset
   built twice differs. Every id here is derived from source keys, and every set
   is sorted before iteration. The framework hashes its outputs but never its
   inputs, and skips a rebuild purely on ``dataset_version`` existing, so
   reproducibility is entirely ours to enforce.

3. **An out-of-window span warns, it does not reject** (``warn_when_outside``
   defaults True). Disruption notices run a median 22.5 days against a 7-day
   context, so almost every one overruns. We widen ``Record.time_span`` to cover
   them rather than clipping -- clipping would destroy the dates, which are the
   information we want.

4. **A record has no metadata slot.** Every static fact is a span-less
   ``Annotation``. That includes ``split``, which is how leakage control travels
   with the dataset instead of living in a downstream script.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Iterable, NamedTuple

import numpy as np

from causes import SERIES_FAMILIES, describe
from profiles import TimelineProfile

# TimeNet is an optional import so the module stays testable, and so a
# `convert`-only unit test never needs the build extra installed.
try:
    from timenet.dataset import TimeFDataset, TimeSeries
    from timenet.dataset.axis import RegularAxis
    from timenet.types import (
        Annotation,
        AnswerTask,
        ClassificationTask,
        DataSource,
        ScalarPredictionTask,
        TimeInterval,
        TimeSeriesSpec,
        ureg,
    )

    TIMENET_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised by the import guard test
    TIMENET_AVAILABLE = False


# --- specs ------------------------------------------------------------------
# One TimeSeriesSpec per *modality*, not per signal: TimeNet keys the schema on
# spec_type, and every signal of a modality shares the spec, differing only by
# its `signal` name. Four of our series are delays, so four share one spec --
# which is exactly why the bridge cannot caption from spec.name (see bridge.py).

SOURCE_NAME = "Deutsche Bahn timetable scrape"
SOURCE_PROVIDER = "piebro/deutsche-bahn-data"

_SPEC_OF_SIGNAL: dict[str, str] = {
    "service_delay": "delay",
    "station_delay": "delay",
    "service_at_station_delay": "delay",
    "station_cancel_rate": "cancellation-rate",
    "station_throughput": "throughput",
    "service_throughput": "throughput",
    "works_share": "cause-share",
    "weather_share": "cause-share",
    "technical_share": "cause-share",
    "knock_on_share": "cause-share",
    "attributed_share": "attribution-share",
}

_SPEC_UNITS = {
    "delay": "minute",
    "cancellation-rate": "dimensionless",
    "throughput": "dimensionless",
    "cause-share": "dimensionless",
    "attribution-share": "dimensionless",
}

_SPEC_NAMES = {
    "delay": "Mean delay",
    "cancellation-rate": "Cancellation rate",
    "throughput": "Stop events per bucket",
    "cause-share": "Share of attributed delay minutes",
    "attribution-share": "Share of stops carrying a cause",
}


def _specs() -> dict[str, Any]:
    source = DataSource(
        data_source_type="operational-record", name=SOURCE_NAME, provider=SOURCE_PROVIDER
    )
    return {
        spec_type: TimeSeriesSpec(
            spec_type=spec_type,
            name=_SPEC_NAMES[spec_type],
            unit_value=getattr(ureg, _SPEC_UNITS[spec_type]),
            data_source=source,
        )
        for spec_type in sorted(_SPEC_NAMES)
    }


# --- annotation contract ----------------------------------------------------
# key -> (caster, unit, description). The caster is the whole point: it forces
# one Python type per key, so `derive_schema` cannot trip over int-vs-float. The
# description lives here rather than at the call site because it is *type-level*
# in TimeNet -- every annotation sharing a key must carry the same one.


class AnnSpec(NamedTuple):
    cast: Callable[[Any], Any]
    unit: str | None
    description: str


_ANNOTATION_SPEC: dict[str, AnnSpec] = {
    "entity_id": AnnSpec(str, None, "Service group and station this record is about."),
    "service_group": AnnSpec(str, None, "Train type and final destination, the service identity."),
    "station": AnnSpec(str, None, "Station the prediction is made at."),
    "train_type": AnnSpec(str, None, "Product class: S, RB, RE, ICE and so on."),
    "anchor_iso": AnnSpec(str, None, "Local midnight starting the travel day; every series ends here."),
    "weekday": AnnSpec(int, None, "Day of week of the anchor, Monday = 0."),
    "scheduled_time_local": AnnSpec(str, None, "Scheduled time of the stop being predicted."),
    "route_position": AnnSpec(int, None, "Index of this stop within the run."),
    "scheduled_recovery_min": AnnSpec(float, "minute", "Timetable slack before the next stop."),
    "run_delay_last": AnnSpec(float, "minute", "Delay at the previous stop of this run today."),
    "run_delay_trend": AnnSpec(float, "minute", "Minutes gained or lost per stop so far today."),
    "stops_elapsed": AnnSpec(int, None, "Stops already made on this run today."),
    "habit_median_delay_8w": AnnSpec(float, "minute", "Median delay for this service here over eight weeks."),
    "imputed_fraction": AnnSpec(float, None, "Share of context buckets filled by imputation."),
    "imputed_station": AnnSpec(float, None, "Imputed share of buckets in which the station had traffic; the gate applied."),
    "imputed_line": AnnSpec(float, None, "Imputed share of buckets in which the service group ran anywhere; the gate applied."),
    "imputed_pair": AnnSpec(float, None, "Imputed share of buckets in which both station and service were live; the gate applied."),
    "attributed_share": AnnSpec(float, None, "Share of delayed stops carrying any cause code."),
    "dominant_cause_code": AnnSpec(int, None, "IRIS cause code holding the largest share, or 0."),
    "dominant_cause_text": AnnSpec(str, None, "German text of the dominant cause."),
    "works_window_coverage": AnnSpec(float, None, "Share of the context window under a works notice."),
    "split": AnnSpec(str, None, "train, validation or test."),
    "split_cell": AnnSpec(str, None, "Leakage cell: which of entity and time is held out."),
    "recency_weight": AnnSpec(float, None, "Exponential weight on anchor age, 90-day half-life."),
    "federal_state": AnnSpec(str, None, "Bundesland of the station, from the db-stations hub."),
    "station_category": AnnSpec(int, None, "DB station category 1 (largest hub) to 7, from db-stations."),
    "station_weight": AnnSpec(float, None, "db-stations footfall weight; München Hbf is ~1035."),
    "horizon_public_holidays": AnnSpec(int, None, "Public holidays in this Bundesland during the seven-day horizon."),
    "horizon_school_holiday_share": AnnSpec(float, None, "Share of horizon days inside a school holiday in this Bundesland."),
    "days_to_school_holiday_start": AnnSpec(int, None, "Days from the anchor to the next school holiday start; 0 if inside one; capped at 60."),
    "days_since_school_holiday_end": AnnSpec(int, None, "Days since the last school holiday ended; 0 if inside one; capped at 60."),
    "artifact_bundle_sha": AnnSpec(str, None, "Hash of the shared artifacts every profile was built from."),
    "pre_prompt_context": AnnSpec(str, None, "Prose context the bridge renders into the prompt."),
    "cause_family_vocabulary": AnnSpec(list, None, "The values a dominant-cause target takes."),
}

# Captions are one key per (layer, signal), declared dynamically but always with
# the same shape and description so the schema stays consistent.
_CAPTION_DESCRIPTION = "Human-readable identity and window of one series, read by the bridge."


def _annotation(key: str, value: Any, ident: str) -> Any:
    """Build an annotation through the contract, or fail loudly."""
    try:
        spec = _ANNOTATION_SPEC[key]
    except KeyError:
        raise KeyError(
            f"annotation key {key!r} is not declared in _ANNOTATION_SPEC. Declare it there with a "
            f"caster and a description -- TimeNet's derive_schema aborts the build if one key ever "
            f"varies in type, unit or description across records."
        ) from None
    return Annotation(
        key=key, value=spec.cast(value), unit=spec.unit, description=spec.description, id=ident
    )


def _caption_annotation(layer_id: str, signal: str, text: str, ident: str) -> Any:
    return Annotation(
        key=f"caption:{layer_id}/{signal}",
        value=str(text),
        description=_CAPTION_DESCRIPTION,
        id=ident,
    )


# --- captions ---------------------------------------------------------------
# The caption is the only channel through which a series' identity *and* its
# absolute scale reach the model, since values arrive z-scored. The bridge
# appends "it has mean X and std Y"; this supplies the half that names the thing.

_SIGNAL_PHRASE = {
    "service_delay": "Mean delay of {service} across its stops",
    "station_delay": "Mean delay of all trains at {station}",
    "service_at_station_delay": "Mean delay of {service} at {station}",
    "station_cancel_rate": "Cancellation rate at {station}",
    "station_throughput": "Stop events per bucket at {station}",
    "service_throughput": "Stop events per bucket made by {service} anywhere on the network",
    "works_share": "Share of delay at {station} attributed to engineering works",
    "weather_share": "Share of delay at {station} attributed to weather",
    "technical_share": "Share of delay at {station} attributed to technical faults",
    "knock_on_share": "Share of delay at {station} imported from other trains",
    "attributed_share": "Share of delayed stops at {station} carrying any cause",
}

_WINDOW_PHRASE = {
    "week": "hourly over the past week",
    "quarter": "six-hourly over the past two months",
    "season": "daily over the past four months",
}


def caption_for(layer_id: str, signal: str, service: str, station: str) -> str:
    return (
        f"{_SIGNAL_PHRASE[signal].format(service=service, station=station)}, "
        f"{_WINDOW_PHRASE[layer_id]}"
    )


def _slug(text: str) -> str:
    """A stable, filesystem-and-id-safe token derived from source text."""
    keep = [c if c.isalnum() else "-" for c in text.lower()]
    return "".join(keep).strip("-")[:48] or "x"


def record_id_for(entity_id: str, anchor: dt.date) -> str:
    """Deterministic and readable. Never a UUID -- see module docstring."""
    return f"{_slug(entity_id)}-{anchor.isoformat()}"


def artifact_bundle_sha(paths: Iterable[Path]) -> str:
    """One hash over the shared artifacts, so cross-profile identity is checkable.

    Every profile carries this. If two datasets disagree, they were not built
    from the same anchors, labels or splits, and the bake-off comparing them is
    meaningless -- so the validator asserts equality rather than trusting it.
    """
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda p: p.name):
        digest.update(path.name.encode())
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def works_intervals(notices: list[dict], window_start: dt.datetime, window_end: dt.datetime) -> list[dict]:
    """Disruption notices overlapping the context window.

    Not clipped. TimeNet warns on an out-of-window span rather than rejecting
    it, and the record's ``time_span`` is widened to cover these instead, so the
    real dates survive into the dataset. That matters: a notice in week one of
    nine behaves differently from one in week eight, and clipping erases the
    difference.
    """
    out = []
    for notice in notices:
        if notice["valid_to"] <= window_start or notice["valid_from"] >= window_end:
            continue
        overlap_start = max(notice["valid_from"], window_start)
        overlap_end = min(notice["valid_to"], window_end)
        span = (window_end - window_start).total_seconds()
        out.append(
            {
                **notice,
                "coverage": (overlap_end - overlap_start).total_seconds() / span if span else 0.0,
            }
        )
    return sorted(out, key=lambda n: (n["valid_from"], n["notice_id"]))


def cause_vocabulary() -> list[str]:
    """The closed set a dominant-cause target draws from.

    Registered as an annotation and named by each ClassificationTask's
    ``target_schema``. A bare schema name tells a consumer nothing about what is
    in the set; the id of an annotation holding the members does.
    """
    return [*sorted(SERIES_FAMILIES), "unattributed"]


VOCABULARY_ID = "db-route-vocabulary-cause-family"


def describe_cause(code: int) -> str:
    return describe(code) if code else "keine Ursache gemeldet"


def z_safe(values: np.ndarray) -> tuple[np.ndarray, float, float]:
    """Standardise, and refuse the degenerate case loudly.

    A constant series z-scores to NaN and then poisons training silently. The
    bridge clamps, but the dataset should never contain one in the first place.
    """
    arr = np.asarray(values, dtype=np.float32)
    if not np.all(np.isfinite(arr)):
        raise ValueError("series contains non-finite values")
    mean = float(arr.mean())
    std = float(arr.std())
    if std <= 1e-6:
        raise ValueError(f"series is constant (std={std:.2e}); it would z-score to NaN")
    return (arr - mean) / std, mean, std


__all__ = [
    "TIMENET_AVAILABLE",
    "artifact_bundle_sha",
    "caption_for",
    "cause_vocabulary",
    "record_id_for",
    "works_intervals",
    "z_safe",
    "VOCABULARY_ID",
]
