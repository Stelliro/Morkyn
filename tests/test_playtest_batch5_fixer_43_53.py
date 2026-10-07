"""
Playtest #43 / #45 / #48 / #53, judged on the live writer-off shapes.

#43a  Under AI_RPG_DSL_SKIP_VERIFY=1 the skip waited on the verifier's summed
      certainty, which never reached 0.6 (33 of 33 live turns). The skip now
      reads what the draft changes.
#43b  The engine's conversation footer ("Conversation (engine decided) - the
      player is talking to ...") was classified with the player's line, so every
      turn was a conversation turn.
#43c  The verify prompt policed narration length, and the DSL parser's skipped
      malformed-op notes reached the verifier as draft issues; both produced
      long "revise" replies that rewrote prose and fixed no fact.
#45   The gear and vibe harmonizer overwrote an explicit "nameless drifter"
      with "transmigrated" ("awoke in" matched "woke in").
#48   Trace files were named by turn only, so a second game overwrote the first.
#53   The world-facts ask list was drawn unseeded, and no model call carried a
      seed, so one form and one campaign seed gave two worlds.

Live texts are copied verbatim into tests/fixtures/playtest_batch5_fixer_43_53.json
from scratchpad\\smoke (ab/A, ab/B, batch4_r1).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn_b5fx_"))
os.environ.update(isolated_data_env(str(_TMP)))
for _key, _name in (
    ("AI_RPG_IDEA_BANK", "idea_bank.json"),
    ("AI_RPG_LAUNCHER_PREFS", "launcher_prefs.json"),
    ("AI_RPG_SKILL_LIBRARY", "skill_library.json"),
):
    os.environ.setdefault(_key, str(_TMP / _name))
os.environ.setdefault("AI_RPG_PACK_DIR", str(_TMP / "packs"))
assert "STELLIROS_WORKSHOP" not in os.environ["AI_RPG_DB"]
# The user's launcher env. Patched per test so the rest of the suite keeps its own.
WRITER_OFF = {
    "AI_RPG_NARRATION_PIPELINE": "0",
    "AI_RPG_NARRATION_PIPELINE_CONSOLIDATE": "1",
    "AI_RPG_FAST_VERIFICATION": "1",
    "AI_RPG_DSL_SKIP_VERIFY": "1",
    "AI_RPG_DRAFT_MODE": "dsl",
}

from app import db, llm, mle, narration_pipeline, prompts, rng, turn_dsl, world, world_facts  # noqa: E402
from app.db import connect  # noqa: E402
from app.starter_logic import fact_check_starter_loadout  # noqa: E402

LIVE = json.loads((ROOT / "tests" / "fixtures" / "playtest_batch5_fixer_43_53.json").read_text(encoding="utf-8"))
SHORT = "You walk on. " * 40  # ~520 characters: most live DSL drafts before the depth retry
LONG = "You walk on, slow. " * 70


def _use_db(tag: str) -> None:
    os.environ["AI_RPG_DB"] = str(_TMP / f"{tag}.db")
    rng.reset_seed_cache()
    db.init_db()


def _set_campaign_seed(seed: int) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('campaign_rng_seed', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (json.dumps(seed),),
        )
    rng.reset_seed_cache()


class DslSkipReadsWhatTheDraftChanges(unittest.TestCase):
    """#43a: the skip setting decides from the draft's changes, not the summed certainty."""

    def setUp(self):
        self._env = mock.patch.dict(os.environ, WRITER_OFF)
        self._env.start()

    def tearDown(self):
        self._env.stop()

    def _live(self, key):
        row = LIVE[key]
        return row["draft_turn"], row["verification_policy"]

    def test_live_talk_turns_with_only_records_skip(self):
        # ab/A/g1 t2 (conversations, events, npcs; cert 0.2), ab/A/g2 t6
        # (conversations, npcs; cert 0.28), batch4_r1 t5 (conversations, events,
        # npcs; cert 0.47): all verified live, none changes what the player has.
        for key in ("ab_A_g1_t2", "ab_A_g2_t6", "r1_t5"):
            draft, policy = self._live(key)
            self.assertLess(policy["certainty"], 0.6, key)
            self.assertTrue(llm._dsl_turn_safe_to_skip(draft, policy), key)

    def test_live_item_and_move_turns_stay_verified(self):
        # batch4_r1 t4 granted an item; ab/B/g2 t4 moved the player and walked.
        for key in ("r1_t4", "ab_B_g2_t4", "ab_B_g1_t4"):
            draft, policy = self._live(key)
            self.assertFalse(llm._dsl_turn_safe_to_skip(draft, policy), key)

    def test_each_risky_change_is_verified(self):
        confident = {"certainty": 0.99, "blockers": []}
        for draft in (
            {"inventory_changes": [{"name": "nail", "quantity_delta": 1}]},
            {"equipment_changes": [{"item_name": "cloak", "equip": True}]},
            {"equipment_slots": [{"code": "S1"}]},
            {"inventory_capacity_modifiers": [{"code": "C1"}]},
            {"quest_marks": [{"op": "QUEST"}]},
            {"quest_changes": {"new": [{"title": "x"}]}},
            {"skill_changes": [{"name": "Tracking"}]},
            {"ability_updates": [{"name": "Spark"}]},
            {"player": {"gold_delta": -12}},
            {"player": {"gold_band": "-small"}},
            {"player": {"xp_band": "small"}},
            {"player": {"health_band": "-small"}},
            {"player": {"level_delta": 1}},
            {"player": {"move_to_location": "The Ridge"}},
            {"player": {"move_to_location_code": "L4"}},
            {"map_walk": {"direction": "east", "steps": 1}},
        ):
            self.assertFalse(llm._dsl_turn_safe_to_skip(draft, confident), draft)

    def test_unresolved_refs_are_verified(self):
        policy = {"certainty": 0.99, "blockers": ["unresolved_entity_references"]}
        self.assertFalse(llm._dsl_turn_safe_to_skip({"npcs": [{"code": "Q"}]}, policy))

    def test_band_none_and_zero_are_not_changes(self):
        draft = {"player": {"gold_band": "none", "xp_delta": 0, "health_band": "", "move_to_location": None}}
        self.assertTrue(llm._dsl_turn_safe_to_skip(draft, {"certainty": 0.1, "blockers": []}))

    def test_offline_repro_no_changes_short_draft_skips(self):
        # prove43_intent.py: conversation intent, short draft, self_check passed,
        # no state changes scored 0.54 and was sent to verify.
        draft = {
            "narration": SHORT,
            "narration_segments": [{"label": "scene", "text": SHORT}],
            "scene_plan": {"focus_points": ["a"]},
            "self_check": {"passed": True},
            "conversations": [{"x": 1}],
            "events": [{"title": "x"}],
        }
        ctx = {"turn_plan": {"turn_kind": "player_action", "primary_intent": "conversation",
                             "verification_checks": ["npc_knowledge", "relationship_consistency"]}}
        policy = llm._verification_policy(ctx, "I crouch and examine the cracked earth.", draft)
        self.assertTrue(llm._dsl_turn_safe_to_skip(draft, policy))

    def test_short_narration_does_not_lower_the_score(self):
        # Length is the depth retry's job, and the score is taken before it runs.
        ctx = {"turn_plan": {"turn_kind": "player_action", "verification_checks": []}}
        base = {"scene_plan": {"focus_points": ["a"]}, "self_check": {"passed": True}}
        short = llm._verification_policy(ctx, "I look around.", {**base, "narration": SHORT})
        long = llm._verification_policy(ctx, "I look around.", {**base, "narration": LONG})
        self.assertEqual(short["certainty"], long["certainty"])
        self.assertNotIn("narration_depth", short["remaining_checks"])


class IntentComesFromThePlayersLine(unittest.TestCase):
    """#43b: the engine footer is not part of what the player said."""

    def test_live_actions_are_not_conversation(self):
        for key in ("ab_B_g1_t4", "r1_t5", "ab_B_g2_t4"):
            row = LIVE[key]
            self.assertIn("\n\nResolved player references:", row["model_input"], key)
            self.assertEqual(row["turn_plan"]["primary_intent"], "conversation", key)  # what live recorded
            got = world._turn_intent(row["model_input"])
            self.assertEqual(got, world._turn_intent(row["player_input"]), key)
            self.assertNotEqual(got[0], "conversation", key)

    def test_live_talk_turn_is_still_conversation(self):
        row = LIVE["r1_t4"]  # "I crouch and examine the ground ..." is not talk
        self.assertNotEqual(world._turn_intent(row["model_input"])[0], "conversation")
        talk = "Nesta, will you tell me who runs this place?\n\nResolved player references: Conversation (engine decided) - the player is talking to Nesta [[A]]."
        self.assertEqual(world._turn_intent(talk)[0], "conversation")

    def test_the_engine_decision_marks_talk(self):
        # Only the conversation engine's own decision makes a plain line a
        # conversation: someone addressed by this line, not carried over.
        line = "Kael Vorn, what is happening here? Why are these refugees hurrying toward the town?"  # ab/A/g2 t2
        named = {"conversation_turn": {"addressed": ["A"], "rule": "name"}}
        self.assertEqual(world._planned_intent(named, line)[0], "conversation")
        crouch = LIVE["ab_B_g1_t4"]["model_input"]
        partner = {"conversation_turn": {"addressed": ["A"], "rule": "partner"}}
        self.assertEqual(world._planned_intent(partner, crouch)[0], "investigation")
        self.assertEqual(world._planned_intent(named, crouch)[0], "investigation")

    def test_focus_terms_hold_no_footer_words(self):
        row = LIVE["ab_B_g1_t4"]
        text = row["model_input"]
        plan = world._turn_plan(text, {}, world._tokens(text), world._explicit_turn_references(text), {})
        for word in ("engine", "decided", "conversation", "resolved", "references", "answers"):
            self.assertNotIn(word, plan["focus_terms"])
        self.assertIn("footprints", plan["focus_terms"])
        # The engine-resolved code stays a hard reference.
        self.assertIn("A", plan["explicit_references"]["all"])


class VerifierChecksFactsOnly(unittest.TestCase):
    """#43c: no length policing, and engine-handled op notes are not draft issues."""

    def test_verify_prompts_do_not_police_length(self):
        for prompt in (prompts.VERIFY_PROMPT, prompts.COMPACT_VERIFY_PROMPT):
            self.assertNotIn("1000", prompt)
            self.assertNotIn("visible characters", prompt)

    def test_live_malformed_index_line_is_not_a_draft_issue(self):
        for key in ("ab_B_g2_t3", "ab_A_g1_t5"):
            row = LIVE[key]
            self.assertTrue(any("INDEX requires" in i for i in row["draft_turn"]["self_check"]["issues_found"]), key)
            turn = turn_dsl.parse_dsl_turn(row["draft_dsl_raw"], player_input=row["player_input"])
            self.assertEqual(turn["_dsl"]["malformed_ops"], 1, key)
            self.assertEqual(turn["self_check"]["issues_found"], [], key)
            self.assertTrue(turn["self_check"]["passed"], key)
            self.assertTrue(any("INDEX requires" in n for n in turn["_dsl"]["malformed_op_notes"]), key)
            shown = llm._prompt_draft(turn)
            self.assertNotIn("INDEX requires", json.dumps(shown), key)


class ExplicitBackstoryModeIsKept(unittest.TestCase):
    """#45: the player's canon mode is authoritative."""

    BODY = LIVE["r1_g2_setup"]["body"]

    def _check(self, mode, story):
        return fact_check_starter_loadout(
            starter_equipment=self.BODY["starter_equipment"],
            appearance=self.BODY["appearance"],
            backstory_mode=mode,
            memory_policy=self.BODY["memory_policy"],
            character_backstory=story,
            intent={"isekai": False, "genre": self.BODY["world_style"]},
            world_style=self.BODY["world_style"],
            tech_level=self.BODY["tech_level"],
            magic_level=self.BODY["magic_level"],
            special_ability_origin=self.BODY.get("special_ability_origin") or "",
            apply_fixes=True,
        )

    def test_live_nameless_drifter_stays(self):
        self.assertEqual(LIVE["r1_g2_setup"]["stored_backstory_mode"], "transmigrated")  # what live stored
        report = self._check("nameless drifter", self.BODY["character_backstory"])
        self.assertEqual(report["backstory_mode"], "nameless drifter")
        self.assertNotIn("transmigrated", str(report.get("summary") or ""))

    def test_no_canon_mode_is_overwritten_by_an_arrival_story(self):
        story = "She died in a crash at her desk job and woke up in another world on a dirt road this morning."
        for mode in ("nameless drifter", "amnesia", "hidden", "fragmented memories"):
            self.assertEqual(self._check(mode, story)["backstory_mode"], mode, mode)

    def test_known_mode_with_an_arrival_story_is_still_promoted(self):
        story = "She died in a crash at her desk job and woke up in another world on a dirt road this morning."
        self.assertEqual(self._check("known", story)["backstory_mode"], "transmigrated")

    def test_start_playthrough_stores_the_sent_mode(self):
        _use_db("b45")
        state = world.start_playthrough(dict(self.BODY))
        self.assertEqual(state["player"]["backstory_mode"], "nameless drifter")


class TracesKeepEachGame(unittest.TestCase):
    """#48: two games in one trace dir keep both sets of traces."""

    def test_second_game_does_not_overwrite_the_first(self):
        _use_db("b48")
        trace_dir = Path(os.environ["AI_RPG_MODEL_TRACE_DIR"])
        paths = []
        for seed, label in ((5017740712799915436, "game one input"), (3169988849100458541, "game two input")):
            _set_campaign_seed(seed)
            paths.append(world._write_model_trace_file(2, "player", label, "", {}, {"narration": label}, False, ""))
        self.assertNotEqual(paths[0], paths[1])
        inputs = sorted(
            json.loads(p.read_text(encoding="utf-8"))["player_input"] for p in trace_dir.glob("turn-*-player.json")
        )
        self.assertEqual(inputs, ["game one input", "game two input"])

    def test_ledger_names_carry_the_campaign(self):
        _use_db("b48l")
        _set_campaign_seed(5017740712799915436)
        one = narration_pipeline.ledger_file_name(3)
        _set_campaign_seed(3169988849100458541)
        two = narration_pipeline.ledger_file_name(3)
        self.assertNotEqual(one, two)
        self.assertTrue(one.startswith("turn-") and one.endswith("-narration-ledger.json"))


class SetupDrawsAreSeeded(unittest.TestCase):
    """#53: one form and one campaign seed ask the same things with the same seeds."""

    OPTS = {"world_style": "frontier dark fantasy", "magic_level": "rare", "tech_level": "iron age",
            "faction_pressure": "guild, crown"}

    def _refine_prompts(self, seed):
        _use_db(f"b53_{seed}")
        _set_campaign_seed(seed)
        seen = []

        def fake_dispatch(config, system_prompt, user_prompt, **kwargs):
            seen.append((user_prompt, kwargs.get("seed")))
            return ""

        with mock.patch.object(llm, "_chat_content_dispatch", side_effect=fake_dispatch), \
                mock.patch.object(world_facts, "post_start_model_allowed", return_value=True), \
                mock.patch.dict(os.environ, {"AI_RPG_POST_START_MODEL": "on"}):
            with connect() as conn:
                conn.execute(
                    "INSERT INTO settings (key, value) VALUES ('playthrough_options', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (json.dumps(self.OPTS),),
                )
            world_facts.run_post_start_passes()
        return [row for row in seen if "write_facts_about" in row[0]]

    def test_same_campaign_same_asks_and_seed(self):
        first = self._refine_prompts(5017740712799915436)
        second = self._refine_prompts(5017740712799915436)
        self.assertEqual(len(first), 1)
        self.assertEqual(first, second)
        self.assertIsNotNone(first[0][1])

    def test_other_campaign_draws_fresh(self):
        one = self._refine_prompts(5017740712799915436)
        two = self._refine_prompts(3169988849100458541)
        self.assertNotEqual(one[0][1], two[0][1])

    def test_proficiency_pass_shows_the_same_name_shapes(self):
        # Live (two seeded setups of the g1 form): the proficiency settle still
        # differed, because its name-shape examples were drawn unseeded.
        from app import proficiencies

        _use_db("b53_prof")
        _set_campaign_seed(5017740712799915436)
        rng.campaign_seed()
        opts = {**self.OPTS, "custom_skills": "Whispering Wound (start rank F; tracked by healing trials)"}
        first = proficiencies.settle_prompt(opts, [], "")
        self.assertEqual(first, proficiencies.settle_prompt(opts, [], ""))
        items = [{"phrase": "healing trials"}]
        self.assertEqual(proficiencies.rename_prompt(items, opts), proficiencies.rename_prompt(items, opts))

    def test_seed_reaches_the_in_process_model(self):
        calls = []

        resets = []

        class FakeModel:
            def token_eos(self):
                return 2

            def reset(self):
                resets.append(1)

            def create_chat_completion(self, **kwargs):
                calls.append(kwargs)
                return {"choices": [{"message": {"content": "ok"}}]}

        with mock.patch.object(mle, "_banned_ids", return_value=()), \
                mock.patch.object(mle, "_script_ban_ids", return_value=()):
            mle._generate(FakeModel(), "x.gguf", "s", "u", timeout=0, temperature=0.4, max_tokens=None,
                          response_format=None, hide_words=None, keep_words=None, seed=1234)
            mle._generate(FakeModel(), "x.gguf", "s", "u", timeout=0, temperature=0.4, max_tokens=None,
                          response_format=None, hide_words=None, keep_words=None)
        self.assertEqual(calls[0].get("seed"), 1234)
        self.assertNotIn("seed", calls[1])
        # Live: one prompt and one seed asked twice in a row gave two answers,
        # because the cached prefix changed the logits. A seeded call runs its
        # whole prompt; an unseeded (turn) call keeps the cache.
        self.assertEqual(len(resets), 1)

    def test_seeded_block_gives_each_call_its_own_seed(self):
        seen = []

        def fake_mle_chat(system_prompt, user_prompt, **kwargs):
            seen.append(kwargs.get("seed"))
            return "{}"

        config = {"provider": "mle", "mle_model": "x"}
        with mock.patch("app.mle.chat", side_effect=fake_mle_chat):
            for _ in range(2):
                with llm.seeded_model_calls(77, "setup"):
                    llm._chat_content_dispatch(config, "s", "u")
                    llm._chat_content_dispatch(config, "s", "u")
            llm._chat_content_dispatch(config, "s", "u")
        self.assertEqual(seen[:2], seen[2:4])
        self.assertNotEqual(seen[0], seen[1])
        self.assertIsNone(seen[4])

    def test_llama_cpp_body_carries_the_seed(self):
        bodies = []

        def fake_urlopen(request, timeout):
            bodies.append(json.loads(request.data.decode("utf-8")))
            return {"choices": [{"message": {"content": "{}"}}]}

        config = {"provider": "llama_cpp", "llama_cpp_base_url": "http://localhost:1"}
        with mock.patch.object(llm, "_urlopen_json", side_effect=fake_urlopen):
            llm._chat_content_openai_compatible(config, "s", "u", 10, 0.4, 100, seed=99)
            llm._chat_content_openai_compatible(config, "s", "u", 10, 0.4, 100)
        self.assertEqual(bodies[0].get("seed"), 99)
        self.assertNotIn("seed", bodies[1])


if __name__ == "__main__":
    unittest.main()
