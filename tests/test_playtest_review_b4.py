"""
Review of the live smoke fixes (#31, #30, #33, #35, #36): five defects the
fixes themselves brought in, each reproduced with the live run's shapes.

  #31  resolve() read any mention of a person who is elsewhere as a call:
       "I give up on Carlos for now ..." (R2 g2 t5), "I follow Carlos Barnes
       toward the forest" (R2 g2 t4) and "the Spindle at Edge that Marisol
       mentioned" told the draft the player was calling them, and
       bring_called_here pulled Carlos in on "Carlos turns down a side lane
       and is lost to sight".
  #30  drop_invented_player_speech read a keeper's opening line after a
       "You ..." action as the player's ("You step up to the counter. 'What
       can I get you?'"), and the drop ran after the depth check.
  #33  generic kind words ("parts", "supply", "bar", "lounge") made ordinary
       prose and street names into venues, and a named move could stamp a
       settlement that holds places as a venue.
  #35  ground_acquisitions dropped every new item on any turn where the
       player named something they hold ("I hand Umar the crystal").
  #36  the auto window tracked live free VRAM and mle reopened the model
       whenever it drifted one step.

The turn-pipeline tests run with the player's launcher env.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-review-b4-"))
ISOLATED_ENV = {
    **isolated_data_env(str(_TMP)),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
    "AI_RPG_IDEA_BANK": str(_TMP / "idea_bank"),
    "AI_RPG_LAUNCHER_PREFS": str(_TMP / "launcher_prefs.json"),
}
os.environ.update(ISOLATED_ENV)
LAUNCHER_ENV = {
    **ISOLATED_ENV,
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


from app import conversation as cv  # noqa: E402
from app import db, llm, mle, venues, world  # noqa: E402
from app.db import connect  # noqa: E402
from app.narration_pipeline import drop_invented_player_speech  # noqa: E402

# Live inputs (R2 g2), copied from the turn payloads.
G2_T4_INPUT = "I follow Carlos Barnes toward the forest, keeping low."
G2_T5_INPUT = "I give up on Carlos for now, walk back to the Chrome Wrench Garage and go inside to see what they sell."
R1_G1_T5_INPUT = "I head for the Spindle at Edge that Marisol mentioned and go inside the first shop I find."


def _g2_ctx():
    # The g2_t4 roster: Marisol, Victor and Carlos at L4, the player at L7.
    return {
        "current_location": {"id": 7, "code": "L7"},
        "locations": [
            {"id": 4, "code": "L4", "npcs": [
                {"id": 1, "code": "A", "name": "Marisol Okafor"},
                {"id": 2, "code": "B", "name": "Victor Silva"},
                {"id": 3, "code": "C", "name": "Carlos Barnes"},
            ]},
            {"id": 7, "code": "L7", "npcs": []},
        ],
        "settings": {},
    }


class MentionIsNotACall(unittest.TestCase):
    """#31 review: only an address form calls an absent person."""

    def test_live_mentions_call_nobody(self):
        for line in (
            G2_T5_INPUT,
            G2_T4_INPUT,
            R1_G1_T5_INPUT,
            "I go back to the garage to see what Victor has.",
        ):
            r = cv.resolve(_g2_ctx(), line, {})
            self.assertNotEqual(r["rule"], "called", line)
            self.assertFalse(r.get("called"), line)
            self.assertNotIn("calls to", cv.model_note(r), line)

    def test_address_forms_still_call(self):
        for line, code in (
            ("Marisol, I woke up in the snow and don't know this place.", "A"),
            ("I call out to Carlos to wait for me.", "C"),
            ("Wait up, Carlos!", "C"),
            ("I shout for Victor over the wind.", "B"),
            ('"Victor, are you there?"', "B"),
            ("I ask Marisol where the pharmacy keeps its stock.", "A"),
        ):
            r = cv.resolve(_g2_ctx(), line, {})
            self.assertEqual(r["rule"], "called", line)
            self.assertEqual(r["called"], [code], line)

    def test_a_given_up_target_is_not_pulled_into_the_scene(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE player (id INTEGER, current_location_id INTEGER)")
        conn.execute("INSERT INTO player VALUES (1, 7)")
        conn.execute("CREATE TABLE npcs (id INTEGER, code TEXT, name TEXT, location_id INTEGER)")
        conn.execute("INSERT INTO npcs VALUES (3, 'C', 'Carlos Barnes', 4)")
        r = cv.resolve(_g2_ctx(), G2_T5_INPUT, {})
        prose = "Somewhere behind you, Carlos turns down a side lane and is lost to sight."
        self.assertEqual(cv.bring_called_here(conn, r, prose), [])
        # Even when called, a sentence that loses him from sight does not bring him.
        called = {"called": ["C"]}
        self.assertEqual(cv.bring_called_here(conn, called, prose), [])
        self.assertEqual(conn.execute("SELECT location_id FROM npcs").fetchone()[0], 4)


class KeeperOpeningLineIsKept(unittest.TestCase):
    """#30 review: an untagged line after "You ..." is the player's only as a reply."""

    def test_shopkeeper_greeting_stays(self):
        para = "You push open the door and step up to the counter. “What can I get you?”"
        kept, dropped = drop_invented_player_speech([para], "I go into the shop.")
        self.assertEqual(dropped, [])
        self.assertIn("What can I get you?", kept[0])
        kept, dropped = drop_invented_player_speech(["You lean on the bar. “Rough night?”"], "I walk to the bar.")
        self.assertEqual(dropped, [])

    def test_an_invented_reply_after_someone_spoke_still_goes(self):
        paras = [
            "“Looking for anything specific?” he asks.",
            "You shake your head. “Just checking what you have to offer.”",
        ]
        kept, dropped = drop_invented_player_speech(paras, "I go inside to see what they sell.")
        self.assertEqual(len(dropped), 1)
        self.assertNotIn("Just checking", kept[1])

    def test_a_drop_under_the_floor_gets_the_depth_retry(self):
        long_npc = "The keeper studies you for a long while. " * 8
        narration = long_npc + "\n\n" + "You shake your head. “" + ("I only want to look around here today. " * 20) + "”"
        turn = {"narration": narration, "self_check": {"corrections_made": []}}
        # Speech after an NPC line so the dialogue convention applies.
        turn["narration"] = "“Well?” he asks.\n\n" + narration
        calls = []

        def depth(t, *a, **k):
            calls.append(len(str(t.get("narration") or "")))
            return t

        passthrough = lambda t, *a, **k: t  # noqa: E731
        with mock.patch.object(llm, "pipeline_enabled", return_value=False), \
                mock.patch.object(llm, "_ensure_narration_depth", side_effect=depth), \
                mock.patch.object(llm, "_ensure_narration_voice", side_effect=passthrough), \
                mock.patch.object(llm, "_ensure_answer_act", side_effect=passthrough), \
                mock.patch.object(llm, "_ensure_recall_specifics", side_effect=passthrough):
            out = llm._ensure_narration_quality(turn, {}, "I walk over to the counter.", "sys", 30, [], "test")
        self.assertNotIn("I only want to look around", out["narration"])
        self.assertEqual(len(calls), 2, "the depth check runs again once the drop took the turn under the floor")
        self.assertLess(calls[1], llm.MIN_TURN_NARRATION_CHARS)


class GenericWordsAreNotVenues(unittest.TestCase):
    """#33 review: weak kind words name a venue only as a head noun."""

    def test_everyday_prose_enters_nothing(self):
        for prose in (
            "You slip through the gap between the scrap parts piled high.",
            "You duck into the supply tent, out of the wind.",
            "You push through the rusted door. Inside, the smell of grease hangs over the parts bins.",
            "You step into the shade of the bar of rusted girders.",
            "You walk into the ruined lounge of the derelict station.",
        ):
            self.assertIsNone(venues.entry_in_prose(prose), prose)

    def test_streets_and_modifiers_are_not_venues(self):
        for name in ("Iron Bar Crossing", "Supply Depot", "Parts Unknown", "Clinic Road", "Smithy Lane", "The Forge Quarter"):
            self.assertEqual(venues.venue_kind_from_name(name), "", name)

    def test_real_venues_still_are(self):
        for name, kind in (
            ("Rust Bar", "bar"), ("Rustwater Supply", "general_store"), ("Kel's Parts", "garage"),
            ("Chrome Wrench Garage", "garage"), ("Ito Salvage", "salvage_yard"), ("Noodle Bar", "diner"),
            ("Okafor Repairs", "garage"), ("The Iron Smithy", "smithy"),
        ):
            self.assertEqual(venues.venue_kind_from_name(name), kind, name)
        self.assertEqual((venues.entry_in_prose("You step into the bar.") or {}).get("kind"), "bar")
        hit = venues.entry_in_prose("You push through the door. Inside, the garage is dimly lit.") or {}
        self.assertEqual(hit.get("kind"), "garage")

    def _seed(self, places, here):
        os.environ["AI_RPG_DB"] = str(_TMP / f"venues_{len(places)}_{here}_{id(self)}.db")
        db.init_db()
        with connect() as conn:
            conn.execute("DELETE FROM npcs")
            for loc_id, name, parent in places:
                if conn.execute("SELECT 1 FROM locations WHERE id = ?", (loc_id,)).fetchone():
                    conn.execute(
                        "UPDATE locations SET name = ?, code = ?, parent_id = ?, kind = '', keeper_npc_id = 0 WHERE id = ?",
                        (name, f"L{loc_id}", parent, loc_id),
                    )
                else:
                    conn.execute(
                        "INSERT INTO locations (id, code, name, summary, parent_id) VALUES (?, ?, ?, '', ?)",
                        (loc_id, f"L{loc_id}", name, parent),
                    )
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (here,))

    def test_supply_tent_mints_no_shop(self):
        self._seed([(1, "Rustwater Town", 0)], 1)
        with connect() as conn:
            self.assertIsNone(world._venue_shown_in_prose(conn, {}, "You duck into the supply tent, out of the wind."))
            self.assertIsNone(world._venue_shown_in_prose(conn, {}, "You slip through the gap between the scrap parts piled high."))
            count = conn.execute("SELECT COUNT(*) FROM locations").fetchone()[0]
        self.assertEqual(count, 1)

    def test_a_place_holding_places_is_not_stamped_a_venue(self):
        self._seed([(1, "Rustwater Town", 0), (2, "Ironside Garage", 0), (3, "Back Lot", 2)], 1)
        with connect() as conn:
            resolved = conn.execute("SELECT * FROM locations WHERE id = 2").fetchone()
            current = conn.execute("SELECT * FROM locations WHERE id = 1").fetchone()
            fields = world._venue_for_named_move(
                conn, {}, {}, "Ironside Garage", resolved, current,
                "I walk to Ironside Garage and go inside.", "You push through the door into Ironside Garage.",
            )
            row = conn.execute("SELECT parent_id, kind FROM locations WHERE id = 2").fetchone()
        self.assertNotIn("venue_stamped", fields)
        self.assertEqual((int(row[0] or 0), str(row[1] or "")), (0, ""))


class HandingOverDoesNotHideAGrant(unittest.TestCase):
    """#35 review: only a stow of a held item reads the claim as that item."""

    STATE = {"inventory": [{"name": "data crystal"}]}

    def test_a_trade_turn_still_grants(self):
        for prose in ("Umar nods. You receive a brass key, cold and heavy.", "You are handed a brass key from his belt."):
            turn: dict = {}
            got = world.ground_acquisitions(turn, prose, self.STATE, player_input="I hand Umar the crystal and ask what it opens")
            self.assertEqual(got, ["brass key"], prose)

    def test_pocketing_a_held_item_still_grants_nothing(self):
        turn: dict = {}
        self.assertEqual(
            world.ground_acquisitions(turn, "You pocket the glowing shard.", self.STATE, player_input="I pocket the crystal"), []
        )
        turn = {}
        self.assertEqual(
            world.ground_acquisitions(
                turn, "You tuck the shard into your coat.", self.STATE, player_input="I put the crystal away in my coat"
            ),
            [],
        )


class AutoWindowIsPinnedPerLoad(unittest.TestCase):
    """#36 review: the automatic window is read once per load, not per call."""

    def setUp(self):
        self.path = _TMP / "model.gguf"
        self.path.write_bytes(b"x")

    def test_free_vram_drift_does_not_reopen(self):
        opened = []

        def fake_open(path, n_ctx):
            opened.append(n_ctx)
            return mock.Mock()

        with mock.patch.object(mle, "_open_model", side_effect=fake_open), mock.patch.object(mle, "_close_quiet"):
            mle._drop_model()
            try:
                for size in (14336, 12288, 12288, 10240):
                    with mock.patch.object(mle, "_context_request", return_value=(size, True)):
                        mle._ensure_loaded(self.path)
                self.assertEqual(opened, [14336])
                self.assertEqual(mle.loaded_context(), 14336)
                # The player setting a size still reopens.
                with mock.patch.object(mle, "_context_request", return_value=(16384, False)):
                    mle._ensure_loaded(self.path)
                self.assertEqual(opened, [14336, 16384])
            finally:
                mle._drop_model()

    def test_request_reports_its_source(self):
        env = {k: v for k, v in os.environ.items() if k != "AI_RPG_CONTEXT_TOKENS"}
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch("app.model_limits.resolve_limits", return_value={"context_tokens": 14336, "source": {"context_tokens": "auto"}}):
                self.assertEqual(mle._context_request(), (14336, True))
            with mock.patch("app.model_limits.resolve_limits", return_value={"context_tokens": 20480, "source": {"context_tokens": "custom"}}):
                self.assertEqual(mle._context_request(), (20480, False))
        with mock.patch.dict(os.environ, {"AI_RPG_CONTEXT_TOKENS": "8192"}):
            self.assertEqual(mle._context_request(), (8192, False))


if __name__ == "__main__":
    unittest.main()
