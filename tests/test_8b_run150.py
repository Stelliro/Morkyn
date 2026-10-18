"""8B run 150: faults fixed by class from T34 to T46.

T34: "Rafe ... watches from the corner. He's a man who speaks with actions,
not promises" seeded a drawn "Eadric Joliffe, eel trapper" for "a man".
T36: "I pick the crustacean back up" rolled lockpicking and made the owned
crab x2 on prose that only held it.
T37, T40: "I'll tell you if I'll do it" and "before I agree to anything" took
the job; Rafe's scroll errand was filed under his crab job.
T46: "You're doing good work ... the guild needs more hands, and you're
helping out" filed "Helping Out at the Guild".

Run:  .venv\\Scripts\\python -m unittest tests.test_8b_run150
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-run150-"))
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


def _pack(*names):
    from app.db import connect, init_db

    init_db()
    with connect() as conn:
        conn.execute("DELETE FROM inventory")
        for i, (name, qty) in enumerate(names):
            conn.execute("INSERT INTO inventory (code, name, quantity) VALUES (?, ?, ?)", (f"I{i + 1}", name, qty))


def _filter(changes, narration, line):
    from app import world
    from app.db import connect

    rejected: list = []
    with connect() as conn:
        kept = world._filter_inventory_changes(conn, changes, narration=narration, player_input=line, rejected=rejected)
    return kept, rejected


class PickingAThingUpIsNoLock(unittest.TestCase):
    def test_pick_back_up_rolls_nothing(self):
        from app.skill_checks import infer_check_from_action

        check = infer_check_from_action(
            "\"Then name it, Rafe. What does the reeve want from me?\" I pick the crustacean back up and wait for a straight answer."
        )
        self.assertFalse(check and check.get("skill_code") == "lockpicking", check)

    def test_picking_the_lock_still_rolls(self):
        from app.skill_checks import infer_check_from_action

        self.assertEqual((infer_check_from_action("I pick the lock on the chest.") or {}).get("skill_code"), "lockpicking")


class OwnThingPickedBackUp(unittest.TestCase):
    LINE = "\"Then name it, Rafe. What does the reeve want from me?\" I pick the crustacean back up and wait for a straight answer."
    PROSE = ("Rafe's jaw tightened as he stared at the crustacean in your hands. You held the crustacean tighter, the shell "
             "cool beneath your fingertips. “The reeve wants more than a name,” he said.")

    def test_the_crab_stays_one_crab(self):
        _pack(("crustacean", 1))
        kept, rejected = _filter([{"name": "crustacean", "quantity_delta": 1}], self.PROSE, self.LINE)
        self.assertEqual(kept, [], rejected)


class AFigureWhoIsTheManJustNamed(unittest.TestCase):
    PROSE = ("You leave the coins where they lie and ask Mabel what the other choice is. Rafe, the harbour reeve, watches "
             "from the corner of his office, his expression unreadable. He’s a man who speaks with actions, not promises, "
             "and his presence adds a subtle pressure to the moment.")

    def test_no_new_person_is_seeded_for_the_man(self):
        from app import world
        from app.db import connect, init_db

        init_db()
        with connect() as conn:
            conn.execute("DELETE FROM npcs")
            conn.execute("INSERT INTO npcs (code, location_id, name, role) VALUES ('A', 1, 'Mabel', 'tally clerk')")
            conn.execute("INSERT INTO npcs (code, location_id, name, role) VALUES ('B', 1, 'Rafe', 'harbour reeve')")
            seeded = world._ensure_npcs_from_narration(conn, {"npcs": []}, self.PROSE, 1)
            names = [str(n.get("name") or "") for n in seeded if isinstance(n, dict)]
        self.assertEqual(names, [], seeded)


class AConditionalYesIsNoYes(unittest.TestCase):
    LINES = [
        "\"A favor, then. Say what it is and I'll tell you if I'll do it.\" I put the crustacean back in my pack and listen.",
        "\"What does loading pay, and whose ship is it?\" I ask Rafe before I agree to anything.",
    ]

    def test_typed_accept_waits(self):
        from app.local_intel import typed_accept
        from app.quest_parser import player_accepts

        for line in self.LINES:
            self.assertFalse(typed_accept(line), line)
            self.assertFalse(player_accepts(line), line)

    def test_a_plain_yes_still_takes_it(self):
        from app.local_intel import typed_accept

        self.assertTrue(typed_accept("\"Cargo first. I'll do it.\" I roll up my sleeves."))


class AJobAboutAnotherThing(unittest.TestCase):
    def test_scroll_is_not_the_crab(self):
        from app.quest_parser import _same_job_subject

        self.assertFalse(_same_job_subject("Fetch a Scroll from the Reeve's Office", "Fetch the Crab from the Reeve"))
        self.assertFalse(_same_job_subject("Coral Wreck Salvage", "Loading the Cargo Crates"))

    def test_the_same_thing_reworded_is_the_same_job(self):
        from app.quest_parser import _same_job_subject

        self.assertTrue(_same_job_subject("Bring the Crab to the Reeve", "Fetch the Crab from the Reeve"))
        self.assertTrue(_same_job_subject("Salvage Job", "Clear the Wreck"))


class PraiseOfWorkIsNoJob(unittest.TestCase):
    def test_good_work_is_vetoed(self):
        from app import quest_offers as qo

        line = "You're doing good work, Flat-runner. The guild needs more hands, and you're helping out."
        self.assertEqual(qo._code_veto(line, asked_for_work=False), "praise_of_work")

    def test_an_offer_with_pay_stands(self):
        from app import quest_offers as qo

        line = "Good work. I've got another job for you: haul the nets in from the flats, two gold for the day."
        self.assertEqual(qo._code_veto(line, asked_for_work=False), "")


if __name__ == "__main__":
    unittest.main()
