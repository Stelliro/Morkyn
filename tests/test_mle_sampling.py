"""The repeat penalty MLE passes to llama-cpp (F205, cheat100 T71).

A prose call gets a repeat penalty; a JSON ask keeps the library default; the
env override can change or turn it off.
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

from app import mle


class ProseCallsGetARepeatPenalty(unittest.TestCase):
    def test_a_prose_call_gets_the_default_penalty(self):
        with mock.patch.dict(os.environ, {"MORKYN_REPEAT_PENALTY": ""}):
            self.assertEqual(mle.sampling_kwargs(None), {"repeat_penalty": mle.PROSE_REPEAT_PENALTY})
            self.assertEqual(mle.sampling_kwargs("text"), {"repeat_penalty": mle.PROSE_REPEAT_PENALTY})

    def test_the_default_is_above_off(self):
        self.assertGreater(mle.PROSE_REPEAT_PENALTY, 1.0)
        self.assertLessEqual(mle.PROSE_REPEAT_PENALTY, 1.3)

    def test_a_json_ask_keeps_the_library_default(self):
        with mock.patch.dict(os.environ, {"MORKYN_REPEAT_PENALTY": "1.3"}):
            self.assertEqual(mle.sampling_kwargs("json"), {})
            self.assertEqual(mle.sampling_kwargs("JSON"), {})


class TheEnvOverride(unittest.TestCase):
    def test_a_number_replaces_the_default(self):
        with mock.patch.dict(os.environ, {"MORKYN_REPEAT_PENALTY": "1.25"}):
            self.assertEqual(mle.sampling_kwargs(None), {"repeat_penalty": 1.25})

    def test_one_point_zero_turns_it_off(self):
        with mock.patch.dict(os.environ, {"MORKYN_REPEAT_PENALTY": "1.0"}):
            self.assertEqual(mle.sampling_kwargs(None), {})

    def test_garbage_falls_back_to_the_default(self):
        with mock.patch.dict(os.environ, {"MORKYN_REPEAT_PENALTY": "lots"}):
            self.assertEqual(mle.sampling_kwargs(None), {"repeat_penalty": mle.PROSE_REPEAT_PENALTY})


if __name__ == "__main__":
    unittest.main()
