"""The ask-weight helper: what a persuasion line asks of the person sets the mark (Stell, 2026-10-21).

Run:  .venv\\Scripts\\python -m unittest tests.test_ask_weight
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _asker(reply):
    calls = []

    def ask(system, user, *, max_tokens, phase):
        calls.append({"system": system, "user": user, "phase": phase})
        if isinstance(reply, Exception):
            raise reply
        return reply

    return ask, calls


class TheRating(unittest.TestCase):
    def test_each_weight_maps_to_a_mark(self):
        from app.ask_weight import difficulty_for

        self.assertEqual(difficulty_for("free"), "trivial")
        self.assertEqual(difficulty_for("ordinary"), "easy")
        self.assertEqual(difficulty_for("personal"), "normal")
        self.assertEqual(difficulty_for("against"), "hard")

    def test_attitude_moves_one_step_and_stays_on_the_ladder(self):
        from app.ask_weight import difficulty_for

        self.assertEqual(difficulty_for("free", "friendly"), "trivial")
        self.assertEqual(difficulty_for("ordinary", "friendly"), "trivial")
        self.assertEqual(difficulty_for("ordinary", "hostile"), "normal")
        self.assertEqual(difficulty_for("against", "hostile"), "brutal")
        # A friend does not make a risky favour cheap.
        self.assertEqual(difficulty_for("personal", "friendly"), "normal")
        self.assertEqual(difficulty_for("against", "friendly"), "hard")

    def test_how_many_would_refuse_maps_to_a_weight(self):
        from app.ask_weight import parse_weight

        self.assertEqual(parse_weight({"refuse": "none"})[0], "free")
        self.assertEqual(parse_weight({"refuse": "Few"})[0], "ordinary")
        self.assertEqual(parse_weight({"refuse": "many"})[0], "personal")
        self.assertEqual(parse_weight({"refuse": "most of them"})[0], "against")
        self.assertEqual(parse_weight({"refuse": "some"}), ("", ""))

    def test_replies_are_read_loosely_and_nonsense_is_no_rating(self):
        from app.ask_weight import parse_weight

        self.assertEqual(parse_weight({"weight": "Free", "why": "public"})[0], "free")
        self.assertEqual(parse_weight('Sure: {"weight": "against", "why": "his orders"}')[0], "against")
        self.assertEqual(parse_weight({"weight": "medium"}), ("", ""))
        self.assertEqual(parse_weight(None), ("", ""))

    def test_the_ask_carries_the_line_and_the_person_and_no_examples(self):
        from app.ask_weight import build_ask

        system, user = build_ask("Where is the reeve's office?", {"name": "Mabel", "role": "tally clerk", "attitude": "neutral"})
        payload = json.loads(user)
        self.assertEqual(payload["player_line"], "Where is the reeve's office?")
        self.assertEqual(payload["aimed_at"]["name"], "Mabel")
        self.assertNotIn("e.g.", system.lower())
        self.assertNotIn("for example", system.lower())

    def test_a_failed_ask_changes_nothing(self):
        from app.ask_weight import rate

        ask, _ = _asker(RuntimeError("model down"))
        self.assertNotIn("difficulty", rate("Where is the office?", {"name": "Mabel"}, ask))
        ask, _ = _asker({"verdict": "pass"})
        self.assertNotIn("difficulty", rate("Where is the office?", {"name": "Mabel"}, ask))


class TheTurnHook(unittest.TestCase):
    CONTEXT = {"current_location": {"npcs": [{"code": "A", "name": "Mabel", "role": "tally clerk", "attitude": "friendly"}]}}

    def test_a_simple_question_to_a_friendly_clerk_is_trivial(self):
        from app.world import _rate_persuasion_asks

        pending = [{"skill_code": "persuasion", "social": True, "opposition": {"name": "Mabel"}, "npc_ref": {"code": "A"}}]
        ask, calls = _asker({"weight": "ordinary", "why": "she would tell anyone"})
        out = _rate_persuasion_asks(pending, self.CONTEXT, "Where is the reeve's office, Mabel?", ask=ask)
        self.assertEqual(pending[0]["difficulty"], "trivial")
        self.assertEqual(out[0]["weight"], "ordinary")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["phase"], "ask_weight")
        self.assertNotIn("attitude", json.loads(calls[0]["user"])["aimed_at"])  # the engine applies mood, not the model
        self.assertEqual(out[0]["attitude"], "friendly")

    def test_other_checks_and_set_marks_are_left_alone(self):
        from app.world import _rate_persuasion_asks

        pending = [
            {"skill_code": "lockpicking"},
            {"skill_code": "persuasion", "difficulty": "hard"},
            {"skill_code": "persuasion", "dc": 18},
            {"skill_code": "persuasion", "act": "haggle"},
        ]
        ask, calls = _asker({"weight": "free"})
        self.assertEqual(_rate_persuasion_asks(pending, self.CONTEXT, "Please?", ask=ask), {})
        self.assertEqual(calls, [])
        self.assertEqual(pending[1]["difficulty"], "hard")

    def test_an_unusable_reply_keeps_the_old_roll(self):
        from app.world import _rate_persuasion_asks

        pending = [{"skill_code": "persuasion", "opposition": {"name": "Mabel"}}]
        ask, _ = _asker("I cannot rate that.")
        self.assertEqual(_rate_persuasion_asks(pending, self.CONTEXT, "Tell me.", ask=ask), {})
        self.assertNotIn("difficulty", pending[0])


if __name__ == "__main__":
    unittest.main()
