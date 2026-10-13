"""7B run 19 (Qwen2.5 7B on MLE, agent as player): a walk to someone is not a move elsewhere; another's act rolls nothing."""
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-7b-run19-"))
_ENV = isolated_data_env(str(_TMP))
_SAVED_ENV: dict[str, str | None] = {}

LINE = ("The tide's coming in, so I'm not going far. I walk over to where the mole catcher is digging. "
        "\"Eadric. Found anything in there besides moles?\"")
PROSE = ("You walk over to where the mole catcher, Eadric Joliffe [[A]], is digging. \"Eadric,\" you say, \"found "
         "anything in there besides moles?\"\n\nEadric pauses. \"Not much. Just a few old stones.\"")


def setUpModule():
    _SAVED_ENV.update({key: os.environ.get(key) for key in _ENV})
    os.environ.update(_ENV)


def tearDownModule():
    for key, value in _SAVED_ENV.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


class WalkToSomeoneIsNotAMoveElsewhere(unittest.TestCase):
    """T1: MOVE "Seventh Pike Stables" applied on a walk over to the mole catcher."""

    def test_move_dropped(self):
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        with connect() as conn:
            here = conn.execute("SELECT current_location_id FROM player").fetchone()[0]
            world._upsert_location(conn, "Seventh Pike Stables", "", parent_id=here, kind="stable")
            result = {"narration": PROSE, "player": {"move_to_location": "Seventh Pike Stables"}}
            world.resolve_movement(conn, result, LINE, intent="travel", narration=PROSE)
        self.assertFalse(result["player"].get("move_to_location"))


class RequestedPlaceBeforeMinted(unittest.TestCase):
    """Run 24 T1: "I head down to the salvage yard" went into a new "Ship's Hold" the prose mentioned."""

    def test_yard_wins(self):
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        prose = ("You head down to the bustling Salvage Yard, workers unloading crates from a ship. You push your way "
                 "through the crowd and step into the ship's hold to look.")
        with connect() as conn:
            result = {"narration": prose, "player": {}, "locations": [{"name": "ship's hold", "summary": "a hold"}]}
            report = world.resolve_movement(
                conn, result, "I head down to the salvage yard to see what the guild has posted.", intent="travel",
                narration=prose,
            )
        self.assertEqual(report["rule"], "venue_requested")
        self.assertIn("Salvage Yard", report["destination"])


class TheNoteHeHoldsOut(unittest.TestCase):
    """Run 24 T3: "I take the note he holds out and read it" stored "note he holds" and rolled investigation."""

    def test_name_and_no_check(self):
        from app import world
        from app.db import connect, init_db
        from app.skill_checks import infer_check_from_action

        init_db()
        line = 'I take the note he holds out and read it. "Where was it last seen?"'
        with connect() as conn:
            conn.execute("DELETE FROM inventory")
            added = world._grant_shown_takes(conn, [], "You take the note he holds out and read it.", line)
        self.assertEqual([a["name"] for a in added], ["note"])
        self.assertIsNone((infer_check_from_action(line, {}) or {}).get("skill_code"))


class AnothersActIsNotTheCheck(unittest.TestCase):
    """T1: "where the mole catcher is digging" rolled athletics."""

    def test_triggers(self):
        from app.skill_checks import infer_check_from_action as infer

        def skill(line):
            return (infer(line, {}) or {}).get("skill_code")

        self.assertIsNone(skill(LINE))
        self.assertEqual(skill("I dig at the mud around the doorway."), "athletics")
        self.assertEqual(skill("I climb the ladder while Tam is hammering."), "athletics")


if __name__ == "__main__":
    unittest.main()
