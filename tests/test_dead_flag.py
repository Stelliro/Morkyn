"""Death is a 0/1 state the narrator is told only when it is 1 (CLAUDE.md, Design decisions, 2026-10-24, #154).

Stell: "npc death state needs to be changed from 0 to 1 ... if not the llm
should assume all npc's state is 0 (we dont need to tell it that npc's are
alive as it already asumes that, we just need to tell it characters are dead
so add something like 'if state "dead = 1" character is dead')".

The row holds npcs.dead 0/1, kept in step with died_turn (a death, a return,
rewind; an old save gets it from died_turn). The narrator is shown the dead=1
people at the player's place (they are there as bodies) and anyone whose death
was recorded on the turn just played, each as "Beth [[B]] dead=1"; the living
carry no flag; the one line "dead=1 means the character is dead." goes out only
with a flag. The engine's own reads stay on the record.

The strings are the tester's Hermes 3 8B game (campaign cc87dd29, T10 Beth
ripped in half, T11 "i search Beth's body"), shared with test_dead_bodies;
the model is mocked with the replies Hermes gave there.

Run:  cd tests && python -m unittest test_dead_flag
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_dead_bodies as B  # noqa: E402  (its sandboxed data dir, strings and helpers)
from app import db, interpreter, llm, world  # noqa: E402
from app.turn_dsl import build_dsl_user_prompt, facts_to_keep  # noqa: E402

I = interpreter
RULE = "dead=1 means the character is dead."


def _packet(line: str) -> dict:
    return json.loads(build_dsl_user_prompt(B._context(line), line))


def _rules(packet: dict) -> list[str]:
    return [line for line in packet.get("instructions") or [] if "dead=1" in line]


def _place_people(packet: dict) -> list[dict]:
    return ((packet.get("world_state") or {}).get("current_location") or {}).get("people") or []


class TestTesterT10T11(unittest.TestCase):
    """cc87dd29 T10 -> T11: Beth's death is a 1 on her row, and T11's narrator is told it with the one line."""

    def setUp(self):
        B._fresh_world()
        B._play(B._turn("The yard is quiet. " * 20, pending=False), "I look around")
        self.code = B._add_npc("Beth")
        self.living = B._add_npc("Kim")
        self.t10 = B.T10.replace("[[B]]", f"[[{self.code}]]")

    def test_before_t10_nobody_is_flagged_and_the_line_is_absent(self):
        packet = _packet(B.T10_LINE)
        self.assertEqual(_rules(packet), [])
        self.assertNotIn("dead=1", json.dumps(packet))
        self.assertEqual(int(B._row(self.code)["dead"]), 0)

    def test_t10_records_dead_1_and_t11_packet_has_the_flag_and_the_line(self):
        B._play(B._turn(self.t10), B.T10_LINE.replace("@C", f"@{self.code}"), B.Model(B.DIES))
        row = B._row(self.code)
        self.assertEqual(int(row["dead"]), 1)
        self.assertGreater(int(row["died_turn"]), 0)

        packet = _packet(B.T11_LINE)
        kept = packet.get("facts_to_keep") or []
        self.assertIn(f"Beth [[{self.code}]] dead=1", kept)
        self.assertIn(f"The body of Beth [[{self.code}]] lies here.", kept)  # the body fact stays
        # The old wording said the same thing twice; it is gone.
        self.assertFalse([f for f in kept if "and is dead" in f or "died in turn" in f], kept)
        # Stell's one line, once, beside the facts.
        self.assertEqual(_rules(packet), [RULE])
        facts_rule = next(i for i, line in enumerate(packet["instructions"]) if line.startswith("facts_to_keep are true"))
        self.assertEqual(packet["instructions"][facts_rule + 1], RULE)

    def test_a_living_person_carries_no_flag(self):
        B._play(B._turn(self.t10), B.T10_LINE, B.Model(B.DIES))
        packet = _packet(B.T11_LINE)
        kim = [p for p in _place_people(packet) if p.get("code") == self.living]
        self.assertEqual(len(kim), 1)
        self.assertNotIn("dead", kim[0])
        self.assertFalse([f for f in packet.get("facts_to_keep") or [] if f"[[{self.living}]]" in f])
        self.assertEqual(int(B._row(self.living)["dead"]), 0)


class TestWhoTheNarratorIsShown(unittest.TestCase):
    """A dead person elsewhere is shown only on the turn after the death is recorded."""

    def setUp(self):
        B._fresh_world()
        B._play(B._turn("The yard is quiet. " * 20, pending=False), "I look around")
        self.town, _ = B._add_place("Radiation Fenced Sanctuary")
        self.code = B._add_npc("Nate", location_id=self.town)

    def _record_death(self):
        with db.connect().closing() as conn:
            turn = world._current_turn_number()
            out = I.apply_events(conn, turn, [I._event(I.KIND_DIED, "npc", {"code": self.code, "name": "Nate"}, "he falls")])
            conn.commit()
        self.assertEqual(out[0]["status"], "applied")

    def test_elsewhere_and_changed_this_turn_is_shown(self):
        self._record_death()
        packet = _packet("I look around")
        kept = packet.get("facts_to_keep") or []
        self.assertIn(f"Nate [[{self.code}]] dead=1", kept)
        self.assertNotIn(f"The body of Nate [[{self.code}]] lies here.", kept)  # the body is not here
        self.assertEqual(_rules(packet), [RULE])

    def test_elsewhere_and_older_is_not_in_the_packet(self):
        self._record_death()
        B._play(B._turn("The road is long and empty. " * 12, pending=False), "I walk on")
        packet = _packet("I look around")
        self.assertFalse([f for f in packet.get("facts_to_keep") or [] if f"[[{self.code}]]" in f])
        self.assertEqual(_rules(packet), [])
        # The engine still holds the record: the_dead keeps him for its own reads.
        context = B._context("I look around")
        self.assertIn(self.code, [p["code"] for p in (context.get("the_dead") or {}).get("people") or []])

    def test_at_the_players_place_and_older_is_shown(self):
        with db.connect().closing() as conn:
            conn.execute("UPDATE npcs SET location_id = ? WHERE code = ?", (B._here_id(), self.code))
            conn.commit()
        self._record_death()
        B._play(B._turn("The road is long and empty. " * 12, pending=False), "I look around")
        packet = _packet("I look around")
        self.assertIn(f"Nate [[{self.code}]] dead=1", packet.get("facts_to_keep") or [])
        self.assertEqual(_rules(packet), [RULE])

    def test_the_expansion_pass_carries_the_same_line_with_a_flag_only(self):
        seen: list[str] = []

        def chat(system, instruction, **kwargs):
            seen.append(instruction)
            return "x" * 3000

        turn = {"narration": "You stand in the yard."}
        with mock.patch.object(llm, "_chat_text", side_effect=chat):
            llm._retry_narration_prose(B._context("I look around"), "I look around", turn, "", 5, [], "retry")
            self._record_death()
            llm._retry_narration_prose(B._context("I look around"), "I look around", turn, "", 5, [], "retry")
        self.assertNotIn(RULE, seen[0])
        self.assertIn(f"Nate [[{self.code}]] dead=1. {RULE}", seen[1])


class TestTheRowKeepsDeadInStep(unittest.TestCase):
    def setUp(self):
        B._fresh_world()
        B._play(B._turn("The yard is quiet. " * 20, pending=False), "I look around")
        self.code = B._add_npc("Beth")
        self.t10 = B.T10.replace("[[B]]", f"[[{self.code}]]")

    def test_rewind_sets_dead_back_to_0(self):
        B._play(B._turn(self.t10), B.T10_LINE, B.Model(B.DIES))
        self.assertEqual(int(B._row(self.code)["dead"]), 1)
        world.rewind_last_turn()
        row = B._row(self.code)
        self.assertEqual((int(row["dead"]), int(row["died_turn"])), (0, 0))
        self.assertEqual(_rules(_packet("i say hi to Beth")), [])

    def test_a_return_sets_dead_back_to_0(self):
        B._play(B._turn(self.t10), B.T10_LINE, B.Model(B.DIES))
        with db.connect().closing() as conn:
            out = I.apply_events(conn, 20, [I._event(I.KIND_RETURNED, "npc", {"code": self.code, "name": "Beth"}, "she rises")])
            conn.commit()
        self.assertEqual(out[0]["status"], "applied")
        row = B._row(self.code)
        self.assertEqual((int(row["dead"]), int(row["died_turn"])), (0, 0))

    def test_an_old_save_gets_dead_from_died_turn(self):
        living = B._add_npc("Kim")
        with db.connect().closing() as conn:
            conn.execute("ALTER TABLE npcs DROP COLUMN dead")
            conn.execute("UPDATE npcs SET died_turn = 4 WHERE code = ?", (self.code,))
            conn.commit()
            # Before the migration the engine reads the death from died_turn.
            row = conn.execute("SELECT * FROM npcs WHERE code = ?", (self.code,)).fetchone()
            self.assertTrue(I.is_dead(row))
        db.init_db()
        self.assertEqual(int(B._row(self.code)["dead"]), 1)
        self.assertEqual(int(B._row(living)["dead"]), 0)
        # Run twice: a living row stays 0.
        db.init_db()
        self.assertEqual(int(B._row(living)["dead"]), 0)

    def test_is_dead_reads_either_field(self):
        self.assertTrue(I.is_dead({"dead": 1, "died_turn": 0}))
        self.assertTrue(I.is_dead({"died_turn": 3}))
        self.assertFalse(I.is_dead({"dead": 0, "died_turn": 0}))
        self.assertFalse(I.is_dead({}))


if __name__ == "__main__":
    unittest.main()
