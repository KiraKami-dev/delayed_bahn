"""Checks for change and journey probabilities."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from connection import TrainForecast, change_probability, journey_probability, point  # noqa: E402


class ConnectionTest(unittest.TestCase):
    """Known cases and a Monte Carlo cross-check."""

    def test_point_masses(self) -> None:
        """Eight minutes of buffer, four to change: five late fails, three late works, a late connection helps."""
        self.assertEqual(change_probability(point(5), point(0), 8, 4), 0.0)
        self.assertEqual(change_probability(point(3), point(0), 8, 4), 1.0)
        self.assertEqual(change_probability(point(5), point(2), 8, 4), 1.0)
        self.assertEqual(change_probability(point(4), point(0), 8, 4), 1.0)

    def test_cancellations_multiply(self) -> None:
        """A sure change becomes as likely as both trains running."""
        p = change_probability(point(0, p_cancel=0.1), point(0, p_cancel=0.2), 8, 4)
        self.assertAlmostEqual(p, 0.9 * 0.8)

    def test_matches_monte_carlo(self) -> None:
        """Geometric-ish delays on both sides agree with sampling."""
        rng = np.random.default_rng(0)
        k = np.arange(200)
        a = TrainForecast(np.exp(-k / 6.0))
        d = TrainForecast(np.exp(-k / 3.0))
        exact = change_probability(a, d, planned_buffer=7, min_transfer=3)
        sa = rng.choice(k, size=400_000, p=a.normalised())
        sd = rng.choice(k, size=400_000, p=d.normalised())
        self.assertAlmostEqual(exact, float(np.mean(sa - sd <= 4)), places=2)

    def test_journey_chains_changes_and_deadline(self) -> None:
        """Two sure changes and a destination slack that half the outcomes meet."""
        final = TrainForecast(np.array([0.5, 0.0, 0.0, 0.5]))
        result = journey_probability([(point(1), point(0), 6, 3), (point(2), point(0), 6, 3)], final, arrival_slack=2)
        self.assertEqual(result["change_probabilities"], [1.0, 1.0])
        self.assertAlmostEqual(result["plan_success"], 0.5)
        self.assertAlmostEqual(result["plan_fail"], 0.5)


if __name__ == "__main__":
    unittest.main()
