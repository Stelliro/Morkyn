"""Places have insides (run fault log 2026-10-18: F15 and its continuations, F151, F155, F167).

  * F155 (8B run 150, T49): "carry the next crate up the gangplank to the hold"
    made "The Hold" a place of the town beside the wharf.
  * F167 (run 150, T85): a search of the far corner of the Hold made "The
    Hidden Passage" a new place and moved the player into it.
  * F151 cont. 2 (run 150, T92): "a name you'd heard whispered in the docks"
    made "The Docks" beside The Dock.
  * F15 cont. 8 (run 149, T96): "Reeves' Office" and "Reeves’ Office" were
    both made in one turn.
  * F15 cont. 9 (run 149, T99): a dropped MOVE left its new place stored.

Run:  .venv\\Scripts\\python -m unittest test_places_have_insides   (from tests/)
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-places-insides-"))
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


def seed() -> dict[str, int]:
    """Saltmarrow with The Dock and The Wharf on its waterfront and the tally house in the town."""
    from app import db, world
    from app.db import connect

    db.init_db()
    with connect().closing() as conn:
        conn.execute("UPDATE player SET current_location_id = 1 WHERE id = 1")
        conn.execute("DELETE FROM npcs")
        conn.execute("DELETE FROM locations WHERE id != 1")
        conn.execute(
            "UPDATE locations SET code = 'L1', name = 'Saltmarrow', summary = '', parent_id = 0, "
            "kind = '', settlement_size = 'town', keeper_npc_id = 0 WHERE id = 1"
        )
        dock = world._upsert_location(conn, "The Dock", "", parent_id=1, kind="")
        conn.execute("UPDATE locations SET parent_id = 1 WHERE id = ?", (dock,))
        wharf = world._upsert_location(conn, "The Wharf", "", parent_id=1, kind="")
        conn.execute("UPDATE locations SET parent_id = 1 WHERE id = ?", (wharf,))
        tally = world._upsert_location(conn, "The Salvage Guild's Tally House", "", parent_id=1, kind="")
        conn.execute("UPDATE locations SET parent_id = 1 WHERE id = ?", (tally,))
    return {"town": 1, "dock": dock, "wharf": wharf, "tally": tally}


def stand(place_id: int) -> None:
    from app.db import connect

    with connect().closing() as conn:
        conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (place_id,))


def place(name: str):
    from app.db import connect

    with connect().closing() as conn:
        return conn.execute("SELECT * FROM locations WHERE name = ?", (name,)).fetchone()


def count_places() -> int:
    from app.db import connect

    with connect().closing() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM locations").fetchone()[0])


class TwoSpellingsAreOnePlace(unittest.TestCase):
    def test_the_key_drops_apostrophe_shape_possessive_plural_and_the(self):
        from app.world import _place_name_key

        self.assertEqual(_place_name_key("The Docks"), _place_name_key("The Dock"))
        self.assertEqual(_place_name_key("Reeves' Office"), _place_name_key("Reeves’ Office"))
        self.assertEqual(_place_name_key("The Reeve's Office"), _place_name_key("Reeves Office"))
        self.assertNotEqual(_place_name_key("The Dock"), _place_name_key("The Wharf"))
        self.assertNotEqual(_place_name_key("The Glass House"), _place_name_key("The Gas House"))

    def test_the_docks_is_the_dock_already_known(self):
        from app import world
        from app.db import connect

        ids = seed()
        before = count_places()
        with connect().closing() as conn:
            self.assertEqual(world._find_location_id(conn, "the docks"), ids["dock"])
        self.assertEqual(count_places(), before)

    def test_one_turns_two_spellings_make_one_place(self):
        from app import world
        from app.db import connect

        seed()
        with connect().closing() as conn:
            first = world._upsert_location(conn, "Reeves' Office", "")
            second = world._upsert_location(conn, "Reeves’ Office", "")
        self.assertEqual(first, second)

    def test_the_turns_named_buildings_fold_both_spellings(self):
        from app import world
        from app.db import connect

        seed()
        prose = ("You pass the Reeves' office on your left. Further on, the Reeves’ office door stands open "
                 "to the square.")
        with connect().closing() as conn:
            world._record_named_buildings(conn, prose)
            names = [r[0] for r in conn.execute("SELECT name FROM locations").fetchall()]
        offices = [n for n in names if "office" in n.lower()]
        self.assertLessEqual(len(offices), 1, names)

    def test_two_known_places_sharing_the_key_resolve_to_neither(self):
        from app import world
        from app.db import connect

        seed()
        with connect().closing() as conn:
            conn.execute("INSERT INTO locations (code, name, summary) VALUES ('L80', 'Mill Street', '')")
            conn.execute("INSERT INTO locations (code, name, summary) VALUES ('L81', 'The Mills Street', '')")
            self.assertIsNone(world._match_location_by_name(conn, "Mills' Street"))


class APartOfAVesselOrBuildingIsInsideIt(unittest.TestCase):
    def test_the_hold_named_at_the_wharf_is_a_part_of_the_wharf(self):
        from app import world
        from app.db import connect

        ids = seed()
        stand(ids["wharf"])
        with connect().closing() as conn:
            hold = world._upsert_location(
                conn, "The Hold", "A dark, damp space below the wharf.",
                here_line="Rested, I get up and carry the next crate up the gangplank to the hold.",
            )
        self.assertEqual(int(place("The Hold")["parent_id"]), ids["wharf"])
        self.assertEqual(int(place("The Hold")["id"]), hold)

    def test_a_search_of_the_hold_finds_a_passage_inside_it_and_the_player_stays_in_the_hold(self):
        from app import world
        from app.db import connect

        ids = seed()
        with connect().closing() as conn:
            hold = world._upsert_location(conn, "The Hold", "", parent_id=ids["wharf"], kind="")
            conn.execute("UPDATE locations SET parent_id = ? WHERE id = ?", (ids["wharf"], hold))
        stand(hold)
        line = '"Fair enough." I leave the worker be and search the far corner of the Hold myself, behind the tallest stacks.'
        with connect().closing() as conn:
            world._apply_player(conn, {"move_to_location": "The Hidden Passage", "_turn_line": line})
            now = int(conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()[0])
        passage = place("The Hidden Passage")
        self.assertIsNotNone(passage)
        self.assertEqual(int(passage["parent_id"]), hold)
        self.assertEqual(now, int(passage["id"]))

    def test_a_journey_line_keeps_the_old_way(self):
        from app import world
        from app.db import connect

        ids = seed()
        stand(ids["dock"])
        with connect().closing() as conn:
            world._upsert_location(conn, "The Northern Passage", "",
                                   here_line="I sail out for three days to reach the Northern Passage.")
        self.assertNotEqual(int(place("The Northern Passage")["parent_id"] or 0), ids["dock"])

    def test_a_part_whose_name_gives_its_owner_belongs_to_that_owner(self):
        from app import world
        from app.db import connect

        ids = seed()
        with connect().closing() as conn:
            conn.execute("INSERT INTO locations (code, name, summary, parent_id) VALUES ('L70', 'The Mistral', '', ?)",
                         (ids["dock"],))
            mistral = int(conn.execute("SELECT id FROM locations WHERE code = 'L70'").fetchone()[0])
        stand(ids["tally"])
        with connect().closing() as conn:
            world._upsert_location(conn, "The Mistral's Hold", "", here_line="I ask Nell what was in the Mistral's hold.")
        self.assertEqual(int(place("The Mistral's Hold")["parent_id"]), mistral)

    def test_without_the_turns_line_nothing_changes(self):
        from app import world
        from app.db import connect

        ids = seed()
        stand(ids["wharf"])
        with connect().closing() as conn:
            world._upsert_location(conn, "The Hold", "")
        self.assertEqual(int(place("The Hold")["parent_id"] or 0), 0)

    def test_a_name_without_a_part_word_is_not_a_part(self):
        from app import world
        from app.db import connect

        ids = seed()
        stand(ids["wharf"])
        with connect().closing() as conn:
            world._upsert_location(conn, "Gull Rock", "", here_line="I look out at Gull Rock.")
        self.assertNotEqual(int(place("Gull Rock")["parent_id"] or 0), ids["wharf"])


class APartIsEnteredFromItsPlace(unittest.TestCase):
    def _hold(self, ids):
        from app.db import connect

        with connect().closing() as conn:
            conn.execute("INSERT INTO locations (code, name, summary, parent_id) VALUES ('L60', 'The Hold', '', ?)",
                         (ids["wharf"],))
            return int(conn.execute("SELECT id FROM locations WHERE code = 'L60'").fetchone()[0])

    def test_from_inside_its_place_the_move_goes_in(self):
        from app import world
        from app.db import connect

        ids = seed()
        hold = self._hold(ids)
        with connect().closing() as conn:
            gate = world.gate_venue_move(conn, ids["wharf"], hold)
        self.assertEqual(gate["location_id"], hold)
        self.assertIsNone(gate["note"])

    def test_from_across_the_town_the_move_ends_at_its_place(self):
        from app import world
        from app.db import connect

        ids = seed()
        hold = self._hold(ids)
        with connect().closing() as conn:
            gate = world.gate_venue_move(conn, ids["tally"], hold)
        self.assertEqual(gate["location_id"], ids["wharf"])
        self.assertEqual(gate["note"]["kind"], "venue_redirect")

    def test_from_a_part_the_building_next_door_is_still_next_door(self):
        from app import world
        from app.db import connect

        ids = seed()
        hold = self._hold(ids)
        with connect().closing() as conn:
            conn.execute("UPDATE locations SET kind = 'guild_hall' WHERE id = ?", (ids["tally"],))
            self.assertTrue(world._stands_beside(conn, hold, 1))

    def test_a_new_shop_named_inside_a_part_stands_in_the_town(self):
        from app import world
        from app.db import connect

        ids = seed()
        hold = self._hold(ids)
        stand(hold)
        with connect().closing() as conn:
            self.assertEqual(world._venue_parent_for_new_place(conn, "bakery"), 1)


class ADroppedMoveStoresNothing(unittest.TestCase):
    def test_a_place_made_under_the_dropped_moves_name_is_removed(self):
        from app import world
        from app.db import connect

        ids = seed()
        stand(ids["town"])
        with connect().closing() as conn:
            top = int(conn.execute("SELECT MAX(id) FROM locations").fetchone()[0])
            world._upsert_location(conn, "Saltmarrow Bakehouse", "")
            gone = world._unstore_dropped_move_places(conn, top, "Saltmarrow Bakehouse")
        self.assertEqual(gone, ["Saltmarrow Bakehouse"])
        self.assertIsNone(place("Saltmarrow Bakehouse"))

    def test_a_place_someone_is_filed_at_stays(self):
        from app import world
        from app.db import connect

        ids = seed()
        with connect().closing() as conn:
            top = int(conn.execute("SELECT MAX(id) FROM locations").fetchone()[0])
            bake = world._upsert_location(conn, "Saltmarrow Bakehouse", "")
            conn.execute(
                "INSERT INTO npcs (code, location_id, name, race, role, summary, attitude) "
                "VALUES ('B', ?, 'Hilde', 'human', 'baker', '', 'neutral')", (bake,))
            gone = world._unstore_dropped_move_places(conn, top, "Saltmarrow Bakehouse")
        self.assertEqual(gone, [])
        self.assertIsNotNone(place("Saltmarrow Bakehouse"))

    def test_the_place_the_player_reached_stays(self):
        from app import world
        from app.db import connect

        seed()
        with connect().closing() as conn:
            top = int(conn.execute("SELECT MAX(id) FROM locations").fetchone()[0])
            bake = world._upsert_location(conn, "Saltmarrow Bakehouse", "")
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (bake,))
            gone = world._unstore_dropped_move_places(conn, top, "Saltmarrow Bakehouse")
        self.assertEqual(gone, [])

    def test_a_place_known_before_the_turn_stays(self):
        from app import world
        from app.db import connect

        ids = seed()
        with connect().closing() as conn:
            top = int(conn.execute("SELECT MAX(id) FROM locations").fetchone()[0])
            gone = world._unstore_dropped_move_places(conn, top, "The Wharf")
        self.assertEqual(gone, [])
        self.assertIsNotNone(place("The Wharf"))


class APlaceOnlySpokenOfIsNotMade(unittest.TestCase):
    def test_a_persons_place_heard_of_is_not_minted(self):
        from app import world
        from app.db import connect

        ids = seed()
        stand(ids["tally"])
        prose = ("The words were smudged, but you could make out the name Veyra at the bottom. A name you'd heard "
                 "whispered in the Smugglers' Den. Nell's gaze followed yours.")
        npcs = [{"name": "Veyra", "role": "mysterious figure", "location": "the Smugglers' Den"}]
        with connect().closing() as conn:
            world._file_people_at_unshown_places(conn, npcs, prose, "I hold out my hand.")
            world._upsert_npc(conn, npcs[0])
            where = conn.execute("SELECT location_id FROM npcs WHERE name = 'Veyra'").fetchone()
        self.assertIsNone(place("The Smugglers' Den"))
        self.assertIsNone(place("Smugglers' Den"))
        self.assertEqual(int(where[0]), 1)

    def test_a_persons_place_the_prose_walks_into_is_kept(self):
        from app import world
        from app.db import connect

        ids = seed()
        stand(ids["dock"])
        prose = "You step into the Smugglers' Den. Veyra looks up from a table by the fire."
        npcs = [{"name": "Veyra", "role": "smuggler", "location": "the Smugglers' Den"}]
        with connect().closing() as conn:
            world._file_people_at_unshown_places(conn, npcs, prose, "I go into the Smugglers' Den.")
        self.assertEqual(npcs[0]["location"], "the Smugglers' Den")

    def test_a_known_person_is_not_moved(self):
        from app import world
        from app.db import connect

        ids = seed()
        with connect().closing() as conn:
            conn.execute(
                "INSERT INTO npcs (code, location_id, name, race, role, summary, attitude) "
                "VALUES ('V', ?, 'Veyra', 'human', 'smuggler', '', 'neutral')", (ids["dock"],))
            npcs = [{"code": "V", "name": "Veyra", "location": "the Smugglers' Den"}]
            world._file_people_at_unshown_places(conn, npcs, "Someone whispered of the Smugglers' Den.", "I listen.")
        self.assertEqual(npcs[0]["location"], "the Smugglers' Den")


class TheTurnFilesTheHoldInsideTheWharf(unittest.TestCase):
    def test_loc_new_the_hold_on_a_carry_turn(self):
        from app import world

        ids = seed()
        stand(ids["wharf"])
        world.apply_turn(
            {
                "narration": ("The hold below is dark, the only light coming from the narrow opening at the top. "
                              "You lower the next load into the hold."),
                "locations": [{"name": "The Hold", "summary": "A dark, damp space below the wharf."}],
                "player": {"move_to_location": None},
            },
            player_input="Rested, I get up and carry the next crate up the gangplank to the hold.",
        )
        hold = place("The Hold")
        self.assertIsNotNone(hold)
        self.assertEqual(int(hold["parent_id"]), ids["wharf"])


if __name__ == "__main__":
    unittest.main()
