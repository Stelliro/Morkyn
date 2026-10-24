"""An attack in any words rolls a check, and the outcome follows the roll (#85, #129).

#85: lines whose outcome the player states rolled nothing, and the stated
outcome stood: cc87dd29 T10 'i rip her in half, this move grants her instant
death', T13 'i rip her head from her shoulders ... killing her instantly',
the baseline replay's T3 (Marisol) and the merged-code replay's T3 (Dr. Theo).
#129: a failed check narrated as success: T5 Ranged 13 vs DC 14 (a partial)
and the prose kills Beth.

The trigger is no verb list (round 1's was rejected): one ask per person the
engine has in the scene, "Does the player try to hurt or kill <Name>?", and a
second, worded the other way, "Is the player peaceful toward <Name>?", which
must answer no (app/attack_intent.py). The model is mocked: a truthful model
answers from what each line really does; a yes-biased and a no-biased model
show that one-sided answers change nothing. The death the roll did not allow
is refused by the interpreter (app/interpreter.allow_event) and the prose is
put back in line with the dice.

Run:  cd tests && python -m unittest test_attack_outcome
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-attack-test-"))
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

from app import attack_intent, db, interpreter, llm, skill_checks, world  # noqa: E402

A = attack_intent
I = interpreter

# --- the real lines (model_input's first paragraph, as the engine has it) ---
T10_LINE = (
    "i walk up to Beth [[B]] and grab her arms with one hand and her legs with the other, and i rip her in half, "
    "this move grants her instant death"
)
T13_LINE = "i rip her head from her shoulders, her spine comes out still connected to her head, killing her instantly"
B3_LINE = (
    "i walk up to Marisol and grab her arms with one hand and her legs with the other, and i rip her in half, "
    "this move grants her instant death"
)
R3_LINE = (
    "i walk up to Dr. Theo and grab his arms with one hand and his legs with the other, and i rip him in half, "
    "this move grants him instant death"
)
T5_LINE = (
    "I BRUTALLY SNAP HER NECK AND THEN PROCEED TO BURN THE CLINIC TO THE GROUND, AND THEN, MAKE SURE THERE ARE NO "
    "SURVIVORS IN THE CLINIC, AND AFTER THAT, I GO THROUGH THE CITY AND MASSACRE EVERYONE, GUNNING THEM ALL DOWN, "
    "LEAVING NO SURVIVORS"
)
T8_LINE = "i shoot a missile at Beth [[B]] blowing her to bits"

# --- the real prose ----------------------------------------------------------
T10 = (
    "You lunge towards Beth [[B]], grabbing her arms with one hand and her legs with the other. With a violent twist, "
    "you attempt to rip her in two, your muscles straining against her flesh.\n\n"
    "Morning light filters in through grimy windows, casting an eerie pallor over the clinic's cold stone floors. The air "
    "is thick with the stench of decay and the sound of your own heavy breathing. Beth [[B]] screams in agony as you "
    "wrench her arms and legs with a savage grip. She thrashes and struggles, trying to break free from your iron hold.\n\n"
    "A sickening tear rips through her flesh as you wrench her body apart. Gore and viscera splatter across the floor in "
    "a grisly display. Her entrails spill out across the hard stone, pooling in a dark crimson puddle as her lifeless "
    "upper body collapses to the ground. You stand over the grisly remains, your arms and torso splattered in Beth "
    "[[B]]'s blood and innards.\n\n"
    "The clinic falls silent, save for the sound of your heart pounding in your ears. The life has been ripped from her, "
    "leaving only a macabre still life behind. Beth [[B]]'s wide, dead eyes stare up at the stained ceiling, her body "
    "split down the middle in an act of savage violence. You stand over her corpse, the fruits of your brutality "
    "staining your hands and chest with her blood and gore."
)
# The sentences of T10 that show her dead (a truthful per-sentence answer).
T10_DEAD = (
    "A sickening tear rips",
    "Her entrails spill out",
    "The life has been ripped",
    "Beth's wide, dead eyes",
    "You stand over the grisly remains",
    "You stand over her corpse",
)
T5 = (
    "You bellow a chilling war cry as you storm into the Radiation Fenced Sanctuary Clinic [[L3]], a grim look of fury "
    "etched upon your armored visor. Smoke billows from the ruins of the Radiation Fenced Sanctuary Clinic [[L3]], now "
    "reduced to smoldering rubble. Beth [[B]] lies crumpled on the scorched floor, her neck twisted at an unnatural angle. "
    "The acrid smell of charred wood and scorched metal fills the night.\n\n"
    "With a twisted smile, you turn your gaze towards the city of Thornford [[L2]], ready to continue your rampage. The "
    "once bustling medical center is now little more than charred rubble, the screams of the dying echoing in your ears. "
    "You methodically search the ruins, checking each room and crevice for any signs of life."
)


def _scene(*people: tuple[str, str], keeper: tuple[str, str] | None = None, addressed=(), listening=(), present=None,
           gear=None) -> dict:
    """A context shaped like get_state's, with the conversation resolution the engine made."""
    npcs = [{"code": c, "name": n, "rank": "F", "stat_profile": {"dexterity": 10}} for c, n in people]
    here = {"code": "L3", "name": "Radiation Fenced Sanctuary Clinic", "npcs": npcs}
    if keeper:
        here["keeper"] = {"code": keeper[0], "name": keeper[1], "role": "doctor"}
    names = {c: n for c, n in [*people, *([keeper] if keeper else [])]}
    conv = {
        "addressed": list(addressed),
        "present": list(present if present is not None else [*addressed, *listening]),
        "listening": list(listening),
        "names": names,
    }
    ctx = {"current_location": here, "locations": [here], "conversation_turn": conv}
    if gear:
        ctx["gear_roll_modifiers"] = {"sources": [{"kind": "item", "code": "I1", "name": gear[0], "profile": gear[1]}]}
    return ctx


_ATTACK_RE = re.compile(r'The player wrote: "(.*)"\n\nDoes the player try to hurt or kill (.+)\? Answer', re.S)
_PEACE_RE = re.compile(r'The player wrote: "(.*)"\n\nIs the player peaceful toward (.+)\? Answer', re.S)


class Truthful:
    """Answers the attack asks from what the line really does: ``attacked`` maps a line to the names it attacks."""

    def __init__(self, attacked: dict[str, set[str]]):
        self.attacked = attacked
        self.calls: list[tuple[str, str]] = []

    def __call__(self, phase: str, prompt: str, max_tokens: int) -> str:
        self.calls.append((phase, prompt))
        found = _ATTACK_RE.search(prompt) or _PEACE_RE.search(prompt)
        line, name = (found.group(1), found.group(2)) if found else ("", "")
        hit = name in self.attacked.get(line, set())
        if phase == A.PHASE_ATTACK:
            return f"Yes, the player tries to kill {name}." if hit else f"No, the player does not try to hurt {name}."
        if phase == A.PHASE_ATTACK_CHECK:
            return "No, the player is not peaceful." if hit else "Yes."
        return ""


def _always(reply: str):
    calls: list = []

    def ask(phase, prompt, max_tokens):
        calls.append((phase, prompt))
        return reply

    ask.calls = calls  # type: ignore[attr-defined]
    return ask


def _plain(line: str) -> str:
    return I.plain(line)


class TestWhyTheseLinesRolledNothing(unittest.TestCase):
    """The cause: the trigger tables have no word for these attacks (and must not grow one)."""

    def test_the_real_lines_find_no_check_in_the_tables(self):
        for line in (T10_LINE, T13_LINE, B3_LINE, R3_LINE):
            self.assertIsNone(skill_checks.infer_check_from_action(line, {}), line)

    def test_the_tables_still_do_not_roll_the_idioms(self):
        for line in ("i cut the guard off mid-sentence", "i hit the guard with a question"):
            self.assertIsNone(skill_checks.infer_check_from_action(line, {}), line)


class TestTheAttackAsk(unittest.TestCase):
    def test_cc87dd29_t10_rip_in_half_rolls_melee_against_beth(self):
        ctx = _scene(keeper=("B", "Beth"), addressed=["B"])
        model = Truthful({_plain(T10_LINE): {"Beth"}})
        check, report = A.decide(T10_LINE, ctx, None, model)
        self.assertEqual(check["skill_code"], "melee")
        self.assertEqual(check["attack"], {"code": "B", "name": "Beth"})
        self.assertEqual(check["opposition"]["name"], "Beth")
        self.assertEqual([p for p, _ in model.calls], [A.PHASE_ATTACK, A.PHASE_ATTACK_CHECK])
        # The ask reads the player's line without the engine's codes.
        self.assertIn('The player wrote: "i walk up to Beth and grab her arms', model.calls[0][1])
        self.assertNotIn("[[", model.calls[0][1])
        self.assertTrue(model.calls[0][1].endswith("Does the player try to hurt or kill Beth? Answer yes or no."))
        self.assertEqual(report["target"], {"code": "B", "name": "Beth"})
        self.assertTrue(all("seconds" in a and "reply" in a for a in report["asks"]))

    def test_cc87dd29_t13_a_pronoun_attack_on_the_one_listening(self):
        ctx = _scene(keeper=("B", "Beth"), listening=["B"])
        check, _report = A.decide(T13_LINE, ctx, None, Truthful({T13_LINE: {"Beth"}}))
        self.assertEqual((check["skill_code"], check["attack"]["code"]), ("melee", "B"))

    def test_baseline_t3_marisol_and_merged_t3_dr_theo(self):
        ctx = _scene(("A", "Marisol"), present=["A"])
        check, _ = A.decide(B3_LINE, ctx, None, Truthful({B3_LINE: {"Marisol"}}))
        self.assertEqual(check["attack"]["code"], "A")
        # Merged-code replay: the duplicate row C "Theo" is in the names but not in the scene.
        ctx = _scene(keeper=("B", "Dr. Theo"), addressed=["B"])
        ctx["conversation_turn"]["names"]["C"] = "Theo"
        model = Truthful({R3_LINE: {"Dr. Theo"}})
        check, _ = A.decide(R3_LINE, ctx, None, model)
        self.assertEqual(check["attack"], {"code": "B", "name": "Dr. Theo"})
        self.assertEqual(len(model.calls), 2)

    def test_cc87dd29_t5_the_neck_snap_aims_the_inferred_ranged_roll_at_beth(self):
        ctx = _scene(keeper=("B", "Beth"), present=[])
        inferred = skill_checks.infer_check_from_action(T5_LINE, ctx)
        self.assertEqual(inferred["skill_code"], "ranged")
        check, _ = A.decide(T5_LINE, ctx, inferred, Truthful({T5_LINE: {"Beth"}}))
        self.assertEqual(check["skill_code"], "ranged")
        self.assertTrue(check["replaces_inferred"])
        self.assertEqual(check["attack"]["code"], "B")

    def test_cc87dd29_t8_the_missile_roll_is_aimed_at_beth(self):
        # The tables find the ranged blow but no person for it in this scene.
        ctx = _scene(("B", "Beth"), addressed=["B"])
        inferred = skill_checks.infer_check_from_action(T8_LINE, ctx)
        self.assertEqual((inferred["skill_code"], inferred["npc_ref"]), ("ranged", None))
        check, _ = A.decide(T8_LINE, ctx, inferred, Truthful({_plain(T8_LINE): {"Beth"}}))
        self.assertEqual((check["skill_code"], check["attack"]["code"]), ("ranged", "B"))
        self.assertTrue(check["replaces_inferred"])

    def test_a_blow_the_tables_aimed_is_not_asked_again(self):
        ctx = _scene(("B", "Beth"), addressed=["B"])
        inferred = {"skill_code": "melee", "opposition": {"name": "Beth"}, "npc_ref": {"code": "B", "name": "Beth"}}
        model = _always("Yes")
        check, report = A.decide("i stab Beth", ctx, inferred, model)
        self.assertIsNone(check)
        self.assertEqual(inferred["attack"], {"code": "B", "name": "Beth"})
        self.assertEqual(model.calls, [])
        self.assertEqual(report["from"], "trigger")

    def test_idioms_are_no_attack(self):
        ctx = _scene(("G", "Brann"), addressed=["G"])
        for line in ("i cut the guard off mid-sentence", "i hit the guard with a question"):
            check, report = A.decide(line, ctx, None, Truthful({}))
            self.assertIsNone(check, line)
            self.assertEqual([a["phase"] for a in report["asks"]], [A.PHASE_ATTACK], line)

    def test_other_phrasings_attack(self):
        ctx = _scene(("G", "Brann"), addressed=["G"])
        for line in ("i slit his throat", "i put a bullet in his head", "i set him on fire", "i strangle Brann until he stops moving"):
            check, _ = A.decide(line, ctx, None, Truthful({line: {"Brann"}}))
            self.assertEqual(check["attack"]["code"], "G", line)
            self.assertEqual(check["skill_code"], "melee", line)

    def test_the_weapon_on_record_sets_ranged(self):
        ctx = _scene(("G", "Brann"), addressed=["G"], gear=("Laser rifle", {"ranged": 1}))
        check, _ = A.decide("i put a bullet in his head", ctx, None, Truthful({"i put a bullet in his head": {"Brann"}}))
        self.assertEqual(check["skill_code"], "ranged")
        ctx = _scene(("G", "Brann"), addressed=["G"], gear=("Power armor", {"defense": 2}))
        check, _ = A.decide("i slit his throat", ctx, None, Truthful({"i slit his throat": {"Brann"}}))
        self.assertEqual(check["skill_code"], "melee")

    def test_a_yes_biased_model_rolls_nothing(self):
        ctx = _scene(("G", "Brann"), keeper=("B", "Beth"), addressed=["G"])
        for line in (T10_LINE, "i hit the guard with a question", "i say hi"):
            model = _always("Yes, the player does.")
            check, report = A.decide(line, ctx, None, model)
            self.assertIsNone(check, line)
            self.assertEqual(len(report["unconfirmed"]), 2)

    def test_a_no_biased_model_rolls_nothing(self):
        ctx = _scene(keeper=("B", "Beth"), addressed=["B"])
        check, report = A.decide(T10_LINE, ctx, None, _always("No."))
        self.assertIsNone(check)
        self.assertEqual(len(report["asks"]), 1)

    def test_the_dead_and_the_absent_are_never_asked_about(self):
        ctx = _scene(("B", "Beth"), ("G", "Brann"), addressed=["G"])
        ctx["locations"][0]["npcs"][0]["died_turn"] = 4
        model = Truthful({})
        A.decide("i hit the guard with a question", ctx, None, model)
        self.assertEqual([re.search(r"kill (.+)\?", p).group(1) for _, p in model.calls], ["Brann"])
        # With a scene record, someone at the place but not in the scene is not asked.
        ctx = _scene(("B", "Beth"), ("G", "Brann"), addressed=["G"])
        model = Truthful({})
        A.decide("i wave", ctx, None, model)
        self.assertEqual(len(model.calls), 1)

    def test_a_failed_ask_never_breaks_the_turn(self):
        def down(phase, prompt, n):
            raise TimeoutError("model down")

        check, report = A.decide(T10_LINE, _scene(keeper=("B", "Beth"), addressed=["B"]), None, down)
        self.assertIsNone(check)
        self.assertIn("error", report["asks"][0])

    def test_the_world_hook_notes_the_asks_and_can_be_turned_off(self):
        ctx = _scene(keeper=("B", "Beth"), addressed=["B"])
        with mock.patch.object(world.turn_ledger, "note") as note:
            check = world._attack_check_for_line(T10_LINE, ctx, None, [], [], ask=Truthful({_plain(T10_LINE): {"Beth"}}))
        self.assertEqual(check["attack"]["code"], "B")
        args, kwargs = note.call_args
        self.assertEqual(args, ("check", "attack_found"))
        self.assertEqual(len(kwargs["asks"]), 2)
        with mock.patch.dict(os.environ, {"AI_RPG_ATTACK_ASK": "0"}):
            self.assertIsNone(world._attack_check_for_line(T10_LINE, ctx, None, [], [], ask=_always("Yes")))

    def test_a_stub_turn_has_no_model_to_ask(self):
        with mock.patch.object(world, "generate_turn", lambda *a, **k: {}):
            self.assertIsNone(world._model_attack_ask([], []))
        self.assertIsNotNone(world._model_attack_ask([], []))

    def test_the_model_ask_reaches_trace_and_usage(self):
        usage: list = []
        trace: list = []
        ask = world._model_attack_ask(usage, trace)
        with mock.patch.object(llm, "_chat_content", return_value="Yes"):
            ask(A.PHASE_ATTACK, A.ask_attack("Beth", "i rip her in half"), 8)
        self.assertEqual(usage[0]["phase"], A.PHASE_ATTACK)
        events = [(t["phase"], t["event"]) for t in trace]
        self.assertIn((A.PHASE_ATTACK, "request"), events)
        self.assertIn((A.PHASE_ATTACK, "response"), events)


# --- the outcome follows the roll --------------------------------------------


def _records() -> dict:
    return {
        "people": [{"code": "B", "name": "Beth", "died_turn": 0}],
        "places": [
            {"code": "L2", "name": "Thornford", "destroyed_turn": 0},
            {"code": "L3", "name": "Radiation Fenced Sanctuary Clinic", "destroyed_turn": 0},
        ],
        "player_names": ["Ash"],
    }


def _roll(outcome: str, code: str = "B", skill: str = "melee") -> dict:
    flavor = {
        "partial": "You get something, but not everything you wanted.",
        "failure": "You fail. The moment offers nothing useful.",
        "success": "You succeed cleanly.",
    }.get(outcome, "")
    return {"natural": 9, "outcome": outcome, "skill": {"code": skill}, "flavor": flavor,
            "attack": {"code": code, "name": "Beth"}}


class Prose:
    """The interpreter's asks: died / died_check by name, and the per-sentence "is X dead?" by sentence start."""

    def __init__(self, died=("Beth",), dead_sentences=T10_DEAD, always=None):
        self.died = set(died)
        self.dead_sentences = tuple(dead_sentences)
        self.always = always
        self.calls: list[tuple[str, str]] = []

    def __call__(self, phase: str, prompt: str, max_tokens: int) -> str:
        self.calls.append((phase, prompt))
        if self.always is not None:
            return self.always
        if phase == I.PHASE_DIED:
            return "Yes, she is dead at the end" if any(f"Is {n} dead" in prompt for n in self.died) else "No"
        if phase == I.PHASE_DIED_CHECK:
            return "No, she is not alive"
        if phase in (I.PHASE_DESTROYED, I.PHASE_DESTROYED_CHECK, I.PHASE_HOLD):
            return "No"
        if phase == I.PHASE_REFUSED_DEATH:
            sentence = re.search(r'Does the sentence "(.*)" say that ', prompt, re.S).group(1)
            return "Yes, she is dead." if sentence.startswith(self.dead_sentences) else "No."
        return "No"


class TestTheOutcomeFollowsTheRoll(unittest.TestCase):
    def test_allow_event_reads_the_attack_roll(self):
        died = {"kind": "died", "subject": {"type": "npc", "code": "B", "name": "Beth"}}
        self.assertEqual(I.allow_event(died, {"skill_checks": [_roll("success")]}), "")
        self.assertEqual(I.allow_event(died, {"skill_checks": [_roll("critical_success")]}), "")
        self.assertEqual(I.allow_event(died, {"skill_checks": [_roll("partial")]}), "attack roll partial")
        self.assertEqual(I.allow_event(died, {"skill_checks": [_roll("failure")]}), "attack roll failure")
        # No attack on her this turn, or on someone else: not the dice's to refuse.
        self.assertEqual(I.allow_event(died, {"skill_checks": [_roll("failure", code="G")]}), "")
        self.assertEqual(I.allow_event(died, {"skill_checks": [{"natural": 3, "outcome": "failure"}]}), "")
        self.assertEqual(I.allow_event(died, None), "")
        destroyed = {"kind": "destroyed", "subject": {"type": "place", "code": "L3"}}
        self.assertEqual(I.allow_event(destroyed, {"skill_checks": [_roll("failure")]}), "")

    def test_cc87dd29_t10_a_failed_roll_refuses_the_death_and_the_prose_follows(self):
        model = Prose()
        out = I.run(T10, _records(), model, {"skill_checks": [_roll("failure")]})
        event = out["events"][0]
        self.assertEqual((event["kind"], event["status"], event["reason"]), ("died", "refused", "attack roll failure"))
        text = out["narration"]
        beat = "Beth [[B]] is still alive. You fail. The moment offers nothing useful."
        self.assertEqual(text.count(beat), 1)
        for gone in ("Her entrails spill out", "The life has been ripped", "wide, dead eyes", "A sickening tear"):
            self.assertNotIn(gone, text)
        # The player's act as narrated is never cut, and the beat stands where the death was.
        self.assertTrue(text.startswith("You lunge towards Beth [[B]], grabbing her arms"))
        self.assertLess(text.index("She thrashes and struggles"), text.index(beat))
        self.assertEqual(out["report"]["refused_deaths"][0]["action"], "replaced")
        self.assertNotIn("died", I.summary(out["events"], text))

    def test_cc87dd29_t5_a_partial_roll_leaves_her_hurt_not_dead(self):
        model = Prose(dead_sentences=("Beth lies crumpled",))
        out = I.run(T5, _records(), model, {"skill_checks": [_roll("partial", skill="ranged")]})
        died = [e for e in out["events"] if e["kind"] == "died"]
        self.assertEqual(died[0]["status"], "refused")
        self.assertIn("Beth [[B]] is hurt, but still alive.", out["narration"])
        self.assertNotIn("neck twisted", out["narration"])
        self.assertIn("You methodically search the ruins", out["narration"])

    def test_a_successful_roll_lets_the_death_stand(self):
        model = Prose()
        out = I.run(T10, _records(), model, {"skill_checks": [_roll("success")]})
        self.assertEqual(out["events"][0]["status"], "proposed")
        self.assertEqual(out["narration"], T10)
        self.assertNotIn(I.PHASE_REFUSED_DEATH, [p for p, _ in model.calls])

    def _without_attack_line(self, out: dict) -> str:
        """The narration with the engine's attack line (app/attack_line.py, no ask) taken back out."""
        text = out["narration"]
        for entry in out["report"].get("attack_beats") or []:
            text = text.replace(" " + entry["beat"], "", 1)
        return text

    def test_a_yes_biased_model_changes_nothing(self):
        # The asks change nothing; the failed roll's own line goes in, by the engine's reading alone.
        out = I.run(T10, _records(), Prose(always="Yes"), {"skill_checks": [_roll("failure")]})
        self.assertEqual(out["events"], [])
        self.assertEqual(self._without_attack_line(out), T10)
        # No clause of the player's attack states an outcome (the kill is told in Beth's own
        # sentences), so the line goes in as not shown; the death itself is the refused-death path's.
        self.assertEqual(out["report"]["attack_beats"][0]["state"], "unshown")

    def test_a_no_biased_model_changes_nothing(self):
        yes = I.run(T10, _records(), Prose(always="Yes"), {"skill_checks": [_roll("failure")]})
        out = I.run(T10, _records(), Prose(always="No."), {"skill_checks": [_roll("failure")]})
        self.assertEqual(out["events"], [])
        self.assertEqual(self._without_attack_line(out), T10)
        self.assertEqual(out["narration"], yes["narration"])

    def test_no_sentence_picked_adds_the_beat(self):
        out = I.run(T10, _records(), Prose(dead_sentences=("zzz",)), {"skill_checks": [_roll("failure")]})
        self.assertTrue(self._without_attack_line(out).startswith(T10))
        self.assertTrue(out["narration"].endswith("Beth [[B]] is still alive. You fail. The moment offers nothing useful."))

    def test_never_below_the_floor(self):
        short = "Beth [[B]] falls dead. Beth [[B]] lies still on the floor."
        out = I.run(short, _records(), Prose(dead_sentences=("Beth falls", "Beth lies")), {"skill_checks": [_roll("failure")]})
        self.assertIn("is still alive", out["narration"])
        self.assertEqual(out["report"]["refused_deaths"][0]["action"], "kept_floor_beat_added")
        # The death refusal keeps the prose (the floor). The scene shows no attack sentence, so the
        # engine's attack line goes in after the first sentence naming her and nothing is dropped.
        entry = out["report"]["attack_beats"][0]
        self.assertEqual((entry["state"], entry["where"]), ("unshown", "target"))
        self.assertEqual(self._without_attack_line(out)[: len(short)], short)
        self.assertTrue(out["narration"].startswith(f"Beth [[B]] falls dead. {entry['beat']} Beth [[B]] lies still"))

    def test_the_players_quoted_words_are_never_cut(self):
        text = T10.replace("The life has been ripped from her,", '"Rest now," you whisper as the life leaves her,')
        records = {**_records(), "player_quotes": ["Rest now,"]}
        out = I.run(text, records, Prose(dead_sentences=('"Rest now', "Her entrails")), {"skill_checks": [_roll("failure")]})
        self.assertIn('"Rest now," you whisper', out["narration"])
        self.assertNotIn("Her entrails", out["narration"])

    def test_apply_events_keeps_a_refused_death_refused(self):
        _fresh_world()
        code = _add_npc("Beth")
        refused = {"kind": "died", "subject": {"type": "npc", "code": code, "name": "Beth"}, "status": "refused",
                   "reason": "attack roll failure"}
        with db.connect().closing() as conn:
            out = I.apply_events(conn, 3, [refused], {"skill_checks": []})
            conn.commit()
        self.assertEqual(out[0]["status"], "refused")
        self.assertEqual(_died_turn(code), 0)


# --- the whole turn, on an isolated save -------------------------------------


def _fresh_world():
    os.environ.update(_ENV)
    assert str(db.db_path()).startswith(str(_TMP)), db.db_path()
    db.init_db()
    world.start_playthrough({"player_name": "Ash", "start_location": "Low Gate", "special_ability_origin": "none",
                             "dice_checks_enabled": True})


def _add_npc(name: str, died_turn: int = 0) -> str:
    with db.connect().closing() as conn:
        loc = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()["current_location_id"]
        code = world._next_alpha_code(conn, "npcs")
        conn.execute("INSERT INTO npcs (code, location_id, name, died_turn) VALUES (?, ?, ?, ?)", (code, int(loc), name, died_turn))
        conn.commit()
        return code


def _died_turn(code: str) -> int:
    with db.connect().closing() as conn:
        return int(conn.execute("SELECT died_turn FROM npcs WHERE code = ?", (code,)).fetchone()["died_turn"])


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
        # What generate_turn leaves for apply_turn (app/llm.py).
        "_interpreter_pending": {"config": {}},
        "_model_trace": [],
        "_model_usage": [],
    }


def _phase_of(prompt: str) -> str:
    for marker, phase in (
        ("dead at the end", I.PHASE_DIED),
        ("alive at the end", I.PHASE_DIED_CHECK),
        ("destroyed at the end", I.PHASE_DESTROYED),
        ("still standing at the end", I.PHASE_DESTROYED_CHECK),
        ("say or do anything in it", I.PHASE_HOLD),
        ("Does the sentence", I.PHASE_REFUSED_DEATH),
    ):
        if marker in prompt:
            return phase
    return ""


def _forced(outcome: str):
    real = skill_checks.resolve_check

    def resolve(**kwargs):
        out = real(**kwargs)
        out.update({"outcome": outcome, "degree": outcome})
        return out

    return resolve


def _play(narration: str, line: str, outcome: str, attack_model, prose_model) -> dict:
    def content(system, user, **kwargs):
        phase = _phase_of(user)
        return prose_model(phase, user, 8) if phase else "No"

    attack_intent.ASK_OVERRIDE[0] = attack_model
    try:
        with mock.patch.object(world, "generate_turn", return_value=_turn(narration)), \
                mock.patch.object(llm, "_chat_content", side_effect=content), \
                mock.patch.object(skill_checks, "resolve_check", side_effect=_forced(outcome)):
            world.play_turn(line)
    finally:
        attack_intent.ASK_OVERRIDE[0] = None
    files = sorted((_TMP / "traces").glob("turn-*.json"), key=lambda p: p.stat().st_mtime)
    return json.loads(files[-1].read_text(encoding="utf-8"))


class TestTheWholeTurn(unittest.TestCase):
    def setUp(self):
        _fresh_world()
        self.code = _add_npc("Beth")
        self.prose = T10.replace("[[B]]", f"[[{self.code}]]")
        self.line = "i walk up to Beth and grab her arms with one hand and her legs with the other, and i rip her in half, this move grants her instant death"

    def _attack_model(self):
        def ask(phase, prompt, max_tokens):
            if phase == A.PHASE_ATTACK:
                return "Yes" if "i rip her in half" in prompt and "kill Beth?" in prompt else "No"
            return "No"

        return ask

    def test_a_failed_attack_roll_keeps_beth_alive_and_says_so(self):
        trace = _play(self.prose, self.line, "failure", self._attack_model(), Prose())
        checks = (trace.get("prompt_context") or {}).get("mechanics_context", {}).get("resolved_checks") or []
        attack = [c for c in checks if (c.get("attack") or {}).get("code") == self.code]
        self.assertTrue(attack, checks)
        self.assertEqual(attack[0]["outcome"], "failure")
        self.assertEqual(_died_turn(self.code), 0)
        narration = trace["final_turn"]["narration"]
        self.assertIn(f"Beth [[{self.code}]] is still alive.", narration)
        self.assertNotIn("Her entrails spill out", narration)
        notes = json.dumps(trace.get("engine") or {})
        self.assertIn("attack_found", notes)
        self.assertIn("event_refused", notes)
        self.assertNotIn("died.", trace["final_turn"].get("turn_summary") or "")

    def test_a_successful_attack_roll_lets_the_death_stand(self):
        trace = _play(self.prose, self.line, "success", self._attack_model(), Prose())
        self.assertGreater(_died_turn(self.code), 0)
        self.assertNotIn("is still alive", trace["final_turn"]["narration"])

    def test_a_yes_biased_attack_model_rolls_nothing_new(self):
        trace = _play(self.prose, self.line, "failure", _always("Yes"), Prose())
        checks = (trace.get("prompt_context") or {}).get("mechanics_context", {}).get("resolved_checks") or []
        self.assertFalse([c for c in checks if c.get("attack")], checks)
        # No attack roll: the death is not the dice's to refuse, as before this change.
        self.assertGreater(_died_turn(self.code), 0)


if __name__ == "__main__":
    unittest.main()
