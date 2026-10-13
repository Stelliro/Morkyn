"""7B run 7: a decision the prose makes for the player ends the scene at the line put to them (#97, #86)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import llm  # noqa: E402

# Run 7, T7 (trace 8): Bertram answers her question, then the prose has Isk
# ask more, offer help, lift the chest, decide to report it and walk it to
# the harbour.
T7_LINE = (
    'I keep the rusty tool handle I pulled out of the mud and call over to the gravedigger. '
    '"Bertram, isn\'t it? Not much call for graves out here. What are you digging for?"'
)
T7_DRAFT = (
    'You keep the rusty tool handle you pulled out of the mud and call over to the gravedigger, Bertram. '
    '"Bertram, isn\'t it? Not much call for graves out here. What are you digging for?"\n\n'
    'Bertram looks up from his work, wiping his hands on his tunic. "Ah, Isk. I\'m just checking the old well. '
    'Something\'s stirring in the mud, and I\'m trying to make sense of it."\n\n'
    'You lean in, curious. "A well? What do you mean by that?"\n\n'
    'Bertram squints into the murky water, then waves his hand to clear a spot. "There\'s a chest down there. '
    'I\'ve been trying to figure out how to lift it without too much disturbance. Maybe we can salvage something useful."\n\n'
    'You consider, the possibility of treasure or useful items intriguing. "Do you need any help?"\n\n'
    'Bertram gives you a thoughtful look. "If you\'re willing, that would be a great help. The chest is heavy, '
    'and I\'m not sure how stable the well is."\n\n'
    'You nod, ready to assist. "Sure, let\'s do it."\n\n'
    'Bertram nods and starts to gather some wooden poles and rope from nearby. Together, you manage to pull the '
    'chest up from the well.\n\n'
    'Bertram glances at the coins, then at you. "Well, we\'ve got some salvage here. What do you think, Isk? '
    'Should we keep it for ourselves or report it to the harbour reeve?"\n\n'
    'You consider the items, then decide. "Let\'s report it. It\'s not right to keep something found without claiming it."\n\n'
    'Bertram agrees, and you both walk the chest and coins to the nearest official at the harbour, where you hand them over.'
)

# Run 7, T3 (trace 4): she only demanded a number; the prose put her words in
# Oriel's mouth, had her accept ("A half then," you say, stepping towards the
# deck) and start the work.
T3_LINE = '"Half the usual of what? Give me a number, Oriel, or I\'m off to the flats on my own."'
T3_DRAFT = (
    'Morning lingers in the Saltmarrow Salvage Yard, the sun\'s first rays casting a warm glow on the debris-strewn '
    'floor. Oriel Rendle, a rag picker, leans against the deck rail, her weathered hands folded as she watches you. '
    '"Half the usual of what?" she asks, her voice carrying a hint of curiosity. "Give me a number, Oriel, or I\'m off '
    'to the flats on my own."\n\n'
    'You notice the tide is indeed low and ebbing, the perfect time to start a small job of cleaning the decks. '
    '"A small job, you say? Half the usual pay for half the work?" you ask, testing the offer.\n\n'
    'Oriel gives a small nod, her eyes flickering with interest. "There\'s a small job of cleaning the decks. You can '
    'start there and see what else you can salvage. As for pay, it\'s a mere half of what you\'d usually earn."\n\n'
    'You consider. The flats beckon, but there\'s still a chance to earn a bit here. "A half then," you say, stepping '
    'towards the deck. "Let\'s get started."\n\n'
    'Oriel\'s eyes light up. "Good choice. Let\'s see what the deck has in store for us."\n\n'
    'You begin to gather debris and sweep the floor, the deck creaking under your feet. Oriel watches from the rail, '
    'her presence a steady reminder of the work at hand.'
)


def _cut(text: str, line: str, **extra) -> dict:
    turn = {"narration": text, "self_check": {}, **extra}
    return llm._cut_scene_at_invented_request(turn, line)


class AnswerToThePlayerIsALinePutToThem(unittest.TestCase):
    def test_t7_scene_ends_on_bertrams_answer(self):
        out = _cut(T7_DRAFT, T7_LINE, gm_events=[{"trigger": "", "summary": "Bertram agrees, and you both walk the chest and coins to the nearest official at the harbour"}])
        self.assertIn("_scene_cut", out)
        self.assertTrue(out["narration"].rstrip().endswith("trying to make sense of it.\""), out["narration"][-120:])
        self.assertNotIn("chest", out["narration"])
        self.assertNotIn("harbour", out["narration"])
        # The op that rested on the cut part goes with it.
        self.assertEqual(out["gm_events"], [])

    def test_a_reply_without_you_is_addressed_only_when_it_answers_the_player(self):
        quotes = ["Bertram, isn't it? Not much call for graves out here. What are you digging for?"]
        own = llm.player_line_of(T7_LINE)
        body = T7_DRAFT
        start = body.index('"Ah, Isk.')
        self.assertTrue(llm._replies_to_player(body, start, own, quotes))
        later = body.index('"There\'s a chest')
        self.assertFalse(llm._replies_to_player(body, later, own, quotes))


class AnInventedAcceptanceIsCutAtTheOffer(unittest.TestCase):
    def test_t3_scene_ends_on_orielss_offer(self):
        out = _cut(T3_DRAFT, T3_LINE)
        self.assertIn("_scene_cut", out)
        self.assertTrue(out["narration"].rstrip().endswith("what you'd usually earn.\""), out["narration"][-120:])
        self.assertNotIn("Good choice", out["narration"])
        self.assertNotIn("gather debris", out["narration"])

    def test_starting_the_work_is_labor_unless_the_player_started_it(self):
        own = llm.player_line_of(T3_LINE)
        sentence = "You begin to gather debris and sweep the floor, the deck creaking under your feet."
        self.assertEqual(llm._invented_unit_family(sentence, own, T3_LINE), "labor")
        started = "I start sorting the pile, metal on the left."
        self.assertEqual(llm._invented_unit_family("You begin sorting the pile.", started, started), "")
        self.assertEqual(llm._invented_unit_family("You set to work on the pile.", own, T3_LINE), "labor")

    def test_no_deal_does_not_excuse_the_work(self):
        line = '"Coppers won\'t touch my debt. No deal, Oriel."'
        own = llm.player_line_of(line)
        self.assertEqual(llm._invented_unit_family("You begin to scrub the deck.", own, line), "labor")


class TheCutStaysWhereItBelongs(unittest.TestCase):
    def test_the_players_own_acceptance_is_not_cut(self):
        line = '"Two gold and I\'ll do it. I\'ll start on the pile now." I roll up my sleeves.'
        text = (
            'You roll up your sleeves. "Two gold and I\'ll do it. I\'ll start on the pile now."\n\n'
            'Oldfield shrugs. "Two it is. The gloves are by the door if you want them."\n\n'
            'You begin sorting the pile, metal on the left and rags by the wall, the work steady under the low roof '
            'of the shed while the fog thins outside and the gulls quarrel on the ridge.'
        )
        out = _cut(text, line)
        self.assertNotIn("_scene_cut", out)

    def test_no_cut_back_over_an_arrival(self):
        # Run 5 T29 shape: a line said before the walk the player asked for;
        # the invented part answers someone at the new place.
        line = '"I\'ll come back for it tomorrow." I leave the book with her and walk back to the salvage yard to ask Roger about the wreck job.'
        text = (
            'You set the book down on her table. "I\'ll come back for it tomorrow."\n\n'
            'The old woman nods. "Ah, Isk. What about it?" she asks, already turning back to her lamp, the light low '
            'and yellow on the shelves of salvaged things that crowd the little room by the stairs.\n\n'
            'You walk into the salvager\'s yard, the scent of salt and old wood filling your nostrils. "I want to go '
            'over the wreck job with you," you say. Roger looks up from his tally.'
        )
        out = _cut(text, line)
        self.assertNotIn("_scene_cut", out)

    def test_npc_talk_to_someone_else_is_not_a_line_put_to_the_player(self):
        line = "I watch the two of them argue by the wall."
        text = (
            'Simon and Oldfield stand by the shed wall, their voices sharp in the fog that drifts in off the flats '
            'and settles between the sorted heaps of metal and rag.\n\n'
            '"The reeve wants it sorted by noon," Oldfield tells Simon. "He said so twice."\n\n'
            'Simon spits. "Then he can sort it himself."'
        )
        out = _cut(text, line)
        self.assertNotIn("_scene_cut", out)


if __name__ == "__main__":
    unittest.main()
