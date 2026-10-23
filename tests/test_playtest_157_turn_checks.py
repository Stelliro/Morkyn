"""The turn checker asks the engine's questions one at a time (playtest #157 b, #77, #156).

cc87dd29 (Linux .deb playtest, Hermes 3 8B): the broad verifier listed eight
rules that do not exist and passed (T5), flagged the laser rifle the player's
own line names and passed (T8/T9), and in T9 patched the player's shot into a
punch while saying so in its own issues. app/turn_checks.py replaces the broad
verdict: one fixed question with its fact (the player's line), yes or no, and
on a no one sentence is rewritten toward the player's line. Nothing else in
the turn is patched.

a1fedf99 (same playtest): eight turns ran on the offline narrator. The turn
payload and the save now say so with the problem's tips fitted to the build.
"""
from __future__ import annotations

import os
import sys
import tempfile
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
# The final prose of T9: the verifier's patch made the shot a punch.
T9_PROSE = (
    "The morning light filters through the grimy clinic windows, casting a dim glow over the tense standoff "
    "between you and Beth [[B]]. She barely manages to dodge your punch, stumbling backwards as she grips the "
    "scalpel tightly. \"What the hell?\" she asks, her voice shaking slightly. \"I'm the doctor here, not the "
    "damn hostile! You're not the hostile, but this is a dangerous place. I have to be careful!\"\n\n"
    "\"I don't know what you're talking about,\" Beth [[B]] replies, her eyes darting between you and the door. "
    "\"I'm just trying to help people here. This place is dangerous, and I have to stay on my guard!\" The red "
    "dot of your laser rifle's sights hovers menacingly above Beth [[B]]'s face as she staggers backwards, her "
    "eyes darting between the weapon and the door. The clinic is deathly silent as you and Beth [[B]] stand in "
    "a tense stalemate, the only sound the faint beeping from medical monitors."
)
# The T9 draft, before the verifier: the act is the player's.
T9_DRAFT_PROSE = (
    "You aim the laser rifle at Beth. She eyes you warily, gripping the scalpel in her hand. \"What the hell?\" "
    "she asks. \"I'm the doctor here, not the... But you're not the... Wait, what is it you think you're doing? "
    "You'd better have a good reason for this.\" She's not backing down, but her eyes flick to the door, gauging "
    "if she can make a run for it."
)
# The T9 verifier reply's issues, as recorded.
T9_VERDICT = {
    "verdict": "revise",
    "issues": [
        "The player attacked Beth with a laser rifle, but there is no laser rifle in the player's inventory.",
        "The patch changes the player's action to a punch rather than a laser rifle attack, which is a smaller "
        "escalation that matches the player's current inventory and avoids a contradiction.",
    ],
    "patch": {"narration": T9_PROSE.replace("The red dot of your laser rifle's sights", "Your fist")},
}

T5_LINE = (
    "I BRUTALLY SNAP HER NECK AND THEN PROCEED TO BURN THE CLINIC TO THE GROUND, AND THEN, MAKE SURE THERE ARE NO "
    "SURVIVORS IN THE CLINIC, AND AFTER THAT, I GO THROUGH THE CITY AND MASSACRE EVERYONE, GUNNING THEM ALL DOWN, "
    "LEAVING NO SURVIVORS"
)
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

A1FEDF99_REASON = (
    "MLE could not load /home/stelliro/.local/share/morkyn/data/mle-models/Hermes-3-Llama-3.1-8B.Q4_K_M.gguf at "
    "context 24576. context 24576: MLE could not import llama_cpp to load "
    "/home/stelliro/.local/share/morkyn/data/mle-models/Hermes-3-Llama-3.1-8B.Q4_K_M.gguf. Failed to load shared "
    "library '/home/stelliro/.local/share/morkyn/runtime/llama-cpp-cuda/site/llama_cpp/lib/libllama.so': Failed to "
    "load dynlib/dll '/home/stelliro/.local/share/morkyn/runtime/llama-cpp-cuda/site/llama_cpp/lib/libllama.so'. "
    "Most likely this dynlib/dll was not found when the application was frozen. Accept the 8192-token fallback to "
    "continue."
)


class ScriptedAsk:
    """Answers each phase from a script and keeps every (phase, user prompt)."""

    def __init__(self, **replies):
        self.replies = replies
        self.calls: list[tuple[str, str, str, int]] = []

    def __call__(self, system, user, phase, max_tokens):
        self.calls.append((phase, system, user, max_tokens))
        reply = self.replies.get(phase, "")
        if isinstance(reply, Exception):
            raise reply
        return reply


def _turn(prose: str) -> dict:
    return {
        "narration": prose,
        "narration_segments": [{"label": "paragraph", "text": p} for p in prose.split("\n\n")],
        "self_check": {"passed": True, "issues_found": [], "corrections_made": ["deterministic_turn_dsl_transcoder"]},
    }


class TestThePlayerActQuestion(unittest.TestCase):
    def test_t9_the_punch_is_rewritten_back_to_the_players_shot(self):
        rewrite = "She barely manages to dodge your laser blast, stumbling backwards as she grips the scalpel tightly."
        ask = ScriptedAsk(check_act="No", check_act_pick="2", check_act_rewrite=rewrite)
        from app.turn_dsl import player_line_of

        result, report = turn_checks.check_turn(_turn(T9_PROSE), player_line_of(T9_INPUT), ask)
        self.assertIn("laser blast", result["narration"])
        self.assertNotIn("punch", result["narration"])
        # Only that sentence changed: the rest of the scene is as written.
        self.assertEqual(result["narration"].replace(rewrite, ""), T9_PROSE.replace(
            "She barely manages to dodge your punch, stumbling backwards as she grips the scalpel tightly.", ""))
        self.assertEqual(result["narration_segments"][0]["text"].split(". ")[0], T9_PROSE.split(". ")[0])
        self.assertTrue(result["self_check"]["passed"])
        self.assertEqual(result["self_check"]["issues_found"], [])
        self.assertIn("deterministic_turn_dsl_transcoder", result["self_check"]["corrections_made"])
        self.assertTrue(any("Rewrote sentence 2" in c for c in result["self_check"]["corrections_made"]))
        self.assertEqual(report["checks"][0]["repair"], "rewrote_sentence")

    def test_the_questions_carry_their_fact_and_no_codes(self):
        ask = ScriptedAsk(check_act="no", check_act_pick="2", check_act_rewrite="She barely dodges your laser shot.")
        from app.turn_dsl import player_line_of

        turn_checks.check_turn(_turn(T9_PROSE), player_line_of(T9_INPUT), ask)
        phases = [call[0] for call in ask.calls]
        self.assertEqual(phases, ["check_act", "check_act_pick", "check_act_rewrite"])
        act_prompt = ask.calls[0][2]
        self.assertIn('The player wrote: "i shoot Beth with my laser rifle"', act_prompt)
        self.assertIn("dodge your punch", act_prompt)
        self.assertNotIn("[[", act_prompt)
        self.assertNotIn("Resolved player references", act_prompt)
        self.assertTrue(act_prompt.rstrip().endswith("Answer yes or no."))
        pick_prompt = ask.calls[1][2]
        self.assertIn("2. She barely manages to dodge your punch", pick_prompt)
        self.assertIn("Answer with its number.", pick_prompt)
        self.assertIn("Sentence: She barely manages to dodge your punch", ask.calls[2][2])
        for _phase, system, _user, max_tokens in ask.calls:
            self.assertEqual(system, turn_checks.ASK_SYSTEM)
            self.assertLessEqual(max_tokens, 200)

    def test_t5_a_yes_passes_with_no_invented_rule(self):
        ask = ScriptedAsk(check_act="Yes.")
        result, report = turn_checks.check_turn(_turn(T5_PROSE), T5_LINE, ask)
        self.assertEqual(result["narration"], T5_PROSE, "the massacre stands as the player wrote it")
        self.assertTrue(result["self_check"]["passed"])
        self.assertEqual(result["self_check"]["issues_found"], [])
        for rule in T5_INVENTED_RULES:
            self.assertNotIn(rule, result["self_check"]["issues_found"])
        self.assertEqual(len(ask.calls), 1, "one question, no repair on a yes")
        self.assertIn("player_act=yes", result["self_check"]["reference_check"])

    def test_t13_a_scene_without_the_act_gets_one_sentence_rewritten(self):
        rewrite = "You grab Dr. Beth and rip her head from her shoulders, her spine still attached."
        ask = ScriptedAsk(check_act="no", check_act_pick="1", check_act_rewrite=rewrite)
        from app.turn_dsl import player_line_of

        result, _report = turn_checks.check_turn(_turn(T13_PROSE), player_line_of(T13_INPUT), ask)
        first = result["narration"].split(". Beth")[0]
        # The code the sentence had is put back after the name.
        self.assertIn("Dr. Beth [[B]] and rip her head", result["narration"])
        self.assertNotIn("You approach Dr. Beth [[B]] cautiously", result["narration"])
        self.assertIn("Beth [[B]] looks you over warily", result["narration"])
        self.assertTrue(first)
        self.assertTrue(result["self_check"]["passed"])

    def test_a_no_that_cannot_be_repaired_is_not_passed(self):
        for replies in (
            {"check_act": "no", "check_act_pick": "none"},
            {"check_act": "no", "check_act_pick": "99"},
            {"check_act": "no", "check_act_pick": "2", "check_act_rewrite": ""},
            {"check_act": "no", "check_act_pick": "2", "check_act_rewrite": "x" * 900},
            {"check_act": "no", "check_act_pick": "2", "check_act_rewrite": "She barely manages to dodge your punch, stumbling backwards as she grips the scalpel tightly."},
            {"check_act": "no", "check_act_pick": llm.LlmError("timed out")},
        ):
            with self.subTest(replies=replies):
                result, report = turn_checks.check_turn(_turn(T9_PROSE), "i shoot Beth with my laser rifle", ScriptedAsk(**replies))
                self.assertEqual(result["narration"], T9_PROSE, "nothing is cut or replaced")
                self.assertFalse(result["self_check"]["passed"])
                self.assertEqual(len(result["self_check"]["issues_found"]), 1)
                self.assertIn("i shoot Beth with my laser rifle", result["self_check"]["issues_found"][0])
                self.assertTrue(report["usable"], "the question itself was answered")

    def test_an_unreadable_answer_is_not_checked_and_not_passed(self):
        for reply in ("Maybe the player", "", llm.LlmError("connection refused")):
            with self.subTest(reply=reply):
                result, report = turn_checks.check_turn(_turn(T9_PROSE), "i shoot Beth", ScriptedAsk(check_act=reply))
                self.assertEqual(result["narration"], T9_PROSE)
                self.assertFalse(result["self_check"]["passed"])
                self.assertIn("Not checked", result["self_check"]["issues_found"][0])
                self.assertFalse(report["usable"])

    def test_an_engine_request_asks_nothing(self):
        for line in ("", "__opening_scene_request__: Begin the playthrough"):
            with self.subTest(line=line):
                from app.turn_dsl import player_line_of

                ask = ScriptedAsk(check_act="no")
                result, report = turn_checks.check_turn(_turn(T5_PROSE), player_line_of(line), ask)
                self.assertEqual(ask.calls, [])
                self.assertTrue(result["self_check"]["passed"])
                self.assertEqual(report["checks"], [])
                self.assertTrue(report["usable"])

    def test_other_phrasings_of_an_answer(self):
        self.assertEqual(turn_checks.yes_no("Yes, the player shoots."), "yes")
        self.assertEqual(turn_checks.yes_no("**No**"), "no")
        self.assertEqual(turn_checks.yes_no("nope"), "")
        self.assertEqual(turn_checks.sentence_number("Sentence 3.", 4), 3)
        self.assertEqual(turn_checks.sentence_number("5", 4), 0)
        self.assertEqual(turn_checks.clean_rewrite('Sentence: "You fire."', "You aim."), "You fire.")
        self.assertEqual(turn_checks.clean_rewrite("You fire.\n\nI changed the verb.", "You aim."), "You fire.")

    def test_retag_puts_back_each_code_once(self):
        self.assertEqual(
            turn_checks.retag("You shoot Beth, and Beth falls.", "You aim at Beth [[B]]."),
            "You shoot Beth [[B]], and Beth falls.",
        )
        self.assertEqual(turn_checks.retag("You shoot Beth [[B]].", "You aim at Beth [[B]]."), "You shoot Beth [[B]].")
        self.assertEqual(turn_checks.retag("You fire at her.", "You aim at Beth [[B]]."), "You fire at her.")


class TestTheAsksAreRecorded(unittest.TestCase):
    """Each ask is a model call with its prompt, raw reply and seconds in the trace and model_usage."""

    def setUp(self):
        llm.reset_verifier_breaker()

    tearDown = setUp

    def test_prompt_reply_and_timing_reach_trace_and_usage(self):
        replies = iter(["No", "2", "She barely manages to dodge your laser blast."])
        usage: list[dict] = []
        trace: list[dict] = []
        with mock.patch.object(llm, "_chat_content", side_effect=lambda *a, **k: next(replies)):
            result = llm._run_turn_checks(_turn(T9_PROSE), T9_INPUT, 60, usage, trace)
        self.assertEqual([u["phase"] for u in usage], ["check_act", "check_act_pick", "check_act_rewrite"])
        requests = [e for e in trace if e.get("event") == "request"]
        responses = [e for e in trace if e.get("event") == "response"]
        self.assertEqual([e["phase"] for e in requests], ["check_act", "check_act_pick", "check_act_rewrite"])
        self.assertIn("i shoot Beth with my laser rifle", requests[0]["user_prompt"])
        self.assertEqual(requests[0]["system_prompt"], turn_checks.ASK_SYSTEM)
        self.assertEqual([e["raw_content"] for e in responses], ["No", "2", "She barely manages to dodge your laser blast."])
        self.assertTrue(all("duration_seconds" in e for e in responses))
        summary = next(e for e in trace if e.get("event") == "turn_checks")
        self.assertEqual(summary["checks"][0]["answer"], "no")
        self.assertIn("laser blast", result["narration"])

    def test_three_unreadable_answers_trip_the_breaker(self):
        with mock.patch.object(llm, "_chat_content", return_value="I think so"):
            for _ in range(3):
                llm._run_turn_checks(_turn(T9_PROSE), T9_INPUT, 60, [], [])
        self.assertTrue(llm.verifier_is_disabled())

    def test_a_turn_check_never_claims_the_verification_memory(self):
        from app.world import _verified_memory_source

        result = {"_model_usage": [{"phase": "draft_dsl"}, {"phase": "check_act"}, {"phase": "check_act_pick"}]}
        self.assertEqual(_verified_memory_source(result), "", "one act question does not verify the turn plan's checklist")


class TestThePipelineNeverPatchesThePlayersAct(unittest.TestCase):
    """The default turn sends no broad verdict, so its patch cannot turn the shot into a punch (T9)."""

    _CONTEXT = {"player": {"name": "Ash"}, "turn_plan": {"turn_kind": "player_action"}}

    def setUp(self):
        llm.reset_verifier_breaker()
        os.environ.pop("AI_RPG_BROAD_VERIFIER", None)
        os.environ["AI_RPG_FAST_VERIFICATION"] = "0"

    def tearDown(self):
        os.environ.pop("AI_RPG_FAST_VERIFICATION", None)
        llm.reset_verifier_breaker()

    def _run(self, act_answer: str):
        calls: list[tuple[str, str]] = []

        def fake_text(system_prompt, user_prompt, **kwargs):
            phase = kwargs.get("phase")
            calls.append((phase, user_prompt))
            if phase == "draft_dsl":
                return f"===NAR===\n{T9_DRAFT_PROSE}\n===OPS===\n"
            if phase == "check_act":
                return act_answer
            return T9_DRAFT_PROSE

        def fake_json(system_prompt, user_prompt, **kwargs):
            calls.append((kwargs.get("phase"), user_prompt))
            return dict(T9_VERDICT)

        with mock.patch.object(llm, "_chat_text", side_effect=fake_text), mock.patch.object(
            llm, "_chat_json", side_effect=fake_json
        ), mock.patch.object(llm, "draft_mode_enabled", return_value=True), mock.patch.object(
            llm, "pipeline_enabled", return_value=False
        ):
            result = llm.generate_turn(dict(self._CONTEXT), T9_INPUT)
        return result, calls

    def test_t9_the_draft_shot_stands_and_no_verdict_is_asked(self):
        result, calls = self._run("yes")
        phases = [phase for phase, _ in calls]
        self.assertNotIn("verify", phases)
        self.assertIn("check_act", phases)
        self.assertIn("laser rifle", result["narration"])
        self.assertNotIn("Your fist", result["narration"])
        self.assertTrue(result["self_check"]["passed"])
        for issue in T9_VERDICT["issues"]:
            self.assertNotIn(issue, result["self_check"]["issues_found"])

    def test_the_checker_reads_the_prose_after_the_quality_passes(self):
        _result, calls = self._run("yes")
        phases = [phase for phase, _ in calls]
        self.assertLess(phases.index("draft_dsl"), phases.index("check_act"))
        self.assertEqual(phases[-1], "check_act", "the question is the turn's last model call")

    def test_the_broad_verdict_is_still_there_behind_its_switch(self):
        os.environ["AI_RPG_BROAD_VERIFIER"] = "1"
        try:
            _result, calls = self._run("yes")
        finally:
            os.environ.pop("AI_RPG_BROAD_VERIFIER", None)
        phases = [phase for phase, _ in calls]
        self.assertIn("verify", phases)
        self.assertNotIn("check_act", phases)


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
