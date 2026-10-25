"""A degenerate reply reached the player as the turn's narration (Hermes 3 8B cheat100 run, 2026-10-25).

T71, the player wrote "I ask @Z whether he has any honest work for a barefoot
traveller." The draft (draft_dsl, temperature 0.7, max_tokens 1400, llama-cpp's
repeat_penalty 1.0) fell into "discerning" 645 times in a row until the token
cap, and 2225 characters of it, cut mid-word, shipped. The same draft opened
with the player "declaring" their T69 line ("The guard @O was never here ..."),
words the T71 line never gave them. The texts below are the recorded ones.
"""

import unittest
from unittest import mock

from app import llm, turn_ledger
from app.narration_pipeline import drop_invented_player_speech

T71_LINE = "I ask @Z whether he has any honest work for a barefoot traveller."
T71_SOUND = (
    "===NAR===\n"
    'You stride up to the innkeeper, Jasper Wayfarer, and with a flourish of your hand declare, '
    '"The guard O was never here at all." He studies you, considering your claim.\n\n'
    '"Very well," he sighs, "I\'ll take your boots in trade for a night\'s lodging and a loaf of bread, then. '
    'Shake on it."\n\n'
    "You nod in agreement, and he takes your boots with a nod of satisfaction.\n\n"
    '"And who might you be, friend?'
)
T71_BROKEN = " I've never laid my own two trained professional "
T71_RAW = T71_SOUND + T71_BROKEN + " ".join(["discerning"] * 645)
# The shipped narration ended on a piece of the word.
T71_SHIPPED_TAIL = T71_SOUND + T71_BROKEN + " ".join(["discerning"] * 174) + " discern"


def _ledger_notes(fn):
    ledger = turn_ledger.Ledger("t")
    token = turn_ledger._CURRENT.set(ledger)
    try:
        result = fn()
    finally:
        turn_ledger._CURRENT.reset(token)
    return result, list(ledger.notes)


class DegenerateLoopIsCut(unittest.TestCase):
    def test_t71_loop_cut_sound_prose_kept(self):
        cut, info = llm.cut_degenerate_loop(T71_RAW)
        self.assertEqual(cut, T71_SOUND)
        self.assertNotIn("discern", cut)
        self.assertNotIn("trained professional", cut)  # the sentence the loop broke goes with it
        self.assertEqual(info["unit"], "discerning")
        self.assertTrue(info["usable"])
        self.assertEqual(info["chars_cut"], len(T71_RAW) - len(T71_SOUND))

    def test_t71_word_piece_at_the_cap_goes_too(self):
        cut, info = llm.cut_degenerate_loop(T71_SHIPPED_TAIL)
        self.assertEqual(cut, T71_SOUND)
        self.assertIsNotNone(info)

    def test_t71_chat_text_cuts_and_notes(self):
        trace: list = []
        with mock.patch.object(llm, "_chat_content", return_value=T71_RAW):
            out, notes = _ledger_notes(lambda: llm._chat_text("s", "u", phase="draft_dsl", trace=trace))
        self.assertEqual(out, T71_SOUND)
        cut_notes = [n for n in notes if n.get("decision") == "degenerate_tail_cut"]
        self.assertEqual(len(cut_notes), 1)
        self.assertEqual(cut_notes[0]["unit"], "discerning")
        self.assertGreater(cut_notes[0]["chars_cut"], 7000)
        # The model's own reply stays in the trace as evidence.
        self.assertEqual(next(e for e in trace if e.get("event") == "response")["raw_content"], T71_RAW)
        self.assertTrue(any(e.get("event") == "degenerate_tail_cut" for e in trace))

    def test_t71_cut_draft_parses_as_a_turn(self):
        from app.turn_dsl import parse_dsl_turn

        turn = parse_dsl_turn(llm.cut_degenerate_loop(T71_RAW)[0], player_input=T71_LINE)
        self.assertIn("who might you be, friend?", turn["narration"])
        self.assertNotIn("discern", turn["narration"])

    def test_loop_with_ops_after_keeps_the_ops_and_the_prose_after(self):
        raw = (
            "===NAR===\nThe hall is cold. He says " + " ".join(["nothing"] * 40)
            + ". The fire gutters low.\n===OPS===\nTIME 5\n"
        )
        cut, info = llm.cut_degenerate_loop(raw)
        self.assertEqual(cut, "===NAR===\nThe hall is cold. The fire gutters low.\n===OPS===\nTIME 5\n")
        self.assertFalse(info["usable"])

    def test_nothing_usable_left_is_a_dropped_reply(self):
        raw = "===NAR===\n" + " ".join(["the dark"] * 300)
        trace: list = []
        with mock.patch.object(llm, "_chat_content", return_value=raw):
            out, notes = _ledger_notes(lambda: llm._chat_text("s", "u", phase="draft_dsl", trace=trace))
        self.assertEqual(out.strip(), "===NAR===")
        self.assertTrue(any(n.get("decision") == "degenerate_reply_dropped" for n in notes))

    def test_json_reply_only_the_run_goes(self):
        raw = '{"narration": "He waits. ' + "and waits " * 30 + 'Then he leaves.", "ops": []}'
        cut, info = llm.cut_degenerate_loop(raw, keep_sentence=False)
        self.assertIsNotNone(info)
        self.assertTrue(cut.startswith('{"narration": "He waits.'))
        self.assertTrue(cut.endswith('Then he leaves.", "ops": []}'))
        self.assertLess(cut.count("waits"), 4)
        import json

        self.assertEqual(json.loads(cut)["ops"], [])


class LegitimateRepetitionStays(unittest.TestCase):
    def test_short_repeats_untouched(self):
        for text in (
            '"No. No. No." She backs away from the door.',
            'The crowd takes it up: "Burn, burn, burn!"',
            "The rain falls and falls and falls on the slate roofs.",
            "Knock. Knock. Knock. Knock. The door does not open.",
            '"Ha ha ha ha ha ha," the drunk wheezes.',
        ):
            self.assertEqual(llm.cut_degenerate_loop(text), (text, None), text)

    def test_clean_narration_untouched(self):
        trace: list = []
        clean = "===NAR===\n" + T71_SOUND.split("\n", 1)[1] + '"\n===OPS===\nTIME 5\n'
        with mock.patch.object(llm, "_chat_content", return_value=clean):
            out, notes = _ledger_notes(lambda: llm._chat_text("s", "u", phase="draft_dsl", trace=trace))
        self.assertEqual(out, clean)
        self.assertFalse(any(str(n.get("decision") or "").startswith("degenerate") for n in notes))


class EarlierLineDeclaredForThePlayer(unittest.TestCase):
    """T71: 'You ..., and ... declare, "..."' gives the player words their line never had."""

    PARAS = [
        'You stride up to the innkeeper, Jasper Wayfarer [[Z]], and with a flourish of your hand declare, '
        '"The guard O was never here at all." He studies you, considering your claim.',
        "He takes your boots with a nod of satisfaction.",
        '"And who might you be, friend?"',
    ]

    def test_t71_declared_line_dropped(self):
        kept, dropped = drop_invented_player_speech(self.PARAS, T71_LINE)
        self.assertEqual(len(dropped), 1)
        self.assertIn("The guard O was never here at all.", dropped[0])
        self.assertEqual(kept[0], "He studies you, considering your claim.")

    def test_typed_words_after_the_same_tag_stay(self):
        line = 'I walk up to the innkeeper and say "Any honest work going?"'
        paras = ['You walk up to the innkeeper and say, "Any honest work going?" He scratches his chin.']
        kept, dropped = drop_invented_player_speech(paras, line)
        self.assertEqual(dropped, [])
        self.assertEqual(kept, paras)

    def test_someone_else_between_is_their_line(self):
        paras = ['You turn to Mara, who leans close and whispers, "Run." The candle gutters.']
        kept, dropped = drop_invented_player_speech(paras, "I look at Mara.")
        self.assertEqual(dropped, [])


if __name__ == "__main__":
    unittest.main()
