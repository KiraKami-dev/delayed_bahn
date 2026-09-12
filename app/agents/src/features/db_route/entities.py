"""Enumerate and curate the (service_group, station) pairs worth training on.

A training sample is one **stop event** -- ``(service_group, station, anchor)``,
"how late will this train be at this stop". Itineraries are deliberately not the
unit: a connection is two stop events plus a transfer rule, and the rule (how
much slack counts as a made connection) is a modelling decision that would end
up baked into the labels where no ablation can reach it.

``service_group`` is ``train_type || ' -> ' || final_destination_station``, not
the line number: ``line_number`` is blank for 100% of ICE, IC, EC, ECE, RJ, NJ
and TGV rows (measured on 2026-08) while ``final_destination_station`` is
populated for 100% of every type. See ``sources.SERVICE_GROUP_SQL``.

Qualification is a **support** test, not a quality test. A pair needs at least
``MIN_SERVICE_DATES`` distinct service dates in the window or there is no
history for the profiles to draw a series over -- and a pair that runs twice a
month is not a stop event a traveller plans around. Measured on 2026-08:

    Munich name-matched        1,201 pairs,   559 with >= 20 service dates (47%)
    one-hop, all train types  16,603 pairs, 8,919 with >= 20 service dates (54%)
    one-hop, local operators   (552 stations)  3,683 with >= 20 service dates

Three things follow. Roughly half of all pairs qualify, so the candidate pool
has to be about twice the corpus. The name match cannot fill a 3,000-entity
corpus at ``MAX_PER_STATION`` = 30 -- that needs >= 100 distinct stations and
the name match has 49. And the catchment the pipeline actually uses is the
third line, ``facts.build_catchment``: one hop but local operators only, which
is 3,683 qualifying pairs against a 3,000 target. That is an 81% selection rate,
so the quota below is close to binding -- expect ``min_affected_share`` to be
the first quota to come back unmet, and read the shortfall in the report rather
than assuming the corpus is balanced.

The **rejection log is a deliverable**, not debug output. "8,919 of 16,603
qualified" is a claim about the corpus; without the reason for each of the other
7,684 it is not a reproducible one, and the first question anyone asks about a
curated set is what it left out.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import duckdb

from sources import SERVICE_DATE_SQL, SERVICE_GROUP_SQL, connect, month_url, months_between

# --- thresholds -------------------------------------------------------------

# Distinct service dates a pair needs in the anchor window. 20 is a little under
# a weekday month (22): it admits a Monday-to-Friday service that lost two days
# to engineering work, and rejects anything that only ran on weekends or was
# introduced mid-window.
MIN_SERVICE_DATES = 20

# "Late" everywhere in this pipeline. Defined here rather than in labels.py
# because entities.py is the bottom of the import chain and both the support
# statistic (`share_late_5`) and the classification target read it, so the two
# cannot drift apart.
LATE_THRESHOLD_MIN = 5

# --- curation quota ---------------------------------------------------------
# The quota is what stops the corpus being 3,000 samples of München Hbf. Each
# number is a constraint on the *design*, not a preference:

DEFAULT_TARGET = 3000
# Below ~25 stations the station-level context channel (`station_delay`) has no
# variance to explain anything with -- every sample would share one congestion
# series.
MIN_STATIONS = 25
# 30 per station at 3,000 entities forces >= 100 distinct stations. That is the
# real content of this cap: it converts the corpus target into a breadth
# requirement that the one-hop catchment (8,919 qualifying pairs over hundreds
# of stations) satisfies and a single-city name match does not.
MAX_PER_STATION = 30
# A soft cap on any one train type. Soft because S-Bahn dominates the catchment
# by count and a hard cap would leave the target unreachable; over-cap picks are
# allowed once nothing else is available and are counted in the report.
MAX_TYPE_SHARE = 0.40
# At least this share of the corpus must have lived through a works or weather
# period. Without it the long profiles (QUARTER, SEASON) are being asked to
# detect a regime shift in a corpus that contains none, and S would win the
# bake-off for the wrong reason.
MIN_AFFECTED_SHARE = 0.20
# ...where "lived through" means this many distinct service dates carrying
# works- or weather-attributed delay. One day is an incident; DB's own works
# notices have a median validity window of 22.5 days (causes.DisruptionNotice),
# so three separate days is a low bar that still excludes a single thunderstorm.
REGIME_MIN_DAYS = 3

# Rejection reasons. Stable strings -- they are read out of entities.json.
REASON_THIN = "thin_service_dates"
REASON_NO_DELAY = "no_observed_delay"
REASON_OUTSIDE_UNIVERSE = "outside_station_universe"

# --- identity ---------------------------------------------------------------


def stable_digest(text: str) -> int:
    """A process-independent 64-bit digest of a source key.

    Python's builtin ``hash`` is salted per process (PYTHONHASHSEED), so a
    corpus keyed on it is not reproducible between two runs on the same machine,
    never mind between machines. Every deterministic choice downstream goes
    through this instead -- entity ids here, the per-entity anchor stagger in
    anchors.py.
    """
    return int.from_bytes(hashlib.blake2s(text.encode("utf-8"), digest_size=8).digest(), "big")


def _slug(text: str | None, limit: int) -> str:
    """Fold to ASCII. ``None`` is not a station name -- say so rather than crash.

    Real months carry rows with a null ``station_name`` or a null destination,
    which no synthetic fixture produced. They are filtered out upstream; this
    guard exists so a future caller gets a readable failure instead of a
    TypeError from deep inside unicodedata.
    """
    if text is None:
        raise ValueError("entity_id needs a station and a service group; got None")
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in folded)
    return "-".join(part for part in cleaned.split("-") if part)[:limit].strip("-")


def entity_id(service_group: str, station: str) -> str:
    """A readable, source-derived, collision-free id for one (group, station).

    The slug is for the human reading the rejection log; the digest is what
    makes it unique. Names collide after ASCII folding and truncation -- the
    dataset carries both "München Hbf" and "Muenchen Hbf" spellings, which fold
    to the same slug -- and a collision would silently merge two entities'
    anchors into one training series.
    """
    digest = hashlib.blake2s(
        f"{service_group}\x1f{station}".encode("utf-8"), digest_size=6
    ).hexdigest()
    return f"{_slug(station, 20)}--{_slug(service_group, 28)}--{digest}"


def content_hash(payload: object) -> str:
    """blake2s over canonical JSON of a manifest.

    Canonical means sorted keys and no whitespace, so the hash is a function of
    the content and not of how json.dump happened to lay it out. Floats are
    rounded by the emitters before they get here -- an unrounded aggregate's
    last bits depend on DuckDB's scan order, which changes with thread count.
    """
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.blake2s(blob.encode("utf-8"), digest_size=16).hexdigest()


# --- records ----------------------------------------------------------------


@dataclass(frozen=True)
class Entity:
    """One stop event type, with the support statistics curation ranks on."""

    entity_id: str
    service_group: str
    station: str
    train_type: str
    n_events: int
    n_service_dates: int
    first_seen: dt.date
    last_seen: dt.date
    mean_delay_min: float
    share_late_5: float
    cancel_rate: float
    n_attributed: int
    affected_days: int

    @property
    def is_regime_affected(self) -> bool:
        """Did this pair live through a works or weather period at all?

        False also when the cause shards for the window have not been extracted
        yet, which is why ``curate`` reports the affected share as a shortfall
        rather than raising: an unmet quota and an unbuilt cache look identical
        from here, and only the caller knows which it is.
        """
        return self.affected_days >= REGIME_MIN_DAYS

    def as_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "service_group": self.service_group,
            "station": self.station,
            "train_type": self.train_type,
            "n_events": self.n_events,
            "n_service_dates": self.n_service_dates,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "mean_delay_min": round(self.mean_delay_min, 4),
            "share_late_5": round(self.share_late_5, 4),
            "cancel_rate": round(self.cancel_rate, 4),
            "n_attributed": self.n_attributed,
            "affected_days": self.affected_days,
            "regime_affected": self.is_regime_affected,
        }


@dataclass(frozen=True)
class Rejection:
    """A candidate pair that did not qualify, and every reason it did not."""

    entity_id: str
    service_group: str
    station: str
    train_type: str
    n_events: int
    n_service_dates: int
    reasons: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "service_group": self.service_group,
            "station": self.station,
            "train_type": self.train_type,
            "n_events": self.n_events,
            "n_service_dates": self.n_service_dates,
            "reasons": list(self.reasons),
        }


# --- enumeration ------------------------------------------------------------

_ENUMERATE_SQL = """
WITH ev AS (
    SELECT {group_sql}  AS service_group,
           station_name AS station,
           train_type,
           {date_sql}    AS service_date,
           delay_in_min,
           (coalesce(arrival_is_canceled, false)
            OR coalesce(departure_is_canceled, false)) AS cancelled,
           id            AS stop_id
    FROM {events}
    WHERE {where}
),
joined AS (
    SELECT ev.*, {families} FROM ev {cause_join}
)
SELECT service_group,
       station,
       min(train_type)                                              AS train_type,
       count(*)                                                     AS n_events,
       count(delay_in_min)                                          AS n_delay_obs,
       count(DISTINCT service_date)                                 AS n_service_dates,
       min(service_date)                                            AS first_seen,
       max(service_date)                                            AS last_seen,
       avg(delay_in_min)                                            AS mean_delay_min,
       avg(CASE WHEN delay_in_min IS NULL THEN NULL
                WHEN delay_in_min >= {late} THEN 1.0 ELSE 0.0 END)  AS share_late_5,
       avg(CASE WHEN cancelled THEN 1.0 ELSE 0.0 END)               AS cancel_rate,
       count(families)                                              AS n_attributed,
       count(DISTINCT CASE WHEN coalesce(list_contains(families, 'works'), false)
                             OR coalesce(list_contains(families, 'weather'), false)
                           THEN service_date END)                   AS affected_days
FROM joined
GROUP BY 1, 2
ORDER BY 1, 2
"""


def event_source(months: Sequence[str]) -> str:
    """SQL relation expression for the processed monthly files.

    A relation *expression* rather than a view, so tests can hand the same
    functions the name of a synthetic table and exercise the real SQL offline.
    """
    return "read_parquet([" + ",".join(f"'{month_url(m)}'" for m in months) + "])"


def cause_source(cache_dir: Path) -> str | None:
    """SQL relation expression over the cause day shards, or None if unbuilt."""
    shards = sorted((cache_dir / "causes").glob("*.parquet"))
    if not shards:
        return None
    return "read_parquet([" + ",".join(f"'{p}'" for p in shards) + "])"


def enumerate_entities(
    con: duckdb.DuckDBPyConnection,
    *,
    events: str,
    causes: str | None = None,
    window: tuple[dt.date, dt.date] | None = None,
    region_sql: str = "TRUE",
    universe: Sequence[str] | None = None,
    min_service_dates: int = MIN_SERVICE_DATES,
) -> tuple[list[Entity], list[Rejection]]:
    """Every candidate (service_group, station) pair, split into pass and fail.

    ``region_sql`` is applied in SQL because it bounds the scan -- enumerating
    every pair in Germany to reject most of them costs the whole file. The
    station universe is applied *in Python* instead, precisely so that a pair
    dropped for being outside the pinned basis says so in the rejection log
    rather than vanishing. Those are different kinds of exclusion and the log is
    the only place the difference is visible.

    Rejection reasons accumulate: a pair can be both thin and outside the
    universe, and recording only the first would make the log's counts depend on
    the order the checks happen to run in.
    """
    # Real months carry rows with a null station or a null final destination --
    # no synthetic fixture produced one, and entity_id cannot be formed from it.
    # Excluded in SQL rather than skipped in Python: a row with no station is not
    # a rejected entity, it is not an entity at all, and putting it in the
    # rejection log would misreport what the log counts.
    where = [region_sql, "station_name IS NOT NULL", "final_destination_station IS NOT NULL"]
    if window is not None:
        start, end = window
        where.append(f"{SERVICE_DATE_SQL} >= DATE '{start.isoformat()}'")
        where.append(f"{SERVICE_DATE_SQL} <= DATE '{end.isoformat()}'")

    sql = _ENUMERATE_SQL.format(
        group_sql=SERVICE_GROUP_SQL,
        date_sql=SERVICE_DATE_SQL,
        events=events,
        where=" AND ".join(where),
        families="c.families AS families" if causes else "NULL::VARCHAR[] AS families",
        cause_join=f"LEFT JOIN {causes} c ON c.stop_id = ev.stop_id" if causes else "",
        late=LATE_THRESHOLD_MIN,
    )

    allowed = set(universe) if universe is not None else None
    qualifying: list[Entity] = []
    rejected: list[Rejection] = []
    for row in con.execute(sql).fetchall():
        (
            service_group,
            station,
            train_type,
            n_events,
            n_delay_obs,
            n_service_dates,
            first_seen,
            last_seen,
            mean_delay,
            share_late_5,
            cancel_rate,
            n_attributed,
            affected_days,
        ) = row
        eid = entity_id(service_group, station)
        reasons: list[str] = []
        if n_service_dates < min_service_dates:
            reasons.append(REASON_THIN)
        if not n_delay_obs:
            reasons.append(REASON_NO_DELAY)
        if allowed is not None and station not in allowed:
            reasons.append(REASON_OUTSIDE_UNIVERSE)
        if reasons:
            rejected.append(
                Rejection(
                    entity_id=eid,
                    service_group=service_group,
                    station=station,
                    train_type=train_type,
                    n_events=n_events,
                    n_service_dates=n_service_dates,
                    reasons=tuple(sorted(reasons)),
                )
            )
            continue
        qualifying.append(
            Entity(
                entity_id=eid,
                service_group=service_group,
                station=station,
                train_type=train_type,
                n_events=n_events,
                n_service_dates=n_service_dates,
                first_seen=first_seen,
                last_seen=last_seen,
                mean_delay_min=float(mean_delay),
                share_late_5=float(share_late_5 or 0.0),
                cancel_rate=float(cancel_rate or 0.0),
                n_attributed=int(n_attributed),
                affected_days=int(affected_days),
            )
        )
    qualifying.sort(key=lambda e: e.entity_id)
    rejected.sort(key=lambda r: r.entity_id)
    return qualifying, rejected


# --- curation ---------------------------------------------------------------


@dataclass(frozen=True)
class Curation:
    """The selected set plus a report of which quotas were actually met."""

    selected: tuple[Entity, ...]
    report: dict

    @property
    def unmet(self) -> list[str]:
        return list(self.report["unmet"])


def _priority(entity: Entity) -> tuple:
    """Rank within a bucket: best-observed first, id as the final tiebreak.

    ``entity_id`` last is what makes the whole curation reproducible -- two
    pairs with identical support must still have a total order, and it must not
    be the order DuckDB returned them in.
    """
    return (-entity.n_service_dates, -entity.n_events, entity.entity_id)


def _build_pools(entities: Sequence[Entity]) -> dict[str, dict[str, list[Entity]]]:
    """station -> train_type -> candidates, worst-first so ``pop()`` is best."""
    pools: dict[str, dict[str, list[Entity]]] = {}
    for entity in sorted(entities, key=_priority, reverse=True):
        pools.setdefault(entity.station, {}).setdefault(entity.train_type, []).append(entity)
    return pools


def _round_fill(
    pools: dict[str, dict[str, list[Entity]]],
    state: dict,
    want: int,
    *,
    station_order: Sequence[str],
    max_per_station: int,
    type_cap: int,
) -> int:
    """Deficit round-robin: one pick per station per round, in station order.

    Round-based rather than "always take the globally best remaining" because
    the quota *is* the spread. Sorting by support and truncating gives 3,000
    entities at a dozen stations; taking one per station per round gives the
    same support ranking inside each station and a flat distribution across
    them, which is the only shape the station-level context channel can learn
    from. Rounds also keep it O(max_per_station x stations) rather than
    O(target x buckets) -- 30 x 400 instead of 3,000 x 6,000.

    Within a station the train type with the fewest picks so far goes first, and
    a type already over ``type_cap`` is deprioritised but not blocked, so a
    catchment dominated by S-Bahn can still reach the target.
    """
    taken = 0
    for round_index in range(max_per_station):
        if taken >= want:
            break
        for station in station_order:
            if taken >= want:
                break
            if station not in pools:
                continue
            picked_here = state["per_station"].get(station, 0)
            if picked_here > round_index or picked_here >= max_per_station:
                continue
            best_type: str | None = None
            best_rank: tuple | None = None
            for train_type, bucket in pools[station].items():
                while bucket and bucket[-1].entity_id in state["selected_ids"]:
                    bucket.pop()
                if not bucket:
                    continue
                over_cap = 1 if state["per_type"].get(train_type, 0) >= type_cap else 0
                rank = (over_cap, state["per_type"].get(train_type, 0), train_type)
                if best_rank is None or rank < best_rank:
                    best_rank, best_type = rank, train_type
            if best_type is None:
                continue
            entity = pools[station][best_type].pop()
            state["selected"].append(entity)
            state["selected_ids"].add(entity.entity_id)
            state["per_station"][station] = picked_here + 1
            state["per_type"][best_type] = state["per_type"].get(best_type, 0) + 1
            if best_rank[0]:
                state["over_type_cap"] += 1
            taken += 1
    return taken


def curate(
    entities: Sequence[Entity],
    *,
    target: int = DEFAULT_TARGET,
    min_stations: int = MIN_STATIONS,
    max_per_station: int = MAX_PER_STATION,
    max_type_share: float = MAX_TYPE_SHARE,
    min_affected_share: float = MIN_AFFECTED_SHARE,
    strict: bool = False,
) -> Curation:
    """Apply the quota to the qualifying set. Deterministic, no RNG.

    Three passes, in this order because each one's constraint is harder to
    satisfy than the next:

      A. **Station floor.** One entity from each of the first ``min_stations``
         stations. A floor rather than a consequence of the round-robin: when
         ``target`` is small the round-robin alone would fill from the busiest
         stations and stop.
      B. **Regime quota.** Fill to ``min_affected_share`` from entities that
         lived through a works or weather period. Second, because affected
         entities are the scarce resource -- spending the budget on them first
         is the only way the quota is reachable at all.
      C. **General fill** to ``target``.

    Every pass respects the per-station cap and shares the same counters, so the
    result is one quota rather than three overlapping ones. Stations are visited
    in descending total support: when the target cannot cover every station, the
    ones that get covered are the ones with the most history behind them.
    """
    entities = sorted(entities, key=lambda e: e.entity_id)
    station_events: dict[str, int] = {}
    for entity in entities:
        station_events[entity.station] = station_events.get(entity.station, 0) + entity.n_events
    station_order = sorted(station_events, key=lambda s: (-station_events[s], s))

    state = {
        "selected": [],
        "selected_ids": set(),
        "per_station": {},
        "per_type": {},
        "over_type_cap": 0,
    }
    type_cap = max(1, math.ceil(max_type_share * target))
    all_pools = _build_pools(entities)
    affected_pools = _build_pools([e for e in entities if e.is_regime_affected])

    _round_fill(
        all_pools,
        state,
        min(min_stations, target),
        station_order=station_order,
        max_per_station=1,
        type_cap=type_cap,
    )
    affected_need = math.ceil(min_affected_share * target) - sum(
        1 for e in state["selected"] if e.is_regime_affected
    )
    if affected_need > 0:
        _round_fill(
            affected_pools,
            state,
            min(affected_need, target - len(state["selected"])),
            station_order=station_order,
            max_per_station=max_per_station,
            type_cap=type_cap,
        )
    _round_fill(
        all_pools,
        state,
        target - len(state["selected"]),
        station_order=station_order,
        max_per_station=max_per_station,
        type_cap=type_cap,
    )

    selected: list[Entity] = sorted(state["selected"], key=lambda e: e.entity_id)
    n_affected = sum(1 for e in selected if e.is_regime_affected)
    affected_share = n_affected / len(selected) if selected else 0.0
    per_station = state["per_station"]
    per_type = state["per_type"]

    unmet: list[str] = []
    if len(selected) < target:
        unmet.append("target")
    if len(per_station) < min_stations:
        unmet.append("min_stations")
    if affected_share < min_affected_share:
        unmet.append("min_affected_share")
    if per_type and max(per_type.values()) > type_cap:
        unmet.append("max_type_share")

    report = {
        "target": target,
        "selected": len(selected),
        "candidates": len(entities),
        "n_stations": len(per_station),
        "max_per_station_observed": max(per_station.values()) if per_station else 0,
        "per_train_type": dict(sorted(per_type.items())),
        "type_cap": type_cap,
        "over_type_cap_picks": state["over_type_cap"],
        "n_regime_affected": n_affected,
        "affected_share": round(affected_share, 4),
        "quotas": {
            "min_stations": min_stations,
            "max_per_station": max_per_station,
            "max_type_share": max_type_share,
            "min_affected_share": min_affected_share,
        },
        "unmet": unmet,
    }
    if strict and unmet:
        raise ValueError(f"curation quotas unmet: {unmet} -- report={report}")
    return Curation(tuple(selected), report)


# --- emission ---------------------------------------------------------------


def entities_manifest(
    qualifying: Sequence[Entity],
    rejected: Sequence[Rejection],
    *,
    curation: Curation | None = None,
    provenance: dict | None = None,
) -> dict:
    """The entities.json payload, content-hashed over everything but the hash."""
    payload: dict = {
        "schema": "db_route/entities/1",
        "provenance": provenance or {},
        "thresholds": {
            "min_service_dates": MIN_SERVICE_DATES,
            "late_threshold_min": LATE_THRESHOLD_MIN,
            "regime_min_days": REGIME_MIN_DAYS,
        },
        "counts": {
            "candidates": len(qualifying) + len(rejected),
            "qualifying": len(qualifying),
            "rejected": len(rejected),
        },
        "rejection_reasons": _reason_counts(rejected),
        "entities": [e.as_dict() for e in qualifying],
        "rejected": [r.as_dict() for r in rejected],
    }
    if curation is not None:
        payload["curation"] = {
            **curation.report,
            "entity_ids": [e.entity_id for e in curation.selected],
        }
    payload["content_hash"] = content_hash(payload)
    return payload


def _reason_counts(rejected: Sequence[Rejection]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for rejection in rejected:
        for reason in rejection.reasons:
            counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items()))


def write_entities(path: Path, manifest: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return path


def read_entities(path: Path) -> list[Entity]:
    """Load the qualifying set back. Curation order is not preserved -- the
    curated subset is a list of ids in the manifest, so a caller that wants it
    filters on ``curation.entity_ids`` rather than trusting list order."""
    manifest = json.loads(path.read_text())
    return [
        Entity(
            entity_id=row["entity_id"],
            service_group=row["service_group"],
            station=row["station"],
            train_type=row["train_type"],
            n_events=row["n_events"],
            n_service_dates=row["n_service_dates"],
            first_seen=dt.date.fromisoformat(row["first_seen"]),
            last_seen=dt.date.fromisoformat(row["last_seen"]),
            mean_delay_min=row["mean_delay_min"],
            share_late_5=row["share_late_5"],
            cancel_rate=row["cancel_rate"],
            n_attributed=row["n_attributed"],
            affected_days=row["affected_days"],
        )
        for row in manifest["entities"]
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enumerate and curate db_route entities.")
    parser.add_argument("--months", default="", help="YYYY-MM,YYYY-MM inclusive range")
    parser.add_argument("--start", default="", help="first service date (default: all)")
    parser.add_argument("--end", default="", help="last service date (default: all)")
    parser.add_argument("--cache", default=Path("~/.cache/db_route").expanduser(), type=Path)
    parser.add_argument("--out", default=None, type=Path)
    parser.add_argument("--target", type=int, default=DEFAULT_TARGET)
    parser.add_argument(
        "--region-sql",
        default="",
        help="SQL predicate bounding the scan; defaults to the catchment EVA list",
    )
    parser.add_argument("--no-universe", action="store_true", help="skip the pinned-basis check")
    args = parser.parse_args(argv)

    months = months_between(*args.months.split(",")) if args.months else []
    if not months:
        parser.error("--months is required, e.g. --months 2025-11,2026-08")
    window = None
    if args.start and args.end:
        window = (dt.date.fromisoformat(args.start), dt.date.fromisoformat(args.end))

    universe = None
    universe_path = args.cache / "station_universe.json"
    if not args.no_universe and universe_path.exists():
        universe = json.loads(universe_path.read_text())["stations"]

    # The scan bound comes from facts.build_catchment by default. It filters on
    # `eva` rather than on the station name for the same reason facts.py does:
    # the dataset carries several spellings of the same station and only the EVA
    # number is a key.
    region_sql = args.region_sql
    catchment_path = args.cache / "catchment_evas.json"
    if not region_sql:
        if not catchment_path.exists():
            parser.error(
                f"no {catchment_path} -- run `facts.py catchment` or pass --region-sql"
            )
        evas = json.loads(catchment_path.read_text())["evas"]
        region_sql = "eva IN (" + ",".join(f"'{e}'" for e in evas) + ")"

    con = connect(memory_limit="8GB")
    try:
        qualifying, rejected = enumerate_entities(
            con,
            events=event_source(months),
            causes=cause_source(args.cache),
            window=window,
            region_sql=region_sql,
            universe=universe,
        )
    finally:
        con.close()

    curation = curate(qualifying, target=args.target)
    manifest = entities_manifest(
        qualifying,
        rejected,
        curation=curation,
        provenance={
            "months": months,
            "window": [window[0].isoformat(), window[1].isoformat()] if window else None,
            "region_sql": args.region_sql or f"catchment: {catchment_path}",
            "cause_shards": bool(cause_source(args.cache)),
            "station_universe": len(universe) if universe else None,
        },
    )
    out = args.out or (args.cache / "entities.json")
    write_entities(out, manifest)
    print(
        f"entities: {len(qualifying):,} qualifying, {len(rejected):,} rejected "
        f"({manifest['rejection_reasons']}), curated {len(curation.selected):,} "
        f"over {curation.report['n_stations']} stations -> {out}",
        flush=True,
    )
    if curation.unmet:
        print(f"  unmet quotas: {curation.unmet}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
