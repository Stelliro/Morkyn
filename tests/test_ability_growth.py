"""app/ability_growth.py: the model picks a template and a seed; the engine does every number."""
from __future__ import annotations

import random
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import ability_growth as g  # noqa: E402

TEMPLATES = ("compounding", "linear", "soft_cap", "breakthrough", "passive", "item_bound")


class SeedTests(unittest.TestCase):
    def test_aliases_and_defaults(self):
        seed = g.normalize_seed({"power_type": "Snowball", "growth": {"pace": "very fast", "start": "near useless"}})
        self.assertEqual(seed, {"template": "compounding", "pace": "fast", "start": "weak", "grows": ""})
        self.assertEqual(g.normalize_seed({})["template"], "linear")
        self.assertEqual(g.normalize_seed({"power_type": "compounding"})["start"], "weak")

    def test_the_seed_carries_no_numbers(self):
        seed = g.normalize_seed({"growth": {"grows": "reach x2 per 10 uses"}})
        self.assertNotRegex(seed["grows"], r"\d")


class ExpandTests(unittest.TestCase):
    def test_thresholds_rise_on_every_template(self):
        for template in TEMPLATES:
            with self.subTest(template=template):
                growth = g.expand(g.normalize_seed({"power_type": template}))
                th = growth["thresholds"]
                self.assertEqual(len(th), len(growth["labels"]))
                self.assertTrue(all(b > a for a, b in zip(th, th[1:])), th)

    def test_pace_and_difficulty_scale_the_curve(self):
        slow = g.expand({"template": "linear", "pace": "slow"})["thresholds"][-1]
        fast = g.expand({"template": "linear", "pace": "fast"})["thresholds"][-1]
        hard = g.expand({"template": "linear", "pace": "steady"}, difficulty="hard")["thresholds"][-1]
        normal = g.expand({"template": "linear", "pace": "steady"})["thresholds"][-1]
        self.assertGreater(slow, normal)
        self.assertLess(fast, normal)
        self.assertGreater(hard, normal)

    def test_the_worlds_rank_scale_names_the_ladder(self):
        growth = g.expand({"template": "breakthrough"}, rank_scale="Common,Trained,Veteran,Elite,Mythic")
        self.assertEqual(growth["labels"], ["Common", "Trained", "Veteran", "Elite", "Mythic"])
        self.assertEqual(len(growth["thresholds"]), 5)

    def test_compounding_outgrows_linear(self):
        comp = g.expand({"template": "compounding", "start": "weak"})
        lin = g.expand({"template": "linear", "start": "weak"})
        top = len(comp["labels"]) - 1
        self.assertGreater(g.effect_multiplier(comp, top), 2 * g.effect_multiplier(lin, top))

    def test_flat_has_no_ladder(self):
        growth = g.expand({"template": "flat"})
        self.assertTrue(growth["flat"])
        state, events = g.award(growth, None, uses=50, risk=4)
        self.assertEqual(events, [])


class RenderTests(unittest.TestCase):
    def test_every_threshold_in_the_text_is_the_engines(self):
        for template in TEMPLATES:
            with self.subTest(template=template):
                growth = g.expand({"template": template, "start": "weak"})
                text = g.render_text(growth)
                segment = text.split("XP to reach:", 1)[1].split(".", 1)[0]
                listed = [int(n.replace(",", "")) for n in re.findall(r"\b[A-Z]{1,3} ([\d,]+)", segment)]
                self.assertEqual(listed, growth["thresholds"][1:])


class AwardTests(unittest.TestCase):
    def test_uses_rank_up_and_report_it(self):
        growth = g.expand({"template": "linear", "start": "weak"})
        state, events = g.award(growth, None, uses=200, risk=1, rng=random.Random(1))
        self.assertGreater(state["index"], 0)
        self.assertEqual(state["uses"], 200)
        ups = [e for e in events if e["type"] == "rank_up"]
        self.assertEqual([e["to_index"] for e in ups], list(range(1, state["index"] + 1)))

    def test_risk_earns_more(self):
        growth = g.expand({"template": "linear", "start": "weak"})
        safe, _ = g.award(growth, None, uses=10, risk=1, rng=random.Random(3))
        risky, _ = g.award(growth, None, uses=10, risk=3, rng=random.Random(3))
        self.assertGreater(risky["xp"], safe["xp"])

    def test_a_breakthrough_wall_holds_until_a_dangerous_use(self):
        growth = g.expand({"template": "breakthrough", "start": "weak"})
        wall = growth["breakthrough_at"][0]
        state = {"index": wall - 1, "xp": growth["thresholds"][wall] - 2, "uses": 0}
        held, events = g.award(growth, state, uses=30, risk=1, rng=random.Random(5))
        self.assertEqual(held["index"], wall - 1)
        self.assertEqual(events[-1]["type"], "plateau")
        broke, events = g.award(growth, held, uses=1, risk=3, rng=random.Random(5))
        self.assertEqual(broke["index"], wall)
        self.assertTrue(events[0]["breakthrough"])

    def test_item_bound_stops_without_its_item(self):
        growth = g.expand({"template": "item_bound"})
        state, events = g.award(growth, None, uses=20, item_ok=False)
        self.assertEqual(state["xp"], g.new_state(growth)["xp"])
        self.assertEqual(events, [{"type": "no_item"}])

    def test_describe_state_leaves_no_math_to_do(self):
        growth = g.expand({"template": "compounding", "start": "weak", "grows": "reach of the echo"})
        line = g.describe_state(growth, g.new_state(growth), name="Echo Step")
        self.assertIn("rank F", line)
        self.assertIn("XP to E", line)


class BuildTests(unittest.TestCase):
    def test_build_rewrites_growth_math_from_the_seed(self):
        card = {"name": "Echo Step", "power_type": "compounding", "growth_math": "XP_to_next = 40 * n^1.55; F→E@60",
                "growth": {"pace": "fast", "start": "weak", "grows": "how far the step reaches"}}
        out = g.build(card, rank_scale="F,E,D,C,B,A,S,SS,SSS", difficulty="hard")
        self.assertNotIn("@60", out["growth_math"])
        self.assertEqual(out["growth_spec"]["template"], "compounding")
        self.assertEqual(out["power_type"], "compounding")
        self.assertIn("how far the step reaches", out["growth_math"])


if __name__ == "__main__":
    unittest.main()
