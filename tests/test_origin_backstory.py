"""Isekai / transmigration origin + backstory package quality."""

from __future__ import annotations

from app.setup_composer import (
    apply_keyword_intent,
    backstory_self_contradictions,
    intent_to_field_overrides,
    normalize_backstory_mode,
    normalize_memory_policy,
    normalize_origin_package,
    normalize_previous_life_age,
    repair_backstory_self_contradictions,
    rewrite_backstory_third_person,
    sanitize_setup_fields,
)
from app.starter_logic import fact_check_starter_loadout


def test_magic_tool_vs_not_wizardry_detected_and_repaired():
    """Classic 8B clash: magic is a tool + survival by wit not wizardry."""
    story = (
        "They were a data analyst in a bustling Tokyo office, drowning in spreadsheets and coffee, "
        "when a mysterious glitch in the company’s server transported them to a world where magic is a tool, "
        "not a gift. Waking up in a foreign town with only a faded ticket and a strange symbol on their wrist, "
        "they’re forced to navigate a reality where survival depends on wit, not wizardry."
    )
    check = backstory_self_contradictions(story)
    assert check["ok"] is False
    assert "magic_affirmed_and_denied" in check["hard"]

    # Magic world: keep tool framing, drop "not wizardry"
    fixed_magic = repair_backstory_self_contradictions(
        story, magic_level="common", world_style="isekai fantasy"
    )
    low_m = fixed_magic.lower()
    assert "not wizardry" not in low_m
    assert "magic is a tool" in low_m or "craft-magic" in low_m or "magic-tools" in low_m
    assert backstory_self_contradictions(fixed_magic)["ok"] is True

    # No-magic world: drop tool affirmation
    fixed_none = repair_backstory_self_contradictions(
        story, magic_level="none", world_style="hard sci-fi"
    )
    low_n = fixed_none.lower()
    assert "magic is a tool" not in low_n
    assert backstory_self_contradictions(fixed_none)["ok"] is True


def test_normalize_mode_from_prose():
    assert normalize_backstory_mode("woke from a truck crash in a fantasy compound") == "transmigrated"
    assert normalize_backstory_mode("reincarnated with fragmented memories of a modern world") == "reincarnated"
    assert normalize_backstory_mode("known") == "known"
    assert (
        normalize_backstory_mode(
            "",
            story="They died at a desk and woke on a dirt road in another world.",
        )
        == "transmigrated"
    )


def test_normalize_memory_and_age():
    assert (
        normalize_memory_policy("remembers former life with fragmented office routines")
        == "former life fragments"
    )
    assert normalize_previous_life_age("late twenties") == "28"
    assert normalize_previous_life_age("twenty-seven") == "27"
    assert normalize_previous_life_age("27") == "27"


def test_first_person_rewritten():
    text = rewrite_backstory_third_person(
        "Born in Neo City, I was a forklift operator. I died in a crash and woke on a road."
    )
    assert "I was" not in text
    assert "they" in text.lower()


def test_summoned_sets_isekai_intent():
    plan = apply_keyword_intent("summoned by a failed ritual into a sect outer court")
    assert plan["isekai"] is True
    assert plan.get("portal_or_rebirth") in {"other_world", "body_transmigration"}


def test_reincarnated_childhood_override():
    plan = apply_keyword_intent(
        "reincarnated as a village child years ago, grew up local, remembers fragments of modern life"
    )
    assert plan["isekai"] is True
    assert plan.get("portal_or_rebirth") == "same_world_rebirth"
    fields = intent_to_field_overrides(plan)
    assert fields.get("backstory_mode") == "reincarnated"
    assert "fragment" in str(fields.get("memory_policy") or "").lower()


def test_truck_story_not_wiped_to_yard_mender():
    story = (
        "Born in a working-class district of Neo-Silicon City, they were a night-shift forklift operator "
        "at a logistics hub until a truck accident killed them. They woke on a dirt road beside a river "
        "compound with warehouse habits intact and no free hero kit."
    )
    report = fact_check_starter_loadout(
        starter_equipment="hoodie, jeans, sneakers, smartphone, water flask",
        appearance="torso: hoodie; feet: sneakers",
        backstory_mode="transmigrated",
        memory_policy="remembers former life",
        character_backstory=story,
        intent={"isekai": True, "genre": "isekai fantasy", "portal_or_rebirth": "other_world"},
        world_style="Mundane isekai compound",
        tech_level="medieval",
        apply_fixes=True,
    )
    final = (report.get("character_backstory") or "").lower()
    assert any(x in final for x in ("forklift", "logistics", "warehouse", "truck", "night-shift", "night shift", "accident"))
    assert "yard mender who kept pumps" not in final
    path = str((report.get("vibe") or {}).get("path") or "")
    assert path in {
        "keep_earth_origin_thin_kit",
        "stitch_arrival_keep_former_life",
        "localize_gear_only",
        "none",
        "already_local",
        "origin_matches_world",
        "keep_earth_origin_thin_kit",
    } or "yard mender who kept pumps" not in final


def test_sanitize_origin_package_collapses_prose_mode():
    fields, dirty = sanitize_setup_fields(
        {
            "backstory_mode": "woke from a truck crash in a fantasy compound",
            "memory_policy": "partial former-life fragments with uncertain rumors and private details",
            "character_backstory": (
                "Born in Neo City, I was a night-shift forklift operator. "
                "My life revolved around warehouse shifts until a crash."
            ),
            "previous_life_age": "late twenties",
            "world_style": "Compound Clerk's Fair Edge",
        },
        idea="isekai truck accident ordinary to overpowered",
    )
    assert fields["backstory_mode"] == "transmigrated"
    assert fields["memory_policy"] in {"former life fragments", "details emerge through choices", "remembers former life"}
    assert "I was" not in fields["character_backstory"]
    assert "another world" in fields["character_backstory"].lower() or "woke" in fields["character_backstory"].lower()
    assert fields["previous_life_age"] == "28"
    ws = str(fields.get("world_style") or "").lower()
    assert "fair edge" not in ws
    assert "isekai" in ws or "fantasy" in ws or "compound" in ws


def test_body_transmigration_keeps_two_lives_framed():
    story = (
        "They remember dying as a tired office clerk, then waking inside the body of a debt-ridden "
        "compound ledger-hand already known to local gate crews. The body's calluses are real; "
        "old-world memories arrive in fragments between work shifts."
    )
    out, _ = normalize_origin_package(
        {
            "backstory_mode": "transmigrated",
            "memory_policy": "former life fragments",
            "character_backstory": story,
        },
        idea="transmigrated into the body of a debt-ridden compound clerk",
    )
    assert out["backstory_mode"] == "transmigrated"
    assert "body" in out["character_backstory"].lower()
    assert "office" in out["character_backstory"].lower() or "clerk" in out["character_backstory"].lower()


def test_native_fantasy_plot_rewritten_for_transmigrated():
    """Disgraced-noble / festival guest + bolted isekai line is NOT a valid transmigration backstory."""
    from app.setup_composer import ensure_isekai_arrival_beat, transmigration_story_score

    bad = (
        "They were a disgraced noble heir in a collapsing empire, forced into exile after a failed coup. "
        "Now, they're a guest at a distant town's festival, posing as a wandering merchant to avoid detection. "
        "Their weak seed skill, Guest Right, allows them to temporarily halt hostilities through shared meals, "
        "but its power is tied to risk and use, making every encounter a gamble. They're desperate to find a way "
        "back to their homeland, but the only path forward is through diplomacy and the hidden costs of compounding "
        "their skill They died or were torn from that life and woke in another world with ordinary work habits "
        "and no free hero kit."
    )
    score = transmigration_story_score(bad)
    assert score["ok"] is False
    assert score["skill_meta"] is True or score["native_fantasy_plot_hits"] >= 2 or score["bolted_generic_arrival"]

    fixed = ensure_isekai_arrival_beat(
        bad,
        mode="transmigrated",
        idea="isekai ordinary to overpowered",
        world_style="Mundane isekai compound",
    )
    fixed_l = fixed.lower()
    assert "guest right" not in fixed_l
    assert "compounding" not in fixed_l
    assert "disgraced noble" not in fixed_l
    # Assert the properties, not a hand-copied keyword list: the composer writes
    # valid transports the list never covered ("...ended with a ferry railing
    # give-way in winter chop"), and the vocabulary lives in setup_composer.
    rebuilt = transmigration_story_score(fixed)
    assert rebuilt["has_former_world"] is True, fixed
    assert rebuilt["has_transport"] is True, fixed
    assert transmigration_story_score(fixed)["ok"] is True


def test_sanitize_rejects_noble_festival_transmigrated_story():
    fields, dirty = sanitize_setup_fields(
        {
            "backstory_mode": "transmigrated",
            "memory_policy": "remembers former life",
            "character_backstory": (
                "They were a disgraced noble heir in a collapsing empire, forced into exile after a failed coup. "
                "Now they pose as a wandering merchant at a festival. Their weak seed skill Guest Right compounds."
            ),
            "world_style": "isekai fantasy compound",
            "tech_level": "medieval",
        },
        idea="isekai transmigrated ordinary start",
    )
    story = str(fields.get("character_backstory") or "").lower()
    assert fields.get("backstory_mode") == "transmigrated"
    assert "guest right" not in story
    assert "disgraced noble" not in story
    assert "former life" in story or "worked" in story or "job" in story or "city" in story


# --- reincarnated is not transmigrated --------------------------------------
#
# `harmonize_identity_to_world_vibe` accepted the caller's arrival classification
# and never read it, then hardcoded mode="transmigrated" into
# `ensure_isekai_arrival_beat` -- walking past that helper's own guard, which
# returns the story untouched for a reincarnated life. A reincarnated character
# with a modern CV came out byte-identical to a transmigrated one: "Before the
# transfer they were a hospital logistics technician... when awareness returned
# they were at Sect Outer Court", while backstory_mode still read "reincarnated".
#
# reincarnated = born into this world, grows up here, carries former-life fragments.
# transmigrated = dies elsewhere, arrives already formed.

# Deliberately free of every `lived_here_long` story marker ("years as", "grew up",
# "raised", "child", "village", "born in"), which is what let this reach the
# transmigration branch in the first place. "technician" makes it a modern resume.
_MODERN_CV = (
    "A hospital logistics technician in Osaka. She worked nights, kept the roster board tidy, "
    "and lived alone in a small flat above a laundromat."
)
_WORLD = dict(
    world_style="low fantasy kingdom of feuding baronies",
    tech_level="medieval",
    magic_level="rare",
)


def _harmonize(mode):
    from app.starter_logic import harmonize_identity_to_world_vibe

    return harmonize_identity_to_world_vibe(
        character_backstory=_MODERN_CV,
        backstory_mode=mode,
        memory_policy="",
        starter_equipment="hoodie, phone, lanyard",
        appearance="short dark hair",
        intent={"isekai": True, "raw_idea": "reborn into a feuding barony"},
        **_WORLD,
    )


_ARRIVAL_LANGUAGE = (
    "before the transfer",
    "awareness returned",
    "another world",
    "did not grow up in this world",
    "arrival",
    "arrived",
    "transport",
    "woke",
)


def test_reincarnated_and_transmigrated_are_different_packages():
    reinc = _harmonize("reincarnated")
    trans = _harmonize("transmigrated")
    assert reinc.get("character_backstory") != trans.get("character_backstory")
    assert reinc.get("path") != trans.get("path")


def test_a_reincarnated_life_gets_a_local_life_not_an_arrival_beat():
    """Both halves matter: no arrival stamped, AND a real local life built.

    Asserting only the absence of arrival language passes vacuously when the
    character falls through every branch untouched, which is what happens if
    the mode stops settling residence on its own.
    """
    reinc = _harmonize("reincarnated")
    story = str(reinc.get("character_backstory") or "")
    low = story.lower()

    found = [w for w in _ARRIVAL_LANGUAGE if w in low]
    assert not found, f"reincarnated backstory describes an arrival: {found} in {low[:160]!r}"

    # A package was actually built, not merely left alone.
    assert reinc.get("path") == "localize_origin_to_world", f"path={reinc.get('path')!r}"
    assert story != _MODERN_CV, "the modern CV was left standing instead of being localized"
    assert "osaka" not in low and "laundromat" not in low, f"modern life kept: {low[:160]!r}"
    assert "reincarnat" in str(reinc.get("backstory_mode") or "")
    assert "fragment" in str(reinc.get("memory_policy") or "").lower()

    notes = " ".join(str(n) for n in (reinc.get("notes") or [])).lower()
    assert "transmigrated package enforced" not in notes
    assert "local life" in notes


def test_a_stray_arrival_sentence_does_not_beat_the_reincarnated_mode():
    """Rebirth is the claim; a leftover "woke in another world" line is not.

    Without the exemption this falls through every branch and keeps the arrival
    prose sitting under a mode that says the character was born here.
    """
    from app.starter_logic import harmonize_identity_to_world_vibe

    res = harmonize_identity_to_world_vibe(
        character_backstory=(
            "A hospital logistics technician in Osaka. Then a truck took her, "
            "and she woke in another world."
        ),
        backstory_mode="reincarnated",
        memory_policy="",
        starter_equipment="hoodie, phone",
        appearance="short dark hair",
        intent={"isekai": True},
        **_WORLD,
    )
    low = str(res.get("character_backstory") or "").lower()
    assert res.get("path") == "localize_origin_to_world", f"path={res.get('path')!r}"
    assert "woke in another world" not in low, f"arrival prose survived: {low[:160]!r}"
    assert "osaka" not in low


def test_a_transmigrated_life_still_gets_its_arrival_beat():
    """The fix must not mute transmigration, which is the case this branch is for."""
    trans = _harmonize("transmigrated")
    story = str(trans.get("character_backstory") or "").lower()
    assert any(w in story for w in _ARRIVAL_LANGUAGE), f"no arrival beat: {story[:160]!r}"
    assert trans.get("path") == "stitch_arrival_keep_former_life"
    assert "transmigrat" in str(trans.get("backstory_mode") or "")


def test_the_arrival_classification_passed_in_is_actually_read():
    """`arrival=` was accepted and dropped; a reincarnated classification must land."""
    from app.starter_logic import ARRIVAL_REINCARNATED, harmonize_identity_to_world_vibe

    res = harmonize_identity_to_world_vibe(
        character_backstory=_MODERN_CV,
        backstory_mode="",  # mode says nothing; only the classification does
        memory_policy="",
        starter_equipment="hoodie, phone",
        appearance="short dark hair",
        intent={"isekai": True},
        arrival={"arrival": ARRIVAL_REINCARNATED},
        **_WORLD,
    )
    story = str(res.get("character_backstory") or "").lower()
    found = [w for w in _ARRIVAL_LANGUAGE if w in story]
    assert not found, f"classification ignored, arrival stamped anyway: {found}"


def test_the_stitch_branch_never_sees_a_reincarnated_mode():
    """Guards the invariant the branch's hardcoded transmigration prose relies on."""
    for mode in ("reincarnated", "reborn", "reincarnated childhood"):
        res = _harmonize(mode)
        assert res.get("path") != "stitch_arrival_keep_former_life", (
            f"{mode!r} reached the transmigration branch"
        )
