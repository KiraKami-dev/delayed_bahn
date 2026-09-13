"""One pipeline, four profiles: the shared body of the ``error404/db-route-*`` connectors.

The four dataset ids differ in exactly one object, a ``profiles.TimelineProfile``,
which says how much history precedes each anchor and at what resolution. Every
other decision -- which entities, which anchors, which labels, which split --
is made once, here, from the same inputs, so the four datasets are a controlled
experiment rather than four datasets. ``artifact_bundle_sha`` on every record
is how a consumer checks that claim instead of trusting it.

The two connector stages map onto the code like this:

    download  -> make sure the local fact cache exists: monthly parquet files,
                 per-day cause and notice shards, the three hourly fact tables.
                 This is the only stage that may touch the network.
    convert   -> enumerate and curate entities, place anchors, compute labels,
                 slice one window per (entity, anchor), attach the dated
                 disruption notices, and assemble the TimeFDataset. Local
                 DuckDB reads only.

The engine hands ``download`` a scratch directory that it deletes after a
successful build. The fact cache is 5.7 GB of monthly archive plus a day-sharded
extraction that took a Nebius job to produce, so it lives at ``$DB_ROUTE_CACHE``
(default ``~/.cache/db_route``) and the scratch directory is ignored. That is a
deliberate departure from the contract's letter and it is what keeps a rebuild
at twenty seconds instead of an hour.

Knobs, all environment variables, all read at build time:

    DB_ROUTE_CACHE     where the fact cache lives
    DB_ROUTE_ENTITIES  how many (service, station) entities to curate (default 500)
    DB_ROUTE_MONTHS    YYYY-MM,YYYY-MM inclusive range; default: every local month
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

# The domain code is the ``db_route`` feature package, kept flat so that the
# training side can import it the same way. Resolve through the symlink that
# puts this org folder under ``timenet_connectors/datasets/``.
FEATURES = Path(__file__).resolve().parents[3] / "src" / "features" / "db_route"
if str(FEATURES) not in sys.path:
    sys.path.insert(0, str(FEATURES))

import anchors as A  # noqa: E402
import build as B  # noqa: E402
import entities as E  # noqa: E402
import facts as F  # noqa: E402
import labels as L  # noqa: E402
import profiles as P  # noqa: E402
from connector import RecordInput, build_dataset  # noqa: E402
from resample import FactCache, anchor_midnight  # noqa: E402
from sources import connect  # noqa: E402

CACHE_ENV = "DB_ROUTE_CACHE"
ENTITIES_ENV = "DB_ROUTE_ENTITIES"
MONTHS_ENV = "DB_ROUTE_MONTHS"
DEFAULT_ENTITIES = 500

# The archive covers ~100 stations from 2024-07 and every station from this
# date. Anchors start one longest-context after it (anchors.plan_anchors), so no
# layer of any profile straddles the expansion.
COVERAGE_START = dt.date(2025, 11, 2)

# A busy station has hundreds of overlapping notices in a season. The eight
# highest-priority ones are the annotation; the rest is noise a reader would
# never get through either.
MAX_NOTICES_PER_RECORD = 8

# Two more sources, both free, both fetched once in download() and read from
# the cache in convert(). Absent (offline, or the API is down) the annotations
# are simply not emitted and the build is otherwise identical -- a consumer can
# tell from the schema which build it has.
#
#   OpenHolidays  per-Bundesland public and school holidays. 7 of 16 public
#                 holidays differ across our six regions and school holidays
#                 are staggered by weeks, so the state-level flag is real
#                 cross-region variance a national one would erase.
#   db-stations   EVA -> Bundesland, DS100, category (1-7) and footfall weight
#                 for all 5,388 stations; the join hub that turns a station
#                 name into everything else.
LAENDER = {
    "Bayern": "DE-BY", "Berlin": "DE-BE", "Hamburg": "DE-HH",
    "Nordrhein-Westfalen": "DE-NW", "Hessen": "DE-HE", "Baden-Württemberg": "DE-BW",
}
OPENHOLIDAYS = (
    "https://openholidaysapi.org/{kind}?countryIsoCode=DE&languageIsoCode=DE"
    "&validFrom={start}&validTo={end}&subdivisionCode={sub}"
)
DB_STATIONS = "https://cdn.jsdelivr.net/npm/db-stations@latest/full.json"


@dataclass(frozen=True)
class RawRefs:
    """What ``download`` hands to ``convert``: paths, never data."""

    cache: Path
    months: tuple[str, ...]
    fingerprint: str  # of the catchment EVA set; selects the cause/notice shards
    catchment: Path

    def month_files(self) -> list[str]:
        return F.month_sources(list(self.months), self.cache)

    def shards(self, kind: str) -> list[Path]:
        return sorted((self.cache / kind / self.fingerprint).glob("*.parquet"))


def default_cache() -> Path:
    return Path(os.environ.get(CACHE_ENV, str(Path.home() / ".cache" / "db_route")))


def _months(cache: Path) -> list[str]:
    spec = os.environ.get(MONTHS_ENV, "").strip()
    if spec:
        first, _, last = spec.partition(",")
        last = last or first
        out, cur = [], dt.date(int(first[:4]), int(first[5:7]), 1)
        end = dt.date(int(last[:4]), int(last[5:7]), 1)
        while cur <= end:
            out.append(cur.strftime("%Y-%m"))
            cur = (cur.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        return out
    local = sorted(p.stem.replace("data-", "") for p in (cache / "monthly").glob("data-*.parquet"))
    if not local:
        raise RuntimeError(
            f"no monthly files under {cache / 'monthly'} and {MONTHS_ENV} is unset; "
            "run `python facts.py all` once or set the range"
        )
    return local


def _sql_list(paths: list[str]) -> str:
    return "[" + ", ".join(f"'{p}'" for p in paths) + "]"


def _fetch(url: str, dest: Path) -> bool:
    """One idempotent GET to a file. False, not an exception, when the source is unreachable."""
    if dest.exists():
        return True
    import urllib.request  # noqa: PLC0415

    try:
        with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310 (fixed https hosts)
            dest.write_bytes(resp.read())
        return True
    except Exception as exc:  # noqa: BLE001 -- degrade, and say so
        print(f"external source unavailable, skipping: {url} ({exc})", file=sys.stderr)
        return False


def fetch_external(cache: Path, months: Sequence[str]) -> Path:
    """Holidays for the six Länder and the station join hub, into ``cache/external``."""
    ext = cache / "external"
    ext.mkdir(parents=True, exist_ok=True)
    start = f"{months[0]}-01"
    last = months[-1]
    end = (dt.date(int(last[:4]), int(last[5:7]), 28) + dt.timedelta(days=40)).isoformat()
    for sub in LAENDER.values():
        for kind in ("PublicHolidays", "SchoolHolidays"):
            _fetch(OPENHOLIDAYS.format(kind=kind, start=start, end=end, sub=sub), ext / f"{kind}_{sub}.json")
    _fetch(DB_STATIONS, ext / "db-stations.json")
    return ext


def download(_engine_cache_dir: Path) -> list[RawRefs]:
    """I/O stage: the fact cache exists when this returns. Idempotent."""
    cache = default_cache()
    cache.mkdir(parents=True, exist_ok=True)
    months = _months(cache)
    fetch_external(cache, months)
    catchment = cache / "catchment_evas.json"
    if not catchment.exists():
        # Network: StaDa/archive lookup of the station set. Munich is the
        # documented default; six regions is `python facts.py catchment --regions ...`.
        F.build_catchment(months[-1], catchment, regions=("munich",))
    meta = json.loads(catchment.read_text())
    evas = meta["evas"]
    fingerprint = F.catchment_fingerprint(evas)

    hourly = [cache / f"hourly_{g}.parquet" for g in ("station", "line", "pair")]
    if not all(p.exists() for p in hourly):
        # Shards before the all-station expansion would only ever describe the
        # ~100 hub stations, and the anchor window starts 120 days after it
        # anyway, so there is nothing to extract for those days.
        start = max(dt.date(int(months[0][:4]), int(months[0][5:7]), 1), COVERAGE_START)
        end = F.available_months(months)[-1]
        end_day = (dt.date(int(end[:4]), int(end[5:7]), 28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
        F.extract_range(start, end_day, cache, evas=evas)  # network, day-sharded, resumable
        F.build_facts(months, meta["stations"], cache, evas=evas)
    return [RawRefs(cache=cache, months=tuple(months), fingerprint=fingerprint, catchment=catchment)]


def _notices_by_station(con: Any, ref: RawRefs, stations: set[str]) -> dict[str, list[dict]]:
    """Dated disruption notices, materialised onto the stations they touched.

    A HIM notice is broadcast to every stop it affects (~55 per notice), so the
    shards carry one row per notice with its stop ids, and the stop id joins
    to the archive's ``id`` column. Grouping back to (station, notice) is what
    turns 79k attachments into one annotation per record per notice. Measured:
    the join over ten months of archive runs in under a minute.
    """
    shards = ref.shards("notices")
    if not shards:
        return {}
    con.execute("CREATE OR REPLACE TEMP TABLE _stations AS SELECT unnest(?::VARCHAR[]) AS station", [sorted(stations)])
    rows = con.execute(
        f"""
        WITH n AS (
            SELECT notice_id, category, priority,
                   CAST(valid_from AS TIMESTAMP) AS vf, CAST(valid_to AS TIMESTAMP) AS vt,
                   unnest(stop_ids) AS sid
            FROM read_parquet({_sql_list([str(p) for p in shards])})
        )
        -- A notice recurs in every day-shard it was live, sometimes with an
        -- extended valid_to or a changed priority. Aggregating with min/max
        -- makes the row deterministic and takes the widest window and the
        -- highest priority the operator ever gave it; any_value() made three
        -- identical builds disagree by a handful of notices.
        SELECT e.station_name, n.notice_id, min(n.category), min(n.vf),
               max(n.vt), min(n.priority)
        FROM n
        JOIN ev e ON e.id = n.sid
        JOIN _stations s ON s.station = e.station_name
        GROUP BY 1, 2
        ORDER BY 1, 2
        """
    ).fetchall()
    out: dict[str, list[dict]] = collections.defaultdict(list)
    for station, nid, cat, vf, vt, pr in rows:
        out[station].append(
            {"notice_id": nid, "category": cat or "", "valid_from": vf, "valid_to": vt, "priority": int(pr or 4)}
        )
    return out


def _notices_for(pool: list[dict], t0: dt.datetime, context_days: float) -> tuple[dict, ...]:
    lo = t0 - dt.timedelta(days=context_days)
    live = [n for n in pool if n["valid_from"] <= t0 and n["valid_to"] >= lo]
    live.sort(key=lambda n: (n["priority"], n["valid_from"], n["notice_id"]))
    return tuple(live[:MAX_NOTICES_PER_RECORD])


class Calendar:
    """What the two external sources say about one station on one travel week."""

    def __init__(self, ext: Path) -> None:
        self.public: dict[str, set[dt.date]] = {}
        self.school: dict[str, list[tuple[dt.date, dt.date]]] = {}
        for sub in LAENDER.values():
            pub = ext / f"PublicHolidays_{sub}.json"
            if pub.exists():
                self.public[sub] = {dt.date.fromisoformat(x["startDate"]) for x in json.loads(pub.read_text())}
            sch = ext / f"SchoolHolidays_{sub}.json"
            if sch.exists():
                self.school[sub] = sorted(
                    (dt.date.fromisoformat(x["startDate"]), dt.date.fromisoformat(x["endDate"]))
                    for x in json.loads(sch.read_text())
                )
        self.stations: dict[str, dict] = {}
        hub = ext / "db-stations.json"
        if hub.exists():
            for row in json.loads(hub.read_text()):
                if row.get("name"):
                    self.stations.setdefault(row["name"], row)

    def annotations(self, station: str, anchor: dt.date, horizon_days: int) -> list[tuple[str, Any]]:
        row = self.stations.get(station)
        out: list[tuple[str, Any]] = []
        if row is None:
            return out
        state = row.get("federalState") or ""
        out.append(("federal_state", state))
        if row.get("category") is not None:
            out.append(("station_category", int(row["category"])))
        if row.get("weight") is not None:
            out.append(("station_weight", float(row["weight"])))
        sub = LAENDER.get(state)
        if sub is None:
            return out
        horizon = [anchor + dt.timedelta(days=i) for i in range(horizon_days)]
        if sub in self.public:
            out.append(("horizon_public_holidays", sum(1 for d in horizon if d in self.public[sub])))
        periods = self.school.get(sub)
        if periods:
            inside = sum(1 for d in horizon if any(a <= d <= b for a, b in periods))
            out.append(("horizon_school_holiday_share", inside / len(horizon)))
            ahead = [(a - anchor).days for a, b in periods if a >= anchor]
            behind = [(anchor - b).days for a, b in periods if b <= anchor]
            in_one = any(a <= anchor <= b for a, b in periods)
            out.append(("days_to_school_holiday_start", 0 if in_one else min(ahead + [60], default=60)))
            out.append(("days_since_school_holiday_end", 0 if in_one else min(behind + [60], default=60)))
        return out


def convert(raw_refs: list[RawRefs], prof: P.TimelineProfile, metadata: Any) -> Any:
    """CPU stage: fact cache -> TimeFDataset for one profile."""
    ref = raw_refs[0]
    con = connect(threads=6, memory_limit="8GB")
    con.execute("SET enable_progress_bar=false; SET TimeZone='Europe/Berlin';")
    con.execute(f"CREATE VIEW ev AS SELECT * FROM read_parquet({_sql_list(ref.month_files())})")
    causes = ref.shards("causes")
    con.execute(f"CREATE VIEW cz AS SELECT * FROM read_parquet({_sql_list([str(p) for p in causes])})")
    universe = json.loads(ref.catchment.read_text())["stations"]

    first = dt.date(int(ref.months[0][:4]), int(ref.months[0][5:7]), 1)
    last_m = ref.months[-1]
    last = (dt.date(int(last_m[:4]), int(last_m[5:7]), 28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
    window = (max(first, COVERAGE_START), last)

    ents, _ = E.enumerate_entities(con, events="ev", causes="cz", window=window, universe=universe)
    target = int(os.environ.get(ENTITIES_ENV, DEFAULT_ENTITIES))
    selected = list(E.curate(ents, target=target).selected)
    anch = A.plan_anchors(selected, window=window, split_mode="both")
    specs = L.specs_from(selected, anch)
    ws = L.open_workspace(con, specs, events="ev", causes="cz", context_days=int(prof.context_days))
    labels = {(lab.entity_id, lab.anchor): lab for lab in L.compute_labels(ws)}
    notices = _notices_by_station(con, ref, {e.station for e in selected})
    calendar = Calendar(ref.cache / "external")

    # The shared artifacts, written so the bundle hash is over bytes on disk
    # that a reviewer can diff, not over an in-memory structure.
    art = ref.cache / "artifacts" / f"{ref.fingerprint}-{target}"
    art.mkdir(parents=True, exist_ok=True)
    (art / "entities.json").write_text(json.dumps([e.entity_id for e in selected], indent=0))
    (art / "anchors.json").write_text(
        json.dumps([[a.entity_id, a.anchor.isoformat(), a.split, a.index] for a in anch], indent=0)
    )
    # Targets only. The ``context`` slots cite statistics over the profile's own
    # window, so they legitimately differ between S and L; the hash is over what
    # must NOT differ -- which entities, which anchors, which answers.
    (art / "labels.json").write_text(
        json.dumps(
            [{k: v for k, v in labels[key].as_dict().items() if k != "context"} for key in sorted(labels)],
            indent=0,
        )
    )
    bundle_sha = B.artifact_bundle_sha([art / n for n in ("entities.json", "anchors.json", "labels.json")])

    fc = FactCache(ref.cache)
    by_entity = {e.entity_id: e for e in selected}
    items: list[RecordInput] = []
    skipped: collections.Counter = collections.Counter()
    for a in anch:
        label = labels.get((a.entity_id, a.anchor))
        if label is None:
            skipped["label not computable"] += 1
            continue
        entity = by_entity[a.entity_id]
        w = fc.window(entity, a.anchor, prof)
        reason = w.reject_reason()
        if reason:
            skipped[reason.split(":")[0]] += 1
            continue
        t0 = anchor_midnight(a.anchor)
        items.append(
            RecordInput(
                entity_id=a.entity_id,
                service_group=entity.service_group,
                station=entity.station,
                train_type=entity.train_type,
                anchor=a.anchor,
                window=w,
                label=label,
                split="test" if a.split.startswith("test") else a.split,
                split_cell=a.split,
                recency_weight=float(a.weight),
                notices=_notices_for(notices.get(entity.station, []), t0, prof.context_days),
                extra=tuple(calendar.annotations(entity.station, a.anchor, P.HORIZON_DAYS)),
            )
        )
    items.sort(key=lambda r: (r.entity_id, r.anchor))
    print(
        f"{prof.profile_id}: {len(ents):,} entities -> {len(selected)} curated -> {len(anch)} anchors "
        f"-> {len(items)} records ({sum(skipped.values())} skipped: {dict(skipped)}); "
        f"notices attached to {sum(1 for r in items if r.notices)} records; "
        f"calendar on {sum(1 for r in items if r.extra)}; bundle {bundle_sha[:12]}",
        file=sys.stderr, flush=True,
    )
    return build_dataset(prof, items, metadata=metadata, bundle_sha=bundle_sha)
