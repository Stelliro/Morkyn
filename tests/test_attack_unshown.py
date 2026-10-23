"""#129 the other way round: the dice decided an attack and the prose never showed it.

integ-r4 T3 (Hermes 3 8B on the round-4 merged code), 'i shoot Dr. Vasilis': the attack
check rolled a natural 20 against Vasilis [[B]], a critical success, and the prose
never names him. It became a shooting test with Dr. Wyatt [[C]] at an 'abandoned
airfield', the round 'wide of the mark', and where_ended moved the player outside.

Three engine causes, three fixes, no new model ask:

* The engine told the narrator two outcomes for one attack. The combat math rolled
  its own d20 ("miss", unarmed) beside the check's critical success, and the prose
  wrote the miss. The combat's hit or miss now follows the attack check on the
  same person (world._combat_follows_attack_check); the damage is still the combat
  math's own roll.
* A rolled attack whose target the final prose names nowhere (by code or by a name
  only they have, the interpreter's Matcher) gets the roll's own outcome line,
  "Your shot hits Vasilis [[B]].", and the summary follows the prose
  (interpreter.show_unnamed_attacks). A prose that names the target is left alone.
* A turn whose line asks for no travel (the movement rules said not_travel) and
  whose rolled attack was aimed at someone in this room is not moved by
  where_ended (where_ended.attacked_here). Real travel still follows the prose.

Also: the narrator was told the roll was 'for' "i shoot Dr." (the clause splitter
stopped at the title); check_for_clause now keeps titles whole.

Run:  cd tests && python -m unittest test_attack_unshown
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-attack-unshown-"))
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

from app import attack_intent, db, interpreter, llm, skill_checks, where_ended, world  # noqa: E402

I = interpreter

T3_LINE = "i shoot Dr. Vasilis"
# The final T3 prose, exactly as the turn trace has it (turn-6b5a9245-000004-player.json).
T3 = (
    'Dr. Wyatt [[C]] waves you over. He calls, "before you go, there\'s one more test. I need you to shoot straight."\n\n'
    "You raise your arm, the X-01 power armor responding with ease. The ship boots ground your stance. You aim at the "
    "distant target and pull the trigger.\n\n"
    "The round flies true, but at the last moment, something seems to deflect it. It passes harmlessly wide of the mark.\n\n"
    'Dr. Wyatt [[C]] nods, satisfied. "Not bad," he says. "You\'ve got the skill, even if your aim can use some work." '
    "The sun casts long shadows across the abandoned airfield as you holster your weapon and head out to meet your next "
    "mission."
)
# T2's prose names him (a turn where the scene does show the person).
T2_NAMED = (
    "You see a grizzled doctor, Wyatt [[C]], tending to a wound. Beside him is a passerby named Vasilis [[B]], who looks "
    "up at your approach."
)

# The T3 check as the trace has it (the fields these rules read).
def _check(outcome: str = "critical_success", code: str = "B", name: str = "Vasilis", skill: str = "ranged",
           natural: int | None = 20) -> dict:
    return {
        "enabled": True, "skill": {"code": skill, "name": skill.title(), "category": "combat"}, "natural": natural,
        "outcome": outcome, "degree": outcome, "flavor": "You make it look effortless — clean, complete, and then some.",
        "attack": {"code": code, "name": name}, "for": "i shoot Dr.",
    }


# The T3 combat as the trace has it (prompt_context.mechanics_context.combat).
T3_COMBAT = {
    "status": "resolved_player_attack",
    "action_kind": "player_attack",
    "player_attack": {"weapon": "unarmed", "weapon_code": "", "equipment": {}, "strength": 7, "defense": 4, "dodge": 4,
                      "attack_min": 2, "attack_max": 4},
    "target": {"code": "B", "name": "Vasilis", "rank": "F", "attitude": "neutral",
               "combat_profile": {"initialized": True, "health": 40, "max_health": 40, "attack_min": 3, "attack_max": 9,
                                  "defense": 6, "dodge": 6}},
    "resolution": {"outcome": "miss", "attack_roll": 4, "attack_total": 6, "evasion_target": 14, "raw_damage_roll": 3,
                   "damage": 0, "target_health_before": 40, "target_health_after": 40, "target_defeated": False},
}


def _records() -> dict:
    """The integ-r4 roster at T3: Dana [[A]], Vasilis [[B]], Wyatt [[C]]."""
    return {
        "people": [
            {"code": "A", "name": "Dana", "died_turn": 0},
            {"code": "B", "name": "Vasilis", "died_turn": 0},
            {"code": "C", "name": "Wyatt", "died_turn": 0},
        ],
        "places": [
            {"code": "L1", "name": "Radiation Fenced Sanctuary", "destroyed_turn": 0},
            {"code": "L2", "name": "Radiation Fenced Sanctuary Clinic", "destroyed_turn": 0},
        ],
        "player_names": ["Will Tanaka"],
    }


class Biased:
    """A model that answers every ask the same way, and counts them."""

    def __init__(self, reply: str):
        self.reply = reply
        self.calls: list[str] = []

    def __call__(self, phase: str, prompt: str, max_tokens: int) -> str:
        self.calls.append(phase)
        return self.reply


def _line(check: dict, label: str = "Vasilis [[B]]") -> str:
    """The engine's own result line for the check (app/attack_line.py: drawn from a pool, seeded by the roll)."""
    from app import attack_line

    return attack_line.line_for(check, label)


T3_TRIGGER = "You aim at the distant target and pull the trigger."


class TheProseIgnoredTheAttack(unittest.TestCase):
    def test_integ_r4_t3_the_critical_hit_goes_in_after_the_shot_and_the_summary_follows(self):
        check = _check()
        beat = _line(check)
        self.assertIn("Vasilis [[B]]", beat)
        out = I.run(T3, _records(), Biased("No"), {"skill_checks": [check]})
        text = out["narration"]
        # Nothing cut: the line goes in after the player's shot (the trigger pulled), not at the end.
        self.assertEqual(text, T3.replace(T3_TRIGGER, f"{T3_TRIGGER} {beat}"))
        self.assertEqual(text.count("Vasilis"), 1)
        entry = out["report"]["attack_beats"][0]
        self.assertEqual((entry["code"], entry["state"], entry["action"]), ("B", "unshown", "inserted"))
        self.assertIn(beat, I.summary(out["events"], text, attack_beats=out["report"]["attack_beats"]))

    def test_the_reverse_a_failed_roll_is_a_miss_on_him(self):
        check = _check("failure", natural=4)
        out = I.run(T3, _records(), Biased("No"), {"skill_checks": [check]})
        self.assertIn(f"{T3_TRIGGER} {_line(check)}", out["narration"])
        self.assertRegex(_line(check), r"miss|wide|short")
        check = _check("partial", skill="melee", natural=11)
        out = I.run(T3, _records(), Biased("No"), {"skill_checks": [check]})
        self.assertRegex(_line(check), r"^Your (blow|fist|strike) (only grazes|glances off|just clips|nicks) Vasilis \[\[B\]\]\.$")
        self.assertIn(_line(check), out["narration"])

    def test_a_scene_that_names_the_target_but_shows_no_attack_gets_the_line_after_that_sentence(self):
        for text in (T2_NAMED, T2_NAMED.replace("Vasilis [[B]]", "Dr. Vasilis")):
            out = I.run(text, _records(), Biased("No"), {"skill_checks": [_check()]})
            self.assertTrue(out["narration"].startswith(text), out["narration"])
            self.assertTrue(out["narration"].endswith(_line(_check())))
            self.assertEqual(out["report"]["attack_beats"][0]["where"], "target")

    def test_yes_and_no_biased_models_change_nothing_and_no_ask_is_made_for_it(self):
        for reply in ("Yes", "No.", "Yes, he is dead at the end"):
            with_roll, without = Biased(reply), Biased(reply)
            out = I.run(T3, _records(), with_roll, {"skill_checks": [_check()]})
            I.run(T3, _records(), without, {"skill_checks": []})
            self.assertEqual(with_roll.calls, without.calls, reply)
            self.assertEqual(out["narration"].count(_line(_check())), 1, reply)

    def test_no_roll_no_attack_record_or_dice_off_adds_nothing(self):
        no_target = _check()
        no_target.pop("attack")
        for checks in ([], [no_target], [_check(natural=None)]):
            out = I.run(T3, _records(), Biased("No"), {"skill_checks": checks})
            self.assertEqual(out["narration"], T3)
        self.assertEqual(I.run(T3, _records(), Biased("No"), None)["narration"], T3)

    def test_with_no_act_to_follow_the_line_goes_before_a_closing_question(self):
        quiet = "The wind moves through the empty yard.\n\nA dog barks somewhere far off."
        beat = _line(_check())
        out = I.run(quiet + "\n\nWhat do you do?", _records(), Biased("No"), {"skill_checks": [_check()]})
        self.assertEqual(out["narration"], f"{quiet} {beat}\n\nWhat do you do?")
        out = I.run(quiet + " What do you do?", _records(), Biased("No"), {"skill_checks": [_check()]})
        self.assertEqual(out["narration"], f"{quiet} {beat} What do you do?")


class OneRollDecidesTheAttack(unittest.TestCase):
    def test_integ_r4_t3_the_combat_miss_follows_the_critical_success(self):
        out = world._combat_follows_attack_check(T3_COMBAT, [_check()])
        self.assertEqual(out["resolution"]["outcome"], "hit")
        # The combat math's own damage roll (3) less the target's defense (6 // 4).
        self.assertEqual(out["resolution"]["damage"], 2)
        self.assertEqual(out["resolution"]["target_health_after"], 38)
        self.assertEqual(out["resolution"]["combat_roll_outcome"], "miss")
        self.assertEqual(T3_COMBAT["resolution"]["outcome"], "miss")  # the input is not changed

    def test_the_reverse_a_combat_hit_follows_a_failed_check(self):
        hit = json.loads(json.dumps(T3_COMBAT))
        hit["resolution"].update({"outcome": "hit", "damage": 2, "target_health_after": 38})
        out = world._combat_follows_attack_check(hit, [_check("failure", natural=3)])
        self.assertEqual((out["resolution"]["outcome"], out["resolution"]["damage"]), ("miss", 0))
        self.assertEqual(out["resolution"]["target_health_after"], 40)
        out = world._combat_follows_attack_check(hit, [_check("partial", natural=12)])
        self.assertEqual((out["resolution"]["outcome"], out["resolution"]["damage"]), ("glancing_hit", 1))

    def test_agreeing_rolls_another_target_or_no_roll_change_nothing(self):
        self.assertIsNone(world._combat_follows_attack_check(T3_COMBAT, [_check("failure", natural=3)]))
        self.assertIsNone(world._combat_follows_attack_check(T3_COMBAT, [_check(code="C", name="Wyatt")]))
        self.assertIsNone(world._combat_follows_attack_check(T3_COMBAT, [_check(natural=None)]))
        self.assertIsNone(world._combat_follows_attack_check({"status": "not_combat"}, [_check()]))

    def test_the_roll_is_for_the_whole_clause(self):
        self.assertEqual(skill_checks.check_for_clause(T3_LINE, "ranged"), "i shoot Dr. Vasilis")
        self.assertEqual(skill_checks.check_for_clause("I look around. Then i shoot him.", "ranged"), "Then i shoot him.")


# --- the whole turn, on an isolated save -------------------------------------


def _fresh_world():
    os.environ.update(_ENV)
    assert str(db.db_path()).startswith(str(_TMP)), db.db_path()
    db.init_db()
    world.start_playthrough({"player_name": "Will Tanaka", "start_location": "Radiation Fenced Sanctuary",
                             "special_ability_origin": "none", "dice_checks_enabled": True})


def _add_npc(name: str) -> str:
    with db.connect().closing() as conn:
        loc = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()["current_location_id"]
        code = world._next_alpha_code(conn, "npcs")
        conn.execute("INSERT INTO npcs (code, location_id, name) VALUES (?, ?, ?)", (code, int(loc), name))
        conn.commit()
        return code


def _here_id() -> int:
    with db.connect().closing() as conn:
        return int(conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()[0])


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


def _where(letter: str):
    """The live T3 replies: "outside Radiation" (C there; B in this save, which has no clinic), then "No."
    to "are you still in <here>?"."""
    def ask(system: str, user: str) -> str:
        return letter if system == "Answer with one letter." else ("Yes" if letter.startswith("A") else "No.")
    return ask


def _play(narration: str, line: str, outcome: str, letter: str = "B) outside Radiation") -> dict:
    previous = where_ended.set_ask(_where(letter))
    try:
        with mock.patch.object(world, "generate_turn", return_value=_turn(narration)), \
                mock.patch.object(llm, "_chat_content", return_value="No"), \
                mock.patch.object(skill_checks, "resolve_check", side_effect=_forced(outcome)):
            world.play_turn(line)
    finally:
        where_ended.set_ask(previous)
    files = sorted((_TMP / "traces").glob("turn-*.json"), key=lambda p: p.stat().st_mtime)
    return json.loads(files[-1].read_text(encoding="utf-8"))


class TheWholeTurn(unittest.TestCase):
    def setUp(self):
        _fresh_world()
        self.b = _add_npc("Vasilis")
        self.c = _add_npc("Wyatt")
        self.here = _here_id()
        self.prose = T3.replace("[[C]]", f"[[{self.c}]]")

    def test_integ_r4_t3_hit_shown_combat_agrees_and_the_player_stays(self):
        trace = _play(self.prose, T3_LINE, "critical_success")
        checks = trace["final_turn"].get("skill_checks") or []
        self.assertTrue([c for c in checks if (c.get("attack") or {}).get("code") == self.b], checks)
        self.assertEqual([c.get("for") for c in checks], ["i shoot Dr. Vasilis"])
        narration = trace["final_turn"]["narration"]
        beat = _line(checks[0], f"Vasilis [[{self.b}]]")
        self.assertIn(f"{T3_TRIGGER} {beat}", narration)
        self.assertIn(beat, trace["final_turn"]["turn_summary"])
        combat = trace["final_turn"]["_deterministic_combat"]
        self.assertEqual(combat["resolution"]["outcome"], "hit")
        self.assertEqual(trace["prompt_context"]["mechanics_context"]["combat"]["resolution"]["outcome"], "hit")
        self.assertEqual(_here_id(), self.here)
        notes = json.dumps(trace.get("engine") or {})
        self.assertIn("move_from_prose_refused", notes)
        self.assertIn("attack_not_in_prose", notes)

    def test_the_reverse_a_failed_roll_says_miss(self):
        trace = _play(self.prose, T3_LINE, "failure")
        check = trace["final_turn"]["skill_checks"][0]
        self.assertIn(f"{T3_TRIGGER} {_line(check, f'Vasilis [[{self.b}]]')}", trace["final_turn"]["narration"])
        self.assertEqual(trace["final_turn"]["_deterministic_combat"]["resolution"]["damage"], 0)

    def test_real_travel_still_follows_the_prose(self):
        # No attack and the line asks to leave: where_ended still moves the player as the prose shows.
        trace = _play("You walk out through the gates onto the open road, the fence shrinking behind you.",
                      "i leave the town", "failure")
        self.assertNotIn("move_from_prose_refused", json.dumps(trace.get("engine") or {}))
        self.assertNotEqual(_here_id(), self.here)


class TheMoveRule(unittest.TestCase):
    def test_settle_keeps_an_attack_turn_in_the_room_and_moves_real_travel(self):
        _fresh_world()
        b = _add_npc("Vasilis")
        here = _here_id()
        with db.connect().closing() as conn:
            built = where_ended.build_options(conn, T3)
            outside = next(o for o in built["options"] if o["kind"] == "outside")

            def result(checks):
                return {"player": {}, "skill_checks": checks,
                        "_where_ended": {"here_id": here, "options": built["options"], "choice": outside,
                                         "confirmed": True}}

            r = result([_check(code=b)])
            report = where_ended.settle(conn, r, {"status": "not_travel"}, T3_LINE)
            self.assertEqual(report.get("where_ended_refused"), "act_aimed_here")
            self.assertFalse(r["player"].get("move_to_location_code"))
            # Travel read in the line (unresolved): the prose still decides.
            r = result([_check(code=b)])
            report = where_ended.settle(conn, r, {"status": "unresolved"}, "i shoot Vasilis and run for the gates")
            self.assertEqual(report.get("rule"), "where_ended_outside")
            # No attack, or an attack on someone not in this room: as before.
            for checks in ([], [_check(code="ZZ")], [_check(code=b, natural=None)]):
                r = result(checks)
                report = where_ended.settle(conn, r, {"status": "not_travel"}, "i look around")
                self.assertEqual(report.get("rule"), "where_ended_outside", checks)


if __name__ == "__main__":
    unittest.main()
