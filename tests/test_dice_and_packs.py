"""
Regression tests for the dice authority, content packs, and the danger model.

Run:  python tests/test_dice_and_packs.py
"""
from __future__ import annotations

import json
import os
import random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Isolate every runtime path before importing app modules.
_TMP = Path(tempfile.mkdtemp(prefix="morkyn-dice-test-"))
_ENV = {
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
}
os.environ.update(_ENV)

from app import content_packs as packs  # noqa: E402
from app import encounters as enc  # noqa: E402
from app import rng  # noqa: E402
from app import skill_checks as sc  # noqa: E402
from app.db import connect, init_db  # noqa: E402
from app.world import resolve_turn_bands  # noqa: E402

# Isolation is a correctness requirement, not a convenience: these tests write
# locations, NPCs and rolls. Assert it took hold rather than trusting import
# order -- when the runtime paths were frozen at first import, running the whole
# suite sent these fixtures into the player's real data/world.db.
def _assert_isolated() -> None:
    from app.db import db_path
    import app.world as _world

    for label, value in (
        ("AI_RPG_DB", db_path()),
        ("AI_RPG_SOURCE_INDEX", _world.source_index_dir()),
        ("AI_RPG_HISTORY_SUMMARY", _world.history_summary_path()),
    ):
        if not str(value).startswith(str(_TMP)):
            raise AssertionError(
                f"test isolation failed: {label} resolves to {value!r}, "
                f"outside the temp dir {_TMP!r}"
            )


def setUpModule() -> None:
    """Re-pin this module's runtime paths before its tests run.

    unittest imports every test module up front, and the paths live in
    process-global environment variables -- so without this the module imported
    last owns the database while everyone else's tests execute against it.
    """
    os.environ.update(_ENV)
    _assert_isolated()


init_db()


class TestDiceNotation(unittest.TestCase):
    def test_parses_common_forms(self):
        r = random.Random(1)
        self.assertEqual(rng.roll_dice("5", r)["total"], 5)
        self.assertEqual(rng.roll_dice("-3", r)["total"], -3)
        d = rng.roll_dice("2d6+3", r)
        self.assertEqual(d["count"], 2)
        self.assertEqual(d["faces"], 6)
        self.assertTrue(5 <= d["total"] <= 15)

    def test_keep_highest_drops_dice(self):
        d = rng.roll_dice("4d6kh3", random.Random(7))
        self.assertEqual(len(d["rolls"]), 4)
        self.assertEqual(len(d["kept"]), 3)
        self.assertEqual(sorted(d["kept"], reverse=True), d["kept"])

    def test_rejects_garbage_and_absurd_dice(self):
        for bad in ("hello", "2d", "999d6", "1d99999", "d1"):
            with self.assertRaises(rng.DiceError, msg=bad):
                rng.roll_dice(bad, random.Random(0))

    def test_empty_notation_means_zero(self):
        """Band tables use "" / "0" for the `none` band; that must not raise."""
        for empty in ("", None, "0"):
            self.assertEqual(rng.roll_dice(empty, random.Random(0))["total"], 0)

    def test_validate_notation_matches_roll(self):
        self.assertTrue(rng.validate_notation("3d8-2"))
        self.assertFalse(rng.validate_notation("3d"))


class TestSeeding(unittest.TestCase):
    def test_seed_is_stable_across_calls(self):
        self.assertEqual(rng.seed_from("a", 1, "x"), rng.seed_from("a", 1, "x"))
        self.assertNotEqual(rng.seed_from("a", 1), rng.seed_from("a", 2))

    def test_same_seed_reproduces_the_same_roll(self):
        first = rng.resolve_magnitude("xp", "large", seed=1234, turn=7, tag="t")
        second = rng.resolve_magnitude("xp", "large", seed=1234, turn=7, tag="t")
        self.assertEqual(first["value"], second["value"])
        self.assertEqual(first["rolls"], second["rolls"])


class TestBands(unittest.TestCase):
    def test_normalizes_synonyms_and_junk(self):
        self.assertEqual(rng.normalize_band("MAJOR"), "large")
        self.assertEqual(rng.normalize_band("a small gain"), "small")
        self.assertEqual(rng.normalize_band(None), "none")
        self.assertEqual(rng.normalize_band("gibberish"), "none")

    def test_bands_are_monotonic(self):
        """A larger band must not produce a smaller average amount."""
        averages = []
        for band in rng.BANDS:
            total = sum(
                rng.resolve_magnitude("xp", band, seed=i, tag=band)["value"]
                for i in range(60)
            )
            averages.append(total / 60.0)
        self.assertEqual(averages, sorted(averages), f"bands not ordered: {averages}")

    def test_none_band_is_always_zero(self):
        for kind in rng.known_magnitude_kinds():
            self.assertEqual(rng.resolve_magnitude(kind, "none", seed=3)["value"], 0, kind)

    def test_negative_band_produces_a_loss(self):
        """Regression: clamping after negation zeroed every loss on floor-0 tables."""
        for kind in ("damage", "heal", "item_count", "fame", "gold", "karma"):
            roll = rng.resolve_magnitude(kind, "moderate", negative=True, seed=11, tag=kind)
            self.assertLess(roll["value"], 0, f"{kind} negative band did not go below zero")

    def test_level_scaling_raises_scaled_kinds_only(self):
        low = sum(rng.resolve_magnitude("xp", "moderate", level=1, seed=i)["value"] for i in range(40))
        high = sum(rng.resolve_magnitude("xp", "moderate", level=20, seed=i)["value"] for i in range(40))
        self.assertGreater(high, low)
        # item_count has scale "none" and must ignore level entirely.
        flat_low = rng.resolve_magnitude("item_count", "small", level=1, seed=5)["value"]
        flat_high = rng.resolve_magnitude("item_count", "small", level=20, seed=5)["value"]
        self.assertEqual(flat_low, flat_high)

    def test_difficulty_and_growth_speed_move_rewards(self):
        easy = sum(rng.resolve_magnitude("xp", "large", difficulty="easy", seed=i)["value"] for i in range(40))
        brutal = sum(rng.resolve_magnitude("xp", "large", difficulty="brutal", seed=i)["value"] for i in range(40))
        self.assertGreater(easy, brutal)
        slow = rng.resolve_magnitude("xp", "large", options={"xp_growth_speed": "very_slow"}, seed=2)["value"]
        fast = rng.resolve_magnitude("xp", "large", options={"xp_growth_speed": "very_fast"}, seed=2)["value"]
        self.assertGreater(fast, slow)

    def test_numbers_map_back_to_sensible_bands(self):
        self.assertEqual(rng.band_from_number("xp", 0), "none")
        self.assertEqual(rng.band_from_number("xp", 250), "huge")
        self.assertIn(rng.band_from_number("gold", 6), ("trivial", "small"))


class TestTurnBandResolution(unittest.TestCase):
    def test_bands_become_numbers(self):
        turn = {
            "player": {"xp_band": "moderate", "gold_band": "small"},
            "inventory_changes": [{"name": "Rope", "quantity_band": "small"}],
            "npcs": [{"code": "A", "trust_band": "small"}],
            "events": [{"title": "Rescue", "fame_band": "moderate"}],
            "skill_changes": [{"name": "Climbing", "delta_band": "small"}],
        }
        with connect() as conn:
            report = resolve_turn_bands(conn, turn, turn=1, options={})
        self.assertEqual(report["mode"], "rolled")
        self.assertGreater(turn["player"]["xp_delta"], 0)
        self.assertGreater(turn["player"]["gold_delta"], 0)
        self.assertGreater(turn["inventory_changes"][0]["quantity_delta"], 0)
        self.assertGreater(turn["npcs"][0]["trust_delta"], 0)
        self.assertGreater(turn["events"][0]["fame_score"], 0)
        self.assertGreater(turn["skill_changes"][0]["delta"], 0)
        # Band keys are consumed so nothing downstream sees both forms.
        self.assertNotIn("xp_band", turn["player"])
        self.assertNotIn("quantity_band", turn["inventory_changes"][0])

    def test_negative_band_damages_the_player(self):
        turn = {"player": {"health_band": "-moderate"}}
        with connect() as conn:
            resolve_turn_bands(conn, turn, turn=2, options={})
        self.assertLess(turn["player"]["health_delta"], 0)

    def test_raw_numbers_are_rerolled_onto_the_curve(self):
        turn = {"player": {"xp_delta": 5000}}
        with connect() as conn:
            resolve_turn_bands(conn, turn, turn=3, options={})
        self.assertLessEqual(turn["player"]["xp_delta"], 500)
        self.assertGreater(turn["player"]["xp_delta"], 0)

    def test_off_mode_leaves_numbers_alone(self):
        os.environ["AI_RPG_BAND_AUTHORITY"] = "off"
        try:
            turn = {"player": {"xp_delta": 250}}
            with connect() as conn:
                resolve_turn_bands(conn, turn, turn=4, options={})
            self.assertEqual(turn["player"]["xp_delta"], 250)
        finally:
            os.environ.pop("AI_RPG_BAND_AUTHORITY", None)

    def test_does_not_open_a_second_connection_mid_transaction(self):
        """
        Regression: campaign_seed() opening its own connection while apply_turn
        held a write transaction made SQLite block on its busy timeout, turning
        a 1.9s benchmark into a 117s one. Resolving many bands under one open
        connection must stay fast.
        """
        import time

        turn = {
            "player": {"xp_band": "small", "gold_band": "small",
                        "health_band": "-small", "karma_band": "small"},
            "inventory_changes": [{"name": f"Item {i}", "quantity_band": "small"} for i in range(8)],
            "npcs": [{"code": "A", "trust_band": "small"}],
            "events": [{"title": "E", "fame_band": "small"}],
            "skill_changes": [{"name": "S", "delta_band": "small"}],
        }
        started = time.time()
        with connect() as conn:
            conn.execute("UPDATE player SET gold = gold WHERE id = 1")  # hold a write lock
            report = resolve_turn_bands(conn, turn, turn=500, options={})
        elapsed = time.time() - started
        self.assertGreaterEqual(len(report["rolls"]), 12)
        self.assertLess(elapsed, 2.0, f"band resolution blocked on SQLite for {elapsed:.1f}s")

    def test_rolls_are_written_to_the_audit_table(self):
        turn = {"player": {"xp_band": "large"}}
        with connect() as conn:
            resolve_turn_bands(conn, turn, turn=99, options={})
        rolls = rng.recent_rolls(limit=10, turn=99)
        self.assertTrue(rolls)
        self.assertEqual(rolls[0]["kind"], "xp")
        self.assertEqual(rolls[0]["band"], "large")


class TestBandsSurviveThePipeline(unittest.TestCase):
    """
    Bands have to survive every filter between the model and apply_turn.

    Found live on a 7B: the handoff cleanup allowlist did not list the band
    fields, so it stripped them before the world layer could roll them. The
    model asked for XP and got nothing, silently.
    """

    def test_handoff_cleanup_keeps_band_fields(self):
        from app.llm import _clean_player_delta_for_handoff

        cleaned = _clean_player_delta_for_handoff(
            {
                "xp_band": "small",
                "gold_band": "-trivial",
                "health_band": "-moderate",
                "karma_band": "small",
                "karma_reason": "helped a stranger",
            }
        )
        for field in ("xp_band", "gold_band", "health_band", "karma_band"):
            self.assertIn(field, cleaned, f"{field} was stripped during handoff cleanup")

    def test_handoff_cleanup_still_keeps_legacy_numbers(self):
        from app.llm import _clean_player_delta_for_handoff

        cleaned = _clean_player_delta_for_handoff({"xp_delta": 5, "gold_delta": -2})
        self.assertEqual(cleaned["xp_delta"], 5)
        self.assertEqual(cleaned["gold_delta"], -2)

    def test_dsl_grant_band_becomes_a_real_item_quantity(self):
        """A GRANT with a band must not reach _apply_inventory as quantity 0."""
        from app.turn_dsl import parse_dsl_turn

        turn = parse_dsl_turn(
            '===NAR===\nA courier hands you a sealed packet.\n\n===OPS===\n'
            'GRANT "sealed packet" QTY small TYPE paper\n',
            "take the packet",
        )
        self.assertEqual(turn["inventory_changes"][0]["quantity_band"], "small")
        with connect() as conn:
            resolve_turn_bands(conn, turn, turn=600, options={})
        self.assertGreaterEqual(turn["inventory_changes"][0]["quantity_delta"], 1)


class TestServerAuthoredAmounts(unittest.TestCase):
    """
    Amounts the server already rolled must not be re-rolled as model guesses.

    Found live on a 7B: a skill-check injury of -1 HP was re-read as a band
    hint and re-rolled into an unrelated number.
    """

    def test_skill_check_injury_is_marked_server_authored(self):
        turn = {"player": {}}
        check = {
            "display_block": "roll",
            "injury": {"health_delta": -4, "limb": "leg", "summary": "hurt leg"},
        }
        merged = sc.apply_check_to_turn(turn, check)
        self.assertIn("player.health_delta", merged.get("_server_authored") or [])

    def test_server_authored_amount_passes_through_untouched(self):
        turn = {"player": {"health_delta": -4}, "_server_authored": ["player.health_delta"]}
        with connect() as conn:
            report = resolve_turn_bands(conn, turn, turn=601, options={})
        self.assertEqual(turn["player"]["health_delta"], -4)
        self.assertEqual(len(report["rolls"]), 0)

    def test_unmarked_amount_is_still_rerolled(self):
        turn = {"player": {"health_delta": -4}}
        with connect() as conn:
            report = resolve_turn_bands(conn, turn, turn=602, options={})
        self.assertEqual(len(report["rolls"]), 1)


class TestUnknownBandWords(unittest.TestCase):
    """A 7B invented "fresh" as a band; that silently deleted the change."""

    def test_invented_band_word_still_produces_a_change(self):
        for word in ("fresh", "modest", "decent"):
            turn = {"player": {"xp_band": word}}
            with connect() as conn:
                resolve_turn_bands(conn, turn, turn=603, options={})
            self.assertGreater(
                turn["player"].get("xp_delta", 0), 0, f"band {word!r} silently vanished"
            )

    def test_explicit_none_still_means_nothing(self):
        turn = {"player": {"xp_band": "none"}}
        with connect() as conn:
            resolve_turn_bands(conn, turn, turn=604, options={})
        self.assertEqual(turn["player"].get("xp_delta"), 0)


class TestPromptBudget(unittest.TestCase):
    """
    Measured on a live 7B: the full skill catalog shipped in every turn prompt
    at ~6.4KB (~1,600 tokens) while the model no longer picks skills, because
    checks resolve server-side. The catalog is now searched, not dumped.
    """

    def test_unfiltered_block_still_returns_everything(self):
        block = sc.gm_context_block(sc.default_check_settings())
        self.assertGreater(len(block["active_skills"]), 40)

    def test_query_filters_the_catalog_hard(self):
        cfg = sc.default_check_settings()
        full = len(json.dumps(sc.gm_context_block(cfg)))
        filtered = len(json.dumps(sc.gm_context_block(cfg, query="I pick the lock on the chest")))
        self.assertLess(filtered, full * 0.35, "filtered catalog should be far smaller")

    def test_search_finds_the_obvious_skill(self):
        cases = {
            "I pick the lock on the chest": "lockpicking",
            "I try to persuade the guard": "persuasion",
            "I sneak past the watchman": "stealth",
            "I bandage the wounded traveler": "healing",
            "I haggle over the price of rope": "appraise",
        }
        for query, expected in cases.items():
            codes = [s["code"] for s in sc.search_skills(query, limit=6)]
            self.assertIn(expected, codes, f"{query!r} -> {codes}")

    def test_filtered_block_always_offers_a_usable_fallback(self):
        """Even a nonsense action must leave the model a valid skill code."""
        block = sc.gm_context_block(sc.default_check_settings(), query="qqqq zzzz")
        self.assertTrue(block["active_skills"])
        self.assertIn("general", [s["code"] for s in block["active_skills"]])

    def test_disabled_dice_still_short_circuits(self):
        block = sc.gm_context_block({"dice_checks_enabled": False}, query="anything")
        self.assertEqual(block, {"dice_checks_enabled": False})


class TestVerificationSkipPolicy(unittest.TestCase):
    """
    On a 7B the model verifier failed on 42/42 turns, so anything that forced
    it was pure cost. Short narration and conversation records no longer do.
    """

    def test_short_narration_is_not_a_blocker(self):
        from app.llm import HIGH_RISK_TURN_CHANGE_KEYS, LOW_RISK_TURN_CHANGE_KEYS

        self.assertNotIn("conversations", HIGH_RISK_TURN_CHANGE_KEYS)
        self.assertIn("conversations", LOW_RISK_TURN_CHANGE_KEYS)

    def test_economy_changes_are_still_high_risk(self):
        from app.llm import HIGH_RISK_TURN_CHANGE_KEYS

        for key in ("inventory_changes", "skill_changes", "events", "ability_updates"):
            self.assertIn(key, HIGH_RISK_TURN_CHANGE_KEYS)


class TestVerifierCircuitBreaker(unittest.TestCase):
    """
    On qwen2.5:7b-instruct the verify pass echoed the input world_state back on
    42/42 turns and never once produced a corrected turn — ~26s per turn of
    pure cost. The breaker notices and stops calling it.
    """

    def setUp(self):
        import app.llm as llm

        llm.reset_verifier_breaker()

    tearDown = setUp

    def test_echoed_prompt_is_not_useful_output(self):
        import app.llm as llm

        draft = {"narration": "x" * 1200}
        self.assertFalse(llm._verified_output_is_useful({"world_state": {}}, draft))
        self.assertFalse(llm._verified_output_is_useful({"draft_turn": {}}, draft))
        self.assertFalse(llm._verified_output_is_useful({"unrelated": 1}, draft))
        self.assertFalse(llm._verified_output_is_useful("not a dict", draft))

    def test_real_corrected_turn_is_useful(self):
        import app.llm as llm

        draft = {"narration": "x" * 1200}
        self.assertTrue(
            llm._verified_output_is_useful({"narration": "y" * 1100, "turn_summary": "s"}, draft)
        )

    def test_breaker_trips_after_repeated_failures(self):
        import app.llm as llm

        self.assertFalse(llm.verifier_is_disabled())
        for _ in range(3):
            llm._note_verify_outcome(False, "echoed input")
        self.assertTrue(llm.verifier_is_disabled())
        self.assertIn("failed 3 times", llm.verifier_breaker_status()["reason"])

    def test_one_success_resets_the_breaker(self):
        import app.llm as llm

        for _ in range(3):
            llm._note_verify_outcome(False)
        self.assertTrue(llm.verifier_is_disabled())
        llm._note_verify_outcome(True)
        self.assertFalse(llm.verifier_is_disabled())
        self.assertEqual(llm.verifier_breaker_status()["failure_streak"], 0)

    def test_breaker_can_be_disabled_by_env(self):
        import app.llm as llm

        os.environ["AI_RPG_VERIFY_FAILURE_LIMIT"] = "0"
        try:
            for _ in range(10):
                llm._note_verify_outcome(False)
            self.assertFalse(llm.verifier_is_disabled(), "limit 0 must mean never trip")
        finally:
            os.environ.pop("AI_RPG_VERIFY_FAILURE_LIMIT", None)


class TestDepthRetryLength(unittest.TestCase):
    def test_prose_retry_respects_the_upper_bound(self):
        """A 7B asked for 'longer' returned 3351 chars against a 2400 ceiling."""
        import app.llm as llm

        turn = {"narration": "Short draft."}
        original_chat = llm._chat_text
        llm._chat_text = lambda *a, **k: "\n\n".join(["A paragraph of scene prose. " * 12] * 12)
        try:
            out = llm._retry_narration_prose({}, "act", turn, "sys", 10, [], "phase", None)
        finally:
            llm._chat_text = original_chat
        self.assertLessEqual(len(out["narration"]), llm.MAX_TURN_NARRATION_CHARS)
        self.assertGreater(len(out["narration"]), len(turn["narration"]))
        # Trimmed on a paragraph boundary, not mid-sentence.
        self.assertTrue(out["narration"].rstrip().endswith("."))


class TestDepthRetryPreservesState(unittest.TestCase):
    """
    The old depth retry regenerated the whole turn as JSON: it truncated
    mid-object on every 7B attempt (18/18) and could drop the draft's
    structured ops. The prose retry only replaces narration.
    """

    def test_prose_cleaner_strips_wrappers(self):
        from app.llm import _clean_retry_prose

        self.assertEqual(_clean_retry_prose("```\nHello there.\n```"), "Hello there.")
        self.assertEqual(_clean_retry_prose("===NAR===\nHello there.\n===OPS===\nXP small"), "Hello there.")
        self.assertEqual(_clean_retry_prose('{"narration": "Hello there."}'), "Hello there.")
        self.assertEqual(_clean_retry_prose("  Plain prose.  "), "Plain prose.")

    def test_prose_retry_keeps_structured_changes(self):
        """Regression: only narration may change, never the ops."""
        import app.llm as llm

        turn = {
            "narration": "Short.",
            "scene_plan": {"goal": "g", "focus_points": []},
            "inventory_changes": [{"name": "Rope", "quantity_band": "small"}],
            "player": {"xp_band": "small"},
            "turn_summary": "kept",
        }
        original_chat = llm._chat_text
        llm._chat_text = lambda *a, **k: "A much longer passage of prose. " * 40
        try:
            out = llm._retry_narration_prose({}, "act", turn, "sys", 10, [], "phase", None)
        finally:
            llm._chat_text = original_chat
        self.assertGreater(len(out["narration"]), len(turn["narration"]))
        self.assertEqual(out["inventory_changes"], turn["inventory_changes"])
        self.assertEqual(out["player"], turn["player"])
        self.assertEqual(out["turn_summary"], "kept")
        self.assertTrue(out["narration_segments"])

    def test_prose_retry_rejects_a_shorter_rewrite(self):
        import app.llm as llm

        turn = {"narration": "This draft is already reasonably long prose."}
        original_chat = llm._chat_text
        llm._chat_text = lambda *a, **k: "tiny"
        try:
            with self.assertRaises(llm.LlmError):
                llm._retry_narration_prose({}, "act", turn, "sys", 10, [], "phase", None)
        finally:
            llm._chat_text = original_chat


class TestContentPacks(unittest.TestCase):
    def setUp(self):
        for pack in packs.list_packs():
            if not pack["builtin"]:
                packs.remove_pack(pack["id"])

    def test_example_pack_validates(self):
        report = packs.validate_pack(packs.EXAMPLE_PACK)
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(report["counts"]["skills"], 1)

    def test_validation_reports_paths_and_fixes(self):
        report = packs.validate_pack(
            {
                "format": "wrong",
                "skills": [{"name": "X", "attribute": "luck", "base_dc": 99, "triggers": ["[bad("]}],
                "items": [{"name": "Y", "roll_profile": {"melee": 99}}],
            }
        )
        self.assertFalse(report["ok"])
        paths = {e["path"] for e in report["errors"]}
        self.assertIn("format", paths)
        self.assertIn("id", paths)
        self.assertIn("skills[0].attribute", paths)
        self.assertIn("skills[0].base_dc", paths)
        self.assertIn("skills[0].triggers[0]", paths)
        self.assertIn("items[0].roll_profile.melee", paths)
        for error in report["errors"]:
            self.assertTrue(error["message"])

    def test_install_then_remove_is_clean(self):
        packs.install_pack(packs.EXAMPLE_PACK)
        self.assertIn("poling", {s["code"] for s in sc.load_skill_library()})
        self.assertIn("AB_river_read", packs.active_powers())
        removed = packs.remove_pack("riverlands_kit")
        self.assertTrue(removed["removed"])
        self.assertEqual(removed["entries_removed"], 3)
        self.assertNotIn("poling", {s["code"] for s in sc.load_skill_library()})
        self.assertNotIn("AB_river_read", packs.active_powers())

    def test_pack_can_disable_a_builtin_skill(self):
        packs.install_pack(
            {
                "format": packs.PACK_FORMAT,
                "id": "killswitch",
                "skills": [
                    {"code": "gambling", "name": "Gambling", "attribute": "charisma", "enabled": False}
                ],
            }
        )
        self.assertIn("gambling", packs.disabled_skill_codes())
        self.assertIsNone(sc.infer_check_from_action("I wager on the cards"))

    def test_pack_triggers_route_actions(self):
        packs.install_pack(packs.EXAMPLE_PACK)
        inferred = sc.infer_check_from_action("I pole the barge upriver")
        self.assertIsNotNone(inferred)
        self.assertEqual(inferred["skill_code"], "poling")

    def test_pack_can_override_magnitude_tables(self):
        packs.install_pack(
            {
                "format": packs.PACK_FORMAT,
                "id": "rich_world",
                "magnitude_tables": {"gold": {"bands": {"small": "100"}}},
            }
        )
        packs.apply_active_packs()
        try:
            roll = rng.resolve_magnitude("gold", "small", seed=1)
            self.assertGreaterEqual(roll["value"], 50)
        finally:
            packs.remove_pack("rich_world")
            packs.apply_active_packs()

    def test_authoring_bundle_is_self_contained(self):
        bundle = packs.authoring_bundle()
        for key in ("format", "hard_rules", "field_reference", "example_pack", "bands", "stat_keys"):
            self.assertIn(key, bundle)
        # The bundle's own example must satisfy the bundle's own rules.
        self.assertTrue(packs.validate_pack(bundle["example_pack"])["ok"])

    def test_shipped_example_file_matches_the_spec(self):
        path = ROOT / "content" / "pack-examples" / "riverlands_kit.json"
        self.assertTrue(path.is_file(), "example pack template is missing")
        self.assertTrue(packs.validate_pack(json.loads(path.read_text(encoding="utf-8")))["ok"])


class TestGearAffectsRolls(unittest.TestCase):
    def test_equipped_item_and_power_shift_the_check(self):
        packs.install_pack(packs.EXAMPLE_PACK)
        try:
            inventory = [
                {
                    "code": "I1",
                    "name": "Ironshod River Pole",
                    "equipped_slot": "main_hand",
                    "roll_profile": json.dumps({"poling": 2}),
                    "power_codes": json.dumps(["AB_river_read"]),
                }
            ]
            gear = sc.gear_roll_modifiers(inventory, [])
            # +2 from the item, +2 more from the power it grants.
            self.assertEqual(gear["modifiers"]["poling"], 4)
            self.assertEqual(gear["modifiers"]["navigation"], 1)
        finally:
            packs.remove_pack("riverlands_kit")

    def test_unequipped_gear_does_nothing(self):
        inventory = [
            {"name": "Sword", "equipped_slot": "", "roll_profile": json.dumps({"melee": 3})}
        ]
        self.assertEqual(sc.gear_roll_modifiers(inventory, [])["modifiers"], {})

    def test_check_total_includes_gear(self):
        inventory = [
            {"name": "Sword", "equipped_slot": "main_hand", "roll_profile": json.dumps({"melee": 3})}
        ]
        with_gear = sc.resolve_check(
            skill_code="melee",
            player_stats={},
            player_skills=[],
            inventory=inventory,
            settings={"dice_checks_enabled": True},
            rng=random.Random(4),
        )
        without = sc.resolve_check(
            skill_code="melee",
            player_stats={},
            player_skills=[],
            settings={"dice_checks_enabled": True},
            rng=random.Random(4),
        )
        self.assertEqual(with_gear["gear_mod"], 3)
        self.assertEqual(with_gear["total"] - without["total"], 3)


class TestDangerModel(unittest.TestCase):
    EXPERT = {
        "player": {"level": 12, "health": 30, "max_health": 30, "karma": 50,
                    "effective_stats": {"wisdom": 16, "dexterity": 14}},
        "skills": [{"name": "Perception", "value": 6}],
        "resources": {"energy": 20, "max_energy": 20, "fatigue": 0, "max_fatigue": 20},
        "inventory_summary": {"weight_capacity": 60, "effective_weight": 10},
    }
    NOVICE = {
        "player": {"level": 2, "health": 6, "max_health": 24, "karma": -450,
                    "effective_stats": {"wisdom": 7, "dexterity": 8}},
        "skills": [],
        "resources": {"energy": 3, "max_energy": 20, "fatigue": 17, "max_fatigue": 20},
        "inventory_summary": {"weight_capacity": 60, "effective_weight": 58},
    }
    CLEAR = {"kind": "clear", "strength": 0}
    STORM = {"kind": "storm", "strength": 0.9}

    def test_terrain_orders_risk(self):
        def danger(terrain):
            return enc.assess_danger(terrain=terrain, weather=self.CLEAR,
                                     world_time={"hour": 12}, **self.EXPERT)["danger"]

        self.assertLess(danger("town"), danger("forest"))
        self.assertLess(danger("forest"), danger("dungeon"))

    def test_weather_and_night_raise_risk(self):
        base = enc.assess_danger(terrain="forest", weather=self.CLEAR,
                                 world_time={"hour": 12}, **self.EXPERT)["danger"]
        stormy = enc.assess_danger(terrain="forest", weather=self.STORM,
                                   world_time={"hour": 12}, **self.EXPERT)["danger"]
        night = enc.assess_danger(terrain="forest", weather=self.CLEAR,
                                  world_time={"hour": 2}, **self.EXPERT)["danger"]
        self.assertGreater(stormy, base)
        self.assertGreater(night, base)

    def test_player_condition_changes_risk_on_identical_ground(self):
        expert = enc.assess_danger(terrain="forest", weather=self.CLEAR,
                                   world_time={"hour": 12}, **self.EXPERT)
        novice = enc.assess_danger(terrain="forest", weather=self.CLEAR,
                                   world_time={"hour": 12}, **self.NOVICE)
        self.assertEqual(expert["environment"], novice["environment"])
        self.assertGreater(novice["danger"], expert["danger"] * 2)

    def test_skills_reduce_but_never_eliminate_risk(self):
        """A great scout in a dungeon is still in a dungeon."""
        assessment = enc.assess_danger(terrain="dungeon", weather=self.CLEAR,
                                       world_time={"hour": 12}, **self.EXPERT)
        self.assertGreater(assessment["danger"], 0.1)
        self.assertLess(assessment["player_multiplier"], 1.0)

    def test_multiplier_does_not_saturate_for_ordinary_penalties(self):
        novice = enc.assess_danger(terrain="town", weather=self.CLEAR,
                                   world_time={"hour": 12}, **self.NOVICE)
        self.assertLess(novice["player_multiplier"], 2.6, "damping should leave headroom")

    def test_exposure_compounds_with_time(self):
        assessment = enc.assess_danger(terrain="forest", weather=self.CLEAR,
                                       world_time={"hour": 12}, **self.NOVICE)
        short = enc.roll_encounter(assessment, minutes=5, seed=1)["chance"]
        long = enc.roll_encounter(assessment, minutes=480, seed=1)["chance"]
        self.assertGreater(long, short)

    def test_encounter_rolls_counts_instead_of_asking_the_model(self):
        assessment = enc.assess_danger(terrain="dungeon", weather=self.STORM,
                                       world_time={"hour": 2}, **self.NOVICE)
        for seed in range(30):
            result = enc.roll_encounter(assessment, minutes=240, seed=seed, player={"level": 2})
            if result.get("happened"):
                self.assertGreaterEqual(result["count"], 1)
                self.assertIn("awareness", result)
                self.assertIn(result["surprise"], ("forewarned", "surprised"))
                self.assertIn("count_roll", result)
                return
        self.fail("no encounter fired in 30 attempts on deadly ground")

    def test_pack_can_override_terrain_tables(self):
        packs.install_pack(
            {
                "format": packs.PACK_FORMAT,
                "id": "peaceful_woods",
                "encounter_tables": {
                    "terrain": {"forest": {"base_chance": 0.01, "kinds": {"traveler": 100}}}
                },
            }
        )
        try:
            assessment = enc.assess_danger(terrain="forest", weather=self.CLEAR,
                                           world_time={"hour": 12}, **self.EXPERT)
            self.assertLess(assessment["base"], 0.05)
        finally:
            packs.remove_pack("peaceful_woods")

    def test_factors_explain_the_score(self):
        assessment = enc.assess_danger(terrain="swamp", weather=self.STORM,
                                       world_time={"hour": 2}, area_reputation=-60, **self.NOVICE)
        names = {f["name"] for f in assessment["factors"]}
        self.assertTrue({"terrain", "weather", "night", "fatigue", "infamy"} <= names, names)
        block = enc.danger_context_block(assessment)
        self.assertTrue(block["reasons"])
        self.assertNotIn("danger", json.dumps(block).lower().split('"note"')[0].replace("danger", "", 1))


if __name__ == "__main__":
    unittest.main(verbosity=2)
