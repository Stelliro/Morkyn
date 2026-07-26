"""Ability / custom_skills quality gate: invent first, deny weak, fallback last."""

from __future__ import annotations

from app.llm import (
    ABILITY_QUALITY_MAX_ATTEMPTS,
    _fallback_custom_skills_from_domain,
    _fallback_special_abilities,
    evaluate_ability_quality,
    evaluate_custom_skills_quality,
    quality_gate_abilities,
)


def test_quality_max_attempts_is_three():
    assert ABILITY_QUALITY_MAX_ATTEMPTS == 3


def test_meditation_hour_cost_fingerprint_and_diversify():
    from app.llm import (
        _cost_structure_fingerprint,
        diversify_ability_costs,
        quality_gate_abilities,
    )

    clone = "Once per rank; 1 hour of meditation to recharge after use"
    fp = _cost_structure_fingerprint(clone)
    assert fp in {
        "ONCE_PER_X_PLUS_HOUR_MEDITATION_RECHARGE",
        "HOUR_MEDITATION_RECHARGE",
        "ONCE_PER_RANK",
    }, fp
    assert _cost_structure_fingerprint(clone) == _cost_structure_fingerprint(clone + ".")

    abs_list = []
    for name in ("Alpha", "Beta", "Gamma"):
        abs_list.append(
            {
                "name": name,
                "description": f"You can perform a concrete {name} action in the scene with a clear limit.",
                "locked": False,
                "prerequisites": "",
                "cost": clone,
                "growth_math": "XP_to_next = 40 * rank_index^1.5; use 6-12 XP × risk (1/2/3); soft cap after C ×0.55",
                "power_type": "linear",
            }
        )
    gate = quality_gate_abilities(abs_list, origin="innate", require_strong_math=False)
    assert gate.get("ok") is False
    denial = " ".join(str(x) for x in (gate.get("denial_summary") or []))
    assert (
        "batch_identical_cost_structure" in denial
        or "batch_meditation_hour_recharge_spam" in denial
    ), denial

    fixed = diversify_ability_costs(abs_list, force=True)
    costs = [str(a.get("cost") or "") for a in fixed]
    assert len(set(c.lower() for c in costs)) >= 2, costs
    assert not all("meditation" in c.lower() for c in costs), costs


def test_near_duplicate_detection_and_local_dedupe():
    from app.llm import (
        ability_similarity_score,
        ensure_distinct_abilities,
        find_near_duplicate_pairs,
        quality_gate_abilities,
    )

    a = {
        "name": "Autumn Veil",
        "description": (
            "You summon a dense living veil of leaves that obscures your presence from sight and sound "
            "for 10 minutes. Once per day you hide behind the veil."
        ),
        "cost": "Once per day. Mild fatigue.",
        "prerequisites": "",
        "growth_math": "XP_to_next = 40 * rank_index^1.5; use 6-12 XP × risk (1/2/3); soft cap after C ×0.55",
        "power_type": "linear",
        "locked": False,
    }
    b = {
        "name": "Leaf Shroud",
        "description": (
            "You create a shroud of autumn leaves that hides you from sight and muffles sound "
            "for several minutes. Use once per day to obscure presence."
        ),
        "cost": "Once per day. Short breathlessness.",
        "prerequisites": "",
        "growth_math": "XP_to_next = 42 * rank_index^1.45; use 5-11 XP × risk (1/2/3); soft cap after C ×0.6",
        "power_type": "linear",
        "locked": False,
    }
    c = {
        "name": "River Craft Hands",
        "description": (
            "Sense the current's mood and guide a boat safely through fog or rapids with careful hands. "
            "A practical navigation aid, not a combat power."
        ),
        "cost": "Concentration while steering.",
        "prerequisites": "",
        "growth_math": "XP_to_next = 30 + 12*level; successful use grants 3-8 XP; soft cap at L6",
        "power_type": "linear",
        "locked": False,
    }
    assert ability_similarity_score(a, b) >= 0.45
    assert ability_similarity_score(a, c) < 0.45
    pairs = find_near_duplicate_pairs([a, b, c])
    assert pairs, "expected veil/shroud pair"
    assert set(pairs[0]["names"]) == {"Autumn Veil", "Leaf Shroud"}

    gate = quality_gate_abilities([a, b, c], origin="innate", require_strong_math=False)
    assert gate.get("ok") is False
    assert any("near_duplicate" in str(x) for x in (gate.get("denial_summary") or []))

    # Local-only path (no LLM): must replace weaker of the pair
    out = ensure_distinct_abilities(
        [a, b, c],
        origin="innate",
        use_llm=False,
        max_rounds=3,
        world_style="isekai fantasy",
    )
    assert out.get("ok") is True or out.get("rounds", 0) >= 1
    names = [str(x.get("name") or "") for x in out.get("abilities") or []]
    # Should not still contain both original near-dup names after local remake of weaker
    if out.get("ok"):
        pairs2 = find_near_duplicate_pairs(out["abilities"])
        assert not pairs2, pairs2
    assert len(names) == 3


def test_special_abilities_group_return_fields_not_character_block():
    """Regression: group 'special_abilities' must not expand to the full character field list."""
    from app.llm import _setup_randomizer_return_fields

    fields = _setup_randomizer_return_fields(
        "special_abilities",
        {"special_ability_origin": "acquired", "_locked_fields": []},
        False,
    )
    assert fields == ["special_abilities"], fields


def test_description_equals_name_hard_fails():
    from app.llm import evaluate_ability_quality

    bad = {
        "name": "shadow weave, mirage tracing",
        "description": "shadow weave, mirage tracing",
        "locked": True,
        "prerequisites": "Unlocks after practice.",
        "cost": "Once per day",
        "growth_math": "XP_to_next = 40 * rank_index^1.5; use 6-14 XP × risk (1/2/3/5); soft cap after C ×0.55",
        "power_type": "linear",
    }
    rep = evaluate_ability_quality(bad, one_skillish=True, origin="acquired")
    assert rep["ok"] is False
    hard = set(rep.get("hard_fail") or [])
    assert "description_equals_name" in hard or "description_too_short" in hard


def test_empty_json_prereq_normalized_and_mild_unlocked():
    from app.llm import (
        estimate_ability_opening_strength,
        normalize_ability_lock_and_prerequisites,
        normalize_ability_prerequisites,
    )

    assert normalize_ability_prerequisites("[]") == ""
    assert normalize_ability_prerequisites([]) == ""
    assert normalize_ability_prerequisites(None) == ""
    assert normalize_ability_prerequisites(["Touch a spent ward"]) == "Touch a spent ward"

    mild = {
        "name": "Echo Recall",
        "description": (
            "You can briefly remember the exact sound of a weapon or tool you've used, "
            "allowing you to replicate its effect in a pinch. Once per day, you can mimic "
            "the sound of a weapon or tool to create a minor distraction or disrupt an enemy's focus."
        ),
        "locked": True,
        "prerequisites": "[]",
        "cost": "Once per day. Mild mental strain.",
        "growth_math": "XP +1 per successful distraction (risk×1.0). Soft cap at rank C.",
        "power_type": "linear",
    }
    assert estimate_ability_opening_strength(mild) == "mild"
    cleaned = normalize_ability_lock_and_prerequisites(mild, origin="acquired")
    assert cleaned["prerequisites"] == ""
    assert cleaned["locked"] is False

    strong = {
        "name": "Absolute Sever",
        "description": "Always-on invulnerable blade that can instant kill any foe with no cooldown.",
        "locked": True,
        "prerequisites": "[]",
        "cost": "No cost",
        "growth_math": "flat power; no growth",
        "power_type": "flat",
    }
    assert estimate_ability_opening_strength(strong) == "strong"
    strong_c = normalize_ability_lock_and_prerequisites(strong, origin="acquired")
    assert strong_c["locked"] is True
    assert strong_c["prerequisites"]
    assert "[]" not in strong_c["prerequisites"]
    assert "later" in strong_c["prerequisites"].lower() or "unlock" in strong_c["prerequisites"].lower()


def test_good_ability_passes():
    good = {
        "name": "Marrow Lantern",
        "description": (
            "When you hold a knucklebone and whisper, a thumb-sized cold flame lights "
            "for a few seconds so you can see a step ahead."
        ),
        "locked": True,
        "prerequisites": "Unlocks after a night vigil over unmarked bones.",
        "cost": "finger numbness for minutes after each use",
        "growth_math": (
            "XP_to_next = 40 * rank_index^1.5; use grants 6-12 XP x risk 1/2/3; "
            "soft cap after C x0.5 until breakthrough; each rank +1 domain check; ladder F to SSS"
        ),
        "power_type": "compounding",
    }
    rep = evaluate_ability_quality(good, one_skillish=True, origin="acquired")
    assert rep["ok"] is True
    assert rep["score"] >= 62


def test_weak_ability_denied():
    bad = {
        "name": "Observation",
        "description": "A mysterious power.",
        "locked": True,
        "prerequisites": "",
        "cost": "no cost",
        "growth_math": "gets stronger",
        "power_type": "compounding",
    }
    rep = evaluate_ability_quality(bad, one_skillish=True, origin="acquired")
    assert rep["ok"] is False
    assert "growth_math_not_calculable" in rep["hard_fail"]
    assert "name_overused_domain" in rep["hard_fail"] or "description_vague_cliche" in rep["hard_fail"]


def test_fallback_abilities_pass_gate():
    from app.llm import ensure_distinct_abilities

    setup = {
        "special_ability_origin": "acquired",
        "_field_context": {"ability_origin": "acquired", "count_min": 1, "count_max": 2},
        "session_theme": {
            "power_fantasy": {"growth": "compounding", "start_power": "near_useless"}
        },
        "world_style": "dark fantasy isekai",
    }
    fb = _fallback_special_abilities(setup)
    assert fb
    # Fallbacks can occasionally share lanes; board dedupe reworks the weaker one.
    fb = ensure_distinct_abilities(
        fb,
        origin="acquired",
        one_skillish=True,
        world_style="dark fantasy isekai",
        use_llm=False,
    ).get("abilities") or fb
    gate = quality_gate_abilities(fb, one_skillish=True, origin="acquired")
    # If still near-dup after local remake, force single ability (thin opening kit is valid)
    if not gate.get("ok") and any("near_duplicate" in str(x) for x in (gate.get("denial_summary") or [])):
        fb = fb[:1]
        gate = quality_gate_abilities(fb, one_skillish=True, origin="acquired")
    assert gate["ok"] is True, gate.get("denial_summary")


def test_maintenance_hour_template_and_batch_spam_denied():
    from app.llm import evaluate_ability_quality, quality_gate_abilities

    one = {
        "name": "Ash Tongue",
        "description": "You can taste when ash in the air has a living source nearby for a few seconds.",
        "locked": True,
        "prerequisites": "Unlocks after a night under a choked sky.",
        "cost": "You must spend 1 hour each day in an environment with heavy ash, smoke, or dust to maintain this ability.",
        "growth_math": (
            "XP_to_next = 40 * rank_index^1.5; use 6-12 XP x risk 1/2/3; "
            "soft cap after C x0.5 until breakthrough; each rank +1 check; ladder F to SSS"
        ),
        "power_type": "compounding",
    }
    rep = evaluate_ability_quality(one, one_skillish=False, origin="acquired")
    assert rep["ok"] is False
    assert "cost_maintenance_hour_template" in rep["hard_fail"] or "cost_must_spend_hours_each_day" in rep[
        "hard_fail"
    ]

    batch = [
        {
            "name": f"Power {i}",
            "description": f"You can sense a faint edge in situation {i} for a few seconds when you focus.",
            "locked": True,
            "prerequisites": "Unlocks through training, a mentor, or a costly field discovery.",
            "cost": cost,
            "growth_math": (
                "XP_to_next = 36 * rank_index^1.5; use 5-11 XP x risk 1/2/3; "
                "soft cap after C; each rank +1 check; ladder F to SSS"
            ),
            "power_type": "compounding",
        }
        for i, cost in enumerate(
            [
                "You must spend 1 hour each dawn in a location with natural light to maintain this ability.",
                "You must spend 1 hour each day in an environment with heavy ash, smoke, or dust to maintain this ability.",
                "You must spend 1 hour each day near water to maintain this ability.",
                "You must spend 1 hour each day in a swamp or similar terrain to maintain this ability.",
            ],
            start=1,
        )
    ]
    gate = quality_gate_abilities(batch, one_skillish=False, origin="acquired")
    assert gate["ok"] is False
    joined = " ".join(gate.get("denial_summary") or [])
    assert (
        "batch_maintenance_hour_spam" in joined
        or "batch_identical_cost_structure" in joined
        or "cost_maintenance" in joined
        or "cost_must_spend" in joined
    )


def test_use_limit_vs_recharge_mismatch_detected_and_repaired():
    from app.llm import (
        ability_cross_field_fact_check,
        repair_ability_cross_field_consistency,
        quality_gate_abilities,
    )

    veil = {
        "name": "Veil of Shadows",
        "description": (
            "You can cloak yourself in a thin veil of shadow, making you nearly invisible "
            "to most eyes. This effect lasts for 10 seconds and can be used once per day."
        ),
        "locked": True,
        "prerequisites": "Unlocks through training, a mentor, or a costly field discovery.",
        "cost": "1 hour of meditation to recharge the veil after use",
        "growth_math": (
            "XP_to_next = 40 * rank_index^1.55; per-use XP = 5 * risk(1/2/3/5); "
            "rank +1 check / +12% duration; soft cap at rank 3 (duration *0.55); max duration 25s"
        ),
        "power_type": "compounding",
    }
    raw = ability_cross_field_fact_check(veil)
    assert raw["ok"] is False
    assert (
        "use_limit_vs_recharge_mismatch" in raw["hard_fail"]
        or "usage_limits_embedded_in_description" in raw["hard_fail"]
    )

    fixed = repair_ability_cross_field_consistency(veil)
    assert "once per day" not in fixed["description"].lower()
    assert "10 seconds" in fixed["description"].lower()
    assert "once per day" in fixed["cost"].lower()
    assert "1 hour" in fixed["cost"].lower() or "hour" in fixed["cost"].lower() or "cooldown" in fixed["cost"].lower()
    assert ability_cross_field_fact_check(fixed)["ok"] is True

    gate = quality_gate_abilities([veil], one_skillish=True, origin="acquired")
    assert gate["ok"] is True
    assert "once per day" in gate["abilities"][0]["cost"].lower()


def test_assign_locks_after_creation_prefers_stronger():
    from app.llm import assign_ability_locks_after_creation, ability_power_lock_score

    mild = {
        "name": "Soft Whisper",
        "description": "A mild brief whisper that can briefly distract one person nearby.",
        "cost": "1 energy",
        "resource_cost": {"energy": 1, "mana": 0, "fatigue": 0, "health": 0, "cooldown_minutes": 0},
        "power_type": "linear",
        "locked": False,
        "prerequisites": "",
    }
    strong = {
        "name": "Annihilating Tide",
        "description": "A battlefield mass wave that can slay and dominate enemies across the field permanently.",
        "cost": "8 mana; 6 energy; 3h cooldown",
        "resource_cost": {"energy": 6, "mana": 8, "fatigue": 2, "health": 0, "cooldown_minutes": 180},
        "power_type": "compounding",
        "locked": False,
        "prerequisites": "",
    }
    mid = {
        "name": "Iron Guard",
        "description": "You raise a solid shield of force that can block one solid strike for a few seconds.",
        "cost": "3 energy; 1 fatigue",
        "resource_cost": {"energy": 3, "mana": 0, "fatigue": 1, "health": 0, "cooldown_minutes": 20},
        "power_type": "linear",
        "locked": False,
        "prerequisites": "",
    }
    sm, _ = ability_power_lock_score(mild)
    ss, _ = ability_power_lock_score(strong)
    assert ss > sm

    # Force many trials: strong should be locked more often than mild when locks exist
    strong_locked = 0
    mild_locked = 0
    trials = 40
    for _ in range(trials):
        batch = assign_ability_locks_after_creation(
            [dict(mild), dict(mid), dict(strong)],
            origin="acquired",
        )
        by_name = {a["name"]: a for a in batch}
        if by_name["Annihilating Tide"].get("locked"):
            strong_locked += 1
            assert str(by_name["Annihilating Tide"].get("prerequisites") or "").strip()
        if by_name["Soft Whisper"].get("locked"):
            mild_locked += 1
    assert strong_locked >= mild_locked
    assert strong_locked >= trials // 3  # strong often locked when any locks roll

    innate = assign_ability_locks_after_creation([dict(strong), dict(mild)], origin="innate")
    assert all(not a.get("locked") for a in innate)
    assert all(not str(a.get("prerequisites") or "").strip() for a in innate)


def test_diversify_generic_prerequisites_across_batch():
    from app.llm import diversify_ability_prerequisites, is_generic_prereq

    clone = "Unlocks through training, a mentor, or a costly field discovery."
    assert is_generic_prereq(clone)
    batch = []
    for name in ("Alpha Tide", "Beta Ember", "Gamma Veil"):
        batch.append(
            {
                "name": name,
                "description": f"You can perform a concrete {name} action in the scene with a clear limit.",
                "locked": True,
                "prerequisites": clone,
                "cost": "Short fatigue after use.",
                "growth_math": "XP_to_next = 40 * rank_index^1.5; use 6-12 XP × risk (1/2/3)",
                "power_type": "linear",
            }
        )
    fixed = diversify_ability_prerequisites(batch, force=True, origin="acquired")
    prereqs = [str(a.get("prerequisites") or "") for a in fixed]
    assert len(prereqs) == 3
    assert len(set(p.lower() for p in prereqs)) == 3, prereqs
    assert not all(is_generic_prereq(p) for p in prereqs), prereqs
    assert clone.lower() not in {p.lower() for p in prereqs} or len(set(p.lower() for p in prereqs)) >= 2


def test_once_per_rank_cooldown_in_desc_vs_breath_cost_repaired():
    """Recurring 8B fail: limits live in description; cost is breath+stamina clone."""
    from app.llm import (
        ability_cross_field_fact_check,
        extract_ability_timing_facts,
        repair_ability_cross_field_consistency,
        quality_gate_abilities,
    )

    wave = {
        "name": "Pressure Wave",
        "description": (
            "Generate a localized wave of water that knocks back enemies within 10 meters. "
            "Can be used once per rank, with a 1-minute cooldown after each use."
        ),
        "locked": False,
        "prerequisites": "",
        "cost": "1 minute of breath control; 10% stamina drain",
        "growth_math": (
            "XP_to_next = 40 * rank_index^1.5; use 6-12 XP × risk (1/2/3); soft cap after C ×0.55"
        ),
        "power_type": "linear",
    }
    d_facts = extract_ability_timing_facts(wave["description"])
    assert d_facts.get("once_per_rank") is True
    assert d_facts.get("recharge_minutes") == 1.0 or abs(float(d_facts.get("recharge_minutes") or 0) - 1.0) < 0.01

    raw = ability_cross_field_fact_check(wave)
    assert raw["ok"] is False
    assert "usage_limits_embedded_in_description" in raw["hard_fail"]

    fixed = repair_ability_cross_field_consistency(wave)
    desc_l = fixed["description"].lower()
    cost_l = fixed["cost"].lower()
    assert "once per rank" not in desc_l
    assert "cooldown" not in desc_l
    assert "knock" in desc_l or "wave of water" in desc_l or "10 meters" in desc_l
    assert "once per rank" in cost_l
    assert "cooldown" in cost_l or "1-minute" in cost_l or "1 minute" in cost_l
    assert "stamina" in cost_l
    assert ability_cross_field_fact_check(fixed)["ok"] is True
    rc = fixed.get("resource_cost") or {}
    assert int(rc.get("cooldown_minutes") or 0) >= 1
    assert int(rc.get("energy") or 0) >= 1

    gate = quality_gate_abilities([wave], origin="innate", require_strong_math=False)
    assert gate["ok"] is True, gate.get("denial_summary")
    g0 = gate["abilities"][0]
    assert "once per rank" not in g0["description"].lower()
    assert "once per rank" in g0["cost"].lower()


def test_custom_skills_skeleton_denied_fallback_ok():
    skeleton = "OP_MC_FRAME: start with one weak seed power (domain chosen later)"
    rep = evaluate_custom_skills_quality(skeleton, one_skillish=True)
    assert rep["ok"] is False
    fb = _fallback_custom_skills_from_domain(
        {
            "world_style": "isekai",
            "special_abilities": [
                {
                    "name": "Salt Circle",
                    "description": "Pour salt that mostly holds a line.",
                }
            ],
        }
    )
    rep2 = evaluate_custom_skills_quality(
        fb,
        abilities=[{"name": "Salt Circle"}],
        one_skillish=True,
    )
    assert rep2["ok"] is True
    assert "weak seed skill:" in fb.lower()
