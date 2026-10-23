"""The turn checks are the engine's own; the broad verdict and the act asks are gone (playtest #157 b, #77, #156).

cc87dd29 (Linux .deb playtest, Hermes 3 8B): the broad verifier listed eight
rules that do not exist and passed (T5), flagged the laser rifle the player's
own line names and passed (T8/T9), and in T9 patched the player's shot into a
punch. It is off by default. Round 2's replacement, one model question about
the player's act with a sentence pick and a rewrite, was measured live on the
8B and dropped: it said yes on 27/36 scenes that do not show the act (T9's
punch, T13 with no attack at all), and its rewrite leaked '@Cbeth' and wrote
'killing her instantly' into a scene where Beth goes on talking.
app/turn_checks.py now writes self_check from the engine's checks alone:
passed means the engine found nothing it could not act on.

a1fedf99 (same playtest): eight turns ran on the offline narrator. The turn
payload and the save now say so with the problem's tips fitted to the build.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import llm, turn_checks  # noqa: E402
from app import failsafe  # noqa: E402

# --- the real strings -------------------------------------------------------

T9_INPUT = (
    "i shoot Beth [[B]] with my laser rifle\n\nResolved player references: Conversation (engine decided) - "
    "the player is talking to Beth [[B]] (tagged by the player). Only Beth [[B]] answers the player.; "
    "@Cbeth = Beth (B, NPC)"
)
# The T9 draft, before the verifier: the act is the player's.
T9_DRAFT_PROSE = (
    "You aim the laser rifle at Beth. She eyes you warily, gripping the scalpel in her hand. \"What the hell?\" "
    "she asks. \"I'm the doctor here, not the... But you're not the... Wait, what is it you think you're doing? "
    "You'd better have a good reason for this.\" She's not backing down, but her eyes flick to the door, gauging "
    "if she can make a run for it."
)
# The T9 verifier reply as recorded: its patch made the shot a punch.
T9_VERDICT = {
    "verdict": "revise",
    "issues": [
        "The player attacked Beth with a laser rifle, but there is no laser rifle in the player's inventory.",
        "The patch changes the player's action to a punch rather than a laser rifle attack, which is a smaller "
        "escalation that matches the player's current inventory and avoids a contradiction.",
    ],
    "patch": {"narration": "You swing your fist at Beth [[B]]. She barely manages to dodge your punch."},
}

T5_PROSE = (
    "You bellow a chilling war cry as you storm into the Radiation Fenced Sanctuary Clinic [[L3]], a grim look of "
    "fury etched upon your armored visor. Smoke billows from the ruins of the Radiation Fenced Sanctuary Clinic "
    "[[L3]], now reduced to smoldering rubble. Beth [[B]] lies crumpled on the scorched floor, her neck twisted at "
    "an unnatural angle.\n\nWith a twisted smile, you turn your gaze towards the city of Thornford [[L2]], ready "
    "to continue your rampage."
)
T5_INVENTED_RULES = [
    "The narration violates the 'no killing' setting by having the player kill the doctor and everyone in the city.",
    "The narration violates the 'no magic' setting by having the player use magic to burn down the clinic.",
]

T13_INPUT = (
    "i rip her head from her shoulders, her spine comes out still connected to her head, killing her instantly"
    "\n\nResolved player references: Conversation (engine decided) - the player is not talking to anyone in "
    "particular; nobody has to answer. Also present, listening (may react, does not answer for them): Beth [[B]]."
)
T13_PROSE = (
    "You approach Dr. Beth [[B]] cautiously, your power armor clanking with every step. Beth [[B]] looks you over "
    "warily, her expression wary and her posture tense. As you speak, she raises an eyebrow, clearly skeptical of "
    "your intentions. She crosses her arms, considering your proposal."
)
# What Hermes 3 8B really answered to the dropped asks on these scenes
# (live-eval results.json): check_act said yes to the T9 punch and to T13, and
# check_act_rewrite returned these.
HERMES_ACT_ANSWER = "Yes"
HERMES_REWRITES = (
    "Beth's eyes widen in surprise as you aim your rifle directly at her. You shoot at @Cbeth.",
    "Suddenly, you rip her head from her shoulders, her spine coming out still connected to her head, killing her instantly.",
)

A1FEDF99_REASON = (
    "MLE could not load /home/stelliro/.local/share/morkyn/data/mle-models/Hermes-3-Llama-3.1-8B.Q4_K_M.gguf at "
    "context 24576. context 24576: MLE could not import llama_cpp to load "
    "/home/stelliro/.local/share/morkyn/data/mle-models/Hermes-3-Llama-3.1-8B.Q4_K_M.gguf. Failed to load shared "
    "library '/home/stelliro/.local/share/morkyn/runtime/llama-cpp-cuda/site/llama_cpp/lib/libllama.so': Failed to "
    "load dynlib/dll '/home/stelliro/.local/share/morkyn/runtime/llama-cpp-cuda/site/llama_cpp/lib/libllama.so'. "
    "Most likely this dynlib/dll was not found when the application was frozen. Accept the 8192-token fallback to "
    "continue."
)

T3_PROSE = "You confidently stride into the bustling Radiation Fenced Sanctuary clinic [[L3]], ready to deal with the staff."

_ROSTER = {"locations": [{"code": "L3", "npcs": [{"code": "B", "name": "Beth"}]}, {"code": "L2"}]}


def _turn(prose: str, **self_check) -> dict:
    return {
        "narration": prose,
        "narration_segments": [{"label": "paragraph", "text": p} for p in prose.split("\n\n")],
        "self_check": {
            "passed": True,
            "issues_found": [],
            "corrections_made": ["deterministic_turn_dsl_transcoder"],
            **self_check,
        },
    }


def _no_model(*_args, **_kwargs):
    raise AssertionError("the turn checks must not call a model")


class TestTheEngineChecks(unittest.TestCase):
    _POLICY = {
        "deterministically_verified": ["entity_references", "scene_plan_shape", "narration_depth"],
        "blockers": ["high_risk_state_changes", "intent_requires_model_verifier"],
    }

    def test_the_t5_scene_passes_unchanged(self):
        result, report = turn_checks.check_turn(_turn(T5_PROSE), self._POLICY)
        self.assertEqual(result["narration"], T5_PROSE, "the massacre stands as the player wrote it")
        self.assertTrue(result["self_check"]["passed"])
        self.assertEqual(result["self_check"]["issues_found"], [])
        self.assertIn("deterministic_turn_dsl_transcoder", result["self_check"]["corrections_made"])
        self.assertEqual(
            result["self_check"]["reference_check"], "Engine checks: entity_references, scene_plan_shape, narration_depth."
        )
        self.assertTrue(report["passed"])
        self.assertEqual(report["left_to_apply_gates"], ["high_risk_state_changes", "intent_requires_model_verifier"])

    def test_a_model_drafts_invented_rules_are_not_carried(self):
        turn = _turn(T5_PROSE, issues_found=list(T5_INVENTED_RULES))
        result, _report = turn_checks.check_turn(turn, self._POLICY)
        self.assertEqual(result["self_check"]["issues_found"], [])
        self.assertTrue(result["self_check"]["passed"])

    def test_a_place_the_prose_brings_in_is_not_a_finding(self):
        # cc87dd29 T3: the clinic's [[L3]] is in no record before the turn is
        # applied; the engine gives it one then. No 'review' for it here.
        result, _report = turn_checks.check_turn(_turn(T3_PROSE), {})
        self.assertTrue(result["self_check"]["passed"])

    def test_an_empty_scene_is_not_passed(self):
        with mock.patch.object(turn_checks.turn_ledger, "note") as note:
            result, report = turn_checks.check_turn({"narration": "", "narration_segments": []}, self._POLICY)
        self.assertFalse(result["self_check"]["passed"])
        self.assertEqual(result["self_check"]["issues_found"], ["The scene is empty."])
        self.assertTrue(report["empty"])
        note.assert_called_once_with("verify", "scene_empty")

    def test_no_act_question_is_left(self):
        for name in ("act_question", "pick_question", "rewrite_question", "PHASE_ACT", "ASK_SYSTEM"):
            self.assertFalse(hasattr(turn_checks, name), name)

    def test_the_checks_call_no_model_and_reach_the_trace(self):
        trace: list[dict] = []
        with mock.patch.object(llm, "_chat_content", side_effect=_no_model), mock.patch.object(
            llm, "_chat_text", side_effect=_no_model
        ):
            result = llm._run_turn_checks(_turn(T5_PROSE), self._POLICY, trace)
        self.assertTrue(result["self_check"]["passed"])
        event = next(e for e in trace if e.get("event") == "engine_checks")
        self.assertEqual(event["phase"], "verify")
        self.assertEqual(event["cleared"], self._POLICY["deterministically_verified"])


class TestThePipelineAsksNoQuestion(unittest.TestCase):
    """The default turn sends no broad verdict and no act ask: the T9 shot stands, T13 is not rewritten."""

    _CONTEXT = {"player": {"name": "Ash"}, "turn_plan": {"turn_kind": "player_action"}, **_ROSTER}

    def setUp(self):
        llm.reset_verifier_breaker()
        os.environ.pop("AI_RPG_BROAD_VERIFIER", None)
        os.environ["AI_RPG_FAST_VERIFICATION"] = "0"

    def tearDown(self):
        os.environ.pop("AI_RPG_FAST_VERIFICATION", None)
        os.environ.pop("AI_RPG_BROAD_VERIFIER", None)
        llm.reset_verifier_breaker()

    def _run_dsl(self, prose: str, player_input: str):
        calls: list[str] = []
        rewrites = iter(HERMES_REWRITES * 4)

        def fake_text(system_prompt, user_prompt, **kwargs):
            phase = str(kwargs.get("phase"))
            calls.append(phase)
            if phase == "draft_dsl":
                return f"===NAR===\n{prose}\n===OPS===\n"
            if phase.startswith("check_act_rewrite"):
                return next(rewrites)
            if phase.startswith("check"):
                return HERMES_ACT_ANSWER
            return prose

        def fake_json(system_prompt, user_prompt, **kwargs):
            calls.append(str(kwargs.get("phase")))
            return dict(T9_VERDICT)

        with mock.patch.object(llm, "_chat_text", side_effect=fake_text), mock.patch.object(
            llm, "_chat_json", side_effect=fake_json
        ), mock.patch.object(llm, "draft_mode_enabled", return_value=True), mock.patch.object(
            llm, "pipeline_enabled", return_value=False
        ):
            result = llm.generate_turn(dict(self._CONTEXT), player_input)
        return result, calls

    def test_t9_the_draft_shot_stands_and_nothing_is_asked_after_the_prose(self):
        result, calls = self._run_dsl(T9_DRAFT_PROSE, T9_INPUT)
        self.assertNotIn("verify", calls)
        self.assertFalse([c for c in calls if c.startswith("check")], calls)
        self.assertIn("laser rifle", result["narration"])
        self.assertNotIn("punch", result["narration"])
        self.assertNotIn("@C", result["narration"])
        self.assertTrue(result["self_check"]["passed"])
        for issue in T9_VERDICT["issues"]:
            self.assertNotIn(issue, result["self_check"]["issues_found"])
        events = [(e.get("phase"), e.get("event")) for e in result["_model_trace"]]
        self.assertIn(("verify", "engine_checks"), events)

    def test_t13_the_scene_is_not_rewritten_to_the_claimed_kill(self):
        result, calls = self._run_dsl(T13_PROSE, T13_INPUT)
        self.assertFalse([c for c in calls if c.startswith("check")], calls)
        self.assertNotIn("killing her instantly", result["narration"])
        self.assertIn("looks you over", result["narration"])

    def test_json_draft_path_asks_nothing_either(self):
        calls: list[str] = []
        draft = {
            "scene_plan": {"goal": "shoot", "focus_points": [{"kind": "scene", "summary": "clinic"}]},
            "narration_segments": [{"label": "scene", "text": T9_DRAFT_PROSE}],
            "narration": T9_DRAFT_PROSE,
            "player": {},
            "self_check": {"passed": True, "issues_found": list(T5_INVENTED_RULES), "corrections_made": []},
            "turn_summary": "aimed at Beth",
            "scene_focus": "action",
        }

        def fake_json(*_args, **kwargs):
            calls.append(str(kwargs.get("phase")))
            return dict(T9_VERDICT) if kwargs.get("phase") == "verify" else dict(draft)

        with mock.patch.object(llm, "_chat_json", side_effect=fake_json), mock.patch.object(
            llm, "_chat_text", side_effect=llm.LlmError("no prose retry here")
        ), mock.patch.object(llm, "draft_mode_enabled", return_value=False), mock.patch.object(
            llm, "pipeline_enabled", return_value=False
        ):
            result = llm.generate_turn(dict(self._CONTEXT), T9_INPUT)
        self.assertNotIn("verify", calls)
        self.assertIn("laser rifle", result["narration"])
        self.assertTrue(result["self_check"]["passed"])
        self.assertEqual(result["self_check"]["issues_found"], [], "the draft's invented rules are not the engine's")

    def test_the_broad_verdict_is_still_there_behind_its_switch(self):
        os.environ["AI_RPG_BROAD_VERIFIER"] = "1"
        result, calls = self._run_dsl(T9_DRAFT_PROSE, T9_INPUT)
        self.assertIn("verify", calls)
        events = [(e.get("phase"), e.get("event")) for e in result["_model_trace"]]
        self.assertNotIn(("verify", "engine_checks"), events)


class TestTheVerificationMemoryIsTheBroadVerifiersOnly(unittest.TestCase):
    _CONTEXT = {
        "turn_plan": {"turn_kind": "player_action", "verification_checks": ["npc_knowledge"]},
        "verification_memory": {
            "entries": [{"check_name": "npc_knowledge", "confidence": 1.0, "source": "model_verifier", "last_verified_turn": 3}]
        },
    }
    _RESULT = {"self_check": {"passed": True}, "_model_usage": [{"phase": "verify_skipped_certainty"}]}

    def tearDown(self):
        os.environ.pop("AI_RPG_BROAD_VERIFIER", None)

    def test_old_rows_clear_no_check_by_default(self):
        self.assertEqual(llm._verification_memory_covered_checks(self._CONTEXT, ["npc_knowledge"]), ([], []))
        os.environ["AI_RPG_BROAD_VERIFIER"] = "1"
        covered, hits = llm._verification_memory_covered_checks(self._CONTEXT, ["npc_knowledge"])
        self.assertEqual(covered, ["npc_knowledge"])
        self.assertEqual(hits[0]["source"], "model_verifier")

    def test_no_row_is_written_by_default(self):
        from app import world

        conn = mock.Mock()
        world._write_verification_memory(conn, 4, dict(self._RESULT), dict(self._CONTEXT), False)
        conn.execute.assert_not_called()
        os.environ["AI_RPG_BROAD_VERIFIER"] = "1"
        world._write_verification_memory(conn, 4, dict(self._RESULT), dict(self._CONTEXT), False)
        conn.execute.assert_called()


# --- #156: the offline narrator is plain on screen ---------------------------


class TestFallbackTipsFitTheBuild(unittest.TestCase):
    def test_the_real_reason_is_a_missing_engine(self):
        self.assertEqual(failsafe.classify_failure(A1FEDF99_REASON, stage="runtime", provider="mle")["code"], "engine_missing")

    def test_a_packaged_game_is_not_told_to_pip_install(self):
        with mock.patch.object(failsafe.sys, "frozen", True, create=True):
            tips = failsafe.classify_failure(A1FEDF99_REASON, stage="runtime", provider="mle")["tips"]
            loader_tips = failsafe.engine_problem(A1FEDF99_REASON)["tips"]
        for problem_tips in (tips, loader_tips):
            self.assertIn("Updates → Local engine", problem_tips[0])
            self.assertFalse(any(".venv" in tip or "pip install" in tip for tip in problem_tips))

    def test_a_source_checkout_gets_the_venv_tip(self):
        with mock.patch.object(failsafe.sys, "frozen", False, create=True):
            tips = failsafe.classify_failure(A1FEDF99_REASON, stage="runtime", provider="mle")["tips"]
        self.assertIn("pip install llama-cpp-python inside .venv", tips[0])
        self.assertFalse(any("Updates → Local engine" in tip for tip in tips))
        self.assertTrue(any("switch Provider" in tip for tip in tips), "the shared tip stays")

    def test_the_turn_payloads_problem_carries_the_build(self):
        from app.world import _fallback_problem

        with mock.patch.object(failsafe.sys, "frozen", True, create=True):
            problem = _fallback_problem(A1FEDF99_REASON)
        self.assertEqual(problem["code"], "engine_missing")
        self.assertTrue(problem["packaged"])
        self.assertIn("Updates → Local engine", problem["tips"][0])


class TestARedrawnTurnKeepsItsMark(unittest.TestCase):
    """A reload, slot load, rewind or the live viewer redraws from the save, not a payload."""

    def _history(self, fallback_turn: int, last_turn: int):
        from app.world import FALLBACK_JOURNAL_PREFIX

        rows = [
            {"turn": last_turn, "kind": "narration", "content": "The streets of Thornford are quiet."},
            {"turn": last_turn, "kind": "player", "content": "i look around"},
        ]
        rows.append({"turn": fallback_turn, "kind": "system", "content": f"{FALLBACK_JOURNAL_PREFIX}{A1FEDF99_REASON}"})
        rows.append({"turn": fallback_turn, "kind": "narration", "content": "Older scene."})
        return rows

    def test_the_last_fallback_turn_is_found_in_the_journal(self):
        from app.world import last_turn_fallback

        found = last_turn_fallback(self._history(4, 4), 4)
        self.assertEqual(found["turn"], 4)
        self.assertEqual(found["reason"], A1FEDF99_REASON)
        self.assertEqual(found["problem"]["code"], "engine_missing")

    def test_a_model_turn_after_a_fallback_has_no_mark(self):
        from app.world import last_turn_fallback

        self.assertIsNone(last_turn_fallback(self._history(3, 4), 4))
        self.assertIsNone(last_turn_fallback([], 4))
        self.assertIsNone(last_turn_fallback(self._history(4, 4), 0))

    def test_resume_carries_the_mark(self):
        from app.world import resume_snapshot

        snap = resume_snapshot({"history": self._history(4, 4), "turn_summaries": [], "settings": {}})
        self.assertEqual(snap["last_fallback"]["reason"], A1FEDF99_REASON)
        snap = resume_snapshot({"history": self._history(3, 4), "turn_summaries": [], "settings": {}})
        self.assertIsNone(snap["last_fallback"])

    def test_api_state_carries_resume_for_the_live_viewer(self):
        from app import main

        state = {"history": self._history(4, 4), "turn_summaries": [], "settings": {}}
        with mock.patch.object(main, "get_state", return_value=state):
            out = main.api_state()
        self.assertEqual(out["resume"]["last_fallback"]["turn"], 4)

    def test_the_page_draws_the_mark_on_every_path(self):
        source = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        restore = source[source.index("function restoreLastTurnPanels"):]
        restore = restore[: restore.index("\n}\n")]
        self.assertIn("state?.resume", restore)
        self.assertIn("last_fallback", restore)
        self.assertIn("fallbackTurnMarkHtml(fallback)", restore)
        self.assertIn("updateModelFallbackBanner(fallback)", restore)
        display = source[source.index("function displayTurnPayload"):]
        display = display[: display.index("\n}\n")]
        self.assertIn("updateModelFallbackBanner(fallback)", display)
        self.assertEqual(display.count("fallbackTurnMarkHtml(fallback)"), 2, "animated and plain draws both mark it")
        self.assertIn(".fallbackTurnMark", source[source.index("const TTS_META_SELECTOR"):][:300], "the mark is not read aloud")


class TestTheTurnPayloadNamesTheProblem(unittest.TestCase):
    def test_play_turn_puts_fallback_problem_in_the_payload(self):
        source = (ROOT / "app" / "world.py").read_text(encoding="utf-8")
        self.assertIn('"fallback_problem": _fallback_problem(fallback_reason) if used_fallback else None', source)
        self.assertIn('f"{FALLBACK_JOURNAL_PREFIX}{reason}"', source, "the journal row resume reads is written with the same prefix")


if __name__ == "__main__":
    unittest.main()
