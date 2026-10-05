"""
Playtest #31, #32, #34 (live Qwen3 8B smoke run, scratchpad\\smoke\\): who is
talked to, who comes along, and who exists.

Every player line and prose shape here is copied from the live run:

  #31  R2 G2 T1  "Marisol, I woke up in the snow and don't know this place."
       Marisol was stored somewhere else, so the line was "addressed to nobody",
       the prose walked her in anyway, and the target became Whitney
       (why=last_speaker).
  #32  R1 G1 T2  "Rolf, come with me. I want to find whoever is burning those
       herbs ..." -> prose "Rolf [[A]] follows ... Rolf [[A]] stops beside you"
       -> scene_thread null, Rolf left behind at L1 while the player moved.
       R2 G2 T4  "I follow Carlos Barnes toward the forest, keeping low." ->
       player at Forest Path, Carlos still at L4.
       R1 G1 T3  "... where Rolf is crouched, looking for footprints or anything
       dropped." -> a pursuit of "footprints" replaced the live thread.
  #34  R1 G2  tech "wasteland iron age" -> 'modern' (building super, street vendor);
       R2 G2  tech "arctic iron age" + custom "Modern urban elements ..." -> 'modern'
       (pharmacist, nurse, bike courier).
       R2 G1 T4  NPC_NEW Umar Mendes LOC L1 -> a second NPC "Umar", role "Mendes".
       R1 G1 opening "... the whisper of a forgotten tongue ... perhaps answers."
       -> two invisible NPCs, "Someone at the edge of the scene."
       R1 G2 T2  the player moves L4 -> The Farmer's Field; "a wiry woman with a
       scar across her cheek, leans in and whispers" is seeded at L4, and on T3
       "the scarred woman" is seeded again at L5.

The turn-pipeline tests run with the player's launcher env.
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
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-live-cast-"))
ISOLATED_ENV = {
    **isolated_data_env(str(_TMP)),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
    "AI_RPG_IDEA_BANK": str(_TMP / "idea_bank"),
    "AI_RPG_LAUNCHER_PREFS": str(_TMP / "launcher_prefs.json"),
}
os.environ.update(ISOLATED_ENV)
LAUNCHER_ENV = {
    # Re-applied while this module runs: under discover a later module's import
    # points AI_RPG_DB at its own file, and this module's seeds (extra places,
    # moved NPCs) must not land in another module's database.
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
from app import db, world  # noqa: E402
from app import example_pools as ep  # noqa: E402
from app import scene_thread as st  # noqa: E402
from app.db import connect  # noqa: E402
from app.turn_dsl import ops_to_turn, parse_ops  # noqa: E402

R2_G2_T1_INPUT = "Marisol, I woke up in the snow and don't know this place. Is there anyone here who hires laborers?"
R1_G1_T2_INPUT = "Rolf, come with me. I want to find whoever is burning those herbs down by the huts before they slip away."
R1_G1_T2_PROSE = (
    "You push past the brittle edge of the Whispering Wastes, where the wind carries the scent of scorched earth. "
    "Rolf [[A]] follows, his boots crunching over the cracked ground. You spot a smoldering trail of herbs leading "
    "toward a cluster of huts. Rolf [[A]] stops beside you, his gaze fixed on the smoke curling into the sky. "
    "You press on, the heat of the flames growing stronger with each step, until you reach a clearing where the "
    "fire has died down to embers."
)
R2_G2_T4_INPUT = "I follow Carlos Barnes toward the forest, keeping low."
R2_G2_T4_PROSE = (
    "You follow Carlos Barnes [[C]] into the forest, staying low and keeping your movements quiet.\n\n"
    "Carlos moves with purpose, his pace steady but not hurried. You catch glimpses of his back as he leads you "
    "deeper into the forest, the path narrowing and twisting between the trees."
)
R1_G1_T3_INPUT = (
    "I kneel and examine the blackened doorway where Rolf is crouched, looking for footprints or anything dropped."
)
R1_G1_OPENING = (
    "You stand at the edge of the Whispering Wastes, where the wind carries the faint hum of ancient magic, a sound "
    "like distant chimes or the whisper of a forgotten tongue. The land is cracked and dry. A faint scent of burning "
    "herbs lingers in the air, suggesting someone is tending a fire nearby, though no smoke rises to mark its "
    "presence. The path ahead leads toward the ridge, a place of unknown promise, while the ravine holds the "
    "promise of shelter and perhaps answers."
)
R1_G2_T2_PROSE = (
    "As you approach, the farmer's gaze flicks toward the hills. He's not the only one watching - a group of "
    "halflings in patched coats huddle near the well. One of them, a wiry woman with a scar across her cheek, "
    "leans in and whispers something to the others, her fingers tracing a pattern in the dust."
)
R1_G2_T3_INPUT = "I examine the pattern the scarred woman traced in the dust."
R1_G2_T3_PROSE = (
    "You examine the pattern the scarred woman traced in the dust. A few steps east, you find her, bent over a "
    "shallow trench. The light catches on the jagged scar across her cheek."
)


def _ctx(locations, here=1, settings=None):
    return {"current_location": {"id": here, "code": f"L{here}"}, "locations": locations, "settings": settings or {}}


# ---------------------------------------------------------------------------
# Isolated DB helpers
# ---------------------------------------------------------------------------


_SEEDS = 0


def seed_world(places: list[tuple[int, str]], npcs: list[tuple[str, int, str, str]], here: int = 1) -> None:
    # A fresh file each time: play_turn leaves rows (map, journal, snapshots)
    # that point at the places, so deleting places in place trips foreign keys.
    # (Windows keeps the old file locked, so each seed gets a new file; the
    # module-level env patch restores AI_RPG_DB afterwards.)
    global _SEEDS
    _SEEDS += 1
    os.environ["AI_RPG_DB"] = str(_TMP / f"world_{_SEEDS}.db")
    db.init_db()
    with connect() as conn:
        conn.execute("DELETE FROM npcs")
        conn.execute("DELETE FROM settings WHERE key IN ('active_scene', 'conversation', 'scene_thread')")
        for loc_id, name in places:
            if conn.execute("SELECT 1 FROM locations WHERE id = ?", (loc_id,)).fetchone():
                conn.execute(
                    "UPDATE locations SET name = ?, code = ?, parent_id = 0, kind = '', keeper_npc_id = 0 WHERE id = ?",
                    (name, f"L{loc_id}", loc_id),
                )
            else:
                conn.execute(
                    "INSERT INTO locations (id, code, name, summary) VALUES (?, ?, ?, '')", (loc_id, f"L{loc_id}", name)
                )
        for code, loc_id, name, role in npcs:
            conn.execute(
                "INSERT INTO npcs (code, location_id, name, role, summary) VALUES (?, ?, ?, ?, 'Known here.')",
                (code, loc_id, name, role),
            )
        conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (here,))


def fake_turn(narration: str, **extra):
    def fake_generate(context, model_input):
        return {
            "scene_plan": {"goal": "go on", "focus_points": []},
            "narration_segments": [{"label": "scene", "text": narration}],
            "narration": narration,
            "player": {},
            "self_check": {"passed": True, "issues_found": [], "corrections_made": []},
            "turn_summary": "the player goes on",
            "scene_focus": "action",
            **extra,
        }

    return fake_generate


def play(player_input: str, narration: str, **extra) -> dict:
    with mock.patch.object(world, "generate_turn", side_effect=fake_turn(narration, **extra)):
        return world.play_turn(player_input)


def npc_location(name: str) -> int | None:
    with connect() as conn:
        row = conn.execute("SELECT location_id FROM npcs WHERE name = ?", (name,)).fetchone()
    return int(row["location_id"]) if row else None


def player_location() -> int:
    with connect() as conn:
        return int(conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()[0])


def setting(key: str):
    with connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return json.loads(row[0]) if row else None


# ---------------------------------------------------------------------------
# #31
# ---------------------------------------------------------------------------


class NamedPersonElsewhereIsCalled(unittest.TestCase):
    def _ctx(self):
        return _ctx([
            {"id": 1, "code": "L1", "npcs": [{"id": 4, "code": "D", "name": "Vanessa Iqbal"}, {"id": 5, "code": "E", "name": "Whitney Garcia"}]},
            {"id": 4, "code": "L4", "name": "Chrome Thermos Pharmacy", "npcs": [{"id": 1, "code": "A", "name": "Marisol Okafor"}]},
        ])

    def test_resolve_carries_who_was_called(self):
        r = cv.resolve(self._ctx(), R2_G2_T1_INPUT)
        self.assertEqual(r["addressed"], [])
        self.assertEqual(r["rule"], "called")
        self.assertEqual(r["called"], ["A"])
        self.assertIn("Marisol Okafor [[A]]", cv.model_note(r))
        self.assertIn("Marisol Okafor [[A]]", json.dumps(cv.writer_view(r)))
        self.assertEqual(cv.world_view(r)["called"][0]["code"], "A")

    def test_a_person_here_still_wins(self):
        ctx = self._ctx()
        ctx["locations"][0]["npcs"].append({"id": 1, "code": "A", "name": "Marisol Okafor"})
        ctx["locations"][1]["npcs"] = []
        r = cv.resolve(ctx, R2_G2_T1_INPUT)
        self.assertEqual((r["addressed"], r["rule"]), (["A"], "name"))

    def test_shown_here_she_moves_in_and_becomes_the_target(self):
        seed_world(
            [(1, "The Frostbound Crossroads"), (4, "Chrome Thermos Pharmacy")],
            [("A", 4, "Marisol Okafor", "pharmacist"), ("D", 1, "Vanessa Iqbal", "carter"), ("E", 1, "Whitney Garcia", "scout")],
        )
        with connect() as conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES ('conversation', ?)",
                (json.dumps({"target": ["E"], "why": "last_speaker", "location": "L1", "here": ["D", "E"], "present": ["D", "E"], "last_speaker": "E"}),),
            )
        prose = (
            "Marisol Okafor, the pharmacist, stands just beyond the low door. She steps forward. "
            "\"Snow takes the careless,\" she says. \"You were lucky.\""
        )
        play(R2_G2_T1_INPUT, prose)
        self.assertEqual(npc_location("Marisol Okafor"), player_location())
        state = setting("conversation")
        self.assertEqual(state["target"], ["A"])

    def test_not_shown_she_stays_where_she_is(self):
        seed_world(
            [(1, "The Frostbound Crossroads"), (4, "Chrome Thermos Pharmacy")],
            [("A", 4, "Marisol Okafor", "pharmacist"), ("E", 1, "Whitney Garcia", "scout")],
        )
        play(R2_G2_T1_INPUT, "Nobody answers. The wind keeps on across the crossroads.")
        self.assertEqual(npc_location("Marisol Okafor"), 4)


# ---------------------------------------------------------------------------
# #32
# ---------------------------------------------------------------------------


class CompanionsAreKept(unittest.TestCase):
    def _rolf(self):
        return _ctx([{"id": 1, "code": "L1", "npcs": [{"id": 1, "code": "A", "name": "Rolf"}, {"id": 2, "code": "B", "name": "Baldric"}]}])

    def test_invite_without_pursuit_or_thread_is_recorded(self):
        ctx = self._rolf()
        tt = st.begin_turn(ctx, R1_G1_T2_INPUT, cv.resolve(ctx, R1_G1_T2_INPUT))
        thread = st.next_thread(
            tt, None, quest_report={}, quests={}, narration=R1_G1_T2_PROSE, player_input=R1_G1_T2_INPUT,
            location="Burnt Herbs Site", turn=3,
        )
        self.assertIsNotNone(thread)
        self.assertEqual(thread["with"], [{"code": "A", "name": "Rolf"}])
        self.assertIn("find whoever is burning those herbs", thread["doing"])

    def test_refusal_still_records_nobody(self):
        ctx = self._rolf()
        tt = st.begin_turn(ctx, R1_G1_T2_INPUT, cv.resolve(ctx, R1_G1_T2_INPUT))
        thread = st.next_thread(
            tt, None, quest_report={}, quests={}, narration="Rolf [[A]] shakes his head and stays behind.",
            player_input=R1_G1_T2_INPUT, location="", turn=3,
        )
        self.assertIsNone(thread)

    def test_live_invite_phrasings(self):
        ctx = self._rolf()
        line = "Rolf, stay close."
        self.assertEqual(st.begin_turn(ctx, line, cv.resolve(ctx, line))["asked_along"], [{"code": "A", "name": "Rolf"}])
        ctx2 = _ctx([{"id": 2, "code": "L2", "npcs": [{"id": 9, "code": "D", "name": "Umar Mendes"}]}], here=2)
        line2 = "I pocket the crystal and follow the Guild watcher toward the warehouses, with Umar beside me."
        tt = st.begin_turn(ctx2, line2, cv.resolve(ctx2, line2))
        self.assertEqual(tt["asked_along"], [{"code": "D", "name": "Umar Mendes"}])

    def test_companion_moves_with_the_player(self):
        seed_world([(1, "Whispering Wastes"), (2, "Burnt Herbs Site")], [("A", 1, "Rolf", "teamster"), ("B", 1, "Baldric", "homesteader")])
        play(R1_G1_T2_INPUT, R1_G1_T2_PROSE, player={"move_to_location": "Burnt Herbs Site"})
        self.assertEqual(player_location(), 2)
        self.assertEqual(npc_location("Rolf"), 2)
        self.assertEqual(npc_location("Baldric"), 1)
        self.assertEqual([p["name"] for p in setting("scene_thread")["with"]], ["Rolf"])

    def test_followed_person_moves_with_the_player(self):
        seed_world([(1, "Frost Market"), (4, "Edge of Town"), (7, "Forest Path")], [("C", 4, "Carlos Barnes", "courier"), ("E", 4, "Whitney Garcia", "scout")], here=4)
        with connect() as conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES ('scene_thread', ?)",
                (json.dumps({"version": 1, "doing": "go after Carlos Barnes", "target": "Carlos Barnes", "target_code": "C", "with": [], "quest": {}, "source": "player", "started_turn": 3, "touched_turn": 3, "where": "Edge of Town"}),),
            )
        play(R2_G2_T4_INPUT, R2_G2_T4_PROSE, player={"move_to_location": "Forest Path"})
        self.assertEqual(player_location(), 7)
        self.assertEqual(npc_location("Carlos Barnes"), 7)
        self.assertEqual(npc_location("Whitney Garcia"), 4)


class SearchIsNotAPursuit(unittest.TestCase):
    def test_looking_for_footprints_is_not_a_pursuit(self):
        self.assertIsNone(st.pursuit_in(R1_G1_T3_INPUT))
        self.assertIsNone(st.pursuit_in("I investigate the marks on the wall."))

    def test_looking_for_a_person_still_is(self):
        self.assertEqual(st.pursuit_in("I look for Rolf near the huts.")["target"], "Rolf")
        self.assertEqual(st.pursuit_in("I search for the hooded figure")["target"], "the hooded figure")
        self.assertEqual(st.follow_target("I follow the courier"), "the courier")

    def test_a_search_does_not_replace_the_live_thread(self):
        prev = {"version": 1, "doing": "go after Carlos Barnes", "target": "Carlos Barnes", "target_code": "C", "with": [],
                "quest": {}, "source": "player", "started_turn": 3, "touched_turn": 3, "where": "Edge of Town"}
        ctx = _ctx([{"id": 6, "code": "L6", "npcs": [{"id": 1, "code": "A", "name": "Rolf"}]}], here=6,
                   settings={"scene_thread": json.dumps(prev)})
        for line in (R1_G1_T3_INPUT, "I search for the hooded stranger's dropped knife."):
            tt = st.begin_turn(ctx, line, cv.resolve(ctx, line))
            self.assertEqual(tt["status"], "continues", line)
            self.assertEqual(tt["target"], "Carlos Barnes")


# ---------------------------------------------------------------------------
# #34
# ---------------------------------------------------------------------------


class EraFromTheTechLevel(unittest.TestCase):
    def test_iron_age_wins_over_setting_words(self):
        self.assertEqual(world.resolve_world_era("wasteland iron age", "frontier dark fantasy", ""), "preindustrial")
        self.assertEqual(
            world.resolve_world_era(
                "arctic iron age", "frontier dark fantasy",
                "Modern urban elements blend with ancient frontier ruins, creating hidden zones where magic flickers.",
            ),
            "preindustrial",
        )

    def test_pools_get_the_same_era(self):
        self.assertEqual(ep.world_context({"tech_level": "wasteland iron age", "world_style": "frontier dark fantasy"})["era"], "preindustrial")

    def test_a_wasteland_alone_still_reads_modern(self):
        self.assertEqual(world.resolve_world_era("", "post-collapse wasteland eighty years after the grid died"), "modern")


class NpcNewKeepsTheWholeName(unittest.TestCase):
    def _npc(self, ops):
        return ops_to_turn("Umar walks beside you.", parse_ops(ops))["npcs"][0]

    def test_positional_two_word_name(self):
        for ops in ("NPC_NEW Umar Mendes LOC L1", "NPC_NEW Umar Mendes L1"):
            npc = self._npc(ops)
            self.assertEqual((npc["name"], npc["role"], npc["location"]), ("Umar Mendes", "local", "L1"), ops)

    def test_unquoted_name_flag(self):
        npc = self._npc("NPC_NEW NAME Umar Mendes LOC L1")
        self.assertEqual((npc["name"], npc["location"]), ("Umar Mendes", "L1"))
        npc = self._npc("NPC_NEW NAME Umar Mendes ROLE courier LOC L1")
        self.assertEqual((npc["name"], npc["role"]), ("Umar Mendes", "courier"))

    def test_name_then_job(self):
        npc = self._npc("NPC_NEW Elara message runner L1")
        self.assertEqual((npc["name"], npc["role"]), ("Elara", "message runner"))
        npc = self._npc("NPC_NEW NAME Bo baker LOC L1")
        self.assertEqual((npc["name"], npc["role"]), ("Bo", "baker"))

    def test_first_name_binds_to_the_known_person(self):
        seed_world([(1, "Far Platform"), (2, "Night Market")], [("A", 2, "Umar Mendes", "courier")])
        with connect() as conn:
            npc_id = world._upsert_npc(conn, {"name": "Umar", "role": "Mendes", "location": "L1"})
            rows = conn.execute("SELECT code, name FROM npcs").fetchall()
        self.assertEqual([(r["code"], r["name"]) for r in rows], [("A", "Umar Mendes")])
        self.assertIsNotNone(npc_id)


class ProseSeedingShowsRealPeople(unittest.TestCase):
    def test_pronouns_and_words_are_not_figures(self):
        for text in ('"Stay back," she says.', "The wind calls through the pass.", R1_G1_OPENING, '"Fine," you say.'):
            self.assertEqual(world._figure_hints(text), [], text)

    def test_a_named_speaker_and_a_shown_stranger_still_are(self):
        self.assertEqual(world._figure_hints("Mara says nothing for a while."), ["Mara says"])
        self.assertTrue(world._figure_hints("A hooded figure leans in."))

    def test_opening_with_nobody_seeds_nobody(self):
        seed_world([(1, "Whispering Wastes")], [])
        with connect() as conn:
            created = world._ensure_npcs_from_narration(conn, {"npcs": []}, R1_G1_OPENING, 1)
        self.assertEqual(created, [])

    def test_seed_is_grounded_in_the_prose(self):
        seed_world([(1, "Farmer's Field")], [])
        with connect() as conn:
            created = world._ensure_npcs_from_narration(conn, {"npcs": []}, R1_G2_T2_PROSE, 1)
            rows = conn.execute("SELECT name, summary, pronouns FROM npcs").fetchall()
        self.assertEqual(len(created), 1)
        self.assertNotIn("Someone at the edge of the scene", rows[0]["summary"])
        self.assertIn("scar", rows[0]["summary"])
        self.assertEqual(rows[0]["pronouns"], "she")

    def test_seeded_where_the_player_ends_up_and_only_once(self):
        seed_world([(1, "Edge of the Wastes"), (4, "Ridge Road"), (5, "The Farmer's Field")], [("A", 4, "Eli Dasgupta", "drifter")], here=4)
        play("Eli, come with me. Let's go after the farmer who keeps glancing at the hills.", R1_G2_T2_PROSE,
             player={"move_to_location": "The Farmer's Field"})
        self.assertEqual(player_location(), 5)
        with connect() as conn:
            seeded = conn.execute("SELECT name, location_id FROM npcs WHERE summary LIKE '%scar%'").fetchall()
        self.assertEqual([r["location_id"] for r in seeded], [5])
        play(R1_G2_T3_INPUT, R1_G2_T3_PROSE)
        with connect() as conn:
            seeded = conn.execute("SELECT name FROM npcs WHERE summary LIKE '%scar%'").fetchall()
        self.assertEqual(len(seeded), 1)


if __name__ == "__main__":
    unittest.main()
