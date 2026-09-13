"""Model server for the app, backed by the db-route bake-off artifacts: a Journey in, one
delay distribution per leg out, plus station cause families for the "why" tab.

The Node backend forwards ``POST /api/predict`` bodies here when ``PREDICT_URL`` points at this
server and ``GET /api/causes`` when ``CAUSES_URL`` does. Both replies follow the contracts in
``app/backend/src/features/delay-prediction/backends/http.js`` and ``causes/routes/causes.js``.

What is served is real, and labelled by where it came from:

* **model forecast** -- the quarter-profile TSLM's held-out minute distribution for a recorded
  (service group, station, travel date), from ``runs/<tag>/<profile>/scalar_<cell>.npz`` written
  by ``train_route.py`` (19 quantiles per row, rebuilt into a minute pmf).
* **recorded history** -- for a (service group, station) the model did not score, the empirical
  distribution of that service's six-hourly mean delay at that stop over the sixty days before
  the latest travel date in the registry.
* **class prior** -- for a train type with no record at all, the average of the model's held-out
  forecasts for that train type; otherwise the average over everything.

A leg is matched by train type (``RB 16`` -> ``RB``) and destination (``leg.to.name``) to a
service group ``<type> -> <final destination>``, with station preference for the leg's own
stations, then by destination alone within the same train class (so ``RB 16 -> München Hbf``
lands on the ``RE -> München Hbf`` records at Rohrbach (Ilm) on the same corridor). The reply
says which record answered.

    ./serve_route.sh --data app/agents/data/db-route --profile quarter --tag route-2k --port 8501
    PREDICT_URL=http://127.0.0.1:8501/predict CAUSES_URL=http://127.0.0.1:8501/causes node app/backend/src/server.js
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import sys
import time
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

MINUTES = 240  # pmf support in whole minutes (the app bins >30 together anyway)
LEVELS = np.round(np.arange(0.05, 1.0, 0.05), 2)  # metrics.LEVELS of the trip recipe
LOW, MEDIAN, HIGH = 1, 9, 17  # indices of the 0.10, 0.50 and 0.90 levels
LATE_MINUTES = 6
CELLS = ("val", "test_seen_entity", "test", "test_seen_time")
SIGNALS = ("service_at_station_delay", "station_delay", "works_share", "weather_share",
           "technical_share", "knock_on_share", "attributed_share")
LONG_DISTANCE = {"ICE", "IC", "EC", "ECE", "TGV", "RJ", "RJX", "NJ", "FLX"}
DB_REGIONAL = {"RB", "RE", "IRE", "MEX", "R"}  # DB Regio's own product names; third-party operators keep their own codes
P_CANCEL = 0.02  # cancellations are not part of the departure-delay task; a flat assumption, said so in sources
BUCKETS_PER_DAY = 4  # the quarter profile is six-hourly


def norm(value) -> str:
    """Lower-case letters and digits, platform suffixes and bracketed qualifiers dropped, so
    'München Hbf Gl.5-10', 'München Hbf' and 'Muenchen Hbf' agree."""
    s = str(value or "").lower()
    s = re.sub(r"gl\.?\s*\d+\s*-\s*\d+", "", s)
    s = re.sub(r"\((?:s-bahn|oberbay|mittelfr|westf|bay|han|b [^)]*|[^)]*)\)", "", s)
    s = s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return re.sub(r"[^a-z0-9]", "", s)


def train_type(train_id: str) -> str:
    m = re.match(r"[A-Za-zäöü]+", str(train_id or "").strip())
    return m.group(0).upper() if m else ""


def train_class(kind: str) -> str:
    if kind in LONG_DISTANCE:
        return "long-distance"
    if kind == "S":
        return "S-Bahn"
    return "regional"


def probs_from_quantiles(q: np.ndarray) -> np.ndarray:
    """A minute pmf with the given quantiles at LEVELS, mass spread uniformly between neighbours
    (the trip recipe's reconstruction for quantile-only prediction files)."""
    q = np.clip(np.round(np.asarray(q, dtype=float)).astype(int), 0, MINUTES - 1)
    levels = np.concatenate([[0.0], LEVELS, [1.0]])
    tail = min(MINUTES - 1, int(q[-1] + max(1, q[-1] - q[-2]) * 2))
    edges = np.concatenate([[0], q, [tail]])
    probs = np.zeros(MINUTES)
    for lo, hi, mass in zip(edges[:-1], edges[1:], np.diff(levels)):
        lo, hi = int(min(lo, hi)), int(max(lo, hi))
        probs[lo:hi + 1] += mass / (hi - lo + 1)
    return probs / probs.sum()


def probs_from_history(values: np.ndarray) -> np.ndarray | None:
    """Empirical pmf of the rounded six-hourly mean delays, lightly smoothed so a transfer
    slack that never happened in the window still has a small tail."""
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    if len(v) < 8:
        return None
    counts = np.bincount(np.clip(np.round(v).astype(int), 0, MINUTES - 1), minlength=MINUTES).astype(float)
    kernel = np.array([0.15, 0.7, 0.15])
    smooth = np.convolve(counts, kernel, mode="same")
    smooth += 1e-3 * np.exp(-np.arange(MINUTES) / 30.0)  # thin geometric tail
    return smooth / smooth.sum()


def quantiles(probs: np.ndarray) -> np.ndarray:
    cdf = np.cumsum(probs) / probs.sum()
    return np.array([min(int((cdf < level - 1e-9).sum()), MINUTES - 1) for level in LEVELS])


def rounded(probs: np.ndarray) -> list[float]:
    return [round(float(p), 6) for p in probs]


class RouteData:
    """The registry, the scored forecasts and a few indexes for matching."""

    def __init__(self, data_dir: Path, tag: str, profile: str):
        t0 = time.time()
        self.profile, self.tag = profile, tag
        reg = data_dir / "registry" / "error404" / f"db-route-{profile}" / "0.1.0"
        run = data_dir / "runs" / tag / profile
        if not reg.exists() or not run.exists():
            raise SystemExit(f"missing data under {data_dir}: run fetch_serving_data.sh first (need {reg} and {run})")

        ann = pd.concat(pd.read_parquet(p) for p in sorted(glob.glob(str(reg / "annotations" / "*.parquet"))))
        ann = ann[ann["span"].isna()].copy()
        ann["rid"] = ann["record_ids"].str[0]
        keep = ["station", "service_group", "train_type", "anchor_iso", "split", "split_cell", "attributed_share",
                "station_category", "federal_state", "entity_id"]
        wide = ann[ann["key"].isin(keep)].pivot_table(index="rid", columns="key", values="value", aggfunc="first")
        self.records = wide.map(lambda v: json.loads(v) if isinstance(v, str) else v)
        self.records["station_key"] = self.records["station"].map(norm)
        self.records["type_key"] = self.records["train_type"].map(lambda t: str(t).upper())
        self.records["dest"] = self.records["service_group"].map(lambda g: str(g).split("->", 1)[1].strip() if "->" in str(g) else "")
        self.records["dest_key"] = self.records["dest"].map(norm)

        tasks = pd.concat(pd.read_parquet(p) for p in sorted(glob.glob(str(reg / "tasks" / "task=scalar_prediction" / "*.parquet"))))
        tasks["rid"] = tasks["record_ids"].str[0]
        self.targets = tasks.set_index("rid")["target"].to_dict()
        # The question each task asked, by (record, kind): the generation log leaves it blank.
        self.prompts: dict[tuple[str, str], str] = {}
        for folder, kind in (("scalar_prediction", "ScalarPredictionTask"), ("classification", "ClassificationTask"), ("answer", "AnswerTask")):
            for p in sorted(glob.glob(str(reg / "tasks" / f"task={folder}" / "*.parquet"))):
                part = pd.read_parquet(p, columns=["record_ids", "prompt"])
                for rids, prompt in zip(part["record_ids"], part["prompt"]):
                    if len(rids):
                        self.prompts.setdefault((rids[0], kind), str(prompt))

        # What the model actually generated for a few held-out rows (parse_generations.py).
        self.generations: list[dict] = []
        gen_path = run / "generations.json"
        if gen_path.exists():
            payload = json.loads(gen_path.read_text())
            self.generations = payload.get("samples", [])
            self.generation_job = payload.get("job", "")
            for g in self.generations:
                g.setdefault("question", self.prompts.get((g["recordId"], g["kind"]), ""))
        self.generation_by_record: dict[str, dict] = {}
        for g in self.generations:
            if g["kind"] == "AnswerTask" or g["recordId"] not in self.generation_by_record:
                self.generation_by_record[g["recordId"]] = g

        # Measured cancellation rates (build_cancellation_rates.py); the flat P_CANCEL is the last resort.
        self.cancellations: dict = {}
        rates_path = data_dir / "cache" / "cancellation_rates.json"
        if rates_path.exists():
            self.cancellations = json.loads(rates_path.read_text())
            # Platform variants ("RE -> München Hbf Gl.27-36") share a normalised key: pool their counts
            # rather than letting whichever came last win.
            pooled: dict[str, dict] = {}
            for k, v in self.cancellations.get("services", {}).items():
                slot = pooled.setdefault(norm(k), {"n": 0, "cancelled": 0.0})
                slot["n"] += v["n"]
                slot["cancelled"] += v["rate"] * v["n"]
            self.cancellations["_services_norm"] = {k: {"n": s["n"], "rate": s["cancelled"] / s["n"]} for k, s in pooled.items() if s["n"]}

        index = pd.concat(pd.read_parquet(p) for p in sorted(glob.glob(str(reg / "time_series_index" / "*.parquet"))))
        short = index["signal"].str.split("/").str[-1]
        index = index[short.isin(SIGNALS)].copy()
        index["short"] = short[index.index]
        wanted = set(index["time_series_id"])
        series: dict[str, np.ndarray] = {}
        for p in sorted(glob.glob(str(reg / "time_series" / "*.parquet"))):
            part = pd.read_parquet(p, columns=["time_series_id", "values"])
            part = part[part["time_series_id"].isin(wanted)]
            for tsid, values in zip(part["time_series_id"], part["values"]):
                series[tsid] = np.asarray(values, dtype=np.float32)
        self.series: dict[tuple[str, str], np.ndarray] = {}
        for rid, sig, tsid in zip(index["record_id"], index["short"], index["time_series_id"]):
            if tsid in series:
                self.series[(rid, sig)] = series[tsid]

        self.forecasts: dict[str, dict] = {}
        for cell in CELLS:
            path = run / f"scalar_{cell}.npz"
            if not path.exists():
                continue
            z = np.load(path)
            for rid, q, y in zip(z["record_id"].tolist(), z["quantiles"], z["y"]):
                self.forecasts[rid] = {"cell": cell, "quantiles": np.asarray(q, dtype=float), "y": float(y)}
        self.metrics = json.loads((run / "metrics.json").read_text()) if (run / "metrics.json").exists() else {}
        self.records["scored"] = self.records.index.isin(self.forecasts)

        self.by_group: dict[tuple[str, str], list[str]] = {}
        self.by_dest: dict[str, list[str]] = {}
        self.by_type: dict[str, list[str]] = {}
        self.by_station: dict[str, list[str]] = {}
        for rid, r in self.records.iterrows():
            self.by_group.setdefault((r["type_key"], r["dest_key"]), []).append(rid)
            self.by_dest.setdefault(r["dest_key"], []).append(rid)
            self.by_type.setdefault(r["type_key"], []).append(rid)
            self.by_station.setdefault(r["station_key"], []).append(rid)
        self.type_prior = {kind: self._mean_forecast(rids) for kind, rids in self.by_type.items()}
        self.type_prior = {k: v for k, v in self.type_prior.items() if v is not None}
        self.global_prior = self._mean_forecast(list(self.records.index))
        self.model_id = f"OpenTSLM db-route-{profile} ({tag})"
        self.loaded_in = time.time() - t0

    def _mean_forecast(self, rids: list[str]) -> np.ndarray | None:
        rows = [probs_from_quantiles(self.forecasts[r]["quantiles"]) for r in rids if r in self.forecasts]
        if not rows:
            return None
        return np.mean(rows, axis=0)

    # --- matching -----------------------------------------------------------

    def _pick(self, rids: list[str], stations: set[str], kind: str) -> tuple[str, bool] | None:
        """Model-scored rows first, then the most similar train type (RB for an RB, DB's own
        regional types before third-party operators), then the leg's own stations, then the
        latest travel date."""
        if not rids:
            return None
        sub = self.records.loc[rids]
        similarity = sub["type_key"].map(lambda t: 2 if t == kind else 1 if {t, kind} <= DB_REGIONAL else 0)
        ranked = sub.assign(_sim=similarity, _own=sub["station_key"].isin(stations)).sort_values(
            ["scored", "_sim", "_own", "anchor_iso"], ascending=False)
        best = ranked.index[0]
        return best, bool(ranked["scored"].iloc[0])

    def match(self, leg: dict) -> tuple[str | None, bool, str]:
        kind = train_type(leg.get("trainId"))
        dest = norm((leg.get("to") or {}).get("name"))
        stations = {norm((leg.get("from") or {}).get("name")), dest}
        hit = self._pick(self.by_group.get((kind, dest), []), stations, kind)
        if hit:
            return hit[0], hit[1], "exact"
        same_class = [r for r in self.by_dest.get(dest, []) if train_class(self.records.at[r, "type_key"]) == train_class(kind)]
        hit = self._pick(same_class, stations, kind)
        if hit:
            return hit[0], hit[1], "corridor"
        at_station = [r for r in self.by_type.get(kind, []) if self.records.at[r, "station_key"] in stations]
        hit = self._pick(at_station, stations, kind)
        if hit:
            return hit[0], hit[1], "station"
        return None, False, "prior"

    # --- forecasts -----------------------------------------------------------

    def leg_forecast(self, leg: dict) -> dict:
        train_id = leg.get("trainId")
        kind = train_type(train_id)
        to_name = (leg.get("to") or {}).get("name") or "the target station"
        rid, scored, how = self.match(leg)
        origin_note = {
            "exact": "",
            "corridor": f" Closest recorded service to {train_id} → {to_name}: same destination, same train class, on the same corridor.",
            "station": f" Closest recorded {kind} service at one of this leg's stations; a different destination.",
        }
        if rid is not None:
            r = self.records.loc[rid]
            label = f"{r['service_group']} at {r['station']}"
            p_cancel, cancel_src = self.cancel_rate(r["service_group"], kind)
            if scored:
                f = self.forecasts[rid]
                probs = probs_from_quantiles(f["quantiles"])
                q = quantiles(probs)
                reasoning = (f"Fine-tuned model forecast for {label}, travel date {r['anchor_iso']} (held-out {f['cell']} row): "
                             f"median +{q[MEDIAN]} min, 10–90% range {q[LOW]}–{q[HIGH]} min for the following week's departure delay. "
                             f"Inputs: 60 days of six-hourly delay, throughput and cause-share history at that stop and across the service."
                             f" What then happened: mean +{f['y']:.1f} min.{origin_note[how]}")
                sources = [f"{self.model_id} (model forecast, {f['cell']} cell)", f"record {rid}",
                           "60 days × 6 h history from piebro/deutsche-bahn-data (CC BY 4.0)",
                           cancel_src]
                confidence = "medium" if how == "exact" else "low"
                origin = "model forecast"
            else:
                hist = self.series.get((rid, "service_at_station_delay"))
                probs = probs_from_history(hist) if hist is not None else None
                if probs is None:
                    return self._prior(leg, kind, f"no usable history for {label}")
                q = quantiles(probs)
                reasoning = (f"Recorded history, not a model forecast: {label} over the 60 days before {r['anchor_iso']} "
                             f"ran a median +{q[MEDIAN]} min late, 10–90% range {q[LOW]}–{q[HIGH]} min (six-hourly means). "
                             f"The model did not score this record.{origin_note[how]}")
                sources = ["recorded history (six-hourly mean delay, 60 days)", f"record {rid}",
                           "piebro/deutsche-bahn-data (CC BY 4.0)", cancel_src]
                confidence = "low"
                origin = "recorded history"
            on_time = float(probs[:LATE_MINUTES].sum()) * (1 - p_cancel)
            out = {
                "trainId": train_id,
                "arrival": {"probs": rounded(probs), "pCancel": round(p_cancel, 4)},
                "departure": {"probs": rounded(probs), "pCancel": round(p_cancel, 4)},
                "reasoning": reasoning,
                "sources": sources,
                "confidence": confidence,
                "origin": origin,
                "match": how,
                "matched": {"recordId": rid, "service": r["service_group"], "station": r["station"],
                            "travelDate": r["anchor_iso"], "state": r.get("federal_state")},
                "quantiles": {"p10": int(q[LOW]), "p50": int(q[MEDIAN]), "p90": int(q[HIGH])},
                "pOnTime": round(on_time, 4),
            }
            if scored:
                out["actual"] = {"meanDelayMinutes": round(self.forecasts[rid]["y"], 1)}
            gen = self.generation_by_record.get(rid)
            if gen:
                out["generation"] = self._describe_generation(gen)
            return out
        return self._prior(leg, kind, f"no recorded {kind or 'train'} service to {to_name}")

    def _prior(self, leg: dict, kind: str, why: str) -> dict:
        p_cancel, cancel_src = self.cancel_rate(None, kind)
        probs = self.type_prior.get(kind)
        scope = f"{kind} trains" if probs is not None else "all trains"
        if probs is None:
            probs = self.global_prior
        q = quantiles(probs)
        return {
            "trainId": leg.get("trainId"),
            "arrival": {"probs": rounded(probs), "pCancel": round(p_cancel, 4)},
            "departure": {"probs": rounded(probs), "pCancel": round(p_cancel, 4)},
            "reasoning": (f"Class prior, not a forecast for this train: {why}, so this is the average of the model's held-out "
                          f"forecasts for {scope} (median +{q[MEDIAN]} min, 10–90% {q[LOW]}–{q[HIGH]} min)."),
            "sources": [f"{self.model_id} (average held-out forecast, {scope})", cancel_src],
            "confidence": "low",
            "origin": "class prior",
            "match": "prior",
            "quantiles": {"p10": int(q[LOW]), "p50": int(q[MEDIAN]), "p90": int(q[HIGH])},
        }

    def forecast(self, journey: dict) -> dict:
        legs = journey.get("legs") or []
        if not isinstance(legs, list) or not legs:
            raise ValueError("Body must be a Journey with at least one leg")
        out = [self.leg_forecast(leg) for leg in legs]
        levels = {"high": 2, "medium": 1, "low": 0}
        return {"modelId": self.model_id, "confidence": min((l["confidence"] for l in out), key=levels.get), "legs": out}

    # --- causes ----------------------------------------------------------------

    def causes(self, station: str | None, eva: str | None) -> dict | None:
        key = norm(station)
        rids = self.by_station.get(key) if key else None
        if not rids and key:
            rids = [r for k, rs in self.by_station.items() if len(key) >= 5 and (key in k or k in key) for r in rs]
        nearby = False
        if not rids and key:
            # No record at the station itself (hubs outside the local-operator catchment, airport
            # terminals): use the latest recorded stop on services that end there, and say so.
            rids, nearby = self.by_dest.get(key, []), True
        if not rids:
            return None
        sub = self.records.loc[rids]
        rid = sub["anchor_iso"].idxmax()
        r = self.records.loc[rid]
        window = 7 * BUCKETS_PER_DAY

        def last(sig: str) -> np.ndarray | None:
            v = self.series.get((rid, sig))
            return None if v is None else np.asarray(v[-window:], dtype=float)

        def mean_of(sig: str) -> float:
            v = last(sig)
            v = v[np.isfinite(v)] if v is not None else np.array([])
            return float(v.mean()) if len(v) else 0.0

        attribution = mean_of("attributed_share")
        if not np.isfinite(attribution) or attribution <= 0:
            attribution = float(r.get("attributed_share") or 0.0)
        raw = {f: max(0.0, mean_of(f"{f}_share")) for f in ("works", "weather", "technical", "knock_on")}
        total = sum(raw.values())
        if total > 1.0:  # shares of attributed delay should sum to at most one; renormalise if the window disagrees
            raw = {k: v / total for k, v in raw.items()}
            total = 1.0
        families = {k: round(v * attribution, 3) for k, v in raw.items()}
        families["staff"] = 0.0
        families["external"] = round(max(0.0, (1.0 - total) * attribution), 3)
        families["unattributed"] = round(max(0.0, 1.0 - attribution), 3)
        anchor = date.fromisoformat(r["anchor_iso"])
        delay = last("station_delay")
        spark = []
        if delay is not None and len(delay) == window:
            for d in range(7):
                day = delay[d * BUCKETS_PER_DAY:(d + 1) * BUCKETS_PER_DAY]
                day = day[np.isfinite(day)]
                spark.append({"date": (anchor - timedelta(days=7 - d)).isoformat(), "meanDelayMin": round(float(day.mean()), 1) if len(day) else None})
        ranked = sorted(((v, k) for k, v in families.items() if k not in ("unattributed", "staff")), reverse=True)
        labels = {"works": "Bauarbeiten / engineering works", "weather": "Witterung / weather", "technical": "Technische Störung / technical fault",
                  "knock_on": "Verspätung eines vorausfahrenden Zuges / knock-on", "external": "Sonstige Ursachen / other attributed causes"}
        codes = {"works": 31, "weather": 22, "technical": 36, "knock_on": 43, "external": 99}
        where = (f"{r['station']}, the last recorded stop of {r['service_group']} before {station} (no records at {station} itself)"
                 if nearby else r["station"])
        return {
            "station": {"evaNumber": eva or "", "name": station if nearby else r["station"]},
            "attributionRate": round(attribution, 3),
            "families": families,
            "top": [{"code": codes[k], "text": labels[k], "family": k, "share": v} for v, k in ranked[:3] if v > 0],
            "sparkline7d": spark,
            "source": (f"piebro/deutsche-bahn-data (DB IRIS cause codes), {where}, seven days to {r['anchor_iso']}; "
                       f"families are IRIS cause families from the db_route pipeline, staff is not tracked as a series"),
            "illustrative": False,
            "matched": not nearby,
            "nearby": nearby,
            "recordId": rid,
            "asOf": r["anchor_iso"],
        }

    def cancel_rate(self, service_group: str | None, kind: str) -> tuple[float, str]:
        """P(cancelled) for a leg and the sentence that says where it came from: the service's own
        measured rate, else its train type's, else the network's, else the flat assumption."""
        c = self.cancellations
        if c:
            window = c.get("window", {})
            span = f"{window.get('start')} to {window.get('end')}"
            hit = c["_services_norm"].get(norm(service_group)) if service_group else None
            if hit:
                return hit["rate"], f"cancellations: {hit['rate']:.1%} of {hit['n']:,} recorded {service_group} stops, {span}"
            hit = c.get("types", {}).get(kind)
            if hit:
                return hit["rate"], f"cancellations: {hit['rate']:.1%} of {hit['n']:,} recorded {kind} stops nationwide, {span}"
            overall = c.get("overall")
            if overall:
                return overall["rate"], f"cancellations: {overall['rate']:.1%} of all recorded stops nationwide, {span}"
        return P_CANCEL, f"cancellations not modelled; {P_CANCEL:.0%} assumed"

    def _describe_generation(self, g: dict) -> dict:
        """A generation sample with the record's station, service and travel date attached."""
        out = dict(g)
        if g["recordId"] in self.records.index:
            r = self.records.loc[g["recordId"]]
            out.update({"station": r["station"], "service": r["service_group"], "travelDate": r["anchor_iso"],
                        "cell": r.get("split_cell")})
        return out

    def generations_payload(self) -> dict:
        return {"modelId": self.model_id, "count": len(self.generations), "job": getattr(self, "generation_job", ""),
                "samples": [self._describe_generation(g) for g in self.generations],
                "note": "Generated on one H100 by generate_route.py from the trained checkpoint for random held-out rows; "
                        "the job log is the only source, parsed by parse_generations.py."}

    def health(self) -> dict:
        cells = {c: v.get("tslm") for c, v in (self.metrics.get("cells") or {}).items()}
        return {"ok": True, "modelId": self.model_id, "records": int(len(self.records)), "scoredRecords": len(self.forecasts),
                "stations": int(self.records["station"].nunique()), "serviceGroups": int(self.records["service_group"].nunique()),
                "trainTypes": sorted(self.type_prior), "metrics": cells, "loadedInSeconds": round(self.loaded_in, 1)}


def make_handler(data: RouteData):
    class Handler(BaseHTTPRequestHandler):
        def _reply(self, status: int, body: dict) -> None:
            payload = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("content-type", "application/json; charset=utf-8")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:  # noqa: N802
            url = urlparse(self.path)
            if url.path.rstrip("/") == "/generations":
                return self._reply(200, data.generations_payload())
            if url.path.rstrip("/") == "/causes":
                q = parse_qs(url.query)
                out = data.causes((q.get("station") or [None])[0], (q.get("eva") or [None])[0])
                if out is None:
                    return self._reply(404, {"error": "no recorded station matches", "station": (q.get("station") or [None])[0]})
                return self._reply(200, out)
            return self._reply(200, data.health())

        def do_POST(self) -> None:  # noqa: N802
            try:
                length = int(self.headers.get("content-length") or 0)
                journey = json.loads(self.rfile.read(length) or b"{}")
                self._reply(200, data.forecast(journey))
            except (ValueError, KeyError, TypeError) as error:
                self._reply(400, {"error": str(error)})

        def log_message(self, fmt, *args) -> None:
            print(f"{self.address_string()} {fmt % args}", flush=True)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--data", default=str(HERE.parents[2] / "data" / "db-route"), help="local mirror of the bucket (fetch_serving_data.sh)")
    parser.add_argument("--profile", default="quarter", help="week | quarter | season | multiscale")
    parser.add_argument("--tag", default="route-2k")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8501)
    args = parser.parse_args()
    data = RouteData(Path(args.data), args.tag, args.profile)
    h = data.health()
    print(f"{h['records']} records, {h['scoredRecords']} model forecasts, {h['stations']} stations, {h['serviceGroups']} service groups "
          f"({h['loadedInSeconds']} s)", flush=True)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(data))
    print(f"serving {data.model_id} on http://{args.host}:{args.port}  (POST /predict, GET /causes?station=, GET /health)", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
