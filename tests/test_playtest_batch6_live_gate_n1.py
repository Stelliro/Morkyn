"""
Live gate N1 (writer off, Qwen3 8B), judged on the verbatim live shapes.

The blind score for the new default found a leak, four invented people or
places, five prose/state mismatches and a companion who agreed to come but
never joined. Each class below is one engine defect those turns prove:

VenueNamesKeepTheirPlace   The venue-name pool built "{place}" from the first
                           word of the place name, so "The Refugees' Trail"
                           gave cast_options "The Kettle at The"; the draft
                           took it as the town's name, MOVE and LOC_NEW stored
                           it and an NPC was named "Mira Kettle" from it.
PoolNamesArePeople         "Li Ping", drawn from the engine's own name pool,
                           failed the person-name check ("Ping" read as the
                           verb "pings") and the repair renamed the merchant
                           "Fang" in the prose while the ops said Li Ping.
AppositiveIsTheNamedPerson "Mira, a wiry woman with a sharp gaze" seeded a
                           second person, Zihan the beekeeper, from Mira's own
                           description.
KnownPersonKeepsTheirPlace A repeat NPC_NEW for Mira with LOC "Mira's Scribe's
                           Office" (her planned, unbuilt workplace) minted that
                           place and moved her into it.
AcceptedInviteInTheReply   "Elias Thorn, come with me": he agreed in the next
                           quoted lines ("Come on, if you're determined to
                           follow..."), which name him only by "he", so he was
                           never shown going along and never joined.
PressingIsAnAct            "You press your palm against it, and the ground
                           beneath shudders" after "I crouch and examine the
                           symbols": a manipulation the player never chose.
NpcNewPlaceIsNotARole      NPC_NEW "Mira Kettle" "shopkeeper" "The Kettle at
                           The" stored the role "shopkeeper The Kettle at The".

Fixture: tests/fixtures/playtest_batch6_live_gate_n1.json, copied from
scratchpad\\smoke\\ab\\transcript_N1.json and the N1 model traces.
"""
from __future__ import annotations

import json
import os
import random
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn_n1gate_"))
os.environ.update(isolated_data_env(str(_TMP)))
for _key, _name in (
    ("AI_RPG_IDEA_BANK", "idea_bank.json"),
    ("AI_RPG_LAUNCHER_PREFS", "launcher_prefs.json"),
    ("AI_RPG_SKILL_LIBRARY", "skill_library.json"),
):
    os.environ.setdefault(_key, str(_TMP / _name))
os.environ.setdefault("AI_RPG_PACK_DIR", str(_TMP / "packs"))
assert "STELLIROS_WORKSHOP" not in os.environ["AI_RPG_DB"]
WRITER_OFF = {
    "AI_RPG_NARRATION_PIPELINE": "0",
    "AI_RPG_NARRATION_PIPELINE_CONSOLIDATE": "1",
    "AI_RPG_FAST_VERIFICATION": "1",
    "AI_RPG_DSL_SKIP_VERIFY": "1",
    "AI_RPG_DRAFT_MODE": "dsl",
}

from app import db, example_pools, scene_thread, turn_dsl, world  # noqa: E402
from app.db import connect  # noqa: E402
from app.llm import drop_invented_player_acts_text  # noqa: E402

LIVE = json.loads((ROOT / "tests" / "fixtures" / "playtest_batch6_live_gate_n1.json").read_text(encoding="utf-8"))
_CLOSED = {"the", "a", "an", "of", "at", "in", "on", "to", "by", "and", "or"}


def _seed(tag: str, places, here: int, npcs=()) -> None:
    os.environ["AI_RPG_DB"] = str(_TMP / f"{tag}.db")
    db.init_db()
    with connect() as conn:
        conn.execute("DELETE FROM npcs")
        for loc_id, name in places:
            if conn.execute("SELECT 1 FROM locations WHERE id = ?", (loc_id,)).fetchone():
                conn.execute("UPDATE locations SET name = ?, code = ? WHERE id = ?", (name, f"L{loc_id}", loc_id))
            else:
                conn.execute(
                    "INSERT INTO locations (id, code, name, summary) VALUES (?, ?, ?, '')", (loc_id, f"L{loc_id}", name)
                )
        for npc_id, code, name, role, loc in npcs:
            conn.execute(
                "INSERT INTO npcs (id, code, name, role, location_id) VALUES (?, ?, ?, ?, ?)",
                (npc_id, code, name, role, loc),
            )
        conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (here,))


class _WriterOff(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, WRITER_OFF)
        patcher.start()
        self.addCleanup(patcher.stop)


class VenueNamesKeepTheirPlace(_WriterOff):
    def test_live_place_with_an_article(self):
        place = LIVE["g2t4"]["current_location"]
        self.assertEqual(place, "The Refugees' Trail")
        self.assertIn("The Kettle at The", LIVE["g2t4"]["cast_options"]["venue_names"])
        for seed in range(200):
            name = example_pools._render_venue("The {noun} at {place}", {"place_name": place}, random.Random(seed), set())
            self.assertNotIn(name.split()[-1].lower(), _CLOSED, name)
            self.assertTrue(name.endswith(" at Refugees"), name)

    def test_lower_case_place_names_their_proper_word(self):
        name = example_pools._render_venue(
            "{place} {trade}", {"place_name": "the threshold of the Whispering Wastes"}, random.Random(3), set()
        )
        self.assertTrue(name.startswith("Whispering "), name)

    def test_no_draw_ends_on_a_closed_word(self):
        for place in ("The Refugees' Trail", "the edge of the Whispering Wastes", "Mudflat Shrine Path", "", "of the"):
            for seed in range(60):
                for name in example_pools.draw("venue_name", {"place_name": place}, 3, random.Random(seed)):
                    self.assertNotIn(name.split()[-1].lower(), _CLOSED, (place, name))


class PoolNamesArePeople(unittest.TestCase):
    def test_live_merchant_name(self):
        self.assertIn("Li Ping", LIVE["g1t5"]["cast_options"]["names"])
        self.assertIn('NPC_NEW: NAME "Li Ping"', LIVE["g1t5"]["raw_ops"])
        self.assertIn("Fang", LIVE["g1t5"]["final_narration"])  # the live rename
        self.assertTrue(world.is_plausible_person_name("Li Ping"))

    def test_every_pool_name_is_a_person(self):
        bad = []
        for culture, pools in example_pools._NAMES.items():
            for sex in ("female", "male"):
                for given in pools.get(sex, ()):
                    # A bare "Odd" reads as a description and stays refused; the
                    # full names below carry it.
                    if not world.is_plausible_person_name(given) and not world.is_generic_person_label(given):
                        bad.append(given)
                    for family in pools.get("family", ())[:12]:
                        name = example_pools._render_name(culture, given, family)
                        if not world.is_plausible_person_name(name):
                            bad.append(name)
        self.assertEqual(bad, [])

    def test_blurbs_and_codes_are_still_not_people(self):
        for text in ("System pings a local job", "AB", "L1", "a", "Hooded Figure", "pings"):
            self.assertFalse(world.is_plausible_person_name(text), text)


class AppositiveIsTheNamedPerson(_WriterOff):
    TEXT = LIVE["g1t1"]["final_narration"]

    def test_live_hints(self):
        hints = world._figure_hints(self.TEXT, ["Mira"])
        self.assertNotIn("a wiry woman", [h.lower() for h in hints])
        self.assertIn("the cloaked figure", [h.lower() for h in hints])

    def test_live_turn_seeds_no_second_mira(self):
        _seed("appos", [(1, "the threshold of the Whispering Wastes")], 1, [(1, "A", "Mira", "talisman scribe", 1)])
        with connect() as conn:
            result = {"npcs": [{"code": "A", "name": "Mira", "role": "talisman scribe"}]}
            created = world._ensure_npcs_from_narration(conn, result, self.TEXT, 1)
            names = [r[0] for r in conn.execute("SELECT name FROM npcs ORDER BY id")]
        self.assertEqual(created, [])
        self.assertEqual(names, ["Mira"])

    def test_a_stranger_is_still_a_face(self):
        hints = world._figure_hints("A wiry woman watches you from the stall. Mira is nowhere to be seen.", ["Mira"])
        self.assertIn("A wiry woman", hints)


class KnownPersonKeepsTheirPlace(_WriterOff):
    def test_live_repeat_npc_new_mints_no_place(self):
        self.assertIn('NPC_NEW: NAME "Mira", ROLE "talisman scribe", LOC "Mira\'s Scribe\'s Office"', LIVE["g1t3"]["raw_ops"])
        _seed(
            "known_loc",
            [(1, "the threshold of the Whispering Wastes"), (2, "the edge of the Whispering Wastes")],
            2,
            [(1, "A", "Mira", "talisman scribe", 2)],
        )
        turn = turn_dsl.ops_to_turn(
            LIVE["g1t3"]["draft_narration"], turn_dsl.parse_ops(LIVE["g1t3"]["raw_ops"]), LIVE["g1t3"]["input"]
        )
        mira = next(n for n in turn["npcs"] if n["name"] == "Mira")
        with connect() as conn:
            npc_id = world._upsert_npc(conn, dict(mira))
            places = [r[0] for r in conn.execute("SELECT name FROM locations ORDER BY id")]
            where = conn.execute("SELECT location_id FROM npcs WHERE id = ?", (npc_id,)).fetchone()[0]
        self.assertEqual(npc_id, 1)
        self.assertNotIn("Mira's Scribe's Office", places)
        self.assertEqual(where, 2)

    def test_known_person_still_moves_to_a_known_place(self):
        _seed("known_move", [(1, "Gate"), (2, "Yard")], 1, [(1, "A", "Mira", "scribe", 1)])
        with connect() as conn:
            world._upsert_npc(conn, {"name": "Mira", "location": "Yard", "role": "scribe"})
            self.assertEqual(conn.execute("SELECT location_id FROM npcs WHERE id = 1").fetchone()[0], 2)

    def test_a_new_person_at_a_new_place_is_unchanged(self):
        _seed("new_loc", [(1, "Gate")], 1)
        with connect() as conn:
            world._upsert_npc(conn, {"name": "Una Gilchrist", "location": "Lantern Yard", "role": "nurse"})
            places = [r[0] for r in conn.execute("SELECT name FROM locations ORDER BY id")]
        self.assertIn("Lantern Yard", places)


class AcceptedInviteInTheReply(unittest.TestCase):
    ASKED = [{"code": "A", "name": "Elias Thorn"}]

    def test_live_fixture(self):
        self.assertEqual(LIVE["g2t2"]["asked_along"], self.ASKED)
        self.assertIsNone(LIVE["g2t2"]["state_changes"]["party"])

    def test_live_reply_is_a_join(self):
        for key in ("draft_narration", "final_narration"):
            self.assertEqual(scene_thread.companions_shown(self.ASKED, LIVE["g2t2"][key]), self.ASKED, key)

    def test_refusal_in_the_reply_is_not_a_join(self):
        text = 'Elias Thorn folds his arms. "I won\'t go after them," he says. "Follow them yourself."'
        self.assertEqual(scene_thread.companions_shown(self.ASKED, text), [])

    def test_someone_else_following_is_not_his_join(self):
        text = "Elias Thorn watches the road. Mira nods and follows you down the path."
        self.assertEqual(scene_thread.companions_shown(self.ASKED, text), [])


class PressingIsAnAct(_WriterOff):
    def test_live_press(self):
        t = LIVE["g2t3"]
        self.assertIn("You press your palm against it", t["final_narration"])
        kept, dropped = drop_invented_player_acts_text(t["draft_narration"], t["input"])
        self.assertNotIn("press your palm", kept)
        self.assertTrue(any("press your palm" in d for d in dropped), dropped)
        self.assertIn("You notice a small indentation", kept)
        self.assertIn("You trace the symbols", kept)

    def test_asked_press_stays(self):
        text = "You press your palm against the indentation, and the ground beneath shudders slightly."
        kept, dropped = drop_invented_player_acts_text(text, "I press the indentation in the wall.")
        self.assertEqual(dropped, [])
        self.assertEqual(kept, text)

    def test_trying_the_door_covers_a_push(self):
        text = "You push the door, and it swings inward on groaning hinges."
        kept, dropped = drop_invented_player_acts_text(text, "I try to open the door.")
        self.assertEqual(dropped, [])


class NpcNewPlaceIsNotARole(unittest.TestCase):
    def test_live_positional_place(self):
        t = LIVE["g2t4"]
        turn = turn_dsl.ops_to_turn(t["draft_narration"], turn_dsl.parse_ops(t["raw_ops"]), t["input"])
        npc = turn["npcs"][0]
        self.assertEqual(npc["name"], "Mira Kettle")
        self.assertEqual(npc["role"], "shopkeeper")
        self.assertEqual(npc["location"], "The Kettle at The")
        self.assertNotIn("_place_candidates", npc)

    def test_a_capitalised_role_that_names_no_place_stays(self):
        turn = turn_dsl.ops_to_turn("Bo waits.", turn_dsl.parse_ops('NPC_NEW "Bo" "Night Watch" captain'), "")
        self.assertEqual(turn["npcs"][0]["role"], "Night Watch captain")
        self.assertEqual(turn["npcs"][0]["location"], "")


if __name__ == "__main__":
    unittest.main()
