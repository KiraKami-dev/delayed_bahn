"""What we are looking for, and the shape every candidate is normalised to."""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass, field

# The window every profile trains on: the all-station archive era.
WINDOW = (dt.date(2025, 11, 2), dt.date(2026, 8, 31))
LICENCE_ALLOW = ("CC-BY-4.0", "CC-BY", "CC0-1.0", "CC0", "ODbL-1.0", "ODbL", "ODC-By-1.0", "MIT", "ISC",
                 "Apache-2.0", "DL-DE-BY-2.0", "dl-de/by-2-0", "dl-de-zero-2.0", "other-open", "public domain")
MACHINE_FORMATS = ("parquet", "csv", "json", "api", "zip", "gpkg", "geojson", "xml")


@dataclass
class DataSpec:
    """The question the scout asks: coverage of *our* window, stations and resolution."""

    window: tuple[dt.date, dt.date] = WINDOW
    max_interval_hours: float = 24.0  # a temporal source must resolve at least daily
    stations_sample: tuple[str, ...] = ("München Hbf", "Berlin Hbf", "Hamburg Hbf", "Köln Hbf", "Frankfurt(Main)Hbf")
    queries: tuple[str, ...] = (
        "deutsche bahn", "db timetable", "zug verspätung", "train delay germany", "bahnhof",
        "fahrplan", "schienennetz", "streckennetz", "wetter stündlich", "schulferien", "feiertage",
    )


@dataclass
class SourceCandidate:
    id: str
    url: str
    registry: str  # huggingface | govdata | zenodo | known
    title: str = ""
    licence: str | None = None
    size_bytes: int | None = None
    temporal_start: str | None = None  # ISO date, or None
    temporal_end: str | None = None
    static: bool = False  # reference data without a time axis
    sampling_interval_hours: float | None = None
    credentials_required: bool = False
    format: str | None = None
    kind: str = ""  # events | reference | calendar | weather | infrastructure | other
    notes: str = ""
    raw: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        d = asdict(self)
        d.pop("raw", None)
        return d
