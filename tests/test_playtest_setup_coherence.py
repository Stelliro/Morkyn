"""
Playtest #21: the character set up for game 2 contradicted itself.

Strings below are copied from the game-2 save
(data/campaign_slots/auto-ab564b3c-t00004/start.json and world.json): name
Miriam with a "she" backstory stored as sex male; a backstory arriving at "The
Empty Lot" while play began at Eldoria's Edge; appearance naming a leather
jerkin and sandals while the worn cards were boots, tunic and trousers; and a
small enchanted lantern in the backstory that never reached the inventory.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-setup-coherence-"))
os.environ.update(isolated_data_env(str(_TMP)))

from app import db, llm, setup_coherence as sc, world  # noqa: E402
from app.db import connect  # noqa: E402

BACKSTORY = (
    "Miriam Shaw, a stagehand with a knack for rigging and a passion for storytelling, was transported to the "
    "new world after a mysterious ferry accident. Upon arriving at The Empty Lot, she carries a tattered script "
    "folder and a small, enchanted lantern that flickers with a soft glow, seemingly drawn to her touch. In her "
    "former life, she worked as a carpenter's apprentice in a small village, crafting intricate traps and "
    "mechanisms. The village elder, sensing her aptitude, secretly trained her in ancient rigging techniques "
    "before her world ended in a ritual gone wrong. Now, she struggles to adapt to her new life, her skills and "
    "memories a double-edged sword in the harsh new world."
)
APPEARANCE = "torso: worn leather jerkin; feet: sturdy leather sandals; face: resolute expression"
CUSTOM_STYLE = (
    "In a land of mist-shrouded forests and storm-wracked coasts, the kingdom of Eldoria is ruled by a council "
    "of mages and warrior-princes."
)
GAME2 = {
    "player_name": "Miriam Shaw",
    "player_sex": "male",
    "player_age": "17",
    "previous_life_sex": "male",
    "backstory_mode": "reincarnated",
    "memory_policy": "remembers former life",
    "character_backstory": BACKSTORY,
    "appearance": APPEARANCE,
    "hair": "messy silver strands",
    "starter_equipment": "boots, tunic, trousers",
    "starter_gear": [
        {"name": "boots", "slot": "FEET", "required": True},
        {"name": "tunic", "slot": "TORSO", "required": True},
        {"name": "trousers", "slot": "LEGS", "required": True},
    ],
    "world_style": "frontier dark fantasy",
    "custom_style": CUSTOM_STYLE,
    "start_location": "Eldoria's Edge",
    "tech_level": "medieval",
    "magic_level": "rare",
    "special_ability_origin": "none",
}


class SexAndPronouns(unittest.TestCase):
    def test_the_backstory_reads_female(self):
        self.assertEqual(sc.pronoun_sex(BACKSTORY), "female")

    def test_a_stray_pronoun_for_someone_else_does_not_flip_it(self):
        story = "She grew up mending nets. Her uncle sold his boat; she kept her knife and her temper."
        self.assertEqual(sc.pronoun_sex(story), "female")
        self.assertEqual(sc.pronoun_sex("They kept their head down."), "")

    def test_the_chosen_sex_is_flagged_not_changed(self):
        warnings = sc.identity_warnings(GAME2)
        self.assertEqual([w["code"] for w in warnings], ["sex_vs_backstory_pronouns"])
        self.assertIn("male", warnings[0]["message"])
        self.assertEqual(sc.infer_player_sex(GAME2), "")

    def test_an_unset_sex_is_inferred_from_the_pronouns(self):
        self.assertEqual(sc.infer_player_sex({**GAME2, "player_sex": ""}), "female")
        self.assertEqual(sc.identity_warnings({**GAME2, "player_sex": "female"}), [])

    def test_a_pool_name_of_the_other_sex_is_flagged(self):
        from app.example_pools import _NAMES

        female_name = _NAMES["common"]["female"][0]
        self.assertEqual(sc.name_sex(female_name), "female")
        codes = [w["code"] for w in sc.identity_warnings({"player_name": female_name, "player_sex": "male"})]
        self.assertEqual(codes, ["sex_vs_name"])

    def test_the_identity_check_route(self):
        from app.main import IdentityCheckRequest, api_setup_identity_check

        body = {k: GAME2[k] for k in ("player_name", "player_sex", "character_backstory")}
        got = api_setup_identity_check(IdentityCheckRequest(**body))
        self.assertEqual(got["warnings"][0]["code"], "sex_vs_backstory_pronouns")
        got = api_setup_identity_check(IdentityCheckRequest(**{**body, "player_sex": ""}))
        self.assertEqual((got["warnings"], got["inferred_sex"]), ([], "female"))


class BackstoryAsk(unittest.TestCase):
    def _prompt(self, current):
        captured = {}

        def fake_chat(system, user, **kwargs):
            captured.setdefault("user", user)
            raise RuntimeError("stop after prompt build")

        original = llm._chat_json
        llm._chat_json = fake_chat
        try:
            llm.generate_setup_randomization("field:character_backstory", current)
        except Exception:
            pass
        finally:
            llm._chat_json = original
        return json.loads(captured["user"])

    def test_the_ask_carries_the_sex_pronouns(self):
        prompt = self._prompt({**GAME2, "character_backstory": ""})
        self.assertEqual(prompt["pronouns"], "he/him")
        self.assertNotIn("they/their", json.dumps(prompt))
        prompt = self._prompt({**GAME2, "player_sex": "female", "character_backstory": ""})
        self.assertEqual(prompt["pronouns"], "she/her")

    def test_a_rolled_backstory_arrives_at_start_location(self):
        out = llm._cohere_identity_fields(GAME2, {"character_backstory": BACKSTORY})
        self.assertIn("Upon arriving at Eldoria's Edge, she carries", out["character_backstory"])
        self.assertNotIn("Empty Lot", out["character_backstory"])

    def test_a_rolled_name_of_the_other_sex_is_redrawn(self):
        from app.example_pools import _NAMES

        female_name = _NAMES["common"]["female"][0] + " Shaw"
        out = llm._cohere_identity_fields({**GAME2, "player_name": ""}, {"player_name": female_name})
        self.assertNotEqual(out["player_name"], female_name)
        self.assertIn(sc.name_sex(out["player_name"]), ("", "male"))


class Arrival(unittest.TestCase):
    def test_the_named_arrival_becomes_the_start_location(self):
        self.assertEqual(sc.arrival_place(BACKSTORY), "The Empty Lot")
        story, changed = sc.align_backstory_arrival(BACKSTORY, "Eldoria's Edge")
        self.assertTrue(changed)
        self.assertEqual(sc.arrival_place(story), "Eldoria's Edge")

    def test_a_region_containing_the_start_is_left_alone(self):
        story = "She woke in Eldoria with nothing."
        self.assertEqual(sc.align_backstory_arrival(story, "Eldoria's Edge"), (story, False))

    def test_the_coherence_pass_moves_the_backstory_with_the_place(self):
        current = {**GAME2, "start_location": "The Empty Lot"}
        fields = llm._cohere_reviewed_arrival(current, {"start_location": "Eldoria's Edge"}, set())
        self.assertIn("arriving at Eldoria's Edge", fields["character_backstory"])
        locked = llm._cohere_reviewed_arrival(current, {"start_location": "Eldoria's Edge"}, {"character_backstory"})
        self.assertNotIn("start_location", locked)


class GearAndItems(unittest.TestCase):
    def test_unnamed_basics_take_the_appearance_clothes(self):
        gear, named = sc.name_basics_from_appearance(GAME2["starter_gear"], APPEARANCE)
        by_slot = {g["slot"]: g["name"] for g in gear}
        self.assertEqual(by_slot["TORSO"], "worn leather jerkin")
        self.assertEqual(by_slot["FEET"], "sturdy leather sandals")
        self.assertEqual(by_slot["LEGS"], "trousers")  # appearance names no legs

    def test_named_cards_win_and_appearance_follows(self):
        cards = [
            {"name": "leather boots", "slot": "FEET"},
            {"name": "worn leather jerkin", "slot": "TORSO"},
            {"name": "wool trousers", "slot": "LEGS"},
        ]
        look, changed = sc.appearance_from_gear(APPEARANCE, cards)
        self.assertEqual(look, "torso: worn leather jerkin; feet: leather boots; face: resolute expression; legs: wool trousers")
        self.assertEqual(sorted(changed), ["FEET", "LEGS"])

    def test_the_backstory_items_are_read(self):
        self.assertEqual(sc.backstory_carried_items(BACKSTORY), ["tattered script folder", "small enchanted lantern"])
        self.assertEqual(sc.backstory_carried_items("He carries a grudge and himself with pride."), [])


class StartAgrees(unittest.TestCase):
    def _start(self, **over):
        db.init_db()
        world.start_playthrough(json.loads(json.dumps({**GAME2, **over})))
        with connect() as conn:
            player = dict(conn.execute("SELECT * FROM player WHERE id = 1").fetchone())
            items = [dict(r) for r in conn.execute("SELECT name, equipped_slot, stat_modifiers FROM inventory").fetchall()]
            options = json.loads(conn.execute("SELECT value FROM settings WHERE key = 'playthrough_options'").fetchone()[0])
        return player, items, options

    def test_game2_setup_starts_coherent(self):
        player, items, options = self._start()
        # The player's chosen sex stands; the setup page flagged it before Start.
        self.assertEqual(player["sex"], "male")
        self.assertIn("arriving at Eldoria's Edge", player["backstory"])
        self.assertNotIn("Empty Lot", player["backstory"])
        worn = {i["equipped_slot"]: i["name"] for i in items if i["equipped_slot"]}
        self.assertEqual(worn["TORSO"], "worn leather jerkin")
        self.assertEqual(worn["FEET"], "sturdy leather sandals")
        for slot in ("TORSO", "FEET", "LEGS"):
            self.assertIn(worn[slot], options["appearance"])
        carried = {i["name"]: i for i in items if not i["equipped_slot"]}
        self.assertIn("tattered script folder", carried)
        lantern = [name for name in carried if "lantern" in name]
        self.assertEqual(len(lantern), 1, carried)
        self.assertEqual(json.loads(carried[lantern[0]]["stat_modifiers"]), {})

    def test_an_unset_sex_is_filled_from_the_backstory(self):
        player, _items, _options = self._start(player_sex="")
        self.assertEqual(player["sex"], "female")


if __name__ == "__main__":
    unittest.main()
