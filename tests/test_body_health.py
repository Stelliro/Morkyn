"""Tests for app/body_health.py (TODO n23, built but not wired).

Pure rule tests need no database. The DB tests use a temp AI_RPG_DB, init_db() plus the module's
ensure_schema(), and check that the writers touch only body_wounds and body_health_log.
"""
from __future__ import annotations

import json
import os
import random
import re
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-body-health-test-"))
_ENV = {
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_CONSOLIDATED_FACTS": str(_TMP / "facts.jsonl"),
    "AI_RPG_CAMPAIGN_SLOTS": str(_TMP / "slots"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
    "AI_RPG_IDEA_BANK": str(_TMP / "idea_bank"),
    "AI_RPG_LAUNCHER_PREFS": str(_TMP / "launcher_prefs.json"),
}
os.environ.update(_ENV)

from app.db import connect, init_db  # noqa: E402
from app import body_health as bh  # noqa: E402


def setUpModule():
    os.environ.update(_ENV)
    init_db()
    with connect() as conn:
        bh.ensure_schema(conn)


class FixedRng:
    """A stand-in rng whose random() returns the values given, in order (the last one repeats)."""

    def __init__(self, *values):
        self.values = list(values) or [0.5]
        self.calls = 0

    def random(self):
        value = self.values[min(self.calls, len(self.values) - 1)]
        self.calls += 1
        return value

    def choice(self, seq):
        return seq[0]


def _body(max_health=20):
    return bh.new_body(max_health)


def _with_wound(max_health=20, *, location="left_arm", kind="cut", severity=None, damage=None, state=None, wound_id=1, abs_minute=0):
    body, wound = bh.add_wound(_body(max_health), location=location, kind=kind, severity=severity, damage=damage, state=state, abs_minute=abs_minute)
    wound["id"] = wound_id
    return body, wound


def _wound_of(body, wound_id):
    for wound in body["wounds"]:
        if wound["id"] == wound_id:
            return wound
    return None


STATUS_LINE_KEYS = {"key", "severity", "line", "blocks"}
STATUS_SEVERITIES = {"info", "mild", "serious", "critical"}
DELTA_KEYS = {"energy", "fatigue", "health", "energy_exact", "fatigue_exact", "health_exact", "reasons"}


def _assert_status_lines(case, lines):
    for line in lines:
        case.assertEqual(set(line), STATUS_LINE_KEYS)
        case.assertIn(line["severity"], STATUS_SEVERITIES)
        case.assertIsInstance(line["line"], str)
        case.assertLessEqual(len(line["line"]), 160)
        case.assertNotIn("*", line["line"])
        case.assertIsInstance(line["blocks"], list)


def _assert_deltas(case, deltas):
    case.assertEqual(set(deltas), DELTA_KEYS)
    for key in ("energy", "fatigue", "health"):
        case.assertIsInstance(deltas[key], int)
        case.assertIsInstance(deltas[key + "_exact"], float)
    case.assertIsInstance(deltas["reasons"], list)


class TablesTests(unittest.TestCase):
    def test_locations_table_sums(self):
        self.assertEqual(sum(row[1] for row in bh.LOCATIONS.values()), 100)
        self.assertEqual(sum(row[2] for row in bh.LOCATIONS.values()), 100)
        for key, (label, share, weight, group) in bh.LOCATIONS.items():
            self.assertTrue(label)
            self.assertIn(group, bh.GROUPS)
            self.assertGreater(share, 0)
        self.assertEqual(len(bh.LOCATIONS), 8)
        for key in bh.BASIC_STATES:
            self.assertIn(key, bh.INFECT_CHANCE_PER_DAY)
            for treatment, target in bh.BASIC_STATES[key]["treatments"].items():
                self.assertIn(treatment, bh.TREATMENTS)
                target_state = target[5:] if target.startswith("roll:") else target
                self.assertIn(target_state, bh.BASIC_STATES)

    def test_water_words_literal(self):
        self.assertEqual(bh.WATER_WORDS, ("water", "waterskin", "water skin", "canteen", "flask", "bottle", "skin", "gourd"))

    def test_quality_from_outcome_table(self):
        self.assertEqual(bh.quality_from_outcome("critical_success"), 1.5)
        self.assertEqual(bh.quality_from_outcome("success"), 1.0)
        self.assertEqual(bh.quality_from_outcome("partial"), 0.8)
        self.assertEqual(bh.quality_from_outcome("failure"), 0.6)
        self.assertEqual(bh.quality_from_outcome("critical_failure"), 0.5)
        self.assertEqual(bh.quality_from_outcome(""), 1.0)
        self.assertEqual(bh.quality_from_outcome("nonsense"), 1.0)

    def test_merge_deltas(self):
        a = bh.zero_deltas()
        a.update({"health": -2, "health_exact": -1.5, "reasons": ["bleeding:left_arm"]})
        b = bh.zero_deltas()
        b.update({"fatigue": 3, "fatigue_exact": 2.5, "energy": -1, "energy_exact": -0.6, "reasons": ["fever:torso"]})
        merged = bh.merge_deltas(a, b)
        _assert_deltas(self, merged)
        self.assertEqual((merged["health"], merged["fatigue"], merged["energy"]), (-2, 3, -1))
        self.assertAlmostEqual(merged["health_exact"], -1.5)
        self.assertAlmostEqual(merged["fatigue_exact"], 2.5)
        self.assertEqual(merged["reasons"], ["bleeding:left_arm", "fever:torso"])
        _assert_deltas(self, bh.zero_deltas())


class BodyTests(unittest.TestCase):
    def test_new_body_shares_max_hp(self):
        body = _body(20)
        locs = body["locations"]
        self.assertEqual(set(locs), set(bh.LOCATIONS))
        self.assertEqual(locs["head"]["max_hp"], 3)
        self.assertEqual(locs["torso"]["max_hp"], 6)
        self.assertEqual(locs["left_arm"]["max_hp"], 2)
        self.assertEqual(locs["right_arm"]["max_hp"], 2)
        self.assertEqual(locs["left_hand"]["max_hp"], 1)
        self.assertEqual(locs["right_hand"]["max_hp"], 1)
        self.assertEqual(locs["left_leg"]["max_hp"], 3)
        self.assertEqual(locs["right_leg"]["max_hp"], 3)
        for loc in locs.values():
            self.assertEqual(loc["hp"], loc["max_hp"])
            self.assertFalse(loc["disabled"])
        self.assertEqual(body["wounds"], [])
        self.assertEqual(bh.health_from_body(body)["health"], 20)

    def test_severity_by_ratio_boundaries(self):
        self.assertEqual(bh.severity_for(10, 100), (1, "minor"))
        self.assertEqual(bh.severity_for(20, 100), (2, "moderate"))
        self.assertEqual(bh.severity_for(45, 100), (3, "serious"))
        self.assertEqual(bh.severity_for(75, 100), (4, "grave"))
        self.assertEqual(bh.severity_for(100, 100), (4, "grave"))

    def test_location_for_words_and_sides(self):
        self.assertEqual(bh.location_for("ribs"), "torso")
        self.assertEqual(bh.location_for("eye"), "head")
        self.assertEqual(bh.location_for("left hand"), "left_hand")
        self.assertEqual(bh.location_for("arm", side_hint="right"), "right_arm")
        first = bh.location_for("arm", rng=random.Random(7))
        second = bh.location_for("arm", rng=random.Random(7))
        self.assertEqual(first, second)
        self.assertIn(first, ("left_arm", "right_arm"))
        self.assertEqual(bh.location_for("tail"), "torso")
        self.assertEqual(bh.location_for("sword arm"), "right_arm")

    def test_roll_location_weighted_and_deterministic(self):
        self.assertEqual(bh.roll_location(rng=random.Random(3)), bh.roll_location(rng=random.Random(3)))
        self.assertEqual(bh.roll_location(abs_minute=500), bh.roll_location(abs_minute=500))
        rng = random.Random(11)
        counts = {}
        for _ in range(2000):
            key = bh.roll_location(rng=rng)
            counts[key] = counts.get(key, 0) + 1
        self.assertEqual(max(counts, key=counts.get), "torso")
        self.assertEqual(set(counts) - set(bh.LOCATIONS), set())

    def test_add_wound_start_state_by_kind(self):
        self.assertEqual(bh.add_wound(_body(), location="left_arm", kind="cut", severity=1)[1]["state"], "bleeding")
        self.assertEqual(bh.add_wound(_body(), location="left_arm", kind="blunt", severity=1)[1]["state"], "bruised")
        self.assertEqual(bh.add_wound(_body(), location="left_leg", kind="blunt", severity=3)[1]["state"], "broken")
        self.assertEqual(bh.add_wound(_body(), location="head", kind="blunt", severity=3)[1]["state"], "bruised")
        self.assertEqual(bh.add_wound(_body(), location="torso", kind="burn", severity=2)[1]["state"], "open")
        self.assertEqual(bh.add_wound(_body(), location="right_hand", kind="bite", severity=1)[1]["state"], "open")
        self.assertEqual(bh.add_wound(_body(), location="right_hand", kind="bite", severity=2)[1]["state"], "bleeding")

    def test_add_wound_requires_damage_or_severity(self):
        with self.assertRaises(ValueError):
            bh.add_wound(_body(), location="torso")
        with self.assertRaises(ValueError):
            bh.add_wound(_body(), location="tail", damage=1)
        with self.assertRaises(ValueError):
            bh.add_wound(_body(), location="torso", kind="curse", damage=1)
        body, wound = bh.add_wound(_body(100), location="torso", severity=2)
        self.assertEqual(wound["severity"], 2)
        self.assertAlmostEqual(wound["damage"], (0.20 + 0.45) / 2 * 30)
        body, wound = bh.add_wound(_body(100), location="torso", severity=4)
        self.assertAlmostEqual(wound["damage"], (0.75 + 1.0) / 2 * 30)
        self.assertEqual(wound["severity"], 4)
        self.assertEqual(len(body["wounds"]), 1)
        self.assertIsNone(wound["id"])
        self.assertEqual(wound["status"], "open")

    def test_add_wound_does_not_mutate_input(self):
        body = _body()
        bh.add_wound(body, location="torso", damage=1)
        self.assertEqual(body["wounds"], [])
        self.assertEqual(body["locations"]["torso"]["damage"], 0.0)

    def test_add_wound_merges_over_cap(self):
        body = _body(100)
        for damage in (1.0, 2.0, 3.0, 4.0):
            body, _ = bh.add_wound(body, location="torso", damage=damage)
        self.assertEqual(len(body["wounds"]), 4)
        body, merged = bh.add_wound(body, location="torso", damage=5.0)
        self.assertEqual(len(body["wounds"]), 4)
        self.assertAlmostEqual(merged["damage"], 9.0)
        self.assertAlmostEqual(body["locations"]["torso"]["damage"], 15.0)

    def test_wounds_from_injury_shapes(self):
        injury = {"kind": "self_injury", "limb": "ribs", "severity": True, "health_delta": -4,
                  "summary": "Botched Athletics: you hurt your ribs.",
                  "combat_penalty": {"mobility": 0, "attack": -1, "defense": -1}}
        body, wound = bh.wounds_from_injury(_body(20), injury, turn=3, abs_minute=100)
        self.assertEqual(wound["location"], "torso")
        self.assertEqual(wound["kind"], "blunt")
        self.assertEqual(wound["damage"], 4.0)
        self.assertEqual(wound["cause"], injury["summary"])
        self.assertEqual(wound["created_turn"], 3)
        self.assertEqual(wound["created_abs"], 100)
        sharp = dict(injury, limb="arm", summary="Unskilled with a knife: you cut your own arm.")
        _, wound2 = bh.wounds_from_injury(_body(20), sharp, turn=3, abs_minute=100, rng=random.Random(1))
        self.assertEqual(wound2["kind"], "cut")
        self.assertIn(wound2["location"], ("left_arm", "right_arm"))

    def test_wounds_from_health_delta_negative_spills_to_torso(self):
        body, touched = bh.wounds_from_health_delta(_body(100), -15, location="left_hand")
        self.assertEqual([w["location"] for w in touched], ["left_hand", "torso"])
        self.assertEqual(touched[0]["damage"], 5.0)
        self.assertEqual(touched[1]["damage"], 10.0)
        self.assertEqual(bh.health_from_body(body)["health"], 85)
        body2, touched2 = bh.wounds_from_health_delta(_body(100), -2, location="left_hand")
        self.assertEqual(len(touched2), 1)
        self.assertEqual(bh.health_from_body(body2)["health"], 98)
        body3, touched3 = bh.wounds_from_health_delta(_body(100), -3, rng=random.Random(5))
        self.assertEqual(len(touched3), 1)
        self.assertEqual(bh.wounds_from_health_delta(_body(100), 0)[1], [])

    def test_wounds_from_health_delta_positive_heals_worst_first(self):
        body, _ = bh.add_wound(_body(100), location="torso", damage=6)
        body, _ = bh.add_wound(body, location="left_leg", damage=2)
        body, touched = bh.wounds_from_health_delta(body, 5)
        damages = sorted(w["damage"] for w in body["wounds"])
        self.assertEqual(damages, [1.0, 2.0])
        self.assertEqual(len(touched), 1)
        body, touched = bh.wounds_from_health_delta(body, 10)
        self.assertEqual(body["wounds"], [])
        self.assertTrue(all(w["status"] == "healed" for w in touched))
        self.assertEqual(bh.health_from_body(body)["health"], 100)

    def test_health_from_body_aggregate_and_incapacitated(self):
        body, _ = bh.add_wound(_body(20), location="left_arm", damage=1.5)
        body, _ = bh.add_wound(body, location="right_leg", damage=2.5)
        view = bh.health_from_body(body)
        self.assertEqual(set(view), {"health", "max_health", "ratio", "incapacitated", "worst", "disabled_locations"})
        self.assertEqual(view["health"], 16)
        self.assertAlmostEqual(view["ratio"], 0.8)
        self.assertFalse(view["incapacitated"])
        self.assertEqual(view["worst"], {"location": "right_leg", "severity": 4, "state": "bleeding"})
        body, _ = bh.add_wound(_body(20), location="torso", damage=6)
        view = bh.health_from_body(body)
        self.assertEqual(view["health"], 0)
        self.assertTrue(view["incapacitated"])
        self.assertEqual(view["disabled_locations"], ["torso"])
        body, _ = bh.add_wound(_body(20), location="left_hand", damage=1)
        view = bh.health_from_body(body)
        self.assertFalse(view["incapacitated"])
        self.assertEqual(view["health"], 19)
        self.assertEqual(view["disabled_locations"], ["left_hand"])

    def test_hp_roundtrip(self):
        body, _ = bh.add_wound(_body(20), location="torso", damage=4)
        body, _ = bh.add_wound(body, location="left_leg", damage=3)
        self.assertEqual(bh.health_from_body(body)["health"], 13)
        body, _ = bh.wounds_from_health_delta(body, 7)
        self.assertEqual(bh.health_from_body(body)["health"], 20)
        self.assertEqual(body["wounds"], [])


class TreatmentTests(unittest.TestCase):
    def test_bandage_stops_bleeding_does_not_heal(self):
        body, wound = _with_wound(100, location="left_arm", kind="cut", severity=3)
        res = bh.apply_treatment(body, 1, "bandage", quality=1.2, abs_minute=30)
        self.assertTrue(res["ok"])
        self.assertEqual(res["reason"], "")
        self.assertEqual((res["from"], res["to"]), ("bleeding", "bandaged"))
        after = _wound_of(res["body"], 1)
        self.assertEqual(after["state"], "bandaged")
        self.assertAlmostEqual(after["damage"], wound["damage"])
        self.assertEqual(after["care_quality"], 1.2)
        self.assertEqual(after["state_since_abs"], 30)
        self.assertIn("not healed", res["line"])
        self.assertEqual(_wound_of(body, 1)["state"], "bleeding")

    def test_bandage_redress_resets_age(self):
        body, wound = _with_wound(100, severity=2, state="bandaged")
        wound["dressing_age_minutes"] = 2000
        res = bh.apply_treatment(body, 1, "bandage")
        self.assertTrue(res["ok"])
        self.assertEqual(res["reason"], "")
        self.assertEqual(_wound_of(res["body"], 1)["dressing_age_minutes"], 0)
        self.assertEqual(_wound_of(res["body"], 1)["state"], "bandaged")

    def test_splint_only_on_broken(self):
        body, _ = _with_wound(100, severity=2)
        res = bh.apply_treatment(body, 1, "splint")
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "not_applicable")
        self.assertIn("does nothing", res["line"])
        body, _ = _with_wound(100, location="left_leg", kind="blunt", severity=3)
        res = bh.apply_treatment(body, 1, "splint", abs_minute=10)
        self.assertTrue(res["ok"])
        self.assertEqual(res["to"], "splinted")

    def test_stitch_minor_acts_as_bandage(self):
        body, _ = _with_wound(100, severity=1)
        res = bh.apply_treatment(body, 1, "stitch")
        self.assertTrue(res["ok"])
        self.assertEqual(res["to"], "bandaged")
        self.assertEqual(res["line"], bh.TREATMENT_LINES[("bandage", "bandaged")].format(loc="left arm"))
        body, _ = _with_wound(100, severity=2)
        res = bh.apply_treatment(body, 1, "stitch")
        self.assertEqual(res["line"], bh.TREATMENT_LINES[("stitch", "bandaged")].format(loc="left arm"))

    def test_clean_and_salve_roll_on_infected(self):
        body, _ = _with_wound(100, severity=2, state="infected")
        fail = bh.apply_treatment(body, 1, "clean", rng=FixedRng(0.7))
        self.assertFalse(fail["ok"])
        self.assertEqual(fail["reason"], "failed_roll")
        self.assertEqual(_wound_of(fail["body"], 1)["state"], "infected")
        win = bh.apply_treatment(body, 1, "clean", rng=FixedRng(0.3), abs_minute=50)
        self.assertTrue(win["ok"])
        self.assertEqual(win["to"], "healing")
        self.assertEqual(_wound_of(win["body"], 1)["state_since_abs"], 50)
        # salve: 0.75 x 1.1 = 0.825
        self.assertFalse(bh.apply_treatment(body, 1, "salve", quality=1.1, rng=FixedRng(0.83))["ok"])
        salve_win = bh.apply_treatment(body, 1, "salve", quality=1.1, rng=FixedRng(0.80))
        self.assertTrue(salve_win["ok"])
        self.assertEqual(salve_win["to"], "healing")
        # 0.75 x 1.5 = 1.125 clamps to 0.95
        self.assertFalse(bh.apply_treatment(body, 1, "salve", quality=1.5, rng=FixedRng(0.96))["ok"])
        self.assertTrue(bh.apply_treatment(body, 1, "salve", quality=1.5, rng=FixedRng(0.94))["ok"])
        nothing = bh.apply_treatment(body, 1, "bandage")
        self.assertFalse(nothing["ok"])
        self.assertEqual(nothing["reason"], "no_effect")

    def test_unknown_wound_and_treatment(self):
        body, _ = _with_wound(100, severity=2)
        res = bh.apply_treatment(body, 999, "bandage")
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "no_such_wound")
        self.assertEqual(set(res), {"ok", "reason", "body", "wound", "from", "to", "line", "quality"})
        with self.assertRaises(ValueError):
            bh.apply_treatment(body, 1, "pray")
        with self.assertRaises(ValueError):
            bh.find_treatment_item([], "pray")

    def test_detect_treatment_intents(self):
        res = bh.detect_treatment("I bandage my left arm with a strip of cloth")
        self.assertEqual(res, {"treatment": "bandage", "location_hint": "left_arm", "item_hint": "strip of cloth"})
        res = bh.detect_treatment("wash the cut with water")
        self.assertEqual(res["treatment"], "clean")
        self.assertEqual(res["item_hint"], "water")
        res = bh.detect_treatment("splint the leg")
        self.assertEqual((res["treatment"], res["location_hint"]), ("splint", "leg"))
        self.assertIsNone(bh.detect_treatment('"Bandage that arm," she says.')["treatment"])
        self.assertIsNone(bh.detect_treatment("I won't bandage it yet")["treatment"])
        self.assertIsNone(bh.detect_treatment("I look around the room")["treatment"])
        self.assertEqual(bh.detect_treatment("stitch the gash on my right hand using a needle")["location_hint"], "right_hand")
        # The earliest treatment phrase wins; "set my" and "press on" count only with a limb word close behind.
        res = bh.detect_treatment("I set my pack down and bandage my arm")
        self.assertEqual((res["treatment"], res["location_hint"]), ("bandage", "arm"))
        self.assertIsNone(bh.detect_treatment("I press on down the road")["treatment"])
        self.assertEqual(bh.detect_treatment("I press on my thigh to slow the blood")["treatment"], "bandage")
        self.assertEqual(bh.detect_treatment("set my arm with a stick")["treatment"], "splint")
        self.assertEqual(bh.detect_treatment("wash the cut, then bandage it")["treatment"], "clean")

    def test_find_treatment_item_words_fallback_consumes(self):
        rows = [{"name": "linen bandages", "quantity": 2, "item_type": "misc", "description": ""}]
        row, quality, consumes = bh.find_treatment_item(rows, "bandage")
        self.assertEqual((row["name"], quality, consumes), ("linen bandages", 1.0, True))
        rows = [{"name": "wool cloak", "quantity": 1, "item_type": "clothing", "description": ""}]
        row, quality, consumes = bh.find_treatment_item(rows, "bandage")
        self.assertEqual((row["name"], quality, consumes), ("wool cloak", 0.6, False))
        rows = [{"name": "waterskin", "quantity": 1, "item_type": "container", "description": "half full"}]
        row, quality, consumes = bh.find_treatment_item(rows, "clean")
        self.assertEqual((row["name"], consumes), ("waterskin", False))
        self.assertEqual(bh.find_treatment_item([], "salve"), (None, 0.0, False))
        rows = [{"name": "linen bandages", "quantity": 0, "item_type": "misc", "description": ""}]
        self.assertEqual(bh.find_treatment_item(rows, "bandage"), (None, 0.0, False))
        rows = [{"name": "small pouch", "quantity": 1, "item_type": "consumable", "description": "a poultice of yarrow"}]
        self.assertEqual(bh.find_treatment_item(rows, "salve")[0]["name"], "small pouch")
        rows = [{"name": "odd blade", "quantity": 1, "item_type": "weapon", "description": "wrapped in a bandage"}]
        self.assertIsNone(bh.find_treatment_item(rows, "bandage")[0])

    def test_pick_wound_prefers_hint_then_applicable_then_severity(self):
        body, _ = bh.add_wound(_body(100), location="left_arm", severity=1)
        body["wounds"][-1]["id"] = 1
        body, _ = bh.add_wound(body, location="right_leg", kind="blunt", severity=3)
        body["wounds"][-1]["id"] = 2
        body, _ = bh.add_wound(body, location="torso", severity=2)
        body["wounds"][-1]["id"] = 3
        self.assertEqual(bh.pick_wound(body, location_hint="left_arm")["id"], 1)
        self.assertEqual(bh.pick_wound(body, location_hint="leg")["id"], 2)
        self.assertEqual(bh.pick_wound(body, treatment="splint")["id"], 2)
        self.assertEqual(bh.pick_wound(body, treatment="bandage")["id"], 3)
        self.assertEqual(bh.pick_wound(body)["id"], 2)
        self.assertIsNone(bh.pick_wound(body, location_hint="head"))
        self.assertIsNone(bh.pick_wound(_body()))


class ModifierTests(unittest.TestCase):
    def test_modifier_accepts_descriptive_and_rejects_basic_or_terminal(self):
        body, _ = _with_wound(100, severity=2, state="bandaged")
        res = bh.add_modifier(body, 1, "poultice of yarrow", note="smells of herbs", turn=4)
        self.assertTrue(res["ok"])
        self.assertEqual(res["modifier"], {"name": "poultice of yarrow", "note": "smells of herbs", "refines": "bandaged", "added_turn": 4})
        body = res["body"]
        res = bh.add_modifier(body, 1, "stitched badly")
        self.assertTrue(res["ok"])
        body = res["body"]
        for bad, reason in (("bleeding", "forbidden_word"), ("not bleeding", "forbidden_word"), ("healed", "forbidden_word"),
                            ("no longer bleeding", "forbidden_word"), ("", "empty"), ("   ", "empty"),
                            ("stitched badly", "duplicate"), ("Stitched Badly", "duplicate")):
            res = bh.add_modifier(body, 1, bad)
            self.assertFalse(res["ok"], bad)
            self.assertEqual(res["reason"], reason, bad)
        res = bh.add_modifier(body, 1, "swollen")
        self.assertTrue(res["ok"])
        body = res["body"]
        res = bh.add_modifier(body, 1, "throbbing")
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "too_many")
        wound = _wound_of(body, 1)
        self.assertEqual(wound["state"], "bandaged")
        self.assertEqual(wound["severity"], 2)
        self.assertEqual(len(wound["modifiers"]), 3)
        self.assertEqual(bh.add_modifier(body, 77, "dirty")["reason"], "no_such_wound")
        res = bh.remove_modifier(body, 1, "swollen")
        self.assertTrue(res["ok"])
        self.assertEqual(len(_wound_of(res["body"], 1)["modifiers"]), 2)
        self.assertEqual(bh.remove_modifier(res["body"], 1, "swollen")["reason"], "not_found")
        self.assertEqual(bh.capabilities(body), bh.capabilities(res["body"]))


class TickTests(unittest.TestCase):
    def test_tick_bleeding_costs_health_not_damage(self):
        body, wound = _with_wound(100, location="left_arm", severity=2)
        res = bh.tick(body, minutes=60, abs_minute=60)
        _assert_deltas(self, res["deltas"])
        self.assertAlmostEqual(res["deltas"]["health_exact"], -1.5)
        self.assertIn(res["deltas"]["health"], (-1, -2))
        self.assertIn("bleeding:left_arm", res["deltas"]["reasons"])
        self.assertAlmostEqual(_wound_of(res["body"], 1)["damage"], wound["damage"])
        self.assertEqual(set(res), {"body", "deltas", "transitions", "healed", "lines", "health", "hours", "minutes"})
        _assert_status_lines(self, res["lines"])

    def test_tick_carry_charges_the_same_over_short_ticks(self):
        # A sev2 bleed (1.5 per hour) at live tick sizes: ten 6-minute ticks charge the same whole points as one hour.
        start, _ = _with_wound(100, location="left_arm", severity=2)
        body = start
        acc = bh.zero_deltas()
        for i in range(10):
            res = bh.tick(body, minutes=6, abs_minute=6 * (i + 1))
            body = res["body"]
            acc = bh.merge_deltas(acc, res["deltas"])
        whole = bh.tick(start, minutes=60, abs_minute=60)
        self.assertEqual(acc["health"], whole["deltas"]["health"])
        self.assertEqual(whole["deltas"]["health"], -2)
        self.assertAlmostEqual(acc["health_exact"], -1.5)
        self.assertAlmostEqual(_wound_of(body, 1)["loss_carry"], _wound_of(whole["body"], 1)["loss_carry"], places=6)
        # Three 20-minute ticks do not overcharge either.
        body = start
        acc = bh.zero_deltas()
        for i in range(3):
            res = bh.tick(body, minutes=20, abs_minute=20 * (i + 1))
            body = res["body"]
            acc = bh.merge_deltas(acc, res["deltas"])
        self.assertEqual(acc["health"], -2)
        # Fever fatigue carries the same way on an infected wound.
        start, _ = _with_wound(100, location="torso", severity=2, state="infected")
        body = start
        acc = bh.zero_deltas()
        for i in range(10):
            res = bh.tick(body, minutes=6, abs_minute=6 * (i + 1), rng=FixedRng(0.99))
            body = res["body"]
            acc = bh.merge_deltas(acc, res["deltas"])
        whole = bh.tick(start, minutes=60, abs_minute=60, rng=FixedRng(0.99))
        self.assertEqual(acc["fatigue"], whole["deltas"]["fatigue"])
        self.assertEqual(acc["health"], whole["deltas"]["health"])

    def test_tick_bleeding_self_stops_minor(self):
        body, _ = _with_wound(100, severity=1)
        res = bh.tick(body, minutes=60, abs_minute=60)
        self.assertEqual(_wound_of(res["body"], 1)["state"], "open")
        self.assertEqual([(t["from"], t["to"], t["reason"]) for t in res["transitions"]], [("bleeding", "open", "self_stop")])
        body, _ = _with_wound(100, severity=3)
        res = bh.tick(body, minutes=600, abs_minute=600, rng=FixedRng(0.99))
        self.assertEqual(_wound_of(res["body"], 1)["state"], "bleeding")
        self.assertEqual(res["transitions"], [])

    def test_tick_open_closes_after_24h(self):
        body, _ = _with_wound(100, severity=2, state="open")
        res = bh.tick(body, minutes=1440, abs_minute=1440, rng=FixedRng(0.99))
        self.assertEqual(_wound_of(res["body"], 1)["state"], "healing")
        self.assertEqual(res["transitions"][0]["reason"], "closed_24h")
        res = bh.tick(body, minutes=1000, abs_minute=1000, rng=FixedRng(0.99))
        self.assertEqual(_wound_of(res["body"], 1)["state"], "open")

    def test_tick_healing_rate_and_rest_mult(self):
        def healed_amount(**kwargs):
            body, wound = _with_wound(20, location="torso", damage=1.0, state="healing")
            if "care" in kwargs:
                wound["care_quality"] = kwargs.pop("care")
            res = bh.tick(body, minutes=600, abs_minute=600, rng=FixedRng(0.99), **kwargs)
            return 1.0 - _wound_of(res["body"], 1)["damage"]

        self.assertAlmostEqual(healed_amount(), 0.48)
        self.assertAlmostEqual(healed_amount(rest_kind="sleep"), 0.48 * 1.6)
        self.assertAlmostEqual(healed_amount(recovery_mult=0.5), 0.24)
        self.assertAlmostEqual(healed_amount(care=1.5), 0.72)
        self.assertAlmostEqual(healed_amount(recovery_mult=0.01), 0.048)
        self.assertAlmostEqual(healed_amount(rest_kind="unknown"), 0.48)

    def test_tick_slices_day_boundary_rolls_infection(self):
        body, _ = _with_wound(100, severity=3, state="open", abs_minute=1400)
        res = bh.tick(body, minutes=20, abs_minute=1450, rng=FixedRng(0.2))
        self.assertEqual(_wound_of(res["body"], 1)["state"], "infected")
        self.assertEqual(res["transitions"][0]["reason"], "infected")
        res = bh.tick(body, minutes=20, abs_minute=1430, rng=FixedRng(0.0))
        self.assertEqual(_wound_of(res["body"], 1)["state"], "open")
        res = bh.tick(body, minutes=20, abs_minute=1450, rng=FixedRng(0.31))
        self.assertEqual(_wound_of(res["body"], 1)["state"], "open")

    def test_tick_bandaged_dirty_dressing_doubles_chance(self):
        body, wound = _with_wound(100, severity=3, state="bandaged", abs_minute=1400)
        res = bh.tick(body, minutes=20, abs_minute=1450, rng=FixedRng(0.12))
        self.assertEqual(_wound_of(res["body"], 1)["state"], "bandaged")
        self.assertEqual(_wound_of(res["body"], 1)["dressing_age_minutes"], 20)
        wound["dressing_age_minutes"] = 1500
        res = bh.tick(body, minutes=20, abs_minute=1450, rng=FixedRng(0.12))
        self.assertEqual(_wound_of(res["body"], 1)["state"], "infected")

    def test_tick_infected_worsens_and_costs(self):
        body, _ = _with_wound(100, location="right_leg", severity=2, state="infected")
        res = bh.tick(body, minutes=1440, abs_minute=1440, rng=FixedRng(0.99))
        after = _wound_of(res["body"], 1)
        self.assertEqual(after["severity"], 3)
        self.assertAlmostEqual(after["damage"], (0.45 + 0.75) / 2 * 13)
        self.assertGreater(res["deltas"]["fatigue"], 0)
        self.assertLess(res["deltas"]["health"], 0)
        self.assertAlmostEqual(res["deltas"]["health_exact"], -0.2 * 24)
        self.assertAlmostEqual(res["deltas"]["fatigue_exact"], 0.5 * 24)
        self.assertIn("worsened", [t["reason"] for t in res["transitions"]])
        self.assertEqual(bh.recovery_mult_from_body(res["body"]), 0.7)
        res = bh.tick(body, minutes=1000, abs_minute=1000, rng=FixedRng(0.99))
        self.assertEqual(_wound_of(res["body"], 1)["severity"], 2)

    def test_tick_splinted_mends(self):
        body, wound = _with_wound(100, location="left_leg", kind="blunt", damage=5.7, state="splinted")
        self.assertEqual(wound["severity"], 2)
        res = bh.tick(body, minutes=120 * 60, abs_minute=120 * 60, rng=FixedRng(0.99))
        after = _wound_of(res["body"], 1)
        self.assertEqual(after["state"], "healing")
        healed_while_splinted = 13 * 0.006 * 0.5 * 120
        self.assertAlmostEqual(after["damage"], (5.7 - healed_while_splinted) / 2)
        self.assertEqual(after["severity"], bh.severity_for(after["damage"], 13)[0])
        self.assertEqual(res["transitions"][0]["reason"], "mended")

    def test_tick_damage_zero_heals_and_removes(self):
        body, _ = _with_wound(20, location="torso", damage=0.1, state="healing")
        res = bh.tick(body, minutes=120, abs_minute=120, rng=FixedRng(0.99))
        self.assertEqual(res["body"]["wounds"], [])
        self.assertEqual(len(res["healed"]), 1)
        self.assertEqual(res["healed"][0]["status"], "healed")
        self.assertEqual(res["healed"][0]["closed_abs"], 120)
        self.assertEqual(res["health"]["health"], 20)
        self.assertEqual(res["lines"], [])
        self.assertEqual(res["transitions"][0]["to"], "healed")

    def test_tick_zero_minutes_noop(self):
        body, _ = _with_wound(100, severity=2)
        for minutes in (0, -5):
            res = bh.tick(body, minutes=minutes, abs_minute=500)
            self.assertEqual(res["body"]["wounds"], body["wounds"])
            self.assertEqual(res["deltas"], bh.zero_deltas())
            self.assertEqual(res["transitions"], [])
            self.assertEqual(res["minutes"], 0)

    def test_tick_does_not_mutate_input(self):
        body, _ = _with_wound(100, severity=1)
        bh.tick(body, minutes=120, abs_minute=120)
        self.assertEqual(_wound_of(body, 1)["state"], "bleeding")

    def test_strain_broken_arm_climb_adds_damage(self):
        body, wound = _with_wound(100, location="left_arm", kind="blunt", severity=3)
        self.assertEqual(wound["state"], "broken")
        res = bh.strain(body, "climb", abs_minute=10)
        after = _wound_of(res["body"], 1)
        self.assertAlmostEqual(after["damage"], wound["damage"] + 0.10 * 10)
        self.assertEqual(res["transitions"][0]["reason"], "strain")
        self.assertEqual(len(res["lines"]), 1)
        res = bh.strain(body, "travel", abs_minute=10, rng=FixedRng(0.0))
        self.assertEqual(res["transitions"], [])
        body, _ = _with_wound(100, location="left_arm", kind="cut", severity=2, state="healing")
        res = bh.strain(body, "fight", rng=FixedRng(0.1))
        self.assertEqual(_wound_of(res["body"], 1)["state"], "bleeding")
        res = bh.strain(body, "fight", rng=FixedRng(0.9))
        self.assertEqual(_wound_of(res["body"], 1)["state"], "healing")
        body, _ = _with_wound(100, location="left_arm", kind="burn", severity=2, state="healing")
        self.assertEqual(bh.strain(body, "fight", rng=FixedRng(0.0))["transitions"], [])
        self.assertEqual(bh.strain(body, "dance")["transitions"], [])
        ticked = bh.tick(_with_wound(100, location="left_arm", kind="blunt", severity=3)[0], minutes=30, abs_minute=30, activity="climb")
        self.assertEqual([t["reason"] for t in ticked["transitions"]], ["strain"])


class CapabilityTests(unittest.TestCase):
    def test_capabilities_clean_body(self):
        caps = bh.capabilities(_body())
        self.assertEqual(caps, {"two_handed": "ok", "climbing": "ok", "fine_work": "ok", "travel_speed_mult": 1.0,
                                "check_mods": {}, "combat": {"attack": 0, "defense": 0, "mobility": 0}, "reasons": [], "blocked": []})

    def test_capabilities_table_folds_worst(self):
        body, _ = bh.add_wound(_body(100), location="right_arm", severity=2)
        caps = bh.capabilities(body)
        self.assertEqual(caps["two_handed"], "hampered")
        self.assertEqual(caps["check_mods"], {"athletics": -1, "melee": -1})
        body, _ = bh.add_wound(body, location="left_leg", kind="blunt", severity=3)
        caps = bh.capabilities(body)
        self.assertAlmostEqual(caps["travel_speed_mult"], 0.4)
        self.assertEqual(caps["climbing"], "blocked")
        self.assertEqual(caps["combat"]["mobility"], -3)
        self.assertEqual(caps["check_mods"]["athletics"], -5)
        self.assertEqual(caps["blocked"], ["climbing"])
        self.assertEqual(len(caps["reasons"]), 2)
        self.assertIn("left leg broken", caps["reasons"])
        body, _ = bh.add_wound(_body(100), location="left_leg", severity=2)
        body, _ = bh.add_wound(body, location="right_leg", severity=2)
        self.assertAlmostEqual(bh.capabilities(body)["travel_speed_mult"], 0.5625)
        body, _ = bh.add_wound(_body(100), location="left_leg", severity=4)
        body, _ = bh.add_wound(body, location="right_leg", severity=4)
        self.assertAlmostEqual(bh.capabilities(body)["travel_speed_mult"], 0.25)
        body, _ = bh.add_wound(_body(100), location="torso", severity=3)
        self.assertEqual(bh.capabilities(body)["combat"]["attack"], -2)

    def test_recovery_modifier_and_merge_recovery(self):
        clean = bh.recovery_modifier(_body())
        self.assertEqual(clean, {"mult": 1.0, "factors": [], "label": ""})
        body, _ = bh.add_wound(_body(100), location="left_arm", severity=2, state="infected")
        mod = bh.recovery_modifier(body)
        self.assertEqual(mod["mult"], 0.7)
        self.assertEqual(mod["factors"], [{"source": "wound:left_arm", "band": "infected", "mult": 0.7}])
        self.assertEqual(mod["label"], "recovery slowed (wound left arm)")
        needs_like = {"mult": 0.85, "factors": [{"source": "hunger", "band": "hungry", "mult": 0.85}], "label": "recovery slowed (hunger)"}
        wound_like = {"mult": 0.8, "factors": [{"source": "wound:left_arm", "band": "bleeding", "mult": 0.8}], "label": "recovery slowed (wound:left_arm)"}
        merged = bh.merge_recovery(needs_like, wound_like)
        self.assertAlmostEqual(merged["mult"], 0.68)
        self.assertEqual(len(merged["factors"]), 2)
        self.assertEqual(set(merged), {"mult", "factors", "label"})
        self.assertAlmostEqual(bh.merge_recovery({"mult": 1.05, "factors": [], "label": ""}, clean)["mult"], 1.05)
        self.assertAlmostEqual(bh.merge_recovery({"mult": 0.1, "factors": [], "label": ""}, wound_like)["mult"], 0.1)
        self.assertAlmostEqual(bh.merge_recovery({"mult": 2.0, "factors": [], "label": ""}, clean)["mult"], 1.25)

    def test_move_verdict_shape_and_reasons(self):
        verdict = bh.move_verdict(_body(), "map_step")
        self.assertEqual(set(verdict), {"allowed", "reason", "message", "label", "kind", "movement_locked"})
        self.assertEqual(verdict, {"allowed": True, "reason": "", "message": "", "label": "", "kind": "map_step", "movement_locked": False})
        body, _ = bh.add_wound(_body(20), location="torso", damage=6)
        verdict = bh.move_verdict(body, "town_walk")
        self.assertFalse(verdict["allowed"])
        self.assertEqual(verdict["reason"], "incapacitated")
        self.assertTrue(verdict["movement_locked"])
        self.assertLessEqual(len(verdict["message"]), 160)
        body, _ = bh.add_wound(_body(20), location="left_leg", damage=3)
        body, _ = bh.add_wound(body, location="right_leg", damage=3)
        verdict = bh.move_verdict(body, "travel_press")
        self.assertEqual(verdict["reason"], "cannot_walk")
        self.assertEqual(verdict["kind"], "travel_press")
        body, _ = bh.add_wound(_body(20), location="left_leg", kind="blunt", severity=3)
        self.assertTrue(bh.move_verdict(body, "map_step")["allowed"])
        self.assertEqual(bh.move_verdict({"bad": "body"}, "map_step")["allowed"], True)
        for reason in bh.MOVE_REASONS:
            self.assertIn(reason, bh.MOVE_MESSAGES)


class ProseTests(unittest.TestCase):
    def test_status_lines_and_prompt_block(self):
        self.assertEqual(bh.status_lines(_body()), [])
        self.assertEqual(bh.prompt_block(_body()), "")
        body, _ = _with_wound(100, location="left_arm", severity=3, state="bandaged")
        body = bh.add_modifier(body, 1, "stitched badly")["body"]
        body, _ = bh.add_wound(body, location="right_leg", kind="blunt", severity=4)
        lines = bh.status_lines(body)
        _assert_status_lines(self, lines)
        keys = [line["key"] for line in lines]
        self.assertIn("wound:left_arm:3", keys)
        self.assertIn("wound:right_leg:4", keys)
        self.assertIn("capability:climbing", keys)
        self.assertIn("travel", keys)
        arm = next(line for line in lines if line["key"] == "wound:left_arm:3")
        self.assertIn("left arm", arm["line"])
        self.assertIn("serious", arm["line"])
        self.assertIn("bandaged", arm["line"])
        self.assertIn("(stitched badly)", arm["line"])
        self.assertEqual(arm["severity"], "serious")
        leg = next(line for line in lines if line["key"] == "wound:right_leg:4")
        self.assertEqual(leg["severity"], "critical")
        climb = next(line for line in lines if line["key"] == "capability:climbing")
        self.assertEqual(climb["blocks"], ["climbing"])
        block = bh.prompt_block(body)
        self.assertTrue(block.startswith("Player body (server truth):\n- Health: "))
        self.assertIn("left arm serious", block)
        self.assertIn(bh.PROMPT_RULE_LINE, block)
        self.assertTrue(all(ln.startswith("- ") for ln in block.splitlines()[1:]))

    def test_conditions_view_legacy_shape(self):
        body, _ = _with_wound(100, location="left_leg", kind="blunt", severity=3, wound_id=9)
        view = bh.conditions_view(body, turn=5)
        self.assertEqual(len(view), 1)
        entry = view[0]
        self.assertEqual(set(entry), {"id", "name", "summary", "penalties", "severe", "turn"})
        self.assertEqual(entry["id"], "wound_9")
        self.assertTrue(entry["severe"])
        self.assertEqual(entry["turn"], 5)
        self.assertEqual(entry["penalties"]["mobility"], -3)
        self.assertIn("Left leg", entry["name"])
        self.assertEqual(bh.conditions_view(_body()), [])

    def test_state_view_shape(self):
        body, _ = _with_wound(100, location="left_arm", severity=2)
        view = bh.state_view(body)
        self.assertEqual(set(view), {"max_health", "health", "locations", "wounds", "capabilities", "lines"})
        self.assertEqual(len(view["locations"]), 8)
        self.assertEqual(view["locations"][2]["states"], ["bleeding"])
        self.assertEqual(view["wounds"][0]["severity_label"], "moderate")
        self.assertEqual(view["wounds"][0]["state_label"], "bleeding")
        self.assertIsInstance(view["lines"][0], str)

    def test_event_proposals_shape(self):
        self.assertEqual(bh.event_proposals(_body(), turn=3), [])
        body, _ = _with_wound(100, severity=3)
        proposals = bh.event_proposals(body, turn=3)
        self.assertEqual(len(proposals), 1)
        event = proposals[0]
        self.assertEqual(set(event), {"kind", "summary", "trigger", "due_turn", "force", "priority", "payload"})
        self.assertEqual(event["kind"], "custom")
        self.assertIs(event["force"], False)
        self.assertEqual(event["trigger"], "body:bleeding")
        self.assertEqual(event["priority"], 6)
        self.assertEqual(event["due_turn"], 4)
        self.assertIsInstance(event["payload"], dict)
        body, _ = _with_wound(100, severity=2)
        self.assertEqual(bh.event_proposals(body, turn=3), [])


def _table_counts(conn):
    names = [row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
    return {name: conn.execute(f'SELECT COUNT(*) AS n FROM "{name}"').fetchone()["n"] for name in names}


def _settings_snapshot(conn):
    return {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM settings")}


WORLD_TIME = {"day": 2, "minute": 90, "hour": 1, "minute_of_hour": 30, "part_of_day": "night",
              "day_length_minutes": 1440, "epoch_label": "", "label": "Day 2, 01:30"}
WORLD_ABS = 1440 + 90


class BodyHealthDbTests(unittest.TestCase):
    def setUp(self):
        os.environ.update(_ENV)
        path = Path(_ENV["AI_RPG_DB"])
        if path.exists():
            path.unlink()
        init_db()
        with connect() as conn:
            bh.ensure_schema(conn)
            conn.execute("DELETE FROM player")
            conn.execute(
                "INSERT INTO player (id, name, health, max_health, level, xp, gold, current_location_id) VALUES (1, 'T', 20, 20, 1, 0, 12, NULL)"
            )
            conn.execute(
                "INSERT INTO inventory (code, name, description, quantity, item_type) VALUES ('I1', 'linen bandages', '', 2, 'misc')"
            )
            conn.execute(
                "INSERT INTO inventory (code, name, description, quantity, item_type) VALUES ('I2', 'waterskin', 'half full', 1, 'container')"
            )

    def _rows(self, conn):
        return [dict(r) for r in conn.execute("SELECT * FROM inventory ORDER BY id").fetchall()]

    def test_ensure_schema_idempotent_and_tables_exist(self):
        path = Path(_ENV["AI_RPG_DB"])
        path.unlink()
        init_db()
        with connect() as conn:
            names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'index')")}
            self.assertNotIn("body_wounds", names)
            self.assertNotIn("body_health_log", names)
            bh.ensure_schema(conn)
            bh.ensure_schema(conn)
            names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'index')")}
            self.assertIn("body_wounds", names)
            self.assertIn("body_health_log", names)
            self.assertIn("idx_body_wounds_status", names)
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(body_wounds)")}
            self.assertEqual(cols, {"id", "location", "kind", "severity", "damage", "state", "state_since_abs", "dressing_age_minutes",
                                    "care_quality", "modifiers", "cause", "created_turn", "created_abs", "closed_turn", "closed_abs", "status",
                                    "loss_carry", "fatigue_carry"})

    def test_save_and_load_roundtrip_ids(self):
        body = _body(20)
        body, _ = bh.add_wound(body, location="left_arm", damage=1.25, cause="a tavern knife", turn=2, abs_minute=50)
        body, _ = bh.add_wound(body, location="torso", kind="blunt", damage=0.1, state="healing", turn=2, abs_minute=50)
        body = bh.add_modifier(body, None, "stitched badly", turn=2)["body"]
        with connect() as conn:
            saved = bh.save_body(conn, body, turn=2, abs_minute=50)
            ids = [w["id"] for w in saved["wounds"]]
            self.assertTrue(all(isinstance(i, int) for i in ids))
            self.assertEqual(len(set(ids)), 2)
            loaded = bh.load_body(conn, max_health=20)
            self.assertEqual(loaded["wounds"], saved["wounds"])
            self.assertEqual(loaded["wounds"][0]["damage"], 1.25)
            self.assertEqual(loaded["wounds"][0]["modifiers"][0]["name"], "stitched badly")
            res = bh.tick(loaded, minutes=120, abs_minute=170, rng=FixedRng(0.99))
            self.assertEqual(len(res["healed"]), 1)
            after = bh.save_body(conn, res["body"], healed=res["healed"], turn=3, abs_minute=170)
            self.assertEqual(len(after["wounds"]), 1)
            reloaded = bh.load_body(conn, max_health=20)
            self.assertEqual(len(reloaded["wounds"]), 1)
            statuses = {r["id"]: r["status"] for r in conn.execute("SELECT id, status FROM body_wounds")}
            self.assertEqual(sorted(statuses.values()), ["healed", "open"])
            events = [r["event"] for r in conn.execute("SELECT event FROM body_health_log ORDER BY id")]
            self.assertEqual(events.count("wound"), 2)
            self.assertEqual(events.count("healed"), 1)

    def test_tick_and_save_logs_and_leaves_player_untouched(self):
        body, _ = bh.add_wound(_body(20), location="left_arm", severity=1, turn=1, abs_minute=WORLD_ABS - 60)
        with connect() as conn:
            bh.save_body(conn, body, turn=1, abs_minute=WORLD_ABS - 60)
        with connect() as conn:
            before = _table_counts(conn)
            player_before = dict(conn.execute("SELECT * FROM player WHERE id = 1").fetchone())
            inventory_before = self._rows(conn)
            settings_before = _settings_snapshot(conn)
            res = bh.tick_and_save(conn, minutes=60, world_time=WORLD_TIME, max_health=20, turn=2)
            after = _table_counts(conn)
            self.assertEqual(dict(conn.execute("SELECT * FROM player WHERE id = 1").fetchone()), player_before)
            self.assertEqual(self._rows(conn), inventory_before)
            self.assertEqual(_settings_snapshot(conn), settings_before)
        changed = {name for name in before if before[name] != after.get(name)}
        self.assertTrue(changed <= set(bh.OWN_TABLES), changed)
        self.assertEqual(after["body_health_log"] - before["body_health_log"], 2)
        with connect() as conn:
            events = [r["event"] for r in conn.execute("SELECT event FROM body_health_log ORDER BY id")]
            self.assertIn("transition", events)
            self.assertIn("tick_loss", events)
            row = conn.execute("SELECT state, state_since_abs FROM body_wounds").fetchone()
            self.assertEqual((row["state"], row["state_since_abs"]), ("open", WORLD_ABS))
        self.assertEqual(res["deltas"]["health"], -1 if res["deltas"]["health_exact"] <= -0.5 else 0)
        self.assertEqual(res["body"]["wounds"][0]["state"], "open")

    def test_treat_from_inventory_proposes_consume_only(self):
        body, _ = bh.add_wound(_body(20), location="left_arm", damage=1.0, turn=1, abs_minute=WORLD_ABS - 10)
        with connect() as conn:
            bh.save_body(conn, body, turn=1, abs_minute=WORLD_ABS - 10)
        intent = bh.detect_treatment("I bandage my left arm with the linen bandages")
        with connect() as conn:
            before = _table_counts(conn)
            inventory_before = self._rows(conn)
            player_before = dict(conn.execute("SELECT * FROM player WHERE id = 1").fetchone())
            res = bh.treat_from_inventory(conn, intent, rows=inventory_before, world_time=WORLD_TIME, max_health=20, turn=2,
                                          skill_quality=bh.quality_from_outcome("success"))
            after = _table_counts(conn)
            self.assertTrue(res["ok"], res)
            self.assertEqual(res["consume"], {"name": "linen bandages", "quantity_delta": -1, "source": "body_health", "reason": "bandage"})
            self.assertEqual(self._rows(conn), inventory_before)
            self.assertEqual(self._rows(conn)[0]["quantity"], 2)
            self.assertEqual(dict(conn.execute("SELECT * FROM player WHERE id = 1").fetchone()), player_before)
            row = conn.execute("SELECT state, care_quality FROM body_wounds").fetchone()
            self.assertEqual(row["state"], "bandaged")
            self.assertEqual(row["care_quality"], 1.0)
            self.assertEqual(conn.execute("SELECT COUNT(*) AS n FROM body_health_log WHERE event = 'treatment'").fetchone()["n"], 1)
        changed = {name for name in before if before[name] != after.get(name)}
        self.assertTrue(changed <= set(bh.OWN_TABLES), changed)
        with connect() as conn:
            rows = self._rows(conn)
            res = bh.treat_from_inventory(conn, bh.detect_treatment("wash the arm with water"), rows=rows, world_time=WORLD_TIME, max_health=20, turn=3)
            self.assertTrue(res["ok"])
            self.assertIsNone(res["consume"])
            self.assertEqual(res["to"], "bandaged")

    def test_treat_from_inventory_no_item(self):
        body, _ = bh.add_wound(_body(20), location="left_arm", damage=1.0, turn=1, abs_minute=WORLD_ABS - 10)
        with connect() as conn:
            bh.save_body(conn, body, turn=1, abs_minute=WORLD_ABS - 10)
            before = _table_counts(conn)
            res = bh.treat_from_inventory(conn, {"treatment": "salve", "location_hint": "", "item_hint": ""}, rows=self._rows(conn),
                                          world_time=WORLD_TIME, max_health=20, turn=2)
            self.assertFalse(res["ok"])
            self.assertEqual(res["reason"], "no_item")
            self.assertIsNone(res["consume"])
            self.assertEqual(_table_counts(conn), before)
            self.assertEqual(conn.execute("SELECT state FROM body_wounds").fetchone()["state"], "bleeding")
            res = bh.treat_from_inventory(conn, {"treatment": None, "location_hint": "", "item_hint": ""}, rows=self._rows(conn),
                                          world_time=WORLD_TIME, max_health=20)
            self.assertFalse(res["ok"])
            res = bh.treat_from_inventory(conn, {"treatment": "bandage", "location_hint": "head", "item_hint": ""}, rows=self._rows(conn),
                                          world_time=WORLD_TIME, max_health=20)
            self.assertEqual(res["reason"], "no_such_wound")
            self.assertEqual(_table_counts(conn), before)

    def test_add_modifier_and_save_persists_json(self):
        body, _ = bh.add_wound(_body(20), location="left_arm", damage=1.0, turn=1)
        with connect() as conn:
            saved = bh.save_body(conn, body, turn=1)
            wound_id = saved["wounds"][0]["id"]
            before = _table_counts(conn)
            res = bh.add_modifier_and_save(conn, wound_id, "poultice of yarrow", note="from the healer", turn=2, world_time=WORLD_TIME, max_health=20)
            self.assertTrue(res["ok"])
            raw = conn.execute("SELECT modifiers FROM body_wounds WHERE id = ?", (wound_id,)).fetchone()["modifiers"]
            self.assertIn('"poultice of yarrow"', raw)
            self.assertEqual(bh.load_body(conn, max_health=20)["wounds"][0]["modifiers"][0]["refines"], "bleeding")
            after = _table_counts(conn)
            self.assertEqual(after["body_health_log"] - before["body_health_log"], 1)
            bad = bh.add_modifier_and_save(conn, wound_id, "healed", turn=2, max_health=20)
            self.assertFalse(bad["ok"])
            self.assertEqual(_table_counts(conn), after)
            missing = bh.add_modifier_and_save(conn, 999, "dirty", turn=2, max_health=20)
            self.assertEqual(missing["reason"], "no_such_wound")
            picked = bh.add_modifier_and_save(conn, None, "swollen", turn=2, max_health=20)
            self.assertTrue(picked["ok"])
            raw = conn.execute("SELECT modifiers FROM body_wounds WHERE id = ?", (wound_id,)).fetchone()["modifiers"]
            self.assertIn('"swollen"', raw)
            self.assertEqual(_table_counts(conn)["body_health_log"] - after["body_health_log"], 1)
            conn.execute("DELETE FROM body_wounds")
            none_left = bh.add_modifier_and_save(conn, None, "dirty", turn=2, max_health=20)
            self.assertEqual(none_left["reason"], "no_such_wound")

    def test_log_event_detail_always_parses(self):
        reasons = [f"bleeding:right_hand_{i:02d}" for i in range(40)]
        with connect() as conn:
            bh.log_event(conn, turn=1, abs_minute=10, wound_id=None, event="tick_loss", detail={"health": -3, "reasons": reasons})
            bh.log_event(conn, turn=1, abs_minute=10, wound_id=None, event="wound", detail={"cause": "x" * 2000})
            rows = [r["detail"] for r in conn.execute("SELECT detail FROM body_health_log ORDER BY id")]
        self.assertEqual(len(rows), 2)
        first = json.loads(rows[0])
        self.assertEqual(first["health"], -3)
        self.assertEqual(len(first["reasons"]), bh.LOG_REASONS_MAX + 1)
        self.assertEqual(first["reasons"][-1], f"+{40 - bh.LOG_REASONS_MAX} more")
        second = json.loads(rows[1])
        self.assertEqual(second, {"truncated": True, "event": "wound"})
        for raw in rows:
            self.assertLessEqual(len(raw), bh.LOG_DETAIL_MAX)

    def test_private_imports_still_exist(self):
        from app import player_resources, prose_state

        for name in ("_int", "_float", "world_abs_minutes"):
            self.assertTrue(hasattr(player_resources, name), name)
        self.assertTrue(hasattr(prose_state, "strip_negated_clauses"))

    def test_module_is_a_leaf(self):
        offenders = []
        pattern = re.compile(r"app\.body_health|import body_health")
        for folder in ("app", "static"):
            for path in (ROOT / folder).rglob("*"):
                if not path.is_file() or path.suffix not in {".py", ".js", ".html", ".css"}:
                    continue
                if path == ROOT / "app" / "body_health.py":
                    continue
                if pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
                    offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [])
        doc = bh.__doc__ or ""
        self.assertIn("Status: built, not wired (TODO n23).", doc)
        self.assertIn("Wiring (not done):", doc)
        self.assertIn("Turn on:", doc)
        self.assertIn("Tests: tests/test_body_health.py", doc)
        self.assertEqual(sorted(bh.OWN_TABLES), ["body_health_log", "body_wounds"])


if __name__ == "__main__":
    unittest.main()
