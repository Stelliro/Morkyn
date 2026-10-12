"""Pacing fixes from the Saltmarrow API-bridge run (docs/showcase/saltmarrow-findings.md E1, E2, C3).

#119 spend kinds and blocking, #122 a title too early, #103 the character's own trade.
"""
from __future__ import annotations

import os
import random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-saltmarrow-pacing-"))
_ENV = isolated_data_env(str(_TMP))
os.environ.update(_ENV)

from app import world  # noqa: E402
from app.player_resources import action_kind_from_text, typed_recovery_minutes  # noqa: E402
from app.skill_checks import home_ground, resolve_check  # noqa: E402

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


class SpendKinds(unittest.TestCase):
    """#119: waiting was rest, the deep channel was an ability, lying flat was talk."""

    def test_nouns_are_not_casting(self):
        self.assertNotEqual(action_kind_from_text("I head out along the deep channel toward the tower."), "ability")
        self.assertNotEqual(action_kind_from_text("I whistle the call back from the channel."), "ability")
        self.assertEqual(action_kind_from_text("I cast a spell on the door."), "ability")
        self.assertEqual(action_kind_from_text("I channel my power into the ward."), "ability")

    def test_lying_flat_is_not_talk(self):
        self.assertEqual(action_kind_from_text("I lie flat and crawl up the ramp on my belly."), "physical")
        self.assertEqual(action_kind_from_text("I lie to the reeve about the bell."), "talk")

    def test_recovery_is_read(self):
        self.assertEqual(action_kind_from_text("I ring the hand bell and wait at the window to sign."), "wait")
        self.assertEqual(action_kind_from_text("We wait it out on the roof."), "wait")
        self.assertEqual(
            action_kind_from_text("I can't climb yet. I rest on the door and get some strength back."), "rest"
        )
        self.assertEqual(action_kind_from_text("I get my breath back on the door."), "rest")
        self.assertEqual(action_kind_from_text("I sleep until dawn."), "sleep")
        # Exertion in the same line is still exertion.
        self.assertEqual(action_kind_from_text("I wait for the guard to pass, then climb the wall."), "physical")
        # A quoted "Wait!" is said, not done.
        self.assertNotEqual(action_kind_from_text('"Wait!" I shout after Tam.'), "wait")

    def test_typed_waits_last_as_long_as_they_say(self):
        self.assertEqual(typed_recovery_minutes("I wait an hour here under the ladder."), 60)
        self.assertEqual(typed_recovery_minutes("I wait two hours."), 120)
        self.assertEqual(typed_recovery_minutes("We wait it out on the roof."), 60)
        self.assertEqual(typed_recovery_minutes("I sleep until dawn."), 480)
        self.assertEqual(typed_recovery_minutes("I wait a moment."), 5)
        self.assertEqual(typed_recovery_minutes("I tie the rope round the chimney."), 0)
        self.assertEqual(world.estimate_action_minutes("I wait an hour here under the ladder."), 60)

    def test_cost_kind_of_the_cited_turns(self):
        ctx = {"conversation_turn": {"speech": True}}
        self.assertEqual(
            world._action_cost_kind(
                "I sit down with my back to the chimney, get my breath, and use Tidecount on that white line.",
                {},
                {"name": "Tidecount"},
            ),
            "rest",
        )
        self.assertEqual(world._action_cost_kind("We wait it out on the roof and watch the water.", {}), "wait")
        self.assertEqual(
            world._action_cost_kind('"No. It\'s the sea." I tie the rope\'s free end round Tam\'s waist.', ctx),
            "general",
        )
        self.assertEqual(world._action_cost_kind('"No. It\'s the sea," I say.', ctx), "talk")


class HomeGround(unittest.TestCase):
    """#103: a Flat-runner failed 3 of 3 mud-bank climbs untrained, with injuries."""

    PLAYER = {
        "name": "Isk Tarrow",
        "title": "Flat-runner",
        "backstory": "Isk grew up in Saltmarrow. She runs the exposed flats at dry tide, pulling salvage out of the drowned lower district.",
    }
    SKILLS = [
        {"name": "Salvage", "value": 3, "notes": "grows with each haul pulled from the drowned district"},
        {"name": "Tide Reading", "value": 3, "notes": "grows with each crossing of the flats timed against the water"},
    ]
    CHANNEL = {"name": "The Deep Channel", "summary": "The old harbour mouth: a trench in the mud out toward the drowned district."}

    def test_found_from_the_place_or_the_act(self):
        home = home_ground(self.PLAYER, self.SKILLS, "I climb out of the channel and follow the ruts.", self.CHANNEL)
        self.assertIsNotNone(home)
        self.assertFalse(home["act"])
        act = home_ground(self.PLAYER, self.SKILLS, "I cross the flats before the tide turns.", {})
        self.assertTrue(act["act"])
        self.assertEqual(act["source"], "Tide Reading")
        self.assertIsNone(home_ground(self.PLAYER, self.SKILLS, "I climb the castle wall.", {"name": "Castle Varn"}))

    def _check(self, code, line, place):
        home = home_ground(self.PLAYER, self.SKILLS, line, place)
        return resolve_check(
            skill_code=code,
            player_stats={},
            player_skills=self.SKILLS,
            settings={"dice_checks_enabled": True},
            rng=random.Random(4),
            home=home,
        )

    def test_a_climb_on_home_ground_is_routine_with_footing(self):
        out = self._check("athletics", "I climb out of the channel.", self.CHANNEL)
        self.assertTrue(out["routine"])
        self.assertEqual(out["skill_match"], "related")
        self.assertIn("home ground", out["skill_source"])
        self.assertTrue(out["home_ground"])

    def test_the_place_alone_is_not_a_craft(self):
        tally = {"name": "The Tally House", "summary": "The salvage guild's counting room above the harbour."}
        out = self._check("lockpicking", "I pick the lock on the reeve's strongbox.", tally)
        self.assertEqual(out["skill_match"], "untrained")
        self.assertFalse(out["home_ground"])

    def test_talk_and_fights_are_never_home_ground(self):
        out = self._check("persuasion", "I talk the salvage guild round on the flats.", self.CHANNEL)
        self.assertFalse(out["home_ground"])


class TitlesTakeRoads(unittest.TestCase):
    """#122: 'Wanderer — walked many roads' after five rows of one town on day one."""

    def test_rooms_and_one_day_are_not_many_lands(self):
        from app import titles
        from app.db import connect, init_db

        init_db()
        with connect() as conn:
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("DELETE FROM locations")
            for i in range(6):
                conn.execute(
                    "INSERT INTO locations (code, name, visit_count, parent_id) VALUES (?, ?, 1, 0)", (f"L{i}", f"Row {i}")
                )
            conn.execute("INSERT INTO pacing (key, value) VALUES ('world_day', '1') ON CONFLICT(key) DO UPDATE SET value = '1'")
            req = {"type": "visit_locations", "count": 5, "min_days": 5}
            self.assertFalse(titles._check_requirement(req, conn))
            conn.execute("UPDATE pacing SET value = '6' WHERE key = 'world_day'")
            self.assertTrue(titles._check_requirement(req, conn))
            # Shops inside a place do not count.
            conn.execute("UPDATE locations SET parent_id = 1 WHERE code IN ('L1', 'L2')")
            self.assertFalse(titles._check_requirement(req, conn))

    def test_old_saves_get_the_new_rule(self):
        import json

        from app import titles
        from app.db import connect, init_db

        init_db()
        with connect() as conn:
            conn.execute(
                "UPDATE titles SET requirements_json = ? WHERE name = 'Wanderer'",
                (json.dumps({"type": "visit_locations", "count": 5}),),
            )
            titles.init_titles(conn)
            stored = json.loads(conn.execute("SELECT requirements_json FROM titles WHERE name = 'Wanderer'").fetchone()[0])
        self.assertEqual(stored.get("min_days"), 5)


_SCENE = "The wind pulls at the ladder. Water slaps the stone below, and the rungs are cold and wet under your hands."


def _stub_turn() -> dict:
    return {
        "scene_plan": {"goal": "beat", "focus_points": []},
        "narration_segments": [{"label": "scene", "text": _SCENE}],
        "narration": _SCENE,
        "player": {},
        "self_check": {"passed": True, "issues_found": [], "corrections_made": []},
        "turn_summary": "a beat",
        "scene_focus": "action",
    }


class BlockedActsAndTypedWaits(unittest.TestCase):
    """#119 through play_turn: a blocked act rolls nothing; a typed wait waits and recovers."""

    @classmethod
    def setUpClass(cls):
        from app import db

        os.environ.update(_ENV)
        db.init_db()
        world.start_playthrough(
            {
                "player_name": "Isk Tarrow",
                "start_location": "Saltmarrow",
                "special_ability_origin": "none",
                "dice_checks_enabled": True,
            }
        )

    def _play(self, line: str, seen: list) -> dict:
        from unittest import mock

        def fake(prompt_context, model_input):
            seen.append((prompt_context, model_input))
            return _stub_turn()

        with mock.patch.object(world, "generate_turn", side_effect=fake):
            return world.play_turn(line)

    def _checks_since(self, conn, last_id):
        return [r["tag"] for r in conn.execute("SELECT tag FROM dice_rolls WHERE id > ? AND kind = 'check'", (last_id,))]

    def test_blocked_climb_rolls_nothing(self):
        from app import db

        with db.connect() as conn:
            conn.execute("UPDATE player SET energy = 0, health = 20, max_health = 20 WHERE id = 1")
            last = conn.execute("SELECT COALESCE(MAX(id), 0) FROM dice_rolls").fetchone()[0]
        seen: list = []
        self._play("I climb the iron ladder up the tower wall, hand over hand.", seen)
        _ctx, model_input = seen[0]
        self.assertIn("__action_blocked__", model_input)
        with db.connect() as conn:
            self.assertEqual(self._checks_since(conn, last), [])
            self.assertEqual(conn.execute("SELECT health FROM player WHERE id = 1").fetchone()[0], 20)

    def test_the_same_climb_rolls_when_rested(self):
        from app import db

        with db.connect() as conn:
            conn.execute("UPDATE player SET energy = max_energy WHERE id = 1")
            last = conn.execute("SELECT COALESCE(MAX(id), 0) FROM dice_rolls").fetchone()[0]
        self._play("I climb the iron ladder up the tower wall, hand over hand.", [])
        with db.connect() as conn:
            self.assertTrue(self._checks_since(conn, last))

    def test_typed_wait_waits_and_recovers(self):
        from app import db

        with db.connect() as conn:
            conn.execute("UPDATE player SET energy = 0 WHERE id = 1")
            before = world.get_world_time(conn)
        seen: list = []
        self._play("I wait an hour here under the ladder.", seen)
        with db.connect() as conn:
            after = world.get_world_time(conn)
            energy = conn.execute("SELECT energy FROM player WHERE id = 1").fetchone()[0]
        elapsed = (int(after["day"]) - int(before["day"])) * 1440 + int(after["minute"]) - int(before["minute"])
        self.assertGreaterEqual(elapsed, 60)
        self.assertGreaterEqual(energy, 3)


if __name__ == "__main__":
    unittest.main()
