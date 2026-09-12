"""Fail closed: everything that must be true before a dataset is allowed to exist.

Three groups, run at three different moments, because a check is only useful
where it can still change the outcome.

**Source-level**, before a single record is built. These read the raw event
stream and answer "is the archive the shape we think it is". Running them after
the build wastes the build; running them per-record is 26 months of the same
answer.

**Record-level**, as each record is assembled. These are per-sample invariants
that a data bug expresses one record at a time -- a flat series, a truncated
window, a rationale citing a number nobody computed.

**Cross-profile**, once every profile is built. S/M/L/XM only constitute a
controlled bake-off if they differ in exactly one variable. These checks are the
only thing standing between "longer context wins" and "the XM run happened to get
an easier test split".

Every check returns findings rather than raising, so one run reports everything
wrong instead of the first thing wrong -- and then :func:`refuse_on_failure`
raises once, at the write boundary. **A validation failure never produces a
partially written dataset.** The output is ``validation_report.json`` plus a
human coverage report; both are written even when validation fails, because the
report is how you find out why.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from bridge import (
    ANN_SPLIT,
    ANSWER_SEPARATOR,
    MIN_STD,
    annotation_map,
    format_answer,
    render_target,
    series_caption,
    series_keys,
    series_values,
)
from profiles import TimelineProfile
from sources import BASIS_EXPANSION_DATE, SERVICE_DATE_SQL

# --- the annotation contract this validator holds the builder to -------------
# `entities.py`, `anchors.py` and `labels.py` own the values; this module only
# names the keys, so that a rename breaks here loudly rather than degrading a
# check into a silent no-op on a missing key.

ANN_ENTITY = ("entity_id", "entity")
"""The (service group, station) pair a record is about.

``build.py``'s ``_ANNOTATION_SPEC`` is authoritative and declares ``entity_id``;
the bare ``entity`` is accepted as an alias so this validator does not become the
reason a rename cannot happen. Tried in order, first hit wins."""

ANN_ANCHOR = ("anchor_iso", "anchor")
"""The travel date the label is computed forward from (``build.py`` declares
``anchor_iso``). ``(entity, anchor)`` is the sample's cross-profile identity: the
same pair must exist in every profile and must land in the same split in all of
them."""

ANN_SPLIT_CELL = "split_cell"
"""The grouping the split was drawn over (an entity x time-block cell). Two
profiles agreeing on ``split`` but not on ``split_cell`` means the splitter ran
twice with different inputs, and the agreement is luck."""

ANN_BUNDLE_SHA = "artifact_bundle_sha"
"""Hash of the fact cache + station universe + label definitions the build read.
Identical across profiles or the bake-off compared two different worlds."""

ANN_IMPUTED_FRACTION = "imputed_fraction"
"""Share of timesteps in this record that were filled rather than observed."""

ANN_RATIONALE_SLOTS = "rationale_slots"
"""Optional single map annotation holding every value the rationale template was
allowed to interpolate.

``labels.py`` carries the same information as ``Label.context``, a flat dict of
``ctx_``-prefixed keys enumerated in ``labels.CONTEXT_SLOTS``, and whether those
reach the record as one map or as one annotation each is ``build.py``'s call. So
:func:`collect_slots` accepts both spellings. The number check below is only as
good as whichever dict it finds is complete."""

CTX_SLOT_PREFIX = "ctx_"
"""``labels.assert_no_horizon_leak`` enforces this prefix on every context slot,
precisely so a horizon-derived number cannot be cited by a rationale. Gathering
by prefix here inherits that guarantee instead of restating it."""

try:  # labels.py is a sibling under active development; do not hard-fail on it
    from labels import CONTEXT_SLOTS
except Exception:  # pragma: no cover
    CONTEXT_SLOTS: tuple[str, ...] = ()

# --- thresholds --------------------------------------------------------------

MAX_IMPUTED_FRACTION = 0.20
"""A fifth of the window filled is the most a record may carry.

Rationale from the coverage measurements in ``facts.py``: an entity seen on 20+
days a month has occasional missing hours, not missing weeks. Past 20% the
series is mostly a description of the imputation rule, and at the daily layer
120 steps means 24 fabricated days -- longer than QUARTER's whole bucket."""

MAX_ABS_DELAY_MIN = 24 * 60
"""A stop reported more than a day late is a clock or parsing error, not a train.
Measured on 2026-08: p99.9 of ``delay_in_min`` is 156, max 1,433."""

MIN_PLANNED_ACTUAL_AGREEMENT = 0.99
"""Share of rows where ``delay_in_min`` agrees with ``actual - planned`` to the
minute. Below this the two columns disagree about which is authoritative and the
label is being computed from the wrong one."""

BASIS_STEP_RATIO = 1.25
"""Largest tolerated ratio between the mean daily observation count after
2025-11-02 and before it, per station.

piebro widens from the ~100 busiest stations to *all* stations on that date. An
aggregate over "whatever was observed" therefore steps that day, and a 120-day
series straddling it carries a manufactured regime change -- a step in every
long series, in the same place, for every entity. The model would learn the
expansion. 1.25 is loose on purpose: real traffic does move month to month, and
this check is looking for a discontinuity, not for growth."""

PHASE_MIN_ABS_CORR = 0.20
"""Below this peak correlation the phase check cannot tell lag 0 from lag +-1, so
it reports 'inconclusive' rather than a false alarm. A pair of unrelated series
peaks wherever the noise says."""

_NUMBER_RE = re.compile(r"\d")
_NUMERIC_TOKEN_RE = re.compile(r"[-+]?\d[\d.,:]*")


# --- findings ----------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    """One thing that is wrong, or one thing that could not be determined.

    ``severity`` is the whole point of the type. An ``error`` refuses the write.
    A ``warning`` is recorded and does not. Nothing else distinguishes them, so
    the decision about which a check emits is made once, in the check, where the
    evidence is.
    """

    check: str
    severity: str  # "error" | "warning"
    subject: str
    message: str
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def is_error(self) -> bool:
        return self.severity == "error"


def error(check: str, subject: str, message: str, **detail: Any) -> Finding:
    return Finding(check, "error", subject, message, detail)


def warning(check: str, subject: str, message: str, **detail: Any) -> Finding:
    return Finding(check, "warning", subject, message, detail)


@dataclass
class ValidationReport:
    """Accumulated findings plus the coverage table, and the write gate.

    Findings accumulate rather than raise so that a failing build reports every
    problem in one pass. A 26-month extraction is too expensive to debug one
    error at a time.
    """

    findings: list[Finding] = field(default_factory=list)
    coverage: list[dict[str, Any]] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    def extend(self, findings: Iterable[Finding]) -> "ValidationReport":
        self.findings.extend(findings)
        return self

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.is_error]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if not f.is_error]

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        counts: dict[str, int] = defaultdict(int)
        for finding in self.findings:
            counts[finding.check] += 1
        return {
            "ok": self.ok,
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "n_errors": len(self.errors),
            "n_warnings": len(self.warnings),
            "findings_per_check": dict(sorted(counts.items())),
            "findings": [asdict(f) for f in self.findings],
            "coverage": self.coverage,
            "stats": self.stats,
        }

    def write_json(self, path: Path) -> Path:
        """Machine-readable report. Written on success *and* on failure."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False, default=str))
        return path

    def write_coverage(self, path: Path) -> Path:
        """Human coverage report.

        A table, not a boolean, because "coverage is fine" is never actionable.
        Which station, which month, how many days short -- that is what tells you
        whether to drop the station, shorten the window, or go and re-extract.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# db_route coverage report",
            "",
            f"generated {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')}",
            f"status: {'PASS' if self.ok else 'FAIL'}  "
            f"({len(self.errors)} errors, {len(self.warnings)} warnings)",
            "",
        ]
        if self.coverage:
            lines += [
                "| station | month | days seen | days in month | observed | gap days |",
                "| --- | --- | ---: | ---: | ---: | ---: |",
            ]
            for row in sorted(
                self.coverage, key=lambda r: (-r.get("gap_days", 0), r["station"], r["month"])
            ):
                lines.append(
                    f"| {row['station']} | {row['month']} | {row['days_seen']} | "
                    f"{row['days_in_month']} | {row.get('n_obs', 0):,} | {row.get('gap_days', 0)} |"
                )
            lines.append("")
        else:
            lines += ["_no coverage rows collected_", ""]

        if self.findings:
            lines += ["## findings", ""]
            for finding in self.findings:
                mark = "ERROR" if finding.is_error else "warn "
                lines.append(f"- `{mark}` **{finding.check}** [{finding.subject}] {finding.message}")
            lines.append("")
        path.write_text("\n".join(lines))
        return path


def refuse_on_failure(report: ValidationReport, what: str = "dataset") -> None:
    """The write gate. Call it immediately before persisting anything.

    Separate from the checks so the refusal happens in exactly one place and
    cannot be forgotten halfway down a build function: everything before this
    line accumulates evidence, everything after it writes.
    """
    if report.ok:
        return
    head = "\n".join(
        f"  [{f.check}] {f.subject}: {f.message}" for f in report.errors[:10]
    )
    more = f"\n  ... and {len(report.errors) - 10} more" if len(report.errors) > 10 else ""
    raise ValidationError(
        f"refusing to write the {what}: {len(report.errors)} validation error(s)\n{head}{more}"
    )


class ValidationError(RuntimeError):
    """Raised by :func:`refuse_on_failure`. Nothing else in this module raises."""


# --- source-level checks -----------------------------------------------------
# Each takes an open DuckDB connection and the name of a relation with the
# processed-event columns. Passing the relation name rather than a URL is what
# makes these testable offline: the tests register a synthetic in-memory table
# and get the same SQL the production run gets.


def check_timestamp_monotonicity(con: Any, events: str = "events") -> list[Finding]:
    """Timestamps must strictly increase within each ``(train_line_ride_id, service_date)``.

    A run is one train's ordered walk down a line, so its stop times increase and
    never repeat. Two things break that, and they break it differently:

    * **Grouping on the calendar date.** A run departing 23:23 and arriving 00:29
      is split across two dates, and each half looks like a run with a broken
      stop sequence. ``sources.SERVICE_DATE_SQL`` shifts by three hours, which
      took clean runs from 99.5% to 100.0% over 2026-08-04..06.
    * **A genuine duplicate scrape**, where the same stop lands twice with a
      revised delay. That is a real merge bug and must not be averaged over.

    So the check runs against the *service* date. A violation here means the
    offset is wrong or the merge is duplicating, and both poison every aggregate
    built on top.
    """
    rows = con.execute(
        f"""
        WITH runs AS (
            SELECT train_line_ride_id, {SERVICE_DATE_SQL} AS service_date, time,
                   lag(time) OVER (
                       PARTITION BY train_line_ride_id, {SERVICE_DATE_SQL} ORDER BY time, stop_number
                   ) AS previous
            FROM {events}
        )
        SELECT count(*) FILTER (WHERE previous IS NOT NULL AND time <= previous) AS violations,
               count(*) AS total
        FROM runs
        """
    ).fetchone()
    violations, total = int(rows[0] or 0), int(rows[1] or 0)
    if violations:
        return [
            error(
                "timestamp_monotonicity",
                events,
                f"{violations:,} of {total:,} consecutive stop pairs are not strictly "
                f"increasing within (train_line_ride_id, service_date)",
                violations=violations,
                total=total,
                service_day_offset_hours=3,
            )
        ]
    return []


def check_duplicate_stop_ids(con: Any, events: str = "events") -> list[Finding]:
    """``id`` is the join key to the IRIS cause table, so it must be unique.

    ``causes.StopCauses.stop_id`` is documented as matching this column exactly
    (``<ride_id>-<YYMMDDHHmm>-<stop_number>``). A duplicate id does not merely
    double-count a stop: the LEFT JOIN in ``facts._agg_select`` fans out, so one
    duplicated stop inflates ``n_obs`` *and* every ``sum_delay_*`` behind it, and
    the resulting rates are silently wrong rather than obviously missing.
    """
    rows = con.execute(
        f"SELECT count(*) FROM (SELECT id FROM {events} GROUP BY id HAVING count(*) > 1)"
    ).fetchone()
    duplicates = int(rows[0] or 0)
    if duplicates:
        sample = [
            r[0]
            for r in con.execute(
                f"SELECT id FROM {events} GROUP BY id HAVING count(*) > 1 LIMIT 5"
            ).fetchall()
        ]
        return [
            error(
                "duplicate_stop_ids",
                events,
                f"{duplicates:,} stop ids occur more than once; the cause join would fan out",
                n_duplicate_ids=duplicates,
                sample=sample,
            )
        ]
    return []


def check_planned_vs_actual(con: Any, events: str = "events") -> list[Finding]:
    """``delay_in_min`` must be what the planned and actual times say it is.

    Two independent failures hide here. The columns can *disagree* -- one of them
    is stale, or the delay was recomputed against a revised plan -- in which case
    the label depends on which column the builder happened to read. And the delay
    can be *impossible*: a 3,000-minute delay is a clock skew or a date parsed in
    the wrong year, and one of those in a 168-step window dominates the mean and
    the z-score for the whole series.
    """
    findings: list[Finding] = []
    agreement, total, extreme = con.execute(
        f"""
        SELECT
          count(*) FILTER (
            WHERE planned_time IS NULL OR actual_time IS NULL
               OR abs(delay_in_min - date_diff('minute', planned_time, actual_time)) <= 1
          ) AS agree,
          count(*) AS total,
          count(*) FILTER (WHERE abs(delay_in_min) > {MAX_ABS_DELAY_MIN}) AS extreme
        FROM {events}
        """
    ).fetchone()
    agreement, total, extreme = int(agreement or 0), int(total or 0), int(extreme or 0)
    share = agreement / total if total else 1.0
    if share < MIN_PLANNED_ACTUAL_AGREEMENT:
        findings.append(
            error(
                "planned_vs_actual",
                events,
                f"only {share:.4%} of rows have delay_in_min within a minute of "
                f"actual - planned (floor {MIN_PLANNED_ACTUAL_AGREEMENT:.2%})",
                agreeing=agreement,
                total=total,
                share=share,
            )
        )
    if extreme:
        findings.append(
            error(
                "planned_vs_actual",
                events,
                f"{extreme:,} rows report |delay| over {MAX_ABS_DELAY_MIN} minutes, "
                f"which is a clock or parse error rather than a train",
                extreme=extreme,
                cap_minutes=MAX_ABS_DELAY_MIN,
            )
        )
    return findings


def coverage_table(con: Any, events: str = "events") -> list[dict[str, Any]]:
    """Days seen per station per month, as rows.

    Deliberately a table and not a pass/fail. "Coverage is complete" is a claim
    nobody can act on; "München-Pasing is missing 6 days in 2025-12" tells you
    whether to re-extract that day range, shorten the window past it, or drop the
    station from the universe. The caller decides what to do; this returns the
    evidence.
    """
    rows = con.execute(
        f"""
        SELECT station_name,
               strftime({SERVICE_DATE_SQL}, '%Y-%m')     AS month,
               count(DISTINCT {SERVICE_DATE_SQL})        AS days_seen,
               count(*)                                  AS n_obs
        FROM {events}
        GROUP BY 1, 2
        ORDER BY 1, 2
        """
    ).fetchall()
    table: list[dict[str, Any]] = []
    for station, month, days_seen, n_obs in rows:
        year, mon = (int(p) for p in str(month).split("-"))
        next_month = dt.date(year + (mon == 12), 1 if mon == 12 else mon + 1, 1)
        days_in_month = (next_month - dt.date(year, mon, 1)).days
        table.append(
            {
                "station": station,
                "month": month,
                "days_seen": int(days_seen),
                "days_in_month": days_in_month,
                "n_obs": int(n_obs),
                "gap_days": days_in_month - int(days_seen),
            }
        )
    return table


def check_no_basis_step(
    con: Any,
    events: str = "events",
    *,
    step_date: dt.date = BASIS_EXPANSION_DATE,
    window_days: int = 28,
    ratio: float = BASIS_STEP_RATIO,
) -> list[Finding]:
    """No station's observation count may step on 2025-11-02.

    **This is the check the whole pinned-universe design exists to enforce**, and
    it is the one most likely to be quietly violated by a well-meaning change.
    piebro carries the ~100 busiest stations from 2024-07 and *every* station from
    2025-11-02. An aggregate over "whatever was observed" therefore jumps that
    day -- and because ``profiles.SEASON`` looks back 120 days, a step on
    2025-11-02 appears inside every long window for four months, in the same
    place, for every entity in the dataset. That is a regime change the model can
    learn and that means nothing.

    ``facts.build_station_universe`` prevents it by keeping only stations present
    in every month. This verifies the prevention worked, per station, by comparing
    mean daily observations in the 28 days either side. A station that was absent
    before the step and present after it shows an infinite ratio and is reported
    as newly appearing, which is the same defect in its purest form.
    """
    before_start = step_date - dt.timedelta(days=window_days)
    after_end = step_date + dt.timedelta(days=window_days)
    rows = con.execute(
        f"""
        WITH daily AS (
            SELECT station_name,
                   {SERVICE_DATE_SQL} AS service_date,
                   count(*)           AS n
            FROM {events}
            WHERE {SERVICE_DATE_SQL} >= DATE '{before_start}'
              AND {SERVICE_DATE_SQL} <  DATE '{after_end}'
            GROUP BY 1, 2
        )
        SELECT station_name,
               avg(n) FILTER (WHERE service_date <  DATE '{step_date}') AS before_mean,
               avg(n) FILTER (WHERE service_date >= DATE '{step_date}') AS after_mean
        FROM daily GROUP BY 1
        """
    ).fetchall()

    findings: list[Finding] = []
    for station, before_mean, after_mean in rows:
        before_mean = float(before_mean) if before_mean is not None else 0.0
        after_mean = float(after_mean) if after_mean is not None else 0.0
        if before_mean <= 0.0 and after_mean > 0.0:
            findings.append(
                error(
                    "basis_step",
                    str(station),
                    f"appears only from {step_date}: 0 observations before, "
                    f"{after_mean:.0f}/day after. This station joined at the basis "
                    f"expansion and must not be in the pinned universe",
                    before_mean=before_mean,
                    after_mean=after_mean,
                )
            )
            continue
        if before_mean <= 0.0:
            continue
        observed = after_mean / before_mean
        if observed > ratio or observed < 1.0 / ratio:
            findings.append(
                error(
                    "basis_step",
                    str(station),
                    f"daily observation count steps {observed:.2f}x across {step_date} "
                    f"({before_mean:.0f}/day -> {after_mean:.0f}/day), past the {ratio}x "
                    f"tolerance; a 120-day window straddling it carries a manufactured "
                    f"regime change",
                    before_mean=before_mean,
                    after_mean=after_mean,
                    observed_ratio=observed,
                    tolerance=ratio,
                )
            )
    return findings


def validate_source(con: Any, events: str = "events") -> ValidationReport:
    """Every source-level check, in one pass, before anything is built."""
    report = ValidationReport()
    report.extend(check_timestamp_monotonicity(con, events))
    report.extend(check_duplicate_stop_ids(con, events))
    report.extend(check_planned_vs_actual(con, events))
    report.extend(check_no_basis_step(con, events))
    report.coverage = coverage_table(con, events)
    gaps = [row for row in report.coverage if row["gap_days"] > 0]
    report.stats["coverage"] = {
        "rows": len(report.coverage),
        "station_months_with_gaps": len(gaps),
        "worst_gap_days": max((row["gap_days"] for row in gaps), default=0),
    }
    return report


# --- record-level checks -----------------------------------------------------


def expected_series_plan(profile: TimelineProfile) -> list[tuple[str, str, int]]:
    """``(layer_id, signal, n_steps)`` in the order the builder must emit them.

    One list, derived from the frozen profile, used both to check the count and
    to check each length. Deriving it rather than restating it means adding a
    profile cannot desynchronise the validator from the builder.
    """
    return [
        (layer.layer_id, signal, layer.n_steps)
        for layer in profile.layers
        for signal in layer.signals
    ]


def check_series_shape(record: Any, profile: TimelineProfile) -> list[Finding]:
    """Series count, per-series length, finiteness, and the std floor.

    The std floor is the important one and the least obvious.
    ``bridge.normalize`` clamps std at 1e-6 so the division cannot produce NaN --
    but the clamp is a *safety net, not an acceptance*. A constant series divided
    by 1e-6 becomes exactly zero everywhere, which trains perfectly happily and
    teaches the model that this channel carries no information, for this record
    only. Nothing downstream errors. It is the likeliest quiet failure in the
    whole pipeline, and this is the only place it is caught.

    Length is checked exactly rather than as a minimum: the collate right-pads
    with zeros and carries **no padding mask**, so a short series is
    indistinguishable from a series that went to zero.
    """
    findings: list[Finding] = []
    subject = str(getattr(record, "record_id", "?"))
    plan = expected_series_plan(profile)
    series = list(record.time_series)

    if len(series) != len(plan):
        findings.append(
            error(
                "series_count",
                subject,
                f"profile {profile.profile_id} expects {len(plan)} series "
                f"({profile.n_series} = sum of per-layer signal counts), record has {len(series)}",
                expected=len(plan),
                found=len(series),
                expected_plan=[f"{layer}/{signal}" for layer, signal, _ in plan],
                found_keys=[series_keys(s)[0] for s in series],
            )
        )

    annotations = annotation_map(record)
    for index, one in enumerate(series):
        key = series_keys(one)[0]
        try:
            values = series_values(one)
        except Exception as exc:  # a 2-D or null-bearing series
            findings.append(error("series_values", subject, f"series {key}: {exc}", index=index))
            continue

        if index < len(plan):
            layer_id, signal, n_steps = plan[index]
            if values.size != n_steps:
                findings.append(
                    error(
                        "series_length",
                        subject,
                        f"series {index} ({layer_id}/{signal}) has {values.size} steps, "
                        f"expected exactly {n_steps}; the collate zero-pads with no mask, "
                        f"so a short series reads as data that went to zero",
                        index=index,
                        expected=n_steps,
                        found=int(values.size),
                    )
                )

        if not np.all(np.isfinite(values)):
            n_bad = int((~np.isfinite(values)).sum())
            findings.append(
                error(
                    "series_finite",
                    subject,
                    f"series {index} ({key}) has {n_bad} non-finite values",
                    index=index,
                    n_non_finite=n_bad,
                )
            )
            continue

        std = float(values.std(ddof=1)) if values.size > 1 else 0.0
        if std <= MIN_STD:
            findings.append(
                error(
                    "series_constant",
                    subject,
                    f"series {index} ({key}) has std {std:.3e} <= {MIN_STD:.0e}: it is "
                    f"constant, so z-scoring divides by the clamp and yields all zeros. "
                    f"Nothing downstream errors; the channel just silently carries nothing",
                    index=index,
                    std=std,
                    floor=MIN_STD,
                    caption=series_caption(one, annotations),
                )
            )
    return findings


def check_imputed_fraction(
    record: Any, *, cap: float = MAX_IMPUTED_FRACTION
) -> list[Finding]:
    """The record's filled-timestep share must be under the cap.

    Missing is required to be *stated*: a record with no ``imputed_fraction``
    annotation is an error, not a zero. An unstated imputation is exactly how a
    zero-filled gap gets treated as a quiet hour.
    """
    subject = str(getattr(record, "record_id", "?"))
    value = annotation_map(record).get(ANN_IMPUTED_FRACTION)
    if value is None:
        return [
            error(
                "imputed_fraction",
                subject,
                f"no {ANN_IMPUTED_FRACTION!r} annotation; an unstated imputation is "
                f"indistinguishable from a genuinely quiet hour",
            )
        ]
    fraction = float(value)
    if not 0.0 <= fraction <= 1.0:
        return [
            error("imputed_fraction", subject, f"{fraction} is not a fraction", value=fraction)
        ]
    if fraction > cap:
        return [
            error(
                "imputed_fraction",
                subject,
                f"{fraction:.1%} of timesteps imputed, over the {cap:.0%} cap; past this "
                f"the series mostly describes the imputation rule",
                value=fraction,
                cap=cap,
            )
        ]
    return []


def check_answer_matches_target(record: Any, task: Any, *, eos_token: str = "") -> list[Finding]:
    """The text after ``" Answer: "`` must equal the task target, exactly.

    Scoring splits the generated string on that literal and compares what follows
    against the target. If the built answer's own suffix does not already match
    the target byte for byte, the model is trained toward one string and graded
    against another, and every metric is wrong by a constant nobody notices.
    Also refuses more than one occurrence: a rationale that happens to contain
    "Answer: " makes the split ambiguous.
    """
    subject = str(getattr(record, "record_id", "?"))
    try:
        target = render_target(task.target)
    except ValueError as exc:
        return [error("answer_target", subject, str(exc))]

    answer = format_answer(getattr(task, "rationale", None), task.target, eos_token)
    occurrences = answer.count(ANSWER_SEPARATOR)
    if occurrences != 1:
        return [
            error(
                "answer_target",
                subject,
                f"the answer contains {ANSWER_SEPARATOR!r} {occurrences} times; scoring "
                f"splits on it and cannot tell which occurrence is the answer",
                occurrences=occurrences,
            )
        ]
    emitted = answer.split(ANSWER_SEPARATOR, 1)[1]
    if eos_token and emitted.endswith(eos_token):
        emitted = emitted[: -len(eos_token)]
    if emitted != target:
        return [
            error(
                "answer_target",
                subject,
                f"answer line ends with {emitted!r} but the task target is {target!r}",
                emitted=emitted,
                target=target,
            )
        ]
    return []


def _renderings(value: Any) -> set[str]:
    """Every plausible string spelling of one slot value.

    A slot holds ``4.7`` and the template may have written ``4.7``, ``4.70`` or
    ``5``. Enumerating the spellings here rather than parsing the rationale keeps
    the check a *containment* test, which is the strict direction: a number in
    the rationale that no slot can spell is a fabrication.
    """
    out: set[str] = {str(value)}
    if isinstance(value, bool):
        return out
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        number = float(value)
        out |= {f"{number:.0f}", f"{number:.1f}", f"{number:.2f}", f"{number:,.0f}"}
        if number.is_integer():
            out.add(str(int(number)))
        if abs(number) < 1.0:
            out.add(f"{number * 100:.0f}")
            out.add(f"{number * 100:.1f}")
    return {spelling for spelling in out if spelling}


def first_annotation(annotations: Mapping[str, Any], keys: Sequence[str]) -> Any:
    """The first of several accepted spellings that the record actually carries."""
    for key in keys:
        if key in annotations:
            return annotations[key]
    return None


def collect_slots(record: Any) -> tuple[Mapping[str, Any] | None, list[Finding]]:
    """The values a rationale is allowed to cite, however the builder carried them.

    Two shapes are accepted, because ``build.py`` has not yet committed to one:
    a single ``rationale_slots`` map, or one flat ``ctx_*`` annotation per slot as
    ``labels.Label.context`` names them. A ``ctx_`` key that ``labels.CONTEXT_SLOTS``
    does not declare is itself reported -- an undeclared slot is how a
    horizon-derived number gets laundered into a rationale, which is the exact
    leak ``labels.assert_no_horizon_leak`` exists to stop.
    """
    subject = str(getattr(record, "record_id", "?"))
    annotations = annotation_map(record)
    explicit = annotations.get(ANN_RATIONALE_SLOTS)
    if isinstance(explicit, Mapping):
        return explicit, []
    if explicit is not None:
        return None, [
            error("rationale_numbers", subject, f"{ANN_RATIONALE_SLOTS!r} is not a map")
        ]

    gathered = {k: v for k, v in annotations.items() if k.startswith(CTX_SLOT_PREFIX)}
    if not gathered:
        return None, []
    findings: list[Finding] = []
    if CONTEXT_SLOTS:
        undeclared = sorted(set(gathered) - set(CONTEXT_SLOTS))
        if undeclared:
            findings.append(
                error(
                    "rationale_numbers",
                    subject,
                    f"context slot(s) {undeclared} are not in labels.CONTEXT_SLOTS; an "
                    f"undeclared slot is how a horizon-derived number reaches a rationale",
                    undeclared=undeclared,
                )
            )
    return gathered, findings


def check_rationale_numbers(
    record: Any, task: Any, slots: Mapping[str, Any] | None = None
) -> list[Finding]:
    """Every number in the rationale must come from the slot dict.

    The rationale is the supervision signal, so a number in it that nothing
    computed is a hallucination we are *training on*. The check is subtractive:
    strip every spelling of every slot value out of the rationale, and any digit
    left standing was invented. That direction catches the interesting cases a
    forward parse misses -- a transposed "17" where the slot said "71", a
    percentage the template multiplied twice, a date the writer typed by hand.

    Longest spellings are removed first, so "12" inside "120" cannot mask the
    remainder.
    """
    subject = str(getattr(record, "record_id", "?"))
    rationale = getattr(task, "rationale", None)
    if not rationale:
        return []
    prefix: list[Finding] = []
    if slots is None:
        slots, prefix = collect_slots(record)
    if slots is None:
        return prefix + [
            error(
                "rationale_numbers",
                subject,
                f"rationale carries numbers but the record has neither a "
                f"{ANN_RATIONALE_SLOTS!r} map nor any {CTX_SLOT_PREFIX}* slot to check "
                f"them against",
            )
        ]

    spellings = {s for value in slots.values() for s in _renderings(value)}
    residue = rationale
    for spelling in sorted(spellings, key=len, reverse=True):
        if _NUMBER_RE.search(spelling):
            residue = residue.replace(spelling, "•")
    leftovers = sorted({m.group(0).strip(".,:") for m in _NUMERIC_TOKEN_RE.finditer(residue)})
    leftovers = [token for token in leftovers if token]
    if leftovers:
        return prefix + [
            error(
                "rationale_numbers",
                subject,
                f"rationale contains number(s) {leftovers} that no slot value spells; "
                f"a number we did not compute is one we are training the model to invent",
                leftovers=leftovers,
                slots=dict(slots),
            )
        ]
    return prefix


def cross_correlation(a: np.ndarray, b: np.ndarray, lag: int) -> float:
    """Pearson correlation of ``a`` against ``b`` shifted by ``lag`` steps.

    Both are z-scored on the overlap so the value is comparable across lags. A
    constant overlap yields 0.0 rather than NaN, which keeps the argmax defined.
    """
    if lag > 0:
        left, right = a[lag:], b[:-lag]
    elif lag < 0:
        left, right = a[:lag], b[-lag:]
    else:
        left, right = a, b
    if left.size < 2:
        return 0.0
    left = left - left.mean()
    right = right - right.mean()
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denominator < 1e-12:
        return 0.0
    return float(np.dot(left, right) / denominator)


def check_phase_alignment(
    record: Any,
    profile: TimelineProfile,
    *,
    pair: tuple[str, str] = ("station_delay", "service_delay"),
    min_abs_corr: float = PHASE_MIN_ABS_CORR,
) -> list[Finding]:
    """Two series that share a cycle must cross-correlate with a peak at lag 0.

    **This catches the one bug that is otherwise invisible and completely fatal:
    a timezone desynchronisation between the station aggregate and the line
    aggregate.** ``causes._parse_iris_time`` stamps IRIS times as Europe/Berlin;
    the processed parquet's ``time`` column is its own thing. If one side is
    bucketed in UTC and the other in local time, both series still look perfectly
    reasonable -- right shape, right magnitude, right daily rush-hour cycle, no
    NaN, no gap, every other check in this file passes -- and they are simply an
    hour apart. The model then learns to predict this morning's congestion from
    last night's, and no amount of staring at a plot of either series alone
    reveals it. Only their relative phase does.

    Both series carry the same daily commuter cycle, so their correlation must
    peak when they are aligned. A peak at lag +-1 is the offset. The DST
    transitions make it seasonal, so it can also appear in half the year only.

    When the peak correlation is under ``min_abs_corr`` the two series simply do
    not share enough structure for the argmax to mean anything, and the check
    reports *inconclusive* as a warning rather than inventing an error.
    """
    subject = str(getattr(record, "record_id", "?"))
    finest = min(profile.layers, key=lambda layer: layer.bucket_seconds)
    plan = expected_series_plan(profile)
    series = list(record.time_series)
    if len(series) != len(plan):
        return []  # the count check already reported this; indices are unreliable

    wanted = {
        signal: index
        for index, (layer_id, signal, _) in enumerate(plan)
        if layer_id == finest.layer_id and signal in pair
    }
    if len(wanted) != 2:
        return [
            warning(
                "phase_alignment",
                subject,
                f"layer {finest.layer_id!r} does not carry both of {pair}, so the phase "
                f"check has no pair to compare",
                available=[s for lid, s, _ in plan if lid == finest.layer_id],
            )
        ]

    try:
        left = series_values(series[wanted[pair[0]]])
        right = series_values(series[wanted[pair[1]]])
    except Exception as exc:
        return [error("phase_alignment", subject, str(exc))]
    if not (np.all(np.isfinite(left)) and np.all(np.isfinite(right))):
        return []  # series_finite already reported it

    correlations = {lag: cross_correlation(left, right, lag) for lag in (-1, 0, 1)}
    peak_lag = max(correlations, key=lambda lag: abs(correlations[lag]))
    peak = abs(correlations[peak_lag])

    if peak < min_abs_corr:
        return [
            warning(
                "phase_alignment",
                subject,
                f"inconclusive: peak |corr| {peak:.3f} < {min_abs_corr} across lags "
                f"-1/0/+1, so the argmax carries no information about alignment",
                correlations=correlations,
            )
        ]
    if peak_lag != 0:
        return [
            error(
                "phase_alignment",
                subject,
                f"{pair[0]} and {pair[1]} at layer {finest.layer_id!r} peak at lag "
                f"{peak_lag:+d} ({correlations[peak_lag]:+.3f}) rather than lag 0 "
                f"({correlations[0]:+.3f}): one bucket of "
                f"{finest.bucket} desynchronisation between the station and line "
                f"aggregates, which every other check in this file passes cleanly",
                correlations=correlations,
                peak_lag=peak_lag,
                bucket=finest.bucket,
            )
        ]
    return []


def validate_record(
    record: Any,
    task: Any,
    profile: TimelineProfile,
    *,
    eos_token: str = "",
    slots: Mapping[str, Any] | None = None,
) -> list[Finding]:
    """Every record-level check for one built sample."""
    findings: list[Finding] = []
    findings += check_series_shape(record, profile)
    findings += check_imputed_fraction(record)
    findings += check_answer_matches_target(record, task, eos_token=eos_token)
    findings += check_rationale_numbers(record, task, slots)
    findings += check_phase_alignment(record, profile)
    return findings


def validate_records(
    dataset: Any, profile: TimelineProfile, *, eos_token: str = ""
) -> ValidationReport:
    """Record-level validation over a whole built ``TimeFDataset``."""
    report = ValidationReport()
    n_records = n_samples = 0
    for record in dataset.records:
        n_records += 1
        tasks = dataset.tasks_for(record)
        if not tasks:
            report.extend(
                [
                    error(
                        "record_has_task",
                        str(record.record_id),
                        "record carries no task, so it can never become a training sample",
                    )
                ]
            )
            continue
        for task in tasks:
            n_samples += 1
            report.extend(validate_record(record, task, profile, eos_token=eos_token))
    report.stats[profile.profile_id] = {
        "records": n_records,
        "samples": n_samples,
        "series_per_record": profile.n_series,
        "patches_per_sample": profile.n_patches,
        "context_days": profile.context_days,
    }
    return report


# --- cross-profile checks ----------------------------------------------------


def check_bundle_sha(datasets: Mapping[str, Any]) -> list[Finding]:
    """Every profile must have been built from the same artifact bundle.

    S/M/L/XM is a controlled comparison of one variable: how much history the
    sample sees. If one profile read a fact cache rebuilt an hour later -- one
    more day extracted, one station added to the universe, one cause code
    reclassified -- then it is not the context length that differs, and the
    bake-off result is unattributable. The sha is the cheapest possible proof
    that all four saw the same world.
    """
    by_sha: dict[str, list[str]] = defaultdict(list)
    findings: list[Finding] = []
    for profile_id, dataset in datasets.items():
        shas = {
            annotation_map(record).get(ANN_BUNDLE_SHA) for record in dataset.records
        }
        shas.discard(None)
        if not shas:
            findings.append(
                error(
                    "bundle_sha",
                    profile_id,
                    f"no record carries an {ANN_BUNDLE_SHA!r} annotation, so there is no "
                    f"evidence the profiles were built from the same inputs",
                )
            )
            continue
        if len(shas) > 1:
            findings.append(
                error(
                    "bundle_sha",
                    profile_id,
                    f"records within this profile carry {len(shas)} different bundle shas",
                    shas=sorted(str(s) for s in shas),
                )
            )
            continue
        by_sha[str(next(iter(shas)))].append(profile_id)

    if len(by_sha) > 1:
        findings.append(
            error(
                "bundle_sha",
                "cross-profile",
                f"profiles were built from {len(by_sha)} different artifact bundles, so "
                f"the bake-off compares more than context length",
                bundles={sha: sorted(ids) for sha, ids in by_sha.items()},
            )
        )
    return findings


def check_split_consistency(datasets: Mapping[str, Any]) -> list[Finding]:
    """The same ``(entity, anchor)`` must land in the same split in every profile.

    A sample that is train in S and test in XM leaks: XM's held-out score is
    partly measured on rows S trained on, and vice versa. It is also the easiest
    thing in the world to do by accident -- re-seed the splitter, or let it hash
    a set whose iteration order moved, and the assignment shifts for a few
    percent of pairs. Comparison is byte-identical on both ``split`` and
    ``split_cell``: agreeing on the split while disagreeing on the cell it was
    drawn from means the two splitters agreed by coincidence, and the next
    profile will not be so lucky.
    """
    seen: dict[tuple[str, str], tuple[str, tuple[str, str]]] = {}
    findings: list[Finding] = []
    for profile_id, dataset in datasets.items():
        for record in dataset.records:
            annotations = annotation_map(record)
            entity = first_annotation(annotations, ANN_ENTITY)
            anchor = first_annotation(annotations, ANN_ANCHOR)
            if entity is None or anchor is None:
                findings.append(
                    error(
                        "split_consistency",
                        f"{profile_id}:{record.record_id}",
                        f"record lacks {ANN_ENTITY[0]!r}/{ANN_ANCHOR[0]!r}, so its split cannot "
                        f"be matched against the other profiles",
                    )
                )
                continue
            key = (str(entity), str(anchor))
            value = (str(annotations.get(ANN_SPLIT)), str(annotations.get(ANN_SPLIT_CELL)))
            if key in seen:
                other_profile, other_value = seen[key]
                if other_value != value:
                    findings.append(
                        error(
                            "split_consistency",
                            f"{entity} @ {anchor}",
                            f"assigned (split={value[0]}, cell={value[1]}) in "
                            f"{profile_id} but (split={other_value[0]}, "
                            f"cell={other_value[1]}) in {other_profile}; the held-out "
                            f"sets overlap and neither profile's score is clean",
                            profiles=[other_profile, profile_id],
                            values=[list(other_value), list(value)],
                        )
                    )
            else:
                seen[key] = (profile_id, value)
    return findings


def validate_cross_profile(datasets: Mapping[str, Any]) -> ValidationReport:
    """Every cross-profile check, once all profiles are built."""
    report = ValidationReport()
    report.extend(check_bundle_sha(datasets))
    report.extend(check_split_consistency(datasets))
    report.stats["profiles"] = {
        profile_id: len(dataset.records) for profile_id, dataset in datasets.items()
    }
    return report


# --- reporting ---------------------------------------------------------------


def merge(*reports: ValidationReport) -> ValidationReport:
    """One report from many, so a build emits a single artifact."""
    merged = ValidationReport()
    for report in reports:
        merged.findings.extend(report.findings)
        merged.coverage.extend(report.coverage)
        merged.stats.update(report.stats)
    return merged


def write_reports(
    report: ValidationReport, out_dir: Path
) -> tuple[Path, Path]:
    """Write ``validation_report.json`` and ``coverage.md``. Always both."""
    return (
        report.write_json(out_dir / "validation_report.json"),
        report.write_coverage(out_dir / "coverage.md"),
    )


def summarize(report: ValidationReport) -> str:
    lines = [
        f"validation: {'PASS' if report.ok else 'FAIL'}  "
        f"{len(report.errors)} error(s), {len(report.warnings)} warning(s)"
    ]
    counts: dict[str, int] = defaultdict(int)
    for finding in report.errors:
        counts[finding.check] += 1
    for check, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"  {count:>6,}  {check}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate db_route sources and built profiles. Refuses to pass on any error."
    )
    parser.add_argument(
        "stage", choices=("source", "records", "cross"), help="which group to run"
    )
    parser.add_argument("--months", default="", help="YYYY-MM,YYYY-MM for the source stage")
    parser.add_argument("--profile", default="XM", help="profile id for the records stage")
    parser.add_argument("--registry", default=None)
    parser.add_argument("--out", default="data/validation", type=Path)
    args = parser.parse_args(argv)

    if args.stage == "source":
        from sources import connect, month_url, months_between

        if not args.months:
            parser.error("--months is required for the source stage")
        urls = [month_url(m) for m in months_between(*args.months.split(","))]
        con = connect()
        con.execute(
            "CREATE VIEW events AS SELECT * FROM read_parquet(?)", [urls]
        )
        report = validate_source(con, "events")
    else:
        from bridge import HAVE_TIMENET, TimeNet
        from profiles import PROFILES, profile as get_profile

        if not HAVE_TIMENET:
            print("timenet is not importable", file=sys.stderr)
            return 2
        client = TimeNet(args.registry)
        if args.stage == "records":
            prof = get_profile(args.profile)
            report = validate_records(client.load(prof.dataset_id), prof)
        else:
            report = validate_cross_profile(
                {pid: client.load(p.dataset_id) for pid, p in PROFILES.items()}
            )

    json_path, coverage_path = write_reports(report, args.out)
    print(summarize(report))
    print(f"  -> {json_path}\n  -> {coverage_path}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
