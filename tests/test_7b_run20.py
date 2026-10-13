"""7B run 20 (Qwen2.5 7B on MLE, agent as player): a named thanks with a walk after it, others' acts,
a pronoun after a speech, a place only in the player's question, and a giver who was not there."""
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-7b-run20-"))
_ENV = isolated_data_env(str(_TMP))
_SAVED_ENV: dict[str, str | None] = {}

T1_LINE = ('"Late for what, Gunilda? Nobody told me I was expected." I look at the water creeping over the lower '
           'district and stay on the dry side of it.')
T1_PARAS = [
    "You stand on the cobblestone street. “Late for what, Gunilda? Nobody told me I was expected,” you say. "
    "You step back onto the higher ground.",
    "Idony looks at you, his expression a mix of curiosity and concern. “You’re right, you are late. The "
    "Gilded Heron is opening its doors. Gunilda Lacey is expecting you.” He gestures towards the inn.",
    "“Thanks, Idony. I’ll head there right away.” You start walking towards the inn, the sound of water "
    "lapping against the cobblestones. The Gilded Heron stands out among the quieter buildings.",
]
T4_LINE = ('"More responsibilities and no pay mentioned. That\'s the guild all over." I fold my arms. '
           '"Where do I find this Thaddeus, then - the harbour office?"')


def setUpModule():
    _SAVED_ENV.update({key: os.environ.get(key) for key in _ENV})
    os.environ.update(_ENV)


def tearDownModule():
    for key, value in _SAVED_ENV.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


class NamedThanksThenAWalk(unittest.TestCase):
    """T1: '"Thanks, Idony. I'll head there right away." You start walking towards the inn' shipped."""

    def test_line_dropped(self):
        from app.narration_pipeline import drop_invented_player_speech

        _kept, dropped = drop_invented_player_speech(list(T1_PARAS), T1_LINE)
        self.assertEqual(dropped, ["“Thanks, Idony. I’ll head there right away.”"])

    def test_scene_cut_at_idonys_line(self):
        from app import llm

        text = "\n\n".join(T1_PARAS)
        turn = {"narration": text, "narration_segments": [{"label": "paragraph", "text": p} for p in T1_PARAS]}
        out = llm._drop_player_overreach(turn, T1_LINE, "test", [])
        self.assertNotIn("start walking", out["narration"])
        self.assertIn("Gunilda Lacey is expecting you", out["narration"])

    def test_a_named_line_with_no_act_after_is_left_to_the_old_rule(self):
        from app.narration_pipeline import drop_invented_player_speech

        paras = T1_PARAS[:2] + ["“Thanks, Idony.” Idony nods and turns back to the forge."]
        _kept, dropped = drop_invented_player_speech(paras, T1_LINE)
        self.assertEqual(dropped, [])


class LookingAtTheWaterIsNotHiding(unittest.TestCase):
    """T1: "I look at the water creeping over the lower district" rolled stealth."""

    def test_triggers(self):
        from app.skill_checks import infer_check_from_action as infer

        self.assertIsNone(infer(T1_LINE, {}))
        self.assertEqual((infer("I creep along the wall.", {}) or {}).get("skill_code"), "stealth")


class PronounAfterTheSpeech(unittest.TestCase):
    """T1: 'her expression' was mended to 'his', but the next '... She gestures' was not."""

    def test_follow_on_sentence(self):
        from app.prose_state import repair_pinned_pronouns

        text = ("Idony looks at you, her expression a mix of curiosity and concern. “You’re right, you are "
                "late. Gunilda Lacey is expecting you.” She gestures towards the inn, The Gilded Heron [[L2]], "
                "its sign fluttering.")
        cast = [{"names": ["Idony Glover", "Idony"], "key": "he"}, {"names": ["Gunilda Lacey", "Gunilda"], "key": "she"}]
        fixed, notes = repair_pinned_pronouns(text, cast, not_people=["The Gilded Heron"])
        self.assertIn("his expression", fixed)
        self.assertIn("He gestures", fixed)
        self.assertEqual(len(notes), 2)


class PlaceOnlyInHerQuestion(unittest.TestCase):
    """T4: "the harbour office?" in her question kept a walk and a MOVE to a new Harbour Office."""

    def test_walk_not_asked(self):
        from app import llm

        self.assertFalse(llm._walk_asked("move toward the Harbour Office, the door standing open.", T4_LINE))

    def test_walk_cut_after_the_answer(self):
        from app import llm

        prose = ('She nods. "He\'s the harbour reeve, Thaddeus. You can find him in the office."\n\n'
                 "You thank her and move toward the Harbour Office, the door standing open.")
        point = llm._scene_cut_point(prose, T4_LINE)
        self.assertIsNotNone(point)
        self.assertEqual(point["family"], "movement")
        self.assertIn("You can find him in the office", point["npc_line"])

    def test_move_dropped(self):
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        prose = ('She nods. "He\'s the harbour reeve, Thaddeus. You can find him in the office." Idony looks up. '
                 '"Over there," he gestures toward a building with a sign that reads "Harbour Office."')
        with connect() as conn:
            result = {"narration": prose, "player": {"move_to_location": "Harbour Office"}}
            world.resolve_movement(conn, result, T4_LINE, intent="", narration=prose)
        self.assertFalse(result["player"].get("move_to_location"))


class GiverWhoWasNotThere(unittest.TestCase):
    """T4: "Salvage contracts" was filed under Wat Sallow, who was not in the scene; Thaddeus offered it."""

    def test_giver_is_the_stranger_who_spoke(self):
        from app import quest_parser

        narration = (
            "You fold your arms. “Where do I find this Thaddeus, then - the harbour office?” you ask.\n\n"
            "You go to the office. A man sits behind a desk. Thaddeus leans back, considering. \"We'll see. Come back "
            "with something substantial, and maybe I'll take you on for the salvage contracts.\""
        )
        reply = {"new": [{
            "title": "Salvage contracts", "giver": "B", "difficulty": "normal",
            "steps": [{"title": "Talk to Thaddeus"}],
            "evidence": "Thaddeus leans back, considering. \"We'll see. Come back with something substantial, and "
                        "maybe I'll take you on for the salvage contracts.\"",
            "offer_line": "We'll see. Come back with something substantial, and maybe I'll take you on for the salvage contracts.",
        }]}
        npcs = [{"id": 2, "code": "B", "name": "Wat Sallow", "role": "thresher"}]
        accepted, _rejected = quest_parser.validate_quest_changes(reply, narration=narration, player_input=T4_LINE, npcs=npcs)
        jobs = accepted.get("new") or []
        self.assertEqual(len(jobs), 1)
        self.assertNotEqual(jobs[0].get("giver_npc_id"), 2)
        self.assertEqual(jobs[0].get("giver"), "Thaddeus")


if __name__ == "__main__":
    unittest.main()
