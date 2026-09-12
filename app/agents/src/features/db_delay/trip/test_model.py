"""Tokenizer-level checks for the answer format; no model weights needed."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from transformers import AutoTokenizer

sys.path.insert(0, str(Path(__file__).parent))

import prompts  # noqa: E402
from model import BASE_LLM, MAX_MINUTES  # noqa: E402


def example_row(**overrides) -> pd.Series:
    """A plausible running long-distance example."""
    row = {
        "example_id": 1, "cls": "long-distance", "train_type": "ICE", "train_number": "771", "line_number": None,
        "origin": "Astadt Hbf", "dest": "Cstadt Hbf", "first_station": "Astadt Hbf", "j_station": "Bdorf",
        "k_station": "Cstadt Hbf", "k_arr_pt": pd.Timestamp("2026-06-10 17:57"), "pre_departure": False,
        "run_delays": np.array([2.0, 7.0, 6.0]), "via": np.array(["Mitteldorf"]), "current_delay": 6.0,
        "delay_change_3": 4.0, "max_delay_so_far": 7.0, "stops_ahead": 2.0, "lead_minutes": 47.0,
        "hist_level": "pattern", "hist_median": 4.0, "hist_p90": 12.0, "hist_cancel_share": 0.02,
        "hist_series": np.arange(30, dtype=np.float32), "station_series": np.linspace(0, 0.3, 72),
        "network_series": np.linspace(0.1, 0.2, 72), "station_late_3h": 0.18, "station_late_72h": 0.14,
        "network_late_3h": 0.31, "network_late_72h": 0.22, "target_minutes": 8.0, "cancelled": False,
    }
    row.update(overrides)
    return pd.Series(row)


class AnswerFormatTest(unittest.TestCase):
    """The loss and the readout find the tokens they expect."""

    @classmethod
    def setUpClass(cls) -> None:
        """Load only the tokenizer."""
        cls.tok = AutoTokenizer.from_pretrained(BASE_LLM)
        cls.space = cls.tok.convert_tokens_to_ids("Ġ")
        cls.cancel = cls.tok.convert_tokens_to_ids("Ġcancelled")

    def encode(self, text: str) -> list[int]:
        """Token ids without special tokens."""
        return self.tok.encode(text, add_special_tokens=False)

    def test_minute_answer_ends_in_space_then_one_number_token(self) -> None:
        """For 0, 8, 57 and 999 the answer is prefix, space, number."""
        for minutes in (0, 8, 57, MAX_MINUTES):
            s = prompts.sample(example_row(target_minutes=float(minutes)))
            answer, prefix = self.encode(s["answer"]), self.encode(s["prefix"])
            self.assertEqual(answer[:-1], prefix + [self.space])
            self.assertEqual(answer[-1], self.tok.convert_tokens_to_ids(str(minutes)))

    def test_cancelled_answer_is_prefix_then_cancel_token(self) -> None:
        """A cancelled target is one token after the same prefix."""
        s = prompts.sample(example_row(cancelled=True, target_minutes=np.nan))
        self.assertEqual(self.encode(s["answer"]), self.encode(s["prefix"]) + [self.cancel])

    def test_rationale_does_not_depend_on_the_target(self) -> None:
        """Changing only the target leaves the rationale and prefix untouched."""
        a = prompts.sample(example_row(target_minutes=3.0))
        b = prompts.sample(example_row(target_minutes=90.0))
        c = prompts.sample(example_row(cancelled=True, target_minutes=np.nan))
        self.assertEqual(a["prefix"], b["prefix"])
        self.assertEqual(a["prefix"], c["prefix"])

    def test_text_only_sample_writes_numbers_and_keeps_the_answer(self) -> None:
        """The text-only baseline has no series, states the numbers, and shares reasoning and answer tokens."""
        encoder = prompts.sample(example_row())
        text = prompts.sample(example_row(), text_only=True)
        self.assertEqual(text["time_series"], [])
        self.assertEqual(text["time_series_text"], [])
        self.assertIn("in percent: 0, 0, 1", text["pre_prompt"])
        self.assertIn("Departure delay at each stop so far, in minutes: 2, 7, 6", text["pre_prompt"])
        self.assertEqual(text["answer"], encoder["answer"])
        self.assertEqual(self.encode(text["answer"])[:-1], self.encode(text["prefix"]) + [self.space])
        self.assertEqual(len(encoder["time_series"]), 4)

    def test_pre_departure_sample_has_a_placeholder_series(self) -> None:
        """Before departure the run series is a single zero and the text says so."""
        s = prompts.sample(example_row(pre_departure=True, run_delays=np.array([]), j_station=None))
        self.assertEqual(len(s["time_series"]), 4)
        self.assertTrue(s["time_series_text"][0].startswith("No departures yet"))
        self.assertIn("not departed", s["pre_prompt"])


if __name__ == "__main__":
    unittest.main()
