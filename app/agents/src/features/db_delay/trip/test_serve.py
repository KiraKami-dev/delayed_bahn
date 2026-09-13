"""Matching journey legs to recorded trips and answering in the backend's contract."""

from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

import numpy as np
import pandas as pd
import pytest

import metrics
import serve


def trip(example_id: int, train_type: str, number: str, line: str, station: str, arrival: str, t0: str,
         target: float = 3.0, cancelled: bool = False) -> dict:
    """One recorded trip with the columns the rationale and the matcher read."""
    hours = np.full(72, 0.1)
    return {
        "example_id": example_id, "split": "test", "cls": "regional" if train_type != "S" else "S-Bahn",
        "train_type": train_type, "train_number": number, "line_number": line, "origin": "Origin Town",
        "dest": "Destination City", "first_station": "Origin Town", "j_station": "Halfway", "k_station": station,
        "t0": pd.Timestamp(t0), "k_arr_pt": pd.Timestamp(arrival),
        "lead_minutes": (pd.Timestamp(arrival) - pd.Timestamp(t0)).total_seconds() / 60,
        "pre_departure": False, "run_delays": np.array([1.0, 2.0, 2.0]), "via": np.array([], dtype=object),
        "hist_series": np.full(30, 2.0), "station_series": hours, "network_series": hours, "hist_level": "pattern",
        "hist_median": 2.0, "hist_p90": 8.0, "hist_cancel_share": 0.02, "current_delay": 2.0,
        "max_delay_so_far": 2.0, "delay_change_3": 0.0, "stops_ahead": 3, "station_late_3h": 0.1,
        "station_late_72h": 0.12, "network_late_3h": 0.1, "network_late_72h": 0.11,
        "target_minutes": target, "cancelled": cancelled,
    }


@pytest.fixture
def frame() -> pd.DataFrame:
    rows = [
        trip(1, "RB", "59143", "RB16", "Big City Hbf", "2026-09-13 07:25", "2026-09-13 06:40"),
        trip(2, "RB", "59143", "RB16", "Big City Hbf", "2026-09-13 07:25", "2026-09-13 07:10"),
        trip(3, "S", "6021", "S8", "Airport Terminal", "2026-09-13 08:22", "2026-09-13 08:00", target=0),
        trip(4, "ICE", "75", "", "Big City Hbf", "2026-09-13 07:25", "2026-09-13 07:00", target=12),
    ] + [trip(100 + i, "RE", str(i), "RE1", "Elsewhere", "2026-09-10 10:00", "2026-09-10 09:30", target=i % 7)
         for i in range(serve.MIN_PRIOR)]
    return pd.DataFrame(rows)


def saved(path, frame: pd.DataFrame, with_probs: bool) -> None:
    """A prediction file like train.py (probs) or combine.py (quantiles only) writes."""
    ids = frame["example_id"].to_numpy()
    probs = np.zeros((len(ids), serve.MINUTES))
    for i, target in enumerate(frame["target_minutes"]):
        probs[i, int(target):int(target) + 3] = [0.5, 0.3, 0.2]
    arrays = {"example_id": ids, "p_cancel": np.full(len(ids), 0.01, dtype=np.float32),
              "quantiles": metrics.quantiles_from_distribution(probs)}
    if with_probs:
        arrays["probs"] = probs.astype(np.float16)
    np.savez_compressed(path, **arrays)


def test_leg_matches_train_spellings_station_and_zone(frame, tmp_path):
    saved(tmp_path / "p.npz", frame, with_probs=True)
    f = serve.Forecaster(frame, [tmp_path / "p.npz"])
    leg = {"trainId": "RB 16", "to": {"name": "Big City"}, "plannedArrival": "2026-09-13T07:25:00+02:00"}
    out = f.leg_forecast(leg, None)
    assert out["exampleId"] == 2, "the forecast made last before arrival wins"
    assert out["quantiles"]["p50"] == 3 and out["actual"] == {"cancelled": False, "delayMinutes": 3}
    assert abs(sum(out["arrival"]["probs"]) - 1) < 1e-3 and out["confidence"] == "high"
    by_number = dict(leg, trainId="RB", trainNumber="59143")
    assert f.leg_forecast(by_number, None)["exampleId"] == 2
    utc = dict(leg, plannedArrival="2026-09-13T05:25:00Z")
    assert f.leg_forecast(utc, None)["exampleId"] == 2
    ice = dict(leg, trainId="ICE 75")
    assert f.leg_forecast(ice, None)["exampleId"] == 4 and f.leg_forecast(ice, None)["quantiles"]["p50"] == 12


def test_now_picks_the_forecast_available_at_that_time(frame, tmp_path):
    saved(tmp_path / "p.npz", frame, with_probs=True)
    f = serve.Forecaster(frame, [tmp_path / "p.npz"])
    leg = {"trainId": "RB16", "to": {"name": "Big City Hbf"}, "plannedArrival": "2026-09-13T07:25:00+02:00"}
    assert f.leg_forecast(leg, pd.Timestamp("2026-09-13 06:50"))["exampleId"] == 1
    assert f.leg_forecast(leg, pd.Timestamp("2026-09-13 07:12"))["exampleId"] == 2


def test_quantile_only_predictions_are_rebuilt_into_a_distribution(frame, tmp_path):
    saved(tmp_path / "q.npz", frame, with_probs=False)
    f = serve.Forecaster(frame, [tmp_path / "q.npz"])
    leg = {"trainId": "S 8", "to": {"name": "Airport Terminal"}, "plannedArrival": "2026-09-13T08:22:00+02:00"}
    out = f.leg_forecast(leg, None)
    probs = np.array(out["arrival"]["probs"])
    assert abs(probs.sum() - 1) < 1e-3 and out["quantiles"]["p50"] <= 2


def test_unmatched_leg_gets_the_class_prior(frame):
    f = serve.Forecaster(frame, [])
    leg = {"trainId": "RE 7", "to": {"name": "Nowhere"}, "plannedArrival": "2026-09-13T09:00:00+02:00"}
    out = f.leg_forecast(leg, None)
    assert out["confidence"] == "low" and "not a forecast" in out["reasoning"]
    probs = np.array(out["arrival"]["probs"])
    assert abs(probs.sum() - 1) < 1e-6 and probs[:7].sum() > 0.99
    wrong_station = {"trainId": "RB 16", "to": {"name": "Somewhere Else"}, "plannedArrival": "2026-09-13T07:25:00+02:00"}
    assert f.leg_forecast(wrong_station, None)["confidence"] == "low"


def test_http_round_trip(frame, tmp_path):
    saved(tmp_path / "p.npz", frame, with_probs=True)
    f = serve.Forecaster(frame, [tmp_path / "p.npz"], model_id="test-model")
    server = ThreadingHTTPServer(("127.0.0.1", 0), serve.make_handler(f))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        conn = HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        journey = {"id": "j1", "legs": [
            {"trainId": "RB 16", "to": {"name": "Big City Hbf"}, "plannedArrival": "2026-09-13T07:25:00+02:00"},
            {"trainId": "S 8", "to": {"name": "Airport Terminal"}, "plannedArrival": "2026-09-13T08:22:00+02:00"},
        ]}
        conn.request("POST", "/", body=json.dumps(journey), headers={"content-type": "application/json"})
        reply = json.loads(conn.getresponse().read())
        assert reply["modelId"] == "test-model" and reply["confidence"] == "high"
        assert [leg["exampleId"] for leg in reply["legs"]] == [2, 3]
        assert all(len(leg["arrival"]["probs"]) == serve.MINUTES for leg in reply["legs"])
        conn.request("POST", "/", body=json.dumps({"legs": []}))
        assert conn.getresponse().status == 400
        conn.request("GET", "/health")
        health = json.loads(conn.getresponse().read())
        assert health["ok"] and health["savedForecasts"] == len(frame)
    finally:
        server.shutdown()
