"""Pull one month of German rail stops into an hourly per-station table.

Reads the monthly parquet straight over HTTPS. DuckDB prunes to the five
columns this needs and fetches only the byte ranges behind them, so a month
costs seconds and no local copy of the 68 GB repository.
"""

from __future__ import annotations

import duckdb

BASE_URL = (
    "https://huggingface.co/datasets/piebro/deutsche-bahn-data/resolve/main/monthly_processed_data"
)


def month_url(month: str) -> str:
    """Return the parquet URL for a month given as ``YYYY-MM``."""
    return f"{BASE_URL}/data-{month}.parquet"


def extract(con: duckdb.DuckDBPyConnection, month: str, n_stations: int = 40) -> None:
    """Build the ``hourly`` table for the busiest stations in one month.

    Args:
        con: An open DuckDB connection; the table is created there.
        month: The month to read, as ``YYYY-MM``.
        n_stations: How many stations to keep, ranked by stop count.
    """
    url = month_url(month)
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute(
        f"""
        CREATE OR REPLACE TABLE top_stations AS
        SELECT station_name, count(*) AS n
        FROM read_parquet('{url}')
        GROUP BY 1 ORDER BY n DESC LIMIT {int(n_stations)}
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE TABLE hourly AS
        SELECT station_name,
               date_trunc('hour', time) AS hour,
               avg(delay_in_min)::DOUBLE AS mean_delay,
               avg(CASE WHEN arrival_is_canceled OR departure_is_canceled THEN 1.0 ELSE 0.0 END)::DOUBLE
                   AS cancel_rate,
               count(*)::DOUBLE AS trains
        FROM read_parquet('{url}')
        WHERE station_name IN (SELECT station_name FROM top_stations)
        GROUP BY 1, 2
        """
    )
