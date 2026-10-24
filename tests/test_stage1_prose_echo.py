"""Text that is not the story reaches the player as prose (Hermes 3 8B stage1 run, 2026-10-25).

T7: the narration began "* 850 chars" (the depth retry copied its own
"Target about 850 characters") and ended with the player's own line pasted
back as a "you" sentence. T9 ended with the line pasted back too. The texts
below are the recorded narration and player lines of those turns.
"""

import unittest
from unittest import mock

from app import llm, turn_ledger

T7_LINE = "I wade further out toward the deep reeds, knife out, and call out to see if anything answers."
T7_NARRATION = (
    '* 850 chars\nThe reeds swallow your footsteps. You call out, "Hello? Is anyone here?"\n\n'
    "The Shore [[L4]] around you is empty. But then, you hear a rustle from the reeds ahead. A figure steps out - "
    "an old woman with a long grey braid. She looks you up and down, then speaks.\n\n"
    '"Looking for something, traveler?"\n\n'
    "You wade further out toward the deep reeds, knife out, and call out to see if anything answers. "
    "She eyes you warily before speaking."
)
T7_ECHO = "You wade further out toward the deep reeds, knife out, and call out to see if anything answers."

T9_LINE = "I thank her, then follow the tracks deeper into the marsh toward where the scaled things are said to lair."
T9_NARRATION = (
    "You follow the tracks deeper into the marsh, the cattails whispering secrets as they part around your feet. "
    "The fog and reeds obscure the scaled creatures' lair, hiding it tantalizingly close. Saltmarrow's interior is "
    "quiet at this early morning hour, 09:09 - only the occasional splash of fish breaking the surface or a bird "
    "calling from its perch high in a dead tree disturb the stillness. The humidity is thick, beads of sweat forming "
    "on your brow as you press onward. The tracks lead you past a small cluster of fishermen mending their nets, "
    "their faces weathered from years spent on the water. As you pass, one of them calls out a warning about the "
    "dangers of the marsh's depths, his voice carrying a hint of concern. You thank him, then continue following "
    "the tracks deeper into the marsh toward where the scaled things are said to lair."
)
T9_ECHO = "You thank him, then continue following the tracks deeper into the marsh toward where the scaled things are said to lair."

T3_LINE = "I agree to patch the water trough for the five silver and go out back to look at the leak."
T3_OPENING = (
    "You agree to patch the water trough for the five silver and go out back to look at the leak. "
    "The silver pays for the cement and your labor."
)


def _ledger_notes(fn):
    ledger = turn_ledger.Ledger("t")
    token = turn_ledger._CURRENT.set(ledger)
    try:
        result = fn()
    finally:
        turn_ledger._CURRENT.reset(token)
    return result, list(ledger.notes)


class LengthNoteIsNotStory(unittest.TestCase):
    def test_t7_length_note_line_dropped_and_noted(self):
        turn = {"narration": T7_NARRATION}
        out, notes = _ledger_notes(lambda: llm._drop_text_notes(turn, "p", None))
        self.assertNotIn("850 chars", out["narration"])
        self.assertTrue(out["narration"].startswith("The reeds swallow your footsteps."))
        self.assertTrue(any(n["decision"] == "text_note_dropped" for n in notes))

    def test_note_shapes(self):
        for line in ("* 850 chars", "(about 900 characters)", "Word count: 212", "**1259 chars**", "~600 words"):
            self.assertTrue(llm._TEXT_NOTE_LINE_RE.match(line), line)
        for line in ("He counts 850 coins.", "850 chars of rope lie coiled.", "Three words: run, now, fast."):
            self.assertFalse(llm._TEXT_NOTE_LINE_RE.match(line), line)


class PlayerLineEchoIsDropped(unittest.TestCase):
    def test_t7_echo_dropped_and_her_reaction_stays(self):
        text, dropped = llm.echoed_player_line(T7_NARRATION, T7_LINE)
        self.assertEqual(dropped, [T7_ECHO])
        self.assertNotIn("You wade further out", text)
        self.assertTrue(text.endswith("She eyes you warily before speaking."))
        # The asked act told once with the player's call: "You call out" is the
        # line's own act (it asked to call out), so it stays.
        self.assertIn('You call out, "Hello? Is anyone here?"', text)
        self.assertIn("The reeds swallow your footsteps.", text)

    def test_t9_echo_dropped_world_answer_kept(self):
        text, dropped = llm.echoed_player_line(T9_NARRATION, T9_LINE)
        self.assertEqual(dropped, [T9_ECHO])
        self.assertTrue(text.startswith("You follow the tracks deeper into the marsh"))
        self.assertIn("one of them calls out a warning", text)

    def test_world_answer_sentence_is_not_an_echo(self):
        text = T7_NARRATION.replace("She eyes you warily", "The reeds close behind you. She eyes you warily")
        kept, dropped = llm.echoed_player_line(text, T7_LINE)
        self.assertEqual(dropped, [T7_ECHO])
        self.assertIn("The reeds close behind you.", kept)

    def test_first_telling_of_the_act_stays(self):
        # T3 opened on its line told back; nothing earlier had shown the act, so it is the act's telling.
        text, dropped = llm.echoed_player_line(T3_OPENING, T3_LINE)
        self.assertEqual(dropped, [])
        self.assertEqual(text, T3_OPENING)

    def test_engine_request_is_never_read(self):
        _, dropped = llm.echoed_player_line(T7_NARRATION, "__opening_scene_request__: " + T7_LINE)
        self.assertEqual(dropped, [])

    def test_turn_level_drop_is_noted(self):
        turn = {"narration": T9_NARRATION, "narration_segments": [{"label": "paragraph", "text": T9_NARRATION}]}
        out, notes = _ledger_notes(lambda: llm._drop_text_not_story(turn, T9_LINE, "p", None))
        self.assertNotIn("You thank him", out["narration"])
        self.assertEqual(out["narration_segments"][-1]["text"], out["narration"])
        self.assertTrue(any(n["decision"] == "player_line_echo_dropped" for n in notes))


class BothGatesRunInTheEngineCleanups(unittest.TestCase):
    def test_t7_through_engine_prose_cleanups(self):
        turn = {"narration": T7_NARRATION}
        out = llm._engine_prose_cleanups(turn, {}, T7_LINE, "p", None)
        self.assertNotIn("850 chars", out["narration"])
        self.assertNotIn(T7_ECHO, out["narration"])
        self.assertIn("She eyes you warily before speaking.", out["narration"])


if __name__ == "__main__":
    unittest.main()
