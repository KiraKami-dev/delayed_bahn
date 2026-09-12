"""The three modules wired together, offline: entities -> anchors -> labels.

Each module has its own tests; this one exists for the seams between them --
the id that entities.py mints and anchors.py hashes, the (entity, anchor) join
that labels.py rebuilds, and the JSON round trip that a build script relies on.

Run: python tests/test_pipeline.py   (or under unittest discovery / pytest)
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from anchors import anchors_manifest, plan_anchors, read_anchors, write_anchors  # noqa: E402
from entities import (  # noqa: E402
    curate,
    entities_manifest,
    enumerate_entities,
    read_entities,
    write_entities,
)
from labels import compute_labels, horizon_support, open_workspace, specs_from  # noqa: E402
from fixtures import EPOCH, corpus_fixture  # noqa: E402

CONTEXT_DAYS = 30


class TestPipeline(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = corpus_fixture(n_stations=10, n_groups_per_station=4, days=200)
        self.con = self.fixture.commit()
        self.qualifying, self.rejected = enumerate_entities(
            self.con, events="events", causes="causes"
        )
        self.curation = curate(self.qualifying, target=20, min_stations=10, max_per_station=4)
        window = (
            EPOCH + dt.timedelta(days=CONTEXT_DAYS),
            EPOCH + dt.timedelta(days=190),
        )
        self.anchors = plan_anchors(self.curation.selected, window=window)

    def tearDown(self) -> None:
        self.con.close()

    def test_anchor_entity_ids_are_the_entity_ids(self) -> None:
        known = {e.entity_id for e in self.curation.selected}
        self.assertEqual({a.entity_id for a in self.anchors}, known)

    def test_specs_join_entities_to_anchors(self) -> None:
        specs = specs_from(self.curation.selected, self.anchors)
        self.assertEqual(len(specs), len({(a.entity_id, a.anchor) for a in self.anchors}))
        by_id = {e.entity_id: e for e in self.curation.selected}
        for spec in specs:
            self.assertEqual(spec.station, by_id[spec.entity_id].station)
            self.assertEqual(spec.service_group, by_id[spec.entity_id].service_group)

    def test_labels_come_out_for_the_computable_samples(self) -> None:
        specs = specs_from(self.curation.selected, self.anchors)
        ws = open_workspace(
            self.con,
            specs,
            events="events",
            causes="causes",
            notices="notices",
            context_days=CONTEXT_DAYS,
        )
        support = {(s.entity_id, s.anchor): s for s in horizon_support(ws)}
        labels = compute_labels(ws)
        self.assertTrue(labels)
        self.assertEqual(
            len(labels), sum(1 for s in support.values() if s.computable)
        )
        for label in labels:
            self.assertTrue(support[(label.entity_id, label.anchor)].computable)

    def test_manifests_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = entities_manifest(
                self.qualifying, self.rejected, curation=self.curation
            )
            write_entities(root / "entities.json", manifest)
            back = read_entities(root / "entities.json")
            self.assertEqual(
                [e.as_dict() for e in back], [e.as_dict() for e in self.qualifying]
            )
            payload = anchors_manifest(self.anchors)
            write_anchors(root / "anchors.json", payload)
            self.assertEqual(
                [a.as_dict() for a in read_anchors(root / "anchors.json")],
                [a.as_dict() for a in self.anchors],
            )
            # The hash survives a write/read cycle, which is what makes it usable
            # as a provenance key in the anchors manifest.
            reloaded = json.loads((root / "entities.json").read_text())
            self.assertEqual(reloaded["content_hash"], manifest["content_hash"])

    def test_rerunning_the_whole_chain_is_byte_identical(self) -> None:
        qualifying, rejected = enumerate_entities(
            self.con, events="events", causes="causes"
        )
        curation = curate(qualifying, target=20, min_stations=10, max_per_station=4)
        window = (EPOCH + dt.timedelta(days=CONTEXT_DAYS), EPOCH + dt.timedelta(days=190))
        anchors = plan_anchors(curation.selected, window=window)
        self.assertEqual(
            entities_manifest(qualifying, rejected, curation=curation)["content_hash"],
            entities_manifest(self.qualifying, self.rejected, curation=self.curation)[
                "content_hash"
            ],
        )
        self.assertEqual(
            anchors_manifest(anchors)["content_hash"],
            anchors_manifest(self.anchors)["content_hash"],
        )

    def test_labels_do_not_depend_on_the_context_length(self) -> None:
        """The bake-off's controlling assumption: change the profile's context
        and the targets must not move, only the slots."""
        specs = specs_from(self.curation.selected, self.anchors)
        targets = {}
        for context_days, prefix in ((15, "_p15"), (30, "_p30")):
            ws = open_workspace(
                self.con,
                specs,
                events="events",
                causes="causes",
                context_days=context_days,
                prefix=prefix,
            )
            targets[context_days] = {
                (l.entity_id, l.anchor): (
                    l.departure_delay_min,
                    l.late_5min,
                    l.dominant_cause_family,
                )
                for l in compute_labels(ws)
            }
        self.assertTrue(targets[15])
        self.assertEqual(targets[15], targets[30])


if __name__ == "__main__":
    unittest.main()
