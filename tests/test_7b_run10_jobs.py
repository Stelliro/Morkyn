"""7B run 10 (Qwen2.5 7B on MLE, agent as player): a deal struck in the scene is a job; routine acts roll nothing."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

T3_LINE = 'I follow her in to the table and pick up the first dull knife from the pile. "I offer my hands. Ten knives for one gold - that\'s my price."'
T3_PROSE = (
    'You follow her in. "I offer my hands. Ten knives for one gold - that\'s my price," you say. '
    'Jehane Tully [[A]] meets your gaze. "Very well, then. What do you have to offer?" she asks.'
)
T4_LINE = '"You asked that already." I set the knife down. "Yes or no, Jehane: one gold for ten sharpened knives?"'
T4_PROSE = (
    '"You asked that already," you say. Jehane Tully [[A]] looks at you with a hint of impatience. You set the knife '
    'down and state your terms clearly: "Yes or no, Jehane: one gold for ten sharpened knives?"\n\n'
    'Jehane Tully [[A]] considers for a moment. "Ten is a good number," she finally says. "But one gold? That\'s '
    'steep for ten."\n\nJehane Tully [[A]] takes a deep breath, her gaze steady. "Very well," she says. "Ten for one '
    'gold. But this is my last chance. If you fail, you won\'t come back here."'
)
JEHANE = [{"id": 1, "code": "A", "name": "Jehane Tully"}]
# The parser's own T4 proposal, quoting a sentence that offers nothing.
T4_REPLY = {
    "new": [
        {
            "title": "Ten sharpened knives for one gold",
            "summary": "Sharpen ten knives for one gold.",
            "giver": "A",
            "steps": [{"title": "Sharpen ten knives", "location": "L1"}],
            "reward": {"gold": 0, "xp": 0, "items": [], "text": ""},
            "evidence": "Jehane Tully [[A]] takes a deep breath, her gaze steady.",
        }
    ],
    "updates": [],
}


class ADealIsTheOffer(unittest.TestCase):
    """T4: the parser proposed the job but quoted a breath, and it was refused as no offer."""

    def test_agreed_deal_becomes_a_taken_job(self):
        from app import quest_parser as qp

        accepted, rejected = qp.validate_quest_changes(
            T4_REPLY, narration=T4_PROSE, player_input=T4_LINE, npcs=JEHANE,
            locations=[{"code": "L1", "name": "Saltmarrow"}],
        )
        self.assertEqual(rejected, [])
        job = accepted["new"][0]
        self.assertEqual((job["status"], job["reward"]["gold"], job["giver_name"]), ("active", 1, "Jehane Tully"))

    def test_no_deal_no_job(self):
        from app import quest_parser as qp

        accepted, rejected = qp.validate_quest_changes(
            T4_REPLY, narration=T3_PROSE, player_input=T3_LINE, npcs=JEHANE,
            locations=[{"code": "L1", "name": "Saltmarrow"}],
        )
        self.assertEqual(accepted["new"], [])
        self.assertTrue(rejected)

    def test_agreement_that_asks_back_is_not_agreement(self):
        from app.quest_parser import agreed_job_price

        self.assertEqual(agreed_job_price(T3_PROSE, T3_LINE), (None, ""))
        self.assertEqual(agreed_job_price(T4_PROSE, T4_LINE), (1, "player_terms_agreed"))


class RoutineActsRollNothing(unittest.TestCase):
    """#102: counting coins in a palm, eating by the fire, reading a posting."""

    def _skill(self, line):
        from app.skill_checks import infer_check_from_action

        check = infer_check_from_action(line, {})
        return (check or {}).get("skill_code")

    def test_nouns_are_not_acts(self):
        self.assertIsNone(self._skill("I count the coins in my palm before I put them away."))
        self.assertNotEqual(self._skill("I eat the soup by the fire."), "ranged")
        self.assertNotEqual(self._skill("I bow to her and wait."), "ranged")

    def test_the_verbs_still_roll(self):
        self.assertEqual(self._skill("I palm the coin while he looks away."), "sleight_of_hand")
        self.assertEqual(self._skill("I fire an arrow at the gull."), "ranged")

    def test_plain_reading_is_routine(self):
        self.assertIsNone(self._skill("I read the posting next to the coins properly. What's the job?"))
        self.assertIsNone(self._skill("I go and read the notice that's been put up."))
        self.assertEqual(self._skill("I read the faded letter and try to make out the smudged marks."), "investigation")
        self.assertEqual(self._skill("I examine the lock on the chest."), "investigation")


if __name__ == "__main__":
    unittest.main()
