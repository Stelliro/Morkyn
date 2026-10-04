"""
Playtest #16: Aria behaved as if Elara's herb shop were hers.

Game 2 ("Eldoria's Edge"). world.db ended with one location. Turn 3's draft
walked the player and Aria into a herb shop ("Elara ... gestures for you to
come in. Inside, the shop is cluttered ... herbs and spices") with no MOVE,
so the shop was never a place and nobody kept it. The draft wrote
`NPC_NEW Elara "Elara" ROLE message runner LOC L1` and Elara was stored as a
"message". Turn 4 had Aria the baker at the counter: "The herbs here are
mostly for sale". Turn 2's depth retry wrote "a cartter [[C]]" and the name
repair made it "a cartter Hearthbin [[C]]" for C, filed as a message runner.

These replay those shapes:
  (a) prose that takes the player indoors with no MOVE makes the building a
      venue (child of the place), moves the player in, binds who let them in
      as keeper and brings in who came along; the draft is asked for the
      MOVE on every turn, and the #6c drop spares a shown entry;
  (b) a trade gets its own workplace venue, kept by that NPC, and the draft
      and writer are told whose place is whose;
  (c) an unquoted multi-word ROLE keeps every word up to the next flag;
  (d) the job in front of a person's tag is the stored one; an appositive
      that differs is reported on the turn.
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-venues-roles-"))
os.environ.update(isolated_data_env(str(_TMP)))
os.environ.update(
    {
        "AI_RPG_PACK_DIR": str(_TMP / "packs"),
        "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
    }
)

from app import db, llm, venues, world  # noqa: E402
from app.db import connect  # noqa: E402
from app.turn_dsl import DSL_SYSTEM_PROMPT, build_dsl_user_prompt, ops_to_turn, parse_ops  # noqa: E402

TURN3_INPUT = (
    'i say to @Caria "want to come with me? if anything happens you should go and get help though, '
    'but im just as curious"'
)
# Turn 3's final narration, tail as the trace recorded it.
TURN3_FINAL = (
    "Suddenly, the hooded figure disappears into a narrow alleyway. You exchange a glance with Aria [[A]], and "
    "she nods for you to follow. The hooded figure disappears into a small shop, and you hesitate. Aria [[A]] "
    "steps forward and knocks gently on the door. After a moment, the door creaks open, revealing a woman with "
    "a concerned look on her face.\n\n"
    "\"Can I help you?\" she asks, her voice tinged with suspicion. Aria [[A]] introduces herself and explains "
    "that you saw a hooded figure enter the shop. Elara nods and gestures for you to come in. Inside, the shop "
    "is cluttered with various goods, and the air is thick with the scent of herbs and spices."
)
TURN3_OPS = 'NPC_NEW Elara "Elara" ROLE message runner LOC L1\nTALK A "We saw a hooded figure enter here."'
TURN4_INPUT = "Examine the herbs on the shop counter"


def seed_edge() -> None:
    db.init_db()
    with connect() as conn:
        conn.execute("UPDATE player SET current_location_id = 1 WHERE id = 1")
        conn.execute("DELETE FROM npcs")
        conn.execute("DELETE FROM locations WHERE id != 1")
        conn.execute("DELETE FROM settings WHERE key IN ('active_scene', 'conversation', 'scene_thread')")
        conn.execute(
            "UPDATE locations SET name = 'Eldoria''s Edge', summary = 'Starting location for a frontier dark "
            "fantasy playthrough.', parent_id = 0, kind = '', settlement_size = '', keeper_npc_id = 0 WHERE id = 1"
        )
        for code, name, role in (("A", "Aria", "baker"), ("B", "Dockwick", "well keeper"), ("C", "Hearthbin", "message runner")):
            conn.execute("INSERT INTO npcs (code, location_id, name, role) VALUES (?, 1, ?, ?)", (code, name, role))


def fake_turn(narration: str, **extra):
    def fake_generate(context, model_input):
        fake_generate.seen = {"context": context, "model_input": model_input}
        return {
            "scene_plan": {"goal": "look", "focus_points": []},
            "narration_segments": [{"label": "scene", "text": narration}],
            "narration": narration,
            "player": {},
            "self_check": {"passed": True, "issues_found": [], "corrections_made": []},
            "turn_summary": "the player follows the figure",
            "scene_focus": "action",
            **extra,
        }

    return fake_generate


def turn3_npcs() -> list[dict]:
    return ops_to_turn(TURN3_FINAL, parse_ops(TURN3_OPS))["npcs"]


def play_turn3() -> dict:
    with mock.patch.object(world, "generate_turn", side_effect=fake_turn(TURN3_FINAL, npcs=turn3_npcs())):
        return world.play_turn(TURN3_INPUT)


class MultiWordRole(unittest.TestCase):
    """(c) ROLE without quotes keeps every word up to the next flag."""

    def role(self, line: str) -> dict:
        return ops_to_turn("x", parse_ops(line))["npcs"][0]

    def test_game2_line(self):
        npc = self.role('NPC_NEW Elara "Elara" ROLE message runner LOC L1')
        self.assertEqual((npc["name"], npc["role"], npc["location"]), ("Elara", "message runner", "L1"))

    def test_stops_at_location_code_attitude_and_quotes(self):
        npc = self.role("NPC_NEW NAME Bo ROLE net mender friendly L1")
        self.assertEqual((npc["role"], npc["attitude"], npc["location"]), ("net mender", "friendly", "L1"))
        self.assertEqual(self.role('NPC_NEW NAME Bo ROLE "off-duty guard" LOC L1')["role"], "off-duty guard")
        self.assertEqual(self.role("NPC_NEW NAME Bo ROLE=carter LOC=L1")["role"], "carter")

    def test_a_capitalised_name_after_the_job_stays_the_name(self):
        npc = self.role("NPC_NEW ROLE baker Bo L1")
        self.assertEqual((npc["name"], npc["role"]), ("Bo", "baker"))


class ProseEntryReader(unittest.TestCase):
    """(a) the player going indoors in prose, and only the player."""

    PEOPLE = ["Aria", "Dockwick", "Hearthbin", "Elara"]

    def test_game2_turn3(self):
        shown = venues.entry_in_prose(TURN3_FINAL, self.PEOPLE)
        self.assertEqual(shown["noun"], "shop")
        self.assertEqual(shown["kind"], "apothecary")  # a shop full of herbs
        self.assertEqual(shown["keeper"], "Elara")
        self.assertEqual(shown["with"], ["Aria"])

    def test_someone_else_going_in_moves_nobody(self):
        self.assertIsNone(venues.entry_in_prose("The hooded figure disappears into a small shop, and you hesitate."))
        self.assertIsNone(venues.entry_in_prose("Elara, the message runner, enters the shop, her steps quiet."))

    def test_open_ground_and_walking_back_out(self):
        self.assertIsNone(venues.entry_in_prose("You step into the street outside the inn."))
        self.assertIsNone(venues.entry_in_prose("You make your way through the crowded streets of the town."))
        self.assertIsNone(venues.entry_in_prose("You step into the forge. The heat is fierce. You step back out into the street."))

    def test_named_kinds(self):
        self.assertEqual(venues.entry_in_prose("You follow Aria into the smithy.", ["Aria"])["kind"], "smithy")
        self.assertEqual(venues.entry_in_prose("You enter the temple quietly.")["kind"], "temple")

    def test_turn2_and_turn4_do_not_enter(self):
        self.assertIsNone(venues.entry_in_prose("You approach Aria [[A]], the baker, and ask about the figure."))
        self.assertIsNone(venues.entry_in_prose("You step closer to the shop counter, where a small pile of dried herbs lies."))


class ShopBecomesAPlace(unittest.TestCase):
    """(a) turn 3 through play_turn: the shop is a venue, kept, and the player is in it."""

    def setUp(self):
        seed_edge()

    def test_turn3_puts_the_player_inside_elaras_shop(self):
        state = play_turn3()["state"]
        here = state["current_location"]
        self.assertEqual(here["name"], "Elara's Shop")
        self.assertTrue(here["inside_venue"])
        self.assertEqual(here["exit_to"], "Eldoria's Edge")
        # Eldoria's Edge reads as a village, too small for an apothecary; the
        # shop the player was shown is kept as a general store, not dropped.
        self.assertEqual(here["venue_kind"], "general_store")
        self.assertEqual(here["keeper"]["name"], "Elara")
        self.assertEqual(state["movement"]["rule"], "venue_shown")
        with connect() as conn:
            rows = {r["name"]: r["location_id"] for r in conn.execute("SELECT name, location_id FROM npcs")}
            shop_id = conn.execute("SELECT id FROM locations WHERE name = ?", ("Elara's Shop",)).fetchone()[0]
            elara_role = conn.execute("SELECT role FROM npcs WHERE name = 'Elara'").fetchone()[0]
        self.assertEqual(rows["Elara"], shop_id)
        self.assertEqual(rows["Aria"], shop_id)  # she came in with the player
        self.assertEqual(rows["Dockwick"], 1)
        self.assertEqual(elara_role, "message runner")

    def test_going_back_in_reuses_the_shop(self):
        play_turn3()
        with connect() as conn:
            conn.execute("UPDATE player SET current_location_id = 1 WHERE id = 1")
            before = conn.execute("SELECT COUNT(*) FROM locations").fetchone()[0]
            prose = "Elara waves you inside again. You step into the shop."
            result = {"narration": prose, "player": {}}
            report = world.resolve_movement(conn, result, "I go back in", intent="general", narration=prose)
            after = conn.execute("SELECT COUNT(*) FROM locations").fetchone()[0]
        self.assertEqual(report["rule"], "venue_shown")
        self.assertEqual(result["player"]["move_to_location"], "Elara's Shop")
        self.assertEqual(before, after)

    def test_unshown_move_rule_spares_a_shown_entry(self):
        prose = TURN3_FINAL
        result = {"narration": prose, "player": {"move_to_location": "Elara's Herb Shop"}}
        with connect() as conn:
            rows = conn.execute("SELECT id, code, name FROM locations").fetchall()
            dropped = world._unasked_unshown_move(
                result, result["player"], rows, TURN3_INPUT, intent="conversation", narration=prose
            )
        self.assertEqual(dropped, "")

    def test_a_model_move_into_a_shop_is_a_venue(self):
        # "shop" is a venue word now; before, "Elara's Shop" became a second town.
        self.assertEqual(venues.venue_kind_from_name("Elara's Shop"), "general_store")
        self.assertEqual(venues.venue_kind_from_name("The Old Apothecary Shop"), "apothecary")

    def test_draft_is_asked_for_the_indoors_move(self):
        context = world.build_prompt_context(world.get_state(include_hidden=True), TURN3_INPUT)
        dsl = build_dsl_user_prompt(context, TURN3_INPUT)
        self.assertIn("===OPS=== MUST contain MOVE with that building's name", dsl)
        play_turn3()
        inside = world.build_prompt_context(world.get_state(include_hidden=True), TURN4_INPUT)
        self.assertNotIn("MOVE with that building's name", build_dsl_user_prompt(inside, TURN4_INPUT))

    def test_writer_keeps_a_draft_entry_inside(self):
        from app.narration_pipeline import NarrationLedger, build_paragraph_briefs

        context = world.build_prompt_context(world.get_state(include_hidden=True), TURN3_INPUT)
        ledger = NarrationLedger(turn=3, player_input=TURN3_INPUT, budget={})
        draft = {"narration": TURN3_FINAL, "player": {"move_to_location": None}}
        facts = build_paragraph_briefs({"paragraphs": 2}, context, TURN3_INPUT, ledger, draft=draft)[0]["scene_facts"]
        self.assertEqual(facts["player_goes_inside"], "the shop")
        self.assertNotIn("player_stays_in", facts)


class WorkplacesAreKnown(unittest.TestCase):
    """(b) a baker has a bakery; in someone else's shop she is a visitor."""

    def setUp(self):
        seed_edge()

    def test_roles_to_kinds(self):
        self.assertEqual(venues.workplace_kind_for_role("baker"), "bakery")
        self.assertEqual(venues.workplace_kind_for_role("blacksmith"), "smithy")
        self.assertEqual(venues.workplace_kind_for_role("message runner"), "")
        self.assertEqual(venues.workplace_kind_for_role("well keeper"), "")
        self.assertEqual(venues.workplace_kind_for_role("off-duty guard"), "")

    def test_baker_gets_a_bakery_once(self):
        with connect() as conn:
            aria = conn.execute("SELECT id FROM npcs WHERE name = 'Aria'").fetchone()[0]
            first = world.ensure_npc_workplace(conn, aria)
            again = world.ensure_npc_workplace(conn, aria)
            row = conn.execute("SELECT * FROM locations WHERE id = ?", (first,)).fetchone()
            runner = conn.execute("SELECT id FROM npcs WHERE name = 'Hearthbin'").fetchone()[0]
            none = world.ensure_npc_workplace(conn, runner)
        self.assertEqual(first, again)
        self.assertEqual(row["name"], "Aria's Bakery")
        self.assertEqual((row["parent_id"], row["kind"], row["keeper_npc_id"]), (1, "bakery", aria))
        self.assertEqual(none, 0)

    def test_turn4_prompts_know_whose_place_it_is(self):
        from app.narration_pipeline import NarrationLedger, build_paragraph_briefs
        from app.prompts import _visible_world

        play_turn3()
        context = world.build_prompt_context(world.get_state(include_hidden=True), TURN4_INPUT)
        place = _visible_world(context, TURN4_INPUT)["current_location"]
        self.assertEqual(place["keeper"], "Elara")
        people = {p["name"]: p for p in place["people"]}
        self.assertTrue(people["Elara"].get("works_here"))
        self.assertEqual(people["Aria"].get("works_at"), "Aria's Bakery")
        self.assertNotIn("works_here", people["Aria"])

        draft = {
            "narration": "Aria [[A]] leans over the counter while Elara [[D]] sorts the herbs.",
            "player": {},
        }
        ledger = NarrationLedger(turn=4, player_input=TURN4_INPUT, budget={})
        facts = build_paragraph_briefs({"paragraphs": 2}, context, TURN4_INPUT, ledger, draft=draft)[0]["scene_facts"]
        cast = {c["name"]: c for c in facts["cast"]}
        self.assertEqual(facts["keeper"], "Elara")
        self.assertEqual(cast["Aria"]["works_at"], "Aria's Bakery")
        self.assertTrue(cast["Elara"]["works_here"])

        seen = {}

        def fake_chat(system, user, **kwargs):
            seen["system"] = system
            return "You run a thumb over the dried mint."

        with mock.patch.object(llm, "_chat_text", side_effect=fake_chat):
            llm._make_pipeline_paragraph_writer([], None, 30, context)(
                build_paragraph_briefs({"paragraphs": 2}, context, TURN4_INPUT, ledger, draft=draft)[0], "", ledger
            )
        self.assertIn("works_at is that person's own workplace", seen["system"])
        dsl = build_dsl_user_prompt(context, TURN4_INPUT)
        self.assertIn("works_at is that person's own workplace", DSL_SYSTEM_PROMPT)
        self.assertIn('"works_at":"Aria\'s Bakery"', dsl)

    def test_rewind_removes_the_shop_and_the_bakery(self):
        play_turn3()
        world.rewind_last_turn()
        with connect() as conn:
            names = [r[0] for r in conn.execute("SELECT name FROM locations").fetchall()]
            where = conn.execute("SELECT location_id, workplace_id FROM npcs WHERE name = 'Aria'").fetchone()
        self.assertNotIn("Aria's Bakery", names)
        self.assertEqual(tuple(where), (1, 0))


class StoredRoleWins(unittest.TestCase):
    """(d) turn 2: "a cartter [[C]]" for Hearthbin the message runner."""

    CONTEXT = {
        "current_location": {"code": "L1", "name": "Eldoria's Edge"},
        "locations": [
            {
                "code": "L1",
                "name": "Eldoria's Edge",
                "npcs": [
                    {"code": "A", "name": "Aria", "role": "baker"},
                    {"code": "C", "name": "Hearthbin", "role": "message runner"},
                ],
            }
        ],
    }

    def repair(self, text: str) -> dict:
        return llm._repair_entity_names_in_turn({"narration": text, "npcs": []}, self.CONTEXT)

    def test_job_before_the_tag_is_the_stored_one(self):
        out = self.repair("Nearby, a cartter [[C]] is unloading crates of vegetables.")["narration"]
        self.assertIn("a message runner Hearthbin [[C]] is unloading", out)
        self.assertNotIn("cartter", out)
        out = self.repair("Nearby, a cartter Hearthbin [[C]] is unloading crates.")["narration"]
        self.assertIn("a message runner Hearthbin [[C]]", out)

    def test_matching_jobs_are_left_alone(self):
        text = "The baker Aria [[A]] looks up. You approach Aria [[A]], the baker, and ask."
        self.assertEqual(self.repair(text)["narration"], text)

    def test_a_different_appositive_is_reported(self):
        result = self.repair("Hearthbin [[C]], the carter, waves. Aria [[A]], the baker, nods.")
        self.assertEqual(result["role_mismatches"], [{"code": "C", "stored": "message runner", "prose": "carter"}])


if __name__ == "__main__":
    unittest.main()
