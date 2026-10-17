"""#102 class: the craft noun alone is not the craft (8B run 142, T5).

"I carry the rusted compass and the weathered ledger back up to the tally
house" rolled navigation on the word compass, failed on a 2, and hurt the
player's leg. The noun-only craft triggers (compass, map, farm, mechanism) now
want the thing used: the skill's own verb, or a using verb on the thing. A
trap carried and then set is still set (7B run 30, T10).

Run:  .venv\\Scripts\\python -m unittest tests.test_playtest102_handled_objects
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.skill_checks import infer_check_from_action  # noqa: E402


def _skill(line: str) -> str:
    check = infer_check_from_action(line, {})
    return str((check or {}).get("skill_code") or "")


class TheNounAloneIsNotTheCraft(unittest.TestCase):
    def test_carrying_a_compass_is_no_navigation(self):
        line = "I carry the rusted compass and the weathered ledger back up to the tally house and set them on Veyra's desk."
        self.assertNotEqual(_skill(line), "navigation")

    def test_pocketing_a_map_is_no_cartography(self):
        self.assertNotEqual(_skill("I pocket the map and walk on to the gate."), "cartography")

    def test_handing_over_a_chart_is_no_cartography(self):
        self.assertNotEqual(_skill("I hand him the chart and wait."), "cartography")

    def test_a_charm_of_stars_is_no_navigation(self):
        self.assertNotEqual(_skill("I pick up the little brass stars charm from the floor."), "navigation")

    def test_walking_across_the_farm_is_no_farming(self):
        self.assertNotEqual(_skill("I walk across the farm to the barn and knock."), "farming")

    def test_looking_at_a_mechanism_is_no_tinkering(self):
        self.assertNotEqual(_skill("I look at the mechanism above the door."), "tinkering")


class LoreSkillsReadTheLineAsTyped(unittest.TestCase):
    def test_feet_planted_in_the_mud_is_no_nature_lore(self):
        # 8B run 145, T34: "planted" de-inflected to "plant" and rolled nature.
        self.assertNotEqual(_skill("I keep my hands open and my feet planted in the mud, and I do not step back."), "nature")

    def test_asking_about_a_plant_still_is(self):
        self.assertEqual(_skill("What kind of plant is that on the wall?"), "nature")


class UsingTheThingStillRolls(unittest.TestCase):
    def test_a_bearing_with_the_compass(self):
        self.assertEqual(_skill("I take a bearing with the compass and plot our route along the coast."), "navigation")

    def test_steering_by_the_stars(self):
        self.assertEqual(_skill("I steer by the stars until the headland shows."), "navigation")

    def test_sketching_a_map(self):
        self.assertEqual(_skill("I sketch a map of the flats on the back of the ledger page."), "cartography")

    def test_plowing_a_field(self):
        self.assertEqual(_skill("I plow the east field before the rain."), "farming")

    def test_fixing_a_mechanism(self):
        self.assertEqual(_skill("I open the clockwork and fix the mechanism with a bent nail."), "tinkering")

    def test_a_trap_carried_and_set_is_still_set(self):
        line = ("I carry the two traps to the tunnels by the brine vats and set the first one where the earth is freshest, "
                "then the second a stride further along.")
        self.assertEqual(_skill(line), "survival")


if __name__ == "__main__":
    unittest.main()
