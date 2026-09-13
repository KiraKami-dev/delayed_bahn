"""Publish runs/<tag>/<profile>/blend_<cell>.npz as a servable tag runs/<tag>-blend/<profile>/ (local + bucket)."""
import json, sys, boto3
from pathlib import Path
SC = Path(__file__).parent
tag, profile = sys.argv[1], sys.argv[2]
src = SC / "runs" / tag / profile; dst = SC / "runs" / f"{tag}-blend" / profile; dst.mkdir(parents=True, exist_ok=True)
bl = json.loads((src / "baselines_local.json").read_text())
files = []
for f in sorted(src.glob("blend_*.npz")):
    out = dst / f.name.replace("blend_", "scalar_"); out.write_bytes(f.read_bytes()); files.append(out)
w = next(iter(bl.values()))["blend"]["w_tslm"]
meta = {"profile": profile, "dataset_id": f"error404/db-route-{profile}", "source_tag": tag, "kind": "blend",
        "note": f"quantiles = {w:.2f} x TSLM ({tag}) + {1 - w:.2f} x gradient boosting on the same rows; weight fitted on val by CRPS (baselines_local.py)",
        "cells": {c: {"tslm": r["tslm"], "gbm": r["gbm"], "blend": r["blend"], "persistence": r.get("persistence")} for c, r in bl.items()}}
(dst / "metrics.json").write_text(json.dumps(meta, indent=2)); files.append(dst / "metrics.json")
env = {}
for line in open(str(Path(__file__).resolve().parents[5] / "backend" / ".env")):
    if line.startswith("NEBIUS_S3_"):
        k, _, v = line.strip().partition("="); env[k] = v.strip().strip('"')
s3 = boto3.client("s3", endpoint_url=env["NEBIUS_S3_ENDPOINT"], region_name=env["NEBIUS_S3_REGION"],
                  aws_access_key_id=env["NEBIUS_S3_ACCESS_KEY_ID"], aws_secret_access_key=env["NEBIUS_S3_SECRET_ACCESS_KEY"])
for f in files:
    s3.upload_file(str(f), env["NEBIUS_S3_BUCKET"], f"runs/{tag}-blend/{profile}/{f.name}")
print(f"published runs/{tag}-blend/{profile}: {[f.name for f in files]} (w_tslm={w:.2f})")
