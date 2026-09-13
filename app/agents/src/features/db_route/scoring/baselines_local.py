"""Persistence and XGBoost on exactly the rows a training job scored, from the saved npz + registry."""
import json, re, sys, collections
import numpy as np
from pathlib import Path
SC = Path(__file__).resolve().parent  # expects ./runs/<tag>/<profile>/ and ./registry_allde beside this file
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "db_delay" / "trip"))
import bridge, metrics
from timenet.client import TimeNet
from sklearn.ensemble import HistGradientBoostingRegressor as HGB
profile = sys.argv[1]
RUN_TAG = sys.argv[2] if len(sys.argv) > 2 else "route-2k"
LEAKY = {"attributed_share", "artifact_bundle_sha", "split", "split_cell", "recency_weight"}
ds = TimeNet(str(SC / "registry_allde")).load(f"error404/db-route-{profile}")
keys = sorted({k for r in ds.records for k, v in bridge.annotation_map(r).items() if isinstance(v, (int, float)) and not isinstance(v, bool) and k not in LEAKY})
feat, y_all, split, cell, own = {}, {}, {}, {}, {}
for r in ds.records:
    ann = bridge.annotation_map(r)
    # The entity's own context series, finest layer first: this service at this station if the
    # profile carries it, else this service group across its stops. Its context mean is the
    # persistence forecast ("the habit"); its values are the route-history distribution.
    by_sig = {t.signal: np.asarray(t.to_numpy(), dtype=float) for t in r.time_series}
    for name in ("service_at_station_delay", "service_delay"):
        cands = [k for k in by_sig if k.endswith("/" + name)]
        if cands:
            lay = {"week": 0, "quarter": 1, "season": 2}
            own[r.record_id] = by_sig[sorted(cands, key=lambda k: lay.get(k.split("/")[0], 9))[0]]
            break
    # Series summaries straight from the registry: level, spread, most recent value and peak of
    # every channel -- the same information the model reads through its captions and encoder.
    stats = []
    for ts in sorted(r.time_series, key=lambda t: t.signal):
        v = np.asarray(ts.to_numpy(), dtype=float)
        stats += [float(np.nanmean(v)), float(np.nanstd(v)), float(v[-1]), float(np.nanmax(v))] if v.size else [np.nan] * 4
    feat[r.record_id] = [float(ann[k]) if isinstance(ann.get(k), (int, float)) else np.nan for k in keys] + stats
    for t in ds.tasks_for(r):
        if type(t).__name__ == "ScalarPredictionTask": y_all[r.record_id] = float(t.target)
    split[r.record_id] = ann.get("split"); cell[r.record_id] = ann.get("split_cell")
n_feat = max(len(v) for v in feat.values())
X = lambda ids: np.array([feat[i] + [np.nan] * (n_feat - len(feat[i])) for i in ids])
train_ids = [i for i in y_all if split[i] == "train"]
Xt, Yt = X(train_ids), np.array([y_all[i] for i in train_ids])
# drop columns that are all-NaN or constant on train: sklearn's binner chokes on them
keep = np.array([np.nanstd(Xt[:, j]) > 0 if np.isfinite(Xt[:, j]).any() else False for j in range(Xt.shape[1])])
print(f"features kept {int(keep.sum())}/{len(keep)} (dropped all-NaN/constant)")
_X = X
X = lambda ids: _X(ids)[:, keep]
Xt = Xt[:, keep]
med = HGB(loss="absolute_error", max_iter=400, max_depth=6, learning_rate=0.05, random_state=0).fit(Xt, Yt)
qm = {lv: HGB(loss="quantile", quantile=lv, max_iter=300, max_depth=6, learning_rate=0.05, random_state=0).fit(Xt, Yt) for lv in (0.05,0.1,0.15,0.2,0.25,0.3,0.35,0.4,0.45,0.5,0.55,0.6,0.65,0.7,0.75,0.8,0.85,0.9,0.95)}
hidx = None
if "habit_median_delay_8w" in keys:
    j = keys.index("habit_median_delay_8w")
    hidx = int(np.cumsum(keep)[j] - 1) if keep[j] else None
out = {}
run = SC / "runs" / RUN_TAG / profile
for npz in sorted(run.glob("scalar_*.npz")):
    c = npz.stem.replace("scalar_", ""); d = np.load(npz, allow_pickle=True)
    ids = [str(i) for i in d["record_id"]]; y = d["y"].astype(float); q = d["quantiles"].astype(float)
    Xc = X(ids); res = {"n": len(ids)}
    res["tslm"] = {"median_error": float(np.abs(q[:, 9] - y).mean()), "crps": float(metrics.crps_from_quantiles(y, q).mean()), "coverage_10_90": float(((y >= q[:, 1]) & (y <= q[:, 17])).mean())}
    pred = med.predict(Xc); Q = np.stack([qm[lv].predict(Xc) for lv in sorted(qm)], axis=1); Q = np.sort(Q, axis=1)
    res["gbm"] = {"median_error": float(np.abs(pred - y).mean()), "crps": float(metrics.crps_from_quantiles(y, Q).mean()), "coverage_10_90": float(((y >= Q[:, 1]) & (y <= Q[:, 17])).mean())}
    if hidx is not None:
        h = Xc[:, hidx]; ok = ~np.isnan(h)
        res["persistence_habit"] = {"median_error": float(np.abs(h[ok] - y[ok]).mean()), "n": int(ok.sum())}
    # Persistence from the series themselves (the habit annotation is never filled by the
    # pipeline, so the job's own persistence row is silently empty -- found by Jonas's review).
    if all(i in own for i in ids):
        hm = np.array([np.nanmean(own[i]) if np.isfinite(own[i]).any() else np.nan for i in ids])
        ok = ~np.isnan(hm)
        res["persistence"] = {"median_error": float(np.abs(hm[ok] - y[ok]).mean()), "crps": float(np.abs(hm[ok] - y[ok]).mean()),
                              "n": int(ok.sum()), "note": "context mean of the entity's own delay series; point forecast so CRPS = MAE"}
        lv = np.array([0.05,0.1,0.15,0.2,0.25,0.3,0.35,0.4,0.45,0.5,0.55,0.6,0.65,0.7,0.75,0.8,0.85,0.9,0.95])
        Qh = np.array([np.nanquantile(own[i], lv) if np.isfinite(own[i]).sum() > 1 else np.full(19, np.nan) for i in ids])
        okq = np.isfinite(Qh).all(axis=1)
        res["route_history"] = {"median_error": float(np.abs(Qh[okq, 9] - y[okq]).mean()), "crps": float(metrics.crps_from_quantiles(y[okq], Qh[okq]).mean()),
                                "coverage_10_90": float(((y[okq] >= Qh[okq, 1]) & (y[okq] <= Qh[okq, 17])).mean()), "n": int(okq.sum()),
                                "note": "empirical quantiles of the entity's own context series"}
    res["mean_baseline"] = {"median_error": float(np.abs(np.median(Yt) - y).mean())}
    res["_q"] = {"y": y, "tslm": q, "gbm": Q, "record_id": np.array(ids)}
    out[c] = res
    print(f"{profile} {c:18} n={len(ids):4}  TSLM {res['tslm']['median_error']:.3f}/{res['tslm']['crps']:.3f}  GBM {res['gbm']['median_error']:.3f}/{res['gbm']['crps']:.3f}  persist {res.get('persistence',{}).get('median_error',float('nan')):.3f}  hist {res.get('route_history',{}).get('median_error',float('nan')):.3f}/{res.get('route_history',{}).get('crps',float('nan')):.3f}  train-median {res['mean_baseline']['median_error']:.3f}   (median error / CRPS, minutes)")
# Blend: one weight on the TSLM quantiles, fitted on val by CRPS, applied everywhere else.
# Jonas's pattern (lead-time blend fitted on validation only); ours has one lead time.
if "val" in out:
    v = out["val"]["_q"]
    ws = np.linspace(0, 1, 21)
    scores = [metrics.crps_from_quantiles(v["y"], np.sort(w * v["tslm"] + (1 - w) * v["gbm"], axis=1)).mean() for w in ws]
    w = float(ws[int(np.argmin(scores))])
    print(f"{profile} blend weight on TSLM (fit on val): {w:.2f}")
    for c, res in out.items():
        d = res["_q"]; Qb = np.sort(w * d["tslm"] + (1 - w) * d["gbm"], axis=1); yb = d["y"]
        res["blend"] = {"w_tslm": w, "median_error": float(np.abs(Qb[:, 9] - yb).mean()), "crps": float(metrics.crps_from_quantiles(yb, Qb).mean()),
                        "coverage_10_90": float(((yb >= Qb[:, 1]) & (yb <= Qb[:, 17])).mean())}
        # Save the blended quantiles in the same shape as the model's scalar_<cell>.npz so a
        # blend can be served by serve_route.py unchanged (make_blend_tag.py).
        np.savez_compressed(run / f"blend_{c}.npz", y=yb, quantiles=Qb, record_id=d["record_id"])
        print(f"{profile} {c:18} BLEND {res['blend']['median_error']:.3f}/{res['blend']['crps']:.3f}  (TSLM {res['tslm']['median_error']:.3f}/{res['tslm']['crps']:.3f}, GBM {res['gbm']['median_error']:.3f}/{res['gbm']['crps']:.3f})")
for res in out.values():
    res.pop("_q", None)
(run / "baselines_local.json").write_text(json.dumps(out, indent=2))
