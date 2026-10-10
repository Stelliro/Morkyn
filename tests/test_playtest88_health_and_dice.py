"""Playtest #88: the 59-turn Deeper-idea run on the 8B.

Health reached 0 at turn 15 and the game played 44 more turns. Every "ask X
about Y" rolled an untrained contested Persuasion check (DC 15-20 against an
average stranger); 28 of 49 misses were promoted to critical failures, each a
limb injury from talking; 35 "Injured ..." rows stacked with no merge; the
draft and the verifier were shown name, title and race and never the health;
verification memory keyed on the player's words and never matched; the idea
model had no memory of its own ideas and repeated them.

These tests pin the engine side of each fix without a model.
"""
from __future__ import annotations

import os
import random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-playtest88-"))
_ENV = isolated_data_env(str(_TMP))
os.environ.update(_ENV)

from app import llm, prompts, world  # noqa: E402


_SAVED_ENV: dict[str, str | None] = {}


def setUpModule():
    # Every module that imports isolated_data_env sets the process env at
    # import; the last import wins, so re-apply ours before the turns below
    # write a database, traces and a journal, and hand the previous env back
    # after, so the module that set it still finds its own files.
    _SAVED_ENV.update({key: os.environ.get(key) for key in _ENV})
    os.environ.update(_ENV)


def tearDownModule():
    for key, value in _SAVED_ENV.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
from app.skill_checks import apply_check_to_turn, infer_check_from_action, resolve_check  # noqa: E402

VAEL = {"code": "B", "name": "Vael", "attitude": "guarded", "rank": "F", "stat_profile": {}}
CTX = {"current_location": {"id": 6, "npcs": [VAEL]}}
AVERAGE = {"name": "Vael", "rank": "F", "stats": {}}


def _roll(skill: str, seed: int, **kw):
    return resolve_check(skill_code=skill, rng=random.Random(seed), **kw)


def _first(skill: str, predicate, **kw):
    for seed in range(4000):
        check = _roll(skill, seed, **kw)
        if predicate(check):
            return check
    raise AssertionError(f"no roll of {skill} matched in 4000 seeds")


class PlainTalkIsRoutine(unittest.TestCase):
    def test_a_question_rolls_routine_persuasion(self):
        for line in ("ask Vael about the Irond's true purpose", "greet Vael", "talk to Vael about the well"):
            check = infer_check_from_action(line, CTX)
            self.assertEqual(check["skill_code"], "persuasion", line)
            self.assertTrue(check.get("routine"), line)
            self.assertTrue(check.get("plain_talk"), line)

    def test_pushing_someone_keeps_the_full_roll(self):
        for line in ("convince Vael to hand over the key", "persuade Vael to come along", "haggle with Vael over the price"):
            check = infer_check_from_action(line, CTX)
            self.assertFalse(check.get("routine"), line)
            self.assertFalse(check.get("plain_talk"), line)

    def test_a_routine_ask_only_goes_wrong_on_a_natural_one(self):
        outcomes = {}
        for seed in range(600):
            check = _roll("persuasion", seed, opposition=AVERAGE, routine=True)
            outcomes.setdefault(check["outcome"], 0)
            outcomes[check["outcome"]] += 1
            if check["outcome"] == "critical_failure":
                self.assertEqual(check["natural"], 1)
        # A natural 1 is one roll in twenty, never half of them.
        self.assertLess(outcomes.get("critical_failure", 0) / 600, 0.09)


class ContestedDcIsAroundTheSkillBase(unittest.TestCase):
    def test_an_average_stranger_is_not_harder_than_a_static_check(self):
        dcs = [_roll("persuasion", seed, opposition=AVERAGE)["dc"] for seed in range(80)]
        # persuasion base 12; power 8 +/- 3 sway: 9..15, never the old 15-20.
        self.assertGreaterEqual(min(dcs), 8)
        self.assertLessEqual(max(dcs), 15)
        self.assertIn(12, dcs)

    def test_a_strong_opponent_still_raises_the_mark(self):
        strong = {"name": "Captain", "rank": "A", "stats": {"charisma": 16}}
        dcs = [_roll("persuasion", seed, opposition=strong)["dc"] for seed in range(80)]
        self.assertGreater(sum(dcs) / len(dcs), 16)


class MishapsAreForTheNaturalOne(unittest.TestCase):
    def test_a_miss_by_four_is_a_plain_failure(self):
        check = _first("persuasion", lambda c: c["natural"] != 1 and -6 <= c["margin"] <= -4, opposition=AVERAGE)
        self.assertEqual(check["outcome"], "failure")
        self.assertFalse(check["mishap"])
        self.assertIsNone(check["injury"])

    def test_a_social_fumble_is_a_blunder_not_a_wound(self):
        check = _first("persuasion", lambda c: c["natural"] == 1, opposition=AVERAGE)
        self.assertEqual(check["outcome"], "critical_failure")
        self.assertTrue(check["mishap"])
        self.assertIsNone(check["injury"])
        self.assertEqual(check["blunder"]["kind"], "social_blunder")
        self.assertIn("Botched Persuasion", check["blunder"]["summary"])
        turn = apply_check_to_turn({}, check)
        self.assertNotIn("condition_changes", turn)
        self.assertNotIn("health_delta", turn.get("player") or {})
        self.assertEqual(turn["journal"][-1]["kind"], "blunder")

    def test_a_bad_physical_miss_costs_a_scratch_and_no_condition(self):
        check = _first("athletics", lambda c: c["mishap"] and c["natural"] != 1)
        self.assertEqual(check["outcome"], "failure")
        self.assertEqual(check["injury"]["health_delta"], -1)
        self.assertFalse(check["injury"]["lasting"])
        turn = apply_check_to_turn({}, check)
        self.assertEqual(turn["player"]["health_delta"], -1)
        self.assertNotIn("condition_changes", turn)

    def test_a_physical_natural_one_leaves_a_lasting_injury(self):
        check = _first("athletics", lambda c: c["natural"] == 1)
        self.assertTrue(check["injury"]["lasting"])
        self.assertLessEqual(check["injury"]["health_delta"], -2)
        turn = apply_check_to_turn({}, check)
        self.assertEqual(len(turn["condition_changes"]), 1)
        self.assertTrue(turn["condition_changes"][0]["name"].startswith("Injured "))


class ConditionsMerge(unittest.TestCase):
    def test_the_same_limb_hurt_again_is_one_row_worse(self):
        rows = world._merge_player_conditions(
            [],
            [{"limb": "side", "combat_penalty": {"attack": -1, "defense": -1}, "severity": False, "summary": "a"}],
            3,
        )
        rows = world._merge_player_conditions(
            rows,
            [{"limb": "side", "combat_penalty": {"attack": -2, "defense": -1}, "severity": True, "summary": "b"}],
            7,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["count"], 2)
        self.assertEqual(rows[0]["penalties"], {"attack": -2, "defense": -1})
        self.assertTrue(rows[0]["severe"])
        self.assertEqual(rows[0]["turn"], 7)

    def test_a_named_lasting_wound_keeps_its_name(self):
        rows = world._merge_player_conditions([], [{"limb": "leg", "name": "Lasting wound (leg)", "severity": True}], 9)
        self.assertEqual(rows[0]["name"], "Lasting wound (leg)")
        self.assertEqual(rows[0]["id"], "wound_leg")


class HealthStateAndRecovery(unittest.TestCase):
    def test_bands(self):
        self.assertEqual(world._health_state(0, 20)["band"], "down")
        self.assertTrue(world._health_state(0, 20)["downed"])
        self.assertEqual(world._health_state(5, 20)["band"], "critical")
        self.assertEqual(world._health_state(10, 20)["band"], "hurt")
        self.assertEqual(world._health_state(14, 20)["band"], "bruised")
        self.assertEqual(world._health_state(20, 20)["band"], "fine")
        state = world._health_state(3, 20, [{"name": "Injured side", "count": 3}, {"name": "Injured leg"}])
        self.assertEqual(state["conditions"], ["Injured side (x3)", "Injured leg"])

    def test_death_rule_parsing(self):
        self.assertEqual(world._death_rule({"death_rules": "lasting injuries"}), "lasting injuries")
        self.assertEqual(world._death_rule({"death_rules": "Permadeath threat"}), "permadeath threat")
        self.assertEqual(world._death_rule({"death_rules": "narrative setback"}), "narrative setback")
        self.assertEqual(world._death_rule({"death_rules": "downed, not deleted"}), "downed, not deleted")
        self.assertEqual(world._death_rule({}), "downed, not deleted")

    def test_recovery_restores_a_quarter_and_marks_by_rule(self):
        downed = {"turn": 15, "limb": "leg"}
        plain = world._downed_recovery(downed, {"death_rules": "downed, not deleted"}, 20, random.Random(1))
        self.assertEqual(plain["health_delta"], 5)
        self.assertIsNone(plain["lasting_injury"])
        self.assertEqual(plain["max_health_delta"], 0)
        lasting = world._downed_recovery(downed, {"death_rules": "lasting injuries"}, 20, random.Random(1))
        self.assertEqual(lasting["lasting_injury"]["name"], "Lasting wound (leg)")
        self.assertTrue(lasting["lasting_injury"]["lasting"])
        setback = world._downed_recovery(downed, {"death_rules": "narrative setback"}, 20, random.Random(1))
        self.assertTrue(setback["setback"])
        threats = [
            world._downed_recovery(downed, {"death_rules": "permadeath threat"}, 20, random.Random(seed))
            for seed in range(60)
        ]
        # A 1-3 on the d20 is the death; the rest come round like anyone else.
        self.assertTrue(any(t.get("died") for t in threats))
        self.assertTrue(any(not t.get("died") and t["health_delta"] == 5 for t in threats))
        self.assertTrue(all("death_roll" in t for t in threats))
        self.assertTrue(all(t["max_health_delta"] == 0 for t in threats))


class ThePromptsCarryTheBody(unittest.TestCase):
    def test_player_view_names_health_and_conditions(self):
        view = prompts._player_view(
            {
                "player": {"name": "Mara Quill", "title": "Courier", "race": "human", "health": 0, "max_health": 20},
                "conditions": [{"name": "Injured side", "count": 8}, {"name": "Injured leg"}],
            }
        )
        self.assertEqual(view["health"], "0/20 (down)")
        self.assertEqual(view["conditions"], ["Injured side (x8)", "Injured leg"])

    def test_mechanics_view_passes_health_state_and_recovery(self):
        view = prompts._mechanics_view(
            {
                "mechanics_context": {
                    "health_state": {"health": 0, "max_health": 20, "band": "down", "conditions": [], "downed": True},
                    "recovery": {
                        "rule": "lasting injuries",
                        "what_happens": "comes round",
                        "health_delta": 5,
                        "max_health_delta": 0,
                        "lasting_injury": {"summary": "Lasting wound (leg): a mark."},
                    },
                }
            }
        )
        self.assertEqual(view["health_state"]["band"], "down")
        self.assertTrue(view["health_state"]["downed"])
        self.assertEqual(view["recovery"]["rule"], "lasting injuries")
        self.assertEqual(view["recovery"]["health_delta"], 5)
        self.assertNotIn("max_health_delta", view["recovery"])
        self.assertIn("Lasting wound", view["recovery"]["lasting_injury"])

    def test_the_rules_tell_the_narrator_about_both(self):
        from app import turn_dsl

        system_rules = Path(prompts.__file__).read_text(encoding="utf-8")
        self.assertIn("mechanics_context.health_state is the player's body", system_rules)
        self.assertIn("mechanics_context.recovery is present", system_rules)
        contract = Path(turn_dsl.__file__).read_text(encoding="utf-8")
        self.assertIn("health_state.downed", contract)
        self.assertIn("mechanics_context.recovery", contract)


class VerificationMemoryKeysOnTheScene(unittest.TestCase):
    def test_two_lines_in_the_same_scene_share_a_signature(self):
        base = {
            "turn_plan": {
                "turn_kind": "player_action",
                "primary_intent": "conversation",
                "secondary_intents": [],
                "explicit_references": {"all": ["B"], "npcs": ["B"]},
                "verification_checks": ["npc_knowledge"],
            },
            "current_location": {"code": "L6"},
            "player": {},
            "settings": {},
            "conversations": [{"id": 1}],
            "relationships": [],
            "events": [],
        }
        first = dict(base, turn_plan=dict(base["turn_plan"], focus_terms=["seal", "markings"]))
        second = dict(base, turn_plan=dict(base["turn_plan"], focus_terms=["irond", "purpose"]))
        sig_a = world._verification_memory_scopes(first)["npc_knowledge"]["context_signature"]
        sig_b = world._verification_memory_scopes(second)["npc_knowledge"]["context_signature"]
        self.assertEqual(sig_a, sig_b)
        self.assertNotIn("focus_terms", world._verification_scope_basis(first, "npc_knowledge"))


class TheIdeasRememberThemselves(unittest.TestCase):
    def _context(self, health: int = 20):
        return {
            "current_location": {"name": "Iron Spire"},
            "last_narration": "Vael [[B]] waits. \"What do you want?\"",
            "locations": [{"npcs": [{"code": "B", "name": "Vael", "role": "traveler", "attitude": "guarded"}]}],
            "conversation": {"target": [{"code": "B"}], "present": [{"code": "B"}]},
            "player": {"name": "Mara Quill", "health": health, "max_health": 20},
            "conditions": [{"name": "Injured leg"}],
            "recent_player_inputs": ["Show the seal to Vael", "ask Vael about the Irond's true purpose"],
            "settings": {"playthrough_options": {}},
        }

    def test_recent_inputs_reach_the_scene_packet(self):
        scene = llm._suggestion_scene(self._context())
        self.assertEqual(scene["recent_player_inputs"], ["Show the seal to Vael", "ask Vael about the Irond's true purpose"])

    def test_the_body_reaches_the_world_packet(self):
        down = llm._suggestion_world(self._context(health=0))["player"]
        self.assertEqual(down["condition"], "down, unconscious")
        self.assertEqual(down["injuries"], ["Injured leg"])
        self.assertEqual(llm._suggestion_world(self._context(health=20))["player"]["condition"], "fine")

    def test_the_rules_forbid_repeats_and_answer_the_body(self):
        from unittest import mock

        with mock.patch.object(llm, "_chat_json", return_value={"action": "Bind the leg", "why": "it bleeds"}) as call:
            llm.generate_input_suggestions(self._context(health=3), "", deeper=True)
        packet = call.call_args.args[1]
        self.assertIn("recent_player_inputs", packet)
        self.assertIn("Do not repeat or rephrase", packet)
        self.assertIn("answers the body first", packet)


_SCENE = " ".join(["Vael waits in the rain and says nothing for a long moment."] * 10)


def _stub_turn() -> dict:
    return {
        "scene_plan": {"goal": "talk", "focus_points": []},
        "narration_segments": [{"label": "scene", "text": _SCENE}],
        "narration": _SCENE,
        "player": {},
        "self_check": {"passed": True, "issues_found": [], "corrections_made": []},
        "turn_summary": "a beat",
        "scene_focus": "conversation",
    }


class DownedThenComingRound(unittest.TestCase):
    """The engine side of a collapse, through play_turn with the model stubbed.

    The run that found this had health 0 from turn 15 (a save in that state
    still exists), so the first turn here starts at 0: it is narrated as the
    drop, the next turn is the coming round by the death rule.
    """

    @classmethod
    def setUpClass(cls):
        from app import db

        os.environ.update(_ENV)
        db.init_db()
        world.start_playthrough(
            {
                "player_name": "Mara Quill",
                "start_location": "Iron Spire",
                "special_ability_origin": "none",
                "dice_checks_enabled": True,
                "death_rules": "lasting injuries",
            }
        )
        with db.connect() as conn:
            conn.execute("UPDATE player SET health = 0, max_health = 20 WHERE id = 1")

    def _play(self, line: str, seen: list) -> dict:
        from unittest import mock

        def fake(prompt_context, model_input):
            seen.append((prompt_context, model_input))
            return _stub_turn()

        with mock.patch.object(world, "generate_turn", side_effect=fake):
            return world.play_turn(line)

    def test_zero_health_is_the_drop_and_the_next_turn_the_waking(self):
        from app import db

        seen: list = []
        self._play("ask Vael about the Irond's true purpose", seen)
        self.assertEqual(len(seen), 1)
        prompt_context, model_input = seen[0]
        self.assertIn("__downed__", model_input)
        self.assertIn("health reaches 0", model_input)
        state = prompt_context.get("mechanics_context", {}).get("health_state") or {}
        self.assertEqual(state.get("band"), "down")
        self.assertTrue(state.get("downed"))
        with db.connect() as conn:
            downed = world._settings(conn).get("player_downed")
        self.assertIsInstance(downed, dict)
        self.assertEqual(downed.get("rule"), "lasting injuries")

        seen.clear()
        self._play("ask Vael about the seal", seen)
        prompt_context, model_input = seen[0]
        self.assertIn("coming round", model_input)
        recovery = prompt_context.get("mechanics_context", {}).get("recovery") or {}
        self.assertEqual(recovery.get("rule"), "lasting injuries")
        self.assertEqual(recovery.get("health_delta"), 5)
        self.assertNotIn("resolved_checks", prompt_context.get("mechanics_context", {}))
        with db.connect() as conn:
            player = dict(conn.execute("SELECT health, max_health FROM player WHERE id = 1").fetchone())
            settings = world._settings(conn)
        self.assertEqual(player["health"], 5)
        self.assertNotIn("player_downed", settings)
        names = [row.get("name") for row in settings.get("player_conditions") or [] if isinstance(row, dict)]
        self.assertIn("Lasting wound (body)", names)
        # And the next ordinary turn is ordinary again: health band, no recovery.
        # A line that rolls nothing, so a natural 1 cannot put the player down again.
        seen.clear()
        self._play("I sit still against the wall and breathe.", seen)
        mechanics = seen[0][0].get("mechanics_context", {})
        self.assertNotIn("recovery", mechanics)
        self.assertEqual((mechanics.get("health_state") or {}).get("band"), "critical")


class _AlwaysOne(random.Random):
    """A d20 that only ever shows 1: the permadeath roll fails."""

    def randint(self, a, b):  # noqa: D401 - test double
        return a


class PermadeathRoll(unittest.TestCase):
    def test_a_failed_death_roll_is_the_death_not_a_weaker_body(self):
        out = world._downed_recovery({"turn": 3, "limb": "leg", "cause": "a fall"}, {"death_rules": "permadeath threat"}, 20, _AlwaysOne())
        self.assertTrue(out["died"])
        self.assertEqual(out["death_roll"], 1)
        self.assertEqual(out["health_delta"], 0)
        self.assertEqual(out["minutes"], 0)
        self.assertIn("last turn of the story", out["what_happens"])
        self.assertEqual(out["max_health_delta"], 0)


class IronmanDeath(unittest.TestCase):
    """Ironman: the drop is the death; the saves go with the character, a copy kept quietly."""

    @classmethod
    def setUpClass(cls):
        from app import db

        os.environ.update(_ENV)
        cls.grave = _TMP / "graveyard"
        os.environ["AI_RPG_GRAVEYARD"] = str(cls.grave)
        db.init_db()
        world.start_playthrough(
            {
                "player_name": "Mara Quill",
                "start_location": "Iron Spire",
                "special_ability_origin": "none",
                "dice_checks_enabled": True,
                "death_rules": "downed, not deleted",
                "ironman_mode": True,
            }
        )
        with db.connect() as conn:
            conn.execute("UPDATE player SET health = 0, max_health = 20 WHERE id = 1")

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("AI_RPG_GRAVEYARD", None)

    def _play(self, line: str, seen: list) -> dict:
        from unittest import mock

        def fake(prompt_context, model_input):
            seen.append((prompt_context, model_input))
            return _stub_turn()

        with mock.patch.object(world, "generate_turn", side_effect=fake):
            return world.play_turn(line)

    def test_the_drop_is_the_death_and_the_saves_are_gone(self):
        from app import db

        cid = world.campaign_id()
        # A save the player could have loaded.
        world.save_campaign_slot(world.autosave_slot_name(cid, 1))
        self.assertTrue(any(world.parse_autosave_slot(str(s.get("slot"))) for s in world.list_campaign_slots()))

        seen: list = []
        payload = self._play("ask Vael about the Irond's true purpose", seen)
        _prompt_context, model_input = seen[0]
        self.assertIn("__death__", model_input)
        self.assertIn("last turn of the story", model_input)
        mechanics = _prompt_context.get("mechanics_context", {})
        self.assertEqual((mechanics.get("death") or {}).get("rule"), "ironman")
        dead = payload.get("dead") or {}
        self.assertEqual(dead.get("rule"), "ironman")
        self.assertTrue(dead.get("ironman"))
        self.assertEqual(dead.get("player_name"), "Mara Quill")
        self.assertGreaterEqual(int(dead.get("saves_removed") or 0), 1)
        self.assertEqual((payload.get("state") or {}).get("dead", {}).get("rule"), "ironman")
        # The record is in settings and the state reports it.
        with db.connect() as conn:
            settings = world._settings(conn)
        self.assertEqual(settings.get("player_dead", {}).get("rule"), "ironman")
        self.assertNotIn("player_downed", settings)
        self.assertEqual((world.get_state().get("dead") or {}).get("rule"), "ironman")
        # No slot of this character is left to load; the graveyard has the copy.
        for slot in world.list_campaign_slots():
            parsed = world.parse_autosave_slot(str(slot.get("slot")))
            self.assertFalse(parsed and parsed[0] == cid, slot.get("slot"))
            self.assertNotEqual(str(slot.get("campaign_id") or ""), cid, slot.get("slot"))
        graves = list(self.grave.glob(f"{cid}-*/world.json"))
        self.assertEqual(len(graves), 1)
        # Continue does not offer a dead character, and no turn follows.
        self.assertFalse(world.has_continuable_save().get("ok"))
        seen.clear()
        refused = self._play("get up", seen)
        self.assertEqual(seen, [])
        self.assertIs(refused.get("advanced_turn"), False)
        self.assertEqual((refused.get("dead") or {}).get("rule"), "ironman")
        self.assertIsNone(refused.get("turn"))


class PermadeathEndsTheStory(unittest.TestCase):
    """permadeath threat: the drop, then a failed roll on the coming round is the death; saves stay."""

    @classmethod
    def setUpClass(cls):
        from app import db

        os.environ.update(_ENV)
        db.init_db()
        world.start_playthrough(
            {
                "player_name": "Mara Quill",
                "start_location": "Iron Spire",
                "special_ability_origin": "none",
                "dice_checks_enabled": True,
                "death_rules": "permadeath threat",
            }
        )
        with db.connect() as conn:
            conn.execute("UPDATE player SET health = 0, max_health = 20 WHERE id = 1")

    def _play(self, line: str, seen: list) -> dict:
        from unittest import mock

        def fake(prompt_context, model_input):
            seen.append((prompt_context, model_input))
            return _stub_turn()

        with mock.patch.object(world, "generate_turn", side_effect=fake), mock.patch.object(
            world, "_skill_check_rng", return_value=_AlwaysOne()
        ):
            return world.play_turn(line)

    def test_drop_then_failed_roll_is_the_death_and_saves_stay(self):
        from app import db

        cid = world.campaign_id()
        world.save_campaign_slot(world.autosave_slot_name(cid, 1))
        seen: list = []
        first = self._play("ask Vael about the seal", seen)
        self.assertIsNone(first.get("dead"))
        self.assertIn("__downed__", seen[0][1])
        seen.clear()
        second = self._play("ask Vael about the Irond", seen)
        _prompt_context, model_input = seen[0]
        self.assertIn("__death__", model_input)
        self.assertEqual((_prompt_context.get("mechanics_context", {}).get("death") or {}).get("rule"), "permadeath threat")
        dead = second.get("dead") or {}
        self.assertEqual(dead.get("rule"), "permadeath threat")
        self.assertEqual(dead.get("death_roll"), 1)
        self.assertFalse(dead.get("ironman"))
        self.assertNotIn("saves_removed", dead)
        kept = [s for s in world.list_campaign_slots() if (world.parse_autosave_slot(str(s.get("slot"))) or ("", 0))[0] == cid]
        self.assertTrue(kept, "the earlier autosave stays loadable")
        with db.connect() as conn:
            player = dict(conn.execute("SELECT health FROM player WHERE id = 1").fetchone())
        self.assertEqual(player["health"], 0)


if __name__ == "__main__":
    unittest.main()
