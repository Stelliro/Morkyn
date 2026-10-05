"""
Playtest #33 (live Qwen3 8B smoke run): shops rarely become venues, plain
questions move the player, and the map walks one way while the prose walks the
other.

Every input and narration here is copied from the live turn payloads of the
smoke run (round 2 = the player's launcher env, round 1 = without it):

  R2 g2 turn 5: "walk back to the Chrome Wrench Garage and go inside" wrote
    MOVE "Chrome Wrench Garage"; the garage the opening made had no parent,
    kind or keeper and kept none, and the draft minted a second mechanic
    (Randy) beside the opening's Victor Silva.
  R2 g1 turn 5: "I slip back out and go into the nearest salvage shop" read
    as an exit; the prose stood the player in Ito Salvage and the engine left
    them at The Iron Gate.
  R1 g1 turn 5: "head for the Spindle at Edge ... and go inside the first shop"
    stopped at the settlement.
  R1 g2 turn 1: "Where were you headed?" was a travel turn, so the draft's
    MOVE to The Old Well (named only in Eli's answer) was kept.
  R2 g1 turn 1: Umar's "They think you're heading there" counted as the
    narration moving the player, so a MOVE to The Twelfth Circuit was kept
    while the prose was in the med-bay.
  R2 g2 turn 5: the prose went east, the map walked west.
"""
from __future__ import annotations

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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-live-venues-33-"))
os.environ.update(isolated_data_env(str(_TMP)))
os.environ.update(
    {
        "AI_RPG_PACK_DIR": str(_TMP / "packs"),
        "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
        "AI_RPG_IDEA_BANK": str(_TMP / "idea_bank"),
        "AI_RPG_LAUNCHER_PREFS": str(_TMP / "launcher_prefs.json"),
    }
)
# The player's launcher env (data/launcher_prefs.json), for this module only.
LAUNCHER_ENV = {
    "AI_RPG_NARRATION_PIPELINE": "1",
    "AI_RPG_NARRATION_PIPELINE_CONSOLIDATE": "1",
    "AI_RPG_FAST_VERIFICATION": "1",
    "AI_RPG_DSL_SKIP_VERIFY": "1",
    "AI_RPG_DRAFT_MODE": "dsl",
}
_launcher_patch = mock.patch.dict(os.environ, {**LAUNCHER_ENV, "AI_RPG_DB": os.environ["AI_RPG_DB"]})


def setUpModule():
    _launcher_patch.start()


def tearDownModule():
    _launcher_patch.stop()


from app import db, example_pools, tile_world, venues, world  # noqa: E402
from app.db import connect  # noqa: E402

# ---------------------------------------------------------------------------
# Live inputs and narrations (verbatim)
# ---------------------------------------------------------------------------

G2T5_INPUT = 'I give up on Carlos for now, walk back to the Chrome Wrench Garage and go inside to see what they sell.'
G2T5_NARRATION = (
    'You leave the Forest Path and head east, the gravel crunching under your boots. The Chrome Wrench Ga'
    'rage comes into view, its metal frame weathered by time and the elements. You push through the creak'
    'ing door, the scent of oil and rust filling your nostrils. Inside, the garage is dimly lit, with too'
    'ls hanging from the ceiling and a few workers scurrying about, their movements sharp and focused.\n\nY'
    'ou approach the counter, where a burly man with a beard and calloused fingers is wiping his gloves. '
    'His voice is gravelly as he asks, “Looking for anything specific?” You shake your head, the motion s'
    'harp and deliberate, and step closer, the scent of oil and metal thick in the stale, dusty air. His '
    'gaze lingers on the calluses, then shifts to the shelves behind him, where bolts, wrenches, and half'
    '-scratched bike parts glint in the dim light.\n\nHe nods, then turns to a shelf behind him, the motion'
    ' slow and practiced, and gestures toward the glinting array of bolts, wrenches, and half-scratched b'
    'ike parts. “We’ve got a few things for sale. Some parts for bikes, some for engines.”'
)
G1T5_INPUT = 'I slip back out and go into the nearest salvage shop to ask what this crystal is worth.'
G1T5_NARRATION = (
    'You slip through the Iron Gate’s side entrance and into Ito Salvage, a cramped shop where the smell '
    'of metal and ozone hangs thick. The shop’s owner, a grizzled human, is bent over a console, his hand'
    's moving with the precision of someone who’s spent years fixing things that shouldn’t work. You appr'
    'oach, and he looks up, his dark gaze narrowing as he takes in the glowing shard you hold.\n\nThe shop’'
    's owner, Adrian Wong, hunches over his work, his calloused hands flickering with the glow of circuit'
    'ry as he adjusts a panel. When you step closer, his gaze lifts, dark and assessing, and he lets out '
    'a quiet sigh, as if the shard’s presence is an inconvenience he’s grown used to. He gestures for you'
    ' to hold it out, his finger tracing the jagged edges with a practiced touch, his expression flickeri'
    'ng between curiosity and caution.\n\n“Not a common find,” he mutters, reaching for it. His touch is ca'
    'reful, almost reverent. “This is a Starborn shard—old tech, but still potent. You’re not the first t'
    'o ask about it, but I’ve never seen one this intact.” His finger traces the jagged edges, pausing wh'
    'ere the glow pulses softly, as if testing its strength. The shop’s dim lighting catches the shard’s '
    'edges, casting long, flickering shapes across the walls.\n\nYou hand it over, and he studies it for a '
    'long time. “It’s not worth much here,” he says finally, “but it could be valuable to the right peopl'
    'e.” His gaze flicks to the Iron Gate’s side entrance, where the wind still whistles through the crac'
    'ks, and his jaw tightens. “You’re not from around here, are you?” The shard’s glow dims slightly in '
    'his hand, as though it, to, senses the unspoken question hanging in the shop’s stale, metallic breat'
    'h.'
)
R1G1T5_INPUT = 'I head for the Spindle at Edge that Rolf mentioned and go inside the first shop I find to ask about the fire.'
R1G1T5_NARRATION = (
    'You head for the Spindle at Edge, the name Rolf [[A]] muttered with the weight of a burden. The path'
    ' ahead is clear, the plains stretching out in a soft golden haze, the sun low enough to cast long sh'
    "adows across the rolling grass. You walk northeast, the terrain shifting from the city's cobblestone"
    ' to the open grasslands, where the wind carries the scent of dust and distant rain. The journey is s'
    'hort, and soon you stand before the Spindle, a weathered building with a sign that creaks in the bre'
    'eze, its edges worn by time and the elements. The door is slightly ajar, as if it has been left that'
    ' way for days, and the faint sound of a hammer striking metal echoes from within.\n\nInside, the shop '
    'is dimly lit, the smell of oil and metal thick in the air, mingling with the faint tang of burnt woo'
    'd. A merchant with a grizzled beard and a scar across his cheek looks up from his work, his gaze ass'
    'essing you with a mix of suspicion and curiosity. His hands are calloused, stained with soot and rus'
    't, and he wears a patched coat that looks like it has seen better days. The shelves are cluttered wi'
    'th tools, bolts, and scraps of metal, some arranged with care and others left in disarray. A small b'
    'ell above the door jingles as you step inside, the sound sharp and clear against the silence.\n\nThe m'
    'erchant sets down his hammer, his eyes narrowing slightly as he studies you. "Looking for something '
    'specific, or just wandering?" he asks, his voice rough and low. You shake your head, explaining that'
    " you're seeking information about the fire that spread through the district last night. His expressi"
    "on doesn't change, but the way he leans back in his chair suggests he's thinking, weighing your word"
    's. A few moments pass before he nods, and he gestures for you to follow him through a narrow passage'
    ' behind the counter. The air grows cooler there, and the scent of something stronger—burnt charcoal '
    'or ash—fills the space.'
)
R1G2T1_INPUT = 'Eli Dasgupta, are those your boot prints by the sign? Where were you headed?'
R1G2T1_NARRATION = (
    'Eli Dasgupta [[A]] lifts his gaze from the ground, his brow furrowed. The boot prints by the sign ar'
    'e faint, half-buried in the dust, and he hesitates before answering. "I was heading to the old well,'
    '" he says, his voice low. "There\'s been talk of water running dry, and I figured it might still be w'
    'orth checking." His eyes flicker toward the east, where the plains stretch endlessly, and for a mome'
    'nt, you wonder if he’s looking for something more than water. The wind carries the scent of dry eart'
    'h and distant smoke, tugging at the edges of his coat. A few feet away, a group of farmers huddle ne'
    'ar a weathered cart, their faces shadowed by the sun, murmuring about the drought and the rumors of '
    'bandits moving through the hills. Eli’s fingers brush the worn leather of his gloves, a habit he’s h'
    'ad since childhood, as if the touch of the earth could steady his thoughts. He glances at you again,'
    ' his expression unreadable, and then turns back to the path, his steps slow but deliberate, as thoug'
    'h each footfall is a decision he’s made to live with.'
)
G1T1_INPUT = "Umar, who is waiting for me in the clinic? I don't remember agreeing to meet anyone."
G1T1_NARRATION = (
    'You step off the platform and into the med-bay, the air thick with the scent of antiseptic and the h'
    'um of machines. Umar Mendes is waiting by the far end of the room, his face lined with worry. He’s n'
    'ot the kind of courier who delivers messages; he’s the kind who carries secrets. You remember now—th'
    'ere was a note in your pack, slipped between your belongings, asking you to meet him here. He leans '
    'in, his voice low. “The Guild’s watching the docks.\n\nHe leans in, his voice low. They think you’re h'
    'eading there, but you’re not. You’re heading to the Starborn Rebellion.” He hands you a small data c'
    'rystal. “This is your next lead.\n\nHe hands you a small data crystal. “This is your next lead.” His f'
    'ingers tighten around it, the metal cool against his palm, as if he’s already preparing to let it go'
    '. You glance at the far end of the room where the machines hum and the antiseptic scent lingers—Umar'
    '’s worry etched into every line of his face. He doesn’t ask if you’re ready. He just waits, like the'
    ' whole thing was always meant to happen, and you’re already too far in to turn back.\n\nThe data cryst'
    'al pulses faintly in your palm, its edges sharp enough to bite if you’re not careful. Umar’s voice d'
    'rags on, low and taut, as if he’s already regretting the words before he says them: “Once you’re in,'
    ' you can’t come back out without a price.” His gaze flicks to the door, then back to you, and for a '
    'moment, the hum of machines and the sterile air feel like a wall between you and everything you’ve l'
    'eft behind. You don’t say anything.'
)

# ---------------------------------------------------------------------------
# Isolated DB helpers
# ---------------------------------------------------------------------------

_SEEDS = 0


def seed_world(places, npcs, here: int, options: dict | None = None) -> None:
    global _SEEDS
    _SEEDS += 1
    os.environ["AI_RPG_DB"] = str(_TMP / f"world_{_SEEDS}.db")
    db.init_db()
    with connect() as conn:
        conn.execute("DELETE FROM npcs")
        conn.execute("DELETE FROM settings WHERE key IN ('active_scene', 'conversation', 'scene_thread')")
        for loc_id, name in places:
            if conn.execute("SELECT 1 FROM locations WHERE id = ?", (loc_id,)).fetchone():
                conn.execute(
                    "UPDATE locations SET name = ?, code = ?, parent_id = 0, kind = '', keeper_npc_id = 0 WHERE id = ?",
                    (name, f"L{loc_id}", loc_id),
                )
            else:
                conn.execute(
                    "INSERT INTO locations (id, code, name, summary) VALUES (?, ?, ?, '')", (loc_id, f"L{loc_id}", name)
                )
        for code, loc_id, name, role in npcs:
            conn.execute(
                "INSERT INTO npcs (code, location_id, name, role, summary) VALUES (?, ?, ?, ?, 'Known here.')",
                (code, loc_id, name, role),
            )
        conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (here,))
        if options is not None:
            import json

            row = conn.execute("SELECT value FROM settings WHERE key = 'playthrough_options'").fetchone()
            merged = {**(json.loads(row[0]) if row else {}), **options}
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES ('playthrough_options', ?)", (json.dumps(merged),)
            )


def fake_turn(narration: str, **extra):
    def fake_generate(context, model_input):
        return {
            "scene_plan": {"goal": "go on", "focus_points": []},
            "narration_segments": [{"label": "scene", "text": narration}],
            "narration": narration,
            "player": {},
            "self_check": {"passed": True, "issues_found": [], "corrections_made": []},
            "turn_summary": "the player goes on",
            "scene_focus": "action",
            **extra,
        }

    return fake_generate


def play(player_input: str, narration: str, **extra) -> dict:
    with mock.patch.object(world, "generate_turn", side_effect=fake_turn(narration, **extra)):
        return world.play_turn(player_input)


def place(location_id: int) -> dict:
    with connect() as conn:
        row = conn.execute("SELECT * FROM locations WHERE id = ?", (location_id,)).fetchone()
    return dict(row) if row else {}


def place_named(name: str) -> dict:
    with connect() as conn:
        row = conn.execute("SELECT * FROM locations WHERE name = ? COLLATE NOCASE", (name,)).fetchone()
    return dict(row) if row else {}


def player_location() -> int:
    with connect() as conn:
        return int(conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()[0])


def npc(name: str) -> dict:
    with connect() as conn:
        row = conn.execute("SELECT * FROM npcs WHERE name = ?", (name,)).fetchone()
    return dict(row) if row else {}


def movement_of(payload: dict) -> dict:
    return payload.get("movement") or (payload.get("state") or {}).get("movement") or {}


# ---------------------------------------------------------------------------
# #33-kind-vocab
# ---------------------------------------------------------------------------


class KindVocabularyIsTheWorlds(unittest.TestCase):
    def test_live_shop_names_are_venues(self):
        expected = {
            "Chrome Wrench Garage": "garage",
            "Ito Salvage": "salvage_yard",
            "Bianchi's Clinic": "clinic",
            "Weber Repairs": "garage",
            "Fischer's Diner": "diner",
            "Twelfth Atlas Laundromat": "laundromat",
            "Chrome Thermos Pharmacy": "pharmacy",
        }
        for name, kind in expected.items():
            self.assertEqual(venues.venue_kind_from_name(name), kind, name)

    def test_fantasy_names_keep_their_kinds(self):
        self.assertEqual(venues.venue_kind_from_name("The Blacksmith's Forge"), "smithy")
        self.assertEqual(venues.venue_kind_from_name("The Crooked Lantern Tavern"), "tavern")
        self.assertEqual(venues.venue_kind_from_name("The Alchemist's Rest"), "")

    def test_every_trade_the_pools_draw_has_a_kind(self):
        # venue_name_options are drawn from these words: each option is a venue.
        for era, words in example_pools._VENUE_TRADE.items():
            for word in words:
                self.assertTrue(venues.venue_kind_from_name(f"Weber {word}"), f"{era}: {word}")

    def test_kinds_possible_are_the_worlds_trades(self):
        def possible(options):
            state = {
                "current_location": {"code": "L1", "name": "The Frostbound Crossroads", "settlement_size": "village"},
                "locations": [{"id": 1, "code": "L1", "name": "The Frostbound Crossroads", "parent_id": 0}],
                "settings": {"playthrough_options": options},
            }
            return world.movement_contract(state, "look around", "investigation").get("venue_kinds_possible") or []

        modern = possible({"tech_level": "near future"})
        self.assertIn("garage", modern)
        self.assertIn("clinic", modern)
        self.assertNotIn("smithy", modern)
        old = possible({"tech_level": "medieval"})
        self.assertIn("smithy", old)
        self.assertNotIn("garage", old)

    def test_a_new_garage_is_a_venue_of_where_the_player_stands(self):
        seed_world([(1, "The Frostbound Crossroads")], [], here=1)
        with connect() as conn:
            new_id = world._upsert_location(conn, "Chrome Wrench Garage")
            row = conn.execute("SELECT * FROM locations WHERE id = ?", (new_id,)).fetchone()
        self.assertEqual(int(row["parent_id"]), 1)
        self.assertEqual(row["kind"], "garage")


# ---------------------------------------------------------------------------
# #33-explicit-move-skips-venue-path and #33-keeper-not-reused
# ---------------------------------------------------------------------------


class ExplicitMoveRunsTheVenueRules(unittest.TestCase):
    def test_live_walk_back_to_the_garage_and_go_inside(self):
        seed_world(
            [(1, "The Frostbound Crossroads"), (2, "Chrome Wrench Garage"), (7, "Forest Path")],
            [("B", 1, "Victor Silva", "mechanic"), ("E", 1, "Whitney Garcia", "nurse")],
            here=7,
            options={"tech_level": "near future"},
        )
        payload = play(
            G2T5_INPUT,
            G2T5_NARRATION,
            player={"move_to_location": "Chrome Wrench Garage"},
            npcs=[{"name": "Randy", "role": "garage mechanic", "location": "Chrome Wrench Garage"}],
        )
        garage = place(2)
        self.assertEqual(garage["kind"], "garage")
        self.assertEqual(int(garage["parent_id"]), 1)
        self.assertEqual(player_location(), 2, movement_of(payload))
        victor = npc("Victor Silva")
        self.assertEqual(int(garage["keeper_npc_id"]), int(victor["id"]))
        self.assertEqual(int(victor["location_id"]), 2)

    def test_live_settlement_then_the_first_shop(self):
        seed_world(
            [(1, "Edge of the Whispering Wastes"), (2, "Burnt Herbs Site"), (3, "Clearing by the Ridge")],
            [("A", 1, "Rolf", "teamster")],
            here=3,
        )
        payload = play(R1G1T5_INPUT, R1G1T5_NARRATION, player={"move_to_location": "Spindle at Edge"})
        settlement = place_named("Spindle at Edge")
        self.assertTrue(settlement, movement_of(payload))
        here = place(player_location())
        self.assertEqual(int(here["parent_id"]), int(settlement["id"]), movement_of(payload))
        self.assertTrue(here["kind"])


class TheOpeningTradespersonKeepsTheShop(unittest.TestCase):
    def test_role_vocabulary(self):
        self.assertEqual(venues.workplace_kind_for_role("mechanic"), "garage")
        self.assertEqual(venues.workplace_kind_for_role("pharmacist"), "pharmacy")
        self.assertEqual(venues.workplace_kind_for_role("nurse"), "clinic")
        self.assertEqual(venues.workplace_kind_for_role("bartender", "modern"), "bar")
        self.assertEqual(venues.workplace_kind_for_role("mechanic", "preindustrial"), "smithy")
        self.assertEqual(venues.workplace_kind_for_role("baker"), "bakery")

    def test_victor_works_at_the_garage_the_opening_made(self):
        seed_world(
            [(1, "The Frostbound Crossroads"), (2, "Chrome Wrench Garage")],
            [("B", 1, "Victor Silva", "mechanic")],
            here=1,
        )
        victor_id = int(npc("Victor Silva")["id"])
        with connect() as conn:
            self.assertEqual(world.plan_npc_workplace(conn, victor_id), 2)
        garage = place(2)
        self.assertEqual(int(garage["parent_id"]), 1)
        self.assertEqual(garage["kind"], "garage")
        self.assertEqual(int(garage["keeper_npc_id"]), victor_id)
        venues_here = world.get_state()["current_location"].get("venues_here") or []
        self.assertIn("Chrome Wrench Garage", [v.get("name") for v in venues_here])


# ---------------------------------------------------------------------------
# #33-exit-read-before-enter and #33-entry-in-prose-first-preposition
# ---------------------------------------------------------------------------


class SlipBackOutAndGoIn(unittest.TestCase):
    def test_last_doorway_motion_wins(self):
        self.assertEqual(world.venue_move_intent(G1T5_INPUT), "enter")
        self.assertEqual(world.venue_move_intent("I go inside, then step back out."), "exit")
        self.assertEqual(world.venue_move_intent("I step back out into the street."), "exit")

    def test_live_salvage_shop(self):
        seed_world(
            [(1, "The Far Platform"), (3, "The Twelfth Circuit"), (4, "The Iron Gate")],
            [("A", 1, "Umar Mendes", "courier")],
            here=4,
            options={"tech_level": "spacefaring salvage"},
        )
        payload = play(
            G1T5_INPUT,
            G1T5_NARRATION,
            npcs=[{"name": "Adrian Wong", "role": "rigger", "location": "Ito Salvage"}],
        )
        here = place(player_location())
        self.assertEqual(here.get("name"), "Ito Salvage", movement_of(payload))
        self.assertEqual(int(here["parent_id"]), 4)
        self.assertEqual(here["kind"], "salvage_yard")


class EntryReadsEveryPreposition(unittest.TestCase):
    def test_through_the_door_and_into_the_shop(self):
        shown = venues.entry_in_prose("You slip through the side door and into a cramped shop where the smell of oil hangs thick.")
        self.assertIsNotNone(shown)
        self.assertEqual(shown["kind"], "general_store")

    def test_live_ito_salvage(self):
        shown = venues.entry_in_prose(G1T5_NARRATION, ["Adrian Wong"])
        self.assertEqual(shown["kind"], "salvage_yard")
        self.assertEqual(shown["name"], "Ito Salvage")

    def test_live_through_the_creaking_door_then_inside(self):
        shown = venues.entry_in_prose(G2T5_NARRATION)
        self.assertIsNotNone(shown)
        self.assertEqual(shown["kind"], "garage")

    def test_a_town_gate_is_not_indoors(self):
        self.assertIsNone(venues.entry_in_prose("You walk through the town gate. The inn stands to your left."))
        self.assertIsNone(venues.entry_in_prose("You step into the street outside the inn."))

    def test_speech_and_exit_still_excluded(self):
        self.assertIsNone(venues.entry_in_prose('"Why don\'t you step into my shop?" she asks.'))
        self.assertIsNone(
            venues.entry_in_prose("You step into the bakery. You buy a loaf. You step back out onto the square.")
        )


# ---------------------------------------------------------------------------
# #33-question-reads-as-travel and #33-speech-counts-as-departure
# ---------------------------------------------------------------------------


class QuestionsAreNotTravel(unittest.TestCase):
    def test_questions_about_someone_else(self):
        self.assertNotEqual(world._turn_intent("Where were you headed?")[0], "travel")
        self.assertFalse(world.travel_intent("Who runs the inn?"))
        self.assertFalse(world.travel_intent("Where are you going?"))
        self.assertFalse(world.travel_intent(R1G2T1_INPUT))
        self.assertEqual(world.venue_move_intent("Did you go into the shop?"), "")

    def test_the_player_going_is_still_travel(self):
        self.assertTrue(world.travel_intent("I head to the inn."))
        self.assertTrue(world.travel_intent("Shall we head to the inn?"))
        self.assertTrue(world.travel_intent("Can I go with you to the well?"))

    def test_live_old_well_move_is_dropped(self):
        seed_world(
            [(1, "The Wasteland's Edge"), (3, "The Spindle at Edge")],
            [("A", 3, "Eli Dasgupta", "drifter")],
            here=3,
        )
        payload = play(R1G2T1_INPUT, R1G2T1_NARRATION, player={"move_to_location": "The Old Well"})
        self.assertEqual(player_location(), 3)
        self.assertFalse(place_named("The Old Well"))
        self.assertEqual(movement_of(payload).get("status"), "dropped_unshown")


class SpeechIsNotTheNarrationMoving(unittest.TestCase):
    def test_spoken_heading_is_not_a_departure(self):
        self.assertFalse(world._player_departs('He leans in. "They think you’re heading there, but you’re not."'))
        self.assertTrue(world._player_departs("You head for the gate."))

    def test_live_twelfth_circuit_move_is_dropped(self):
        seed_world(
            [(1, "The Far Platform"), (3, "The Twelfth Circuit")],
            [("A", 1, "Umar Mendes", "courier")],
            here=1,
            options={"tech_level": "spacefaring salvage"},
        )
        payload = play(G1T1_INPUT, G1T1_NARRATION, player={"move_to_location": "The Twelfth Circuit"})
        movement = movement_of(payload)
        self.assertNotEqual(player_location(), 3, movement)
        if movement.get("status") == "repaired":
            # The prose went into the med-bay: that is where the player is.
            self.assertEqual(movement.get("dropped"), "The Twelfth Circuit")
            here = place(player_location())
            self.assertEqual(here["kind"], "clinic")
            self.assertEqual(int(here["parent_id"]), 1)
        else:
            self.assertEqual(movement.get("status"), "dropped_unshown")

    def test_named_move_absent_from_prose_is_flagged(self):
        seed_world([(1, "The Far Platform"), (3, "The Old Mill")], [], here=1)
        with connect() as conn:
            result = {"player": {"move_to_location": "The Old Mill"}}
            report = world.resolve_movement(
                conn,
                result,
                "I walk on.",
                intent="travel",
                narration='You walk along the road for an hour. "The Old Mill is that way," a carter says.',
            )
        self.assertEqual(report["status"], "model")
        self.assertEqual(report.get("prose_mismatch"), "The Old Mill")


# ---------------------------------------------------------------------------
# #33-map-walk-vs-prose-direction
# ---------------------------------------------------------------------------


def _cell(x, y, state="plains"):
    return {"x": x, "y": y, "state": state, "walkable": True, "elevation": 0, "image_path": "skip", "image_data_url": ""}


def _chart(player, settlements=None, anchors=None):
    grid = [[_cell(x, y) for x in range(12)] for y in range(8)]
    return {
        "id": "",
        "width": 12,
        "height": 8,
        "player": {"x": player[0], "y": player[1]},
        "grid": grid,
        "visited": [f"{player[0]},{player[1]}"],
        "settlements_meta": list(settlements or []),
        "landmarks": [],
        "place_anchors": dict(anchors or {}),
        "knowledge": {"settlements": [], "danger": [], "notes": [], "sources": []},
    }


_CROSSROADS = {"code": "L1", "name": "The Frostbound Crossroads", "x": 4, "y": 3}
_STATE = {
    "current_location": {"code": "L7", "name": "Forest Path"},
    "locations": [
        {"id": 1, "code": "L1", "name": "The Frostbound Crossroads", "parent_id": 0},
        {"id": 2, "code": "L2", "name": "Chrome Wrench Garage", "parent_id": 1, "kind": "garage"},
        {"id": 7, "code": "L7", "name": "Forest Path", "parent_id": 0},
    ],
    "settings": {},
}


class TheEngineDecidesTheBearing(unittest.TestCase):
    def test_known_places_carry_bearings(self):
        chart = _chart((8, 3), anchors={"L1": _CROSSROADS, "the frostbound crossroads": _CROSSROADS})
        space = tile_world.spatial_contract(chart)
        contract = world.movement_contract(_STATE, G2T5_INPUT, "travel", map_space=space)
        self.assertEqual(contract["bearings"]["The Frostbound Crossroads"], "west, 4 tiles")

    def test_walk_to_the_garage_is_told_the_way_the_map_walks(self):
        chart = _chart((8, 3), anchors={"L1": _CROSSROADS, "the frostbound crossroads": _CROSSROADS})
        contract = world.movement_contract(_STATE, G2T5_INPUT, "travel", map_space=tile_world.spatial_contract(chart))
        self.assertEqual(contract["walk_plan"]["direction"], "west")
        self.assertIn("runs west", contract["expectation"])
        walked = tile_world.apply_story_map_walk(
            chart,
            player_input=G2T5_INPUT,
            movement_report={"status": "model", "from": "L7", "destination": "Chrome Wrench Garage"},
            origin={"id": 7, "code": "L7", "name": "Forest Path", "parent_id": 0},
            dest={
                "id": 2, "code": "L2", "name": "Chrome Wrench Garage", "parent_id": 1,
                "parent_code": "L1", "parent_name": "The Frostbound Crossroads",
            },
            travel=True,
        )
        self.assertEqual(walked["direction"], contract["walk_plan"]["direction"])

    def test_a_walk_with_no_direction_is_told_the_fallback_heading(self):
        town = [{"id": "S1", "x": 8, "y": 6, "state": "town", "name": "Redwick", "bbox": [8, 6, 8, 6]}]
        chart = _chart((8, 1), settlements=town)
        state = {
            "current_location": {"code": "L2", "name": "Burnt Herbs Site"},
            "locations": [{"id": 2, "code": "L2", "name": "Burnt Herbs Site", "parent_id": 0}],
            "settings": {},
        }
        line = "I follow the trail of whoever set the fire. Rolf, stay close."
        contract = world.movement_contract(state, line, "travel", map_space=tile_world.spatial_contract(chart))
        plan = contract["walk_plan"]
        walked = tile_world.apply_story_map_walk(
            chart,
            player_input=line,
            movement_report={"status": "model", "from": "L2", "destination": "Clearing by the Ridge"},
            origin={"id": 2, "code": "L2", "name": "Burnt Herbs Site", "parent_id": 0},
            dest={"id": 3, "code": "L3", "name": "Clearing by the Ridge", "parent_id": 0},
            travel=True,
        )
        self.assertEqual(plan["direction"], "south")
        self.assertEqual(walked["direction"], plan["direction"])

    def test_the_draft_prompt_carries_the_heading(self):
        from app.turn_dsl import build_dsl_user_prompt

        chart = _chart((8, 3), anchors={"L1": _CROSSROADS, "the frostbound crossroads": _CROSSROADS})
        contract = world.movement_contract(_STATE, G2T5_INPUT, "travel", map_space=tile_world.spatial_contract(chart))
        prompt = build_dsl_user_prompt({"movement_contract": contract, "current_location": _STATE["current_location"]}, G2T5_INPUT)
        self.assertIn("the way runs west", prompt)
        self.assertIn("west, 4 tiles", prompt)


if __name__ == "__main__":
    unittest.main()
