import unittest

from app.llm import _grok_reasoning_effort, _is_light_question, _verification_policy
from app.turn_dsl import parse_dsl_turn
from app.world import _expand_input_references, _mention_slug, _pick_mention


class MentionExpandTests(unittest.TestCase):
    def test_slug_uses_underscores(self):
        self.assertEqual(_mention_slug("Arnold Schwarzenegger"), "arnold_schwarzenegger")

    def test_prefix_matches_one_character(self):
        rows = [
            {"kind": "C", "name": "Arnold Schwarzenegger", "code": "C", "slug": "arnold_schwarzenegger", "label": "NPC"},
            {"kind": "C", "name": "Arnold Smith", "code": "D", "slug": "arnold_smith", "label": "NPC"},
            {"kind": "I", "name": "non-slip shoes", "code": "I2", "slug": "non_slip_shoes", "label": "item"},
        ]
        hit = _pick_mention(rows, "C", "arnold_sc")
        self.assertEqual(hit["code"], "C")
        self.assertIsNone(_pick_mention(rows, "C", "arn"))
        self.assertIsNone(_pick_mention(rows, "C", "a"))

    def test_player_text_becomes_name_and_code(self):
        context = {
            "locations": [
                {
                    "code": "L1",
                    "name": "Low Gate",
                    "npcs": [{"code": "C", "name": "Arnold Schwarzenegger"}],
                }
            ],
            "inventory": [{"code": "I2", "name": "non-slip shoes"}],
            "events": [],
            "aliases": [],
        }
        expanded = _expand_input_references(
            context,
            "I ask @Carnold_sc about @Inon_slip_shoes",
        )
        self.assertIn("Arnold Schwarzenegger [[C]]", expanded)
        self.assertIn("non-slip shoes [[I2]]", expanded)
        self.assertNotIn("@C", expanded.split("Resolved player references:", 1)[0])
        self.assertIn("@Carnold_schwarzenegger = Arnold Schwarzenegger (C, NPC)", expanded)

    def test_alias_and_multiletter_code_are_not_stolen(self):
        context = {
            "locations": [
                {
                    "code": "L1",
                    "name": "Low Gate",
                    "npcs": [
                        {"code": "B", "name": "Anna"},
                        {"code": "D", "name": "Captain Reed"},
                        {"code": "CA", "name": "Captain Reed"},
                    ],
                }
            ],
            "inventory": [],
            "events": [],
            "aliases": [{"alias": "ca", "entity_type": "npc", "entity_code": "D"}],
            "abilities": [],
        }
        hailed = _expand_input_references(context, "I hail @ca")
        self.assertIn("@ca", hailed.split("Resolved player references:", 1)[0])
        self.assertNotIn("Anna [[B]]", hailed)
        attacked = _expand_input_references(context, "I attack @CA")
        self.assertIn("@CA", attacked.split("Resolved player references:", 1)[0])
        self.assertNotIn("Anna [[B]]", attacked)

    def test_bare_first_name_is_annotated_from_the_bible(self):
        context = {
            "locations": [
                {
                    "code": "L1",
                    "name": "Low Gate",
                    "npcs": [
                        {"code": "C", "name": "Marta Venn"},
                        {"code": "D", "name": "Joel Pike"},
                    ],
                }
            ],
            "inventory": [],
            "events": [],
            "aliases": [],
            "settings": {"active_scene": {"present": ["D"], "interacting": ["C"], "keywords": ["gate"]}},
        }
        expanded = _expand_input_references(context, "Is the gate open, marta?")
        self.assertIn("marta = Marta Venn (@Cmarta_venn, C, NPC)", expanded)
        self.assertIn("interacting (replies to the player): Marta Venn [[C]]", expanded)
        self.assertIn("present (nearby, does not answer): Joel Pike [[D]]", expanded)
        self.assertTrue(_is_light_question(expanded))


class LightQuestionTests(unittest.TestCase):
    def test_grok_turns_default_to_low_reasoning(self):
        self.assertEqual(_grok_reasoning_effort("grok-4.7"), "low")
        self.assertIsNone(_grok_reasoning_effort("llama3.1"))

    def test_plain_question_skips_verifier(self):
        self.assertTrue(_is_light_question("what is your name?"))
        self.assertFalse(_is_light_question("I attack the guard"))
        draft = {
            "narration": "She tells you her name.",
            "scene_plan": {"goal": "answer", "focus_points": ["the question"]},
            "player": {},
        }
        policy = _verification_policy({}, "what is your name?", draft)
        self.assertEqual(policy["mode"], "skip_model_verifier")
        self.assertNotIn("draft_self_check_not_passed", policy["blockers"])
        asked = _verification_policy(
            {"turn_plan": {"primary_intent": "conversation", "verification_checks": ["npc_knowledge", "relationship_consistency"]}},
            "tell me your name",
            draft,
        )
        self.assertEqual(asked["mode"], "skip_model_verifier")

    def test_cast_toggles_are_separate(self):
        turn = parse_dsl_turn(
            "===NAR===\nMarta looks up.\n\n===OPS===\nCAST interacting C\nCAST present D\nCAST keyword gate\n"
        )
        self.assertEqual(turn["scene_cast"]["interacting"], ["C"])
        self.assertEqual(turn["scene_cast"]["present"], ["D"])
        self.assertEqual(turn["scene_cast"]["keywords"], ["gate"])


if __name__ == "__main__":
    unittest.main()
