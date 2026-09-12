"""TimeNet -> OpenTSLM: the path neither project ships.

TimeNet's README is explicit that it "hands you the data and stops there", and
every OpenTSLM dataset class loads its own source from disk -- ``HARCoTQADataset``
reads a CoT parquet, ``SleepEDFCoTQADataset`` reads EDF, ``ECGQACoTQADataset``
reads PTB-XL. There is no class in either tree that takes a TimeF dataset and
yields OpenTSLM training samples. This module is that class.

**Nothing here is rail-specific, and that is a hard requirement.** The module
reads a TimeF ``Record``'s series in order, reads its annotations by key, and
reads the attached ``Task``'s target and rationale. It never mentions a station,
a delay, a timescale or a profile. Point it at any TimeF dataset whose records
carry a ``split`` annotation and whose tasks carry a scalar target, and it emits
OpenTSLM samples. ``validate.py`` is where the rail knowledge lives.

The five keys, each verified against installed OpenTSLM 0.1.0 source
(``opentslm/prompt/prompt_with_answer.py::PromptWithAnswer.to_dict``):

    {"pre_prompt": str, "time_series_text": list[str],
     "time_series": list[1-D array], "post_prompt": str, "answer": str}

and the constraints that turn that dict from "plausible" into "trainable":

* ``TextTimeSeriesPrompt.__init__`` asserts ``ndim == 1``, ``size > 0`` and a
  numeric dtype. Multivariate input is N captioned 1-D series, never one 2-D
  array -- the assert fires before the collate ever sees it.
* The collate (``time_series_datasets/util.py``) pads every series in a sample
  up to a common multiple of ``PATCH_SIZE`` with **zeros and no padding mask**.
  Ragged lengths inside one sample therefore inject fabricated zeros that the
  encoder cannot distinguish from data. ``validate.py`` pins every length to
  ``layer.n_steps``, and ``profiles.py`` keeps each divisible by 4.
* ``TransformerCNNEncoder`` allocates ``max_patches=1024`` positional rows and
  *raises* past them (``"Time series of length {N*4} is too long"``), so 4096
  samples is a wall, not a truncation.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, ClassVar, Iterable, Iterator, Mapping, Sequence

import numpy as np

# --- guarded upstream imports ------------------------------------------------
# Both packages install cleanly (timenet 0.1.0, opentslm 0.1.0, verified), but
# opentslm drags in torch/transformers/open_clip and timenet drags in pyarrow and
# pint. This module is imported by `validate.py` and by tests that only need the
# pure assembly helpers, so a missing heavy dependency must degrade to a clear
# error at *use* time rather than an ImportError at *import* time.

try:  # pragma: no cover - exercised by whichever environment lacks the package
    from opentslm.prompt.text_time_series_prompt import TextTimeSeriesPrompt
    from opentslm.time_series_datasets.QADataset import QADataset as _QADataset

    HAVE_OPENTSLM = True
    OPENTSLM_IMPORT_ERROR: BaseException | None = None
except Exception as exc:  # pragma: no cover
    HAVE_OPENTSLM = False
    OPENTSLM_IMPORT_ERROR = exc

    class TextTimeSeriesPrompt:  # type: ignore[no-redef]
        """Stand-in mirroring OpenTSLM's assertions so shape bugs still surface.

        Deliberately re-implements the four asserts rather than accepting
        anything: a sample that passes here must pass upstream, or the smoke
        test on a machine without torch would be worthless.
        """

        def __init__(self, text: str, time_series: Sequence[float]) -> None:
            assert isinstance(text, str), "Text must be a string!"
            array = np.asarray(time_series)
            assert array.ndim == 1, "Time series must be one-dimensional!"
            assert array.size > 0, "Time series must not be empty!"
            assert np.issubdtype(array.dtype, np.number), (
                "Time series must contain only numeric values!"
            )
            self._text, self._array = text, array

        def get_text(self) -> str:
            return self._text

        def get_time_series(self) -> np.ndarray:
            return self._array

    class _QADataset:  # type: ignore[no-redef]
        """Stand-in base so the subclass below is still importable and inspectable."""

        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            raise ImportError(
                "opentslm is not importable, so a QADataset cannot be instantiated: "
                f"{OPENTSLM_IMPORT_ERROR!r}. The assembly helpers in this module "
                "(build_sample, captioned_series, format_answer) work without it."
            )

try:  # pragma: no cover
    from timenet.client import TimeNet

    HAVE_TIMENET = True
    TIMENET_IMPORT_ERROR: BaseException | None = None
except Exception as exc:  # pragma: no cover
    HAVE_TIMENET = False
    TIMENET_IMPORT_ERROR = exc
    TimeNet = None  # type: ignore[assignment]


# --- the record contract -----------------------------------------------------
# Annotation keys this bridge reads. Every one is optional except SPLIT, and
# every one is a plain string key, so a producer in any domain can satisfy them
# without importing this module.

ANN_SPLIT = "split"
"""Required, record-scoped. One of ``train`` / ``validation`` / ``test``."""

ANN_CAPTION_PREFIX = "caption:"
"""Optional, record-scoped, one per series. See :func:`series_caption`."""

ANN_PRE_PROMPT_CONTEXT = "pre_prompt_context"
"""Optional, record-scoped. A sentence naming *what this record is about*, used
in place of the generic opener. It is the only place a domain gets to say
"this is the 07:41 from Munich Ost" without the bridge knowing what that means."""

SPLIT_ALIASES: Mapping[str, str] = {
    "train": "train",
    "training": "train",
    "validation": "validation",
    "val": "validation",
    "valid": "validation",
    "dev": "validation",
    "test": "test",
    "eval": "test",
}
"""Producers disagree about the middle split's name; OpenTSLM only accepts
``validation``. Normalising here beats an empty validation set that trains fine
and early-stops on nothing."""

SPLITS: tuple[str, str, str] = ("train", "validation", "test")

# --- the caption contract ----------------------------------------------------

MIN_STD = 1e-6
"""Clamp floor for the per-series standard deviation.

Matched to OpenTSLM's own datasets (``HARCoTQADataset`` clamps at 1e-6 and
comments that 1e-8 was not stable enough). A series whose true std is below this
is constant; the clamp stops the division producing NaN, and ``validate.py``
rejects the record outright rather than letting a flat channel train."""

CAPTION_TEMPLATE = "{description}, it has mean {mean:.4f} and std {std:.4f}:"
"""The exact caption shape OpenTSLM's datasets emit, reproduced character for
character (``f"{label}, it has mean {mean:.4f} and std {std:.4f}:"``).

This is not cosmetic. The series handed to the model is z-scored, so its
absolute scale is *gone*: 2 minutes late and 20 minutes late produce byte-identical
tensors. The mean and std in this string are the only surviving channel for
scale. Drift from the template and the model has seen the numbers during
pretraining in a different shape; drop them and the task becomes unanswerable."""

ANSWER_SEPARATOR = " Answer: "
"""OpenTSLM's CoT prompts all end with ``You MUST end your response with
"Answer: "``, and evaluation splits the generation on that literal. The leading
space matters: the rationale's final full stop butts straight up against it."""

MAX_SERIES_SAMPLES = 4096
"""``TransformerCNNEncoder(max_patches=1024)`` x ``PATCH_SIZE=4``. Past this the
encoder raises. Checked here so the failure names the series, not a tensor."""


@dataclass(frozen=True)
class BridgeRow:
    """One training sample's inputs: a record and the one task being asked of it.

    A record with three tasks becomes three rows sharing the same series. That is
    the unit OpenTSLM's ``QADataset`` iterates, and keeping record and task
    together is what lets ``_get_answer`` and ``_get_text_time_series_prompt_list``
    see the same sample without a lookup.
    """

    record: Any
    task: Any

    @property
    def annotations(self) -> Mapping[str, Any]:
        return annotation_map(self.record)


# --- pure assembly helpers ---------------------------------------------------
# Free functions, not methods: `validate.py` re-derives the answer string and the
# captions to check a built dataset, and it must not need a torch import to do it.


def annotation_map(record: Any) -> dict[str, Any]:
    """Record-scoped annotations as ``{key: value}``.

    Only span-less annotations are record-scoped context (TimeNet models an
    interval annotation as the same class with a ``span``), so a dated disruption
    notice attached to the same record never shadows a caption.

    Later duplicates win, matching how a producer would think of an override.
    """
    out: dict[str, Any] = {}
    for annotation in getattr(record, "annotations", ()) or ():
        if getattr(annotation, "span", None) is None:
            out[annotation.key] = annotation.value
    return out


def series_keys(series: Any) -> tuple[str, ...]:
    """Identity keys for one series, most specific first.

    A TimeF ``TimeSeries`` states its identity in three places and a producer may
    use any of them, so the bridge tries all three rather than guessing:

    1. ``time_series_id`` -- an explicit per-series override.
    2. ``{source_id}/{signal}`` -- the two-part form the caption key is spelled
       in (``caption:<layer>/<signal>``). A producer that puts the timescale in
       ``source_id`` lands here.
    3. ``signal`` -- for a producer that already spells the whole thing into the
       signal name (``"week/service_delay"``), or a single-scale dataset where
       the signal alone is unique.
    """
    keys: list[str] = []
    series_id = getattr(series, "time_series_id", None)
    source_id = getattr(series, "source_id", None)
    signal = getattr(series, "signal", "")
    if series_id:
        keys.append(str(series_id))
    if source_id:
        keys.append(f"{source_id}/{signal}")
    if signal:
        keys.append(str(signal))
    return tuple(dict.fromkeys(keys))


def series_caption(series: Any, annotations: Mapping[str, Any]) -> str:
    """The human description for one series -- identity, before scale is appended.

    **This exists because of a defect in the sibling implementation, and it is
    the single most consequential line in the module.** That implementation
    captions from ``spec.name``. A ``TimeSeriesSpec`` is a *measurement modality*
    contract, not a channel name: our records put ``service_delay``,
    ``station_delay`` and ``service_at_station_delay`` on one shared ``delay``
    spec because they are the same kind of measurement in the same unit. Caption
    from ``spec.name`` and all three read "Delay". At the multi-scale profile the
    same signal also appears at three timescales, so ``week/service_delay``,
    ``quarter/service_delay`` and ``season/service_delay`` collapse onto the same
    string as well -- twelve series, four distinct captions.

    That is fatal rather than untidy, because the caption is the *only* thing
    distinguishing series i from series j: the tensors are z-scored, so identical
    captions leave the model with N interchangeable channels and no way to know
    which one the question is about, nor which timescale it is looking at.

    So: read ``caption:<key>`` off the record, most specific key first, and fall
    back to ``spec.name`` only when the producer supplied nothing. The fallback
    keeps the module usable against a dataset that never heard of this
    convention.
    """
    for key in series_keys(series):
        caption = annotations.get(f"{ANN_CAPTION_PREFIX}{key}")
        if caption:
            return str(caption)
    spec = getattr(series, "spec", None)
    name = getattr(spec, "name", None)
    return str(name) if name else str(getattr(series, "signal", "series"))


def series_values(series: Any) -> np.ndarray:
    """One series as a 1-D float64 array.

    ``to_numpy`` raises on nulls by design; the bridge lets that propagate rather
    than filling, because a silently zero-filled gap is exactly the failure the
    imputed-fraction check in ``validate.py`` exists to catch. A spec with a
    ``value_shape`` yields a 2-D array here, and that is an error, not something
    to ravel: OpenTSLM wants N captioned 1-D series, so the producer has to split
    the channels and caption each one.
    """
    values = np.asarray(series.to_numpy())
    if values.ndim != 1:
        raise ValueError(
            f"series {series_keys(series)[0]!r} is {values.ndim}-D with shape "
            f"{values.shape}; OpenTSLM takes N separately captioned 1-D series, "
            f"never one multi-channel array (TextTimeSeriesPrompt asserts ndim == 1)"
        )
    return values.astype(np.float64, copy=False)


def normalize(values: np.ndarray, *, min_std: float = MIN_STD) -> tuple[np.ndarray, float, float]:
    """z-score one series and return ``(normalized, mean, clamped_std)``.

    Normalisation happens **here, in the dataset class**, not in the collate.
    ``extend_time_series_to_match_patch_size_and_aggregate`` does take a
    ``normalize=`` flag, but it defaults to False and the training entry points
    do not set it, so a dataset that leaves raw values in gets raw values to the
    encoder. Every shipped OpenTSLM dataset normalises in ``_get_text_time_series_prompt_list``.

    ``ddof=1`` matches those datasets, which compute the std with ``torch.std``
    (sample) rather than ``np.std`` (population). The difference is 0.3% at
    n=168 and irrelevant to the model, but the caption states a number a human
    will compare against a pandas ``describe()``, so it should be the same
    number. n is always >= 4 here (``profiles.py`` requires n_steps divisible by
    4), but the guard keeps the helper honest for a 1-sample caller.
    """
    mean = float(values.mean())
    std = float(values.std(ddof=1)) if values.size > 1 else 0.0
    std = max(std, min_std)
    return (values - mean) / std, mean, std


def captioned_series(
    record: Any,
    *,
    caption_only: bool = False,
    annotations: Mapping[str, Any] | None = None,
) -> tuple[list[str], list[np.ndarray]]:
    """Every series on a record as aligned ``(captions, arrays)``.

    Alignment is positional and load-bearing -- OpenTSLM zips the two lists and
    never re-checks them -- so both are built in one pass over
    ``record.time_series`` and returned together rather than by two functions a
    caller could call in different orders.

    ``caption_only`` zeroes the arrays and keeps the captions verbatim, including
    the real mean and std. It is the ablation that makes the long-context claim
    falsifiable: if XM still beats S with the shapes removed, the advantage was
    never the shape, only the summary statistics a one-line prompt could have
    carried, and the multi-scale story is dead.
    """
    annotations = annotation_map(record) if annotations is None else annotations
    captions: list[str] = []
    arrays: list[np.ndarray] = []
    for series in record.time_series:
        values = series_values(series)
        if values.size > MAX_SERIES_SAMPLES:
            raise ValueError(
                f"series {series_keys(series)[0]!r} has {values.size} samples, past "
                f"OpenTSLM's {MAX_SERIES_SAMPLES}-sample encoder cap, which raises "
                f"rather than truncating"
            )
        normalized, mean, std = normalize(values)
        captions.append(
            CAPTION_TEMPLATE.format(
                description=series_caption(series, annotations), mean=mean, std=std
            )
        )
        arrays.append(np.zeros_like(normalized) if caption_only else normalized)
    return captions, arrays


def render_target(target: Any) -> str:
    """A task target as the exact string the model must emit.

    Only scalar targets round-trip through a text answer. A forecasting or
    correspondence task answers with a record or a list of ids, which is not a
    string the ``Answer:`` convention can carry, so it is refused here rather
    than stringified into something no metric can score.
    """
    if target is None:
        raise ValueError("task has no target, so there is nothing for the model to answer")
    if isinstance(target, bool):
        return "yes" if target else "no"
    if isinstance(target, (str, int, float)):
        return str(target)
    raise ValueError(
        f"target of type {type(target).__name__} is not a scalar answer; OpenTSLM's "
        f"'Answer: <text>' convention carries strings and numbers only"
    )


def format_answer(rationale: str | None, target: Any, eos_token: str = "") -> str:
    """``rationale + " Answer: " + target + EOS``.

    ``QADataset._format_sample`` appends ``EOS_TOKEN`` itself when the answer does
    not already end with it, then calls ``.strip()`` on the result. Two
    consequences worth stating: appending the EOS here is idempotent and safe,
    and a *whitespace* EOS token (``"\\n"``) is stripped straight back off. If a
    tokenizer's EOS is whitespace, pass ``""`` and let the tokenizer add it.
    """
    body = (rationale or "").strip()
    answer = f"{body}{ANSWER_SEPARATOR}{render_target(target)}"
    return answer if answer.endswith(eos_token) and eos_token else answer + eos_token


def build_sample(
    row: BridgeRow,
    *,
    eos_token: str = "",
    caption_only: bool = False,
    label_options: Sequence[str] = (),
) -> dict[str, Any]:
    """One OpenTSLM training sample: exactly the five keys, in one place.

    The dataset class below delegates to this so the assembly is testable without
    torch, and so ``validate.py`` can re-derive a sample from a record and compare
    it against what was written.
    """
    captions, arrays = captioned_series(row.record, caption_only=caption_only)
    return {
        "pre_prompt": pre_prompt_for(row),
        "time_series_text": captions,
        "time_series": arrays,
        "post_prompt": post_prompt_for(row, label_options),
        "answer": format_answer(getattr(row.task, "rationale", None), row.task.target, eos_token),
    }


# --- prompt construction -----------------------------------------------------

_GENERIC_CONTEXT = (
    "You are given {n} time series drawn from one entity. Each is z-scored, and "
    "the caption above it states the mean and standard deviation it was scaled by, "
    "so absolute magnitudes must be read from the captions rather than the values."
)

_INSTRUCTIONS = (
    "Instructions:\n"
    "- Begin by analysing the series without assuming an answer.\n"
    "- Reason step by step about level, trend, and the alignment between series.\n"
    "- Write your rationale as a single natural paragraph, with no bullet points "
    "or headings.\n"
    "- Cite magnitudes in their original units, reconstructed from the captions.\n"
    "- Do not state the answer until the final sentence."
)


def pre_prompt_for(row: BridgeRow) -> str:
    """Opening context plus the reasoning instructions.

    The context sentence comes from the record's ``pre_prompt_context`` annotation
    when it has one. That single indirection is what keeps this module
    domain-agnostic while still letting the samples say something specific: the
    producer knows the record is an S8 at Munich Ost next Tuesday, the bridge only
    knows it is a record with seven series. Without it the bridge would either
    emit a uselessly generic opener or would have to learn the domain.
    """
    context = row.annotations.get(ANN_PRE_PROMPT_CONTEXT)
    if not context:
        context = _GENERIC_CONTEXT.format(n=len(row.record.time_series))
    question = getattr(row.task, "prompt", None)
    parts = [str(context).strip()]
    if question:
        parts.append(str(question).strip())
    parts.append(_INSTRUCTIONS)
    return "\n\n".join(parts)


def post_prompt_for(row: BridgeRow, label_options: Sequence[str] = ()) -> str:
    """The closing turn, carrying the answer space and the ``Answer:`` contract.

    Options go *after* the series rather than in the pre-prompt, which is where
    every shipped OpenTSLM CoT dataset puts them (``SleepEDFCoTQADataset``,
    ``ECGQACoTQADataset``). With the soft-prompt tokens sitting between the two,
    the closing turn is the one the answer is conditioned on most directly.
    """
    lines: list[str] = []
    if label_options:
        lines.append("Possible answers are: " + ", ".join(label_options) + ".")
    lines.append(
        "Please now write your rationale. Make sure that your last word is the "
        'answer. You MUST end your response with "Answer: "'
    )
    return "\n\n".join(lines)


# --- the dataset class -------------------------------------------------------


class TimeNetQADataset(_QADataset):
    """An OpenTSLM ``QADataset`` backed by a TimeNet dataset id.

    Configuration is class-level because it has to be: ``QADataset.__init__``
    takes only ``(split, EOS_TOKEN, format_sample_str, time_series_format_function)``
    and there is no hook for a dataset id. Use :func:`timenet_qa_dataset` to mint
    a configured subclass rather than mutating these in place.

    .. rubric:: The class-cache trap

    ``QADataset.__init__`` guards its loading with ``hasattr(self.__class__,
    "loaded")`` and then stores the three formatted splits on
    ``self.__class__``. Three things follow, and all three have teeth:

    1. **The first instantiation wins for every split.** Constructing
       ``train`` formats train, validation *and* test immediately, all with the
       ``EOS_TOKEN`` passed on that first call. A later
       ``Dataset(split="test", EOS_TOKEN=tok.eos_token)`` silently reuses samples
       built with the earlier token. Instantiate all three splits from one place
       with one token.
    2. **``hasattr`` walks the MRO.** A subclass of an already-loaded class sees
       ``loaded`` inherited, skips loading, and then reads the *parent's*
       ``_train_dataset`` -- so profile M would train on profile S's samples with
       no error anywhere. :meth:`__init__` below refuses that explicitly rather
       than letting it through.
    3. **The cache outlives the instance.** :meth:`reset_cache` is the only way
       to reload, and it is what the tests use between fixtures.
    """

    dataset_id: ClassVar[str] = ""
    """TimeNet ``org/name`` ref, optionally ``@version``."""

    registry: ClassVar[str | Path | None] = None
    """Registry URL, ``file://`` URI or local path. ``None`` uses ``$TIMENET_REGISTRY``,
    then the hosted registry."""

    version: ClassVar[str | None] = None
    caption_only: ClassVar[bool] = False
    max_label_options: ClassVar[int] = 32
    """Above this many distinct targets the answer space is not a menu, so the
    post-prompt stops enumerating it and the task becomes open-ended."""

    label_options: ClassVar[tuple[str, ...]] = ()
    split_counts: ClassVar[dict[str, int]] = {}

    def __init__(
        self,
        split: str = "train",
        EOS_TOKEN: str = "",  # noqa: N803 - upstream's parameter name
        format_sample_str: bool = False,
        time_series_format_function: Callable[[np.ndarray], str] | None = None,
    ) -> None:
        cls = type(self)
        if not cls.dataset_id:
            raise ValueError(
                "TimeNetQADataset needs a dataset_id. Build a configured subclass with "
                "timenet_qa_dataset(dataset_id=...) rather than instantiating the base."
            )
        if "loaded" not in vars(cls) and hasattr(cls, "loaded"):
            owner = next(k.__name__ for k in cls.__mro__ if "loaded" in vars(k))
            raise RuntimeError(
                f"{cls.__name__} inherits a populated split cache from {owner}. "
                f"QADataset guards on hasattr(self.__class__, 'loaded'), which walks the "
                f"MRO, so this instance would silently serve {owner}'s samples. Mint each "
                f"configuration with timenet_qa_dataset() (a direct subclass of "
                f"TimeNetQADataset), or call {owner}.reset_cache()."
            )
        super().__init__(split, EOS_TOKEN, format_sample_str, time_series_format_function)

    # -- the five abstract methods --------------------------------------------

    def _load_splits(self) -> tuple[list[BridgeRow], list[BridgeRow], list[BridgeRow]]:
        """Load the TimeNet dataset and partition its records by ``split``.

        Returns ``(train, validation, test)`` in that order -- upstream unpacks
        the tuple positionally, and getting it wrong swaps validation and test
        without any error.

        One row per ``(record, task)`` pair: a record carrying two questions is
        two samples over one set of series. A record with no task is dropped and
        counted, because an OpenTSLM sample without an answer cannot exist.
        """
        dataset = self.load_timenet_dataset()
        rows: dict[str, list[BridgeRow]] = {name: [] for name in SPLITS}
        untasked = 0
        for record in dataset.records:
            annotations = annotation_map(record)
            raw = annotations.get(ANN_SPLIT)
            if raw is None:
                raise ValueError(
                    f"record {record.record_id!r} has no {ANN_SPLIT!r} annotation. The "
                    f"bridge partitions on it and will not invent one: an accidental "
                    f"train/test mix is unrecoverable once training starts."
                )
            split = SPLIT_ALIASES.get(str(raw).strip().lower())
            if split is None:
                raise ValueError(
                    f"record {record.record_id!r} has split {raw!r}; expected one of "
                    f"{sorted(set(SPLIT_ALIASES))}"
                )
            tasks = dataset.tasks_for(record)
            if not tasks:
                untasked += 1
                continue
            rows[split].extend(BridgeRow(record, task) for task in tasks)

        type(self).split_counts = {name: len(rows[name]) for name in SPLITS}
        type(self).split_counts["records_without_task"] = untasked
        type(self).label_options = self._derive_label_options(rows["train"])
        return rows["train"], rows["validation"], rows["test"]

    def _get_answer(self, row: BridgeRow) -> str:
        return format_answer(getattr(row.task, "rationale", None), row.task.target, self.EOS_TOKEN)

    def _get_pre_prompt(self, row: BridgeRow) -> str:
        return pre_prompt_for(row)

    def _get_post_prompt(self, row: BridgeRow) -> str:
        return post_prompt_for(row, type(self).label_options)

    def _get_text_time_series_prompt_list(self, row: BridgeRow) -> list[TextTimeSeriesPrompt]:
        captions, arrays = captioned_series(row.record, caption_only=type(self).caption_only)
        return [
            TextTimeSeriesPrompt(caption, values)
            for caption, values in zip(captions, arrays, strict=True)
        ]

    # -- helpers ---------------------------------------------------------------

    @classmethod
    def load_timenet_dataset(cls) -> Any:
        """``TimeNet(registry).load(dataset_id)``, with a legible failure.

        Split out so a test can stub it with an in-memory ``TimeFDataset`` and
        exercise the whole partition-and-format path with no registry on disk.
        """
        if not HAVE_TIMENET:  # pragma: no cover
            raise ImportError(
                f"timenet is not importable: {TIMENET_IMPORT_ERROR!r}. "
                f"Install it with `pip install 'timenet[build]'`."
            )
        return TimeNet(cls.registry).load(cls.dataset_id, cls.version)

    @classmethod
    def _derive_label_options(cls, train_rows: Iterable[BridgeRow]) -> tuple[str, ...]:
        """The answer menu, read off the train split's targets.

        Derived rather than declared, so the bridge stays domain-agnostic: it
        does not need to know that "on time / minor / major" is the label set.
        Train only -- reading validation or test targets to build a prompt shown
        at test time leaks the answer space of the held-out cells.
        """
        seen: set[str] = set()
        for row in train_rows:
            try:
                seen.add(render_target(row.task.target))
            except ValueError:
                return ()
        if not seen or len(seen) > cls.max_label_options:
            return ()
        return tuple(sorted(seen))

    @classmethod
    def reset_cache(cls) -> None:
        """Drop this class's cached splits so the next instantiation reloads."""
        for attribute in ("loaded", "_train_dataset", "_validation_dataset", "_test_dataset"):
            if attribute in vars(cls):  # own attribute only; never an ancestor's
                delattr(cls, attribute)


def timenet_qa_dataset(
    dataset_id: str,
    *,
    registry: str | Path | None = None,
    version: str | None = None,
    caption_only: bool = False,
    class_name: str | None = None,
) -> type[TimeNetQADataset]:
    """Mint a configured ``QADataset`` subclass for one TimeNet dataset.

    A factory rather than constructor arguments, because the split cache lives on
    the class (see :class:`TimeNetQADataset`). One class per configuration means
    two profiles, or the same profile with and without ``caption_only``, can be
    loaded in one process without one silently serving the other's samples.
    Every returned class is a *direct* subclass of ``TimeNetQADataset``, so the
    inherited-``loaded`` hazard cannot arise between them.
    """
    suffix = "".join(part.title() for part in dataset_id.replace("/", "-").split("-") if part)
    name = class_name or f"TimeNetQA{suffix}{'CaptionOnly' if caption_only else ''}"
    return type(
        name,
        (TimeNetQADataset,),
        {
            "dataset_id": dataset_id,
            "registry": registry,
            "version": version,
            "caption_only": caption_only,
            "__doc__": f"OpenTSLM QADataset over TimeNet dataset {dataset_id!r}.",
        },
    )


def iter_samples(
    dataset: Any,
    *,
    split: str | None = None,
    eos_token: str = "",
    caption_only: bool = False,
) -> Iterator[dict[str, Any]]:
    """Assemble samples straight from an in-memory ``TimeFDataset``.

    The path that skips ``QADataset`` entirely -- no torch, no class cache, no
    eager formatting of all three splits. Used by ``--smoke``, by ``validate.py``
    to check what a record *would* produce, and by anything that wants to write
    the samples out rather than train on them.
    """
    wanted = SPLIT_ALIASES.get((split or "").strip().lower()) if split else None
    rows: list[BridgeRow] = []
    for record in dataset.records:
        raw = annotation_map(record).get(ANN_SPLIT)
        resolved = SPLIT_ALIASES.get(str(raw).strip().lower()) if raw is not None else None
        if wanted is not None and resolved != wanted:
            continue
        rows.extend(BridgeRow(record, task) for task in dataset.tasks_for(record))
    train_rows = [
        row
        for row in rows
        if SPLIT_ALIASES.get(str(annotation_map(row.record).get(ANN_SPLIT)).strip().lower())
        == "train"
    ]
    options = TimeNetQADataset._derive_label_options(train_rows or rows)
    for row in rows:
        yield build_sample(
            row, eos_token=eos_token, caption_only=caption_only, label_options=options
        )


# --- CLI ---------------------------------------------------------------------


def _preview(values: np.ndarray, head: int = 6) -> str:
    shown = ", ".join(f"{v:+.3f}" for v in values[:head])
    tail = f", ... ({values.size} values)" if values.size > head else ""
    return f"[{shown}{tail}]"


def smoke(
    dataset_id: str,
    *,
    registry: str | Path | None = None,
    version: str | None = None,
    caption_only: bool = False,
    split: str | None = None,
    as_json: bool = False,
) -> int:
    """Print one fully assembled sample. The five-second check that this works."""
    if not HAVE_TIMENET:  # pragma: no cover
        print(f"timenet is not importable: {TIMENET_IMPORT_ERROR!r}", file=sys.stderr)
        return 2
    try:
        dataset = TimeNet(registry).load(dataset_id, version)
    except Exception as exc:
        # A smoke test that dumps a traceback has failed at its one job, which is
        # to say in one line whether the path works.
        print(f"could not load {dataset_id!r}: {type(exc).__name__}: {exc}", file=sys.stderr)
        if registry is None:
            print(
                "hint: no --registry given, so this went to the hosted registry. Point "
                "it at the local build with --registry /path/to/registry.",
                file=sys.stderr,
            )
        return 2
    sample = next(iter_samples(dataset, split=split, caption_only=caption_only), None)
    if sample is None:
        print(f"{dataset_id}: no record carries a task in split {split!r}", file=sys.stderr)
        return 1

    if as_json:
        print(
            json.dumps(
                {**sample, "time_series": [array.tolist() for array in sample["time_series"]]},
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    print(f"=== {dataset_id} :: one assembled OpenTSLM sample ===")
    print(f"keys: {sorted(sample)}")
    print(f"\n--- pre_prompt ---\n{sample['pre_prompt']}")
    print(f"\n--- {len(sample['time_series'])} series ---")
    for index, (caption, values) in enumerate(
        zip(sample["time_series_text"], sample["time_series"], strict=True)
    ):
        finite = "finite" if np.all(np.isfinite(values)) else "NON-FINITE"
        print(f"[{index:>2}] {caption}")
        print(f"     {_preview(values)}  n={values.size}  {finite}")
    print(f"\n--- post_prompt ---\n{sample['post_prompt']}")
    print(f"\n--- answer ---\n{sample['answer']}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TimeNet -> OpenTSLM bridge.")
    parser.add_argument("--smoke", action="store_true", help="print one assembled sample")
    parser.add_argument("--dataset-id", default="error404/db-route-multiscale")
    parser.add_argument("--registry", default=None)
    parser.add_argument("--version", default=None)
    parser.add_argument("--split", default=None, choices=(None, *SPLITS))
    parser.add_argument(
        "--caption-only",
        action="store_true",
        help="zero every series, keep every caption (the ablation)",
    )
    parser.add_argument("--json", action="store_true", help="emit the sample as JSON")
    args = parser.parse_args(argv)

    if not args.smoke:
        parser.print_help()
        return 0
    return smoke(
        args.dataset_id,
        registry=args.registry,
        version=args.version,
        caption_only=args.caption_only,
        split=args.split,
        as_json=args.json,
    )


if __name__ == "__main__":
    sys.exit(main())
