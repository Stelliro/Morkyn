"""8B run 146, T56: a well in a clearing in the woods is not a venue.

"I put the vial back where it lay and walk to the well" at "The clearing"
(a wild place reached along a stream) opened a venue "The clearing Well" and
moved the player into it. Venues open in settlements; a feature of a wild
place is a thing in that place, and the player stays put.

Run:  .venv\\Scripts\\python -m unittest tests.test_8b_run146_wild_well
"""
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-run146-well-"))
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


LINE = "I put the vial back where it lay and walk to the well. I lower the bucket on its rope, draw it up, and taste the water."
PROSE = ("The vial is returned to its resting place, a small stone ledge beside the well. You walk toward the well, the "
         "morning light catching on the wooden bucket as you lower it on its rope. The taste is sharp, a hint of salt.")


class AWellInTheWoodsIsNoVenue(unittest.TestCase):
    def test_no_venue_opens_in_a_clearing(self):
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        with connect() as conn:
            clearing = world._upsert_location(conn, "The clearing", "A narrow strip of cleared ground by a stream.")
            self.assertEqual(world._mint_venue_from_request(conn, int(clearing), LINE, PROSE), "")
            self.assertEqual(world._venue_requested_and_reached(conn, LINE, PROSE, "L%d" % int(clearing)), "")
            conn.rollback()

    def test_a_coil_of_rope_is_the_rope(self):
        # 8B run 146, T88: GRANT "rope" and GRANT "coil" for "a coil of rope" put "coil x1" beside the rope.
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        prose = ("Elara gestures toward a shelf where coils of rope hang in neat bundles. You pick up a coil, its texture "
                 "rough under your fingers. You buy a flask of lamp oil, its glass clear and unmarked.")
        line = "I walk with Elara to the general store to buy a coil of rope and a flask of lamp oil."
        changes = [
            {"name": "rope", "quantity_band": "small"},
            {"name": "lamp oil", "quantity_band": "small"},
            {"name": "coil", "quantity_band": "trivial"},
        ]
        with connect() as conn:
            kept = world._filter_inventory_changes(conn, changes, narration=prose, player_input=line)
            self.assertEqual(sorted(c["name"] for c in kept), ["lamp oil", "rope"])
            conn.rollback()

    def test_holding_up_an_owned_thing_takes_no_second_one(self):
        # 8B run 146, T98: GRANT "Captain's Ledger" while the player held up their own made it x2.
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        prose = ("You lower the spike and hold up the Captain's Ledger in the flickering light of the oil lamp. The paper is "
                 "brittle, its edges curled with age, but the ink remains legible.")
        line = "I lower the spike and hold up the Captain's Ledger in the lantern light. \"I am no scavenger.\""
        with connect() as conn:
            conn.execute("INSERT INTO inventory (code, name, quantity) VALUES ('I9', 'Captain''s Ledger', 1)")
            kept = world._filter_inventory_changes(conn, [{"name": "Captain's Ledger", "quantity_band": "small"}],
                                                    narration=prose, player_input=line)
            self.assertEqual(kept, [])
            # Another one handed over still arrives.
            handed = "Rolf hands you a second ledger, its cover stamped with the Captain's mark. You take the ledger."
            kept = world._filter_inventory_changes(conn, [{"name": "ledger", "quantity_band": "small"}],
                                                    narration=handed, player_input="I take it.")
            self.assertEqual([c["name"] for c in kept], ["ledger"])
            conn.rollback()

    def test_a_things_provenance_is_no_hand_over(self):
        # 8B run 147, T23: "a brass instrument your mother gave you" put a second tide-reckoner in the pack.
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        prose = ("You flick the wick of your lamp. The tide-reckoner, a brass instrument your mother gave you, hums softly "
                 "as you adjust its gears. It's been a while since you last calibrated it.")
        line = "I sit on the dock edge, light the lantern, and read the tide-reckoner to see how long until low water."
        with connect() as conn:
            conn.execute("DELETE FROM inventory")
            conn.execute("INSERT INTO inventory (code, name, quantity) VALUES ('I91', 'mother''s brass tide-reckoner', 1)")
            kept = world._filter_inventory_changes(conn, [{"name": "Tide-reckoner", "quantity_band": "small"}],
                                                    narration=prose, player_input=line)
            self.assertEqual(kept, [])
            conn.rollback()

    def test_the_same_grant_twice_is_one_gain(self):
        # 8B run 147, T27: two GRANT "Rowing pole" lines put "Rowing pole x2" in the pack.
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        prose = "You take the rowing pole from Wulfstan Orme's hand and lower yourself into the skiff. You grip the pole tightly."
        line = "I take the rowing pole he offers and climb into the skiff."
        with connect() as conn:
            kept = world._filter_inventory_changes(
                conn, [{"name": "Rowing pole", "quantity_band": "small"}, {"name": "Rowing pole", "quantity_band": "small"}],
                narration=prose, player_input=line,
            )
            self.assertEqual([c["name"] for c in kept], ["Rowing pole"])
            conn.rollback()

    def test_ropes_found_on_the_wreck_are_new_beside_the_rope_bought_in_town(self):
        # 8B run 147, T28: GRANT "Ropes" for the tarred ropes found aboard was bound to the owned "Rope".
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        prose = ("You find a bundle of tarred ropes, their ends frayed but intact, and a rusted iron anchor, its chain tangled "
                 "with seaweed. You pocket the ropes and anchor, feeling the weight of them in your hands.")
        line = "I search the wreck's deck and hull for anything the guild would count as salvage."
        with connect() as conn:
            conn.execute("DELETE FROM inventory")
            conn.execute("INSERT INTO inventory (code, name, quantity) VALUES ('I92', 'Rope', 1)")
            kept = world._filter_inventory_changes(conn, [{"name": "Ropes", "quantity_band": "moderate"}], narration=prose, player_input=line)
            self.assertEqual([c["name"] for c in kept], ["Ropes"])
            # Taking one's own thing back is still the owned one (8B run 146, T22).
            conn.execute("INSERT INTO inventory (code, name, quantity) VALUES ('I93', 'Captain''s Ledger', 1)")
            back = "You take the ledger back out of Wulfstan's hands and tuck it into your shirt."
            kept = world._filter_inventory_changes(conn, [{"name": "ledger", "quantity_band": "small"}], narration=back,
                                                    player_input="I take the ledger back out of Wulfstan's hands.")
            self.assertEqual(kept, [])
            conn.rollback()

    def test_a_title_and_surname_is_the_known_person(self):
        # 8B run 147, T45: "Reeve Dunmore" minted beside Gregory Dunmore, the Harbour Reeve.
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        with connect() as conn:
            town = int(conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()[0])
            conn.execute("INSERT INTO npcs (code, name, role, location_id) VALUES ('X', 'Gregory Dunmore', 'harbour reeve', ?)", (town,))
            matches = world._near_name_matches(conn, "Reeve Dunmore")
            self.assertEqual([str(r["name"]) for r in matches], ["Gregory Dunmore"])
            self.assertEqual(world._near_name_matches(conn, "Reeve Hatcher"), [])
            conn.rollback()

    def test_the_clerk_who_steps_in_is_the_known_clerk(self):
        # 8B run 147, T50: "A clerk steps in" at the tally house, where Mira Venn the clerk was filed, minted "Elias".
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        prose = ("The door creaks open again. A clerk steps in, their face pale with worry. \"The guild's share is due,\" "
                 "they mutter. \"The ledger needs to be marked. Now.\"")
        with connect() as conn:
            here = int(conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()[0])
            conn.execute("INSERT INTO npcs (code, name, role, location_id) VALUES ('A', 'Mira Venn', 'tally clerk', ?)", (here,))
            kept = world._npcs_shown_in_prose(conn, [{"name": "Elias", "role": "clerk", "code": "H"}], prose)
            self.assertEqual([n["name"] for n in kept], ["Mira Venn"])
            # Named apart, the figure is someone else.
            apart = prose + " Mira Venn watches from her own desk, saying nothing."
            kept = world._npcs_shown_in_prose(conn, [{"name": "Elias", "role": "clerk", "code": "H"}], apart)
            self.assertNotIn("Mira Venn", [n["name"] for n in kept])
            conn.rollback()

    def test_taking_a_posted_job_costs_nothing(self):
        # 8B run 147, T67: "I'll take it" had the prose hand the giver the job's own fifteen gold.
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        prose = ("You hand over fifteen gold to Mira Venn, and she nods, a thin smile playing at her lips. \"The contract is "
                 "for a wrecked boat near the mudflats,\" she says.")
        line = "\"Fifteen gold for the mudflats contract. I'll take it.\" I ask Mira what exactly is to be salvaged."
        with connect() as conn:
            conn.execute(
                "INSERT INTO quests (code, title, status, reward_gold) VALUES ('Q4', 'Salvage Contract Near Mudflats', 'offered', 15)"
            )
            result = {"narration": prose, "player": {}}
            note = world._settle_stated_gold(result, line, conn=conn)
            self.assertEqual((note or {}).get("source"), "accept_is_no_payment", note)
            self.assertNotIn("gold_delta", result["player"])
            # A real purchase of another sum still pays.
            result = {"narration": "You hand over three gold to Mira Venn for the chart.", "player": {}}
            note = world._settle_stated_gold(result, "I pay Mira three gold for the chart.", conn=conn)
            self.assertEqual(result["player"].get("gold_delta"), -3, note)
            conn.rollback()

    def test_cargo_hauled_to_the_wharf_is_not_kept(self):
        # 8B run 148, T11: hauling the Mistral's fish to the wharf put "cod fillets x1" in the pack.
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        prose = ("You shoulder the first bundle of fresh-caught cod from the holds. You carry it down the gangplank to the wharf, "
                 "where Roderic is waiting with a cart. You drop it onto the cart, and he grunts.")
        line = "I start hauling: I shoulder the first bundle of fish up out of the hold and carry it down the gangplank to the wharf, then go back for the next."
        with connect() as conn:
            conn.execute("DELETE FROM inventory")
            kept = world._filter_inventory_changes(
                conn, [{"name": "cod fillets", "quantity_delta": -1}, {"name": "cod fillets", "quantity_band": "small"}],
                narration=prose, player_input=line,
            )
            self.assertEqual(kept, [])
            # A thing carried and pocketed is kept.
            pocketed = "You pick up the brass key and carry it over to the lamp, then slip it into your pack."
            kept = world._filter_inventory_changes(conn, [{"name": "brass key", "quantity_band": "small"}], narration=pocketed,
                                                    player_input="I pick up the brass key and carry it over to the lamp to look at it.")
            self.assertEqual([c["name"] for c in kept], ["brass key"])
            conn.rollback()

    def test_a_town_well_still_opens(self):
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        with connect() as conn:
            town = int(conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()[0])
            name = world._mint_venue_from_request(conn, town, "I walk to the well in the square and draw a bucket.", PROSE)
            self.assertTrue(name, "a town well is a venue of the town")
            conn.rollback()


if __name__ == "__main__":
    unittest.main()
