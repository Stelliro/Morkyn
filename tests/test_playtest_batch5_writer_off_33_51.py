"""
Playtest #33 / #34 / #35 / #50 / #51, judged on the live writer-off A/B shapes.

#50  One shop became two rows on a going-in turn: a MOVE naming the shop was read
     as the street outside it and "<Name> Shop" was minted inside; a LOC_NEW and
     the doorway rule's "<Place> General Store" were both stored and the player
     went into the invented one.
#33  The companion carried over the shop door as the only one who answers, so
     the draft cast them as the shopkeeper.
#34  An opening NPC_NEW the prose never shows was stored as a full person.
#35  Split fact titles ended mid-clause ("Frontier dark fantasy where thin").
#51  "Come along" put the companion on the scene thread but never in the party.

Live texts are copied verbatim into tests/fixtures/playtest_batch5_writer_off.json
from scratchpad\\smoke\\ab and batch4_r2.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn_b5wo_"))
os.environ.update(isolated_data_env(str(_TMP)))
for _key, _name in (
    ("AI_RPG_IDEA_BANK", "idea_bank.json"),
    ("AI_RPG_LAUNCHER_PREFS", "launcher_prefs.json"),
    ("AI_RPG_SKILL_LIBRARY", "skill_library.json"),
):
    os.environ.setdefault(_key, str(_TMP / _name))
os.environ.setdefault("AI_RPG_PACK_DIR", str(_TMP / "packs"))
assert "STELLIROS_WORKSHOP" not in os.environ["AI_RPG_DB"]
# The user's launcher env: the paragraph writer is off. Patched per test so
# the rest of the suite keeps its own env.
WRITER_OFF = {
    "AI_RPG_NARRATION_PIPELINE": "0",
    "AI_RPG_NARRATION_PIPELINE_CONSOLIDATE": "1",
    "AI_RPG_FAST_VERIFICATION": "1",
    "AI_RPG_DSL_SKIP_VERIFY": "1",
    "AI_RPG_DRAFT_MODE": "dsl",
}

from app import conversation as cv  # noqa: E402
from app import db, scene_thread, turn_dsl, venues, world, world_facts  # noqa: E402
from app.db import connect  # noqa: E402
from app.party import get_party, init_party  # noqa: E402

LIVE = json.loads((ROOT / "tests" / "fixtures" / "playtest_batch5_writer_off.json").read_text(encoding="utf-8"))


def _seed(tag: str, places, here: int, npcs=()) -> None:
    os.environ["AI_RPG_DB"] = str(_TMP / f"{tag}.db")
    db.init_db()
    with connect() as conn:
        conn.execute("DELETE FROM npcs")
        for loc_id, name, parent, kind in places:
            if conn.execute("SELECT 1 FROM locations WHERE id = ?", (loc_id,)).fetchone():
                conn.execute(
                    "UPDATE locations SET name = ?, code = ?, parent_id = ?, kind = ?, keeper_npc_id = 0 WHERE id = ?",
                    (name, f"L{loc_id}", parent, kind, loc_id),
                )
            else:
                conn.execute(
                    "INSERT INTO locations (id, code, name, summary, parent_id, kind) VALUES (?, ?, ?, '', ?, ?)",
                    (loc_id, f"L{loc_id}", name, parent, kind),
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
        self.addCleanup(patcher.stop)  # also restores AI_RPG_DB after _seed


def _rows(conn):
    return [tuple(r) for r in conn.execute("SELECT id, name, kind, parent_id FROM locations ORDER BY id")]


class OneShopPerEntry(_WriterOff):
    """#50 and the #33 venue-name remainder."""

    def test_move_names_the_shop_itself(self):
        # ab/B/g1 T5: MOVE "The Hare and Goose"; the sign reads *The Hare and Goose*.
        shape = LIVE["ab_B_g1_t5"]
        _seed("b1", [(1, "the threshold of the Whispering Wastes", 0, ""), (2, "The Merchant's Cart", 0, ""),
                     (3, "The Fissure's Edge", 0, "")], 1, [(1, "A", "Lin Zhuo", "gleaner", 1)])
        with connect() as conn:
            result = {"player": {"move_to_location": "The Hare and Goose"}}
            report = world.resolve_movement(conn, result, shape["input"], intent="travel", narration=shape["narration"])
            rows = _rows(conn)
        self.assertEqual(result["player"]["move_to_location"], "The Hare and Goose")
        self.assertEqual(report["destination"], "The Hare and Goose")
        self.assertNotIn("The Hare and Goose Shop", [r[1] for r in rows])
        shop = [r for r in rows if r[1] == "The Hare and Goose"]
        self.assertEqual(len(shop), 1, rows)
        self.assertTrue(shop[0][2], rows)  # a venue, with a kind
        self.assertEqual(shop[0][3], 1, rows)  # inside the place the player stands in

    def test_loc_new_shop_is_the_one_entered(self):
        # ab/B/g2 T5: LOC_NEW "Trask and Daughters", no MOVE; the sign reads "Trask and Daughters."
        shape = LIVE["ab_B_g2_t5"]
        _seed("b2", [(1, "Mudflat Shrine Path", 0, ""), (2, "The Hollow Trail", 0, ""), (3, "The Ridge", 0, "")], 3,
              [(1, "A", "Kendra Sallow", "stagecoach guard", 3)])
        with connect() as conn:
            loc_new = {"name": "Trask and Daughters", "summary": "a modest storefront"}
            result = {"player": {}, "locations": [loc_new]}
            report = world.resolve_movement(conn, result, shape["input"], intent="travel", narration=shape["narration"])
            self.assertTrue(loc_new.get("_venue_consumed"))
            # apply_turn's LOC_NEW loop: an upsert of the same name finds the venue.
            world._upsert_location(conn, "Trask and Daughters", "a modest storefront")
            rows = _rows(conn)
        self.assertEqual(report["destination"], "Trask and Daughters")
        self.assertEqual(result["player"]["move_to_location"], "Trask and Daughters")
        self.assertNotIn("The Ridge General Store", [r[1] for r in rows])
        self.assertEqual([r for r in rows if r[1] == "Trask and Daughters"][0][3], 3, rows)
        self.assertEqual(len(rows), 4, rows)

    def test_sign_name_keeps_its_own_trade(self):
        # batch4_r2 g1 T5: "The sign above the door reads *Blind Pike Pharmacy*"; the player said "shop".
        shape = LIVE["r2_g1_t5"]
        _seed("r1", [(1, "Whispering Range's edge", 0, ""), (2, "The Stag at Whispering", 0, ""),
                     (3, "The Foundry at Thornreach", 0, "")], 3,
              [(1, "A", "Ulric Tolley", "omnibus driver", 3), (2, "B", "Delphine Goodwin", "foundry worker", 3)])
        with connect() as conn:
            result = {"player": {}, "locations": [{"name": "Blind Pike Pharmacy"}]}
            report = world.resolve_movement(conn, result, shape["input"], intent="travel", narration=shape["narration"])
            rows = _rows(conn)
        self.assertEqual(report["destination"], "Blind Pike Pharmacy")
        self.assertNotIn("The Foundry at Thornreach General Store", [r[1] for r in rows])
        self.assertEqual([r for r in rows if r[1] == "Blind Pike Pharmacy"][0][2:], ("pharmacy", 3), rows)

    def test_parent_named_in_the_line_holds_the_shop(self):
        # batch4_r2 g2 T5: "walk back to the outskirts and go inside the first trading post".
        shape = LIVE["r2_g2_t5"]
        _seed("r2", [(1, "Ashfall Outskirts of Veldrune", 0, ""), (2, "Red Shears Dry Goods", 1, "general_store"),
                     (3, "Haze Entrance", 0, "")], 3)
        with connect() as conn:
            result = {"player": {"move_to_location": "First Trading Post"}}
            report = world.resolve_movement(conn, result, shape["input"], intent="travel", narration=shape["narration"])
            rows = _rows(conn)
        self.assertEqual(report.get("via"), "Ashfall Outskirts of Veldrune")
        self.assertEqual([r for r in rows if r[1] == "First Trading Post"][0][3], 1, rows)

    def test_move_to_a_place_named_in_the_line_still_goes_through_it(self):
        # The #33 shape the via rule exists for: the MOVE is the settlement the player names.
        _seed("via", [(1, "Mosswake Gate", 0, "")], 1)
        nar = ("You follow the road to the Spindle at Edge. You push open the door and step into the first shop "
               "you find, its shelves stacked with tinned goods.")
        with connect() as conn:
            result = {"player": {"move_to_location": "The Spindle at Edge"}}
            report = world.resolve_movement(
                conn, result, "I head for the Spindle at Edge and go inside the first shop.", intent="travel", narration=nar
            )
        self.assertEqual(report.get("rule"), "venue_via")
        self.assertEqual(report.get("via"), "The Spindle at Edge")

    def test_sign_names(self):
        self.assertEqual(venues.sign_name(LIVE["ab_B_g1_t5"]["narration"]), "The Hare and Goose")
        self.assertEqual(venues.sign_name(LIVE["ab_B_g2_t5"]["narration"]), "Trask and Daughters")
        self.assertEqual(venues.sign_name(LIVE["r2_g1_t5"]["narration"]), "Blind Pike Pharmacy")
        self.assertEqual(venues.sign_name("A sign hangs crooked over the door."), "")


class CompanionIsNotTheShopkeeper(_WriterOff):
    """#33 remainder: the draft is no longer told the companion alone answers in the shop."""

    CTX = {
        "current_location": {"id": 3, "code": "L3"},
        "locations": [{"id": 3, "code": "L3", "npcs": [{"id": 1, "code": "A", "name": "Kendra Sallow", "role": "stagecoach guard"}]}],
        "settings": {},
    }
    STATE = {"target": ["A"], "why": "partner", "here": ["A"], "location": "L3"}

    def test_live_shop_entries(self):
        for key in ("ab_B_g1_t5", "ab_B_g2_t5", "r2_g1_t5", "r2_g2_t5"):
            r = cv.resolve(self.CTX, LIVE[key]["input"], dict(self.STATE))
            note = cv.model_note(r)
            self.assertEqual(r["addressed"], [], key)
            self.assertEqual(r["rule"], "venue", key)
            self.assertNotIn("Only Kendra", note, key)
            self.assertIn("works there", note, key)
            self.assertIn("Kendra Sallow [[A]]", note, key)  # listening, a visitor
            self.assertEqual(cv.world_view(r)["listening"], [{"name": "Kendra Sallow", "code": "A"}])

    def test_talking_to_the_companion_still_goes_to_them(self):
        for line in ("Come with me into the shop.", "Kendra, let's go into the shop.", "Do you know what they sell in that shop?"):
            r = cv.resolve(self.CTX, line, dict(self.STATE))
            self.assertEqual(r["addressed"], ["A"], line)

    def test_open_ground_is_not_a_venue(self):
        r = cv.resolve(self.CTX, "I go into the forest.", dict(self.STATE))
        self.assertEqual(r["rule"], "partner")


class NpcNewMustBeShown(_WriterOff):
    """#34 remainder."""

    def _collect(self, key, narration=None):
        turn = turn_dsl.parse_dsl_turn(LIVE[key], "")
        nar = narration if narration is not None else (turn.get("narration") or "")
        _seed(key, [(1, "Here", 0, "")], 1)
        with connect() as conn:
            return world._npcs_shown_in_prose(conn, world._collect_npcs_from_turn_result(turn), nar)

    def test_unshown_name_is_bound_to_the_one_figure(self):
        kept = self._collect("ab_B_g1_opening_draft")
        self.assertEqual([n["name"] for n in kept], ["Lin Zhuo"])
        self.assertIn("lone figure in a tattered cloak", kept[0]["summary"])

    def test_unshown_name_with_no_figure_for_it_is_dropped(self):
        # ab/B/g2 final opening prose: a man and a lone figure, no stagecoach guard, no Kendra.
        self.assertEqual(self._collect("ab_B_g2_opening_draft", LIVE["ab_B_g2_t0"]["narration"]), [])
        self.assertEqual(self._collect("ab_A_g2_opening_draft"), [])

    def test_role_in_the_figure_sentence_binds(self):
        # ab/A/g1: "The trader at the post, a woman with a sharp gaze..."
        kept = self._collect("ab_A_g1_opening_draft", LIVE["ab_A_g1_t0"]["narration"])
        self.assertEqual([n["name"] for n in kept], ["Mira"])
        self.assertIn("trader at the post", kept[0]["summary"])

    def test_named_and_known_people_are_kept(self):
        _seed("known", [(1, "Here", 0, "")], 1, [(1, "A", "Old Brann", "smith", 1)])
        with connect() as conn:
            npcs = [{"name": "Old Brann", "code": "A"}, {"name": "Tova Reyes", "role": "ferrier"}]
            kept = world._npcs_shown_in_prose(conn, npcs, "Tova leans on the rail and waves you over.")
        self.assertEqual([n["name"] for n in kept], ["Old Brann", "Tova Reyes"])

    def test_the_ask_says_npc_new_is_for_someone_shown(self):
        prompt = turn_dsl.DSL_SYSTEM_PROMPT
        self.assertIn("NPC_NEW records someone ===NAR=== shows", prompt)
        line = prompt[prompt.index("NPC_NEW records someone"):][:200]
        self.assertNotRegex(line, r'"[A-Z][a-z]+')  # no example names (#39)


class FactTitlesEndOnANoun(_WriterOff):
    """#35 remainder: the five live split texts."""

    CASES = {
        "Frontier dark fantasy where thin law and harsh weather define survival.": "Frontier dark fantasy",
        "Small settlements struggle with scarce resources, and magic is whispered rumor.": "Small settlements",
        "The tone is grounded, with a focus on fair challenges and narrative stakes, where each level of mastery "
        "unlocks new responsibilities and dangers": "Grounded tone",
        "ensuring that strength is not inherited but earned through perseverance and calculated growth.":
            "Strength earned through perseverance",
        "In a world where magic is whispered and power is earned through risk and training, the land of Elyndor "
        "thrives on a balance of medieval technology and cultivation magic.": "Land of Elyndor thrives",
    }

    def test_live_titles(self):
        for text, want in self.CASES.items():
            self.assertEqual(world_facts._title_for(text), want, text)


class ComeAlongJoinsTheParty(_WriterOff):
    """#51."""

    LINE = LIVE["ab_A_g1_t2"]["input"]

    def _turn(self, tag):
        _seed(tag, [(1, "Mosswake Gate", 0, ""), (2, "The Wastes", 0, "")], 1, [(1, "A", "Mira", "trader", 1)])
        ctx = {
            "current_location": {"id": 1, "code": "L1"},
            "locations": [{"id": 1, "code": "L1", "npcs": [{"id": 1, "code": "A", "name": "Mira"}]}],
            "settings": {},
        }
        return scene_thread.begin_turn(ctx, self.LINE, {"addressed": ["A"], "names": {"A": "Mira"}})

    def test_live_invite_joins(self):
        turn_thread = self._turn("party_join")
        with connect() as conn:
            init_party(conn)
            thread = scene_thread.update_after_turn(
                conn, turn_thread=turn_thread, quest_report={}, narration=LIVE["ab_A_g1_t2"]["narration"],
                player_input=self.LINE, turn=3,
            )
            party = get_party(conn=conn)
        self.assertEqual(thread["with"], [{"code": "A", "name": "Mira"}])
        self.assertEqual([(m["npc_name"], m["role"], m["joined_turn"]) for m in party], [("Mira", "companion", 3)])

    def test_left_behind_leaves(self):
        turn_thread = self._turn("party_leave")
        with connect() as conn:
            init_party(conn)
            scene_thread.update_after_turn(
                conn, turn_thread=turn_thread, quest_report={}, narration=LIVE["ab_A_g1_t2"]["narration"],
                player_input=self.LINE, turn=3,
            )
            # Next turn the player walks on and the prose shows Mira staying behind.
            conn.execute("UPDATE player SET current_location_id = 2 WHERE id = 1")
            scene_thread.update_after_turn(
                conn, turn_thread=None, quest_report={}, narration="Mira stays behind at the gate, arms folded.",
                player_input="I walk on into the wastes.", turn=4,
            )
            party = get_party(conn=conn)
        self.assertEqual(party, [])

    def test_a_refusal_is_not_a_join(self):
        turn_thread = self._turn("party_refuse")
        with connect() as conn:
            init_party(conn)
            scene_thread.update_after_turn(
                conn, turn_thread=turn_thread, quest_report={}, narration="Mira shakes her head. \"I won't go out there.\"",
                player_input=self.LINE, turn=3,
            )
            self.assertEqual(get_party(conn=conn), [])


if __name__ == "__main__":
    unittest.main()
