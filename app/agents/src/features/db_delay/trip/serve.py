"""Model server for the app: a Journey in, one arrival-delay distribution per leg out.

The Node backend forwards ``POST /api/predict`` bodies here when ``PREDICT_URL`` points at this
server, and expects::

    {"modelId": ..., "confidence": ..., "legs": [{"trainId": ..., "arrival": {"probs": [...],
     "pCancel": p}, "reasoning": ..., "sources": [...]}]}

Each leg is matched to a recorded trip in the examples file by train, target station and planned
arrival, and answered with the forecast the model made for that trip: from a saved prediction file
(``--predictions``, the ``tslm_*.npz`` or ``blend_*.npz`` written by train.py and combine.py) or,
with ``--checkpoint`` on a GPU, computed on the spot. A leg with no recorded trip gets the
empirical delay distribution of its train type, marked as such, so the app never has to fall back
to its mock for the whole journey.

    python trip/serve.py --examples data/trip/forward.parquet \
        --predictions out/trip/forward_text-plaincrps/tslm_test.npz --port 8501

Extra per-leg fields (``exampleId``, ``leadMinutes``, ``forecastAt``, ``quantiles``, ``pOnTime``,
``actual``) are additive; the backend keeps what the contract names and ignores the rest.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

import metrics  # noqa: E402
import prompts  # noqa: E402

LOCAL_TZ = "Europe/Berlin"
MINUTES = 1000  # the model's minute vocabulary
MATCH_MINUTES = 1  # planned arrival may differ by this much between the app and the record
MIN_PRIOR = 200  # rows needed before a train type gets its own prior instead of its class
LONG_DISTANCE = {"ICE", "IC", "EC", "ECE", "TGV", "RJ", "RJX", "NJ", "FLX"}
SOURCES = ["delays at the stops so far", "previous trains on the route today",
           "90-day route history", "72 h of hourly late shares at the station and nationwide"]


def norm(value) -> str:
    """Lower-case letters and digits only, so 'S 8', 'S8' and 'S  8' agree."""
    return re.sub(r"[^a-z0-9äöüß]", "", str(value or "").lower())


def train_keys(row: pd.Series) -> set[str]:
    """Every spelling of a recorded train the app might send."""
    keys = {norm(f"{row['train_type']}{row['train_number']}"), norm(row["line_number"])}
    return {k for k in keys if k}


def leg_keys(leg: dict) -> set[str]:
    """The spellings carried by a journey leg."""
    keys = {norm(leg.get("trainId"))}
    number = leg.get("trainNumber")
    if number:
        prefix = re.match(r"[A-Za-z]+", str(leg.get("trainId") or ""))
        keys.add(norm(f"{prefix.group(0) if prefix else ''}{number}"))
    return {k for k in keys if k}


def station_match(a, b) -> bool:
    """Equal after normalisation, or one contains the other (the share text drops parts of names)."""
    a, b = norm(a), norm(b)
    return bool(a and b) and (a == b or (min(len(a), len(b)) >= 4 and (a in b or b in a)))


def local_naive(value: str) -> pd.Timestamp:
    """An ISO timestamp as the naive local time the examples use."""
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts
    return ts.tz_convert(LOCAL_TZ).tz_localize(None)


def train_class(train_id: str) -> str:
    """The class the examples use, from the train id alone."""
    prefix = re.match(r"[A-Za-z]+", str(train_id or ""))
    kind = prefix.group(0).upper() if prefix else ""
    if kind in LONG_DISTANCE:
        return "long-distance"
    if kind == "S":
        return "S-Bahn"
    return "regional"


def probs_from_quantiles(q: np.ndarray) -> np.ndarray:
    """A minute distribution with the given quantiles at :data:`metrics.LEVELS`, mass spread
    uniformly between neighbouring quantiles. Used for prediction files that saved no ``probs``."""
    q = np.clip(np.round(q).astype(int), 0, MINUTES - 1)
    levels = np.concatenate([[0.0], metrics.LEVELS, [1.0]])
    edges = np.concatenate([[0], q, [min(MINUTES - 1, q[-1] + max(1, q[-1] - q[-2]) * 2)]])
    probs = np.zeros(MINUTES)
    for lo, hi, mass in zip(edges[:-1], edges[1:], np.diff(levels)):
        lo, hi = int(min(lo, hi)), int(max(lo, hi))
        probs[lo:hi + 1] += mass / (hi - lo + 1)
    return probs / probs.sum()


def rounded(probs: np.ndarray) -> list[float]:
    """Compact JSON: six decimals, still summing to one within float noise."""
    return [round(float(p), 6) for p in probs]


class Forecaster:
    """Recorded trips, their saved forecasts, and an optional live model."""

    def __init__(self, frame: pd.DataFrame, predictions: list[Path] | None = None, model=None,
                 mode: str = "both", scaling: str = "z", model_id: str = "db-trip-delay", live=None):
        self.frame = frame.reset_index(drop=True)
        self.model, self.mode, self.scaling, self.model_id = model, mode, scaling, model_id
        self.live = live  # live.Live: examples built from the Timetables API for legs without a record
        arrivals = pd.to_datetime(self.frame["k_arr_pt"])
        self.by_minute: dict[pd.Timestamp, list[int]] = {}
        for i, ts in enumerate(arrivals.dt.floor("min")):
            self.by_minute.setdefault(ts, []).append(i)
        self.keys = [train_keys(row) for _, row in self.frame.iterrows()]
        self.saved: dict[int, tuple[dict, int]] = {}
        for path in predictions or []:
            data = np.load(path)
            arrays = {k: data[k] for k in data.files}
            for j, example_id in enumerate(arrays["example_id"].tolist()):
                self.saved.setdefault(int(example_id), (arrays, j))
        self.priors = self._priors()

    def _priors(self) -> dict[str, tuple[np.ndarray, float]]:
        """Empirical delay distributions per train type and per class, for legs without a record."""
        priors = {}
        for key, group in list(self.frame.groupby("train_type")) + list(self.frame.groupby("cls")):
            if len(group) < MIN_PRIOR and key not in set(self.frame["cls"]):
                continue
            runs = group[~group["cancelled"].astype(bool)]
            counts = np.bincount(np.clip(runs["target_minutes"].fillna(0).astype(int), 0, MINUTES - 1), minlength=MINUTES)
            priors[str(key)] = (counts / max(1, counts.sum()), float(group["cancelled"].astype(bool).mean()))
        return priors

    def candidates(self, leg: dict) -> list[int]:
        """Rows whose train and planned arrival agree with the leg, station-matched rows first."""
        try:
            arrival = local_naive(leg["plannedArrival"]).floor("min")
        except (ValueError, TypeError, KeyError):
            return []
        wanted = leg_keys(leg)
        rows = [i for d in range(-MATCH_MINUTES, MATCH_MINUTES + 1)
                for i in self.by_minute.get(arrival + pd.Timedelta(minutes=d), []) if self.keys[i] & wanted]
        station = (leg.get("to") or {}).get("name")
        with_station = [i for i in rows if station_match(station, self.frame.at[i, "k_station"])]
        return with_station or ([] if station and rows and not with_station else rows)

    def pick(self, rows: list[int], now: pd.Timestamp | None) -> int:
        """The forecast made last before ``now``, or the latest one before the planned arrival."""
        frame = self.frame.loc[rows]
        if now is not None:
            before = frame[pd.to_datetime(frame["t0"]) <= now]
            if len(before):
                return int(before["t0"].astype(str).idxmax())
        lead = frame["lead_minutes"].astype(float)
        return int(sorted(rows, key=lambda i: (lead[i] < 0, abs(lead[i])))[0])

    def forecast_row(self, i: int) -> tuple[np.ndarray, float, str]:
        """Minute distribution and P(cancelled) for one recorded trip, and where they came from."""
        row = self.frame.loc[i]
        saved = self.saved.get(int(row["example_id"]))
        if saved is not None:
            arrays, j = saved
            probs = arrays["probs"][j].astype(np.float64) if "probs" in arrays else probs_from_quantiles(arrays["quantiles"][j])
            return probs / probs.sum(), float(arrays["p_cancel"][j]), "saved forecast"
        if self.model is not None:
            probs, p_cancel = self.model_forecast(row)
            return probs, p_cancel, "live model"
        raise LookupError("no saved forecast and no model")

    def model_forecast(self, row: pd.Series) -> tuple[np.ndarray, float]:
        """The loaded model's minute distribution and P(cancelled) for one example row."""
        from train import collate  # noqa: PLC0415  (torch stays optional for the precomputed mode)

        out = self.model.predict_distribution(collate([prompts.sample(row, mode=self.mode, scaling=self.scaling)]))
        return out["probs"][0].float().cpu().numpy().astype(np.float64), float(out["p_cancel"][0])

    def live_forecast(self, leg: dict) -> dict:
        """The leg forecast from an example built live from the Timetables API."""
        row, sources = self.live.example(leg)
        probs, p_cancel = self.model_forecast(row)
        q = metrics.quantiles_from_distribution(probs[None])[0]
        lead = float(row["lead_minutes"])
        return {
            "trainId": leg.get("trainId"),
            "arrival": {"probs": rounded(probs), "pCancel": round(p_cancel, 4)},
            "reasoning": prompts.rationale(row),
            "sources": [f"{self.model_id} (live data)"] + sources,
            "confidence": "high" if lead <= 30 else "medium",
            "leadMinutes": lead,
            "forecastAt": str(row["t0"]),
            "matched": {"train": prompts.train_label(row), "station": prompts.name(row["k_station"]),
                        "plannedArrival": str(row["k_arr_pt"])},
            "quantiles": {"p10": int(q[metrics.LOW]), "p50": int(q[metrics.MEDIAN]), "p90": int(q[metrics.HIGH])},
            "pOnTime": round(float(probs[:metrics.LATE_MINUTES].sum()) * (1 - p_cancel), 4),
        }

    def leg_forecast(self, leg: dict, now: pd.Timestamp | None) -> dict:
        """The contract's leg forecast, from a recorded trip or the class prior."""
        rows = self.candidates(leg)
        if rows:
            i = self.pick(rows, now)
            row = self.frame.loc[i]
            try:
                probs, p_cancel, origin = self.forecast_row(i)
            except LookupError:
                rows = []
            else:
                q = metrics.quantiles_from_distribution(probs[None])[0]
                on_time = float(probs[:metrics.LATE_MINUTES].sum()) * (1 - p_cancel)
                lead = float(row["lead_minutes"])
                out = {
                    "trainId": leg.get("trainId"),
                    "arrival": {"probs": rounded(probs), "pCancel": round(p_cancel, 4)},
                    "reasoning": prompts.rationale(row),
                    "sources": [f"{self.model_id} ({origin})", f"forecast {lead:.0f} min before the planned arrival"] + SOURCES,
                    "confidence": "high" if lead <= 30 else "medium",
                    "exampleId": int(row["example_id"]),
                    "leadMinutes": lead,
                    "forecastAt": str(row["t0"]),
                    "matched": {"train": prompts.train_label(row), "station": prompts.name(row["k_station"]),
                                "plannedArrival": str(row["k_arr_pt"])},
                    "quantiles": {"p10": int(q[metrics.LOW]), "p50": int(q[metrics.MEDIAN]), "p90": int(q[metrics.HIGH])},
                    "pOnTime": round(on_time, 4),
                }
                if pd.notna(row.get("target_minutes")) or bool(row.get("cancelled")):
                    out["actual"] = {"cancelled": bool(row["cancelled"]),
                                     "delayMinutes": None if bool(row["cancelled"]) else int(row["target_minutes"])}
                return out
        live_failure = ""
        if self.live is not None and self.model is not None:
            try:
                return self.live_forecast(leg)
            except (LookupError, RuntimeError, OSError, ValueError, KeyError) as error:
                live_failure = f" Live data could not be used: {error}."
                print(f"live example failed for {leg.get('trainId')}: {error!r}", flush=True)
        prefix = re.match(r"[A-Za-z]+", str(leg.get("trainId") or ""))
        kind = prefix.group(0).upper() if prefix else ""
        probs, p_cancel = self.priors.get(kind) or self.priors.get(train_class(leg.get("trainId")), (None, None))
        if probs is None:
            probs, p_cancel = probs_from_quantiles(np.arange(19, dtype=float)), 0.02
        return {
            "trainId": leg.get("trainId"),
            "arrival": {"probs": rounded(probs), "pCancel": round(float(p_cancel), 4)},
            "reasoning": (f"No recorded trip matches {leg.get('trainId')} arriving at "
                          f"{(leg.get('to') or {}).get('name') or 'the target station'} at the planned time, so this is "
                          f"the average of recorded {kind or train_class(leg.get('trainId'))} arrivals, not a forecast."
                          f"{live_failure}"),
            "sources": ["class average of the recorded trips (no matching record)"],
            "confidence": "low",
        }

    def forecast(self, journey: dict) -> dict:
        """The contract's reply for a whole journey."""
        legs = journey.get("legs") or []
        if not isinstance(legs, list) or not legs:
            raise ValueError("Body must be a Journey with at least one leg")
        now = local_naive(journey["now"]) if journey.get("now") else None
        out = [self.leg_forecast(leg, now) for leg in legs]
        levels = {"high": 2, "medium": 1, "low": 0}
        confidence = min((leg["confidence"] for leg in out), key=levels.get)
        return {"modelId": self.model_id, "confidence": confidence, "legs": out}


def load_model(checkpoint: str, start_checkpoint: str | None, device: str):
    """The fine-tuned model, when serving live."""
    from model import START_CHECKPOINT, TripTSLM  # noqa: PLC0415

    model = TripTSLM.from_opentslm_checkpoint(start_checkpoint or START_CHECKPOINT, device=device)
    if not model.lora_enabled:
        model.enable_lora()
    model.load_from_file(checkpoint)
    model.eval()
    return model


def make_handler(forecaster: Forecaster):
    """An HTTP handler bound to one forecaster."""

    class Handler(BaseHTTPRequestHandler):
        def _reply(self, status: int, body: dict) -> None:
            payload = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("content-type", "application/json; charset=utf-8")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:  # noqa: N802
            self._reply(200, {"ok": True, "modelId": forecaster.model_id, "examples": len(forecaster.frame),
                              "savedForecasts": len(forecaster.saved), "live": forecaster.model is not None,
                              "liveData": forecaster.live is not None,
                              "apiCalls": forecaster.live.feeds.client.calls if forecaster.live is not None else 0})

        def do_POST(self) -> None:  # noqa: N802
            try:
                length = int(self.headers.get("content-length") or 0)
                journey = json.loads(self.rfile.read(length) or b"{}")
                self._reply(200, forecaster.forecast(journey))
            except (ValueError, KeyError, TypeError) as error:
                self._reply(400, {"error": str(error)})

        def log_message(self, fmt, *args) -> None:
            print(f"{self.address_string()} {fmt % args}", flush=True)

    return Handler


def main() -> None:
    """Load the records and forecasts, then serve."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--examples", default="data/trip/forward.parquet")
    parser.add_argument("--split", default=None, help="only these examples, e.g. test")
    parser.add_argument("--predictions", nargs="*", default=[], help="npz files from train.py or combine.py")
    parser.add_argument("--checkpoint", help="checkpoint.pt for live forecasts of unsaved legs")
    parser.add_argument("--start-checkpoint", default=None)
    parser.add_argument("--prompt-mode", default="both", choices=prompts.MODES)
    parser.add_argument("--series-scaling", default="z", choices=prompts.SCALINGS)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--model-id", default="OpenTSLM db-trip-delay")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--xgb", help="saved statistical forecast (live_xgb.py): enables live examples from the Timetables API")
    parser.add_argument("--env", help=".env with DB_CLIENT_ID and DB_API_KEY (default: the repo root's)")
    parser.add_argument("--calls-per-minute", type=int, default=55)
    args = parser.parse_args()

    frame = pd.read_parquet(args.examples)
    if args.split:
        frame = frame[frame["split"] == args.split]
    model = load_model(args.checkpoint, args.start_checkpoint, args.device) if args.checkpoint else None
    live_builder = None
    if args.xgb:
        import live  # noqa: PLC0415  (xgboost and the API client only when live examples are wanted)

        live_builder = live.create(args.examples, args.xgb, args.env, args.calls_per_minute)
    forecaster = Forecaster(frame, [Path(p) for p in args.predictions], model, args.prompt_mode, args.series_scaling,
                            args.model_id, live_builder)
    print(f"{len(forecaster.frame)} recorded trips, {len(forecaster.saved)} saved forecasts, live model: {model is not None}, "
          f"live data: {live_builder is not None}", flush=True)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(forecaster))
    print(f"serving on http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
