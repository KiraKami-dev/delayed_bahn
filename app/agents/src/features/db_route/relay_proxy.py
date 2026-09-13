"""Laptop side of the bucket relay: an HTTP model server whose answers come from the GPU job.

``serve_live.py`` runs on a Nebius job that has no ingress. This proxy speaks the same HTTP
contract as ``serve_route.py`` (``POST /predict``, ``GET /causes``, ``GET /health``) and forwards
each request as a JSON object in the shared bucket, ``live/<name>/requests/<id>.json``; the job
answers with ``live/<name>/responses/<id>.json``, which is returned here and deleted.

Credentials: ``NEBIUS_S3_ACCESS_KEY_ID`` / ``NEBIUS_S3_SECRET_ACCESS_KEY`` (and optional
``NEBIUS_S3_ENDPOINT``) from the repo-root ``.env`` or the environment.

    uv run --no-project --with boto3 python relay_proxy.py --port 8502
    PREDICT_URL=http://127.0.0.1:8502/predict CAUSES_URL=http://127.0.0.1:8502/causes node app/backend/src/server.js
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

HERE = Path(__file__).parent


def load_env() -> None:
    try:
        root = Path(os.popen(f"git -C '{HERE}' rev-parse --show-toplevel").read().strip())
    except OSError:
        return
    env = root / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        if line.startswith("NEBIUS_S3_") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


class Relay:
    def __init__(self, bucket: str, prefix: str, timeout_s: float, poll_s: float, fallback: str = ""):
        load_env()
        self.fallback = fallback.rstrip("/")
        endpoint = os.environ.get("NEBIUS_S3_ENDPOINT", "https://storage.eu-north1.nebius.cloud")
        self.s3 = boto3.client(
            "s3", endpoint_url=endpoint, region_name=endpoint.split("storage.", 1)[1].split(".", 1)[0],
            aws_access_key_id=os.environ["NEBIUS_S3_ACCESS_KEY_ID"], aws_secret_access_key=os.environ["NEBIUS_S3_SECRET_ACCESS_KEY"],
            config=Config(retries={"max_attempts": 2}, connect_timeout=5, read_timeout=10, max_pool_connections=32),
        )
        self.bucket, self.prefix, self.timeout_s, self.poll_s = bucket, prefix.strip("/"), timeout_s, poll_s
        self.calls, self.total_ms = 0, 0.0

    def ready(self, max_age_s: float = 120.0) -> float | None:
        """Timestamp of the job's latest heartbeat if it is recent, else None (a dead job leaves
        its files behind, so a stale heartbeat counts as not ready)."""
        for name in ("heartbeat.txt", "ready.txt"):
            try:
                obj = self.s3.get_object(Bucket=self.bucket, Key=f"{self.prefix}/{name}")
                ts = float(obj["Body"].read().decode().strip())
            except (ClientError, ValueError):
                continue
            return ts if time.time() - ts < max_age_s else None
        return None

    def keep_folders(self) -> None:
        """An emptied prefix vanishes on an object store; a .keep object keeps both folders listable."""
        for sub in ("requests", "responses"):
            try:
                self.s3.put_object(Bucket=self.bucket, Key=f"{self.prefix}/{sub}/.keep", Body=b"keep\n")
            except ClientError as error:
                print(f"could not create {sub}/.keep: {error}", flush=True)

    def call(self, method: str, path: str, query: dict, body: dict | None) -> tuple[int, dict]:
        if self.fallback and self.ready() is None:
            return self.fall_back(method, path, query, body, "GPU job not ready")
        rid = f"{time.time():.3f}-{uuid.uuid4().hex[:8]}"
        req = {"id": rid, "ts": time.time(), "method": method, "path": path, "query": query, "body": body}
        t = time.time()
        self.s3.put_object(Bucket=self.bucket, Key=f"{self.prefix}/requests/{rid}.json", Body=json.dumps(req).encode())
        key = f"{self.prefix}/responses/{rid}.json"
        while time.time() - t < self.timeout_s:
            time.sleep(self.poll_s)
            try:
                raw = self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()
            except ClientError as error:
                if error.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                    continue
                raise
            try:
                reply = json.loads(raw)
            except ValueError:
                continue  # partially written; the job writes in one call, so the next read is whole
            try:
                self.s3.delete_object(Bucket=self.bucket, Key=key)
            except ClientError:
                pass
            ms = (time.time() - t) * 1000
            self.calls += 1
            self.total_ms += ms
            body_out = reply.get("body") or {}
            if isinstance(body_out, dict):
                body_out.setdefault("relayMs", round(ms))
            print(f"{method} {path} -> {reply.get('status')} via bucket in {ms:.0f} ms", flush=True)
            return int(reply.get("status", 200)), body_out
        try:
            self.s3.delete_object(Bucket=self.bucket, Key=f"{self.prefix}/requests/{rid}.json")
        except ClientError:
            pass
        print(f"{method} {path}: no answer from the GPU job within {self.timeout_s:.0f} s", flush=True)
        if self.fallback:
            return self.fall_back(method, path, query, body, f"GPU job silent for {self.timeout_s:.0f} s")
        return 504, {"error": f"the GPU job did not answer within {self.timeout_s:.0f} s", "relay": self.prefix}

    def fall_back(self, method: str, path: str, query: dict, body: dict | None, why: str) -> tuple[int, dict]:
        """Answer from the local precomputed server and say so in modelId, so the app never lies."""
        import urllib.request  # noqa: PLC0415
        from urllib.parse import urlencode  # noqa: PLC0415
        url = self.fallback + path + (f"?{urlencode(query)}" if query else "")
        data = json.dumps(body).encode() if method == "POST" else None
        req = urllib.request.Request(url, data=data, method=method, headers={"content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as res:
                out = json.loads(res.read())
                status = res.status
        except Exception as error:  # noqa: BLE001
            return 502, {"error": f"{why}; local fallback failed too: {error}"}
        if isinstance(out, dict) and "modelId" in out:
            out["modelId"] = f"{out['modelId']} (precomputed fallback: {why})"
            out["live"] = False
        print(f"{method} {path} -> {status} from local fallback ({why})", flush=True)
        return status, out


def make_handler(relay: Relay):
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
            query = {k: v[0] for k, v in parse_qs(url.query).items()}
            if url.path.rstrip("/") == "/relay":
                ready = relay.ready()
                return self._reply(200 if ready else 503, {"ok": bool(ready), "gpuJobReadySince": ready, "calls": relay.calls,
                                                            "meanMs": round(relay.total_ms / relay.calls) if relay.calls else None})
            try:
                status, body = relay.call("GET", url.path, query, None)
            except Exception as error:  # noqa: BLE001
                return self._reply(502, {"error": str(error)})
            self._reply(status, body)

        def do_POST(self) -> None:  # noqa: N802
            try:
                length = int(self.headers.get("content-length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError as error:
                return self._reply(400, {"error": str(error)})
            try:
                status, out = relay.call("POST", urlparse(self.path).path, {}, body)
            except Exception as error:  # noqa: BLE001
                return self._reply(502, {"error": str(error)})
            self._reply(status, out)

        def log_message(self, fmt, *args) -> None:
            pass

    return Handler


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--bucket", default=os.environ.get("NEBIUS_BUCKET", "error404-db-route"))
    ap.add_argument("--name", default="live-route-quarter", help="matches serve_live.py --name")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8502)
    ap.add_argument("--timeout", type=float, default=20.0)
    ap.add_argument("--poll", type=float, default=0.15)
    ap.add_argument("--fallback", default="http://127.0.0.1:8501", help="local serve_route.py used when the GPU job does not answer ('' to disable)")
    args = ap.parse_args()
    relay = Relay(args.bucket, f"live/{args.name}", args.timeout, args.poll, args.fallback)
    relay.keep_folders()
    ready = relay.ready()
    print(f"GPU job {'ready' if ready else 'not ready yet'} at s3://{args.bucket}/live/{args.name}", flush=True)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(relay))
    print(f"relay proxy on http://{args.host}:{args.port}  (POST /predict, GET /causes, GET /health, GET /relay)", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    sys.exit(main())
