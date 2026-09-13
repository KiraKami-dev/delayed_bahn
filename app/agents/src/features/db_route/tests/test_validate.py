"""The validator is only evidence if it can be seen to reject.

Every check here is tested twice: once that the clean fixture passes it, and once
that a specific, realistic corruption trips it. A suite that only ever shows
green proves the checks run, not that they discriminate -- so each failing case
below is a bug that has a plausible way of reaching production.
"""

from __future__ import annotations

import datetime as dt
import json

import numpy as np
import pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bridge_fixtures import (  # noqa: E402
    N_STEPS,
    add_sample,
    daily_cycle,
    event_row,
    events_connection,
    make_dataset,
    series,
)

import validate  # noqa: E402
from validate import (  # noqa: E402
    ValidationError,
    check_bundle_sha,
    check_duplicate_stop_ids,
    check_imputed_fraction,
    check_no_basis_step,
    check_phase_alignment,
    check_phase_consensus,
    PHASE_CONSENSUS_MIN_RECORDS,
    check_planned_vs_actual,
    check_rationale_numbers,
    check_series_shape,
    check_split_consistency,
    check_timestamp_monotonicity,
    coverage_table,
    refuse_on_failure,
    validate_cross_profile,
    validate_record,
    validate_records,
    validate_source,
    write_reports,
)

BASE = dt.datetime(2026, 6, 1, 6, 0)


def errors(findings):
    return [f for f in findings if f.is_error]


def checks(findings):
    return {f.check for f in findings if f.is_error}


# --- the happy path ----------------------------------------------------------


def test_a_clean_dataset_passes_every_record_level_check(dataset, profile):
    report = validate_records(dataset, profile)
    assert report.ok, [f.message for f in report.errors]
    assert report.stats["TINY"]["samples"] == 3


def test_a_clean_source_passes_every_source_level_check():
    rows = []
    for day in range(3):
        for ride in ("r1", "r2"):
            for stop in range(4):
                rows.append(
                    event_row(
                        f"{ride}-{day}",
                        stop,
                        BASE + dt.timedelta(days=day, minutes=17 * stop),
                    )
                )
    report = validate_source(events_connection(rows))
    assert report.ok, [f.message for f in report.errors]
    assert report.coverage and report.coverage[0]["station"] == "Muenchen Ost"


# --- record-level rejections -------------------------------------------------


def test_rejects_a_constant_series(profile):
    """The likeliest quiet failure: z-scoring a flat channel yields all zeros and
    nothing downstream errors."""
    ds = make_dataset()
    record, _ = add_sample(ds, "flat", station_values=np.full(N_STEPS, 4.2))
    findings = check_series_shape(record, profile)
    assert "series_constant" in checks(findings)
    assert "std" in errors(findings)[0].message

    report = validate_records(ds, profile)
    assert not report.ok
    with pytest.raises(ValidationError, match="refusing to write"):
        refuse_on_failure(report)


def test_rejects_a_length_mismatch(profile):
    """A short series is indistinguishable from data that went to zero, because the
    collate pads with zeros and carries no mask."""
    ds = make_dataset()
    record, _ = add_sample(ds, "short", station_values=daily_cycle(N_STEPS - 4))
    findings = check_series_shape(record, profile)
    assert "series_length" in checks(findings)
    assert f"expected exactly {N_STEPS}" in errors(findings)[0].message


def test_rejects_a_wrong_series_count(profile):
    ds = make_dataset()
    record, _ = add_sample(ds, "extra")
    record.time_series = (*record.time_series, series(daily_cycle(), "works_share"))
    assert "series_count" in checks(check_series_shape(record, profile))


def test_rejects_non_finite_values(profile):
    values = daily_cycle()
    values[3] = np.nan
    ds = make_dataset()
    record, _ = add_sample(ds, "nan", station_values=values)
    assert "series_finite" in checks(check_series_shape(record, profile))


def test_rejects_a_phase_shifted_pair(profile):
    """A station/line timezone desynchronisation: every other check passes cleanly."""
    ds = make_dataset()
    aligned, _ = add_sample(ds, "aligned")
    assert check_phase_alignment(aligned, profile) == []

    shifted, _ = add_sample(
        ds,
        "shifted",
        station_values=daily_cycle(shift=1),
        service_values=daily_cycle(shift=-1, level=6.0, amp=2.5),
    )
    findings = check_phase_alignment(shifted, profile)
    assert [f.check for f in findings] == ["phase_alignment"]
    assert findings[0].detail["peak_lag"] != 0
    # One record off-phase is a warning: a station and its network-wide service
    # genuinely lead or lag each other. The bug signature is the whole corpus
    # leaning one way, and that is the error.
    assert findings[0].severity == "warning"
    assert check_phase_consensus(findings) == []
    consensus = check_phase_consensus(findings * PHASE_CONSENSUS_MIN_RECORDS)
    assert [f.check for f in consensus] == ["phase_consensus"]
    assert consensus[0].is_error
    # ...and it is invisible to every other check.
    assert check_series_shape(shifted, profile) == []
    assert check_imputed_fraction(shifted) == []


def test_a_pair_with_no_shared_structure_is_inconclusive_not_a_false_alarm(profile):
    rng = np.random.default_rng(0)
    ds = make_dataset()
    record, _ = add_sample(
        ds,
        "noise",
        station_values=rng.normal(size=N_STEPS),
        service_values=rng.normal(size=N_STEPS),
    )
    findings = check_phase_alignment(record, profile)
    assert findings and not findings[0].is_error
    assert "inconclusive" in findings[0].message


def test_rejects_a_tampered_rationale_number(profile):
    """A number in the supervision signal that nothing computed is one we are
    training the model to invent."""
    ds = make_dataset()
    clean, clean_task = add_sample(ds, "clean")
    assert check_rationale_numbers(clean, clean_task) == []

    tampered, task = add_sample(
        ds,
        "tampered",
        rationale="The mean delay over the window is 4.0 minutes and works are active on 9 days.",
    )
    findings = check_rationale_numbers(tampered, task)
    assert "rationale_numbers" in checks(findings)
    assert findings[0].detail["leftovers"] == ["9"]


def test_slot_values_may_be_spelled_several_ways(profile):
    ds = make_dataset()
    record, task = add_sample(
        ds,
        "spelled",
        rationale="Attribution ran at 35% over 4.70 minutes across 120 buckets.",
        slots={"attributed": 0.35, "mean_delay": 4.7, "n_steps": 120},
    )
    assert check_rationale_numbers(record, task) == []


def test_a_rationale_with_no_slot_map_is_refused():
    ds = make_dataset()
    record, task = add_sample(ds, "noslots")
    record.annotations = tuple(a for a in record.annotations if a.key != "rationale_slots")
    findings = check_rationale_numbers(record, task)
    assert "rationale_numbers" in checks(findings)
    assert "neither a 'rationale_slots' map nor any ctx_* slot" in findings[0].message


def test_rejects_an_answer_line_that_does_not_match_the_target(profile):
    ds = make_dataset()
    record, task = add_sample(ds, "mismatch", target="minor")
    assert validate.check_answer_matches_target(record, task) == []

    task.rationale = "Delay is stable. Answer: on_time because I say so."
    findings = validate.check_answer_matches_target(record, task)
    assert "answer_target" in checks(findings)
    assert "2 times" in findings[0].message


def test_rejects_an_imputed_fraction_over_the_cap():
    ds = make_dataset()
    record, _ = add_sample(ds, "gappy", imputed_fraction=0.6)
    findings = check_imputed_fraction(record)
    assert "imputed_fraction" in checks(findings)
    assert "sanity cap" in findings[0].message


def test_a_quarter_of_the_context_overnight_is_not_a_gap():
    """The overall share is descriptive; a small station's week is ~25% overnight."""
    ds = make_dataset()
    record, _ = add_sample(ds, "small-station", imputed_fraction=0.3)
    assert check_imputed_fraction(record) == []


def test_reapplies_the_per_grain_budget_from_the_record():
    from timenet.types import Annotation

    ds = make_dataset()
    record, _ = add_sample(ds, "over-budget", imputed_fraction=0.1)
    record.annotations = (
        *record.annotations,
        Annotation(key="imputed_station", value=0.3, id="over-budget-imputed_station"),
    )
    findings = check_imputed_fraction(record)
    assert [f.detail.get("grain") for f in findings] == ["station"]
    assert findings[0].is_error


def test_an_unstated_imputation_is_an_error_not_a_zero():
    ds = make_dataset()
    record, _ = add_sample(ds, "silent")
    record.annotations = tuple(a for a in record.annotations if a.key != "imputed_fraction")
    assert "imputed_fraction" in checks(check_imputed_fraction(record))


def test_validate_record_runs_every_group_at_once(profile):
    ds = make_dataset()
    record, task = add_sample(
        ds,
        "broken",
        station_values=np.full(N_STEPS, 1.0),
        imputed_fraction=0.9,
        rationale="Delay was 77 minutes.",
    )
    assert checks(validate_record(record, task, profile)) >= {
        "series_constant",
        "imputed_fraction",
        "rationale_numbers",
    }


# --- cross-profile rejections ------------------------------------------------


def _profile_dataset(profile_id, *, split="train", cell="cell-0", sha="sha-aaa"):
    ds = make_dataset(f"test/{profile_id}")
    add_sample(ds, f"{profile_id}-0", split=split, split_cell=cell, bundle_sha=sha)
    return ds


def test_matching_profiles_pass():
    report = validate_cross_profile(
        {"S": _profile_dataset("S"), "XM": _profile_dataset("XM")}
    )
    assert report.ok, [f.message for f in report.errors]


def test_rejects_a_split_collision_between_profiles():
    """The same (entity, anchor) train in one profile and test in another: XM's
    held-out score would be partly measured on rows S trained on."""
    findings = check_split_consistency(
        {"S": _profile_dataset("S", split="train"), "XM": _profile_dataset("XM", split="test")}
    )
    assert "split_consistency" in checks(findings)
    assert "held-out sets overlap" in findings[0].message


def test_rejects_agreement_on_split_but_not_on_split_cell():
    findings = check_split_consistency(
        {
            "S": _profile_dataset("S", cell="cell-0"),
            "XM": _profile_dataset("XM", cell="cell-9"),
        }
    )
    assert "split_consistency" in checks(findings)


def test_rejects_profiles_built_from_different_artifact_bundles():
    findings = check_bundle_sha(
        {"S": _profile_dataset("S", sha="sha-aaa"), "XM": _profile_dataset("XM", sha="sha-bbb")}
    )
    assert "bundle_sha" in checks(findings)
    assert "more than context length" in findings[-1].message


def test_a_missing_bundle_sha_is_an_error_not_a_pass():
    ds = _profile_dataset("S")
    for record in ds.records:
        record.annotations = tuple(
            a for a in record.annotations if a.key != "artifact_bundle_sha"
        )
    assert "bundle_sha" in checks(check_bundle_sha({"S": ds}))


# --- source-level rejections -------------------------------------------------


def test_rejects_non_monotonic_timestamps_within_a_run():
    rows = [
        event_row("r1", 0, BASE),
        event_row("r1", 1, BASE + dt.timedelta(minutes=20)),
        event_row("r1", 2, BASE + dt.timedelta(minutes=20)),  # repeated stop time
    ]
    findings = check_timestamp_monotonicity(events_connection(rows))
    assert "timestamp_monotonicity" in checks(findings)


def test_a_run_crossing_midnight_is_one_run_not_two():
    """The service-day offset is what makes this pass; the calendar date would
    split the run and leave both halves looking broken."""
    start = dt.datetime(2026, 6, 1, 23, 23)
    rows = [
        event_row("night", stop, start + dt.timedelta(minutes=22 * stop)) for stop in range(4)
    ]
    con = events_connection(rows)
    assert check_timestamp_monotonicity(con) == []
    assert con.execute(
        "SELECT count(DISTINCT CAST(time - INTERVAL 3 HOUR AS DATE)) FROM events"
    ).fetchone()[0] == 1


def test_rejects_duplicate_stop_ids():
    rows = [
        event_row("r1", 0, BASE, stop_id="dup"),
        event_row("r1", 1, BASE + dt.timedelta(minutes=10), stop_id="dup"),
    ]
    findings = check_duplicate_stop_ids(events_connection(rows))
    assert "duplicate_stop_ids" in checks(findings)
    assert findings[0].detail["sample"] == ["dup"]


def test_rejects_a_delay_that_contradicts_planned_minus_actual():
    rows = [
        event_row("r1", stop, BASE + dt.timedelta(minutes=10 * stop)) for stop in range(9)
    ]
    rows.append(
        event_row(
            "r1",
            9,
            BASE + dt.timedelta(minutes=90),
            planned=BASE,
            actual=BASE + dt.timedelta(minutes=5),
            delay=40,  # says 40, the columns say 5
        )
    )
    assert "planned_vs_actual" in checks(check_planned_vs_actual(events_connection(rows)))


def test_rejects_an_impossible_delay():
    rows = [event_row("r1", 0, BASE, delay=3000)]
    findings = check_planned_vs_actual(events_connection(rows))
    assert any("clock or parse error" in f.message for f in errors(findings))


def test_rejects_an_observation_count_step_at_the_basis_expansion():
    """piebro widens from ~100 stations to all stations on 2025-11-02. An aggregate
    over whatever was observed would carry that step into every long series."""
    step = validate.BASIS_EXPANSION_DATE
    rows = []
    for offset in range(-20, 20):
        day = dt.datetime.combine(step + dt.timedelta(days=offset), dt.time(9, 0))
        # Steady station: same traffic either side. Stepping station: 4x after.
        for stop in range(2):
            rows.append(event_row(f"s{offset}", stop, day, station="Steady"))
        for stop in range(2 if offset < 0 else 8):
            rows.append(event_row(f"x{offset}", stop, day, station="Stepping"))

    findings = check_no_basis_step(events_connection(rows))
    assert "basis_step" in checks(findings)
    flagged = {f.subject for f in errors(findings)}
    assert flagged == {"Stepping"}
    assert "manufactured regime change" in errors(findings)[0].message


def test_reports_a_station_that_only_appears_after_the_expansion():
    step = validate.BASIS_EXPANSION_DATE
    rows = []
    for offset in range(-20, 20):
        day = dt.datetime.combine(step + dt.timedelta(days=offset), dt.time(9, 0))
        rows.append(event_row(f"s{offset}", 0, day, station="Steady"))
        if offset >= 0:
            rows.append(event_row(f"n{offset}", 0, day, station="Newcomer"))
    findings = check_no_basis_step(events_connection(rows))
    assert {f.subject for f in errors(findings)} == {"Newcomer"}
    assert "joined at the basis expansion" in errors(findings)[0].message


def test_coverage_is_a_table_not_a_boolean():
    rows = [
        event_row("r", 0, dt.datetime(2026, 6, day, 9, 0), station="Muenchen Ost")
        for day in (1, 2, 3)
    ]
    table = coverage_table(events_connection(rows))
    assert table == [
        {
            "station": "Muenchen Ost",
            "month": "2026-06",
            "days_seen": 3,
            "days_in_month": 30,
            "n_obs": 3,
            "gap_days": 27,
        }
    ]


# --- reporting and the write gate --------------------------------------------


def test_reports_are_written_on_failure_too(tmp_path, profile):
    ds = make_dataset()
    add_sample(ds, "flat", station_values=np.full(N_STEPS, 4.2))
    report = validate_records(ds, profile)
    json_path, coverage_path = write_reports(report, tmp_path)

    payload = json.loads(json_path.read_text())
    assert payload["ok"] is False
    assert payload["n_errors"] >= 1
    assert payload["findings_per_check"]["series_constant"] == 1
    assert "FAIL" in coverage_path.read_text()

    with pytest.raises(ValidationError):
        refuse_on_failure(report, "XM dataset")


def test_the_write_gate_lets_a_clean_report_through(dataset, profile):
    refuse_on_failure(validate_records(dataset, profile))  # must not raise


def test_warnings_alone_do_not_refuse_the_write():
    report = validate.ValidationReport()
    report.extend([validate.warning("phase_alignment", "r", "inconclusive")])
    assert report.ok
    refuse_on_failure(report)


def test_merge_keeps_every_finding_and_the_coverage_rows(dataset, profile):
    a = validate_records(dataset, profile)
    b = validate.ValidationReport(coverage=[{"station": "X", "month": "2026-06", "gap_days": 1}])
    b.extend([validate.error("x", "y", "z")])
    merged = validate.merge(a, b)
    assert not merged.ok
    assert len(merged.coverage) == 1
    assert "FAIL" in validate.summarize(merged)


# --- contract alignment with build.py / labels.py ----------------------------


def test_the_builders_declared_entity_and_anchor_spellings_are_accepted():
    """build.py's _ANNOTATION_SPEC declares entity_id / anchor_iso, not entity / anchor."""
    from bridge_fixtures import Annotation

    datasets = {}
    for profile_id, split in (("S", "train"), ("XM", "test")):
        ds = make_dataset(f"test/{profile_id}")
        record, _ = add_sample(ds, f"{profile_id}-0", split=split)
        record.annotations = tuple(
            a for a in record.annotations if a.key not in {"entity", "anchor"}
        )
        record.add_annotations(
            [
                Annotation(key="entity_id", value="S8|Muenchen Ost"),
                Annotation(key="anchor_iso", value="2026-06-01"),
            ]
        )
        datasets[profile_id] = ds

    findings = check_split_consistency(datasets)
    assert "split_consistency" in checks(findings)  # the collision is still seen


def test_flat_ctx_slots_are_gathered_the_way_labels_names_them():
    """labels.Label.context is a flat ctx_-prefixed dict, not a single map."""
    from bridge_fixtures import Annotation

    ds = make_dataset()
    record, task = add_sample(
        ds, "ctx", rationale="Mean delay is 4.0 minutes over 12 service dates."
    )
    record.annotations = tuple(a for a in record.annotations if a.key != "rationale_slots")
    record.add_annotations(
        [
            Annotation(key="ctx_mean_delay_min", value=4.0),
            Annotation(key="ctx_service_count", value=12),
        ]
    )
    slots, findings = validate.collect_slots(record)
    assert findings == []
    assert slots == {"ctx_mean_delay_min": 4.0, "ctx_service_count": 12}
    assert check_rationale_numbers(record, task) == []


def test_an_undeclared_ctx_slot_is_reported():
    """An undeclared slot is how a horizon-derived number reaches a rationale."""
    from bridge_fixtures import Annotation
    from labels import CONTEXT_SLOTS

    assert "ctx_horizon_mean_delay" not in CONTEXT_SLOTS
    ds = make_dataset()
    record, task = add_sample(ds, "leak", rationale="Next week averages 9.0 minutes.")
    record.annotations = tuple(a for a in record.annotations if a.key != "rationale_slots")
    record.add_annotations([Annotation(key="ctx_horizon_mean_delay", value=9.0)])

    findings = check_rationale_numbers(record, task)
    assert "rationale_numbers" in checks(findings)
    assert any("labels.CONTEXT_SLOTS" in f.message for f in findings)


def test_the_validator_names_slots_labels_actually_declares():
    from labels import CONTEXT_SLOTS

    assert CONTEXT_SLOTS, "labels.CONTEXT_SLOTS should be importable and non-empty"
    assert all(key.startswith(validate.CTX_SLOT_PREFIX) for key in CONTEXT_SLOTS)
