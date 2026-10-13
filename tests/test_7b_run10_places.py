"""7B run 10 (Qwen2.5 7B on MLE, agent as player): following in, the opening's door, open parts of town, pins."""
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-7b-run10-places-"))
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


OPENING = (
    "The morning sun hangs low over Saltmarrow [[L1]], casting a pale light over the town's cobblestone streets. "
    "You stand before the Cropper and Sons forge, where the sound of hammering and the scent of red-hot metal "
    "greet you. A small sign above the door reads \"Cropper and Sons,\" hinting at the skill within.\n\n"
    "Inside, the air is hot and filled with the clink of tools and the steady beat of hammer on anvil. "
    "A man, Jehane Tully, a knife grinder by the look of his tools and the small whetstones he carries, is "
    "sharpening a blade. His movements are precise, his hands steady. He glances up as you approach.\n\n"
    "Jehane looks up, his eyes narrowing as he studies you. \"Depends, flat-runner. What have you got to offer?\"\n\n"
    "\"This is all I have. My mother worked the flats, and I need to repay her debt to the guild.\""
)


def _town_with_forge():
    from app import world
    from app.db import connect, init_db

    init_db()
    with connect() as conn:
        for table in ("npcs", "inventory", "journal"):
            conn.execute(f"DELETE FROM {table}")
        conn.execute("UPDATE player SET current_location_id = NULL WHERE id = 1")
        conn.execute("DELETE FROM locations")
        conn.execute("INSERT INTO locations (id, code, name, summary) VALUES (1, 'L1', 'Saltmarrow', 'A drowned harbour town.')")
        conn.execute(
            "INSERT INTO locations (id, code, name, summary, parent_id, kind) "
            "VALUES (2, 'L2', 'Cropper and Sons Forge', '', 1, 'smithy')"
        )
        if conn.execute("SELECT 1 FROM player WHERE id = 1").fetchone() is None:
            conn.execute("INSERT INTO player (id, name) VALUES (1, 'Isk')")
        conn.execute("UPDATE player SET current_location_id = 1 WHERE id = 1")
    return world


class OpeningAtTheDoorThenInside(unittest.TestCase):
    """T0: 'You stand before the Cropper and Sons forge ... Inside, the air is hot' kept her in the square."""

    def test_inside_after_the_door_is_the_start(self):
        world = _town_with_forge()
        from app.db import connect

        with connect() as conn:
            self.assertEqual(world._opening_entry(conn, OPENING), "Cropper and Sons Forge")

    def test_passing_by_is_not_inside(self):
        world = _town_with_forge()
        from app.db import connect

        text = "You walk past the Cropper and Sons forge. Inside, someone is hammering."
        with connect() as conn:
            self.assertEqual(world._opening_entry(conn, text), "")


class FollowingHerIn(unittest.TestCase):
    """T3: 'I follow her in to the table' at the forge door stayed in Saltmarrow."""

    def test_follow_in_enters_the_building_of_the_scene(self):
        world = _town_with_forge()
        from app.db import connect

        prose = (
            "You follow her in to the table and pick up the first dull knife. The forge is warm and the light "
            "from the oil lamps casts flickering shadows on the walls."
        )
        line = "I follow her in to the table and pick up the first dull knife from the pile."
        with connect() as conn:
            self.assertEqual(world._followed_inside(conn, line, prose, "L1"), "Cropper and Sons Forge")
            # Following someone down the road is not going in.
            self.assertEqual(world._followed_inside(conn, "I follow her down the road.", prose, "L1"), "")

    def test_through_resolve_movement(self):
        world = _town_with_forge()
        from app.db import connect

        # The shipped T3 prose: no "into the forge", only "in to the table" and "The forge is warm".
        narration = (
            "You follow her in to the table and pick up the first dull knife from the pile, testing the edge "
            "with your thumb. \"I offer my hands. Ten knives for one gold - that's my price,\" you say. Jehane "
            "Tully [[A]] meets your gaze.\n\nYou feel the weight of the knife in your hand. The room is filled "
            "with the scent of hot oil and the rhythmic sound of grinding stone on steel. The forge is warm and "
            "the light from the oil lamps casts flickering shadows on the walls."
        )
        result = {"narration": narration, "player": {}}
        line = (
            "I follow her in to the table and pick up the first dull knife from the pile, testing the edge with "
            "my thumb. \"I offer my hands. Ten knives for one gold - that's my price.\""
        )
        with connect() as conn:
            intent, _ = world._turn_intent(line)
            report = world.resolve_movement(conn, result, line, intent=intent, narration=narration)
        self.assertEqual(report.get("rule"), "follow_inside", report)
        self.assertEqual(result["player"].get("move_to_location"), "Cropper and Sons Forge")


class OpenPartsOfTown(unittest.TestCase):
    """T8: 'walk down to the edge of the mudflats' stayed put."""

    def test_made_in_the_town(self):
        world = _town_with_forge()
        from app.db import connect

        prose = (
            "You walk down to the edge of the mudflats, the water a thin line just beyond. The sea has receded "
            "further than you expected."
        )
        line = "I count the coins in my palm, then walk down to the edge of the mudflats to see how far out the water is."
        with connect() as conn:
            name = world._outdoor_area_requested(conn, 1, line, prose)
            self.assertEqual(name, "The Mudflats")
            row = conn.execute("SELECT parent_id, kind FROM locations WHERE name = ?", (name,)).fetchone()
            self.assertEqual((row["parent_id"], row["kind"]), (1, ""))
            # The second walk finds it rather than making another.
            again = world._outdoor_area_requested(conn, 1, "I head back to the mudflats.", "You head back to the flats.")
            self.assertEqual(again, "The Mudflats")

    def test_through_resolve_movement(self):
        world = _town_with_forge()
        from app.db import connect

        narration = (
            "You count the loose silver and copper in your palm. You walk down to the edge of the mudflats, the "
            "water a thin line just beyond. The sea has receded further than you expected."
        )
        line = "I count the coins in my palm before I put them away, then walk down to the edge of the mudflats to see how far out the water is."
        result = {"narration": narration, "player": {}}
        with connect() as conn:
            intent, _ = world._turn_intent(line)
            report = world.resolve_movement(conn, result, line, intent=intent, narration=narration)
        self.assertEqual(result["player"].get("move_to_location"), "The Mudflats", report)

    def test_stopped_or_unnamed_walks_do_nothing(self):
        world = _town_with_forge()
        from app.db import connect

        with connect() as conn:
            # The prose never goes there.
            self.assertEqual(world._outdoor_area_requested(conn, 1, "I walk to the harbour.", "You stay by the forge."), "")
            # No open area word at all.
            self.assertEqual(world._outdoor_area_requested(conn, 1, "I walk to the forge.", "You walk to the forge."), "")


class OpeningPinsJehane(unittest.TestCase):
    """T0/T1: Jehane was 'his' in the opening and 'her' after; the opening pinned nothing."""

    def test_speech_and_someones_mother_do_not_count(self):
        from app.world import infer_npc_pronouns

        self.assertEqual(infer_npc_pronouns("Jehane Tully", OPENING, []), "he")
        # Her own kin still say who she is.
        self.assertEqual(infer_npc_pronouns("Mara", "Mara strokes her mother's hair.", []), "she")


if __name__ == "__main__":
    unittest.main()
