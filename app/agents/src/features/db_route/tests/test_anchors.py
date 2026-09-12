"""Offline tests for anchors.py: placement, disjointness, weighting, splits.

Run: python tests/test_anchors.py   (or under unittest discovery / pytest)
"""

from __future__ import annotations

import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from anchors import (  # noqa: E402
    ANCHOR_GAP_DAYS,
    EVAL_SPLITS,
    M_ANCHORS,
    MIN_ANCHOR_GAP_DAYS,
    REPEAT_MAX,
    anchor_window,
    anchors_manifest,
    horizon_of,
    plan_anchors,
    recency_weight,
    repeat_count,
)
from profiles import ANCHOR_STRIDE_DAYS, HORIZON_DAYS, RECENCY_HALF_LIFE_DAYS, profile  # noqa: E402

WINDOW = (dt.date(2025, 6, 1), dt.date(2026, 8, 31))
IDS = [f"station-{n:02d}--s-dest-{n:02d}--{n:012x}" for n in range(40)]


class TestPlacement(unittest.TestCase):
    def setUp(self) -> None:
        self.anchors = plan_anchors(IDS, window=WINDOW)

    def test_gap_is_thirty_rounded_onto_the_stride_grid(self) -> None:
        self.assertEqual(ANCHOR_GAP_DAYS, 35)
        self.assertGreaterEqual(ANCHOR_GAP_DAYS, MIN_ANCHOR_GAP_DAYS)
        self.assertEqual(ANCHOR_GAP_DAYS % ANCHOR_STRIDE_DAYS, 0)

    def test_horizons_of_one_entity_are_disjoint(self) -> None:
        """The reason for the >= 30 day gap: two anchors of one entity must
        never share a label observation, or the second is a copy of the first."""
        by_entity: dict[str, list] = {}
        for anchor in self.anchors:
            by_entity.setdefault(anchor.entity_id, []).append(anchor)
        self.assertTrue(by_entity)
        for entity_id, group in by_entity.items():
            group.sort(key=lambda a: a.anchor)
            for earlier, later in zip(group, group[1:]):
                self.assertLess(earlier.horizon_end, later.horizon_start, entity_id)
                self.assertGreaterEqual(
                    (later.anchor - earlier.anchor).days, MIN_ANCHOR_GAP_DAYS, entity_id
                )

    def test_horizon_starts_the_day_after_the_anchor(self) -> None:
        start, end = horizon_of(dt.date(2026, 3, 10))
        self.assertEqual(start, dt.date(2026, 3, 11))
        self.assertEqual(end, dt.date(2026, 3, 17))
        self.assertEqual((end - start).days + 1, HORIZON_DAYS)

    def test_every_entity_keeps_one_weekday(self) -> None:
        by_entity: dict[str, set[int]] = {}
        for anchor in self.anchors:
            by_entity.setdefault(anchor.entity_id, set()).add(anchor.anchor.weekday())
        for entity_id, weekdays in by_entity.items():
            self.assertEqual(len(weekdays), 1, entity_id)

    def test_the_corpus_covers_all_seven_weekdays(self) -> None:
        """`index mod 7`: any one entity's horizons stay on one weekday, and the
        corpus as a whole is flat over the week."""
        weekdays = {a.anchor.weekday() for a in self.anchors}
        self.assertEqual(weekdays, set(range(7)))

    def test_stagger_spreads_the_union_beyond_any_one_entity(self) -> None:
        per_entity_span = (M_ANCHORS - 1) * ANCHOR_GAP_DAYS
        dates = [a.anchor for a in self.anchors]
        union_span = (max(dates) - min(dates)).days
        self.assertGreater(union_span, per_entity_span)
        # ...and no entity's own span is longer than the design says.
        by_entity: dict[str, list[dt.date]] = {}
        for anchor in self.anchors:
            by_entity.setdefault(anchor.entity_id, []).append(anchor.anchor)
        for entity_id, dates in by_entity.items():
            self.assertLessEqual((max(dates) - min(dates)).days, per_entity_span, entity_id)

    def test_placement_is_reproducible_from_the_id_alone(self) -> None:
        again = plan_anchors(list(reversed(IDS)), window=WINDOW)
        self.assertEqual([a.as_dict() for a in self.anchors], [a.as_dict() for a in again])

    def test_a_short_window_drops_anchors_rather_than_shrinking_the_gap(self) -> None:
        short = (dt.date(2026, 1, 1), dt.date(2026, 3, 1))
        anchors = plan_anchors(IDS, window=short)
        counts = {}
        for anchor in anchors:
            counts[anchor.entity_id] = counts.get(anchor.entity_id, 0) + 1
        self.assertTrue(all(n < M_ANCHORS for n in counts.values()))
        for entity_id in counts:
            dates = sorted(a.anchor for a in anchors if a.entity_id == entity_id)
            for earlier, later in zip(dates, dates[1:]):
                self.assertGreaterEqual((later - earlier).days, MIN_ANCHOR_GAP_DAYS)


class TestWeighting(unittest.TestCase):
    def test_weight_halves_at_one_half_life(self) -> None:
        reference = dt.date(2026, 8, 31)
        fresh = recency_weight(reference, reference)
        one = recency_weight(reference - dt.timedelta(days=RECENCY_HALF_LIFE_DAYS), reference)
        two = recency_weight(reference - dt.timedelta(days=2 * RECENCY_HALF_LIFE_DAYS), reference)
        self.assertAlmostEqual(fresh, 1.0, places=12)
        self.assertAlmostEqual(one, 0.5, places=12)
        self.assertAlmostEqual(two, 0.25, places=12)
        self.assertAlmostEqual(one, fresh * 0.5, places=12)

    def test_repeat_is_the_weight_scaled_and_floored_at_one(self) -> None:
        reference = dt.date(2026, 8, 31)
        for age, expected in ((0, REPEAT_MAX), (90, 2), (180, 1), (365, 1)):
            weight = recency_weight(reference - dt.timedelta(days=age), reference)
            self.assertEqual(repeat_count(weight, "train"), expected, age)

    def test_eval_anchors_are_never_oversampled(self) -> None:
        """Reweighting a held-out set makes the metric a function of the
        weighting scheme, so val and test always get repeat=1 -- including the
        freshest ones, which is where the bug would be."""
        anchors = plan_anchors(IDS, window=WINDOW)
        evals = [a for a in anchors if a.split in EVAL_SPLITS]
        self.assertTrue(evals)
        self.assertTrue(all(a.repeat == 1 for a in evals))
        # The weight itself is still emitted, so an analysis can slice by it.
        self.assertTrue(any(a.weight > 0.5 for a in evals))
        # And the train split really is oversampled, or the test proves nothing.
        trains = [a for a in anchors if a.split == "train"]
        self.assertTrue(any(a.repeat > 1 for a in trains))

    def test_repeat_ignores_weight_for_eval_even_at_weight_one(self) -> None:
        self.assertEqual(repeat_count(1.0, "val"), 1)
        self.assertEqual(repeat_count(1.0, "test"), 1)
        self.assertEqual(repeat_count(1.0, "train"), REPEAT_MAX)


class TestSplits(unittest.TestCase):
    def test_temporal_split_is_ordered_in_time(self) -> None:
        anchors = plan_anchors(IDS, window=WINDOW)
        latest_train = max(a.anchor for a in anchors if a.split == "train")
        earliest_test = min(a.anchor for a in anchors if a.split == "test")
        self.assertLess(latest_train, earliest_test)

    def test_purge_keeps_a_train_horizon_out_of_the_val_period(self) -> None:
        anchors = plan_anchors(IDS, window=WINDOW)
        earliest_val = min(a.anchor for a in anchors if a.split == "val")
        for anchor in anchors:
            if anchor.split == "train":
                self.assertLess(anchor.horizon_end, earliest_val)

    def test_no_purge_means_no_gap(self) -> None:
        unpurged = plan_anchors(IDS, window=WINDOW, purge_days=0)
        purged = plan_anchors(IDS, window=WINDOW)
        self.assertGreater(len(unpurged), len(purged))

    def test_entity_split_puts_a_whole_entity_on_one_side(self) -> None:
        anchors = plan_anchors(IDS, window=WINDOW, split_mode="entity")
        by_entity: dict[str, set[str]] = {}
        for anchor in anchors:
            by_entity.setdefault(anchor.entity_id, set()).add(anchor.split)
        self.assertTrue(all(len(s) == 1 for s in by_entity.values()))
        self.assertEqual(
            {s for splits in by_entity.values() for s in splits}, {"train", "val", "test"}
        )

    def test_bad_splits_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            plan_anchors(IDS, window=WINDOW, splits=(0.5, 0.3, 0.3))
        with self.assertRaises(ValueError):
            plan_anchors(IDS, window=WINDOW, split_mode="random")


class TestWindowAndManifest(unittest.TestCase):
    def test_anchor_window_reserves_context_and_horizon(self) -> None:
        prof = profile("XM")
        first, last = anchor_window(prof, dt.date(2025, 11, 2), dt.date(2026, 8, 31))
        self.assertEqual(first, dt.date(2025, 11, 2) + dt.timedelta(days=119))
        self.assertEqual(last, dt.date(2026, 8, 31) - dt.timedelta(days=HORIZON_DAYS))

    def test_too_short_an_archive_raises(self) -> None:
        with self.assertRaises(ValueError):
            anchor_window(profile("XM"), dt.date(2026, 1, 1), dt.date(2026, 2, 1))

    def test_manifest_is_content_hashed_and_counts_add_up(self) -> None:
        anchors = plan_anchors(IDS, window=WINDOW)
        one = anchors_manifest(anchors)
        two = anchors_manifest(anchors)
        self.assertEqual(one["content_hash"], two["content_hash"])
        self.assertEqual(sum(one["counts"]["by_split"].values()), len(anchors))
        self.assertEqual(one["counts"]["entities"], len(IDS))
        self.assertNotEqual(
            one["content_hash"],
            anchors_manifest(anchors[:-1])["content_hash"],
        )
        self.assertAlmostEqual(
            one["design"]["effective_samples_per_entity"], 2.778, places=3
        )


if __name__ == "__main__":
    unittest.main()
