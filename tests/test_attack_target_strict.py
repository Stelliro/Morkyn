"""Whom the player's attack line is at, upstream (unnamed T3, unnamed2 T3/T4; merge1 T4 live, F186; round 3).

'i shoot the nearest ghoul' with Tunde Iqbal the hunter and the ghouls here
was aimed at him: world._clear_combat_target took the one candidate, the
combat math hurt him, skill_checks made him the inferred check's npc_ref and
attack_intent marked that as the attack ("trigger"). 'i shoot the closest
ghoul' did the same to Carlos Khan, a companion. The line's own words decide
now, in one place (attack_intent.line_may_target, kind_figures), used by the
combat target, the attack intent's candidate list and the interpreter's
attacked_row.

Round 3 (the review of round 2): the match refused targets the player plainly
named. A line names a person when any word of their roster name that is not a
title appears ("Theo" for Dr. Theo, "Sam" for Old Sam, "Iqbal", "Theo's"), and
a determiner noun refuses the person only on positive evidence that it is
something else: another living figure's kind here, another person's job, a
place, or scenery the engine never takes for a person (a lock, a door). "the
bastard", "the creep", "the thing", "the doc", "the merc" leave the one person
present a possible target, as main did; there is no person-word list. A
companion whose role holds the kind word ("ghoul hunter") is not "the ghoul":
kinds come from the kind column. One resolution per row: a combat block
already resolved on the row an untargeted roll is matched to is not resolved
again; when its hit or miss disagrees with the check's band, the band wins and
the combat is corrected to it by the difference (#129).

The whole turn, merge1 T4 (F186): the roll has no target (the ghouls are
filed by the prose, after the roll); the engine gives the new rows a combat
profile, the interpreter matches the roll to Ghoul 1, the combat math follows
the check on that row, the damage is applied, and the line goes into the prose
and the summary.

Run:  cd tests && python -m unittest test_attack_target_strict
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-attack-target-"))
_ENV = {
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
    "AI_RPG_CAMPAIGN_SLOTS": str(_TMP / "slots"),
}
os.environ.update(_ENV)

from app import attack_intent as A, attack_line, db, interpreter as I, llm, skill_checks, whereabouts, world  # noqa: E402
from test_attack_line import M1_T4, M1_T4_LINE  # noqa: E402


def _person(code: str, name: str, role: str = "", kind: str = "", number: int = 0, **extra) -> dict:
    return {"code": code, "name": name, "role": role, "kind": kind, "kind_number": number, "died_turn": 0, "rank": "F",
            "stat_profile": {}, **extra}


TUNDE = _person("A", "Tunde Iqbal", "hunter")
CARLOS = _person("A", "Carlos Khan", "ranger")
CHIARA = _person("A", "Chiara Weber", "doctor")
GHOUL1 = _person("D", "Ghoul 1", "ghoul", "Ghoul", 1)
GHOUL2 = _person("E", "Ghoul 2", "ghoul", "Ghoul", 2)
THEO = _person("B", "Dr. Theo", "doctor")
VASILIS = _person("B", "Dr. Vasilis", "doctor")
SAM = _person("G", "Old Sam", "farmer")
GRIT = _person("K", "Grit", "mercenary")
HUNTER = _person("C", "Carlos Khan", "ghoul hunter")


class TheLinesWords(unittest.TestCase):
    def test_object_nouns(self):
        self.assertEqual(A.object_nouns("i shoot the nearest ghoul with my crowbar"), ["ghoul"])
        self.assertEqual(A.object_nouns("i shoot another ghoul"), ["ghoul"])
        self.assertEqual(A.object_nouns("i shoot the ghouls"), ["ghoul"])
        self.assertEqual(A.object_nouns("i shoot at the sound, maybe ghouls"), ["sound"])
        self.assertEqual(A.object_nouns("i cut the guard off mid-sentence"), ["guard"])
        self.assertEqual(A.object_nouns("i shoot the lock on Mira's door"), ["lock"])
        self.assertEqual(A.object_nouns("i shoot him"), [])
        self.assertEqual(A.object_nouns("i shoot Tunde [[A]]"), [])
        # Two phrases joined by "and" are two nouns; a possessive is the phrase's noun.
        self.assertEqual(A.object_nouns("i shoot the ghouls and the raider"), ["ghoul", "raider"])
        self.assertEqual(A.object_nouns("i smash the ghoul's head"), ["ghoul"])
        self.assertEqual(A.object_nouns("i put a bullet in Theo's head"), ["bullet"])

    def test_a_named_person_is_meant_by_name_job_or_pronoun_and_refused_only_on_evidence(self):
        for line in ("i shoot Tunde", "i shoot Tunde Iqbal", "i shoot [[A]]", "i shoot @A", "i shoot the hunter",
                     "i shoot the man by the fence", "i shoot the stranger", "i shoot him", "i put a bullet in his head",
                     "i open fire", "i attack"):
            self.assertTrue(A.line_may_target(line, TUNDE), line)
        # Positive evidence that the thing named is something else: a ghoul here, a place, scenery.
        here = [TUNDE, GHOUL1]
        for line in ("i shoot the nearest ghoul", "i shoot the closest ghoul", "i shoot another ghoul", "i shoot the ghouls",
                     "i shoot the ghoul in its head", "i shoot the ghoul in the chest"):
            self.assertFalse(A.line_may_target(line, TUNDE, people=here), line)
        for line in ("i shoot the lock on the door", "i shoot the lock", "i shoot the door", "i shoot the sign"):
            self.assertFalse(A.line_may_target(line, TUNDE), line)
        self.assertFalse(A.line_may_target("i shoot at the clinic", TUNDE, places=[{"code": "L2", "name": "Sanctuary Clinic"}]))
        self.assertTrue(A.line_may_target("i shoot the doctor", CHIARA))
        self.assertFalse(A.line_may_target("i shoot the closest ghoul", CARLOS, people=[CARLOS, GHOUL1]))
        self.assertFalse(A.line_may_target("", TUNDE))
        # With no ghoul on the roster the word is no evidence: the trigger's aim stands, as main had it.
        self.assertTrue(A.line_may_target("i shoot the nearest ghoul", TUNDE))
        self.assertTrue(A.line_may_target("i shoot the nearest ghoul", TUNDE, people=[TUNDE]))

    def test_a_numbered_figure_is_meant_by_its_kind(self):
        self.assertTrue(A.line_may_target("i shoot the nearest ghoul", GHOUL1))
        self.assertTrue(A.line_may_target("i shoot the ghouls", GHOUL2))
        self.assertTrue(A.line_may_target("i shoot it", GHOUL1))
        # "the doctor" is the doctor's when one is here; alone, the word is no evidence.
        self.assertFalse(A.line_may_target("i shoot the doctor", GHOUL1, people=[GHOUL1, CHIARA]))
        self.assertTrue(A.line_may_target("i shoot the doctor", GHOUL1))
        self.assertTrue(A.line_may_target("i shoot at the sound, maybe ghouls", GHOUL1))
        self.assertEqual(A.name_words(GHOUL1), [])

    def test_kind_figures_are_the_living_ones_of_the_kind_named_lowest_first(self):
        people = [TUNDE, GHOUL2, GHOUL1]
        self.assertEqual([p["code"] for p in A.kind_figures("i shoot the closest ghoul", people)], ["D", "E"])
        self.assertEqual(A.kind_figures("i shoot at the sound, maybe ghouls", people), [])
        self.assertEqual(A.kind_figures("i shoot the hunter", people), [])
        dead = [{**GHOUL1, "died_turn": 3}, GHOUL2]
        self.assertEqual([p["code"] for p in A.kind_figures("i shoot the ghoul", dead)], ["E"])


class TheNamedPersonIsMeant(unittest.TestCase):
    """Round 3 (a): any word of the roster name that is not a title, possessives and codes included."""

    def test_name_words_take_the_titles_off(self):
        self.assertEqual(A.name_words(THEO), ["Theo"])
        self.assertEqual(A.name_words(SAM), ["Sam"])
        self.assertEqual(A.name_words(TUNDE), ["Tunde", "Iqbal"])
        self.assertEqual(A.name_words(_person("Q", "Captain Mara Voss")), ["Mara", "Voss"])
        self.assertEqual(A.name_words(_person("Q", "Elder")), ["Elder"])  # a lone word is the name
        self.assertEqual(A.name_words(_person("Q", "Mr. Jo")), [])  # two letters are no name

    def test_the_lines_that_round_2_refused(self):
        cases = [
            ("i shoot Theo in the chest", THEO),
            ("i shoot Dr. Theo in the chest", THEO),
            ("i put a bullet in Theo's head", THEO),
            ("i shoot theo", THEO),
            ("i shoot @B", THEO),
            ("i shoot [[B]]", THEO),
            ("i shoot Vasilis in the leg", VASILIS),
            ("i hit Sam with the crowbar", SAM),
            ("i hit Old Sam with the crowbar", SAM),
            ("i shoot Iqbal in the knee", TUNDE),
            ("i hit Tunde with the crowbar", TUNDE),
            ("i stab Mira in the gut", _person("A", "Mira Holt", "doctor")),
        ]
        for line, person in cases:
            self.assertTrue(A.line_names_person(line, person), line)
            self.assertTrue(A.line_may_target(line, person, people=[person, GHOUL1]), line)
        self.assertFalse(A.line_names_person("i shoot Theodora", THEO))
        self.assertFalse(A.line_names_person("i shoot the doctor", THEO))

    def test_a_noun_the_engine_knows_nothing_about_is_no_evidence(self):
        for line, person in [
            ("i shoot the bastard", TUNDE), ("i shoot the creep", TUNDE), ("i shoot the thing", TUNDE),
            ("i fire my rifle at the bastard", TUNDE), ("i shoot the gun out of his hand", TUNDE),
            ("i shoot the doc", THEO), ("i shoot the healer", THEO), ("i shoot the merc", GRIT),
            ("i shoot the mercenary", GRIT), ("i shoot the hunter", TUNDE), ("i shoot the stranger", TUNDE),
            ("i shoot the old man", TUNDE),
        ]:
            self.assertTrue(A.line_may_target(line, person, people=[person]), line)
        self.assertFalse(A.line_may_target("i shoot the lock", TUNDE, people=[TUNDE]))

    def test_the_kind_word_of_a_figure_here_goes_to_the_figure_never_to_a_named_person(self):
        here = [TUNDE, GHOUL1]
        self.assertFalse(A.line_may_target("i shoot the ghoul", TUNDE, people=here))
        self.assertTrue(A.line_may_target("i shoot the ghoul", GHOUL1, people=here))
        self.assertEqual([p["code"] for p in A.kind_figures("i shoot the ghoul", here)], ["D"])

    def test_a_companions_role_holding_the_kind_word_is_not_the_kind(self):
        # Synthetic R17: Carlos the "ghoul hunter" is "the hunter", never "the ghoul".
        here = [HUNTER, GHOUL1, GHOUL2]
        self.assertFalse(A.line_may_target("i shoot the ghoul", HUNTER, people=here))
        self.assertTrue(A.line_may_target("i shoot the hunter", HUNTER, people=here))
        self.assertTrue(A.line_may_target("i shoot the ghoul hunter", HUNTER, people=here))
        self.assertEqual([p["code"] for p in A.kind_figures("i shoot the ghoul", here)], ["D", "E"])
        # The role never makes a kind: its head noun is the job. With no ghoul here the word is no evidence either way.
        self.assertEqual(A._role_words(HUNTER), ("ghoul hunter", {"hunter"}))
        self.assertEqual(A._kind_of(HUNTER), "")
        self.assertTrue(A.line_may_target("i shoot the ghoul", HUNTER))

    def test_a_person_pronoun_means_someone_here_whatever_else_the_line_names(self):
        # cc87dd29 T5: "i snap her neck and then burn the clinic to the ground" is at the one person here.
        beth = _person("B", "Beth", "doctor")
        clinic = [{"code": "L3", "name": "Radiation Fenced Sanctuary Clinic"}]
        self.assertTrue(A.line_may_target("i snap her neck and then burn the clinic to the ground", beth, people=[beth], places=clinic))
        self.assertTrue(A.line_may_target("i put a bullet in his head", TUNDE, people=[TUNDE, GHOUL1]))
        # "it" / "its" is the creature's: the ghoul named stays the ghoul's.
        self.assertFalse(A.line_may_target("i shoot the ghoul in its head", TUNDE, people=[TUNDE, GHOUL1]))


def _scene(*people: dict, addressed=(), present=None) -> dict:
    here = {"code": "L1", "name": "Radiation Fenced Sanctuary", "npcs": list(people)}
    conv = {"addressed": list(addressed), "present": list(present if present is not None else addressed),
            "listening": [], "names": {p["code"]: p["name"] for p in people}}
    return {"current_location": here, "locations": [here], "conversation_turn": conv}


class Model:
    def __init__(self, reply: str = "Yes"):
        self.reply = reply
        self.calls: list[tuple[str, str]] = []

    def __call__(self, phase: str, prompt: str, max_tokens: int) -> str:
        self.calls.append((phase, prompt))
        return self.reply if phase == A.PHASE_ATTACK else "No"


def _trigger(person: dict) -> dict:
    return {"skill_code": "ranged", "opposition": {"name": person["name"]}, "npc_ref": {"code": person["code"], "name": person["name"]}}


class TheAttackIntent(unittest.TestCase):
    def test_unnamed_t3_the_trigger_target_tunde_is_not_the_lines_when_a_ghoul_is_here(self):
        ctx = _scene(TUNDE, GHOUL1, addressed=["A"], present=["A", "D"])
        model = Model("Yes")
        inferred = _trigger(TUNDE)
        check, report = A.decide("i shoot the nearest ghoul", ctx, inferred, model)
        self.assertEqual(check["attack"]["code"], "D")
        self.assertNotIn("attack", inferred)
        self.assertIsNone(inferred["npc_ref"])
        self.assertIsNone(inferred["opposition"])
        self.assertEqual(report["not_the_lines"], {"code": "A", "name": "Tunde Iqbal"})
        self.assertEqual(model.calls, [])  # a yes-biased model is never asked about him
        # A thing the engine knows is not a person: nobody is the target, and nobody is asked about.
        inferred = _trigger(TUNDE)
        check, report = A.decide("i shoot the lock", _scene(TUNDE, addressed=["A"]), inferred, model)
        self.assertIsNone(check)
        self.assertIsNone(inferred["npc_ref"])
        self.assertEqual(report["not_the_lines"]["code"], "A")
        self.assertEqual(report["people"], [])

    def test_with_no_ghoul_on_the_roster_the_triggers_aim_stands(self):
        # unnamed T3 as recorded: no ghoul row exists; the word is no evidence (as main had it).
        inferred = _trigger(TUNDE)
        check, report = A.decide("i shoot the nearest ghoul", _scene(TUNDE, addressed=["A"]), inferred, Model("Yes"))
        self.assertIsNone(check)
        self.assertEqual((inferred["attack"]["code"], report["from"]), ("A", "trigger"))

    def test_the_figure_of_the_kind_the_line_names_is_the_target_instead(self):
        ctx = _scene(TUNDE, GHOUL1, GHOUL2, addressed=["A"], present=["A", "D", "E"])
        check, report = A.decide("i shoot the nearest ghoul", ctx, _trigger(TUNDE), Model("Yes"))
        self.assertEqual(check["attack"]["code"], "D")
        self.assertEqual(check["skill_code"], "ranged")
        self.assertTrue(check["replaces_inferred"])
        self.assertEqual(report["from"], "kind")

    def test_a_trigger_target_the_line_names_stands_as_before(self):
        ctx = _scene(TUNDE, addressed=["A"])
        for line in ("i shoot Tunde", "i shoot the hunter", "i shoot him", "i shoot the bastard", "i shoot the man",
                     "i shoot Iqbal in the knee", "i hit Tunde with the crowbar"):
            inferred = _trigger(TUNDE)
            check, report = A.decide(line, ctx, inferred, Model("Yes"))
            self.assertIsNone(check, line)
            self.assertEqual((inferred["attack"]["code"], report["from"]), ("A", "trigger"), line)
        for line, person in [("i shoot Theo in the chest", THEO), ("i put a bullet in Theo's head", THEO), ("i shoot the doc", THEO),
                             ("i shoot the healer", THEO), ("i shoot Vasilis in the leg", VASILIS), ("i hit Sam with the crowbar", SAM),
                             ("i shoot the merc", GRIT), ("i shoot the creep", GRIT), ("i shoot the thing", GRIT)]:
            inferred = _trigger(person)
            check, report = A.decide(line, _scene(person, addressed=[person["code"]]), inferred, None)
            self.assertIsNone(check, line)
            self.assertEqual(inferred["attack"], {"code": person["code"], "name": person["name"]}, line)
            self.assertEqual(inferred["opposition"], {"name": person["name"]}, line)
            self.assertEqual(report["from"], "trigger", line)

    def test_the_ask_candidates_are_the_people_the_line_can_mean_figures_first(self):
        ctx = _scene(CARLOS, GHOUL1, addressed=["A"], present=["A", "D"])
        model = Model("Yes")
        check, report = A.decide("i shoot the closest ghoul", ctx, None, model)
        self.assertEqual(report["people"], ["D"])
        self.assertEqual(check["attack"]["code"], "D")
        # A pronoun line names no kind: the engine's own order stands (the one addressed first).
        model = Model("Yes")
        check, report = A.decide("i shoot him", ctx, None, model)
        self.assertEqual(report["people"], ["A", "D"])
        # An unknown noun leaves everyone a candidate.
        check, report = A.decide("i shoot the bastard", ctx, None, Model("Yes"))
        self.assertEqual(report["people"], ["A", "D"])


class TheCombatTarget(unittest.TestCase):
    def _state(self, *people: dict) -> dict:
        here = {"code": "L1", "name": "Radiation Fenced Sanctuary", "npcs": list(people)}
        return {"current_location": here, "locations": [here], "player": {"level": 1}, "settings": {}}

    def test_a_thing_the_engine_knows_is_not_a_person_is_no_combat_target(self):
        with mock.patch.object(world.turn_ledger, "note") as note:
            self.assertIsNone(world._clear_combat_target(self._state(TUNDE), "i shoot the lock", {}))
        self.assertEqual(note.call_args[0][:2], ("check", "combat_target_not_the_lines"))
        self.assertIsNone(world._clear_combat_target(self._state(TUNDE), "i shoot the door", {}))
        self.assertIsNone(world._clear_combat_target(self._state(TUNDE), "i shoot toward the sanctuary", {}))

    def test_the_figure_of_the_kind_named_is_the_combat_target_over_a_named_person(self):
        state = self._state(TUNDE, GHOUL2, GHOUL1)
        self.assertEqual(world._clear_combat_target(state, "i shoot the nearest ghoul", {})["code"], "D")
        self.assertEqual(world._clear_combat_target(state, "i shoot the hunter", {})["code"], "A")
        self.assertEqual(world._clear_combat_target(self._state(TUNDE), "i shoot him", {})["code"], "A")
        self.assertEqual(world._clear_combat_target(self._state(CHIARA), "i shoot the doctor", {})["code"], "A")
        self.assertEqual(world._clear_combat_target(self._state(TUNDE), "attack Tunde [[A]]", {"npcs": ["A"]})["code"], "A")
        # With no ghoul here the one candidate stands (unnamed T3 as recorded, as main had it).
        self.assertEqual(world._clear_combat_target(self._state(TUNDE), "i shoot the nearest ghoul", {})["code"], "A")
        # The companion whose role holds the kind word is not the ghoul (R17).
        self.assertEqual(world._clear_combat_target(self._state(HUNTER, GHOUL1), "i shoot the ghoul", {})["code"], "D")

    def test_the_lines_that_round_2_refused_keep_their_target(self):
        for line, person in [("i shoot the bastard", TUNDE), ("i shoot the creep", TUNDE), ("i shoot the thing", TUNDE),
                             ("i shoot Iqbal in the knee", TUNDE), ("i shoot Theo in the chest", THEO),
                             ("i put a bullet in Theo's head", THEO), ("i shoot the doc", THEO), ("i shoot the healer", THEO),
                             ("i shoot Vasilis in the leg", VASILIS), ("i hit Sam with the crowbar", SAM), ("i shoot the merc", GRIT)]:
            with mock.patch.object(world.turn_ledger, "note") as note:
                target = world._clear_combat_target(self._state(person), line, {})
            self.assertEqual((target or {}).get("code"), person["code"], line)
            self.assertFalse(note.called, line)


def _chk(outcome: str, nat: int, code: str = "", name: str = "", skill: str = "ranged", weapon: str = "") -> dict:
    c = {"enabled": True, "skill": {"code": skill, "name": skill, "category": "combat"}, "natural": nat, "total": nat,
         "outcome": outcome, "weapon_or_tool": weapon, "opposition": None}
    if code:
        c["attack"] = {"code": code, "name": name}
        c["opposition"] = {"name": name}
    return c


def _row(code: str, name: str, role: str = "", kind: str = "", number: int = 0, hp: int = 40, died: int = 0) -> dict:
    return {"code": code, "name": name, "died_turn": died, "location_id": 3, "kind": kind, "kind_number": number, "role": role,
            "rank": "F", "attitude": "hostile" if kind else "neutral", "health": hp, "max_health": hp, "defense": 4,
            "dodge": 1, "attack_min": 1, "attack_max": 3}


def _records(line: str, people: list[dict]) -> dict:
    return {"people": people, "places": [], "player_names": ["Will"], "here_id": 3, "player_line": line}


NEEDS = {"status": "needs_target", "action_kind": "player_attack",
         "player_attack": {"weapon": "rifle", "attack_min": 2, "attack_max": 5, "strength": 3}}


class TheInterpretersTarget(unittest.TestCase):
    def test_an_aimed_check_at_a_titled_name_the_line_names_by_a_word_stays_on_them(self):
        people = [_row("B", "Dr. Theo", "doctor"), _row("A", "Mira Holt", "doctor")]
        for line in ("i shoot Theo in the chest", "i put a bullet in Theo's head", "i shoot the doc"):
            match = I.Matcher(people, [])
            row = I.attacked_row(_chk("success", 15, "B", "Dr. Theo"), _records(line, people), match)
            self.assertEqual((row or {}).get("code"), "B", line)
        # Untargeted: a roll with no target is matched to a whole name or code only (a mention is not an attack).
        row = I.attacked_row(_chk("success", 15), _records("i shoot Dr. Theo in the chest", people), I.Matcher(people, []))
        self.assertEqual((row or {}).get("code"), "B")
        self.assertIsNone(I.attacked_row(_chk("success", 15), _records("i shoot Theo in the chest", people), I.Matcher(people, [])))

    def test_a_word_three_rows_share_does_not_hide_the_row_named_whole(self):
        # integ-r3: "Dr. Theo", "Theo" and a leaked "NAME Theo ROLE"; 'i shoot Dr. Theo' is the one whole name.
        people = [_row("A", "NAME Theo ROLE"), _row("B", "Dr. Theo", "doctor"), _row("C", "Theo")]
        row = I.attacked_row(_chk("failure", 9), _records("i shoot Dr. Theo", people), I.Matcher(people, []))
        self.assertEqual((row or {}).get("code"), "B")
        # An aimed check at any of them stands when the line holds the shared word.
        for code in ("A", "B", "C"):
            row = I.attacked_row(_chk("failure", 9, code, "Theo"), _records("i shoot Theo", people), I.Matcher(people, []))
            self.assertEqual((row or {}).get("code"), code)
        # Two rows a word alone names, neither whole: nobody (ambiguous matches resolve to nothing).
        people = [_row("A", "Mara Khan"), _row("B", "Carlos Khan")]
        self.assertIsNone(I.attacked_row(_chk("failure", 9), _records("i shoot Khan", people), I.Matcher(people, [])))

    def test_r17_the_ghoul_hunter_aimed_by_an_old_check_gives_way_to_the_ghoul(self):
        people = [_row("C", "Carlos Khan", "ghoul hunter"), _row("D", "Ghoul 1", "ghoul", "Ghoul", 1), _row("E", "Ghoul 2", "ghoul", "Ghoul", 2)]
        out = I.run("You fire into the dark. Carlos [[C]] flinches at the shot.", _records("i shoot the ghoul", people),
                    lambda *a: "No", {"skill_checks": [_chk("success", 15, "C", "Carlos Khan")], "_deterministic_combat": dict(NEEDS)})
        beats = out["report"].get("attack_beats") or []
        self.assertEqual([(b["code"], b["aimed"]) for b in beats], [("D", False)])
        self.assertEqual(out["report"]["combat_after_draft"]["target"]["code"], "D")
        self.assertIn("the ghoul [[D]]", out["narration"])
        self.assertNotIn("Carlos Khan [[C]].", out["narration"])

    def test_the_one_person_present_is_the_target_of_an_unknown_noun(self):
        people = [_row("A", "Tunde Iqbal", "hunter")]
        out = I.run("You fire. Tunde [[A]] staggers.", _records("i shoot the bastard", people), lambda *a: "No",
                    {"skill_checks": [_chk("success", 15, "A", "Tunde Iqbal")], "_deterministic_combat": {"status": "not_combat"}})
        self.assertEqual([b["code"] for b in out["report"].get("attack_beats") or []], ["A"])


class OneResolutionPerRow(unittest.TestCase):
    """Round 3 (d): a combat block already resolved on the row is not resolved again; the band wins a disagreement."""

    def _combat(self, outcome: str, damage: int, after: int) -> dict:
        return {"status": "resolved_player_attack", "action_kind": "player_attack",
                "player_attack": {"weapon": "rifle", "attack_min": 2, "attack_max": 5},
                "target": {"code": "A", "name": "Mira Holt", "combat_profile": {"max_health": 40, "defense": 4}},
                "resolution": {"outcome": outcome, "damage": damage, "raw_damage_roll": 4, "target_health_before": 40,
                               "target_health_after": after}}

    def test_agreeing_bands_resolve_nothing_again(self):
        people = [_row("A", "Mira Holt", "doctor", hp=37)]
        combat = self._combat("hit", 3, 37)
        out = I.run("You raise the rifle at Mira [[A]]. She freezes.", _records("i shoot Mira [[A]]", people), lambda *a: "No",
                    {"skill_checks": [_chk("success", 15)], "_deterministic_combat": combat})
        beats = out["report"].get("attack_beats") or []
        self.assertEqual([(b["code"], b["aimed"], b["state"]) for b in beats], [("A", False, "unshown")])
        self.assertNotIn("resolution", beats[0])
        self.assertIsNone(out["report"].get("combat_after_draft"))
        self.assertIsNone(attack_line.follow_band(_chk("success", 15), combat))

    def test_the_bands_disagree_the_check_wins_and_the_combat_is_corrected_by_the_difference(self):
        # baseline T3: the check rolled a failure, the combat's own d20 a glancing hit (damage 1).
        people = [_row("A", "Mira Holt", "doctor", hp=39)]
        combat = self._combat("glancing_hit", 1, 39)
        out = I.run("You raise the rifle at Mira [[A]]. She freezes.", _records("i shoot Mira [[A]]", people), lambda *a: "No",
                    {"skill_checks": [_chk("failure", 6)], "_deterministic_combat": combat})
        after = out["report"]["combat_after_draft"]
        self.assertEqual((after["resolution"]["outcome"], after["resolution"]["damage"], after["resolution"]["damage_applied_before"]),
                         ("miss", 0, 1))
        self.assertEqual(after["resolution"]["combat_roll_outcome"], "glancing_hit")
        self.assertTrue(after["resolved_after_draft"] and after["reapplied_from_band"])
        self.assertIn("Mira Holt [[A]]", out["narration"])
        beat = out["report"]["attack_beats"][0]
        self.assertIn("miss", beat["beat"].lower() + " " + ("short" if "short" in beat["beat"] else ""))
        # A hit on a miss: the damage follows the combat's own roll against the band.
        followed = attack_line.follow_band(_chk("success", 15), self._combat("miss", 0, 40))
        self.assertEqual((followed["resolution"]["outcome"], followed["resolution"]["damage"], followed["resolution"]["target_health_after"],
                          followed["resolution"]["damage_applied_before"]), ("hit", 3, 37, 0))
        graze = attack_line.follow_band(_chk("partial", 11), self._combat("hit", 3, 37))
        self.assertEqual((graze["resolution"]["outcome"], graze["resolution"]["damage"], graze["resolution"]["damage_applied_before"]), ("glancing_hit", 1, 3))

    def test_world_moves_the_health_by_the_difference(self):
        _fresh_world()
        with db.connect().closing() as conn:
            conn.execute("INSERT INTO npcs (code, location_id, name, role, health, max_health) VALUES ('ZZ', 1, 'Mira Holt', 'doctor', 39, 40)")
            conn.commit()
            combat = self._combat("glancing_hit", 1, 39)
            combat["target"]["code"] = "ZZ"
            corrected = attack_line.follow_band(_chk("failure", 6), combat)
            world._reapply_combat_from_band(conn, corrected, 3)
            conn.commit()
            self.assertEqual(conn.execute("SELECT health FROM npcs WHERE code = 'ZZ'").fetchone()[0], 40)
            # And the other way: a hit the combat called a miss takes its damage off.
            up = attack_line.follow_band(_chk("success", 15), {**self._combat("miss", 0, 40), "target": {**combat["target"]}})
            world._reapply_combat_from_band(conn, up, 4)
            conn.commit()
            self.assertEqual(conn.execute("SELECT health FROM npcs WHERE code = 'ZZ'").fetchone()[0], 37)
            journal = [r[0] for r in conn.execute("SELECT content FROM journal WHERE kind = 'mechanics' ORDER BY id").fetchall()]
        self.assertTrue(any("follows the attack check" in j and "ZZ" in j for j in journal), journal)


# --- The whole turn: merge1 T4 live (F186) -----------------------------------------


def _fresh_world():
    os.environ.update(_ENV)
    assert str(db.db_path()).startswith(str(_TMP)), db.db_path()
    db.init_db()
    world.start_playthrough({"player_name": "Will Tanaka", "start_location": "Radiation Fenced Sanctuary",
                             "special_ability_origin": "none", "dice_checks_enabled": True})


def _turn(narration: str) -> dict:
    return {
        "scene_plan": {"goal": "act", "focus_points": []},
        "narration_segments": [{"label": "scene", "text": narration}],
        "narration": narration,
        "player": {},
        "self_check": {"passed": True, "issues_found": [], "corrections_made": []},
        "turn_summary": "a beat",
        "scene_focus": "action",
        "scene_cast": {"present": [], "interacting": [], "off": []},
        "_interpreter_pending": {"config": {}},
        "_model_trace": [],
        "_model_usage": [],
    }


def _forced(outcome: str):
    real = skill_checks.resolve_check

    def resolve(**kwargs):
        out = real(**kwargs)
        out.update({"outcome": outcome, "degree": outcome})
        return out

    return resolve


def _file_two_ghouls(conn, turn, max_id_before, text, turn_npcs=None, here_at_start=0):
    """Stands in for whereabouts.file_new_people: the prose's two ghouls are filed where the player is, no profile yet."""
    here = int(conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()[0])
    out = []
    for number in (1, 2):
        code = world._next_alpha_code(conn, "npcs")
        conn.execute(
            "INSERT INTO npcs (code, location_id, name, role, attitude, kind, kind_number) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (code, here, f"Ghoul {number}", "ghoul", "hostile", "Ghoul", number),
        )
        out.append({"code": code})
    return out


class TheWholeTurnMerge1T4(unittest.TestCase):
    def setUp(self):
        _fresh_world()

    def _ghouls(self) -> list[dict]:
        with db.connect().closing() as conn:
            return [dict(r) for r in conn.execute("SELECT code, name, health, max_health, location_id FROM npcs WHERE kind = 'Ghoul' ORDER BY kind_number").fetchall()]

    def test_f186_the_untargeted_roll_hurts_ghoul_1_and_the_line_goes_in(self):
        with mock.patch.object(world, "generate_turn", return_value=_turn(M1_T4)), \
                mock.patch.object(llm, "_chat_content", return_value="No"), \
                mock.patch.object(skill_checks, "resolve_check", side_effect=_forced("success")), \
                mock.patch.object(whereabouts, "file_new_people", side_effect=_file_two_ghouls):
            world.play_turn(M1_T4_LINE)
        files = sorted((_TMP / "traces").glob("turn-*.json"), key=lambda p: p.stat().st_mtime)
        trace = json.loads(files[-1].read_text(encoding="utf-8"))
        final = trace["final_turn"]
        checks = [c for c in final.get("skill_checks") or [] if c.get("natural") is not None]
        self.assertEqual([((c.get("skill") or {}).get("code"), (c.get("attack") or {}).get("code")) for c in checks], [("ranged", None)])
        ghouls = self._ghouls()
        self.assertEqual([g["name"] for g in ghouls], ["Ghoul 1", "Ghoul 2"])
        one = ghouls[0]
        # The combat math followed the check on Ghoul 1 after the draft, and the damage came off.
        combat = final["_deterministic_combat"]
        self.assertEqual((combat["status"], combat["target"]["code"], combat["resolution"]["outcome"]), ("resolved_player_attack", one["code"], "hit"))
        self.assertTrue(combat["resolved_after_draft"] and combat["applied_after_draft"])
        self.assertGreater(one["max_health"], 0)
        self.assertEqual(one["health"], one["max_health"] - combat["resolution"]["damage"])
        self.assertLess(one["health"], one["max_health"])
        self.assertEqual(ghouls[1]["health"], ghouls[1]["max_health"])
        # The line, on the ghoul, in the prose and the summary.
        beat = attack_line.line_for(checks[0], f"the ghoul [[{one['code']}]]")
        self.assertIn(beat, final["narration"])
        self.assertIn(beat, final["turn_summary"])
        self.assertTrue(final["narration"].replace(" " + beat, "", 1).startswith(M1_T4[:400]))
        notes = json.dumps(trace.get("engine") or {})
        for note in ("combat_profiles_here", "combat_applied_after_draft", "attack_not_in_prose"):
            self.assertIn(note, notes)


if __name__ == "__main__":
    unittest.main()
