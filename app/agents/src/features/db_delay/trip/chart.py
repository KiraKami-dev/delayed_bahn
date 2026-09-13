"""One chart for the pitch: CRPS by lead time, our model next to the baselines, as an SVG.

Reads saved predictions (the npz files written by train.py, baselines.py, combine.py or
apply_blend.py), scores them on the examples they share, and draws grouped bars per lead-time
bucket plus the overall score. No plotting library; the SVG is written directly so it renders
anywhere, in both light and dark pages.

    python trip/chart.py --examples data/trip/forward_v4.parquet \\
        --model "XGBoost=out/trip/baselines_v3f/xgboost_forward.npz" \\
        --model "TSLM=out/trip/ablations/v4-text_forward/tslm_test.npz" \\
        --title "September 2026, 10,000 trips the models never saw" --out out/trip/chart_september.svg
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

import metrics  # noqa: E402
from combine import COLUMNS, aligned, load  # noqa: E402

GROUPS = ["overall", "lead <=15 min", "lead 15-30 min", "lead 30-60 min", "lead 60-120 min", "lead >120 min"]
LABELS = ["all trips", "up to 15 min", "15 to 30 min", "30 to 60 min", "1 to 2 h", "over 2 h"]
PALETTE = ["#8A93A6", "#0F5FA8", "#1F7A45", "#B06A00", "#B23A2C"]
LEFT, TOP, WIDTH, HEIGHT = 56, 64, 760, 300


def scores(examples: pd.DataFrame, models: dict[str, Path]) -> tuple[dict[str, dict[str, float]], dict[str, int], int]:
    """CRPS per group for every model on the examples all of them scored, with group sizes."""
    preds = {name: load(path) for name, path in models.items()}
    ids = None
    for pred in preds.values():
        ids = set(pred["example_id"].tolist()) if ids is None else ids & set(pred["example_id"].tolist())
    ids = np.array(sorted(ids))
    frame = examples.set_index("example_id").loc[ids].reset_index()
    out, sizes = {}, {}
    for name, pred in preds.items():
        arrays = aligned(pred, ids)
        result = metrics.evaluate(frame, arrays["quantiles"], arrays["p_cancel"], arrays["p_late"])
        out[name] = {group: result[group]["crps"] for group in GROUPS if group in result}
        sizes = {group: int(result[group]["n"]) for group in GROUPS if group in result}
    return out, sizes, len(ids)


def svg(crps: dict[str, dict[str, float]], sizes: dict[str, int], n: int, title: str, subtitle: str) -> str:
    """Grouped bars: one group per lead bucket, one bar per model, value labels on top."""
    names = list(crps)
    top = max(v for row in crps.values() for v in row.values())
    ymax = float(np.ceil(top * 1.15 * 2) / 2)
    group_w = WIDTH / len(GROUPS)
    bar_w = min(34, (group_w - 24) / len(names))
    y_of = lambda v: TOP + HEIGHT - v / ymax * HEIGHT  # noqa: E731
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {LEFT + WIDTH + 24} {TOP + HEIGHT + 104}" '
             f'font-family="IBM Plex Sans, Helvetica Neue, Arial, sans-serif" font-size="13">',
             f'<text x="{LEFT}" y="26" font-size="19" font-weight="600" fill="currentColor">{title}</text>',
             f'<text x="{LEFT}" y="46" fill="currentColor" opacity="0.7">{subtitle}</text>']
    tick = 0.5 if ymax <= 4 else 1.0
    for value in np.arange(0, ymax + 1e-9, tick):
        y = y_of(value)
        parts.append(f'<line x1="{LEFT}" y1="{y:.1f}" x2="{LEFT + WIDTH}" y2="{y:.1f}" stroke="currentColor" opacity="0.15"/>')
        parts.append(f'<text x="{LEFT - 8}" y="{y + 4:.1f}" text-anchor="end" fill="currentColor" opacity="0.7">{value:g}</text>')
    parts.append(f'<text x="{LEFT - 44}" y="{TOP + HEIGHT / 2:.1f}" transform="rotate(-90 {LEFT - 44} {TOP + HEIGHT / 2:.1f})" '
                 f'text-anchor="middle" fill="currentColor" opacity="0.7">CRPS in minutes (lower is better)</text>')
    for g, (group, label) in enumerate(zip(GROUPS, LABELS)):
        x0 = LEFT + g * group_w + (group_w - bar_w * len(names)) / 2
        for m, name in enumerate(names):
            value = crps[name].get(group)
            if value is None:
                continue
            x = x0 + m * bar_w
            parts.append(f'<rect x="{x:.1f}" y="{y_of(value):.1f}" width="{bar_w - 3:.1f}" height="{TOP + HEIGHT - y_of(value):.1f}" '
                         f'fill="{PALETTE[m % len(PALETTE)]}"/>')
            parts.append(f'<text x="{x + (bar_w - 3) / 2:.1f}" y="{y_of(value) - 5:.1f}" text-anchor="middle" font-size="11" '
                         f'fill="currentColor">{value:.2f}</text>')
        cx = LEFT + g * group_w + group_w / 2
        parts.append(f'<text x="{cx:.1f}" y="{TOP + HEIGHT + 20}" text-anchor="middle" fill="currentColor">{label}</text>')
        parts.append(f'<text x="{cx:.1f}" y="{TOP + HEIGHT + 36}" text-anchor="middle" font-size="11" fill="currentColor" opacity="0.6">'
                     f'{sizes.get(group, 0):,} trips</text>')
    parts.append(f'<text x="{LEFT + WIDTH / 2:.1f}" y="{TOP + HEIGHT + 56}" text-anchor="middle" fill="currentColor" opacity="0.7">'
                 f'minutes before the planned arrival when the forecast was made</text>')
    x = LEFT
    for m, name in enumerate(names):
        parts.append(f'<rect x="{x}" y="{TOP + HEIGHT + 70}" width="12" height="12" fill="{PALETTE[m % len(PALETTE)]}"/>')
        parts.append(f'<text x="{x + 18}" y="{TOP + HEIGHT + 81}" fill="currentColor">{name}</text>')
        x += 18 + 7 * len(name) + 24
    parts.append("</svg>")
    return "\n".join(parts)


def svg_relative(crps: dict[str, dict[str, float]], sizes: dict[str, int], n: int, title: str, subtitle: str) -> str:
    """Bars of CRPS difference to the first model per lead bucket; a bar above the line is a gain."""
    names = list(crps)
    base = crps[names[0]]
    diffs = {name: {g: crps[name][g] - base[g] for g in GROUPS if g in crps[name] and g in base} for name in names[1:]}
    span = max(abs(v) for row in diffs.values() for v in row.values()) or 0.1
    lim = float(np.ceil(span * 1.25 * 20) / 20)
    group_w = WIDTH / len(GROUPS)
    bar_w = min(40, (group_w - 24) / max(1, len(diffs)))
    zero = TOP + HEIGHT / 2
    y_of = lambda v: zero + v / lim * HEIGHT / 2  # noqa: E731
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {LEFT + WIDTH + 24} {TOP + HEIGHT + 104}" '
             f'font-family="IBM Plex Sans, Helvetica Neue, Arial, sans-serif" font-size="13">',
             f'<text x="{LEFT}" y="26" font-size="19" font-weight="600" fill="currentColor">{title}</text>',
             f'<text x="{LEFT}" y="46" fill="currentColor" opacity="0.7">{subtitle}</text>']
    tick = 0.05 if lim <= 0.3 else 0.1
    for value in np.arange(-lim, lim + 1e-9, tick):
        y = y_of(value)
        parts.append(f'<line x1="{LEFT}" y1="{y:.1f}" x2="{LEFT + WIDTH}" y2="{y:.1f}" stroke="currentColor" opacity="0.15"/>')
        parts.append(f'<text x="{LEFT - 8}" y="{y + 4:.1f}" text-anchor="end" fill="currentColor" opacity="0.7">{value:+.2f}</text>')
    parts.append(f'<line x1="{LEFT}" y1="{zero:.1f}" x2="{LEFT + WIDTH}" y2="{zero:.1f}" stroke="currentColor" stroke-width="1.5"/>')
    parts.append(f'<text x="{LEFT + 4}" y="{zero + 14:.1f}" font-size="11" fill="currentColor" opacity="0.7">{names[0]} = 0</text>')
    parts.append(f'<text x="{LEFT - 44}" y="{TOP + HEIGHT / 2:.1f}" transform="rotate(-90 {LEFT - 44} {TOP + HEIGHT / 2:.1f})" '
                 f'text-anchor="middle" fill="currentColor" opacity="0.7">CRPS minus {names[0]} (above the line is better)</text>')
    for g, (group, label) in enumerate(zip(GROUPS, LABELS)):
        x0 = LEFT + g * group_w + (group_w - bar_w * len(diffs)) / 2
        for m, name in enumerate(diffs):
            value = diffs[name].get(group)
            if value is None:
                continue
            x, y = x0 + m * bar_w, y_of(value)
            top_y, height = (min(zero, y), abs(y - zero))
            parts.append(f'<rect x="{x:.1f}" y="{top_y:.1f}" width="{bar_w - 3:.1f}" height="{height:.1f}" '
                         f'fill="{PALETTE[(m + 1) % len(PALETTE)]}"/>')
            label_y = y + 14 if value > 0 else y - 5
            parts.append(f'<text x="{x + (bar_w - 3) / 2:.1f}" y="{label_y:.1f}" text-anchor="middle" font-size="11" '
                         f'fill="currentColor">{value:+.3f}</text>')
        cx = LEFT + g * group_w + group_w / 2
        parts.append(f'<text x="{cx:.1f}" y="{TOP + HEIGHT + 20}" text-anchor="middle" fill="currentColor">{label}</text>')
        parts.append(f'<text x="{cx:.1f}" y="{TOP + HEIGHT + 36}" text-anchor="middle" font-size="11" fill="currentColor" opacity="0.6">'
                     f'{sizes.get(group, 0):,} trips</text>')
        parts.append(f'<text x="{cx:.1f}" y="{TOP + HEIGHT + 50}" text-anchor="middle" font-size="11" fill="currentColor" opacity="0.6">'
                     f'{names[0]} {base.get(group, float("nan")):.2f}</text>')
    parts.append(f'<text x="{LEFT + WIDTH / 2:.1f}" y="{TOP + HEIGHT + 68}" text-anchor="middle" fill="currentColor" opacity="0.7">'
                 f'minutes before the planned arrival when the forecast was made</text>')
    x = LEFT
    for m, name in enumerate(diffs):
        parts.append(f'<rect x="{x}" y="{TOP + HEIGHT + 80}" width="12" height="12" fill="{PALETTE[(m + 1) % len(PALETTE)]}"/>')
        parts.append(f'<text x="{x + 18}" y="{TOP + HEIGHT + 91}" fill="currentColor">{name}</text>')
        x += 18 + 7 * len(name) + 24
    parts.append("</svg>")
    return "\n".join(parts)


def main() -> None:
    """Score, draw, write the SVG and the numbers behind it."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--examples", default="data/trip/examples.parquet")
    parser.add_argument("--model", action="append", required=True, help="name=path/to/predictions.npz, in drawing order")
    parser.add_argument("--title", default="Arrival-delay forecasts by lead time")
    parser.add_argument("--out", default="out/trip/chart.svg")
    parser.add_argument("--relative", action="store_true", help="draw differences to the first model instead of levels")
    args = parser.parse_args()

    models = {name: Path(path) for name, path in (item.split("=", 1) for item in args.model)}
    examples = pd.read_parquet(args.examples, columns=COLUMNS)
    crps, sizes, n = scores(examples, models)
    subtitle = f"{n:,} trips scored by every model; CRPS over the trips that ran"
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    draw = svg_relative if args.relative else svg
    out.write_text(draw(crps, sizes, n, args.title, subtitle))
    out.with_suffix(".json").write_text(json.dumps({"n": n, "sizes": sizes, "crps": crps}, indent=2))
    for name, row in crps.items():
        print(name, {g: round(v, 3) for g, v in row.items()})
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
