"""Fight list: only people in the fight, and unknown moves stay unmeasured."""

import sqlite3
import unittest

from app.encounter_board import merge_encounter, record_encounter_turn


def _player():
    return {"name": "Bram Holt", "health": 18, "max_health": 20}


def _attack(code="A1", name="Oswin Fen", status="resolved_player_attack"):
    return {
        "turn": 4,
        "combat": {
            "status": status,
            "target": {"code": code, "name": name},
            "resolution": {"outcome": "hit", "damage": 3, "target_health_after": 9},
        },
        "player": _player(),
        "party": [],
        "present": [
            {"code": "A1", "name": "Oswin Fen", "health": 9, "max_health": 12, "role": "miller", "attitude": "hostile", "summary": "A miller with a hooked knife."},
            {"code": "A2", "name": "Mira Voss", "health": 9, "max_health": 9, "role": "clerk", "attitude": "wary", "summary": "Keeps the stall book."},
        ],
        "target": {"code": "A1", "name": "Oswin Fen", "health": 9, "max_health": 12, "role": "miller", "attitude": "hostile", "summary": "A miller with a hooked knife."},
        "named_foes": [],
        "known_abilities": [{"name": "Ember Ward", "description": "A brief heat shield."}],
        "player_input": "I ask Mira Voss where the lane goes, then I attack Oswin Fen.",
        "narration": "Oswin Fen favors his left leg. Oswin Fen casts Ember Ward at you.",
        "sheet": [],
    }


class MergeEncounterTests(unittest.TestCase):
    def test_a_quiet_turn_opens_no_board(self):
        board = merge_encounter(None, {"turn": 2, "combat": {"status": "not_combat"}, "player": _player(), "narration": "You look around."})
        self.assertFalse(board["active"])
        self.assertEqual(board["foes"], [])
        self.assertEqual(board["allies"], [])

    def test_only_the_target_is_listed_when_someone_else_is_named(self):
        board = merge_encounter(None, _attack())
        names = [person["name"] for person in board["foes"]]
        self.assertEqual(names, ["Oswin Fen"])
        self.assertEqual([person["name"] for person in board["allies"]], ["Bram Holt"])
        foe = board["foes"][0]
        self.assertEqual(foe["role"], "miller")
        self.assertEqual(foe["health"], 9)
        self.assertTrue(foe["health_known"])
        self.assertTrue(any("left leg" in note for note in foe["notes"]))
        ability = foe["abilities"][0]
        self.assertEqual(ability["name"], "Ember Ward")
        self.assertTrue(ability["known"])
        self.assertIn("heat shield", ability["detail"])
        self.assertTrue(ability["effectiveness"])

    def test_a_joiner_is_added_and_a_distant_name_is_not(self):
        first = merge_encounter(None, _attack())
        packet = _attack()
        packet["turn"] = 5
        packet["combat"] = {"status": "not_combat"}
        packet["narration"] = "Mira Voss rushes in. Far away, the watch shouts."
        packet["player_input"] = "I keep my guard up."
        board = merge_encounter(first, packet)
        self.assertEqual([person["name"] for person in board["foes"]], ["Oswin Fen", "Mira Voss"])
        self.assertTrue(any("Stepped into the fight." in person["notes"] for person in board["foes"] if person["name"] == "Mira Voss"))

        quiet = _attack()
        quiet["present"] = quiet["present"] + [
            {"code": "A3", "name": "Sella Wren", "health": 8, "max_health": 8, "role": "porter", "attitude": "neutral", "summary": ""},
        ]
        quiet["narration"] = "Someone rushes in from the alley. " + ("The square stays loud. " * 8) + "Sella Wren only watches."
        board = merge_encounter(None, quiet)
        self.assertNotIn("Sella Wren", [person["name"] for person in board["foes"]])

    def test_a_crowd_does_not_become_a_roster(self):
        packet = _attack()
        packet["player_input"] = "I swing at the army and at Oswin Fen."
        packet["narration"] = "The army surges, and Oswin Fen meets you."
        board = merge_encounter(None, packet)
        self.assertEqual([person["name"] for person in board["foes"]], ["Oswin Fen"])
        self.assertIn("crowd", board["scale_note"].lower())

    def test_an_unknown_move_keeps_effectiveness_empty(self):
        packet = _attack()
        packet["narration"] = "Oswin Fen casts a spiral of ash at you."
        board = merge_encounter(None, packet)
        ability = board["foes"][0]["abilities"][0]
        self.assertFalse(ability["known"])
        self.assertIsNone(ability["effectiveness"])
        self.assertIn("spiral of ash", ability["seen"])

    def test_unknown_health_is_not_shown_as_zero(self):
        packet = _attack()
        packet["target"] = {"code": "A9", "name": "Hooded Figure", "health": 0, "max_health": 0}
        packet["present"] = []
        packet["narration"] = "The hooded figure slips aside."
        packet["sheet"] = [packet["target"], _player()]
        board = merge_encounter(None, packet)
        foe = board["foes"][0]
        self.assertFalse(foe["health_known"])
        self.assertIsNone(foe["health"])
        self.assertTrue(board["active"])

    def test_a_swing_with_no_target_stays_open(self):
        board = merge_encounter(
            None,
            {
                "turn": 3,
                "combat": {"status": "needs_target"},
                "player": _player(),
                "present": [],
                "narration": "You swing and hit only air.",
                "player_input": "I attack.",
            },
        )
        self.assertTrue(board["active"])
        self.assertEqual(board["foes"], [])
        self.assertIn("no one person", board["outcome"])

    def test_known_dead_foes_close_the_fight_and_leaving_does_too(self):
        packet = _attack()
        packet["target"]["health"] = 0
        packet["present"][0]["health"] = 0
        packet["sheet"] = [packet["target"], _player()]
        board = merge_encounter(None, packet)
        self.assertFalse(board["active"])
        self.assertIn("cannot keep fighting", board["outcome"])

        left = merge_encounter(merge_encounter(None, _attack()), {"turn": 6, "moved": True, "combat": {"status": "not_combat"}, "player": _player()})
        self.assertFalse(left["active"])
        self.assertIn("left the place", left["outcome"])

    def test_a_companion_stays_on_our_side(self):
        packet = _attack()
        packet["party"] = [{"code": "A2", "name": "Mira Voss", "health": 9, "max_health": 9, "role": "companion"}]
        packet["narration"] = "Mira Voss rushes in beside you. Oswin Fen casts a spiral of ash at you."
        board = merge_encounter(None, packet)
        self.assertIn("Mira Voss", [person["name"] for person in board["allies"]])
        self.assertNotIn("Mira Voss", [person["name"] for person in board["foes"]])


def _memory():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE player (
            id INTEGER PRIMARY KEY,
            name TEXT,
            health INTEGER,
            max_health INTEGER,
            current_location_id INTEGER
        );
        CREATE TABLE npcs (
            id INTEGER PRIMARY KEY,
            code TEXT,
            name TEXT,
            health INTEGER,
            max_health INTEGER,
            location_id INTEGER,
            role TEXT,
            attitude TEXT,
            summary TEXT
        );
        CREATE TABLE abilities (name TEXT, description TEXT);
        CREATE TABLE party_members (id INTEGER PRIMARY KEY, npc_id INTEGER);
        INSERT INTO player VALUES (1, 'Bram Holt', 20, 20, 1);
        INSERT INTO npcs VALUES (1, 'A1', 'Oswin Fen', 9, 12, 1, 'miller', 'hostile', 'A miller with a hooked knife.');
        INSERT INTO npcs VALUES (2, 'A2', 'Mira Voss', 9, 9, 1, 'clerk', 'wary', 'Keeps the stall book.');
        INSERT INTO abilities VALUES ('Ember Ward', 'A brief heat shield.');
        """
    )
    return conn


class RecordEncounterTests(unittest.TestCase):
    def test_a_mentioned_bystander_is_not_added_until_they_join(self):
        conn = _memory()
        board = record_encounter_turn(
            conn,
            turn=4,
            player_input="I ask Mira Voss where the lane goes, then I attack Oswin Fen.",
            narration="Oswin Fen favors his left leg. Oswin Fen casts Ember Ward at you.",
            combat={
                "status": "resolved_player_attack",
                "target": {"code": "A1", "name": "Oswin Fen"},
                "resolution": {"outcome": "hit", "damage": 3, "target_health_after": 9},
            },
            moved=False,
        )
        self.assertEqual([person["name"] for person in board["foes"]], ["Oswin Fen"])
        self.assertTrue(board["foes"][0]["abilities"][0]["known"])
        joined = record_encounter_turn(
            conn,
            turn=5,
            player_input="I keep my guard up.",
            narration="Mira Voss rushes in.",
            combat={"status": "not_combat"},
            moved=False,
        )
        self.assertEqual([person["name"] for person in joined["foes"]], ["Oswin Fen", "Mira Voss"])


if __name__ == "__main__":
    unittest.main()
