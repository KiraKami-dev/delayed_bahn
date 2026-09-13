"""Live model server: the fine-tuned db-route TSLM answers every journey on the GPU, per request.

Same reply contract as ``serve_route.py`` (``POST /predict``, ``GET /causes``, ``GET /health``),
but the minute distribution for a matched record comes from a forward pass of the trained
checkpoint at request time, not from the ``scalar_<cell>.npz`` files the training job wrote.
Because the model is here, every recorded (service group, station) can be forecast, not only
the held-out cells that were scored during training.

Runs as a Nebius job (one GPU) with the training staging: ``/outputs/code/db_route_live.tar.gz``
(this repo's agents code, with ``serve_route.py`` and this file), ``/outputs/registry`` and
``/outputs/runs/<tag>/<profile>/checkpoint.pt`` from the bucket mount. A Nebius job has no
ingress, so requests reach it through the bucket: ``relay_proxy.py`` on the laptop writes
``live/<name>/requests/<id>.json`` and this server answers with ``live/<name>/responses/<id>.json``
(``--relay``, the default). ``--tunnel`` instead opens a Cloudflare quick tunnel and publishes its
URL to ``/outputs/serve/<name>/url.txt`` and the job log (``TUNNEL_URL=https://...``).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import numpy as np

OUT = Path(os.environ.get("NEBIUS_OUTPUT_DIR", "/outputs"))
CLOUDFLARED = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="quarter")
    ap.add_argument("--tag", default="route-2k")
    ap.add_argument("--checkpoint", default=None, help="default runs/<tag>/<profile>/checkpoint.pt in the bucket")
    ap.add_argument("--registry", default=str(OUT / "registry"))
    ap.add_argument("--tarball", default=str(OUT / "code" / "db_route_live.tar.gz"))
    ap.add_argument("--name", default="live", help="folder under /outputs/serve that receives url.txt")
    ap.add_argument("--port", type=int, default=8501)
    ap.add_argument("--relay", default=str(OUT / "live"), help="bucket folder for the request/response relay ('' to disable)")
    ap.add_argument("--tunnel", action="store_true", help="also open a Cloudflare quick tunnel (public URL)")
    args = ap.parse_args()
    checkpoint = Path(args.checkpoint) if args.checkpoint else OUT / "runs" / args.tag / args.profile / "checkpoint.pt"

    sys.path.insert(0, str(Path(__file__).parent))
    import train_route as T  # noqa: PLC0415

    T.stage(0, Path(args.tarball))
    import torch  # noqa: PLC0415
    import torch.nn.functional as F  # noqa: PLC0415
    from opentslm.model_config import PATCH_SIZE  # noqa: PLC0415
    from opentslm.time_series_datasets.util import extend_time_series_to_match_patch_size_and_aggregate  # noqa: PLC0415
    from timenet.client import TimeNet  # noqa: PLC0415

    import bridge  # noqa: PLC0415
    import serve_route as S  # noqa: PLC0415
    from model import START_CHECKPOINT, TripTSLM  # noqa: PLC0415

    t0 = time.time()
    dataset = TimeNet(args.registry).load(f"error404/db-route-{args.profile}")
    rows = T.build_rows(dataset, bridge)
    scalar = {r["record_id"]: r for r in rows if r["kind"] == "ScalarPredictionTask"}
    print(f"{len(scalar)} records with a delay task ({time.time() - t0:.0f}s)", flush=True)

    t0 = time.time()
    RouteTSLM = T.make_model_class(TripTSLM, torch, F)
    model = RouteTSLM.from_opentslm_checkpoint(START_CHECKPOINT, loss_mode="plain_crps", device="cuda")
    if not model.lora_enabled:
        model.enable_lora()
    model.load_from_file(str(checkpoint))
    model.eval()
    gpu = torch.cuda.get_device_name(0)
    print(f"loaded {checkpoint} on {gpu} ({time.time() - t0:.0f}s)", flush=True)

    def collate(batch):
        return extend_time_series_to_match_patch_size_and_aggregate([T.strip(s) for s in batch], patch_size=PATCH_SIZE)

    lock = threading.Lock()

    def infer(row: dict) -> tuple[np.ndarray, float, float]:
        """Minute pmf on serve_route's support, the model's P(cancelled), and the wall time in ms."""
        t = time.time()
        with lock, torch.no_grad():
            out = model.predict_distribution(collate([row]))
            full = out["probs"][0].float().cpu().numpy()
            p_cancel = float(out["p_cancel"][0])
        probs = np.zeros(S.MINUTES)
        probs[: S.MINUTES] = full[: S.MINUTES]
        probs[-1] += full[S.MINUTES:].sum()
        return probs / probs.sum(), p_cancel, (time.time() - t) * 1000

    class LiveData(S.RouteData):
        def __init__(self):
            super().__init__(OUT, args.tag, args.profile)
            # Every record with a task can be forecast now, so the matcher should prefer the
            # leg's own stations and the latest date rather than the training-time scored cells.
            self.records["scored"] = self.records.index.isin(scalar)
            self.model_id = f"{self.model_id} · live on {gpu.replace('NVIDIA ', '')}"
            self.served = 0
            self.total_ms = 0.0

        def leg_forecast(self, leg: dict) -> dict:
            rid, _scored, how = self.match(leg)
            row = scalar.get(rid) if rid is not None else None
            if row is None:
                return super().leg_forecast(leg)
            r = self.records.loc[rid]
            train_id = leg.get("trainId")
            kind = S.train_type(train_id)
            to_name = (leg.get("to") or {}).get("name") or "the target station"
            label = f"{r['service_group']} at {r['station']}"
            probs, model_p_cancel, ms = infer(row)
            self.served += 1
            self.total_ms += ms
            q = S.quantiles(probs)
            p_cancel, cancel_src = self.cancel_rate(r["service_group"], kind)
            origin_note = {
                "exact": "",
                "corridor": f" Closest recorded service to {train_id} → {to_name}: same destination, same train class, on the same corridor.",
                "station": f" Closest recorded {kind} service at one of this leg's stations; a different destination.",
            }[how]
            actual = row.get("y")
            happened = f" What then happened: mean +{actual:.1f} min." if actual is not None else ""
            reasoning = (f"Live forecast: the fine-tuned model ran on the GPU for this request ({ms:.0f} ms) for {label}, "
                         f"travel date {r['anchor_iso']} ({row['cell']} row): median +{q[S.MEDIAN]} min, "
                         f"10–90% range {q[S.LOW]}–{q[S.HIGH]} min for the following week's departure delay. "
                         f"Inputs: 60 days of six-hourly delay, throughput and cause-share history at that stop and across the service."
                         f"{happened}{origin_note}")
            sources = [f"{self.model_id} (live GPU inference, {ms:.0f} ms, {row['cell']} row)", f"record {rid}",
                       "60 days × 6 h history from piebro/deutsche-bahn-data (CC BY 4.0)", cancel_src]
            on_time = float(probs[: S.LATE_MINUTES].sum()) * (1 - p_cancel)
            out = {
                "trainId": train_id,
                "arrival": {"probs": S.rounded(probs), "pCancel": round(p_cancel, 4)},
                "departure": {"probs": S.rounded(probs), "pCancel": round(p_cancel, 4)},
                "reasoning": reasoning,
                "sources": sources,
                "confidence": "medium" if how == "exact" else "low",
                "origin": "live model forecast",
                "live": True,
                "inferenceMs": round(ms, 1),
                "modelPCancel": round(model_p_cancel, 4),
                "match": how,
                "matched": {"recordId": rid, "service": r["service_group"], "station": r["station"],
                            "travelDate": r["anchor_iso"], "state": r.get("federal_state"), "cell": row["cell"]},
                "quantiles": {"p10": int(q[S.LOW]), "p50": int(q[S.MEDIAN]), "p90": int(q[S.HIGH])},
                "pOnTime": round(on_time, 4),
            }
            if actual is not None:
                out["actual"] = {"meanDelayMinutes": round(float(actual), 1)}
            gen = self.generation_by_record.get(rid)
            if gen:
                out["generation"] = self._describe_generation(gen)
            return out

        def health(self) -> dict:
            h = super().health()
            h.update(live=True, gpu=gpu, checkpoint=str(checkpoint), forecastableRecords=len(scalar),
                     served=self.served, meanInferenceMs=round(self.total_ms / self.served, 1) if self.served else None)
            return h

    data = LiveData()
    # Warm up: the first CUDA call pays for kernel loading; do it before the URL goes public.
    any_row = next(iter(scalar.values()))
    _, _, warm = infer(any_row)
    _, _, second = infer(any_row)
    print(f"warm-up forward {warm:.0f} ms, second {second:.0f} ms", flush=True)

    server = ThreadingHTTPServer(("0.0.0.0", args.port), S.make_handler(data))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"serving {data.model_id} on http://0.0.0.0:{args.port}", flush=True)

    if args.relay:
        threading.Thread(target=relay, args=(data, Path(args.relay) / args.name), daemon=True).start()
    if args.tunnel:
        threading.Thread(target=tunnel, args=(args.port, OUT / "serve" / args.name), daemon=True).start()
    try:
        while True:
            time.sleep(60)
            print(f"alive: served {data.served} live legs, mean {data.total_ms / data.served if data.served else 0:.0f} ms", flush=True)
    except KeyboardInterrupt:
        return 0


def relay(data, folder: Path, poll_s: float = 0.3, max_age_s: float = 60.0, heartbeat_s: float = 20.0) -> None:
    """Answer requests dropped into the bucket by relay_proxy.py. Each request is one JSON file
    ``{"id", "method", "path", "query", "body"}``; the reply is ``{"status", "body"}`` under the
    same id in ``responses/``. The mount is an object store: an emptied folder disappears, so both
    folders keep a ``.keep`` object, every write re-creates its folder, and the loop never dies on
    one bad pass. ``heartbeat.txt`` is rewritten so the proxy can tell a live job from a dead one."""
    requests_dir, responses_dir = folder / "requests", folder / "responses"

    def ensure(d: Path) -> None:
        d.mkdir(parents=True, exist_ok=True)
        keep = d / ".keep"
        if not keep.exists():
            keep.write_bytes(b"keep\n")

    def write(path: Path, payload: bytes) -> None:
        ensure(path.parent)
        try:
            path.unlink()
        except OSError:
            pass
        path.write_bytes(payload)

    for d in (requests_dir, responses_dir):
        ensure(d)
    write(folder / "ready.txt", f"{time.time():.0f}\n".encode())
    write(folder / "heartbeat.txt", f"{time.time():.0f}\n".encode())
    print(f"relay listening on {requests_dir}", flush=True)
    done: set[str] = set()
    last_beat = time.time()
    while True:
        try:
            if time.time() - last_beat > heartbeat_s:
                write(folder / "heartbeat.txt", f"{time.time():.0f}\n".encode())
                last_beat = time.time()
            try:
                names = sorted(os.listdir(requests_dir))
            except FileNotFoundError:
                ensure(requests_dir)
                names = []
            for name in names:
                if not name.endswith(".json") or name in done:
                    continue
                path = requests_dir / name
                try:
                    req = json.loads(path.read_bytes())
                except (OSError, ValueError):
                    continue  # still being written, or already gone; next pass
                done.add(name)
                if time.time() - float(req.get("ts", time.time())) > max_age_s:
                    _unlink(path)
                    continue
                t = time.time()
                status, body = answer(data, req)
                write(responses_dir / name, json.dumps({"status": status, "body": body}, ensure_ascii=False).encode())
                _unlink(path)
                print(f"relay {req.get('method')} {req.get('path')} -> {status} in {(time.time() - t) * 1000:.0f} ms", flush=True)
            if len(done) > 5000:
                done = set(sorted(done)[-1000:])
        except Exception as error:  # noqa: BLE001  -- the relay must outlive any single bad pass
            print(f"relay pass failed: {type(error).__name__}: {error}", flush=True)
            time.sleep(1)
        time.sleep(poll_s)


def answer(data, req: dict) -> tuple[int, dict]:
    path = str(req.get("path", "/")).rstrip("/")
    query = req.get("query") or {}
    try:
        if req.get("method") == "POST":
            return 200, data.forecast(req.get("body") or {})
        if path == "/causes":
            out = data.causes(query.get("station"), query.get("eva"))
            return (200, out) if out is not None else (404, {"error": "no recorded station matches", "station": query.get("station")})
        if path == "/generations":
            return 200, data.generations_payload()
        return 200, data.health()
    except (ValueError, KeyError, TypeError) as error:
        return 400, {"error": str(error)}


def _unlink(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def tunnel(port: int, publish_dir: Path) -> None:
    """Open a Cloudflare quick tunnel to the local server and publish its URL; restart if it dies."""
    binary = Path("/workspace/cloudflared")
    if not binary.exists():
        urllib.request.urlretrieve(CLOUDFLARED, binary)
        binary.chmod(0o755)
    while True:
        proc = subprocess.Popen([str(binary), "tunnel", "--url", f"http://127.0.0.1:{port}", "--no-autoupdate"],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in proc.stdout:
            m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
            if m:
                url = m.group(0)
                print(f"TUNNEL_URL={url}", flush=True)
                try:
                    publish_dir.mkdir(parents=True, exist_ok=True)
                    (publish_dir / "url.txt").write_bytes((url + "\n").encode())
                except OSError as error:
                    print(f"could not publish url to {publish_dir}: {error}", flush=True)
        proc.wait()
        print(f"cloudflared exited {proc.returncode}; restarting in 5 s", flush=True)
        time.sleep(5)


if __name__ == "__main__":
    raise SystemExit(main())
