"""Tier 3: the assessment rubric. Filled from metadata and the probe; an LLM may propose, the probe verifies.

Set ``DISCOVER_LLM`` to a command that reads a candidate JSON on stdin and writes
a rubric JSON on stdout to let a model fill the free-text fields. Every boolean it
returns is re-checked against the probe, so a hopeful ``true`` cannot survive.
"""

from __future__ import annotations

import json
import os
import subprocess

from .spec import SourceCandidate

FIELDS = ("covers_window", "resolution", "has_actual_times", "has_cancellation", "has_cause_codes", "static", "role", "notes")


def rubric(c: SourceCandidate, probed: dict) -> dict:
    r = {
        "covers_window": bool(c.static or (c.temporal_start and c.temporal_end)),
        "resolution": "static" if c.static else (f"{c.sampling_interval_hours:g} h" if c.sampling_interval_hours else "unknown"),
        "has_actual_times": bool(probed.get("has_actual_times", False)),
        "has_cancellation": bool(probed.get("has_cancellation", False)),
        "has_cause_codes": bool(probed.get("has_cause_codes", False)),
        "static": c.static,
        "role": {"events": "primary series", "calendar": "annotations", "reference": "annotations / join hub",
                 "weather": "context annotations or channels", "infrastructure": "annotations", "other": "slide only"}.get(c.kind, "unknown"),
        "notes": c.notes,
        "filled_by": "metadata+probe",
    }
    cmd = os.environ.get("DISCOVER_LLM")
    if cmd:
        try:
            proposed = json.loads(subprocess.run(cmd, shell=True, input=json.dumps(c.as_dict()), capture_output=True, text=True, timeout=60).stdout)  # noqa: S602
            # The model may add prose; booleans that disagree with the probe are overruled.
            for k in ("notes", "role"):
                if isinstance(proposed.get(k), str):
                    r[k] = proposed[k]
            for k in ("has_actual_times", "has_cancellation", "has_cause_codes"):
                if k in proposed and bool(proposed[k]) != r[k] and probed.get("probed"):
                    r[f"{k}_llm_overruled"] = bool(proposed[k])
            r["filled_by"] = "llm+probe"
        except Exception as exc:  # noqa: BLE001
            r["llm_error"] = str(exc)[:120]
    return r
