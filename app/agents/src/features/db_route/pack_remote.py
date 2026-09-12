"""Build the self-contained copy of remote_extract.py for Nebius submission.

The job needs `causes`, `facts`, `sources` and the EVA list, but the API caps
the *total* injected payload at 65,536 bytes and those four come to ~107 KB once
base64 expands them by 4/3. Gzipped into the script itself they fit with room
to spare.

Run this instead of submitting the repo copy directly -- the repo copy carries
an empty payload on purpose, so that a stale duplicate of three modules never
ends up in git.

    python pack_remote.py --evas /path/to/evas.json --out /tmp/remote_extract.py
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import re
import tarfile
from pathlib import Path

HERE = Path(__file__).parent
MODULES = ("facts.py", "causes.py", "sources.py")
CAP = 65536


def pack(evas_path: Path, out: Path) -> Path:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name in MODULES:
            tar.add(HERE / name, arcname=name)
        payload = evas_path.read_bytes()
        info = tarfile.TarInfo("evas.json")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    blob = base64.b64encode(buf.getvalue()).decode()

    source = (HERE / "remote_extract.py").read_text()
    packed = re.sub(r'_PAYLOAD = "[^"]*"[^\n]*', f'_PAYLOAD = "{blob}"', source, count=1)
    out.write_text(packed)

    encoded = int(out.stat().st_size * 4 / 3)
    if encoded > CAP:
        raise SystemExit(
            f"packed script is {encoded:,} bytes base64, over the {CAP:,} cap. "
            "Trim a module or move the EVA list to the bucket."
        )
    n = len(json.loads(evas_path.read_text()))
    print(f"packed {len(MODULES)} modules + {n} EVAs -> {out}")
    print(f"  {out.stat().st_size:,} bytes, {encoded:,} base64 ({CAP - encoded:,} under the cap)")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--evas", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("/tmp/remote_extract.packed.py"))
    args = ap.parse_args()
    pack(args.evas, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
