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


if __name__ == "__main__":
    unittest.main()
