"""Stage 4, agentic: the agent writes a retrieval plan per accepted source; code validates it and fetches the data.

The v1 loop stopped at decisions. Here the agent chooses, for every source that passed the gates
and the live probe, *what to fetch*: which months, which columns, which stations, which variables,
which calendar kinds, under a byte budget. Code checks the plan against the probe (a column or
month the source does not have is a rejected plan, one re-prompt with the problems, then the
source is skipped) and executes it with DuckDB over HTTP range reads or plain HTTP. Every fetch
lands as a parquet file with a manifest: rows, columns, bytes, seconds, and the plan that made it.
"""

from __future__ import annotations

import datetime as dt
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

from . import llm

PIEBRO_BASE = "https://huggingface.co/datasets/piebro/deutsche-bahn-data/resolve/main/monthly_processed_data"
OPENHOLIDAYS = "https://openholidaysapi.org"
DB_STATIONS = "https://cdn.jsdelivr.net/npm/db-stations@latest/full.json"
BRIGHT_SKY = "https://api.brightsky.dev/weather"

PLAN_SCHEMAS = {
    "known:piebro/deutsche-bahn-data": (
        '{"months": ["YYYY-MM", ...], "columns": [...], "exclude_train_types": [...], '
        '"station_filter": null or [station names], "row_limit_per_month": int, "reasoning": "..."}'),
    "hf:piebro/deutsche-bahn-data": None,  # same bytes as the known entry; skipped as a duplicate
    "known:openholidays": '{"subdivisions": ["DE-BY", ...], "kinds": ["public", "school"], "reasoning": "..."}',
    "known:db-stations": '{"fields": [...], "reasoning": "..."}',
    "known:bright-sky": ('{"variables": [...], "stations": [{"name": "...", "lat": 0.0, "lon": 0.0}, ...], '
                         '"date_from": "YYYY-MM-DD", "date_to": "YYYY-MM-DD", "reasoning": "..."}'),
}
BRIGHT_SKY_VARIABLES = ("temperature", "precipitation", "wind_speed", "wind_gust_speed", "visibility", "condition",
                        "cloud_cover", "relative_humidity", "pressure_msl", "dew_point", "sunshine")
STATION_COORDS = {"München Hbf": (48.1402, 11.5586), "Berlin Hbf": (52.5251, 13.3694), "Hamburg Hbf": (53.5527, 10.0067),
                  "Köln Hbf": (50.9430, 6.9587), "Frankfurt(Main)Hbf": (50.1071, 8.6638), "Stuttgart Hbf": (48.7837, 9.1816),
                  "Hannover Hbf": (52.3767, 9.7410), "Leipzig Hbf": (51.3455, 12.3820), "Nürnberg Hbf": (49.4456, 11.0823),
                  "Dresden Hbf": (51.0400, 13.7320)}


def _get(url: str, timeout: int = 60) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "db-route-discover/2"}), timeout=timeout) as r:  # noqa: S310
        return r.read()


def months_in(window: tuple[dt.date, dt.date]) -> list[str]:
    out, d = [], window[0].replace(day=1)
    while d <= window[1]:
        out.append(d.strftime("%Y-%m"))
        d = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return out


def plan_for(entry: dict, need: str, window: tuple, budget: dict, problems: list[str] | None = None) -> dict | None:
    """Ask the agent for a retrieval plan; `problems` carries the verifier's objections on a re-prompt."""
    schema = PLAN_SCHEMAS.get(entry["id"])
    if not schema:
        return None
    probe = entry.get("probe", {})
    facts = {k: v for k, v in probe.items() if k in ("columns_typed", "per_month", "fields", "stations", "coverage_step")}
    system = ("You plan data retrieval for a train-delay forecasting dataset. Reply with one JSON object exactly in the "
              "given schema. Choose only what the source actually has (see the probe facts). Prefer the smallest fetch "
              "that serves the need; say why in 'reasoning'. Never invent columns, months or fields.")
    user = (f"Need: {need}\nWindow: {window[0]} to {window[1]}.\nBudget: {json.dumps(budget)}.\n"
            f"Source: {entry['id']} ({entry.get('kind')}), role: {entry.get('rubric', {}).get('role', '')}.\n"
            f"Probe facts: {json.dumps(facts, ensure_ascii=False)[:3000]}\n"
            + (f"Bright Sky variables available: {list(BRIGHT_SKY_VARIABLES)}; station coordinates known: {list(STATION_COORDS)}\n"
               if entry["id"] == "known:bright-sky" else "")
            + (f"Your previous plan was rejected: {problems}. Fix exactly these.\n" if problems else "")
            + f"Schema: {schema}")
    return llm.chat(f"retrieval plan {entry['id']}", system, user, max_tokens=700)


def validate_plan(entry: dict, plan: dict, window: tuple, budget: dict) -> list[str]:
    """Deterministic checks against the probe and the budget. Empty list = the plan stands."""
    p = entry.get("probe", {}); sid = entry["id"]; bad: list[str] = []
    if sid == "known:piebro/deutsche-bahn-data":
        have_cols = {c[0] for c in p.get("columns_typed", [])}
        have_months = set(p.get("per_month", {}))
        cols = plan.get("columns") or []
        months = plan.get("months") or []
        bad += [f"unknown column {c}" for c in cols if c not in have_cols]
        bad += [f"month {m} not in the archive probe" for m in months if m not in have_months]
        bad += [f"month {m} outside the window" for m in months if m not in months_in(window)]
        if not cols: bad.append("no columns chosen")
        if not months: bad.append("no months chosen")
        if len(months) > budget.get("max_months", 1): bad.append(f"at most {budget.get('max_months', 1)} month(s) under this budget")
        for req in ("time", "station_name", "delay_in_min"):
            if req not in cols: bad.append(f"required column {req} missing (the target and its keys)")
        if not isinstance(plan.get("row_limit_per_month"), int) or plan["row_limit_per_month"] > budget.get("max_rows_per_month", 10**9):
            bad.append(f"row_limit_per_month must be an int <= {budget.get('max_rows_per_month')}")
    elif sid == "known:openholidays":
        subs = plan.get("subdivisions") or []
        bad += [f"bad subdivision {s}" for s in subs if not (isinstance(s, str) and s.startswith("DE-") and len(s) == 5)]
        if not subs: bad.append("no subdivisions")
        if not set(plan.get("kinds") or []) <= {"public", "school"} or not plan.get("kinds"): bad.append("kinds must be a subset of public, school")
    elif sid == "known:db-stations":
        have = set(p.get("fields", []))
        fields = plan.get("fields") or []
        bad += [f"unknown field {f}" for f in fields if have and f not in have]
        if not fields: bad.append("no fields")
    elif sid == "known:bright-sky":
        bad += [f"unknown variable {v}" for v in plan.get("variables") or [] if v not in BRIGHT_SKY_VARIABLES]
        st = plan.get("stations") or []
        if not st: bad.append("no stations")
        if len(st) > budget.get("max_weather_stations", 3): bad.append(f"at most {budget.get('max_weather_stations', 3)} stations under this budget")
        try:
            a, b = dt.date.fromisoformat(plan["date_from"]), dt.date.fromisoformat(plan["date_to"])
            if (b - a).days > budget.get("max_weather_days", 7) or b < a: bad.append(f"date span must be 0..{budget.get('max_weather_days', 7)} days")
            if a < window[0] or b > window[1]: bad.append("dates outside the window")
        except Exception:  # noqa: BLE001
            bad.append("date_from/date_to must be ISO dates")
    return bad


def execute(entry: dict, plan: dict, out_dir: Path) -> dict:
    """Run a validated plan. Returns the manifest; raises on transport errors (the caller records them)."""
    import duckdb  # noqa: PLC0415

    sid = entry["id"]; t0 = time.time(); out_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    if sid == "known:piebro/deutsche-bahn-data":
        con.execute("INSTALL httpfs; LOAD httpfs;")
        path = out_dir / "events.parquet"
        cols = ", ".join(f'"{c}"' for c in plan["columns"])
        excl = plan.get("exclude_train_types") or []
        where = ["TRUE"]
        if excl: where.append("train_type NOT IN (" + ", ".join("'" + t.replace("'", "''") + "'" for t in excl) + ")")
        if plan.get("station_filter"): where.append("station_name IN (" + ", ".join("'" + s.replace("'", "''") + "'" for s in plan["station_filter"]) + ")")
        parts = []
        for m in plan["months"]:
            parts.append(f"SELECT {cols} FROM read_parquet('{PIEBRO_BASE}/data-{m}.parquet') WHERE {' AND '.join(where)} LIMIT {int(plan['row_limit_per_month'])}")
        con.execute(f"COPY ({' UNION ALL '.join(parts)}) TO '{path}' (FORMAT PARQUET)")
    elif sid == "known:openholidays":
        path = out_dir / "holidays.parquet"; rows = []
        for sub in plan["subdivisions"]:
            for kind in plan["kinds"]:
                ep = "PublicHolidays" if kind == "public" else "SchoolHolidays"
                url = (f"{OPENHOLIDAYS}/{ep}?countryIsoCode=DE&languageIsoCode=DE&validFrom={plan.get('date_from', '2025-11-01')}"
                       f"&validTo={plan.get('date_to', '2026-09-30')}&subdivisionCode={sub}")
                for x in json.loads(_get(url)):
                    rows.append({"subdivision": sub, "kind": kind, "start": x.get("startDate"), "end": x.get("endDate"),
                                 "name": (x.get("name") or [{}])[0].get("text"), "nationwide": x.get("nationwide"), "type": x.get("type")})
        tmp = out_dir / "holidays.json"; tmp.write_text(json.dumps(rows))
        con.execute(f"COPY (SELECT * FROM read_json_auto('{tmp}')) TO '{path}' (FORMAT PARQUET)"); tmp.unlink()
    elif sid == "known:db-stations":
        path = out_dir / "stations.parquet"
        data = json.loads(_get(DB_STATIONS)); fields = plan["fields"]
        rows = [{f: (x.get(f) if not isinstance(x.get(f), (dict, list)) else json.dumps(x.get(f), ensure_ascii=False)) for f in fields} for x in data]
        tmp = out_dir / "stations.json"; tmp.write_text(json.dumps(rows, ensure_ascii=False))
        con.execute(f"COPY (SELECT * FROM read_json_auto('{tmp}')) TO '{path}' (FORMAT PARQUET)"); tmp.unlink()
    elif sid == "known:bright-sky":
        path = out_dir / "weather.parquet"; rows = []
        for st in plan["stations"]:
            lat, lon = (st.get("lat"), st.get("lon")) if st.get("lat") else STATION_COORDS.get(st.get("name"), (None, None))
            if lat is None: continue
            url = f"{BRIGHT_SKY}?lat={lat}&lon={lon}&date={plan['date_from']}&last_date={plan['date_to']}"
            for w in json.loads(_get(url)).get("weather", []):
                rows.append({"station": st.get("name"), "timestamp": w.get("timestamp"), **{v: w.get(v) for v in plan["variables"]}})
        tmp = out_dir / "weather.json"; tmp.write_text(json.dumps(rows))
        con.execute(f"COPY (SELECT * FROM read_json_auto('{tmp}')) TO '{path}' (FORMAT PARQUET)"); tmp.unlink()
    else:
        raise ValueError(f"no executor for {sid}")
    n, ncol = con.execute(f"SELECT count(*), (SELECT count(*) FROM (DESCRIBE SELECT * FROM read_parquet('{path}'))) FROM read_parquet('{path}')").fetchone()
    return {"path": str(path), "rows": int(n), "columns": int(ncol), "bytes": path.stat().st_size, "seconds": round(time.time() - t0, 1), "plan": plan}
