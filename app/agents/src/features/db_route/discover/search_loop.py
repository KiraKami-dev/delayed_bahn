"""v3: a closed loop over dataset variants, scored by a cheap proxy on held-out validation.

The agent proposes a variant of the training set (which series channels to keep) with a stated
hypothesis; code builds the variant's feature table from the registry, fits gradient boosting
(the proxy that tracked the TSLM within 0.05 min on every cell today) on the training split and
scores CRPS on validation; the agent reads the result against the noise floor and proposes the
next. Stops when a proposal cannot beat the incumbent by more than the noise floor, or after
--rounds. Only validation is used for selection; the test cells are scored once, for the winner.

    python -m discover.search_loop --registry <dir> --profile quarter --rounds 5 --out discover/results_v3
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from . import llm

NOISE_FLOOR = 0.02  # CRPS spread between three seeds of the same recipe on the same rows (13 Sep 2026)
LEAKY = {"attributed_share", "artifact_bundle_sha", "split", "split_cell", "recency_weight"}
LEVELS = np.array([0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95])


def crps(y: np.ndarray, q: np.ndarray) -> float:
    """Pinball loss averaged over the 19 quantile levels: the same proper score the runs report."""
    d = y[:, None] - q
    return float(np.mean(np.maximum(LEVELS * d, (LEVELS - 1) * d)) * 2)


def load(registry: str, profile: str, bridge):
    from timenet.client import TimeNet  # noqa: PLC0415

    ds = TimeNet(registry).load(f"error404/db-route-{profile}")
    keys = sorted({k for r in ds.records for k, v in bridge.annotation_map(r).items()
                   if isinstance(v, (int, float)) and not isinstance(v, bool) and k not in LEAKY})
    rows = []
    for r in ds.records:
        ann = bridge.annotation_map(r)
        y = next((float(t.target) for t in ds.tasks_for(r) if type(t).__name__ == "ScalarPredictionTask"), None)
        if y is None:
            continue
        series = {t.signal: np.asarray(t.to_numpy(), dtype=float) for t in r.time_series}
        rows.append({"id": str(r.record_id), "split": ann.get("split"), "cell": ann.get("split_cell", ann.get("split")), "y": y,
                     "scalars": [float(ann[k]) if isinstance(ann.get(k), (int, float)) else np.nan for k in keys], "series": series})
    signals = sorted({s for row in rows for s in row["series"]})
    return rows, keys, signals


def features(rows: list[dict], keep: list[str]) -> np.ndarray:
    out = []
    for row in rows:
        f = list(row["scalars"])
        for s in keep:
            v = row["series"].get(s)
            f += [np.nanmean(v), np.nanstd(v), float(v[-1]), np.nanmax(v)] if v is not None and v.size else [np.nan] * 4
        out.append(f)
    return np.array(out, dtype=float)


def score(rows: list[dict], keep: list[str], cells: tuple[str, ...] = ("val",)) -> dict:
    from sklearn.ensemble import HistGradientBoostingRegressor as HGB  # noqa: PLC0415

    tr = [r for r in rows if r["split"] == "train"]
    Xt, yt = features(tr, keep), np.array([r["y"] for r in tr])
    ok = np.array([np.isfinite(Xt[:, j]).any() and np.nanstd(Xt[:, j]) > 0 for j in range(Xt.shape[1])])
    Xt = Xt[:, ok]
    models = {lv: HGB(loss="quantile", quantile=lv, max_iter=200, max_depth=6, learning_rate=0.05, random_state=0).fit(Xt, yt) for lv in LEVELS}
    out = {}
    for cell in cells:
        rs = [r for r in rows if r["cell"] == cell]
        X, y = features(rs, keep)[:, ok], np.array([r["y"] for r in rs])
        Q = np.sort(np.stack([models[lv].predict(X) for lv in LEVELS], axis=1), axis=1)
        out[cell] = {"n": len(rs), "crps": round(crps(y, Q), 4), "median_error": round(float(np.abs(Q[:, 9] - y).mean()), 4),
                     "coverage_10_90": round(float(((y >= Q[:, 1]) & (y <= Q[:, 17])).mean()), 3)}
    return out


def propose(signals: list[str], history: list[dict], need: str) -> dict | None:
    system = ("You are searching for the best training-set variant for a train-delay forecasting model. A variant is the "
              "list of series channels to KEEP (all others are dropped). Reply with one JSON object: "
              '{"keep": [channels], "hypothesis": "one sentence on why this should beat the incumbent", "stop": false}. '
              "Set stop=true with an explanation in 'hypothesis' if you believe no variant can beat the incumbent by more "
              "than the noise floor. Propose exactly one variant per round; do not repeat a tried variant.")
    user = (f"Need: {need}\nChannels available: {signals}\nNoise floor (CRPS): {NOISE_FLOOR}\n"
            f"Rounds so far (lower CRPS is better; the first row is the incumbent with every channel):\n"
            + "\n".join(json.dumps({k: h[k] for k in ("round", "keep", "hypothesis", "val")}, ensure_ascii=False) for h in history))
    return llm.chat("dataset variant", system, user, max_tokens=500)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", required=True)
    ap.add_argument("--profile", default="quarter")
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--out", default="discover/results_v3", type=Path)
    args = ap.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import bridge  # noqa: PLC0415

    args.out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    rows, keys, signals = load(args.registry, args.profile, bridge)
    print(f"loaded {len(rows)} scalar rows, {len(keys)} scalar annotations, {len(signals)} channels in {time.time() - t0:.0f}s", flush=True)
    need = ("Forecast next week's mean departure delay of a service group at a station from 60 days of six-hourly history "
            "(the quarter profile) plus calendar and station annotations; scored by CRPS on held-out validation.")
    history = []
    base = score(rows, signals)
    history.append({"round": 0, "keep": signals, "hypothesis": "incumbent: every channel", "val": base["val"], "accepted": True})
    best = history[0]
    print(f"round 0 incumbent: val CRPS {base['val']['crps']} (all {len(signals)} channels)", flush=True)
    for rnd in range(1, args.rounds + 1):
        prop = propose(signals, history, need) if llm.available() else None
        if not prop:
            print("agent unavailable or failed; stopping", flush=True); break
        if prop.get("stop"):
            history.append({"round": rnd, "keep": None, "hypothesis": prop.get("hypothesis", ""), "val": None, "accepted": False, "stop": True})
            print(f"round {rnd}: agent stops: {prop.get('hypothesis', '')[:160]}", flush=True); break
        keep = [s for s in prop.get("keep") or [] if s in signals]
        if not keep or any(keep == h["keep"] for h in history):
            history.append({"round": rnd, "keep": keep, "hypothesis": prop.get("hypothesis", ""), "val": None, "accepted": False,
                            "note": "empty or repeated variant, not scored"}); continue
        res = score(rows, keep)
        gain = best["val"]["crps"] - res["val"]["crps"]
        accepted = gain > NOISE_FLOOR
        h = {"round": rnd, "keep": keep, "hypothesis": prop.get("hypothesis", ""), "val": res["val"], "gain_vs_incumbent": round(gain, 4), "accepted": accepted}
        history.append(h)
        print(f"round {rnd}: keep {len(keep)}/{len(signals)} -> val CRPS {res['val']['crps']} (gain {gain:+.4f}, {'ACCEPTED' if accepted else 'rejected'}) | {h['hypothesis'][:120]}", flush=True)
        if accepted:
            best = h
    final = score(rows, best["keep"], ("val", "test_seen_entity", "test", "test_seen_time"))
    result = {"profile": args.profile, "registry": args.registry, "noise_floor": NOISE_FLOOR, "channels": signals, "history": history,
              "winner": {"keep": best["keep"], "dropped": [s for s in signals if s not in best["keep"]], "scores": final},
              "agent": {"model": llm.MODEL if llm.available() else None, "calls": len(llm.LOG)}}
    (args.out / "search.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    (args.out / "agent_log_search.json").write_text(json.dumps(llm.LOG, indent=2, ensure_ascii=False))
    lines = ["# Dataset variant search (v3)", "", f"Profile {args.profile}, proxy = gradient boosting on per-channel summaries + annotations, "
             f"selection on validation CRPS only, noise floor {NOISE_FLOOR}. Agent: {result['agent']['model']}, {result['agent']['calls']} calls.", "",
             "| round | channels kept | hypothesis (agent) | val CRPS | gain | verdict |", "|---|---|---|---|---|---|"]
    for h in history:
        v = h.get("val") or {}
        lines.append(f"| {h['round']} | {len(h['keep']) if h.get('keep') else '-'} | {h['hypothesis'][:140]} | {v.get('crps', '')} | {h.get('gain_vs_incumbent', '')} | "
                     f"{'stop' if h.get('stop') else 'accepted' if h.get('accepted') else h.get('note', 'rejected')} |")
    lines += ["", f"Winner keeps {len(best['keep'])} of {len(signals)} channels; dropped: {result['winner']['dropped']}", "",
              "| cell | n | median error | CRPS | coverage 10-90 |", "|---|---:|---|---|---|"]
    for c, s in final.items():
        lines.append(f"| {c} | {s['n']} | {s['median_error']:.3f} | {s['crps']:.3f} | {s['coverage_10_90']:.2f} |")
    (args.out / "SEARCH.md").write_text("\n".join(lines) + "\n")
    print(f"wrote {args.out}/search.json, SEARCH.md; winner drops {result['winner']['dropped']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
