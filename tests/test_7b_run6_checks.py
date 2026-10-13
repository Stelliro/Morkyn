"""Fixes from the sixth Saltmarrow run on Qwen2.5 7B: checks, roles from prose, swallowed errors."""
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-7b-run6-checks-"))
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


def _one_person(conn, code, name, role):
    conn.execute("DELETE FROM npcs")
    if not conn.execute("SELECT 1 FROM locations WHERE id = 1").fetchone():
        conn.execute("INSERT INTO locations (id, code, name) VALUES (1, 'L1', 'Saltmarrow')")
    conn.execute("INSERT INTO npcs (code, name, role, location_id) VALUES (?, ?, ?, 1)", (code, name, role))


class SpeechIsNotAnAct(unittest.TestCase):
    """T3: "...before they pick the lower district clean" rolled lockpicking on a walk."""

    def _code(self, line):
        from app.skill_checks import infer_check_from_action

        check = infer_check_from_action(line, {})
        return (check or {}).get("skill_code")

    def test_a_word_in_the_quote_rolls_nothing(self):
        line = (
            "\"Then I'd best get my hauling done before they pick the lower district clean.\" "
            "I nod to Simon and head down to the salvage yard to see what the overseer has on the board today."
        )
        self.assertIsNone(self._code(line))
        self.assertIsNone(self._code("“Lift that, would you, and I'll pick the lock after.”"))

    def test_the_narrated_act_still_rolls(self):
        self.assertEqual(self._code("I pick the lock on the chest."), "lockpicking")
        self.assertEqual(self._code("I lift the crate. \"Heavy,\" I mutter."), "athletics")

    def test_speech_still_carries_a_social_check(self):
        self.assertEqual(self._code("\"Convince the reeve for me, I'm begging you.\""), "persuasion")
        self.assertEqual(self._code("\"Lift that crate for me?\" I ask Simon."), "persuasion")

    def test_a_quest_step_reads_the_act_not_the_question(self):
        from app.quests import match_quest_step

        quests = [{
            "id": 1, "code": "Q1", "title": "Polish swords", "current_step": 1, "total_steps": 1,
            "steps": [{"step_number": 1, "title": "Polish the swords on the rack"}],
        }]
        self.assertTrue(match_quest_step("I polish the swords on the rack. \"Good enough?\"", quests))
        self.assertIsNone(match_quest_step("\"Should I polish the swords on the rack?\"", quests))


class RoleFromTheIntroducingSentence(unittest.TestCase):
    """T3: NPC_NEW "Oldfield" "village reeve" with 'The overseer, a grizzled man named Oldfield'."""

    def _role(self, name, role, prose):
        from app import world
        from app.db import connect, init_db

        init_db()
        with connect() as conn:
            conn.execute("DELETE FROM npcs")
            return world._roles_stated_in_prose(conn, [{"name": name, "role": role}], prose)[0].get("role")

    def test_the_prose_job_wins(self):
        prose = "The lower district is busy. The overseer, a grizzled man named Oldfield [[B]], is scribbling on a ledger."
        self.assertEqual(self._role("Oldfield", "village reeve", prose), "overseer")
        self.assertEqual(self._role("Simon Pennick", "", "One of them, Simon Pennick, a wheelwright, stands out."), "wheelwright")
        self.assertEqual(self._role("Abel", "", "Abel, the woodcutter, hails you."), "woodcutter")

    def test_the_op_role_stays_when_the_sentence_names_it(self):
        prose = "A young apprentice named Isolde, the tallow chandler, rushes over."
        self.assertEqual(self._role("Isolde", "tallow chandler", prose), "tallow chandler")
        prose = "The trader at the post, a woman with a sharp gaze named Mira, nods."
        self.assertEqual(self._role("Mira", "trader", prose), "trader")

    def test_looks_are_not_a_job_and_known_people_keep_theirs(self):
        from app import world
        from app.db import connect, init_db

        self.assertEqual(self._role("Tam", "", "Tam, a tall man, waves."), "")
        init_db()
        with connect() as conn:
            _one_person(conn, "Z", "Oldfield", "reeve")
            out = world._roles_stated_in_prose(
                conn, [{"name": "Oldfield", "role": "reeve"}], "The overseer, a grizzled man named Oldfield, waits."
            )
        self.assertEqual(out[0]["role"], "reeve")


class NpcNoteInOneArgument(unittest.TestCase):
    """T9: NPC_NOTE "Oldfield B, village reeve, stern but fair" was dropped as malformed."""

    def test_code_and_fact_are_split(self):
        from app import turn_dsl

        turn = turn_dsl.parse_dsl_turn(
            '===NAR===\nOldfield nods.\n\n===OPS===\nNPC_NOTE "Oldfield B, village reeve, stern but fair"\n'
        )
        notes = [u for u in turn["index_updates"] if u.get("entity_type") == "npc"]
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["code"], "B")
        self.assertEqual(notes[0]["known_fact"], "village reeve, stern but fair")

    def test_a_name_without_code_resolves_by_name(self):
        from app import turn_dsl, world
        from app.db import connect, init_db

        turn = turn_dsl.parse_dsl_turn('===NAR===\nOldfield nods.\n\n===OPS===\nNPC_NOTE "Oldfield, stern but fair"\n')
        update = turn["index_updates"][0]
        self.assertEqual(update["name"], "Oldfield")
        init_db()
        with connect() as conn:
            _one_person(conn, "B", "Oldfield", "overseer")
            world._apply_index_updates(conn, [update])
            facts = conn.execute("SELECT known_facts FROM npcs WHERE code = 'B'").fetchone()[0]
        self.assertIn("stern but fair", facts)

    def test_the_two_argument_form_is_unchanged(self):
        from app import turn_dsl

        turn = turn_dsl.parse_dsl_turn('===NAR===\nOldfield nods.\n\n===OPS===\nNPC_NOTE B "keeps the yard ledger"\n')
        self.assertEqual(turn["index_updates"][0]["code"], "B")
        self.assertEqual(turn["index_updates"][0]["known_fact"], "keeps the yard ledger")


class UnsetContextSizeDoesNotRaise(unittest.TestCase):
    def test_blank_env_is_not_an_exception(self):
        from app import mle

        saved = os.environ.pop("AI_RPG_CONTEXT_TOKENS", None)
        try:
            os.environ["AI_RPG_CONTEXT_TOKENS"] = ""
            window, _auto = mle._context_request()
            self.assertGreater(window, 0)
            os.environ["AI_RPG_CONTEXT_TOKENS"] = "8192"
            self.assertEqual(mle._context_request(), (8192, False))
        finally:
            os.environ.pop("AI_RPG_CONTEXT_TOKENS", None)
            if saved is not None:
                os.environ["AI_RPG_CONTEXT_TOKENS"] = saved


if __name__ == "__main__":
    unittest.main()
