"""TimeNet connector for ``error404/db-trip-delay``: German rail trip delay from the public DB scrape.

``download`` fetches the processed monthly parquet files from Hugging Face into the cache,
skipping files already there. ``convert`` runs the trip example builder over them and writes
one TimeF record per example. Connectors take no constructor arguments, so the months and the
example scale come from environment variables.
"""

from __future__ import annotations

import os
import sys
import tempfile
import urllib.request
from pathlib import Path

import pandas as pd
from timenet.connectors import BaseConnector
from timenet.dataset import TimeFDataset

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import build  # noqa: E402
import timef_export  # noqa: E402

URL = "https://huggingface.co/datasets/piebro/deutsche-bahn-data/resolve/main/monthly_processed_data/data-{}.parquet"
DEFAULT_MONTHS = "2025-11,2025-12,2026-01,2026-02,2026-03,2026-04,2026-05,2026-06,2026-07,2026-08"


class DbTripDelayConnector(BaseConnector[Path]):
    """Monthly scrape files in, one record per (run, target stop, prediction moment) out."""

    def download(self, cache_dir: Path) -> list[Path]:
        """Fetch each month once; a partial download is written aside and renamed when complete.

        Args:
            cache_dir: Where the monthly files live.

        Returns:
            The local paths, in month order.
        """
        months = os.environ.get("DB_TRIP_MONTHS", DEFAULT_MONTHS).split(",")
        paths = []
        for month in months:
            path = Path(cache_dir) / f"data-{month}.parquet"
            if not path.exists():
                part = path.with_suffix(".part")
                urllib.request.urlretrieve(URL.format(month), part)
                part.rename(path)
            paths.append(path)
        return paths

    def convert(self, raw_refs: list[Path]) -> TimeFDataset:
        """Build the examples with :mod:`build` and convert them with :mod:`timef_export`.

        Args:
            raw_refs: Monthly parquet files from :meth:`download`.

        Returns:
            The dataset, one record per example.
        """
        scale = float(os.environ.get("DB_TRIP_SCALE", "1.0"))
        base = build.Config(files=tuple(str(p) for p in raw_refs))
        cfg = build.Config(files=base.files,
                           examples_per_class={k: int(v * scale) for k, v in base.examples_per_class.items()})
        with tempfile.TemporaryDirectory() as tmp:
            table = build.build(cfg, Path(tmp) / "examples.parquet")
        frame: pd.DataFrame = table.to_pandas()
        return timef_export.to_timef(frame, self.metadata())


CONNECTOR = DbTripDelayConnector
