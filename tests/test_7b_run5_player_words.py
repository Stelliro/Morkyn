"""The player's own words in 7B run 5 (#123, #86): kept as typed, said by the player, and not added to."""
from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-7b-run5-words-"))
_ENV = isolated_data_env(str(_TMP))
_SAVED_ENV: dict[str, str | None] = {}


def setUpModule():
    _SAVED_ENV.update({key: os.environ.get(key) for key in _ENV})
    os.environ.update(_ENV)


def tearDownModule():
    for key, value in _SAVED_ENV.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _keep(text, line):
    from app.narration_pipeline import keep_player_words

    return keep_player_words(text, line)


def _drop(text, line):
    from app.narration_pipeline import drop_invented_player_speech

    kept, dropped = drop_invented_player_speech(re.split(r"\n\s*\n", text), line)
    return "\n\n".join(p for p in kept if p.strip()), dropped


class TheQuoteIsSaid(unittest.TestCase):
    def test_a_dropped_quote_is_said_as_the_scene_opens(self):
        # T21: the prose did the acts and left the words out.
        line = '"The reckoner is not for sale." I take it back from the clerk\'s counter and put it in my pocket.'
        prose = "You walk back to the counter, retrieve the reckoner from the clerk's hands, and tuck it into your pocket."
        out, changes = _keep(prose, line)
        self.assertTrue(out.startswith("“The reckoner is not for sale,” you say. You walk back"), out)
        self.assertEqual(changes[0]["action"], "missing_line_said")

    def test_a_question_is_asked_and_two_lines_stay_in_order(self):
        out, _ = _keep("The fog presses in.", '"I\'m Isk, not Warin." I nod. "Morning, then. Gate at first light?"')
        # The tag goes with the line it follows: "I'm Isk, not Warin" is said, not asked (8B run 2).
        self.assertTrue(
            out.startswith("“I'm Isk, not Warin,” you say. “Morning, then. Gate at first light?”"),
            out,
        )

    def test_a_reworded_line_is_put_back_word_for_word(self):
        # T38: "guild" became "the salvage's" in the model's own draft.
        line = 'I keep my distance and call out, "This wreck\'s under guild tally. Who are you?"'
        prose = 'You keep your distance and call out, "This wreck\'s under the salvage\'s tally. Who are you?" Abel steps closer.'
        out, changes = _keep(prose, line)
        self.assertIn("\"This wreck's under guild tally. Who are you?\" Abel steps closer.", out)
        self.assertEqual(changes[0]["action"], "reworded_line_restored")

    def test_the_players_words_leave_the_keepers_mouth(self):
        # T64: the tavern keeper said the player's whole line.
        line = "\"Four's steep for a mug. Do you have a room tonight, and what's it cost?\""
        prose = (
            "Verity [[H]], the tavern keeper, stands behind the bar. \"Four's steep for a mug,\" she says, glancing at you. "
            "\"Do you have a room tonight, and what's it cost?\"\n\n"
            "Verity looks you over. \"The room's a few silver pieces.\""
        )
        out, changes = _keep(prose, line)
        self.assertTrue(out.startswith("“Four's steep for a mug. Do you have a room tonight, and what's it cost?” you ask."), out)
        self.assertEqual(out.count("Four's steep"), 1)
        self.assertNotIn("she says, glancing", out)
        self.assertIn("The room's a few silver pieces.", out)
        self.assertIn("line_taken_from_other_speaker", [c["action"] for c in changes])

    def test_one_invented_line_becomes_the_missing_one(self):
        # T71: "Pay? I'll take what I can," you reply -- for "I'll sort it. What's the pay?"
        line = '"I\'ll sort it. What\'s the pay?" Once he answers, I roll up my sleeves and start sorting.'
        prose = 'Abel watches you. "Pay? I\'ll take what I can," you reply, your focus sharp.'
        out, changes = _keep(prose, line)
        self.assertIn("\"I'll sort it. What's the pay?\" you reply", out)
        self.assertEqual(changes[0]["action"], "invented_line_replaced")

    def test_a_line_voicing_the_rest_of_the_turn_is_not_replaced(self):
        # T50: "ask Warin for a bed" was voiced; the quote was reworded elsewhere.
        line = '"I never said that. That\'s what I need from the book." I ask Warin for a bed for tonight.'
        prose = (
            'You turn to Warin. "I never said that. That\'s what I\'m looking for in the book." '
            'You then ask, "Could you give me a bed for the night, Warin?"'
        )
        out, _ = _keep(prose, line)
        self.assertIn("\"I never said that. That's what I need from the book.\"", out)
        self.assertIn("Could you give me a bed for the night, Warin?", out)

    def test_a_line_split_by_its_tag_is_already_said(self):
        # T4: '"I'll take the hold," you say, "How much does it pay, and which boat is it?"'
        line = "\"I'll take the hold. How much does it pay, and which boat is it?\""
        prose = '"I\'ll take the hold," you say, "How much does it pay, and which boat is it?" Roger glances up.'
        out, changes = _keep(prose, line)
        self.assertEqual((out, changes), (prose, []))

    def test_said_already_and_npc_lines_untouched(self):
        line = 'I ask Abel, "Who wants to meet me?"'
        prose = 'You ask, "Who wants to meet me?" Abel nods. "Warin Croft," he says.'
        self.assertEqual(_keep(prose, line), (prose, []))
        self.assertEqual(_keep(prose, "I wait by the gate."), (prose, []))


class InventedSpeechGoes(unittest.TestCase):
    def test_an_asked_question_is_voiced_once_not_played_out(self):
        # T41: "ask him what he'll pay" became five lines of haggling.
        line = "I go into the salvage yard, put the fittings on Roger's scale and ask him what he'll pay for them."
        prose = (
            'You set the fitting on the scale.\n\n"Brass, you say?" Roger lifts the pan.\n\n'
            '"I have a bit more, if you\'re interested," you reply, hoping to make a fair deal.\n\n'
            'Roger nods. "How much do you have?"\n\n'
            '"Just one more like that," you say, holding up another fitting.\n\n'
            '"I\'ll consider it," you say. "What can you offer for them?"'
        )
        out, dropped = _drop(prose, line)
        self.assertNotIn("I have a bit more", out)
        self.assertNotIn("Just one more like that", out)
        self.assertIn("What can you offer for them?", out)
        self.assertNotIn("I'll consider it", out)
        self.assertIn("Brass, you say?", out)
        self.assertEqual(len(dropped), 3)

    def test_a_line_on_the_asked_subject_stays(self):
        out, dropped = _drop('"What about the docks?" you ask. The keeper shrugs.', "I ask the keeper about the docks.")
        self.assertEqual(dropped, [])
        self.assertIn("What about the docks?", out)

    def test_a_voiced_request_does_not_claim_the_npcs_lines(self):
        # T20: the old dialogue-paragraph guess read Roger's appraisal as the player's.
        line = "I walk to the salvage yard to sell the good rope and ask who else is buying."
        prose = (
            '"Good to see you," Roger says.\n\n'
            'You hand over the good rope, and Roger appraises it. "This should fetch a decent price."'
        )
        out, dropped = _drop(prose, line)
        self.assertEqual(dropped, [])
        self.assertIn("This should fetch a decent price.", out)

    def test_explain_repeat_and_call_out_are_the_players_tags(self):
        # T82 and T88.
        out, dropped = _drop(
            'Philippa steps over. "Found something?" she asks.\n\nYou explain, "It\'s a tool I remember from a past job."',
            "I take my lantern and go look at the crate, carefully.",
        )
        self.assertNotIn("a tool I remember", out)
        line = 'I stay in the yard and ask, "Who in the harbour wants to meet me, Abel?"'
        out, dropped = _drop(
            '"A man named Warin Croft," Abel says.\n\n"Warin Croft," you repeat, the name rolling off your tongue. "I\'ll go see him."',
            line,
        )
        self.assertNotIn("I'll go see him", out)
        self.assertIn("A man named Warin Croft", out)


class TheAskCarriesTheWords(unittest.TestCase):
    def test_draft_packet_lists_player_says(self):
        from app.db import init_db
        from app.turn_dsl import build_dsl_user_prompt
        from app.world import get_state

        init_db()
        context = get_state(include_hidden=True)
        prompt = build_dsl_user_prompt(context, '"The reckoner is not for sale." I put it in my pocket.')
        self.assertIn('"player_says":["The reckoner is not for sale."]', prompt)
        self.assertIn("word for word", prompt)
        plain = build_dsl_user_prompt(context, "I put it in my pocket.")
        self.assertNotIn("player_says", plain)


class TheTurnKeepsThem(unittest.TestCase):
    def test_engine_passes_restore_the_line(self):
        from app import llm

        turn = {
            "narration": "You walk back to the counter and tuck the reckoner into your pocket.",
            "narration_segments": [{"label": "paragraph", "text": "You walk back to the counter and tuck the reckoner into your pocket."}],
            "self_check": {"corrections_made": []},
        }
        trace: list = []
        out = llm._keep_player_words(turn, '"The reckoner is not for sale." I take it back.', "test", trace)
        self.assertTrue(out["narration"].startswith("“The reckoner is not for sale,” you say."))
        self.assertEqual(out["narration_segments"][0]["text"], out["narration"])
        self.assertEqual(trace[-1]["event"], "player_words_kept")


if __name__ == "__main__":
    unittest.main()
