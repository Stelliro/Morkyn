"""Gold taken with no payment in the prose (#41 reopened): the interpreter's gold asks.

The baseline replay before the fixes (Hermes 3 8B, the tester's setup,
scratchpad live/baseline): the purse went 12 -> 2 -> 0 over "i shoot Marisol"
(draft GOLD -5, settled -10, rolled as a 'small' loss band) and the rip-in-half
line (draft GOLD -10, rolled -8); the merged-code replay (live/integ-r3) T3 had
the same -10 voided only by luck (a refused GRANT). Nothing in those scenes
mentions coin, a payment, a fine or a loss.

The interpreter now asks over the final scene "Does the player give, pay or
lose money in this text?" (and "receive"), and a second ask ("the same money at
the end as at the start?") must answer no before either counts. A loss counts
only when the scene shows it; the amount stays the engine's. Both answers are
logged beside _settle_stated_gold (shadow mode).

The model is mocked at the transport (the real _chat_text runs, so every ask
is in the trace and model_usage): a reader that answers right, a yes-biased
one and a no-biased one.

Run:  cd tests && python -m unittest test_interpreter_gold
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-interpreter-gold-test-"))
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

from app import db, interpreter, llm, turn_ledger, world  # noqa: E402

I = interpreter

# --- baseline replay T2 (trace 3): "i shoot Marisol", draft GOLD -5 -> -10 ---
B2 = (
    "You enter the Radiation Fenced Sanctuary Clinic [[L2]], a small but well-kept medical outpost. The front door is "
    "locked, but a side door stands open. Inside, the clinic is clean and organized, with rows of beds on either side. A "
    "woman in medical scrubs, Marisol [[A]], is moving between them, checking on patients. She sees you enter and waves "
    "you over.\n\n"
    "Marisol [[A]] says, \"Oh good, a new volunteer. We could use the help. What's your name?\"\n\n"
    "You: i shoot Marisol [[A]]\n\n"
    "Marisol [[A]]'s eyes widen and she steps back, raising her hands defensively. \"Whoa, easy there! I'm not the "
    "enemy.\" She glances around, worried. \"You're not planning on shooting anyone, are you? In here, we patch people "
    "up, not send them off to their deaths.\"\n\n"
    "Marisol [[A]] says, \"I'm just trying to help. This clinic is a safe place, for patients and volunteers both. We "
    "work together to save lives, not fight each other.\""
)

# --- baseline replay T3 (trace 4): the rip-in-half line, draft GOLD -10 -> -8 -
B3 = (
    "You lunge at Marisol [[A]], grabbing her arms with one hand and her legs with the other. With a brutal motion, you "
    "rip her in two. Marisol [[A]]'s body separates at the waist, her upper and lower halves falling to the floor in a "
    "spray of blood. The other volunteers scream and scramble away from the carnage.\n\n"
    "Marisol [[A]]'s death is instantaneous. She had no chance to fight back or even cry out.\n\n"
    "The clinic erupts in chaos as the volunteers flee in terror. Some of them shout for the guards, while others rush "
    "to contain the damage. The scene is one of pure shock and horror.\n\n"
    "As the dust settles, you stand over Marisol [[A]]'s remains, panting heavily. Her blood is pooled on the floor, and "
    "her eyes seem to still be staring at you in disbelief. You feel no remorse for what you've done.\n\n"
    "You are still in the Radiation Fenced Sanctuary Clinic [[L2]]. The grisly murder has left the place in utter "
    "disarray. The other volunteers are huddled in a corner, clearly terrified of you. You have no weapons or items to "
    "take from the scene.\n\n"
    "The clinic's exits are still intact, though the volunteers seem to be trying to barricade them. You could try to "
    "flee the scene before the guards arrive. Alternatively, you could hide among the bodies and hope the guards don't "
    "find you.\n\n"
    "What do you do now?"
)

# --- merged-code replay T3 (live/integ-r3, trace 4): draft GOLD -10 -----------
M3 = (
    "The morning sun filters through the windows of the empty waiting room, casting a soft glow on the grisly scene "
    "that unfolds before you. Dr. Theo [[B]] stands motionless, his eyes locked on your outstretched hands as they "
    "grasp his limbs. With a sudden, violent motion, you wrench him apart, his body splitting down the middle like a "
    "torn sheet of paper. His innards spill out onto the cold, white tiles, a gruesome spectacle in the quiet of the "
    "clinic. Theo [[C]]'s face contorts in shock and agony as he lies there in two halves, his eyes wide with the "
    "realization that he has been ripped asunder. The silence of the room is shattered only by the sound of his "
    "lifeless gaze, fixed upon the horror of his own dismembered body. You have dealt him instant death."
)

PURCHASE = (
    "The merchant sets a coil of rope on the counter. \"Five gold,\" she says. You pay the merchant 5 gold and she "
    "slides the rope across to you."
)
ROBBERY = (
    "Someone jostles you in the crowd near the fish stalls. By the time you turn, the thief makes off with your purse, "
    "vanishing down an alley."
)
FINE = (
    "The watch sergeant writes in his ledger. \"Brawling in the square. That's a fine of ten gold.\" You hand the ten "
    "gold over and he waves you on."
)

# What the scene really shows (my reading): out = money leaves the player.
TRUTH = {
    "B2": {"out": False, "in": False},
    "B3": {"out": False, "in": False},
    "M3": {"out": False, "in": False},
    "PURCHASE": {"out": True, "in": False},
    "ROBBERY": {"out": True, "in": False},
    "FINE": {"out": True, "in": False},
}
TEXTS = {"B2": B2, "B3": B3, "M3": M3, "PURCHASE": PURCHASE, "ROBBERY": ROBBERY, "FINE": FINE}


def _gold_phase(prompt: str) -> str:
    if "give, pay or lose money" in prompt:
        return I.PHASE_GOLD_OUT
    if "receive money" in prompt:
        return I.PHASE_GOLD_IN
    if "same money at the end" in prompt:
        return I.PHASE_GOLD_CHECK
    return ""


class Reader:
    """A model that reads the scene right: yes where the truth says so, and the check agrees."""

    def __init__(self, truth: dict[str, bool]):
        self.truth = truth
        self.calls: list[str] = []

    def __call__(self, phase: str, prompt: str, max_tokens: int = 8) -> str:
        self.calls.append(phase)
        if phase == I.PHASE_GOLD_OUT:
            return "Yes, the player pays." if self.truth["out"] else "No."
        if phase == I.PHASE_GOLD_IN:
            return "Yes." if self.truth["in"] else "No, the player does not receive money."
        if phase == I.PHASE_GOLD_CHECK:
            return "No, it changes." if (self.truth["out"] or self.truth["in"]) else "Yes."
        return "No"


class YesBiased(Reader):
    def __init__(self):
        super().__init__({"out": True, "in": True})

    def __call__(self, phase: str, prompt: str, max_tokens: int = 8) -> str:
        self.calls.append(phase)
        return "Yes."


class NoBiased(Reader):
    def __init__(self):
        super().__init__({"out": False, "in": False})

    def __call__(self, phase: str, prompt: str, max_tokens: int = 8) -> str:
        self.calls.append(phase)
        return "No."


class Down(Reader):
    def __init__(self):
        super().__init__({"out": False, "in": False})

    def __call__(self, phase: str, prompt: str, max_tokens: int = 8) -> str:
        raise TimeoutError("model down")


# --- The asks themselves -----------------------------------------------------


class TestReadGold(unittest.TestCase):
    def test_the_replayed_violent_turns_show_no_money_leaving(self):
        for key in ("B2", "B3", "M3"):
            out = I.read_gold(TEXTS[key], Reader(TRUTH[key]))
            self.assertIs(out["out"], False, key)
            self.assertIs(out["in"], False, key)

    def test_a_purchase_a_robbery_and_a_fine_show_it(self):
        for key in ("PURCHASE", "ROBBERY", "FINE"):
            model = Reader(TRUTH[key])
            out = I.read_gold(TEXTS[key], model)
            self.assertIs(out["out"], True, key)
            self.assertIs(out["in"], False, key)
            # the second check was asked before it counted, once
            self.assertEqual(model.calls.count(I.PHASE_GOLD_CHECK), 1, key)

    def test_a_yes_biased_model_needs_the_second_check(self):
        model = YesBiased()
        out = I.read_gold(B2, model)
        self.assertIs(out["out"], False)
        self.assertIs(out["in"], False)
        self.assertIn(I.PHASE_GOLD_CHECK, model.calls)
        self.assertEqual({u["direction"] for u in out["report"]["unconfirmed"]}, {"out", "in"})

    def test_a_no_biased_model_counts_nothing(self):
        model = NoBiased()
        out = I.read_gold(PURCHASE, model)
        self.assertIs(out["out"], False)
        self.assertNotIn(I.PHASE_GOLD_CHECK, model.calls)

    def test_a_model_that_is_down_decides_nothing(self):
        out = I.read_gold(B2, Down())
        self.assertIsNone(out["out"])
        self.assertIsNone(out["in"])

    def test_the_asks_are_one_plain_question_over_the_scene_without_codes(self):
        model = Reader(TRUTH["B2"])
        prompts: list[str] = []
        I.read_gold(B2, lambda phase, prompt, n: (prompts.append(prompt), model(phase, prompt, n))[1])
        self.assertTrue(prompts[0].endswith("Does the player give, pay or lose money in this text? Answer yes or no."))
        self.assertTrue(prompts[1].endswith("Does the player receive money in this text? Answer yes or no."))
        self.assertNotIn("[[", prompts[0])
        self.assertIn("I'm not the enemy", prompts[0])


class TestTheVoidRule(unittest.TestCase):
    """world._void_unbought_spend is the one place a loss is voided."""

    def test_a_loss_not_shown_is_voided_and_says_why(self):
        result = {"player": {"gold_delta": -10}}
        report: dict = {}
        self.assertTrue(world._void_unbought_spend(result, [], [], report, "i shoot Marisol", B2, loss_shown=False))
        self.assertEqual(result["player"]["gold_delta"], 0)
        self.assertEqual(report["voided_spend"]["why"], "loss_not_shown")

    def test_a_loss_shown_stands(self):
        result = {"player": {"gold_delta": -5}}
        self.assertFalse(world._void_unbought_spend(result, [], [], {}, "i buy the rope", PURCHASE, loss_shown=True))
        self.assertEqual(result["player"]["gold_delta"], -5)

    def test_unasked_keeps_the_old_rules(self):
        # Reverse: with no interpreter answer the loss stands as the rules decide (a toll, a fine).
        result = {"player": {"gold_delta": -10}}
        self.assertFalse(world._void_unbought_spend(result, [], [], {}, "i shoot Marisol", B2))
        self.assertEqual(result["player"]["gold_delta"], -10)

    def test_a_gain_is_never_touched(self):
        result = {"player": {"gold_delta": 7}}
        self.assertFalse(world._void_unbought_spend(result, [], [], {}, "", B2, loss_shown=False))
        self.assertEqual(result["player"]["gold_delta"], 7)


# --- The engine side, on a real (isolated) save ------------------------------


def _fresh_world():
    os.environ.update(_ENV)
    assert str(db.db_path()).startswith(str(_TMP)), db.db_path()
    db.init_db()
    world.start_playthrough({"player_name": "Ash", "start_location": "Low Gate", "special_ability_origin": "none"})
    with db.connect().closing() as conn:
        conn.execute("UPDATE player SET gold = 12 WHERE id = 1")
        conn.commit()


def _gold() -> int:
    with db.connect().closing() as conn:
        return int(conn.execute("SELECT gold FROM player WHERE id = 1").fetchone()["gold"])


def _turn(narration: str, player: dict, pending: bool = True) -> dict:
    turn = {
        "scene_plan": {"goal": "act", "focus_points": []},
        "narration_segments": [{"label": "scene", "text": narration}],
        "narration": narration,
        "player": dict(player),
        "self_check": {"passed": True, "issues_found": [], "corrections_made": []},
        "turn_summary": "a beat",
        "scene_focus": "action",
        "scene_cast": {"present": [], "interacting": [], "off": []},
    }
    if pending:
        turn["_interpreter_pending"] = {"config": {}}
        turn["_model_trace"] = []
        turn["_model_usage"] = []
    return turn


def _play(turn: dict, player_input: str, model: Reader | None = None) -> None:
    def content(system, user, **kwargs):
        phase = _gold_phase(user)
        if model is None:
            return "No"
        return model(phase, user, kwargs.get("max_tokens") or 8) if phase else "No"

    with mock.patch.object(world, "generate_turn", return_value=turn), mock.patch.object(llm, "_chat_content", side_effect=content):
        world.play_turn(player_input)


def _last_trace() -> dict:
    files = sorted((_TMP / "traces").glob("turn-*.json"), key=lambda p: p.stat().st_mtime)
    return json.loads(files[-1].read_text(encoding="utf-8"))


def _notes(decision: str) -> list[dict]:
    return [n for n in (turn_ledger.last_finished() or {}).get("notes") or [] if n.get("decision") == decision]


class TestTheEngineTakesOnlyShownGold(unittest.TestCase):
    def setUp(self):
        _fresh_world()

    def test_baseline_t2_shooting_takes_no_gold(self):
        _play(_turn(B2, {"gold_delta": -10}), "i shoot Marisol", Reader(TRUTH["B2"]))
        self.assertEqual(_gold(), 12)
        self.assertTrue(_notes("loss_not_shown"))
        shadow = _notes("gold_shadow")
        self.assertTrue(shadow)
        trace = _last_trace()
        record = [t for t in trace["model_trace"] if t.get("phase") == "interpreter_gold"][-1]
        self.assertEqual(record["engine"]["settled"] < 0, True)
        self.assertEqual(record["engine"]["final"], 0)
        self.assertIs(record["interpreter"]["out"], False)
        self.assertIs(record["agree"], False)
        self.assertEqual([(e["direction"], e["status"]) for e in record["events"]], [("out", "refused")])
        # every ask's prompt, reply and seconds are in the trace and model_usage
        for phase in (I.PHASE_GOLD_OUT, I.PHASE_GOLD_IN):
            requests = [t for t in trace["model_trace"] if t.get("phase") == phase and t.get("event") == "request"]
            responses = [t for t in trace["model_trace"] if t.get("phase") == phase and t.get("event") == "response"]
            self.assertTrue(requests and responses and "duration_seconds" in responses[0], phase)
        with db.connect().closing() as conn:
            logged = {r["phase"] for r in conn.execute("SELECT phase FROM model_logs WHERE phase LIKE 'interpreter_gold%'").fetchall()}
        self.assertLessEqual({I.PHASE_GOLD_OUT, I.PHASE_GOLD_IN}, logged)

    def test_baseline_t3_and_merged_t3_take_no_gold(self):
        _play(_turn(B3, {"gold_delta": -10}), "i rip her in half", Reader(TRUTH["B3"]))
        self.assertEqual(_gold(), 12)
        _play(_turn(M3, {"gold_delta": -10}), "i rip him in half", Reader(TRUTH["M3"]))
        self.assertEqual(_gold(), 12)

    def test_a_loss_band_with_no_coin_in_the_prose_is_refused(self):
        _play(_turn(B3, {"gold_band": "-small"}), "i rip her in half", Reader(TRUTH["B3"]))
        self.assertEqual(_gold(), 12)

    def test_a_purchase_pays(self):
        _play(_turn(PURCHASE, {"gold_delta": -5}), "i buy the rope", Reader(TRUTH["PURCHASE"]))
        self.assertEqual(_gold(), 7)
        record = [t for t in _last_trace()["model_trace"] if t.get("phase") == "interpreter_gold"][-1]
        self.assertIs(record["agree"], True)
        self.assertEqual([(e["direction"], e["amount"], e["status"]) for e in record["events"]], [("out", 5, "applied")])
        self.assertEqual(record["readers"]["paid"], [5])

    def test_a_robbery_takes_the_rolled_sum(self):
        _play(_turn(ROBBERY, {"gold_band": "-small"}), "i walk through the market", Reader(TRUTH["ROBBERY"]))
        self.assertLess(_gold(), 12)

    def test_a_fine_is_paid(self):
        _play(_turn(FINE, {"gold_delta": -10}), "i pay the fine", Reader(TRUTH["FINE"]))
        self.assertEqual(_gold(), 2)

    def test_a_yes_biased_model_takes_nothing_without_the_check(self):
        _play(_turn(B2, {"gold_delta": -10}), "i shoot Marisol", YesBiased())
        self.assertEqual(_gold(), 12)

    def test_a_no_biased_model_keeps_the_purse_and_cuts_no_prose(self):
        # A false no on a real payment refuses the loss (measured as disagreement
        # with the prose readers), and the paying sentence is left, not cut.
        _play(_turn(PURCHASE, {"gold_delta": -5}), "i buy the rope", NoBiased())
        self.assertEqual(_gold(), 12)
        trace = _last_trace()
        self.assertIn("You pay the merchant 5 gold", trace["final_turn"]["narration"])
        record = [t for t in trace["model_trace"] if t.get("phase") == "interpreter_gold"][-1]
        self.assertEqual(record["readers"]["paid"], [5])
        self.assertIs(record["agree"], False)

    def test_without_the_interpreter_the_old_rules_stand(self):
        # Reverse: no model turn (no pending interpreter), the loss is applied as before.
        _play(_turn(FINE, {"gold_delta": -10}, pending=False), "i pay the fine")
        self.assertEqual(_gold(), 2)
        with mock.patch.dict(os.environ, {"AI_RPG_INTERPRETER": "off"}):
            _play(_turn(B2, {"gold_delta": -2}), "i shoot Marisol", Reader(TRUTH["B2"]))
        self.assertEqual(_gold(), 0)

    def test_a_gain_stays_with_the_existing_rules(self):
        # Shadow only for gains: a no from the interpreter does not touch it.
        text = "The captain counts out ten gold and hands the coins to you. \"For the crates,\" he says."
        _play(_turn(text, {"gold_delta": 10}), "i deliver the crates", NoBiased())
        self.assertEqual(_gold(), 22)


if __name__ == "__main__":
    unittest.main()
