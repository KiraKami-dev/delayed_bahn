"""Turn the hourly station table into fixed windows with deterministic targets.

The unit of analysis is one station's hourly delay curve, not one train run: a
run visits too few stops, too irregularly, for a patch encoder to beat a plain
text baseline. Every target here is computed from the horizon by a function,
never written by hand, so the labels stay objective.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

CONTEXT_HOURS = 168  # one week
HORIZON_HOURS = 24
STRIDE_HOURS = 24
FORECAST_HOURS = 6
MAX_IMPUTED_FRACTION = 0.10

CHANNELS = ("mean_delay", "cancel_rate", "trains")


@dataclass(frozen=True)
class Window:
    """One context window plus the targets derived from the horizon after it."""

    station: str
    start_index: int
    context: dict[str, np.ndarray]
    horizon_delay: np.ndarray
    imputed_fraction: float
    next_6h_mean_delay: float
    worse_than_context: bool
    peak_hour_of_next_day: int
    context_mean_delay: float
    horizon_mean_delay: float
    hour_of_day_at_start: int


def impute(values: np.ndarray, present: np.ndarray, fill: str) -> np.ndarray:
    """Fill gaps on a complete hourly grid.

    Args:
        values: The grid values, with arbitrary content where ``present`` is False.
        present: True where the hour carried at least one train.
        fill: ``"interpolate"`` for a rate-like channel, ``"zero"`` for a count.

    Returns:
        A float64 array with no gaps.
    """
    out = np.asarray(values, dtype=np.float64).copy()
    if present.all():
        return out
    if fill == "zero":
        out[~present] = 0.0
        return out
    index = np.arange(out.size, dtype=np.float64)
    out[~present] = np.interp(index[~present], index[present], out[present])
    return out


def build_windows(station: str, grid: dict[str, np.ndarray], present: np.ndarray) -> list[Window]:
    """Slide a context/horizon pair across one station's month.

    Args:
        station: The station name, used as the record's subject.
        grid: One complete-grid array per channel in :data:`CHANNELS`.
        present: True where the hour carried at least one train.

    Returns:
        Every window whose imputed fraction stays under the cap.
    """
    total = present.size
    span = CONTEXT_HOURS + HORIZON_HOURS
    windows: list[Window] = []
    for start in range(0, total - span + 1, STRIDE_HOURS):
        ctx = slice(start, start + CONTEXT_HOURS)
        hor = slice(start + CONTEXT_HOURS, start + span)
        imputed = 1.0 - float(present[start : start + span].mean())
        if imputed > MAX_IMPUTED_FRACTION:
            continue
        delay = grid["mean_delay"]
        context_mean = float(delay[ctx].mean())
        horizon_mean = float(delay[hor].mean())
        horizon_delay = delay[hor]
        windows.append(
            Window(
                station=station,
                start_index=start,
                context={name: grid[name][ctx] for name in CHANNELS},
                horizon_delay=horizon_delay,
                imputed_fraction=imputed,
                next_6h_mean_delay=float(horizon_delay[:FORECAST_HOURS].mean()),
                worse_than_context=horizon_mean > context_mean,
                peak_hour_of_next_day=int((start + CONTEXT_HOURS + int(horizon_delay.argmax())) % 24),
                context_mean_delay=context_mean,
                horizon_mean_delay=horizon_mean,
                hour_of_day_at_start=start % 24,
            )
        )
    return windows


def rationale_for_forecast(window: Window) -> str:
    """Write the chain of thought for the six-hour forecast.

    The reasoning is anchored on what the same hours of day did across the
    context week, and the closing clause is derived from the target itself, so
    the rationale can never contradict the answer it precedes.
    """
    delay = window.context["mean_delay"]
    hour_of_day = (window.start_index + np.arange(delay.size)) % 24
    first_horizon_hour = (window.start_index + CONTEXT_HOURS) % 24
    horizon_hours = {(first_horizon_hour + offset) % 24 for offset in range(FORECAST_HOURS)}
    seasonal = float(np.mean([delay[hour_of_day == hour].mean() for hour in sorted(horizon_hours)]))
    target = window.next_6h_mean_delay
    if target > seasonal * 1.15:
        relation = "above"
    elif target < seasonal * 0.85:
        relation = "below"
    else:
        relation = "close to"
    return (
        f"Over the past week this station averaged {window.context_mean_delay:.1f} minutes of delay. "
        f"At the same hours of day it averaged {seasonal:.1f} minutes. "
        f"The window ends at {first_horizon_hour:02d}:00, and the six hours that follow "
        f"come in {relation} that seasonal level."
    )


def rationale_for_comparison(window: Window) -> str:
    """Write the chain of thought for the better-or-worse call."""
    direction = "above" if window.worse_than_context else "at or below"
    return (
        f"The weekly baseline is {window.context_mean_delay:.1f} minutes. "
        f"The coming day runs {direction} it, averaging {window.horizon_mean_delay:.1f} minutes."
    )


def rationale_for_peak(window: Window, horizon_delay: np.ndarray) -> str:
    """Write the chain of thought for the peak-hour call from the horizon itself.

    The sentence must not assert a shape the data does not show, so the wording
    is chosen from the measured spread rather than fixed in advance.
    """
    peak = float(horizon_delay.max())
    typical = float(np.median(horizon_delay))
    sharpness = "a clear spike above" if peak > 2 * max(typical, 0.1) else "a mild rise over"
    return (
        f"Across the coming day delay runs around {typical:.1f} minutes typically, with "
        f"{sharpness} that at {peak:.1f} minutes. That maximum falls at "
        f"{window.peak_hour_of_next_day:02d}:00."
    )
