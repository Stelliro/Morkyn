"""
Playtest #28 (live Qwen3 8B smoke run): opening NPCs stored at a place named "The".

Every line here is copied from the live model traces under the smoke run:

  round 2 (launcher env), game 2 opening draft:
    NPC_NEW NAME "Marisol Okafor" ROLE pharmacist LOC The Frostbound Crossroads ATTITUDE wary
  The parser read LOC as one token, so the NPCs went to a new location "The"
  instead of beside the player at The Frostbound Crossroads. The code repair
  then tagged every "the" in the prose as [[L4]], and an examine turn ("the
  frost trail on the underbrush") was read as following someone and moved the
  player to "The".

  round 1 (no launcher env), game 2 opening draft:
    FOCUS location <The Wasteland's Edge>
    NPC_NEW NAME "Eli Dasgupta" ROLE drifter LOC <The Wasteland's Edge> ATTITUDE wary
    TALK <Eli Dasgupta> "You're not the first to follow that trail, but you might be the last."
  The op list's <slot> placeholders were copied as literal brackets.

Covered:
  (a) an unquoted LOC runs to the next flag; a code stays a code;
  (b) <...> wrappers are syntax, not text, and the op list no longer shows them;
  (c) a place "named" by a stop word or a bracket fragment is never minted;
  (d) the code tagger ignores a stop-word name already stored in an old save;
  (e) "the frost trail" is a noun, not a pursuit, and a stop-word place never
      matches the narration's articles.
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
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-live-places-"))
os.environ.update(isolated_data_env(str(_TMP)))
os.environ.update(
    {
        "AI_RPG_PACK_DIR": str(_TMP / "packs"),
        "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
        "AI_RPG_IDEA_BANK": str(_TMP / "idea_bank"),
        "AI_RPG_LAUNCHER_PREFS": str(_TMP / "launcher_prefs.json"),
    }
)
# The player's launcher env (data/launcher_prefs.json), for this module only:
# left in os.environ it would switch verification off for every later module.
LAUNCHER_ENV = {
    "AI_RPG_NARRATION_PIPELINE": "1",
    "AI_RPG_NARRATION_PIPELINE_CONSOLIDATE": "1",
    "AI_RPG_FAST_VERIFICATION": "1",
    "AI_RPG_DSL_SKIP_VERIFY": "1",
    "AI_RPG_DRAFT_MODE": "dsl",
}
_launcher_patch = mock.patch.dict(os.environ, LAUNCHER_ENV)


def setUpModule():
    _launcher_patch.start()


def tearDownModule():
    _launcher_patch.stop()


from app import db, world  # noqa: E402
from app.db import connect  # noqa: E402
from app.llm import _inject_entity_codes_for_known_names  # noqa: E402
from app.scene_thread import follow_target  # noqa: E402
from app.turn_dsl import DSL_SYSTEM_PROMPT, ops_to_turn, parse_ops  # noqa: E402

R2_G2_OPENING_OPS = (
    'NPC_NEW NAME "Marisol Okafor" ROLE pharmacist LOC The Frostbound Crossroads ATTITUDE wary\n'
    'NPC_NEW NAME "Victor Silva" ROLE mechanic LOC The Frostbound Crossroads ATTITUDE neutral\n'
    'NPC_NEW NAME "Carlos Barnes" ROLE bike courier LOC The Frostbound Crossroads ATTITUDE curious'
)
R1_G2_OPENING_OPS = (
    "FOCUS location <The Wasteland's Edge>\n"
    "FOCUS risk <sharp local danger>\n"
    "NPC_NEW NAME \"Eli Dasgupta\" ROLE drifter LOC <The Wasteland's Edge> ATTITUDE wary\n"
    "TALK <Eli Dasgupta> \"You're not the first to follow that trail, but you might be the last.\"\n"
    "MOVE <The Spindle at Edge>"
)
R1_G1_GOAL = "GOAL <explore the immediate surroundings and decide which direction to take>"
R1_TURN4_FOCUS = "FOCUS event <the scarred woman digging> <she is searching for the roots>"
R2_G2_TURN3_INPUT = "I crouch and examine the frost trail on the underbrush for tyre marks or footprints."
R2_G2_OPENING_NAR = (
    "Snow drifts across The Frostbound Crossroads. Marisol Okafor watches you from the doorway of the "
    "pharmacy, a scarf pulled up to her eyes."
)


def turn(ops: str, narration: str = "You stand there.") -> dict:
    return ops_to_turn(narration, parse_ops(ops))


class UnquotedLocRunsToTheNextFlag(unittest.TestCase):
    """(a) the live round 2 line."""

    def test_live_line_keeps_the_whole_place_name(self):
        npcs = turn(R2_G2_OPENING_OPS)["npcs"]
        self.assertEqual(
            [(n["name"], n["location"], n["attitude"]) for n in npcs],
            [
                ("Marisol Okafor", "The Frostbound Crossroads", "wary"),
                ("Victor Silva", "The Frostbound Crossroads", "neutral"),
                ("Carlos Barnes", "The Frostbound Crossroads", "curious"),
            ],
        )
        self.assertEqual(npcs[2]["role"], "bike courier")

    def test_a_code_stays_a_code(self):
        npc = turn('NPC_NEW NAME "Vanessa Iqbal" ROLE "garbage collector" LOC L1 ATTITUDE wary')["npcs"][0]
        self.assertEqual(npc["location"], "L1")
        self.assertEqual(npc["attitude"], "wary")

    def test_quoted_name_and_last_flag(self):
        npc = turn('NPC_NEW NAME "Randy" ROLE "garage mechanic" LOC "Chrome Wrench Garage" RACE "human" RANK "D"')["npcs"][0]
        self.assertEqual(npc["location"], "Chrome Wrench Garage")
        npc = turn('NPC_NEW NAME "Bo" ROLE baker LOC Old Mill Lane')["npcs"][0]
        self.assertEqual(npc["location"], "Old Mill Lane")

    def test_op_list_asks_for_a_code_or_a_quoted_name(self):
        self.assertIn('LOC location_code_or_"place name"', DSL_SYSTEM_PROMPT)


class AngleBracketPlaceholders(unittest.TestCase):
    """(b) the live round 1 lines."""

    def test_round1_opening(self):
        out = turn(R1_G2_OPENING_OPS)
        self.assertEqual(out["npcs"][0]["location"], "The Wasteland's Edge")
        focus = out["scene_plan"]["focus_points"]
        self.assertEqual(focus[0]["kind"], "location")
        self.assertEqual(focus[0]["summary"], "The Wasteland's Edge")
        self.assertEqual(focus[1]["summary"], "sharp local danger")
        code = out["conversations"][0]["npc_code"]
        self.assertNotIn("<", code)
        self.assertNotIn(">", code)

    def test_round1_goal_and_two_wrapped_args(self):
        self.assertEqual(
            turn(R1_G1_GOAL)["scene_plan"]["goal"],
            "explore the immediate surroundings and decide which direction to take",
        )
        focus = turn(R1_TURN4_FOCUS)["scene_plan"]["focus_points"][0]
        self.assertEqual(focus["kind"], "event")
        self.assertEqual(focus["summary"], "the scarred woman digging she is searching for the roots")

    def test_entity_code_brackets_are_untouched(self):
        npc = turn('NPC_NEW NAME "Bo" ROLE baker LOC [[L2]] ATTITUDE wary')["npcs"][0]
        self.assertEqual(npc["location"], "[[L2]]")
        self.assertEqual(npc["attitude"], "wary")

    def test_op_list_has_no_angle_bracket_slots(self):
        start = DSL_SYSTEM_PROMPT.index("Allowed opcodes")
        end = DSL_SYSTEM_PROMPT.index("Rules:")
        self.assertNotIn("<", DSL_SYSTEM_PROMPT[start:end])
        self.assertNotIn(">", DSL_SYSTEM_PROMPT[start:end])


class StopWordPlaces(unittest.TestCase):
    """(c) and (d)."""

    def test_predicate(self):
        for bad in ("The", "<The", "Of", "the", "In the", "Edge>", "[The"):
            self.assertFalse(world.is_plausible_place_name(bad), bad)
        for good in ("The Frostbound Crossroads", "The Wasteland's Edge", "Ys", "The Hollow"):
            self.assertTrue(world.is_plausible_place_name(good), good)

    def test_tagger_ignores_a_stop_word_place(self):
        text = "I woke up in the snow. The morning light"
        self.assertEqual(_inject_entity_codes_for_known_names(text, {"L4": "The"}), text)
        self.assertEqual(
            _inject_entity_codes_for_known_names("You reach The Frostbound Crossroads.", {"L1": "The Frostbound Crossroads"}),
            "You reach The Frostbound Crossroads [[L1]].",
        )


class FrostTrailIsNotAPursuit(unittest.TestCase):
    """(e) the live turn 3 line."""

    def test_noun_trail_is_not_followed(self):
        self.assertEqual(follow_target(R2_G2_TURN3_INPUT), "")
        self.assertEqual(follow_target("I examine the tracks in the mud."), "")

    def test_verb_trail_still_is(self):
        self.assertEqual(follow_target("I trail the courier"), "the courier")
        self.assertEqual(follow_target("We quietly shadow the guard"), "the guard")
        self.assertEqual(follow_target("I follow Marisol"), "Marisol")

    def test_stop_word_place_never_matches_an_article(self):
        rows = [{"name": "The", "code": "L4"}, {"name": "Edge of Town", "code": "L6"}]
        self.assertIsNone(
            world._known_place_named_in(rows, "You follow it east, where the trail splits toward the hill.", "Edge of Town")
        )


def seed_crossroads() -> None:
    db.init_db()
    with connect() as conn:
        conn.execute("UPDATE player SET current_location_id = 1 WHERE id = 1")
        conn.execute("DELETE FROM npcs")
        conn.execute("DELETE FROM locations WHERE id != 1")
        conn.execute("DELETE FROM settings WHERE key IN ('active_scene', 'conversation', 'scene_thread')")
        conn.execute(
            "UPDATE locations SET name = 'The Frostbound Crossroads', summary = 'A frozen junction.', "
            "parent_id = 0, kind = '', settlement_size = '', keeper_npc_id = 0 WHERE id = 1"
        )


def fake_turn(narration: str, **extra):
    def fake_generate(context, model_input):
        return {
            "scene_plan": {"goal": "look", "focus_points": []},
            "narration_segments": [{"label": "scene", "text": narration}],
            "narration": narration,
            "player": {},
            "self_check": {"passed": True, "issues_found": [], "corrections_made": []},
            "turn_summary": "the player wakes in the snow",
            "scene_focus": "action",
            **extra,
        }

    return fake_generate


class OpeningNpcsStandBesideThePlayer(unittest.TestCase):
    """The live opening through play_turn: no location 'The', NPCs at L1."""

    def setUp(self):
        seed_crossroads()

    def _play(self, ops: str) -> dict:
        npcs = turn(ops, R2_G2_OPENING_NAR)["npcs"]
        with mock.patch.object(world, "generate_turn", side_effect=fake_turn(R2_G2_OPENING_NAR, npcs=npcs)):
            return world.play_turn("I look around.")

    def test_round2_opening(self):
        self._play(R2_G2_OPENING_OPS)
        with connect() as conn:
            names = [r["name"] for r in conn.execute("SELECT name FROM locations")]
            where = {r["name"]: r["location_id"] for r in conn.execute("SELECT name, location_id FROM npcs")}
        self.assertNotIn("The", names)
        self.assertEqual(where.get("Marisol Okafor"), 1)
        self.assertEqual(where.get("Victor Silva"), 1)
        self.assertEqual(where.get("Carlos Barnes"), 1)

    def test_a_bare_fragment_falls_back_to_the_player(self):
        self._play('NPC_NEW NAME "Umar Mendes" ROLE medic LOC <The')
        with connect() as conn:
            names = [r["name"] for r in conn.execute("SELECT name FROM locations")]
            where = {r["name"]: r["location_id"] for r in conn.execute("SELECT name, location_id FROM npcs")}
        self.assertFalse([n for n in names if n.strip("<>[]{} ").lower() == "the"], names)
        self.assertEqual(where.get("Umar Mendes"), 1)


if __name__ == "__main__":
    unittest.main()
