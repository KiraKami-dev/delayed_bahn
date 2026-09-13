"""Run the cause extraction on a Nebius node instead of a laptop.

The work is HTTP fetch plus regex parsing over ~300 independent days, so it is
embarrassingly parallel and bound by cores and bandwidth -- neither of which a
laptop has much of. Measured locally: 8 workers on 10 cores, 26 s per day,
~2 h for six regions. The `4gpu-128vcpu-768gb` preset has **128 vCPUs** and sits
in a datacenter, so the same work should finish in minutes. The GPUs go unused;
at $7.28/h a fifteen-minute run costs about $1.80, which is cheaper than the
two hours it replaces.

The one real risk is the Hub's rate limiter. A laptop on 8 workers already
earned an HTTP 429 once, and a datacenter IP asking harder is more likely to,
not less -- so the worker count is deliberately well under the core count and
the retry/backoff in `facts.extract_day_causes` still applies. Raising
`--workers` past ~48 is more likely to trip the limiter than to finish sooner.

Shards land in /outputs, which is the mounted bucket; nothing is written to the
container disk, since that is discarded when the job ends.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import multiprocessing as mp
import os
import re
import sys
import time
from pathlib import Path

# The pipeline modules travel inside this file as a gzipped tar, but only in the
# packed copy -- see pack_remote.py.
#
# They cannot be injected as separate files: the API caps the *total* injected
# payload at 65,536 bytes and the four come to ~107 KB once base64 expands them
# by 4/3. Compressed they are a third of that. Committing the packed blob would
# mean carrying a copy of three modules that goes stale the moment they change,
# so the repo keeps this placeholder and the blob is built at submit time.
_PAYLOAD = ""  # filled in by pack_remote.py at submit time


def _unpack(dest: Path) -> None:
    """Extract the bundled modules, if this is a packed copy.

    Empty payload means we are running from the repo, where the modules sit
    beside this file already -- so the import below just works and nothing is
    written. The payload is only present in the copy `pack_remote.py` builds
    for submission, which keeps a stale duplicate of three modules out of git.
    """
    if not _PAYLOAD:
        return
    import base64, io, tarfile  # noqa: PLC0415

    with tarfile.open(fileobj=io.BytesIO(base64.b64decode(_PAYLOAD)), mode="r:gz") as tar:
        tar.extractall(dest)


_unpack(Path(__file__).parent)
sys.path.insert(0, str(Path(__file__).parent))

from causes import parse_stops  # noqa: E402
from facts import catchment_fingerprint  # noqa: E402

HF = "https://huggingface.co/datasets/piebro/deutsche-bahn-data"
TREE = "https://huggingface.co/api/datasets/piebro/deutsche-bahn-data/tree/main"


def _get_json(url: str, retries: int = 5):
    import urllib.error, urllib.request  # noqa: PLC0415

    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return json.load(r)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            if attempt == retries - 1:
                raise
            time.sleep(3 * 2**attempt)
    return []


def list_raw_files(start: dt.date, end: dt.date) -> dict[str, list[str]]:
    """Every raw file in the range, as one request per month.

    `?recursive=1` at the `raw_data` root does work, but the response is paged
    through `Link` headers rather than a cursor field, and getting that wrong
    silently returns nothing. A month is small enough to need no paging at all --
    measured: 2026-08 returns 149 parquet files across all 31 days in a single
    request -- so ten requests cover the whole range and there is no pagination
    to get wrong.
    """
    by_day: dict[str, list[str]] = {}
    month = dt.date(start.year, start.month, 1)
    while month <= end:
        batch = _get_json(f"{TREE}/raw_data/year={month.year}/month={month.month}?recursive=1")
        for entry in batch:
            path = entry.get("path", "")
            if entry.get("type") != "file" or not path.endswith(".parquet"):
                continue
            m = re.search(r"year=(\d+)/month=(\d+)/day=(\d+)/", path)
            if not m:
                continue
            day = dt.date(int(m[1]), int(m[2]), int(m[3]))
            if start <= day <= end:
                by_day.setdefault(day.isoformat(), []).append(f"{HF}/resolve/main/{path}")
        month = (month.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return {d: sorted(v) for d, v in by_day.items()}


def _download(url: str, dest: Path, retries: int = 5) -> Path:
    """Whole file, one request.

    This is the change that matters. Range-reading the parquet from the Hub
    issues many small requests per file, and at 32 workers the Hub throttles
    them: measured 487s for a day that takes 160s from a laptop, and one shard
    in thirty-five minutes. A whole-file GET is a single request the CDN is
    happy to serve at full speed -- 30-56 MB/s even from a laptop.
    """
    import urllib.error, urllib.request  # noqa: PLC0415

    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "db-route/0.1"})
            tmp = dest.with_suffix(".part")
            with urllib.request.urlopen(req, timeout=900) as r, open(tmp, "wb") as f:
                while chunk := r.read(1 << 22):
                    f.write(chunk)
            tmp.rename(dest)
            return dest
        except (urllib.error.URLError, TimeoutError) as exc:
            dest.with_suffix(".part").unlink(missing_ok=True)
            if attempt == retries - 1:
                raise RuntimeError(f"download failed: {url}: {exc}") from exc
            time.sleep(5 * 2**attempt)
    return dest


def process_day(args) -> dict:
    """Download one day's raw files, project them, write the shard, delete them."""
    day, urls, out_root, evas, workdir = args
    causes_dir = out_root / "causes" / catchment_fingerprint(evas)
    notices_dir = out_root / "notices" / catchment_fingerprint(evas)
    cpath, npath = causes_dir / f"{day}.parquet", notices_dir / f"{day}.parquet"
    if cpath.exists() and npath.exists():
        return {"day": day, "status": "cached"}

    import pyarrow as pa  # noqa: PLC0415
    import pyarrow.parquet as pq  # noqa: PLC0415

    started = time.time()
    scratch = Path(workdir) / day
    scratch.mkdir(parents=True, exist_ok=True)
    eva_set = set(evas)
    stop_ids, stop_codes, stop_fams = [], [], []
    notices: dict[str, tuple] = {}
    notice_stops: dict[str, set] = {}
    nbytes = 0
    try:
        for i, url in enumerate(urls):
            local = _download(url, scratch / f"{i}.parquet")
            table = pq.read_table(local, columns=["api_name", "url", "response_data"])
            nbytes += local.stat().st_size
            local.unlink()
            api = table.column("api_name").to_pylist()
            urlcol = table.column("url").to_pylist()
            data = table.column("response_data").to_pylist()
            for a, u, xml in zip(api, urlcol, data):
                if not xml or "fchg" not in (a or "") or "<m " not in xml:
                    continue
                m = re.search(r"(\d+)$", u or "")
                # An empty EVA set means every station: the all-Germany run.
                if not m or (eva_set and m.group(1) not in eva_set):
                    continue
                cz, nz = parse_stops(xml)
                for c in cz:
                    stop_ids.append(c.stop_id)
                    stop_codes.append(list(c.codes))
                    stop_fams.append(list(c.families))
                for n in nz:
                    notices.setdefault(
                        n.notice_id,
                        (n.category, n.valid_from, n.valid_to, n.priority, n.issued_at),
                    )
                    notice_stops.setdefault(n.notice_id, set()).add(n.stop_id)
    finally:
        for leftover in scratch.glob("*"):
            leftover.unlink(missing_ok=True)
        scratch.rmdir()

    causes_dir.mkdir(parents=True, exist_ok=True)
    notices_dir.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.table({
            "stop_id": pa.array(stop_ids, pa.string()),
            "codes": pa.array(stop_codes, pa.list_(pa.int16())),
            "families": pa.array(stop_fams, pa.list_(pa.string())),
        }),
        cpath, compression="zstd",
    )
    ids = sorted(notices)
    pq.write_table(
        pa.table({
            "notice_id": pa.array(ids, pa.string()),
            "category": pa.array([notices[i][0] for i in ids], pa.string()),
            "valid_from": pa.array([notices[i][1] for i in ids], pa.timestamp("us", tz="UTC")),
            "valid_to": pa.array([notices[i][2] for i in ids], pa.timestamp("us", tz="UTC")),
            "priority": pa.array([notices[i][3] for i in ids], pa.int8()),
            "issued_at": pa.array([notices[i][4] for i in ids], pa.timestamp("us", tz="UTC")),
            "stop_ids": pa.array([sorted(notice_stops[i]) for i in ids], pa.list_(pa.string())),
        }),
        npath, compression="zstd",
    )
    return {
        "day": day, "status": "built", "stops": len(stop_ids), "notices": len(ids),
        "mb": round(nbytes / 1e6), "seconds": round(time.time() - started, 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2025-11-02")
    parser.add_argument("--end", default="2026-08-31")
    parser.add_argument("--workers", type=int, default=0, help="0 = one per core")
    parser.add_argument("--evas", default=str(Path(__file__).parent / "evas.json"))
    parser.add_argument("--out", default=os.environ.get("NEBIUS_OUTPUT_DIR", "/outputs"))
    parser.add_argument("--scratch", default="/tmp/rawcache")
    args = parser.parse_args()

    evas = json.loads(Path(args.evas).read_text())
    if isinstance(evas, dict):
        evas = evas["evas"]
    out = Path(args.out) / "db_route"
    workers = args.workers or (os.cpu_count() or 8)

    print(f"cores={os.cpu_count()} workers={workers} evas={len(evas)}", flush=True)
    t0 = time.time()
    by_day = list_raw_files(dt.date.fromisoformat(args.start), dt.date.fromisoformat(args.end))
    print(f"listed {len(by_day)} days, {sum(len(v) for v in by_day.values())} files "
          f"in {time.time()-t0:.0f}s", flush=True)

    jobs = [(d, by_day[d], out, evas, args.scratch) for d in sorted(by_day)]
    built = failed = 0
    started = time.time()
    with mp.Pool(workers) as pool:
        for r in pool.imap_unordered(process_day, jobs, chunksize=1):
            if r["status"] == "built":
                built += 1
                done = built
                rate = (time.time() - started) / done
                print(f"  [{done}/{len(jobs)}] {r['day']}  {r['stops']:>7,} stops  "
                      f"{r['notices']:>4} notices  {r['mb']:>4} MB  {r['seconds']:>5.1f}s  "
                      f"(~{rate*(len(jobs)-done)/60:.0f} min left)", flush=True)
    print(f"\nDONE built={built} failed={failed} in {(time.time()-started)/60:.1f} min", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
