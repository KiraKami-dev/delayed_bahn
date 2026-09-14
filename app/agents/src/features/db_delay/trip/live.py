"""Live examples from the DB Timetables API, so the model forecasts a train that is running now.

A journey leg (train, boarding station, target stop, planned times) becomes one example row in the
v7 layout of build.py, computed at t0 = now:

- From the API (plan per station and hour, fchg per station): the run's departure delays at its
  origin and at the stops just before the boarding station, the previous trains of the same type
  and destination at the target in the last 6 hours, the other trains that left the start station
  in the last 3 hours and already reached the target, and the target's late share in the last
  3 hours.
- From stored examples (the latest recorded rows, up to the end of the September scrape): the
  90-day history at the target, the same train number's earlier days, and the older station hours
  and the nationwide hours, both filled by hour of day. The forecast's sources say so.
- The xgb_* columns from the refitted statistical forecast (live_xgb.py).

A cold leg costs about 30 to 40 calls; station lookups and plan hours are cached for the process,
change feeds for a minute. A sliding window keeps the client under one key's 60 calls per minute.

When the API fails, a change feed fetched earlier is reused and the sources say from when. Without
any live data, ``offline_example`` builds the row from the latest recorded run of the train (route,
history) with no live delays, previous trains or corridor. After an outage every call fails at once
for a minute, so these fallbacks answer quickly.

    python trip/live.py --stored september_test.parquet --xgb out/trip/xgb_v7 --env .env \\
        --train "RE 1" --from "Hamm (Westf) Hbf" --to "Dortmund Hbf" \\
        --departure 2026-09-13T09:05 --arrival 2026-09-13T09:24
"""

from __future__ import annotations

import argparse
import collections
import re
import sys
import threading
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[6]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))

import db_live_extract as dbx  # noqa: E402

LOCAL_TZ = ZoneInfo("Europe/Berlin")
LATE_MINUTES = 6
SERIES_HOURS = 72
HISTORY_DAYS = 90
SAME_TRAIN_DAYS = 28
LIVE_STATION_HOURS = 3  # recent hours of the target's late share taken from the API
PREV_HOURS = 6
CORRIDOR_HOURS = 3
CORRIDOR_TRAINS = 8
RUN_STOPS_BACK = 4  # stops before the boarding station whose departures are fetched, plus the origin
SEARCH_HOURS = 8  # how many plan hours back a previous stop is searched
API_TIMEOUT = 8  # seconds per call; a slow API should fall back, not stall the app
DOWN_SECONDS = 60  # after an outage, calls fail at once for this long
LONG_DISTANCE = ("ICE", "IC", "EC")
HIST = ["hist_series", "hist_level", "hist_n", "hist_cancel_share", "hist_median", "hist_p90", "hist_mean",
        "hist_days", "hist_median_long", "hist_p90_long", "hist_median_7", "hist_window_days"]
HOUR = timedelta(hours=1)


def norm(value) -> str:
    """Lower-case letters and digits only."""
    return re.sub(r"[^a-z0-9äöüß]", "", str(value or "").lower())


def local_naive(value) -> datetime:
    """An ISO timestamp as naive Berlin time, like the Timetables feeds."""
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is not None:
        stamp = stamp.tz_convert(LOCAL_TZ).tz_localize(None)
    return stamp.to_pydatetime()


def now_local() -> datetime:
    """The current naive Berlin time."""
    return datetime.now(LOCAL_TZ).replace(tzinfo=None)


def floor_hour(moment: datetime) -> datetime:
    return moment.replace(minute=0, second=0, microsecond=0)


def hours(start: datetime, end: datetime) -> list[datetime]:
    """Every plan hour from the one holding ``start`` to the one holding ``end``."""
    out, hour = [], floor_hour(start)
    while hour <= end:
        out.append(hour)
        hour += HOUR
    return out


def minutes(later: datetime | None, earlier: datetime | None) -> int | None:
    return None if later is None or earlier is None else round((later - earlier).total_seconds() / 60)


def parse(raw: str | None) -> datetime | None:
    return datetime.strptime(raw, dbx.TS_FORMAT) if raw else None


def train_class(train_type: str | None) -> str:
    return "long-distance" if train_type in LONG_DISTANCE else "S-Bahn" if train_type == "S" else "regional"


def stop_row(stop, station: str | None) -> dict:
    """One merged plan and change <s> element as a stops row of build.py, plus the route paths."""
    ar, dp, tl = stop.ar, stop.dp, stop.tl
    arr_pt, dep_pt = parse(ar.get("pt")), parse(dp.get("pt"))
    # A stop without a change time ran as planned, the convention of the upstream archive.
    arr_ct, dep_ct = parse(ar.get("ct")) or arr_pt, parse(dp.get("ct")) or dep_pt
    run, _, num = stop.stop_id.rpartition("-")
    after = dbx.path_stations(dp.get("cpth") or dp.get("ppth"))
    return {
        "run": run, "num": int(num) if num.isdigit() else None, "station": station,
        "train_type": tl.get("c"), "train_number": tl.get("n"), "line_number": dp.get("l") or ar.get("l"),
        "dest": after[-1] if after else station,
        "arr_pt": arr_pt, "arr_ct": arr_ct, "dep_pt": dep_pt, "dep_ct": dep_ct,
        "arr_canc": ar.get("cs") == "c", "dep_canc": dp.get("cs") == "c",
        "arr_delay": minutes(arr_ct, arr_pt), "dep_delay": minutes(dep_ct, dep_pt),
        "delay": minutes(dep_ct, dep_pt) if dep_pt else minutes(arr_ct, arr_pt),
        "event_time": dep_ct or arr_ct or dep_pt or arr_pt,
        "before": dbx.path_stations(ar.get("cpth") or ar.get("ppth")), "after": after,
    }


def row_keys(row: dict) -> set[str]:
    """Every spelling of a timetable train the app might send."""
    kind, line = row.get("train_type") or "", row.get("line_number") or ""
    keys = {norm(f"{kind}{row.get('train_number') or ''}"), norm(line), norm(f"{kind}{line}")}
    return {k for k in keys if k and k != norm(kind)}


def leg_keys(leg: dict) -> set[str]:
    """The spellings carried by a journey leg."""
    keys = {norm(leg.get("trainId"))}
    if leg.get("trainNumber"):
        prefix = re.match(r"[A-Za-z]+", str(leg.get("trainId") or ""))
        keys.add(norm(f"{prefix.group(0) if prefix else ''}{leg['trainNumber']}"))
    return {k for k in keys if k}


class Client(dbx.TimetablesClient):
    """Timetables with a sliding one-minute window, short timeouts and a pause after the API fails.

    After an outage, a timeout or a refused key every call fails at once for ``DOWN_SECONDS``, so a
    journey reaches its fallback in milliseconds instead of waiting on each of its 20 to 40 calls.
    ``offline`` switches the API off entirely (demos without network, tests)."""

    def __init__(self, creds: dbx.Credentials, per_minute: int = 55, offline: bool = False):
        super().__init__(creds, min_interval=0.0)
        self.per_minute, self.offline = per_minute, offline
        self.stamps: collections.deque[float] = collections.deque()
        self.lock = threading.Lock()
        self.calls = 0
        self.down_until = 0.0

    def _throttle(self) -> None:
        with self.lock:
            while True:
                now = time.monotonic()
                while self.stamps and now - self.stamps[0] >= 60:
                    self.stamps.popleft()
                if len(self.stamps) < self.per_minute:
                    self.stamps.append(now)
                    self.calls += 1
                    return
                time.sleep(60.05 - (now - self.stamps[0]))

    def get(self, path: str, attempts: int = 2) -> bytes:
        if self.offline:
            raise dbx.DBError("offline mode, DB live data switched off")
        wait = self.down_until - time.monotonic()
        if wait > 0:
            raise dbx.DBError(f"DB API unavailable, next try in {wait:.0f} s")
        url = f"{dbx.MARKETPLACE}/{path}"
        request = urllib.request.Request(url, headers=self.creds.headers(self.accept))
        for attempt in range(1, attempts + 1):
            self._throttle()
            try:
                with urllib.request.urlopen(request, timeout=API_TIMEOUT) as response:
                    return response.read()
            except urllib.error.HTTPError as error:
                if error.code in (429, 500, 502, 503, 504) and attempt < attempts:
                    time.sleep(2)
                    continue
                if error.code in (401, 403, 429, 500, 502, 503, 504):
                    self.down_until = time.monotonic() + DOWN_SECONDS
                raise dbx.DBError(f"HTTP {error.code} for {path}") from error
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                self.down_until = time.monotonic() + DOWN_SECONDS
                raise dbx.DBError(f"DB API unreachable ({error})") from error
        raise dbx.DBError(f"gave up on {path}")


class Feeds:
    """Station lookups and plan hours cached for the process, change feeds for ``change_ttl`` seconds.

    A change feed that cannot be refreshed is served from its last copy; ``stale`` records since when."""

    def __init__(self, client: Client, change_ttl: float = 60.0):
        self.client, self.change_ttl = client, change_ttl
        self.stations: dict[str, tuple[str, str, list[str]] | None] = {}
        self.plans: dict[tuple[str, str], ET.Element | None] = {}
        self.changes: dict[str, tuple[float, ET.Element, datetime]] = {}
        self.stale: dict[str, datetime] = {}

    def station(self, name: str) -> tuple[str, str, list[str]] | None:
        """EVA number, Timetables name and the EVA numbers of its sub-stations for a station name."""
        key = norm(name)
        if key not in self.stations:
            found = []
            # The pattern is a URL path segment: cut at "/" and let the exact match pick the station.
            for pattern in dict.fromkeys([name.split("/")[0].strip(), re.sub(r"\s*\(.*?\)", "", name).split("/")[0].strip()]):
                # An error is raised, not cached: a shorter pattern would find the wrong station, e.g. the
                # main station for "Stuttgart Hbf (tief)", and keep it for the whole process.
                found = self.client.find_stations(pattern)
                if found:
                    break
            exact = [s for s in found if norm(s.name) == key]
            pick = (exact or found or [None])[0]
            self.stations[key] = (pick.eva, pick.name, [m for m in pick.meta if len(m) == 7]) if pick else None
        return self.stations[key]

    def plan(self, eva: str, hour: datetime) -> ET.Element | None:
        key = (eva, f"{hour:%y%m%d%H}")
        if key not in self.plans:
            try:
                self.plans[key] = self.client.plan(eva, hour)
            except dbx.DBError as error:
                if "HTTP 404" not in str(error) and "HTTP 410" not in str(error):
                    raise
                self.plans[key] = None  # outside the served window
        return self.plans[key]

    def change(self, eva: str) -> ET.Element:
        hit = self.changes.get(eva)
        if hit is None or time.monotonic() - hit[0] > self.change_ttl:
            try:
                fresh = (time.monotonic(), self.client.full_changes(eva), now_local())
            except dbx.DBError:
                if hit is None:
                    raise
                self.stale[eva] = hit[2]  # the API failed: keep the last known changes, and say from when
                return hit[1]
            self.changes[eva] = hit = fresh
            self.stale.pop(eva, None)
        return hit[1]

    def stops(self, eva: str, plan_hours: list[datetime]) -> list[dict]:
        """Every stop planned at the station in those hours, with the current changes applied."""
        snapshot = dbx.StationSnapshot(eva)
        for hour in sorted(set(plan_hours)):
            document = self.plan(eva, hour)
            if document is not None:
                snapshot.absorb(document, create=True)
        snapshot.absorb(self.change(eva), create=False)
        return [stop_row(stop, snapshot.xml_station_name) for stop in snapshot.stops.values()]


def by_hour_of_day(series, t0) -> dict[int, float]:
    """The latest value per hour of day of a stored hourly series ending with the hour before t0."""
    base = floor_hour(pd.Timestamp(t0).to_pydatetime())
    values = np.asarray(series, dtype=np.float64)
    return {(base - (len(values) - i) * HOUR).hour: float(v) for i, v in enumerate(values)}


def weighted_share(late: np.ndarray, counts: np.ndarray, last: int) -> float:
    lt, n = np.nan_to_num(late[-last:]), counts[-last:]
    return float((lt * n).sum() / max(n.sum(), 1)) if n.sum() > 0 else 0.0


def same_hour_share(late: np.ndarray, counts: np.ndarray, t0: datetime, arrival: datetime) -> float:
    """build.py's share at the planned arrival's hour of day over the hourly window."""
    offset = (t0.hour - 1 - arrival.hour) % 24
    idx = np.arange(len(late))
    weights = np.where(((len(late) - 1 - idx) % 24) == offset, counts, 0.0)
    return float(np.nansum(late * weights) / max(weights.sum(), 1)) if weights.sum() > 0 else 0.0


def run_columns(run_delays: list[float]) -> dict:
    """The scalar columns build.py derives from the run's departure delays."""
    return {"run_delays": run_delays, "run_plan_next": [], "run_plan_dwell": [], "run_plan_left": [],
            "current_delay": run_delays[-1] if run_delays else 0.0, "max_delay_so_far": max(run_delays) if run_delays else 0.0,
            "delay_change_3": run_delays[-1] - run_delays[max(0, len(run_delays) - 4)] if run_delays else 0.0,
            "run_len": float(len(run_delays))}


class Live:
    """Builds example rows for journey legs from the API, stored examples and the refitted forecast."""

    def __init__(self, feeds: Feeds, stored: pd.DataFrame, forecast):
        self.feeds, self.forecast = feeds, forecast
        stored = stored.copy()
        stored["t0"] = pd.to_datetime(stored["t0"])
        stored["_k"] = stored["k_station"].map(norm)
        stored["_train"] = (stored["train_type"].astype(str) + stored["train_number"].astype(str)).map(norm)
        start = np.where(stored["pre_departure"].astype(bool) | stored["j_station"].isna(), stored["first_station"], stored["j_station"])
        stored["_start"] = pd.Series(start, index=stored.index).map(norm)
        identity = stored[["train_type", "train_number", "line_number"]].astype(object).where(lambda f: f.notna(), "")
        stored["_keys"] = [row_keys(r) for r in identity.to_dict("records")]
        self.stored = stored
        self.station_names = stored["_k"].unique()
        self.train_types = set(stored["train_type"].astype(str))
        self.data_end = stored["t0"].max()

    def _at_station(self, name: str) -> pd.Series:
        """Stored rows whose target is this station, allowing for the archive's longer names."""
        n = norm(name)
        names = [s for s in self.station_names if s == n or (min(len(s), len(n)) >= 4 and (s in n or n in s))]
        return self.stored["_k"].isin(names)

    def _latest(self, mask: pd.Series) -> pd.Series | None:
        rows = self.stored[mask]
        return None if rows.empty else rows.loc[rows["t0"].idxmax()]

    def _candidates(self, stop: dict | None) -> list[str]:
        """EVA numbers to try for a journey station: the one sent, the name's, and their sub-stations.

        DB gives platforms of one place their own numbers (Stuttgart Hbf's S-Bahn platforms are
        "Stuttgart Hbf (tief)"), and an app may send the main station's number for either."""
        stop = stop or {}
        evas = [str(stop["evaNumber"])] if stop.get("evaNumber") else []
        found = self.feeds.station(stop["name"]) if stop.get("name") else None
        if found:
            evas += [found[0]] + found[2]
        if not evas:
            raise LookupError(f"station {stop.get('name')!r} not found in the Timetables API")
        return list(dict.fromkeys(evas))

    def _stored_parts(self, k_station: str, train: str, train_type: str, start: str | None, cls: str,
                      now: datetime, arrival: datetime, live_hours: dict[datetime, list[float]] | None) -> dict:
        """History, same-train days and the hourly series from stored rows; the target's last hours from
        ``live_hours`` when the API supplied them, else like the older hours by hour of day."""
        at_k = self._at_station(k_station)
        hist = self._latest(at_k & (self.stored["_train"] == train))
        if hist is None:
            hist = self._latest(at_k & (self.stored["train_type"] == train_type))
        same = None if start is None else self._latest(at_k & (self.stored["_train"] == train) & (self.stored["_start"] == norm(start)))
        k_latest = self._latest(at_k)
        n_latest = self._latest(self.stored["cls"] == cls)

        t0_hour = floor_hour(now)
        stored_station = by_hour_of_day(k_latest["station_series"], k_latest["t0"]) if k_latest is not None else {}
        typical = float(k_latest["station_stops_24h"]) / 24 if k_latest is not None else 1.0
        st_late, st_n = np.zeros(SERIES_HOURS), np.zeros(SERIES_HOURS)
        for i in range(SERIES_HOURS):
            hour = t0_hour - (SERIES_HOURS - i) * HOUR
            if live_hours is not None and SERIES_HOURS - i <= LIVE_STATION_HOURS:
                values = live_hours.get(hour, [])
                st_late[i], st_n[i] = (float(np.mean(values)), len(values)) if values else (0.0, 0.0)
            else:
                st_late[i], st_n[i] = stored_station.get(hour.hour, 0.0), typical
        stored_network = by_hour_of_day(n_latest["network_series"], n_latest["t0"]) if n_latest is not None else {}
        nw_late = np.array([stored_network.get((t0_hour - (SERIES_HOURS - i) * HOUR).hour, 0.0) for i in range(SERIES_HOURS)])
        nw_n = np.ones(SERIES_HOURS)

        parts = {
            "station_series": st_late, "network_series": nw_late,
            "station_late_3h": weighted_share(st_late, st_n, 3), "station_late_24h": weighted_share(st_late, st_n, 24),
            "station_late_72h": weighted_share(st_late, st_n, 72), "station_stops_24h": float(st_n[-24:].sum()),
            "network_late_3h": weighted_share(nw_late, nw_n, 3), "network_late_24h": weighted_share(nw_late, nw_n, 24),
            "network_late_72h": weighted_share(nw_late, nw_n, 72),
            "station_late_same_hour": same_hour_share(st_late, st_n, now, arrival),
            "network_late_same_hour": same_hour_share(nw_late, nw_n, now, arrival),
        }
        if hist is not None:
            parts |= {c: hist[c] for c in HIST}
        else:
            parts |= {"hist_series": np.zeros(HISTORY_DAYS), "hist_level": "none", "hist_n": 0.0, "hist_cancel_share": 0.0,
                      "hist_median": 0.0, "hist_p90": 0.0, "hist_mean": 0.0, "hist_days": 0.0, "hist_median_long": 0.0,
                      "hist_p90_long": 0.0, "hist_median_7": 0.0, "hist_window_days": HISTORY_DAYS}
        if same is not None and same["same_train_days"] > 0:
            parts |= {c: same[c] for c in ("same_train_gains", "same_train_days", "same_train_gain_median", "same_train_gain_median_7")}
        else:
            parts |= {"same_train_gains": np.zeros(SAME_TRAIN_DAYS), "same_train_days": 0.0,
                      "same_train_gain_median": np.nan, "same_train_gain_median_7": np.nan}
        return parts

    def _finish(self, row: dict) -> pd.Series:
        """The same-train expectation and the statistical forecast, once the rest of the row is there."""
        row["same_train_expected"] = max(0.0, row["current_delay"] + row["same_train_gain_median"]) \
            if np.isfinite(row["same_train_gain_median"]) else np.nan
        row |= self.forecast.columns_for(pd.DataFrame([row])).iloc[0].to_dict()
        return pd.Series(row)

    def example(self, leg: dict, now: datetime | None = None) -> tuple[pd.Series, list[str]]:
        """One v7 example row for the leg at t0 = now, and the sources of its parts."""
        now = now or now_local()
        departure, arrival = local_naive(leg["plannedDeparture"]), local_naive(leg["plannedArrival"])
        calls_before = self.feeds.client.calls
        wanted = leg_keys(leg)
        f_name, k_name = (leg.get("from") or {}).get("name"), (leg.get("to") or {}).get("name")

        f = f_eva = None
        for eva in self._candidates(leg.get("from")):
            at_f = [r for r in self.feeds.stops(eva, [departure]) if r["dep_pt"] and abs(minutes(r["dep_pt"], departure)) <= 1
                    and row_keys(r) & wanted]
            if at_f:
                f, f_eva = at_f[0], eva
                break
        if f is None:
            raise LookupError(f"{leg.get('trainId')} does not leave {f_name} at {departure:%H:%M} in the live timetable")
        run = f["run"]
        k_hours = hours(arrival - PREV_HOURS * HOUR, min(arrival, now)) + [arrival] + hours(now - LIVE_STATION_HOURS * HOUR, now)
        k = k_rows = k_eva = None
        for eva in self._candidates(leg.get("to")):
            rows = self.feeds.stops(eva, k_hours)
            k = next((r for r in rows if r["run"] == run and r["arr_pt"]), None)
            if k is not None:
                k_rows, k_eva = rows, eva
                break
        if k is None:
            raise LookupError(f"{leg.get('trainId')} has no planned arrival at {k_name} at {arrival:%H:%M}")

        # The run so far: the origin and the stops just before the boarding station.
        before = f["before"]
        origin = before[0] if before else f["station"]
        run_stops, stations_of = {f["num"]: f}, {f["num"]: f_eva}
        upper = f["arr_pt"] or f["dep_pt"]
        for name in list(reversed(before[-RUN_STOPS_BACK:])) + ([origin] if len(before) > RUN_STOPS_BACK else []):
            station = self.feeds.station(name)
            if station is None:
                continue
            hour = floor_hour(upper)
            for _ in range(SEARCH_HOURS + 1):
                mine = [r for r in self.feeds.stops(station[0], [hour]) if r["run"] == run]
                if mine:
                    run_stops[mine[0]["num"]] = mine[0]
                    stations_of[mine[0]["num"]] = station[0]
                    upper = mine[0]["dep_pt"] or mine[0]["arr_pt"] or upper
                    break
                hour -= HOUR
        ordered = [run_stops[n] for n in sorted(run_stops)]
        departed = [r for r in ordered if r["dep_ct"] is not None and r["dep_ct"] <= now and not r["dep_canc"]
                    and r["dep_delay"] is not None]
        pre = not departed
        j = None if pre else departed[-1]
        first_num = f["num"] - len(before)
        from_num = first_num if pre else j["num"]
        start_name = origin if pre else j["station"]
        start_eva = stations_of.get(ordered[0]["num"]) if pre and norm(ordered[0]["station"]) == norm(origin) else (
            None if pre else stations_of[j["num"]])
        run_delays = [float(r["dep_delay"]) for r in departed]

        path = before + [f["station"]] + f["after"]
        k_index = next((i for i in range(len(before) + 1, len(path)) if norm(path[i]) == norm(k["station"])), len(path))
        from_index = 0 if pre else next((i for i, s in enumerate(path) if norm(s) == norm(j["station"])), 0)
        via = path[from_index + 1:k_index]
        dest = f["after"][-1] if f["after"] else f["station"]

        prev = sorted((r for r in k_rows if r["run"] != run and r["train_type"] == f["train_type"]
                       and norm(r["dest"]) == norm(dest) and r["arr_pt"] and arrival - PREV_HOURS * HOUR <= r["arr_pt"] < k["arr_pt"]
                       and r["arr_ct"] is not None and r["arr_ct"] <= now and not r["arr_canc"] and r["arr_delay"] is not None),
                      key=lambda r: r["arr_pt"])[-5:]
        prev_delays = [float(r["arr_delay"]) for r in prev]
        prev_gaps = [float(minutes(k["arr_pt"], r["arr_pt"])) for r in prev]

        corridor = []
        if start_eva is not None:
            arrived = {r["run"]: r for r in k_rows if r["arr_ct"] is not None and r["arr_ct"] < now and not r["arr_canc"]
                       and r["arr_delay"] is not None}
            for a in self.feeds.stops(start_eva, hours(now - CORRIDOR_HOURS * HOUR, now)):
                b = arrived.get(a["run"])
                if (a["run"] != run and b is not None and a["num"] is not None and b["num"] is not None and b["num"] > a["num"]
                        and a["dep_ct"] is not None and now - CORRIDOR_HOURS * HOUR <= a["dep_ct"] < now
                        and a["dep_delay"] is not None and not a["dep_canc"]):
                    corridor.append((b["arr_ct"], a["run"], float(b["arr_delay"] - a["dep_delay"]), float(b["arr_delay"])))
            corridor = sorted(sorted(corridor, key=lambda c: c[1]), key=lambda c: c[0], reverse=True)[:CORRIDOR_TRAINS][::-1]

        t0_hour = floor_hour(now)
        live_hours: dict[datetime, list[float]] = collections.defaultdict(list)
        for r in k_rows:
            if r["event_time"] is not None and not r["arr_canc"] and not r["dep_canc"] and r["delay"] is not None:
                hour = floor_hour(r["event_time"])
                if t0_hour - LIVE_STATION_HOURS * HOUR <= hour < t0_hour:
                    live_hours[hour].append(float(r["delay"] >= LATE_MINUTES))

        cls = train_class(f["train_type"])
        train = norm(f"{f['train_type']}{f['train_number']}")
        k_arrival = k["arr_pt"]
        row = {
            "example_id": -1, "split": "live", "run": run, "cls": cls, "train_type": f["train_type"],
            "train_number": f["train_number"], "line_number": f["line_number"], "origin": origin, "dest": dest,
            "first_station": origin, "j_station": None if pre else j["station"], "k_station": k["station"],
            "k_num": k["num"], "j_num": None if pre else j["num"], "first_num": first_num, "t0": now, "k_arr_pt": k_arrival,
            "pre_departure": pre, "via": via, "prev_arr_delays": prev_delays, "prev_gaps": prev_gaps, "prev_n": float(len(prev)),
            "prev_last": prev_delays[-1] if prev else 0.0, "prev_mean": float(np.mean(prev_delays)) if prev else 0.0,
            "prev_gap_last": prev_gaps[-1] if prev else 0.0,
            "corridor_gains": [c[2] for c in corridor], "corridor_arr_delays": [c[3] for c in corridor],
            "corridor_n": float(len(corridor)), "corridor_gain_mean": float(np.mean([c[2] for c in corridor])) if corridor else np.nan,
            "corridor_gain_last": corridor[-1][2] if corridor else np.nan,
            "lead_minutes": (k_arrival - now).total_seconds() / 60, "stops_ahead": float(k["num"] - from_num),
            "arr_hour": float(k_arrival.hour), "arr_weekday": float(k_arrival.weekday()), "target_minutes": 0.0, "cancelled": False,
        } | run_columns(run_delays) | self._stored_parts(k["station"], train, f["train_type"], start_name, cls, now, k_arrival, live_hours)
        row = self._finish(row)

        where = "not departed yet" if pre else f"left {j['station']} {row['current_delay']:.0f} min late"
        sources = [
            f"live DB Timetables at {now:%H:%M}: {where}, delays at {len(run_delays)} departed stops, "
            f"{len(prev)} previous trains and {len(corridor)} corridor trains at {k['station']}, its last "
            f"{LIVE_STATION_HOURS} hours ({self.feeds.client.calls - calls_before} API calls)",
            f"stored until {self.data_end:%d %b %H:%M}: {row['hist_level']} history over {HISTORY_DAYS} days, "
            f"same train number on {int(row['same_train_days'])} days, older station and nationwide hours by hour of day",
            "statistical forecast refitted on the v7 training split",
        ]
        used = set(stations_of.values()) | {k_eva, start_eva}
        stale = [t for eva, t in self.feeds.stale.items() if eva in used]
        if stale:
            sources.insert(1, f"DB API unavailable: change feeds from {min(stale):%H:%M} used for {len(stale)} stations")
        return row, sources

    def offline_example(self, leg: dict, now: datetime | None = None, reason: str = "") -> tuple[pd.Series, list[str]]:
        """An example row without the API, for when DB live data is unreachable.

        The route comes from the latest recorded run of the same train to the target, else of a train
        of its type there; history, same-train days and the hourly series come from stored rows as in
        ``example``. There are no live delays, previous trains or corridor trains, so the row reads as
        a train that has not departed yet."""
        now = now or now_local()
        arrival = local_naive(leg["plannedArrival"])
        to_name, from_name = (leg.get("to") or {}).get("name") or "", (leg.get("from") or {}).get("name") or ""
        prefix = re.match(r"[A-Za-z]+", str(leg.get("trainId") or ""))
        kind = prefix.group(0).upper() if prefix else ""
        at_k = self._at_station(to_name)
        wanted = leg_keys(leg)
        template = self._latest(at_k & self.stored["_keys"].map(lambda keys: bool(keys & wanted)))
        same_train = template is not None
        if template is None:
            template = self._latest(at_k & (self.stored["train_type"] == kind))
        if template is None and len(kind) >= 2:
            # A train from abroad (an EC from Zürich) may have no run of its type recorded at a German stop
            # while a sibling type has (an ECE; IC and ICE alike): borrow that route, keep the train's own type.
            types = self.stored["train_type"].astype(str)
            template = self._latest(at_k & (types.str.startswith(kind) | types.map(lambda t: bool(t) and kind.startswith(t))))
        if template is None:
            template = self._latest(at_k & (self.stored["cls"] == train_class(kind)))
        if template is None:
            raise LookupError(f"no recorded {leg.get('trainId')} or {train_class(kind)} run to {to_name} for an offline estimate")

        train_type = template["train_type"] if same_train or kind not in self.train_types else kind
        train_number = template["train_number"] if same_train else str(leg.get("trainNumber") or "")
        cls = template["cls"] if same_train else train_class(train_type)
        first = template["first_station"] if same_train else from_name
        row = {
            "example_id": -1, "split": "offline", "run": "", "cls": cls, "train_type": train_type, "train_number": train_number,
            "line_number": template["line_number"] if same_train else None,
            "origin": template["origin"] if same_train else from_name, "dest": template["dest"] if same_train else to_name,
            "first_station": first, "j_station": None, "k_station": template["k_station"], "k_num": template["k_num"],
            "j_num": None, "first_num": template["first_num"], "t0": now, "k_arr_pt": arrival, "pre_departure": True,
            "via": list(template["via"]) if same_train and template["via"] is not None else [],
            "prev_arr_delays": [], "prev_gaps": [], "prev_n": 0.0, "prev_last": 0.0, "prev_mean": 0.0, "prev_gap_last": 0.0,
            "corridor_gains": [], "corridor_arr_delays": [], "corridor_n": 0.0, "corridor_gain_mean": np.nan, "corridor_gain_last": np.nan,
            "lead_minutes": (arrival - now).total_seconds() / 60, "stops_ahead": float(template["k_num"] - template["first_num"]),
            "arr_hour": float(arrival.hour), "arr_weekday": float(arrival.weekday()), "target_minutes": 0.0, "cancelled": False,
        } | run_columns([]) | self._stored_parts(template["k_station"], norm(f"{train_type}{train_number}"), train_type,
                                                first if same_train else None, cls, now, arrival, None)
        row = self._finish(row)
        route = (f"route of the latest recorded {train_type} {train_number} to {template['k_station']} ({template['t0']:%d %b})"
                 if same_train else f"no recorded run of {leg.get('trainId')}: a {template['train_type']} train to {template['k_station']} as the template")
        sources = [
            f"offline estimate at {now:%H:%M}: DB live data unavailable ({reason or 'no live data'}), so no live delays, "
            "previous trains or corridor trains",
            route,
            f"stored until {self.data_end:%d %b %H:%M}: {row['hist_level']} history over {HISTORY_DAYS} days, "
            f"same train number on {int(row['same_train_days'])} days, station and nationwide hours by hour of day",
            "statistical forecast refitted on the v7 training split",
        ]
        return row, sources


def create(stored: str, xgb_dir: str, env: str | None = None, per_minute: int = 55, offline: bool = False) -> Live:
    """A live example builder with credentials from the .env file."""
    import live_xgb  # noqa: PLC0415  (xgboost only when live examples are wanted)

    dbx.load_dotenv(env or str(ROOT / ".env"))
    creds = dbx.Credentials("", "") if offline else dbx.Credentials.from_env()
    client = Client(creds, per_minute, offline)
    return Live(Feeds(client), pd.read_parquet(stored), live_xgb.Forecast(Path(xgb_dir)))


def main() -> None:
    """Build and print one live (or offline) example: the prompt text, the sources and the API calls it took."""
    import prompts  # noqa: PLC0415

    parser = argparse.ArgumentParser()
    parser.add_argument("--stored", required=True)
    parser.add_argument("--xgb", required=True)
    parser.add_argument("--env")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--train", required=True)
    parser.add_argument("--number")
    parser.add_argument("--from", dest="origin", required=True)
    parser.add_argument("--to", required=True)
    parser.add_argument("--departure", required=True)
    parser.add_argument("--arrival", required=True)
    args = parser.parse_args()
    live = create(args.stored, args.xgb, args.env, offline=args.offline)
    leg = {"trainId": args.train, "trainNumber": args.number, "from": {"name": args.origin}, "to": {"name": args.to},
           "plannedDeparture": args.departure, "plannedArrival": args.arrival}
    started = time.time()
    try:
        row, sources = live.example(leg)
    except (LookupError, RuntimeError, OSError) as error:
        row, sources = live.offline_example(leg, reason=str(error))
    sample = prompts.sample(row, mode="text")
    print(sample["pre_prompt"], "\n", sample["prefix"], "\n", "\n".join(sources), sep="")
    print(f"{live.feeds.client.calls} calls in {time.time() - started:.0f}s")


if __name__ == "__main__":
    main()
