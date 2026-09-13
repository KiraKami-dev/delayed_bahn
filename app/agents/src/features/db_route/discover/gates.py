"""Tier 1: assess. Hard gates, each a deterministic predicate with a stated reason."""

from __future__ import annotations

import datetime as dt
import re

from .spec import LICENCE_ALLOW, MACHINE_FORMATS, DataSpec, SourceCandidate

RAIL_TERMS = re.compile(r"bahn|zug|train|rail|verspät|delay|fahrplan|timetable|haltestell|station|schienen|strecke|infrastruktur|"
                        r"punctual|pünktlich|holiday|ferien|feiertag|wetter|weather|zensus|bevölkerung|population|gtfs|iris", re.I)
NOT_OPERATIONS = re.compile(r"mnist|faq|email|lektion|kultur|begrün|octopos|hello world|synonymous|dissertation", re.I)


def _date(s: str | None) -> dt.date | None:
    if not s:
        return None
    try:
        return dt.date.fromisoformat(s[:10])
    except ValueError:
        return None


def gate(c: SourceCandidate, spec: DataSpec) -> tuple[bool, str]:
    """(accepted, reason). The first failing gate is the reason; order is cheapest-first."""
    text = f"{c.title} {c.id} {c.notes}"
    if NOT_OPERATIONS.search(text) or not RAIL_TERMS.search(text):
        return False, "not about rail operations, weather, calendar or infrastructure (name/description)"
    if c.credentials_required:
        return False, "needs registration or an API key: not reproducible by a stranger running timenet-build"
    if not c.licence:
        return False, "licence not stated"
    if not any(c.licence.lower().startswith(a.lower()) for a in LICENCE_ALLOW):
        return False, f"licence {c.licence!r} not in the open allowlist"
    if c.format and not any(f in c.format.lower() for f in MACHINE_FORMATS):
        return False, f"format {c.format!r} is not machine-readable data (map service / html / pdf)"
    if not c.static:
        s, e = _date(c.temporal_start), _date(c.temporal_end)
        if s is None or e is None:
            # A registry rarely states the extent. Do not reject on silence: the probe can measure
            # it, and run.py only lets the candidate through if the probe actually does.
            return True, "temporal coverage not stated; accepted only if a probe measures it"
        if e < spec.window[0] or s > spec.window[1]:
            return False, f"coverage {s}..{e} does not overlap the window {spec.window[0]}..{spec.window[1]}"
        if c.sampling_interval_hours is not None and c.sampling_interval_hours > spec.max_interval_hours:
            return False, f"resolution {c.sampling_interval_hours:.0f} h is coarser than the {spec.max_interval_hours:.0f} h the profiles need"
    return True, "passes every gate"
