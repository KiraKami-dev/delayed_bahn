"""The agentic retrieval loop, end to end: search, assess, probe (v1) then fetch and dilute (new).

    OPENAI_API_KEY=... python -m discover.run_v2 --out discover/results_v2 --months 1 --rows-per-month 400000

Stages 1-3 are run.py unchanged: registries searched with agent-proposed queries, deterministic
gates, live probes, agent relevance and schema maps verified by code. Stage 4 (acquire.py) has
the agent write a retrieval plan per surviving source and code execute it. Stage 5 (reduce.py)
has the agent decide, per fetched table, which columns and rows the training set keeps, and code
verify and apply it. REPORT.md lists every decision with its reason and its measured effect.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from . import acquire, llm, reduce
from .spec import DataSpec

NEED = (
    "Training records for a route-planning TSLM: one record = one service group (train type -> final destination) at one "
    "station on one travel date. Inputs are aggregates over the 7 to 120 days before the travel date: mean departure delay "
    "of the service and of the station, cancellation rate, stop counts (throughput), and shares of delay minutes by IRIS "
    "cause family; target = mean departure delay of that service at that station over the following week. Annotations: "
    "public and school holidays per federal state, station category / federal state / weight, dated works notices, "
    "weather as context. From an events source we need stop-level rows with: event time, station name (and id), train "
    "type, train number or line, final destination, delay minutes, arrival/departure cancellation flags, the ride id and "
    "stop sequence number. Buses are out of scope. Planned vs changed timestamps are the label's ingredients, not inputs."
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="discover/results_v2", type=Path)
    ap.add_argument("--months", type=int, default=1)
    ap.add_argument("--rows-per-month", type=int, default=400_000)
    ap.add_argument("--weather-days", type=int, default=7)
    ap.add_argument("--weather-stations", type=int, default=3)
    ap.add_argument("--skip-search", action="store_true", help="reuse <out>/assessment.json from an earlier run")
    args = ap.parse_args()
    out: Path = args.out; out.mkdir(parents=True, exist_ok=True)
    spec = DataSpec()
    budget = {"max_months": args.months, "max_rows_per_month": args.rows_per_month, "max_weather_days": args.weather_days,
              "max_weather_stations": args.weather_stations}

    if not args.skip_search or not (out / "assessment.json").exists():
        from . import run as v1  # noqa: PLC0415
        sys.argv = ["discover.run", "--out", str(out)]
        v1.main()
    entries = json.loads((out / "assessment.json").read_text())["entries"]
    live = [e for e in entries if e["accepted"] and e.get("probe", {}).get("probed") and acquire.PLAN_SCHEMAS.get(e["id"])]
    print(f"\nacquire: {len(live)} sources have a live probe and an executor: {[e['id'] for e in live]}")

    acquisition = []
    data_dir = out / "data"
    for e in live:
        rec = {"id": e["id"], "kind": e.get("kind")}
        plan = acquire.plan_for(e, NEED, spec.window, budget)
        if not plan:
            rec["status"] = "no plan (agent unavailable or failed)"; acquisition.append(rec); print(f"  {e['id']}: {rec['status']}"); continue
        problems = acquire.validate_plan(e, plan, spec.window, budget)
        rec["first_plan"], rec["first_plan_problems"] = plan, problems
        if problems:
            plan = acquire.plan_for(e, NEED, spec.window, budget, problems) or {}
            problems = acquire.validate_plan(e, plan, spec.window, budget) if plan else ["no second plan"]
            rec["second_plan"], rec["second_plan_problems"] = plan, problems
        if problems:
            rec["status"] = f"skipped: plan rejected twice ({'; '.join(problems)[:200]})"; acquisition.append(rec); print(f"  {e['id']}: {rec['status']}"); continue
        try:
            rec["manifest"] = acquire.execute(e, plan, data_dir / e["id"].replace(":", "_").replace("/", "_"))
            rec["status"] = "fetched"
            m = rec["manifest"]; print(f"  {e['id']}: fetched {m['rows']} rows x {m['columns']} cols, {m['bytes']/1e6:.1f} MB in {m['seconds']}s")
        except Exception as exc:  # noqa: BLE001
            rec["status"] = f"fetch failed: {str(exc)[:200]}"; print(f"  {e['id']}: {rec['status']}")
        acquisition.append(rec)
    (out / "acquisition.json").write_text(json.dumps(acquisition, indent=2, ensure_ascii=False, default=str))

    reduction = []
    for rec in acquisition:
        if rec.get("status") != "fetched": continue
        path = Path(rec["manifest"]["path"]); kind = rec["kind"] if rec["kind"] in reduce.ROLES else "reference"
        prof = reduce.profile_table(path)
        prop = reduce.propose(rec["id"], kind, NEED, prof)
        r = {"id": rec["id"], "kind": kind, "profile": prof}
        if not prop:
            r["status"] = "no proposal"; reduction.append(r); continue
        problems = reduce.verify(prop, kind, prof, path)
        r["first_proposal"], r["first_problems"] = prop, problems
        if problems:
            prop = reduce.propose(rec["id"], kind, NEED, prof, problems) or {}
            problems = reduce.verify(prop, kind, prof, path) if prop else ["no second proposal"]
            r["second_proposal"], r["second_problems"] = prop, problems
        if problems:
            r["status"] = f"kept whole: proposal rejected twice ({'; '.join(problems)[:200]})"; reduction.append(r)
            print(f"  {rec['id']}: {r['status']}"); continue
        r["applied"] = reduce.apply(path, prop, out / "reduced" / path.name)
        r["status"] = "reduced"
        a = r["applied"]
        print(f"  {rec['id']}: {a['rows_before']}->{a['rows_after']} rows, {a['columns_before']}->{a['columns_after']} cols, "
              f"{a['bytes_before']/1e6:.1f}->{a['bytes_after']/1e6:.1f} MB; dropped {[d['column'] for d in a['dropped']]}")
        reduction.append(r)
    (out / "reduction.json").write_text(json.dumps(reduction, indent=2, ensure_ascii=False, default=str))
    (out / "agent_log.json").write_text(json.dumps(llm.LOG, indent=2, ensure_ascii=False))

    lines = ["# Agentic retrieval, run of record (v2)", "",
             f"Generated {dt.datetime.now(dt.UTC):%Y-%m-%d %H:%M} UTC. Agent: {llm.MODEL if llm.available() else 'none'}, {len(llm.LOG)} calls in total "
             f"(search, assessment, schema maps, retrieval plans, reductions). Budget: {json.dumps(budget)}.", "",
             "## Stage 4: what the agent chose to fetch, and what code did with it", "",
             "| source | plan (agent) | verifier | fetched |", "|---|---|---|---|"]
    for rec in acquisition:
        plan = rec.get("second_plan") or rec.get("first_plan") or {}
        ver = "accepted first plan" if not rec.get("first_plan_problems") else ("accepted after re-prompt: " + "; ".join(rec["first_plan_problems"])[:120] if rec.get("status") == "fetched" else "rejected twice")
        m = rec.get("manifest"); got = f"{m['rows']} rows x {m['columns']} cols, {m['bytes']/1e6:.1f} MB, {m['seconds']}s" if m else rec.get("status", "")
        lines.append(f"| `{rec['id']}` | {json.dumps({k: v for k, v in plan.items() if k != 'reasoning'}, ensure_ascii=False)[:220]} — {plan.get('reasoning', '')[:160]} | {ver} | {got} |")
    lines += ["", "## Stage 5: how the agent diluted each table, and the measured effect", ""]
    for r in reduction:
        lines.append(f"### `{r['id']}`"); lines.append("")
        a = r.get("applied")
        if not a:
            lines.append(f"{r.get('status')}"); lines.append(""); continue
        lines.append(f"{a['rows_before']:,} -> {a['rows_after']:,} rows, {a['columns_before']} -> {a['columns_after']} columns, "
                     f"{a['bytes_before']/1e6:.1f} -> {a['bytes_after']/1e6:.1f} MB. Roles: {json.dumps(a['roles'], ensure_ascii=False)}")
        lines.append(""); lines.append(f"Agent's reasoning: {a['reasoning'][:500]}"); lines.append("")
        if a.get("normalisation"):
            lines.append("Code normalised the proposal without changing its substance: " + "; ".join(a["normalisation"])[:400]); lines.append("")
        if a["dropped"]:
            lines += ["| dropped column | agent's reason |", "|---|---|"] + [f"| `{d['column']}` | {d.get('reason', '')[:160]} |" for d in a["dropped"]] + [""]
        if a["filters"]:
            lines += ["| row filter | agent's reason | rows it removes alone |", "|---|---|---:|"] + [f"| `{f['sql'][:90]}` | {f['reason'][:140]} | {f['rows_removed_alone']:,} |" for f in a["filters"]] + [""]
        if r.get("first_problems"):
            lines.append(f"Verifier objected to the first proposal: {'; '.join(r['first_problems'])[:300]}"); lines.append("")
    (out / "REPORT.md").write_text("\n".join(lines) + "\n")
    print(f"\nwrote {out}/acquisition.json, reduction.json, REPORT.md, agent_log.json ({len(llm.LOG)} agent calls)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
