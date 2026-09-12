"""From per-train delay distributions to the chance that a change, and a journey, works out.

Transfer times are applied here, after the model. A change works when both trains run
and the planned buffer plus the connecting train's departure delay covers the arriving
train's delay plus the minimum transfer time. Trains are treated as independent, which
is optimistic when one disruption hits both; DB holding a connecting train is not modelled.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class TrainForecast:
    """A train's delay at one stop: P(delay = k minutes | runs) for k = 0.., and P(cancelled)."""

    probs: np.ndarray
    p_cancel: float = 0.0

    def normalised(self) -> np.ndarray:
        """The delay distribution scaled to sum to one."""
        total = float(np.sum(self.probs))
        if total <= 0:
            raise ValueError("delay distribution has no mass")
        return np.asarray(self.probs, dtype=np.float64) / total


def change_probability(arriving: TrainForecast, departing: TrainForecast, planned_buffer: float,
                       min_transfer: float) -> float:
    """P(both trains run and arrival delay - departure delay <= planned buffer - minimum transfer).

    Args:
        arriving: The incoming train's arrival delay at the change station.
        departing: The connecting train's departure delay at the change station.
        planned_buffer: Minutes between planned arrival and planned departure.
        min_transfer: Minutes needed to change, e.g. from RIS::Stations connecting times.
    """
    a, d = arriving.normalised(), departing.normalised()
    # Distribution of (arrival delay - departure delay): convolve with the reversed departure pmf.
    diff = np.convolve(a, d[::-1])
    offsets = np.arange(diff.size) - (d.size - 1)
    slack = np.floor(planned_buffer - min_transfer)
    p_made = float(diff[offsets <= slack].sum())
    return (1 - arriving.p_cancel) * (1 - departing.p_cancel) * p_made


def journey_probability(changes: list[tuple[TrainForecast, TrainForecast, float, float]],
                        final_arrival: TrainForecast | None = None, arrival_slack: float | None = None) -> dict:
    """Chain the changes of a journey into one success probability.

    Each change is ``(arriving, departing, planned_buffer, min_transfer)``. Changes are
    multiplied as if independent. A connecting train's departure delay and its later
    arrival delay are correlated, so this is an approximation that ignores that link.

    Args:
        changes: The journey's changes in order.
        final_arrival: The last train's arrival delay at the destination, if a deadline matters.
        arrival_slack: Minutes of lateness at the destination the traveller can absorb.

    Returns:
        Per-change probabilities and the probability that the whole plan works.
    """
    per_change = [change_probability(*change) for change in changes]
    success = float(np.prod(per_change)) if per_change else 1.0
    if final_arrival is not None and arrival_slack is not None:
        pmf = final_arrival.normalised()
        on_time = float(pmf[: int(np.floor(arrival_slack)) + 1].sum())
        success *= (1 - final_arrival.p_cancel) * on_time
    return {"change_probabilities": per_change, "plan_success": success, "plan_fail": 1 - success}


def point(minutes: int, size: int = 1000, p_cancel: float = 0.0) -> TrainForecast:
    """A forecast certain of one delay, handy for tests and fixed timetables."""
    probs = np.zeros(size)
    probs[minutes] = 1.0
    return TrainForecast(probs, p_cancel)
