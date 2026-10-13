"""7B run 8: the time of day the prose states agrees with the clock (#132), and a closing fragment is mended."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import prose_state  # noqa: E402

T1 = (
    "The air in the tavern is thick with the scent of salt and ale, and the murmur of "
    "conversations grows louder as the night progresses."
)


class ClockWords(unittest.TestCase):
    def test_run8_t1_night_at_eight_in_the_morning(self):
        text, fixes = prose_state.repair_clock_words(T1, 8)
        self.assertIn("grows louder as the morning progresses.", text)
        self.assertEqual(fixes[0]["from"], "as the night progresses")
        self.assertEqual(text.replace("morning", "night"), T1)

    def test_words_that_fit_the_hour_stay(self):
        for sentence, hour in (
            ("The evening is calm, the crowd noise in the background.", 20),
            ("You step out of the yard, the afternoon sun warming your shoulders.", 12),
            ("The morning light filters through the window.", 8),
            ("As the evening draws on, the lamps are lit.", 17),
            ("The night air is cold on the flats.", 2),
        ):
            self.assertEqual(prose_state.repair_clock_words(sentence, hour), (sentence, []), sentence)

    def test_speech_is_left_alone(self):
        sentence = '"The night is still young, and I\'ll see you through it," she says.'
        self.assertEqual(prose_state.repair_clock_words(sentence, 16), (sentence, []))

    def test_evening_light_at_noon_and_capitals(self):
        text, _ = prose_state.repair_clock_words("The evening light falls across the yard.", 12)
        self.assertEqual(text, "The afternoon light falls across the yard.")
        text, _ = prose_state.repair_clock_words("It is night. Gulls cry over the flats.", 9)
        self.assertEqual(text, "It is morning. Gulls cry over the flats.")

    def test_daylight_at_night_has_no_safe_swap(self):
        sentence = "The morning sun glints off the salt crystals."
        self.assertEqual(prose_state.repair_clock_words(sentence, 23), (sentence, []))
        self.assertEqual(len(prose_state.clock_clashes(sentence, 23)), 1)

    def test_other_time_words_are_not_read(self):
        for sentence in (
            "Patrons who have returned from their evening ventures sit at the counter.",
            "You should be back by tonight.",
            "Last night's storm left the flats littered with wrack.",
        ):
            self.assertEqual(prose_state.clock_clashes(sentence, 10), [], sentence)


class ClosingFragment(unittest.TestCase):
    def test_run8_t0(self):
        text = '"Be careful out there."\n\nThe pressure of the day settling in.'
        out, fix = prose_state.repair_trailing_fragment(text)
        self.assertEqual(out, '"Be careful out there."\n\nThe pressure of the day is settling in.')
        self.assertEqual(fix["why"], "trailing_fragment")

    def test_plural_head(self):
        out, _ = prose_state.repair_trailing_fragment("You wait. The gulls circling overhead.")
        self.assertEqual(out, "You wait. The gulls are circling overhead.")

    def test_sentences_with_a_verb_stay(self):
        for text in (
            "The ship's gentle rocking lulls you into a light doze.",
            "The tide is coming in.",
            "The fog hangs low over the flats, rolling in from the sea.",
            "Your boots squelching in the mud, you head for the yard.",
        ):
            self.assertEqual(prose_state.repair_trailing_fragment(text), (text, None), text)


class DepthRetryCarriesTheClock(unittest.TestCase):
    """Run 8 T1: the depth retry adds light and sound and had no clock; it wrote the night in."""

    def test_the_hour_reaches_the_expansion_ask(self):
        from app import llm

        seen: list[str] = []

        def fake_chat(system_prompt, instruction, **kwargs):
            seen.append(instruction)
            return "x" * 900

        context = {"world_time": {"hour": 8, "minute_of_hour": 20, "part_of_day": "morning"}}
        turn = {"narration": "You drink half the ale and set the mug down."}
        with mock.patch.object(llm, "_chat_text", side_effect=fake_chat):
            try:
                llm._retry_narration_prose(context, "I drink half the ale.", turn, "sys", 30, [], "narration_depth_retry")
            except Exception:
                pass
        self.assertTrue(seen)
        self.assertIn("It is morning, 08:20.", seen[0])


if __name__ == "__main__":
    unittest.main()
