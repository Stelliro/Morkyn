"""Place fixes from the sixth Saltmarrow run on Qwen2.5 7B (round 2 of the run-5 place work)."""
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-7b-run6-places-"))
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


def seed() -> None:
    """Run 6's world at T3: Saltmarrow and nothing else."""
    from app import db
    from app.db import connect

    db.init_db()
    with connect() as conn:
        conn.execute("UPDATE player SET current_location_id = 1 WHERE id = 1")
        conn.execute("DELETE FROM npcs")
        conn.execute("DELETE FROM locations WHERE id != 1")
        conn.execute(
            "UPDATE locations SET code = 'L1', name = 'Saltmarrow', "
            "summary = 'Starting location for a frontier dark fantasy playthrough.', parent_id = 0, "
            "kind = '', settlement_size = 'town', keeper_npc_id = 0 WHERE id = 1"
        )


def row(conn, name):
    return conn.execute("SELECT * FROM locations WHERE name = ?", (name,)).fetchone()


T3_LINE = (
    "\"Then I'd best get my hauling done before they pick the lower district clean.\" I nod to Simon and head "
    "down to the salvage yard to see what the overseer has on the board today."
)
T3_PROSE = (
    "You nod to Simon Pennick [[A]] and head down to the salvage yard, the sun casting long shadows in the early "
    "light of the day. The lower district is already bustling with salvagers setting up their tents and carts. "
    "The overseer, a grizzled man named Oldfield, is scribbling something on a ledger. You approach him, ready to "
    "see what tasks he has for you."
)
T9_LINE = (
    "I follow Oldfield to the shed door before he can get away. \"Oldfield. Two gold, by noon, we said. It's not "
    "noon and the pile's done.\""
)
T9_PROSE = (
    "You follow Oldfield [[B]] to the shed door before he can get away. \"Oldfield. Two gold, by noon, we said. "
    "It's not noon and the pile's done.\" Oldfield [[B]] stops and turns, a hint of surprise on his face.\n\n"
    "The sorting shed [[L2]] is a cluttered space, filled with crates and bales of various salvaged items.\n\n"
    "Oldfield [[B]] gives you a nod of approval. \"Well, you've earned this.\""
)
T0_PROSE = (
    "You stand on the edge of Saltmarrow, where the high tide marks the boundary between the living and the "
    "drowned.\n\nOn your right, the Elwood and Daughters dairy stands open, its wooden door creaking gently in the "
    "morning breeze. To the west, the Anchor and Ox inn is closed for the morning, its shutters tightly closed. In "
    "the distance, the Badger at Saltmarrow, a familiar sight, is also quiet, its windows dark."
)


class AShedStandsInTheTown(unittest.TestCase):
    """T4: 'Sorting shed' was minted top-level, a second town beside Saltmarrow."""

    def test_outbuilding_is_the_towns_child(self):
        from app.db import connect
        from app.world import _upsert_location

        seed()
        with connect() as conn:
            _upsert_location(conn, "Sorting shed", "A small shed filled with salvaged goods, ready to be sorted")
            self.assertEqual(int(row(conn, "Sorting shed")["parent_id"]), 1)
            self.assertEqual(str(row(conn, "Sorting shed")["kind"] or ""), "")

    def test_inside_a_child_the_new_one_is_the_towns_too(self):
        from app.db import connect
        from app.world import _upsert_location

        seed()
        with connect() as conn:
            shed = _upsert_location(conn, "Sorting shed", "")
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (shed,))
            _upsert_location(conn, "Net loft", "")
            self.assertEqual(int(row(conn, "Net loft")["parent_id"]), 1)

    def test_roads_far_places_and_plain_names_stay_top_level(self):
        from app.db import connect
        from app.world import _upsert_location

        seed()
        with connect() as conn:
            _upsert_location(conn, "Coast Road", "The road north along the dunes.")
            _upsert_location(conn, "Redhill", "A village two days' walk inland.")
            _upsert_location(conn, "Boathouse", "An old boathouse across the bay, beyond the point.")
            for name in ("Coast Road", "Redhill", "Boathouse"):
                with self.subTest(name=name):
                    self.assertEqual(int(row(conn, name)["parent_id"]), 0)


class AMoveToWhereYouStandIsNoTrip(unittest.TestCase):
    """8B run 10, T0: "MOVE to Saltmarrow dropped" while the player stood in Saltmarrow."""

    def test_no_drop_note(self):
        from app import world
        from app.db import connect

        seed()
        prose = "You stand on the edge of the flats. A narrow path leads toward the town of Saltmarrow [[L1]]."
        with connect() as conn:
            result = {"player": {"move_to_location": "Saltmarrow"}, "narration": prose}
            report = world.resolve_movement(conn, result, "", intent="opening", narration=prose)
            here = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()[0]
        self.assertNotEqual(report.get("status"), "dropped_unshown")
        self.assertEqual(int(here), 1)

    def test_the_shared_check_both_paths_use(self):
        # 8B run 17, T0: the town path calls the same check and still wrote the note.
        from app import world

        patch = {"move_to_location": "Saltmarrow"}
        rows = [{"id": 1, "code": "L1", "name": "Saltmarrow", "parent_id": 0, "kind": ""}]
        got = world._unasked_unshown_move({"player": patch}, patch, rows, "", intent="opening",
                                          narration="You stand on the edge of the flats.", current_name="Saltmarrow")
        self.assertEqual(got, "")

    def test_by_code_or_another_spelling(self):
        # 8B run 30, T2: MOVE "L2" and "the Salvage Guild’s Tally House" while standing in it.
        from app import world

        rows = [{"id": 2, "code": "L2", "name": "The Salvage Guild's Tally House", "parent_id": 1, "kind": ""}]
        for patch in ({"move_to_location_code": "L2"}, {"move_to_location": "the Salvage Guild’s Tally House"},
                      {"move_to_location": "The Salvage Tally House"}):  # 8B run 37, T2: a shorter spelling
            got = world._unasked_unshown_move({"player": patch}, patch, rows, "", intent="conversation",
                                              narration="Gregory leans back.", current_name="The Salvage Guild's Tally House")
            self.assertEqual(got, "", patch)


class SomeoneMetAtTheEndOfAWalk(unittest.TestCase):
    """8B run 11, T3: the fisherman asked at the docks was stored at the district the player left."""

    LINE = ("I head back up toward the docks where the fishermen are readying their nets, and ask the nearest one "
            "whether anyone in Saltmarrow buys old jars or opens locks.")

    def _place(self, line):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            district = world._upsert_location(conn, "Drowned District", "")
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (district,))
            npcs = [{"name": "Eldric Thorne", "location": "L2", "role": "fisherman"}]
            world._place_new_people_at_arrival(conn, npcs, {"player": {"move_to_location_code": "L1"}}, line)
        return npcs[0]["location"]

    def test_the_one_asked_after_the_walk_is_at_the_end(self):
        self.assertEqual(self._place(self.LINE), "L1")

    def test_someone_asked_before_the_walk_stays(self):
        self.assertEqual(self._place("I ask the fisherman about the jar, then head back up to the docks."), "L2")

    def _place_known(self, narration):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            district = world._upsert_location(conn, "Drowned District", "")
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (district,))
            world._upsert_npc(conn, {"name": "Eldric Thorne", "location": "L2", "role": "fisherman"})
            npcs = [{"name": "Eldric Thorne", "location": "L2", "role": "fisherman"}]
            world._place_new_people_at_arrival(conn, npcs, {"player": {"move_to_location_code": "L1"}}, self.LINE,
                                               narration)
        return npcs[0]["location"]

    def test_someone_known_shown_at_the_end_is_there(self):
        # 8B run 40, T1: the tallyman from the opening, behind his desk, was kept in the town left behind.
        self.assertEqual(self._place_known("At the docks Eldric Thorne looks up from his nets."), "L1")

    def test_someone_known_not_shown_stays(self):
        self.assertEqual(self._place_known("At the docks a fisherman looks up from his nets."), "L2")

    def test_no_op_at_all_but_shown_after_arrival(self):
        # 8B run 60, T1: Milo [[A]] at the tally house, his only op cut with the tail.
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            district = world._upsert_location(conn, "Drowned District", "")
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (district,))
            world._upsert_npc(conn, {"name": "Eldric Thorne", "location": "Drowned District", "role": "fisherman"})
            code = conn.execute("SELECT code FROM npcs WHERE name = 'Eldric Thorne'").fetchone()[0]
            world._place_new_people_at_arrival(
                conn, [], {"player": {"move_to_location_code": "L1"}}, self.LINE,
                f"You climb back up to Saltmarrow. By the nets, Eldric Thorne [[{code}]] looks up.")
            where = conn.execute("SELECT l.code FROM npcs n JOIN locations l ON l.id = n.location_id "
                                 "WHERE n.name = 'Eldric Thorne'").fetchone()[0]
        self.assertEqual(where, "L1")

    def test_a_code_only_talk_moves_the_one_shown(self):
        # 8B run 53, T1: TALK "A" alone, and Elsabet [[A]] behind the counter stayed in town.
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            district = world._upsert_location(conn, "Drowned District", "")
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (district,))
            world._upsert_npc(conn, {"name": "Eldric Thorne", "location": "Drowned District", "role": "fisherman"})
            code = conn.execute("SELECT code FROM npcs WHERE name = 'Eldric Thorne'").fetchone()[0]
            world._place_new_people_at_arrival(
                conn, [{"code": code, "name": "", "role": "local"}], {"player": {"move_to_location_code": "L1"}},
                self.LINE, f"At the docks Eldric Thorne [[{code}]] looks up from his nets.")
            where = conn.execute("SELECT l.code FROM npcs n JOIN locations l ON l.id = n.location_id "
                                 "WHERE n.name = 'Eldric Thorne'").fetchone()[0]
        self.assertEqual(where, "L1")


class AnErrandInTownIsNoDiscovery(unittest.TestCase):
    """8B run 42, T1: walking to the guild's tally house by name paid 6 XP as a new place."""

    def _outcomes(self, name, line):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            world._upsert_location(conn, name, "", parent_id=1)
            return world._turn_outcomes(conn, {"player": {"move_to_location": name}}, player_input=line)

    def test_the_tally_house_is_an_errand(self):
        self.assertNotIn("new_place", self._outcomes(
            "The Salvage Guild's Tally House", "I walk up into town to the salvage guild's tally house."))

    def test_exploring_still_counts(self):
        self.assertIn("new_place", self._outcomes(
            "The Salvage Guild's Tally House", "I explore the town and find the salvage guild's tally house."))

    def test_a_named_place_that_is_no_building_counts(self):
        self.assertIn("new_place", self._outcomes("The Sunken Causeway", "I wade out to the sunken causeway."))

    def test_the_tallyman_met_there_is_no_find(self):
        # 8B run 58, T1.
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            house = world._upsert_location(conn, "The Salvage Guild's Tally House", "", parent_id=1)
            conn.execute("UPDATE locations SET visit_count = 1 WHERE id = ?", (house,))
            before = int(conn.execute("SELECT COALESCE(MAX(id), 0) FROM npcs").fetchone()[0])
            world._upsert_npc(conn, {"name": "Elias Vane", "location": "The Salvage Guild's Tally House", "role": "tallyman"})
            outcomes = world._turn_outcomes(conn, {"player": {}}, player_input="I walk up to the tally house.",
                                            max_npc_before=before)
            self.assertNotIn("new_person", outcomes)
            world._upsert_npc(conn, {"name": "Rook", "location": "Saltmarrow", "role": "beachcomber"})
            outcomes = world._turn_outcomes(conn, {"player": {}}, player_input="I walk the flats.",
                                            max_npc_before=before)
            self.assertIn("new_person", outcomes)

    def test_a_place_visited_before_is_no_find(self):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            place = world._upsert_location(conn, "The Sunken Causeway", "", parent_id=1)
            conn.execute("UPDATE locations SET visit_count = 2 WHERE id = ?", (place,))
            outcomes = world._turn_outcomes(conn, {"player": {"move_to_location": "The Sunken Causeway"}},
                                            player_input="I wade out to the sunken causeway.")
        self.assertNotIn("new_place", outcomes)


class TheAskedPlaceBeforeTheLane(unittest.TestCase):
    """8B run 75, T1: "you step into the narrow lane leading to the salvage guild's tally house" made "Narrow Lane"."""

    def test_the_tally_house_is_reached(self):
        from app import world
        from app.db import connect

        seed()
        line = ("Before the tide turns I walk up into town to the salvage guild's tally house to ask the tallyman what "
                "work he'll take against my debt.")
        prose = ("You step into the narrow lane leading to the salvage guild's tally house. You pass a tinker's cart. "
                 "You reach the tally house, a squat structure with a crooked roof. The door creaks open as you approach.")
        with connect() as conn:
            self.assertEqual(world._venue_requested_and_reached(conn, line, prose, "L1"), "The Salvage Guild's Tally House")


class TheBerthAfterTheWreck(unittest.TestCase):
    """8B run 73, T6: lifting the core "out of the hull" walked Isk off; "no one pays you much mind" paid +35;
    "The Salvage Union's Tally House" made a second tally house."""

    def test_lifting_out_is_no_exit(self):
        from app import world

        self.assertEqual(world.venue_move_intent(
            "I tuck the logbook inside my tunic, go back and lift the freed iron core out of the hull, and carry "
            "it up onto the berth."), "")
        self.assertEqual(world.venue_move_intent("I step back out into the street."), "exit")

    def test_paying_mind_is_no_coin(self):
        from app import world

        prose = ("You set the iron core down on the planks. A few workers move about, but no one pays you much mind. "
                 "The logbook feels like a small victory.")
        result = {"narration": prose, "player": {"gold_delta": 20}}
        note = world._settle_stated_gold(result, "I carry the core up onto the berth.")
        self.assertEqual(note["source"], "gain_without_coin_dropped")

    def test_one_word_off_is_the_same_house(self):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            house = world._upsert_location(conn, "The Salvage Guild's Tally House", "", parent_id=1)
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (house,))
        world.apply_turn({"narration": "You set the core down. The tally house stands beyond the berth.",
                          "locations": [{"name": "The Salvage Union's Tally House", "summary": "a weathered building"}]},
                         player_input="I carry the core up onto the berth.")
        with connect() as conn:
            names = [r[0] for r in conn.execute("SELECT name FROM locations").fetchall()]
        self.assertNotIn("The Salvage Union's Tally House", names)


class AVagueFigureIsTheOneNamedLater(unittest.TestCase):
    """8B run 72, T9: "A figure, crouched low" then "Her name is Edith Skinner" seeded a second, drawn person."""

    PROSE = ("The shadow moves again. A figure, crouched low, slips from the shallows and vanishes into the reeds. "
             "You wait, the air thick with brine.\n\nA voice cuts through the silence. “You’re not the first to "
             "watch that spot,” she says. The speaker emerges from the reeds, a woman with a weathered face. Her "
             "name is Edith Skinner, and she is the bonesetter of the town.")

    def test_no_second_person(self):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            world._upsert_npc(conn, {"name": "Edith Skinner", "role": "bonesetter", "location": "Saltmarrow"})
            seeded = world._ensure_npcs_from_narration(
                conn, {"npcs": [{"name": "Edith Skinner", "role": "bonesetter"}]}, self.PROSE, 1)
        self.assertEqual(seeded, [])


class APromiseIsNoPayAndNoHaul(unittest.TestCase):
    """8B run 71, T4: "you'll be paid thirty gold" paid 30, and "I'll haul the beams" put beams in the pack."""

    LINE = "\"I'll haul the beams off the east pier wreck.\" I nod at the ledger. \"Put my name down. Isk Tarrow, flat-runner.\""
    PROSE = ("The wreck off the east pier is your new task. You'll haul iron beams from the wreckage, and for that, "
             "you'll be paid thirty gold. The tallyman offers no more than that.")

    def test_no_coin(self):
        from app import world

        result = {"narration": self.PROSE, "player": {"gold_delta": 30}}
        note = world._settle_stated_gold(result, self.LINE)
        self.assertEqual(note["source"], "gain_without_coin_dropped")

    def test_no_beams(self):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            kept = world._filter_inventory_changes(conn, [{"name": "Iron beams", "quantity_delta": 1}],
                                                   narration=self.PROSE, player_input=self.LINE, draft_narration=self.PROSE)
        self.assertEqual(kept, [])


class APlacePassedIsNotEntered(unittest.TestCase):
    """8B run 70, T1: "You pass Millicent's Bakery ... continue toward the tally house" entered the bakery."""

    def test_the_bakery_is_passed(self):
        from app import world
        from app.db import connect

        seed()
        line = ("Before the tide turns I walk up into town to the salvage guild's tally house to ask the tallyman "
                "what work he'll take against my debt.")
        prose = ("You pass Millicent's Bakery, where the scent of fresh loaves lingers, and continue toward the "
                 "salvage guild's tally house. The door is heavy. Inside, the air is thick with old parchment.")
        with connect() as conn:
            world._upsert_location(conn, "Millicent's Bakery", "", parent_id=1, kind="bakery")
            self.assertIsNone(world._venue_named_in(conn, 1, line, prose))
            self.assertIsNotNone(world._venue_named_in(conn, 1, "I go into Millicent's Bakery.", "You step inside."))


class ADrawnNameFitsTheOneShown(unittest.TestCase):
    """8B run 68, T1-T2: "a man in a soot-stained coat" got the drawn name "Gunilda"."""

    def test_a_man_gets_a_mans_name(self):
        from app import world
        from app.db import connect
        from app.example_pools import draw_names, world_context, world_options

        seed()
        with connect() as conn:
            ctx = world_context(world_options(conn), sex="female")
            women = {n.split()[0].lower() for n in draw_names(ctx, 200, __import__("random").Random(1), set(), sex="female")}
            for i in range(6):
                npc_id = world._upsert_npc(conn, {"name": "Tallyman", "role": "tallyman", "code": f"Z{i}",
                                                  "location": "Saltmarrow", "_figure_pronouns": "he"})
                name = conn.execute("SELECT name FROM npcs WHERE id = ?", (npc_id,)).fetchone()[0]
                conn.execute("DELETE FROM npcs WHERE id = ?", (npc_id,))
                self.assertNotIn(name.split()[0].lower(), women, name)


class ARoomOfTheBuilding(unittest.TestCase):
    """8B run 64, T4: "go down to the lower vault" in the tally house left the player upstairs."""

    def test_the_vault_is_made_inside(self):
        from app import world
        from app.db import connect

        seed()
        prose = "The vault door groans as you descend the narrow stairwell. The lower vault is dimly lit by a lamp."
        with connect() as conn:
            house = world._upsert_location(conn, "The Salvage Guild's Tally House", "", parent_id=1)
            here = world._location_row(conn, house)
            name = world._room_requested(conn, here, "I nod and go down to the lower vault to search the records.", prose)
            row = conn.execute("SELECT parent_id FROM locations WHERE name = ?", (name,)).fetchone()
        self.assertEqual(name, "The Lower Vault")
        self.assertEqual(int(row[0]), house)

    def test_not_from_the_open_town(self):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            here = world._location_row(conn, 1)
            self.assertEqual(world._room_requested(conn, here, "I go down to the cellar.", "You go down to the cellar."), "")


class ANewPlaceWalkedToIsInTown(unittest.TestCase):
    """8B run 54, T4-T7: "Berth Three" had no parent, so the walk back to the tally house ended in the street."""

    def _adopt(self, line):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            house = world._upsert_location(conn, "The Salvage Guild's Tally House", "", parent_id=1)
            top = int(conn.execute("SELECT MAX(id) FROM locations").fetchone()[0])
            berth = world._upsert_location(conn, "Berth Three", "")
            conn.execute("UPDATE locations SET parent_id = 0 WHERE id = ?", (berth,))
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (berth,))
            world._adopt_new_place_into_town(conn, house, top, line)
            return int(conn.execute("SELECT parent_id FROM locations WHERE id = ?", (berth,)).fetchone()[0] or 0)

    def test_walked_to_is_in_town(self):
        self.assertEqual(self._adopt("I walk down to the docks to find berth three and the foreman Harlow."), 1)

    def test_sailed_to_is_not(self):
        self.assertEqual(self._adopt("I sail out across the bay to find berth three."), 0)


class TheWayIsNotTheEnd(unittest.TestCase):
    """8B run 51, T4: "along the shore path toward the Hollow Reach" made "The Shore" and stood Isk on it."""

    def test_the_walk_ends_at_the_hollow_reach(self):
        from app import world
        from app.db import connect

        seed()
        line = ("I nod to the captain, tuck my hands into my sleeves against the cold, and head out along the shore "
                "path toward the Hollow Reach to find the fisherfolk.")
        prose = ("The wind bites at your sleeves as you step onto the shore path. The morning mist turns the Hollow "
                 "Reach into a grey smear on the horizon. You reach the edge of the settlement.")
        with connect() as conn:
            name = world._outdoor_area_requested(conn, 1, line, prose)
        self.assertEqual(name, "The Hollow Reach")


class AnotherSpellingIsNoNewPlace(unittest.TestCase):
    """8B run 50, T4: LOC_NEW "The Salvage Tally House" in "The Salvage Guild's Tally House" minted a second place."""

    def test_no_second_tally_house(self):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            house = world._upsert_location(conn, "The Salvage Guild's Tally House", "", parent_id=1)
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (house,))
        world.apply_turn({"narration": "Jory taps the ledger. \"The job is to recover what was lost.\"",
                          "locations": [{"name": "The Salvage Tally House", "summary": "a dim room"}]},
                         player_input="\"Name the job, Jory.\"")
        with connect() as conn:
            names = [r[0] for r in conn.execute("SELECT name FROM locations").fetchall()]
        self.assertNotIn("The Salvage Tally House", names)


class LiftingItOutTakesIt(unittest.TestCase):
    """8B run 57, T7: "lift out whatever is glinting" and "You lift the glinting object" refused the ring."""

    def test_the_ring_is_kept(self):
        from app import world
        from app.db import connect

        seed()
        line = "I reach into the hollow and lift out whatever is glinting down there, and turn it over in the grey light."
        prose = ("You lift the glinting object from the hollow, turning it in the grey light. It's a small, tarnished "
                 "ring with a jagged edge, like it was torn from a chain.")
        with connect() as conn:
            kept = world._filter_inventory_changes(conn, [{"name": "tarnished ring", "quantity_delta": 1}],
                                                   narration=prose, player_input=line, draft_narration=prose)
        self.assertEqual([k["name"] for k in kept], ["tarnished ring"])


class AskingWhereIsNoTaking(unittest.TestCase):
    """8B run 47, T3: "I'll take it" (the job) and "Where do the guild's carts wait?" put two carts in the pack."""

    LINE = ("\"I'll take it. A full load, ten silver's worth, and no guild help.\" I nod once. \"Where do the "
            "guild's carts wait when the load comes in?\"")
    PROSE = ("“The carts wait at the wharf—near the third pile of driftwood. They’re marked with a red "
             "stripe and a rusted iron hook.” You nod, the promise of ten silver in your pocket a quiet certainty.")

    def _kept(self, line):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            return world._filter_inventory_changes(conn, [{"name": "red stripe cart", "quantity_delta": 2}],
                                                   narration=self.PROSE, player_input=line, draft_narration=self.PROSE)

    def test_the_carts_stay_at_the_wharf(self):
        self.assertEqual(self._kept(self.LINE), [])


class AQuestionAskedPaysNothing(unittest.TestCase):
    """8B run 45, T2: "You ask what kind of work pays against the ledger" backed GOLD 50 (+37)."""

    def test_the_asked_pay_is_no_coin(self):
        from app import world

        prose = ("The tallyman looks up from his work. You ask what kind of work pays against the ledger, and he "
                 "leans back, a smirk playing on his lips. “We’ve got a job,” he says.")
        result = {"narration": prose, "player": {"gold_delta": 50}}
        note = world._settle_stated_gold(result, "\"What job have you got that pays against the ledger?\"")
        self.assertEqual(note["source"], "gain_without_coin_dropped")
        self.assertNotIn("gold_delta", result["player"])

    def test_willing_to_pay_is_no_payment(self):
        # 8B run 95, T3: "they're willing to pay for it" backed GOLD 15 (+11).
        from app import world

        result = {"player": {"gold_delta": 15}, "narration": (
            "Mira straightens. “That’s where you come in.” This is something the guild wants, and "
            "they’re willing to pay for it.")}
        note = world._settle_stated_gold(result, "\"Why is old kelp worth a winter of credit?\"")
        self.assertEqual(note["source"], "gain_without_coin_dropped")


class TheJobsFigureIsTheOneHere(unittest.TestCase):
    """8B run 45, T2: "The tallyman, a man with a sharp eye" bound NPC_NEW "Ralf Wadley" to the tallyman."""

    def test_the_tallyman_is_no_one_new(self):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            house = world._upsert_location(conn, "Salvage Guild Tally House", "", parent_id=1)
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (house,))
            world._upsert_npc(conn, {"name": "Eldrin Vane", "location": "Salvage Guild Tally House", "role": "tallyman"})
            prose = ("You stand before the desk. The tallyman, a man with a sharp eye and a sharper tongue, looks up "
                     "from his work. “We’ve got a job,” he says.")
            npcs = world._npcs_shown_in_prose(conn, [{"name": "Ralf Wadley", "role": "rat catcher"}], prose)
        self.assertEqual(npcs, [])


class AnUnshownKnownPersonStaysPut(unittest.TestCase):
    """8B run 83, T6: NPC_NEW "Mara" for an unnamed woman on a wreck moved the guild's leader to the bay."""

    def test_the_leader_stays_in_town_in_her_job(self):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            world._upsert_npc(conn, {"name": "Mara", "location": "Saltmarrow", "role": "Salvage Guild Leader"})
            bay = world._upsert_location(conn, "Eastern Bay", "", parent_id=1)
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (bay,))
            prose = ("A moment later, the hooded figure steps down from the wreckage, revealing a woman with a scar. "
                     "\"You're not the first to come for it,\" she says.")
            npcs = world._npcs_shown_in_prose(
                conn, [{"name": "Mara", "role": "tide watcher", "location": "Eastern Bay"}], prose
            )
            for npc in npcs:
                world._upsert_npc(conn, npc)
            mara = conn.execute("SELECT location_id, role FROM npcs WHERE name = 'Mara'").fetchone()
        self.assertEqual(int(mara["location_id"]), 1)
        self.assertEqual(mara["role"], "Salvage Guild Leader")

    def test_named_in_the_prose_she_comes(self):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            world._upsert_npc(conn, {"name": "Mara", "location": "Saltmarrow", "role": "Salvage Guild Leader"})
            bay = world._upsert_location(conn, "Eastern Bay", "", parent_id=1)
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (bay,))
            prose = "Mara steps down from the wreckage and looks you over."
            for npc in world._npcs_shown_in_prose(conn, [{"name": "Mara", "location": "Eastern Bay"}], prose):
                world._upsert_npc(conn, npc)
            mara = conn.execute("SELECT location_id FROM npcs WHERE name = 'Mara'").fetchone()
        self.assertEqual(int(mara["location_id"]), int(bay))


class TalkedToAndShownHereIsHere(unittest.TestCase):
    """8B run 109, T5: TALK "C" and "Thaddeus Grimes [[C]], the tallyman, steps out" at the reeve's; he stayed away."""

    def test_he_is_here(self):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            house = world._upsert_location(conn, "The Salvage Guild's Tally House", "", parent_id=1)
            office = world._upsert_location(conn, "The reeve's office", "", parent_id=1)
            world._upsert_npc(conn, {"name": "Thaddeus Grimes", "role": "tallyman", "location": "The Salvage Guild's Tally House"})
            code = conn.execute("SELECT code FROM npcs WHERE name = 'Thaddeus Grimes'").fetchone()[0]
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (office,))
            prose = (f"The reeve's door creaks open. Thaddeus Grimes [[{code}]], the tallyman, steps out, his face a "
                     "map of exhaustion.")
            result = {"narration": prose, "player": {}, "conversations": [{"npc_code": code, "topic": "the contract"}]}
            world._place_talked_to_in_scene(conn, [], result)
            at = conn.execute("SELECT location_id FROM npcs WHERE name = 'Thaddeus Grimes'").fetchone()[0]
        self.assertEqual(int(at), int(office))

    def test_only_talked_about_he_stays(self):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            house = world._upsert_location(conn, "The Salvage Guild's Tally House", "", parent_id=1)
            office = world._upsert_location(conn, "The reeve's office", "", parent_id=1)
            world._upsert_npc(conn, {"name": "Thaddeus Grimes", "role": "tallyman", "location": "The Salvage Guild's Tally House"})
            code = conn.execute("SELECT code FROM npcs WHERE name = 'Thaddeus Grimes'").fetchone()[0]
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (office,))
            prose = f"“Thaddeus Grimes [[{code}]] sent me,” you say. The reeve looks up."
            result = {"narration": prose, "player": {}, "conversations": [{"npc_code": code, "topic": "the contract"}]}
            world._place_talked_to_in_scene(conn, [], result)
            at = conn.execute("SELECT location_id FROM npcs WHERE name = 'Thaddeus Grimes'").fetchone()[0]
        self.assertEqual(int(at), int(house))


class TheJobIsNoPartOfTheName(unittest.TestCase):
    """8B run 104, T1: NAME "Tallyman Darrick" ROLE "Salvage Guild Tallyman" stored "Tallyman Darrick"."""

    def test_the_title_goes(self):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            world._upsert_npc(conn, {"name": "Tallyman Darrick", "role": "Salvage Guild Tallyman", "location": "Saltmarrow"})
            world._upsert_npc(conn, {"name": "Smith Harrow", "role": "fisher", "location": "Saltmarrow"})
            names = sorted(r[0] for r in conn.execute("SELECT name FROM npcs"))
        self.assertEqual(names, ["Darrick", "Smith Harrow"])


class AJobToldAgainTakesTheTelling(unittest.TestCase):
    """8B run 103, T3: the card said "Clear the Guild's Sheds"; Garrick then said salvage from the docks."""

    PROSE = ("“I am up for it,” you say. “What is the job, and how much does it take off the ledger?” "
             "Garrick Thorne [[A]]’s fingers drum a slow rhythm on the counter. “A job,” he says. "
             "“You’ll be fetching salvage from the docks. The storm’s left a mess—ships grounded, cargo "
             "spilled. You’ll be paid in coin, but the real reward is the ledger.”")

    def test_the_card_matches_what_he_said(self):
        from app import quest_parser, world
        from app.db import connect
        from app.quests import create_quest

        seed()
        with connect() as conn:
            house = world._upsert_location(conn, "The Salvage Guild's Tally House", "", parent_id=1)
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (house,))
            world._upsert_npc(conn, {"name": "Garrick Thorne", "code": "A", "role": "tallyman",
                                     "location": "The Salvage Guild's Tally House"})
            gid = conn.execute("SELECT id FROM npcs WHERE code = 'A'").fetchone()[0]
            qid = create_quest(conn, title="Clear the Guild's Sheds", steps=[{"title": "Gather tools from the storage room"}],
                               giver_npc_id=gid, status="offered", created_turn=2)
            reply = {"new": [{
                "title": "Fetch Salvage from the Docks", "giver": "Garrick Thorne", "difficulty": "normal",
                "summary": "Fetch salvage from the docks to reduce the ledger.",
                "steps": [{"title": "Fetch salvage from the docks", "description": "Collect what the storm left.",
                           "location": ""}],
                "reward": {"gold": 0, "xp": 0, "items": [], "text": "the real reward is the ledger"},
                "offer_line": "You’ll be fetching salvage from the docks.",
                "evidence": "You’ll be fetching salvage from the docks.", "_from_mark": True}], "updates": []}
            quest_parser.apply_quest_changes(conn, reply, narration=self.PROSE,
                                             player_input='"I am up for it." I rest my hands on the counter. "What is the job?"',
                                             turn=3)
            rows = [tuple(r) for r in conn.execute("SELECT id, title, status FROM quests")]
            step = conn.execute("SELECT title FROM quest_steps WHERE quest_id = ?", (qid,)).fetchone()[0]
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual(rows[0][1], "Fetch Salvage from the Docks")
        self.assertEqual(step, "Fetch salvage from the docks")


class AShortNameIsTheKnownPlace(unittest.TestCase):
    """8B run 102, T1: LOC "tally house" beside "The Salvage Guild's Tally House" minted a second one."""

    def test_the_tail_of_one_place_is_that_place(self):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            house = world._upsert_location(conn, "The Salvage Guild's Tally House", "", parent_id=1)
            self.assertEqual(world._find_location_id(conn, "tally house"), int(house))
            count = conn.execute("SELECT COUNT(*) FROM locations").fetchone()[0]
        self.assertEqual(count, 2)

    def test_a_word_left_out_is_the_same_place(self):
        # 8B run 111, T4: "The Salvage Tally House" for "The Salvage Guild's Tally House".
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            house = world._upsert_location(conn, "The Salvage Guild's Tally House", "", parent_id=1)
            self.assertEqual(world._find_location_id(conn, "The Salvage Tally House"), int(house))

    def test_a_name_only_spoken_of_is_not_the_figure(self):
        # 8B run 111, T4: '"Ellen Croft," he repeats' and the hooded woman's "She's not here".
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            prose = ("“Ellen Croft,” he repeats. A figure steps inside, her cloak damp with brine. The "
                     "woman tilts her head. “She’s not here,” she says.")
            npcs = world._npcs_shown_in_prose(conn, [{"name": "Ellen Croft", "role": "mysterious figure"}], prose)
            self.assertEqual(npcs, [])
            intro = "A figure steps inside. “I’m Ellen Croft,” she says."
            named = world._npcs_shown_in_prose(conn, [{"name": "Ellen Croft", "role": "mysterious figure"}], intro)
        self.assertEqual([n["name"] for n in named], ["Ellen Croft"])

    def test_two_such_places_mint_nothing_by_guess(self):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            a = world._upsert_location(conn, "The North Tally House", "", parent_id=1)
            b = world._upsert_location(conn, "The South Tally House", "", parent_id=1)
            got = world._find_location_id(conn, "tally house")
        self.assertNotIn(got, (int(a), int(b)))


class ANamedFigureAndAnotherAreTwoPeople(unittest.TestCase):
    """8B run 101, T4: "a figure standing at the bow—Captain Miren" and "a man with a weathered face"
    stored only a drawn dock hand."""

    PROSE = ("You scan the area, your gaze settling on a ship with a blackened mast and a figure standing at the "
             "bow—Captain Miren, her silhouette sharp against the early light.\n\nA creak of wood draws your "
             "attention. A figure steps from the shadows, their boots scuffing the planks. It’s a man with a "
             "weathered face and a coat patched with tar.")

    def test_both_are_stored(self):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            docks = world._upsert_location(conn, "The Docks", "", parent_id=1)
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (docks,))
            world._ensure_npcs_from_narration(conn, {"narration": self.PROSE, "npcs": []}, self.PROSE, docks)
            rows = [tuple(r) for r in conn.execute("SELECT name, role FROM npcs ORDER BY id")]
        self.assertEqual(len(rows), 2, rows)
        self.assertEqual(rows[0], ("Miren", "captain"))


class TheTallymanStandsWhereTheWalkEnds(unittest.TestCase):
    """8B run 100: the tallyman, LOC "L1" for "Inside, the tallyman ...", stayed in town; then his move was refused."""

    LINE = ("Before the tide turns I walk up into town to the salvage guild's tally house to ask the tallyman what "
            "work he'll take against my debt.")

    def test_a_place_made_this_turn_gets_its_people(self):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            npcs = [{"name": "Veyra Drowned", "role": "tallyman", "location": "L1"}]
            result = {"player": {"move_to_location": "Salvage Guild Tally House"}}
            world._place_new_people_at_arrival(conn, npcs, result, self.LINE, "Inside, the tallyman looks up.")
            self.assertEqual(result.get("_arrive_with_player"), ["Veyra Drowned"])
            for npc in npcs:
                world._upsert_npc(conn, npc)
            house = world._upsert_location(conn, "Salvage Guild Tally House", "", parent_id=1)
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (house,))
            world._stand_new_people_at_arrival(conn, result, 1)
            at = conn.execute("SELECT location_id FROM npcs WHERE name = 'Veyra Drowned'").fetchone()[0]
        self.assertEqual(int(at), int(house))

    def test_someone_known_shown_at_the_new_place_comes(self):
        # 8B run 108, T4: "Elias Vane [[B]] watches from a distance" at the new Eastern Dock.
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            house = world._upsert_location(conn, "The Salvage Guild's Tally House", "", parent_id=1)
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (house,))
            world._upsert_npc(conn, {"name": "Elias Vane", "code": "B", "role": "tallyman",
                                     "location": "The Salvage Guild's Tally House"})
            prose = ("You step out of the tally house and make your way east. The merchant ship is half-buried in the "
                     "muck by the Eastern Dock. You crouch down. Elias Vane watches from a distance.")
            result = {"player": {"move_to_location": "Eastern Dock"}}
            line = "I leave the tally house and walk down to the eastern dock, looking for the ship. I ask about it."
            world._place_new_people_at_arrival(conn, [], result, line, prose)
            dock = world._upsert_location(conn, "Eastern Dock", "", parent_id=1)
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (dock,))
            world._stand_new_people_at_arrival(conn, result, int(house))
            at = conn.execute("SELECT location_id FROM npcs WHERE name = 'Elias Vane'").fetchone()[0]
        self.assertEqual(int(at), int(dock))

    def test_shown_by_job_he_may_come(self):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            world._upsert_npc(conn, {"name": "Veyra Drowned", "location": "Saltmarrow", "role": "tallyman"})
            house = world._upsert_location(conn, "Salvage Guild Tally House", "", parent_id=1)
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (house,))
            prose = "The guild’s clerk, a man with a face like weathered leather, looks up from his ledger."
            for npc in world._npcs_shown_in_prose(
                conn, [{"name": "Veyra Drowned", "role": "guild clerk", "location": "Salvage Guild Tally House"}], prose
            ):
                world._upsert_npc(conn, npc)
            at = conn.execute("SELECT location_id FROM npcs WHERE name = 'Veyra Drowned'").fetchone()[0]
        self.assertEqual(int(at), int(house))


class TheEmployerIsNoOneThere(unittest.TestCase):
    """8B run 95, T3: ROLE "salvage guild scout" bound NPC_NEW "Elias" to "the guild" in the prose."""

    def test_the_guild_is_no_figure(self):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            house = world._upsert_location(conn, "Salvage Guild Tally House", "", parent_id=1)
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (house,))
            prose = ("Mira straightens. This is something the guild wants, and they’re willing to pay for it. "
                     "The words settle like stones in your chest.")
            npcs = world._npcs_shown_in_prose(conn, [{"name": "Elias", "role": "salvage guild scout"}], prose)
        self.assertEqual(npcs, [])


class ACommonNounNameIsAJob(unittest.TestCase):
    """8B run 85, T1: NAME "Tallyman" for "They are the tallyman" stored a person called Tallyman."""

    def test_the_tallyman_gets_a_name(self):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            house = world._upsert_location(conn, "Salvage Guild Tally House", "", parent_id=1)
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (house,))
            prose = ("A single figure sits behind a counter, fingers stained with ink. They are the tallyman, the one "
                     "who keeps track of debts and salvage work.")
            npcs = world._npcs_shown_in_prose(
                conn, [{"name": "Tallyman", "role": "Salvage Guild Ledger Clerk", "location": "Salvage Guild Tally House"}],
                prose,
            )
            for npc in npcs:
                world._upsert_npc(conn, npc)
            names = [r[0] for r in conn.execute("SELECT name FROM npcs").fetchall()]
        self.assertEqual(len(names), 1)
        self.assertNotIn(names[0].lower(), {"tallyman", "the tallyman"})

    def test_a_name_the_prose_writes_as_a_name_stays(self):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            npcs = world._npcs_shown_in_prose(conn, [{"name": "Wren", "role": "netmaker"}], "Wren looks up from her nets.")
        self.assertEqual(npcs[0]["name"], "Wren")


class ALineNoOneSaysIsNotLogged(unittest.TestCase):
    """8B run 44, T0: TALK "You're late, Flat-runner." on a silent opening was logged as said, then echoed."""

    PROSE = ("You stand at the edge of the flats. The first thing you see is a figure standing at the far end of "
             "the flats, watching you.")

    def _logged(self, summary, prose=PROSE):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            conn.execute("DELETE FROM conversations")
            world._upsert_npc(conn, {"name": "Tilda", "location": "L1", "role": "watcher"})
            world._apply_conversations(conn, [{"npc_code": "Tilda", "summary": summary}], 1, prose, "")
            return [r[0] for r in conn.execute("SELECT summary FROM conversations").fetchall()]

    def test_the_unsaid_line_is_not_logged(self):
        self.assertEqual(self._logged("You're late, Flat-runner."), [])

    def test_a_topic_the_scene_shows_is_logged(self):
        self.assertEqual(self._logged("The figure watching you at the flats."), ["The figure watching you at the flats."])

    def test_a_said_line_is_logged(self):
        prose = self.PROSE + " “You're late, Flat-runner,” Tilda says."
        self.assertEqual(self._logged("You're late, Flat-runner.", prose), ["You're late, Flat-runner."])


class SomeoneTalkedToIsInTheScene(unittest.TestCase):
    """8B run 12, T1: the potter's LOC "Saltmarrow Stables" minted stables while she talked in the street."""

    def _place(self, loc, talked=True):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            npcs = [{"name": "Mira", "location": loc, "role": "potter"}]
            convo = [{"npc_code": "MIRA", "topic": "old pots"}] if talked else []
            world._place_talked_to_in_scene(conn, npcs, {"player": {}, "conversations": convo})
            minted = conn.execute("SELECT COUNT(*) FROM locations").fetchone()[0]
        return npcs[0]["location"], minted

    def test_an_unknown_place_is_the_scene(self):
        self.assertEqual(self._place("Saltmarrow Stables"), ("L1", 1))

    def test_someone_shown_in_the_scene_is_in_it(self):
        # 8B run 22, T2: the man at the post, bound to Roger Treloar, came with LOC "Saltmarrow Stables".
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            npcs = [{"name": "Roger Treloar", "location": "Saltmarrow Stables", "_bound_hint": "a man"}]
            world._place_talked_to_in_scene(conn, npcs, {"player": {}, "conversations": []})
        self.assertEqual(npcs[0]["location"], "L1")

    def test_someone_where_the_walk_goes_stays_there(self):
        # 8B run 38, T5: the figure on "The Northern Coast Road" was put in the tally house left behind.
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            npcs = [{"name": "Eldrin", "location": "The Northern Coast Road", "_bound_hint": "a figure"}]
            world._place_talked_to_in_scene(conn, npcs, {"player": {"move_to_location": "The Northern Coast Road"},
                                                         "conversations": []})
        self.assertEqual(npcs[0]["location"], "The Northern Coast Road")

    def test_a_known_place_or_no_talk_is_kept(self):
        self.assertEqual(self._place("Saltmarrow")[0], "Saltmarrow")
        self.assertEqual(self._place("Saltmarrow Stables", talked=False)[0], "Saltmarrow Stables")


class AWalkDownTheSlopeToTheDocks(unittest.TestCase):
    """8B run 13, T3: "I head down the slope toward the old docks" left the player in the square."""

    LINE = "I nod once. \"By dusk, then.\" I head down the slope toward the old docks, keeping to the firm mud near the pilings."
    PROSE = ("\"By dusk, then,\" you say. The mud clings to your boots as you descend the slope. The distant creak of "
             "pulleys and the occasional shout from the dockworkers echo through the morning haze. You keep to the edge "
             "of the pilings, where the ground is less treacherous.")

    def test_the_old_docks_are_reached(self):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            result = {"player": {}, "narration": self.PROSE}
            report = world.resolve_movement(conn, result, self.LINE, intent="travel", narration=self.PROSE)
        self.assertEqual(report.get("status"), "repaired")
        self.assertEqual(report.get("destination"), "The Old Docks")


class SpeechNeverAsksToGo(unittest.TestCase):
    """8B run 16, T3: '"I'll walk the first stretch with you"' kept a MOVE the cut scene never shows."""

    LINE = ("\"New routes.\" I check the tide-reckoner, for all the good it does. \"Show me one, Alaric. I'll walk the "
            "first stretch with you while the water's out.\"")
    PROSE = ("\"New routes,\" you say. The tide-reckoner's face gleams. Alaric watches you, then gestures toward the "
             "east. A narrow path cuts through the square, leading toward the edge of the harbor. \"Start there,\" he says.")

    def test_the_move_is_dropped(self):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            result = {"player": {"move_to_location": "Saltmarrow's East Passage"}, "narration": self.PROSE}
            report = world.resolve_movement(conn, result, self.LINE, intent="travel", narration=self.PROSE)
        self.assertEqual(report.get("status"), "dropped_unshown")


class TheLineNamesTheDrownedLowerDistrict(unittest.TestCase):
    """8B run 17, T1: "pick my way down into the drowned lower district" dropped the MOVE there as unasked."""

    def test_named_with_a_filler_word_between(self):
        from app import world

        line = ("I tap the frozen face of the reckoner, then pick my way down into the drowned lower district along "
                "the line of old fence posts, looking for anything the last tide uncovered.")
        prose = "The lower district lies ahead. You move carefully, your boots crunching on the damp earth."
        patch = {"move_to_location": "Drowned Lower District"}
        rows = [{"id": 1, "code": "L1", "name": "Saltmarrow", "parent_id": 0, "kind": ""}]
        got = world._unasked_unshown_move({"player": patch}, patch, rows, line, intent="investigation", narration=prose)
        self.assertEqual(got, "")
        self.assertTrue(world._line_names_place("down into the drowned lower district", world._place_words("Drowned Lower District")))
        self.assertFalse(world._line_names_place("the drowned cellar by the district wall", world._place_words("Drowned Lower District")))
        self.assertTrue(world.travel_intent(line))
        self.assertFalse(world.travel_intent("I make my way through the ledger page by page, looking for her name."))


class StowingItIsTakingIt(unittest.TestCase):
    """8B run 18, T3: "I coil the chain section and stow it in my pack" kept nothing; the draft wrote no GRANT."""

    def test_the_chain_reaches_the_pack(self):
        from app import world
        from app.db import connect

        seed()
        line = ("I coil the chain section and stow it in my pack, then trace one of the etched symbols with my thumb. "
                "Do I know this mark?")
        prose = ("The wind tugs at your pack as you coil the chain and tuck it away. Your thumb traces the etched "
                 "symbol, its lines rough and uneven. You don't recognize it.")
        with connect() as conn:
            changes = world._grant_shown_takes(conn, [], prose, line)
        self.assertTrue(any("chain" in str(c.get("name") or "") for c in changes), changes)

    def test_putting_it_on_the_table_is_no_take(self):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            changes = world._grant_shown_takes(conn, [], "You set the lamp down and put it on the table.",
                                               "I put the lamp on the table.")
        self.assertEqual(changes, [])


class TheGuildsTallyHouseIsNoSalvageYard(unittest.TestCase):
    """8B run 26, T1: "to the salvage guild's tally house" opened a "Saltmarrow Salvage Yard"."""

    LINE = ("Before the tide turns I walk up into town to the salvage guild's tally house to ask the tallyman what "
            "work he'll take against my debt.")
    PROSE = ("You head toward the salvage guild's tally house, a squat building with a rusted door. Inside, the scent "
             "of oil and rusted metal fills the room. The tallyman is a man with a scar.")

    def test_the_tally_house_is_entered(self):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            report = world.resolve_movement(conn, {"player": {}, "narration": self.PROSE}, self.LINE, intent="travel",
                                            narration=self.PROSE)
        self.assertEqual(report.get("destination"), "The Salvage Guild's Tally House")

    def test_inside_after_it_is_the_entry(self):
        # 8B run 28, T1: "The salvage guild's tally house looms ahead ... Inside, the scent of oil ..."
        from app import world
        from app.db import connect

        seed()
        prose = ("You step off the cobbled path. The salvage guild's tally house looms ahead, its weathered sign "
                 "creaking in the breeze. Inside, the scent of oil and damp wood mixes with the tang of seaweed.")
        with connect() as conn:
            report = world.resolve_movement(conn, {"player": {}, "narration": prose}, self.LINE, intent="travel",
                                            narration=prose)
        self.assertEqual(report.get("destination"), "The Salvage Guild's Tally House")

    def test_the_heads(self):
        from app import llm

        self.assertEqual(llm._asked_destination_heads("I go into the apothecary for a salve.", whole=True), {"apothecary"})
        self.assertEqual(llm._asked_destination_heads("I head back across the flats to the salvage yard in Saltmarrow "
                                                      "to sell the brass.", whole=True), {"yard"})


class TheShellsHandedOverAreAllOfThem(unittest.TestCase):
    """8B run 37, T6: "You hand over the shells" took 1 of 2."""

    def test_whole_stack(self):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            conn.execute("DELETE FROM inventory")
            conn.execute("INSERT INTO inventory (name, quantity) VALUES ('shells', 2)")
            self.assertEqual(world._whole_stack_handed(conn, "shells", "You hand over the shells, and she counts them."), 2)
            self.assertEqual(world._whole_stack_handed(conn, "shells", "You hand her one of the shells."), 0)
            self.assertEqual(world._whole_stack_handed(conn, "shells", "\"Hand over the shells,\" she says."), 0)


class FollowingToTheDoorIsNoJourney(unittest.TestCase):
    """T9: 'I follow Oldfield to the shed door' counted as travel, so a MOVE out to Saltmarrow stood."""

    def test_travel_intent(self):
        from app.world import travel_intent

        self.assertFalse(travel_intent(T9_LINE))
        self.assertFalse(travel_intent("I walk over to the counter and set the fittings down."))
        self.assertTrue(travel_intent(T3_LINE))
        self.assertTrue(travel_intent("I follow her out of the inn and down to the harbour."))
        self.assertTrue(travel_intent("I follow Oldfield."))

    def test_the_move_out_is_dropped(self):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            shed = world._upsert_location(conn, "Sorting shed", "")
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (shed,))
            result = {"player": {"move_to_location": "Saltmarrow"}, "narration": T9_PROSE}
            report = world.resolve_movement(conn, result, T9_LINE, intent="claim_check", narration=T9_PROSE)
        self.assertEqual(report["status"], "dropped_unshown")
        self.assertIsNone(result["player"]["move_to_location"])


class WalkingToANamedBuilding(unittest.TestCase):
    """T3: 'I head down to the salvage yard' in a world of one place left her in the square."""

    def test_the_yard_is_made_and_reached(self):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            result = {"player": {}, "narration": T3_PROSE}
            report = world.resolve_movement(conn, result, T3_LINE, intent="travel", narration=T3_PROSE)
            self.assertEqual((report["status"], report.get("rule")), ("repaired", "venue_requested"))
            yard = row(conn, report["destination"])
            self.assertIsNotNone(yard)
            self.assertEqual((int(yard["parent_id"]), str(yard["kind"])), (1, "salvage_yard"))
            self.assertEqual(result["player"]["move_to_location"], str(yard["name"]))
            # The second time it is found, not made again.
            again = world._venue_requested_and_reached(conn, T3_LINE, T3_PROSE, "L1")
            self.assertEqual(again, str(yard["name"]))
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM locations WHERE kind = 'salvage_yard'").fetchone()[0], 1)

    def test_not_when_the_prose_stays(self):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            prose = "Simon shakes his head. \"The salvage yard is shut till the bell,\" he says. You stay by the wall."
            self.assertEqual(world._venue_requested_and_reached(conn, T3_LINE, prose, "L1"), "")
            self.assertEqual(
                world._venue_requested_and_reached(conn, "What does the salvage yard pay?", T3_PROSE, "L1"), ""
            )


class BuildingsNamedInPassing(unittest.TestCase):
    """T0: the opening named an inn and a dairy in Saltmarrow and neither was made."""

    def test_recorded_as_the_towns_children(self):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            made = world._record_named_buildings(conn, T0_PROSE)
            self.assertEqual(sorted(made), ["Elwood and Daughters Dairy", "The Anchor and Ox"])
            inn = row(conn, "The Anchor and Ox")
            self.assertEqual((int(inn["parent_id"]), str(inn["kind"])), (1, "inn"))
            self.assertEqual(int(row(conn, "Elwood and Daughters Dairy")["parent_id"]), 1)
            # Once known, not made twice.
            self.assertEqual(world._record_named_buildings(conn, T0_PROSE), [])

    def test_speech_and_far_off_are_not_recorded(self):
        from app import world
        from app.db import connect

        seed()
        with connect() as conn:
            prose = (
                "\"The Crooked Mast tavern serves the worst ale on the coast,\" Simon says. "
                "Far out across the flats, the Gull Rock lighthouse blinks."
            )
            self.assertEqual(world._record_named_buildings(conn, prose), [])


class NoTownCodeOnAnInn(unittest.TestCase):
    """T0: 'the Badger at Saltmarrow [[L1]]' - the town's code read as the inn's."""

    def test_tail_of_a_longer_name_is_not_tagged(self):
        from app.llm import _inject_entity_codes_for_known_names

        out = _inject_entity_codes_for_known_names(T0_PROSE, {"L1": "Saltmarrow"})
        self.assertIn("the Badger at Saltmarrow, a familiar sight", out)
        self.assertIn("edge of Saltmarrow [[L1]]", out)
        out = _inject_entity_codes_for_known_names("Back in Saltmarrow, the tide turns.", {"L1": "Saltmarrow"})
        self.assertIn("Back in Saltmarrow [[L1]]", out)


if __name__ == "__main__":
    unittest.main()
