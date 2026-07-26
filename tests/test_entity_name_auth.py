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
