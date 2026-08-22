"""Regression tests: asked for a name, the world gives one.

From a 100-turn continuity probe. "The sealed letter is addressed to Corvin
Marrow" was planted on turn 2. On turn 26 the model read the name aloud when
asked. On turn 94, asked the identical question, it wrote

    ...the name you read brings a weight to your chest...

and never said it. It knew the letter existed and volunteered an unrelated
debt in the same paragraph; it just would not commit to the name.

The rule under test: reuse the established name when the world has one, mint
and record one when it does not, and never leave the question unanswered.

Run:  python -m unittest tests.test_naming
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-naming-test-"))
_ENV = {
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
}
os.environ.update(_ENV)

import app.naming as naming  # noqa: E402
from app.db import connect, db_path, init_db  # noqa: E402


def _assert_isolated() -> None:
    if not str(db_path()).startswith(str(_TMP)):
        raise AssertionError(f"test isolation failed: AI_RPG_DB resolves to {db_path()!r}")


def setUpModule() -> None:
    """Re-pin paths: unittest imports every test module before running any test."""
    os.environ.update(_ENV)
    _assert_isolated()


_assert_isolated()
init_db()


def _fresh(rows: list[tuple[str, str]] | None = None):
    """A connection with a clean ledger and an optional journal history."""
    conn = connect()
    conn.execute("DELETE FROM name_ledger")
    conn.execute("DELETE FROM journal")
    for kind, content in rows or []:
        conn.execute("INSERT INTO journal (turn, kind, content) VALUES (0, ?, ?)", (kind, content))
    return conn


PLANT = (
    "I say my name aloud so it is heard: Ash Vale. I explain that I carry a sealed "
    "letter addressed to a man named Corvin Marrow, and that it must not be opened."
)
PROBE = (
    "I take out the sealed letter and read the name written on it aloud, "
    "so there is no confusion about who it is for."
)
DODGE = (
    "You take out the sealed letter and the air shifts. The name you read brings a "
    "weight to your chest, a slow heavy throb that spreads outward."
)


class TestDemandDetection(unittest.TestCase):
    def test_the_probe_that_failed_is_detected(self):
        self.assertTrue(naming.name_request_intent(PROBE)["asked"])

    def test_ways_of_asking(self):
        for line in (
            "I ask the bargeman what his name is.",
            "I read out the name on the parcel.",
            "Who is it addressed to?",
            "I ask for their name before going further.",
            "What are you called?",
            "I introduce myself to the guard.",
        ):
            with self.subTest(line=line):
                self.assertTrue(naming.name_request_intent(line)["asked"], line)

    def test_ordinary_prose_is_not_a_demand(self):
        # "name" is a common word; triggering on it made every third turn a demand.
        for line in (
            "I carve my initials into the post.",
            "I look for a name I recognise among the notices.",
            "I make a name for myself by taking the harder job.",
            "The names of the dead are painted on the wall.",
            "I walk a short way along the most promising path, staying alert.",
        ):
            with self.subTest(line=line):
                self.assertFalse(naming.name_request_intent(line)["asked"], line)


class TestSubjectExtraction(unittest.TestCase):
    """A live run keyed the letter's name under the participle "written".

    Because nothing in history matched the subject "written", the resolver fell
    through to minting and produced a name that *contradicted* the established
    one. Wrong subject is worse than no answer, so these are pinned.
    """

    def test_the_probe_keys_to_the_letter(self):
        self.assertEqual(naming.subject_key(PROBE, ["sealed letter"]), "letter")

    def test_the_probe_keys_to_the_letter_without_help(self):
        self.assertEqual(naming.subject_key(PROBE, []), "letter")

    def test_asking_a_stranger_keys_to_the_stranger(self):
        self.assertEqual(
            naming.subject_key("I ask the nearest stranger what their name is.", []), "stranger"
        )

    def test_never_keys_to_a_function_word_or_participle(self):
        for line in (
            PROBE,
            "I ask the nearest stranger what their name is.",
            "I read out the name written on the parcel.",
            "Who is it addressed to?",
        ):
            with self.subTest(line=line):
                key = naming.subject_key(line, [])
                self.assertNotIn(key, {"written", "what", "read", "name", "and", "nearest"}, key)

    def test_world_entity_name_wins_over_a_generic_head(self):
        key = naming.subject_key(
            "I show the guard the wax-sealed letter and ask who it is addressed to.",
            ["wax-sealed letter"],
        )
        self.assertEqual(key, "letter")


class TestReuseEstablishedName(unittest.TestCase):
    def test_recovers_the_name_the_player_committed(self):
        conn = _fresh([("player", PLANT)])
        with conn:
            got = naming.resolve_name_demand(conn, PROBE, known_names=["sealed letter"], turn=94)
        self.assertTrue(got["asked"])
        self.assertIn("Marrow", got["name"])
        self.assertEqual(got["source"], "history")

    def test_player_statement_outranks_narration(self):
        conn = _fresh([
            ("narration", "The letter, they say, is for one Bellwright Hux."),
            ("player", PLANT),
        ])
        with conn:
            got = naming.resolve_name_demand(conn, PROBE, known_names=["sealed letter"], turn=30)
        self.assertIn("Marrow", got["name"])

    def test_second_asking_matches_the_first(self):
        conn = _fresh([("player", PLANT)])
        with conn:
            first = naming.resolve_name_demand(conn, PROBE, known_names=["sealed letter"], turn=26)
            second = naming.resolve_name_demand(conn, PROBE, known_names=["sealed letter"], turn=94)
        self.assertEqual(first["name"], second["name"])
        self.assertEqual(second["source"], "ledger", "the answer should be pinned after the first ask")


class TestMintWhenNothingEstablished(unittest.TestCase):
    def test_mints_a_name_rather_than_answering_nothing(self):
        conn = _fresh()
        with conn:
            got = naming.resolve_name_demand(conn, PROBE, known_names=["sealed letter"], turn=5)
        self.assertTrue(got["name"], "a demand must never resolve to an empty name")
        self.assertEqual(got["source"], "minted")

    def test_minted_names_are_stable_across_asks(self):
        conn = _fresh()
        with conn:
            first = naming.resolve_name_demand(conn, PROBE, known_names=["sealed letter"], turn=5)
            second = naming.resolve_name_demand(conn, PROBE, known_names=["sealed letter"], turn=60)
        self.assertEqual(first["name"], second["name"])

    def test_minting_is_deterministic_for_the_same_subject(self):
        self.assertEqual(naming.mint_name("letter"), naming.mint_name("letter"))
        self.assertNotEqual(naming.mint_name("letter"), naming.mint_name("ledger"))

    def test_the_players_own_name_answers_a_self_demand(self):
        conn = _fresh()
        with conn:
            got = naming.resolve_name_demand(
                conn, "I introduce myself to the guard.", turn=3, player_name="Ash Vale"
            )
        self.assertEqual(got["name"], "Ash Vale")
        self.assertEqual(got["source"], "player")


class TestRepairTheDodge(unittest.TestCase):
    def test_dodging_narration_gets_the_name_appended(self):
        resolved = {"asked": True, "kind": "written", "subject": "letter", "name": "Corvin Marrow"}
        fixed, repaired = naming.enforce_named_answer(DODGE, resolved)
        self.assertTrue(repaired)
        self.assertIn("Corvin Marrow", fixed)
        self.assertTrue(fixed.startswith("You take out the sealed letter"), "original prose is kept")

    def test_narration_that_already_answers_is_left_alone(self):
        resolved = {"asked": True, "kind": "written", "subject": "letter", "name": "Corvin Marrow"}
        good = "You read it aloud: Corvin Marrow. The name hangs in the cold air."
        fixed, repaired = naming.enforce_named_answer(good, resolved)
        self.assertFalse(repaired)
        self.assertEqual(fixed, good)

    def test_surname_alone_counts_as_answering(self):
        resolved = {"asked": True, "kind": "written", "subject": "letter", "name": "Corvin Marrow"}
        fixed, repaired = naming.enforce_named_answer("You say it: Marrow, of the low ward.", resolved)
        self.assertFalse(repaired)

    def test_no_repair_when_no_name_was_demanded(self):
        text = "You walk on through the rain."
        fixed, repaired = naming.enforce_named_answer(text, {"asked": False, "name": ""})
        self.assertFalse(repaired)
        self.assertEqual(fixed, text)


class TestContract(unittest.TestCase):
    def test_established_name_is_stated_as_already_committed(self):
        contract = naming.naming_contract(
            {"asked": True, "kind": "written", "subject": "letter", "name": "Corvin Marrow", "source": "history"}
        )
        self.assertIsNotNone(contract)
        self.assertEqual(contract["name"], "Corvin Marrow")
        self.assertIn("already committed", contract["rule"])

    def test_minted_name_is_stated_as_the_new_answer(self):
        contract = naming.naming_contract(
            {"asked": True, "kind": "written", "subject": "letter", "name": "Hollowbrand", "source": "minted"}
        )
        self.assertIn("none was ever established", contract["rule"])
        self.assertIn("Hollowbrand", contract["rule"])

    def test_no_contract_without_a_demand(self):
        self.assertIsNone(naming.naming_contract({"asked": False, "name": ""}))
        self.assertIsNone(naming.naming_contract(None))


class TestNarrationTextRoundTrip(unittest.TestCase):
    """The repair has to land where the prose actually lives.

    The first wiring wrote only `result["narration"]`. The deterministic
    fallback fills `narration_segments` instead, and the payload and journal are
    rebuilt from the segments -- so the repair reported `repaired: True` and the
    player saw no change at all. Both keys must move together.
    """

    def test_reads_prose_out_of_segments_when_narration_is_empty(self):
        from app.world import _narration_text_of

        turn = {
            "narration": "",
            "narration_segments": [
                {"label": "paragraph", "text": "You step into the square."},
                {"label": "paragraph", "text": "Rain starts up again."},
            ],
        }
        text = _narration_text_of(turn)
        self.assertIn("You step into the square.", text)
        self.assertIn("Rain starts up again.", text)

    def test_prefers_narration_when_present(self):
        from app.world import _narration_text_of

        turn = {"narration": "Real prose.", "narration_segments": [{"text": "stale"}]}
        self.assertEqual(_narration_text_of(turn), "Real prose.")

    def test_writing_updates_both_places(self):
        from app.world import _narration_text_of, _set_narration_text

        turn = {"narration": "", "narration_segments": [{"label": "paragraph", "text": "Old."}]}
        _set_narration_text(turn, "One.\n\nTwo. The name is Corvin Marrow.")
        self.assertIn("Corvin Marrow", turn["narration"])
        joined = " ".join(str(s.get("text") or "") for s in turn["narration_segments"])
        self.assertIn("Corvin Marrow", joined, "segments still hold the pre-repair prose")
        self.assertEqual(len(turn["narration_segments"]), 2)
        self.assertIn("Corvin Marrow", _narration_text_of(turn))

    def test_single_paragraph_still_produces_a_segment(self):
        from app.world import _set_narration_text

        turn: dict = {}
        _set_narration_text(turn, "Just the one line.")
        self.assertEqual(len(turn["narration_segments"]), 1)
        self.assertEqual(turn["narration_segments"][0]["text"], "Just the one line.")


class TestLedgerIsWriteOnce(unittest.TestCase):
    def test_first_writer_wins(self):
        conn = _fresh()
        with conn:
            naming.ledger_record(conn, "letter", "Corvin Marrow", source="history", turn=2)
            naming.ledger_record(conn, "letter", "Someone Else", source="minted", turn=90)
            self.assertEqual(naming.ledger_lookup(conn, "letter"), "Corvin Marrow")


if __name__ == "__main__":
    unittest.main()
