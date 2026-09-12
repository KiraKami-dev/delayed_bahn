#!/usr/bin/env python3
"""Smoke test for the DB Timetables API: next departures for a station.

Usage:
    python3 scripts/db_timetables.py "Hamburg Hbf"
    python3 scripts/db_timetables.py "Nuernberg Hbf" --hours 3 --limit 25
    python3 scripts/db_timetables.py --eva 8000284

Credentials are read from .env (DB_CLIENT_ID, DB_API_KEY). Stdlib only.
Timetable times are German local time; the clock here is the system clock.
"""

import argparse
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree

BASE = "https://apis.deutschebahn.com/db-api-marketplace/apis/timetables/v1"


def load_env(path):
    """Minimal .env reader. Real environment variables win."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def get(path, client_id, api_key):
    request = urllib.request.Request(
        f"{BASE}/{path}",
        headers={
            "DB-Client-Id": client_id,
            "DB-Api-Key": api_key,
            "Accept": "application/xml",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return ElementTree.fromstring(response.read())
    except urllib.error.HTTPError as error:
        body = error.read().decode(errors="replace").strip()[:400]
        hint = ""
        if error.code in (401, 403):
            hint = "\nCheck DB_CLIENT_ID / DB_API_KEY, and that the application is subscribed to Timetables."
        sys.exit(f"HTTP {error.code} on /{path}\n{body}{hint}")
    except urllib.error.URLError as error:
        sys.exit(f"network error on /{path}: {error.reason}")


def find_station(pattern, client_id, api_key):
    root = get(f"station/{urllib.parse.quote(pattern)}", client_id, api_key)
    stations = root.findall("station")
    if not stations:
        sys.exit(f"no station matched {pattern!r}")
    if len(stations) > 1:
        print("matches:", ", ".join(f"{s.get('name')} ({s.get('eva')})" for s in stations[:8]))
    return stations[0].get("name"), stations[0].get("eva")


def parse_time(value):
    return datetime.strptime(value, "%y%m%d%H%M") if value else None


def collect(eva, hours, client_id, api_key, now):
    """Planned departures for the next `hours` hourly slices, with live changes applied."""
    rows = {}
    for offset in range(hours):
        slice_start = now + timedelta(hours=offset)
        root = get(f"plan/{eva}/{slice_start:%y%m%d}/{slice_start:%H}", client_id, api_key)
        for stop in root.findall("s"):
            departure = stop.find("dp")
            if departure is None:
                continue  # arrival-only stop
            trip = stop.find("tl")
            category = trip.get("c", "") if trip is not None else ""
            number = departure.get("l") or (trip.get("n", "") if trip is not None else "")
            route = departure.get("ppth", "")
            rows[stop.get("id")] = {
                "time": parse_time(departure.get("pt")),
                "delay": 0,
                "platform": departure.get("pp", ""),
                "train": f"{category} {number}".strip(),
                "destination": route.split("|")[-1] if route else "",
                "cancelled": False,
            }

    for stop in get(f"fchg/{eva}", client_id, api_key).findall("s"):
        row = rows.get(stop.get("id"))
        departure = stop.find("dp")
        if row is None or departure is None:
            continue
        changed = parse_time(departure.get("ct"))
        if changed and row["time"]:
            row["delay"] = round((changed - row["time"]).total_seconds() / 60)
            row["time"] = changed
        if departure.get("cp"):
            row["platform"] = departure.get("cp")
        if departure.get("cs") == "c":
            row["cancelled"] = True
        if departure.get("cpth"):
            row["destination"] = departure.get("cpth").split("|")[-1]

    upcoming = [r for r in rows.values() if r["time"] and r["time"] >= now - timedelta(minutes=5)]
    return sorted(upcoming, key=lambda r: r["time"])


def main():
    parser = argparse.ArgumentParser(description="Next departures from the DB Timetables API.")
    parser.add_argument("station", nargs="?", help="station name, e.g. \"Hamburg Hbf\"")
    parser.add_argument("--eva", help="EVA number, skips the station lookup")
    parser.add_argument("--hours", type=int, default=2, help="hourly slices to fetch (default 2)")
    parser.add_argument("--limit", type=int, default=15, help="rows to print (default 15)")
    args = parser.parse_args()

    if not args.station and not args.eva:
        parser.error("give a station name or --eva")

    load_env(Path(__file__).resolve().parent.parent / ".env")
    client_id = os.environ.get("DB_CLIENT_ID")
    api_key = os.environ.get("DB_API_KEY")
    if not client_id or not api_key:
        sys.exit("missing DB_CLIENT_ID / DB_API_KEY: copy .env.example to .env and fill it in")

    if args.eva:
        name, eva = args.station or f"eva {args.eva}", args.eva
    else:
        name, eva = find_station(args.station, client_id, api_key)

    now = datetime.now()
    departures = collect(eva, args.hours, client_id, api_key, now)

    print(f"\n{name} (eva {eva})  {now:%a %d %b %H:%M}\n")
    if not departures:
        print("  no departures in this window")
        return
    for row in departures[: args.limit]:
        delay = f"+{row['delay']}" if row["delay"] > 0 else ("" if row["delay"] == 0 else str(row["delay"]))
        status = "CANCELLED" if row["cancelled"] else delay
        platform = f"pl {row['platform']}" if row["platform"] else ""
        print(
            f"  {row['time']:%H:%M} {status:>9}  {row['train']:<10} {platform:<6} {row['destination']}"
        )
    print()


if __name__ == "__main__":
    main()
