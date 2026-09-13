"""Falling back when DB live data fails: the client's pause, stale change feeds and offline estimates.

No network and no model: the API address is a closed local port, the change feeds come from a stub,
and the statistical forecast and the model's distribution are fixed values.
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

import live
import prompts
import serve
from test_serve import trip

NOW = datetime(2026, 9, 13, 9, 0)
XGB_COLUMNS = ["xgb_median", "xgb_q10", "xgb_q90", "xgb_p_late", "xgb_p_cancel"]


class FixedForecast:
    """Stands in for live_xgb.Forecast."""

    def columns_for(self, frame: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame([[3.0, 1.0, 8.0, 0.2, 0.01]] * len(frame), columns=XGB_COLUMNS, index=frame.index)


def recorded_run(train_type: str, number: str, line: str, station: str, t0: str) -> dict:
    """One stored example with the columns an offline row is built from."""
    return {
        "example_id": 1, "t0": pd.Timestamp(t0), "k_station": station, "train_type": train_type, "train_number": number,
        "line_number": line, "cls": "S-Bahn" if train_type == "S" else "regional", "pre_departure": True, "j_station": None,
        "first_station": "Origin Town", "origin": "Origin Town", "dest": "Destination City", "via": np.array(["Middle"], dtype=object),
        "k_num": 5, "first_num": 1, "station_series": np.full(72, 0.2), "network_series": np.full(72, 0.1),
        "station_stops_24h": 48.0, "hist_series": np.full(90, 2.0), "hist_level": "pattern", "hist_n": 40.0,
        "hist_cancel_share": 0.02, "hist_median": 2.0, "hist_p90": 6.0, "hist_mean": 2.5, "hist_days": 30.0,
        "hist_median_long": 2.0, "hist_p90_long": 6.0, "hist_median_7": 1.0, "hist_window_days": 90,
        "same_train_gains": np.full(28, 1.0), "same_train_days": 20.0, "same_train_gain_median": 1.0, "same_train_gain_median_7": 1.0,
    }


@pytest.fixture
def offline_live() -> live.Live:
    stored = pd.DataFrame([
        recorded_run("RB", "59143", "RB16", "Big City Hbf", "2026-09-12 17:00"),
        recorded_run("RE", "4711", "RE1", "Harbour Station", "2026-09-12 16:00"),
    ])
    client = live.Client(live.dbx.Credentials("", ""), offline=True)
    return live.Live(live.Feeds(client), stored, FixedForecast())


def leg(train: str, to: str, number: str | None = None) -> dict:
    return {"trainId": train, "trainNumber": number, "from": {"name": "Origin Town"}, "to": {"name": to},
            "plannedDeparture": "2026-09-13T10:00:00+02:00", "plannedArrival": "2026-09-13T10:25:00+02:00"}


def test_client_pauses_after_the_api_fails(monkeypatch):
    monkeypatch.setattr(live.dbx, "MARKETPLACE", "http://127.0.0.1:9")  # nothing listens there
    client = live.Client(live.dbx.Credentials("id", "key"))
    with pytest.raises(live.dbx.DBError, match="unreachable"):
        client.plan("8000105", NOW)
    assert client.calls == 1 and client.down_until > time.monotonic() + 50
    with pytest.raises(live.dbx.DBError, match="unavailable"):
        client.full_changes("8000105")
    assert client.calls == 1, "during the pause nothing is sent"


def test_offline_client_never_calls():
    client = live.Client(live.dbx.Credentials("", ""), offline=True)
    with pytest.raises(live.dbx.DBError, match="offline"):
        client.full_changes("8000105")
    assert client.calls == 0


def test_change_feed_is_served_stale_when_the_api_fails():
    class Flaky:
        failing = False

        def full_changes(self, eva):
            if self.failing:
                raise live.dbx.DBError("HTTP 503 for fchg")
            return ET.fromstring('<timetable station="Big City Hbf"/>')

    client = Flaky()
    feeds = live.Feeds(client, change_ttl=0)
    first = feeds.change("8000105")
    client.failing = True
    assert feeds.change("8000105") is first and "8000105" in feeds.stale
    with pytest.raises(live.dbx.DBError):
        feeds.change("8000261")  # never fetched: nothing to fall back on


def test_offline_row_follows_the_recorded_run_of_the_same_train(offline_live):
    row, sources = offline_live.offline_example(leg("RB 16", "Big City", "59143"), NOW, reason="HTTP 503")
    assert row["pre_departure"] and row["k_station"] == "Big City Hbf" and list(row["via"]) == ["Middle"]
    assert row["stops_ahead"] == 4 and row["lead_minutes"] == 85 and row["run_delays"] == []
    assert row["hist_level"] == "pattern" and row["same_train_days"] == 20 and row["xgb_median"] == 3.0
    assert sources[0].startswith("offline estimate at 09:00") and "HTTP 503" in sources[0]
    assert "latest recorded RB 59143" in sources[1]
    assert "Answer:" in prompts.sample(row, mode="text")["prefix"]


def test_offline_row_falls_back_to_a_train_of_the_same_type(offline_live):
    row, sources = offline_live.offline_example(leg("RE 7", "Harbour Station", "9999"), NOW)
    assert row["train_number"] == "9999" and list(row["via"]) == [] and row["dest"] == "Harbour Station"
    assert row["same_train_days"] == 0 and "no recorded run of RE 7" in sources[1]
    with pytest.raises(LookupError):
        offline_live.offline_example(leg("ICE 5", "Harbour Station"), NOW)


def test_forecaster_falls_back_from_live_to_offline_to_the_prior(offline_live):
    frame = pd.DataFrame([trip(100 + i, "RE", str(i), "RE1", "Elsewhere", "2026-09-10 10:00", "2026-09-10 09:30", target=i % 7)
                          for i in range(serve.MIN_PRIOR)])
    f = serve.Forecaster(frame, [], model=object(), mode="text", model_id="test-model", live=offline_live)
    probs = np.zeros(serve.MINUTES)
    probs[2] = 1.0
    f.model_forecast = lambda row: (probs, 0.02)

    out = f.leg_forecast(leg("RB 16", "Big City", "59143"), None)
    assert out["sources"][0] == "test-model (offline estimate)" and out["offline"] and out["confidence"] == "low"
    assert out["quantiles"]["p50"] == 2 and out["sources"][1].startswith("offline estimate")
    assert f.row_for(leg("RB 16", "Big City", "59143"))["k_station"] == "Big City Hbf", "explanations reuse the offline row"

    prior = f.leg_forecast(leg("ICE 5", "Nowhere"), None)
    assert prior["confidence"] == "low" and "Live data could not be used" in prior["reasoning"]
