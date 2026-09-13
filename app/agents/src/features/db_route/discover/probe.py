"""Tier 2: probe. Cheap, measured facts about a source that the rubric and the gates cannot know from metadata."""

from __future__ import annotations

import datetime as dt
import json
import urllib.request

from .spec import SourceCandidate


def _get(url: str, timeout: int = 30) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as r:  # noqa: S310
        return r.read()


def _head(url: str, timeout: int = 20) -> dict:
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
        return {"status": r.status, "content_length": r.headers.get("Content-Length"), "content_type": r.headers.get("Content-Type")}


def probe_piebro() -> dict:
    """Schema, one month's row count, and stations-per-month across the coverage step -- over HTTP range reads."""
    import duckdb  # noqa: PLC0415

    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    base = "https://huggingface.co/datasets/piebro/deutsche-bahn-data/resolve/main/monthly_processed_data"
    schema = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{base}/data-2026-08.parquet')").fetchall()
    per_month = {}
    for m in ("2025-10", "2025-11", "2026-08"):
        n, st = con.execute(f"SELECT count(*), count(DISTINCT station_name) FROM read_parquet('{base}/data-{m}.parquet')").fetchone()
        per_month[m] = {"rows": int(n), "stations": int(st)}
    cols = [c[0] for c in schema]
    return {
        "columns": cols, "columns_typed": [[c[0], c[1]] for c in schema], "n_columns": len(cols), "per_month": per_month,
        "has_actual_times": any("change_time" in c for c in cols), "has_cancellation": any("cancel" in c for c in cols),
        "has_platform": any("platform" in c for c in cols), "has_cause_codes": False,
        "coverage_step": {"before": per_month["2025-10"]["stations"], "after": per_month["2025-11"]["stations"],
                          "ratio": round(per_month["2025-11"]["stations"] / max(1, per_month["2025-10"]["stations"]), 1)},
        "notes": "cause codes live only in raw_data/ IRIS XML (measured 30.1% of stops carry one)",
    }


def probe_openholidays() -> dict:
    d = json.loads(_get("https://openholidaysapi.org/SchoolHolidays?countryIsoCode=DE&languageIsoCode=DE&validFrom=2025-11-01&validTo=2026-09-30&subdivisionCode=DE-BY"))
    p = json.loads(_get("https://openholidaysapi.org/PublicHolidays?countryIsoCode=DE&languageIsoCode=DE&validFrom=2025-11-01&validTo=2026-09-30&subdivisionCode=DE-BY"))
    return {"school_periods_BY": len(d), "public_holidays_BY": len(p), "fields": sorted(d[0].keys()) if d else []}


def probe_db_stations() -> dict:
    d = json.loads(_get("https://cdn.jsdelivr.net/npm/db-stations@latest/full.json"))
    return {"stations": len(d), "fields": sorted(d[0].keys())[:20], "with_federal_state": sum(1 for x in d if x.get("federalState"))}


def probe_bright_sky() -> dict:
    d = json.loads(_get("https://api.brightsky.dev/weather?lat=48.1402&lon=11.5586&date=2026-06-01&last_date=2026-06-08"))
    w = d.get("weather", [])
    return {"hourly_rows_one_week": len(w), "fields": sorted(w[0].keys()) if w else [], "source": (d.get("sources") or [{}])[0].get("station_name")}


def probe_head(url: str) -> dict:
    h = _head(url)
    return {"status": h["status"], "size_mb": round(int(h["content_length"]) / 1e6, 1) if h.get("content_length") else None, "content_type": h.get("content_type")}


PROBES = {
    "known:piebro/deutsche-bahn-data": probe_piebro,
    "hf:piebro/deutsche-bahn-data": probe_piebro,
    "known:openholidays": probe_openholidays,
    "known:db-stations": probe_db_stations,
    "known:bright-sky": probe_bright_sky,
    "known:infrago-infrastruktur": lambda: probe_head("https://mobilithek.info/mdp-api/files/aux/922109165921083392/Infrastrukturdaten.zip"),
    "known:zensus-2022-grid": lambda: probe_head("https://www.destatis.de/static/DE/zensus/gitterdaten/Zensus2022_Bevoelkerungszahl.zip"),
}


def probe(c: SourceCandidate) -> dict:
    fn = PROBES.get(c.id)
    if fn is None:
        return {"probed": False, "reason": "no probe for this source; accepted on metadata only"}
    started = dt.datetime.now()
    try:
        out = fn()
        out.update(probed=True, seconds=round((dt.datetime.now() - started).total_seconds(), 1))
        return out
    except Exception as exc:  # noqa: BLE001
        return {"probed": False, "error": str(exc)[:200]}
