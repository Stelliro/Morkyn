"""Story walks stay on the generated grid and the map remembers every step."""

import copy
import os
import tempfile
import unittest
from pathlib import Path

from app.tile_world import (  # noqa: E402
    apply_story_map_walk,
    local_map_view,
    plan_story_walk,
    spatial_contract,
    walk_steps,
)
from app.turn_dsl import DSL_SYSTEM_PROMPT, parse_dsl_turn  # noqa: E402
from app.world import movement_contract  # noqa: E402


def _cell(x, y, state="plains", walkable=True):
    return {
        "x": x,
        "y": y,
        "state": state,
        "walkable": walkable,
        "elevation": 0,
        "image_path": "skip",
        "image_data_url": "",
    }


def _chart(player=(1, 1), water_x=None, settlements=None):
    grid = []
    for y in range(6):
        row = []
        for x in range(6):
            if water_x is not None and x == water_x:
                row.append(_cell(x, y, "water", False))
            else:
                row.append(_cell(x, y))
        grid.append(row)
    return {
        "id": "",
        "width": 6,
        "height": 6,
        "player": {"x": player[0], "y": player[1]},
        "grid": grid,
        "visited": [f"{player[0]},{player[1]}", "5,0"],
        "settlements_meta": list(settlements or []),
        "landmarks": [],
        "place_anchors": {},
        "knowledge": {"settlements": [], "danger": [], "notes": [], "sources": []},
    }


def _harrowford():
    return [{"id": "S1", "x": 1, "y": 4, "state": "town", "name": "Harrowford", "bbox": [1, 4, 1, 4]}]


class MapWalkTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="morkyn-map-walk-")
        root = Path(self._tmp.name)
        self._saved = {key: os.environ.get(key) for key in (
            "AI_RPG_DB",
            "AI_RPG_CAMPAIGN_SLOTS",
            "AI_RPG_MODEL_TRACE_DIR",
            "AI_RPG_HISTORY_SUMMARY",
            "AI_RPG_SOURCE_INDEX",
            "AI_RPG_CONSOLIDATED_FACTS",
        )}
        os.environ["AI_RPG_DB"] = str(root / "world.db")
        os.environ["AI_RPG_CAMPAIGN_SLOTS"] = str(root / "slots")
        os.environ["AI_RPG_MODEL_TRACE_DIR"] = str(root / "traces")
        os.environ["AI_RPG_HISTORY_SUMMARY"] = str(root / "history.jsonl")
        os.environ["AI_RPG_SOURCE_INDEX"] = str(root / "source")
        os.environ["AI_RPG_CONSOLIDATED_FACTS"] = str(root / "facts.jsonl")

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmp.cleanup()

    def test_east_into_water_stops_and_keeps_the_start(self):
        chart = _chart(water_x=2)
        report = walk_steps(chart, "east", 4, save=False)
        self.assertEqual(report["steps_taken"], 0)
        self.assertEqual(report["stopped"], "blocked")
        self.assertEqual(chart["player"], {"x": 1, "y": 1})
        self.assertIn("1,1", chart["visited"])
        self.assertIn("5,0", chart["visited"])

    def test_south_to_the_edge_then_another_step_drops_nothing(self):
        chart = _chart(player=(1, 4))
        chart["visited"] = ["1,4", "1,1", "5,0"]
        first = walk_steps(chart, "south", 4, save=False)
        self.assertEqual(first["steps_taken"], 1)
        self.assertEqual(chart["player"]["y"], 5)
        remembered = set(chart["visited"])
        second = walk_steps(chart, "south", 4, save=False)
        self.assertEqual(second["steps_taken"], 0)
        self.assertEqual(second["stopped"], "edge")
        self.assertTrue(remembered <= set(chart["visited"]))
        self.assertIn("1,1", chart["visited"])
        self.assertIn("5,0", chart["visited"])

    def test_steps_above_the_budget_clamp_to_four(self):
        chart = _chart()
        report = walk_steps(chart, "east", 99, save=False)
        self.assertEqual(report["steps_requested"], 4)
        self.assertEqual(report["steps_taken"], 4)
        self.assertEqual(chart["player"]["x"], 5)
        self.assertIn("1,1", chart["visited"])
        self.assertIn("5,0", chart["visited"])

    def test_local_view_keeps_the_start_after_walking_away(self):
        chart = _chart()
        walk_steps(chart, "south", 4, save=False)
        view = local_map_view(chart, radius=6)
        keys = {f"{tile['x']},{tile['y']}" for tile in view["tiles"]}
        self.assertTrue(view["memory"])
        self.assertEqual(view["bounds"], {"width": 6, "height": 6})
        self.assertIn("1,1", keys)
        self.assertIn("5,0", keys)
        self.assertNotIn("5,5", keys)
        self.assertGreaterEqual(view["explored_tiles"], 2)
        self.assertTrue(any(tile.get("fog") for tile in view["tiles"]))
        start = next(tile for tile in view["tiles"] if tile["x"] == 1 and tile["y"] == 1)
        self.assertTrue(start["visited"])
        self.assertEqual(start["rel_x"], 1 - chart["player"]["x"])
        self.assertEqual(start["rel_y"], 1 - chart["player"]["y"])

    def test_spatial_contract_is_the_finite_land(self):
        chart = _chart(water_x=2, settlements=_harrowford())
        space = spatial_contract(chart)
        self.assertEqual(space["width"], 6)
        self.assertEqual(space["height"], 6)
        self.assertEqual(space["step_budget"], 4)
        self.assertEqual(space["player"]["terrain"], "plains")
        self.assertEqual(space["exits"]["east"]["status"], "blocked")
        self.assertEqual(space["exits"]["east"]["terrain"], "water")
        self.assertEqual(space["exits"]["south"]["status"], "walkable")
        names = [place["name"] for place in space["places_in_reach"]]
        self.assertIn("Harrowford", names)
        harrowford = next(place for place in space["places_in_reach"] if place["name"] == "Harrowford")
        self.assertEqual(harrowford["direction"], "south")
        self.assertEqual(harrowford["distance"], 3)

    def test_walk_opcode_parses_and_clamps_steps(self):
        # The op legend describes WALK in words since playtest #39 (no slot words).
        self.assertIn("WALK: a compass direction. May add STEPS and a number from 1 to 4.", DSL_SYSTEM_PROMPT)
        turn = parse_dsl_turn(
            "===NAR===\nYou walk east until the ground runs out.\n\n===OPS===\nWALK east STEPS 99\n",
            "I walk east",
        )
        self.assertEqual(turn["map_walk"], {"direction": "east", "steps": 4})
        short = parse_dsl_turn(
            "===NAR===\nYou take one step south.\n\n===OPS===\nSTEP south STEPS 1\n",
            "I step south",
        )
        self.assertEqual(short["map_walk"], {"direction": "south", "steps": 1})

    def test_handoff_keeps_map_walk(self):
        from app.llm import _clean_turn_for_handoff

        cleaned = _clean_turn_for_handoff(
            {
                "narration": "You walk east.",
                "narration_segments": [{"label": "paragraph", "text": "You walk east."}],
                "player": {"move_to_location": None},
                "map_walk": {"direction": "east", "steps": 2},
            },
            "test",
        )
        self.assertEqual(cleaned["map_walk"]["direction"], "east")
        self.assertEqual(cleaned["map_walk"]["steps"], 2)

    def test_door_does_not_hike_and_unresolved_travel_still_steps(self):
        chart = _chart()
        door = plan_story_walk(
            chart,
            player_input="I step into the watchhouse",
            input_kind="player",
            movement_report={"status": "model", "from": "L1", "destination": "Watchhouse"},
            origin={"id": 1, "code": "L1", "name": "Market", "parent_id": 0},
            dest={"id": 2, "code": "L2", "name": "Watchhouse", "parent_id": 1},
            travel=True,
        )
        self.assertEqual(door["action"], "skip")
        self.assertEqual(door["reason"], "door")
        stayed = apply_story_map_walk(
            copy.deepcopy(chart),
            player_input="I step into the watchhouse",
            movement_report={"status": "model", "from": "L1", "destination": "Watchhouse"},
            origin={"id": 1, "code": "L1", "name": "Market", "parent_id": 0},
            dest={"id": 2, "code": "L2", "name": "Watchhouse", "parent_id": 1},
            travel=True,
            save=False,
        )
        self.assertEqual(stayed["status"], "skipped")

        moved = copy.deepcopy(chart)
        journey = apply_story_map_walk(
            moved,
            player_input="I leave this exact spot and walk toward the nearest other place",
            movement_report={"status": "model", "from": "L1", "destination": "Watchhouse"},
            origin={"id": 1, "code": "L1", "name": "Market", "parent_id": 0},
            dest={"id": 2, "code": "L2", "name": "Watchhouse", "parent_id": 1},
            travel=True,
            save=False,
        )
        self.assertEqual(journey["status"], "walked")
        self.assertGreaterEqual(journey["steps_taken"], 1)
        self.assertNotEqual(moved["player"], {"x": 1, "y": 1})
        self.assertIn("1,1", moved["visited"])
        self.assertIn("5,0", moved["visited"])

        unresolved = plan_story_walk(
            chart,
            player_input="I walk east along the lane",
            input_kind="player",
            movement_report={"status": "unresolved", "from": "L1"},
            origin={"id": 1, "code": "L1", "name": "Market", "parent_id": 0},
            dest={"id": 1, "code": "L1", "name": "Market", "parent_id": 0},
            travel=True,
        )
        self.assertEqual(unresolved["action"], "steps")
        self.assertEqual(unresolved["direction"], "east")
        self.assertEqual(unresolved["steps"], 4)

        waiting = plan_story_walk(
            chart,
            player_input="I walk east",
            input_kind="wait",
            movement_report={"status": "not_travel", "from": "L1"},
            travel=True,
        )
        self.assertEqual(waiting["reason"], "not_player")
        explicit = plan_story_walk(
            chart,
            player_input="I walk east",
            input_kind="wait",
            map_walk={"direction": "east", "steps": 99},
            movement_report={"status": "not_travel", "from": "L1"},
        )
        self.assertEqual(explicit["action"], "steps")
        self.assertEqual(explicit["steps"], 4)

    def test_outdoor_move_walks_toward_a_named_place_and_pins_both_ends(self):
        chart = _chart(settlements=_harrowford())
        report = apply_story_map_walk(
            chart,
            player_input="I travel to Harrowford",
            input_kind="player",
            movement_report={"status": "model", "from": "L1", "destination": "Harrowford"},
            origin={"id": 1, "code": "L1", "name": "Market", "parent_id": 0},
            dest={"id": 3, "code": "L3", "name": "Harrowford", "parent_id": 0},
            travel=True,
            save=False,
        )
        self.assertEqual(report["status"], "walked")
        self.assertGreater(report["steps_taken"], 0)
        self.assertEqual(chart["player"], {"x": 1, "y": 4})
        self.assertEqual(chart["place_anchors"]["L1"]["y"], 1)
        self.assertEqual(chart["place_anchors"]["harrowford"]["x"], 1)
        self.assertEqual(chart["place_anchors"]["harrowford"]["y"], 4)
        self.assertIn("1,1", chart["visited"])
        self.assertIn("The map remembers", report["journal"])
        back = apply_story_map_walk(
            chart,
            player_input="I go back to the market",
            movement_report={"status": "model", "from": "L3", "destination": "Market"},
            origin={"id": 3, "code": "L3", "name": "Harrowford", "parent_id": 0},
            dest={"id": 1, "code": "L1", "name": "Market", "parent_id": 0},
            travel=True,
            save=False,
        )
        self.assertEqual(back["status"], "walked")
        self.assertEqual(chart["player"]["y"], 1)
        self.assertEqual(chart["place_anchors"]["harrowford"]["y"], 4)

    def test_outdoor_move_without_a_heading_still_takes_a_step(self):
        chart = _chart()
        report = apply_story_map_walk(
            chart,
            player_input="I leave this place behind",
            movement_report={"status": "repaired", "from": "L1", "destination": "Reed Camp"},
            origin={"id": 1, "code": "L1", "name": "Market", "parent_id": 0},
            dest={"id": 4, "code": "L4", "name": "Reed Camp", "parent_id": 0},
            travel=True,
            save=False,
        )
        self.assertEqual(report["status"], "walked")
        self.assertEqual(report["steps_taken"], 1)
        self.assertEqual(chart["player"], {"x": 1, "y": 0})
        self.assertIn("1,1", chart["visited"])

    def test_travel_expectation_uses_the_map_when_one_exists(self):
        state = {
            "current_location": {"code": "L1", "name": "Market"},
            "locations": [{"code": "L1", "name": "Market"}],
        }
        bounded = movement_contract(
            state,
            "I head east",
            "travel",
            map_space={"width": 32, "height": 24, "step_budget": 4},
        )
        self.assertIn("step budget", bounded["expectation"].lower())
        self.assertNotIn("invent a fitting name", bounded["expectation"].lower())
        open_land = movement_contract(state, "I head east", "travel")
        self.assertIn("invent a fitting name", open_land["expectation"])


if __name__ == "__main__":
    unittest.main()
