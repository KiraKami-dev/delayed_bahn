"""The one re-bucketing path. Every profile goes through it; nothing branches.

`profiles.py` says a timescale is a config object rather than a code path. This
module is where that claim is either true or a lie. Three (four with XM) profiles
read the same hourly fact cache, and the only thing that differs between them is
the `Layer` passed in: its `bucket` becomes the INTERVAL in one SQL template and
its `n_steps` becomes the length of the slice. There is no `if bucket == ...`
anywhere below, and adding a fifth profile must not add one.

What it produces: for a `(entity, anchor, TimelineProfile)` triple, one float32
array of exactly `layer.n_steps` values per `(layer_id, signal)`, ending at the
anchor, plus the `present` mask that says which of those values were observed
rather than filled.

Three things it has to get right, in order of how badly they bite.

**Sums, never means.** `facts.py` stores `sum_delay` and `n_obs` separately for
exactly this module's benefit: a 6-hour bucket is `sum(sum_delay)/sum(n_obs)`,
not the mean of six hourly means. The difference is not cosmetic. An hour with 4
trains averaging 20 min and an hour with 400 averaging 2 min give 11.0 as a mean
of means and 2.18 as the true mean -- a 5x error, biased towards whatever
happened when nothing was running. `TestUnbiasedRebucketing` is the test
this module exists to pass.

**Phase.** Every layer ends at the same anchor `t0` = 00:00 local on the travel
day, and buckets are aligned to a midnight origin, so index `i` of the week layer
always has hour-of-day `i mod 24` and index `i` of the quarter layer always has
6h-block `i mod 4`. The model gets the daily cycle as a positional fact instead
of having to infer it. It is free and it is only free if it is exact.

**Gaps are not zeros.** A bucket with no rows means no trains were observed, and
for a rate that is missing, not zero. Filling a 3 a.m. hole with 0.0 minutes of
delay teaches the model that the night is punctual. Rates are interpolated, the
one count channel is zero-filled, and the caller is told what fraction was made
up so it can throw the window away.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, NamedTuple, Sequence

import duckdb
import numpy as np
import pyarrow as pa

from causes import SERIES_FAMILIES
from profiles import CAUSE_SIGNALS, SIGNALS, Layer, PROFILES, TimelineProfile

DEFAULT_CACHE_DIR = Path.home() / ".cache" / "db_route"

# A window whose values are largely invented is not evidence. But the budget has
# to be per *grain*, because absence means different things at different grains.
#
# Station and line channels see trains nearly every hour, so a gap there is a
# scrape failure and a tenth is generous.
#
# A (service, station) pair is different: one service calls at one stop a few
# times a day, so most hourly buckets are legitimately empty on a perfectly
# healthy record -- measured at a quarter to a third of 168 at the week layer.
# Judging that against 0.10 rejects essentially every record, which is how a
# structural property of the timetable turns into an empty dataset. The pair
# budget is therefore set above the structural floor, leaving room to still catch
# a genuinely broken window.
MAX_IMPUTED_FRACTION: dict[str, float] = {"station": 0.10, "line": 0.10, "pair": 0.45}

# A constant series has zero standard deviation, and the downstream z-score
# divides by it. The result is NaN or inf in every position, the loss goes to
# NaN, and nothing in the stack says why -- so the check lives here, upstream of
# the normalisation, where the series still has units and a name.
DEGENERATE_STD = 1e-6

# The SQL bucket origin. NOT the anchor's midnight, and that is the whole trick:
# every anchor's t0 is a local midnight, and every bucket in `profiles._SECONDS`
# (1h, 6h, 1d) divides 24 hours, so the bucket grid seeded from *any* midnight is
# the same grid. One aggregation therefore serves all ~15,000 anchors, and a
# window is a slice instead of a query. Fixed before COVERAGE_START (2024-07-01)
# so every bucket index is non-negative.
PHASE_ORIGIN = dt.datetime(2024, 1, 1, 0, 0, 0)

# Measured, so no longer a caveat: `time` is naive **Europe/Berlin wall-clock**.
# The hour-of-day traffic curve over Munich in 2026-08 troughs at 03:00 with
# 1,998 events, ramps to 18,000 by 05:00 and peaks at 18:00 with 29,543. That is
# the German rail day in local time; under UTC (CEST, +2 in August) the trough
# would sit at 01:00 and the ramp at 03:00, and it does not. It also confirms the
# 3-hour service-day offset in sources.py lands squarely in the trough.
#
# So the grid is 24 wall-clock hours per day, and the two DST transitions a year
# show up as one doubled bucket in October and one empty bucket in March -- both
# absorbed by the gap handling below.

FACT_TABLES: dict[str, str] = {
    "station": "hourly_station",
    "line": "hourly_line",
    "pair": "hourly_pair",
}

# The grouping keys of each fact table, in the order facts.py wrote them.
GRAIN_KEYS: dict[str, tuple[str, ...]] = {
    "station": ("station",),
    "line": ("service_group",),
    "pair": ("service_group", "station"),
}


class EntityKey(NamedTuple):
    """What a record is about: one service group calling at one station.

    `entities.py` owns the real entity type. This module deliberately does not
    import it -- it needs two strings, and taking them structurally keeps the
    two modules independent. `resolve_entity` accepts an EntityKey, a
    `(service_group, station)` pair, or anything with those two attributes.
    """

    service_group: str
    station: str


@dataclass(frozen=True)
class SignalSpec:
    """How one named signal is computed from the additive fact columns.

    Every signal is a ratio of two sums, or a bare count. Keeping that as data
    rather than code is what makes the SQL template signal-agnostic: the query
    fetches columns, this table turns columns into channels.
    """

    grain: str  # key of FACT_TABLES
    numerator: str  # a facts.FACT_COLUMNS name
    denominator: str | None  # None => the numerator IS the value (a count)
    impute: str  # "linear" for rates, "zero" for counts


def _cause_share(family: str) -> SignalSpec:
    """`<family>_share` = family minutes / attributed minutes.

    The denominator is *minutes*, not events, and that choice is the difference
    between "this cause is responsible for the delay" and "this cause was
    mentioned near it". Ten stops flagged `works` that ran 40 minutes late are a
    construction regime; ten flagged `works` that ran one minute late are noise
    with the same event count. Only the minute-weighted share separates them,
    and the rationale downstream asserts responsibility.

    Station grain, not pair. The pair grain would be the more specific claim but
    it does not survive coarsening: causes.py measures 30.1% of stops carrying a
    code at all, and a (service, station) pair sees on the order of a handful of
    trains in a 6-hour bucket, so its attributed-minutes denominator is zero far
    more often than not and the "share" is mostly interpolation. The station's
    cause mix is what a works closure or a storm actually moves.
    """
    return SignalSpec("station", f"sum_delay_{family}", "sum_delay_attributed", "linear")


SIGNAL_SPECS: dict[str, SignalSpec] = {
    # mean delay over every stop this service group made in the bucket
    "service_delay": SignalSpec("line", "sum_delay", "n_obs", "linear"),
    # mean delay over every train at this station -- the congestion channel
    "station_delay": SignalSpec("station", "sum_delay", "n_obs", "linear"),
    # this service AT this station: the specific habit, and the only channel the
    # other two grains cannot express
    "service_at_station_delay": SignalSpec("pair", "sum_delay", "n_obs", "linear"),
    "station_cancel_rate": SignalSpec("station", "n_cancelled", "n_obs", "linear"),
    # the one count channel. Not a rate: an empty bucket here is a real zero.
    "station_throughput": SignalSpec("station", "n_obs", None, "zero"),
    "attributed_share": SignalSpec("station", "n_attributed", "n_obs", "linear"),
    **{f"{family}_share": _cause_share(family) for family in SERIES_FAMILIES},
}

_DECLARED = set(SIGNALS) | set(CAUSE_SIGNALS)
_MISSING = _DECLARED - set(SIGNAL_SPECS)
if _MISSING:
    raise ImportError(
        f"profiles.py declares signals with no formula here: {sorted(_MISSING)}. "
        f"profiles.py is the frozen contract, so the fix is in this module."
    )

# Columns to pull per grain: the union over every signal defined at that grain,
# so a panel is built once and serves any profile. Station carries nine of the
# twelve fact columns, line and pair two each.
GRAIN_COLUMNS: dict[str, tuple[str, ...]] = {
    grain: tuple(
        dict.fromkeys(
            col
            for spec in SIGNAL_SPECS.values()
            if spec.grain == grain
            for col in (spec.numerator, spec.denominator)
            if col is not None
        )
    )
    for grain in FACT_TABLES
}


def is_degenerate(values: np.ndarray) -> bool:
    """True if this series is flat enough that z-scoring it produces NaN.

    Checked here rather than downstream because downstream is a tensor with no
    name attached: by the time the standardiser divides by ~0 the caller cannot
    say which of fifteen channels of which of fifteen thousand records went bad.

    The realistic case is `station_cancel_rate` at the season layer, where a
    quiet station cancels nothing for 120 consecutive days and the channel is a
    line of zeros -- informative to a human, undefined to a z-score.
    """
    if values.size == 0:
        return True
    return float(np.std(values.astype(np.float64))) <= DEGENERATE_STD


def resolve_entity(entity: Any) -> EntityKey:
    """Accept whatever `entities.py` settles on, as long as it names both parts."""
    if isinstance(entity, EntityKey):
        return entity
    if isinstance(entity, tuple) and len(entity) == 2:
        return EntityKey(str(entity[0]), str(entity[1]))
    service_group = getattr(entity, "service_group", None)
    station = getattr(entity, "station", None)
    if service_group is None or station is None:
        raise TypeError(
            f"cannot read (service_group, station) off {type(entity).__name__}; pass an "
            f"EntityKey, a (service_group, station) tuple, or an object with those attributes"
        )
    return EntityKey(str(service_group), str(station))


def anchor_midnight(anchor: Any) -> dt.datetime:
    """t0 for an anchor: 00:00 local on the travel day.

    Every layer of every profile ends here, which is what makes the bake-off a
    controlled comparison -- same anchor, same label, only the history differs.

    Accepts a date, a datetime, or a record carrying one: `anchors.Anchor`
    spells the field `anchor`, so both spellings are taken rather than making
    this module and that one agree on a name they do not need to share.
    """
    if isinstance(anchor, (dt.datetime, dt.date)):
        return dt.datetime(anchor.year, anchor.month, anchor.day)
    for attribute in ("travel_date", "anchor"):
        inner = getattr(anchor, attribute, None)
        if isinstance(inner, (dt.datetime, dt.date)):
            return anchor_midnight(inner)
    raise TypeError(
        f"cannot read a travel date off {type(anchor).__name__}; pass a date, a "
        f"datetime, or an object with a `travel_date` or `anchor` date"
    )


def bucket_index(moment: dt.datetime, bucket_seconds: int) -> int:
    """Index of `moment` on the global bucket grid seeded at PHASE_ORIGIN.

    Raises unless `moment` lands exactly on a bucket boundary. That is not
    defensive noise: an anchor that is not a local midnight silently shifts the
    phase of every series in the record, the arrays still come out the right
    length, and nothing downstream can see it.
    """
    offset = int((moment - PHASE_ORIGIN).total_seconds())
    if offset % bucket_seconds:
        raise ValueError(
            f"{moment} is {offset % bucket_seconds}s off the {bucket_seconds}s bucket grid "
            f"anchored at {PHASE_ORIGIN}; phase alignment would be silently wrong"
        )
    return offset // bucket_seconds


def bucket_starts(layer: Layer, anchor: Any) -> np.ndarray:
    """The wall-clock start of each of the layer's `n_steps` buckets.

    The last entry is one bucket before t0: the context stops at the anchor and
    never includes the travel day, whose outcome is the label.
    """
    secs = layer.bucket_seconds
    end = bucket_index(anchor_midnight(anchor), secs)
    first = end - layer.n_steps
    offsets = (np.arange(layer.n_steps, dtype=np.int64) + first) * secs
    return np.datetime64(PHASE_ORIGIN, "s") + offsets.astype("timedelta64[s]")


# --- panels -----------------------------------------------------------------
# A panel is one fact table re-bucketed to one INTERVAL, held in memory and
# indexed by entity. XM carries 15 series (7 + 4 + 4) and the build is ~15,000
# records, so a query per series is ~225,000 round trips against parquet. A
# panel turns that into one aggregation per (grain, bucket) plus a searchsorted
# per series. Seven panels exist for XM, not nine: only the week layer draws the
# pair grain.
#
# Measured on a synthetic fixture sized to the real cache -- 400 stations x
# 7,400 hourly buckets (10.3 months of pinned coverage), 1,000 service groups,
# 3,683 (service, station) pairs, 17M fact rows in total, the dimensions
# facts.py reports for the Munich catchment:
#
#     build all seven panels   4.0 s     (once)
#     one XM window            0.29 ms   -> 4 s for 15,000 records
#     panels resident          0.62 GB
#
# Rows stay sparse rather than densified. Densifying the pair grain to
# 3,683 x 7,400 would allocate 27M cells to hold 3.7M real ones; sparse plus a
# searchsorted for a 168-long slice out of 7,400 is both smaller and faster.
# Column selection is per grain (GRAIN_COLUMNS): station needs nine of the twelve
# fact columns, line and pair two each, which is why the 7.4M-row hourly line
# panel costs 178 MB and the 3.0M-row station panel costs 260 MB.


@dataclass
class _Panel:
    """One (grain, bucket) aggregation: sorted rows, plus each entity's range."""

    bucket_index: np.ndarray  # int64, ascending within each entity block
    columns: dict[str, np.ndarray]  # float64, parallel to bucket_index
    groups: dict[tuple[str, ...], tuple[int, int]]  # entity key -> [start, stop)

    def rows(self, key: tuple[str, ...]) -> tuple[int, int]:
        return self.groups.get(key, (0, 0))


# The single SQL template. `bucket` and the key list are the only things that
# vary across profiles, which is the property this module is here to hold.
# CAST to DOUBLE is not cosmetic: DuckDB widens sum(BIGINT) to HUGEINT, which
# arrives in Arrow as decimal128 and does not convert to a numpy float.
_BUCKET_SQL = """
SELECT {keys},
       CAST(floor((epoch(time_bucket(INTERVAL '{bucket}', hour, TIMESTAMP '{origin}'))
                   - epoch(TIMESTAMP '{origin}')) / {secs}) AS BIGINT) AS bucket_index,
       {sums}
FROM {relation}
GROUP BY ALL
ORDER BY {keys}, bucket_index
"""


def _group_offsets(
    table: pa.Table, key_names: Sequence[str]
) -> dict[tuple[str, ...], tuple[int, int]]:
    """Row range per entity, from a table already ordered by the key columns.

    Dictionary-encoding each key column keeps this off the Python heap: the
    alternative is materialising 12M strings to compare neighbours, where this
    compares 12M int64s and only decodes the few thousand distinct keys.
    """
    n = table.num_rows
    if n == 0:
        return {}
    codes = np.zeros(n, dtype=np.int64)
    indices: list[np.ndarray] = []
    dictionaries: list[list[str]] = []
    for name in key_names:
        column = table.column(name).combine_chunks()
        if not pa.types.is_dictionary(column.type):
            column = column.dictionary_encode()
        idx = column.indices.to_numpy(zero_copy_only=False).astype(np.int64)
        indices.append(idx)
        dictionaries.append(column.dictionary.to_pylist())
        codes = codes * len(dictionaries[-1]) + idx

    change = np.flatnonzero(codes[1:] != codes[:-1]) + 1
    starts = np.concatenate(([0], change))
    stops = np.concatenate((change, [n]))
    groups = {
        tuple(dictionaries[j][indices[j][start]] for j in range(len(key_names))): (
            int(start),
            int(stop),
        )
        for start, stop in zip(starts, stops)
    }
    if len(groups) != len(starts):
        raise RuntimeError(
            "fact rows for one entity are not contiguous -- the ORDER BY in _BUCKET_SQL "
            "is what the slicing relies on"
        )
    return groups


class FactCache:
    """Hourly facts, re-bucketed on demand and held per (grain, bucket).

    Points at `~/.cache/db_route/` by default. `relations` overrides where each
    grain is read from -- the tests pass in-memory table names, which is what
    lets the invariants be checked without the 26-month extraction.
    """

    def __init__(
        self,
        cache_dir: Path | str = DEFAULT_CACHE_DIR,
        *,
        con: duckdb.DuckDBPyConnection | None = None,
        relations: Mapping[str, str] | None = None,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self._owns_con = con is None
        self.con = con if con is not None else duckdb.connect()
        if relations is None:
            relations = {}
            for grain, table in FACT_TABLES.items():
                path = self.cache_dir / f"{table}.parquet"
                if not path.exists():
                    raise FileNotFoundError(
                        f"{path} is missing -- run `python facts.py facts --cache {self.cache_dir}`"
                    )
                relations[grain] = f"read_parquet('{path}')"
        self.relations = dict(relations)
        self._panels: dict[tuple[str, str], _Panel] = {}

    def close(self) -> None:
        if self._owns_con:
            self.con.close()

    def __enter__(self) -> "FactCache":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def panel(self, grain: str, bucket: str) -> _Panel:
        """Aggregate one grain to one bucket, once."""
        cached = self._panels.get((grain, bucket))
        if cached is not None:
            return cached

        keys = GRAIN_KEYS[grain]
        columns = GRAIN_COLUMNS[grain]
        secs = _bucket_seconds(bucket)
        sql = _BUCKET_SQL.format(
            keys=", ".join(keys),
            bucket=bucket,
            origin=PHASE_ORIGIN.isoformat(sep=" "),
            secs=secs,
            sums=",\n       ".join(f"CAST(sum({c}) AS DOUBLE) AS {c}" for c in columns),
            relation=self.relations[grain],
        )
        result = self.con.execute(sql)
        table = (
            result.to_arrow_table() if hasattr(result, "to_arrow_table") else result.arrow()
        )
        panel = _Panel(
            bucket_index=table.column("bucket_index")
            .combine_chunks()
            .to_numpy(zero_copy_only=False)
            .astype(np.int64),
            columns={
                c: table.column(c).combine_chunks().to_numpy(zero_copy_only=False).astype(
                    np.float64
                )
                for c in columns
            },
            groups=_group_offsets(table, keys),
        )
        self._panels[(grain, bucket)] = panel
        return panel

    def series(
        self, signal: str, layer: Layer, key: EntityKey, first: int
    ) -> tuple[np.ndarray, np.ndarray]:
        """One channel: `(values, present)` over `n_steps` buckets from `first`.

        `present` is False where the bucket held no rows at this grain, and also
        where the ratio's denominator is zero -- a bucket with trains but no
        attributed delay minutes does not have a works share of 0.0, it has no
        works share. Treating it as observed zero would pull the interpolation
        towards a regime that was never measured.

        Stricter than `nullif(denominator, 0)` on purpose: `sum_delay_attributed`
        can go negative when the attributed stops ran early, and a negative
        denominator yields a "share" outside [0, 1], which is worse than absent.
        """
        spec = SIGNAL_SPECS[signal]
        panel = self.panel(spec.grain, layer.bucket)
        start, stop = panel.rows(_grain_key(spec.grain, key))

        n = layer.n_steps
        covered = np.zeros(n, dtype=bool)
        numerator = np.zeros(n, dtype=np.float64)
        denominator = np.zeros(n, dtype=np.float64)

        if stop > start:
            window = panel.bucket_index[start:stop]
            lo = start + int(np.searchsorted(window, first, side="left"))
            hi = start + int(np.searchsorted(window, first + n, side="left"))
            if hi > lo:
                at = (panel.bucket_index[lo:hi] - first).astype(np.intp)
                covered[at] = True
                numerator[at] = panel.columns[spec.numerator][lo:hi]
                if spec.denominator is not None:
                    denominator[at] = panel.columns[spec.denominator][lo:hi]

        if spec.denominator is None:
            return numerator, covered
        present = covered & (denominator > 0.0)
        values = np.zeros(n, dtype=np.float64)
        np.divide(numerator, denominator, out=values, where=present)
        return values, present

    def window(self, entity: Any, anchor: Any, prof: TimelineProfile) -> "Window":
        """Every channel of every layer of one profile, for one record.

        The loop below is the entire multiscale implementation. `prof.layers` is
        the only thing that distinguishes S from M from L from XM.
        """
        key = resolve_entity(entity)
        t0 = anchor_midnight(anchor)
        values: dict[tuple[str, str], np.ndarray] = {}
        present: dict[tuple[str, str], np.ndarray] = {}
        imputed: dict[tuple[str, str], float] = {}
        starts: dict[str, np.ndarray] = {}

        for layer in prof.layers:
            first = bucket_index(t0, layer.bucket_seconds) - layer.n_steps
            starts[layer.layer_id] = bucket_starts(layer, t0)
            for signal in layer.signals:
                raw, mask = self.series(signal, layer, key, first)
                filled = _impute(raw, mask, SIGNAL_SPECS[signal].impute)
                if not np.all(np.isfinite(filled)):
                    bad = int(np.count_nonzero(~np.isfinite(filled)))
                    raise ValueError(
                        f"{signal} at layer {layer.layer_id} for {key} anchored {t0.date()} "
                        f"has {bad} non-finite values; a NaN here reaches the loss and "
                        f"nothing downstream can name the channel it came from"
                    )
                if filled.size != layer.n_steps:
                    raise RuntimeError(
                        f"{signal}/{layer.layer_id}: {filled.size} steps, expected "
                        f"{layer.n_steps}"
                    )
                cell = (layer.layer_id, signal)
                values[cell] = filled.astype(np.float32)
                present[cell] = mask
                imputed[cell] = float(np.count_nonzero(~mask)) / layer.n_steps

        return Window(
            entity=key,
            anchor=t0,
            profile_id=prof.profile_id,
            values=values,
            present=present,
            imputed_fraction=imputed,
            bucket_starts=starts,
        )


def _grain_key(grain: str, key: EntityKey) -> tuple[str, ...]:
    """Project an entity onto one fact table's grouping key.

    EntityKey's field names are the fact tables' key column names, so this is a
    lookup rather than a mapping -- and if that ever stops being true the
    getattr raises instead of silently keying on the wrong column.
    """
    return tuple(getattr(key, name) for name in GRAIN_KEYS[grain])


def _bucket_seconds(bucket: str) -> int:
    """Seconds in a bucket.

    Goes through `Layer` rather than a local table so an unrecognised INTERVAL
    literal fails here exactly as it would in a profile definition, with the same
    message, instead of drifting into a second list of legal buckets.
    """
    return Layer("_probe", bucket, 4, ()).bucket_seconds


def _impute(values: np.ndarray, present: np.ndarray, mode: str) -> np.ndarray:
    """Fill the unobserved buckets.

    "linear" for rates: a mean delay between two observed hours is best guessed
    as the line between them, and `np.interp` holds the end values flat past the
    outermost observations rather than extrapolating a trend off the edge of the
    data, which is the conservative choice for a window that starts in a gap.

    "zero" for the count channel: no trains observed at 03:00 is genuinely zero
    throughput, not an unknown one, and interpolating it would invent a night
    service.

    A channel with nothing observed at all cannot be interpolated. It returns
    zeros -- and an imputed fraction of 1.0, which is ten times the budget, so
    the caller drops the record before the zeros mean anything.
    """
    if mode == "zero":
        return np.where(present, values, 0.0)
    if mode != "linear":
        raise ValueError(f"unknown imputation mode {mode!r}")
    if present.all():
        return values.astype(np.float64, copy=True)
    known = np.flatnonzero(present)
    if known.size == 0:
        return np.zeros_like(values)
    return np.interp(np.arange(values.size, dtype=np.float64), known.astype(np.float64),
                     values[known])


@dataclass(frozen=True)
class Window:
    """One record's context: `{(layer_id, signal): float32[n_steps]}` and its provenance.

    `values` is what the builder hands to TimeNet. Everything else is the
    evidence needed to decide whether it should: which buckets were real, how
    much was filled in, and whether any channel came out flat.
    """

    entity: EntityKey
    anchor: dt.datetime
    profile_id: str
    values: dict[tuple[str, str], np.ndarray]
    present: dict[tuple[str, str], np.ndarray]
    imputed_fraction: dict[tuple[str, str], float]
    bucket_starts: dict[str, np.ndarray] = field(default_factory=dict)

    @property
    def worst_imputed_fraction(self) -> dict[str, float]:
        """The gate, measured over the interpolated channels only.

        `station_throughput`'s gaps are not imputation -- an empty bucket is a
        counted zero -- so including it would reject a quiet station for being
        quiet. Its fraction is still reported per-channel above; it just does
        not vote.

        Reported per grain, because absence means different things at
        different grains -- see MAX_IMPUTED_FRACTION. A single max across all
        channels would let the structurally-sparse pair grain veto every record.
        """
        worst: dict[str, float] = {}
        for (_, signal), fraction in self.imputed_fraction.items():
            spec = SIGNAL_SPECS[signal]
            if spec.impute == "zero":
                continue
            worst[spec.grain] = max(worst.get(spec.grain, 0.0), fraction)
        return worst

    @property
    def overall_imputed_fraction(self) -> float:
        """One number for the whole record: filled buckets over total buckets.

        This is what `build.py`'s `imputed_fraction` annotation describes -- a
        share of the context, not the worst channel. Same interpolated-channel
        denominator as `worst_imputed_fraction`, for the same reason.
        """
        filled = total = 0
        for (layer_id, signal), mask in self.present.items():
            if SIGNAL_SPECS[signal].impute == "zero":
                continue
            filled += int(np.count_nonzero(~mask))
            total += mask.size
        return filled / total if total else 0.0

    @property
    def within_imputation_budget(self) -> bool:
        return all(
            fraction <= MAX_IMPUTED_FRACTION[grain]
            for grain, fraction in self.worst_imputed_fraction.items()
        )

    @property
    def degenerate_channels(self) -> tuple[tuple[str, str], ...]:
        return tuple(cell for cell, v in self.values.items() if is_degenerate(v))

    def reject_reason(self) -> str | None:
        """Why this window is unusable, or None. The caller's whole decision."""
        if not self.within_imputation_budget:
            over = [
                f"{grain} {fraction:.1%} > {MAX_IMPUTED_FRACTION[grain]:.0%}"
                for grain, fraction in sorted(self.worst_imputed_fraction.items())
                if fraction > MAX_IMPUTED_FRACTION[grain]
            ]
            return "imputed buckets over budget: " + ", ".join(over)
        flat = self.degenerate_channels
        if flat:
            return f"constant channels {sorted(flat)} would z-score to NaN"
        return None


def resample(
    entity: Any,
    anchor: Any,
    prof: TimelineProfile | str,
    cache: FactCache,
) -> Window:
    """The module's front door. `prof` may be a TimelineProfile or its id."""
    if isinstance(prof, str):
        prof = PROFILES[prof]
    return cache.window(entity, anchor, prof)
