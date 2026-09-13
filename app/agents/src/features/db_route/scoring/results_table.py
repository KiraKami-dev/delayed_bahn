"""Markdown table of every scored run: tag, profile, steps, cell, n, TSLM, GBM, persistence, blend, coverage."""
import json, sys
from pathlib import Path
SC = Path(__file__).parent
rows = []
for bl in sorted((SC / "runs").glob("*/*/baselines_local.json")):
    tag, profile = bl.parts[-3], bl.parts[-2]
    m = json.loads((bl.parent / "metrics.json").read_text()) if (bl.parent / "metrics.json").exists() else {}
    steps = m.get("steps") or (m.get("args") or {}).get("steps") or ""
    if m.get("kind") == "blend": continue
    args = m.get("args") or {}
    variant = ("plain" if args.get("loss_mode") == "plain" else "") + (" caption-only" if args.get("caption_only") else "") + \
              (" six-region" if "six" in str(args.get("registry", "")) else "") + (" lr x2" if args.get("lr") == 2e-4 else "") + \
              (f" seed {args.get('seed')}" if args.get("seed") not in (None, 0) else "")
    d = json.loads(bl.read_text())
    for cell in ("val", "test_seen_entity", "test", "test_seen_time"):
        r = d.get(cell)
        if not r: continue
        rows.append((tag, profile, steps, variant.strip(), cell, r["n"], r["tslm"]["median_error"], r["tslm"]["crps"], r["tslm"].get("coverage_10_90"),
                     r["gbm"]["median_error"], r["gbm"]["crps"], (r.get("persistence") or {}).get("median_error"),
                     r.get("blend", {}).get("median_error"), r.get("blend", {}).get("crps"), r.get("blend", {}).get("w_tslm")))
cells = sys.argv[1:] or ["test", "test_seen_entity"]
print("| run | profile | steps | variant | cell | n | TSLM | cov | GBM | persist | blend (w) |")
print("|---|---|---:|---|---|---:|---|---:|---|---:|---|")
for t, p, s, v, c, n, tm, tc, cov, gm, gc, pe, bm, bc, w in rows:
    if c not in cells: continue
    f = lambda a, b: f"{a:.2f} / {b:.2f}" if a is not None and b is not None else ""
    print(f"| {t} | {p} | {s} | {v} | {c} | {n} | {f(tm, tc)} | {cov:.2f} | {f(gm, gc)} | {pe:.2f} | {f(bm, bc)} ({w:.2f}) |")
