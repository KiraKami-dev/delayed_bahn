"""Offline tests for error404/db-route-week and its three siblings. No network, no fact cache.

The synthetic fixture is the db_route feature package's own: three hourly fact
tables with a known rush-hour shape. What is tested here is the connector
boundary -- that the card loads, that the four ids bind to the four profiles,
that a build is byte-identical to itself, and that the annotation model is
used the way the card claims (spans on the disruption notices, captions per
series, four tasks per record, chained).
"""

from __future__ import annotations

import datetime as dt
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
FEATURES = HERE.parents[4] / "src" / "features" / "db_route"
for p in (FEATURES, FEATURES / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import labels as L  # noqa: E402
import profiles as P  # noqa: E402
from connector import RecordInput, build_dataset  # noqa: E402
from resample import FactCache  # noqa: E402
from test_resample import ANCHOR, KEY, RELATIONS, SERVICE, STATION, fixture_connection  # noqa: E402
from timenet.testing import assert_datasets_equal  # noqa: E402
from timenet.types import TimeInterval  # noqa: E402

from timenet_connectors.datasets.error404.db_route_multiscale import CONNECTOR as XM  # noqa: E402
from timenet_connectors.datasets.error404.db_route_quarter import CONNECTOR as M  # noqa: E402
from timenet_connectors.datasets.error404.db_route_season import CONNECTOR as LL  # noqa: E402
from timenet_connectors.datasets.error404.db_route_week import CONNECTOR as S  # noqa: E402

EXPECTED = {
    S: ("error404/db-route-week", "S"),
    M: ("error404/db-route-quarter", "M"),
    LL: ("error404/db-route-season", "L"),
    XM: ("error404/db-route-multiscale", "XM"),
}


def _label() -> L.Label:
    return L.Label(
        entity_id="e1", anchor=ANCHOR, n_events=40, n_service_dates=7,
        departure_delay_min=3.2, arrival_delay_log1p=1.435, late_5min=False, late_5_share=0.2,
        dominant_cause_family="knock_on", horizon_attributed_share=0.41,
        family_shares={"knock_on": 0.6, "works": 0.1},
        context={"ctx_habit_median_delay_8w": 2.5, "ctx_scheduled_recovery_min": 3.0},
    )


def _records(prof: P.TimelineProfile) -> list[RecordInput]:
    cache = FactCache(con=fixture_connection(), relations=RELATIONS)
    window = cache.window(KEY, ANCHOR, prof)
    notice = {
        "notice_id": "r1", "category": "Bauarbeiten", "priority": 1,
        "valid_from": dt.datetime(2026, 5, 20), "valid_to": dt.datetime(2026, 6, 10),
    }
    return [RecordInput(
        entity_id="e1", service_group=SERVICE, station=STATION, train_type="S", anchor=ANCHOR,
        window=window, label=_label(), split="train", split_cell="train", recency_weight=1.0,
        notices=(notice,),
    )]


class TestCards(unittest.TestCase):
    def test_four_ids_bind_four_profiles(self) -> None:
        for cls, (dataset_id, profile_id) in EXPECTED.items():
            meta = cls().metadata()
            self.assertEqual(meta.dataset_id, dataset_id)
            self.assertEqual(cls.PROFILE, profile_id)
            self.assertIn(f"profile:{profile_id}", meta.tags)
            self.assertEqual(str(meta.license.value), "CC-BY-4.0")


class TestBuild(unittest.TestCase):
    def test_build_is_deterministic_and_uses_the_annotation_model(self) -> None:
        prof = P.PROFILES["S"]
        meta = S().metadata()
        first = build_dataset(prof, _records(prof), metadata=meta, bundle_sha="test")
        second = build_dataset(prof, _records(prof), metadata=meta, bundle_sha="test")
        assert_datasets_equal(first, second)

        self.assertEqual(len(first.records), 1)
        record = first.records[0]
        self.assertEqual(len(record.time_series), prof.n_series)
        signals = {ts.signal for ts in record.time_series}
        self.assertIn("week/station_delay", signals)

        by_key: dict[str, list] = {}
        for ann in record.annotations:
            by_key.setdefault(ann.key, []).append(ann)
        # metadata travels as span-less annotations
        for key in ("entity_id", "station", "split", "split_cell", "artifact_bundle_sha", "recency_weight"):
            self.assertIn(key, by_key, key)
            self.assertIsNone(by_key[key][0].span)
        # one caption per series, and they differ (four series share one spec)
        captions = [a for k, v in by_key.items() if k.startswith("caption:") for a in v]
        self.assertEqual(len(captions), prof.n_series)
        self.assertEqual(len({a.value for a in captions}), prof.n_series)
        # the dated notice is an interval annotation, not a flag
        works = by_key["planned_disruption"]
        self.assertEqual(len(works), 1)
        self.assertIsInstance(works[0].span, TimeInterval)
        self.assertEqual(works[0].value, "Bauarbeiten")

        tasks = [t for t in first.tasks]
        self.assertEqual(len(tasks), 4)
        schema = first.derive_schema()
        self.assertGreaterEqual(len(schema.annotations), 10)

    def test_multiscale_carries_three_axes(self) -> None:
        prof = P.PROFILES["XM"]
        ds = build_dataset(prof, _records(prof), metadata=XM().metadata(), bundle_sha="test")
        record = ds.records[0]
        rates = {ts.time_axis.period_us for ts in record.time_series}
        self.assertEqual(len(rates), 3)
        ds.derive_schema()


if __name__ == "__main__":
    unittest.main()
