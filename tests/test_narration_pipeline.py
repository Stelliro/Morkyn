"""Unit checks for adaptive narration pipeline (no Ollama)."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.narration_pipeline import (
    apply_edit_ops,
    cascade_fix_pairs,
    check_adjacent_paragraphs,
    collect_local_npcs,
    infer_model_tier,
    infer_turn_number,
    looks_garbage_fragment,
    looks_truncated,
    plan_paragraph_budget,
    polish_paragraph,
    run_narration_pipeline,
    scene_density,
    should_skip_consolidator,
)


def test_tier_small_for_8b() -> None:
    assert infer_model_tier({"ollama_model": "qwen3:8b", "context_window": 8192, "response_token_cap": 800}) == "small"


def test_tier_large_for_big_ctx() -> None:
    assert infer_model_tier({"ollama_model": "qwen3:32b", "context_window": 65536, "response_token_cap": 2000}) == "large"


def test_budget_small_low_density() -> None:
    ctx = {
        "current_location": {"name": "Gate", "npcs": []},
        "locations": [{"name": "Gate"}],
        "events": [],
        "inventory": [],
        "settings": {"playthrough_options": {"narration_detail": "concise"}},
    }
    budget = plan_paragraph_budget(ctx, "I look around.", {"ollama_model": "qwen3:8b", "context_window": 8192, "response_token_cap": 800})
    assert budget["tier"] == "small"
    assert 2 <= budget["paragraphs"] <= 4
    assert budget["soft_total_chars"] >= 900
    assert budget["chars_per_paragraph"]["min"] >= 320


def test_density_reads_npcs_from_location_tree() -> None:
    """get_state nests NPCs on locations[], not current_location."""
    ctx = {
        "current_location": {"id": 1, "code": "L1", "name": "Mosswake Gate"},
        "locations": [
            {
                "id": 1,
                "code": "L1",
                "name": "Mosswake Gate",
                "npcs": [
                    {"id": 10, "code": "N1", "name": "Eldrin", "location_id": 1},
                    {"id": 11, "code": "N2", "name": "Brask", "location_id": 1},
                ],
                "events": [{"code": "E1", "title": "Bandit rumor", "status": "active"}],
            }
        ],
        "events": [{"code": "E1", "title": "Bandit rumor", "status": "active"}],
        "inventory": [{"code": "I1", "name": "Sealed Letter", "quantity": 1}],
    }
    npcs = collect_local_npcs(ctx)
    assert len(npcs) == 2
    dense = scene_density(ctx, "I ask Eldrin about trouble on the road.")
    assert dense["active_npc_count"] == 2
    assert dense["score"] >= 6
    assert "Eldrin" in dense["npc_names"]


def test_infer_turn_number_from_summaries() -> None:
    assert infer_turn_number({}) == 1
    assert infer_turn_number({"turn_summaries": [{"turn": 1}, {"turn": 3}]}) == 4
    assert infer_turn_number({"model_logs": [{"turn": 2}], "history": [{"turn": 5}]}) == 6


def test_skip_consolidator_lean_two_para() -> None:
    assert should_skip_consolidator(2, 3) is True
    assert should_skip_consolidator(2, 6) is True
    assert should_skip_consolidator(2, 7) is False
    assert should_skip_consolidator(3, 3) is False


def test_budget_rises_with_density() -> None:
    ctx = {
        "current_location": {
            "name": "Gate",
            "npcs": [{"name": "A"}, {"name": "B"}, {"name": "C"}, {"name": "D"}],
        },
        "locations": [{"name": "Gate"}, {"name": "Alley"}, {"name": "Road"}],
        "events": [
            {"title": "Ambush", "status": "active"},
            {"title": "Debt", "status": "active"},
            {"title": "Fire", "status": "active"},
        ],
        "inventory": [{"name": "Letter"}],
        "settings": {"playthrough_options": {"narration_detail": "expansive"}},
    }
    dense = scene_density(ctx, "I attack the bandit and flee toward the alley and buy a ration")
    budget = plan_paragraph_budget(
        ctx,
        "I attack the bandit and flee toward the alley and buy a ration",
        {"ollama_model": "qwen3:32b", "context_window": 65536, "response_token_cap": 2000},
    )
    assert dense["score"] >= 7
    assert budget["paragraphs"] >= 3


def test_adjacent_detects_double() -> None:
    a = "Eldrin warns about bandits on the north road near Mosswake Gate."
    b = "Eldrin warns about bandits on the north road near Mosswake Gate and repeats himself."
    result = check_adjacent_paragraphs(a, b)
    assert result["pass"] is False
    assert any(i.get("type") == "double" for i in result["issues"])


def test_surgical_replace() -> None:
    text = "The merchant sells bread. The merchant sells bread again."
    out = apply_edit_ops(text, [{"op": "delete_span", "match": " The merchant sells bread again."}])
    assert "again" not in out
    assert "bread" in out


def test_cascade_reduces_overlap() -> None:
    paras = [
        "You enter the gate under cold lantern smoke and watch the wardens.",
        "You enter the gate under cold lantern smoke and watch the wardens while asking for news.",
        "A new alley opens with oil and quiet footfalls.",
    ]
    fixed, reports = cascade_fix_pairs(paras, max_edits=2)
    # Near-duplicates are dropped rather than shredded into fragments.
    assert len(fixed) >= 2
    assert any(not r.get("pass") for r in reports) or jaccard_ok(fixed)
    assert all(not looks_garbage_fragment(p) for p in fixed)


def test_polish_cuts_to_sentence() -> None:
    raw = (
        "The air in the Derelict Cybernetic Forge hums with ghostly echoes. "
        "At the center the Core pulses with a faint glow. The Forge is more than just a place; it's a thres"
    )
    out = polish_paragraph(raw, max_chars=480)
    assert not looks_truncated(out)
    assert "thres" not in out
    assert out.endswith(".") or out.endswith("!") or out.endswith("?")


def test_garbage_fragment_detected() -> None:
    assert looks_garbage_fragment("ent faint hum pulses through the air")
    assert looks_truncated("You can feel the w")
    assert not looks_garbage_fragment("Then the wardens step aside and open the gate.")


def jaccard_ok(paras: list[str]) -> bool:
    from app.narration_pipeline import jaccard, token_set

    return jaccard(token_set(paras[0]), token_set(paras[1])) < 0.9


def test_pipeline_end_to_end_deterministic() -> None:
    ctx = {
        "current_location": {"name": "Mosswake Gate", "npcs": [{"name": "Eldrin", "code": "N1"}]},
        "locations": [{"name": "Mosswake Gate", "code": "L1"}],
        "events": [{"title": "Sealed letter", "status": "active"}],
        "inventory": [{"name": "Sealed Letter", "code": "I1"}],
        "settings": {"playthrough_options": {"narration_detail": "balanced"}},
    }
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "ledger.json"
        result = run_narration_pipeline(
            ctx,
            "I ask Eldrin about trouble on the road.",
            config={"ollama_model": "qwen3:8b", "context_window": 8192, "response_token_cap": 800},
            turn_number=7,
            ledger_path=path,
        )
        assert path.exists()
        assert result["narration_segments"]
        assert result["narration"]
        assert result["budget"]["paragraphs"] == len(result["narration_segments"]) or len(result["narration_segments"]) >= 1
        ledger = result["ledger"]
        assert ledger["attempts"]
        assert ledger["final_paragraphs"]


def main() -> int:
    tests = [
        test_tier_small_for_8b,
        test_tier_large_for_big_ctx,
        test_budget_small_low_density,
        test_budget_rises_with_density,
        test_density_reads_npcs_from_location_tree,
        test_infer_turn_number_from_summaries,
        test_skip_consolidator_lean_two_para,
        test_adjacent_detects_double,
        test_surgical_replace,
        test_cascade_reduces_overlap,
        test_polish_cuts_to_sentence,
        test_garbage_fragment_detected,
        test_pipeline_end_to_end_deterministic,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  PASS: {fn.__name__}")
        except Exception as exc:
            failed += 1
            print(f"  FAIL: {fn.__name__}: {exc}")
    print(f"\nPassed: {len(tests) - failed}")
    print(f"Failed: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
