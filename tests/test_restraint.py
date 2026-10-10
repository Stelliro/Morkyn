"""Tests for app/restraint.py (TODO n13, built but not wired).

Pure tests need no database. The DB tests use a temporary file pinned through the AI_RPG_* environment
at import and again in setUpModule, so nothing here ever touches data/world.db. No model, no network,
no wall clock: every time is a world-time dict handed in by the test.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-restraint-test-"))
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

from app.db import connect, db_path, init_db  # noqa: E402
from app import restraint  # noqa: E402


def setUpModule() -> None:
    os.environ.update(_ENV)
    assert str(db_path()).startswith(str(_TMP)), f"test isolation failed: {db_path()!r}"
    init_db()
    conn = connect()
    try:
        with conn:
            restraint.ensure_schema(conn)
    finally:
        conn.close()


# contracts.md 1: the shared shapes this module produces.
_MOVE_VERDICT_TYPES = {"allowed": bool, "reason": str, "message": str, "label": str, "kind": str, "movement_locked": bool}
_JOURNAL_NOTE_TYPES = {"kind": str, "content": str}
_EVIDENCE_TYPES = {"check": str, "ok": bool, "evidence": str, "severity": str, "weight": float}
_STATUS_LINE_TYPES = {"key": str, "severity": str, "line": str, "blocks": list}
_ENTITY_REF_TYPES = {"code": str, "name": str, "kind": str, "role": str}
_SEVERITIES = ("info", "mild", "serious", "critical")
_EVIDENCE_SEVERITIES = ("block", "warn", "info")

WT = {"day": 1, "minute": 300}          # abs minute 300
WT_600 = {"day": 1, "minute": 600}
WT_599 = {"day": 1, "minute": 599}


def _assert_shape(case, value, types, *, extra_ok=()):
    case.assertIsInstance(value, dict)
    case.assertEqual(set(value) - set(extra_ok), set(types), f"keys differ: {sorted(value)}")
    for key, typ in types.items():
        case.assertIsInstance(value[key], typ, f"{key} should be {typ.__name__}, got {type(value[key]).__name__}")


def _assert_journal(case, notes):
    case.assertIsInstance(notes, list)
    for note in notes:
        _assert_shape(case, note, _JOURNAL_NOTE_TYPES)
        case.assertLessEqual(len(note["kind"]), 40)
        case.assertLessEqual(len(note["content"]), 900)
        case.assertIn(note["kind"], ("restrained", "released", "escort", "system"))


def _bonds_state(**over):
    st = restraint.free_state()
    st.update({
        "mode": "restrained", "label": "Bound at the wrists", "reason": "capture:lost_fight",
        "by": {"code": "A", "name": "Captain Ror", "kind": "person", "role": "guard captain"},
        "scope": "person", "since": {"turn": 3, "abs_minute": 300},
        "conditions": [{"type": "time", "abs_minute": 600}],
        "allowed": list(restraint.ALLOWED_BY_MODE["restrained"]),
        "escape": {"skill": "athletics", "dc": 14, "attempts": 0, "last_turn": 0, "cooldown_turns": 1, "fail_penalty_minutes": 30},
        "set_turn": 3,
    })
    st.update(over)
    return st


def _custody_state(**over):
    st = _bonds_state(mode="custody", label="In the watch's custody", faction="town watch",
                      allowed=list(restraint.ALLOWED_BY_MODE["custody"]),
                      escape={"skill": "stealth", "dc": 16, "attempts": 0, "last_turn": 0, "cooldown_turns": 2, "fail_penalty_minutes": 60},
                      conditions=[])
    st.update(over)
    return st


def _confined_state(**over):
    st = _bonds_state(mode="confined", label="Held in the gaol cell", scope="location",
                      place={"location_id": 7, "location_code": "L7", "plot": "C7.1.0.12", "city_id": "C7", "cell": [3, 4]},
                      allowed=list(restraint.ALLOWED_BY_MODE["confined"]),
                      escape={"skill": "lockpicking", "dc": 18, "attempts": 0, "last_turn": 0, "cooldown_turns": 3, "fail_penalty_minutes": 240},
                      conditions=[{"type": "time", "abs_minute": 1740}])
    st.update(over)
    return st


def _board(width=12, height=12, water_x=None):
    tiles = []
    for y in range(height):
        for x in range(width):
            state = "water" if water_x is not None and x == water_x else "plains"
            tiles.append({"x": x, "y": y, "state": state, "walkable": state != "water"})
    return {"id": "board-test", "width": width, "height": height, "tiles": tiles, "player": {"x": 1, "y": 1}}


def _world_chart():
    return {
        "id": "world-test", "scale": "world", "width": 16383, "height": 16383,
        "cities": [{"id": "C7", "name": "Ashbarrow", "x": 50, "y": 50, "band": "town", "cells": [{"x": 50, "y": 50, "local": [0, 0]}]}],
        "player": {"x": 40, "y": 40},
    }


_LOCATIONS = [
    {"id": 5, "code": "L4", "name": "Old Mill", "parent_id": 0, "plot_id": "", "city_id": ""},
    {"id": 7, "code": "L7", "name": "Gaol cell", "parent_id": 5, "plot_id": "C7.1.0.12", "city_id": "C7"},
]


class LeafTests(unittest.TestCase):
    def test_module_is_a_leaf(self):
        needle = re.compile(r"app\.restraint\b|from app import restraint\b|import restraint\b")
        offenders = []
        for folder in ("app", "static"):
            for path in sorted((ROOT / folder).rglob("*")):
                if not path.is_file() or path.suffix not in (".py", ".js", ".html", ".css"):
                    continue
                if path == ROOT / "app" / "restraint.py":
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                if needle.search(text):
                    offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [], "the live game must not import app.restraint in this pass")
        doc = restraint.__doc__ or ""
        self.assertIn("Status: built, not wired (TODO n13).", doc)
        self.assertIn("Wiring (not done):", doc)
        self.assertIn("Turn on:", doc)
        self.assertIn("Tests: tests/test_restraint.py", doc)
        # Private-import pins (contracts.md 5.3): the names the module reads must still exist.
        from app import tile_world, town_grid, turn_prompts, world

        self.assertTrue(callable(world._turn_intent))
        self.assertTrue(callable(tile_world._cell_at))
        self.assertTrue(callable(tile_world._player_xy))
        self.assertTrue(callable(tile_world.tile_walkable))
        self.assertTrue(callable(tile_world.walk_minutes_for_step))
        self.assertTrue(callable(town_grid._locate))
        self.assertTrue(callable(turn_prompts.next_world_step))
        self.assertEqual(restraint.ESCORT_CELL_BUDGET, 3 * tile_world.STEP_BUDGET)

    def test_docstring_hooks_name_real_functions(self):
        doc = restraint.__doc__ or ""
        hooks = re.findall(r"(app/[\w/]+\.py):(\w+)\(\)", doc)
        self.assertGreaterEqual(len(hooks), 18)
        for rel, func in hooks:
            source = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIsNotNone(re.search(rf"^def {re.escape(func)}\(", source, re.M), f"{rel}:{func}() is named as a hook but does not exist")
        town_source = (ROOT / "app" / "town_moves.py").read_text(encoding="utf-8")
        for func in ("plan_exit", "walk_out", "walk_to_cell", "click_walk", "enter_town", "_set_marker"):
            self.assertIsNotNone(re.search(rf"^def {func}\(", town_source, re.M), func)
        tile_source = (ROOT / "app" / "tile_world.py").read_text(encoding="utf-8")
        self.assertIsNotNone(re.search(r"^def restore_player_position\(", tile_source, re.M))
        world_source = (ROOT / "app" / "world.py").read_text(encoding="utf-8")
        for name in ("SNAPSHOT_SETTING_KEYS", "WORLD_TABLES", "RESTORE_ORDER", "AUTOINC_TABLES", "WORLD_EVENT_KINDS"):
            self.assertIn(f"\n{name} = ", world_source, name)
        self.assertIsNotNone(re.search(r"^def _capture_pre_turn_rows\(", world_source, re.M))
        self.assertIn("\nOPCODES = ", (ROOT / "app" / "turn_dsl.py").read_text(encoding="utf-8"))

    def test_rules_tables_hold_the_designed_numbers(self):
        self.assertEqual(restraint.CAPTURE_DEFAULTS["bonds"], ("restrained", "person", "Bound at the wrists", 120, "athletics", 14, 1, 30))
        self.assertEqual(restraint.CAPTURE_DEFAULTS["custody"], ("custody", "person", "In {faction} custody", 0, "stealth", 16, 2, 60))
        self.assertEqual(restraint.CAPTURE_DEFAULTS["cell"], ("confined", "location", "Held in {place}", 1440, "lockpicking", 18, 3, 240))
        self.assertEqual(restraint.CAPTURE_MINUTES_BY_SEVERITY, {"light": 0.5, "normal": 1.0, "harsh": 3.0})
        self.assertEqual(restraint.ESCAPE_DC_BY_CAPTOR_POWER, ((0, -2), (20, 0), (40, 2), (70, 4)))
        self.assertEqual((restraint.ESCAPE_MAX_ATTEMPTS_PER_DAY, restraint.ESCAPE_COOLDOWN_TURNS, restraint.RELEASE_GRACE_MINUTES), (3, 2, 0))
        self.assertEqual(restraint.CORROBORATION, {"lost_opposed_check": 0.35, "lost_fight": 0.40, "outnumbered_ambush": 0.30, "player_surrender": 0.40, "engine_event": 1.00, "model_op": 0.00})
        self.assertEqual((restraint.PROSE_SIGNAL_WEIGHT, restraint.CAPTURE_THRESHOLD, restraint.COMBAT_LOSS_HEALTH_RATIO), (0.4, 0.7, 0.25))
        self.assertEqual((restraint.MODEL_MAX_CELLS, restraint.TRANSFER_MAX_CELLS, restraint.ESCORT_CELL_BUDGET, restraint.LOG_KEEP), (12, 400, 12, 200))
        self.assertTrue(restraint.ESCORT_NO_ENCOUNTERS)
        for mode, allowed in restraint.ALLOWED_BY_MODE.items():
            if mode != "free":
                self.assertNotIn("travel", allowed)
            self.assertIn("talk", allowed)
            self.assertIn("wait", allowed)
        self.assertEqual(set(restraint.MOVE_KINDS), {"map_step", "story_walk", "town_walk", "town_leave", "travel_press", "location_move", "venue_enter", "venue_exit"})
        self.assertEqual(set(restraint.MOVE_REASONS), {"restrained", "custody", "confined", "escort_in_progress", "unknown_target"})
        self.assertEqual(set(restraint.JOURNAL_KINDS.values()), {"restrained", "released", "escort", "system"})
        for severity, _line, _blocks in restraint.STATUS_LINES.values():
            self.assertIn(severity, _SEVERITIES)


class StateTests(unittest.TestCase):
    def test_free_state_default_and_normalize(self):
        free = restraint.normalize_state(None)
        self.assertEqual(free["mode"], "free")
        self.assertEqual(free["conditions"], [])
        self.assertEqual(free["notes"], [])
        self.assertEqual(free["allowed"], list(restraint.ACTIONS))
        self.assertEqual(restraint.normalize_state("garbage")["mode"], "free")
        self.assertEqual(restraint.normalize_state({"mode": "levitating", "label": "x"})["mode"], "free")
        st = restraint.normalize_state(_bonds_state(escape={"skill": "athletics", "dc": 40}, bogus=1, conditions=[{"type": "time", "abs_minute": 5}, {"type": "moon"}]))
        self.assertEqual(st["escape"]["dc"], 22)
        self.assertNotIn("bogus", st)
        self.assertEqual(restraint.normalize_state(_bonds_state(escape={"skill": "athletics", "dc": 3}))["escape"]["dc"], 12)
        self.assertEqual([c["type"] for c in st["conditions"]], ["time"])
        self.assertEqual(set(st), set(restraint.FREE_STATE))
        self.assertEqual(restraint.FREE_STATE["mode"], "free")
        with self.assertRaises(ValueError):
            restraint.normalize_condition({"type": "moon", "phase": "full"})
        # A stored list can never shut conversation or waiting; travel is always dropped.
        emptied = restraint.normalize_state(_custody_state(allowed=[]))
        self.assertIn("talk", emptied["allowed"])
        self.assertIn("wait", emptied["allowed"])
        self.assertTrue(restraint.allowed_actions(emptied, "I talk to the guard.")["allowed"])
        trimmed = restraint.normalize_state(_confined_state(allowed=["rest", "travel"]))
        self.assertEqual(trimmed["allowed"], ["rest", "talk", "wait"])
        # The whole game-state dict is the wrong argument and must not pass as a free state.
        with self.assertRaises(TypeError):
            restraint.normalize_state({"player": {"name": "T"}, "restraint": _bonds_state()})
        with self.assertRaises(TypeError):
            restraint.allowed_actions({"player": {}, "restraint": _bonds_state()}, "I walk out of here.")
        self.assertEqual(restraint.prompt_block(None, WT), "")

    def test_place_and_target_converters_roundtrip(self):
        forms = (
            {"x": 3, "y": 4},
            {"x": 3, "y": 4, "city": "C7"},
            {"x": 3, "y": 4, "city": "C7", "location_code": "L4"},
            {"plot": "C7.1.0.12", "city": "C7", "x": 3, "y": 4},
            {"plot": "C7.1.0.12", "city": "C7", "x": 3, "y": 4, "location_code": "L9"},
        )
        for target in forms:
            place = restraint.place_from_target(target)
            self.assertEqual(set(place), {"location_id", "location_code", "plot", "city_id", "cell"})
            back = restraint.target_from_place(place)
            self.assertEqual(back, target, f"round trip changed {target}")
        self.assertIsNone(restraint.place_from_target(None))
        self.assertIsNone(restraint.place_from_target({}))
        self.assertIsNone(restraint.target_from_place(None))
        only_loc = restraint.target_from_place({"location_id": 9, "location_code": "L9"})
        self.assertEqual(only_loc, {"location_code": "L9", "location_id": 9})
        self.assertEqual(restraint.place_from_target({"x": 1, "y": 2}, location_id=4, location_code="l4")["location_code"], "L4")


class MoveTests(unittest.TestCase):
    def _targets(self):
        return {
            "map_step": {"x": 2, "y": 2}, "story_walk": None, "town_walk": {"cx": 3, "cy": 4, "plot": "C7.1.0.12"},
            "town_leave": None, "travel_press": None, "location_move": {"location_code": "L4"},
            "venue_enter": {"location_id": 9}, "venue_exit": None,
        }

    def test_may_move_free_allows_every_kind(self):
        for kind, target in self._targets().items():
            v = restraint.may_move_state(restraint.free_state(), kind, target)
            _assert_shape(self, v, _MOVE_VERDICT_TYPES)
            self.assertTrue(v["allowed"], kind)
            self.assertFalse(v["movement_locked"])
            self.assertEqual((v["reason"], v["label"], v["kind"]), ("", "", kind))

    def test_may_move_restrained_blocks_every_kind_with_409_shape(self):
        for kind, target in self._targets().items():
            v = restraint.may_move_state(_bonds_state(), kind, target)
            self.assertEqual(set(v), {"allowed", "reason", "message", "label", "kind", "movement_locked"})
            self.assertFalse(v["allowed"], kind)
            self.assertTrue(v["movement_locked"])
            self.assertEqual(v["reason"], "restrained")
            self.assertEqual(v["label"], "Bound at the wrists")
            self.assertLessEqual(len(v["message"]), 160)
            self.assertEqual(v["message"], restraint.MESSAGES["restrained"])

    def test_may_move_custody_and_escort_reason(self):
        v = restraint.may_move_state(_custody_state(), "map_step", {"x": 1, "y": 1})
        self.assertEqual(v["reason"], "custody")
        self.assertIn("Captain Ror", v["message"])
        escorted = _custody_state(escort={"to": {"x": 6, "y": 1, "plot": "", "city_id": "", "location_code": ""}, "legs_done": 0, "legs_total": 2, "plan_id": "esc"})
        v = restraint.may_move_state(escorted, "travel_press", None)
        self.assertEqual(v["reason"], "escort_in_progress")
        self.assertIn("escort_in_progress", restraint.MOVE_REASONS)

    def test_may_move_confined_scope_plot(self):
        st = _confined_state(scope="plot")
        self.assertTrue(restraint.may_move_state(st, "town_walk", {"cx": 3, "cy": 4, "plot": "C7.1.0.12"})["allowed"])
        other = restraint.may_move_state(st, "town_walk", {"cx": 3, "cy": 4, "plot": "C7.1.0.13"})
        self.assertFalse(other["allowed"])
        self.assertEqual(other["reason"], "confined")
        self.assertIn("the gaol cell", other["message"])
        self.assertFalse(restraint.may_move_state(st, "map_step", {"x": 3, "y": 4})["allowed"])
        self.assertFalse(restraint.may_move_state(st, "town_leave", None)["allowed"])

    def test_may_move_confined_scope_cell_and_location(self):
        cell = _confined_state(scope="cell")
        self.assertTrue(restraint.may_move_state(cell, "town_walk", {"cx": 3, "cy": 4})["allowed"])
        self.assertFalse(restraint.may_move_state(cell, "town_walk", {"cx": 4, "cy": 4})["allowed"])
        self.assertTrue(restraint.may_move_state(cell, "venue_enter", {"location_code": "L8", "cx": 3, "cy": 4})["allowed"])
        self.assertFalse(restraint.may_move_state(cell, "venue_enter", {"location_code": "L8"})["allowed"])
        loc = _confined_state(scope="location")
        self.assertTrue(restraint.may_move_state(loc, "venue_exit", None)["allowed"])
        self.assertTrue(restraint.may_move_state(loc, "location_move", {"location_id": 7})["allowed"])
        self.assertTrue(restraint.may_move_state(loc, "location_move", {"location_code": "L7"})["allowed"])
        self.assertFalse(restraint.may_move_state(loc, "location_move", {"location_id": 8})["allowed"])
        self.assertFalse(restraint.may_move_state(loc, "town_walk", {"cx": 3, "cy": 4})["allowed"])
        self.assertFalse(restraint.may_move_state(_confined_state(scope="person"), "venue_exit", None)["allowed"])

    def test_may_move_unknown_kind_raises_and_bad_target_refuses(self):
        with self.assertRaises(ValueError):
            restraint.may_move_state(restraint.free_state(), "fly", {"x": 1, "y": 1})
        for state in (restraint.free_state(), _confined_state(scope="cell")):
            v = restraint.may_move_state(state, "town_walk", {})
            self.assertFalse(v["allowed"])
            self.assertEqual(v["reason"], "unknown_target")
            self.assertEqual(v["message"], restraint.MESSAGES["unknown_target"])
        self.assertEqual(restraint.may_move_state(restraint.free_state(), "map_step", {"x": "a", "y": 1})["reason"], "unknown_target")
        self.assertEqual(restraint.may_move_state(restraint.free_state(), "location_move", {"location_id": 0})["reason"], "unknown_target")
        self.assertEqual(restraint.may_move_state(restraint.free_state(), "map_step", None)["reason"], "unknown_target")

    def test_allowed_actions_by_mode(self):
        for state in (restraint.free_state(), _bonds_state(), _custody_state(), _confined_state()):
            a = restraint.allowed_actions(state, "I talk to the guard.")
            self.assertEqual(set(a), {"allowed", "action", "reason", "message", "escape"})
            self.assertTrue(a["allowed"], state["mode"])
            self.assertEqual(a["action"], "talk")
        train = "I train my footwork in the corner."
        self.assertFalse(restraint.allowed_actions(_bonds_state(), train)["allowed"])
        self.assertFalse(restraint.allowed_actions(_custody_state(), train)["allowed"])
        self.assertTrue(restraint.allowed_actions(_confined_state(), train)["allowed"])
        self.assertEqual(restraint.allowed_actions(_confined_state(), train)["action"], "train")
        for state in (_bonds_state(), _custody_state(), _confined_state()):
            a = restraint.allowed_actions(state, "I walk out of here.")
            self.assertFalse(a["allowed"], state["mode"])
            self.assertEqual(a["action"], "travel")
            self.assertEqual(a["reason"], state["mode"])
            self.assertIn("go anywhere", a["message"])
        self.assertTrue(restraint.allowed_actions(restraint.free_state(), "I walk out of here.")["allowed"])
        a = restraint.allowed_actions(_confined_state(), "I pick the lock with a bent nail.")
        self.assertEqual(a["action"], "escape_attempt")
        self.assertTrue(a["escape"])
        self.assertTrue(a["allowed"])

    def test_wait_allowed_always(self):
        self.assertEqual(restraint.wait_allowed(_bonds_state(), 360), {"allowed": True, "minutes": 360})
        self.assertEqual(restraint.wait_allowed(restraint.free_state(), "90"), {"allowed": True, "minutes": 90})


class ClassifyTests(unittest.TestCase):
    def _assert_verdict(self, v):
        self.assertEqual(set(v), {"verdict", "kind", "confidence", "evidence", "captor", "place_hint", "sentence"})
        self.assertIn(v["verdict"], ("capture", "flavour", "none"))
        self.assertIn(v["kind"], ("bonds", "custody", "cell", ""))
        self.assertIsInstance(v["confidence"], float)
        for row in v["evidence"]:
            _assert_shape(self, row, _EVIDENCE_TYPES)
            self.assertIn(row["severity"], _EVIDENCE_SEVERITIES)
            self.assertIn(row["check"], restraint.EVIDENCE_CHECKS)
            self.assertLessEqual(len(row["evidence"]), 240)
        if v["captor"] is not None:
            _assert_shape(self, v["captor"], _ENTITY_REF_TYPES, extra_ok=("power_rank",))
            self.assertTrue(v["captor"]["name"])

    def test_classify_prose_only_is_flavour(self):
        v = restraint.classify_capture(narration="The guards shackle your wrists.")
        self._assert_verdict(v)
        self.assertEqual(v["verdict"], "flavour")
        self.assertEqual(v["confidence"], 0.4)
        self.assertEqual([r["check"] for r in v["evidence"]], ["capture_prose"])
        self.assertEqual(v["kind"], "bonds")
        self.assertIn("shackle", v["sentence"])

    def test_classify_flavour_phrases_are_not_signals(self):
        v = restraint.classify_capture(narration="He grabs your arm and blocks your way.")
        self._assert_verdict(v)
        self.assertEqual(v["verdict"], "flavour")
        self.assertEqual(v["confidence"], 0.0)
        self.assertEqual([r["check"] for r in v["evidence"]], ["flavour_prose"])
        self.assertTrue(v["evidence"][0]["ok"])

    def test_classify_negated_sentence_does_not_count(self):
        v = restraint.classify_capture(narration="If you resist they would chain you.")
        self.assertEqual(v["verdict"], "none")
        self.assertEqual(v["evidence"], [])
        self.assertEqual(v["kind"], "")
        self.assertTrue(restraint._negated("They could not hold you."))
        self.assertTrue(restraint._negated("You twist free before they bind you."))

    def test_classify_negation_matches_whole_words_only(self):
        check = {"outcome": "failure", "skill": {"code": "melee"}, "opposition": {"name": "Guard", "code": "C"}}
        for text in (
            "They bind your wrists with a tight knot and haul you to the wagon.",
            "The guards seize you and march you off; you cannot break their grip.",
            "Almighty blows rain down and they chain your hands.",
        ):
            self.assertFalse(restraint._negated(text), text)
            v = restraint.classify_capture(narration=text, checks=[check])
            self.assertEqual(v["verdict"], "capture", text)
            self.assertEqual(v["confidence"], 0.75, text)

    def test_classify_quoted_speech_ignored(self):
        v = restraint.classify_capture(narration='"We\'ll chain you up," he laughs.')
        self.assertEqual(v["verdict"], "none")
        self.assertEqual(restraint.strip_quotes('"We\'ll chain you up," he laughs.').strip(), "he laughs.")
        self.assertEqual(restraint.strip_quotes("“Bind him,” she says.").strip(), "she says.")

    def test_classify_capture_with_lost_opposed_check(self):
        check = {"outcome": "failure", "skill": {"code": "pursuit", "name": "Pursuit"}, "opposition": {"name": "Captain Ror", "code": "B", "power_total": 14}, "margin": -4}
        v = restraint.classify_capture(narration="They run you down and march you off to the gaol.", checks=[check])
        self._assert_verdict(v)
        self.assertEqual(v["verdict"], "capture")
        self.assertEqual(v["confidence"], 0.75)
        self.assertEqual(v["captor"]["name"], "Captain Ror")
        self.assertEqual(v["captor"]["code"], "B")
        self.assertEqual(v["kind"], "custody")
        self.assertEqual(v["place_hint"], "gaol")
        # A lost check with no opposition, or on an unrelated skill, does not corroborate.
        flat = restraint.classify_capture(narration="They march you off to the gaol.", checks=[{"outcome": "failure", "skill": {"code": "cooking"}, "opposition": {"name": "x"}}])
        self.assertEqual(flat["verdict"], "flavour")
        alone = restraint.classify_capture(narration="You chat about the weather.", checks=[check])
        self.assertEqual(alone["verdict"], "none")

    def test_classify_capture_with_lost_fight_ratio(self):
        combat = {"resolution": {"outcome": "resolved"}, "player_health_after": 3, "player_max_health": 20, "target": {"code": "D", "name": "Brute"}}
        v = restraint.classify_capture(narration="The brute drags you off into the dark.", combat=combat)
        self.assertEqual(v["verdict"], "capture")
        self.assertEqual(v["confidence"], 0.8)
        self.assertEqual(v["captor"]["name"], "Brute")
        healthy = dict(combat, player_health_after=15)
        self.assertEqual(restraint.classify_capture(narration="The brute drags you off into the dark.", combat=healthy)["verdict"], "flavour")
        worded = {"resolution": {"outcome": "overpowered"}}
        self.assertEqual(restraint.classify_capture(narration="The brute drags you off into the dark.", combat=worded)["verdict"], "capture")

    def test_classify_capture_outnumbered_ambush(self):
        text = "The bandits seize you and march you away from the road."
        enc = {"hostile_default": True, "surprise": "surprised", "count": 3, "npc_name": "Bandit leader"}
        v = restraint.classify_capture(narration=text, encounter=enc)
        self.assertEqual(v["verdict"], "capture")
        self.assertEqual(v["confidence"], 0.7)
        self.assertEqual(v["captor"]["name"], "Bandit leader")
        self.assertEqual(restraint.classify_capture(narration=text, encounter=dict(enc, count=1))["verdict"], "flavour")
        self.assertEqual(restraint.classify_capture(narration=text, encounter=dict(enc, surprise="forewarned"))["verdict"], "flavour")

    def test_classify_player_surrender_corroborates(self):
        v = restraint.classify_capture(narration="The watch takes you away in irons.", player_input="I surrender, take me.")
        self.assertEqual(v["verdict"], "capture")
        self.assertEqual(v["confidence"], 0.8)
        self.assertIn("player_surrender", [r["check"] for r in v["evidence"]])
        self.assertEqual(restraint.classify_capture(narration="You chat.", player_input="I surrender.")["verdict"], "none")

    def test_classify_engine_event_alone_is_capture(self):
        event = {"id": 3, "kind": "custom", "summary": "The warden has you taken below.", "trigger": "restraint:test", "status": "active",
                 "payload": {"restrain": {"kind": "cell", "by": {"code": "A", "name": "Warden", "power_rank": 45}}}}
        v = restraint.classify_capture(narration="", event=event)
        self._assert_verdict(v)
        self.assertEqual(v["verdict"], "capture")
        self.assertEqual(v["confidence"], 1.0)
        self.assertEqual(v["kind"], "cell")
        self.assertEqual(v["captor"]["name"], "Warden")
        self.assertEqual(v["captor"]["power_rank"], 45)
        self.assertEqual(v["evidence"][0]["severity"], "block")

    def test_classify_model_op_is_signal_not_corroboration(self):
        ops = [{"op": "RESTRAIN", "args": ["bonds", "Bound tight"], "flags": {}, "line": 1, "raw": 'RESTRAIN bonds "Bound tight"'}]
        v = restraint.classify_capture(narration="You chat about the weather.", ops=ops)
        self.assertEqual(v["verdict"], "flavour")
        self.assertEqual(v["confidence"], 0.4)
        self.assertEqual([r["check"] for r in v["evidence"]], ["model_op"])
        self.assertEqual(v["kind"], "bonds")
        check = {"outcome": "critical_failure", "skill": {"code": "melee"}, "opposition": {"name": "Guard", "code": "C"}}
        v2 = restraint.classify_capture(narration="You chat about the weather.", ops=ops, checks=[check])
        self.assertEqual(v2["verdict"], "capture")
        self.assertEqual(v2["confidence"], 0.75)
        # With prose already counted the op adds no second vote.
        v3 = restraint.classify_capture(narration="The guards shackle your wrists.", ops=ops)
        self.assertEqual(v3["confidence"], 0.4)
        self.assertEqual([r["weight"] for r in v3["evidence"] if r["check"] == "model_op"], [0.0])

    def test_propose_capture_defaults_and_severity(self):
        bonds = restraint.classify_capture(narration="The guards shackle your wrists.", player_input="I give up.")
        self.assertEqual(bonds["verdict"], "capture")
        st = restraint.propose_capture(bonds, world_time=WT, turn=4, location=None)
        self.assertEqual(st["mode"], "restrained")
        self.assertEqual(st["conditions"], [{"type": "time", "abs_minute": 300 + 120}])
        self.assertEqual((st["escape"]["skill"], st["escape"]["dc"], st["escape"]["cooldown_turns"], st["escape"]["fail_penalty_minutes"]), ("athletics", 14, 1, 30))
        self.assertEqual(st["allowed"], list(restraint.ALLOWED_BY_MODE["restrained"]))
        self.assertEqual(st["reason"], "capture:surrender")
        self.assertIsNone(st["place"])
        self.assertEqual(set(st), set(restraint.FREE_STATE))
        event = {"payload": {"restrain": {"kind": "cell", "by": {"code": "A", "name": "Warden", "power_rank": 45}}}, "summary": "taken below"}
        cell = restraint.classify_capture(narration="", event=event)
        harsh = restraint.propose_capture(cell, world_time=WT, turn=4, location={"id": 7, "code": "L7", "name": "the gaol cell", "plot": "C7.1.0.12", "city_id": "C7"}, severity="harsh", faction="town watch")
        self.assertEqual(harsh["mode"], "confined")
        self.assertEqual(harsh["conditions"][0], {"type": "time", "abs_minute": 300 + 4320})
        self.assertEqual(harsh["escape"]["dc"], 20)
        self.assertEqual(harsh["place"]["location_id"], 7)
        self.assertEqual(harsh["label"], "Held in the gaol cell")
        self.assertEqual(harsh["by"]["name"], "Warden")
        self.assertNotIn("power_rank", harsh["by"])
        self.assertIsNone(restraint.propose_capture(cell, world_time=WT, turn=4, location=None, allow_escape=False)["escape"])
        fined = restraint.propose_capture(cell, world_time=WT, turn=4, location=None, fine_units=400, currency_set="coin_medieval")
        self.assertIn({"type": "payment", "units": 400, "currency_set": "coin_medieval"}, fined["conditions"])
        light = restraint.propose_capture(cell, world_time=WT, turn=4, location=None, severity="light")
        self.assertEqual(light["conditions"][0]["abs_minute"], 300 + 720)
        custody = restraint.propose_capture(dict(cell, kind="custody"), world_time=WT, turn=4, location=None)
        self.assertEqual(custody["conditions"], [])
        self.assertEqual(custody["label"], "In their custody")
        # A fine of nothing adds no payment condition (0 units would be met on the first tick).
        unfined = restraint.propose_capture(cell, world_time=WT, turn=4, location=None, fine_units=0, currency_set="coin_medieval")
        self.assertEqual([c["type"] for c in unfined["conditions"]], ["time"])
        # A named captor with no power_rank counts as rank 10 (the npcs default): the lowest row, shift -2.
        unranked = restraint.classify_capture(narration="They run you down and march you off.", checks=[{"outcome": "failure", "skill": {"code": "pursuit"}, "opposition": {"name": "Sheriff", "code": "B"}}])
        self.assertEqual(unranked["verdict"], "capture")
        self.assertNotIn("power_rank", unranked["captor"])
        self.assertEqual(restraint.propose_capture(unranked, world_time=WT, turn=4, location=None)["escape"]["dc"], 14)
        self.assertEqual(restraint.propose_capture(dict(unranked, kind="bonds"), world_time=WT, turn=4, location=None)["escape"]["dc"], 12)
        ranked = dict(unranked, captor=dict(unranked["captor"], power_rank=10))
        self.assertEqual(restraint.propose_capture(ranked, world_time=WT, turn=4, location=None)["escape"]["dc"], 14)
        self.assertEqual(restraint.propose_capture(dict(ranked, kind="bonds"), world_time=WT, turn=4, location=None)["escape"]["dc"], 12)
        with self.assertRaises(ValueError):
            restraint.propose_capture(cell, world_time=WT, turn=4, location=None, extra_conditions=[{"type": "moon", "phase": "full"}])
        with self.assertRaises(ValueError):
            restraint.propose_capture(restraint.classify_capture(narration="The guards shackle your wrists."), world_time=WT, turn=4, location=None)


class PlanTests(unittest.TestCase):
    def test_plan_position_trust_rules(self):
        board = _board(40, 40)
        far = {"x": 21, "y": 1}
        too_far = restraint.plan_position(_custody_state(), far, actor="A", trust="model", chart=board, current_location_id=1, current_town=None, locations=_LOCATIONS)
        self.assertFalse(too_far["ok"])
        self.assertEqual(too_far["reason"], "too_far")
        self.assertEqual(too_far["distance_cells"], 20)
        near = restraint.plan_position(_custody_state(), {"x": 9, "y": 1}, actor="A", trust="model", chart=board, current_location_id=1, current_town=None, locations=_LOCATIONS)
        self.assertTrue(near["ok"])
        engine = restraint.plan_position(_custody_state(), far, actor="engine", trust="engine", chart=board, current_location_id=1, current_town=None, locations=_LOCATIONS)
        self.assertTrue(engine["ok"])
        big = _board(600, 2)
        ok_event = restraint.plan_position(_custody_state(), {"x": 301, "y": 1}, actor="event", trust="event", chart=big, current_location_id=1, current_town=None, locations=_LOCATIONS)
        self.assertTrue(ok_event["ok"])
        self.assertEqual(ok_event["distance_cells"], 300)
        far_event = restraint.plan_position(_custody_state(), {"x": 501, "y": 1}, actor="event", trust="event", chart=big, current_location_id=1, current_town=None, locations=_LOCATIONS)
        self.assertEqual(far_event["reason"], "too_far")
        with self.assertRaises(ValueError):
            restraint.plan_position(_custody_state(), far, actor="x", trust="wizard", chart=board, current_location_id=1, current_town=None, locations=_LOCATIONS)
        # The model may always put the player at the captor's own place.
        own = _confined_state(place={"location_id": 5, "location_code": "L4", "plot": "", "city_id": "", "cell": [30, 30]})
        at_captor = restraint.plan_position(own, {"x": 30, "y": 30, "location_code": "L4"}, actor="A", trust="model", chart=board, current_location_id=1, current_town=None, locations=_LOCATIONS)
        self.assertTrue(at_captor["ok"])
        unknown = restraint.plan_position(_custody_state(), {}, actor="engine", trust="engine", chart=board, current_location_id=1, current_town=None, locations=_LOCATIONS)
        self.assertEqual(unknown["reason"], "unknown_target")

    def test_plan_position_layers_from_fixtures(self):
        board = _board()
        plan = restraint.plan_position(_custody_state(), {"x": 6, "y": 6, "location_code": "L4"}, actor="engine", trust="engine", chart=board, current_location_id=2, current_town=None, locations=_LOCATIONS)
        self.assertTrue(plan["ok"])
        self.assertEqual(set(plan), {"ok", "reason", "actor", "trust", "target", "as_target", "layers", "calls", "journal", "distance_cells"})
        self.assertEqual(plan["layers"]["location"], {"from_id": 2, "to_id": 5})
        self.assertEqual(plan["layers"]["token"], {"map_id": "board-test", "from": [1, 1], "to": [6, 6]})
        self.assertEqual(plan["layers"]["town"], {"action": "keep", "came_from": None})
        self.assertEqual(plan["distance_cells"], 5)
        self.assertEqual(plan["as_target"], {"x": 6, "y": 6, "location_code": "L4"})
        self.assertEqual(plan["target"]["location_id"], 5)
        _assert_journal(self, plan["journal"])
        self.assertIn("Old Mill", plan["journal"][0]["content"])
        self.assertEqual(len(plan["calls"]), 2)
        world = _world_chart()
        enter = restraint.plan_position(_custody_state(), {"x": 50, "y": 50, "city": "C7"}, actor="engine", trust="escort", chart=world, current_location_id=2, current_town=None, locations=_LOCATIONS)
        self.assertTrue(enter["ok"])
        self.assertEqual(enter["layers"]["town"], {"action": "enter", "came_from": [40, 40]})
        self.assertIsNone(enter["layers"]["location"])
        self.assertEqual(enter["layers"]["token"]["to"], [50, 50])
        self.assertNotIn("cell_index", world, "plan_position must not cache into the caller's chart")
        clear = restraint.plan_position(_custody_state(), {"x": 45, "y": 45}, actor="engine", trust="engine", chart=world, current_location_id=2, current_town={"city_id": "C7", "cx": 50, "cy": 50}, locations=_LOCATIONS)
        self.assertEqual(clear["layers"]["town"]["action"], "clear")
        no_map = restraint.plan_position(_custody_state(), {"x": 45, "y": 45}, actor="engine", trust="engine", chart=None, current_location_id=2, current_town=None, locations=_LOCATIONS)
        self.assertEqual(no_map["reason"], "no_map")
        same = restraint.plan_position(_custody_state(), {"x": 1, "y": 1, "location_code": "L4"}, actor="engine", trust="engine", chart=board, current_location_id=5, current_town=None, locations=_LOCATIONS)
        self.assertTrue(same["ok"])
        self.assertEqual(same["layers"], {"location": None, "token": None, "town": {"action": "keep", "came_from": None}})

    def test_plan_escort_on_board_map(self):
        plan = restraint.plan_escort(_board(), start=(1, 1), dest={"x": 6, "y": 1})
        self.assertEqual(set(plan), {"ok", "stopped", "from", "to", "legs", "minutes_total", "cells", "plan_id"})
        self.assertTrue(plan["ok"])
        self.assertEqual(plan["stopped"], "arrived")
        self.assertEqual(len(plan["legs"]), 1)
        leg = plan["legs"][0]
        self.assertEqual(leg["kind"], "world")
        self.assertEqual(len(leg["path"]) - 1, 5)
        self.assertEqual(leg["path"][0], [1, 1])
        self.assertEqual(leg["path"][-1], [6, 1])
        self.assertEqual(leg["minutes"], 5 * 12)
        self.assertEqual(plan["minutes_total"], 60)
        self.assertEqual(plan["cells"], 5)
        self.assertEqual(leg["terrains"], ["plains"] * 5)
        self.assertEqual(plan["plan_id"], "esc-1,1-6,1-12")
        wide = restraint.plan_escort(_board(30, 12), start=(1, 1), dest={"x": 20, "y": 1}, budget=12)
        self.assertEqual(wide["stopped"], "budget")
        self.assertTrue(wide["ok"])
        self.assertEqual(wide["cells"], 12)
        from app.tile_world import _cell_at, tile_walkable

        water = _board(water_x=4)
        blocked = restraint.plan_escort(water, start=(1, 1), dest={"x": 6, "y": 1})
        self.assertIn(blocked["stopped"], {"arrived", "blocked"})
        for leg in blocked["legs"]:
            for x, y in leg["path"]:
                self.assertTrue(tile_walkable(_cell_at(water, x, y)), f"path entered water at {x},{y}")
        if blocked["stopped"] == "blocked":
            self.assertFalse(blocked["ok"])
        self.assertEqual(water["player"], {"x": 1, "y": 1}, "plan_escort must not move the chart's player")
        self.assertEqual(restraint.plan_escort(None, start=(1, 1), dest={"x": 6, "y": 1})["stopped"], "no_map")
        same = restraint.plan_escort(_board(), start=(1, 1), dest={"x": 1, "y": 1})
        self.assertEqual(same["stopped"], "same_cell")
        self.assertEqual(same["legs"], [])
        with self.assertRaises(ValueError):
            restraint.plan_escort(_board(), start=(1, 1), dest={"plot": "C7.1.0.1"})

    def test_plan_escort_adds_deferred_town_legs(self):
        plan = restraint.plan_escort(_board(), start=(1, 1), dest={"x": 6, "y": 1, "plot": "C9.0.0.3", "city": "C9"}, town_position={"city_id": "C7", "cx": 1, "cy": 1})
        self.assertEqual([leg["kind"] for leg in plan["legs"]], ["leave", "world", "town"])
        self.assertEqual(plan["legs"][0], {"kind": "leave", "target": [6, 1], "deferred": True, "via": "town_moves.walk_out"})
        last = plan["legs"][-1]
        self.assertTrue(last["deferred"])
        self.assertEqual(last["via"], "turn_prompts.walk_in_town")
        self.assertEqual(last["rule"], "town_led")
        self.assertEqual(last["target"], {"plot": "C9.0.0.3", "city_id": "C9", "cx": 6, "cy": 1})
        inside = restraint.plan_escort(_board(), start=(1, 1), dest={"x": 1, "y": 1, "plot": "C7.0.0.3", "city": "C7"}, town_position={"city_id": "C7", "cx": 1, "cy": 1})
        self.assertEqual([leg["kind"] for leg in inside["legs"]], ["town"])

    def test_escort_travel_dict_shape(self):
        plan = restraint.plan_escort(_board(), start=(1, 1), dest={"x": 6, "y": 1})
        travel = restraint.escort_travel_dict(plan["legs"][0])
        self.assertEqual(set(travel), {"minutes", "terrain", "from", "to", "steps", "encounter", "escort", "on_road"})
        self.assertEqual(travel["encounter"], {"happened": False})
        self.assertTrue(travel["escort"])
        self.assertEqual((travel["minutes"], travel["terrain"], travel["from"], travel["to"], travel["steps"], travel["on_road"]), (60, "plains", [1, 1], [6, 1], 5, False))
        road = restraint.escort_travel_dict({"kind": "world", "path": [[0, 0], [1, 0]], "terrains": ["road"], "minutes": 8})
        self.assertTrue(road["on_road"])
        deferred = restraint.escort_travel_dict({"kind": "leave", "target": [6, 1], "deferred": True, "via": "town_moves.walk_out"})
        self.assertEqual((deferred["minutes"], deferred["steps"], deferred["to"]), (0, 0, [6, 1]))
        with self.assertRaises(ValueError):
            restraint.escort_travel_dict("leg")


class ProseTests(unittest.TestCase):
    def test_status_lines_and_prompt_block(self):
        self.assertEqual(restraint.status_lines(restraint.free_state(), WT), [])
        self.assertEqual(restraint.prompt_block(restraint.free_state(), WT), "")
        st = _confined_state(conditions=[{"type": "time", "abs_minute": 300 + 180}, {"type": "payment", "units": 400, "currency_set": "coin_medieval"}])
        lines = restraint.status_lines(st, WT)
        for row in lines:
            _assert_shape(self, row, _STATUS_LINE_TYPES)
            self.assertIn(row["severity"], _SEVERITIES)
            self.assertLessEqual(len(row["line"]), 160)
            self.assertNotIn("[[", row["line"])
        self.assertEqual([row["key"] for row in lines], ["restraint", "time_left", "payment"])
        self.assertEqual([row["severity"] for row in lines], ["serious", "info", "info"])
        self.assertIn("travel", lines[0]["blocks"])
        self.assertIn("the gaol cell", lines[0]["line"])
        self.assertIn("by Captain Ror", lines[0]["line"])
        self.assertIn("3 hours", lines[1]["line"])
        self.assertIn("4 silver", lines[2]["line"])
        block = restraint.prompt_block(st, WT)
        self.assertTrue(block.startswith("Player restraint (server truth):\n- "))
        self.assertEqual(block.count("\n- "), 3)
        bound = restraint.status_lines(_bonds_state(), WT)
        self.assertEqual(bound[0]["severity"], "critical")
        self.assertEqual(bound[0]["blocks"], ["travel", "inventory", "train"])
        one_hour = restraint.status_lines(_bonds_state(conditions=[{"type": "time", "abs_minute": 300 + 60}]), WT)
        self.assertIn("About 1 hour before", one_hour[1]["line"])
        escorted = _custody_state(escort={"to": {"x": 6, "y": 1, "plot": "", "city_id": "", "location_code": "L4"}, "legs_done": 1, "legs_total": 3, "plan_id": "esc"})
        keys = [row["key"] for row in restraint.status_lines(escorted, WT)]
        self.assertEqual(keys, ["restraint", "escort"])
        self.assertIn("2 more stretches", restraint.status_lines(escorted, WT)[1]["line"])
        self.assertEqual(len(restraint.status_lines(st, None)), 2, "no clock, no time_left line")

    def test_parse_restraint_op_grammar(self):
        entry = {"op": "RESTRAIN", "args": ["bonds", "Bound at the wrists", "BY", "A", "AT", "L4", "FOR", "120", "UNTIL", "skill:lockpicking:3"], "flags": {}, "line": 1, "raw": "RESTRAIN ..."}
        out = restraint.parse_restraint_op(entry)
        self.assertEqual(set(out), {"ok", "op", "proposal", "error"})
        self.assertTrue(out["ok"], out["error"])
        self.assertEqual(out["proposal"], {"kind": "bonds", "label": "Bound at the wrists", "by_code": "A", "place_ref": "L4", "minutes": 120,
                                           "conditions": [{"type": "skill", "name": "lockpicking", "level": 3}]})
        flagged = restraint.parse_restraint_op({"op": "RESTRAIN", "args": ["cell", "Held below"], "flags": {"BY": "B", "FOR": "60", "UNTIL": "pay:400"}, "line": 1, "raw": ""})
        self.assertTrue(flagged["ok"])
        self.assertEqual(flagged["proposal"]["conditions"], [{"type": "payment", "units": 400, "currency_set": ""}])
        self.assertEqual(flagged["proposal"]["minutes"], 60)
        self.assertFalse(restraint.parse_restraint_op({"op": "RESTRAIN", "args": ["bonds"], "flags": {}})["ok"])
        self.assertIn("label", restraint.parse_restraint_op({"op": "RESTRAIN", "args": ["bonds"], "flags": {}})["error"])
        self.assertFalse(restraint.parse_restraint_op({"op": "RESTRAIN", "args": ["bonds", "Tied"], "flags": {"FOR": "abc"}})["ok"])
        self.assertFalse(restraint.parse_restraint_op({"op": "RESTRAIN", "args": ["bonds", "Tied"], "flags": {"UNTIL": "moon:full"}})["ok"])
        self.assertFalse(restraint.parse_restraint_op({"op": "RESTRAIN", "args": ["net", "Caught"], "flags": {}})["ok"])
        for until, cond in (("quest:Q3:completed", {"type": "quest_status", "code": "Q3", "status": "completed"}),
                            ("stage:gaol_break", {"type": "quest_stage", "stage_id": "gaol_break"}),
                            ("event:festival", {"type": "event", "kind": "festival", "trigger": ""})):
            parsed = restraint.parse_restraint_op({"op": "RESTRAIN", "args": ["cell", "Held"], "flags": {"UNTIL": until}})
            self.assertEqual(parsed["proposal"]["conditions"], [cond], until)
        release = restraint.parse_restraint_op({"op": "RELEASE", "args": ["the captain relents"], "flags": {"BY": "A"}, "line": 2, "raw": ""})
        self.assertTrue(release["ok"])
        self.assertEqual((release["proposal"]["kind"], release["proposal"]["label"], release["proposal"]["by_code"]), ("release", "the captain relents", "A"))
        escort = restraint.parse_restraint_op({"op": "ESCORT", "args": ["TO", "L7", "BY", "A"], "flags": {}, "line": 3, "raw": ""})
        self.assertTrue(escort["ok"])
        self.assertEqual((escort["proposal"]["kind"], escort["proposal"]["place_ref"], escort["proposal"]["by_code"]), ("escort", "L7", "A"))
        self.assertFalse(restraint.parse_restraint_op({"op": "ESCORT", "args": [], "flags": {}})["ok"])
        self.assertFalse(restraint.parse_restraint_op({"op": "MOVE", "args": ["L7"], "flags": {}})["ok"])
        self.assertFalse(restraint.parse_restraint_op("RESTRAIN")["ok"])
        from app.turn_dsl import OPCODES

        for op in restraint.RESTRAINT_OPS:
            self.assertNotIn(op, OPCODES, "the ops stay unregistered in this pass")


class RestraintDbTests(unittest.TestCase):
    def setUp(self):
        os.environ.update(_ENV)
        path = db_path()
        if path.exists():
            path.unlink()
        init_db()
        self.conn = connect()
        with self.conn:
            restraint.ensure_schema(self.conn)
            if not self.conn.execute("SELECT id FROM player WHERE id = 1").fetchone():
                self.conn.execute(
                    "INSERT INTO player (id, name, health, max_health, level, xp, gold, current_location_id) VALUES (1, 'T', 20, 20, 1, 0, 12, NULL)"
                )

    def tearDown(self):
        self.conn.close()

    def _rows(self, sql, params=()):
        return self.conn.execute(sql, params).fetchall()

    def _log_events(self):
        return [r["event"] for r in self._rows("SELECT event FROM restraint_log ORDER BY id")]

    def _snapshot(self):
        tables = [r[0] for r in self._rows("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
        counts = {t: self._rows(f'SELECT COUNT(*) FROM "{t}"')[0][0] for t in tables if t != "restraint_log"}
        settings = {r["key"]: r["value"] for r in self._rows("SELECT key, value FROM settings WHERE key != ?", (restraint.STATE_KEY,))}
        player = tuple(self._rows("SELECT * FROM player WHERE id = 1")[0])
        return counts, settings, player

    def test_ensure_schema_idempotent_and_table_shape(self):
        with self.conn:
            restraint.ensure_schema(self.conn)
            restraint.ensure_schema(self.conn)
        cols = [(r["name"], r["type"]) for r in self._rows("PRAGMA table_info(restraint_log)")]
        self.assertEqual(cols, [
            ("id", "INTEGER"), ("turn", "INTEGER"), ("abs_minute", "INTEGER"), ("event", "TEXT"), ("mode", "TEXT"), ("reason", "TEXT"),
            ("actor_code", "TEXT"), ("from_location_id", "INTEGER"), ("to_location_id", "INTEGER"), ("detail", "TEXT"), ("created_at", "TEXT"),
        ])
        self.assertEqual([r["name"] for r in self._rows("PRAGMA index_list(restraint_log)") if r["name"].startswith("idx_")], ["idx_restraint_log_turn"])
        with self.conn:
            restraint.capture(self.conn, _bonds_state(), turn=1, world_time=WT)
        self.assertEqual(self._rows("SELECT seq FROM sqlite_sequence WHERE name = 'restraint_log'")[0][0], 1)
        from app import world

        self.assertNotIn("restraint_log", world.WORLD_TABLES)
        self.assertNotIn("restraint", world.SNAPSHOT_SETTING_KEYS)

    def test_save_state_roundtrip_and_delete_on_free(self):
        with self.conn:
            restraint.save_state(self.conn, _custody_state())
        loaded = restraint.load_state(self.conn)
        self.assertEqual(loaded, restraint.normalize_state(_custody_state()))
        self.assertEqual(loaded["mode"], "custody")
        self.assertEqual(restraint.state_view(self.conn), {"restraint": loaded})
        self.assertTrue(restraint.is_locked(self.conn))
        with self.conn:
            restraint.save_state(self.conn, restraint.FREE_STATE)
        self.assertEqual(self._rows("SELECT key FROM settings WHERE key = 'restraint'"), [])
        self.assertEqual(restraint.state_view(self.conn), {"restraint": None})
        self.assertFalse(restraint.is_locked(self.conn))
        with self.conn:
            self.conn.execute("INSERT INTO settings (key, value) VALUES ('restraint', '{not json')")
        self.assertEqual(restraint.load_state(self.conn)["mode"], "free")
        self.assertEqual(restraint.may_move(self.conn, "map_step", {"x": 1, "y": 1})["allowed"], True)

    def test_capture_writes_row_and_log_and_journal(self):
        proposal = _bonds_state()
        with self.conn:
            report = restraint.capture(self.conn, proposal, turn=4, world_time=WT)
        self.assertEqual(set(report), {"ok", "state", "journal", "log_id", "replaced_previous"})
        self.assertTrue(report["ok"])
        self.assertFalse(report["replaced_previous"])
        self.assertEqual(restraint.load_state(self.conn), restraint.normalize_state(dict(proposal, set_turn=4)))
        rows = self._rows("SELECT * FROM restraint_log")
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["event"], rows[0]["mode"], rows[0]["turn"], rows[0]["abs_minute"], rows[0]["actor_code"]), ("captured", "restrained", 4, 300, "A"))
        self.assertEqual(json.loads(rows[0]["detail"])["state"]["label"], "Bound at the wrists")
        _assert_journal(self, report["journal"])
        self.assertEqual(report["journal"][0]["kind"], "restrained")
        self.assertIn("Bound at the wrists", report["journal"][0]["content"])
        self.assertIn("Captain Ror", report["journal"][0]["content"])
        self.assertFalse(restraint.may_move(self.conn, "map_step", {"x": 2, "y": 2})["allowed"])
        with self.conn:
            second = restraint.capture(self.conn, _confined_state(), turn=5, world_time=WT)
        self.assertTrue(second["replaced_previous"])
        self.assertEqual(self._log_events(), ["captured", "transferred"])
        self.assertEqual(restraint.load_state(self.conn)["mode"], "confined")
        with self.assertRaises(ValueError):
            restraint.capture(self.conn, restraint.FREE_STATE, turn=6, world_time=WT)
        self.assertEqual(self._rows("SELECT COUNT(*) FROM journal")[0][0], 0, "journal notes are proposals; nothing is inserted")

    def test_tick_releases_on_time_only_at_or_after(self):
        with self.conn:
            restraint.capture(self.conn, _bonds_state(), turn=4, world_time=WT)
            early = restraint.tick(self.conn, world_time=WT_599, turn=5)
        self.assertEqual(set(early), {"changed", "released", "state", "met", "next_check_abs_minute", "journal", "log_event"})
        self.assertFalse(early["changed"])
        self.assertFalse(early["released"])
        self.assertEqual(early["next_check_abs_minute"], 600)
        self.assertEqual(early["state"]["mode"], "restrained")
        self.assertEqual(self._log_events(), ["captured"])
        with self.conn:
            done = restraint.tick(self.conn, world_time=WT_600, turn=6)
        self.assertTrue(done["changed"])
        self.assertTrue(done["released"])
        self.assertEqual(done["met"], [{"type": "time", "abs_minute": 600}])
        self.assertEqual(done["state"]["mode"], "free")
        self.assertEqual(done["log_event"], "tick_release")
        self.assertIsNone(done["next_check_abs_minute"])
        _assert_journal(self, done["journal"])
        self.assertEqual(done["journal"][0]["kind"], "released")
        self.assertEqual(self._rows("SELECT key FROM settings WHERE key = 'restraint'"), [])
        rows = self._rows("SELECT * FROM restraint_log ORDER BY id")
        self.assertEqual([r["event"] for r in rows], ["captured", "tick_release"])
        self.assertEqual((rows[1]["turn"], rows[1]["abs_minute"], rows[1]["reason"]), (6, 600, "release:time"))
        with self.conn:
            again = restraint.tick(self.conn, world_time=WT_600, turn=7)
        self.assertFalse(again["changed"])
        self.assertEqual(len(self._rows("SELECT id FROM restraint_log")), 2)

    def test_tick_releases_on_skill_quest_stage_payment_event(self):
        base = {"abs_minute": 300, "turn": 5, "skills": [], "quest_stages": {}, "quests": [], "events": []}
        cases = [
            ({"type": "skill", "name": "lockpicking", "level": 3}, dict(base, skills=[{"name": "Lockpicking", "value": 3}]), dict(base, skills=[{"name": "Lockpicking", "value": 2}])),
            ({"type": "quest_stage", "stage_id": "gaol_break"}, dict(base, quest_stages={"gaol_break": {"kind": "test"}}), base),
            ({"type": "event", "kind": "quest_stage", "trigger": "restraint:"}, dict(base, events=[{"kind": "quest_stage", "trigger": "restraint:gaol", "status": "resolved"}]),
             dict(base, events=[{"kind": "quest_stage", "trigger": "restraint:gaol", "status": "pending"}])),
            ({"type": "quest_status", "code": "Q3", "status": "completed"}, dict(base, quests=[{"code": "Q3", "status": "completed"}]), dict(base, quests=[{"code": "Q3", "status": "active"}])),
            ({"type": "turns", "turn": 5}, base, dict(base, turn=4)),
        ]
        for cond, met_facts, unmet_facts in cases:
            state = _confined_state(conditions=[cond])
            pending = restraint.evaluate_conditions(state, unmet_facts)
            self.assertEqual(set(pending), {"release", "met", "pending", "next_check_abs_minute"})
            self.assertFalse(pending["release"], cond)
            self.assertEqual(pending["pending"], [cond])
            self.assertTrue(restraint.evaluate_conditions(state, met_facts)["release"], cond)
            with self.conn:
                restraint.save_state(self.conn, restraint.FREE_STATE)
                restraint.capture(self.conn, state, turn=4, world_time=WT)
                stay = restraint.tick(self.conn, facts=unmet_facts)
                self.assertFalse(stay["released"], cond)
                go = restraint.tick(self.conn, facts=met_facts)
            self.assertTrue(go["released"], cond)
            self.assertEqual(restraint.load_state(self.conn)["mode"], "free")
        # Payment: the running total lives in the state; record_payment adds and ticks.
        with self.conn:
            restraint.capture(self.conn, _confined_state(conditions=[{"type": "payment", "units": 400, "currency_set": "coin_medieval"}]), turn=4, world_time=WT)
            part = restraint.record_payment(self.conn, 250, turn=5, world_time=WT)
        self.assertTrue(part["changed"])
        self.assertFalse(part["released"])
        self.assertEqual(restraint.load_state(self.conn)["paid_units"], 250)
        with self.conn:
            rest = restraint.record_payment(self.conn, 250, turn=6, world_time=WT)
        self.assertTrue(rest["released"])
        self.assertEqual(rest["met"], [{"type": "payment", "units": 400, "currency_set": "coin_medieval"}])
        self.assertIn("payment", self._log_events())
        self.assertEqual(self._log_events()[-1], "tick_release")
        # release_word is never met by tick on its own.
        word = _confined_state(conditions=[{"type": "release_word", "by": "A"}])
        self.assertFalse(restraint.evaluate_conditions(word, base)["release"])
        self.assertTrue(restraint.evaluate_conditions(dict(word, notes=["released_by:A"]), base)["release"])
        self.assertIsNone(restraint.evaluate_conditions(_confined_state(conditions=[]), base)["next_check_abs_minute"])
        self.assertFalse(restraint.evaluate_conditions(_confined_state(conditions=[]), base)["release"], "no conditions means indefinite")
        # A skill name that only resolves through the library loads it once per evaluation, not once per row.
        from unittest import mock

        from app import skill_checks

        rows = [{"name": f"Skill {n}", "value": 9} for n in range(25)] + [{"name": "Lockpicking", "value": 3}]
        spelled = _confined_state(conditions=[{"type": "skill", "name": "lock picking", "level": 3}])
        with mock.patch.object(skill_checks, "load_skill_library", wraps=skill_checks.load_skill_library) as loader:
            self.assertTrue(restraint.evaluate_conditions(spelled, dict(base, skills=rows))["release"])
            self.assertEqual(loader.call_count, 1)
            self.assertFalse(restraint.evaluate_conditions(spelled, dict(base, skills=rows[:-1]))["release"])
            self.assertFalse(restraint.evaluate_conditions(spelled, dict(base, skills=rows[:-1] + [{"name": "Lockpicking", "value": 2}]))["release"])
        with mock.patch.object(skill_checks, "load_skill_library", wraps=skill_checks.load_skill_library) as loader:
            exact = _confined_state(conditions=[{"type": "skill", "name": "lockpicking", "level": 3}])
            self.assertTrue(restraint.evaluate_conditions(exact, dict(base, skills=rows))["release"])
            self.assertEqual(loader.call_count, 0, "an exact name match never opens the library")

    def test_gather_facts_reads_tables(self):
        from app.player_resources import world_abs_minutes
        from app.world import get_world_time

        with self.conn:
            self.conn.execute("INSERT INTO player_skills (name, value) VALUES ('Lockpicking', 3)")
            self.conn.execute("INSERT INTO quests (code, title, status) VALUES ('Q3', 'Out of the gaol', 'completed')")
            self.conn.execute("INSERT INTO gm_events (turn, trigger, summary, status, kind) VALUES (2, 'restraint:gaol', 'The warden relents', 'resolved', 'quest_stage')")
            self.conn.execute("INSERT INTO settings (key, value) VALUES ('quest_stages', ?)", (json.dumps({"gaol_break": {"kind": "test"}}),))
            self.conn.execute("INSERT OR REPLACE INTO pacing (key, value) VALUES ('turn', '9')")
        facts = restraint.gather_facts(self.conn)
        self.assertEqual(set(facts), {"abs_minute", "turn", "skills", "quest_stages", "quests", "events"})
        self.assertEqual(facts["skills"], [{"name": "Lockpicking", "value": 3}])
        self.assertEqual(facts["quests"], [{"code": "Q3", "status": "completed"}])
        self.assertEqual(facts["events"], [{"kind": "quest_stage", "trigger": "restraint:gaol", "status": "resolved"}])
        self.assertEqual(facts["quest_stages"], {"gaol_break": {"kind": "test"}})
        self.assertEqual(facts["turn"], 9)
        self.assertEqual(facts["abs_minute"], world_abs_minutes(get_world_time(self.conn)))
        self.assertEqual(restraint.gather_facts(self.conn, {"day": 3, "minute": 10})["abs_minute"], 2 * 1440 + 10)
        state = _confined_state(conditions=[{"type": "skill", "name": "lockpicking", "level": 3}])
        self.assertTrue(restraint.evaluate_conditions(state, facts)["release"])

    def test_release_reports_and_noop_when_free(self):
        with self.conn:
            noop = restraint.release(self.conn, reason="debug", turn=1, world_time=WT)
        self.assertEqual(noop, {"ok": False, "was": "free", "reason": "debug", "journal": [], "log_id": 0})
        self.assertEqual(self._log_events(), [])
        with self.conn:
            restraint.capture(self.conn, _custody_state(), turn=4, world_time=WT)
            rep = restraint.release(self.conn, reason="captor_word", turn=5, world_time=WT, by_code="a")
        self.assertEqual(set(rep), {"ok", "was", "reason", "journal", "log_id"})
        self.assertTrue(rep["ok"])
        self.assertEqual(rep["was"], "custody")
        _assert_journal(self, rep["journal"])
        self.assertEqual(rep["journal"][0]["kind"], "released")
        rows = self._rows("SELECT * FROM restraint_log ORDER BY id")
        self.assertEqual([r["event"] for r in rows], ["captured", "released"])
        self.assertEqual((rows[1]["reason"], rows[1]["actor_code"], rows[1]["mode"]), ("release:captor_word", "A", "free"))
        self.assertIn("released_by:A", json.loads(rows[1]["detail"])["was"]["notes"])
        self.assertEqual(restraint.load_state(self.conn)["mode"], "free")

    def test_record_escape_attempt_success(self):
        with self.conn:
            restraint.capture(self.conn, _bonds_state(), turn=4, world_time=WT)
            rep = restraint.record_escape_attempt(self.conn, {"outcome": "success", "margin": 3}, turn=5, world_time=WT)
        self.assertEqual(set(rep), {"attempted", "escaped", "reason", "dc", "outcome", "penalty_minutes", "journal", "state"})
        self.assertTrue(rep["attempted"])
        self.assertTrue(rep["escaped"])
        self.assertEqual((rep["dc"], rep["outcome"], rep["penalty_minutes"]), (14, "success", 0))
        self.assertEqual(rep["state"]["mode"], "free")
        _assert_journal(self, rep["journal"])
        rows = self._rows("SELECT event, reason FROM restraint_log ORDER BY id")
        self.assertEqual([tuple(r) for r in rows], [("captured", "capture:lost_fight"), ("escaped", "escape:success"), ("released", "release:escape")])
        with self.conn:
            free = restraint.record_escape_attempt(self.conn, {"outcome": "success"}, turn=6, world_time=WT)
        self.assertEqual((free["attempted"], free["reason"]), (False, "free"))

    def test_record_escape_attempt_failure_cooldown_cap(self):
        with self.conn:
            restraint.capture(self.conn, _bonds_state(), turn=4, world_time=WT)
            fail = restraint.record_escape_attempt(self.conn, {"outcome": "failure", "margin": -2}, turn=10, world_time=WT)
        self.assertTrue(fail["attempted"])
        self.assertFalse(fail["escaped"])
        self.assertEqual((fail["reason"], fail["penalty_minutes"]), ("failed", 30))
        state = restraint.load_state(self.conn)
        self.assertEqual(state["escape"]["attempts"], 1)
        self.assertEqual(state["escape"]["last_turn"], 10)
        self.assertEqual(state["conditions"][0]["abs_minute"], 630)
        with self.conn:
            again = restraint.record_escape_attempt(self.conn, {"outcome": "failure"}, turn=10, world_time=WT)
        self.assertEqual((again["attempted"], again["reason"]), (False, "cooldown"))
        self.assertEqual(restraint.load_state(self.conn)["escape"]["attempts"], 1)
        with self.conn:
            self.assertTrue(restraint.record_escape_attempt(self.conn, {"outcome": "failure"}, turn=12, world_time=WT)["attempted"])
            self.assertTrue(restraint.record_escape_attempt(self.conn, {"outcome": "partial"}, turn=14, world_time=WT)["attempted"])
            capped = restraint.record_escape_attempt(self.conn, {"outcome": "failure"}, turn=16, world_time=WT)
        self.assertEqual((capped["attempted"], capped["reason"]), (False, "daily_cap"))
        self.assertEqual(restraint.load_state(self.conn)["escape"]["attempts"], 3)
        self.assertEqual(restraint.load_state(self.conn)["conditions"][0]["abs_minute"], 600 + 3 * 30)
        self.assertEqual(self._log_events().count("escape_failed"), 3)
        with self.conn:
            next_day = restraint.record_escape_attempt(self.conn, {"outcome": "failure"}, turn=18, world_time={"day": 2, "minute": 10})
        self.assertTrue(next_day["attempted"], "the cap is per world day")
        with self.conn:
            self.assertEqual(restraint.record_escape_attempt(self.conn, {"outcome": "narrative"}, turn=30, world_time={"day": 3, "minute": 10})["reason"], "no_dice")
        with self.conn:
            restraint.save_state(self.conn, _bonds_state(escape=None))
            none = restraint.record_escape_attempt(self.conn, {"outcome": "success"}, turn=40, world_time=WT)
        self.assertEqual((none["attempted"], none["reason"]), (False, "no_escape"))

    def test_escape_check_request_shape(self):
        req = restraint.escape_check_request(_bonds_state())
        self.assertEqual(set(req), {"skill_code", "dc", "context_note", "opposition"})
        self.assertEqual((req["skill_code"], req["dc"], req["opposition"]), ("athletics", 14, None))
        self.assertIn("athletics", req["context_note"])
        self.assertIsNone(restraint.escape_check_request(_bonds_state(escape=None)))
        self.assertIsNone(restraint.escape_check_request(restraint.free_state()))
        cooling = _bonds_state(escape={"skill": "athletics", "dc": 14, "attempts": 1, "last_turn": 10, "cooldown_turns": 2, "fail_penalty_minutes": 30})
        self.assertIsNone(restraint.escape_check_request(cooling, turn=11))
        self.assertIsNotNone(restraint.escape_check_request(cooling, turn=12))
        ranked = restraint.escape_check_request(_bonds_state(), player_skills=[{"name": "Athletics", "value": 2}])
        self.assertIn("rank 2", ranked["context_note"])

    def test_apply_position_requires_writers_and_logs(self):
        world = _world_chart()
        locations = _LOCATIONS + [{"id": 9, "code": "L9", "name": "Ashbarrow", "parent_id": 0, "plot_id": "", "city_id": "C7"}]
        plan = restraint.plan_position(_custody_state(), {"x": 50, "y": 50, "city": "C7", "location_code": "L9"}, actor="A", trust="escort", chart=world, current_location_id=5, current_town=None, locations=locations)
        self.assertTrue(plan["ok"])
        with self.assertRaises(RuntimeError):
            restraint.apply_position(self.conn, plan, writers=None, turn=5, world_time=WT)
        player_before = tuple(self._rows("SELECT * FROM player WHERE id = 1")[0])
        calls: list[tuple] = []
        writers = {
            "location": lambda conn, to_id: calls.append(("location", to_id)),
            "token": lambda map_id, x, y: calls.append(("token", map_id, x, y)),
            "town": lambda conn, action, came_from: calls.append(("town", action, came_from)),
        }
        with self.conn:
            restraint.capture(self.conn, _custody_state(), turn=4, world_time=WT)
            out = restraint.apply_position(self.conn, plan, writers=writers, turn=5, world_time=WT)
        self.assertEqual(set(out), {"applied", "log_id", "journal"})
        self.assertEqual(out["applied"], ["location", "token", "town"])
        self.assertEqual(calls, [("location", 9), ("token", "world-test", 50, 50), ("town", "enter", (40, 40))])
        _assert_journal(self, out["journal"])
        rows = self._rows("SELECT * FROM restraint_log WHERE event = 'position_set'")
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["actor_code"], rows[0]["from_location_id"], rows[0]["to_location_id"], rows[0]["reason"]), ("A", 5, 9, "position:escort"))
        self.assertEqual(json.loads(rows[0]["detail"])["applied"], ["location", "token", "town"])
        self.assertEqual(restraint.load_state(self.conn)["place"]["cell"], [50, 50])
        self.assertEqual(tuple(self._rows("SELECT * FROM player WHERE id = 1")[0]), player_before, "the module never moves the player itself")
        with self.assertRaises(ValueError):
            restraint.apply_position(self.conn, dict(plan, ok=False), writers=writers, turn=5, world_time=WT)
        with self.assertRaises(RuntimeError):
            restraint.apply_position(self.conn, plan, writers={"location": writers["location"]}, turn=5, world_time=WT)
        # Bonds travel with the player: a restrained state keeps place None after a position set.
        with self.conn:
            restraint.capture(self.conn, _bonds_state(), turn=6, world_time=WT)
            bound_plan = restraint.plan_position(restraint.load_state(self.conn), {"x": 50, "y": 50, "city": "C7", "location_code": "L9"}, actor="A", trust="escort", chart=world, current_location_id=5, current_town=None, locations=locations)
            self.assertTrue(bound_plan["ok"])
            restraint.apply_position(self.conn, bound_plan, writers=writers, turn=6, world_time=WT)
        held = restraint.load_state(self.conn)
        self.assertEqual(held["mode"], "restrained")
        self.assertIsNone(held["place"])

    def test_begin_and_advance_escort(self):
        plan = restraint.plan_escort(_board(), start=(1, 1), dest={"x": 6, "y": 1, "plot": "C9.0.0.3", "city": "C9"})
        self.assertEqual(len(plan["legs"]), 2)
        with self.conn:
            rep = restraint.begin_escort(self.conn, plan, by={"code": "A", "name": "Captain Ror"}, turn=4, world_time=WT)
        self.assertTrue(rep["ok"])
        self.assertFalse(rep["replaced_previous"])
        _assert_journal(self, rep["journal"])
        self.assertEqual(rep["journal"][0]["kind"], "escort")
        state = restraint.load_state(self.conn)
        self.assertEqual((state["mode"], state["scope"]), ("custody", "person"))
        self.assertEqual(state["escort"]["legs_total"], 2)
        self.assertEqual(state["escort"]["to"], {"x": 6, "y": 1, "plot": "C9.0.0.3", "city_id": "C9", "location_code": ""})
        self.assertEqual(state["escort"]["plan_id"], plan["plan_id"])
        self.assertEqual(state["by"]["name"], "Captain Ror")
        self.assertEqual(restraint.may_move(self.conn, "travel_press", None)["reason"], "escort_in_progress")
        with self.conn:
            mid = restraint.advance_escort(self.conn, legs_done=1, turn=5)
        self.assertEqual(mid["escort"]["legs_done"], 1)
        with self.conn:
            done = restraint.advance_escort(self.conn, legs_done=2, turn=6)
        self.assertIsNone(done["escort"])
        self.assertEqual(done["mode"], "custody")
        self.assertEqual(restraint.may_move(self.conn, "travel_press", None)["reason"], "custody")
        self.assertEqual(self._log_events(), ["captured"])
        with self.conn:
            again = restraint.begin_escort(self.conn, plan, by=None, turn=7, world_time=WT)
        self.assertTrue(again["replaced_previous"])
        self.assertEqual(self._log_events(), ["captured", "transferred"])
        self.assertEqual(restraint.load_state(self.conn)["by"]["name"], "Captain Ror", "a missing captor keeps the previous one")
        with self.assertRaises(ValueError):
            restraint.begin_escort(self.conn, dict(plan, ok=False), by=None, turn=8, world_time=WT)
        # A plan with nothing to walk never starts an escort, or the block would never clear.
        same_cell = restraint.plan_escort(_board(), start=(1, 1), dest={"x": 1, "y": 1})
        self.assertTrue(same_cell["ok"])
        self.assertEqual(same_cell["legs"], [])
        with self.assertRaises(ValueError):
            restraint.begin_escort(self.conn, same_cell, by=None, turn=8, world_time=WT)
        self.assertEqual(self._log_events(), ["captured", "transferred"])

    def test_transfer_moves_confinement(self):
        with self.conn:
            noop = restraint.transfer(self.conn, {"location_id": 7}, turn=3, world_time=WT)
        self.assertFalse(noop["ok"])
        with self.conn:
            restraint.capture(self.conn, _custody_state(), turn=4, world_time=WT)
            rep = restraint.transfer(self.conn, {"location_id": 7, "location_code": "L7"}, turn=5, world_time=WT, by={"code": "B", "name": "Warden"}, reason="gaol")
        self.assertTrue(rep["ok"])
        state = restraint.load_state(self.conn)
        self.assertEqual((state["mode"], state["scope"], state["place"]["location_id"], state["by"]["name"]), ("confined", "location", 7, "Warden"))
        self.assertEqual(self._log_events(), ["captured", "transferred"])
        self.assertTrue(restraint.may_move(self.conn, "location_move", {"location_id": 7})["allowed"])
        self.assertFalse(restraint.may_move(self.conn, "location_move", {"location_id": 5})["allowed"])
        with self.assertRaises(ValueError):
            restraint.transfer(self.conn, {}, turn=6, world_time=WT)

    def test_log_prune_keeps_latest(self):
        with self.conn:
            for i in range(210):
                restraint._log(self.conn, turn=i, abs_minute=i, event="blocked", mode="restrained", reason="blocked:map_step", detail={"i": i})
        ids = [r[0] for r in self._rows("SELECT id FROM restraint_log ORDER BY id")]
        self.assertEqual(len(ids), 200)
        self.assertEqual((ids[0], ids[-1]), (11, 210))
        rows = restraint.log_rows(self.conn, limit=3)
        self.assertEqual([r["turn"] for r in rows], [209, 208, 207])
        self.assertEqual(rows[0]["detail"], {"i": 209})
        with self.conn:
            removed = restraint.log_prune(self.conn, keep=5)
        self.assertEqual(removed, 195)
        self.assertEqual(len(self._rows("SELECT id FROM restraint_log")), 5)

    def test_runtime_flags_shape_and_own_connection(self):
        flags = restraint.runtime_flags()
        self.assertEqual(flags, {"movement_locked": False, "label": "", "hint": "", "reason": "", "restraint": None})
        with self.conn:
            restraint.capture(self.conn, _confined_state(), turn=4, world_time=WT)
        flags = restraint.runtime_flags()
        self.assertEqual(set(flags), {"movement_locked", "label", "hint", "reason", "restraint"})
        self.assertTrue(flags["movement_locked"])
        self.assertEqual((flags["label"], flags["reason"]), ("Held in the gaol cell", "confined"))
        self.assertIn("the gaol cell", flags["hint"])
        self.assertEqual(flags["restraint"]["mode"], "confined")
        self.assertEqual(restraint.runtime_flags(self.conn), flags)
        self.assertEqual(self._rows("SELECT key FROM settings WHERE key IN ('movement_locked', 'map_blank', 'location_special_flags', 'town_position', 'travel_ready')"), [])

    def test_writers_touch_only_own_table_and_row(self):
        with self.conn:
            self.conn.execute("INSERT INTO settings (key, value) VALUES ('town_position', '{\"cx\": 1}')")
            self.conn.execute("INSERT INTO settings (key, value) VALUES ('movement_locked', 'false')")
            self.conn.execute("INSERT INTO journal (turn, kind, content) VALUES (1, 'fact', 'before')")
            self.conn.execute("INSERT INTO locations (code, name) VALUES ('L4', 'Old Mill')")
            loc_id = self.conn.execute("SELECT id FROM locations WHERE code = 'L4'").fetchone()[0]
            self.conn.execute("INSERT INTO npcs (code, name, location_id) VALUES ('A', 'Captain Ror', ?)", (loc_id,))
            self.conn.execute("INSERT INTO quests (code, title, status) VALUES ('Q3', 'Out', 'active')")
        before = self._snapshot()
        board = _board()
        world = _world_chart()
        calls: list[str] = []
        writers = {"location": lambda c, i: calls.append("l"), "token": lambda m, x, y: calls.append("t"), "town": lambda c, a, f: calls.append("w")}
        verdict = restraint.classify_capture(narration="They march you off to the gaol.", player_input="I surrender.")
        with self.conn:
            restraint.capture(self.conn, restraint.propose_capture(verdict, world_time=WT, turn=4, location={"id": 7, "code": "L7", "name": "the gaol"}, fine_units=400, currency_set="coin_medieval"), turn=4, world_time=WT)
            restraint.record_payment(self.conn, 100, turn=5, world_time=WT)
            restraint.record_escape_attempt(self.conn, {"outcome": "failure"}, turn=6, world_time=WT)
            restraint.tick(self.conn, world_time=WT, turn=7)
            restraint.transfer(self.conn, {"location_id": 5, "location_code": "L4"}, turn=8, world_time=WT)
            plan = restraint.plan_position(restraint.load_state(self.conn), {"x": 50, "y": 50, "city": "C7"}, actor="engine", trust="engine", chart=world, current_location_id=5, current_town=None, locations=_LOCATIONS)
            restraint.apply_position(self.conn, plan, writers=writers, turn=9, world_time=WT)
            restraint.begin_escort(self.conn, restraint.plan_escort(board, start=(1, 1), dest={"x": 6, "y": 1}), by=None, turn=10, world_time=WT)
            restraint.advance_escort(self.conn, legs_done=1, turn=11)
            restraint.release(self.conn, reason="debug", turn=12, world_time=WT, by_code="A")
            restraint.log_prune(self.conn)
        after = self._snapshot()
        self.assertEqual(before, after, "a restraint writer changed something outside restraint_log and the restraint settings row")
        self.assertEqual(self._log_events(), ["captured", "payment", "escape_failed", "transferred", "position_set", "transferred", "released"])
        self.assertEqual(self._rows("SELECT key FROM settings WHERE key = 'restraint'"), [])
        self.assertEqual(self._rows("SELECT value FROM settings WHERE key = 'movement_locked'")[0][0], "false")


if __name__ == "__main__":
    unittest.main()
