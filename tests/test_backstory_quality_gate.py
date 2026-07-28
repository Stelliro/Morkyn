"""Backstory quality gate: invent first, deny stock clones, diversified fallback."""

from __future__ import annotations

from app.setup_composer import (
    backstory_has_overused_motifs,
    build_transmigration_backstory,
    evaluate_backstory_quality,
    quality_gate_backstory,
    transmigration_story_score,
)


STOCK_FREIGHT = (
    "In their former life they worked night shifts moving freight and labels, living by schedules "
    "and sore feet rather than swords. A truck accident ended that life; they woke on a dirt road "
    "at the edge of a work-yard fence line in a low-tech other world, with only travel clothes and "
    "a bent pair of glasses. The story starts at that arrival (or the hours just before), not as a "
    "native already living a local plot. They have no free hero kit — only ordinary habits and the "
    "need to learn which rules of this world can kill them."
)


def test_stock_freight_is_hard_denied():
    assert backstory_has_overused_motifs(STOCK_FREIGHT)
    rep = evaluate_backstory_quality(
        STOCK_FREIGHT,
        mode="transmigrated",
        idea="isekai",
        world_style="fantasy compound",
    )
    assert rep["ok"] is False
    assert "overused_stock_motifs" in rep["hard_fail"]


def test_quality_gate_repairs_stock_to_fresh_story():
    gate = quality_gate_backstory(
        STOCK_FREIGHT,
        mode="transmigrated",
        idea="isekai ordinary start",
        world_style="Mundane isekai compound",
        auto_repair=True,
        seed=4242,
    )
    assert gate["ok"] is True
    story = str(gate["story"] or "")
    low = story.lower()
    assert "no free hero kit" not in low
    assert "freight and labels" not in low
    assert "bent pair of glasses" not in low
    assert "not as a native already living a local plot" not in low
    assert transmigration_story_score(story)["ok"] is True
    assert gate.get("source") in {
        "fallback_transmigration_bank",
        "isekai_arrival_beat",
        "contradiction_repair",
        "raw",
    }


def test_good_teacher_story_passes():
    good = (
        "Before the transfer they were a middle-school math teacher who graded papers past midnight. "
        "Then came a wet stairwell fall that ended mid-breath; when awareness returned they were at "
        "a lantern-lit market lane that smelled of oil and wet rope, carrying a red pen, lesson notes "
        "in a tote, and a bus pass that means nothing. Play begins at that arrival — they are a "
        "newcomer with ordinary habits, not a local plot already in motion."
    )
    rep = evaluate_backstory_quality(
        good,
        mode="transmigrated",
        idea="isekai",
        world_style="fantasy",
    )
    assert rep["ok"] is True, rep
    assert rep["score"] >= 62


def test_native_fantasy_plot_denied_for_transmigrated():
    bad = (
        "They were a disgraced noble heir in a collapsing empire, forced into exile after a failed coup. "
        "Now they pose as a wandering merchant at a distant town's festival. Their weak seed skill "
        "Guest Right compounds with risk."
    )
    rep = evaluate_backstory_quality(bad, mode="transmigrated", idea="isekai")
    assert rep["ok"] is False
    assert any(
        c in rep["hard_fail"]
        for c in (
            "skill_meta_in_backstory",
            "native_fantasy_plot",
            "missing_former_world_life",
            "missing_transport",
        )
    )


def test_build_bank_never_emits_stock_package():
    samples = [
        build_transmigration_backstory(
            old_story=STOCK_FREIGHT,
            idea="isekai",
            world_style="fantasy compound",
            seed=s,
        )
        for s in range(20, 40)
    ]
    for s in samples:
        low = s.lower()
        assert "no free hero kit" not in low
        assert "freight and labels" not in low
        assert "bent pair of glasses" not in low
        assert transmigration_story_score(s)["ok"] is True, s[:200]


def test_gate_without_repair_returns_denial():
    gate = quality_gate_backstory(
        STOCK_FREIGHT,
        mode="transmigrated",
        idea="isekai",
        auto_repair=False,
    )
    assert gate["ok"] is False
    assert gate["denial_summary"]
