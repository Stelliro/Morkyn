"""#157 (c), integ-r4 replay (Hermes 3 8B, round-4 code): who the records say keeps the clinic.

T1 "I go into the clinic.": the prose introduced "Dr. Vasilis [[B]], a
middle-aged man with graying hair" behind the counter. The engine filed
Vasilis, and then seeded a second, drawn person "Wyatt" from "a middle-aged
man", which is Vasilis's own apposition. Wyatt took the clinic's trade
(doctor), the counter (keeper_npc_id) and Vasilis's sentence as his summary.
T2's packet then told the narrator Wyatt [[C]] is the doctor and keeps the
clinic, and the prose followed the records: "a grizzled doctor, Wyatt [[C]]
... a passerby named Vasilis [[B]]". The narrator was told the wrong fact;
the fix is the record, not the prose.

The fix: the people the prose introduces this turn are known to the figure
hints, so an introduced person's own apposition is them. A second rule that
handed the venue's trade to the first role-less introduction was taken out
(round-5 skeptic): it made the named customer the doctor ("Jory Pike ...
waits on the bench. A woman in a white coat calls out") and the real keeper
a roofer. Those probes are kept below so the trade stays with the figure the
prose puts behind the counter.

Strings are copied from the run's traces (turn-6b5a9245-000002-player.json,
final_turn.narration; -000003 prompt_context.current_location.keeper) and
from the skeptic's probes (verify5-roles-scratch/probe.py, probe2.py).
No model ask is involved in this path.
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-integ-r4-roles-"))
_ENV = isolated_data_env(str(_TMP))
_SAVED_ENV: dict[str, str | None] = {}


def setUpModule():
    _SAVED_ENV.update({key: os.environ.get(key) for key in _ENV})
    _SAVED_ENV.setdefault("AI_RPG_DB", os.environ.get("AI_RPG_DB"))
    os.environ.update(_ENV)


def tearDownModule():
    for key, value in _SAVED_ENV.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


T1_PROSE = (
    'You enter the clinic, a small stone building with a sign out front that reads "Dr. Vasilis - Healing for a '
    'Price." The air inside is sterile, with the sharp scent of disinfectant. Behind the counter sits Dr. Vasilis '
    "[[B]], a middle-aged man with graying hair. He looks up at you wearily as you approach.\n\n"
    '"Another adventurer in need of healing," Dr. Vasilis [[B]] says with a sigh. "I can\'t say I\'m surprised. '
    'The price of survival these days is steep."\n\n'
    '"What brings you here, traveler?" he asks.'
)


class _VenueCase(unittest.TestCase):
    def _seed(self, prose: str, *, kind: str = "clinic", keeperless: bool = True):
        """The call apply_turn makes after a move into a venue, with its keeper binding."""
        from app import db, venues, world

        os.environ["AI_RPG_DB"] = str(_TMP / f"world_{self._testMethodName}.db")
        db.init_db()
        with db.connect().closing() as conn:
            conn.execute("DELETE FROM npcs")
            conn.execute(
                "INSERT INTO npcs (code, location_id, name, role, summary) VALUES ('A', 1, 'Marisol Nolan', 'scavenger', '')"
            )
            if conn.execute("SELECT 1 FROM locations WHERE id = 2").fetchone():
                conn.execute(
                    "UPDATE locations SET name = 'The Venue', code = 'L2', parent_id = 1, kind = ?, keeper_npc_id = 0 "
                    "WHERE id = 2",
                    (kind,),
                )
            else:
                conn.execute(
                    "INSERT INTO locations (id, code, name, summary, parent_id, kind) VALUES (2, 'L2', 'The Venue', '', 1, ?)",
                    (kind,),
                )
            conn.execute("UPDATE player SET current_location_id = 2")
            conn.commit()
            result = {"narration": prose, "npcs": []}
            seeded = world._ensure_npcs_from_narration(
                conn, result, prose, 2, keeper_role=venues.keeper_role_for_kind(kind) if keeperless else ""
            )
            if seeded and keeperless:
                world.bind_venue_keeper(conn, 2)
            conn.commit()
            people = [dict(r) for r in conn.execute(
                "SELECT id, code, name, role, summary FROM npcs WHERE location_id = 2 ORDER BY id"
            ).fetchall()]
            keeper = int(conn.execute("SELECT keeper_npc_id FROM locations WHERE id = 2").fetchone()[0] or 0)
        by_name = {p["name"]: p for p in people}
        keeper_name = next((p["name"] for p in people if p["id"] == keeper), None)
        return people, by_name, keeper_name


class TheIntroducedPersonIsTheirOwnApposition(_VenueCase):
    def test_t1_the_doctor_behind_the_counter_is_one_person_and_keeps_the_clinic(self):
        people, _by_name, keeper = self._seed(T1_PROSE)
        self.assertEqual([p["name"] for p in people], ["Vasilis"], people)
        self.assertEqual(keeper, "Vasilis")

    def test_t2_packet_source_names_no_drawn_doctor(self):
        """What the narrator is told next turn: nobody holds Vasilis's own sentence as their summary."""
        people, _by_name, _keeper = self._seed(T1_PROSE)
        self.assertFalse([p for p in people if "Vasilis," in (p["summary"] or "")], people)
        self.assertFalse([p for p in people if p["name"] != "Vasilis" and p["role"] == "doctor"], people)

    def test_the_same_doctor_without_the_sign_is_still_one_person(self):
        prose = (
            "You enter the clinic. Dr. Vasilis, a middle-aged man with graying hair, washes his hands. "
            "Beside him, a nurse in a stained apron sorts bandages."
        )
        people, _by_name, keeper = self._seed(prose)
        self.assertEqual([p["name"] for p in people], ["Vasilis"], people)
        self.assertEqual(keeper, "Vasilis")

    def test_a_stranger_beside_the_named_doctor_is_still_seeded(self):
        """Reverse: a figure who is not in anyone's apposition is another person."""
        prose = (
            "Behind the counter sits Dr. Vasilis [[B]], a middle-aged man with graying hair. "
            "A young woman with a bandaged arm waits on the bench by the door."
        )
        people, _by_name, _keeper = self._seed(prose)
        self.assertEqual(len(people), 2, people)
        self.assertEqual(people[0]["name"], "Vasilis")

    def test_an_unnamed_figure_behind_the_counter_still_gets_the_trade(self):
        prose = "Behind the counter sits a middle-aged man with graying hair. He looks up at you wearily."
        people, _by_name, keeper = self._seed(prose)
        self.assertEqual(len(people), 1, people)
        self.assertEqual(people[0]["role"], "doctor")
        self.assertEqual(keeper, people[0]["name"])

    def test_an_introduced_job_is_kept(self):
        prose = "Rosa Vance, the smith, leans on the counter, waiting her turn."
        people, _by_name, _keeper = self._seed(prose)
        self.assertEqual([(p["name"], p["role"]) for p in people], [("Rosa Vance", "smith")])

    def test_a_venue_someone_keeps_gives_no_trade(self):
        people, _by_name, _keeper = self._seed(T1_PROSE, keeperless=False)
        self.assertEqual([p["name"] for p in people], ["Vasilis"])
        self.assertNotEqual(people[0]["role"], "doctor")


class TheTradeStaysWithTheFigureBehindTheCounter(_VenueCase):
    """The round-5 skeptic's probes: a named customer is not handed the venue's trade."""

    def test_the_patient_on_the_bench_is_not_the_doctor(self):
        prose = (
            "You enter the clinic. Jory Pike, a young man with a bloody rag around his hand, waits on the bench. "
            "A woman in a white coat calls out from the back room."
        )
        people, by_name, keeper = self._seed(prose)
        self.assertNotEqual(by_name["Jory Pike"]["role"], "doctor", people)
        self.assertEqual(len(people), 2, people)
        doctor = [p for p in people if p["name"] != "Jory Pike"][0]
        self.assertEqual(doctor["role"], "doctor")
        self.assertEqual(keeper, doctor["name"])

    def test_the_drinker_at_the_corner_table_is_not_the_tavern_keeper(self):
        prose = (
            "You step into the tavern. Marta Holt, a tired-looking woman, sits at a corner table nursing a drink. "
            "Behind the bar, a bald man polishes glasses."
        )
        people, by_name, keeper = self._seed(prose, kind="tavern")
        self.assertNotEqual(by_name["Marta Holt"]["role"], "tavern keeper", people)
        barman = [p for p in people if p["name"] != "Marta Holt"][0]
        self.assertEqual(barman["role"], "tavern keeper")
        self.assertEqual(keeper, barman["name"])

    def test_the_browser_is_not_the_shopkeeper(self):
        prose = (
            "You enter the shop. Elena Cross, a woman in a long coat, browses the shelves. "
            "The shopkeeper, a thin old man, nods at you."
        )
        people, by_name, _keeper = self._seed(prose, kind="shop")
        self.assertNotEqual(by_name["Elena Cross"]["role"], "shopkeeper", people)
        self.assertIn("shopkeeper", [p["role"] for p in people if p["name"] != "Elena Cross"])

    def test_customers_alone_are_not_given_the_trade_outright(self):
        for kind, trade, name, prose in (
            ("shop", "shopkeeper", "Pete Ross",
             "You enter the shop with Dana. Nobody is behind the counter; a cat sleeps on the till. "
             "Pete Ross, a scruffy boy, is stealing apples."),
            ("tavern", "tavern keeper", "Mira Holt",
             "You push open the door. Mira Holt, a wiry woman, points at a man in a long coat by the fire. "
             "\"He's the one you want,\" she says."),
            ("shop", "shopkeeper", "Kara Voss",
             "You step inside. Kara Voss, a lanky woman in a patched jacket, haggles with the old man behind the counter."),
            ("tavern", "tavern keeper", "Marta Holt",
             "Behind the bar, a bald man polishes glasses. Marta Holt, a tired-looking woman, sits at a corner table "
             "nursing a drink."),
        ):
            with self.subTest(name=name):
                people, by_name, _keeper = self._seed(prose, kind=kind)
                self.assertNotEqual(by_name[name]["role"], trade, people)

    def test_a_named_barkeep_keeps_their_own_job(self):
        prose = (
            "Old Ben Carter, a grizzled man, drinks alone at the end of the bar. Behind it, Sara Quill, the barkeep, "
            "wipes a mug and nods at you."
        )
        _people, by_name, keeper = self._seed(prose, kind="tavern")
        self.assertEqual(by_name["Sara Quill"]["role"], "barkeep")
        self.assertEqual(keeper, "Sara Quill")


class ATitleIsNotASentenceEnd(unittest.TestCase):
    """_sentence_index uses the narration pipeline's title-aware split: on "Dr." the
    T1 man's own description was counted as the sentence after his title."""

    def test_the_apposition_is_in_the_name_sentence(self):
        from app import world

        text = "Behind the counter sits Dr. Vasilis [[B]], a middle-aged man with graying hair. He looks up."
        self.assertEqual(world._sentence_index(text, "a middle-aged man"), 0)
        self.assertEqual(world._sentence_index(text, "Vasilis"), 0)
        self.assertEqual(world._sentence_index(text, "He looks up"), 1)

    def test_t1_sentences_count_from_the_sign(self):
        """The sign's quoted 'Dr. Vasilis' and the counter's 'Dr. Vasilis' were split
        into five pieces; the man is in the second sentence, his look in the third."""
        from app import world

        self.assertEqual(world._sentence_index(T1_PROSE, "a middle-aged man"), 1)
        self.assertEqual(world._sentence_index(T1_PROSE, "He looks up at you"), 2)

    def test_a_titled_name_is_read_as_the_untitled_one(self):
        """Main read 'Dr. Elena Moreau' as two sentences, so the figure hint just before
        her was seeded as a drawn doctor who kept the clinic; the untitled sentence
        already reads as one person. The title no longer changes the outcome."""
        case = _VenueCase("_seed")
        case._testMethodName = "titled_vs_untitled"
        before = "A young man with a bandaged arm waits on the bench. "
        plain, _b1, plain_keeper = case._seed(before + "Elena Moreau, a tall woman, writes in a ledger.")
        titled, _b2, titled_keeper = case._seed(before + "Dr. Elena Moreau, a tall woman, writes in a ledger.")
        self.assertEqual([(p["name"], p["role"]) for p in titled], [(p["name"], p["role"]) for p in plain])
        self.assertEqual((titled_keeper, plain_keeper), ("Elena Moreau", "Elena Moreau"))

    def test_a_plain_full_stop_still_ends_a_sentence(self):
        from app import world

        text = "The bell rings. A tall woman in a long coat waits by the door."
        self.assertEqual(world._sentence_index(text, "a tall woman"), 1)


if __name__ == "__main__":
    unittest.main()
