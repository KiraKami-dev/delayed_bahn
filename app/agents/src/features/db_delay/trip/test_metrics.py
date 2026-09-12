"""Sanity checks for the shared metrics."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

import metrics  # noqa: E402


class MetricsTest(unittest.TestCase):
    """Quantiles, CRPS and P(late) behave as expected on known distributions."""

    def test_point_mass_has_zero_crps_and_exact_quantiles(self) -> None:
        """A distribution concentrated on the truth scores perfectly."""
        probs = np.zeros((1, 1000))
        probs[0, 8] = 1.0
        q = metrics.quantiles_from_distribution(probs)
        self.assertTrue((q == 8).all())
        self.assertAlmostEqual(float(metrics.crps_from_quantiles(np.array([8.0]), q)[0]), 0.0)
        self.assertEqual(float(metrics.late_from_distribution(probs)[0]), 1.0)

    def test_crps_grows_with_distance(self) -> None:
        """Mass one minute off costs less than mass fifty minutes off."""
        near = np.full((1, len(metrics.LEVELS)), 9.0)
        far = np.full((1, len(metrics.LEVELS)), 58.0)
        y = np.array([8.0])
        self.assertLess(metrics.crps_from_quantiles(y, near)[0], metrics.crps_from_quantiles(y, far)[0])

    def test_uniform_quantiles_and_late_share(self) -> None:
        """Uniform over 0..19: median 9, P(late) 0.7 exactly and about 0.7 from quantiles."""
        probs = np.zeros((1, 1000))
        probs[0, :20] = 1 / 20
        q = metrics.quantiles_from_distribution(probs)
        self.assertEqual(q[0, metrics.MEDIAN], 9.0)
        self.assertAlmostEqual(float(metrics.late_from_distribution(probs)[0]), 0.7)
        self.assertLess(abs(float(metrics.late_from_quantiles(q)[0]) - 0.7), 0.05)


if __name__ == "__main__":
    unittest.main()
