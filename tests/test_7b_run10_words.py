"""7B run 10 (Qwen2.5 7B on MLE, agent as player): the opening's invented lines, stale cut lines,
short repeats, stage directions and the sun."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-7b-run10-words-"))
_ENV = isolated_data_env(str(_TMP))
_SAVED_ENV: dict[str, str | None] = {}


def setUpModule():
    _SAVED_ENV.update({key: os.environ.get(key) for key in _ENV})
    os.environ.update(_ENV)


def tearDownModule():
    for key, value in _SAVED_ENV.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


OPENING_INPUT = (
    "__opening_scene_request__: Begin the playthrough before the player acts. "
    "Establish the immediate situation and its concrete hooks, then stop; the player acts first."
)
# Run 10, T0, the draft's prose (shortened at the start).
OPENING = (
    "The morning sun hangs low over Saltmarrow, casting a pale light over the town's cobblestone streets. "
    "You stand before the Cropper and Sons forge, where the sound of hammering and the scent of red-hot metal "
    "greet you. A small sign above the door reads \"Cropper and Sons,\" hinting at the skill within.\n\n"
    "Inside, the forge is bustling. A man, Jehane Tully, a knife grinder by the look of his tools, is sharpening "
    "a blade. He glances up as you approach, a spark of interest in his eyes.\n\n"
    "\"Good morn,\" you say, feeling the weight of your mother's brass tide-reckoner in your hand. "
    "\"Is there work to be done today?\"\n\n"
    "Jehane looks up, his eyes narrowing as he studies you. \"Depends, flat-runner. What have you got to offer?\"\n\n"
    "\"This is all I have. My mother worked the flats, and I need to repay her debt to the guild.\"\n\n"
    "Jehane's eyes flicker. \"A tide-reckoner, eh? That's a useful tool. I might be able to use it.\""
)


class TheOpeningGivesThePlayerNoLines(unittest.TestCase):
    """T0: the opening gave Isk two spoken lines and an offer of her reckoner."""

    def test_speech_drop_runs_on_the_opening(self):
        import re

        from app.narration_pipeline import drop_invented_player_speech

        _kept, dropped = drop_invented_player_speech(re.split(r"\n\s*\n", OPENING), OPENING_INPUT)
        self.assertTrue(any("Good morn" in d for d in dropped), dropped)
        # World-event turns and other engine requests are left as before. A Wait
        # or Sleep is silent like the opening (7B run 18, T9: a night's sleep
        # became a working day with lines the player never said).
        _kept, none = drop_invented_player_speech(re.split(r"\n\s*\n", OPENING), "__event_request__: kind=storm")
        self.assertEqual(none, [])
        _kept, waited = drop_invented_player_speech(re.split(r"\n\s*\n", OPENING), "__wait_request__: kind=wait")
        self.assertTrue(any("Good morn" in d for d in waited), waited)

    def test_opening_ends_before_her_first_line(self):
        from app import llm

        turn = {
            "narration": OPENING,
            "self_check": {},
            "inventory_changes": [{"name": "reckoner", "quantity_delta": 1}],
        }
        out = llm._end_silent_scene_before_player(turn, OPENING_INPUT)
        self.assertTrue(out["narration"].endswith("a spark of interest in his eyes."), out["narration"][-120:])
        self.assertNotIn("Good morn", out["narration"])
        self.assertNotIn("This is all I have", out["narration"])
        # The duplicate reckoner rested only on the cut part.
        self.assertEqual(out["inventory_changes"], [])
        self.assertIn("GRANT reckoner", out["_scene_cut"]["cut_ops"])

    def test_player_turns_are_not_touched(self):
        from app import llm

        turn = {"narration": OPENING}
        out = llm._end_silent_scene_before_player(turn, '"Good morn." I step inside.')
        self.assertEqual(out["narration"], OPENING)

    def test_the_ask_says_so(self):
        from app import world

        self.assertIn("give them no words", world.OPENING_SCENE_INPUT)


class AStaleLineIsNoCutPoint(unittest.TestCase):
    """T1: the 7B re-told the opening and the cut ended on its stale line, which the memory then dropped."""

    TEXT = (
        "“The reckoner isn't for trade,” you say. Jehane Tully stands by the forge entrance.\n\n"
        "Jehane looks up. \"Depends, flat-runner. What have you got to offer?\"\n\n"
        "\"I can use it to count and mark the knives. It's precise and steady,\" you say.\n\n"
        "Jehane's eyes narrow as she studies the tool."
    )
    LINE = '"The reckoner isn\'t for trade." I put it back inside my shirt. "But I\'ll sharpen your knives. How many, and what does it pay?"'

    def test_without_memory_it_cuts_there(self):
        from app import llm

        point = llm._scene_cut_point(self.TEXT, self.LINE)
        self.assertEqual((point or {}).get("npc_line"), "Depends, flat-runner. What have you got to offer?")

    def test_with_memory_it_steps_over(self):
        from app import llm

        earlier = ["Depends, flat-runner. What have you got to offer?"]
        self.assertIsNone(llm._scene_cut_point(self.TEXT, self.LINE, earlier=earlier))


class AShortLineSaidAgain(unittest.TestCase):
    """T2-T3: "Very well, then. What do you have to offer?" came back word for word."""

    def test_whole_line_repeat(self):
        from app.narration_pipeline import speech_repeats

        self.assertTrue(speech_repeats(["Very well, then. What do you have to offer?"], "Very well, then. What do you have to offer?"))
        self.assertFalse(speech_repeats(["Very well, then."], "Very well, then."))  # too short to be anyone's
        self.assertFalse(speech_repeats(["What do you have to offer?"], "Very well, then. What do you have to offer?"))

    def test_the_memory_drop_takes_it(self):
        from app.narration_pipeline import drop_speech_said_before

        text = (
            "Jehane Tully [[A]] meets your gaze. \"Very well, then. What do you have to offer?\" she asks, "
            "her voice steady."
        )
        kept, dropped = drop_speech_said_before(
            [text], ["Very well, then. What do you have to offer?"], [], "I wait.", ["A"],
            {"\"Very well, then. What do you have to offer?\" she asks, her voice steady.": "A"},
        )
        self.assertEqual(len(dropped), 1, kept)


class TheAskCarriesTheQuestion(unittest.TestCase):
    def test_player_asks(self):
        from app.db import init_db
        from app.turn_dsl import build_dsl_user_prompt
        from app.world import get_state

        init_db()
        context = get_state(include_hidden=True)
        prompt = build_dsl_user_prompt(context, '"The reckoner isn\'t for trade." "How many, and what does it pay?"')
        self.assertIn('"player_asks":["How many, and what does it pay?"]', prompt)
        plain = build_dsl_user_prompt(context, '"The reckoner isn\'t for trade."')
        self.assertNotIn("player_asks", plain)


class StageDirections(unittest.TestCase):
    """T3: a whole descriptive sentence went because it opened "The scene shifts slightly,"."""

    def test_description_after_the_shift_stays(self):
        from app.prose_state import repair_meta_leaks

        text = (
            "The scene shifts slightly, the light from the oil lamps shifting with the movement of your hand as you "
            "lay out the dull knife you've just sharpened. Jehane watches."
        )
        self.assertEqual(repair_meta_leaks(text), (text, []))

    def test_constructs_still_go(self):
        from app.prose_state import repair_meta_leaks

        for sentence in (
            "The focus shifts to the task at hand.",
            "The scene shifts.",
            "The scene shifts back to the docks.",
            "The scene is about to change as you step into a new location.",
        ):
            out, fixes = repair_meta_leaks(sentence + " Jehane watches.")
            self.assertEqual(out, "Jehane watches.", sentence)
            self.assertEqual(fixes[0]["why"], "stage_direction")


class TheSunKeepsTheClock(unittest.TestCase):
    """T9: "The sun begins to dip lower in the sky" at 10:57."""

    def test_setting_sun_in_the_morning(self):
        from app.prose_state import repair_clock_words

        out, fixes = repair_clock_words("The sun begins to dip lower in the sky, casting a golden glow.", 10)
        self.assertEqual(out, "The sun begins to climb higher in the sky, casting a golden glow.")
        self.assertEqual(fixes[0]["why"], "sun_position")

    def test_rising_sun_in_the_afternoon(self):
        from app.prose_state import repair_sun_words

        self.assertEqual(repair_sun_words("The rising sun paints the flats.", 15)[0], "The sinking sun paints the flats.")

    def test_left_alone(self):
        from app.prose_state import repair_sun_words

        for text, hour in (
            ("The sun begins to dip lower in the sky.", 17),  # evening: right
            ("The setting sun glows.", 23),  # night: no sun to move
            ("\"The sun sets early here,\" she says.", 10),  # speech
            ("The morning sun climbs higher.", 9),
        ):
            self.assertEqual(repair_sun_words(text, hour), (text, []), text)


if __name__ == "__main__":
    unittest.main()
