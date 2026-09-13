"""Timeline profiles: how much history one training sample sees.

**This module is a frozen contract.** Everything downstream reads it and nothing
else knows about timescale, so a profile is a config object rather than a code
path. Adding a fifth profile is a tuple literal, not a branch.

Delay causes live at different timescales -- rush hour is daily, construction is
monthly, weather is seasonal -- so the pipeline emits sibling datasets that
differ *only* in how much history precedes the anchor, and held-out cells pick
the winner. Same anchors, same labels, same splits, same tasks, same seed.

Two constraints set the ladder, and they are not the same constraint:

* **The hard cap.** OpenTSLM refuses a series longer than 4096 samples
  (1024 patches x patch_size 4) -- it raises rather than truncating. Hourly
  therefore tops out at 170 days.
* **Timetable churn, which bites first.** Germany's Fahrplanwechsel is every
  December; construction schedules shift; demand moved with the Deutschlandticket.
  A 364-day window straddles a timetable change and so partly describes a network
  that no longer exists. 60-180 days is the band where history is still about
  *this* network.

Every ``n_steps`` below is divisible by 4, so no series is ever right-zero-padded.
That matters more than it sounds: OpenTSLM pads to a multiple of the patch size
and carries **no padding mask**, so padding is indistinguishable from data.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

# The six canonical signals. Every profile draws from this set; a layer picks a
# subset. Names are stable -- they become the ``signal`` on a TimeNet TimeSeries
# and the key of the caption annotation the bridge reads.
SIGNALS: tuple[str, ...] = (
    "service_delay",  # mean delay of this service group across its stops
    "station_delay",  # mean delay of all trains at this station (congestion)
    "station_cancel_rate",  # cancellation rate at this station
    "service_at_station_delay",  # this service AT this station -- the specific habit
    "station_throughput",  # stop-event count at this station
    "service_throughput",  # stop-event count for this service group network-wide
    "works_share",  # share of attributed delay minutes from the `works` family
)

# Cause-family shares carried only at the coarser layers. At 7 days they are too
# sparse to be anything but noise; at 60+ they are how a regime shift becomes
# visible, which is the whole point of the long profiles.
CAUSE_SIGNALS: tuple[str, ...] = (
    "weather_share",
    "technical_share",
    "knock_on_share",
    "attributed_share",
)

_SECONDS = {"1 hour": 3600, "6 hours": 21600, "1 day": 86400}

# OpenTSLM's encoder positional table is 1024 patches at patch_size 4.
MAX_SAMPLES = 4096
PATCH_SIZE = 4


@dataclass(frozen=True)
class Layer:
    """One (bucket, span) view of history, and the signals drawn at that scale."""

    layer_id: str  # "week" | "quarter" | "season"
    bucket: str  # a DuckDB INTERVAL literal, key of _SECONDS
    n_steps: int
    signals: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.bucket not in _SECONDS:
            raise ValueError(f"unknown bucket {self.bucket!r}; expected one of {sorted(_SECONDS)}")
        if self.n_steps % PATCH_SIZE:
            raise ValueError(
                f"{self.layer_id}: n_steps={self.n_steps} is not divisible by {PATCH_SIZE}, so the "
                f"collate would right-zero-pad it -- and there is no padding mask to tell the "
                f"encoder which values are real"
            )
        if not 0 < self.n_steps <= MAX_SAMPLES:
            raise ValueError(
                f"{self.layer_id}: n_steps={self.n_steps} exceeds OpenTSLM's {MAX_SAMPLES}-sample "
                f"cap, which raises rather than truncating"
            )
        unknown = set(self.signals) - set(SIGNALS) - set(CAUSE_SIGNALS)
        if unknown:
            raise ValueError(f"{self.layer_id}: unknown signals {sorted(unknown)}")

    def with_signals(self, signals: tuple[str, ...]) -> "Layer":
        """A trimmed copy of this layer.

        Standalone M and L can afford the full cause set, because series count
        does not compound. Inside XM it does -- three layers of seven is 21
        series, past the 1-12 range the paper works in -- so XM uses trimmed
        coarse layers. Same buckets, same spans, fewer channels.
        """
        return Layer(self.layer_id, self.bucket, self.n_steps, signals)

    @property
    def bucket_seconds(self) -> int:
        return _SECONDS[self.bucket]

    @property
    def rate_hz(self) -> Fraction:
        """Sampling rate as an exact Fraction.

        TimeNet's ``RegularAxis.from_rate_hz`` refuses floats on purpose: 29.97
        is 2997/100 by its spelling and 30000/1001 by its intent, and the two
        drift apart. Ours are exact either way, but the type is the contract.
        """
        return Fraction(1, self.bucket_seconds)

    @property
    def span_days(self) -> float:
        return self.n_steps * self.bucket_seconds / 86400.0

    @property
    def n_patches(self) -> int:
        return self.n_steps // PATCH_SIZE


# 7 days at hourly: the operational week. Daily and weekly rush-hour cycle.
# Index i has hour-of-day i mod 24, so the model gets that alignment for free.
# `service_at_station_delay` is deliberately absent here. One service calling at
# one station appears a handful of times a day, so at hourly resolution it is
# ~93% empty by construction -- measured median imputation 0.42 even counting
# only service hours. That is a fact about the timetable, not a data gap, and no
# amount of imputation makes 12 observations into 168. The channel is dense at
# 6-hourly and daily, so it lives at those layers instead.
WEEK = Layer(
    layer_id="week",
    bucket="1 hour",
    n_steps=168,  # 42 patches
    signals=tuple(x for x in SIGNALS if x != "service_at_station_delay") + ("attributed_share",),
)

# 60 days at 6-hourly: the regime layer. Construction that appeared last month
# and was absent the quarter before is visible here and nowhere shorter.
QUARTER = Layer(
    layer_id="quarter",
    bucket="6 hours",
    n_steps=240,  # 60 patches
    signals=(
        "service_delay",
        "station_delay",
        "service_at_station_delay",
        "station_throughput",
        "service_throughput",
        "works_share",
    )
    + CAUSE_SIGNALS,
)

# 120 days at daily: the seasonal / structural layer.
#
# Sized by data coverage, not by preference. piebro carries all stations only
# from 2025-11-02, and pinning the observation basis any earlier collapses the
# universe to the ~100 busiest nationally -- which drops most of the Munich
# S-Bahn. Taking the expansion as the start gives 10.3 months, and every day of
# context is a day of anchors given up:
#
#     context 180d -> 4.1 months of anchors   (too thin to cross a season)
#     context 120d -> 6.1 months of anchors   <- chosen
#     context  60d -> 8.1 months of anchors
#
# 120 days still holds four months of regime history, twice QUARTER's span, and
# it is the honest ceiling rather than a design target. Raise it the moment the
# archive is deeper -- it is one integer.
SEASON = Layer(
    layer_id="season",
    bucket="1 day",
    n_steps=120,  # 30 patches
    signals=(
        "service_delay",
        "station_delay",
        "service_at_station_delay",
        "station_throughput",
        "service_throughput",
        "works_share",
    )
    + CAUSE_SIGNALS,
)


@dataclass(frozen=True)
class TimelineProfile:
    """One dataset variant. ``build.py`` iterates layers x signals; nothing else
    in the pipeline knows a timescale exists."""

    profile_id: str
    dataset_id: str  # TimeNet org/name
    layers: tuple[Layer, ...]

    def __post_init__(self) -> None:
        if not self.layers:
            raise ValueError(f"{self.profile_id}: a profile needs at least one layer")
        ids = [layer.layer_id for layer in self.layers]
        if len(set(ids)) != len(ids):
            raise ValueError(f"{self.profile_id}: duplicate layer ids {ids}")

    @property
    def n_series(self) -> int:
        return sum(len(layer.signals) for layer in self.layers)

    @property
    def n_patches(self) -> int:
        """Soft-prompt token cost per sample -- the thing that drives VRAM."""
        return sum(layer.n_patches * len(layer.signals) for layer in self.layers)

    @property
    def context_days(self) -> float:
        """The longest span any layer looks back. Sets the archive requirement
        and the size of the purge at the train/test boundary."""
        return max(layer.span_days for layer in self.layers)


S = TimelineProfile("S", "error404/db-route-week", (WEEK,))
M = TimelineProfile("M", "error404/db-route-quarter", (QUARTER,))
L = TimelineProfile("L", "error404/db-route-season", (SEASON,))
# The hypothesis, with S as the null. S-vs-M-vs-L is a *substitution* test --
# does a quarter beat a week? The real question is *additivity*: does longer
# history help on top of the operational week? Only XM answers that, and it is
# free: a profile with three layers, no new code.
# At the coarse layers XM keeps only the channels a regime clause actually cites:
# the trend in this service's delay, the station's, whether works are active, and
# how much of the delay is attributable at all.
# The two count channels ride every layer of every profile. They are not there
# for the model's sake (though service frequency is a real feature): they are
# each grain's imputation denominator -- see resample.Window.service_buckets.
# Measured before they were here: 91 of 150 XM windows rejected, every one of
# them for a "gap" at a coarse layer that had no denominator to judge it by.
_XM_COARSE = (
    "service_delay",
    "station_delay",
    "station_throughput",
    "service_throughput",
    "works_share",
    "attributed_share",
)
XM = TimelineProfile(
    "XM",
    "error404/db-route-multiscale",
    (WEEK, QUARTER.with_signals(_XM_COARSE), SEASON.with_signals(_XM_COARSE)),
)

PROFILES: dict[str, TimelineProfile] = {p.profile_id: p for p in (S, M, L, XM)}

# Horizon is profile-independent by design: the label is computed from the 7 days
# following the anchor, never from the context. That is what makes the bake-off a
# controlled comparison -- same labels, only the history differs.
HORIZON_DAYS = 7
# Anchors step by one horizon, so no two records share a label observation.
ANCHOR_STRIDE_DAYS = 7
# Recency: an anchor this old is drawn half as often. Orthogonal to context
# length -- this is which travel dates we train on, not how far back each looks.
RECENCY_HALF_LIFE_DAYS = 90


def profile(profile_id: str) -> TimelineProfile:
    try:
        return PROFILES[profile_id]
    except KeyError:
        raise ValueError(
            f"unknown profile {profile_id!r}; expected one of {sorted(PROFILES)}"
        ) from None


def required_archive_days(prof: TimelineProfile, anchor_span_days: float) -> float:
    """Calendar the build needs: context + anchors + horizon.

    For XM over a 12-month anchor span this is ~18.4 months, and the driver is
    the anchor span, not the sample count -- we need a full seasonal cycle of
    travel dates including one December timetable change.
    """
    return prof.context_days + anchor_span_days + HORIZON_DAYS
