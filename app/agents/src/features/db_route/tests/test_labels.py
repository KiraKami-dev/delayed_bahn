"""Offline tests for labels.py: the attribution rule, computability, no leaks.

Run: python tests/test_labels.py   (or under unittest discovery / pytest)
"""

from __future__ import annotations

import datetime as dt
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from causes import ATTRIBUTION_FLOOR, DOMINANCE_FLOOR, FAMILY_NAMES  # noqa: E402
from labels import (  # noqa: E402
    CONTEXT_SLOTS,
    MIN_HORIZON_SERVICE_DATES,
    REASON_NO_SERVICE,
    REASON_OK,
    REASON_THIN_DATES,
    TREND_WINDOW_DAYS,
    UNATTRIBUTED,
    LabelSpec,
    assert_no_horizon_leak,
    compute_labels,
    label_computable,
    log1p_delay,
    open_workspace,
    resolve_cause,
)
from fixtures import new_fixture  # noqa: E402

ANCHOR = dt.date(2026, 3, 1)
CONTEXT_DAYS = 60
START = ANCHOR - dt.timedelta(days=CONTEXT_DAYS + 30)


def _spec(station: str = "Hbf", group: str = "S -> Ost", anchor: dt.date = ANCHOR) -> LabelSpec:
    return LabelSpec("e1", group, station, anchor)


def _workspace(fixture, specs, *, causes="causes", notices=None, context_days=CONTEXT_DAYS):
    con = fixture.commit()
    return open_workspace(
        con,
        specs,
        events="events",
        causes=causes,
        notices=notices,
        context_days=context_days,
    )


class TestAttributionRule(unittest.TestCase):
    """`resolve_cause` in isolation -- the two floors, exercised at the edges."""

    def test_refuses_to_name_a_cause_below_the_attribution_floor(self) -> None:
        # Every attributed minute is `works`, but only 20% of delayed stops
        # carry any code at all. One unanimous fifth is not evidence.
        family, share, shares = resolve_cause(100, 20, {"works": 500.0})
        self.assertEqual(family, UNATTRIBUTED)
        self.assertAlmostEqual(share, 0.20)
        self.assertAlmostEqual(shares["works"], 1.0)

    def test_names_a_cause_when_both_floors_clear(self) -> None:
        family, share, shares = resolve_cause(
            100, 60, {"works": 80.0, "knock_on": 20.0}
        )
        self.assertEqual(family, "works")
        self.assertAlmostEqual(share, 0.60)
        self.assertAlmostEqual(shares["works"], 0.80)

    def test_refuses_when_no_family_dominates(self) -> None:
        # Well above the attribution floor, but three families at a third each:
        # a week where everything went slightly wrong has no single reason.
        family, share, _ = resolve_cause(
            100, 90, {"works": 30.0, "weather": 30.0, "knock_on": 30.0}
        )
        self.assertEqual(family, UNATTRIBUTED)
        self.assertGreater(share, ATTRIBUTION_FLOOR)

    def test_the_floors_are_exactly_the_contract_values(self) -> None:
        just_under = resolve_cause(100, 34, {"works": 100.0})[0]
        just_over = resolve_cause(100, 35, {"works": 100.0})[0]
        self.assertEqual(just_under, UNATTRIBUTED)
        self.assertEqual(just_over, "works")
        self.assertEqual(ATTRIBUTION_FLOOR, 0.35)
        under = resolve_cause(100, 100, {"a": 39.0, "b": 61.0})
        self.assertEqual(DOMINANCE_FLOOR, 0.40)
        self.assertEqual(under[0], "b")
        split = resolve_cause(100, 100, {"works": 39.0, "weather": 39.0, "staff": 22.0})
        self.assertEqual(split[0], UNATTRIBUTED)

    def test_no_attributed_minutes_is_unattributed_not_a_crash(self) -> None:
        self.assertEqual(resolve_cause(0, 0, {})[0], UNATTRIBUTED)
        self.assertEqual(resolve_cause(10, 10, {})[0], UNATTRIBUTED)

    def test_ties_resolve_alphabetically(self) -> None:
        first = resolve_cause(10, 10, {"weather": 50.0, "staff": 50.0})[0]
        second = resolve_cause(10, 10, {"staff": 50.0, "weather": 50.0})[0]
        self.assertEqual(first, second)
        self.assertEqual(first, "staff")


class TestAttributionEndToEnd(unittest.TestCase):
    """The same rule, but reached through the real SQL over cause shards."""

    def _build(self, attributed_days: int, families: tuple[str, ...]) -> list:
        fixture = new_fixture()
        horizon_days = tuple(ANCHOR + dt.timedelta(days=d) for d in range(1, 8))
        fixture.add_service(
            train_type="S",
            destination="Ost",
            station="Hbf",
            start=START,
            days=(ANCHOR - START).days + 10,
            delay=9,
        )
        # Attach causes to the first `attributed_days` days of the horizon only.
        for day in horizon_days[:attributed_days]:
            fixture.add_cause(f"S-Ost-Hbf-{day.isoformat()}-0", [31], list(families))
        ws = _workspace(fixture, [_spec()])
        return compute_labels(ws)

    def test_thin_attribution_in_the_horizon_stays_unattributed(self) -> None:
        labels = self._build(2, ("works",))  # 2 of 7 delayed stops = 29% < 35%
        self.assertEqual(len(labels), 1)
        self.assertEqual(labels[0].dominant_cause_family, UNATTRIBUTED)
        self.assertLess(labels[0].horizon_attributed_share, ATTRIBUTION_FLOOR)

    def test_dense_attribution_names_the_family(self) -> None:
        labels = self._build(6, ("works",))  # 6 of 7 = 86%
        self.assertEqual(labels[0].dominant_cause_family, "works")
        self.assertGreater(labels[0].horizon_attributed_share, ATTRIBUTION_FLOOR)
        self.assertAlmostEqual(labels[0].family_shares["works"], 1.0)

    def test_a_multi_family_stop_counts_in_every_family(self) -> None:
        labels = self._build(6, ("works", "weather", "technical"))
        self.assertEqual(labels[0].dominant_cause_family, UNATTRIBUTED)
        shares = labels[0].family_shares
        self.assertAlmostEqual(sum(shares.values()), 1.0, places=6)
        self.assertAlmostEqual(shares["works"], 1 / 3, places=6)


class TestComputability(unittest.TestCase):
    def test_rejects_a_thin_entity(self) -> None:
        """The gate that has to run before curation: a pair that calls twice in
        the horizon has no label, however good its monthly support looked."""
        fixture = new_fixture()
        fixture.add_service(
            train_type="S",
            destination="Ost",
            station="Hbf",
            start=START,
            days=(ANCHOR - START).days + 10,
            weekdays=(5,),  # Saturdays only: one, maybe two, days per horizon
            delay=3,
        )
        con = fixture.commit()
        support = label_computable(con, _spec(), ANCHOR, events="events")
        self.assertFalse(support.computable)
        self.assertEqual(support.reason, REASON_THIN_DATES)
        self.assertLess(support.n_service_dates, MIN_HORIZON_SERVICE_DATES)

    def test_accepts_a_weekday_service_that_lost_a_day(self) -> None:
        fixture = new_fixture()
        fixture.add_service(
            train_type="S",
            destination="Ost",
            station="Hbf",
            start=START,
            days=(ANCHOR - START).days + 10,
            weekdays=(0, 1, 2, 3),  # four weekdays: exactly the design minimum
            delay=3,
        )
        con = fixture.commit()
        support = label_computable(con, _spec(), ANCHOR, events="events")
        self.assertTrue(support.computable)
        self.assertEqual(support.reason, REASON_OK)

    def test_no_service_at_all_is_its_own_reason(self) -> None:
        fixture = new_fixture()
        fixture.add_service(
            train_type="S", destination="Ost", station="Hbf", start=START, days=30, delay=3
        )
        con = fixture.commit()
        support = label_computable(
            con, _spec(anchor=dt.date(2026, 12, 1)), dt.date(2026, 12, 1), events="events"
        )
        self.assertFalse(support.computable)
        self.assertEqual(support.reason, REASON_NO_SERVICE)

    def test_incomputable_samples_are_skipped_by_default(self) -> None:
        fixture = new_fixture()
        fixture.add_service(
            train_type="S",
            destination="Ost",
            station="Hbf",
            start=START,
            days=(ANCHOR - START).days + 10,
            weekdays=(5,),
            delay=3,
        )
        ws = _workspace(fixture, [_spec()])
        self.assertEqual(compute_labels(ws), [])
        self.assertEqual(len(compute_labels(ws, skip_incomputable=False)), 1)


class TestTargets(unittest.TestCase):
    def _labels(self, delay: int):
        fixture = new_fixture()
        fixture.add_service(
            train_type="S",
            destination="Ost",
            station="Hbf",
            start=START,
            days=(ANCHOR - START).days + 10,
            delay=delay,
        )
        return compute_labels(_workspace(fixture, [_spec()]))[0]

    def test_scalar_and_bool_never_disagree(self) -> None:
        under = self._labels(4)
        over = self._labels(6)
        self.assertFalse(under.late_5min)
        self.assertTrue(over.late_5min)
        self.assertAlmostEqual(under.departure_delay_min, 4.0)
        self.assertAlmostEqual(over.departure_delay_min, 6.0)

    def test_log1p_is_emitted_alongside_the_raw_scalar(self) -> None:
        label = self._labels(12)
        self.assertAlmostEqual(label.arrival_delay_log1p, math.log1p(12.0), places=9)
        self.assertAlmostEqual(label.departure_delay_min, 12.0)

    def test_log1p_clamps_early_trains(self) -> None:
        self.assertEqual(log1p_delay(-3.0), 0.0)
        self.assertEqual(log1p_delay(0.0), 0.0)
        label = self._labels(-4)
        self.assertAlmostEqual(label.departure_delay_min, -4.0)  # raw keeps the sign
        self.assertEqual(label.arrival_delay_log1p, 0.0)
        self.assertFalse(label.late_5min)

    def test_no_resampling_happens_here(self) -> None:
        """labels.py emits one row per (entity, anchor) whatever the class. The
        only multiplicity in this pipeline is anchors.repeat."""
        fixture = new_fixture()
        specs = []
        for n in range(6):
            station = f"S{n}"
            fixture.add_service(
                train_type="S",
                destination="Ost",
                station=station,
                start=START,
                days=(ANCHOR - START).days + 10,
                delay=1 if n % 2 else 20,
            )
            specs.append(LabelSpec(f"e{n}", "S -> Ost", station, ANCHOR))
        labels = compute_labels(_workspace(fixture, specs))
        self.assertEqual(len(labels), 6)
        self.assertEqual(len({(l.entity_id, l.anchor) for l in labels}), 6)
        self.assertEqual(sum(1 for l in labels if l.late_5min), 3)


class TestContextSlots(unittest.TestCase):
    def _fixture(self, horizon_delay: int, works: bool = False):
        fixture = new_fixture()
        fixture.add_service(
            train_type="S",
            destination="Ost",
            station="Hbf",
            start=START,
            days=(ANCHOR - START).days,  # context only, up to and including the anchor
            delay=3,
        )
        fixture.add_service(
            train_type="S",
            destination="Ost",
            station="Hbf",
            start=ANCHOR + dt.timedelta(days=1),
            days=7,
            delay=horizon_delay,
            families=("works",) if works else (),
        )
        return fixture

    def test_slots_are_invariant_to_the_horizon(self) -> None:
        """The invariant the whole module exists to hold. Same context, two
        different horizons: the answer moves, the citable numbers do not."""
        calm = compute_labels(_workspace(self._fixture(2), [_spec()]))[0]
        wild = compute_labels(_workspace(self._fixture(45, works=True), [_spec()]))[0]
        self.assertNotEqual(calm.departure_delay_min, wild.departure_delay_min)
        self.assertNotEqual(calm.late_5min, wild.late_5min)
        self.assertEqual(calm.context, wild.context)

    def test_every_declared_slot_is_present(self) -> None:
        label = compute_labels(_workspace(self._fixture(2), [_spec()]))[0]
        self.assertEqual(set(label.context), set(CONTEXT_SLOTS))
        assert_no_horizon_leak(label.context)

    def test_undeclared_or_unprefixed_slots_are_refused(self) -> None:
        with self.assertRaises(ValueError):
            assert_no_horizon_leak({"mean_delay_min": 3.0})
        with self.assertRaises(ValueError):
            assert_no_horizon_leak({"ctx_not_declared": 1.0})

    def test_context_numbers_describe_the_context(self) -> None:
        label = compute_labels(_workspace(self._fixture(45), [_spec()]))[0]
        self.assertAlmostEqual(label.context["ctx_mean_delay_min"], 3.0)
        self.assertAlmostEqual(label.context["ctx_median_delay_min"], 3.0)
        # The fixture's context service stops the day before the anchor, so the
        # 60-day window holds 59 service dates -- and the anchor day is in the
        # context window, not the horizon.
        self.assertEqual(label.context["ctx_service_dates"], CONTEXT_DAYS - 1)
        self.assertEqual(label.context["ctx_service_count"], CONTEXT_DAYS - 1)
        self.assertEqual(label.context["ctx_modal_hour"], 8)
        self.assertEqual(label.context["ctx_trend_window_days"], TREND_WINDOW_DAYS)
        self.assertAlmostEqual(label.context["ctx_trend_delta_min"], 0.0)
        self.assertEqual(label.context["ctx_late_5_share"], 0.0)

    def test_trend_sees_a_shift_inside_the_context(self) -> None:
        fixture = new_fixture()
        split_at = ANCHOR - dt.timedelta(days=TREND_WINDOW_DAYS)
        fixture.add_service(
            train_type="S", destination="Ost", station="Hbf",
            start=ANCHOR - dt.timedelta(days=CONTEXT_DAYS - 1),
            days=CONTEXT_DAYS - TREND_WINDOW_DAYS, delay=2,
        )
        fixture.add_service(
            train_type="S", destination="Ost", station="Hbf",
            start=split_at + dt.timedelta(days=1), days=TREND_WINDOW_DAYS, delay=10,
        )
        fixture.add_service(
            train_type="S", destination="Ost", station="Hbf",
            start=ANCHOR + dt.timedelta(days=1), days=7, delay=2,
        )
        label = compute_labels(_workspace(fixture, [_spec()]))[0]
        self.assertAlmostEqual(label.context["ctx_recent_mean_delay_min"], 10.0)
        self.assertAlmostEqual(label.context["ctx_prior_mean_delay_min"], 2.0)
        self.assertAlmostEqual(label.context["ctx_trend_delta_min"], 8.0)

    def test_missing_cause_shards_read_as_None_not_zero(self) -> None:
        """"No delay was attributed" and "attribution was never extracted" are
        different claims; a rationale must not be handed 0.0 for the second."""
        fixture = self._fixture(2)
        ws = _workspace(fixture, [_spec()], causes=None)
        label = compute_labels(ws)[0]
        self.assertIsNone(label.context["ctx_attributed_share"])
        for family in FAMILY_NAMES:
            self.assertIsNone(label.context[f"ctx_family_share_{family}"])
        self.assertIsNone(label.context["ctx_works_notice_coverage"])

    def test_modal_hour_picks_the_busiest_hour_deterministically(self) -> None:
        fixture = new_fixture()
        for hour, days in ((7, 40), (17, 20)):
            fixture.add_service(
                train_type="S", destination="Ost", station="Hbf",
                start=ANCHOR - dt.timedelta(days=CONTEXT_DAYS - 1),
                days=days, hour=hour, delay=2 if hour == 7 else 30,
            )
        fixture.add_service(
            train_type="S", destination="Ost", station="Hbf",
            start=ANCHOR + dt.timedelta(days=1), days=7, hour=7, delay=2,
        )
        label = compute_labels(_workspace(fixture, [_spec()]))[0]
        self.assertEqual(label.context["ctx_modal_hour"], 7)
        self.assertAlmostEqual(label.context["ctx_mean_delay_at_hour"], 2.0)
        # ...and it is not just the overall mean, which the 17:00 run inflates.
        self.assertGreater(label.context["ctx_mean_delay_min"], 2.0)


class TestWorksNoticeCoverage(unittest.TestCase):
    def test_coverage_is_the_fraction_of_context_days_under_a_notice(self) -> None:
        fixture = new_fixture()
        fixture.add_service(
            train_type="S", destination="Ost", station="Hbf",
            start=ANCHOR - dt.timedelta(days=CONTEXT_DAYS - 1),
            days=CONTEXT_DAYS + 8, delay=3,
        )
        covered_from = ANCHOR - dt.timedelta(days=29)
        fixture.add_notice(
            "him-1", "Bauarbeiten", covered_from, ANCHOR,
            [f"S-Ost-Hbf-{covered_from.isoformat()}-0"],
        )
        ws = _workspace(fixture, [_spec()], notices="notices")
        label = compute_labels(ws)[0]
        self.assertAlmostEqual(label.context["ctx_works_notice_coverage"], 30 / CONTEXT_DAYS, places=4)

    def test_a_non_works_notice_does_not_count(self) -> None:
        fixture = new_fixture()
        fixture.add_service(
            train_type="S", destination="Ost", station="Hbf",
            start=ANCHOR - dt.timedelta(days=CONTEXT_DAYS - 1),
            days=CONTEXT_DAYS + 8, delay=3,
        )
        day = ANCHOR - dt.timedelta(days=29)
        fixture.add_notice(
            "him-2", "Information", day, ANCHOR, [f"S-Ost-Hbf-{day.isoformat()}-0"]
        )
        ws = _workspace(fixture, [_spec()], notices="notices")
        self.assertEqual(compute_labels(ws)[0].context["ctx_works_notice_coverage"], 0.0)

    def test_overlapping_notices_cannot_push_coverage_over_one(self) -> None:
        fixture = new_fixture()
        fixture.add_service(
            train_type="S", destination="Ost", station="Hbf",
            start=ANCHOR - dt.timedelta(days=CONTEXT_DAYS - 1),
            days=CONTEXT_DAYS + 8, delay=3,
        )
        first = ANCHOR - dt.timedelta(days=CONTEXT_DAYS - 1)
        for n in range(4):
            fixture.add_notice(
                f"him-{n}", "Bauarbeiten", first, ANCHOR, [f"S-Ost-Hbf-{first.isoformat()}-0"]
            )
        ws = _workspace(fixture, [_spec()], notices="notices")
        self.assertAlmostEqual(compute_labels(ws)[0].context["ctx_works_notice_coverage"], 1.0)


class TestDeterminism(unittest.TestCase):
    def test_two_runs_agree_exactly(self) -> None:
        fixture = new_fixture()
        specs = []
        for n in range(5):
            station = f"S{n}"
            fixture.add_service(
                train_type="S", destination="Ost", station=station, start=START,
                days=(ANCHOR - START).days + 10, delay=2 + n, jitter=3, seed=n,
                families=("works",) if n % 2 else (),
            )
            specs.append(LabelSpec(f"e{n}", "S -> Ost", station, ANCHOR))
        one = [l.as_dict() for l in compute_labels(_workspace(fixture, specs))]
        two = [l.as_dict() for l in compute_labels(_workspace(fixture, list(reversed(specs))))]
        self.assertEqual(one, two)
        self.assertEqual([l["entity_id"] for l in one], sorted(l["entity_id"] for l in one))


if __name__ == "__main__":
    unittest.main()
