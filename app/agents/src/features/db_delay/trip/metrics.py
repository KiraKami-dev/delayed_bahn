"""One evaluation for every model: delay quantiles, P(late), P(cancelled).

Models hand over 19 quantiles of the arrival delay given the train runs, a
probability of cancellation and, optionally, a probability of arriving at least
six minutes late. CRPS is approximated from the quantiles with the pinball loss,
so a quantile regressor and a full distribution are scored the same way.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

LEVELS = np.round(np.arange(0.05, 1.0, 0.05), 2)
MEDIAN = int(np.argmin(np.abs(LEVELS - 0.5)))
LOW = int(np.argmin(np.abs(LEVELS - 0.1)))
HIGH = int(np.argmin(np.abs(LEVELS - 0.9)))
LATE_MINUTES = 6
LEAD_BINS = [-np.inf, 15, 30, 60, 120, np.inf]
LEAD_LABELS = ["lead <=15 min", "lead 15-30 min", "lead 30-60 min", "lead 60-120 min", "lead >120 min"]
CLIP = 1e-4


def quantiles_from_distribution(probs: np.ndarray) -> np.ndarray:
    """Quantiles at :data:`LEVELS` of discrete distributions over minutes 0..K-1."""
    cdf = np.cumsum(probs, axis=1)
    cdf = cdf / cdf[:, -1:]
    # The tolerance keeps float round-off in the running sum from skipping a minute.
    idx = np.stack([(cdf < level - 1e-9).sum(axis=1) for level in LEVELS], axis=1)
    return np.minimum(idx, probs.shape[1] - 1).astype(np.float64)


def late_from_distribution(probs: np.ndarray) -> np.ndarray:
    """P(delay >= 6) of discrete distributions over minutes."""
    return probs[:, LATE_MINUTES:].sum(axis=1) / probs.sum(axis=1)


def late_from_quantiles(quantiles: np.ndarray) -> np.ndarray:
    """P(delay >= 6) read off the quantile function, to 0.05 resolution.

    If k levels lie below six minutes the CDF at six sits between the k-th and
    (k+1)-th level; take the midpoint.
    """
    below = (quantiles < LATE_MINUTES).sum(axis=1)
    cdf = np.clip(below * 0.05 + 0.025, 0.0, 1.0)
    return 1.0 - cdf


def crps_from_quantiles(y: np.ndarray, quantiles: np.ndarray) -> np.ndarray:
    """Per-example CRPS approximated as twice the mean pinball loss over the levels."""
    diff = y[:, None] - quantiles
    pinball = np.maximum(LEVELS * diff, (LEVELS - 1) * diff)
    return 2.0 * pinball.mean(axis=1)


def summarize(y: np.ndarray, cancelled: np.ndarray, quantiles: np.ndarray, p_cancel: np.ndarray,
              p_late: np.ndarray) -> dict:
    """All metrics for one group of examples."""
    runs = ~cancelled
    out: dict = {"n": int(len(y)), "cancel_rate": float(cancelled.mean()) if len(y) else float("nan")}
    if runs.any():
        yv, qv = y[runs], quantiles[runs]
        late = yv >= LATE_MINUTES
        out |= {
            "mae_median": float(np.abs(yv - qv[:, MEDIAN]).mean()),
            "crps": float(crps_from_quantiles(yv, qv).mean()),
            "coverage_10_90": float(((yv >= qv[:, LOW]) & (yv <= qv[:, HIGH])).mean()),
            "width_10_90": float((qv[:, HIGH] - qv[:, LOW]).mean()),
            "late_rate": float(late.mean()),
            "brier_late": float(((p_late[runs] - late) ** 2).mean()),
        }
    pc = np.clip(p_cancel, CLIP, 1 - CLIP)
    out |= {
        "brier_cancel": float(((pc - cancelled) ** 2).mean()),
        "log_loss_cancel": float(-(cancelled * np.log(pc) + (~cancelled) * np.log(1 - pc)).mean()),
    }
    return out


def evaluate(frame: pd.DataFrame, quantiles: np.ndarray, p_cancel: np.ndarray,
             p_late: np.ndarray | None = None) -> dict[str, dict]:
    """Metrics overall, per train class, per lead-time bucket and before departure."""
    y = np.nan_to_num(frame["target_minutes"].to_numpy(dtype=np.float64))
    cancelled = frame["cancelled"].to_numpy(dtype=bool)
    if p_late is None:
        p_late = late_from_quantiles(quantiles)
    groups: dict[str, np.ndarray] = {"overall": np.ones(len(frame), dtype=bool)}
    for cls in sorted(frame["cls"].unique()):
        groups[cls] = (frame["cls"] == cls).to_numpy()
    lead = pd.cut(frame["lead_minutes"], LEAD_BINS, labels=LEAD_LABELS)
    for label in LEAD_LABELS:
        groups[label] = (lead == label).to_numpy()
    groups["before departure"] = frame["pre_departure"].to_numpy(dtype=bool)
    return {
        name: summarize(y[mask], cancelled[mask], quantiles[mask], p_cancel[mask], p_late[mask])
        for name, mask in groups.items()
        if mask.any()
    }


def to_markdown(results: dict[str, dict[str, dict]], group: str = "overall") -> str:
    """A table with one row per model for one group."""
    columns = ["mae_median", "crps", "coverage_10_90", "width_10_90", "brier_late", "log_loss_cancel"]
    lines = ["| Model | n | " + " | ".join(columns) + " |", "|---" * (len(columns) + 2) + "|"]
    for model, groups in results.items():
        row = groups.get(group)
        if row is None:
            continue
        cells = [f"{row[c]:.3f}" if c in row else "" for c in columns]
        lines.append(f"| {model} | {row['n']} | " + " | ".join(cells) + " |")
    return "\n".join(lines)
