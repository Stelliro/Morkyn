"""Tests for app/realtime_clock.py (TODO n2, built but not wired).

The module is a leaf: nothing in app/ or static/ imports it. These tests run it against a
temporary database with no model, no network and no wall clock (every now_wall is a literal).
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-realtime-clock-test-"))
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
    # The two keys the module reads: blank means "no override".
    "AI_RPG_REALTIME_ENABLED": "",
    "AI_RPG_REALTIME_RATIO": "",
}
os.environ.update(_ENV)

from app.db import connect, db_path, init_db  # noqa: E402
from app import realtime_clock as rc  # noqa: E402

MODULE_PATH = ROOT / "app" / "realtime_clock.py"

NOW = 1_700_000_000.0  # a literal epoch second; never time.time()


def setUpModule():
    os.environ.update(_ENV)
    init_db()
    with connect() as conn:
        rc.ensure_schema(conn)


@contextmanager
def _env(**values):
    old = {k: os.environ.get(k) for k in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _running_cfg(**over) -> dict:
    cfg = {"enabled": True, "paused": False, "ratio": 12.0, "anchor_wall": NOW, "anchor_world_minute": 480}
    cfg.update(over)
    return rc.normalize_config(cfg)


def _table_counts(conn) -> dict[str, int]:
    names = [
        r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    ]
    return {name: int(conn.execute(f'SELECT COUNT(*) AS n FROM "{name}"').fetchone()["n"]) for name in names}


def _settings_except_own(conn) -> dict[str, str]:
    return {
        r["key"]: r["value"]
        for r in conn.execute("SELECT key, value FROM settings WHERE key != ?", (rc.SETTING_KEY,))
    }


def _pacing(conn) -> dict[str, str]:
    return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM pacing")}


def _assert_slice(case: unittest.TestCase, item: dict) -> None:
    case.assertEqual(set(item), {"minutes", "kind", "effects"})
    case.assertIsInstance(item["minutes"], int)
    case.assertEqual(item["kind"], "wait")
    case.assertEqual(item["effects"], ["advance_world_time", "apply_regen", "roll_wait_events"])


def _assert_plan_shape(case: unittest.TestCase, plan: dict) -> None:
    case.assertEqual(
        set(plan),
        {"status", "reason", "due_minutes", "apply_minutes", "capped", "dropped_minutes", "slices",
         "anchor_after", "world_abs_now", "expected_world_minute"},
    )
    case.assertIn(plan["status"], {"tick", "skip"})
    case.assertIn(plan["reason"], set(rc.SKIP_REASONS) | {""})
    for key in ("due_minutes", "apply_minutes", "dropped_minutes", "world_abs_now", "expected_world_minute"):
        case.assertIsInstance(plan[key], int, key)
    case.assertIsInstance(plan["capped"], bool)
    case.assertIsInstance(plan["slices"], list)
    for item in plan["slices"]:
        _assert_slice(case, item)
    case.assertEqual(set(plan["anchor_after"]), {"wall", "world_minute"})
    case.assertIsInstance(plan["anchor_after"]["wall"], float)
    case.assertIsInstance(plan["anchor_after"]["world_minute"], int)


# ---------------------------------------------------------------------------
# Leaf and docstring
# ---------------------------------------------------------------------------


class LeafTests(unittest.TestCase):
    def test_module_is_a_leaf(self):
        pattern = re.compile(r"app\.realtime_clock|import realtime_clock")
        offenders = []
        for folder in ("app", "static"):
            for path in (ROOT / folder).rglob("*"):
                if not path.is_file() or path.suffix not in {".py", ".js", ".html", ".css"}:
                    continue
                if path == MODULE_PATH:
                    continue
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                if pattern.search(text):
                    offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [], f"realtime_clock is imported by: {offenders}")
        doc = rc.__doc__ or ""
        self.assertIn("Status: built, not wired (TODO n2).", doc)
        self.assertIn("Wiring (not done):", doc)
        self.assertIn("Turn on:", doc)
        self.assertIn("Tests: tests/test_realtime_clock.py", doc)
        # The heavy writers are imported lazily inside wait_effects, never at module level.
        for name in ("advance_world_time", "apply_regen", "roll_wait_events", "get_world_time"):
            self.assertFalse(hasattr(rc, name), name)

    def test_docstring_hooks_name_real_functions(self):
        hooks = {
            "app/main.py": ["def api_tts_config(", "def api_update_tts_config("],
            "app/world.py": ["def advance_world_time(", "def roll_wait_events(", "def play_turn(",
                             "def play_wait_turn(", "def start_playthrough(", "def get_state(",
                             "def init_world_clock(", "def apply_turn(", "def get_world_time("],
            "app/player_resources.py": ["def apply_regen(", "def world_abs_minutes("],
            "static/app.js": ["function startGenerationProgressPolling("],
        }
        for rel, names in hooks.items():
            text = (ROOT / rel).read_text(encoding="utf-8", errors="ignore")
            for name in names:
                self.assertIn(name, text, f"{rel} no longer defines {name}")

    def test_rules_tables_hold_the_designed_numbers(self):
        self.assertEqual(rc.SETTING_KEY, "realtime_clock")
        self.assertEqual(
            rc.RATIO_PRESETS,
            {"real": 1.0, "brisk": 4.0, "day_in_two_hours": 12.0, "day_in_hour": 24.0, "day_in_quarter_hour": 96.0},
        )
        self.assertEqual((rc.RATIO_MIN, rc.RATIO_MAX), (0.1, 1440.0))
        self.assertEqual((rc.SLICE_DEFAULT, rc.SLICE_MIN, rc.SLICE_MAX), (60, 5, 360))
        self.assertEqual((rc.MAX_CATCH_UP_DEFAULT, rc.MAX_CATCH_UP_MIN, rc.MAX_CATCH_UP_MAX), (1440, 60, 10080))
        self.assertEqual(rc.WORLD_DAY_MINUTES, 1440)
        self.assertEqual(rc.PAUSE_REASONS, ("player", "turn_in_flight", "travel_pending", "setup", "disabled"))
        self.assertEqual(rc.SLICE_EFFECTS, ("advance_world_time", "apply_regen", "roll_wait_events"))
        self.assertEqual(rc.SLICE_KIND, "wait")
        self.assertEqual((rc.ENV_ENABLED, rc.ENV_RATIO), ("AI_RPG_REALTIME_ENABLED", "AI_RPG_REALTIME_RATIO"))
        from app import world as W

        self.assertEqual(rc.SLICE_MAX, max(W.WAIT_MINUTE_CHOICES))
        self.assertEqual(rc.WORLD_DAY_MINUTES, W.WORLD_DAY_LENGTH_MINUTES)


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


class ConfigTests(unittest.TestCase):
    def test_defaults_and_normalize(self):
        cfg = rc.normalize_config({})
        self.assertEqual(
            cfg,
            {"enabled": False, "paused": True, "ratio": 12.0, "preset": "day_in_two_hours", "anchor_wall": None,
             "anchor_world_minute": None, "last_tick_wall": None, "slice_minutes": 60,
             "max_catch_up_minutes": 1440, "pause_reason": "", "paused_at_wall": None},
        )
        self.assertEqual(rc.normalize_config(None), cfg)
        by_name = rc.normalize_config({"ratio": "day_in_hour"})
        self.assertEqual((by_name["ratio"], by_name["preset"]), (24.0, "day_in_hour"))
        by_preset = rc.normalize_config({"preset": "brisk"})
        self.assertEqual((by_preset["ratio"], by_preset["preset"]), (4.0, "brisk"))
        clamped = rc.normalize_config({"ratio": 5000, "slice_minutes": 2, "max_catch_up_minutes": 10})
        self.assertEqual(clamped["ratio"], 1440.0)
        self.assertEqual(clamped["preset"], "custom")
        self.assertEqual(clamped["slice_minutes"], 5)
        self.assertEqual(clamped["max_catch_up_minutes"], 60)
        high = rc.normalize_config({"slice_minutes": 999, "max_catch_up_minutes": 99999})
        self.assertEqual((high["slice_minutes"], high["max_catch_up_minutes"]), (360, 10080))
        odd = rc.normalize_config({"enabled": "yes", "paused": "no", "pause_reason": "nonsense",
                                   "anchor_wall": "1.5", "anchor_world_minute": "77", "ratio": "junk"})
        self.assertTrue(odd["enabled"])
        self.assertFalse(odd["paused"])
        self.assertEqual(odd["pause_reason"], "")
        self.assertEqual(odd["anchor_wall"], 1.5)
        self.assertEqual(odd["anchor_world_minute"], 77)
        self.assertEqual(odd["ratio"], 12.0)

    def test_resolve_ratio(self):
        self.assertEqual(rc.resolve_ratio("day_in_quarter_hour"), 96.0)
        self.assertEqual(rc.resolve_ratio(" REAL "), 1.0)
        self.assertEqual(rc.resolve_ratio(0.01), 0.1)
        self.assertEqual(rc.resolve_ratio(-3), 12.0)
        self.assertEqual(rc.resolve_ratio(None), 12.0)
        self.assertEqual(rc.resolve_ratio("30"), 30.0)

    def test_env_overrides_on_read(self):
        with connect() as conn:
            rc.update_config(conn, {"ratio": 12.0, "enabled": False}, now_wall=NOW)
            with _env(AI_RPG_REALTIME_RATIO="4", AI_RPG_REALTIME_ENABLED="on"):
                cfg = rc.get_config(conn)
                self.assertEqual(cfg["ratio"], 4.0)
                self.assertEqual(cfg["preset"], "brisk")
                self.assertTrue(cfg["enabled"])
            plain = rc.get_config(conn)
            self.assertEqual(plain["ratio"], 12.0)
            self.assertFalse(plain["enabled"])


class ElapsedTests(unittest.TestCase):
    def test_elapsed_zero_when_paused_disabled_or_unanchored(self):
        self.assertEqual(rc.elapsed_world_minutes(_running_cfg(enabled=False), NOW + 600), 0)
        self.assertEqual(rc.elapsed_world_minutes(_running_cfg(paused=True), NOW + 600), 0)
        self.assertEqual(rc.elapsed_world_minutes(_running_cfg(anchor_wall=None), NOW + 600), 0)
        self.assertEqual(rc.elapsed_world_minutes(_running_cfg(anchor_world_minute=None), NOW + 600), 0)
        self.assertEqual(rc.elapsed_world_minutes(_running_cfg(), NOW - 600), 0)

    def test_elapsed_ratio_math(self):
        cfg = _running_cfg()
        self.assertEqual(rc.elapsed_world_minutes(cfg, NOW + 600), 120)
        self.assertEqual(rc.elapsed_world_minutes(cfg, NOW + 4.9), 0)  # 0.98 world minutes floors to 0
        self.assertEqual(rc.elapsed_world_minutes(cfg, NOW + 9.9), 1)  # 1.98 floors to 1, not 2
        self.assertEqual(rc.elapsed_world_minutes(_running_cfg(ratio=1.0), NOW + 3600), 60)

    def test_wall_world_roundtrip(self):
        cfg = _running_cfg(ratio=12.0)
        self.assertIsNone(rc.wall_to_world(rc.normalize_config({}), NOW))
        self.assertIsNone(rc.world_to_wall(rc.normalize_config({}), 500))
        self.assertEqual(rc.wall_to_world(cfg, NOW), 480)
        self.assertEqual(rc.wall_to_world(cfg, NOW + 600), 600)
        self.assertEqual(rc.world_to_wall(cfg, 600), NOW + 600)
        one_world_minute = 60.0 / 12.0
        for wall in (NOW, NOW + 7.3, NOW + 600.0, NOW + 12345.6):
            back = rc.world_to_wall(cfg, rc.wall_to_world(cfg, wall))
            self.assertLessEqual(back, wall)
            self.assertLess(wall - back, one_world_minute + 1e-6)
        self.assertEqual(rc.wall_to_world(cfg, rc.world_to_wall(cfg, 1234)), 1234)

    def test_slice_plan_shapes(self):
        self.assertEqual(rc.slice_plan(150, 60), [60, 60, 30])
        self.assertEqual(rc.slice_plan(0, 60), [])
        self.assertEqual(rc.slice_plan(-5, 60), [])
        self.assertEqual(rc.slice_plan(45, 60), [45])
        self.assertEqual(rc.slice_plan(120, 60), [60, 60])
        self.assertEqual(rc.slice_plan(7, 0), [1] * 7)
        _assert_slice(self, rc.make_slice(30))


class PlanTests(unittest.TestCase):
    def test_plan_nothing_due_rebases_anchor(self):
        cfg = _running_cfg()
        # 120 owed, but play advanced the world to 700: nothing due, anchor jumps to (now, 700).
        plan = rc.plan_catch_up(cfg, now_wall=NOW + 600, world_abs_now=700)
        _assert_plan_shape(self, plan)
        self.assertEqual(plan["status"], "skip")
        self.assertEqual(plan["reason"], "nothing_due")
        self.assertEqual(plan["due_minutes"], -100)
        self.assertEqual(plan["expected_world_minute"], 600)
        self.assertEqual(plan["anchor_after"], {"wall": NOW + 600, "world_minute": 700})
        self.assertEqual(plan["slices"], [])
        # Only a fraction of a world minute passed and play did not move: the anchor is kept.
        tiny = rc.plan_catch_up(cfg, now_wall=NOW + 2.0, world_abs_now=480)
        self.assertEqual((tiny["status"], tiny["reason"]), ("skip", "nothing_due"))
        self.assertEqual(tiny["anchor_after"], {"wall": NOW, "world_minute": 480})

    def test_plan_due_minus_play(self):
        cfg = _running_cfg()
        plan = rc.plan_catch_up(cfg, now_wall=NOW + 600, world_abs_now=510)
        _assert_plan_shape(self, plan)
        self.assertEqual(plan["status"], "tick")
        self.assertEqual(plan["reason"], "")
        self.assertEqual(plan["due_minutes"], 90)
        self.assertEqual(plan["apply_minutes"], 90)
        self.assertFalse(plan["capped"])
        self.assertEqual(plan["dropped_minutes"], 0)
        self.assertEqual([s["minutes"] for s in plan["slices"]], [60, 30])
        self.assertEqual(plan["expected_world_minute"], 600)
        self.assertEqual(plan["anchor_after"], {"wall": NOW + 600, "world_minute": 600})

    def test_plan_keeps_the_fraction_of_a_minute(self):
        cfg = _running_cfg()
        # 603 real seconds = 120.6 world minutes: 120 are due; the 0.6 (3 real seconds) stays with the anchor.
        plan = rc.plan_catch_up(cfg, now_wall=NOW + 603, world_abs_now=480)
        self.assertEqual(plan["apply_minutes"], 120)
        self.assertAlmostEqual(plan["anchor_after"]["wall"], NOW + 600, places=6)
        self.assertEqual(plan["anchor_after"]["world_minute"], 600)

    def test_plan_capped_and_dropped(self):
        cfg = _running_cfg()
        plan = rc.plan_catch_up(cfg, now_wall=NOW + 15000, world_abs_now=480)  # 3000 owed
        _assert_plan_shape(self, plan)
        self.assertEqual(plan["status"], "tick")
        self.assertEqual(plan["due_minutes"], 3000)
        self.assertEqual(plan["apply_minutes"], 1440)
        self.assertTrue(plan["capped"])
        self.assertEqual(plan["dropped_minutes"], 1560)
        self.assertEqual([s["minutes"] for s in plan["slices"]], [60] * 24)
        self.assertEqual(plan["anchor_after"], {"wall": NOW + 15000, "world_minute": 1920})

    def test_plan_skips_busy_and_travel_pending(self):
        cfg = _running_cfg()
        busy = rc.plan_catch_up(cfg, now_wall=NOW + 600, world_abs_now=480, busy=True)
        self.assertEqual((busy["status"], busy["reason"]), ("skip", "busy"))
        self.assertEqual(busy["due_minutes"], 120)
        self.assertEqual(busy["anchor_after"], {"wall": NOW, "world_minute": 480})
        held = rc.plan_catch_up(cfg, now_wall=NOW + 600, world_abs_now=480, travel_pending=True)
        self.assertEqual((held["status"], held["reason"]), ("skip", "travel_pending"))
        off = rc.plan_catch_up(_running_cfg(enabled=False), now_wall=NOW + 600, world_abs_now=480)
        self.assertEqual((off["status"], off["reason"]), ("skip", "disabled"))
        paused = rc.plan_catch_up(_running_cfg(paused=True), now_wall=NOW + 600, world_abs_now=480)
        self.assertEqual((paused["status"], paused["reason"]), ("skip", "paused"))
        loose = rc.plan_catch_up(_running_cfg(anchor_wall=None), now_wall=NOW + 600, world_abs_now=480)
        self.assertEqual((loose["status"], loose["reason"]), ("skip", "no_anchor"))
        for plan in (busy, held, off, paused, loose):
            _assert_plan_shape(self, plan)
            self.assertEqual(plan["slices"], [])
            self.assertEqual(plan["apply_minutes"], 0)

    def test_rebase_after_partial(self):
        cfg = _running_cfg()
        plan = rc.plan_catch_up(cfg, now_wall=NOW + 750, world_abs_now=480)  # 150 owed: [60, 60, 30]
        after = rc.rebase_after(cfg, plan, applied_minutes=60, now_wall=NOW + 750)
        self.assertEqual(after["world_minute"], 540)
        # 90 minutes stay owed: the anchor sits 90 world minutes (450 real seconds) before now.
        self.assertAlmostEqual(after["wall"], NOW + 300, places=6)
        self.assertEqual(rc.wall_to_world(rc.normalize_config({**cfg, **{"anchor_wall": after["wall"],
                                                                          "anchor_world_minute": 540}}),
                                          NOW + 750), 630)

    def test_describe_and_next_tick_seconds(self):
        self.assertEqual(rc.describe(_running_cfg()), "One world day passes in 2.0 real hours (ratio 12.0). Running.")
        self.assertEqual(
            rc.describe(_running_cfg(paused=True, pause_reason="turn_in_flight")),
            "One world day passes in 2.0 real hours (ratio 12.0). Paused: turn in flight.",
        )
        self.assertEqual(rc.describe(_running_cfg(paused=True)), "One world day passes in 2.0 real hours (ratio 12.0). Paused.")
        self.assertEqual(rc.describe(rc.normalize_config({})), "Real-time clock is off. One world day passes in 2.0 real hours (ratio 12.0).")
        self.assertEqual(rc.describe(_running_cfg(ratio=96.0)), "One world day passes in 15 real minutes (ratio 96.0). Running.")
        self.assertEqual(rc.describe(_running_cfg(anchor_wall=None)), "One world day passes in 2.0 real hours (ratio 12.0). Not anchored yet.")
        cfg = _running_cfg()
        self.assertEqual(rc.next_tick_seconds(cfg, NOW), 300)          # a 60-minute slice at ratio 12
        self.assertEqual(rc.next_tick_seconds(cfg, NOW + 100), 200)
        self.assertEqual(rc.next_tick_seconds(cfg, NOW + 300), 300)    # one owed; the next is 300 s away
        self.assertEqual(rc.next_tick_seconds(cfg, NOW + 299.5), 1)
        self.assertIsNone(rc.next_tick_seconds(_running_cfg(paused=True), NOW))
        self.assertIsNone(rc.next_tick_seconds(_running_cfg(enabled=False), NOW))
        self.assertIsNone(rc.next_tick_seconds(_running_cfg(anchor_world_minute=None), NOW))


# ---------------------------------------------------------------------------
# Busy signal
# ---------------------------------------------------------------------------


class BusyTests(unittest.TestCase):
    def test_turn_in_flight_reads_generation_progress(self):
        from app import generation_progress as gp

        gp.end()
        with mock.patch("app.gpu_gate.gate_status", return_value={"active": {}}):
            self.assertFalse(rc.turn_in_flight())
            gp.begin("turn")
            try:
                self.assertTrue(rc.turn_in_flight())
            finally:
                gp.end()
            self.assertFalse(rc.turn_in_flight())
        with mock.patch("app.gpu_gate.gate_status", return_value={"active": {"llm": 2.5}}):
            self.assertTrue(rc.turn_in_flight())
        with mock.patch("app.gpu_gate.gate_status", return_value={"active": {"image": 1.0}}):
            self.assertFalse(rc.turn_in_flight())
        with mock.patch("app.gpu_gate.gate_status", side_effect=RuntimeError("no gpu")):
            self.assertFalse(rc.turn_in_flight())

    def test_travel_pending_reads_travel_ready(self):
        with connect() as conn:
            conn.execute("DELETE FROM settings WHERE key = 'travel_ready'")
            self.assertFalse(rc.travel_pending(conn))
            for raw, expected in (("false", True), ("true", False), ('"no"', True), ("0", True), ("1", False),
                                  ("off", True), ("yes", False)):
                conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('travel_ready', ?)", (raw,))
                self.assertEqual(rc.travel_pending(conn), expected, raw)
            conn.execute("DELETE FROM settings WHERE key = 'travel_ready'")


# ---------------------------------------------------------------------------
# Writers and the tick (a fresh DB per test)
# ---------------------------------------------------------------------------


class RealtimeClockDbTests(unittest.TestCase):
    def setUp(self):
        os.environ.update(_ENV)
        path = db_path()
        if path.exists():
            path.unlink()
        init_db()
        with connect() as conn:
            rc.ensure_schema(conn)
            # init_db seeds a player row; replace it with the template row so every test starts alike.
            conn.execute(
                "INSERT OR REPLACE INTO player (id, name, health, max_health, level, xp, gold, current_location_id) "
                "VALUES (1, 'T', 20, 20, 1, 0, 12, NULL)"
            )
            conn.execute("INSERT OR REPLACE INTO pacing (key, value) VALUES ('world_day', '1')")
            conn.execute("INSERT OR REPLACE INTO pacing (key, value) VALUES ('world_minute', '480')")

    def _enable(self, conn, **extra):
        rc.update_config(conn, {"enabled": True, **extra}, now_wall=NOW)
        return rc.resume(conn, now_wall=NOW, world_abs_now=480)

    def test_ensure_schema_is_a_no_op(self):
        with connect() as conn:
            before = _table_counts(conn)
            names_before = set(before)
            self.assertIsNone(rc.ensure_schema(conn))
            rc.ensure_schema(conn)
            self.assertEqual(set(_table_counts(conn)), names_before)
            self.assertEqual(_table_counts(conn), before)

    def test_get_config_without_a_row_and_with_own_connection(self):
        with connect() as conn:
            self.assertIsNone(conn.execute("SELECT value FROM settings WHERE key = ?", (rc.SETTING_KEY,)).fetchone())
            self.assertEqual(rc.get_config(conn), rc.normalize_config({}))
        self.assertEqual(rc.get_config(), rc.normalize_config({}))

    def test_update_config_partial_and_errors(self):
        with connect() as conn:
            with self.assertRaises(ValueError):
                rc.update_config(conn, "ratio=4")  # type: ignore[arg-type]
            cfg = rc.update_config(conn, {"ratio": "day_in_hour", "slice_minutes": 30, "bogus": 1,
                                          "anchor_world_minute": 999, "paused": False}, now_wall=NOW)
            self.assertEqual((cfg["ratio"], cfg["preset"], cfg["slice_minutes"]), (24.0, "day_in_hour", 30))
            self.assertIsNone(cfg["anchor_world_minute"])  # anchors never come from a payload
            self.assertTrue(cfg["paused"])                  # neither does paused
            self.assertFalse(cfg["enabled"])
            cfg2 = rc.update_config(conn, {"preset": "brisk"}, now_wall=NOW)
            self.assertEqual((cfg2["ratio"], cfg2["preset"], cfg2["slice_minutes"]), (4.0, "brisk", 30))
            cfg3 = rc.update_config(conn, {"max_catch_up_minutes": None}, now_wall=NOW)
            self.assertEqual(cfg3["max_catch_up_minutes"], 1440)
            self.assertEqual(cfg3["ratio"], 4.0)
            stored = conn.execute("SELECT value FROM settings WHERE key = ?", (rc.SETTING_KEY,)).fetchone()
            self.assertIsNotNone(stored)

    def test_pause_resume_cycle(self):
        with connect() as conn:
            # resume on a disabled row: nothing written, pause_reason "disabled" in the answer
            answer = rc.resume(conn, now_wall=NOW, world_abs_now=480)
            self.assertEqual(answer["pause_reason"], "disabled")
            self.assertTrue(answer["paused"])
            self.assertIsNone(conn.execute("SELECT value FROM settings WHERE key = ?", (rc.SETTING_KEY,)).fetchone())
            cfg = rc.update_config(conn, {"enabled": True}, now_wall=NOW)
            self.assertTrue(cfg["enabled"])
            self.assertTrue(cfg["paused"])  # a fresh row is paused until resume anchors it
            cfg = rc.resume(conn, now_wall=NOW, world_abs_now=500)
            self.assertFalse(cfg["paused"])
            self.assertEqual(cfg["pause_reason"], "")
            self.assertIsNone(cfg["paused_at_wall"])
            self.assertEqual((cfg["anchor_wall"], cfg["anchor_world_minute"]), (NOW, 500))
            cfg = rc.pause(conn, reason="turn_in_flight", now_wall=NOW + 100)
            self.assertTrue(cfg["paused"])
            self.assertEqual(cfg["pause_reason"], "turn_in_flight")
            self.assertEqual(cfg["paused_at_wall"], NOW + 100)
            self.assertEqual(rc.elapsed_world_minutes(cfg, NOW + 1000), 0)
            bad = rc.pause(conn, reason="whatever", now_wall=NOW + 101)
            self.assertEqual(bad["pause_reason"], "player")
            # resume after a pause re-anchors: the paused span owes nothing
            cfg = rc.resume(conn, now_wall=NOW + 1000, world_abs_now=530)
            self.assertEqual((cfg["anchor_wall"], cfg["anchor_world_minute"]), (NOW + 1000, 530))
            self.assertEqual(rc.elapsed_world_minutes(cfg, NOW + 1000), 0)
            self.assertEqual(rc.elapsed_world_minutes(cfg, NOW + 1300), 60)

    def test_resume_reads_the_world_clock_when_not_given(self):
        with connect() as conn:
            conn.execute("INSERT OR REPLACE INTO pacing (key, value) VALUES ('world_day', '2')")
            conn.execute("INSERT OR REPLACE INTO pacing (key, value) VALUES ('world_minute', '30')")
            rc.update_config(conn, {"enabled": True}, now_wall=NOW)
            cfg = rc.resume(conn, now_wall=NOW)
            self.assertEqual(cfg["anchor_world_minute"], 1470)

    def test_reset_anchor(self):
        with connect() as conn:
            cfg = rc.reset_anchor(conn, now_wall=NOW + 5)
            self.assertEqual((cfg["anchor_wall"], cfg["anchor_world_minute"]), (NOW + 5, 480))
            self.assertIsNone(cfg["last_tick_wall"])
            self.assertFalse(cfg["enabled"])
            self.assertTrue(cfg["paused"])
            self._enable(conn)
            rc.commit_tick(conn, rc.plan_catch_up(rc.get_config(conn), now_wall=NOW + 600, world_abs_now=480),
                           now_wall=NOW + 600)
            self.assertEqual(rc.get_config(conn)["last_tick_wall"], NOW + 600)
            cfg = rc.reset_anchor(conn, now_wall=NOW + 700, world_abs_now=480)
            self.assertEqual((cfg["anchor_wall"], cfg["anchor_world_minute"]), (NOW + 700, 480))
            self.assertIsNone(cfg["last_tick_wall"])
            self.assertTrue(cfg["enabled"])
            self.assertFalse(cfg["paused"])

    def test_update_ratio_reanchors_running_clock(self):
        with connect() as conn:
            self._enable(conn)
            # 600 real seconds at ratio 12 reached world minute 600; the new ratio starts from there.
            cfg = rc.update_config(conn, {"ratio": 24.0}, now_wall=NOW + 600)
            self.assertEqual((cfg["anchor_wall"], cfg["anchor_world_minute"]), (NOW + 600, 600))
            self.assertEqual(cfg["ratio"], 24.0)
            self.assertEqual(rc.elapsed_world_minutes(cfg, NOW + 600), 0)
            self.assertEqual(rc.elapsed_world_minutes(cfg, NOW + 900), 120)
            # the same ratio again, or a slice change, does not move the anchor
            same = rc.update_config(conn, {"ratio": 24.0, "slice_minutes": 10}, now_wall=NOW + 2000)
            self.assertEqual((same["anchor_wall"], same["anchor_world_minute"]), (NOW + 600, 600))
            # a paused clock keeps its anchor on a ratio change
            rc.pause(conn, now_wall=NOW + 2000)
            paused = rc.update_config(conn, {"ratio": 1.0}, now_wall=NOW + 3000)
            self.assertEqual((paused["anchor_wall"], paused["anchor_world_minute"]), (NOW + 600, 600))

    def test_disable_pauses_with_reason(self):
        with connect() as conn:
            self._enable(conn)
            off = rc.update_config(conn, {"enabled": False}, now_wall=NOW + 10)
            self.assertFalse(off["enabled"])
            self.assertTrue(off["paused"])
            self.assertEqual(off["pause_reason"], "disabled")
            on = rc.update_config(conn, {"enabled": True}, now_wall=NOW + 20)
            self.assertTrue(on["paused"])
            self.assertEqual(on["pause_reason"], "")

    def test_commit_tick_rules(self):
        with connect() as conn:
            self._enable(conn)
            cfg = rc.get_config(conn)
            # a busy skip writes nothing
            busy = rc.plan_catch_up(cfg, now_wall=NOW + 600, world_abs_now=480, busy=True)
            same = rc.commit_tick(conn, busy, now_wall=NOW + 600)
            self.assertEqual((same["anchor_wall"], same["anchor_world_minute"], same["last_tick_wall"]), (NOW, 480, None))
            # nothing_due with play ahead re-bases but is not a tick
            ahead = rc.plan_catch_up(cfg, now_wall=NOW + 600, world_abs_now=700)
            moved = rc.commit_tick(conn, ahead, now_wall=NOW + 600)
            self.assertEqual((moved["anchor_wall"], moved["anchor_world_minute"], moved["last_tick_wall"]), (NOW + 600, 700, None))
            # a tick moves the anchor and stamps last_tick_wall
            tick = rc.plan_catch_up(moved, now_wall=NOW + 1200, world_abs_now=700)
            self.assertEqual(tick["apply_minutes"], 120)
            done = rc.commit_tick(conn, tick, now_wall=NOW + 1200)
            self.assertEqual((done["anchor_wall"], done["anchor_world_minute"], done["last_tick_wall"]), (NOW + 1200, 820, NOW + 1200))
            # malformed plans are ignored
            self.assertEqual(rc.commit_tick(conn, {"status": "tick"}, now_wall=NOW + 1300), done)
            self.assertEqual(rc.commit_tick(conn, None, now_wall=NOW + 1300), done)  # type: ignore[arg-type]

    def test_catch_up_plan_only_writes_nothing(self):
        with connect() as conn:
            self._enable(conn)
            row_before = conn.execute("SELECT value FROM settings WHERE key = ?", (rc.SETTING_KEY,)).fetchone()["value"]
            pacing_before = _pacing(conn)
            report = rc.catch_up(conn, now_wall=NOW + 750, apply=None, busy=False)
            self.assertEqual(set(report), {"plan", "applied", "applied_minutes", "error", "config"})
            self.assertEqual(report["plan"]["status"], "tick")
            self.assertEqual([s["minutes"] for s in report["plan"]["slices"]], [60, 60, 30])
            self.assertEqual(report["applied"], [])
            self.assertEqual(report["applied_minutes"], 0)
            self.assertEqual(report["error"], "")
            self.assertEqual(report["config"], rc.get_config(conn))
            row_after = conn.execute("SELECT value FROM settings WHERE key = ?", (rc.SETTING_KEY,)).fetchone()["value"]
            self.assertEqual(row_before, row_after)
            self.assertEqual(_pacing(conn), pacing_before)
            self.assertEqual(_pacing(conn)["world_minute"], "480")

    def test_catch_up_applies_slices_in_order_and_commits(self):
        with connect() as conn:
            self._enable(conn)
            seen: list[int] = []

            def apply(item):
                _assert_slice(self, item)
                seen.append(item["minutes"])
                return {"ok": item["minutes"]}

            report = rc.catch_up(conn, now_wall=NOW + 750, apply=apply, busy=False)
            self.assertEqual(seen, [60, 60, 30])
            self.assertEqual(report["applied"], [{"ok": 60}, {"ok": 60}, {"ok": 30}])
            self.assertEqual(report["applied_minutes"], 150)
            self.assertEqual(report["error"], "")
            cfg = report["config"]
            self.assertEqual((cfg["anchor_wall"], cfg["anchor_world_minute"]), (NOW + 750, 630))
            self.assertEqual(cfg["last_tick_wall"], NOW + 750)
            self.assertEqual(rc.get_config(conn), cfg)
            # the stub moved nothing in pacing (the real writers run only through wait_effects), so the
            # same 150 minutes are still owed to the world
            self.assertEqual(_pacing(conn)["world_minute"], "480")
            owed = rc.catch_up(conn, now_wall=NOW + 750, apply=None, busy=False)
            self.assertEqual((owed["plan"]["status"], owed["plan"]["due_minutes"]), ("tick", 150))
            # once the world clock stands where the slices put it, a tick straight after owes nothing
            conn.execute("INSERT OR REPLACE INTO pacing (key, value) VALUES ('world_minute', '630')")
            again = rc.catch_up(conn, now_wall=NOW + 750, apply=apply, busy=False)
            self.assertEqual((again["plan"]["status"], again["plan"]["reason"]), ("skip", "nothing_due"))
            self.assertEqual(seen, [60, 60, 30])

    def test_catch_up_stops_on_apply_error_and_commits_done_slices(self):
        with connect() as conn:
            self._enable(conn)
            calls: list[int] = []

            def apply(item):
                calls.append(item["minutes"])
                if len(calls) == 2:
                    raise RuntimeError("regen failed")
                return item["minutes"]

            report = rc.catch_up(conn, now_wall=NOW + 750, apply=apply, busy=False)
            self.assertEqual(calls, [60, 60])
            self.assertEqual(report["applied"], [60])
            self.assertEqual(report["applied_minutes"], 60)
            self.assertEqual(report["error"], "RuntimeError: regen failed")
            cfg = report["config"]
            self.assertEqual(cfg["anchor_world_minute"], 540)
            self.assertEqual(cfg["last_tick_wall"], NOW + 750)
            # 90 minutes stay owed: at the same wall time the next plan asks for them again
            nxt = rc.plan_catch_up(cfg, now_wall=NOW + 750, world_abs_now=540)
            self.assertEqual(nxt["status"], "tick")
            self.assertEqual(nxt["due_minutes"], 90)
            self.assertEqual([s["minutes"] for s in nxt["slices"]], [60, 30])

    def test_catch_up_never_raises_when_busy_paused_or_disabled(self):
        with connect() as conn:
            called = []
            off = rc.catch_up(conn, now_wall=NOW, apply=called.append, busy=False)
            self.assertEqual((off["plan"]["status"], off["plan"]["reason"]), ("skip", "disabled"))
            rc.update_config(conn, {"enabled": True}, now_wall=NOW)
            paused = rc.catch_up(conn, now_wall=NOW, apply=called.append, busy=False)
            self.assertEqual((paused["plan"]["status"], paused["plan"]["reason"]), ("skip", "paused"))
            rc.resume(conn, now_wall=NOW, world_abs_now=480)
            busy = rc.catch_up(conn, now_wall=NOW + 600, apply=called.append, busy=True)
            self.assertEqual((busy["plan"]["status"], busy["plan"]["reason"]), ("skip", "busy"))
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('travel_ready', 'false')")
            held = rc.catch_up(conn, now_wall=NOW + 600, apply=called.append, busy=False)
            self.assertEqual((held["plan"]["status"], held["plan"]["reason"]), ("skip", "travel_pending"))
            conn.execute("DELETE FROM settings WHERE key = 'travel_ready'")
            self.assertEqual(called, [])
            cfg = rc.get_config(conn)
            self.assertEqual((cfg["anchor_wall"], cfg["anchor_world_minute"]), (NOW, 480))

    def test_catch_up_reads_turn_in_flight_when_busy_not_given(self):
        with connect() as conn:
            self._enable(conn)
            with mock.patch("app.realtime_clock.turn_in_flight", return_value=True) as flag:
                report = rc.catch_up(conn, now_wall=NOW + 600, apply=lambda item: item)
            self.assertEqual(flag.call_count, 1)
            self.assertEqual((report["plan"]["status"], report["plan"]["reason"]), ("skip", "busy"))

    def test_wait_effects_calls_the_three_writers_in_order(self):
        order: list[tuple] = []

        def fake_advance(conn, minutes):
            order.append(("advance_world_time", minutes))
            return {"advanced_minutes": minutes}

        def fake_regen(conn, *, minutes, kind, options):
            order.append(("apply_regen", minutes, kind, options))
            return {"minutes": minutes}

        def fake_roll(*, minutes, crowd, danger, seed):
            order.append(("roll_wait_events", minutes, crowd, danger, seed))
            return {"event_count": 0, "seed": seed}

        with connect() as conn:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('playthrough_options', ?)",
                         ('{"difficulty": "normal"}',))
            with mock.patch("app.world.advance_world_time", fake_advance), \
                    mock.patch("app.player_resources.apply_regen", fake_regen), \
                    mock.patch("app.world.roll_wait_events", fake_roll):
                apply = rc.wait_effects(conn)
                out = apply(rc.make_slice(60))
                self.assertEqual(set(out), {"time", "regen", "events"})
                self.assertEqual(out["time"], {"advanced_minutes": 60})
                self.assertEqual(out["regen"], {"minutes": 60})
                expected_seed = (480 * 10007) ^ (60 * 17)
                self.assertEqual(out["events"], {"event_count": 0, "seed": expected_seed})
                self.assertEqual(
                    order,
                    [("advance_world_time", 60),
                     ("apply_regen", 60, "wait", {"difficulty": "normal"}),
                     ("roll_wait_events", 60, rc.DEFAULT_CROWD, rc.DEFAULT_DANGER, expected_seed)],
                )
                order.clear()
                tuned = rc.wait_effects(conn, options={"difficulty": "hard"}, crowd=2.0, danger=-1.0, seed=7)
                tuned(rc.make_slice(30))
                self.assertEqual(order[1], ("apply_regen", 30, "wait", {"difficulty": "hard"}))
                self.assertEqual(order[2], ("roll_wait_events", 30, 1.0, 0.0, 7))
            # the stubs never touched the clock
            self.assertEqual(_pacing(conn)["world_minute"], "480")

    def test_state_view_shape(self):
        with connect() as conn:
            view = rc.state_view(conn, now_wall=NOW)
            self.assertEqual(set(view), {"realtime_clock"})
            inner = view["realtime_clock"]
            self.assertEqual(set(inner), {"enabled", "paused", "ratio", "preset", "pause_reason", "next_tick_seconds", "label"})
            self.assertEqual(inner["enabled"], False)
            self.assertEqual(inner["paused"], True)
            self.assertEqual(inner["ratio"], 12.0)
            self.assertEqual(inner["preset"], "day_in_two_hours")
            self.assertEqual(inner["pause_reason"], "")
            self.assertIsNone(inner["next_tick_seconds"])
            self.assertEqual(inner["label"], rc.describe(rc.get_config(conn)))
            self._enable(conn)
            running = rc.state_view(conn, now_wall=NOW + 100)["realtime_clock"]
            self.assertEqual(running["next_tick_seconds"], 200)
            self.assertEqual(running["label"], "One world day passes in 2.0 real hours (ratio 12.0). Running.")
            self.assertIsInstance(running["ratio"], float)
            self.assertIsInstance(running["next_tick_seconds"], int)

    def test_no_pacing_write_without_apply(self):
        with connect() as conn:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('travel_ready', 'true')")
            pacing_before = _pacing(conn)
            rc.update_config(conn, {"enabled": True, "ratio": "day_in_hour", "slice_minutes": 30}, now_wall=NOW)
            rc.resume(conn, now_wall=NOW, world_abs_now=480)
            rc.catch_up(conn, now_wall=NOW + 600, apply=None, busy=False)
            rc.pause(conn, reason="player", now_wall=NOW + 700)
            rc.resume(conn, now_wall=NOW + 800)
            rc.update_config(conn, {"ratio": 4.0}, now_wall=NOW + 900)
            rc.catch_up(conn, now_wall=NOW + 5000, apply=None, busy=False)
            rc.commit_tick(conn, rc.plan_catch_up(rc.get_config(conn), now_wall=NOW + 5000, world_abs_now=480),
                           now_wall=NOW + 5000)
            rc.reset_anchor(conn, now_wall=NOW + 6000)
            rc.state_view(conn, now_wall=NOW + 6000)
            self.assertEqual(_pacing(conn), pacing_before)
            self.assertEqual(_pacing(conn)["world_minute"], "480")
            self.assertEqual(conn.execute("SELECT value FROM settings WHERE key = 'travel_ready'").fetchone()["value"], "true")

    def test_no_foreign_writes(self):
        with connect() as conn:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('travel_ready', 'true')")
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('playthrough_options', '{}')")
            before = _table_counts(conn)
            settings_before = _settings_except_own(conn)
            pacing_before = _pacing(conn)
            rc.update_config(conn, {"enabled": True}, now_wall=NOW)
            rc.resume(conn, now_wall=NOW, world_abs_now=480)
            rc.catch_up(conn, now_wall=NOW + 750, apply=lambda item: item["minutes"], busy=False)
            rc.pause(conn, now_wall=NOW + 800)
            rc.reset_anchor(conn, now_wall=NOW + 900)
            rc.state_view(conn, now_wall=NOW + 900)
            after = _table_counts(conn)
        changed = {name for name in set(before) | set(after) if before.get(name) != after.get(name)}
        self.assertEqual(changed, {"settings"}, changed)
        self.assertEqual(after["settings"], before["settings"] + 1)  # the module's own row only
        with connect() as conn:
            self.assertEqual(_settings_except_own(conn), settings_before)
            self.assertEqual(_pacing(conn), pacing_before)
            for name in ("player", "inventory", "npcs", "journal", "locations", "pacing", "gm_events"):
                self.assertEqual(before.get(name), after.get(name), name)

    def test_import_has_no_side_effects(self):
        import subprocess

        code = (
            "import os, sys\n"
            "before = set(sys.modules)\n"
            "import app.realtime_clock as m\n"
            "assert not hasattr(m, 'advance_world_time')\n"
            "assert 'app.world' not in sys.modules, 'app.world must load lazily'\n"
            "assert not os.path.exists(os.environ['AI_RPG_DB']), 'import touched the database'\n"
            "print('ok', end='')\n"
        )
        env = dict(os.environ)
        env["AI_RPG_DB"] = str(_TMP / "import-probe.db")
        proc = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), env=env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "ok")


if __name__ == "__main__":
    unittest.main()
