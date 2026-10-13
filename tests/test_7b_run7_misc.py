"""Assorted fixes from the seventh Saltmarrow run on Qwen2.5 7B (round 3)."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-7b-run7-misc-"))
_ENV = isolated_data_env(str(_TMP))
_SAVED_ENV: dict[str, str | None] = {}


def setUpModule():
    _SAVED_ENV.update({key: os.environ.get(key) for key in _ENV})
    os.environ.update(_ENV)


def tearDownModule():
    for key, value in _SAVED_ENV.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def seed_yard() -> None:
    """Run 7 at T2: Saltmarrow (L1) and its salvage yard (L2), the player in the yard."""
    from app import db
    from app.db import connect

    db.init_db()
    with connect() as conn:
        conn.execute("UPDATE player SET current_location_id = 1 WHERE id = 1")
        conn.execute("DELETE FROM npcs")
        conn.execute("DELETE FROM locations WHERE id != 1")
        conn.execute(
            "UPDATE locations SET code = 'L1', name = 'Saltmarrow', summary = '', parent_id = 0, kind = '', "
            "settlement_size = 'town', keeper_npc_id = 0 WHERE id = 1"
        )
        conn.execute(
            "INSERT INTO locations (id, code, name, summary, parent_id, kind) "
            "VALUES (2, 'L2', 'Saltmarrow Salvage Yard', '', 1, 'salvage_yard')"
        )
        conn.execute("UPDATE player SET current_location_id = 2 WHERE id = 1")


class APartOfTheYardIsNotASecondYard(unittest.TestCase):
    """T2: LOC_NEW 'Saltmarrow Salvage Deck', 'A small part of the yard', became a second salvage yard."""

    def test_trade_word_before_a_part_word_is_not_the_kind(self):
        from app import venues

        self.assertEqual(venues.venue_kind_from_name("Saltmarrow Salvage Deck"), "")
        self.assertEqual(venues.venue_kind_from_name("Smithy Shed"), "")
        self.assertEqual(venues.venue_kind_from_name("Saltmarrow Salvage Yard"), "salvage_yard")
        self.assertEqual(venues.venue_kind_from_name("The Blind Pike Inn"), "inn")

    def test_the_deck_stands_in_the_yard(self):
        from app import world
        from app.db import connect

        seed_yard()
        summary = "A small part of the yard, focused on the sunken cargo's decks, with crates and debris scattered around."
        with connect() as conn:
            new_id = world._upsert_location(conn, "Saltmarrow Salvage Deck", summary)
            row = conn.execute("SELECT parent_id, kind FROM locations WHERE id = ?", (new_id,)).fetchone()
            yards = conn.execute("SELECT COUNT(*) FROM locations WHERE kind = 'salvage_yard'").fetchone()[0]
        self.assertEqual((row["parent_id"], row["kind"]), (2, ""))
        self.assertEqual(yards, 1)

    def test_part_of_somewhere_else_is_not_placed_here(self):
        from app import world
        from app.db import connect

        seed_yard()
        with connect() as conn:
            self.assertEqual(world._part_of_here(conn, "A small part of the harbour, by the old crane."), 0)
            self.assertEqual(world._part_of_here(conn, "The back of the yard."), 2)


class TheOpsJobStandsWhenThePoseNamesIt(unittest.TestCase):
    """T1: 'the overseer, Oriel Rendle, the rag picker' with op role 'overseer Ssalvage' stored 'rag picker'."""

    def test_garbled_op_role_is_cleaned_and_kept(self):
        from app import world
        from app.db import connect

        seed_yard()
        prose = (
            "As you near the entrance, a tall figure with a weathered face and arms covered in calluses is overseeing "
            "the work. You approach the overseer, Oriel Rendle, the rag picker.\n\n\"Good morn,\" Oriel says."
        )
        with connect() as conn:
            out = world._roles_stated_in_prose(conn, [{"name": "Oriel Rendle", "role": "overseer Ssalvage"}], prose)
        self.assertEqual(out[0]["role"], "overseer")

    def test_prose_job_still_wins_over_a_different_op_job(self):
        from app import world
        from app.db import connect

        seed_yard()
        prose = "The overseer, a grizzled man named Oldfield, is scribbling something on a ledger."
        with connect() as conn:
            out = world._roles_stated_in_prose(conn, [{"name": "Oldfield", "role": "village reeve"}], prose)
        self.assertEqual(out[0]["role"], "overseer")


class SceneFocusLineIsRepaired(unittest.TestCase):
    def test_t3_line(self):
        from app.prose_state import repair_meta_leaks

        text = (
            "You begin to gather debris and sweep the floor.\n\n"
            "The scene is focused on the job of cleaning the decks, with Oriel Rendle [[A]] as the central figure."
        )
        out, fixes = repair_meta_leaks(text)
        self.assertNotIn("central figure", out)
        self.assertIn("gather debris", out)
        self.assertTrue(fixes)

    def test_a_story_sentence_stays(self):
        from app.prose_state import repair_meta_leaks

        text = "The square is focused on the gallows, every face turned the same way."
        self.assertEqual(repair_meta_leaks(text)[0], text)


class LearnedIsEarnedInPlay(unittest.TestCase):
    """T6: four setup skills and one dig made a level-1 character 'Learned' (#122)."""

    def _learned(self, learned: int) -> bool:
        import json

        from app import titles
        from app.db import connect, init_db

        init_db()
        with connect() as conn:
            conn.execute("DELETE FROM player_skills")
            for i in range(4):
                conn.execute(
                    "INSERT INTO player_skills (name, value, notes) VALUES (?, 5, ?)",
                    (f"Setup skill {i}", "Start rank D; tracked by practice; limit: none"),
                )
            for i in range(learned):
                conn.execute(
                    "INSERT INTO player_skills (name, value, notes) VALUES (?, 1, ?)",
                    (f"Learned skill {i}", "Learned by doing: something"),
                )
            row = conn.execute("SELECT requirements_json FROM titles WHERE name = 'Learned'").fetchone()
            return titles._check_requirement(json.loads(row[0]), conn)

    def test_setup_skills_do_not_count(self):
        self.assertFalse(self._learned(1))
        self.assertTrue(self._learned(5))

    def test_peacekeeper_is_not_paid_for_jobs(self):
        import json

        from app import titles
        from app.db import connect, init_db

        init_db()
        with connect() as conn:
            row = conn.execute("SELECT requirements_json FROM titles WHERE name = 'Peacekeeper'").fetchone()
            self.assertEqual(json.loads(row[0])["type"], "custom")

    def test_old_saves_move_to_the_new_rules(self):
        import json

        from app import titles
        from app.db import connect, init_db

        init_db()
        with connect() as conn:
            conn.execute(
                "UPDATE titles SET requirements_json = ? WHERE name = 'Learned'",
                (json.dumps({"type": "skills_count_min", "count": 5}),),
            )
            titles.init_titles(conn)
            row = conn.execute("SELECT requirements_json FROM titles WHERE name = 'Learned'").fetchone()
        self.assertEqual(json.loads(row[0])["type"], "skills_learned_min")


class FirstScenePronouns(unittest.TestCase):
    """T1: Oriel was 'his voice' on her first scene, then 'she' from T2; T1 never pinned."""

    def test_first_scene_commits(self):
        from app.world import infer_npc_pronouns

        prose = (
            "You approach the overseer, Oriel Rendle, the rag picker.\n\n"
            "\"Good morn,\" Oriel says, his voice rough from years in the yard. \"What can I help you with today?\""
        )
        self.assertEqual(infer_npc_pronouns("Oriel Rendle", prose), "he")

    def test_play_turn_pins_people_made_this_turn(self):
        source = (ROOT / "app" / "world.py").read_text(encoding="utf-8")
        self.assertIn("pronouns_pinned_on_first_scene", source)


class WeatherReachesTheScene(unittest.TestCase):
    """T6: the weather turned in the turn's own minutes, after the packet showed a clear sky."""

    def test_play_turn_refreshes_the_packet(self):
        source = (ROOT / "app" / "world.py").read_text(encoding="utf-8")
        start = source.index("spent = estimate_action_minutes(player_line)")
        block = source[start:start + 2000]
        self.assertIn('mechanics_context["weather_announce"] = ticked.get("weather_announce")', block)


if __name__ == "__main__":
    unittest.main()
