"""Build the four db-route datasets for all of Germany on a Nebius box.

The laptop builds Munich in four minutes; all ~5,300 stations is ten times the
pair grain and a 140M-row archive scan per profile, so it runs where there are
128 cores and 768 GB. Everything the job needs is in the mounted bucket:

    /outputs/code/db_route.tar.gz     app/agents/{src/features/db_route,connectors}
    /outputs/causes/all, notices/all  the unfiltered day shards (remote_extract, evas=[])

and it writes back:

    /outputs/registry/                the built TimeF datasets, four ids
    /outputs/validation/              the fail-closed reports
    /outputs/cache/hourly_*.parquet   the all-Germany fact tables, so a rebuild is cheap

Submit with the training-jobs CLI, output volume = the pipeline bucket:

    npm run train -- submit --name build-all-germany --script remote_build.py \
        --requirements req_build.txt --image python:3.12-slim \
        --platform gpu-l40s-d --preset 4gpu-128vcpu-768gb \
        --output storagebucket-e0016098467606655017642 --timeout 3h
"""

from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
from pathlib import Path

OUT = Path(os.environ.get("NEBIUS_OUTPUT_DIR", "/outputs"))
CODE = Path("/workspace/code")
CACHE = Path(os.environ.get("DB_ROUTE_CACHE", "/tmp/db_route_cache"))
# Where the day shards were written. The extraction job's ``--out``; a second
# extraction racing for a free node writes to its own prefix, so this is a knob.
SHARDS = Path(os.environ.get("DB_ROUTE_SHARDS", str(OUT)))
MONTHS = os.environ.get("DB_ROUTE_MONTHS", "2025-11,2026-08")
ENTITIES = os.environ.get("DB_ROUTE_ENTITIES", "3000")
PROCESSED = "https://huggingface.co/datasets/piebro/deutsche-bahn-data/resolve/main/monthly_processed_data"


def copy_tree_bytes(src: Path, dst: Path) -> int:
    """Copy a tree with nothing but mkdir and byte writes.

    The bucket mount accepts file bytes and directory creation and refuses
    every metadata call -- chmod, utime, rename. The stdlib tree copy runs
    copystat on every directory it fills, and the TimeF writer commits with
    a rename: three builds died on exactly that; a smoke job proved this walk.
    """
    n = 0
    for root, _dirs, files in os.walk(src):
        rel = Path(root).relative_to(src)
        (dst / rel).mkdir(parents=True, exist_ok=True)
        for name in files:
            shutil.copyfile(Path(root) / name, dst / rel / name)
            n += 1
    return n


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def months() -> list[str]:
    first, _, last = MONTHS.partition(",")
    last = last or first
    out, cur = [], dt.date(int(first[:4]), int(first[5:7]), 1)
    end = dt.date(int(last[:4]), int(last[5:7]), 1)
    while cur <= end:
        out.append(cur.strftime("%Y-%m"))
        cur = (cur.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return out


def fetch_month(month: str) -> str:
    dest = CACHE / "monthly" / f"data-{month}.parquet"
    if dest.exists() and dest.stat().st_size > 1_000_000:
        return f"{month}: cached"
    tmp = dest.with_suffix(".part")
    with urllib.request.urlopen(f"{PROCESSED}/data-{month}.parquet", timeout=120) as r, tmp.open("wb") as f:
        shutil.copyfileobj(r, f, 16 << 20)
    tmp.rename(dest)
    return f"{month}: {dest.stat().st_size / 1e9:.2f} GB"


def main() -> int:
    log(f"cores={os.cpu_count()} months={MONTHS} entities={ENTITIES}")
    CODE.mkdir(parents=True, exist_ok=True)
    with tarfile.open(OUT / "code" / "db_route.tar.gz") as tar:
        tar.extractall(CODE)
    agents = CODE / "app" / "agents"
    features = agents / "src" / "features" / "db_route"
    subprocess.run([sys.executable, str(agents / "connectors" / "link.py")], check=True)

    (CACHE / "monthly").mkdir(parents=True, exist_ok=True)
    ms = months()
    with cf.ThreadPoolExecutor(4) as pool:
        for line in pool.map(fetch_month, ms):
            log(line)

    # Shards: the unfiltered extraction lives in the bucket; the pipeline
    # expects them under the cache keyed by fingerprint "all".
    for kind in ("causes", "notices"):
        src, dst = SHARDS / kind / "all", CACHE / kind / "all"
        dst.mkdir(parents=True, exist_ok=True)
        n = 0
        for p in sorted(src.glob("*.parquet")):
            if not (dst / p.name).exists():
                shutil.copyfile(p, dst / p.name)
            n += 1
        log(f"{kind}: {n} day shards")
        if n < 200:
            raise SystemExit(f"only {n} {kind} shards under {src}; extraction incomplete")

    # The catchment for all Germany: every station observed in the window.
    # evas=[] is the fingerprint "all" the shards were extracted under.
    catchment = CACHE / "catchment_evas.json"
    if not catchment.exists():
        import duckdb  # noqa: PLC0415

        files = [str(CACHE / "monthly" / f"data-{m}.parquet") for m in ms]
        con = duckdb.connect()
        con.execute(f"SET threads={os.cpu_count()}")
        stations = [
            r[0]
            for r in con.execute(
                "SELECT DISTINCT station_name FROM read_parquet(?) WHERE station_name IS NOT NULL "
                "AND CAST(time - INTERVAL 3 HOUR AS DATE) >= DATE '2025-11-02' ORDER BY 1",
                [files],
            ).fetchall()
        ]
        catchment.write_text(json.dumps({"evas": [], "stations": stations, "regions": ["all"]}))
        log(f"catchment: {len(stations)} stations")

    # Reuse fact tables from an earlier run of this job, if any.
    for g in ("station", "line", "pair"):
        prior = OUT / "cache" / f"hourly_{g}.parquet"
        if prior.exists() and not (CACHE / f"hourly_{g}.parquet").exists():
            shutil.copyfile(prior, CACHE / f"hourly_{g}.parquet")
            log(f"reused {prior.name} from the bucket")

    env = dict(os.environ, DB_ROUTE_CACHE=str(CACHE), DB_ROUTE_ENTITIES=ENTITIES,
               DB_ROUTE_MONTHS=MONTHS, DB_ROUTE_MEMORY=os.environ.get("DB_ROUTE_MEMORY", "200GB"),
               TIMENET_ISOLATION="off",
               PYTHONPATH=str(features))
    # Build on local disk. The TimeF writer commits a version by renaming its
    # staging directory into place (os.replace), and the bucket mount cannot
    # rename a directory -- measured: the whole build ran, then died on the
    # commit. Plain file writes to the mount are fine, so the finished
    # registry is copied over afterwards.
    registry = Path("/tmp/registry")
    for name in ("week", "quarter", "season", "multiscale"):
        t = time.time()
        subprocess.run(
            ["timenet-build", "build", f"error404/db-route-{name}", "--out", str(registry), "--no-isolation"],
            check=True, env=env,
        )
        log(f"built error404/db-route-{name} in {time.time() - t:.0f}s")
        copy_tree_bytes(registry, OUT / "registry")
        log(f"copied registry to {OUT / 'registry'}")
        # The fact tables exist after the first build; bank them.
        for g in ("station", "line", "pair"):
            src = CACHE / f"hourly_{g}.parquet"
            dst = OUT / "cache" / f"hourly_{g}.parquet"
            if src.exists() and not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dst)
        if not (OUT / "cache" / "catchment_evas.json").exists():
            (OUT / "cache").mkdir(parents=True, exist_ok=True)
            shutil.copyfile(catchment, OUT / "cache" / "catchment_evas.json")

    validate = features / "validate.py"
    vout = Path("/tmp/validation")
    for pid in ("S", "M", "L", "XM"):
        subprocess.run([sys.executable, str(validate), "records", "--profile", pid, "--registry", str(registry),
                        "--out", str(vout / pid)], env=env, check=False)
    subprocess.run([sys.executable, str(validate), "cross", "--registry", str(registry),
                    "--out", str(vout / "cross")], env=env, check=False)
    copy_tree_bytes(vout, OUT / "validation")
    log("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
