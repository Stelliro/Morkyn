"""
Review of the playtest #1-#9 fixes: the gaps a replay of the logged turns found.

  - Turn 5, "come out now" commanding whatever is hiding: the engine said the
    line went to Aria ("the one the player was talking to"), which tells the
    draft only Aria answers -- the one person the call was not for.
  - The bare-code repair turned any known two- or three-letter NPC code into
    that person's name, so a shouted "AH!" or a king's "IV" in a world with
    enough NPCs became "Name [[AH]]".
  - Item grounding read "Aria took the loaf" (a name, past tense) as the
    player taking it.
  - The DSL prompt said a bare QTY number is re-rolled one line before it said
    a plain number is kept as a real stack.
  - The proficiency settle prompt listed sample tracking answers.
"""
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-review-fixes-"))
os.environ.update(isolated_data_env(str(_TMP)))
os.environ.update(
    {
        "AI_RPG_PACK_DIR": str(_TMP / "packs"),
        "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
    }
)

from app import conversation as cv  # noqa: E402
from app import world  # noqa: E402
from app.llm import _repair_entity_names_in_turn  # noqa: E402
from app.proficiencies import _SETTLE_SYSTEM  # noqa: E402
from app.turn_dsl import DSL_SYSTEM_PROMPT  # noqa: E402

# Turn 5, as the trace recorded it.
TURN5_INPUT = 'i use @Swhispering_fates and say "come out now" commanding whatever is hiding to reveal itself'
TURN5_CAST = {"present": [], "interacting": ["C"], "off": [], "keywords": []}
TURN5_FINAL = (
    "You raise your hand and murmur, \"Come out now.\" The air seems to quiver, and then a shadow stirs from "
    "the darkest corner.\n\nThe figure's hooded head turns towards you. \"Who are you, and what do you seek in "
    "the Back Lane?\" the figure demands.\n\nThe hood falls back, revealing a stern face: Ashwalker [[C]]."
)
TURN6_INPUT = (
    'i say "state your business, if you came to intimidate you came to the wrong place" '
    "essentially insulting them while also making their actions look unintelligent."
)
SCENE_BEFORE_5 = {"present": ["A"], "interacting": ["A"], "keywords": []}
SCENE_AFTER_5 = {"present": ["A", "C"], "interacting": ["A", "C"], "keywords": []}


def lane_context(settings: dict | None = None) -> dict:
    return {
        "current_location": {"id": 1, "code": "L1", "name": "The Back Lane"},
        "locations": [
            {
                "id": 1,
                "code": "L1",
                "name": "The Back Lane",
                "npcs": [
                    {"id": 1, "code": "A", "name": "Aria"},
                    {"id": 2, "code": "B", "name": "Quillwatch"},
                    {"id": 3, "code": "C", "name": "Ashwalker"},
                ],
            },
        ],
        "settings": settings if settings is not None else {"active_scene": dict(SCENE_BEFORE_5)},
    }


class CallToSomeoneUnseen(unittest.TestCase):
    def test_turn5_call_is_not_given_to_aria(self):
        r5 = cv.resolve(lane_context(), TURN5_INPUT)
        self.assertEqual(r5["addressed"], [])
        self.assertEqual(r5["rule"], "unseen")
        self.assertIn("A", r5["listening"])

    def test_every_stage_hears_that_nobody_present_answers_for_them(self):
        r5 = cv.resolve(lane_context(), TURN5_INPUT)
        note = cv.model_note(r5)
        self.assertIn("calls out to someone unseen", note)
        self.assertNotIn("Only Aria", note)
        self.assertIn("listening", note)
        self.assertEqual(cv.writer_view(r5)["who_answers"], [])
        self.assertIn("unseen", cv.writer_view(r5)["player_talks_to"][0])
        self.assertIn("not the listeners", cv.world_view(r5)["answers"])

    def test_the_reveal_still_hands_turn6_to_the_figure(self):
        ctx = lane_context()
        r5 = cv.resolve(ctx, TURN5_INPUT)
        state = cv.next_state(
            cv.load_state(ctx["settings"]),
            context=ctx,
            resolution=r5,
            scene_before=SCENE_BEFORE_5,
            scene_after=SCENE_AFTER_5,
            scene_cast=TURN5_CAST,
            narration=TURN5_FINAL,
            player_input=TURN5_INPUT,
            turn=5,
        )
        after = lane_context({"active_scene": cv.synced_scene(SCENE_AFTER_5, state), "conversation": state})
        r6 = cv.resolve(after, TURN6_INPUT)
        self.assertEqual(r6["addressed"], ["C"])
        self.assertIn("A", r6["listening"])

    def test_a_name_in_the_line_still_wins(self):
        r = cv.resolve(lane_context(), 'i say "Aria, come out from behind the cart"')
        self.assertEqual(r["addressed"], ["A"])

    def test_ordinary_talk_keeps_the_partner(self):
        r = cv.resolve(lane_context(), 'i say "the bread smells good"')
        self.assertEqual(r["addressed"], ["A"])


class BareCodesThatAreWords(unittest.TestCase):
    def _repair(self, narration, npcs):
        context = {"locations": [{"code": "L1", "name": "Back Lane", "npcs": npcs}]}
        return _repair_entity_names_in_turn({"narration": narration}, context)["narration"]

    def test_a_shout_is_not_the_34th_person(self):
        out = self._repair("AH, the hinge screams as you shove the gate.", [{"code": "AH", "name": "Merrow"}])
        self.assertNotIn("Merrow", out)

    def test_a_regnal_number_is_not_a_person(self):
        out = self._repair("The banner of Edric IV hangs over the gate.", [{"code": "IV", "name": "Tamsin"}])
        self.assertNotIn("Tamsin", out)

    def test_capitals_inside_speech_are_left_alone(self):
        out = self._repair('"BRN is a lie," she hisses.', [{"code": "BRN", "name": "Bram"}])
        self.assertNotIn("Bram", out)

    def test_a_code_in_narration_is_still_named(self):
        out = self._repair("Then BRN waves you over.", [{"code": "BRN", "name": "Bram"}])
        self.assertIn("Bram [[BRN]] waves", out)


class NamedSubjectIsNotThePlayer(unittest.TestCase):
    TOKENS = ["loaf", "bread"]

    def test_a_named_npc_taking_it_is_not_your_gain(self):
        for text in ("Aria took the loaf of bread.", "Aria [[A]] took the loaf of bread and smiled."):
            self.assertIsNone(world._prose_item_outcome(text, "loaf of bread", self.TOKENS), text)

    def test_the_player_taking_it_still_is(self):
        for text in (
            "You take the loaf of bread.",
            "Then you take the loaf of bread.",
            "You consider, then take the loaf of bread.",
        ):
            self.assertEqual(world._prose_item_outcome(text, "loaf of bread", self.TOKENS), "gain", text)


class PromptsSayOneThing(unittest.TestCase):
    def test_dsl_prompt_does_not_reroll_item_counts(self):
        self.assertNotIn("a bare number is\n  read as a band hint", DSL_SYSTEM_PROMPT.replace("\r\n", "\n"))
        self.assertIn("A real stack may be a plain number", DSL_SYSTEM_PROMPT)

    def test_settle_prompt_lists_no_sample_tracking(self):
        self.assertNotIn("a mentor, use on the job", _SETTLE_SYSTEM)
        self.assertNotIn("(practice", _SETTLE_SYSTEM)


if __name__ == "__main__":
    unittest.main()
