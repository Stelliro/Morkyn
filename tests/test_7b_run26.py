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


class CapitalYouTagAndOneSharedWord(unittest.TestCase):
    """Run 28 T6: '"Flat-runner. My name is Isk. But what's in it for me?" You ask, eyeing the tanner' kept."""

    def test_dropped(self):
        from app.narration_pipeline import drop_invented_player_speech

        line = '"What task, and what\'s your name? I don\'t follow strangers around Saltmarrow without one."'
        paras = [
            '"What task, and what\'s your name? I don\'t follow strangers around Saltmarrow without one."',
            'Stephen\'s eyes narrow. "It\'s Stephen. You?"',
            '"Flat-runner. My name is Isk. But what\'s in it for me?" You ask, eyeing the tanner with interest.',
        ]
        self.assertEqual(len(drop_invented_player_speech(paras, line)[1]), 1)
        self.assertEqual(drop_invented_player_speech(['"Where is it?" You ask.'], '"Where is it?"')[1], [])


class StrayUnderscore(unittest.TestCase):
    """Run 29 T7: the model wrote 'Is the _hull worth patching' into the player's own line."""

    def test_repaired(self):
        from app.prose_state import repair_meta_leaks

        out, fixes = repair_meta_leaks('"Is the _hull worth patching?" The _hull groans. A [[C]] code and _italic_ stay.')
        self.assertIn('"Is the hull worth patching?" The hull groans.', out)
        self.assertIn("[[C]]", out)
        self.assertEqual([f["why"] for f in fixes if f["why"] == "stray_underscore"], ["stray_underscore"])


class FairWeatherInAStorm(unittest.TestCase):
    """Run 29 T9: 'The sea outside is calm, the waves barely lapping' under a heavy storm."""

    def test_dropped_in_rough_weather_only(self):
        from app.prose_state import repair_fair_weather

        text = ("Osric looks at you. \"The sea is calm enough today,\" he says. The sea outside is calm, the waves "
                "barely lapping at the hull. Gulls call in the distance over the long grey quay, their cries thin. "
                "Rope creaks against the bollards and the planks are slick under your boots.")
        out, fixes = repair_fair_weather(text, "storm")
        self.assertNotIn("barely lapping", out)
        self.assertIn('"The sea is calm enough today,"', out)
        self.assertEqual(len(fixes), 1)
        self.assertEqual(repair_fair_weather(text, "clear")[1], [])
        self.assertEqual(repair_fair_weather("Despite the storm, you remember the clear sky of yesterday and "
                                             "the gulls over the long grey quay, their cries thin.", "storm")[1], [])

    def test_a_fresh_storm_builds(self):
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        with connect() as conn:
            for minute in range(0, 1440, 7):
                world.set_weather(conn, {"kind": "clear"})
                out = world.tick_weather(conn, minutes_advanced=20, time_after={"day": 1, "minute": minute, "hour": minute // 60})
                if out["weather"]["kind"] != "clear":
                    self.assertLessEqual(out["weather"]["strength"], 0.37, out["weather"])


class ABoatsBowIsNotAWeapon(unittest.TestCase):
    """Run 29 T10: 'I check the knot on the bow line' rolled ranged, crit-failed, and hurt Isk 'unskilled with bow'."""

    def test_no_ranged_roll(self):
        from app.skill_checks import infer_check_from_action

        line = ('"Keep the pay, then. I did not come for coin from you." I check the knot on the bow line once more '
                'and look toward the guildhall through the rain.')
        check = infer_check_from_action(line, {}) or {}
        self.assertNotEqual(check.get("skill_code"), "ranged")
        self.assertNotEqual(check.get("weapon_or_tool"), "bow")
        self.assertEqual((infer_check_from_action("I draw my bow and aim at the gull.", {}) or {}).get("skill_code"), "ranged")
        self.assertNotEqual((infer_check_from_action("I walk to the bow of the ship.", {}) or {}).get("skill_code"), "ranged")


class PastedLineAndWalkIn(unittest.TestCase):
    """Run 29 T10: Osric's T9 reply came back unquoted as narration, and the prose walked Isk into the guildhall."""

    LINE = ('"Keep the pay, then. I did not come for coin from you." I check the knot on the bow line once more '
            'and look toward the guildhall through the rain.')

    def test_pasted_line_dropped(self):
        from app.narration_pipeline import drop_speech_said_before

        earlier = ["The work is always a gamble, flat-runner,",
                   "But the weather is on our side for once. If the tide holds, we might as well take the chance and keep the pay for ourselves."]
        para = ("You check the knot on the bow line once more. The work is always a gamble, flat-runner, but the "
                "weather is on our side for once. If the tide holds, we might as well take the chance and keep the "
                "pay for ourselves. You see a ship moored at the dock.")
        kept, dropped = drop_speech_said_before([para], earlier, [], self.LINE)
        self.assertEqual(len(dropped), 2)
        self.assertIn("You see a ship moored at the dock.", kept[0])

    def test_walk_in_cut(self):
        from app import llm

        text = ("“Keep the pay, then. I did not come for coin from you,” you say. You check the knot on the bow "
                "line once more and peer through the rain toward The Guildhall [[L2]]. The rain runs off the planks "
                "and the rope creaks against the post. You push the door of The Guildhall [[L2]] open and step inside.\n\n"
                "The hall is dimly lit by a few oil lamps.")
        turn = {"narration": text, "narration_segments": [{"label": "paragraph", "text": x} for x in text.split("\n\n")]}
        out = llm._cut_scene_after_completed_act(turn, self.LINE)
        self.assertNotIn("step inside", out["narration"])


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
