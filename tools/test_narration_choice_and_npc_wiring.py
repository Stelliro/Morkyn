"""Prove: narration pipeline last beat asks for a choice menu; collect_local_npcs misses packet NPC codes.

Bug class (correctness-choice-beat-menu):
  PROSE_VOICE / DSL_SYSTEM_PROMPT: never end a scene by restating the player's
  options as a menu — that was the most common failure (unplayed turn).
  _beat_roles always ends on "choice"; build_paragraph_briefs then appends
  "Leave at least one concrete next choice open." The default writer template
  lists "press, wait, speak, withdraw". That is the menu the voice contract bans.

Bug class (wiring-local-npcs-codes):
  collect_local_npcs comments say it merges action_context / working_set.
  world._working_set ships nearby_npc_codes (not npcs).
  world._action_context ships local_focus_codes.nearby_npcs (not local_npcs).
  After focused handoff, locations[] is optional so nested npcs are gone.
  The collectors then return [] and density / must_cover miss everyone on screen.

CPU only — no live draft / no story model.

Exit 0 = both invariants hold
Exit 1 = bug proven
Exit 2 = harness/setup error
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.narration_pipeline import (  # noqa: E402
    _beat_roles,
    build_paragraph_briefs,
    collect_local_npcs,
    plan_paragraph_budget,
    scene_density,
)
from app.prompts import PROSE_VOICE  # noqa: E402
from app.turn_dsl import DSL_SYSTEM_PROMPT  # noqa: E402
from app.world import _action_context, _working_set  # noqa: E402


def main() -> int:
    fails: list[str] = []

    voice = PROSE_VOICE + "\n" + DSL_SYSTEM_PROMPT
    if "Never end" not in voice or "choice restated" not in voice.lower() and "The choice is yours" not in voice:
        # Voice contract must still ban menus or this harness is testing the wrong thing.
        if "choice is yours" not in voice.lower() and "restated" not in voice.lower():
            print("FAIL harness: PROSE_VOICE/DSL no longer ban choice menus", file=sys.stderr)
            return 2

    print("=== correctness-choice-beat-menu ===")
    for n in range(2, 7):
        roles = _beat_roles(n)
        print(f"  _beat_roles({n}) = {roles}")
        if roles and roles[-1] == "choice":
            fails.append(f"_beat_roles({n}) ends on 'choice' (menu beat vs PROSE_VOICE)")

    budget = {
        "paragraphs": 3,
        "beat_roles": _beat_roles(3),
        "chars_per_paragraph": {"min": 320, "max": 480},
        "max_tokens_per_paragraph": 200,
    }
    briefs = build_paragraph_briefs(
        budget,
        {"current_location": {"name": "Gate", "code": "L1"}},
        "I walk east toward the river camp.",
        __import__("app.narration_pipeline", fromlist=["NarrationLedger"]).NarrationLedger(
            turn=1, player_input="I walk east", budget=budget
        ),
        ops_summary="MOVE river camp",
    )
    cover_blob = " ".join(" ".join(b.get("must_cover") or []) for b in briefs)
    roles_blob = " ".join(str(b.get("beat_role") or "") for b in briefs)
    print("  brief roles:", [b.get("beat_role") for b in briefs])
    print("  must_cover blob:", cover_blob[:240])
    if "choice" in roles_blob.split() and "Leave at least one concrete next choice open" in cover_blob:
        fails.append("briefs ask to leave a next choice open on a choice beat")
    if "Leave at least one concrete next choice open" in cover_blob:
        fails.append("must_cover still requests a choice menu")

    print("=== wiring-local-npcs-codes ===")
    locations = [
        {
            "code": "L1",
            "name": "Mosswake Gate",
            "npcs": [
                {"code": "A", "name": "Eldrin"},
                {"code": "F", "name": "Hearthpost"},
            ],
            "events": [],
        }
    ]
    ws = _working_set("L1", locations, [])
    ac = _action_context(
        "general",
        [],
        {"current_location": {"code": "L1", "name": "Mosswake Gate"}, "player": {}, "inventory_summary": {}},
        set(),
        {"npcs": [], "locations": [], "items": [], "events": [], "all": []},
        locations,
        [],
        [],
        [],
        [],
    )
    print("  working_set keys:", sorted(ws.keys()))
    print("  working_set.nearby_npc_codes:", ws.get("nearby_npc_codes"))
    print("  action_context.local_focus_codes:", ac.get("local_focus_codes"))
    if "npcs" in ws:
        fails.append("unexpected: working_set grew a npcs list; harness assumption stale")
        return 2
    if not ws.get("nearby_npc_codes"):
        print("FAIL harness: _working_set did not ship nearby_npc_codes", file=sys.stderr)
        return 2

    # Focused packet after handoff: current_location without nested npcs, no locations[].
    focused = {
        "current_location": {"id": 1, "code": "L1", "name": "Mosswake Gate"},
        "working_set": ws,
        "action_context": ac,
    }
    found = collect_local_npcs(focused)
    codes = {str(n.get("code") or "") for n in found}
    print("  collect_local_npcs(focused) codes:", sorted(codes))
    if "A" not in codes or "F" not in codes:
        fails.append(
            f"collect_local_npcs ignored working_set.nearby_npc_codes / "
            f"local_focus_codes.nearby_npcs; got {sorted(codes)}"
        )

    # DSL-shaped top-level NPC uses `location`, not location_code.
    dsl_shaped = {
        "current_location": {"id": 1, "code": "L1", "name": "Mosswake Gate"},
        "npcs": [{"code": "A", "name": "Eldrin", "location": "L1"}],
    }
    dsl_found = collect_local_npcs(dsl_shaped)
    dsl_codes = {str(n.get("code") or "") for n in dsl_found}
    print("  collect_local_npcs(dsl location field) codes:", sorted(dsl_codes))
    if "A" not in dsl_codes:
        fails.append("collect_local_npcs ignores npc.location (DSL/JSON schema field)")

    dense = scene_density(focused, "I ask Eldrin about the road.")
    print("  focused density npc_count:", dense.get("active_npc_count"), "score:", dense.get("score"))

    if fails:
        print("FAIL:")
        for f in fails:
            print(" -", f)
        return 1
    print("OK: last beat is not a choice menu; local NPC codes survive focused packets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
