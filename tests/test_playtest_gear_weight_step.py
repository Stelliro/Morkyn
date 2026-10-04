"""
The gear card's Weight box rejected the engine's own rolls: weights are
rounded to 0.01 kg (0.77) but the input had step 0.1, so the browser
refused the value ("the two nearest valid values are 0.7 and 0.8").
"""
from __future__ import annotations

import random
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import gear  # noqa: E402


class TestGearWeightStepFitsRolls(unittest.TestCase):
    def test_the_weight_box_accepts_two_decimals(self):
        js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        match = re.search(r'step="([0-9.]+)" data-gear-item-stat="weight"', js)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "0.01")

    def test_rolled_weights_have_at_most_two_decimals(self):
        rng = random.Random(7)
        for name, slot in (("Well-Worn Boots", "FEET"), ("Leather Greaves", "LEGS"), ("Small, Enchanted Lantern", "")):
            weight = gear.roll_item_stats({"name": name, "slot": slot}, {}, rng, force=True)["weight"]
            self.assertEqual(round(weight, 2), weight)


if __name__ == "__main__":
    unittest.main()
