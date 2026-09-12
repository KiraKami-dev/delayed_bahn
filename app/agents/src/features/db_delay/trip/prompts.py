"""Turn a trip example into an OpenTSLM sample: text, four series and the answer.

The rationale is written from the inputs alone and never mentions the target,
so teacher-forcing it at evaluation leaks nothing and the minute distribution
read after it is not anchored on a number the model already committed to.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

CANCELLED = "cancelled"
MIN_STD = 1e-6
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
HISTORY_SUBJECT = {"pattern": "this service", "route": "trains on this route", "type": None, "none": None}


def as_list(values) -> list:
    """A parquet list cell as a Python list; missing cells become empty."""
    if values is None or (isinstance(values, float) and np.isnan(values)):
        return []
    return list(values)


def name(value) -> str:
    """A station name, or a neutral placeholder where the scrape lost it."""
    return value if isinstance(value, str) and value else "an unnamed station"


def train_label(row: pd.Series) -> str:
    """How the traveller sees the train: line for regional services, category and number otherwise."""
    number = row["train_number"] if isinstance(row["train_number"], str) else ""
    service = f"{row['train_type']} {number}".strip()
    line = row.get("line_number")
    if row["cls"] != "long-distance" and isinstance(line, str) and line:
        return f"{line} ({service})"
    return service


def normalised(values, label: str, unit: str) -> tuple[str, list[float]]:
    """Z-normalise a series and state its mean and spread, as OpenTSLM's own datasets do."""
    series = np.asarray(values, dtype=np.float64)
    mean = float(series.mean())
    std = max(float(series.std()), MIN_STD)
    return f"{label}, in {unit}, mean {mean:.2f} and std {std:.2f}:", ((series - mean) / std).tolist()


def pct(share: float) -> str:
    """A share as a whole percentage."""
    return f"{100 * share:.0f}%"


def rationale(row: pd.Series) -> str:
    """Facts read off the inputs, in the order a dispatcher would weigh them."""
    stop = name(row["k_station"])
    stops = int(row["stops_ahead"])
    lead = float(row["lead_minutes"])
    # Lead time counts to the planned arrival, which a late train may already have passed.
    due = f"planned to arrive in {lead:.0f} minutes" if lead >= 1 else f"its planned arrival was {abs(lead):.0f} minutes ago"
    parts = []
    if row["pre_departure"]:
        parts.append(f"The train has not departed yet; {stop} is {stops} stops away, {due}.")
    else:
        parts.append(f"The train left {name(row['j_station'])} {row['current_delay']:.0f} minutes late; "
                     f"{stop} is {stops} stops ahead, {due}.")
        delays = as_list(row["run_delays"])
        if len(delays) >= 2:
            change = row["delay_change_3"]
            trend = "grown" if change > 1 else "shrunk" if change < -1 else "held steady"
            parts.append(f"Over the last stops the delay has {trend}, from {delays[max(0, len(delays) - 4)]:.0f} "
                         f"to {delays[-1]:.0f} minutes; the most so far was {row['max_delay_so_far']:.0f}.")
    subject = HISTORY_SUBJECT[row["hist_level"]] or (f"{row['train_type']} trains" if row["hist_level"] == "type" else None)
    if subject:
        parts.append(f"In the last 30 days {subject} reached {stop} with a median delay of {row['hist_median']:.0f} "
                     f"minutes (90th percentile {row['hist_p90']:.0f}) and {pct(row['hist_cancel_share'])} cancelled.")
    else:
        parts.append(f"There is too little recent history at {stop} to lean on.")
    if subject and "hist_median_long" in row and int(row["hist_window_days"]) > 30:
        # Longer and shorter scales of the same history, so the model can weigh trend against base rate.
        parts.append(f"Over {int(row['hist_window_days'])} days the median was {row['hist_median_long']:.0f} minutes "
                     f"(90th percentile {row['hist_p90_long']:.0f}); over the last 7 days it was {row['hist_median_7']:.0f}.")
    if "station_late_same_hour" in row and len(row["station_series"]) >= 168:
        parts.append(f"At this time of day, {pct(row['station_late_same_hour'])} of stops at {stop} ran late over the "
                     f"last {len(row['station_series']) // 24} days, {pct(row['network_late_same_hour'])} nationwide.")
    parts.append(f"At {stop}, {pct(row['station_late_3h'])} of stops ran at least 6 minutes late in the last "
                 f"3 hours, against {pct(row['station_late_72h'])} over 3 days.")
    parts.append(f"Nationwide, {pct(row['network_late_3h'])} of {row['cls']} stops were late in the last 3 hours, "
                 f"against {pct(row['network_late_72h'])} over 3 days.")
    return " ".join(parts)


def target_text(row: pd.Series) -> str:
    """The answer token: whole minutes, or cancelled."""
    return CANCELLED if row["cancelled"] else str(int(row["target_minutes"]))


def as_text(values: np.ndarray) -> str:
    """Numbers written into the prompt for the text-only baseline, rounded to whole units."""
    return ", ".join(f"{value:.0f}" for value in values)


MODES = ("series", "text", "both")
TEXT_HOURS = 72  # the prompt never carries more than this many hourly values; the encoder gets them all
TEXT_DAYS = 30  # likewise for the daily route history


def sample(row: pd.Series, text_only: bool = False, mode: str = "series") -> dict:
    """One OpenTSLM sample, plus the answer prefix used to read out the distribution.

    ``mode`` decides how the four series reach the model: through the time-series encoder
    (``series``), written into the prompt as numbers with no encoder (``text``, the baseline;
    ``text_only`` is the same), or both at once (``both``).
    """
    if text_only:
        mode = "text"
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
    arrival = pd.Timestamp(row["k_arr_pt"])
    via = [v for v in as_list(row["via"]) if isinstance(v, str) and v]
    stop = name(row["k_station"])
    via_text = f" via {', '.join(via[:5])}{' and further stops' if len(via) > 5 else ''}" if via else ""
    where = (f"It has not departed from {name(row['first_station'])} yet." if row["pre_departure"]
             else f"It has just left {name(row['j_station'])}.")
    pre_prompt = (
        f"You predict how late a German train will arrive, for a traveller. Train {train_label(row)} from "
        f"{name(row['origin'])} to {name(row['dest'])}. {where} Target stop: {stop}{via_text}, planned arrival "
        f"{WEEKDAYS[arrival.weekday()]} {arrival:%H:%M}."
    )
    run = as_list(row["run_delays"])
    raw = [
        ("Departure delay at each stop so far" if run else "No departures yet", run or [0.0], "minutes"),
        (f"Daily median arrival delay at {stop}, last {len(row['hist_series'])} days", row["hist_series"], "minutes"),
        (f"Hourly share of late stops at {stop}, last {len(row['station_series'])} hours", row["station_series"], "share"),
        (f"Hourly share of late {row['cls']} stops nationwide, last {len(row['network_series'])} hours",
         row["network_series"], "share"),
    ]
    if mode in ("text", "both"):
        # The same numbers written into the prompt; in ``text`` no time-series encoder is involved.
        lines = []
        for label, values, unit in raw:
            values = np.asarray(values, dtype=np.float64)
            if unit == "share" and len(values) > TEXT_HOURS:  # long hourly series: the text gets the recent end
                values = values[-TEXT_HOURS:]
                label = label.rsplit(", last ", 1)[0] + f", last {TEXT_HOURS} hours"
            elif "Daily median" in label and len(values) > TEXT_DAYS:
                values = values[-TEXT_DAYS:]
                label = label.rsplit(", last ", 1)[0] + f", last {TEXT_DAYS} days"
            lines.append(f"{label}, in {'percent' if unit == 'share' else unit}: "
                         f"{as_text(values * (100 if unit == 'share' else 1))}")
        pre_prompt = pre_prompt + "\n" + "\n".join(lines)
    series = [] if mode == "text" else [normalised(values, label, unit) for label, values, unit in raw]
    post_prompt = (f"How many minutes late will the train arrive at {stop}? Reason from the data, "
                   f"then answer with whole minutes or {CANCELLED}.\nRationale:")
    reasoning = rationale(row)
    return {
        "pre_prompt": pre_prompt,
        "time_series_text": [text for text, _ in series],
        "time_series": [values for _, values in series],
        "post_prompt": post_prompt,
        "answer": f"{reasoning} Answer: {target_text(row)}",
        "prefix": f"{reasoning} Answer:",
        "example_id": int(row["example_id"]),
    }
