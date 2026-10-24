"""The engine writes the attack's result line (CLAUDE.md, Design decisions, 2026-10-24; #129, F186), round 2.

Stell's decision: the roll comes first; the engine writes the attack's result
line itself from the roll and the weapon; the narrator writes the scene around
it; when the draft leaves the line out or contradicts it, the engine puts its
own line in. No model rewrite, no extra model call, no new narrator text, and
(round 2, after the skeptical review of c065c4f) never a sentence dropped: the
line is only ever inserted. Whether the draft shows the outcome is read from
clauses whose subject is the player's attack or what it sent and whose object
is the target; a hit line is written only when the hit was applied; the target
is matched strictly (code, a name only it has, or its kind when it is the only
living one of that kind here), never a dead row, and never a named person the
line does not mean.

The live turns (Hermes 3 8B, recorded traces, prose verbatim):

* merge1 T4 (F186): 'i shoot the closest ghoul', ranged success 18, rolled
  before the ghouls were on the roster (no target on the check). The prose
  has the player charge and never shoot. The hit goes in on Ghoul 1 [[D]]
  after the combat math followed the check on that row.
* merge1 T5: failure 7 on the ghoul [[D]]; the prose already writes the miss.
* combined T4: critical success on Mara [[C]]; the prose shows the hit.
* final T4: 'i shoot Nate', critical failure 1, and the prose has the shot strike
  him: the line goes in after the passage, the prose stays, the death is the
  refused-death path's.
* integ-r3 T3: 'i shoot Dr. Theo', failure 9, no target on the check; the roster
  also has a "Theo": the longer name is the one the line names.
* unnamed T3 / unnamed2 T3, T4: the check was recorded on Tunde / Carlos for
  'i shoot the nearest ghoul': not the line's target; no ghoul row, no line.

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
FINAL_T4_PASSAGE_END = "collapsing face-first onto the gravel."
R3_T3 = (
    "You stand in the clinic, surrounded by the smell of antiseptic and the faint hum of medical machinery. The clinic "
    "is small but well-equipped, with a few cots and a desk where Dr. Theo [[B]] is scribbling some notes.\n\n"
    'Dr. Theo [[B]] looks up from his work and frowns at you. "You almost hit me with that shot! I thought you were '
    'trying to kill me!"'
)
UNNAMED_T3 = (
    "The radiation-fenced sanctuary stands before you, an oasis in the post-apocalyptic wasteland.\n\n"
    'Tunde Iqbal [[A]] emerges from the shadows, his hunter\'s eyes adjusting to your presence. "Another survivor," '
    'he notes, "or perhaps a scavenger seeking the sanctuary\'s treasures. What brings you to my home, stranger?"'
)
UNNAMED2_T3 = (
    "You stand up from your resting spot, stretching your arms and legs. Carlos Khan [[A]] emerges from his hiding "
    'spot, stepping out into the open.\n\n"Morning," he greets with a nod. "Did you have any luck last night?"'
)

# The merge1 combat block at T4: the player's attack with no target (status needs_target).
COMBAT_NEEDS_TARGET = {
    "status": "needs_target", "action_kind": "player_attack",
    "player_attack": {"weapon": "unarmed", "weapon_code": "", "equipment": {}, "strength": 7, "defense": 4, "dodge": 4,
                      "attack_min": 2, "attack_max": 4},
    "target_candidates": [],
}


def _check(outcome: str, natural: int, code: str = "", name: str = "", skill: str = "ranged", weapon: str = "") -> dict:
    out = {"enabled": True, "skill": {"code": skill, "name": skill.title(), "category": "combat"}, "natural": natural,
           "total": natural, "outcome": outcome, "weapon_or_tool": weapon, "opposition": None}
    if code:
        out["attack"] = {"code": code, "name": name}
        out["opposition"] = {"name": name}
    return out


def _ghoul(code: str, number: int, here: int = 3, health: int = 40) -> dict:
    return {"code": code, "name": f"Ghoul {number}", "died_turn": 0, "location_id": here, "kind": "Ghoul",
            "kind_number": number, "health": health, "max_health": health, "defense": 6, "dodge": 6, "role": "ghoul"}


def _ghouls(here: int = 3, line: str = M1_T4_LINE) -> dict:
    """The merge1 roster after T4's draft: Ghoul 1 [[D]] and Ghoul 2 [[E]] filed where the player is, with health."""
    return {
        "people": [
            {"code": "A", "name": "Yusuf Jansen", "died_turn": 0, "location_id": here, "role": "hunter"},
            _ghoul("D", 1, here), _ghoul("E", 2, here),
        ],
        "places": [{"code": "L1", "name": "Radiation Fenced Sanctuary", "destroyed_turn": 0},
                   {"code": "L3", "name": "Outside Radiation Fenced Sanctuary", "destroyed_turn": 0}],
        "player_names": ["Will Tanaka"],
        "here_id": here,
        "player_line": line,
    }


def _people(*rows: tuple[str, str], line: str = "", **extra) -> dict:
    return {"people": [{"code": c, "name": n, "died_turn": 0, **extra} for c, n in rows], "places": [], "player_names": [],
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
    if combat is not None:
        turn["_deterministic_combat"] = combat
    return I.run(text, records, No(), turn)


def _without(out: dict) -> str:
    """The narration with every engine line taken back out: what the prose was."""
    text = out["narration"]
    for entry in out["report"].get("attack_beats") or []:
        text = text.replace(" " + entry["beat"], "", 1).replace(entry["beat"], "", 1)
    return text


def _beats(out: dict) -> list[dict]:
    return out["report"].get("attack_beats") or []


class TheLiveTurns(unittest.TestCase):
    def test_merge1_t4_f186_the_combat_follows_the_check_on_ghoul_1_and_the_hit_goes_in(self):
        check = _check("success", 18)
        with Notes() as notes:
            out = _run(M1_T4, _ghouls(), [check], COMBAT_NEEDS_TARGET)
        entry = _beats(out)[0]
        self.assertEqual((entry["code"], entry["state"], entry["action"], entry["aimed"]), ("D", "unshown", "inserted", False))
        beat = entry["beat"]
        self.assertEqual(beat, L.line_for(check, "the ghoul [[D]]"))
        self.assertEqual(L.outcome_of(beat), L.HIT)
        # After the player's act (the last sentence they are the subject of), the rest kept as written.
        self.assertEqual(out["narration"], M1_T4.replace(M1_T4_ACT, f"{M1_T4_ACT} {beat}"))
        # The hit was applied first: the combat math followed the check on Ghoul 1.
        resolved = entry["resolution"]
        self.assertEqual(resolved["outcome"], "hit")
        self.assertGreaterEqual(resolved["damage"], 1)
        self.assertEqual(resolved["target_health_after"], 40 - resolved["damage"])
        combat = out["report"]["combat_after_draft"]
        self.assertEqual((combat["status"], combat["target"]["code"], combat["resolved_after_draft"]), ("resolved_player_attack", "D", True))
        self.assertEqual(combat["resolution"]["damage"], resolved["damage"])
        self.assertIn("attack_not_in_prose", notes.events())
        self.assertIn(beat, I.summary(out["events"], out["narration"], attack_beats=_beats(out)))

    def test_merge1_t5_the_miss_is_already_written_nothing_changes(self):
        with Notes() as notes:
            out = _run(M1_T5, _ghouls(), [_check("failure", 7, "D", "Ghoul 1")])
        self.assertEqual(out["narration"], M1_T5)
        entry = _beats(out)[0]
        self.assertEqual((entry["state"], entry["action"]), ("shown", "none"))
        self.assertEqual(notes.events(), ["attack_shown"])

    def test_combined_t4_the_critical_hit_is_already_written(self):
        out = _run(COMBINED_T4, _people(("C", "Mara")), [_check("critical_success", 20, "C", "Mara")])
        self.assertEqual(out["narration"], COMBINED_T4)
        self.assertEqual(_beats(out)[0]["state"], "shown")

    def test_final_t4_a_critical_miss_the_prose_lands_the_line_goes_in_after_the_passage_and_the_prose_stays(self):
        records = _people(("A", "Nate"), line="i shoot Nate", health=40, max_health=40)
        with Notes() as notes:
            out = _run(FINAL_T4, records, [_check("critical_failure", 1)], COMBAT_NEEDS_TARGET)
        entry = _beats(out)[0]
        self.assertEqual((entry["code"], entry["state"], entry["action"], entry["where"]), ("A", "contradicted", "inserted", "passage"))
        self.assertEqual(L.outcome_of(entry["beat"]), L.MISS)
        self.assertEqual(out["narration"], FINAL_T4.replace(FINAL_T4_PASSAGE_END, f"{FINAL_T4_PASSAGE_END} {entry['beat']}"))
        self.assertIn("attack_contradiction_line_added", notes.events())
        self.assertEqual(entry["resolution"]["damage"], 0)

    def test_integ_r3_t3_the_longer_name_is_the_target_and_the_miss_follows_him(self):
        records = _people(("A", "NAME Theo ROLE"), ("B", "Dr. Theo"), ("C", "Theo"), line="i shoot Dr. Theo",
                          health=40, max_health=40)
        out = _run(R3_T3, records, [_check("failure", 9)], COMBAT_NEEDS_TARGET)
        entry = _beats(out)[0]
        self.assertEqual((entry["code"], entry["where"]), ("B", "target"))
        self.assertIn(f"Dr. Theo [[B]] is scribbling some notes. {entry['beat']}", out["narration"])
        # His quoted "You almost hit me" is someone speaking, never the outcome.
        self.assertEqual(entry["state"], "unshown")

    def test_unnamed_t3_the_check_recorded_on_tunde_stands_with_no_ghoul_on_the_roster_and_gives_way_to_one(self):
        # As recorded, no ghoul row exists: "the nearest ghoul" is no evidence against the one person
        # present (a noun's absence from a list is never evidence; round 3), so the aimed check stands on him.
        records = _people(("A", "Tunde Iqbal"), line="i shoot the nearest ghoul", role="hunter", health=40, max_health=40)
        out = _run(UNNAMED_T3, records, [_check("success", 18, "A", "Tunde Iqbal")])
        self.assertEqual([(b["code"], b["aimed"]) for b in _beats(out)], [("A", True)])
        # With a ghoul filed here the ghoul is the target and the line is never on Tunde.
        records["people"].append(_ghoul("D", 1, here=0))
        with Notes() as notes:
            out = _run(UNNAMED_T3, records, [_check("success", 18, "A", "Tunde Iqbal")], COMBAT_NEEDS_TARGET)
        self.assertEqual([(b["code"], b["aimed"]) for b in _beats(out)], [("D", False)])
        self.assertIn("attack_retargeted", notes.events())
        self.assertNotIn("Tunde Iqbal [[A]].", out["narration"])
        # A thing the engine knows is not a person: no target, no line, a note.
        records = _people(("A", "Tunde Iqbal"), line="i shoot the lock", role="hunter", health=40, max_health=40)
        with Notes() as notes:
            out = _run(UNNAMED_T3, records, [_check("success", 18, "A", "Tunde Iqbal")])
        self.assertEqual((out["narration"], _beats(out)), (UNNAMED_T3, []))
        self.assertIn("attack_target_not_in_line", notes.events())

    def test_unnamed2_t3_carlos_the_companion_is_not_the_closest_ghoul(self):
        records = _people(("A", "Carlos Khan"), line="i shoot the closest ghoul", role="ranger", health=40, max_health=40)
        out = _run(UNNAMED2_T3, records, [_check("failure", 7, "A", "Carlos Khan")])
        # No ghoul on the roster: the word is no evidence and the aimed check stands (as main had it).
        self.assertEqual([(b["code"], b["aimed"]) for b in _beats(out)], [("A", True)])
        # With a ghoul filed here, the line is aimed at the ghoul, not Carlos.
        records["people"].append(_ghoul("D", 1, here=0))
        out = _run(UNNAMED2_T3, records, [_check("failure", 7, "A", "Carlos Khan")], COMBAT_NEEDS_TARGET)
        self.assertEqual([(b["code"], b["aimed"]) for b in _beats(out)], [("D", False)])
        self.assertIn("the ghoul [[D]]", _beats(out)[0]["beat"])
        self.assertNotIn("Carlos", _beats(out)[0]["beat"])


class NothingIsEverDropped(unittest.TestCase):
    """The skeptical review's regressions, one test each: the prose stays, the line goes in."""

    GHOULS = staticmethod(lambda line="i shoot the ghoul": {
        **_ghouls(line=line), "people": [_ghoul("D", 1), {"code": "F", "name": "Raider 1", "died_turn": 0, "location_id": 3,
                                                           "kind": "Raider", "kind_number": 1, "health": 30, "max_health": 30}],
    })

    def test_9_the_ghouls_counterattack_hits_you_is_not_the_players_hit(self):
        text = "You swing the machete and miss the ghoul [[D]]. It rakes its claws and hits you across the arm."
        out = _run(text, self.GHOULS(), [_check("failure", 4, "D", "Ghoul 1", "melee", "machete")])
        self.assertEqual(out["narration"], text)
        self.assertEqual(_beats(out)[0]["state"], "shown")

    def test_10_the_players_dodge_is_not_a_miss(self):
        text = "You hit the ghoul [[D]] with the crowbar. It lashes back but you dodge its claws."
        out = _run(text, self.GHOULS(), [_check("success", 15, "D", "Ghoul 1", "melee", "crowbar")])
        self.assertEqual(out["narration"], text)
        self.assertEqual(_beats(out)[0]["state"], "shown")

    def test_11_dead_eyes_are_a_description_not_a_hit(self):
        text = "You fire and the shot goes wide. The ghoul [[D]] turns its dead eyes on you and hisses."
        out = _run(text, self.GHOULS(), [_check("failure", 6, "D", "Ghoul 1")])
        self.assertEqual(out["narration"], text)
        self.assertEqual(_beats(out)[0]["state"], "shown")

    def test_22_you_hit_the_ground_is_not_a_hit_the_line_goes_in_after_the_shot(self):
        text = "You fire at the ghoul [[D]]. It ducks under the shot and lunges, and you hit the ground hard."
        out = _run(text, self.GHOULS(), [_check("failure", 7, "D", "Ghoul 1")])
        entry = _beats(out)[0]
        self.assertEqual((entry["state"], entry["where"]), ("unshown", "attack"))
        self.assertEqual(out["narration"], f"You fire at the ghoul [[D]]. {entry['beat']} It ducks under the shot and lunges, and you hit the ground hard.")

    def test_16_two_attacks_in_one_turn_each_reads_its_own_clause(self):
        text = "You fire twice. The first bullet hits the ghoul [[D]]. The second misses the raider [[F]]."
        checks = [_check("success", 16, "D", "Ghoul 1"), _check("failure", 5, "F", "Raider 1")]
        out = _run(text, self.GHOULS("i shoot the ghoul and then the raider"), checks)
        self.assertEqual(out["narration"], text)
        self.assertEqual([(b["code"], b["state"]) for b in _beats(out)], [("D", "shown"), ("F", "shown")])

    def test_21_a_quoted_missed_spoken_by_the_target_is_not_the_outcome(self):
        text = 'You pull the trigger. Dr. Theo [[B]] clutches his arm. "You missed my heart, at least!"'
        out = _run(text, _people(("B", "Dr. Theo")), [_check("success", 13, "B", "Dr. Theo")])
        entry = _beats(out)[0]
        self.assertEqual(entry["state"], "unshown")
        self.assertEqual(out["narration"], f"You pull the trigger. {entry['beat']} Dr. Theo [[B]] clutches his arm. \"You missed my heart, at least!\"")

    def test_6_a_miss_written_on_a_success_is_kept_and_the_line_follows_the_passage(self):
        text = "You fire at the ghoul [[D]]. The bullet whistles past its head. It snarls and keeps coming."
        with Notes() as notes:
            out = _run(text, self.GHOULS(), [_check("success", 14, "D", "Ghoul 1")])
        entry = _beats(out)[0]
        self.assertEqual((entry["state"], entry["action"], entry["where"]), ("contradicted", "inserted", "passage"))
        self.assertEqual(out["narration"], f"{text} {entry['beat']}")
        self.assertEqual(len(entry["kept"]), 3)
        self.assertIn("attack_contradiction_line_added", notes.events())
        self.assertNotIn("attack_contradiction_replaced", notes.events())

    def test_a_kill_written_on_a_failure_is_kept_and_the_line_goes_in(self):
        text = "You swing your crowbar at Beth [[B]]. The crowbar kills her where she stands.\n\nWyatt [[C]] shouts."
        out = _run(text, _people(("B", "Beth"), ("C", "Wyatt")), [_check("failure", 3, "B", "Beth", skill="melee", weapon="crowbar")])
        entry = _beats(out)[0]
        self.assertEqual((entry["state"], entry["action"]), ("contradicted", "inserted"))
        self.assertRegex(entry["beat"], r"^(Your crowbar|Your blow with the crowbar) .*Beth \[\[B\]\]")
        self.assertEqual(out["narration"], f"You swing your crowbar at Beth [[B]]. The crowbar kills her where she stands. {entry['beat']}\n\nWyatt [[C]] shouts.")

    def test_7_a_kill_with_no_readable_attack_clause_is_left_to_the_refused_death_path(self):
        text = "You drive the knife into Mira [[A]]. She collapses, dead."
        out = _run(text, _people(("A", "Mira Holt")), [_check("failure", 5, "A", "Mira Holt", "melee", "knife")])
        entry = _beats(out)[0]
        self.assertEqual(entry["state"], "unshown")
        self.assertEqual(_without(out), text)
        self.assertIn("She collapses, dead.", out["narration"])

    def test_a_passive_you_are_struck_is_the_player_hit_not_the_target(self):
        text = "You swing at the raider [[F]]. You are struck across the face by his club."
        out = _run(text, self.GHOULS("i hit the raider"), [_check("failure", 5, "F", "Raider 1", "melee")])
        self.assertEqual(_beats(out)[0]["state"], "unshown")
        self.assertEqual(_without(out), text)

    def test_the_replace_path_is_gone(self):
        self.assertFalse(hasattr(L, "replace_span"))


class TheTargetIsMatchedStrictly(unittest.TestCase):
    def test_19_the_kind_word_alone_names_neither_of_two_ghouls(self):
        text = "You fire. The bullet hits the ghoul [[E]] in the leg. The other ghoul [[D]] keeps coming."
        out = _run(text, _ghouls(line="i shoot the ghoul"), [_check("success", 15, "D", "Ghoul 1")])
        entry = _beats(out)[0]
        self.assertEqual((entry["state"], entry["where"]), ("unshown", "attack"))
        self.assertEqual(_without(out), text)
        self.assertIn("the ghoul [[D]]", entry["beat"])

    def test_the_kind_word_names_the_one_living_ghoul_here(self):
        records = _ghouls(line="i shoot the ghoul")
        records["people"] = [p for p in records["people"] if p["code"] != "E"]
        text = "You fire at the ghoul. The bullet hits the ghoul in the leg."
        out = _run(text, records, [_check("success", 15, "D", "Ghoul 1")])
        self.assertEqual(_beats(out)[0]["state"], "shown")

    def test_15_a_roll_aimed_at_a_dead_person_writes_nothing_on_the_body(self):
        records = _people(("G", "Old Sam"), line="i stab old sam")
        records["people"][0]["died_turn"] = 4
        text = "You kneel by Old Sam [[G]]'s body."
        with Notes() as notes:
            out = _run(text, records, [_check("success", 15, "G", "Old Sam", "melee", "knife")])
        self.assertEqual(out["narration"], text)
        self.assertEqual(_beats(out), [])
        self.assertIn("attack_target_dead", notes.events())

    def test_14_an_untargeted_roll_naming_no_one_here_gets_no_target(self):
        text = "You fire into the dark. Nothing answers but the echo."
        out = _run(text, _ghouls(line="i shoot at the sound, maybe ghouls"), [_check("failure", 3)], COMBAT_NEEDS_TARGET)
        self.assertEqual((out["narration"], _beats(out)), (text, []))
        for line in ("i shoot the lock on Mira's door", "i practice sword drills with Theo watching", "i draw my knife and watch Mira"):
            records = _people(("A", "Mira Holt"), ("B", "Dr. Theo"), line=line, health=40, max_health=40)
            out = _run("Mira [[A]] and Dr. Theo [[B]] watch you.", records, [_check("success", 15, skill="melee")], COMBAT_NEEDS_TARGET)
            self.assertEqual(_beats(out), [], line)

    def test_the_kind_the_line_names_as_a_thing_is_the_lowest_numbered_living_one_here(self):
        match = lambda r: I.Matcher(r["people"], r.get("places"))  # noqa: E731
        records = _ghouls()
        self.assertEqual(I.attacked_row(_check("success", 18), records, match(records))["code"], "D")
        records["people"][1]["died_turn"] = 4  # Ghoul 1 is dead: the next one
        self.assertEqual(I.attacked_row(_check("success", 18), records, match(records))["code"], "E")
        elsewhere = _ghouls()
        for row in elsewhere["people"]:
            row["location_id"] = 9
        self.assertIsNone(I.attacked_row(_check("success", 18), elsewhere, match(elsewhere)))
        self.assertIsNone(I.attacked_row(_check("success", 18), _ghouls(line="i shoot at the sound, maybe ghouls"), match(records)))

    def test_a_named_person_is_the_target_only_when_the_line_names_or_describes_them(self):
        match = lambda r: I.Matcher(r["people"], r.get("places"))  # noqa: E731
        hunter = _people(("A", "Tunde Iqbal"), line="i shoot the nearest ghoul", role="hunter")
        # No ghoul on the roster: the word is no evidence and the aimed check stands on him (round 3).
        self.assertEqual(I.attacked_row(_check("success", 18, "A", "Tunde Iqbal"), hunter, match(hunter))["code"], "A")
        with_ghoul = {**hunter, "people": [*hunter["people"], _ghoul("D", 1, here=0)]}
        self.assertEqual(I.attacked_row(_check("success", 18, "A", "Tunde Iqbal"), with_ghoul, match(with_ghoul))["code"], "D")
        locked = {**hunter, "player_line": "i shoot the lock"}
        self.assertIsNone(I.attacked_row(_check("success", 18, "A", "Tunde Iqbal"), locked, match(locked)))
        for line in ("i shoot Tunde", "i shoot the hunter", "i shoot him", "i shoot the man by the gate", "i shoot [[A]]", "i open fire",
                     "i shoot the bastard", "i shoot Iqbal in the knee"):
            records = {**hunter, "player_line": line}
            self.assertEqual(I.attacked_row(_check("success", 18, "A", "Tunde Iqbal"), records, match(records))["code"], "A", line)
        doctor = _people(("A", "Chiara Weber"), line="i shoot the doctor", role="doctor")
        self.assertEqual(I.attacked_row(_check("success", 15, "A", "Chiara Weber"), doctor, match(doctor))["code"], "A")

    def test_a_name_two_people_answer_to_is_no_one(self):
        records = _people(("A", "Sam Reyes"), ("B", "Sam Ortiz"), line="i shoot Sam Reyes and Sam Ortiz")
        match = I.Matcher(records["people"], records.get("places"))
        self.assertIsNone(I.attacked_row(_check("success", 12), records, match))
        records = _people(("A", "Sam Reyes"), line="i punch Sam Reyes")
        self.assertEqual(I.attacked_row(_check("success", 12, skill="melee"), records, I.Matcher(records["people"]))["code"], "A")

    def test_only_a_melee_or_ranged_roll_without_a_target_is_matched(self):
        records = _people(("A", "Sam Reyes"), line="i talk to Sam Reyes")
        match = I.Matcher(records["people"])
        self.assertIsNone(I.attacked_row(_check("success", 12, skill="persuasion"), records, match))
        self.assertIsNone(I.attacked_row(_check("success", 12), {**records, "player_line": ""}, match))


class NoHitLineWithoutTheHit(unittest.TestCase):
    def test_an_untargeted_roll_with_no_combat_block_writes_no_line(self):
        for combat in (None, {}, {"status": "not_combat"}):
            with Notes() as notes:
                out = _run(M1_T4, _ghouls(), [_check("success", 18)], combat)
            self.assertEqual(out["narration"], M1_T4, combat)
            self.assertEqual(_beats(out), [])
            self.assertIn("attack_unresolved_no_line", notes.events())
            self.assertNotIn("combat_after_draft", out["report"])

    def test_a_row_with_no_health_cannot_be_resolved_against(self):
        records = _ghouls()
        records["people"][1]["max_health"] = 0
        records["people"][1]["health"] = 0
        with Notes() as notes:
            out = _run(M1_T4, records, [_check("success", 18)], COMBAT_NEEDS_TARGET)
        self.assertEqual((out["narration"], _beats(out)), (M1_T4, []))
        self.assertIn("attack_unresolved_no_line", notes.events())

    def test_the_resolution_follows_the_band_and_the_combats_attack_range(self):
        row = _ghoul("D", 1)
        for band, landed, damage_floor in (("critical_success", "hit", 1), ("success", "hit", 1), ("partial", "glancing_hit", 1),
                                           ("failure", "miss", 0), ("critical_failure", "miss", 0)):
            out = L.resolve(_check(band, 12), row, COMBAT_NEEDS_TARGET)
            self.assertEqual(out["outcome"], landed, band)
            self.assertEqual(out["damage"] == 0, landed == "miss", band)
            self.assertGreaterEqual(out["damage"], damage_floor)
            self.assertLessEqual(out["damage"], 4)
            self.assertEqual(out["target_health_after"], 40 - out["damage"])
            self.assertEqual(out["target_health_before"], 40)
        # The same roll resolves the same (the engine's seeded dice).
        self.assertEqual(L.resolve(_check("success", 12), row, COMBAT_NEEDS_TARGET), L.resolve(_check("success", 12), row, COMBAT_NEEDS_TARGET))
        # The combat block's own candidate record wins over the row's columns.
        combat = {**COMBAT_NEEDS_TARGET, "target_candidates": [{"code": "D", "combat_profile": {"health": 5, "max_health": 40, "defense": 0}}]}
        self.assertEqual(L.resolve(_check("success", 12), row, combat)["target_health_before"], 5)

    def test_a_combat_already_resolved_on_the_row_is_not_resolved_twice(self):
        combat = {**COMBAT_NEEDS_TARGET, "status": "resolved_player_attack", "target": {"code": "D", "name": "Ghoul 1"},
                  "resolution": {"outcome": "hit", "damage": 2}}
        out = _run(M1_T4, _ghouls(), [_check("success", 18)], combat)
        self.assertNotIn("combat_after_draft", out["report"])
        self.assertNotIn("resolution", _beats(out)[0])
        self.assertIn(_beats(out)[0]["beat"], out["narration"])

    def test_run_interpreter_carries_the_resolved_combat_and_the_line_into_the_turn(self):
        turn = {"narration": M1_T4, "skill_checks": [_check("success", 18)], "turn_summary": "You charge the ghouls.",
                "_deterministic_combat": dict(COMBAT_NEEDS_TARGET)}
        records = {key: value for key, value in _ghouls().items() if key != "player_line"}
        with mock.patch.object(llm, "_interpreter_ask", return_value=No()):
            out = llm._run_interpreter(turn, M1_T4_LINE, usage=[], trace=[], records=records)
        beat = L.line_for(_check("success", 18), "the ghoul [[D]]")
        self.assertIn(beat, out["narration"])
        self.assertTrue(out["turn_summary"].startswith(beat), out["turn_summary"])
        self.assertEqual(out["turn_summary"].count(beat), 1)
        combat = out["_deterministic_combat"]
        self.assertEqual((combat["status"], combat["target"]["code"], combat["resolution"]["outcome"]), ("resolved_player_attack", "D", "hit"))
        self.assertTrue(combat["resolved_after_draft"])


class TheReadingItself(unittest.TestCase):
    def test_a_standing_death_of_the_target_shows_the_hit(self):
        text = "You swing the axe at Beth [[B]] and she falls dead at your feet."
        records = _people(("B", "Beth"), line="i kill Beth")

        def dead(phase: str, prompt: str, n: int) -> str:  # "Is Beth dead?" yes; "Is Beth alive?" no; the rest no
            return "Yes" if phase == I.PHASE_DIED else "No"

        out = I.run(text, records, dead, {"skill_checks": [_check("success", 16, "B", "Beth", "melee", "axe")]})
        self.assertEqual([e["kind"] for e in out["events"]], ["died"])
        self.assertEqual((_beats(out)[0]["state"], out["narration"]), ("shown", text))

    def test_a_look_is_no_blow(self):
        text = "Your gaze lands on Beth [[B]]. She stares back at you."
        out = _run(text, _people(("B", "Beth")), [_check("failure", 4, "B", "Beth")])
        entry = _beats(out)[0]
        self.assertEqual((entry["state"], entry["where"]), ("unshown", "target"))
        self.assertEqual(out["narration"], f"Your gaze lands on Beth [[B]]. {entry['beat']} She stares back at you.")

    def test_your_knuckles_and_the_crowbar_are_what_the_player_sent(self):
        out = _run("You throw a punch at Dr. Theo [[B]]. Your knuckles only graze his cheek.", _people(("B", "Dr. Theo")),
                   [_check("partial", 11, "B", "Dr. Theo", "melee")])
        self.assertEqual(_beats(out)[0]["state"], "shown")
        out = _run("You swing hard. The crowbar slams into Beth [[B]].", _people(("B", "Beth")),
                   [_check("success", 14, "B", "Beth", "melee", "crowbar")])
        self.assertEqual(_beats(out)[0]["state"], "shown")

    def test_an_outcome_word_used_as_a_noun_is_not_an_outcome(self):
        out = _run("You swing at Beth [[B]]. Your armor takes the hit as she shoves you back.", _people(("B", "Beth")),
                   [_check("failure", 4, "B", "Beth", "melee")])
        self.assertEqual(_beats(out)[0]["state"], "unshown")

    def test_a_graze_agrees_with_a_partial_and_a_miss_does_not(self):
        text = "You slash at Beth [[B]]. The blade only grazes her arm."
        out = _run(text, _people(("B", "Beth")), [_check("partial", 11, "B", "Beth", skill="melee")])
        self.assertEqual((out["narration"], _beats(out)[0]["state"]), (text, "shown"))
        out = _run(text.replace("only grazes her arm", "misses her by a mile"), _people(("B", "Beth")),
                   [_check("partial", 11, "B", "Beth", skill="melee")])
        self.assertEqual((_beats(out)[0]["state"], _beats(out)[0]["action"]), ("contradicted", "inserted"))

    def test_with_no_act_to_follow_the_line_goes_before_a_closing_question(self):
        text = "The yard is quiet. Wind rattles the tin roof. What do you do?"
        out = _run(text, _people(("F", "Raider 1"), line="i punch the raider"), [_check("critical_failure", 1, "F", "Raider 1", "melee")])
        entry = _beats(out)[0]
        self.assertEqual(out["narration"], f"The yard is quiet. Wind rattles the tin roof. {entry['beat']} What do you do?")

    def test_the_line_is_read_as_shown_by_the_engine_so_a_second_pass_changes_nothing(self):
        first = _run(M1_T4, _ghouls(), [_check("success", 18)], COMBAT_NEEDS_TARGET)
        again = _run(first["narration"], _ghouls(), [_check("success", 18)], COMBAT_NEEDS_TARGET)
        self.assertEqual(again["narration"], first["narration"])
        self.assertEqual(_beats(again)[0]["state"], "shown")


class TheLineItself(unittest.TestCase):
    BANDS = {"critical_success": L.HIT, "success": L.HIT, "partial": L.GRAZE, "failure": L.MISS, "critical_failure": L.MISS}

    def test_every_band_skill_and_weapon_reads_back_as_its_own_outcome(self):
        records = _ghouls()
        records["people"] = [records["people"][1]]  # the one ghoul here: its kind names it
        match = I.Matcher(records["people"])
        for band, landed in self.BANDS.items():
            for skill, weapon in (("ranged", ""), ("ranged", "hunting rifle"), ("melee", ""), ("melee", "crowbar")):
                for natural in range(1, 21):
                    line = L.line_for(_check(band, natural, skill=skill), "the ghoul [[D]]", weapon)
                    self.assertTrue(line.endswith(".") and "the ghoul [[D]]" in line, line)
                    self.assertTrue(L.is_attack_sentence(line), line)
                    self.assertEqual(L.outcome_of(line), landed, line)
                    self.assertNotRegex(line.lower(), r"\bdead\b|\bkill", line)
                    seen = L.read(line, records["people"][0], landed, match, records, 1, weapon)
                    self.assertEqual(seen["state"], "shown", line)

    def test_the_wording_is_drawn_from_a_pool_not_one_fixed_sentence(self):
        lines = {L.line_for(_check("success", n), "Beth [[B]]") for n in range(1, 21)}
        self.assertGreater(len(lines), 1)
        self.assertEqual(L.line_for(_check("success", 14), "Beth [[B]]"), L.line_for(_check("success", 14), "Beth [[B]]"))

    def test_the_weapon_is_the_checks_else_the_combats_and_bare_hands_are_no_weapon(self):
        check = _check("success", 12, "B", "Beth", skill="melee")
        self.assertEqual(I.attack_weapon({**check, "weapon_or_tool": "machete"}, None), "machete")
        self.assertEqual(I.attack_weapon(check, {"_deterministic_combat": {"player_attack": {"weapon": "pipe wrench"}}}), "pipe wrench")
        self.assertEqual(I.attack_weapon(check, {"_deterministic_combat": {"player_attack": {"weapon": "unarmed"}}}), "")
        bare = {L.line_for(_check("success", n, skill="melee"), "Beth [[B]]") for n in range(1, 21)}
        self.assertTrue(all(re.match(r"^Your (blow|fist|strike) ", b) for b in bare), bare)
        armed = {L.line_for(_check("success", n, skill="melee"), "Beth [[B]]", "machete") for n in range(1, 21)}
        self.assertTrue(all("machete" in a for a in armed), armed)

    def test_no_roll_or_no_band_is_no_line(self):
        self.assertEqual(L.line_for(_check("success", 0) | {"natural": None}, "Beth [[B]]"), "")
        self.assertEqual(L.line_for(_check("routine", 12), "Beth [[B]]"), "")
        self.assertEqual(L.line_for(_check("success", 12), ""), "")
        records = _people(("A", "Sam Reyes"), line="i shoot Sam Reyes")
        text = "Sam Reyes [[A]] waits by the door."
        self.assertEqual(_run(text, records, [_check("success", 12) | {"natural": None}])["narration"], text)
        self.assertEqual(_run(text, records, [_check("success", 12, skill="persuasion")])["narration"], text)


if __name__ == "__main__":
    unittest.main()
