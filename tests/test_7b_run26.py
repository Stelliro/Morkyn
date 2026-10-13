"""7B run 26 (Qwen2.5 7B on MLE, agent as player): an offered job's pay reaches the narrator."""
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-7b-run26-"))
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


class OfferPaysReachesThePacket(unittest.TestCase):
    """T2: "What does it pay?" got "I see" - open_offers carried no sum."""

    def test_list_and_view(self):
        from app import world
        from app.db import connect, init_db
        from app.local_intel import list_open_offers

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        with connect() as conn:
            conn.execute(
                "INSERT INTO quests (code, title, description, status, reward_gold) VALUES ('Q1', 'Tailoring a coat', '', 'offered', 11)"
            )
        offers = list_open_offers()
        self.assertEqual(offers[0]["pays_gold"], 11)

        from app import prompts

        source = Path(prompts.__file__).read_text(encoding="utf-8")
        self.assertIn('slim["pays"]', source)


class TakeThePatrol(unittest.TestCase):
    """Run 27 T3: "I'll take the patrol" did not take "Help with mudflats patrol"."""

    def test_accept_by_title_word(self):
        from app.quest_parser import player_takes_job

        quest = {"id": 1, "code": "Q1", "title": "Help with mudflats patrol", "status": "offered"}
        self.assertTrue(player_takes_job(quest, '"Fifteen gold. I\'ll take the patrol, Avice."', [quest]))
        self.assertFalse(player_takes_job(quest, '"I\'ll take the road home."', [quest]))
        self.assertFalse(player_takes_job(quest, '"Not yet. I\'ll take the patrol later maybe."', [quest]))


class NamedWithNoJob(unittest.TestCase):
    """Run 27 T1: "Gisela Hatcher, a stout woman with a stern face" stored nobody."""

    def test_stored_without_a_job(self):
        from app.world import _introduced_people

        self.assertEqual(
            _introduced_people("Gisela Hatcher, a stout woman with a stern face, is standing on the quayside.", []),
            [{"name": "Gisela Hatcher", "role": ""}],
        )


class NotPartOfAnInnsName(unittest.TestCase):
    """Run 27 T5: "The Twice-Blessed Hound, the steady heat of the day" stored a person called Blessed Hound."""

    def test_skipped(self):
        from app.world import _introduced_people

        self.assertEqual(_introduced_people("You step into The Twice-Blessed Hound, the steady heat of the day breaking.", []), [])


class MiddaySun(unittest.TestCase):
    """Run 27 T5: "the sun climbs higher" at 12:18 was turned to "sinks"."""

    def test_band(self):
        from app.prose_state import repair_sun_words

        self.assertEqual(repair_sun_words("The sun climbs higher.", 12)[1], [])
        self.assertTrue(repair_sun_words("The sun climbs higher.", 15)[1])
        self.assertTrue(repair_sun_words("The sun begins to sink.", 11)[1])


class ThankAndWalkAfterHerOwnQuestion(unittest.TestCase):
    """Run 28 T2: after Isk's own question, "You thank her and turn to head towards the clock tower" ran on."""

    def test_cut(self):
        from app import llm

        line = ('"No boats, no salvage." I look out at the water. "Then I\'ll try my luck on the flats myself. '
                'Where\'s the reeve keep the tide tables these days?"')
        text = (
            "You look out at the water, the tide still high and the boats not yet in. \"No boats, no salvage.\" "
            "You say, \"Then I'll try my luck on the flats myself. Where's the reeve keep the tide tables these days?\" "
            "Lettice looks up from her notes, her pen still in her hand and her lips pressed thin.\n\n"
            "You thank her and turn to head towards the clock tower. You climb the steps and take the tide tables."
        )
        turn = {"narration": text, "narration_segments": [{"label": "paragraph", "text": x} for x in text.split("\n\n")]}
        out = llm._cut_scene_after_completed_act(turn, line)
        self.assertEqual(out["_scene_cut"]["trigger"], "You thank her and turn to head towards the clock tower.")
        self.assertNotIn("clock tower", out["narration"])


class AWaitMovesNobody(unittest.TestCase):
    """Run 27 T4: a Wait described the inn's empty inside through an open door and put the player in it."""

    def test_no_venue_shown_on_a_wait(self):
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        prose = ("You wait out the afternoon. The inn's door stands open; you step inside the inn. Inside, the pub is "
                 "empty, save for the smell of ale.")
        with connect() as conn:
            result = {"narration": prose, "player": {}}
            report = world.resolve_movement(
                conn, result, "__wait_request__: kind=wait minutes=240", intent="wait", narration=prose
            )
        self.assertNotEqual(report.get("rule"), "venue_shown")
        self.assertFalse(result["player"].get("move_to_location"))


if __name__ == "__main__":
    unittest.main()
