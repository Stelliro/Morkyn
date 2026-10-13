"""7B run 5 leaks: the duty line pasted into the prose (#83) and op/packet/meta text (#131)."""
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-7b-run5-leaks-"))
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


BODY = (
    "You haul the last crate up the ladder and set it down on the deck, the salt wind cold on your face. "
    "Abel watches you work, his axe resting against the rail."
)


class DutyIsAFlagNotASentence(unittest.TestCase):
    """#83 reopened: the packet's duty sentence was pasted into the prose (T12, T37, T97, T99)."""

    def _person(self, duty):
        from app import prompts

        context = {
            "current_location": {"id": 1, "name": "The Blind Pike Tavern"},
            "locations": [{"id": 1, "name": "The Blind Pike Tavern", "npcs": [
                {"name": "Verity", "code": "H", "role": "tavern keeper", "duty": duty},
            ]}],
        }
        return prompts._place_view(context)["people"][0]

    def test_off_duty_person_here_is_not_said_to_be_at_home(self):
        person = self._person({"on_duty": False, "shift": "15:30-01:30", "off_duty_likely": "asleep at home"})
        self.assertIs(person["working"], False)
        text = repr(person)
        for leak in ("asleep", "at home", "shift", "15:30", "duty"):
            self.assertNotIn(leak, text)

    def test_on_duty_and_an_override_reason(self):
        person = self._person({"on_duty": True, "shift": "08:00-18:00", "reason": "covering a shift"})
        self.assertIs(person["working"], True)
        self.assertEqual(person["working_because"], "covering a shift")
        self.assertNotIn("08:00", repr(person))

    def test_the_ask_says_everyone_listed_is_here(self):
        from app.turn_dsl import DSL_SYSTEM_PROMPT

        self.assertIn("Everyone listed under people is here", DSL_SYSTEM_PROMPT)
        self.assertNotIn("duty says whether", DSL_SYSTEM_PROMPT)

    def test_duty_note_is_kept_for_tools_only(self):
        from app import shifts

        self.assertIn("off duty", shifts.duty_note({"on_duty": False, "shift": "22:00-06:00"}))
        self.assertEqual(shifts.working_fields(None), {})


class AttitudeIsAPlainWord(unittest.TestCase):
    """#131 T19: "attitude":"Dismissive" became "gives you a Dismissive look"."""

    def test_packet_attitude_is_lowercase(self):
        from app import prompts

        view = prompts._mechanics_view({"mechanics_context": {"resolved_checks": [{
            "skill_code": "persuasion", "outcome": "partial", "social_attitude": "Dismissive",
            "social_direction": "NPC reaction lean: Dismissive. Honor traits.",
        }]}})
        row = view["resolved_checks"][0]
        self.assertEqual(row["attitude"], "dismissive")
        self.assertNotIn("Dismissive", row["direction"])


class MetaLeaksRepaired(unittest.TestCase):
    """#131 shapes, as shipped in run 5."""

    def repair(self, text):
        from app.prose_state import repair_meta_leaks

        return repair_meta_leaks(text)

    def test_op_lines_go(self):  # T6
        text = BODY + (
            "\n\nThe GOAL is to finish the task and return to your duties on the ship.\n"
            "The FOCUS is on the task you completed and the acknowledgment from Everard.\n"
            "The NPC is Everard Kemp, a hunter who has noticed your efforts.\n"
            "The SCENE is a busy ship deck with crates and tangled ropes."
        )
        out, fixes = self.repair(text)
        self.assertEqual(out, BODY)
        self.assertEqual([f["why"] for f in fixes], ["op_line"] * 4)

    def test_label_lines_go(self):  # T12, T18, T19, T27
        for label in (
            "Abel Hollis [[D]] (D) - woodcutter (on duty (shift 08:00-18:00))",
            "Roger [[A]]",
            "Roger Sowerby [[A]]",
            "The Blind Pike [[L7]]",
        ):
            out, fixes = self.repair(BODY + "\n\n" + label)
            self.assertEqual(out, BODY, label)
            self.assertEqual(fixes[0]["why"], "label_line")

    def test_a_list_and_a_named_sentence_stay(self):  # T69's board, ordinary prose
        text = BODY + "\n\nThe board reads:\n- Abel Hollis [[D]]: 3 barrels of flour\n- Verity [[H]]: 2 sacks of fish"
        self.assertEqual(self.repair(text), (text, []))
        text = BODY + "\n\nRoger [[A]] looks up from his ledger."
        self.assertEqual(self.repair(text), (text, []))
        text = BODY + '\n\nVerity [[H]] - "Two coins," she says.'
        self.assertEqual(self.repair(text)[0], text)

    def test_stage_directions_and_status_line_go(self):  # T31, T92, T23
        text = (
            BODY + " The focus shifts to the task at hand, and the uncertainty of the salvage job ahead.\n\n"
            "The scene is about to change as you step into a new location: the Blind Pike [[L7]] Tavern.\n\n"
            "You are fine, with 19/20 health."
        )
        out, fixes = self.repair(text)
        self.assertEqual(out, BODY)
        self.assertEqual(sorted(f["why"] for f in fixes), ["stage_direction", "stage_direction", "status_line"])

    def test_the_scene_in_the_story_stays(self):
        text = BODY + " The scene below the cliff is grim: three hulls broken on the rocks."
        self.assertEqual(self.repair(text), (text, []))

    def test_packet_keys_markdown_and_attitude(self):  # T100, T4, T71, T19
        out, fixes = self.repair(
            "You put the small, tarnished brass_key on a string. The open_offers remain. "
            "The hold of the _Sea Sprite_ needs cleaning in the *Saltsort* yards. "
            "Roger gives you a Dismissive look and turns away."
        )
        self.assertEqual(
            out,
            "You put the small, tarnished brass key on a string. The open offers remain. "
            "The hold of the Sea Sprite needs cleaning in the Saltsort yards. "
            "Roger gives you a dismissive look and turns away.",
        )
        self.assertEqual(sorted({f["why"] for f in fixes}), ["attitude_label", "markdown", "packet_key"])

    def test_a_scene_that_is_all_leak_is_left(self):
        text = "Roger [[A]]"
        self.assertEqual(self.repair(text), (text, []))


class BandCoinBecomesTheAmount(unittest.TestCase):
    """#131 T72: "hands over a moderate bag of coin" while the engine moved a number."""

    def test_one_phrase_and_a_moved_amount(self):
        from app.prose_state import settle_band_coin

        text = "Abel Hollis [[D]] nods and hands over a moderate bag of coin for your efforts."
        out, fix = settle_band_coin(text, 12)
        self.assertEqual(out, "Abel Hollis [[D]] nods and hands over 12 gold for your efforts.")
        self.assertEqual(fix["why"], "band_coin")

    def test_nothing_moved_or_two_phrases_left(self):
        from app.prose_state import settle_band_coin

        text = "He hands over a small bag of coin."
        self.assertEqual(settle_band_coin(text, 0), (text, None))
        two = text + " Then a large purse of gold."
        self.assertEqual(settle_band_coin(two, 9), (two, None))


class ReconcileRepairsAndNotes(unittest.TestCase):
    """The repairs run in apply's reconcile step and are listed in the turn ledger."""

    def test_reconcile_and_ledger(self):
        from app import turn_ledger, world
        from app.db import connect, init_db

        init_db()
        result = {"narration": BODY + "\n\nRoger [[A]]\n\nYou are fine, with 19/20 health.", "player": {}}

        @turn_ledger.recorded("turn")
        def run():
            with connect() as conn:
                return world._reconcile_prose_with_state(conn, result, rejected=[], movement_report={},
                                                         gold_note=None, purse_note=None)

        report = run()
        self.assertEqual(world._narration_text(result), BODY)
        self.assertEqual(sorted(e["why"] for e in report["trimmed"]), ["label_line", "status_line"])
        notes = turn_ledger.last_finished()["notes"]
        self.assertEqual([n["decision"] for n in notes], ["meta_leak_repaired", "meta_leak_repaired"])


if __name__ == "__main__":
    unittest.main()
