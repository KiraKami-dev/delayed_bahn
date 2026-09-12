"""Choose the travel dates each entity is trained on.

An anchor is a **travel date**, not a cursor into a file. The sample is "on the
day before this anchor, predict how late this train will be at this stop over
the next ``HORIZON_DAYS``", so the anchor splits time into a context that ends
at the anchor and a horizon that starts the day after. Nothing here knows what
a profile is: ``profiles.HORIZON_DAYS``, ``ANCHOR_STRIDE_DAYS`` and
``RECENCY_HALF_LIFE_DAYS`` are read from the frozen contract and the same
anchors are handed to S, M, L and XM. If the anchors differed the bake-off
would not be a controlled comparison.

**How many anchors per entity, and why five.**

Repeated anchors on the same entity are not independent samples -- the same
platform, the same junction, the same timetable. Under the usual
exchangeable-within-cluster model with intra-entity correlation rho, M
observations of one entity carry ``M / (1 + (M-1) rho)`` effective samples, so
the M-th anchor is worth roughly ``1 / (1 + (M-1) rho)^2`` of a fresh entity.
With the measured pair-level rho ~ 0.20:

    M =  1   1.00 effective   (20% of the asymptote)
    M =  5   2.78 effective   (56%)
    M = 10   3.57 effective   (71%)
    M = 20   4.17 effective   (83%)
    M -> inf 5.00 effective   -- the asymptote is 1/rho, whatever M you pick

That asymptote is the whole argument. Beyond 1/rho = 5 effective samples per
entity there is nothing left to buy, so the question is only how cheaply to get
most of it. M=5 captures 56% at a quarter of the anchors M=20 needs, and the
budget freed goes into *more entities*, where the returns are still linear.

**Why the window start is staggered per entity.**

Two things are wanted at once and they pull opposite ways. Per entity the
anchors should sit close together, because a short per-entity span means the
five anchors describe one timetable regime and the design effect stays near the
1.8 the arithmetic above assumes. Across the corpus the anchors should cover
every week available, or the model only ever sees one season. Staggering
resolves it: each entity gets a deterministic offset from a hash of its id, so
its own span stays ``(M-1) * ANCHOR_GAP_DAYS`` while the *union* over thousands
of entities tiles the whole archive. The offset is a hash rather than a draw
because the corpus has to be reproducible from the entity list alone.

**Why the gap is 35 and not 30.**

30 days apart is the requirement; 35 is 30 rounded up onto the
``ANCHOR_STRIDE_DAYS`` = 7 grid. Staying on the grid means every anchor of an
entity falls on the same weekday, so the five horizons are the same seven
weekdays and the five samples differ by date rather than by which days of the
week they happen to contain. The weekday itself is then set per entity by
``index mod 7``, which spreads the corpus evenly over all seven weekdays.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from entities import Entity, content_hash, read_entities, stable_digest
from profiles import (
    ANCHOR_STRIDE_DAYS,
    HORIZON_DAYS,
    RECENCY_HALF_LIFE_DAYS,
    TimelineProfile,
    profile,
)

# --- the design -------------------------------------------------------------

M_ANCHORS = 5
# Intra-entity correlation of the pair-level delay series. Sets the asymptote
# 1/rho = 5 effective samples per entity that fixes M above.
PAIR_AUTOCORRELATION = 0.20
MIN_ANCHOR_GAP_DAYS = 30
# 30 rounded up onto the stride grid. See the module docstring.
ANCHOR_GAP_DAYS = ANCHOR_STRIDE_DAYS * math.ceil(MIN_ANCHOR_GAP_DAYS / ANCHOR_STRIDE_DAYS)

# Oversampling ceiling for the recency weight. 4 makes the freshest anchor
# appear four times and one two half-lives (180 days) old appear once, a 4:1
# ratio. Higher and the newest weeks' idiosyncrasies -- one storm, one closure
# -- start to dominate the gradient; lower and the weighting does nothing that
# a 0.5-vs-1.0 loss weight would not do more cheaply.
REPEAT_MAX = 4

# Fractions of *anchors*, not of calendar: the splits are quantiles of the
# anchor date distribution, so a thin stretch of archive does not become a
# disproportionate test set.
DEFAULT_SPLITS: tuple[float, float, float] = (0.70, 0.15, 0.15)

# Purge at each split boundary. HORIZON_DAYS is the honest minimum: it
# guarantees no label observation is shared between two splits. It does NOT
# remove context overlap -- a test sample looking back `context_days` sees days
# that were training labels -- and no purge short of the full context length
# would, which at SEASON's 120 days would cost more anchors than the test set
# contains. Pass `purge_days=prof.context_days` to buy that if it matters.
PURGE_DAYS = HORIZON_DAYS

# Fraction of entities held out in "both" mode, kept separate from `splits`.
#
# The two axes multiply: holding out 15% of dates and 15% of entities leaves 2.2%
# of the corpus in the both-disjoint cell, which measured at 294 anchors -- fine
# for an MAE (standard error ~0.35 min at sd 6) but only ~82 late events, and
# calibration wants several hundred. Widening the entity axis alone buys the cell
# back without touching the date boundary or the purge.
ENTITY_HOLDOUT = 0.30

SPLITS: tuple[str, ...] = ("train", "val", "test")
EVAL_SPLITS: frozenset[str] = frozenset({"val", "test"})


@dataclass(frozen=True)
class Anchor:
    """One (entity, travel date) training sample, before its label exists."""

    anchor_id: str
    entity_id: str
    anchor: dt.date
    index: int  # 0..M-1 within this entity, in date order
    horizon_start: dt.date
    horizon_end: dt.date
    split: str
    age_days: int
    weight: float
    repeat: int

    def as_dict(self) -> dict:
        return {
            "anchor_id": self.anchor_id,
            "entity_id": self.entity_id,
            "anchor": self.anchor.isoformat(),
            "index": self.index,
            "horizon_start": self.horizon_start.isoformat(),
            "horizon_end": self.horizon_end.isoformat(),
            "split": self.split,
            "age_days": self.age_days,
            "weight": round(self.weight, 6),
            "repeat": self.repeat,
        }


def anchor_id(entity_id: str, anchor: dt.date) -> str:
    """Named from its source keys, so the id is a fact about the sample."""
    return f"{entity_id}@{anchor.isoformat()}"


def horizon_of(anchor: dt.date, horizon_days: int = HORIZON_DAYS) -> tuple[dt.date, dt.date]:
    """``[anchor+1, anchor+horizon_days]``.

    The anchor day itself belongs to the *context*: on the evening of the anchor
    a traveller has seen that day's running and is asking about the week ahead.
    Putting the anchor day in the horizon instead would put a day the context
    already contains into the label, which is a leak so small it would never
    show up in a metric and never be found.
    """
    return anchor + dt.timedelta(days=1), anchor + dt.timedelta(days=horizon_days)


def recency_weight(
    anchor: dt.date, reference: dt.date, half_life_days: float = RECENCY_HALF_LIFE_DAYS
) -> float:
    """``0.5 ** (age_days / half_life)``. Exactly 0.5 at one half-life.

    Age is clamped at zero. Under a temporal split the reference is the end of
    the *training* period (see ``plan_anchors``), so val and test anchors sit
    after it and would otherwise weigh more than 1.0 -- an eval sample counting
    for more than a fresh training sample is meaningless, and their repeat is 1
    regardless.
    """
    age = max((reference - anchor).days, 0)
    return 0.5 ** (age / half_life_days)


def repeat_count(weight: float, split: str, repeat_max: int = REPEAT_MAX) -> int:
    """Oversampling multiplicity for the train split; always 1 for val/test.

    Eval anchors are never oversampled, and this is not a detail. Reweighting a
    held-out set makes the metric a function of the weighting scheme: MAE over a
    recency-weighted test set improves when you shorten the half-life, and that
    improvement is not a model getting better. The eval set has to answer "how
    wrong is this model on the dates we held out", one date one vote. The
    ``weight`` field is still emitted for eval anchors so an analysis can slice
    by recency after the fact -- it just must not reach the sampler.
    """
    if split in EVAL_SPLITS:
        return 1
    return max(1, round(weight * repeat_max))


# --- placement --------------------------------------------------------------


def anchor_window(
    prof: TimelineProfile, archive_start: dt.date, archive_end: dt.date
) -> tuple[dt.date, dt.date]:
    """First and last legal anchor date for a profile over an archive range.

    The first anchor needs a full context behind it and the last needs a full
    horizon ahead of it, so the usable band is the archive minus
    ``context_days + HORIZON_DAYS``. For XM over the 2025-11-02 expansion that
    is 120 + 7 days of the archive spent before a single sample exists, which is
    the cost profiles.SEASON's docstring is weighing when it picks 120 over 180.
    """
    first = archive_start + dt.timedelta(days=math.ceil(prof.context_days) - 1)
    last = archive_end - dt.timedelta(days=HORIZON_DAYS)
    if first > last:
        raise ValueError(
            f"archive {archive_start}..{archive_end} is shorter than profile {prof.profile_id} "
            f"needs: {prof.context_days:.0f}d context + {HORIZON_DAYS}d horizon"
        )
    return first, last


def _entity_anchor_dates(
    entity_id: str,
    corpus_index: int,
    window: tuple[dt.date, dt.date],
    m: int,
    gap_days: int,
) -> list[dt.date]:
    """The m anchor dates for one entity: staggered start, fixed weekday, fixed gap."""
    window_start, window_end = window
    span = (window_end - window_start).days
    # Reserve the weekday shift (0..6) and the entity's own span before deciding
    # how many whole weeks of stagger are available.
    weekday_shift = corpus_index % ANCHOR_STRIDE_DAYS
    required = (m - 1) * gap_days
    slack = span - required - (ANCHOR_STRIDE_DAYS - 1)
    if slack < 0:
        # Not enough archive for m anchors at this gap. Drop anchors rather than
        # shrink the gap: a 3-anchor entity is honest, a 5-anchor entity whose
        # anchors are 12 days apart is five near-copies wearing a design effect
        # the arithmetic above does not cover.
        m = max(1, span // gap_days + 1)
        required = (m - 1) * gap_days
        slack = max(0, span - required - (ANCHOR_STRIDE_DAYS - 1))
    weeks = slack // ANCHOR_STRIDE_DAYS
    offset_weeks = stable_digest(entity_id) % (weeks + 1)
    start = window_start + dt.timedelta(days=offset_weeks * ANCHOR_STRIDE_DAYS + weekday_shift)
    return [start + dt.timedelta(days=k * gap_days) for k in range(m)]


def _quantile_cuts(dates: Sequence[dt.date], splits: tuple[float, float, float]) -> tuple[dt.date, dt.date]:
    ordered = sorted(dates)
    n = len(ordered)
    val_cut = ordered[min(n - 1, int(round(splits[0] * n)))]
    test_cut = ordered[min(n - 1, int(round((splits[0] + splits[1]) * n)))]
    return val_cut, test_cut


def plan_anchors(
    entities: Sequence[Entity] | Sequence[str],
    *,
    window: tuple[dt.date, dt.date],
    m: int = M_ANCHORS,
    gap_days: int = ANCHOR_GAP_DAYS,
    horizon_days: int = HORIZON_DAYS,
    reference: dt.date | None = None,
    splits: tuple[float, float, float] = DEFAULT_SPLITS,
    split_mode: str = "temporal",
    entity_holdout: float = ENTITY_HOLDOUT,
    purge_days: int = PURGE_DAYS,
    half_life_days: float = RECENCY_HALF_LIFE_DAYS,
    repeat_max: int = REPEAT_MAX,
) -> list[Anchor]:
    """Every (entity, anchor) in the corpus, split, weighted and purged.

    ``split_mode`` is ``"temporal"`` by default: the held-out cells are later
    travel dates than the training ones, because the deployed question is
    "predict next week" and a random split would let the model interpolate a
    week it has already seen either side of. ``"entity"`` splits by entity
    instead -- generalisation to a stop event never trained on, which is a
    different and easier-to-cheat question, offered only because the bake-off
    may want both.

    Anchor dates are placed before splitting, so the split boundary falls where
    the anchors are dense rather than where the calendar happens to be.

    ``reference`` -- the date recency is measured back from -- defaults to the
    **last training anchor**, not to the end of the archive, and that is not a
    detail either. Under a temporal split every training anchor is older than
    every eval anchor by construction, so measuring age from the archive end
    downweights the whole training set uniformly: over a 15-month window the
    freshest training anchor is already ~136 days old, ``0.5 ** (136/90) * 4``
    rounds to 1, and every repeat count collapses to 1. The weighting would then
    be doing nothing while appearing to be configured. Measured from the end of
    the training period it does what it is for -- tilting training toward the
    network as it most recently ran.
    """
    if split_mode not in ("temporal", "entity", "both"):
        raise ValueError(f"unknown split_mode {split_mode!r}")
    if abs(sum(splits) - 1.0) > 1e-9:
        raise ValueError(f"splits must sum to 1.0, got {splits}")
    if not 0.0 < entity_holdout < 1.0:
        raise ValueError(f"entity_holdout must be in (0, 1), got {entity_holdout}")

    ids = [e.entity_id if isinstance(e, Entity) else str(e) for e in entities]
    ids = sorted(set(ids))

    placed: list[tuple[str, int, dt.date]] = []
    for corpus_index, eid in enumerate(ids):
        for index, date in enumerate(
            _entity_anchor_dates(eid, corpus_index, window, m, gap_days)
        ):
            placed.append((eid, index, date))

    if split_mode == "temporal":
        val_cut, test_cut = _quantile_cuts([d for _, _, d in placed], splits)

        def split_of(eid: str, date: dt.date) -> str:
            return "train" if date < val_cut else ("val" if date < test_cut else "test")

        def purged(eid: str, date: dt.date, split: str) -> bool:
            # An earlier split's anchor is dropped when its horizon, plus the
            # purge margin, reaches the next boundary.
            horizon_end = date + dt.timedelta(days=horizon_days)
            cut = val_cut if split == "train" else (test_cut if split == "val" else None)
            return cut is not None and horizon_end + dt.timedelta(days=purge_days) >= cut
    elif split_mode == "both":
        # The 2x2 that separates the three ways this model can overfit.
        #
        # A date holdout alone catches a model that memorised the calendar. It
        # does NOT catch one that memorised the trains: a service's base delay is
        # stable across a time boundary, so "the 07:42 is four minutes down at
        # Pasing" scores just as well next month as last. That model looks
        # excellent on a temporal split and collapses in deployment.
        #
        # So hold out both axes and report four cells. `test` is the honest one
        # (unseen train AND later date); the gap between `test_seen_entity` and
        # `test` is the memorisation estimate, and publishing it is what makes
        # the headline number believable.
        val_cut, test_cut = _quantile_cuts([d for _, _, d in placed], splits)
        n = len(ids)
        held_at = int(round((1.0 - entity_holdout) * n))
        rank = {eid: i for i, eid in enumerate(sorted(ids, key=stable_digest))}
        entity_held = {eid for eid, i in rank.items() if i >= held_at}

        def split_of(eid: str, date: dt.date) -> str:
            late = date >= test_cut
            unseen = eid in entity_held
            if not late and not unseen:
                return "train" if date < val_cut else "val"
            if late and not unseen:
                return "test_seen_entity"  # cell A: temporal generalisation
            if not late and unseen:
                return "test_seen_time"  # cell B: route generalisation
            return "test"  # cell C: both held out -- the production number

        def purged(eid: str, date: dt.date, split: str) -> bool:
            # Only the training cells need purging: a held-out entity shares no
            # label with training whatever its date, so the date boundary is the
            # only place a horizon can leak across.
            if split not in ("train", "val"):
                return False
            horizon_end = date + dt.timedelta(days=horizon_days)
            cut = val_cut if split == "train" else test_cut
            return horizon_end + dt.timedelta(days=purge_days) >= cut
    else:
        n = len(ids)
        val_at = int(round(splits[0] * n))
        test_at = int(round((splits[0] + splits[1]) * n))
        # Ranked by digest, not by position: the entity list is sorted by id, and
        # ids begin with the station slug, so slicing it positionally would put
        # whole stations in one split.
        rank = {eid: i for i, eid in enumerate(sorted(ids, key=stable_digest))}

        def split_of(eid: str, date: dt.date) -> str:
            i = rank[eid]
            return "train" if i < val_at else ("val" if i < test_at else "test")

        def purged(eid: str, date: dt.date, split: str) -> bool:
            return False

    kept = [
        (eid, index, date, split_of(eid, date))
        for eid, index, date in placed
        if not purged(eid, date, split_of(eid, date))
    ]
    if reference is None:
        train_dates = [date for _, _, date, split in kept if split == "train"]
        reference = max(train_dates) if train_dates else window[1]

    anchors: list[Anchor] = []
    for eid, index, date, split in kept:
        horizon_start, horizon_end = horizon_of(date, horizon_days)
        weight = recency_weight(date, reference, half_life_days)
        anchors.append(
            Anchor(
                anchor_id=anchor_id(eid, date),
                entity_id=eid,
                anchor=date,
                index=index,
                horizon_start=horizon_start,
                horizon_end=horizon_end,
                split=split,
                age_days=max((reference - date).days, 0),
                weight=weight,
                repeat=repeat_count(weight, split, repeat_max),
            )
        )
    anchors.sort(key=lambda a: (a.entity_id, a.anchor))
    return anchors


# --- emission ---------------------------------------------------------------


def anchors_manifest(anchors: Sequence[Anchor], *, provenance: dict | None = None) -> dict:
    """The anchors.json payload, content-hashed over everything but the hash."""
    by_split: dict[str, int] = {}
    repeats: dict[str, int] = {}
    weekdays: dict[int, int] = {}
    for anchor in anchors:
        by_split[anchor.split] = by_split.get(anchor.split, 0) + 1
        repeats[anchor.split] = repeats.get(anchor.split, 0) + anchor.repeat
        weekdays[anchor.anchor.weekday()] = weekdays.get(anchor.anchor.weekday(), 0) + 1
    dates = [a.anchor for a in anchors]
    payload: dict = {
        "schema": "db_route/anchors/1",
        "provenance": provenance or {},
        "design": {
            "m_anchors": M_ANCHORS,
            "min_anchor_gap_days": MIN_ANCHOR_GAP_DAYS,
            "anchor_gap_days": ANCHOR_GAP_DAYS,
            "horizon_days": HORIZON_DAYS,
            "anchor_stride_days": ANCHOR_STRIDE_DAYS,
            "recency_half_life_days": RECENCY_HALF_LIFE_DAYS,
            "repeat_max": REPEAT_MAX,
            "purge_days": PURGE_DAYS,
            # Recoverable from any anchor: date + age_days. Emitted so a reader
            # of anchors.json does not have to reconstruct which end of the
            # training period the weights were measured from.
            "recency_reference": (
                max(
                    (a.anchor + dt.timedelta(days=a.age_days) for a in anchors),
                    default=None,
                ).isoformat()
                if anchors
                else None
            ),
            "pair_autocorrelation": PAIR_AUTOCORRELATION,
            "effective_samples_per_entity": round(
                M_ANCHORS / (1 + (M_ANCHORS - 1) * PAIR_AUTOCORRELATION), 3
            ),
        },
        "counts": {
            "entities": len({a.entity_id for a in anchors}),
            "anchors": len(anchors),
            "by_split": dict(sorted(by_split.items())),
            "train_rows_after_repeat": repeats.get("train", 0),
            "by_weekday": {str(k): v for k, v in sorted(weekdays.items())},
            "first_anchor": min(dates).isoformat() if dates else None,
            "last_anchor": max(dates).isoformat() if dates else None,
        },
        "anchors": [a.as_dict() for a in anchors],
    }
    payload["content_hash"] = content_hash(payload)
    return payload


def write_anchors(path: Path, manifest: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return path


def read_anchors(path: Path) -> list[Anchor]:
    manifest = json.loads(path.read_text())
    return [
        Anchor(
            anchor_id=row["anchor_id"],
            entity_id=row["entity_id"],
            anchor=dt.date.fromisoformat(row["anchor"]),
            index=row["index"],
            horizon_start=dt.date.fromisoformat(row["horizon_start"]),
            horizon_end=dt.date.fromisoformat(row["horizon_end"]),
            split=row["split"],
            age_days=row["age_days"],
            weight=row["weight"],
            repeat=row["repeat"],
        )
        for row in manifest["anchors"]
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan db_route anchors.")
    parser.add_argument("--entities", type=Path, default=None, help="entities.json")
    parser.add_argument("--profile", default="XM", help="profile whose context sets the window")
    parser.add_argument("--archive-start", required=True)
    parser.add_argument("--archive-end", required=True)
    parser.add_argument("--cache", default=Path("~/.cache/db_route").expanduser(), type=Path)
    parser.add_argument("--out", default=None, type=Path)
    parser.add_argument("--split-mode", default="temporal", choices=("temporal", "entity"))
    parser.add_argument("--curated", action="store_true", help="use only the curated subset")
    args = parser.parse_args(argv)

    entities_path = args.entities or (args.cache / "entities.json")
    manifest = json.loads(entities_path.read_text())
    entities = read_entities(entities_path)
    if args.curated:
        keep = set(manifest.get("curation", {}).get("entity_ids", []))
        if not keep:
            parser.error(f"{entities_path} carries no curation block")
        entities = [e for e in entities if e.entity_id in keep]

    prof = profile(args.profile)
    window = anchor_window(
        prof, dt.date.fromisoformat(args.archive_start), dt.date.fromisoformat(args.archive_end)
    )
    anchors = plan_anchors(entities, window=window, split_mode=args.split_mode)
    out = args.out or (args.cache / "anchors.json")
    payload = anchors_manifest(
        anchors,
        provenance={
            "entities": str(entities_path),
            "entities_content_hash": manifest.get("content_hash"),
            "curated_only": bool(args.curated),
            "profile": prof.profile_id,
            "context_days": prof.context_days,
            "archive": [args.archive_start, args.archive_end],
            "anchor_window": [window[0].isoformat(), window[1].isoformat()],
            "split_mode": args.split_mode,
        },
    )
    write_anchors(out, payload)
    print(
        f"anchors: {payload['counts']['anchors']:,} over "
        f"{payload['counts']['entities']:,} entities "
        f"{payload['counts']['by_split']}, "
        f"{payload['counts']['train_rows_after_repeat']:,} train rows after repeat "
        f"-> {out} ({payload['content_hash'][:12]})",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
