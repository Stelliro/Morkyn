"""Every world_state key the prompt talks about must actually reach the model.

`_clean_context_for_handoff` is an allowlist: `HANDOFF_BASE_CONTEXT_KEYS` plus
whatever the turn plan opens up. A key that is not in it is dropped silently --
no error, no warning, and the packet ships `"key": null`.

That is not hypothetical. The system prompt has been telling the model "Honor
world_state.world_time. Do not change day/hour unless the turn is a wait/travel
or the action clearly spends time" on every turn, while `world_time` was absent
from both allowlists, so the clock was built, dropped, and arrived null. `turn`
went the same way.

This is the same silent-drop shape as the closed rosters whose lookups ignored
their own synonym data, and as the two intent gates in
tests/test_location_theme_enum.py. The general fix is a gate, not another
one-key patch: if a rule cites `world_state.X`, X has to survive the filter.

Run:  python -m unittest tests.test_prompt_context_reachability
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-reachability-test-"))
os.environ.update({
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
})

from app.llm import (  # noqa: E402
    HANDOFF_BASE_CONTEXT_KEYS,
    HANDOFF_OPTIONAL_CONTEXT_KEYS,
    _clean_context_for_handoff,
)

PROMPTS_SRC = (ROOT / "app" / "prompts.py").read_text(encoding="utf-8")
ALLOWED = set(HANDOFF_BASE_CONTEXT_KEYS) | set(HANDOFF_OPTIONAL_CONTEXT_KEYS)

# `history` is emptied on purpose by the filter -- the packet carries turn
# summaries instead. Anything else in here needs a reason next to it.
DELIBERATELY_DROPPED = {"history"}


def _cited_world_state_keys() -> set[str]:
    """Root keys the prompt text tells the model to read off world_state.

    Only the ROOT is checked. A rule may cite `world_state.player.resources`
    and that is fine: `player` survives the filter and carries its own
    resources dict. That was the resolution for `resources`, which used to be
    cited at the top level -- the data was already nested under `player` and
    under `mechanics_context`, so the honest fix was to correct the rule rather
    than ship a third copy of it and grow the packet for nothing.
    """
    return {m for m in re.findall(r"world_state\.([a-z_]+)", PROMPTS_SRC)}


class TestCitedKeysSurvive(unittest.TestCase):
    def test_every_cited_world_state_key_is_allowed_through(self):
        unreachable = sorted(_cited_world_state_keys() - ALLOWED - DELIBERATELY_DROPPED)
        self.assertEqual(
            unreachable,
            [],
            "the system prompt cites these but the handoff filter drops them, "
            f"so they arrive null: {unreachable}",
        )

    def test_world_time_specifically_survives(self):
        # The one that was actually broken. Named on purpose so a future
        # allowlist tidy-up cannot quietly take it out again.
        self.assertIn("world_time", ALLOWED)
        self.assertIn("world_time", _cited_world_state_keys())

    def test_active_quests_survive(self):
        # prompts.py built an active-quest view from world_state.active_quests
        # while the handoff dropped the key, so the narrator never saw the
        # player's quests.
        self.assertIn("active_quests", ALLOWED)
        self.assertIn("active_quests", _cited_world_state_keys())
        cleaned = _clean_context_for_handoff(
            {"active_quests": [{"code": "Q1", "title": "Find the well"}]}, "planner_to_draft"
        )
        self.assertEqual(cleaned.get("active_quests"), [{"code": "Q1", "title": "Find the well"}])


class TestTheFilterActuallyKeepsThem(unittest.TestCase):
    """The allowlist is necessary but the filter is what decides."""

    def _clean(self, context):
        return _clean_context_for_handoff(context, "planner_to_draft")

    def test_world_time_and_turn_come_through_a_focused_turn(self):
        context = {
            "world_time": {"day": 3, "hour": 14, "minute": 60, "label": "Day 3 - 14:00"},
            "turn": 12,
            "player": {"name": "X"},
            "turn_plan": {"turn_kind": "player_action"},
            "action_context": {},
        }
        cleaned = self._clean(context)
        self.assertEqual(cleaned.get("turn"), 12)
        self.assertEqual((cleaned.get("world_time") or {}).get("day"), 3)
        self.assertEqual((cleaned.get("world_time") or {}).get("hour"), 14)

    def test_an_unknown_key_is_still_dropped(self):
        # The allowlist must stay an allowlist -- this test failing would mean
        # the filter stopped filtering.
        cleaned = self._clean({"player": {}, "not_a_real_key": {"a": 1}})
        self.assertNotIn("not_a_real_key", cleaned)

    def test_the_drop_is_recorded_in_the_trace(self):
        # dropped_keys is how this class of bug gets found; keep it populated.
        cleaned = self._clean({"player": {}, "not_a_real_key": 1})
        cleanup = (cleaned.get("retrieval") or {}).get("handoff_cleanup") or {}
        self.assertIn("not_a_real_key", cleanup.get("dropped_keys") or [])


class TestPromptBuildsWithTheClock(unittest.TestCase):
    def test_the_packet_carries_a_non_null_world_time(self):
        from app.prompts import build_user_prompt

        context = _clean_context_for_handoff(
            {
                "world_time": {"day": 3, "hour": 14, "label": "Day 3 - 14:00"},
                "turn": 12,
                "settings": {"setup_complete": True},
                "player": {"name": "X"},
                "turn_plan": {"turn_kind": "player_action"},
                "action_context": {},
            },
            "planner_to_draft",
        )
        packet = build_user_prompt(context, "I wait")
        self.assertIn('"world_time"', packet)
        self.assertNotIn('"world_time": null', packet)
        self.assertIn("Day 3", packet)


class TestStandingView(unittest.TestCase):
    """A scene call sees the tile underfoot, not the land catalog."""

    def _context(self):
        return {
            "world_time": {"day": 3, "hour": 14, "label": "Day 3 - 14:00"},
            "player": {"name": "Ash", "backstory": "SECRET_BACKSTORY", "health": 20},
            "map_space": {
                "width": 16383,
                "height": 16383,
                "scale": "world",
                "step_budget": 4,
                "density_percent": 8,
                "materials": ["limestone", "glow-fungus"],
                "player": {"x": 10, "y": 12, "terrain": "cavern"},
                "people_leaning": {
                    "majority": ["dwarven", "darkling"],
                    "kind": "dwarven",
                    "province": [0, 0],
                    "option": "If this stretch needs inhabitants, they may be dwarves.",
                },
                "rule": "The land is this fixed 16383 by 16383 map.",
                "places_in_reach": [{"name": "Far City", "x": 1, "y": 2}],
            },
            "mechanics_context": {
                "purpose": "a long mechanics essay",
                "resources": {"energy": 10, "max_energy": 10},
                "weather": {"kind": "rain", "label": "Steady rain", "strength": 0.5},
                "combat": {"status": "not_combat"},
            },
            "abilities": [{
                "name": "Hearth Spark",
                "code": "AB1",
                "description": "A small flame.",
                "cost": "4 mana",
                "growth_math": "x*2",
            }],
            "inventory": [{
                "name": "iron sword",
                "code": "I9",
                "equipped_slot": "MAIN",
                "description": "A nicked blade.",
                "stat_modifiers": {"damage": 5},
            }],
            "current_location": {"name": "Saltcut", "code": "L2", "id": 2},
            "locations": [{
                "id": 2,
                "name": "Saltcut",
                "code": "L2",
                "summary": "A long history of the ward that should stay out.",
                "npcs": [{"name": "Elara", "code": "A", "role": "miller", "summary": "She keeps the mill."}],
            }],
        }

    def test_a_look_sees_the_tile_and_not_the_catalog(self):
        from app.prompts import build_user_prompt

        packet = build_user_prompt(self._context(), "look around")
        self.assertIn("cavern", packet)
        self.assertIn("dwarven", packet)
        self.assertIn("Steady rain", packet)
        self.assertIn("Day 3", packet)
        self.assertIn("Saltcut", packet)
        self.assertIn("Elara", packet)
        self.assertIn("iron sword", packet)
        self.assertNotIn("16383", packet)
        self.assertNotIn("glow-fungus", packet)
        self.assertNotIn("Far City", packet)
        self.assertNotIn('"province"', packet)
        self.assertNotIn("SECRET_BACKSTORY", packet)
        self.assertNotIn("Hearth Spark", packet)
        self.assertNotIn("growth_math", packet)
        self.assertNotIn("A nicked blade", packet)
        self.assertNotIn("long history of the ward", packet)
        self.assertNotIn('"step_budget"', packet)

    def test_a_walk_adds_the_step_limit_without_the_land_size(self):
        from app.prompts import build_user_prompt

        packet = build_user_prompt(self._context(), "I walk east")
        self.assertIn('"step_budget":4', packet)
        self.assertNotIn("16383", packet)

    def test_a_named_spell_is_one_line(self):
        from app.prompts import build_user_prompt

        packet = build_user_prompt(self._context(), "I cast Hearth Spark")
        self.assertIn("Hearth Spark", packet)
        self.assertIn("A small flame", packet)
        self.assertNotIn("growth_math", packet)
        self.assertNotIn("4 mana", packet)

    def test_the_check_looks_up_what_the_scene_named(self):
        from app.prompts import build_user_prompt, build_verify_prompt

        context = self._context()
        scene = build_user_prompt(context, "look around")
        self.assertNotIn("Hearth Spark", scene)
        checked = build_verify_prompt(
            context,
            "look around",
            {"narration_segments": [{"text": "You cup a Hearth Spark in one hand."}]},
        )
        self.assertIn("Hearth Spark", checked)
        self.assertIn("A small flame", checked)
        self.assertNotIn("growth_math", checked)
        self.assertNotIn("4 mana", checked)

    def test_the_story_draft_keeps_the_step_rule_without_the_land_size(self):
        from app.turn_dsl import build_dsl_user_prompt

        packet = build_dsl_user_prompt(self._context(), "where can I buy food")
        self.assertIn("One step does not cross inside a city.", packet)
        self.assertNotIn("16383", packet)
        self.assertNotIn("(10,12)", packet)
        self.assertNotIn("9 by 9", packet)


if __name__ == "__main__":
    unittest.main()
