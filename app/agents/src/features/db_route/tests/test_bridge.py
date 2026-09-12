"""The bridge produces samples OpenTSLM will actually accept.

The interesting assertions are not "it returns a dict". They are: the caption
carries the pre-normalization scale in the exact upstream shape, the captions are
distinct even when the specs are shared, and the two lists stay positionally
aligned.
"""

from __future__ import annotations

import numpy as np
import pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bridge_fixtures import (  # noqa: E402
    N_STEPS,
    TINY,
    add_sample,
    make_dataset,
    series,
)

import bridge  # noqa: E402
from bridge import (  # noqa: E402
    ANSWER_SEPARATOR,
    BridgeRow,
    build_sample,
    captioned_series,
    format_answer,
    iter_samples,
    normalize,
    series_caption,
    timenet_qa_dataset,
)


def test_sample_has_exactly_the_five_keys(dataset):
    sample = next(iter_samples(dataset))
    assert set(sample) == {
        "pre_prompt",
        "time_series_text",
        "time_series",
        "post_prompt",
        "answer",
    }
    assert isinstance(sample["pre_prompt"], str)
    assert isinstance(sample["post_prompt"], str)
    assert isinstance(sample["answer"], str)
    assert isinstance(sample["time_series_text"], list)
    assert isinstance(sample["time_series"], list)


def test_every_series_is_strictly_one_dimensional_and_aligned(dataset):
    sample = next(iter_samples(dataset))
    assert len(sample["time_series"]) == len(sample["time_series_text"]) == 2
    for values in sample["time_series"]:
        assert values.ndim == 1
        assert values.size == N_STEPS
        assert np.issubdtype(values.dtype, np.number)
    # Positional alignment: caption i describes series i, and nothing re-checks it
    # downstream, so it is checked here.
    assert sample["time_series_text"][0].startswith("The mean delay of this service")
    assert sample["time_series_text"][1].startswith("The mean delay at this station")


def test_caption_carries_pre_normalization_scale_in_the_exact_upstream_shape(dataset):
    record = dataset.records[0]
    captions, arrays = captioned_series(record)
    raw = record.time_series[0].to_numpy().astype(np.float64)
    mean, std = float(raw.mean()), float(raw.std(ddof=1))

    assert captions[0] == (
        f"The mean delay of this service, it has mean {mean:.4f} and std {std:.4f}:"
    )
    # ...and the series really is z-scored, so the caption is the only scale left.
    assert arrays[0].mean() == pytest.approx(0.0, abs=1e-9)
    assert arrays[0].std(ddof=1) == pytest.approx(1.0, abs=1e-9)


def test_shared_spec_would_collapse_captions_but_the_annotation_saves_them():
    """The defect the sibling implementation has, reproduced and then avoided."""
    ds = make_dataset()
    add_sample(ds, "r", captions=False)
    record = ds.records[0]
    # Both series are on the one shared `delay` spec, so spec.name is identical...
    assert record.time_series[0].spec.name == record.time_series[1].spec.name == "Delay"
    without = [c.split(",")[0] for c in captioned_series(record)[0]]
    assert without[0] == without[1] == "Delay"  # the collapse, in one line

    ds2 = make_dataset()
    add_sample(ds2, "r", captions=True)
    with_annotation = [c.split(",")[0] for c in captioned_series(ds2.records[0])[0]]
    assert with_annotation[0] != with_annotation[1]


def test_caption_key_resolution_order():
    ds = make_dataset()
    record, _ = add_sample(ds, "r", captions=False)
    one = record.time_series[0]  # id "week/service_delay", source_id "week"
    assert series_caption(one, {"caption:week/service_delay": "by id"}) == "by id"
    assert series_caption(one, {"caption:service_delay": "by signal"}) == "by signal"
    assert series_caption(one, {}) == "Delay"  # spec.name fallback


def test_std_is_clamped_so_a_constant_series_never_yields_nan():
    normalized, mean, std = normalize(np.full(8, 3.5))
    assert std == bridge.MIN_STD
    assert mean == pytest.approx(3.5)
    assert np.all(normalized == 0.0)
    assert np.all(np.isfinite(normalized))


def test_answer_is_rationale_then_separator_then_target_then_eos():
    answer = format_answer("Because the trend is flat.", "on_time", "<eos>")
    assert answer == "Because the trend is flat. Answer: on_time<eos>"
    assert answer.count(ANSWER_SEPARATOR) == 1
    # QADataset appends EOS itself when absent, so appending here must be idempotent.
    assert format_answer("x.", "y", "<eos>").endswith("<eos>")
    assert not format_answer("x.", "y", "<eos>").endswith("<eos><eos>")


def test_caption_only_zeroes_the_series_and_keeps_every_caption(dataset):
    record = dataset.records[0]
    plain, _ = captioned_series(record)
    ablated_captions, ablated = captioned_series(record, caption_only=True)
    assert ablated_captions == plain  # scale statistics survive verbatim
    for values in ablated:
        assert values.size == N_STEPS
        assert np.all(values == 0.0)


def test_pre_prompt_uses_the_context_annotation_when_present(dataset):
    row = BridgeRow(dataset.records[0], dataset.tasks_for(dataset.records[0])[0])
    assert "S8 calling at Muenchen Ost" in bridge.pre_prompt_for(row)

    ds = make_dataset()
    add_sample(ds, "r", pre_prompt_context=None)
    generic = bridge.pre_prompt_for(BridgeRow(ds.records[0], ds.tasks_for(ds.records[0])[0]))
    assert "You are given 2 time series" in generic


def test_post_prompt_carries_the_answer_contract_and_the_label_menu(dataset):
    row = BridgeRow(dataset.records[0], dataset.tasks_for(dataset.records[0])[0])
    post = bridge.post_prompt_for(row, ("major", "minor", "on_time"))
    assert "Possible answers are: major, minor, on_time." in post
    assert 'You MUST end your response with "Answer: "' in post


def test_load_splits_partitions_records_by_annotation(dataset, monkeypatch):
    cls = timenet_qa_dataset("test/tiny")
    monkeypatch.setattr(cls, "load_timenet_dataset", classmethod(lambda _c: dataset))

    train = cls(split="train", EOS_TOKEN="")
    assert cls.split_counts == {
        "train": 1,
        "validation": 1,
        "test": 1,
        "records_without_task": 0,
    }
    assert len(train) == 1
    # All three splits are formatted on the first instantiation and cached on the
    # class; the later constructions must not reload.
    assert len(cls(split="validation", EOS_TOKEN="")) == 1
    assert len(cls(split="test", EOS_TOKEN="")) == 1

    sample = train[0]
    assert set(sample) == {
        "pre_prompt",
        "time_series_text",
        "time_series",
        "post_prompt",
        "answer",
    }
    assert sample["answer"].endswith(" Answer: minor")
    # Label options come from the train split only, so held-out targets do not leak.
    assert cls.label_options == ("minor",)


def test_the_first_eos_token_wins_for_every_split(dataset, monkeypatch):
    """The documented cache trap, demonstrated rather than asserted in prose."""
    cls = timenet_qa_dataset("test/tiny", class_name="EosTrap")
    monkeypatch.setattr(cls, "load_timenet_dataset", classmethod(lambda _c: dataset))

    cls(split="train", EOS_TOKEN="<first>")
    later = cls(split="test", EOS_TOKEN="<second>")
    assert later[0]["answer"].endswith("<first>")  # not <second>
    assert "<second>" not in later[0]["answer"]

    cls.reset_cache()
    assert cls(split="test", EOS_TOKEN="<second>")[0]["answer"].endswith("<second>")


def test_a_subclass_of_a_loaded_class_refuses_to_serve_its_parents_cache(dataset, monkeypatch):
    parent = timenet_qa_dataset("test/tiny", class_name="CacheParent")
    monkeypatch.setattr(parent, "load_timenet_dataset", classmethod(lambda _c: dataset))
    parent(split="train", EOS_TOKEN="")

    child = type("CacheChild", (parent,), {})
    with pytest.raises(RuntimeError, match="inherits a populated split cache"):
        child(split="train", EOS_TOKEN="")


def test_a_multi_channel_series_is_refused_rather_than_ravelled():
    ds = make_dataset()
    record, _ = add_sample(ds, "r")

    class TwoDimensional:
        spec, signal, source_id, time_series_id = None, "wide", "week", "week/wide"

        def to_numpy(self):
            return np.zeros((4, 3))

    record.time_series = (*record.time_series, TwoDimensional())
    with pytest.raises(ValueError, match="never one multi-channel array"):
        captioned_series(record)


def test_a_record_without_a_split_annotation_is_refused(monkeypatch):
    ds = make_dataset()
    record, _ = add_sample(ds, "r")
    record.annotations = tuple(a for a in record.annotations if a.key != "split")
    cls = timenet_qa_dataset("test/tiny", class_name="NoSplit")
    monkeypatch.setattr(cls, "load_timenet_dataset", classmethod(lambda _c: ds))
    with pytest.raises(ValueError, match="has no 'split' annotation"):
        cls(split="train", EOS_TOKEN="")


def test_series_longer_than_the_encoder_cap_is_refused():
    ds = make_dataset()
    record = ds.add_record(
        record_id="long",
        time_series=(series(np.arange(bridge.MAX_SERIES_SAMPLES + 4), "service_delay"),),
    )
    with pytest.raises(ValueError, match="encoder cap"):
        captioned_series(record)


@pytest.mark.skipif(not bridge.HAVE_OPENTSLM, reason="opentslm not importable")
def test_the_prompt_objects_upstream_would_build_accept_our_arrays(dataset):
    from opentslm.prompt.prompt_with_answer import PromptWithAnswer
    from opentslm.prompt.text_prompt import TextPrompt
    from opentslm.prompt.text_time_series_prompt import TextTimeSeriesPrompt

    row = BridgeRow(dataset.records[0], dataset.tasks_for(dataset.records[0])[0])
    sample = build_sample(row)
    upstream = PromptWithAnswer(
        TextPrompt(sample["pre_prompt"]),
        [
            TextTimeSeriesPrompt(text, values)
            for text, values in zip(sample["time_series_text"], sample["time_series"])
        ],
        TextPrompt(sample["post_prompt"]),
        sample["answer"],
    ).to_dict()
    assert set(upstream) == set(sample)
    assert upstream["time_series_text"] == sample["time_series_text"]


@pytest.mark.skipif(not bridge.HAVE_OPENTSLM, reason="opentslm not importable")
def test_the_collate_leaves_our_uniform_lengths_untouched(dataset):
    """Every length equals n_steps, so the maskless zero padding never fires."""
    from opentslm.time_series_datasets.util import (
        extend_time_series_to_match_patch_size_and_aggregate as collate,
    )

    sample = next(iter_samples(dataset))
    batched = collate([{"time_series": sample["time_series"]}])[0]["time_series"]
    assert tuple(batched.shape) == (2, N_STEPS)
    assert N_STEPS % 4 == 0


def test_the_profile_ladder_stays_inside_the_encoder_cap():
    from profiles import PROFILES

    for profile in PROFILES.values():
        for layer in profile.layers:
            assert layer.n_steps <= bridge.MAX_SERIES_SAMPLES
            assert layer.n_steps % 4 == 0
    assert TINY.n_series == 2


# --- the two ablations that catch a model ignoring the charts ---------------
# Splits catch a model memorising examples. Neither of these does -- they catch a
# model that never read the series at all, which a split cannot distinguish from
# genuine skill. A test that only asserts the flags exist would miss the failure
# mode where a flag is wired but ablates nothing, so each of these compares the
# ablated input against the honest one.


def test_caption_only_removes_the_shape_but_keeps_the_scale(dataset):
    """The ablation must zero the numbers and change nothing else.

    Captions carry the pre-normalization mean and std, so they still tell the
    model the absolute level. If a caption-only run scores near the full one, the
    model was reading those two summary statistics and never the shape -- which
    is the thing the whole time-series encoder exists to do.
    """
    record = dataset.records[0]
    honest_captions, honest = captioned_series(record)
    ablated_captions, ablated = captioned_series(record, caption_only=True)

    assert ablated_captions == honest_captions, "captions must survive verbatim"
    assert any(np.any(a != 0) for a in honest), "fixture must have a non-zero series"
    assert all(np.all(a == 0) for a in ablated), "every series must be zeroed"
    assert [a.shape for a in ablated] == [a.shape for a in honest]
    assert any("mean" in c and "std" in c for c in ablated_captions), (
        "the scale must still reach the model, or this ablation tests the wrong thing"
    )


def test_the_text_baseline_carries_no_series_array(dataset):
    """The no-connector baseline: same numbers, serialised as words.

    This is what proves the connector earns its place. If the TSLM only matches
    it, the encoder, the projector and the whole TimeNet path bought nothing.
    """
    record = dataset.records[0]
    _, honest = captioned_series(record)
    assert honest and honest[0].size > 0

    sample = build_sample(BridgeRow(record, dataset.tasks_for(record)[0]))
    assert set(sample) == {"pre_prompt", "time_series_text", "time_series", "post_prompt", "answer"}
    assert len(sample["time_series"]) == len(sample["time_series_text"]), (
        "captions and arrays are positionally aligned; a mismatch silently "
        "mislabels every series"
    )
    for array in sample["time_series"]:
        assert np.asarray(array).ndim == 1, "OpenTSLM rejects anything but 1-D"
