"""Whom the player's attack line is at, upstream (unnamed T3, unnamed2 T3/T4; merge1 T4 live, F186).

'i shoot the nearest ghoul' with only Tunde Iqbal the hunter here was aimed at
him: world._clear_combat_target took the one candidate, the combat math hurt
him, skill_checks made him the inferred check's npc_ref and attack_intent
marked that as the attack ("trigger"). 'i shoot the closest ghoul' did the same
to Carlos Khan, a companion. The line's own words decide now, in one place
(attack_intent.line_may_target, kind_figures), used by the combat target, the
attack intent's candidate list and the interpreter's attacked_row.

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

from app import attack_intent as A, attack_line, db, llm, skill_checks, whereabouts, world  # noqa: E402
from test_attack_line import M1_T4, M1_T4_LINE  # noqa: E402


def _person(code: str, name: str, role: str = "", kind: str = "", number: int = 0, **extra) -> dict:
    return {"code": code, "name": name, "role": role, "kind": kind, "kind_number": number, "died_turn": 0, "rank": "F",
            "stat_profile": {}, **extra}


TUNDE = _person("A", "Tunde Iqbal", "hunter")
CARLOS = _person("A", "Carlos Khan", "ranger")
CHIARA = _person("A", "Chiara Weber", "doctor")
GHOUL1 = _person("D", "Ghoul 1", "ghoul", "Ghoul", 1)
GHOUL2 = _person("E", "Ghoul 2", "ghoul", "Ghoul", 2)


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

    def test_a_named_person_is_meant_by_name_job_person_word_or_pronoun_not_by_a_kind(self):
        for line in ("i shoot Tunde", "i shoot Tunde Iqbal", "i shoot [[A]]", "i shoot @A", "i shoot the hunter",
                     "i shoot the man by the fence", "i shoot the stranger", "i shoot him", "i put a bullet in his head",
                     "i open fire", "i attack"):
            self.assertTrue(A.line_may_target(line, TUNDE), line)
        for line in ("i shoot the nearest ghoul", "i shoot the closest ghoul", "i shoot another ghoul", "i shoot the ghouls",
                     "i shoot the lock on the door"):
            self.assertFalse(A.line_may_target(line, TUNDE), line)
        self.assertTrue(A.line_may_target("i shoot the doctor", CHIARA))
        self.assertFalse(A.line_may_target("i shoot the closest ghoul", CARLOS))
        self.assertFalse(A.line_may_target("", TUNDE))

    def test_a_numbered_figure_is_meant_by_its_kind(self):
        self.assertTrue(A.line_may_target("i shoot the nearest ghoul", GHOUL1))
        self.assertTrue(A.line_may_target("i shoot the ghouls", GHOUL2))
        self.assertTrue(A.line_may_target("i shoot it", GHOUL1))
        self.assertFalse(A.line_may_target("i shoot the doctor", GHOUL1))
        self.assertFalse(A.line_may_target("i shoot at the sound, maybe ghouls", GHOUL1))

    def test_kind_figures_are_the_living_ones_of_the_kind_named_lowest_first(self):
        people = [TUNDE, GHOUL2, GHOUL1]
        self.assertEqual([p["code"] for p in A.kind_figures("i shoot the closest ghoul", people)], ["D", "E"])
        self.assertEqual(A.kind_figures("i shoot at the sound, maybe ghouls", people), [])
        self.assertEqual(A.kind_figures("i shoot the hunter", people), [])
        dead = [{**GHOUL1, "died_turn": 3}, GHOUL2]
        self.assertEqual([p["code"] for p in A.kind_figures("i shoot the ghoul", dead)], ["E"])


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


class TheAttackIntent(unittest.TestCase):
    def test_unnamed_t3_the_trigger_target_tunde_is_not_the_lines_and_no_one_else_is_asked_about(self):
        ctx = _scene(TUNDE, addressed=["A"])
        inferred = {"skill_code": "ranged", "opposition": {"name": "Tunde Iqbal"}, "npc_ref": {"code": "A", "name": "Tunde Iqbal"}}
        model = Model("Yes")
        check, report = A.decide("i shoot the nearest ghoul", ctx, inferred, model)
        self.assertIsNone(check)
        self.assertNotIn("attack", inferred)
        self.assertIsNone(inferred["npc_ref"])
        self.assertIsNone(inferred["opposition"])
        self.assertEqual(report["not_the_lines"], {"code": "A", "name": "Tunde Iqbal"})
        self.assertIsNone(report["target"])
        self.assertEqual(model.calls, [])  # a yes-biased model is never asked about him

    def test_the_figure_of_the_kind_the_line_names_is_the_target_instead(self):
        ctx = _scene(TUNDE, GHOUL1, GHOUL2, addressed=["A"], present=["A", "D", "E"])
        inferred = {"skill_code": "ranged", "opposition": {"name": "Tunde Iqbal"}, "npc_ref": {"code": "A", "name": "Tunde Iqbal"}}
        check, report = A.decide("i shoot the nearest ghoul", ctx, inferred, Model("Yes"))
        self.assertEqual(check["attack"]["code"], "D")
        self.assertEqual(check["skill_code"], "ranged")
        self.assertTrue(check["replaces_inferred"])
        self.assertEqual(report["from"], "kind")

    def test_a_trigger_target_the_line_names_stands_as_before(self):
        ctx = _scene(TUNDE, addressed=["A"])
        for line in ("i shoot Tunde", "i shoot the hunter", "i shoot him"):
            inferred = {"skill_code": "ranged", "opposition": {"name": "Tunde Iqbal"}, "npc_ref": {"code": "A", "name": "Tunde Iqbal"}}
            check, report = A.decide(line, ctx, inferred, Model("Yes"))
            self.assertIsNone(check, line)
            self.assertEqual((inferred["attack"]["code"], report["from"]), ("A", "trigger"), line)

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


class TheCombatTarget(unittest.TestCase):
    def _state(self, *people: dict) -> dict:
        here = {"code": "L1", "name": "Radiation Fenced Sanctuary", "npcs": list(people)}
        return {"current_location": here, "locations": [here], "player": {"level": 1}, "settings": {}}

    def test_unnamed_t3_the_one_person_here_is_not_the_combat_target_of_a_ghoul_line(self):
        with mock.patch.object(world.turn_ledger, "note") as note:
            self.assertIsNone(world._clear_combat_target(self._state(TUNDE), "i shoot the nearest ghoul", {}))
        self.assertEqual(note.call_args[0][:2], ("check", "combat_target_not_the_lines"))
        self.assertIsNone(world._clear_combat_target(self._state(CARLOS), "i shoot the closest ghoul", {}))
        self.assertIsNone(world._clear_combat_target(self._state(CARLOS), "i shoot another ghoul", {}))

    def test_the_figure_of_the_kind_named_is_the_combat_target_over_a_named_person(self):
        state = self._state(TUNDE, GHOUL2, GHOUL1)
        self.assertEqual(world._clear_combat_target(state, "i shoot the nearest ghoul", {})["code"], "D")
        self.assertEqual(world._clear_combat_target(state, "i shoot the hunter", {})["code"], "A")
        self.assertEqual(world._clear_combat_target(self._state(TUNDE), "i shoot him", {})["code"], "A")
        self.assertEqual(world._clear_combat_target(self._state(CHIARA), "i shoot the doctor", {})["code"], "A")
        self.assertEqual(world._clear_combat_target(self._state(TUNDE), "attack Tunde [[A]]", {"npcs": ["A"]})["code"], "A")


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
