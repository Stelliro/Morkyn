"""7B run 29 (Qwen2.5 7B on MLE, agent as player): one accept takes one job; a pointer is no job; pay ahead counts."""
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-7b-run29-"))
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


T4_LINE = ('"Paying before the work\'s done? Generous." I tuck the pouch away. "All right, Oswin, I\'ll take the job. '
           'Where\'s the ship and what needs pulling off it?"')


class OneAcceptOneJob(unittest.TestCase):
    """T4: "I'll take the job. Where's the ship" took both "Visit the guild for work" and the ship job."""

    def test_the_ship_job(self):
        from app.local_intel import typed_offer_choice
        from app.quest_parser import _means_this_offer

        guild = {"id": 1, "title": "Visit the guild for work", "giver": "Oswin Sadler", "status": "offered"}
        ship = {"id": 2, "title": "Salvage a damaged ship", "giver": "", "status": "offered"}
        self.assertIs(typed_offer_choice([ship, guild], T4_LINE), ship)
        self.assertFalse(_means_this_offer(guild, [guild, ship], T4_LINE))
        self.assertTrue(_means_this_offer(ship, [guild, ship], T4_LINE))
        # The giver's name alone still picks between offers with no title word said.
        tower = {"id": 3, "title": "Ring the tower bell", "giver": "Una Bell", "status": "offered"}
        bread = {"id": 4, "title": "Carry the bread", "giver": "Hal Garner", "status": "offered"}
        self.assertIs(typed_offer_choice([tower, bread], "I'll take the job, Hal."), bread)


class APointerIsNoJob(unittest.TestCase):
    """T1: "You might want to head over to the guild and see if they have any tasks" became a job."""

    def test_pointer(self):
        from app.quest_parser import points_elsewhere_for_work

        self.assertTrue(points_elsewhere_for_work(
            "Visit the guild for work",
            "You might want to head over to the guild and see if they have any tasks for you. They usually offer something by now.",
            "The guildhall is just a short walk away.",
        ))
        self.assertTrue(points_elsewhere_for_work("Ask at the harbour", "Try down at the harbour, see if anyone needs hands."))

    def test_real_offers_kept(self):
        from app.quest_parser import points_elsewhere_for_work

        for title, line in (
            ("Copy tidal maps for the week", "I could use someone to copy the tidal chart for the week. It's a tedious job, but the pay is decent."),
            ("Sort salvaged goods", "I need you to help with the sorting of salvaged goods. You'll find the details on the board there."),
            ("Retrieve the tide-reckoner", "Retrieve the missing tide-reckoner from the old tide-watcher's cottage near the northern docks."),
            ("Find work for the guild", "Go see if they have work at the guild, it pays five gold a day."),
        ):
            self.assertFalse(points_elsewhere_for_work(title, line), title)


class GettingThereIsNotTheWork(unittest.TestCase):
    """T5: "I head down to the docks ... to find the damaged ship" finished and paid the salvage job."""

    NARRATION = ("You head down to the docks by the old warehouse to find the damaged ship. The wooden planks creak. "
                 "\"You can start by helping to secure the rigging and patch the hull.\"")

    def _check(self, title, evidence, narration=None):
        from app.quest_parser import validate_quest_changes

        quest = {"id": 2, "code": "Q2", "title": title, "status": "active", "current_step": 1, "total_steps": 1,
                 "current_step_text": "Go to the harbor Reach the damaged ship for salvage work"}
        accepted, rejected = validate_quest_changes(
            {"updates": [{"quest": "Q2", "action": "step_done", "evidence": evidence}]},
            narration=narration or self.NARRATION,
            player_input="I head down to the docks by the old warehouse to find the damaged ship.",
            existing=[quest],
        )
        return accepted["updates"], [r["reasons"] for r in rejected]

    def test_travel_quote_refused(self):
        done, why = self._check("Salvage a damaged ship", "You head down to the docks by the old warehouse to find the damaged ship.")
        self.assertEqual(done, [])
        self.assertTrue(why)

    def test_arrival_refused_for_work_but_kept_for_a_trip(self):
        narration = "You reach the old warehouse at the water's edge, where the damaged ship lies."
        done, _ = self._check("Salvage a damaged ship", "You reach the old warehouse at the water's edge, where the damaged ship lies.", narration)
        self.assertEqual(done, [])
        narration = "You reach the mill and the miller takes the letter from your hand."
        done, _ = self._check("Deliver the letter to the mill", "You reach the mill and the miller takes the letter from your hand.", narration)
        self.assertEqual(len(done), 1)

    def test_purpose_is_not_a_result(self):
        from app.quest_parser import _shows_result

        self.assertFalse(_shows_result("You head out to find the crate."))
        self.assertTrue(_shows_result("You find the crate under the nets."))


class PayAheadCountsAsThePay(unittest.TestCase):
    """T3: the ship job's 11 gold was handed over while it was only offered; T5 paid 11 again."""

    def test_recorded_and_not_paid_twice(self):
        from app import world
        from app.db import connect, init_db
        from app.quests import pay_quest_reward

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        narration = (
            "Ellen looks at the notice. \"That's the ship down by the saltworks. You can speak with Oswin Sadler about it.\"\n\n"
            "Oswin Sadler hands you a small pouch, containing 11 gold. \"There's the payment. It's a tricky job, but I'm sure "
            "you can handle it.\""
        )
        with connect() as conn:
            conn.execute("INSERT INTO npcs (code, name, role, location_id) VALUES ('B', 'Oswin Sadler', 'furrier', 1)")
            conn.execute(
                "INSERT INTO quests (code, title, description, status, reward_gold, reward_xp, notes) "
                "VALUES ('Q2', 'Salvage a damaged ship', '', 'offered', 11, 18, 'parser:parser')"
            )
            qid = conn.execute("SELECT id FROM quests WHERE code = 'Q2'").fetchone()[0]
            report = world._settle_story_terms_and_pay(
                conn, {"player": {"gold_delta": 11}}, {"status": "empty", "created": [], "updated": []},
                narration=narration, player_input='"Who do I see about this salvage job, and what does it pay?"',
                turn=4, skip_ids=set(), gold_note={"source": "prose_received"},
            )
            self.assertEqual(report["updated"][-1]["action"], "paid_in_advance")
            row = conn.execute("SELECT reward_gold, notes FROM quests WHERE id = ?", (qid,)).fetchone()
            self.assertEqual(row["reward_gold"], 0)
            self.assertIn("paid_in_advance:11", row["notes"])
            conn.execute("UPDATE quests SET status = 'active' WHERE id = ?", (qid,))
            paid = pay_quest_reward(conn, qid, turn=6)
            self.assertEqual(paid["gold"], 0)
            self.assertGreater(paid["xp"], 0)

    def test_coin_for_a_finished_job_still_finishes_it(self):
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        with connect() as conn:
            conn.execute("INSERT INTO npcs (code, name, role, location_id) VALUES ('C', 'Hal Garner', 'chandler', 1)")
            npc = conn.execute("SELECT id FROM npcs WHERE code = 'C'").fetchone()[0]
            conn.execute(
                "INSERT INTO quests (code, title, description, status, reward_gold, reward_xp, giver_npc_id, total_steps, current_step) "
                "VALUES ('Q5', 'Sort the nets', '', 'active', 4, 10, ?, 1, 1)", (npc,),
            )
            report = world._settle_story_terms_and_pay(
                conn, {"player": {"gold_delta": 4}}, {"status": "empty", "created": [], "updated": []},
                narration="Hal Garner counts four gold into your palm. \"For the work. You've earned it.\"",
                player_input="I hand Hal the last sorted net.", turn=9, skip_ids=set(), gold_note={"source": "prose_received"},
            )
            self.assertEqual(report["updated"][-1]["source"], "story_pay")


if __name__ == "__main__":
    unittest.main()
