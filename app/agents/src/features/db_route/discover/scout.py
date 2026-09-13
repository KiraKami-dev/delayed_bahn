"""Tier 0: search. Registries with real APIs, plus the candidates we already know by name.

The queries are coverage-specific (our window, our stations, rail operations),
not "train datasets" in general: a generic hunt returns piles of archives that
turn out not to cover Hannover Hbf in March.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import Iterable

from .spec import DataSpec, SourceCandidate


def _get_json(url: str, timeout: int = 20):
    with urllib.request.urlopen(url, timeout=timeout) as r:  # noqa: S310
        return json.loads(r.read().decode())


def _dedupe(cands: Iterable[SourceCandidate]) -> list[SourceCandidate]:
    seen: dict[str, SourceCandidate] = {}
    for c in cands:
        seen.setdefault(c.id, c)
    return list(seen.values())


_DCAT = {"cc-by/4.0": "CC-BY-4.0", "cc-by-sa/4.0": "CC-BY-SA-4.0", "cc-zero": "CC0-1.0", "cc-by": "CC-BY-4.0",
         "dl-by-de/2.0": "DL-DE-BY-2.0", "dl-zero-de/2.0": "dl-de-zero-2.0", "odbl": "ODbL-1.0", "odc-by": "ODC-By-1.0", "other-open": "other-open"}


def _dcat_licence(uri: str) -> str | None:
    tail = uri.rstrip("/").split("licenses/")[-1].lower()
    for key, name in _DCAT.items():
        if tail.startswith(key):
            return name
    return tail or None


def huggingface(spec: DataSpec) -> list[SourceCandidate]:
    out = []
    for q in spec.queries[:6]:
        try:
            hits = _get_json(f"https://huggingface.co/api/datasets?search={urllib.parse.quote(q)}&limit=25&full=true")
        except Exception as exc:  # noqa: BLE001
            print(f"huggingface search {q!r} failed: {exc}")
            continue
        for h in hits:
            card = h.get("cardData") or {}
            lic = card.get("license")
            if isinstance(lic, list):
                lic = lic[0] if lic else None
            out.append(SourceCandidate(
                id=f"hf:{h['id']}", url=f"https://huggingface.co/datasets/{h['id']}", registry="huggingface",
                title=h.get("id", ""), licence=str(lic).upper().replace("CC-BY-4.0", "CC-BY-4.0") if lic else None,
                size_bytes=(h.get("usedStorage") or None), format="parquet", kind="unknown",
                notes=f"lastModified {h.get('lastModified', '')[:10]}, downloads {h.get('downloads')}",
                raw={"tags": h.get("tags", [])[:20], "lastModified": h.get("lastModified")},
            ))
    return out


def govdata(spec: DataSpec) -> list[SourceCandidate]:
    out = []
    for q in ("deutsche bahn", "verspätung zug", "fahrplan bahn", "schienennetz", "infrastrukturdaten db infrago"):
        try:
            res = _get_json(f"https://www.govdata.de/ckan/api/3/action/package_search?q={urllib.parse.quote(q)}&rows=25")["result"]
        except Exception as exc:  # noqa: BLE001
            print(f"govdata search {q!r} failed: {exc}")
            continue
        for p in res.get("results", []):
            fmts = sorted({(r.get("format") or "").lower() for r in p.get("resources", []) if r.get("format")})
            extras = {e.get("key"): e.get("value") for e in p.get("extras", []) if isinstance(e, dict)}
            # govdata keeps the licence on the resources as a DCAT-AP URI, not on the package.
            uris = {(r.get("license") or "") for r in p.get("resources", [])} - {""}
            licence = p.get("license_id") or next((_dcat_licence(u) for u in sorted(uris)), None)
            t_start, t_end = extras.get("temporal_start") or None, extras.get("temporal_end") or None
            out.append(SourceCandidate(
                id=f"govdata:{p['name']}", url=f"https://www.govdata.de/suche/daten/{p['name']}", registry="govdata",
                title=p.get("title", ""), licence=licence,
                temporal_start=t_start, temporal_end=t_end,
                # No temporal extent on a govdata package means reference data (a network, a station list).
                static=not (t_start or t_end),
                format=",".join(fmts) or None, kind="reference" if not (t_start or t_end) else "unknown",
                notes=f"publisher {(p.get('organization') or {}).get('title', '')}; formats {fmts}",
                raw={"resources": [r.get("url") for r in p.get("resources", [])][:5]},
            ))
    return out


def zenodo(spec: DataSpec) -> list[SourceCandidate]:
    out = []
    for q in ("deutsche bahn delay", "train delay germany dataset", "railway punctuality germany"):
        try:
            hits = _get_json(f"https://zenodo.org/api/records?q={urllib.parse.quote(q)}&size=25&sort=mostrecent")["hits"]["hits"]
        except Exception as exc:  # noqa: BLE001
            print(f"zenodo search {q!r} failed: {exc}")
            continue
        for h in hits:
            m = h.get("metadata", {})
            files = h.get("files", []) or []
            fmts = sorted({(f.get("key", "").rsplit(".", 1)[-1]).lower() for f in files if "." in f.get("key", "")})
            out.append(SourceCandidate(
                id=f"zenodo:{h.get('id')}", url=h.get("links", {}).get("self_html") or h.get("links", {}).get("html", ""),
                registry="zenodo", title=m.get("title", ""), licence=(m.get("license") or {}).get("id"),
                size_bytes=sum(f.get("size", 0) for f in files) or None, format=",".join(fmts) or None,
                credentials_required=m.get("access_right") not in (None, "open"), kind="unknown",
                notes=f"published {m.get('publication_date', '')}; access {m.get('access_right')}",
            ))
    return out


def known() -> list[SourceCandidate]:
    """Candidates we already know by name. The scout must find these *and* judge them like the rest."""
    k = lambda **kw: SourceCandidate(registry="known", **kw)  # noqa: E731
    return [
        k(id="known:piebro/deutsche-bahn-data", url="https://huggingface.co/datasets/piebro/deutsche-bahn-data", title="DB Timetables API archive (piebro)",
          licence="CC-BY-4.0", temporal_start="2024-07-01", temporal_end="2026-09-12", sampling_interval_hours=1 / 60, format="parquet", kind="events",
          notes="processed monthly parquet + raw IRIS XML; ~100 stations to 2025-11-02, all stations after"),
        k(id="known:bahn-vorhersage", url="https://opus.bibliothek.uni-augsburg.de/opus4/127213", title="Bahn-Vorhersage archive (Univ. Augsburg)",
          licence="ODbL-1.0", temporal_start="2021-09-01", temporal_end="2025-12-31", sampling_interval_hours=1 / 60, format="zip", kind="events",
          notes="DB Timetable API polled per station since 2021; ~3.5-5M stops/week"),
        k(id="known:openholidays", url="https://openholidaysapi.org/", title="OpenHolidays API", licence="ODbL-1.0",
          temporal_start="2012-01-01", temporal_end="2028-12-31", sampling_interval_hours=24, format="api", kind="calendar",
          notes="public and school holidays per Bundesland"),
        k(id="known:db-stations", url="https://cdn.jsdelivr.net/npm/db-stations@latest/full.json", title="db-stations (station hub)", licence="ISC",
          static=True, format="json", kind="reference", notes="5,388 stations: EVA, DS100, Bundesland, category, weight, coordinates"),
        k(id="known:bright-sky", url="https://api.brightsky.dev/weather", title="Bright Sky (DWD hourly weather)", licence="DL-DE-BY-2.0",
          temporal_start="2010-01-01", temporal_end="2026-09-13", sampling_interval_hours=1, format="api", kind="weather",
          notes="hourly observations for any lat/lon, no key"),
        k(id="known:infrago-infrastruktur", url="https://mobilithek.info/mdp-api/files/aux/922109165921083392/Infrastrukturdaten.zip",
          title="DB InfraGO Infrastrukturdaten", licence="CC-BY-4.0", static=True, format="zip", kind="infrastructure",
          notes="track count, electrification, line speed, Bauzustand, Betriebsstellen with DS100 and km"),
        k(id="known:zensus-2022-grid", url="https://www.destatis.de/static/DE/zensus/gitterdaten/Zensus2022_Bevoelkerungszahl.zip",
          title="Zensus 2022 population grid (100 m)", licence="DL-DE-BY-2.0", static=True, format="zip", kind="reference",
          notes="catchment population per station"),
        k(id="known:mobilithek-delfi-gtfs", url="https://mobilithek.info/offers/-6901989592576801458", title="DELFI GTFS Germany (Mobilithek)",
          licence="CC-BY-4.0", static=True, format="zip", kind="reference", credentials_required=True,
          notes="requires Mobilithek registration; timetable only, next ~30 days"),
        k(id="known:db-gtfs-rt", url="https://developers.deutschebahn.com/db-api-marketplace/apis/product/gtfs-rt", title="DB GTFS-RT",
          licence="CC-BY-4.0", temporal_start="2026-09-13", temporal_end="2026-09-13", sampling_interval_hours=1 / 60, format="api", kind="events",
          credentials_required=True, notes="live only, no history"),
        k(id="known:db-timetables-api", url="https://developers.deutschebahn.com/db-api-marketplace/apis/product/timetables", title="DB Timetables (IRIS) API",
          licence="CC-BY-4.0", temporal_start="2026-09-13", temporal_end="2026-09-14", sampling_interval_hours=1 / 60, format="api", kind="events",
          credentials_required=True, notes="~18 h forward, no history; the live layer at inference"),
        k(id="known:stada", url="https://developers.deutschebahn.com/db-api-marketplace/apis/product/stada", title="DB StaDa (station data)",
          licence="CC-BY-4.0", static=True, format="api", kind="reference", credentials_required=True, notes="accessibility, facilities"),
        k(id="known:openligadb", url="https://api.openligadb.de/", title="openligadb (football fixtures)", licence="ODbL-1.0",
          temporal_start="2025-08-01", temporal_end="2026-05-31", sampling_interval_hours=24 * 7, format="api", kind="other",
          notes="attendance null everywhere; kick-offs collinear with Saturday 15:30"),
        k(id="known:auma-messen", url="https://www.auma.de/", title="AUMA trade-fair calendar", licence=None, static=False, format="html", kind="other",
          notes="no API, no export, past events purged"),
        k(id="known:ticketmaster-discovery", url="https://developer.ticketmaster.com/", title="Ticketmaster Discovery API", licence="proprietary",
          temporal_start="2026-09-13", temporal_end="2026-12-31", sampling_interval_hours=24, format="api", kind="other", credentials_required=True,
          notes="ToS forbids caching; Eventim holds ~70% of German ticketing"),
    ]


def scout(spec: DataSpec) -> list[SourceCandidate]:
    cands = known() + huggingface(spec) + govdata(spec) + zenodo(spec)
    cands = _dedupe(cands)
    # A registry hit that duplicates a known candidate is the scout confirming it; keep both records but link them.
    for c in cands:
        if c.registry != "known" and re.search(r"piebro/deutsche-bahn-data", c.id):
            c.notes += "; duplicates known:piebro/deutsche-bahn-data (scout confirms the primary source)"
    return cands
