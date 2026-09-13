#!/usr/bin/env python3
"""
Extract live Deutsche Bahn data and emit it in the schema of
huggingface.co/datasets/piebro/deutsche-bahn-data (monthly_processed_data).

Two DB APIs are used:
  * Timetables  -> the actual stop events (plan + changes)
  * RIS::Stations -> canonical station names, to fill `station_name`
                     (the Timetables XML name goes to `xml_station_name`)

One output row = one train stopping at one station. That is the unit of the
HF dataset; it is NOT a journey. A "Munich -> Frankfurt" query is therefore
expressed as: all departures from the origin station whose onward route path
contains the destination. See JourneyFilter.

Credentials come from the environment:
    export DB_CLIENT_ID=...
    export DB_API_KEY=...

You give it a place, a destination, a date (DD/MM/YYYY) and a time (HH:MM);
it gives you HF-schema rows.

Examples
--------
# Munich -> Frankfurt, 13 September 2026, from 08:00, three hours:
python db_hf_extract.py --from "München Hbf" --to "Frankfurt" \
    --date 13/09/2026 --time 08:00 -o muc_fra.parquet

# Everything leaving Munich right now:
python db_hf_extract.py --from "München Hbf" -o live.parquet

# Longer window, including the S-Bahn level:
python db_hf_extract.py --from "München Hbf" --to Augsburg \
    --date 13/09/2026 --time 06:00 --window 6 --sub-stations -o out.jsonl
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Iterable, Iterator, Sequence
from zoneinfo import ZoneInfo

log = logging.getLogger("db_hf")

MARKETPLACE = "https://apis.deutschebahn.com/db-api-marketplace/apis"
BERLIN = ZoneInfo("Europe/Berlin")

# Timetables timestamps are local Berlin time, format YYMMDDHHmm.
TS_FORMAT = "%y%m%d%H%M"


# --------------------------------------------------------------------------
# Output schema
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StopRecord:
    """One train's stop at one station, in the HF dataset's column order."""

    station_name: str | None  # canonical name (RIS::Stations)
    xml_station_name: str | None  # name as given in the Timetables XML
    eva: str | None  # zero-prefixed EVA, e.g. "08000261"
    train_number: str | None  # tl@n   e.g. "592"
    line_number: str | None  # ar/dp@l e.g. "RB23"; null for ICE/IC/EC
    final_destination_station: str | None
    delay_in_min: int | None
    time: datetime | None  # actual time: departure if present, else arrival
    arrival_is_canceled: bool
    departure_is_canceled: bool
    train_type: str | None  # tl@c   e.g. "ICE", "S", "RE"
    train_line_ride_id: str | None
    train_line_station_num: int | None
    arrival_planned_time: datetime | None
    arrival_change_time: datetime | None
    departure_planned_time: datetime | None
    departure_change_time: datetime | None
    id: str | None  # the raw Timetables stop id

    COLUMNS = (
        "station_name",
        "xml_station_name",
        "eva",
        "train_number",
        "line_number",
        "final_destination_station",
        "delay_in_min",
        "time",
        "arrival_is_canceled",
        "departure_is_canceled",
        "train_type",
        "train_line_ride_id",
        "train_line_station_num",
        "arrival_planned_time",
        "arrival_change_time",
        "departure_planned_time",
        "departure_change_time",
        "id",
    )


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------


class DBError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Station:
    """A station as the Timetables /station endpoint reports it."""

    eva: str
    name: str
    ds100: str
    meta: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return f"{self.name} (EVA {self.eva}, {self.ds100})"


@dataclass(frozen=True, slots=True)
class Query:
    """What the user asked for, in their own terms."""

    origin: str  # station name, DS100 or bare EVA
    destination: str | None  # substring of any station on the onward route
    day: date
    start_hour: int
    window_hours: int

    @property
    def hours(self) -> range:
        return range(self.start_hour, min(24, self.start_hour + self.window_hours))

    def describe(self) -> str:
        via = f" via {self.destination}" if self.destination else ""
        last = min(23, self.start_hour + self.window_hours - 1)
        return (
            f"{self.origin}{via} on {self.day:%d/%m/%Y}, "
            f"{self.start_hour:02d}:00-{last:02d}:59"
        )


@dataclass
class Credentials:
    client_id: str
    api_key: str

    @classmethod
    def from_env(cls) -> "Credentials":
        cid = os.environ.get("DB_CLIENT_ID")
        key = os.environ.get("DB_API_KEY")
        if not cid or not key:
            raise DBError(
                "Set DB_CLIENT_ID and DB_API_KEY. Get them from "
                "developers.deutschebahn.com and subscribe your application "
                "to both the Timetables and RIS::Stations APIs."
            )
        return cls(cid, key)

    def headers(self, accept: str) -> dict[str, str]:
        return {
            "DB-Client-Id": self.client_id,
            "DB-Api-Key": self.api_key,
            "Accept": accept,
        }


class _HttpClient:
    """Thin GET wrapper with retry on 429/5xx."""

    accept = "application/xml"

    def __init__(self, creds: Credentials, min_interval: float = 0.4):
        self.creds = creds
        self.min_interval = min_interval  # crude rate limit
        self._last_call = 0.0

    def _throttle(self) -> None:
        wait = self.min_interval - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def get(self, path: str, attempts: int = 3) -> bytes:
        url = f"{MARKETPLACE}/{path}"
        req = urllib.request.Request(url, headers=self.creds.headers(self.accept))
        for attempt in range(1, attempts + 1):
            self._throttle()
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return resp.read()
            except urllib.error.HTTPError as exc:
                body = exc.read()[:200].decode("utf-8", "replace")
                if exc.code in (429, 500, 502, 503, 504) and attempt < attempts:
                    backoff = 2**attempt
                    log.warning("HTTP %s on %s, retrying in %ss", exc.code, path, backoff)
                    time.sleep(backoff)
                    continue
                raise DBError(f"HTTP {exc.code} for {url}: {body}") from exc
        raise DBError(f"gave up on {url}")


class TimetablesClient(_HttpClient):
    """Timetables v1. Returns XML."""

    accept = "application/xml"
    base = "timetables/v1"

    def plan(self, eva: str, when: datetime) -> ET.Element:
        """Planned stops for a single hour slice. Static, safe to cache."""
        path = f"{self.base}/plan/{eva}/{when:%y%m%d}/{when:%H}"
        return ET.fromstring(self.get(path))

    def full_changes(self, eva: str) -> ET.Element:
        """All currently known deviations for this station."""
        return ET.fromstring(self.get(f"{self.base}/fchg/{eva}"))

    def recent_changes(self, eva: str) -> ET.Element:
        """Only the last ~2 minutes of deviations. Cheap; use for polling."""
        return ET.fromstring(self.get(f"{self.base}/rchg/{eva}"))

    def find_stations(self, pattern: str) -> list["Station"]:
        """Resolve a station name (or DS100 code) to EVA numbers."""
        quoted = urllib.parse.quote(pattern)
        root = ET.fromstring(self.get(f"{self.base}/station/{quoted}"))
        return [
            Station(
                eva=element.get("eva", ""),
                name=element.get("name", ""),
                ds100=element.get("ds100", ""),
                meta=[m for m in (element.get("meta") or "").split("|") if m],
            )
            for element in root.findall("station")
            if element.get("eva")
        ]


class RisStationsClient(_HttpClient):
    """RIS::Stations v1. Needs the DB vendor media type, returns JSON."""

    accept = "application/vnd.de.db.ris+json"
    base = "ris-stations/v1"

    def __init__(self, creds: Credentials):
        super().__init__(creds)
        self._cache: dict[str, str | None] = {}

    def canonical_name(self, eva: str) -> str | None:
        """Official long name for an EVA number, or None if unknown."""
        if eva in self._cache:
            return self._cache[eva]
        import json

        name: str | None = None
        try:
            raw = self.get(f"{self.base}/stop-places/by-key?keyType=EVA&key={eva}")
            places = json.loads(raw).get("stopPlaces") or []
            if places:
                name = places[0].get("names", {}).get("DE", {}).get("nameLong")
        except DBError as exc:
            log.warning("RIS lookup failed for %s: %s", eva, exc)
        self._cache[eva] = name
        return name


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------


def parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw, TS_FORMAT).replace(tzinfo=BERLIN)
    except ValueError:
        log.debug("unparseable timestamp %r", raw)
        return None


def split_stop_id(stop_id: str) -> tuple[str | None, int | None]:
    """
    Timetables stop ids look like  <rideId>-<YYMMDDHHmm>-<stationNum>
    with a possibly negative rideId, e.g. -1291355389794506596-2406302318-13.
    Split from the right so the leading minus survives.
    """
    parts = stop_id.rsplit("-", 2)
    if len(parts) != 3:
        return None, None
    ride_id, _departure_stamp, station_num = parts
    try:
        return ride_id, int(station_num)
    except ValueError:
        return ride_id, None


def last_of_path(raw: str | None) -> str | None:
    """ppth/cpth is a pipe-separated route; the last entry is the terminus."""
    if not raw:
        return None
    stops = [s for s in raw.split("|") if s]
    return stops[-1] if stops else None


def path_stations(raw: str | None) -> list[str]:
    return [s for s in (raw or "").split("|") if s]


def normalize(name: str) -> str:
    """
    Fold a station name for comparison.

    DB writes the same place many ways: 'Frankfurt(Main)Hbf',
    'Frankfurt(M) Flughafen Fernbf', 'Frankfurt (Main) Hbf'. Stripping
    everything but letters and digits lets a user type 'Frankfurt Main Hbf'
    and still match.
    """
    return "".join(ch for ch in name.casefold() if ch.isalnum())


@dataclass
class _Stop:
    """Mutable working copy of one <s> element while plan and changes merge."""

    stop_id: str
    tl: dict[str, str] = field(default_factory=dict)
    ar: dict[str, str] = field(default_factory=dict)
    dp: dict[str, str] = field(default_factory=dict)

    def absorb(self, element: ET.Element) -> None:
        """Overlay attributes from a plan or change <s> element."""
        for tag, target in (("tl", self.tl), ("ar", self.ar), ("dp", self.dp)):
            found = element.find(tag)
            if found is not None:
                target.update({k: v for k, v in found.attrib.items() if v != ""})


class StationSnapshot:
    """Accumulates plan hours and change feeds for ONE station."""

    def __init__(self, eva: str, xml_station_name: str | None = None):
        self.eva = eva
        self.xml_station_name = xml_station_name
        self.stops: dict[str, _Stop] = {}

    def absorb(self, timetable: ET.Element, create: bool = True) -> "StationSnapshot":
        """
        Merge a <timetable> document.

        `create=True` for /plan, which defines which stops exist in the window.
        `create=False` for /fchg and /rchg: those feeds cover the whole day, so
        letting them create stops would pull in trains outside the requested
        hours with no plan data attached (no <tl>, no route path).
        """
        if timetable.get("station"):
            self.xml_station_name = timetable.get("station")
        for element in timetable.findall("s"):
            stop_id = element.get("id")
            if not stop_id:
                continue
            stop = self.stops.get(stop_id)
            if stop is None:
                if not create:
                    continue
                stop = self.stops.setdefault(stop_id, _Stop(stop_id))
            stop.absorb(element)
        return self

    # -- record construction ------------------------------------------------

    def to_records(self, station_name: str | None = None) -> list[StopRecord]:
        return [self._build(stop, station_name) for stop in self.stops.values()]

    def _build(self, stop: _Stop, station_name: str | None) -> StopRecord:
        ar, dp, tl = stop.ar, stop.dp, stop.tl

        arrival_planned = parse_ts(ar.get("pt"))
        arrival_change = parse_ts(ar.get("ct")) or arrival_planned
        departure_planned = parse_ts(dp.get("pt"))
        departure_change = parse_ts(dp.get("ct")) or departure_planned

        # The HF dataset reports the departure event when there is one,
        # otherwise the arrival (i.e. at a terminus).
        if departure_planned is not None:
            actual, planned = departure_change, departure_planned
        else:
            actual, planned = arrival_change, arrival_planned

        delay = None
        if actual is not None and planned is not None:
            delay = round((actual - planned).total_seconds() / 60)

        # Terminus: the end of the onward path, or this station if the train
        # terminates here.
        destination = last_of_path(dp.get("cpth") or dp.get("ppth"))
        if destination is None:
            destination = self.xml_station_name

        ride_id, station_num = split_stop_id(stop.stop_id)

        return StopRecord(
            station_name=station_name or self.xml_station_name,
            xml_station_name=self.xml_station_name,
            eva=f"0{self.eva}" if not self.eva.startswith("0") else self.eva,
            train_number=tl.get("n"),
            line_number=dp.get("l") or ar.get("l"),
            final_destination_station=destination,
            delay_in_min=delay,
            time=actual,
            arrival_is_canceled=ar.get("cs") == "c",
            departure_is_canceled=dp.get("cs") == "c",
            train_type=tl.get("c"),
            train_line_ride_id=ride_id,
            train_line_station_num=station_num,
            arrival_planned_time=arrival_planned,
            arrival_change_time=arrival_change,
            departure_planned_time=departure_planned,
            departure_change_time=departure_change,
            id=stop.stop_id,
        )

    # -- filtering ----------------------------------------------------------

    def route_contains(self, stop_id: str, needle: str) -> bool:
        """True if the train's onward path passes through `needle`."""
        stop = self.stops.get(stop_id)
        if stop is None:
            return False
        path = path_stations(stop.dp.get("cpth") or stop.dp.get("ppth"))
        target = normalize(needle)
        return any(target in normalize(station) for station in path)


# --------------------------------------------------------------------------
# Collection
# --------------------------------------------------------------------------


def hour_slices(day: date, first: int, last: int) -> Iterator[datetime]:
    for hour in range(first, last + 1):
        yield datetime(day.year, day.month, day.day, hour, tzinfo=BERLIN)


def collect_station(
    timetables: TimetablesClient,
    eva: str,
    slices: Sequence[datetime],
    with_changes: bool = True,
) -> StationSnapshot:
    """Fetch plan for each hour slice, then overlay live changes."""
    snapshot = StationSnapshot(eva)
    beyond_horizon: list[datetime] = []
    for when in slices:
        try:
            snapshot.absorb(timetables.plan(eva, when))
        except DBError as exc:
            if "HTTP 404" in str(exc):
                beyond_horizon.append(when)
            else:
                log.warning("plan %s %s: %s", eva, when, exc)
    if beyond_horizon:
        log.warning(
            "%s: no plan published yet for %d hour slice(s) from %s onward "
            "(the timetable horizon is roughly 18 hours)",
            eva,
            len(beyond_horizon),
            beyond_horizon[0].strftime("%Y-%m-%d %H:00"),
        )
    if with_changes:
        try:
            snapshot.absorb(timetables.full_changes(eva), create=False)
        except DBError as exc:
            log.warning("fchg %s: %s", eva, exc)
    log.info("%s: %d stops over %d hour slices", eva, len(snapshot.stops), len(slices))
    return snapshot


ARCHIVE_REPO = "hf://datasets/piebro/deutsche-bahn-data/monthly_processed_data"
ARCHIVE_FIRST = date(2024, 7, 1)


def archive_url(day: date) -> str:
    return f"{ARCHIVE_REPO}/data-{day:%Y-%m}.parquet"


def load_archive(query: Query, departures_only: bool, station_name: str | None = None):
    """
    Past dates come from the collected archive, not the API.

    The Timetables API keeps only a rolling window, so anything before today
    is served from piebro/deutsche-bahn-data, which has the identical schema.
    Needs `pip install huggingface_hub`.

    The monthly files are large, so the station and day filters are pushed
    down into the parquet reader — loading a whole month into memory will get
    the process OOM-killed on a laptop.

    One difference worth knowing: the archive stores each stop's
    `final_destination_station` but not the full route path, so a destination
    filter here matches the terminus only — it cannot see intermediate stops
    the way the live path filter can.
    """
    import pandas as pd

    if query.day < ARCHIVE_FIRST:
        raise DBError(f"the archive starts at {ARCHIVE_FIRST:%B %Y}")

    day_start = datetime(query.day.year, query.day.month, query.day.day)
    day_end = day_start + timedelta(days=1)

    name = station_name or query.origin
    filters = [
        [
            ("xml_station_name", "==", name),
            ("time", ">=", day_start),
            ("time", "<", day_end),
        ],
        [
            ("station_name", "==", name),
            ("time", ">=", day_start),
            ("time", "<", day_end),
        ],
    ]

    url = archive_url(query.day)
    log.info("reading archive for %s at %r (streams a monthly file)", query.day, name)
    try:
        frame = pd.read_parquet(url, filters=filters)
    except FileNotFoundError as exc:
        raise DBError(
            f"{query.day:%B %Y} is not in the archive yet. The API only covers "
            f"today and tomorrow, and the archive ends before this month, so "
            f"{query.day:%d/%m/%Y} falls in the gap between them and is not "
            f"available from any source."
        ) from exc
    except ImportError as exc:
        raise DBError("pip install huggingface_hub to read the archive") from exc

    if frame.empty:
        log.warning(
            "no rows for %r in the archive — the name must match exactly; "
            "try the DB spelling, e.g. 'Frankfurt(Main)Hbf'",
            name,
        )
        return frame

    frame = frame[frame["time"].dt.hour.isin(list(query.hours))]

    if query.destination:
        wanted = normalize(query.destination)
        before = len(frame)
        frame = frame[
            frame["final_destination_station"]
            .fillna("")
            .map(lambda n: wanted in normalize(n))
        ]
        log.info(
            "  %d of %d terminate at %r (archive matches terminus only, "
            "not intermediate stops)",
            len(frame),
            before,
            query.destination,
        )

    if departures_only:
        frame = frame[frame["departure_planned_time"].notna()]

    return frame.sort_values("time").reset_index(drop=True)


def resolve_origin(timetables: TimetablesClient, origin: str) -> Station:
    """
    Turn whatever the user typed into one Station.

    /station is a fairly literal lookup, not a fuzzy search: asking for
    "Berlin" returns "Berlin Attilastr.", a small S-Bahn halt, and nothing
    else. So when a bare city name is given we also try "<city> Hbf", and we
    say out loud which station was picked — a silently wrong station is the
    easiest way to get a clean-looking but meaningless dataset.
    """
    if origin.isdigit():
        return Station(eva=origin, name="", ds100="")

    candidates: list[Station] = []
    attempts = [origin]
    if "hbf" not in origin.casefold() and "hauptbahnhof" not in origin.casefold():
        attempts.append(f"{origin} Hbf")

    for attempt in attempts:
        try:
            candidates.extend(timetables.find_stations(attempt))
        except DBError as exc:
            log.debug("lookup %r failed: %s", attempt, exc)

    # de-duplicate, keeping order
    unique: dict[str, Station] = {}
    for station in candidates:
        unique.setdefault(station.eva, station)
    matches = list(unique.values())

    if not matches:
        raise DBError(
            f"no station matches {origin!r}. Try the full name as DB writes it, "
            f"e.g. 'Berlin Hbf' rather than 'Berlin'."
        )

    target = normalize(origin)
    exact = [s for s in matches if normalize(s.name) == target]
    hbf = [s for s in matches if "hbf" in s.name.casefold()]
    chosen = (exact or hbf or matches)[0]

    if normalize(chosen.name) != target:
        log.warning(
            "%r resolved to %s — check this is the station you meant", origin, chosen
        )
    else:
        log.info("resolved %r to %s", origin, chosen)
    if len(matches) > 1:
        log.info(
            "  other matches: %s",
            ", ".join(str(s) for s in matches if s.eva != chosen.eva),
        )
    return chosen


def extract(
    query: Query,
    with_changes: bool = True,
    resolve_names: bool = True,
    include_sub_stations: bool = False,
    departures_only: bool | None = None,
) -> list[StopRecord]:
    """Run a Query against the DB APIs and return HF-schema records."""
    creds = Credentials.from_env()
    timetables = TimetablesClient(creds)
    ris = RisStationsClient(creds) if resolve_names else None

    station = resolve_origin(timetables, query.origin)
    evas = [station.eva] + (station.meta if include_sub_stations else [])

    slices = [
        datetime(query.day.year, query.day.month, query.day.day, h, tzinfo=BERLIN)
        for h in query.hours
    ]

    # A journey query is about leaving the origin, so drop terminating trains.
    if departures_only is None:
        departures_only = query.destination is not None

    records: list[StopRecord] = []
    for eva in evas:
        snapshot = collect_station(timetables, eva, slices, with_changes)

        # Some big stations publish nothing on their primary EVA and put all
        # traffic on a linked sub-station (Berlin Hbf 8011160 is empty; the
        # trains are on 8098160). Fall back rather than return an empty file.
        if not snapshot.stops and eva == station.eva and station.meta:
            log.warning(
                "EVA %s has no timetable of its own; falling back to its "
                "sub-stations %s",
                eva,
                ", ".join(station.meta),
            )
            for sub in station.meta:
                sub_snapshot = collect_station(timetables, sub, slices, with_changes)
                if sub_snapshot.stops:
                    records.extend(
                        _finish(
                            sub_snapshot, sub, ris, query, departures_only
                        )
                    )
            continue

        records.extend(_finish(snapshot, eva, ris, query, departures_only))

    records.sort(key=lambda r: (r.time or datetime.max.replace(tzinfo=BERLIN)))
    return records


def _finish(
    snapshot: StationSnapshot,
    eva: str,
    ris: RisStationsClient | None,
    query: Query,
    departures_only: bool,
) -> list[StopRecord]:
    """Apply the destination filter and turn one snapshot into records."""
    if query.destination:
        keep = {
            sid for sid in snapshot.stops if snapshot.route_contains(sid, query.destination)
        }
        log.info(
            "  %s: %d of %d run via %r",
            eva,
            len(keep),
            len(snapshot.stops),
            query.destination,
        )
        snapshot.stops = {k: v for k, v in snapshot.stops.items() if k in keep}

    name = ris.canonical_name(eva) if ris else None
    batch = snapshot.to_records(station_name=name)
    if departures_only:
        batch = [r for r in batch if r.departure_planned_time is not None]
    return batch


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


def to_dataframe(records: Iterable[StopRecord]):
    import pandas as pd

    frame = pd.DataFrame([asdict(r) for r in records], columns=list(StopRecord.COLUMNS))
    # HF stores naive timestamps in local time; drop the tz to match.
    for column in (
        "time",
        "arrival_planned_time",
        "arrival_change_time",
        "departure_planned_time",
        "departure_change_time",
    ):
        frame[column] = pd.to_datetime(frame[column], utc=True).dt.tz_convert(
            BERLIN
        ).dt.tz_localize(None)
    frame["delay_in_min"] = frame["delay_in_min"].astype("Int32")
    frame["train_line_station_num"] = frame["train_line_station_num"].astype("Int32")
    return frame


def write(records: list[StopRecord], path: str) -> None:
    frame = to_dataframe(records)
    if path.endswith(".parquet"):
        frame.to_parquet(path, index=False)
    elif path.endswith(".jsonl"):
        frame.to_json(path, orient="records", lines=True, date_format="iso")
    elif path.endswith(".csv"):
        frame.to_csv(path, index=False)
    else:
        raise SystemExit("output must end in .parquet, .jsonl or .csv")
    log.info("wrote %d rows to %s", len(frame), path)


def write_frame(frame, path: str) -> None:
    """Write an already-built dataframe (archive path)."""
    if path.endswith(".parquet"):
        frame.to_parquet(path, index=False)
    elif path.endswith(".jsonl"):
        frame.to_json(path, orient="records", lines=True, date_format="iso")
    elif path.endswith(".csv"):
        frame.to_csv(path, index=False)
    else:
        raise SystemExit("output must end in .parquet, .jsonl or .csv")
    log.info("wrote %d rows to %s", len(frame), path)


def preview_frame(frame, limit: int = 15) -> None:
    import pandas as pd

    print(f"\n{len(frame)} rows\n")
    header = f"{'time':<17}{'train':<12}{'+':<5}{'destination':<32}{'station'}"
    print(header)
    print("-" * len(header))

    def text(value) -> str:
        return "" if value is None or pd.isna(value) else str(value)

    for _, row in frame.head(limit).iterrows():
        label = text(row.line_number) or text(row.train_number)
        train = f"{text(row.train_type) or '?'} {label}".strip()
        if row.departure_is_canceled or row.arrival_is_canceled:
            flag = "CANC"
        elif not pd.isna(row.delay_in_min) and row.delay_in_min:
            flag = f"{int(row.delay_in_min):+d}"
        else:
            flag = ""
        stamp = "-" if pd.isna(row.time) else row.time.strftime("%Y-%m-%d %H:%M")
        print(
            f"{stamp:<17}{train:<12}{flag:<5}"
            f"{text(row.final_destination_station)[:31]:<32}{text(row.xml_station_name)}"
        )


def preview(records: list[StopRecord], limit: int = 15) -> None:
    print(f"\n{len(records)} rows\n")
    header = f"{'time':<17}{'train':<12}{'+':<5}{'destination':<32}{'station'}"
    print(header)
    print("-" * len(header))
    for r in records[:limit]:
        train = f"{r.train_type or '?'} {r.line_number or r.train_number or ''}".strip()
        if r.departure_is_canceled or r.arrival_is_canceled:
            flag = "CANC"
        elif r.delay_in_min:
            flag = f"{r.delay_in_min:+d}"  # keeps the sign right for early trains
        else:
            flag = ""
        stamp = r.time.strftime("%Y-%m-%d %H:%M") if r.time else "-"
        print(
            f"{stamp:<17}{train:<12}{flag:<5}"
            f"{(r.final_destination_station or '')[:31]:<32}{r.xml_station_name or ''}"
        )


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def parse_day(raw: str) -> date:
    """Accept DD/MM/YYYY, DD.MM.YYYY or YYYY-MM-DD."""
    for fmt in ("%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise DBError(f"cannot read date {raw!r}; use DD/MM/YYYY")


def parse_hour(raw: str) -> int:
    """
    Accept HH:MM, HH.MM, HHMM or HH, 24-hour. Minutes are ignored: the
    Timetables API is sliced by whole hours.
    """
    text = raw.strip().lower().replace("h", ":").rstrip(":")
    for separator in (":", ".", ","):
        if separator in text:
            text = text.split(separator)[0]
            break
    else:
        if len(text) == 4 and text.isdigit():  # "0800"
            text = text[:2]
    try:
        hour = int(text)
    except ValueError as exc:
        raise DBError(
            f"cannot read time {raw!r}; use HH:MM in 24-hour form, e.g. 08:00"
        ) from exc
    if not 0 <= hour <= 23:
        raise DBError(f"hour {hour} is out of range; use 00-23")
    return hour


def load_dotenv(path: str = ".env") -> None:
    """Read KEY=VALUE lines from .env so credentials survive between runs."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def prompt_query() -> tuple[str, str | None, str | None, str | None]:
    """Ask for everything in one go when no arguments were given."""
    print("Leave any line blank to skip it.\n")
    origin = input("  From (station)        : ").strip() or "München Hbf"
    destination = input("  To (station, or skip) : ").strip() or None
    day = input("  Date DD/MM/YYYY       : ").strip() or None
    clock = input("  Time HH:MM            : ").strip() or None
    return origin, destination, day, clock


def default_filename(query: Query) -> str:
    def slug(text: str) -> str:
        return "".join(ch if ch.isalnum() else "-" for ch in text.casefold()).strip("-")

    parts = [slug(query.origin)]
    if query.destination:
        parts.append(slug(query.destination))
    parts.append(f"{query.day:%Y%m%d}-{query.start_hour:02d}")
    return "_".join(parts) + ".parquet"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "All four inputs can be given positionally, in this order:\n"
            "  db_hf_extract.py ORIGIN [DESTINATION] [DD/MM/YYYY] [HH:MM]\n\n"
            "Run with no arguments to be prompted for them instead."
        ),
    )
    parser.add_argument("args", nargs="*", metavar="ORIGIN DESTINATION DATE TIME",
                        help="all four inputs at once, in order")
    parser.add_argument("--from", dest="origin", help="override the origin")
    parser.add_argument("--to", dest="destination", help="override the destination")
    parser.add_argument("--date", help="override the date, DD/MM/YYYY")
    parser.add_argument("--time", help="override the time, HH:MM")
    parser.add_argument("--window", type=int, default=3, help="hours to cover (default 3)")
    parser.add_argument("--all-stops", action="store_true",
                        help="keep terminating trains too, not just departures")
    parser.add_argument("--sub-stations", action="store_true",
                        help="also pull linked sub-stations (S-Bahn level, wings)")
    parser.add_argument("--no-changes", action="store_true", help="plan only, skip fchg")
    parser.add_argument("--no-ris", action="store_true", help="skip canonical name lookup")
    parser.add_argument("-o", "--out", help="output .parquet / .jsonl / .csv")
    parser.add_argument("--no-file", action="store_true", help="print only, write nothing")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    for noisy in ("httpx", "httpcore", "urllib3", "huggingface_hub", "fsspec", "filelock"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    load_dotenv()

    # Positional inputs first, then let any explicit flag override them.
    positional = list(args.args) + [None] * 4
    origin, destination, day_text, time_text = positional[:4]
    if not any([origin, args.origin]):
        origin, destination, day_text, time_text = prompt_query()

    origin = args.origin or origin
    destination = args.destination or destination
    day_text = args.date or day_text
    time_text = args.time or time_text

    now = datetime.now(BERLIN)
    try:
        query = Query(
            origin=origin,
            destination=destination,
            day=parse_day(day_text) if day_text else now.date(),
            start_hour=parse_hour(time_text) if time_text else now.hour,
            window_hours=max(1, args.window),
        )
        log.info("query: %s", query.describe())

        if query.day < now.date():
            log.info(
                "%s is in the past — the API keeps no archive, reading the "
                "collected dataset instead",
                query.day,
            )
            # /station is not date-scoped, so it still gives us the exact DB
            # spelling to match against the archive's station columns.
            name = query.origin
            try:
                name = resolve_origin(TimetablesClient(Credentials.from_env()),
                                      query.origin).name or query.origin
            except DBError as exc:
                log.debug("name lookup skipped: %s", exc)
            frame = load_archive(
                query,
                departures_only=bool(query.destination) and not args.all_stops,
                station_name=name,
            )
            preview_frame(frame)
            if not args.no_file and not frame.empty:
                write_frame(frame, args.out or default_filename(query))
            return 0

        if query.day > now.date() and not args.no_changes:
            log.warning(
                "%s is in the future: fchg carries no deviations that far ahead, "
                "so delay_in_min will be 0 for every row.",
                query.day,
            )

        records = extract(
            query,
            with_changes=not args.no_changes,
            resolve_names=not args.no_ris,
            include_sub_stations=args.sub_stations,
            departures_only=False if args.all_stops else None,
        )
    except DBError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    preview(records)
    if not args.no_file:
        write(records, args.out or default_filename(query))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
