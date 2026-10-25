"""stage2 (Hermes 3 8B, Sonnet as the player, 2026-10-25): the attack machinery landed a blow on the wrong one, or rolled one the player never made.

The recorded turns (run folder stage2, traces turn-472167e5-0000NN-player.json, NN = T + 1):

- T10: the prose showed the boar rooting ("the boar doesn't budge", "eyeing the boar warily"), never attacking,
  so no row was filed for it. Wat Thatcher the snare setter [[E]] was filed at the player's place.
- T11: "I ignore them and stab at the boar with my knife, aiming for its throat." melee 1d20=13, partial. The
  trigger tables aimed the roll at Wat (the one person in the pool; the scene record was empty, so
  attack_intent.decide had people []). line_may_target kept him: "boar" was no evidence (a noun the engine
  had no row or creature word for) and the "them" of "I ignore them", in another clause, read as a person
  pronoun meaning someone here. The fight block (built on Wat by the intent reader) took 2 damage off him.
  After the draft Boar 1 [[F]] was filed, the reader retargeted the roll E -> F, but F had no health and the
  fight was on E: attack_unresolved_no_line, no engine line, Wat kept the 2 damage.
- T14: "I say we cannot wait for tomorrow: I lead Maelis and Reinald out the gate into the marsh now to find
  the beast." No blow. The attack ask about the boar replied "Yes, the player is leading Mael" and the
  peaceful ask "No, the player does not seem to": a confirmed attack, melee success 17, and the engine wrote
  "Your blow hits the boar [[F]]." into the prose: the engine acted for the player.
- T15: "I stab at the boar with my knife as it charges, going for its eye, while Maelis and Reinald stand
  beside me." Aimed at F by the trigger, partial, "Your blow only grazes the boar [[F]]." Must keep working.

The prose, lines, rows and replies below are the run's own, verbatim.
"""
from __future__ import annotations

import copy
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-stage2-attack-"))
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


# --- the run's own words -----------------------------------------------------

T10_PROSE = (
    "The reeds grow thicker around you, the clawed prints still leading the path. You keep your distance, not wanting "
    "to get any closer to the beast, but needing to find it. Reinald [[C]] stays close behind you, his axe at the "
    "ready.\n\nYou push through the curtain of stalks, the air heavy with the salt tang of the marsh. The ground "
    "beneath your feet is spongy and wet, each step a sucking squelch. The prints lead you deeper into the heart of "
    "Saltmarrow.\n\nThe reeds thin out ahead and you spot a dark shape huddled in the shadows. It's large, with "
    "matted fur and a humped back. It's the beast you've been tracking.\n\nThe creature doesn't move as you "
    "approach, its head bowed low to the ground. The beast isn't attacking, but instead seems to be... digging.\n\n"
    "You see it now - the beast is burrowing into the soft earth. It's not a monster, but a creature of the marsh. "
    "A saltmarrow boar, rooting for food. You let out a breath you didn't know you were holding.\n\n\"Easy now,\" "
    "you say to Reinald [[C]].\n\nThe reeve nods, but keeps his axe out, ready. You've both been spooked by the "
    "unknown, but now see it for what it is. A normal saltmarrow boar, no different from those in the marshes.\n\n"
    "You wave your hands to scare it off, but the boar doesn't budge. It keeps rooting, its snout disappearing into "
    "the earth. You approach it cautiously, not wanting to get any closer than needed.\n\n\"Leave it be,\" Reinald "
    "[[C]] says. \"It's just looking for grubs and roots. No need to chase it down.\"\n\nYou agree and turn to leave "
    "the beast to its meal. The reeds part ahead and you spot a figure standing watch. It's a snare setter, Wat "
    "Thatcher, who's been tracking the boar.\n\nHe nods to you in recognition. \"Thought I heard something,\" he "
    "says, eyeing the boar warily. \"Best leave it to its meal. It won't harm you.\"\n\nYou and Reinald [[C]] "
    "exchange looks. The beast is just a normal boar, no threat. No need to chase it further."
)
T11_LINE = "I ignore them and stab at the boar with my knife, aiming for its throat."
T11_PROSE = (
    "Blood sprays and the beast turns, lashing out with its tusks. You dodge under its chin, stabbing again - this "
    "time grazing the thick corded throat. The boar bellows in pain and charges, trying to trample you underfoot. "
    "You leap away and it crashes past, snorting and bellowing. It wheels around and charges again, the shallow "
    "wounds on its neck now oozing blood. The crowd cheers as you circle warily, waiting for an opening to strike "
    "again.\nYou spot a chance and lunge, aiming for the vulnerable throat once more. It staggers and collapses, "
    "thrashing. With one final geyser of blood it goes still and lies dead on the ground.\nYou stand over the fallen "
    "beast. The crowd roars in approval and you feel a surge of pride. You have bested a dangerous quarry and earned "
    "the respect of these hard-bitten folk. Now, what's next?\nYou survey the crowd of onlookers, your eye catching "
    "on a grizzled old huntswoman. She approaches you, her weathered face impassive but her eyes keen. \"Well "
    "fought,\" she says gruffly. \"I'm Maelis. You've got some potential. Think you're ready for a real hunt?\""
)
T14_LINE = ("I say we cannot wait for tomorrow: I lead Maelis and Reinald out the gate into the marsh now to find "
            "the beast.")
T15_LINE = ("I stab at the boar with my knife as it charges, going for its eye, while Maelis and Reinald stand "
            "beside me.")
T14_PROSE = (
    "You stand at the gate of Saltmarrow [[L1]], Maelis [[G]] and Reinald [[C]] beside you. The marsh spreads out "
    "before you, pale in the morning light. \"We dare not wait for dawn to come,\" you tell them.\n\nMaelis [[G]] "
    "follows close, her bow at the ready. Reinald [[C]] lags behind, her hands thrust deep in her cloak.\n\nThe marsh "
    "is still and silent. A light mist curls about your feet as you wade through the tall grass. Your boots sink "
    "with each step, the cold mud dragging at your feet.\n\nSuddenly, an earsplitting squeal pierces the air. Ahead, "
    "a large boar bursts from the reeds, charging directly at you!\n\n\"Look out!\" shouts Maelis [[G]], nocking an "
    "arrow to her bow.\n\nYou dodge to the side. The boar skids to a halt, snorting and pawing at the marsh floor. "
    "Its tiny piggy mind seems to be struggling to process your sudden appearance.\n\n\"Attack it!\" Maelis [[G]] "
    "commands, aiming her arrow at the boar's head.\n\nYou charge forward. The boar lets out a furious squeal and "
    "charges to meet you!"
)  # T14's draft as recorded, without the engine's inserted "Your blow hits the boar [[F]]."
# The T14 attack ask replies, as recorded (attack_ask, attack_ask_check, code F).
T14_ATTACK_REPLY = "Yes, the player is leading Mael"
T14_CHECK_REPLY = "No, the player does not seem to"

# The rows (prompt_context.locations[0].npcs of the traces).
WAT = {"id": 5, "code": "E", "name": "Wat Thatcher", "role": "snare setter", "kind": "", "kind_number": 0,
       "location_id": 1, "attitude": "cautious", "sex": None, "health": 21, "max_health": 21, "attack_min": 2,
       "attack_max": 6, "defense": 3, "dodge": 3, "died_turn": 0, "race": "human"}
REINALD = {"id": 3, "code": "C", "name": "Reinald", "role": "farmer", "kind": "", "kind_number": 0, "location_id": 1,
           "attitude": "neutral", "sex": None, "health": 21, "max_health": 21, "attack_min": 2, "attack_max": 6,
           "defense": 3, "dodge": 3, "died_turn": 0, "race": "human"}
BOAR = {"id": 6, "code": "F", "name": "Boar 1", "role": "boar", "kind": "Boar", "kind_number": 1, "location_id": 1,
        "attitude": "hostile", "sex": None, "health": 21, "max_health": 21, "attack_min": 2, "attack_max": 6,
        "defense": 3, "dodge": 3, "died_turn": 0, "race": "unknown"}
MAELIS = {"id": 7, "code": "G", "name": "Maelis", "role": "huntswoman", "kind": "", "kind_number": 0, "location_id": 1,
          "attitude": "neutral", "sex": None, "health": 21, "max_health": 21, "attack_min": 2, "attack_max": 6,
          "defense": 3, "dodge": 3, "died_turn": 0, "race": "human"}

# T11's resolved melee check (final_turn.skill_checks[0]) and fight block (final_turn._deterministic_combat).
T11_CHECK = {
    "enabled": True, "skill": {"code": "melee", "name": "Melee", "category": "combat", "attribute": "strength"},
    "dice": "d20", "natural": 13, "total": 13, "dc": 15, "outcome": "partial", "degree": "partial",
    "weapon_or_tool": "", "attack": {"code": "E", "name": "Wat Thatcher"},
    "opposition": {"name": "Wat Thatcher", "attribute": "strength", "stat_score": 10, "rank": "F"},
    "injury": None, "mishap": False,
}
T11_COMBAT = {
    "status": "resolved_player_attack", "action_kind": "player_attack",
    "player_attack": {"weapon": "unarmed", "weapon_code": "", "equipment": {}, "strength": 7, "defense": 4, "dodge": 4,
                      "attack_min": 2, "attack_max": 4},
    "target_candidates": [{"code": "E", "name": "Wat Thatcher", "rank": "F", "attitude": "cautious",
                           "combat_profile": {"initialized": True, "health": 21, "max_health": 21, "attack_min": 2,
                                              "attack_max": 6, "defense": 3, "dodge": 3}}],
    "target": {"code": "E", "name": "Wat Thatcher", "rank": "F", "attitude": "cautious",
               "combat_profile": {"initialized": True, "health": 21, "max_health": 21, "attack_min": 2,
                                  "attack_max": 6, "defense": 3, "dodge": 3}},
    "resolution": {"outcome": "glancing_hit", "attack_roll": 9, "attack_total": 11, "evasion_target": 11,
                   "raw_damage_roll": 4, "damage": 2, "target_health_before": 21, "target_health_after": 19,
                   "target_defeated": False, "decided_by": "attack_check", "combat_roll_outcome": "hit"},
}


def _context(rows: list[dict], present: list[str] | None, names: dict, prior: str) -> dict:
    place = {"id": 1, "code": "L1", "name": "Saltmarrow", "npcs": [copy.deepcopy(r) for r in rows]}
    return {
        "current_location": {"id": 1, "code": "L1", "name": "Saltmarrow"},
        "locations": [place],
        "conversation_turn": {"addressed": [], "present": present, "listening": [], "names": names},
        "last_narration": prior,
        "dead": [],
    }


def _t11_inferred() -> dict:
    """infer_check_from_action's melee for the T11 line on the recorded context: aimed at Wat, the one person in the pool."""
    return {"skill_code": "melee", "social": False, "opposition": {"name": "Wat Thatcher"},
            "npc_ref": {"code": "E", "name": "Wat Thatcher", "attitude": "cautious", "role": None}}


class Notes:
    def __init__(self):
        self.rows: list[dict] = []

    def __call__(self, area, decision, **detail):
        self.rows.append({"area": area, "decision": decision, **detail})

    def named(self, decision: str) -> list[dict]:
        return [r for r in self.rows if r["decision"] == decision]


def _no_ask(phase, prompt, max_tokens):
    raise AssertionError(f"no attack ask is needed: {phase} {prompt[:80]}")


# --- T11: "stab at the boar" hits neither man --------------------------------


class T11TheBoarIsNoOneHere(unittest.TestCase):

    def test_the_recorded_trigger_roll_is_cleared_of_wat(self):
        from app import attack_intent as A

        ctx = _context([WAT], [], {"E": "Wat Thatcher"}, T10_PROSE)
        inferred = _t11_inferred()
        check, report = A.decide(T11_LINE, ctx, inferred, _no_ask)
        self.assertIsNone(check)
        self.assertIsNone(report["target"])
        self.assertEqual(report["not_the_lines"]["code"], "E")
        self.assertEqual(report["unknown_noun"], "boar")
        self.assertIsNone(inferred.get("npc_ref"))
        self.assertNotIn("attack", inferred)
        self.assertEqual(inferred["not_at"], ["E"])

    def test_with_reinald_and_wat_both_here_neither_is_hit(self):
        from app import attack_intent as A

        for present in ([], ["C", "E"]):
            for ref in ("E", "C"):
                person = WAT if ref == "E" else REINALD
                ctx = _context([WAT, REINALD], present, {"E": "Wat Thatcher", "C": "Reinald"}, T10_PROSE)
                inferred = {"skill_code": "melee", "social": False,
                            "npc_ref": {"code": ref, "name": person["name"], "role": person["role"]}}
                check, report = A.decide(T11_LINE, ctx, inferred, _no_ask)
                self.assertIsNone(check, (present, ref))
                self.assertIsNone(report["target"], (present, ref))
                self.assertEqual(report["unknown_noun"], "boar")

    def test_the_boar_is_the_prose_s_thing_and_no_word_for_either_man(self):
        from app import attack_intent as A

        for person in (WAT, REINALD):
            self.assertTrue(A.prose_thing_not(person, "boar", T10_PROSE))
            self.assertFalse(A.line_may_target(T11_LINE, person, people=[WAT, REINALD], prose=T10_PROSE))
        # A noun the prose never used, or a person word, stays no evidence (4833150).
        self.assertFalse(A.prose_thing_not(WAT, "bastard", T10_PROSE))
        self.assertFalse(A.prose_thing_not(WAT, "figure", T10_PROSE))
        self.assertFalse(A.prose_thing_not(WAT, "reeve", T10_PROSE + " The guard nods."))
        self.assertTrue(A.line_may_target("i stab the bastard", WAT, people=[WAT], prose=T10_PROSE))
        # The prose calling him by it is a word for him.
        self.assertFalse(A.prose_thing_not(WAT, "trapper", "The trapper Wat Thatcher nods."))
        self.assertFalse(A.prose_thing_not(WAT, "trapper", "Wat [[E]], the trapper, nods."))

    def test_the_fight_built_on_wat_does_not_stand(self):
        from app import world

        check = {**copy.deepcopy(T11_CHECK), "attack": None, "opposition": None, "not_at": ["E"]}
        check.pop("attack")
        notes = Notes()
        with mock.patch("app.turn_ledger.note", notes):
            cleared = world._combat_off_cleared_target(copy.deepcopy(T11_COMBAT), [check])
            self.assertIsNotNone(cleared)
            self.assertEqual(cleared["status"], "needs_target")
            self.assertNotIn("resolution", cleared)
            self.assertEqual(cleared["player_attack"], T11_COMBAT["player_attack"])
            self.assertEqual(notes.named("combat_target_cleared")[0]["code"], "E")
            # Nothing to aim the fight at before the draft: no block is built on anyone.
            self.assertIsNone(world._combat_for_aimed_check({}, T11_LINE, cleared, [check]))
            # The recorded roll, aimed at Wat, keeps its fight (the clearing is the reader's, not a guess).
            self.assertIsNone(world._combat_off_cleared_target(copy.deepcopy(T11_COMBAT), [copy.deepcopy(T11_CHECK)]))


class T11TheResultLandsOnBoar1(unittest.TestCase):

    def _show(self, check: dict, combat: dict):
        from app import interpreter as I

        people = [copy.deepcopy(WAT), copy.deepcopy(REINALD), copy.deepcopy(BOAR)]
        records = {"people": people, "places": [], "player_names": ["Isk"], "here_id": 1, "player_line": T11_LINE,
                   "player_quotes": [], "shown_kinds": ["boar"], "prose_before": T10_PROSE}
        report: dict = {}
        notes = Notes()
        with mock.patch("app.turn_ledger.note", notes):
            out = I.show_attacks(T11_PROSE, {"skill_checks": [check], "_deterministic_combat": combat},
                                 I.Matcher(people, []), report, records)
        return out, report, notes

    def _assert_graze_on_boar(self, out: str, report: dict):
        after = report["combat_after_draft"]
        self.assertEqual(after["target"]["code"], "F")
        self.assertEqual(after["resolution"]["outcome"], "glancing_hit")
        beat = report["attack_beats"][0]
        self.assertEqual(beat["code"], "F")
        self.assertIn("grazes the boar [[F]]", beat["beat"])
        self.assertIn(beat["beat"], out)
        # The first telling of the fight is kept; no draft sentence is dropped.
        for sentence in ("Blood sprays and the beast turns, lashing out with its tusks.",
                         "It staggers and collapses, thrashing.",
                         "With one final geyser of blood it goes still and lies dead on the ground."):
            self.assertIn(sentence, out)

    def test_the_cleared_roll_is_resolved_on_the_boar_the_scene_filed(self):
        check = {k: v for k, v in copy.deepcopy(T11_CHECK).items() if k != "attack"}
        check.update({"opposition": None, "not_at": ["E"]})
        combat = {**{k: v for k, v in copy.deepcopy(T11_COMBAT).items() if k not in {"target", "resolution"}},
                  "status": "needs_target", "cleared_target": "E"}
        out, report, _notes = self._show(check, combat)
        self._assert_graze_on_boar(out, report)
        self.assertNotIn("moved_from", report["combat_after_draft"])

    def test_the_run_as_it_was_moves_the_result_off_wat(self):
        # The recorded roll on E and the fight applied to E: the reader retargets to F and the result moves.
        out, report, notes = self._show(copy.deepcopy(T11_CHECK), copy.deepcopy(T11_COMBAT))
        self.assertEqual(notes.named("attack_retargeted")[0]["now"], "F")
        self.assertFalse(notes.named("attack_unresolved_no_line"))
        self._assert_graze_on_boar(out, report)
        self.assertEqual(report["combat_after_draft"]["moved_from"], "E")
        self.assertEqual(notes.named("attack_result_moved")[0]["was"], "E")

    def test_wat_gets_his_health_back_and_the_boar_takes_the_blow(self):
        from app import db, world

        db.init_db()
        with db.connect().closing() as conn:
            for row in (WAT, BOAR):
                conn.execute("DELETE FROM npcs WHERE code = ?", (row["code"],))
                conn.execute(
                    "INSERT INTO npcs (code, location_id, name, role, kind, kind_number, health, max_health, attack_min,"
                    " attack_max, defense, dodge) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (row["code"], 1, row["name"], row["role"], row["kind"], row["kind_number"], row["health"],
                     row["max_health"], row["attack_min"], row["attack_max"], row["defense"], row["dodge"]),
                )
            conn.commit()
            combat = copy.deepcopy(T11_COMBAT)
            notes = Notes()
            with mock.patch("app.turn_ledger.note", notes), mock.patch("app.party.party_combat_bonus", return_value=0):
                world._apply_deterministic_combat(conn, combat, 11)
                self.assertEqual(conn.execute("SELECT health FROM npcs WHERE code = 'E'").fetchone()[0], 19)
                after = {**dict(combat), "status": "resolved_player_attack", "moved_from": "E",
                         "target": {"code": "F", "name": "Boar 1"},
                         "resolution": {"outcome": "glancing_hit", "damage": 1}, "resolved_after_draft": True}
                world._undo_applied_combat(conn, after, 11)
                world._apply_deterministic_combat(conn, after, 11)
            self.assertEqual(conn.execute("SELECT health FROM npcs WHERE code = 'E'").fetchone()[0], 21)
            self.assertEqual(conn.execute("SELECT health FROM npcs WHERE code = 'F'").fetchone()[0], 20)
            self.assertEqual(notes.named("attack_damage_undone")[0]["damage"], 2)
            # The standing the blow cost him is put back (he had none on record before it).
            rel = conn.execute("SELECT COUNT(*) FROM npc_player_relationships WHERE npc_id = "
                               "(SELECT id FROM npcs WHERE code = 'E')").fetchone()[0]
            self.assertEqual(rel, 0)


# --- T14: no blow in the line, no roll ---------------------------------------


class T14LeadingThemOutIsNoAttack(unittest.TestCase):

    def _ctx(self) -> dict:
        return _context([BOAR, MAELIS, WAT, REINALD], ["F", "C", "G"],
                        {"E": "Wat Thatcher", "F": "Boar 1", "G": "Maelis", "C": "Reinald"}, "")

    def test_the_recorded_replies_roll_no_attack(self):
        from app import attack_intent as A

        asked: list[str] = []

        def ask(phase, prompt, max_tokens):
            asked.append(prompt)
            if "the boar" in prompt.lower():
                return T14_ATTACK_REPLY if phase == A.PHASE_ATTACK else T14_CHECK_REPLY
            return "No"

        check, report = A.decide(T14_LINE, self._ctx(), None, ask)
        self.assertIsNone(check)
        self.assertIsNone(report["target"])
        self.assertEqual(report["aim_only"], ["F"])
        self.assertFalse(any("the boar" in p.lower() for p in asked))

    def test_the_line_s_aim_is_no_act(self):
        from app import attack_intent as A

        here = [BOAR, MAELIS, REINALD]
        self.assertTrue(A.aim_only(T14_LINE, BOAR, here))
        self.assertFalse(A.aim_only(T14_LINE, MAELIS, here))
        # A blow in the line's own act, or a blow as its aim, is unchanged.
        self.assertFalse(A.aim_only(T15_LINE, BOAR, here))
        self.assertFalse(A.aim_only("I run at the boar to stab it", BOAR, here))
        self.assertFalse(A.aim_only("i slit his throat", WAT, [WAT]))

    def test_a_yes_about_someone_else_is_no_yes(self):
        from app import attack_intent as A

        here = [BOAR, MAELIS, REINALD]
        self.assertEqual(A.reply_about_another(T14_ATTACK_REPLY, BOAR, here), "G")
        self.assertEqual(A.reply_about_another("Yes", BOAR, here), "")
        self.assertEqual(A.reply_about_another("Yes, the player stabs the boar", BOAR, here), "")
        report = {"asks": [], "unconfirmed": []}

        def ask(phase, prompt, max_tokens):
            return T14_ATTACK_REPLY if phase == A.PHASE_ATTACK else T14_CHECK_REPLY

        self.assertIsNone(A.find_target(T14_LINE, [BOAR], ask, report, here))
        self.assertEqual(report["unconfirmed"][0]["why"], "reply_about_another")
        self.assertEqual([a["phase"] for a in report["asks"]], [A.PHASE_ATTACK])

    def test_the_turn_s_attack_reader_notes_the_refusal_and_inserts_no_line(self):
        from app import interpreter as I
        from app import world

        notes = Notes()

        def ask(phase, prompt, max_tokens):
            if "the boar" in prompt.lower():
                return T14_ATTACK_REPLY if "hurt or kill" in prompt else T14_CHECK_REPLY
            return "No"

        with mock.patch("app.turn_ledger.note", notes):
            check = world._attack_check_for_line(T14_LINE, self._ctx(), None, [], [], ask=ask)
        self.assertIsNone(check)
        self.assertEqual(notes.named("attack_ask_aim_only")[0]["codes"], ["F"])
        self.assertFalse(notes.named("attack_found"))
        # No roll, so the reader after the draft has nothing to show: the draft stands as written.
        report: dict = {}
        out = I.show_attacks(T14_PROSE, {"skill_checks": []}, I.Matcher([BOAR, MAELIS, REINALD], []), report,
                             {"player_line": T14_LINE, "here_id": 1})
        self.assertEqual(out, T14_PROSE)
        self.assertNotIn("Your blow", out)


# --- T15: the aimed roll on the boar still works ------------------------------


class T15TheAimedBlowStillLands(unittest.TestCase):

    def test_the_trigger_roll_stays_on_boar_1(self):
        from app import attack_intent as A

        ctx = _context([REINALD, BOAR, MAELIS, WAT], ["F", "C", "G"],
                       {"C": "Reinald", "E": "Wat Thatcher", "F": "Boar 1", "G": "Maelis"}, T14_PROSE)
        inferred = {"skill_code": "melee", "social": False,
                    "npc_ref": {"code": "F", "name": "Boar 1", "attitude": "apprehensive", "role": None}}
        check, report = A.decide(T15_LINE, ctx, inferred, _no_ask)
        self.assertIsNone(check)
        self.assertEqual(report["target"], {"code": "F", "name": "Boar 1"})
        self.assertEqual(report["from"], "trigger")
        self.assertNotIn("not_at", inferred)


if __name__ == "__main__":
    unittest.main()
