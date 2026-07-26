"""NPC/place names must not be event or system-job sentences."""

from __future__ import annotations

from app.llm import _repair_entity_names_in_turn
from app.world import invent_person_name, is_plausible_person_name, is_plausible_place_name


def test_system_job_phrase_rejected_as_person_or_place():
    bad = "System pings a local job"
    assert not is_plausible_person_name(bad)
    assert not is_plausible_place_name(bad)
    assert is_plausible_person_name("Mara")
    assert is_plausible_person_name("Dockhand Kesh")
    assert is_plausible_place_name("Mosswake Gate")
    assert is_plausible_place_name("Cinder Market")


def test_scenery_phrase_rejected_as_person_name():
    """Classic fail: location furniture used as an NPC who 'stands' and 'leans'."""
    bad = "Sky-crack first window"
    assert not is_plausible_person_name(bad)
    assert not is_plausible_person_name("first window")
    assert not is_plausible_person_name("Rusted fire escape")
    assert is_plausible_place_name("Skycrack Spire")  # real place-ish name ok


def test_repair_rewrites_bad_npc_and_location_in_narration():
    narr = (
        "A cloaked figure named System pings a local job appears, offering coins. "
        "System pings a local job's voice is steady."
    )
    result = {
        "npcs": [{"code": "A", "name": "System pings a local job", "role": "broker"}],
        "locations": [{"code": "L1", "name": "System pings a local job", "summary": "x"}],
        "narration": narr,
    }
    fixed = _repair_entity_names_in_turn(
        result,
        {"current_location": {"name": "Mosswake Gate", "code": "L1"}},
    )
    npc_name = fixed["npcs"][0]["name"]
    loc_name = fixed["locations"][0]["name"]
    assert "System pings" not in npc_name
    assert is_plausible_person_name(npc_name)
    assert loc_name == "Mosswake Gate"
    assert "System pings" not in fixed["narration"]
    assert npc_name in fixed["narration"]


def test_invent_person_name_is_short():
    n = invent_person_name(seed=42)
    assert is_plausible_person_name(n)
    assert len(n.split()) <= 2


def test_repair_scenery_npc_and_does_not_spam_name_before_every_verb():
    from app.llm import _repair_prose_entity_labels, _strip_leaked_entity_html

    narr = (
        "The sky-crack first window is your only view of the world below, where "
        "Sky-crack first window stands at the edge of the city’s crumbling edge. "
        "Below, Sky-crack first window leans against a rusted fire escape."
    )
    result = {
        "npcs": [{"code": "A", "name": "Sky-crack first window", "role": "watcher"}],
        "locations": [{"code": "L1", "name": "Sky-crack first window", "summary": "a sill"}],
        "narration": narr,
    }
    fixed = _repair_entity_names_in_turn(
        result,
        {"current_location": {"name": "Cinder Market", "code": "L1"}},
    )
    npc_name = fixed["npcs"][0]["name"]
    assert "window" not in npc_name.lower()
    assert is_plausible_person_name(npc_name)
    assert fixed["locations"][0]["name"] == "Cinder Market"
    # Physical window kept as object; person uses renamed
    assert "window is your only view" in fixed["narration"].lower()
    assert f"{npc_name.lower()} stands" in fixed["narration"].lower()
    assert f"{npc_name.lower()} leans" in fixed["narration"].lower()
    # Should not paste the name before every verb endlessly
    assert fixed["narration"].lower().count(npc_name.lower()) <= 3

    leaked = (
        'where Sky-crack first window Sky-crack first window" type="button">'
        "Sky-crack first window stands"
    )
    clean = _strip_leaked_entity_html(leaked)
    assert "type=" not in clean
    assert "button>" not in clean.lower()
    assert clean.lower().count("sky-crack first window") <= 1

    # Mid-clause "and stands" must NOT force a subject insert
    prose = "Mara walks the edge and stands watch over the alley [[A]]."
    repaired = _repair_prose_entity_labels(prose, {"A": "Mara"})
    assert repaired.lower().count("mara") <= 2
    assert "Mara Mara" not in repaired
