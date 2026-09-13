"""The agent in the loop. An LLM proposes queries, relevance, rubric fields and column maps; code verifies.

OpenAI chat completions over urllib (no SDK), JSON mode, low temperature. Every call is logged
(model, purpose, prompt digest, usage) into ``LOG`` so the run can show what the agent was asked
and what it answered. With no ``OPENAI_API_KEY`` every function returns ``None`` and the pipeline
falls back to metadata and the probe.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.request

MODEL = os.environ.get("DISCOVER_LLM_MODEL", "gpt-4o-mini")
LOG: list[dict] = []

_SCOUT = ("You are a data scout for a hackathon team fine-tuning a time-series language model on German "
          "rail delays. The team already has an archive of Deutsche Bahn per-stop events (Nov 2025 - Aug 2026, "
          "all stations). You look for OPEN, machine-readable, no-registration sources that add information "
          "for that window: cause codes, disruption notices, weather, holidays, infrastructure, station reference "
          "data, or comparable rail archives. Answer JSON only.")


def available() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def chat(purpose: str, system: str, user: str, *, max_tokens: int = 600) -> dict | None:
    if not available():
        return None
    body = {"model": MODEL, "temperature": 0.2, "max_tokens": max_tokens, "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310
                out = json.loads(r.read().decode())
            content = out["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            LOG.append({"purpose": purpose, "model": MODEL, "prompt_sha": hashlib.sha256((system + user).encode()).hexdigest()[:12],
                        "usage": out.get("usage"), "answer": parsed})
            return parsed
        except Exception as exc:  # noqa: BLE001
            if attempt == 1:
                LOG.append({"purpose": purpose, "model": MODEL, "error": str(exc)[:160]})
                return None
            time.sleep(2)
    return None


def propose_queries(window: tuple, needs: str) -> dict[str, list[str]] | None:
    """Search terms per registry, from the spec. The scout unions these with its fixed list."""
    user = (f"Data window: {window[0]} to {window[1]}. Needs: {needs}. Registries: 'huggingface' (English dataset "
            f"search), 'govdata' (German federal open-data CKAN; German terms work best), 'zenodo' (research data). "
            f"Return {{\"huggingface\": [..], \"govdata\": [..], \"zenodo\": [..]}} with up to 6 short search strings each, "
            f"specific enough to avoid unrelated hits.")
    ans = chat("propose_queries", _SCOUT, user)
    if not ans:
        return None
    return {k: [str(q) for q in ans.get(k, [])][:6] for k in ("huggingface", "govdata", "zenodo")}


def assess(candidate: dict, probe: dict | None, window: tuple) -> dict | None:
    """Relevance and the rubric, proposed. The caller overrules every boolean the probe contradicts."""
    user = (f"Candidate: {json.dumps(candidate, ensure_ascii=False)[:1800]}\n"
            f"Probe (measured, trust over metadata): {json.dumps(probe or {}, ensure_ascii=False)[:1200]}\n"
            f"Our window: {window[0]}..{window[1]}. Return JSON: relevant (bool: does it add information for German rail "
            f"delay prediction in that window?), role (one of 'primary series','annotations','join hub','context channels',"
            f"'slide only','not useful'), covers_window (bool|null), has_actual_times (bool|null), has_cancellation (bool|null), "
            f"has_cause_codes (bool|null), resolution (string), confidence (0-1), reasoning (<=50 words).")
    return chat("assess", _SCOUT, user)


def map_schema(source_id: str, columns: list[tuple[str, str]]) -> dict | None:
    """Propose which columns play which role. Verified against the real column list by the caller."""
    user = (f"Source {source_id} has these columns (name, type): {json.dumps(columns)}. Map our roles to column names "
            f"or null: timestamp (event time), entity_id (unique stop event), station, value (delay in minutes), "
            f"cancellation_flag, line_id, sequence_index (stop number within a run), cause_code, planned_time, "
            f"changed_time. Return JSON with those keys plus reasoning (<=40 words).")
    return chat("map_schema", "You map dataset columns to a fixed schema for a rail-delay pipeline. Answer JSON only.", user)


def verify_schema(proposed: dict, columns: list[tuple[str, str]]) -> dict:
    """Deterministic check of a proposed map: every named column must exist, and typed roles must have plausible types."""
    names = {c for c, _ in columns}
    types = dict(columns)
    problems = []
    for role in ("timestamp", "entity_id", "station", "value", "cancellation_flag", "line_id", "sequence_index", "cause_code", "planned_time", "changed_time"):
        col = proposed.get(role)
        if col is None:
            continue
        if col not in names:
            problems.append(f"{role}: column {col!r} does not exist")
            continue
        t = types[col].upper()
        if role in ("timestamp", "planned_time", "changed_time") and "TIME" not in t and "DATE" not in t:
            problems.append(f"{role}: {col!r} is {t}, not a timestamp")
        if role == "value" and not any(k in t for k in ("INT", "DOUBLE", "FLOAT", "DECIMAL")):
            problems.append(f"value: {col!r} is {t}, not numeric")
        if role == "cancellation_flag" and "BOOL" not in t and "INT" not in t:
            problems.append(f"cancellation_flag: {col!r} is {t}, not boolean")
    return {"verified": not problems, "problems": problems}
