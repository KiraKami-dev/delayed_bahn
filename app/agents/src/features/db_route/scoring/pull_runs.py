"""Pull metrics.json and scalar_*.npz for the given run tags from the bucket into runs/<tag>/<profile>/."""
import os, sys, boto3
from pathlib import Path
env = {}
for line in open(str(Path(__file__).resolve().parents[5] / "backend" / ".env")):
    if line.startswith("NEBIUS_S3_"):
        k, _, v = line.strip().partition("="); env[k] = v.strip().strip('"')
s3 = boto3.client("s3", endpoint_url=env["NEBIUS_S3_ENDPOINT"], region_name=env["NEBIUS_S3_REGION"],
                  aws_access_key_id=env["NEBIUS_S3_ACCESS_KEY_ID"], aws_secret_access_key=env["NEBIUS_S3_SECRET_ACCESS_KEY"])
B = env["NEBIUS_S3_BUCKET"]; SC = Path(__file__).parent
tags = sys.argv[1:] or ["r12k-w", "r12k-l", "r6k-q", "r12k-q-s0", "r12k-q-s1", "r12k-q-s2", "r12k-q-plain", "r12k-q-caponly", "r12k-q-six", "r12k-q-lr2x", "r12k-q-full"]
for tag in tags:
    pages = s3.get_paginator("list_objects_v2").paginate(Bucket=B, Prefix=f"runs/{tag}/")
    got = []
    for page in pages:
        for o in page.get("Contents", []):
            key = o["Key"]; name = key.rsplit("/", 1)[-1]
            if name == "metrics.json" or (name.startswith("scalar_") and name.endswith(".npz")):
                dest = SC / key; dest.parent.mkdir(parents=True, exist_ok=True)
                if not dest.exists() or dest.stat().st_size != o["Size"]:
                    s3.download_file(B, key, str(dest))
                got.append(name)
    print(f"{tag:16} {'complete' if 'metrics.json' in got and len(got) >= 5 else 'partial' if got else 'nothing yet'}  {sorted(got)}")
