"""Pytest fixtures for the bridge and validator suites.

The callables live in ``bridge_fixtures.py`` so test modules can import them by
name regardless of which subset of the suite a given run collects.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bridge_fixtures import TINY, add_sample, make_dataset  # noqa: E402


@pytest.fixture
def dataset():
    """A three-record dataset, one per split. The happy path everything else perturbs."""
    ds = make_dataset()
    add_sample(ds, "r-train", split="train", anchor="2026-06-01", target="minor")
    add_sample(ds, "r-val", split="validation", anchor="2026-06-08", target="on_time")
    add_sample(ds, "r-test", split="test", anchor="2026-06-15", target="major")
    return ds


@pytest.fixture
def profile():
    return TINY
