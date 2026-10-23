"""The engine writes the attack's result line (CLAUDE.md, Design decisions, 2026-10-24; #129, F186).

Stell's decision: the roll comes first; the engine writes the attack's result
line itself from the roll and the weapon; the narrator writes the scene around
it; when the draft leaves the line out or contradicts it, the engine puts its
own line in. No model rewrite, no extra model call, no new narrator text.

The live turns (Hermes 3 8B, recorded traces, prose verbatim):

* merge1 T4 (F186): 'i shoot the closest ghoul', ranged success 18, rolled
  before the ghouls were on the roster (no target on the check). The prose
  has the player charge and never shoot. The hit goes in on Ghoul 1 [[D]],
  the lowest-numbered ghoul now filed here.
* merge1 T5: failure 7 on the ghoul [[D]]; the prose already writes the miss.
  Nothing changes.
* combined T4: critical success on Mara [[C]]; the prose shows the hit. Nothing changes.
* final T4: 'i shoot Nate', critical failure 1, and the prose has the shot strike
  him in more than one sentence: the line goes in after the shot, the prose stays.
* integ-r3 T3: 'i shoot Dr. Theo', failure 9, no target on the check; the roster
  also has a "Theo": the longer name is the one the line names.

Run:  cd tests && python -m unittest test_attack_line
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import attack_line, interpreter, llm  # noqa: E402

I = interpreter
L = attack_line

M1_T4_LINE = "i shoot the closest ghoul"
M1_T4 = (
    "The sun climbs higher in the sky as you stand outside the Radiation Fenced Sanctuary [[L1]]. You scan the horizon "
    "for any sign of movement. In the distance, you spot a group of two ghouls shambling towards you, attracted by the "
    "Sanctuary's glow. They look weak and diseased, but there are a lot of them.\n\n"
    "All you have are your bare hands and your power armor. This is going to hurt.\n\n"
    "The ghouls are still far away. With a deep breath, you steel yourself for the fight ahead. The air is crisp and "
    "cool, with a faint tang of ozone from the radiation. Shafts of sunlight pierce the grass, casting long shadows "
    "across the empty plains.\n\n"
    "The ghouls lurch forward, their movements jerky and unnatural. Their skin is a sickly pale green, and their eyes "
    "glint with a malevolent hunger. You tighten your grip on the armor's controls, preparing to activate your shields.\n\n"
    "If they breach the fences, the radiation will kill them, but it will also unleash a horde of deadly creatures into "
    "the open.\n\n"
    "The ghouls are closer now, less than a hundred yards away. You take a final look around, making sure there's no "
    "one else to put in danger, and then you steel yourself. With a roar of determination, you charge forward to meet "
    "your enemy, ready to fight with everything you have."
)
M1_T4_ACT = "and then you steel yourself."
M1_T5 = (
    "You stand outside Radiation Fenced Sanctuary [[L3]], scanning the crowd of ghouls. One of them is reaching into "
    "his pack. You fumble for your rifle, but it's not here. The closest ghoul moves to block your path.\n\n"
    'You miss wildly as you shoot. The bullet whistles past and the ghoul barely notices. He grins and moves closer, '
    '"Aim better next time, friend."'
)
COMBINED_T4 = (
    "You stand in the dim light of the ruined subway tunnel [[L3]], the glow of the Sanctuary Clinic's radiation fence "
    "a faint promise ahead. Mara [[C]], the ghoul, is still and silent, having heard your footsteps but not yet seen "
    "you. Her eyes flicker open as you raise your arm, aiming to shoot the closest ghoul.\n\n"
    "The shot rings out, echoing through the tunnel. The bullet finds its mark, hitting Mara [[C]] square in the chest. "
    "She staggers back, clutching at the wound, blood seeping between her fingers. Her eyes, once hungry, now hold a "
    "flicker of pain and surprise."
)
FINAL_T4 = (
    "You crouch behind a rusted air scrubber, aiming your X-01 at Nate [[A]]'s heart. Morning light glints off the "
    "energy bolt as you squeeze the trigger. It streaks across the gap between the two scaffold towns, striking Nate "
    "[[A]] square in the chest. His eyes widen in shock, and he staggers back two steps before collapsing face-first "
    "onto the gravel.\n\n"
    "Nate [[A]] lies motionless, his body sprawled in the dirt. You approach cautiously, wary of a final surprise, but "
    "he remains still and lifeless."
)
R3_T3 = (
    "You stand in the clinic, surrounded by the smell of antiseptic and the faint hum of medical machinery. The clinic "
    "is small but well-equipped, with a few cots and a desk where Dr. Theo [[B]] is scribbling some notes.\n\n"
    'Dr. Theo [[B]] looks up from his work and frowns at you. "You almost hit me with that shot! I thought you were '
    'trying to kill me!"'
)


def _check(outcome: str, natural: int, code: str = "", name: str = "", skill: str = "ranged", weapon: str = "") -> dict:
    out = {"enabled": True, "skill": {"code": skill, "name": skill.title(), "category": "combat"}, "natural": natural,
           "total": natural, "outcome": outcome, "weapon_or_tool": weapon, "opposition": None}
    if code:
        out["attack"] = {"code": code, "name": name}
        out["opposition"] = {"name": name}
    return out


def _ghouls(here: int = 3) -> dict:
    """The merge1 roster after T4's draft: Ghoul 1 [[D]] and Ghoul 2 [[E]] filed where the player is."""
    return {
        "people": [
            {"code": "A", "name": "Yusuf Jansen", "died_turn": 0, "location_id": here},
            {"code": "D", "name": "Ghoul 1", "died_turn": 0, "location_id": here, "kind": "Ghoul", "kind_number": 1},
            {"code": "E", "name": "Ghoul 2", "died_turn": 0, "location_id": here, "kind": "Ghoul", "kind_number": 2},
        ],
        "places": [{"code": "L1", "name": "Radiation Fenced Sanctuary", "destroyed_turn": 0},
                   {"code": "L3", "name": "Outside Radiation Fenced Sanctuary", "destroyed_turn": 0}],
        "player_names": ["Will Tanaka"],
        "here_id": here,
        "player_line": M1_T4_LINE,
    }


def _people(*rows: tuple[str, str], line: str = "") -> dict:
    return {"people": [{"code": c, "name": n, "died_turn": 0} for c, n in rows], "places": [], "player_names": [],
            "player_line": line}


class No:
    def __init__(self):
        self.calls: list[str] = []

    def __call__(self, phase: str, prompt: str, max_tokens: int) -> str:
        self.calls.append(phase)
        return "No"


class Notes:
    """The interpreter's turn-ledger notes, caught."""

    def __enter__(self):
        self.seen: list[tuple[str, dict]] = []
        self._patch = mock.patch.object(I, "_note", side_effect=lambda event, **f: self.seen.append((event, f)))
        self._patch.start()
        return self

    def __exit__(self, *exc):
        self._patch.stop()

    def events(self) -> list[str]:
        return [e for e, _f in self.seen]


def _run(text: str, records: dict, checks: list[dict], combat: dict | None = None) -> dict:
    turn = {"skill_checks": checks}
    if combat:
        turn["_deterministic_combat"] = combat
    return I.run(text, records, No(), turn)


class TheLiveTurns(unittest.TestCase):
    def test_merge1_t4_f186_the_hit_goes_in_on_ghoul_1(self):
        check = _check("success", 18)
        with Notes() as notes:
            out = _run(M1_T4, _ghouls(), [check], {"player_attack": {"weapon": "unarmed"}})
        entry = out["report"]["attack_beats"][0]
        self.assertEqual((entry["code"], entry["state"], entry["action"], entry["aimed"]), ("D", "unshown", "inserted", False))
        beat = entry["beat"]
        self.assertEqual(beat, L.line_for(check, "the ghoul [[D]]"))
        self.assertRegex(beat, r"^Your shot .*the ghoul \[\[D\]\]")
        self.assertEqual(L.outcome_of(beat), L.HIT)
        # After the player's act (the last sentence they are the subject of), the rest kept as written.
        self.assertEqual(out["narration"], M1_T4.replace(M1_T4_ACT, f"{M1_T4_ACT} {beat}"))
        self.assertIn("attack_not_in_prose", notes.events())
        self.assertIn(beat, I.summary(out["events"], out["narration"], attack_beats=out["report"]["attack_beats"]))

    def test_merge1_t5_the_miss_is_already_written_nothing_changes(self):
        with Notes() as notes:
            out = _run(M1_T5, _ghouls(), [_check("failure", 7, "D", "Ghoul 1")])
        self.assertEqual(out["narration"], M1_T5)
        entry = out["report"]["attack_beats"][0]
        self.assertEqual((entry["state"], entry["action"]), ("shown", "none"))
        self.assertEqual(notes.events(), ["attack_shown"])

    def test_combined_t4_the_critical_hit_is_already_written(self):
        out = _run(COMBINED_T4, _people(("C", "Mara")), [_check("critical_success", 20, "C", "Mara")])
        self.assertEqual(out["narration"], COMBINED_T4)
        self.assertEqual(out["report"]["attack_beats"][0]["state"], "shown")

    def test_final_t4_a_critical_miss_the_prose_lands_twice_the_line_goes_in_and_the_prose_stays(self):
        records = _people(("A", "Nate"), line="i shoot Nate")
        with Notes() as notes:
            out = _run(FINAL_T4, records, [_check("critical_failure", 1)])
        entry = out["report"]["attack_beats"][0]
        self.assertEqual((entry["code"], entry["state"], entry["action"]), ("A", "contradicted", "inserted"))
        self.assertGreaterEqual(len(entry["kept"]), 2)
        self.assertEqual(L.outcome_of(entry["beat"]), L.MISS)
        self.assertEqual(out["narration"].replace(" " + entry["beat"], "", 1), FINAL_T4)
        self.assertIn("attack_contradiction_line_added", notes.events())

    def test_integ_r3_t3_the_longer_name_is_the_target_and_the_miss_follows_him(self):
        records = _people(("A", "NAME Theo ROLE"), ("B", "Dr. Theo"), ("C", "Theo"), line="i shoot Dr. Theo")
        out = _run(R3_T3, records, [_check("failure", 9)])
        entry = out["report"]["attack_beats"][0]
        self.assertEqual((entry["code"], entry["where"]), ("B", "target"))
        self.assertIn(f"Dr. Theo [[B]] is scribbling some notes. {entry['beat']}", out["narration"])


class TheContradiction(unittest.TestCase):
    RECORDS = staticmethod(lambda: _people(("B", "Beth"), ("C", "Wyatt")))

    def test_a_miss_written_on_a_success_gives_way_to_the_line(self):
        text = "You fire at Beth [[B]]. The shot goes wide and smacks the wall. Wyatt [[C]] flinches."
        with Notes() as notes:
            out = _run(text, self.RECORDS(), [_check("success", 15, "B", "Beth")])
        entry = out["report"]["attack_beats"][0]
        self.assertEqual((entry["action"], entry["dropped"]), ("replaced", "The shot goes wide and smacks the wall."))
        self.assertEqual(out["narration"], f"You fire at Beth [[B]]. {entry['beat']} Wyatt [[C]] flinches.")
        self.assertIn("attack_contradiction_replaced", notes.events())

    def test_a_kill_written_on_a_failure_gives_way_to_the_line(self):
        text = "You swing your crowbar at Beth [[B]]. The crowbar kills her where she stands.\n\nWyatt [[C]] shouts."
        out = _run(text, self.RECORDS(), [_check("failure", 3, "B", "Beth", skill="melee", weapon="crowbar")])
        entry = out["report"]["attack_beats"][0]
        self.assertEqual(entry["action"], "replaced")
        self.assertRegex(entry["beat"], r"^(Your crowbar|Your blow with the crowbar) .*Beth \[\[B\]\]")
        self.assertEqual(out["narration"], f"You swing your crowbar at Beth [[B]]. {entry['beat']}\n\nWyatt [[C]] shouts.")

    def test_a_graze_agrees_with_a_partial_and_a_miss_does_not(self):
        text = "You slash at Beth [[B]]. The blade only grazes her arm."
        out = _run(text, self.RECORDS(), [_check("partial", 11, "B", "Beth", skill="melee")])
        self.assertEqual((out["narration"], out["report"]["attack_beats"][0]["state"]), (text, "shown"))
        out = _run(text.replace("only grazes her arm", "misses her by a mile"), self.RECORDS(),
                   [_check("partial", 11, "B", "Beth", skill="melee")])
        self.assertEqual(out["report"]["attack_beats"][0]["action"], "replaced")

    def test_two_sentences_saying_the_opposite_are_kept_and_the_line_goes_in(self):
        text = "You shoot at Beth [[B]]. The round misses. It whistles past her ear and Wyatt [[C]] ducks."
        out = _run(text, self.RECORDS(), [_check("success", 16, "B", "Beth")])
        entry = out["report"]["attack_beats"][0]
        self.assertEqual((entry["state"], entry["action"], len(entry["kept"])), ("contradicted", "inserted", 2))
        self.assertEqual(out["narration"].replace(" " + entry["beat"], "", 1), text)

    def test_a_quoted_sentence_is_never_dropped(self):
        text = 'You shoot at Beth [[B]]. "You missed me!" Beth [[B]] laughs.'
        out = _run(text, self.RECORDS(), [_check("success", 16, "B", "Beth")])
        entry = out["report"]["attack_beats"][0]
        self.assertEqual(entry["action"], "inserted")
        self.assertIn('"You missed me!"', out["narration"])

    def test_a_look_is_no_blow_and_is_never_dropped(self):
        text = "Your gaze lands on Beth [[B]]. She stares back at you."
        out = _run(text, self.RECORDS(), [_check("failure", 4, "B", "Beth")])
        entry = out["report"]["attack_beats"][0]
        self.assertEqual((entry["state"], entry["action"], entry["where"]), ("unshown", "inserted", "target"))
        self.assertEqual(out["narration"], f"Your gaze lands on Beth [[B]]. {entry['beat']} She stares back at you.")

    def test_the_line_is_read_as_shown_by_the_engine_so_a_second_pass_changes_nothing(self):
        first = _run(M1_T4, _ghouls(), [_check("success", 18)])
        again = _run(first["narration"], _ghouls(), [_check("success", 18)])
        self.assertEqual(again["narration"], first["narration"])
        self.assertEqual(again["report"]["attack_beats"][0]["state"], "shown")


class TheLineItself(unittest.TestCase):
    BANDS = {"critical_success": L.HIT, "success": L.HIT, "partial": L.GRAZE, "failure": L.MISS, "critical_failure": L.MISS}

    def test_every_band_skill_and_weapon_reads_back_as_its_own_outcome(self):
        for band, landed in self.BANDS.items():
            for skill, weapon in (("ranged", ""), ("ranged", "hunting rifle"), ("melee", ""), ("melee", "crowbar")):
                for natural in range(1, 21):
                    line = L.line_for(_check(band, natural, skill=skill), "the ghoul [[D]]", weapon)
                    self.assertTrue(line.endswith(".") and "the ghoul [[D]]" in line, line)
                    self.assertTrue(L.is_attack_sentence(line), line)
                    self.assertEqual(L.outcome_of(line), landed, line)
                    self.assertNotRegex(line.lower(), r"\bdead\b|\bkill", line)

    def test_the_wording_is_drawn_from_a_pool_not_one_fixed_sentence(self):
        lines = {L.line_for(_check("success", n), "Beth [[B]]") for n in range(1, 21)}
        self.assertGreater(len(lines), 1)
        # Seeded by the roll: the same roll reads the same on a replay.
        self.assertEqual(L.line_for(_check("success", 14), "Beth [[B]]"), L.line_for(_check("success", 14), "Beth [[B]]"))

    def test_the_weapon_is_the_checks_else_the_combats_and_bare_hands_are_no_weapon(self):
        check = _check("success", 12, "B", "Beth", skill="melee")
        self.assertEqual(I.attack_weapon({**check, "weapon_or_tool": "machete"}, None), "machete")
        self.assertEqual(I.attack_weapon(check, {"_deterministic_combat": {"player_attack": {"weapon": "pipe wrench"}}}),
                         "pipe wrench")
        self.assertEqual(I.attack_weapon(check, {"_deterministic_combat": {"player_attack": {"weapon": "unarmed"}}}), "")
        bare = {L.line_for(_check("success", n, skill="melee"), "Beth [[B]]") for n in range(1, 21)}
        self.assertTrue(all(re.match(r"^Your (blow|fist|strike) ", b) for b in bare), bare)
        armed = {L.line_for(_check("success", n, skill="melee"), "Beth [[B]]", "machete") for n in range(1, 21)}
        self.assertTrue(all("machete" in a for a in armed), armed)

    def test_no_roll_or_no_band_is_no_line(self):
        self.assertEqual(L.line_for(_check("success", 0) | {"natural": None}, "Beth [[B]]"), "")
        self.assertEqual(L.line_for(_check("routine", 12), "Beth [[B]]"), "")
        self.assertEqual(L.line_for(_check("success", 12), ""), "")


class TheTargetFoundAfterTheDraft(unittest.TestCase):
    def _row(self, records: dict, check: dict):
        return I.attacked_row(check, records, I.Matcher(records["people"], records.get("places")))

    def test_the_kind_the_line_names_is_the_lowest_numbered_living_one_here(self):
        records = _ghouls()
        self.assertEqual(self._row(records, _check("success", 18))["code"], "D")
        records["people"][1]["died_turn"] = 4  # Ghoul 1 is dead: the next one
        self.assertEqual(self._row(records, _check("success", 18))["code"], "E")
        elsewhere = _ghouls()
        for row in elsewhere["people"]:
            row["location_id"] = 9
        self.assertIsNone(self._row(elsewhere, _check("success", 18)))

    def test_a_name_two_people_answer_to_is_no_one(self):
        records = _people(("A", "Sam Reyes"), ("B", "Sam Ortiz"), line="i shoot Sam Reyes and Sam Ortiz")
        self.assertIsNone(self._row(records, _check("success", 12)))
        records = _people(("A", "Sam Reyes"), line="i punch Sam Reyes")
        self.assertEqual(self._row(records, _check("success", 12, skill="melee"))["code"], "A")

    def test_only_a_melee_or_ranged_roll_without_a_target_is_matched(self):
        records = _people(("A", "Sam Reyes"), line="i talk to Sam Reyes")
        self.assertIsNone(self._row(records, _check("success", 12, skill="persuasion")))
        self.assertIsNone(self._row({**records, "player_line": ""}, _check("success", 12)))

    def test_dice_off_or_another_skill_adds_nothing_to_the_prose(self):
        records = _people(("A", "Sam Reyes"), line="i shoot Sam Reyes")
        text = "Sam Reyes [[A]] waits by the door."
        self.assertEqual(_run(text, records, [_check("success", 12) | {"natural": None}])["narration"], text)
        self.assertEqual(_run(text, records, [_check("success", 12, skill="persuasion")])["narration"], text)


class TheSummaryFollowsTheLine(unittest.TestCase):
    def test_run_interpreter_puts_the_line_in_the_turn_summary(self):
        turn = {"narration": M1_T4, "skill_checks": [_check("success", 18)], "turn_summary": "You charge the ghouls.",
                "_deterministic_combat": {"player_attack": {"weapon": "unarmed"}}}
        records = {key: value for key, value in _ghouls().items() if key != "player_line"}
        with mock.patch.object(llm, "_interpreter_ask", return_value=No()):
            out = llm._run_interpreter(turn, M1_T4_LINE, usage=[], trace=[], records=records)
        beat = L.line_for(_check("success", 18), "the ghoul [[D]]")
        self.assertIn(beat, out["narration"])
        self.assertTrue(out["turn_summary"].startswith(beat), out["turn_summary"])
        self.assertEqual(out["turn_summary"].count(beat), 1)


if __name__ == "__main__":
    unittest.main()
