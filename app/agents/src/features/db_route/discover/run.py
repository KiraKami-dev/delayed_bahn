"""Run the retrieval pipeline's search, assess and probe tiers and write the artifacts.

    python -m discover.run --out data/discover
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from . import llm
from .gates import gate
from .probe import probe
from .rubric import rubric
from .scout import NEEDS, scout
from .spec import DataSpec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/discover", type=Path)
    args = ap.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    spec = DataSpec()

    proposed_queries = llm.propose_queries(spec.window, NEEDS) if llm.available() else None
    if proposed_queries:
        print("agent proposed queries:", json.dumps(proposed_queries, ensure_ascii=False)[:400])
    cands = scout(spec, proposed_queries)
    (out / "candidates.jsonl").write_text("\n".join(json.dumps(c.as_dict(), ensure_ascii=False) for c in cands) + "\n")
    print(f"scout: {len(cands)} candidates ({sum(c.registry == 'known' for c in cands)} known, "
          f"{sum(c.registry == 'huggingface' for c in cands)} huggingface, {sum(c.registry == 'govdata' for c in cands)} govdata, "
          f"{sum(c.registry == 'zenodo' for c in cands)} zenodo)")

    assessment = []
    for c in cands:
        ok, reason = gate(c, spec)
        entry = {"id": c.id, "title": c.title, "registry": c.registry, "accepted": ok, "reason": reason, "licence": c.licence, "kind": c.kind}
        if ok:
            p = probe(c)
            entry["probe"] = p
            entry["rubric"] = rubric(c, p)
            if llm.available():
                # The agent judges relevance and fills the rubric; the probe overrules any boolean it contradicts.
                verdict = llm.assess(c.as_dict(), p if p.get("probed") else None, spec.window)
                if verdict:
                    overruled = {k: verdict[k] for k in ("has_actual_times", "has_cancellation", "has_cause_codes")
                                 if p.get("probed") and k in verdict and verdict[k] is not None and bool(verdict[k]) != bool(p.get(k, False))}
                    entry["agent"] = {"proposed": verdict, "overruled_by_probe": overruled}
                    if verdict.get("relevant") is False:
                        entry["accepted"] = False
                        entry["reason"] = f"agent judged not relevant: {verdict.get('reasoning', '')[:120]}"
                    elif isinstance(verdict.get("role"), str):
                        entry["rubric"]["role"] = verdict["role"]
                        entry["rubric"]["filled_by"] = "agent+probe"
                if entry["accepted"] and p.get("columns_typed"):
                    proposal = llm.map_schema(c.id, p["columns_typed"])
                    if proposal:
                        entry["schema_map"] = {"proposed": proposal, **llm.verify_schema(proposal, [tuple(x) for x in p["columns_typed"]])}
            if p.get("probed") is False and "error" in p:
                entry["accepted"] = False
                entry["reason"] = f"probe failed: {p['error']}"
            elif reason.startswith("temporal coverage not stated"):
                months = p.get("per_month") or {}
                if months:
                    entry["reason"] = f"coverage measured by probe: {min(months)}..{max(months)} present"
                else:
                    entry["accepted"] = False
                    entry["reason"] = "temporal coverage not stated and no probe could measure it"
        assessment.append(entry)
    (out / "assessment.json").write_text(json.dumps({"generated": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                                                     "window": [d.isoformat() for d in spec.window], "agent": {"model": llm.MODEL if llm.available() else None,
                                                     "proposed_queries": proposed_queries, "calls": len(llm.LOG)}, "entries": assessment}, indent=2, ensure_ascii=False))
    (out / "agent_log.json").write_text(json.dumps(llm.LOG, indent=2, ensure_ascii=False))

    acc = [e for e in assessment if e["accepted"]]
    rej = [e for e in assessment if not e["accepted"]]
    probed = [e for e in acc if e.get("probe", {}).get("probed")]
    meta_only = [e for e in acc if not e.get("probe", {}).get("probed")]
    lines = ["# Source assessment", "", f"Generated {dt.datetime.now(dt.UTC):%Y-%m-%d %H:%M} UTC over window {spec.window[0]}..{spec.window[1]}. "
             f"{len(cands)} candidates from four registries (known list, HuggingFace, govdata CKAN, Zenodo); {len(acc)} passed every gate "
             f"({len(probed)} probed live, {len(meta_only)} accepted on metadata only and not used), {len(rej)} rejected. "
             "Every verdict is a deterministic predicate; the reason is the first gate that failed.", "",
             "## Accepted and probed live", "", "| source | kind | licence | role | what the probe measured |", "|---|---|---|---|---|"]
    for e in probed:
        p = e.get("probe", {}); r = e.get("rubric", {})
        summary = {k: v for k, v in p.items() if k in ("per_month", "coverage_step", "stations", "hourly_rows_one_week", "school_periods_BY", "public_holidays_BY", "size_mb", "n_columns", "has_actual_times", "has_cancellation")}
        lines.append(f"| `{e['id']}` | {e['kind']} | {e['licence']} | {r.get('role', '')} | {json.dumps(summary, ensure_ascii=False)[:200]} |")
    lines += ["", "## Accepted on metadata only (open licence, machine-readable, reference data) — candidates, not used", "", "| source | licence | formats |", "|---|---|---|"]
    for e in meta_only:
        lines.append(f"| `{e['id']}` — {e['title'][:70]} | {e['licence']} | {next((c.format for c in cands if c.id == e['id']), '')} |")
    lines += ["", "## Rejected", "", "| source | registry | reason |", "|---|---|---|"]
    for e in rej:
        lines.append(f"| `{e['id']}` — {e['title'][:60]} | {e['registry']} | {e['reason']} |")
    (out / "REJECTIONS.md").write_text("\n".join(lines) + "\n")
    print(f"assess: {len(acc)} accepted, {len(rej)} rejected -> {out}/assessment.json, {out}/REJECTIONS.md")
    for e in acc:
        sm = e.get("schema_map")
        print(f"  ACCEPT {e['id']:42} {e['kind']:15} {e.get('rubric', {}).get('role', '')}"
              + (f"  schema map {'verified' if sm['verified'] else 'REJECTED: ' + '; '.join(sm['problems'])}" if sm else ""))
    if llm.available():
        print(f"agent: {llm.MODEL}, {len(llm.LOG)} calls, {sum(1 for e in assessment if e.get('agent'))} candidates assessed, "
              f"{sum(1 for e in assessment if e.get('reason', '').startswith('agent judged'))} rejected by the agent")
    from collections import Counter
    for reason, n in Counter(e["reason"].split(":")[0] for e in rej).most_common():
        print(f"  reject x{n:<3} {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
