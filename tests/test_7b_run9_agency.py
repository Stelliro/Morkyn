"""7B run 9 (Qwen2.5 7B on MLE, agent as player): the scene cut and the player's words, round 5."""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

T2_LINE = (
    '"Thanks, Hal." I head for the northern edge he pointed at and start probing the mud with my boot heel, '
    "looking for anything solid worth digging out."
)
T2_DRAFT = (
    "You head for the northern edge Hal pointed at and start probing the muddy ground with your boot heel, looking "
    "for anything solid worth digging out. The wind stirs the brackish air, making it hard to see far. You find a "
    "small, glinting object and bend to examine it more closely.\n\n"
    "Hal Garner, the rag picker, watches from a distance, his eyes flickering between you and the shifting sand. "
    '"Ah, good find," he says, his voice low and cautious. "That could be worth something."\n\n'
    'You pocket the object, your fingers closing around its cool, hard shape. "Thanks, Hal," you call back, '
    '"I\'ll be careful."\n\n'
    "The wind picks up, ruffling your tunic and making your hair whip around your face. You continue your search, "
    "the ground yielding up small treasures: a rusted coin, a broken shard of glass, and, finally, a small, tarnished "
    "key. You pocket these as well, your bag growing heavier with each new addition.\n\n"
    "Hal's eyes follow your movements, his expression a mix of wary interest and helpfulness. \"You might find more,\" "
    'he murmurs, "if you dig a little deeper."\n\n'
    "The morning light is starting to dim, and the shadows stretch longer as the sun prepares to sink behind the "
    "horizon. You decide to take a break and inspect the items you've gathered."
)
T4_LINE = (
    '"A gull coin. Old harbour money, maybe." I turn it over once more. "Hal, who in Saltmarrow buys old coins - '
    'and who pays fair for them?"'
)
T4_DRAFT = (
    "You turn the gull coin over once more in the palm of your hand, the weathered surface catching the morning "
    'light. "Hal, who in Saltmarrow buys old coins - and who pays fair for them?" Hal Garner raises an eyebrow, his '
    "eyes narrowing as he considers the coin.\n\n"
    '"That\'s an odd piece," he says, "but old harbour money could fetch something. There\'s the old man at the Black '
    "Anchor, and the Reeve's men might be interested. They've been buying up relics and old coin for some time now.\"\n\n"
    "You consider the Black Anchor, a notorious spot known for its shady dealings, and the Harbour's Keep, where "
    'Captain Thorne\'s men operate. "I\'ll check with the old man first," you decide, pocketing the coin.\n\n'
    "Hal nods, his gaze lingering on the coin for a moment longer before he returns to his work, sorting through a "
    "pile of salvaged materials. You make your way towards the Black Anchor, the old man's reputation weighing on "
    "you as you step into the dimly lit alley."
)


class SearchingKeepsTheFinds(unittest.TestCase):
    """T2: the cut fired on "You pocket these as well" and lost the key, the coin and the shard."""

    def test_the_search_line_asks_to_take(self):
        from app.llm import player_take_intent

        self.assertTrue(player_take_intent(T2_LINE))
        self.assertTrue(player_take_intent("I poke through the wreck for anything I can sell."))
        self.assertFalse(player_take_intent("I look around the square."))

    def test_the_cut_keeps_the_finds(self):
        from app.llm import _cut_scene_at_invented_request

        out = _cut_scene_at_invented_request({"narration": T2_DRAFT}, T2_LINE)
        self.assertIn("You pocket these as well", out["narration"])
        cut = out.get("_scene_cut") or {}
        self.assertNotIn("careful", str(cut.get("npc_line") or ""))
        self.assertNotIn("take a break", out["narration"])


class TheCutEndsOnSomeoneElse(unittest.TestCase):
    """T2: the cut's last line was the player's own invented "I'll be careful."."""

    def test_invented_half_of_the_players_line_goes(self):
        from app.narration_pipeline import drop_invented_player_speech

        para = 'You pocket the object. "Thanks, Hal," you call back, "I\'ll be careful."'
        kept, dropped = drop_invented_player_speech([para], T2_LINE)
        self.assertEqual(dropped, ['"I\'ll be careful."'])
        self.assertIn('"Thanks, Hal," you call back', kept[0])
        self.assertNotIn("careful", kept[0])
        self.assertTrue(kept[0].rstrip().endswith("."))

    def test_a_tag_before_the_quote_is_the_players(self):
        from app.llm import _PLAYER_TAG_BEFORE_RE

        self.assertTrue(_PLAYER_TAG_BEFORE_RE.search('"Thanks, Hal," you call back, '))
        self.assertIsNone(_PLAYER_TAG_BEFORE_RE.search('"That\'s an odd piece," he says, '))


class ADecisionTagIsSpeech(unittest.TestCase):
    """T4: '"I'll check with the old man first," you decide' stayed, and the walk after it."""

    def test_decide_is_a_speech_tag(self):
        from app.narration_pipeline import drop_invented_player_speech

        kept, dropped = drop_invented_player_speech(re.split(r"\n\s*\n", T4_DRAFT), T4_LINE)
        self.assertTrue(any("check with the old man" in d for d in dropped))

    def test_the_scene_ends_on_hals_answer(self):
        from app.llm import _cut_scene_at_invented_request

        out = _cut_scene_at_invented_request({"narration": T4_DRAFT}, T4_LINE)
        self.assertTrue(out["narration"].rstrip().endswith('for some time now."'))
        self.assertNotIn("Black Anchor, the old man's reputation", out["narration"])

    def test_a_reply_in_two_halves_answers_the_player(self):
        from app.llm import _replies_to_player
        from app.narration_pipeline import player_quotes

        second = T4_DRAFT.index('"but old harbour')
        own = T4_LINE
        self.assertTrue(_replies_to_player(T4_DRAFT, second, own, player_quotes(T4_LINE)))


class OwnAcceptanceStillStands(unittest.TestCase):
    def test_a_player_who_said_yes_is_not_cut(self):
        from app.llm import _scene_cut_point

        text = (
            '"Will you help me lift it?" Bertram asks.\n\n'
            '"Aye, I\'ll help," you say, and you set your shoulder to the chest with him. Together you heave it up '
            "onto the mud, and the lid creaks as it settles."
        )
        self.assertIsNone(_scene_cut_point(text, '"Aye, I\'ll help." I set my shoulder to the chest.'))


if __name__ == "__main__":
    unittest.main()
