"""
Playtest issue #4: input suggestions were bland, and there was no deeper one.

The 2026-10-05 playtest got "Inquire about local rumors", "Examine the
enchanted lantern", "Negotiate a favor with Aria" after a turn where Aria and
Ashwalker had just squared off in the lane. The packet carried world lists and
the whole setup (about 39,000 characters) but no scene text, so the model could
only offer moves that fit any scene. The lantern one landed because the
inventory was in the packet; that has to stay.

These build the prompt from a turn-6 shaped context with the model call
mocked, and check what the model is given and asked:
  - the end of the last narration, without [[codes]];
  - questions the narration left open;
  - the people in it, who the player faces, what they care about;
  - active quests and open offers;
  - every carried item by name;
  - no whole setup block, and a smaller packet than before;
  - the "Deeper idea" ask returns one action and a one-line why.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-suggestions-"))
os.environ.update(isolated_data_env(str(_TMP)))

from app import llm  # noqa: E402

TURN6_NARRATION = (
    'Aria [[A]] narrows her icy blue stare at you, arms crossed over her chest. She leans back against the '
    'brick wall, one eyebrow raised.\n\n'
    '"I didn\'t come to fight," she says. "I was looking for someone else." '
    'Ashwalker [[C]], a burly figure with a weathered face, shifts uncomfortably. '
    '"Intimidate, you said? I was merely passing through when I heard your little exchange." '
    'He glances at you. "Who sent you down this lane?"'
)


def turn6_context() -> dict:
    return {
        "settings": {
            "setup_complete": True,
            "playthrough_options": {
                "world_style": "frontier dark fantasy",
                "custom_style": "Harsh climates and sparse settlements.",
                "magic_level": "rare",
                "difficulty": "normal",
                # The old packet shipped all of this every time.
                "starter_gear": [{"name": "Well-Worn Boots", "description": "x" * 4000}],
                "race_magic_rules": "y" * 4000,
            },
        },
        "player": {"name": "Harrow Ames", "level": 1, "health": 20, "max_health": 20, "gold": 12, "stat_blob": "z" * 3000},
        "current_location": {"id": 1, "code": "L1", "name": "The Back Lane"},
        "locations": [
            {
                "id": 1,
                "code": "L1",
                "name": "The Back Lane",
                "npcs": [
                    {
                        "id": 1,
                        "code": "A",
                        "name": "Aria",
                        "role": "baker",
                        "attitude": "cautious",
                        "likes": "her ovens kept warm, regular customers",
                        "known_facts": json.dumps(["[[I am a baker in Low Gate, cautious of strangers.]]"]),
                    },
                    {"id": 3, "code": "C", "name": "Ashwalker", "role": "rag picker", "attitude": "neutral", "known_facts": "[]"},
                    {"id": 2, "code": "B", "name": "Quillwatch", "role": "porter", "attitude": "neutral"},
                ],
            },
            {"id": 9, "code": "L9", "name": "Far Shore", "npcs": [{"id": 9, "code": "Z", "name": "Distant Stranger", "role": "hermit"}]},
        ],
        "conversation": {
            "target": [{"code": "C", "name": "Ashwalker"}],
            "present": [{"code": "A", "name": "Aria"}, {"code": "C", "name": "Ashwalker"}],
        },
        "last_narration": TURN6_NARRATION,
        "active_quests": [{"code": "Q1", "title": "Find the lost ledger", "current_objective": "Ask around Low Gate"}],
        "open_quest_offers": [{"code": "Q2", "title": "Sweep the ovens", "giver": "Aria", "current_objective": "Clean the ash pit"}],
        "carried_items": [{"name": "Small, Enchanted Lantern", "worn": "OFF"}, {"name": "loaf of bread", "qty": 2}],
        "inventory_summary": {"equipped_item_codes": ["I1", "I2", "I3", "I4"]},
        "skills": [{"name": "Whispering Fates", "value": 1}],
        "abilities": [{"name": "Luminous Veil", "description": "Bend lantern light into a veil."}],
        "events": [],
        "conversations": [],
        "relevant_sources": [],
        "turn_summaries": [],
    }


class CapturedCall:
    def __init__(self, reply: dict):
        self.reply = reply
        self.system = ""
        self.prompt: dict = {}
        self.raw = ""
        self.kwargs: dict = {}

    def __call__(self, system, user, **kwargs):
        self.system = system
        self.raw = user
        self.prompt = json.loads(user)
        self.kwargs = kwargs
        return self.reply


class SuggestionPromptTests(unittest.TestCase):
    def ask(self, deeper: bool = False, reply: dict | None = None) -> tuple[dict, CapturedCall]:
        call = CapturedCall(reply or {"suggestions": ["one move", "two move", "three move"]})
        with mock.patch.object(llm, "_chat_json", call):
            result = llm.generate_input_suggestions(turn6_context(), "", deeper=deeper)
        return result, call

    def test_scene_text_reaches_the_model_without_codes(self):
        _, call = self.ask()
        scene = call.prompt["scene"]
        self.assertIn("Who sent you down this lane?", scene["last_scene"])
        self.assertNotIn("[[", json.dumps(call.prompt["scene"]))
        self.assertEqual(scene["place"], "The Back Lane")

    def test_open_questions_are_lifted_from_the_narration(self):
        _, call = self.ask()
        questions = call.prompt["scene"]["questions_left_open"]
        self.assertIn("Who sent you down this lane?", questions)
        self.assertIn("Intimidate, you said?", questions)

    def test_people_carry_what_they_care_about_and_who_faces_the_player(self):
        _, call = self.ask()
        people = {row["name"]: row for row in call.prompt["scene"]["people"]}
        self.assertEqual(list(people)[0], "Ashwalker", "the person the player faces comes first")
        self.assertTrue(people["Ashwalker"]["facing_player"])
        self.assertIn("ovens", people["Aria"]["cares_about"])
        self.assertEqual(people["Aria"]["attitude"], "cautious")
        self.assertIn("baker in Low Gate", people["Aria"]["known"][0])
        self.assertNotIn("Distant Stranger", people, "someone elsewhere and unnamed is not in the scene")

    def test_quests_offers_and_inventory_stay(self):
        _, call = self.ask()
        scene = call.prompt["scene"]
        self.assertEqual(scene["active_quests"][0]["title"], "Find the lost ledger")
        self.assertEqual(scene["open_offers"][0]["giver"], "Aria")
        names = [item["name"] for item in call.prompt["world_state"]["carried_items"]]
        self.assertIn("Small, Enchanted Lantern", names)

    def test_packet_drops_the_setup_block(self):
        _, call = self.ask()
        self.assertNotIn("settings", call.prompt["world_state"])
        self.assertNotIn("starter_gear", call.raw)
        self.assertNotIn("stat_blob", call.raw)
        self.assertLess(len(call.raw), 8000)
        self.assertEqual(call.kwargs["max_tokens"], 180)

    def test_ask_is_for_scene_specific_moves(self):
        _, call = self.ask()
        rules = " ".join(call.prompt["rules"])
        self.assertIn("would fit any scene is wrong", rules)
        self.assertIn("carried item", rules)
        self.assertIn("questions_left_open", rules)

    def test_three_suggestions_still_returned_and_codes_stripped(self):
        result, _ = self.ask(reply={"suggestions": ["Answer Ashwalker [[C]] plainly", "b", "c"]})
        self.assertEqual(result["suggestions"][0], "Answer Ashwalker plainly")
        self.assertEqual(len(result["suggestions"]), 3)


class DeeperSuggestionTests(unittest.TestCase):
    def test_one_action_and_one_line_why(self):
        call = CapturedCall({"action": "Offer Ashwalker [[C]] a loaf of bread " + "and ask " * 40, "why": "He is hungry " * 20})
        with mock.patch.object(llm, "_chat_json", call):
            result = llm.generate_input_suggestions(turn6_context(), "", deeper=True)
        deeper = result["deeper"]
        self.assertNotIn("suggestions", result)
        self.assertTrue(deeper["action"].startswith("Offer Ashwalker a loaf"))
        self.assertLessEqual(len(deeper["action"]), llm.SUGGESTION_DEEPER_ACTION_CHARS)
        self.assertLessEqual(len(deeper["why"]), llm.SUGGESTION_DEEPER_WHY_CHARS)
        self.assertLessEqual(len(deeper["action"]) + len(deeper["why"]), 270)
        self.assertEqual(call.kwargs["phase"], "input_suggestion_deeper")
        self.assertIn("scene", call.prompt)
        self.assertEqual(set(call.prompt["return_shape"]), {"action", "why"})

    def test_empty_action_is_an_error(self):
        with mock.patch.object(llm, "_chat_json", CapturedCall({"action": "", "why": "x"})):
            with self.assertRaises(llm.LlmError):
                llm.generate_input_suggestions(turn6_context(), "", deeper=True)

    def test_route_passes_the_flag(self):
        from app import main

        with mock.patch.object(main, "get_input_suggestions", return_value={"deeper": {"action": "a", "why": "b"}}) as fake:
            out = main.api_suggestions(main.SuggestionRequest(instruction="be bold", deeper=True))
        fake.assert_called_once_with("be bold", deeper=True)
        self.assertEqual(out["deeper"]["action"], "a")
        with mock.patch.object(main, "get_input_suggestions", return_value={"suggestions": ["a", "b", "c"]}) as fake:
            main.api_suggestions(main.SuggestionRequest())
        fake.assert_called_once_with("")


if __name__ == "__main__":
    unittest.main()
