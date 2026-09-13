"""Put the error404 org folder where TimeNet discovers connectors.

TimeNet finds a connector at ``timenet_connectors.datasets.<org>.<name>`` and nowhere else, and
``datasets`` is a plain package, so a connector kept in this repo has to be linked into the
installed package. Run once per environment::

    python app/agents/connectors/link.py

Idempotent; prints what it did. Upstream contributes connectors by copying the folder into the
package; a symlink keeps this repo the source of truth while it is being developed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    import timenet_connectors.datasets as datasets  # noqa: PLC0415

    target = Path(datasets.__file__).parent / "error404"
    source = Path(__file__).resolve().parent / "error404"
    if target.is_symlink() or target.exists():
        if target.resolve() == source:
            print(f"already linked: {target} -> {source}")
            return 0
        print(f"refusing: {target} exists and is not this folder", file=sys.stderr)
        return 1
    os.symlink(source, target, target_is_directory=True)
    print(f"linked: {target} -> {source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
