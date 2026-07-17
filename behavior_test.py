"""
Regression tests for hierarchical memory, token budget, and source scoring.
Run: python behavior_test.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

temp_dir = tempfile.mkdtemp(prefix="airpg_behavior_")
db_path = os.path.join(temp_dir, "test_world.db")
source_index_dir = os.path.join(temp_dir, "source_index")
history_summary_path = os.path.join(temp_dir, "history_summaries.jsonl")
consolidated_path = os.path.join(temp_dir, "consolidated_facts.jsonl")
slots_dir = os.path.join(temp_dir, "campaign_slots")
os.makedirs(source_index_dir, exist_ok=True)

os.environ["AI_RPG_DB"] = db_path
os.environ["AI_RPG_SOURCE_INDEX"] = source_index_dir
os.environ["AI_RPG_HISTORY_SUMMARY"] = history_summary_path
os.environ["AI_RPG_CONSOLIDATED_FACTS"] = consolidated_path
os.environ["AI_RPG_CAMPAIGN_SLOTS"] = slots_dir
os.environ["AI_RPG_MEMORY_KEEP_SUMMARIES"] = "3"
os.environ["AI_RPG_MEMORY_MAX_FACTS"] = "50"

passed = 0
failed = 0


def test(name: str, fn) -> None:
    global passed, failed
    try:
        fn()
        passed += 1
        print(f"  PASS: {name}")
    except Exception as exc:
        failed += 1
        print(f"  FAIL: {name}: {exc}")


def main() -> int:
    print("Importing app modules under temp data paths...")
    from app import db
    from app import llm
    from app import world

    db.init_db()

    def test_source_scoring_prefers_recency_and_importance():
        query = {"oath", "tower", "aldric"}
        recent = {
            "kind": "event",
            "code": "E9",
            "title": "Aldric oath",
            "text": "Aldric swore an oath at the ruined tower.",
            "turn": 40,
            "importance": 0.7,
        }
        old = {
            "kind": "item",
            "code": "I1",
            "title": "Apples",
            "text": "A merchant sold apples long ago.",
            "turn": 1,
            "importance": 0.3,
        }
        high = world._score_source_record(query, recent, current_turn=42)
        low = world._score_source_record(query, old, current_turn=42)
        assert high > low, f"expected recent/important score higher ({high} vs {low})"

    def test_consolidate_memory_rolls_old_summaries():
        with db.connect() as conn:
            conn.execute("DELETE FROM turn_summaries")
            for turn in range(1, 8):
                conn.execute(
                    "INSERT INTO turn_summaries (turn, summary) VALUES (?, ?)",
                    (turn, f"Turn {turn}: the party discovered a secret alliance and accepted a quest near the tower."),
                )
            conn.execute(
                "INSERT INTO pacing (key, value) VALUES ('turn', '7') ON CONFLICT(key) DO UPDATE SET value = excluded.value"
            )
        result = world.consolidate_memory(keep_recent_summaries=3, max_facts=50)
        assert result.get("skipped") is False, result
        assert int(result.get("facts_added") or 0) > 0, result
        facts = world._load_consolidated_facts()
        assert len(facts) > 0
        assert CONSOLIDATED_FACTS_PATH_EXISTS()

    def CONSOLIDATED_FACTS_PATH_EXISTS() -> bool:
        return Path(consolidated_path).exists() and Path(consolidated_path).stat().st_size > 0

    def test_consolidate_is_idempotent_for_same_turns():
        first = world.consolidate_memory(keep_recent_summaries=3, max_facts=50)
        second = world.consolidate_memory(keep_recent_summaries=3, max_facts=50)
        assert first.get("skipped") is False or first.get("facts_total", 0) >= 0
        assert int(second.get("facts_added") or 0) == 0, second

    def test_token_budget_passes_small_prompts():
        system, user, diag = llm.enforce_token_budget("You are the GM.", "What happens next?", max_input_tokens=8000, reserve_output_tokens=500)
        assert system.startswith("You are")
        assert "next" in user
        assert diag.get("within_budget") is True
        assert diag.get("pruned") is False

    def test_token_budget_prunes_large_user_prompt():
        huge = "A" * 50000
        system, user, diag = llm.enforce_token_budget("sys", huge, max_input_tokens=2000, reserve_output_tokens=200)
        assert len(user) < len(huge)
        assert "truncated by enforce_token_budget" in user
        assert diag.get("pruned") is True
        assert diag.get("within_budget") is True

    def test_campaign_slot_round_trip_requires_exportable_state():
        # Minimal setup so export/import works if playthrough tables exist
        with db.connect() as conn:
            conn.execute(
                "INSERT INTO locations (code, name, summary) VALUES ('L1', 'Crossroads', 'A quiet fork.') "
                "ON CONFLICT(code) DO UPDATE SET name=excluded.name"
            )
            loc = conn.execute("SELECT id FROM locations WHERE code = 'L1'").fetchone()
            loc_id = loc["id"] if loc else 1
            conn.execute(
                """
                INSERT INTO player (id, name, current_location_id, health, max_health, level, xp, gold, karma)
                VALUES (1, 'Tester', ?, 10, 10, 1, 0, 0, 0)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name, current_location_id=excluded.current_location_id
                """,
                (loc_id,),
            )
            conn.execute(
                "INSERT INTO settings (key, value) VALUES ('setup_complete', 'true') "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value"
            )
            conn.execute(
                "INSERT INTO gm_notes (id, content) VALUES (1, '') ON CONFLICT(id) DO NOTHING"
            )
        meta = world.save_campaign_slot("unit_test_slot")
        assert meta.get("slot") == "unit_test_slot"
        slots = world.list_campaign_slots()
        assert any(item.get("slot") == "unit_test_slot" for item in slots)
        world.load_campaign_slot("unit_test_slot")
        world.delete_campaign_slot("unit_test_slot")
        slots_after = world.list_campaign_slots()
        assert all(item.get("slot") != "unit_test_slot" for item in slots_after)

    def test_context_health_shape():
        health = world.get_context_health()
        assert "model_budget" in health
        assert "memory" in health
        assert "gm_events" in health
        assert "campaign_slots" in health

    print("Behavior tests")
    test("source scoring prefers recency + importance", test_source_scoring_prefers_recency_and_importance)
    test("consolidate_memory rolls old summaries into facts", test_consolidate_memory_rolls_old_summaries)
    test("consolidate_memory is idempotent for already-rolled turns", test_consolidate_is_idempotent_for_same_turns)
    test("enforce_token_budget allows small prompts", test_token_budget_passes_small_prompts)
    test("enforce_token_budget prunes huge user prompts", test_token_budget_prunes_large_user_prompt)
    test("campaign slot save/load/delete", test_campaign_slot_round_trip_requires_exportable_state)
    test("context health diagnostics shape", test_context_health_shape)

    print(f"\nPassed: {passed}")
    print(f"Failed: {failed}")
    try:
        shutil.rmtree(temp_dir)
    except OSError:
        pass
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
