"""Offline tests for entities.py: enumeration, the rejection log, the quota.

Run: python tests/test_entities.py   (or under unittest discovery / pytest)
"""

from __future__ import annotations

import datetime as dt
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from entities import (  # noqa: E402
    MAX_PER_STATION,
    MIN_SERVICE_DATES,
    REASON_OUTSIDE_UNIVERSE,
    REASON_THIN,
    curate,
    entities_manifest,
    entity_id,
    enumerate_entities,
    stable_digest,
)
from fixtures import EPOCH, corpus_fixture  # noqa: E402


class TestEnumeration(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = corpus_fixture()
        self.con = self.fixture.commit()

    def tearDown(self) -> None:
        self.con.close()

    def test_thin_pairs_are_rejected_with_a_reason(self) -> None:
        qualifying, rejected = enumerate_entities(
            self.con, events="events", causes="causes"
        )
        self.assertTrue(qualifying)
        self.assertTrue(rejected)
        for rejection in rejected:
            self.assertIn(REASON_THIN, rejection.reasons)
            self.assertLess(rejection.n_service_dates, MIN_SERVICE_DATES)
        for entity in qualifying:
            self.assertGreaterEqual(entity.n_service_dates, MIN_SERVICE_DATES)
        # The log accounts for every candidate: nothing is silently dropped.
        self.assertEqual(len(qualifying) + len(rejected), 8 * 6)

    def test_universe_exclusion_is_logged_not_hidden(self) -> None:
        keep = [f"Station {n:02d}" for n in range(4)]
        qualifying, rejected = enumerate_entities(
            self.con, events="events", causes="causes", universe=keep
        )
        self.assertTrue(all(e.station in keep for e in qualifying))
        outside = [r for r in rejected if REASON_OUTSIDE_UNIVERSE in r.reasons]
        self.assertTrue(outside)
        self.assertTrue(all(r.station not in keep for r in outside))
        # A pair can fail two checks; both are recorded, in sorted order.
        both = [r for r in rejected if len(r.reasons) > 1]
        self.assertTrue(both)
        self.assertEqual(list(both[0].reasons), sorted(both[0].reasons))

    def test_service_group_is_type_and_destination(self) -> None:
        qualifying, _ = enumerate_entities(self.con, events="events")
        entity = qualifying[0]
        self.assertEqual(entity.service_group, f"{entity.train_type} -> {entity.service_group.split(' -> ')[1]}")

    def test_window_bounds_the_enumeration(self) -> None:
        window = (EPOCH, EPOCH + dt.timedelta(days=9))
        qualifying, rejected = enumerate_entities(
            self.con, events="events", window=window
        )
        # Ten days of calendar cannot produce 20 distinct service dates.
        self.assertEqual(qualifying, [])
        self.assertTrue(all(r.n_service_dates <= 10 for r in rejected))

    def test_regime_affected_flag_comes_from_cause_families(self) -> None:
        qualifying, _ = enumerate_entities(self.con, events="events", causes="causes")
        affected = [e for e in qualifying if e.is_regime_affected]
        self.assertTrue(affected)
        self.assertTrue(all(e.affected_days >= 3 for e in affected))
        # Without the cause shards nothing is affected -- and that must not look
        # like "the network was calm".
        no_causes, _ = enumerate_entities(self.con, events="events")
        self.assertTrue(all(e.affected_days == 0 for e in no_causes))


class TestIdentity(unittest.TestCase):
    def test_entity_id_is_process_independent(self) -> None:
        """The whole corpus is keyed on these ids, so PYTHONHASHSEED must not
        reach them. builtin hash() would pass a single-process test and produce
        a different corpus on the next run."""
        snippet = (
            "import sys; sys.path.insert(0, %r); "
            "from entities import entity_id, stable_digest; "
            "print(entity_id('S -> M\\u00fcnchen Ost', 'M\\u00fcnchen Hbf'), "
            "stable_digest('abc'))" % str(Path(__file__).resolve().parents[1])
        )
        outputs = set()
        for seed in ("0", "1", "12345"):
            result = subprocess.run(
                [sys.executable, "-c", snippet],
                capture_output=True,
                text=True,
                env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"},
                check=True,
            )
            outputs.add(result.stdout.strip())
        self.assertEqual(len(outputs), 1, outputs)

    def test_folded_names_do_not_collide(self) -> None:
        a = entity_id("S -> München Ost", "München Hbf")
        b = entity_id("S -> Munchen Ost", "Muenchen Hbf")
        self.assertNotEqual(a, b)
        self.assertTrue(a.startswith("munchen-hbf--"))


class TestCuration(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = corpus_fixture(n_stations=30, n_groups_per_station=8)
        self.con = self.fixture.commit()
        self.qualifying, self.rejected = enumerate_entities(
            self.con, events="events", causes="causes"
        )

    def tearDown(self) -> None:
        self.con.close()

    def test_curation_is_deterministic(self) -> None:
        first = curate(self.qualifying, target=100)
        second = curate(list(reversed(self.qualifying)), target=100)
        self.assertEqual(
            [e.entity_id for e in first.selected], [e.entity_id for e in second.selected]
        )
        self.assertEqual(first.report, second.report)

    def test_quota_holds(self) -> None:
        result = curate(self.qualifying, target=100, min_stations=25, max_per_station=5)
        self.assertEqual(len(result.selected), 100)
        per_station: dict[str, int] = {}
        for entity in result.selected:
            per_station[entity.station] = per_station.get(entity.station, 0) + 1
        self.assertLessEqual(max(per_station.values()), 5)
        self.assertGreaterEqual(len(per_station), 25)
        self.assertGreater(len(result.report["per_train_type"]), 1)
        self.assertGreaterEqual(result.report["affected_share"], 0.20)
        self.assertNotIn("min_affected_share", result.unmet)

    def test_station_floor_holds_when_the_target_is_small(self) -> None:
        result = curate(self.qualifying, target=25, min_stations=25, max_per_station=30)
        self.assertEqual(len({e.station for e in result.selected}), 25)

    def test_unreachable_quota_is_reported_not_raised(self) -> None:
        result = curate(self.qualifying, target=10_000)
        self.assertIn("target", result.unmet)
        self.assertLess(result.report["selected"], 10_000)
        with self.assertRaises(ValueError):
            curate(self.qualifying, target=10_000, strict=True)

    def test_default_cap_binds_at_the_real_target(self) -> None:
        """MAX_PER_STATION=30 at target 3,000 needs >= 100 stations. A 30-station
        pool must therefore stop at 900, and say so rather than over-filling."""
        result = curate(self.qualifying, target=3000)
        self.assertLessEqual(result.report["max_per_station_observed"], MAX_PER_STATION)
        self.assertLessEqual(len(result.selected), 30 * MAX_PER_STATION)
        self.assertIn("target", result.unmet)


class TestManifest(unittest.TestCase):
    def test_content_hash_tracks_content(self) -> None:
        fixture = corpus_fixture(n_stations=4, n_groups_per_station=4)
        con = fixture.commit()
        qualifying, rejected = enumerate_entities(con, events="events", causes="causes")
        one = entities_manifest(qualifying, rejected, curation=curate(qualifying, target=5))
        two = entities_manifest(qualifying, rejected, curation=curate(qualifying, target=5))
        self.assertEqual(one["content_hash"], two["content_hash"])
        three = entities_manifest(qualifying, rejected, curation=curate(qualifying, target=6))
        self.assertNotEqual(one["content_hash"], three["content_hash"])
        self.assertEqual(
            one["counts"]["candidates"],
            one["counts"]["qualifying"] + one["counts"]["rejected"],
        )
        con.close()


if __name__ == "__main__":
    unittest.main()
