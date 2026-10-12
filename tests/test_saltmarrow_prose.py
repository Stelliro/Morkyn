"""Prose-pass fixes from the Saltmarrow API-bridge run (docs/showcase/saltmarrow-findings.md).

#97 overreach trim, #108 empty quote, #109 tags inside names, #110 silent closing cut,
#78 speech memory and name knowledge, #23 fact titles.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-saltmarrow-prose-"))
_ENV = isolated_data_env(str(_TMP))
os.environ.update(_ENV)

from app import llm  # noqa: E402
from app.conversation import introduces_self, spoken_lines  # noqa: E402
from app.narration_pipeline import drop_speech_said_before, drop_untold_name  # noqa: E402
from app.world_facts import _title_for  # noqa: E402

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


def _dropped(text, line):
    return llm.drop_invented_player_acts_text(text, line)[1]


class TrimKeepsThePlayersOwnWork(unittest.TestCase):
    """#97: the player's stated work, worded differently, was cut as an invented act."""

    def test_reworded_work_stays(self):
        cases = [
            ("I take the bell rope Mam has tied to the clapper and ring it. Hard.", "You pull. You pull harder."),
            ("Hereward, Tam and I haul Wat's cart up the harbour stairs.", "You take the shafts."),
            (
                "I pin them up on the tally board, over the guild contracts.",
                "You take the nails out of the top row and put the figures up over the guild's sheets.",
            ),
            (
                "I put her hand on the bell rope beside mine, and we ring the high water.",
                "You take your mother's hand and put it on the bell rope above yours, and you pull together.",
            ),
            (
                "I untie the rope and we crawl back along the planks toward the door.",
                "You go back along the planks the way you came.",
            ),
            (
                "I lie flat and crawl up the ramp on my belly, testing each handhold.",
                "You push with your good leg and test every lump before you give it any weight.",
            ),
        ]
        for line, prose in cases:
            self.assertEqual(_dropped(prose, line), [], line)

    def test_engine_mishap_of_the_stated_climb_stays(self):
        line = "I limp along the channel floor until the bank is low and firm, then climb out there."
        prose = "You twist to get the other leg up and something in your side catches, and you slide back off the bank."
        self.assertEqual(_dropped(prose, line), [])

    def test_invented_acts_still_go(self):
        self.assertTrue(_dropped("For a moment you think he is right.", "I step back and take her hand."))
        self.assertTrue(_dropped("You leave the charcoal on its string.", "I take a fresh stick of charcoal from the box."))
        self.assertTrue(_dropped("You grab at the wrist and get a sleeve.", "!wait -1 sleep"))
        self.assertTrue(_dropped("You take the bread from the shelf.", "I ask the baker about the road north."))


class NameRepairAndQuotes(unittest.TestCase):
    """#108, #109."""

    def test_name_only_line_leaves_no_empty_quote(self):
        out, removed = drop_untold_name(
            '"Isk Tarrow," Jocosa repeats, and something in her face changes.', ["Isk Tarrow", "Isk", "Tarrow"]
        )
        self.assertNotIn('""', out)
        self.assertEqual(out, "Something in her face changes.")
        self.assertTrue(removed)

    def test_trailing_name_still_goes(self):
        out, _ = drop_untold_name('"What can I do for you, Isk?" she asks.', ["Isk"])
        self.assertEqual(out, '"What can I do for you?" she asks.')

    def test_no_tag_inside_an_unknown_place_name(self):
        text = "Over its lintel someone has painted Philippa Kemp's General Store."
        out = llm._repair_prose_entity_labels(text, {"A": "Philippa Kemp"})
        self.assertNotIn("[[A]]'s General Store", out)
        self.assertIn("Philippa Kemp's General Store", out)

    def test_unnamed_description_keeps_no_name(self):
        out = llm._repair_prose_entity_labels("A woman in a fish-scaled apron [[O]] comes in for wicks.", {"O": "Ursula"})
        self.assertNotIn("Ursula", out)
        self.assertIn("a fish-scaled apron comes in", out)
        out = llm._repair_prose_entity_labels("You hand the rope to [[H]].", {"H": "Tam Kemp"})
        self.assertIn("Tam Kemp [[H]]", out)


class ClosingParagraphsSurviveHandoff(unittest.TestCase):
    """#110: the handoff kept 8 segments, so a 9-paragraph scene lost its close."""

    def test_ninth_paragraph_kept(self):
        paragraphs = [
            "Baldwin Thorne looks at the page in your hand.",
            "Then he takes it between finger and thumb and tears it in half.",
            "The crowd makes a sound like a wave drawing back over shingle.",
            "Hereward speaks, and his voice is not thin any more.",
            "He turns to the crowd and tells them what the page said.",
            "Thorne's smile does not move, but something behind it does.",
            "He calls his clerk overwrought, mildly, to nobody in particular.",
            "Wulfstan dares him to read the next one, very loudly, from your other side.",
            "Thorne does not move toward the board. The crowd watches him not move toward the board.",
        ]
        turn = {
            "narration": "\n\n".join(paragraphs),
            "narration_segments": [{"label": "paragraph", "text": p} for p in paragraphs],
            "self_check": {},
        }
        out = llm._clean_turn_for_handoff(turn, "dsl_to_verify", [])
        self.assertIn("The crowd watches him not move toward the board.", out["narration"])
        self.assertIn("Wulfstan dares him", out["narration"])


class SpeechMemory(unittest.TestCase):
    """#78: who said what, and who was told the name."""

    ROWS = [{"code": "H", "name": "Tam Kemp", "aliases": []}, {"code": "K", "name": "Mara Tarrow", "aliases": []}]

    def test_possessive_is_not_the_speaker_and_scare_quotes_are_not_speech(self):
        narration = (
            'Tam Kemp [[H]] has come up the stair. "Don\'t ask me," he says. He looks at Mara\'s hand on her chest, '
            'and his voice drops. "She can\'t, can she. She can\'t talk." Tam opens his mouth, and the word "aunt" stops it.'
        )
        lines = spoken_lines(narration, self.ROWS, "")
        self.assertEqual([e["code"] for e in lines], ["H", "H"])
        self.assertNotIn("aunt", [e["line"] for e in lines])

    def test_link_markup_not_stored_in_lines(self):
        lines = spoken_lines('Tam says, "That\'s Mara Tarrow [[K]]. She didn\'t drown."', self.ROWS, "")
        self.assertEqual(lines[0]["line"], "That's Mara Tarrow. She didn't drown.")

    def test_another_speakers_words_do_not_cut_a_line(self):
        unit = '"Tam signed for the customs bell yesterday, before anyone else," Philippa says.'
        earlier = ["Tam signed for the customs bell yesterday, before anyone else."]
        kept, dropped = drop_speech_said_before([unit], earlier, [], "", ["D"], {unit: "A"})
        self.assertEqual(dropped, [])
        kept, dropped = drop_speech_said_before([unit], earlier, [], "", ["A"], {unit: "A"})
        self.assertTrue(dropped)
        kept, dropped = drop_speech_said_before([unit], earlier, [], "", ["D"], {})
        self.assertTrue(dropped)  # speaker unknown: anyone's earlier line still counts

    def test_giving_the_name_counts(self):
        names = ["Isk Tarrow"]
        self.assertTrue(introduces_self('I walk up the bank. "Isk Tarrow. Thank you."', names))
        self.assertTrue(introduces_self('I don\'t move. "It\'s Isk. It\'s me, Mam."', names))
        self.assertTrue(introduces_self("I take the pen and write my name in the book: Isk Tarrow.", names))
        self.assertTrue(introduces_self("I wait at the window to sign for the customs bell.", names))
        self.assertFalse(introduces_self("I ask Tam where Isk Tarrow's boat is.", names))


class FactTitles(unittest.TestCase):
    """#23: custom_style facts got garbled first-words titles."""

    def test_titles(self):
        self.assertEqual(_title_for("A drowned harbour town at the edge of mudflats the sea left behind."), "Drowned harbour town")
        self.assertEqual(_title_for("Salvage, debt and a tide that keeps the wrong hours."), "Salvage, debt and a tide")
        self.assertEqual(_title_for("Snow closes the high passes."), "Snow and high passes")
        self.assertEqual(_title_for("Magic is rare."), "Rare magic")


if __name__ == "__main__":
    unittest.main()
