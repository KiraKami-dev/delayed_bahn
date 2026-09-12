"""Targets and context slots for one (entity, anchor).

**Profile-independent by construction.** A label is a function of the entity and
the horizon -- the ``HORIZON_DAYS`` after the anchor -- and of nothing else. No
function in this module reads a ``profiles.Layer``, and the only thing a profile
contributes is ``context_days``, which sizes the *context slots* and never the
targets. That is what makes the S/M/L/XM bake-off a controlled comparison: the
four datasets differ in how much history precedes the anchor and in nothing
else, so a difference in held-out error is attributable to history length.

The mirror-image rule holds for the **context slots**: every number a rationale
is allowed to cite is computed from ``[anchor - context_days + 1, anchor]``, and
every horizon-derived number is a target. A rationale that says "delays here
have averaged 6 minutes lately, and the works notice runs to the 14th, so expect
about 7" is only honest if none of those three numbers came from the week it is
predicting. Enforcement is by naming: context keys all begin ``ctx_``, and
``assert_no_horizon_leak`` refuses anything else. It is a weak mechanism
defending a strong invariant, which is why the test suite also checks it
behaviourally -- mutate the horizon rows, and the slots must not move.

Three notes on things the source data leaves open, resolved here once:

* **The bool is the scalar thresholded.** ``late_5min`` is
  ``departure_delay_min >= 5``, not an independently defined class. Defined
  separately the two targets can contradict -- a sample labelled "not late" with
  a regression target of 6.2 minutes -- and a rationale reading both would be
  incoherent. Measured share of stop events at or over 5 minutes on 2026-08:
  18.9% nationwide, 23.4% over the Munich catchment, 28% over the Munich name
  match. That is a workable class balance at every scope, so nothing is
  resampled and no stratification is applied. Resampling would also fight the
  recency weighting in anchors.py, which is the one reweighting this pipeline
  does on purpose.
* **``departure_delay_min`` is ``delay_in_min``, and that is the DEPARTURE
  delay.** Measured over all 14,270,628 rows of 2026-08: ``delay_in_min`` equals
  ``departure_change - departure_planned`` for 99.998% of rows that have a
  departure, and the arrival difference for only 53.3%. (A check restricted to
  pure-arrival rows -- termini, with no departure -- shows 100% arrival, which is
  the same fact seen from a biased subset.)

  The target is named for what it is rather than switched to arrival, because
  every channel in the fact cache is built on ``delay_in_min``: changing the
  label alone would leave ``service_at_station_delay`` measuring one quantity and
  the target another. It is also the right quantity for the question -- a
  passenger boarding here cares when the train leaves. ``TRUE_ARRIVAL_DELAY_SQL``
  below is the escape hatch, via ``open_workspace(delay_sql=...)``, and adopting
  it means rebuilding ``facts.py`` too.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field
from typing import Iterable, NamedTuple, Sequence

import duckdb
import pyarrow as pa

from causes import ATTRIBUTION_FLOOR, DOMINANCE_FLOOR, FAMILY_NAMES
from entities import LATE_THRESHOLD_MIN, Entity
from profiles import HORIZON_DAYS
from sources import SERVICE_DATE_SQL, SERVICE_GROUP_SQL

# --- thresholds -------------------------------------------------------------

UNATTRIBUTED = "unattributed"

# The delay expression. `delay_in_min` is what facts.py aggregates, so it is
# what the context channels measure; see the module docstring for why the target
# follows it rather than the arrival timestamps.
DEPARTURE_DELAY_SQL = "delay_in_min"
# The arrival-side alternative, kept next to the default so the choice is
# visible rather than buried in a diff. Adopting it means changing facts.py too.
TRUE_ARRIVAL_DELAY_SQL = (
    "CASE WHEN arrival_planned_time IS NOT NULL AND arrival_change_time IS NOT NULL "
    "THEN date_diff('minute', arrival_planned_time, arrival_change_time) "
    "ELSE delay_in_min END"
)

# A stop is "delayed" -- and so has something to attribute -- at one minute.
# Not 5: the attribution question ("was a reason given") is different from the
# lateness question ("did it matter to a traveller"), and a stop three minutes
# down with a `Bauarbeiten` code is evidence about the cause even though no one
# missed a connection over it.
DELAYED_STOP_MIN = 1

# Horizon support required before a label means anything. The horizon is 7 days,
# so a Monday-to-Friday service contributes 5 service dates. Requiring 4 admits
# a weekday service that lost one day to engineering work; requiring 5 would
# reject it, and requiring 3 would admit a pair that only runs at weekends,
# whose "next week" is two observations.
MIN_HORIZON_SERVICE_DATES = 4
MIN_HORIZON_EVENTS = 4

# Trend is the last 28 days of context against the 28 before them. Four weeks
# because anything shorter compares one week's weather to another's, and because
# a works notice has a median validity of 22.5 days (causes.DisruptionNotice) --
# a 28-day window is the shortest one that can contain a whole typical closure
# and so show it arriving.
TREND_WINDOW_DAYS = 28

REASON_OK = "ok"
REASON_NO_SERVICE = "no_service_in_horizon"
REASON_THIN_DATES = "thin_horizon_service_dates"
REASON_THIN_EVENTS = "thin_horizon_events"

# Every key a rationale may cite, in emission order. Published as a tuple so a
# prompt template can be checked against it rather than against a sample.
CONTEXT_SLOTS: tuple[str, ...] = (
    "ctx_service_count",
    "ctx_service_dates",
    "ctx_mean_delay_min",
    "ctx_median_delay_min",
    "ctx_modal_hour",
    "ctx_mean_delay_at_hour",
    "ctx_median_delay_at_hour",
    "ctx_recent_mean_delay_min",
    "ctx_prior_mean_delay_min",
    "ctx_trend_delta_min",
    "ctx_trend_window_days",
    "ctx_late_5_share",
    "ctx_cancel_rate",
    "ctx_attributed_share",
    "ctx_works_notice_coverage",
    *tuple(f"ctx_family_share_{family}" for family in FAMILY_NAMES),
)


# --- records ----------------------------------------------------------------


class LabelSpec(NamedTuple):
    """The join key of a training sample. Everything else is derived."""

    entity_id: str
    service_group: str
    station: str
    anchor: dt.date


@dataclass(frozen=True)
class Support:
    """Whether the horizon has enough service for a label to exist."""

    entity_id: str
    anchor: dt.date
    n_events: int
    n_service_dates: int
    computable: bool
    reason: str


@dataclass(frozen=True)
class Label:
    """Targets for one (entity, anchor), plus the context a rationale may cite."""

    entity_id: str
    anchor: dt.date
    n_events: int
    n_service_dates: int
    departure_delay_min: float
    arrival_delay_log1p: float
    late_5min: bool
    late_5_share: float
    dominant_cause_family: str
    horizon_attributed_share: float
    family_shares: dict[str, float] = field(default_factory=dict)
    context: dict[str, float | int | None] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "anchor": self.anchor.isoformat(),
            "n_events": self.n_events,
            "n_service_dates": self.n_service_dates,
            "departure_delay_min": round(self.departure_delay_min, 4),
            "arrival_delay_log1p": round(self.arrival_delay_log1p, 6),
            "late_5min": self.late_5min,
            "late_5_share": round(self.late_5_share, 4),
            "dominant_cause_family": self.dominant_cause_family,
            "horizon_attributed_share": round(self.horizon_attributed_share, 4),
            "family_shares": {k: round(v, 4) for k, v in sorted(self.family_shares.items())},
            "context": dict(sorted(self.context.items())),
        }


def assert_no_horizon_leak(context: dict) -> None:
    """Every context key must be ``ctx_``-prefixed and known.

    Naming is the enforcement mechanism because the leak this guards against is
    a typo, not a conspiracy: someone adds ``mean_delay`` to the slots meaning
    the context one and wires the horizon aggregate to it. An unprefixed key
    fails here; a prefixed key pointing at horizon data fails the behavioural
    test in tests/test_labels.py, which mutates the horizon and checks the slots
    do not move.
    """
    unknown = sorted(set(context) - set(CONTEXT_SLOTS))
    if unknown:
        raise ValueError(f"context slots not declared in CONTEXT_SLOTS: {unknown}")
    unprefixed = sorted(key for key in context if not key.startswith("ctx_"))
    if unprefixed:
        raise ValueError(f"context slot without a ctx_ prefix: {unprefixed}")


# --- attribution ------------------------------------------------------------


def resolve_cause(
    n_delayed: int, n_delayed_attributed: int, family_minutes: dict[str, float]
) -> tuple[str, float, dict[str, float]]:
    """Name a cause family, or refuse to. Returns (family, attributed_share, shares).

    Two independent gates, both from causes.py, and both have to pass:

      1. ``ATTRIBUTION_FLOOR`` (0.35) -- enough of the delayed stops carry a code
         at all. Below it the honest statement is that the delay is diffuse, and
         the dataset has to be able to say so; "unattributed" is a real answer,
         not a missing value. Measured attribution over all stops is 30.1%, so
         this gate refuses often and on purpose.
      2. ``DOMINANCE_FLOOR`` (0.40) -- one family holds enough of the attributed
         minutes to be *the* reason. Three families at 33% each is a week where
         everything went slightly wrong, and naming the largest would be a
         coin-flip dressed as an explanation.

    Ties in the top share resolve alphabetically, which only matters for exact
    ties and keeps the corpus reproducible when it happens.
    """
    attributed_share = (n_delayed_attributed / n_delayed) if n_delayed else 0.0
    total = sum(family_minutes.values())
    shares = {family: 0.0 for family in FAMILY_NAMES}
    if total > 0:
        for family, minutes in family_minutes.items():
            shares[family] = minutes / total
    if attributed_share < ATTRIBUTION_FLOOR or total <= 0:
        return UNATTRIBUTED, attributed_share, shares
    top_family, top_share = sorted(shares.items(), key=lambda kv: (-kv[1], kv[0]))[0]
    if top_share < DOMINANCE_FLOOR:
        return UNATTRIBUTED, attributed_share, shares
    return top_family, attributed_share, shares


def log1p_delay(delay_min: float) -> float:
    """``log1p`` of the delay, clamped at zero first.

    Delay is heavily right-skewed -- the mass sits at 0-2 minutes with a tail
    past 60 -- so a plain MAE is dominated by the bulk and a model that never
    predicts a bad week scores well. The log target is what the tail metrics are
    computed against; report both, and report the tail separately.

    Clamped because early trains exist: 80,753 of 14,270,628 stop events on
    2026-08 carry a negative ``delay_in_min`` (0.57%) and ``log1p(-3)`` is
    undefined. A train three minutes early and one exactly on time are the same
    answer to "how late will it be", so folding them together loses nothing the
    question cares about. The raw scalar keeps the sign.
    """
    return math.log1p(max(delay_min, 0.0))


# --- workspace --------------------------------------------------------------


@dataclass
class Workspace:
    """Temp views and the spec table the label queries run against.

    Everything is set-based. A per-anchor query would be 15,000 round trips for
    a 3,000-entity corpus at M=5; this is six queries whatever the corpus size.
    The cost is a range join between the spec table and the events relation,
    which DuckDB plans as an IEJoin -- fine for an offline build, and the reason
    the spec table exists at all rather than a WHERE clause per anchor.
    """

    con: duckdb.DuckDBPyConnection
    prefix: str
    context_days: int
    horizon_days: int
    has_causes: bool
    has_notices: bool

    @property
    def spec(self) -> str:
        return f"{self.prefix}_spec"

    @property
    def evc(self) -> str:
        return f"{self.prefix}_evc"

    @property
    def works(self) -> str:
        return f"{self.prefix}_works"


def _bulk_insert(
    con: duckdb.DuckDBPyConnection, table: str, rows: Sequence[tuple], schema: pa.Schema
) -> None:
    """Insert through a registered Arrow table rather than ``executemany``.

    Measured: 10,000 rows via ``executemany`` take 4.7 seconds because DuckDB
    prepares and executes one statement per row; the same rows through Arrow
    take 0.07. A 3,000-entity corpus at M=5 is 15,000 spec rows, and this
    workspace is rebuilt once per profile in the bake-off.
    """
    if not rows:
        return
    columns = {
        field.name: pa.array([row[i] for row in rows], field.type)
        for i, field in enumerate(schema)
    }
    view = "_src_" + "".join(ch if ch.isalnum() else "_" for ch in table)
    con.register(view, pa.table(columns, schema=schema))
    try:
        con.execute(f"INSERT INTO {table} SELECT * FROM {view}")
    finally:
        con.unregister(view)


_SPEC_SCHEMA = pa.schema(
    [
        ("entity_id", pa.string()),
        ("service_group", pa.string()),
        ("station", pa.string()),
        ("anchor", pa.date32()),
        ("ctx_start", pa.date32()),
        ("hz_start", pa.date32()),
        ("hz_end", pa.date32()),
    ]
)
_MODAL_SCHEMA = pa.schema(
    [("entity_id", pa.string()), ("anchor", pa.date32()), ("hour_of_day", pa.int32())]
)


def _join(alias_spec: str, alias_ev: str, lo: str, hi: str) -> str:
    return (
        f"{alias_ev}.service_group = {alias_spec}.service_group "
        f"AND {alias_ev}.station = {alias_spec}.station "
        f"AND {alias_ev}.service_date >= {alias_spec}.{lo} "
        f"AND {alias_ev}.service_date <= {alias_spec}.{hi}"
    )


def open_workspace(
    con: duckdb.DuckDBPyConnection,
    specs: Sequence[LabelSpec],
    *,
    events: str,
    causes: str | None = None,
    notices: str | None = None,
    context_days: int,
    horizon_days: int = HORIZON_DAYS,
    prefix: str = "_lbl",
    delay_sql: str = DEPARTURE_DELAY_SQL,
) -> Workspace:
    """Build the temp views and the spec table. Idempotent within a connection."""
    con.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW {prefix}_ev AS
        SELECT {SERVICE_GROUP_SQL}                         AS service_group,
               station_name                                AS station,
               {SERVICE_DATE_SQL}                          AS service_date,
               CAST(extract('hour' FROM time) AS INTEGER)  AS hour_of_day,
               {delay_sql}                                 AS delay_in_min,
               (coalesce(arrival_is_canceled, false)
                OR coalesce(departure_is_canceled, false)) AS cancelled,
               id                                          AS stop_id
        FROM {events}
        """
    )
    families = "c.families" if causes else "NULL::VARCHAR[]"
    cause_join = f"LEFT JOIN {causes} c ON c.stop_id = e.stop_id" if causes else ""
    con.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW {prefix}_evc AS
        SELECT e.*, {families} AS families FROM {prefix}_ev e {cause_join}
        """
    )
    con.execute(f"DROP TABLE IF EXISTS {prefix}_spec")
    con.execute(
        f"""
        CREATE TEMP TABLE {prefix}_spec (
            entity_id VARCHAR, service_group VARCHAR, station VARCHAR,
            anchor DATE, ctx_start DATE, hz_start DATE, hz_end DATE
        )
        """
    )
    rows = [
        (
            spec.entity_id,
            spec.service_group,
            spec.station,
            spec.anchor,
            spec.anchor - dt.timedelta(days=context_days - 1),
            spec.anchor + dt.timedelta(days=1),
            spec.anchor + dt.timedelta(days=horizon_days),
        )
        for spec in sorted(set(specs))
    ]
    _bulk_insert(con, f"{prefix}_spec", rows, _SPEC_SCHEMA)

    con.execute(f"DROP TABLE IF EXISTS {prefix}_works")
    if notices:
        # Notices carry stop_ids, and a stop_id is <ride>-<stamp>-<num> with no
        # station in it, so the only way to a station is back through the events
        # relation. Done once here rather than per anchor.
        con.execute(
            f"""
            CREATE TEMP TABLE {prefix}_works AS
            WITH n AS (
                SELECT notice_id, valid_from, valid_to, unnest(stop_ids) AS stop_id
                FROM {notices}
                WHERE category LIKE 'Bauarbeiten%'
            )
            SELECT DISTINCT e.station,
                   CAST(n.valid_from AS DATE) AS d_from,
                   CAST(n.valid_to   AS DATE) AS d_to
            FROM n JOIN {prefix}_ev e ON e.stop_id = n.stop_id
            """
        )
    return Workspace(
        con=con,
        prefix=prefix,
        context_days=context_days,
        horizon_days=horizon_days,
        has_causes=bool(causes),
        has_notices=bool(notices),
    )


# --- computability ----------------------------------------------------------


def horizon_support(ws: Workspace) -> list[Support]:
    """Does the service actually call at the station often enough in the horizon?

    This gates *before* curation, not after. An entity that qualified on a
    month's support can still have a horizon in which its line was replaced by a
    bus, and a label averaged over one surviving stop is noise presented as an
    answer. Everything downstream -- the series, the rationale, the metric -- is
    worthless for such a sample, and it is cheaper to find them here than to
    explain an outlier later.
    """
    rows = ws.con.execute(
        f"""
        SELECT s.entity_id, s.anchor,
               count(e.stop_id)              AS n_events,
               count(DISTINCT e.service_date) AS n_service_dates
        FROM {ws.spec} s
        LEFT JOIN {ws.prefix}_ev e ON {_join('s', 'e', 'hz_start', 'hz_end')}
        GROUP BY 1, 2
        ORDER BY 1, 2
        """
    ).fetchall()
    out: list[Support] = []
    for entity_id, anchor, n_events, n_service_dates in rows:
        if not n_events:
            reason = REASON_NO_SERVICE
        elif n_service_dates < MIN_HORIZON_SERVICE_DATES:
            reason = REASON_THIN_DATES
        elif n_events < MIN_HORIZON_EVENTS:
            reason = REASON_THIN_EVENTS
        else:
            reason = REASON_OK
        out.append(
            Support(
                entity_id=entity_id,
                anchor=anchor,
                n_events=int(n_events),
                n_service_dates=int(n_service_dates),
                computable=reason == REASON_OK,
                reason=reason,
            )
        )
    return out


def label_computable(
    con: duckdb.DuckDBPyConnection,
    entity: Entity | LabelSpec,
    anchor: dt.date,
    *,
    events: str,
    context_days: int = 1,
    horizon_days: int = HORIZON_DAYS,
    prefix: str = "_lblchk",
) -> Support:
    """Single-sample convenience over ``horizon_support``.

    ``context_days`` defaults to 1 because computability does not look at the
    context at all -- only at whether the horizon has service.
    """
    spec = (
        LabelSpec(entity.entity_id, entity.service_group, entity.station, anchor)
        if isinstance(entity, Entity)
        else entity._replace(anchor=anchor)
    )
    ws = open_workspace(
        con,
        [spec],
        events=events,
        context_days=context_days,
        horizon_days=horizon_days,
        prefix=prefix,
    )
    return horizon_support(ws)[0]


# --- targets and slots ------------------------------------------------------


def _horizon_rows(ws: Workspace) -> dict[tuple[str, dt.date], tuple]:
    rows = ws.con.execute(
        f"""
        SELECT s.entity_id, s.anchor,
               count(e.stop_id)                                          AS n_events,
               count(DISTINCT e.service_date)                            AS n_service_dates,
               avg(e.delay_in_min)                                       AS mean_delay,
               avg(CASE WHEN e.delay_in_min IS NULL THEN NULL
                        WHEN e.delay_in_min >= {LATE_THRESHOLD_MIN} THEN 1.0
                        ELSE 0.0 END)                                    AS late_share,
               count(*) FILTER (WHERE e.delay_in_min >= {DELAYED_STOP_MIN})
                                                                         AS n_delayed,
               count(*) FILTER (WHERE e.delay_in_min >= {DELAYED_STOP_MIN}
                                  AND e.families IS NOT NULL)            AS n_delayed_attributed
        FROM {ws.spec} s
        LEFT JOIN {ws.evc} e ON {_join('s', 'e', 'hz_start', 'hz_end')}
        GROUP BY 1, 2
        ORDER BY 1, 2
        """
    ).fetchall()
    return {(r[0], r[1]): r[2:] for r in rows}


def _family_minutes(ws: Workspace, lo: str, hi: str) -> dict[tuple[str, dt.date], dict[str, float]]:
    if not ws.has_causes:
        return {}
    rows = ws.con.execute(
        f"""
        WITH hit AS (
            SELECT s.entity_id, s.anchor, e.delay_in_min AS minutes, e.families
            FROM {ws.spec} s
            JOIN {ws.evc} e ON {_join('s', 'e', lo, hi)}
            WHERE e.families IS NOT NULL AND e.delay_in_min >= {DELAYED_STOP_MIN}
        ), spread AS (
            SELECT entity_id, anchor, unnest(families) AS family, minutes FROM hit
        )
        SELECT entity_id, anchor, family, sum(minutes) AS minutes
        FROM spread GROUP BY 1, 2, 3 ORDER BY 1, 2, 3
        """
    ).fetchall()
    out: dict[tuple[str, dt.date], dict[str, float]] = {}
    for entity_id, anchor, family, minutes in rows:
        out.setdefault((entity_id, anchor), {})[family] = float(minutes)
    return out


def _modal_hours(ws: Workspace) -> dict[tuple[str, dt.date], int]:
    """The hour-of-day this stop event usually happens, from the context.

    ``mode()`` is not used: DuckDB does not define its tie-break, and a pair
    served equally at 07:00 and 17:00 would get a different answer on a
    different thread count. Ranking by (count desc, hour asc) is the same
    statistic with a stated tie-break.
    """
    rows = ws.con.execute(
        f"""
        SELECT entity_id, anchor, hour_of_day FROM (
            SELECT s.entity_id, s.anchor, e.hour_of_day,
                   row_number() OVER (PARTITION BY s.entity_id, s.anchor
                                      ORDER BY count(*) DESC, e.hour_of_day ASC) AS rn
            FROM {ws.spec} s
            JOIN {ws.evc} e ON {_join('s', 'e', 'ctx_start', 'anchor')}
            GROUP BY 1, 2, 3
        ) WHERE rn = 1
        ORDER BY 1, 2
        """
    ).fetchall()
    return {(r[0], r[1]): int(r[2]) for r in rows}


def _context_rows(ws: Workspace, modal: dict[tuple[str, dt.date], int]) -> dict[tuple[str, dt.date], tuple]:
    ws.con.execute(f"DROP TABLE IF EXISTS {ws.prefix}_modal")
    ws.con.execute(
        f"CREATE TEMP TABLE {ws.prefix}_modal (entity_id VARCHAR, anchor DATE, hour_of_day INTEGER)"
    )
    _bulk_insert(
        ws.con,
        f"{ws.prefix}_modal",
        [(eid, anchor, hour) for (eid, anchor), hour in sorted(modal.items())],
        _MODAL_SCHEMA,
    )
    rows = ws.con.execute(
        f"""
        SELECT s.entity_id, s.anchor,
               count(e.stop_id)                                          AS n_events,
               count(DISTINCT e.service_date)                            AS n_service_dates,
               avg(e.delay_in_min)                                       AS mean_delay,
               median(e.delay_in_min)                                    AS median_delay,
               avg(CASE WHEN e.hour_of_day = m.hour_of_day
                        THEN e.delay_in_min END)                         AS mean_delay_at_hour,
               median(CASE WHEN e.hour_of_day = m.hour_of_day
                           THEN e.delay_in_min END)                      AS median_delay_at_hour,
               avg(CASE WHEN e.service_date > s.anchor - {TREND_WINDOW_DAYS}
                        THEN e.delay_in_min END)                         AS recent_mean,
               avg(CASE WHEN e.service_date <= s.anchor - {TREND_WINDOW_DAYS}
                         AND e.service_date > s.anchor - {2 * TREND_WINDOW_DAYS}
                        THEN e.delay_in_min END)                         AS prior_mean,
               avg(CASE WHEN e.delay_in_min IS NULL THEN NULL
                        WHEN e.delay_in_min >= {LATE_THRESHOLD_MIN} THEN 1.0
                        ELSE 0.0 END)                                    AS late_share,
               avg(CASE WHEN e.cancelled THEN 1.0 ELSE 0.0 END)          AS cancel_rate,
               count(*) FILTER (WHERE e.delay_in_min >= {DELAYED_STOP_MIN})
                                                                         AS n_delayed,
               count(*) FILTER (WHERE e.delay_in_min >= {DELAYED_STOP_MIN}
                                  AND e.families IS NOT NULL)            AS n_delayed_attributed
        FROM {ws.spec} s
        LEFT JOIN {ws.evc} e ON {_join('s', 'e', 'ctx_start', 'anchor')}
        LEFT JOIN {ws.prefix}_modal m
               ON m.entity_id = s.entity_id AND m.anchor = s.anchor
        GROUP BY 1, 2
        ORDER BY 1, 2
        """
    ).fetchall()
    return {(r[0], r[1]): r[2:] for r in rows}


def _works_coverage(ws: Workspace) -> dict[tuple[str, dt.date], float]:
    """Fraction of context days at this station covered by a works notice.

    Day-grid rather than summing notice durations, because notices overlap --
    335 distinct ids behind 18,364 attachments in one day (causes.py) and 79% of
    windows longer than a week. Summing overlapping windows gives coverage above
    1.0; counting covered days does not.
    """
    if not ws.has_notices:
        return {}
    rows = ws.con.execute(
        f"""
        WITH days AS (
            SELECT s.entity_id, s.anchor, s.station,
                   CAST(unnest(generate_series(s.ctx_start, s.anchor, INTERVAL 1 DAY)) AS DATE) AS d
            FROM {ws.spec} s
        ), hit AS (
            SELECT DISTINCT d.entity_id, d.anchor, d.d
            FROM days d
            JOIN {ws.works} w ON w.station = d.station AND d.d BETWEEN w.d_from AND w.d_to
        )
        SELECT d.entity_id, d.anchor, count(h.d) * 1.0 / count(*) AS coverage
        FROM days d
        LEFT JOIN hit h ON h.entity_id = d.entity_id AND h.anchor = d.anchor AND h.d = d.d
        GROUP BY 1, 2
        ORDER BY 1, 2
        """
    ).fetchall()
    return {(r[0], r[1]): float(r[2]) for r in rows}


def compute_labels(ws: Workspace, *, skip_incomputable: bool = True) -> list[Label]:
    """Targets and context slots for every spec in the workspace.

    Six queries: horizon aggregate, horizon family minutes, context modal hour,
    context aggregate, context family minutes, works coverage. Their results are
    joined in Python on (entity_id, anchor) because that is 15,000 dict lookups,
    not because it would be hard in SQL -- keeping the horizon and context
    queries textually separate is what makes it possible to read this file and
    see that no context slot touches ``hz_start``.
    """
    support = {(s.entity_id, s.anchor): s for s in horizon_support(ws)}
    horizon = _horizon_rows(ws)
    horizon_families = _family_minutes(ws, "hz_start", "hz_end")
    context_families = _family_minutes(ws, "ctx_start", "anchor")
    modal = _modal_hours(ws)
    context = _context_rows(ws, modal)
    coverage = _works_coverage(ws)

    labels: list[Label] = []
    for key in sorted(horizon):
        entity_id, anchor = key
        if skip_incomputable and not support[key].computable:
            continue
        (
            n_events,
            n_service_dates,
            mean_delay,
            late_share,
            n_delayed,
            n_delayed_attributed,
        ) = horizon[key]
        mean_delay = float(mean_delay or 0.0)
        family, attributed_share, shares = resolve_cause(
            int(n_delayed), int(n_delayed_attributed), horizon_families.get(key, {})
        )
        labels.append(
            Label(
                entity_id=entity_id,
                anchor=anchor,
                n_events=int(n_events),
                n_service_dates=int(n_service_dates),
                departure_delay_min=mean_delay,
                arrival_delay_log1p=log1p_delay(mean_delay),
                late_5min=mean_delay >= LATE_THRESHOLD_MIN,
                late_5_share=float(late_share or 0.0),
                dominant_cause_family=family,
                horizon_attributed_share=attributed_share,
                family_shares=shares,
                context=_context_slots(
                    context.get(key),
                    context_families.get(key, {}),
                    coverage.get(key),
                    modal.get(key),
                    ws,
                ),
            )
        )
    return labels


def _context_slots(
    row: tuple | None,
    family_minutes: dict[str, float],
    works_coverage: float | None,
    modal_hour: int | None,
    ws: Workspace,
) -> dict[str, float | int | None]:
    """Assemble the slots. Reads the context aggregate only -- never ``horizon``."""
    if row is None:
        row = (0, 0, None, None, None, None, None, None, None, None, 0, 0)
    (
        n_events,
        n_service_dates,
        mean_delay,
        median_delay,
        mean_at_hour,
        median_at_hour,
        recent_mean,
        prior_mean,
        late_share,
        cancel_rate,
        n_delayed,
        n_delayed_attributed,
    ) = row
    total = sum(family_minutes.values())
    slots: dict[str, float | int | None] = {
        "ctx_service_count": int(n_events),
        "ctx_service_dates": int(n_service_dates),
        "ctx_mean_delay_min": _round(mean_delay),
        "ctx_median_delay_min": _round(median_delay),
        "ctx_modal_hour": modal_hour,
        "ctx_mean_delay_at_hour": _round(mean_at_hour),
        "ctx_median_delay_at_hour": _round(median_at_hour),
        "ctx_recent_mean_delay_min": _round(recent_mean),
        "ctx_prior_mean_delay_min": _round(prior_mean),
        "ctx_trend_delta_min": (
            _round(float(recent_mean) - float(prior_mean))
            if recent_mean is not None and prior_mean is not None
            else None
        ),
        "ctx_trend_window_days": TREND_WINDOW_DAYS,
        "ctx_late_5_share": _round(late_share),
        "ctx_cancel_rate": _round(cancel_rate),
        # None, not 0.0, when there is nothing to divide by or no shards to read:
        # "no delay was attributed" and "attribution was never extracted" are
        # different statements and a rationale must not confuse them.
        "ctx_attributed_share": (
            _round(n_delayed_attributed / n_delayed) if ws.has_causes and n_delayed else None
        ),
        "ctx_works_notice_coverage": _round(works_coverage) if ws.has_notices else None,
    }
    for name in FAMILY_NAMES:
        slots[f"ctx_family_share_{name}"] = (
            _round(family_minutes.get(name, 0.0) / total) if total > 0 else None
        )
    assert_no_horizon_leak(slots)
    return slots


def _round(value: float | None, places: int = 4) -> float | None:
    """Round for reproducibility, not for looks.

    A float sum's low bits depend on the order DuckDB visits the rows in, which
    changes with thread count and with how a parquet file happens to be split.
    Four decimals is far below any resolution a delay statistic has and puts the
    content hash of a manifest back under the pipeline's control.
    """
    return None if value is None else round(float(value), places)


def specs_from(entities: Iterable[Entity], anchors: Iterable) -> list[LabelSpec]:
    """Join entities to anchors on ``entity_id`` -- the only place they meet.

    ``anchors`` is an iterable of ``anchors.Anchor``; typed loosely so labels.py
    does not import anchors.py and create a cycle through entities.py.
    """
    by_id = {entity.entity_id: entity for entity in entities}
    out: list[LabelSpec] = []
    for anchor in anchors:
        entity = by_id.get(anchor.entity_id)
        if entity is None:
            continue
        out.append(LabelSpec(entity.entity_id, entity.service_group, entity.station, anchor.anchor))
    return sorted(set(out))
