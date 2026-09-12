"""IRIS delay-cause codes: the table, the families, and the XML projection.

Deutsche Bahn's Timetables (IRIS) API attaches ``<m>`` message elements to a stop.
Each carries a numeric cause code ``c`` and a German display category ``cat``.
The processed monthly parquet files drop both; only ``raw_data/`` keeps the
original XML, so this module is the only path to "why was it late".

Measured on 2026-08-04 (400 fchg responses, 23,292 stop elements): 30.1% of stops
carry at least one code. That number is the point, not a shortfall -- most delay
is not attributable to a named cause, and the dataset has to say so rather than
inventing one. See ATTRIBUTION_FLOOR below.

Codes 1-69 are delay causes, 70-98 are quality-of-service remarks (a missing
coach is not why the train is late), 99 is a generic catch-all. Two codes appear
in the data but not in DB's published range and are handled explicitly:
  0     the most frequent value by far; a placeholder on messages that carry no
        cause at all. NOT counted as attributed.
  1000  a HIM (Hafas Information Manager) message id, not a cause. Ignored.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Iterator, NamedTuple
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")

# --- the code table ---------------------------------------------------------
# German text as DB renders it. Kept verbatim: it is what a German traveller
# reads on the platform display, and the rationale quotes it.

CAUSE_TEXT: dict[int, str] = {
    1: "Nähere Informationen in Kürze",
    2: "Polizeieinsatz",
    3: "Feuerwehreinsatz auf der Strecke",
    4: "Kurzfristiger Personalausfall",
    5: "Ärztliche Versorgung eines Fahrgastes",
    6: "Betätigen der Notbremse",
    7: "Unbefugte Personen auf der Strecke",
    8: "Notarzteinsatz auf der Strecke",
    9: "Streikauswirkungen",
    10: "Tiere auf der Strecke",
    11: "Unwetter",
    12: "Warten auf ein verspätetes Schiff",
    13: "Pass- und Zollkontrolle",
    14: "Defekt am Bahnhof",
    15: "Beeinträchtigung durch Vandalismus",
    16: "Entschärfung einer Fliegerbombe",
    17: "Beschädigung einer Brücke",
    18: "Umgestürzter Baum auf der Strecke",
    19: "Unfall an einem Bahnübergang",
    20: "Tiere im Gleis",
    21: "Warten auf Anschlussreisende",
    22: "Witterungsbedingte Beeinträchtigungen",
    23: "Betriebsstabilisierung",
    24: "Verspätung im Ausland",
    25: "Bereitstellung weiterer Wagen",
    26: "Abhängen von Wagen",
    27: "Technische Störung am Bus",
    28: "Gegenstände auf der Strecke",
    29: "Ersatzverkehr mit Bus ist eingerichtet",
    30: "Personalausfall im Stellwerk",
    31: "Bauarbeiten",
    32: "Längere Haltezeit am Bahnhof",
    33: "Defekt an der Oberleitung",
    34: "Defekt an einem Signal",
    35: "Streckensperrung",
    36: "Technische Störung am Zug",
    37: "Kurzfristiger Fahrzeugausfall",
    38: "Defekt an der Strecke",
    39: "Stau / Hohes Verkehrsaufkommen",
    40: "Defektes Stellwerk",
    41: "Defekt an einem Bahnübergang",
    42: "Außerplanmäßige Geschwindigkeitsbeschränkung",
    43: "Verspätung eines vorausfahrenden Zuges",
    44: "Warten auf einen entgegenkommenden Zug",
    45: "Vorfahrt eines anderen Zuges",
    46: "Vorfahrt eines anderen Zuges",
    47: "Verspätete Bereitstellung",
    48: "Verspätung aus vorheriger Fahrt",
    49: "Kurzfristiger Personalausfall",
    50: "Kurzfristige Erkrankung von Personal",
    51: "Verspätetes Personal aus vorheriger Fahrt",
    52: "Streik",
    53: "Unwetterauswirkungen",
    54: "Verfügbarkeit der Gleise derzeit eingeschränkt",
    55: "Technischer Defekt an einem anderen Zug",
    56: "Laden der Antriebsbatterie",
    57: "Zusätzlicher Halt",
    58: "Umleitung",
    59: "Schnee und Eis",
    60: "Witterungsbedingt verminderte Geschwindigkeit",
    61: "Defekte Tür",
    62: "Behobener Defekt am Zug",
    63: "Technische Untersuchung am Zug",
    64: "Defekt an einer Weiche",
    65: "Erdrutsch",
    66: "Hochwasser",
    67: "Behördliche Maßnahme",
    68: "Hohes Fahrgastaufkommen",
    69: "Zug verkehrt mit verminderter Geschwindigkeit",
    99: "Verzögerungen im Betriebsablauf",
}

# --- families ---------------------------------------------------------------
# Six families over the delay codes. Chosen so each is (a) frequent enough to
# make a dense series and (b) something a traveller can act on differently.
# A code appears in at most one family.

CAUSE_FAMILY: dict[str, frozenset[int]] = {
    # Track works and anything that closes or slows a line on purpose. The
    # regime-shift family: present for weeks, absent the quarter before.
    "works": frozenset({31, 35, 42, 54, 58}),
    # Weather, including its second-order effects.
    "weather": frozenset({11, 22, 53, 59, 60, 66, 65, 18}),
    # Kit that broke: infrastructure and rolling stock alike.
    "technical": frozenset({14, 27, 33, 34, 36, 37, 38, 40, 41, 55, 56, 61, 62, 63, 64}),
    # Delay imported from elsewhere in the network. The dominant family in
    # practice, and the one a buffer actually protects against.
    "knock_on": frozenset({21, 23, 24, 39, 43, 44, 45, 46, 47, 48, 12, 32, 57, 69, 99}),
    # People who were not there.
    "staff": frozenset({4, 9, 30, 49, 50, 51, 52}),
    # Incidents on or beside the track, including emergencies.
    "external": frozenset({2, 3, 5, 6, 7, 8, 10, 13, 15, 16, 17, 19, 20, 28, 67, 68}),
}

FAMILY_NAMES: tuple[str, ...] = tuple(CAUSE_FAMILY)

# The five families carried as their own series. "external" is deliberately not
# among them: it is a grab-bag of one-off incidents with no temporal structure a
# model could learn, so it would be a series the rationale never cites.
SERIES_FAMILIES: tuple[str, ...] = ("works", "weather", "technical", "knock_on", "staff")

_CODE_TO_FAMILY: dict[int, str] = {
    code: family for family, codes in CAUSE_FAMILY.items() for code in codes
}

# Quality-of-service remarks. Real information, but not a reason the train is
# late, so they never enter delay attribution.
QOS_RANGE = range(70, 99)

# Seen in the data, outside DB's published cause range. See module docstring.
PLACEHOLDER_CODES = frozenset({0})
HIM_MESSAGE_FLOOR = 1000

# The rationale may name a cause only when at least this share of delayed stops
# carry one. Below it, the honest statement is that the delay is diffuse.
ATTRIBUTION_FLOOR = 0.35
# ...and only when a single family holds at least this share of attributed
# delay minutes. Otherwise no one cause is responsible.
DOMINANCE_FLOOR = 0.40


def is_delay_cause(code: int) -> bool:
    """True for codes that explain lateness, excluding QoS and placeholders."""
    if code in PLACEHOLDER_CODES or code >= HIM_MESSAGE_FLOOR:
        return False
    if code in QOS_RANGE:
        return False
    return code in CAUSE_TEXT


def family_of(code: int) -> str | None:
    """The family a delay code belongs to, or None if it is not a delay cause."""
    return _CODE_TO_FAMILY.get(code) if is_delay_cause(code) else None


def describe(code: int) -> str:
    """German cause text, falling back to a stable label for unknown codes."""
    return CAUSE_TEXT.get(code, f"Ursachencode {code}")


# --- XML projection ---------------------------------------------------------
# Measured on 2026-08-04 (36,006 message elements): the archive carries TWO
# disjoint kinds of ``<m>``, and conflating them is a real bug.
#
#   t="h"          17,841   never a cause code, ALWAYS from/to/cat/pr
#                           -> a HIM planned-disruption notice, with real dates
#   t in d,f,q     17,955   ALWAYS a cause code, never from/to
#                           -> the per-stop reason this train is late
#   t="c"             210   neither; negligible
#
# The overlap is zero, so one extractor cannot serve both. They also land in
# different parts of the TimeNet model: codes become cause-family rate channels,
# notices become interval annotations.
#
# Regex rather than a DOM parse, deliberately. The raw column holds one
# ``<timetable>`` document per (station, hour) and we want a handful of
# attributes out of it; ElementTree would build the whole tree to reach them,
# and there are ~24,000 such documents per day across two years. The shapes are
# fixed by DB's own XSD, so the patterns are not guessing at loose markup.

_STOP_RE = re.compile(r'<s\s+id="([^"]+)"(.*?)</s>', re.S)
_MSG_RE = re.compile(r"<m\b[^>]*>")
_TYPE_RE = re.compile(r'\bt="([^"]*)"')
_CODE_RE = re.compile(r'\bc="(\d+)"')
_CAT_RE = re.compile(r'\bcat="([^"]*)"')
_ID_RE = re.compile(r'\bid="([^"]*)"')
_FROM_RE = re.compile(r'\bfrom="(\d{10})"')
_TO_RE = re.compile(r'\bto="(\d{10})"')
_PRIO_RE = re.compile(r'\bpr="(\d+)"')
_TS_RE = re.compile(r'\bts="(\d{10})"')

# Message types that carry a delay cause code.
CAUSE_TYPES = frozenset({"d", "f", "q"})
# Message type that carries a dated planned-disruption notice.
NOTICE_TYPE = "h"

# DB appends a provenance suffix to some categories ("Bauarbeiten. (Quelle:
# zuginfo.nrw)"). The category itself is what a traveller reads.
_SOURCE_SUFFIX = ". (Quelle:"


def _clean_category(raw: str) -> str:
    return raw.split(_SOURCE_SUFFIX)[0].strip()


def _parse_iris_time(stamp: str) -> dt.datetime:
    """IRIS stamps are ``YYMMDDHHmm`` in Europe/Berlin local time."""
    return dt.datetime.strptime(stamp, "%y%m%d%H%M").replace(tzinfo=BERLIN)


class StopCauses(NamedTuple):
    """Delay causes attached to one stop event.

    ``stop_id`` matches the ``id`` column of ``monthly_processed_data``. IRIS
    spells it ``<ride_id>-<YYMMDDHHmm>-<stop_number>``, so the join is exact.
    """

    stop_id: str
    codes: tuple[int, ...]  # delay causes only, deduplicated, sorted
    families: tuple[str, ...]  # families those codes fall into


class DisruptionNotice(NamedTuple):
    """A dated planned-disruption notice, as attached to one stop.

    One notice is broadcast across many stops -- measured at 335 distinct ids
    behind 18,364 attachments in a single day, 190 of them spanning more than
    one station. Callers deduplicate on ``notice_id`` before emitting an
    annotation, or a single construction project becomes fifty identical ones.

    Windows are long: median 22.5 days, p90 64, max 685, and 79% exceed a week.
    """

    notice_id: str
    stop_id: str
    category: str  # German display text: Bauarbeiten, Störung, Information...
    valid_from: dt.datetime
    valid_to: dt.datetime
    priority: int  # 1 = highest .. 4
    issued_at: dt.datetime | None  # when DB published it

    @property
    def duration_days(self) -> float:
        return (self.valid_to - self.valid_from).total_seconds() / 86400.0

    @property
    def is_works(self) -> bool:
        """True for construction notices -- 34% of all dated notices."""
        return self.category.startswith("Bauarbeiten")


def _iter_stop_messages(xml: str) -> Iterator[tuple[str, str]]:
    """Yield ``(stop_id, message_element)`` for every ``<m>`` inside a stop."""
    if not xml or "<m " not in xml:
        return
    for stop_id, body in _STOP_RE.findall(xml):
        if "<m " not in body:
            continue
        for msg in _MSG_RE.findall(body):
            yield stop_id, msg


def parse_stop_causes(xml: str) -> Iterator[StopCauses]:
    """Yield one StopCauses per stop that carries at least one delay cause.

    Stops with no message, or only QoS and placeholder messages, are skipped.
    They are the unattributed majority -- roughly 70% of stops -- and the caller
    counts them as the denominator rather than storing them per-stop.
    """
    by_stop: dict[str, set[int]] = {}
    for stop_id, msg in _iter_stop_messages(xml):
        msg_type = _TYPE_RE.search(msg)
        if msg_type is None or msg_type.group(1) not in CAUSE_TYPES:
            continue
        code_match = _CODE_RE.search(msg)
        if code_match is None:
            continue
        code = int(code_match.group(1))
        if is_delay_cause(code):
            by_stop.setdefault(stop_id, set()).add(code)
    for stop_id, codes in by_stop.items():
        ordered = tuple(sorted(codes))
        families = tuple(dict.fromkeys(f for f in map(family_of, ordered) if f))
        yield StopCauses(stop_id, ordered, families)


def parse_disruption_notices(xml: str) -> Iterator[DisruptionNotice]:
    """Yield one DisruptionNotice per (notice, stop) attachment.

    Deduplicate on ``notice_id`` downstream: the same notice reaches ~55 stops.
    """
    for stop_id, msg in _iter_stop_messages(xml):
        msg_type = _TYPE_RE.search(msg)
        if msg_type is None or msg_type.group(1) != NOTICE_TYPE:
            continue
        notice_id = _ID_RE.search(msg)
        valid_from = _FROM_RE.search(msg)
        valid_to = _TO_RE.search(msg)
        if not (notice_id and valid_from and valid_to):
            continue
        category = _CAT_RE.search(msg)
        priority = _PRIO_RE.search(msg)
        issued = _TS_RE.search(msg)
        yield DisruptionNotice(
            notice_id=notice_id.group(1),
            stop_id=stop_id,
            category=_clean_category(category.group(1)) if category else "",
            valid_from=_parse_iris_time(valid_from.group(1)),
            valid_to=_parse_iris_time(valid_to.group(1)),
            priority=int(priority.group(1)) if priority else 4,
            issued_at=_parse_iris_time(issued.group(1)) if issued else None,
        )


def parse_stops(xml: str) -> tuple[list[StopCauses], list[DisruptionNotice]]:
    """Both projections in one pass over the document.

    Calling ``parse_stop_causes`` and ``parse_disruption_notices`` separately
    scans the XML twice, and the stop regex over a 580 MB day is most of the
    cost -- measured at roughly double the runtime. Since every extraction wants
    both, dispatch by message type in a single walk instead.
    """
    causes: list[StopCauses] = []
    notices: list[DisruptionNotice] = []
    if not xml or "<m " not in xml:
        return causes, notices

    for stop_id, body in _STOP_RE.findall(xml):
        if "<m " not in body:
            continue
        codes: set[int] = set()
        for msg in _MSG_RE.findall(body):
            msg_type = _TYPE_RE.search(msg)
            if msg_type is None:
                continue
            kind = msg_type.group(1)
            if kind in CAUSE_TYPES:
                code_match = _CODE_RE.search(msg)
                if code_match:
                    code = int(code_match.group(1))
                    if is_delay_cause(code):
                        codes.add(code)
            elif kind == NOTICE_TYPE:
                notice_id = _ID_RE.search(msg)
                valid_from = _FROM_RE.search(msg)
                valid_to = _TO_RE.search(msg)
                if not (notice_id and valid_from and valid_to):
                    continue
                category = _CAT_RE.search(msg)
                priority = _PRIO_RE.search(msg)
                issued = _TS_RE.search(msg)
                notices.append(
                    DisruptionNotice(
                        notice_id=notice_id.group(1),
                        stop_id=stop_id,
                        category=_clean_category(category.group(1)) if category else "",
                        valid_from=_parse_iris_time(valid_from.group(1)),
                        valid_to=_parse_iris_time(valid_to.group(1)),
                        priority=int(priority.group(1)) if priority else 4,
                        issued_at=_parse_iris_time(issued.group(1)) if issued else None,
                    )
                )
        if codes:
            ordered = tuple(sorted(codes))
            families = tuple(dict.fromkeys(f for f in map(family_of, ordered) if f))
            causes.append(StopCauses(stop_id, ordered, families))
    return causes, notices
