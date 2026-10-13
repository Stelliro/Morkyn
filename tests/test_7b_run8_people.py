"""7B run 8, T0: a code glued to a name, a note as a job, and one woman stored twice."""
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-7b-run8-people-"))
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


# Run 8's opening draft, shortened; the ops are as the 7B wrote them.
NOTE = "works_at the Wren's Rest, reliable and concerned for your safety"
DRAFT = (
    "===NAR===\n"
    "You stand on the salt-scented flats of Saltmarrow, the harbour town that the sea abandoned forty years ago.\n\n"
    "To your right, the Wren's Rest, a modest inn, beckons with the promise of warmth and rest. Linnet Eastlake, "
    "the hayward, is sweeping the path in front of the Wren's Rest, her broom stirring up clouds of fine dust.\n\n"
    "\"Good morning, Isk,\" Linnet calls out, her voice carrying the weight of familiarity. \"The tide will turn "
    "soon. You best be getting your gear ready.\"\n\n"
    "\"Madoc says the tide will be a little stronger today,\" she says. \"Be careful out there, Isk.\"\n\n"
    "===OPS===\n"
    "GOAL \"to prepare for the upcoming tide and salvage operation\"\n"
    "TALK \"L1 Linnet Eastlake\" \"You need to be ready, Isk.\"\n"
    f"NPC_NOTE \"L1 Linnet Eastlake\" \"knows your name, {NOTE[9:]}\"\n"
    f"NPC_NEW \"L1 Linnet Eastlake\" \"{NOTE}\"\n"
    "CAST \"interacting\" \"L1 Linnet Eastlake\"\n"
)


class CodesAreNotNames(unittest.TestCase):
    def test_strip_name_codes(self):
        from app.turn_dsl import _strip_name_codes as strip

        self.assertEqual(strip("L1 Linnet Eastlake"), "Linnet Eastlake")
        self.assertEqual(strip("[[B]] Linnet Eastlake [[B]]"), "Linnet Eastlake")
        self.assertEqual(strip("Oldfield B"), "Oldfield")
        self.assertEqual(strip("Linnet Eastlake I4"), "Linnet Eastlake")
        # A lone code stays a code; a roman numeral and an ordinary name stay whole.
        self.assertEqual(strip("L1"), "L1")
        self.assertEqual(strip("Henry V"), "Henry V")
        self.assertEqual(strip("Mira Kettle"), "Mira Kettle")
        self.assertEqual(strip("A"), "A")

    def test_the_draft_parses_to_one_named_person(self):
        from app.turn_dsl import parse_dsl_turn

        turn = parse_dsl_turn(DRAFT)
        [npc] = turn["npcs"]
        self.assertEqual(npc["name"], "Linnet Eastlake")
        # The note is what is known about her, not her job.
        self.assertNotIn("works_at", npc["role"])
        self.assertNotIn(",", npc["role"])
        self.assertIn("Wren's Rest", npc["summary"])
        # A name in TALK's code slot stays a name, never the code "LINNET EASTLAKE".
        self.assertEqual(turn["conversations"][0]["npc_code"], "Linnet Eastlake")
        self.assertNotIn("L1", turn["scene_cast"]["interacting"])
        self.assertEqual(turn["scene_cast"]["interacting"], ["Linnet Eastlake"])
        update = turn["index_updates"][0]
        self.assertEqual(update["name"], "Linnet Eastlake")

    def test_an_ordinary_role_is_kept(self):
        from app.turn_dsl import parse_dsl_turn

        turn = parse_dsl_turn("===NAR===\nSimon Pennick works on a wheel.\n\n===OPS===\nNPC_NEW \"Simon Pennick\" \"wheelwright\" L1\n")
        self.assertEqual(turn["npcs"][0]["role"], "wheelwright")


class SplitNameJoined(unittest.TestCase):
    def test_tag_inside_a_full_name_goes_after_it(self):
        from app.llm import _join_split_names

        self.assertEqual(
            _join_split_names("Linnet [[B]] Eastlake, the hayward, is sweeping.", {"A": "Linnet Eastlake"}),
            "Linnet Eastlake [[A]], the hayward, is sweeping.",
        )
        self.assertEqual(
            _join_split_names("Linnet [[A]] Eastlake [[A]] nods.", {"A": "Linnet Eastlake"}),
            "Linnet Eastlake [[A]] nods.",
        )
        # A first name followed by another word is left alone.
        self.assertEqual(
            _join_split_names("Linnet [[A]] smiles.", {"A": "Linnet Eastlake"}),
            "Linnet [[A]] smiles.",
        )


class OneWomanOneRow(unittest.TestCase):
    """apply_turn on the opening: one Linnet, named and with the prose's job."""

    def setUp(self):
        from app import db, rng, world

        db.init_db()
        rng.reset_seed_cache()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})

    def test_opening_stores_one_linnet(self):
        from app import db, world
        from app.turn_dsl import parse_dsl_turn

        turn = parse_dsl_turn(DRAFT)
        turn["self_check"] = {"passed": True, "issues_found": [], "corrections_made": []}
        turn["turn_summary"] = "opening"
        world.apply_turn(turn, "", input_kind="opening")
        with db.connect() as conn:
            rows = [dict(r) for r in conn.execute("SELECT code, name, role FROM npcs")]
        linnets = [r for r in rows if "linnet" in r["name"].lower()]
        self.assertEqual(len(linnets), 1, rows)
        self.assertEqual(linnets[0]["name"], "Linnet Eastlake")
        self.assertEqual(linnets[0]["role"], "hayward")
        text = world._narration_text(turn)
        self.assertNotIn("[[L1]] Linnet", text)
        self.assertNotRegex(text, r"Linnet \[\[[A-Z]+\]\] Eastlake")


if __name__ == "__main__":
    unittest.main()
