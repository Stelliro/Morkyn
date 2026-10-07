"""
Playtest #39 / #40 / #41 / #46 / #49, judged on the live batch 4 and A/B shapes.

#39  The op list was a template of value-shaped snake_case slot words, and the
     model copied them as values: GOAL choose_direction, TALK "topic_of_the_exchange".
#40  The known-name tagger tagged a shorter item name inside a longer one and the
     label expander then doubled the longer name.
#41  A GOLD loss survived after every GRANT it paid for was removed, and the band
     line hid the sign ("2d6+3 [1, 1] +3 = -5").
#46  The movement report said "model" with a destination while the venue gate kept
     the player in place; scene_cast carried a raw "[[B]]".
#49  Qwen3 finished English phrases in Chinese ("warm空气"); nothing checked script.

Live fixtures are copied verbatim from scratchpad\\smoke\\batch4_r1, batch4_r2 and ab.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn_b4fix_"))
os.environ.update(isolated_data_env(str(_TMP)))
for _key, _name in (
    ("AI_RPG_IDEA_BANK", "idea_bank.json"),
    ("AI_RPG_LAUNCHER_PREFS", "launcher_prefs.json"),
    ("AI_RPG_SKILL_LIBRARY", "skill_library.json"),
):
    os.environ.setdefault(_key, str(_TMP / _name))
os.environ.setdefault("AI_RPG_PACK_DIR", str(_TMP / "packs"))

from app import db, llm, mle, rng, world  # noqa: E402
from app import turn_dsl  # noqa: E402
from app.turn_dsl import DSL_SYSTEM_PROMPT, parse_dsl_turn  # noqa: E402

WRITER_OFF = {
    "AI_RPG_NARRATION_PIPELINE": "0",
    "AI_RPG_NARRATION_PIPELINE_CONSOLIDATE": "1",
    "AI_RPG_FAST_VERIFICATION": "1",
    "AI_RPG_DSL_SKIP_VERIFY": "1",
    "AI_RPG_DRAFT_MODE": "dsl",
}


_ISOLATED_ENV = {
    **isolated_data_env(str(_TMP)),
    "AI_RPG_IDEA_BANK": str(_TMP / "idea_bank.json"),
    "AI_RPG_LAUNCHER_PREFS": str(_TMP / "launcher_prefs.json"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
}
_ENV_PATCH = mock.patch.dict(os.environ, _ISOLATED_ENV)


def setUpModule():
    # Under discover, a later test module rewrites the data env at import time;
    # take this module's temp paths back for its own run and restore afterwards.
    _ENV_PATCH.start()
    assert str(db.db_path()).startswith(str(_TMP)), db.db_path()
    db.init_db()


def tearDownModule():
    _ENV_PATCH.stop()


def _fresh_world():
    db.init_db()
    rng.reset_seed_cache()
    world.start_playthrough({"player_name": "Ash", "start_location": "Low Gate", "special_ability_origin": "none"})


def _player() -> dict:
    with db.connect() as conn:
        return dict(conn.execute("SELECT * FROM player WHERE id = 1").fetchone())


class WriterOffEnv(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, WRITER_OFF)
        patcher.start()
        self.addCleanup(patcher.stop)


# --- #39 -----------------------------------------------------------------------

# batch4_r2 g2 turn-000005 draft_dsl, and the opening / setup copies.
R2_G2_T5_OPS = (
    "===NAR===\nThe small figure vanishes into the haze, leaving you and Humphrey in the open.\n\n"
    "===OPS===\n"
    "WALK east STEPS 3\n"
    "MOVE haze_entrance\n"
    "FOCUS risk\n"
    'TALK "Hubert Chandler" "the trail"\n'
)
SLOT_COPIES = (
    "===NAR===\nYou wait by the gate.\n\n===OPS===\n"
    "GOAL choose_direction\n"
    'TALK A "topic_of_the_exchange"\n'
    "FOCUS risk short_summary\n"
    "SUMMARY compact_memory_line_under_55_words\n"
    "MOVE place_name\n"
)
OLD_SLOT_WORDS = (
    "topic_of_the_exchange",
    "one_sentence_scene_goal",
    "compact_memory_line_under_55_words",
    "short_summary",
    "place_name",
    "real_name",
    "job_words",
    "durable_fact",
    "item_name",
    "first_thing_to_do",
    "one_scene_word",
    "private_future_note",
    "summary_append",
)


class OpLegendHasNoSlotWords(WriterOffEnv):
    def test_no_old_slot_word_ships(self):
        for word in OLD_SLOT_WORDS:
            with self.subTest(word=word):
                self.assertNotIn(word, DSL_SYSTEM_PROMPT)

    def test_the_legend_has_no_snake_case_token(self):
        start = DSL_SYSTEM_PROMPT.index("Allowed opcodes")
        end = DSL_SYSTEM_PROMPT.index("Rules:")
        legend = DSL_SYSTEM_PROMPT[start:end]
        tokens = set(re.findall(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b", legend)) - {"step_done"}
        self.assertEqual(tokens, set())

    def test_no_fixed_band_example_line(self):
        for fixed in ('"GOLD -moderate"', '"HP -small"', '"XP small"'):
            self.assertNotIn(fixed, DSL_SYSTEM_PROMPT)
        self.assertIn("GRANT takes the item's name in quotes", DSL_SYSTEM_PROMPT)

    def test_every_op_is_still_described(self):
        start = DSL_SYSTEM_PROMPT.index("Allowed opcodes")
        end = DSL_SYSTEM_PROMPT.index("Rules:")
        legend = DSL_SYSTEM_PROMPT[start:end]
        for op in turn_dsl.OPCODES:
            with self.subTest(op=op):
                self.assertRegex(legend, rf"(?m)^{op}\b|[ ,]{op}[,:]")

    def test_a_colon_after_the_op_word_still_parses(self):
        turn = parse_dsl_turn('===NAR===\nYou wait.\n\n===OPS===\nTALK: A "the toll at the bridge"\nGOAL: "cross before dark"\n', "I wait")
        self.assertEqual(turn["conversations"][0]["npc_code"], "A")
        self.assertEqual(turn["conversations"][0]["topic"], "the toll at the bridge")
        self.assertEqual(turn["scene_plan"]["goal"], "cross before dark")


class SlotCopiesAreMalformed(WriterOffEnv):
    def test_copied_slot_words_are_not_stored(self):
        turn = parse_dsl_turn(SLOT_COPIES, "I wait")
        self.assertNotEqual(turn["scene_plan"].get("goal"), "choose_direction")
        self.assertEqual(turn["conversations"], [])
        self.assertNotIn("short_summary", [f.get("summary") for f in turn["scene_plan"]["focus_points"]])
        self.assertNotEqual(turn.get("turn_summary"), "compact_memory_line_under_55_words")
        self.assertNotEqual((turn.get("player") or {}).get("move_to_location"), "place_name")

    def test_real_values_still_pass(self):
        turn = parse_dsl_turn(R2_G2_T5_OPS, "I follow the trail")
        self.assertEqual(turn["conversations"][0]["topic"], "the trail")
        # An invented slug destination is still a place name; apply humanizes it.
        self.assertEqual(turn["player"]["move_to_location"], "haze_entrance")
        self.assertEqual(world.humanize_place_name("haze_entrance"), "Haze Entrance")
        goal = parse_dsl_turn('===NAR===\nx\n\n===OPS===\nGOAL "find the smith before dark"\n', "x")
        self.assertEqual(goal["scene_plan"]["goal"], "find the smith before dark")

    def test_stored_slot_conversations_stop_reentering_prompts(self):
        _fresh_world()
        with db.connect() as conn:
            conn.execute(
                "INSERT INTO conversations (turn, npc_id, topic, summary, player_claims) VALUES (1, NULL, ?, ?, '[]')",
                ("topic_of_the_exchange", "topic_of_the_exchange"),
            )
            conn.execute(
                "INSERT INTO conversations (turn, npc_id, topic, summary, player_claims) VALUES (1, NULL, ?, ?, '[]')",
                ("the toll", "Asked about the toll at the bridge."),
            )
            # The verifier path writes conversations without the DSL parse.
            world._apply_conversations(conn, [{"npc_code": "A", "topic": "topic_of_the_exchange", "summary": "topic_of_the_exchange"}], 2)
        summaries = [c.get("summary") for c in world.get_state().get("conversations") or []]
        self.assertNotIn("topic_of_the_exchange", summaries)
        self.assertIn("Asked about the toll at the bridge.", summaries)
        with db.connect() as conn:
            n = conn.execute("SELECT COUNT(*) FROM conversations WHERE turn = 2").fetchone()[0]
        self.assertEqual(n, 0)


# --- #40 -----------------------------------------------------------------------

R2_G2_T5_TEXT = (
    "the weight of the charred ledger satchel feels less oppressive. "
    "his gaze lingering on the charred ledger satchel slung over your shoulder."
)
R2_G2_NAMES = {"I4": "charred ledger", "I5": "charred ledger satchel", "A": "Humphrey Fowler"}


class PrefixItemNamesDoNotDouble(unittest.TestCase):
    def test_live_satchel_line(self):
        fixed = llm._repair_prose_entity_labels(R2_G2_T5_TEXT, R2_G2_NAMES)
        self.assertNotIn("satchel charred", fixed)
        self.assertNotIn("[[I4]]", fixed)
        self.assertEqual(fixed.count("charred ledger satchel [[I5]]"), 2)

    def test_inject_never_tags_inside_a_longer_name(self):
        out = llm._inject_entity_codes_for_known_names(R2_G2_T5_TEXT, R2_G2_NAMES)
        self.assertNotIn("ledger [[I4]] satchel", out)
        self.assertEqual(out.count("charred ledger satchel [[I5]]"), 2)

    def test_the_shorter_item_alone_is_still_tagged(self):
        text = "You set the charred ledger on the table, and the charred ledger satchel stays on your back."
        out = llm._repair_prose_entity_labels(text, R2_G2_NAMES)
        self.assertIn("charred ledger [[I4]] on the table", out)
        self.assertIn("charred ledger satchel [[I5]] stays", out)

    def test_a_writer_tagged_longer_name_is_not_split(self):
        text = "his gaze on the charred ledger satchel [[I5]] slung over your shoulder."
        out = llm._repair_prose_entity_labels(text, R2_G2_NAMES)
        self.assertEqual(out, text)

    def test_an_interleaved_tag_does_not_re_expand(self):
        text = "the charred ledger [[I4]] satchel [[I5]] feels less oppressive."
        out = llm._repair_prose_entity_labels(text, R2_G2_NAMES)
        self.assertNotIn("satchel charred ledger satchel", out)


# --- #41 -----------------------------------------------------------------------

# batch4_r2 g2 turn-000006 draft_dsl: the player only asked to look.
R2_G2_T6_INPUT = "go inside the first trading post to see what they sell"
R2_G2_T6_DSL = (
    "===NAR===\nYou step inside the trading post. Shelves of coal, cloth and oddities line the walls, "
    "and the keeper watches you from behind the counter.\n\n"
    "===OPS===\n"
    'GRANT "coal" QTY small\n'
    'GRANT "cloth" QTY small\n'
    'GRANT "oddities" QTY trivial\n'
    "GOLD -small\n"
)


def _verifier_dropped_the_grants(turn: dict) -> dict:
    """The live verify patch: inventory_changes [] and the gold band kept."""
    patched = dict(turn)
    patched["inventory_changes"] = []
    patched["self_check"] = {"passed": True, "issues_found": [], "corrections_made": ["Verifier replaced inventory_changes."]}
    patched["turn_summary"] = "looked at the stock"
    return patched


class SpendWithNothingBought(WriterOffEnv):
    def test_explain_shows_a_loss_as_a_loss(self):
        roll = rng.resolve_magnitude("gold", "small", negative=True, rng=__import__("random").Random(1))
        line = rng.explain(roll)
        self.assertLess(roll["value"], 0)
        self.assertIn(f"lost ({roll['value']})", line)
        self.assertNotRegex(line, r"= -\d+$")

    def test_explain_of_a_gain_is_unchanged(self):
        roll = rng.resolve_magnitude("gold", "small", rng=__import__("random").Random(1))
        self.assertTrue(rng.explain(roll).endswith(f"= {roll['value']}"))

    def test_gold_loss_is_voided_when_every_grant_was_removed(self):
        _fresh_world()
        before = int(_player()["gold"])
        turn = _verifier_dropped_the_grants(parse_dsl_turn(R2_G2_T6_DSL, R2_G2_T6_INPUT))
        state = world.apply_turn(turn, R2_G2_T6_INPUT)
        self.assertEqual(int(_player()["gold"]), before)
        lines = " ".join((state.get("dice_rolls") or {}).get("lines") or [])
        self.assertIn("nothing was bought", lines)

    def test_gold_loss_stands_when_an_item_was_bought(self):
        _fresh_world()
        with db.connect() as conn:
            conn.execute("UPDATE player SET gold = 200 WHERE id = 1")
        dsl = (
            "===NAR===\nYou buy a coil of rope from the keeper and hand over the coins. "
            "He passes the rope across the counter.\n\n===OPS===\nGRANT \"rope\" QTY small\nGOLD -small\n"
        )
        turn = parse_dsl_turn(dsl, "I buy a coil of rope")
        turn["self_check"] = {"passed": True, "issues_found": [], "corrections_made": []}
        turn["turn_summary"] = "bought rope"
        world.apply_turn(turn, "I buy a coil of rope")
        self.assertLess(int(_player()["gold"]), 200)

    def test_a_toll_with_no_grant_still_costs(self):
        _fresh_world()
        with db.connect() as conn:
            conn.execute("UPDATE player SET gold = 200 WHERE id = 1")
        dsl = "===NAR===\nYou pay the bridge toll and the guard waves you through.\n\n===OPS===\nGOLD -trivial\n"
        turn = parse_dsl_turn(dsl, "I pay the toll")
        turn["self_check"] = {"passed": True, "issues_found": [], "corrections_made": []}
        turn["turn_summary"] = "paid the toll"
        world.apply_turn(turn, "I pay the toll")
        self.assertLess(int(_player()["gold"]), 200)


# --- #46 -----------------------------------------------------------------------

R1_G1_T2_INPUT = "Iseult, come with me. We go after whoever is watching"


class MovementReportMatchesTheRecord(WriterOffEnv):
    def test_refused_venue_reports_refused(self):
        _fresh_world()
        with db.connect() as conn:
            conn.execute(
                "UPDATE locations SET name = ?, summary = ?, settlement_size = '' WHERE id = 1",
                ("Threshold of the Stormcallers' First Breath", "Starting location for a Fantasy progression RPG playthrough."),
            )
        before = _player()["current_location_id"]
        dsl = (
            "===NAR===\nYou step through the door of the Threshold Apothecary with Iseult behind you.\n\n"
            "===OPS===\nMOVE \"Threshold Apothecary\"\n"
        )
        turn = parse_dsl_turn(dsl, R1_G1_T2_INPUT)
        turn["self_check"] = {"passed": True, "issues_found": [], "corrections_made": []}
        turn["turn_summary"] = "went for the apothecary"
        state = world.apply_turn(turn, R1_G1_T2_INPUT)
        self.assertEqual(_player()["current_location_id"], before)
        movement = state.get("movement") or {}
        self.assertEqual(movement.get("status"), "refused")
        self.assertIn("apothecary", str(movement.get("reason") or "").lower())
        with db.connect() as conn:
            notes = [r[0] for r in conn.execute("SELECT kind FROM journal WHERE kind LIKE 'venue_%'").fetchall()]
        self.assertIn("venue_refused", notes)

    def test_upsert_reports_the_refusal(self):
        _fresh_world()
        with db.connect() as conn:
            conn.execute("UPDATE locations SET settlement_size = '' WHERE id = 1")
            conn.execute("UPDATE locations SET name = ? WHERE id = 1", ("Threshold of the Stormcallers' First Breath",))
            refusal: dict = {}
            loc = world._find_location_id(conn, "Threshold Apothecary", refusal=refusal)
            self.assertEqual(loc, 1)
            self.assertEqual(refusal.get("reason"), "too_small")


class SceneCastCodesAreUnwrapped(WriterOffEnv):
    def test_dsl_cast_unwraps_the_prose_tag(self):
        turn = parse_dsl_turn("===NAR===\nIseult nods.\n\n===OPS===\nCAST interacting [[B]]\n", "x")
        self.assertEqual(turn["scene_cast"]["interacting"], ["B"])

    def test_apply_unwraps_and_drops_unknown_codes(self):
        _fresh_world()
        with db.connect() as conn:
            conn.execute(
                "INSERT INTO npcs (code, name, role, location_id, summary) VALUES ('B', 'Iseult', 'guide', 1, '')"
            )
            cast = {"present": ["[[ZZ]]"], "interacting": ["[[B]]"], "off": [], "keywords": []}
            world._apply_scene_cast(conn, cast)
            scene = world._settings(conn).get("active_scene")
        self.assertEqual(cast["interacting"], ["B"], "the payload carries the unwrapped code")
        self.assertEqual(scene["interacting"], ["B"])
        self.assertNotIn("ZZ", scene["present"])
        self.assertNotIn("[[ZZ]]", scene["present"])


# --- #49 -----------------------------------------------------------------------

from app import script_guard  # noqa: E402  (new in this fix)

LIVE_CJK = (
    ("Inside, the scent of oil and iron hangs in the stale, warm空气. A woman", "Inside, the scent of oil and iron hangs in the stale, warm air. A woman"),
    ("the smell of oil and metal thick in the空气. A merchant", "the smell of oil and metal thick in the air. A merchant"),
    ("pressing urgency in the空气.", "pressing urgency in the air."),
    ("reinforced glass罩", "reinforced glass cover"),
)


class OutOfScriptRepair(unittest.TestCase):
    def test_live_leaks_are_repaired(self):
        for raw, want in LIVE_CJK:
            with self.subTest(raw=raw):
                fixed, hits = script_guard.repair_out_of_script(raw)
                self.assertEqual(fixed, want)
                self.assertTrue(hits)

    def test_an_unmapped_run_is_dropped_cleanly(self):
        fixed, hits = script_guard.repair_out_of_script("You hear the 他们 voices beyond the door.")
        self.assertEqual(fixed, "You hear the voices beyond the door.")
        self.assertEqual(hits[0]["run"], "他们")

    def test_english_typography_is_untouched(self):
        text = "Café — “naïve”, she says… £5 and 3×4."
        self.assertEqual(script_guard.repair_out_of_script(text), (text, []))

    def test_json_stays_valid(self):
        import json

        raw = '{"narration": "thick in the空气.", "items": [{"description": "reinforced glass罩"}]}'
        fixed, _ = script_guard.repair_out_of_script(raw)
        data = json.loads(fixed)
        self.assertEqual(data["narration"], "thick in the air.")

    def test_chat_layer_repairs_and_traces(self):
        with mock.patch.object(llm, "_chat_content_dispatch", return_value="It hangs in the stale, warm空气."):
            with mock.patch.object(llm, "get_model_config", return_value={"provider": "mle", "mle_model": "x"}):
                out = llm._chat_content_unlocked("sys", "user", response_format=None)
        self.assertEqual(out, "It hangs in the stale, warm air.")
        trace: list = []
        with mock.patch.object(llm, "_chat_content", return_value=out):
            llm._script_repair_state.hits = [{"run": "空气", "replacement": "air"}]
            entry = llm._script_repair_trace()
        self.assertEqual(entry["script_repair"][0]["run"], "空气")
        self.assertEqual(llm._script_repair_trace(), {})


class OutOfScriptTokenMask(unittest.TestCase):
    def test_piece_classifier(self):
        self.assertTrue(script_guard.piece_is_out_of_script("空气".encode("utf-8")))
        self.assertTrue(script_guard.piece_is_out_of_script(b"\xe7"))  # a lone lead byte of a Han character
        self.assertTrue(script_guard.piece_is_out_of_script("。".encode("utf-8")))
        self.assertTrue(script_guard.piece_is_out_of_script("가".encode("utf-8")))
        for ok in (b" air", "—".encode("utf-8"), " café".encode("utf-8"), b"\xa9", b"\x80", "“".encode("utf-8")):
            with self.subTest(piece=ok):
                self.assertFalse(script_guard.piece_is_out_of_script(ok))

    def test_ban_ids_come_from_the_vocab_pieces(self):
        pieces = (b"the", "空".encode("utf-8"), b" air", b"\xe6", "—".encode("utf-8"))
        with mock.patch.object(mle, "_vocab_pieces", return_value=pieces):
            mle._SCRIPT_BAN_CACHE.clear()
            self.assertEqual(mle._script_ban_ids(object(), "fake.gguf"), (1, 3))
        with mock.patch.dict(os.environ, {"AI_RPG_SCRIPT_GUARD": "0"}):
            self.assertEqual(mle._script_ban_ids(object(), "fake.gguf"), ())
        mle._SCRIPT_BAN_CACHE.clear()

    def test_generate_masks_the_script_ids(self):
        captured: dict = {}

        class Model:
            def token_eos(self):
                return 0

            def create_chat_completion(self, **kwargs):
                captured.update(kwargs)
                return {"choices": [{"message": {"content": "fine"}}]}

        with mock.patch.object(mle, "_banned_ids", return_value=()), mock.patch.object(mle, "_script_ban_ids", return_value=(7, 9)):
            mle._generate(
                Model(), "x.gguf", "sys", "user", timeout=0, temperature=0.7,
                max_tokens=None, response_format=None, hide_words=None, keep_words=None,
            )
        processors = captured.get("logits_processor")
        self.assertIsNotNone(processors)
        self.assertEqual(sorted(int(i) for i in processors[0].banned), [7, 9])


if __name__ == "__main__":
    unittest.main()
