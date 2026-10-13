"""7B run 28 (Qwen2.5 7B on MLE, agent as player): the player's place over the model's MOVE; a job word is no name."""
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-7b-run28-"))
_ENV = isolated_data_env(str(_TMP))
_SAVED_ENV: dict[str, str | None] = {}

_LINE = "\"Thanks, Lettice.\" I walk to the town hall to look for the reeve's tide charts."
_PROSE = (
    "You leave Lettice at her stall and walk to the town hall, a squat stone building at the top of the lane. "
    "You push open the heavy door and step inside. Ledgers line the shelves, and a stern-looking man with a "
    "clipboard looks up from a desk. \"Found what you needed?\" he asks."
)


def setUpModule():
    _SAVED_ENV.update({key: os.environ.get(key) for key in _ENV})
    os.environ.update(_ENV)


def tearDownModule():
    for key, value in _SAVED_ENV.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _fresh():
    from app import world
    from app.db import init_db

    init_db()
    world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})


class PlayersPlaceOverUnshownMove(unittest.TestCase):
    """T4: "I walk to the town hall" saved a new Town Square from MOVE "town square"."""

    def test_town_hall_wins(self):
        from app import world
        from app.db import connect

        _fresh()
        with connect() as conn:
            result = {"narration": _PROSE, "player": {"move_to_location": "town square"}}
            report = world.resolve_movement(conn, result, _LINE, intent="travel", narration=_PROSE)
            self.assertEqual(report["status"], "repaired")
            self.assertEqual(report["destination"], "The Town Hall")
            self.assertEqual(result["player"]["move_to_location"], "The Town Hall")
            conn.rollback()

    def test_no_move_still_reaches_the_hall(self):
        from app import world
        from app.db import connect

        _fresh()
        with connect() as conn:
            result = {"narration": _PROSE, "player": {}}
            report = world.resolve_movement(conn, result, _LINE, intent="travel", narration=_PROSE)
            self.assertEqual(report.get("destination"), "The Town Hall")
            conn.rollback()

    def test_hall_named_only_in_speech_is_not_made(self):
        from app import world
        from app.db import connect

        _fresh()
        prose = "Lettice shrugs. \"The town hall keeps the charts, but it's shut till noon.\" You stay by her stall."
        with connect() as conn:
            self.assertEqual(world._venue_requested_and_reached(conn, "I walk to the town hall.", prose, "L1"), "")
            conn.rollback()

    def test_move_the_player_also_named_stands(self):
        from app import world
        from app.db import connect

        _fresh()
        with connect() as conn:
            self.assertIsNone(
                world._player_place_over_unshown_move(conn, {}, "I cross the town square to the town hall.", _PROSE, "L1", "town square")
            )
            conn.rollback()


class CutTailMoveToAnotherPlace(unittest.TestCase):
    """T4: the cut tail's MOVE "town square" survived because the player asked to move at all."""

    def test_move_named_only_in_tail_goes(self):
        from app.llm import _drop_ops_of_cut_tail

        turn = {"player": {"move_to_location": "town square"}}
        head = "You walk to the town hall and step inside. A stern man with a clipboard looks up."
        tail = "You thank him, tuck the reckoner away and head to the town square to look for the carter."
        dropped = _drop_ops_of_cut_tail(turn, head, tail, "I walk to the town hall to look for the charts.")
        self.assertTrue(any(d.startswith("MOVE town square") for d in dropped))
        self.assertIsNone(turn["player"]["move_to_location"])

    def test_asked_move_named_by_player_stays(self):
        from app.llm import _drop_ops_of_cut_tail

        turn = {"player": {"move_to_location": "town square"}}
        head = "You set off past the stalls."
        tail = "You reach the town square as the bell rings and look about for the carter."
        dropped = _drop_ops_of_cut_tail(turn, head, tail, "I head to the town square.")
        self.assertFalse(any(d.startswith("MOVE") for d in dropped))
        self.assertEqual(turn["player"]["move_to_location"], "town square")


class JobWordIsNoName(unittest.TestCase):
    """T4: NPC_NEW "A" "reeve" stored a person called "reeve"."""

    def test_role_phrase(self):
        from app import world

        for word in ("reeve", "smith", "carter"):
            self.assertEqual(world._role_phrase(word), word)
        self.assertEqual(world._role_phrase("wrenna"), "")
        self.assertEqual(world._role_phrase("Carter"), "")

    def test_reeve_is_drawn_a_name(self):
        from app import world
        from app.db import connect

        _fresh()
        with connect() as conn:
            conn.execute("DELETE FROM npcs WHERE role LIKE '%reeve%'")
            npc_id = world._upsert_npc(conn, {"code": "A", "name": "reeve", "location": "L1"})
            row = conn.execute("SELECT name, role FROM npcs WHERE id = ?", (npc_id,)).fetchone()
            self.assertNotEqual(row["name"].lower(), "reeve")
            self.assertEqual(row["role"], "reeve")
            conn.rollback()

    def test_reeve_is_the_known_holder(self):
        from app import world
        from app.db import connect

        _fresh()
        with connect() as conn:
            conn.execute("DELETE FROM npcs WHERE role LIKE '%reeve%'")
            held = world._upsert_npc(conn, {"name": "Rosamund Colley", "role": "harbour reeve", "location": "L1"})
            npc_id = world._upsert_npc(conn, {"code": "A", "name": "reeve", "location": "L1"})
            self.assertEqual(npc_id, held)
            conn.rollback()

    def test_lowercase_name_stays_a_name(self):
        from app import world
        from app.db import connect

        _fresh()
        with connect() as conn:
            npc_id = world._upsert_npc(conn, {"name": "wrenna", "role": "net mender", "location": "L1"})
            row = conn.execute("SELECT name FROM npcs WHERE id = ?", (npc_id,)).fetchone()
            self.assertEqual(row["name"].lower(), "wrenna")
            conn.rollback()


if __name__ == "__main__":
    unittest.main()
