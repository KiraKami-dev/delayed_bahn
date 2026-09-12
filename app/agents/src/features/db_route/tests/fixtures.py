"""Synthetic in-memory DuckDB fixtures. No network, no cache, no fact tables.

The tables here carry the real column names and types of
``monthly_processed_data`` and of the ``causes``/``notices`` day shards, because
the point of the offline tests is to exercise the *actual SQL* the modules run.
A fixture that hands the functions a pandas frame would test the Python and
leave every ``date_trunc``, ``unnest`` and range join untested, which is where
the interesting mistakes live.

Everything is generated from a fixed seed and a fixed calendar. There is no
randomness anywhere in the pipeline under test, so a fixture with unseeded
randomness would make a failure unreproducible for no benefit.
"""

from __future__ import annotations

import datetime as dt
import random
from dataclasses import dataclass, field

import duckdb
import pyarrow as pa

EPOCH = dt.date(2026, 1, 1)

EVENT_DDL = """
CREATE TABLE events (
    station_name              VARCHAR,
    eva                       VARCHAR,
    train_number              VARCHAR,
    line_number               VARCHAR,
    final_destination_station VARCHAR,
    delay_in_min              INTEGER,
    time                      TIMESTAMP,
    arrival_is_canceled       BOOLEAN,
    departure_is_canceled     BOOLEAN,
    train_type                VARCHAR,
    train_line_ride_id        VARCHAR,
    train_line_station_num    INTEGER,
    arrival_planned_time      TIMESTAMP,
    arrival_change_time       TIMESTAMP,
    departure_planned_time    TIMESTAMP,
    departure_change_time     TIMESTAMP,
    id                        VARCHAR
)
"""

CAUSE_DDL = "CREATE TABLE causes (stop_id VARCHAR, codes SMALLINT[], families VARCHAR[])"
NOTICE_DDL = """
CREATE TABLE notices (
    notice_id VARCHAR, category VARCHAR,
    valid_from TIMESTAMPTZ, valid_to TIMESTAMPTZ,
    priority TINYINT, issued_at TIMESTAMPTZ, stop_ids VARCHAR[]
)
"""


_TS = pa.timestamp("us")
_TSTZ = pa.timestamp("us", tz="UTC")
_EVENT_SCHEMA = pa.schema(
    [
        ("station_name", pa.string()),
        ("eva", pa.string()),
        ("train_number", pa.string()),
        ("line_number", pa.string()),
        ("final_destination_station", pa.string()),
        ("delay_in_min", pa.int32()),
        ("time", _TS),
        ("arrival_is_canceled", pa.bool_()),
        ("departure_is_canceled", pa.bool_()),
        ("train_type", pa.string()),
        ("train_line_ride_id", pa.string()),
        ("train_line_station_num", pa.int32()),
        ("arrival_planned_time", _TS),
        ("arrival_change_time", _TS),
        ("departure_planned_time", _TS),
        ("departure_change_time", _TS),
        ("id", pa.string()),
    ]
)
_CAUSE_SCHEMA = pa.schema(
    [("stop_id", pa.string()), ("codes", pa.list_(pa.int16())), ("families", pa.list_(pa.string()))]
)
_NOTICE_SCHEMA = pa.schema(
    [
        ("notice_id", pa.string()),
        ("category", pa.string()),
        ("valid_from", _TSTZ),
        ("valid_to", _TSTZ),
        ("priority", pa.int8()),
        ("issued_at", _TSTZ),
        ("stop_ids", pa.list_(pa.string())),
    ]
)


def _load(con: duckdb.DuckDBPyConnection, table: str, rows: list[tuple], schema: pa.Schema) -> None:
    if not rows:
        return
    columns = {
        field.name: pa.array([row[i] for row in rows], field.type)
        for i, field in enumerate(schema)
    }
    view = f"_src_{table}"
    con.register(view, pa.table(columns, schema=schema))
    con.execute(f"INSERT INTO {table} SELECT * FROM {view}")
    con.unregister(view)


@dataclass
class Fixture:
    """One synthetic month-or-more of stop events, plus causes and notices."""

    con: duckdb.DuckDBPyConnection
    events: list[tuple] = field(default_factory=list)
    causes: list[tuple] = field(default_factory=list)
    notices: list[tuple] = field(default_factory=list)

    def add_service(
        self,
        *,
        train_type: str,
        destination: str,
        station: str,
        start: dt.date,
        days: int,
        hour: int = 8,
        weekdays: tuple[int, ...] = (0, 1, 2, 3, 4, 5, 6),
        delay: int = 2,
        jitter: int = 0,
        seed: int = 0,
        cancelled: bool = False,
        families: tuple[str, ...] = (),
        family_days: tuple[dt.date, ...] | None = None,
        per_day: int = 1,
    ) -> None:
        """One (service_group, station) pair running on a fixed daily pattern.

        ``families`` attaches a cause row to every stop, or only to the dates in
        ``family_days`` -- which is how a works period is built: the same pair,
        the same delay, a cause code present for a stretch of days and absent
        either side.
        """
        rng = random.Random(seed)
        ride_base = f"{train_type}-{destination}-{station}"
        for offset in range(days):
            day = start + dt.timedelta(days=offset)
            if day.weekday() not in weekdays:
                continue
            for slot in range(per_day):
                when = dt.datetime.combine(day, dt.time(hour + slot, 17))
                value = delay + (rng.randint(-jitter, jitter) if jitter else 0)
                stop_id = f"{ride_base}-{day.isoformat()}-{slot}"
                self.events.append(
                    (
                        station,
                        "8000000",
                        "1",
                        "",
                        destination,
                        value,
                        when,
                        cancelled,
                        cancelled,
                        train_type,
                        f"{ride_base}-{day.isoformat()}",
                        slot + 1,
                        when,
                        when + dt.timedelta(minutes=value),
                        when,
                        when + dt.timedelta(minutes=value),
                        stop_id,
                    )
                )
                if families and (family_days is None or day in family_days):
                    self.causes.append((stop_id, [31], list(families)))

    def add_cause(self, stop_id: str, codes: list[int], families: list[str]) -> None:
        self.causes.append((stop_id, codes, families))

    def add_notice(
        self,
        notice_id: str,
        category: str,
        valid_from: dt.date,
        valid_to: dt.date,
        stop_ids: list[str],
    ) -> None:
        self.notices.append(
            (
                notice_id,
                category,
                dt.datetime.combine(valid_from, dt.time(0, 0), dt.timezone.utc),
                dt.datetime.combine(valid_to, dt.time(23, 59), dt.timezone.utc),
                2,
                dt.datetime.combine(valid_from, dt.time(0, 0), dt.timezone.utc),
                stop_ids,
            )
        )

    def commit(self) -> duckdb.DuckDBPyConnection:
        """Materialise the three tables.

        Loaded through registered Arrow tables, not ``executemany``. Measured on
        this fixture: 10,080 event rows take 27s row-by-row and 0.1s through
        Arrow, because DuckDB prepares and executes each row separately. That is
        the difference between a two-minute test suite and a two-second one.
        """
        con = self.con
        for name, ddl in (
            ("events", EVENT_DDL),
            ("causes", CAUSE_DDL),
            ("notices", NOTICE_DDL),
        ):
            con.execute(f"DROP TABLE IF EXISTS {name}")
            con.execute(ddl)
        _load(con, "events", self.events, _EVENT_SCHEMA)
        _load(con, "causes", self.causes, _CAUSE_SCHEMA)
        _load(con, "notices", self.notices, _NOTICE_SCHEMA)
        return con


def new_fixture() -> Fixture:
    return Fixture(duckdb.connect())


def corpus_fixture(
    *,
    n_stations: int = 8,
    n_groups_per_station: int = 6,
    start: dt.date = EPOCH,
    days: int = 60,
) -> Fixture:
    """A small many-station, many-type corpus for the curation tests.

    Every third pair is thin (runs on 6 days, below MIN_SERVICE_DATES) so the
    rejection log has something in it, and every fifth pair carries works or
    weather causes so the regime quota has a pool to draw on.
    """
    fixture = new_fixture()
    types = ("S", "RE", "RB", "ICE")
    index = 0
    for station_num in range(n_stations):
        station = f"Station {station_num:02d}"
        for group_num in range(n_groups_per_station):
            train_type = types[group_num % len(types)]
            destination = f"Dest {group_num:02d}"
            thin = index % 3 == 2
            affected = index % 5 == 0
            families = ("works",) if index % 10 == 0 else (("weather",) if affected else ())
            fixture.add_service(
                train_type=train_type,
                destination=destination,
                station=station,
                start=start,
                days=6 if thin else days,
                hour=6 + (index % 12),
                delay=1 + (index % 9),
                jitter=2,
                seed=index,
                families=families,
                family_days=(
                    tuple(start + dt.timedelta(days=d) for d in range(10, 20))
                    if families
                    else None
                ),
            )
            index += 1
    return fixture
