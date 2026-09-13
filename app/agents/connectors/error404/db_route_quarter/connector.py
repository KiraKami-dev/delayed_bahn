"""error404/db-route-quarter: profile M (6h x 60d). The body is shared; see ../db_route/pipeline.py."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from timenet.connectors import BaseConnector
from timenet.dataset import TimeFDataset


class DbRouteQuarter(BaseConnector[Any]):
    PROFILE = "M"

    def download(self, cache_dir: Path) -> list[Any]:
        from timenet_connectors.datasets.error404.db_route import pipeline  # noqa: PLC0415

        return pipeline.download(cache_dir)

    def convert(self, raw_refs: list[Any]) -> TimeFDataset:
        from timenet_connectors.datasets.error404.db_route import pipeline  # noqa: PLC0415

        return pipeline.convert(raw_refs, pipeline.P.PROFILES[self.PROFILE], self.metadata())


CONNECTOR = DbRouteQuarter
