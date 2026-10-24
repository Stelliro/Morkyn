"""sonnet100 T42 (Hermes 3 8B, Sonnet as the player, 2026-10-25): the engine's own rule text ended the prose (F193).

The recorded turn: 'I stab at Peregrine again and shove him back from the grave, shouting at him to keep
away from me.' rolled melee 1d20=3, failure, degree unskilled_mishap, a self-injury to the hand (-1 HP).
The draft had Peregrine recoil and fall. The shipped narration ended:

    "Peregrine [[H]] is still alive. Without training, the weapon/tool does as much harm to you as to the
    world. You are unskilled at wielding this — you end up taking your own hand into the mess. Unskilled
    with Melee: you injure your own hand."

Verified cause (the trace, model_trace[37] "refused_deaths"): the draft never held those sentences. The
model's died-ask said yes (Peregrine dead), the roll refused it, and interpreter.outcome_beat appended the
check's "flavor" (skill_checks.DEGREE_FLAVOR["unskilled_mishap"] + the mishap join + the injury summary)
after "is still alive." The turn summary took the last sentence too. The narrator had also been shown the
injury summary as text (prompts._mechanics_view: "injury": "Unskilled with Melee: you injure your own hand.").

The fix, by class (mechanics never reach the player as rule sentences):
* the refused-death beat is the fact alone; the attack's own result, hurt included, is the engine's
  attack line (app/attack_line.py: "Your fist goes wide of Peregrine [[H]]; your own hand takes the hurt.");
* the flavor and summary strings stay engine data (ledger, journal, dice chip); the narrator's context
  is not changed (it did not paste them at T42);
* the one gate this class allows (CLAUDE.md: engine text in the prose): strip_rule_text takes a whole
  sentence that is one of the engine's own check sentences (the flavor pools, this turn's check strings,
  the label templates resolve_check builds them from) out of the prose, with a ledger note, and keeps
  the rest;
* the mechanical effect (the roll, the self-injury, health 20 -> 19) is unchanged.

Run:  cd tests && ../.venv/bin/python -m unittest test_sonnet100_rule_text
"""
from __future__ import annotations

import json
import random
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import attack_line, interpreter, skill_checks, world  # noqa: E402

I = interpreter
L = attack_line

T42_LINE = "I stab at Peregrine again and shove him back from the grave, shouting at him to keep away from me."

# The draft as the interpreter read it (after the engine's code repair), verbatim.
T42_DRAFT = (
    "You stab at Peregrine [[H]] again and he recoils from your strike, stumbling back from the grave. "
    "\"Stay away from me, you dead dog!\" you shout at him, shoving him back with another push. "
    "Peregrine [[H]] trips and falls, his hands scrabbling at the ground for purchase. He looks up at you, fear in his eyes."
)

# What the player read, verbatim (turns/042.json "narration").
T42_SHIPPED = (
    "You stab at Peregrine [[H]] again and he recoils from your strike, stumbling back from the grave. "
    "Your fist goes wide of Peregrine [[H]]. \"Stay away from me, you dead dog!\" you shout at him, shoving him back "
    "with another push. Peregrine [[H]] trips and falls, his hands scrabbling at the ground for purchase. He looks up "
    "at you, fear in his eyes. Peregrine [[H]] is still alive. Without training, the weapon/tool does as much harm "
    "to you as to the world. You are unskilled at wielding this — you end up taking your own hand into the mess. "
    "Unskilled with Melee: you injure your own hand."
)
T42_RULE_TEXT = (
    "Without training, the weapon/tool does as much harm to you as to the world.",
    "You are unskilled at wielding this — you end up taking your own hand into the mess.",
    "Unskilled with Melee: you injure your own hand.",
)

# The check as resolved (final_turn.skill_checks[0]), the fields the fix reads, values verbatim.
T42_CHECK = {
    "enabled": True,
    "skill": {"code": "melee", "name": "Melee", "category": "combat", "attribute": "strength"},
    "dice": "d20", "natural": 3, "base": 10, "modifier": 0, "total": 3, "dc": 14, "dc_source": "contested",
    "skill_match": "untrained", "skill_source": "", "unskilled": True,
    "opposition": {"name": "Peregrine", "attribute": "strength", "stat_score": 10, "rank": "F", "power_total": 10},
    "outcome": "failure", "degree": "unskilled_mishap", "margin": -11, "mishap": True,
    "injury": {"kind": "self_injury", "limb": "hand", "severity": False, "lasting": False, "health_delta": -1,
               "summary": "Unskilled with Melee: you injure your own hand.", "combat_penalty": {}},
    "blunder": None, "crit": False, "fumble": False,
    "flavor": " ".join(T42_RULE_TEXT), "guidance": " ".join(T42_RULE_TEXT),
    "weapon_or_tool": "",
    "attack": {"code": "H", "name": "Peregrine"},
    "for": T42_LINE,
}

# The combat block of the turn (final_turn._deterministic_combat): resolved on H before the draft, a miss.
T42_COMBAT = {
    "status": "resolved_player_attack", "action_kind": "player_attack",
    "player_attack": {"weapon": "unarmed", "weapon_code": "", "equipment": {}, "strength": 7, "defense": 4, "dodge": 4,
                      "attack_min": 2, "attack_max": 4},
    "target": {"code": "H", "name": "Peregrine", "rank": "F", "attitude": "neutral",
               "combat_profile": {"initialized": True, "health": 18, "max_health": 21, "attack_min": 2, "attack_max": 6,
                                  "defense": 3, "dodge": 3}},
    "resolution": {"outcome": "miss", "damage": 0, "target_health_before": 18, "target_health_after": 18},
}

PEREGRINE = {"code": "H", "name": "Peregrine", "died_turn": 0, "location_id": 6, "role": "orchard keeper",
             "health": 18, "max_health": 21, "defense": 3, "dodge": 3}


def _records() -> dict:
    return {
        "people": [PEREGRINE],
        "places": [{"code": "L1", "name": "Saltmarrow", "destroyed_turn": 0},
                   {"code": "L6", "name": "The Ruined Church", "destroyed_turn": 0}],
        "player_names": ["Isk Tarrow", "Isk"],
        "here_id": 6,
        "player_line": T42_LINE,
        "player_quotes": ["Stay away from me, you dead dog!"],
    }


class T42Model:
    """The model's answers at T42, from the trace: yes he is dead, no he is not alive, no sentence says so."""

    def __init__(self):
        self.calls: list[str] = []

    def __call__(self, phase: str, prompt: str, max_tokens: int) -> str:
        self.calls.append(phase)
        if phase == I.PHASE_DIED_CHECK:
            return "No, Peregrine is not alive"
        if phase == I.PHASE_REFUSED_DEATH:
            return "No. The sentence does not say that"
        if phase == I.PHASE_DIED:
            return "Yes, Peregrine is dead at"
        return "No"


def _rule_text_in(text: str) -> list[str]:
    marks = ("Unskilled with", "weapon/tool", "unskilled at wielding", "into the mess", "Without training")
    return [m for m in marks if m in text]


class TheRefusedDeathBeatIsTheFactAlone(unittest.TestCase):
    """T42 replayed through the interpreter with its recorded answers and check."""

    def run_t42(self) -> dict:
        turn = {"skill_checks": [T42_CHECK], "_deterministic_combat": T42_COMBAT}
        return I.run(T42_DRAFT, _records(), T42Model(), turn)

    def test_the_death_is_refused_and_the_beat_carries_no_rule_text(self):
        out = self.run_t42()
        event = out["events"][0]
        self.assertEqual((event["kind"], event["status"], event["reason"]), ("died", "refused", "attack roll failure"))
        refused = out["report"]["refused_deaths"][0]
        self.assertEqual(refused["beat"], "Peregrine [[H]] is still alive.")
        self.assertEqual(refused["action"], "beat_added")
        text = out["narration"]
        self.assertIn("Peregrine [[H]] is still alive.", text)
        self.assertEqual(_rule_text_in(text), [], text)
        # Nothing of the draft was cut.
        for piece in ("You stab at Peregrine [[H]] again", "Stay away from me, you dead dog!", "fear in his eyes."):
            self.assertIn(piece, text)

    def test_the_attack_line_shows_the_miss_and_the_hurt(self):
        out = self.run_t42()
        beats = out["report"]["attack_beats"]
        self.assertEqual(len(beats), 1)
        beat = beats[0]["beat"]
        self.assertEqual(beat, L.line_for(T42_CHECK, "Peregrine [[H]]"))
        self.assertEqual(L.outcome_of(beat), L.MISS)
        self.assertIn("your own hand", beat)
        self.assertIn(beat, out["narration"])
        # The line goes in where the attack is, not at the end after the beat.
        self.assertLess(out["narration"].index(beat), out["narration"].index("is still alive"))

    def test_the_summary_carries_the_line_and_no_rule_text(self):
        out = self.run_t42()
        built = I.summary(out["events"], out["narration"], player_quotes=["Stay away from me, you dead dog!"],
                          attack_beats=out["report"]["attack_beats"])
        self.assertEqual(_rule_text_in(built), [], built)
        self.assertIn(out["report"]["attack_beats"][0]["beat"], built)
        self.assertNotIn("died", built)

    def test_outcome_beat_never_appends_the_flavor(self):
        self.assertEqual(I.outcome_beat(PEREGRINE, T42_CHECK), "Peregrine [[H]] is still alive.")
        partial = {**T42_CHECK, "outcome": "partial", "flavor": "You get something, but not everything you wanted."}
        self.assertEqual(I.outcome_beat(PEREGRINE, partial), "Peregrine [[H]] is hurt, but still alive.")


class TheAttackLineCarriesTheMishap(unittest.TestCase):
    def test_t42_bare_handed_the_hurt_is_the_lines_second_clause(self):
        line = L.line_for(T42_CHECK, "Peregrine [[H]]")
        first, second = line.split("; ", 1)
        self.assertEqual(L.outcome_of(first + "."), L.MISS)
        self.assertIn(second, {"your own hand takes the hurt.", "you jar your own hand."})
        self.assertEqual(_rule_text_in(line), [])

    def test_with_a_weapon_the_weapon_bites(self):
        check = {**T42_CHECK, "weapon_or_tool": "knife"}
        line = L.line_for(check, "Peregrine [[H]]", "knife")
        self.assertRegex(line, r"; the knife (?:turns in your grip and bites|comes back on) your own hand\.$")
        ranged = {**T42_CHECK, "skill": {"code": "ranged", "name": "Ranged", "category": "combat"}}
        line = L.line_for(ranged, "Peregrine [[H]]", "bow")
        self.assertRegex(line, r"^Your shot|^The shot from your bow")
        self.assertRegex(line, r"; the bow (?:kicks back into|bucks and jars) your own hand\.$")

    def test_no_applied_injury_no_clause(self):
        dropped = {**T42_CHECK, "injury": None, "injury_unshown": T42_CHECK["injury"]}
        line = L.line_for(dropped, "Peregrine [[H]]")
        self.assertNotIn(";", line)
        self.assertEqual(L.mishap_clause(dropped), "")
        clean = {**T42_CHECK, "injury": None, "mishap": False, "degree": "failure"}
        self.assertNotIn(";", L.line_for(clean, "Peregrine [[H]]"))

    def test_the_engines_own_line_reads_as_shown(self):
        records = _records()
        match = I.Matcher(records["people"], records["places"])
        line = L.line_for(T42_CHECK, "Peregrine [[H]]")
        seen = L.read(f"{T42_DRAFT} {line}", PEREGRINE, L.MISS, match, records, 1, "")
        self.assertEqual(seen["state"], "shown", seen)

    def test_the_same_roll_reads_the_same(self):
        self.assertEqual(L.line_for(T42_CHECK, "Peregrine [[H]]"), L.line_for(dict(T42_CHECK), "Peregrine [[H]]"))


class TheMechanicalEffectIsUnchanged(unittest.TestCase):
    """Only where the words go changed: the roll, the self-injury and the HP change are as before."""

    def test_resolve_check_builds_the_same_strings_and_the_same_hurt(self):
        # Seed 1: an untrained melee 5 vs DC 14, unskilled mishap, a -1 self-injury (no fumble).
        check = skill_checks.resolve_check(skill_code="melee", dc=14, player_stats={"strength": 10},
                                           player_skills=[], rng=random.Random(1))
        self.assertEqual(check["degree"], "unskilled_mishap")
        injury = check["injury"]
        self.assertEqual((injury["kind"], injury["limb"], injury["health_delta"], injury["lasting"]),
                         ("self_injury", "eye", -1, False))
        self.assertEqual(injury["summary"], "Unskilled with Melee: you injure your own eye.")
        self.assertTrue(check["flavor"].endswith(
            "You are unskilled at wielding this — you end up taking your own eye into the mess. "
            "Unskilled with Melee: you injure your own eye."))
        # The dice chip (display_block) and the journal still carry the engine's words.
        self.assertIn("Unskilled with Melee: you injure your own eye.", check["display_block"])

    def test_t42_the_hurt_is_still_applied_minus_one(self):
        # The injury is judged on the draft before the interpreter runs (play_turn), so the
        # outcome beat losing its flavor changes nothing here: health 20 -> 19 as recorded.
        kept = world.drop_unshown_check_injuries([T42_CHECK], T42_DRAFT)
        self.assertEqual(kept[0]["injury"], T42_CHECK["injury"])
        turn = skill_checks.apply_check_to_turn({}, kept[0])
        self.assertEqual(turn["player"]["health_delta"], -1)

    def test_a_social_blunder_label_is_unchanged(self):
        self.assertEqual(skill_checks._BOTCHED_LABEL.format(skill="Persuasion", how="the words come out wrong."),
                         "Botched Persuasion: the words come out wrong.")


class TheGateOnEngineText(unittest.TestCase):
    def test_t42_the_three_rule_sentences_go_and_the_rest_stays(self):
        cleaned, taken = skill_checks.strip_rule_text(T42_SHIPPED, [T42_CHECK])
        self.assertEqual(taken, list(T42_RULE_TEXT))
        expected = T42_SHIPPED
        for sentence in T42_RULE_TEXT:
            expected = expected.replace(" " + sentence, "")
        self.assertEqual(cleaned, expected)
        self.assertTrue(cleaned.endswith("He looks up at you, fear in his eyes. Peregrine [[H]] is still alive."))
        self.assertIn("Your fist goes wide of Peregrine [[H]].", cleaned)

    def test_near_copies_of_the_labels_go(self):
        prose = ("You swing and the blade turns. Unskilled with the blade: you injure your own arm. "
                 "Botched Persuasion: you say the one thing they did not want to hear. He frowns.")
        cleaned, taken = skill_checks.strip_rule_text(prose, [])
        self.assertEqual(cleaned, "You swing and the blade turns. He frowns.")
        self.assertEqual(len(taken), 2)

    def test_a_flavor_line_pasted_whole_goes_even_split_in_two(self):
        prose = "You lunge at the lock. You fail. The moment offers nothing useful. The hall stays quiet."
        cleaned, taken = skill_checks.strip_rule_text(prose, [])
        self.assertEqual(cleaned, "You lunge at the lock. The hall stays quiet.")
        self.assertEqual(taken, ["You fail.", "The moment offers nothing useful."])

    def test_speech_about_skill_is_not_engine_text(self):
        prose = ("\"You're unskilled with that blade, boy,\" Peregrine [[H]] spits. You fail to answer him. "
                 "Without training you would never have found the door.")
        cleaned, taken = skill_checks.strip_rule_text(prose, [T42_CHECK])
        self.assertEqual(taken, [])
        self.assertEqual(cleaned, prose)

    def test_nothing_left_keeps_the_prose(self):
        prose = " ".join(T42_RULE_TEXT)
        cleaned, taken = skill_checks.strip_rule_text(prose, [T42_CHECK])
        self.assertEqual((cleaned, taken), (prose, []))

    def test_the_turn_is_cleaned_in_both_places_with_a_ledger_note(self):
        result = {"narration": T42_SHIPPED, "narration_segments": [{"label": "paragraph", "text": T42_SHIPPED}],
                  "skill_checks": [T42_CHECK]}
        with mock.patch.object(world.turn_ledger, "note") as note:
            taken = world.strip_rule_text_from_result(result)
        self.assertEqual(taken, list(T42_RULE_TEXT))
        self.assertEqual(_rule_text_in(result["narration"]), [])
        self.assertEqual(_rule_text_in(json.dumps(result["narration_segments"])), [])
        self.assertTrue(result["narration"].endswith("Peregrine [[H]] is still alive."))
        self.assertEqual(note.call_args.args[:2], ("check", "rule_text_stripped"))
        self.assertEqual(note.call_args.kwargs["count"], 3)
        # The engine's data is untouched: the check keeps its flavor and summary for the ledger, audit and UI.
        self.assertEqual(result["skill_checks"][0]["flavor"], " ".join(T42_RULE_TEXT))

    def test_a_clean_turn_is_left_alone(self):
        result = {"narration": T42_DRAFT, "skill_checks": [T42_CHECK]}
        with mock.patch.object(world.turn_ledger, "note") as note:
            self.assertEqual(world.strip_rule_text_from_result(result), [])
        self.assertEqual(result["narration"], T42_DRAFT)
        note.assert_not_called()

    def test_apply_turn_runs_the_gate_before_the_summary_and_the_interpreter(self):
        source = (ROOT / "app" / "world.py").read_text(encoding="utf-8")
        gate = source.index("strip_rule_text_from_result(result)\n", source.index("def apply_turn("))
        self.assertLess(gate, source.index("_run_interpreter(", gate))
        self.assertLess(gate, source.index("_write_turn_summary(conn", gate))


if __name__ == "__main__":
    unittest.main()
