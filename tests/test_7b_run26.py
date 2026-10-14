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


class IntroducedThenTagged(unittest.TestCase):
    """Run 30 T0: "A mole catcher named Dunstan Wadley" then '"Morning," Dunstan calls out' stored a bare "Dunstan"."""

    def test_full_name_stored(self):
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        text = ("You stand at the edge of the market square.\n\n"
                "A mole catcher named Dunstan Wadley, with a stubbled face and a battered hat, stands near the tannery "
                "entrance. He glances at you with a mix of curiosity and wariness.\n\n"
                "\"Morning, flat-runner,\" Dunstan calls out, his voice rough from sleep. \"Need any help with the moles?\"")
        with connect() as conn:
            loc = conn.execute("SELECT current_location_id FROM player").fetchone()[0]
            conn.execute("DELETE FROM npcs")
            world._ensure_npcs_from_narration(conn, {"npcs": []}, text, loc)
            names = [r[0] for r in conn.execute("SELECT name FROM npcs").fetchall()]
        self.assertEqual(names, ["Dunstan Wadley"])


class HooksSentence(unittest.TestCase):
    """Run 30 T0: "The tannery and the mole catcher offer two concrete hooks: ..." shipped."""

    def test_dropped_and_not_asked(self):
        from app import world
        from app.prose_state import repair_meta_leaks

        text = ("You stand in the square. The tannery looms to your left, its barrels stacked high with hides.\n\n"
                "The tannery and the mole catcher offer two concrete hooks: assist in mole control or ignore him.")
        out, fixes = repair_meta_leaks(text)
        self.assertNotIn("hooks", out)
        self.assertIn("A variety of ropes hang from hooks.", repair_meta_leaks("A variety of ropes hang from hooks.")[0])
        self.assertNotIn("hooks", world.OPENING_SCENE_INPUT)


class RunsIsNotARune(unittest.TestCase):
    """Run 30 T3: 'feel which way the tunnel runs' de-inflected to 'rune' and rolled symbol lore."""

    def test_noun_triggers_as_typed(self):
        from app.skill_checks import infer_check_from_action

        def code(line):
            return (infer_check_from_action(line, {}) or {}).get("skill_code")

        self.assertNotEqual(code("I push my arm into the soft earth to feel which way the tunnel runs."), "symbol_lore")
        self.assertEqual(code("I study the runes carved over the door."), "symbol_lore")
        self.assertEqual(code("I trace the etched sigil with a finger."), "symbol_lore")


class AFollowerIsNotToldTheName(unittest.TestCase):
    """Run 30 T6: Dunstan, a scene companion since T2, said "Good thinking, Isk." and NPC_NOTE wrote knows_your_name."""

    def test_companion_and_packet_note(self):
        from app import world
        from app.db import connect, init_db
        from app.party import sync_scene_companions

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        with connect() as conn:
            loc = conn.execute("SELECT current_location_id FROM player").fetchone()[0]
            conn.execute("DELETE FROM npcs")
            conn.execute("INSERT INTO npcs (code, location_id, name, role, known_facts) VALUES ('A', ?, 'Dunstan', 'mole catcher', '[]')", (loc,))
            sync_scene_companions(conn, [{"code": "A", "name": "Dunstan"}], "Dunstan follows you to the old pits.", 2)
            world._apply_index_updates(conn, [{"entity_type": "npc", "code": "A", "summary_append": "knows_your_name",
                                               "known_fact": "knows_your_name"}])
            row = conn.execute("SELECT summary, known_facts FROM npcs WHERE code = 'A'").fetchone()
        self.assertNotIn("knows_your_name", str(row[0]) + str(row[1]))
        state = world.get_state()
        flags = [n.get("knows_player_name") for loc_ in state.get("locations") or [] for n in loc_.get("npcs") or []
                 if n.get("code") == "A"]
        self.assertTrue(flags)
        self.assertFalse(any(int(f or 0) for f in flags))


class ScriptLabel(unittest.TestCase):
    """Run 30 T6: 'Dunstan [[A]]: "I'll fetch a few more from the storeroom."' shipped as a script line."""

    def test_tagged(self):
        from app.prose_state import repair_meta_leaks

        text = 'You keep at it.\n\nDunstan [[A]]: "I\'ll fetch a few more from the storeroom."\n\nAbel Hollis: "Rest."'
        out, fixes = repair_meta_leaks(text)
        self.assertIn('Dunstan [[A]] says, "I\'ll fetch a few more from the storeroom."', out)
        self.assertIn('Abel Hollis says, "Rest."', out)
        self.assertEqual(repair_meta_leaks('You read the sign: "Closed".')[0], 'You read the sign: "Closed".')


class PeriodBeforeTag(unittest.TestCase):
    """Run 30 T8: '...before noon." you ask Dunstan' kept its full stop before a lowercase tag."""

    def test_comma(self):
        from app.prose_state import repair_meta_leaks

        out = repair_meta_leaks('"How many are left? I can cover the rest before noon." you ask Dunstan.')[0]
        self.assertIn('before noon," you ask Dunstan.', out)
        same = '"Fine." You turn away.'
        self.assertEqual(repair_meta_leaks(same)[0], same)


class RoleKeptOnRedeclare(unittest.TestCase):
    """Run 30: Dunstan the mole catcher became 'runner' (Isk's Flat-runner) and then 'local' (no role given)."""

    def test_kept(self):
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        with connect() as conn:
            conn.execute("UPDATE player SET title = 'Flat-runner'")
            loc = conn.execute("SELECT current_location_id FROM player").fetchone()[0]
            conn.execute("DELETE FROM npcs")
            conn.execute("INSERT INTO npcs (code, location_id, name, role) VALUES ('A', ?, 'Dunstan', 'mole catcher')", (loc,))
            for given in ("runner", "", "local"):
                world._upsert_npc(conn, {"code": "A", "name": "Dunstan", "role": given, "location": loc})
                self.assertEqual(conn.execute("SELECT role FROM npcs WHERE code = 'A'").fetchone()[0], "mole catcher")
            world._upsert_npc(conn, {"code": "A", "name": "Dunstan", "role": "harbour reeve", "location": loc})
            self.assertEqual(conn.execute("SELECT role FROM npcs WHERE code = 'A'").fetchone()[0], "harbour reeve")


class UnownedWeapon(unittest.TestCase):
    """Run 30 T12: 'one hand resting near the hilt of your knife' with no knife owned."""

    def test_clause_dropped_unless_owned_or_typed(self):
        from app.prose_state import repair_unowned_weapon

        text = ("The floor creaks under your boots as you move quietly, one hand resting near the hilt of your knife. "
                "The ground trembles slightly, and you lean in closer, straining to hear.")
        out, fixes = repair_unowned_weapon(text, ["worn boots"])
        self.assertNotIn("knife", out)
        self.assertIn("The floor creaks under your boots as you move quietly.", out)
        self.assertEqual(repair_unowned_weapon(text, ["worn boots", "gutting knife"])[1], [])
        self.assertEqual(repair_unowned_weapon(text, [], "I pry the lid off with my knife.")[1], [])


class RefusedFindFollowOn(unittest.TestCase):
    """Run 31 T1: "It's a small piece, but it might be useful." stayed after the refused find went."""

    def test_follow_on_goes(self):
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        prose = ("You walk out along the driftwood path, the mud still damp and cold beneath your boots, and look over "
                 "what the last tide left.\n\nThe tide's marks are faint, but you can make out the ripple patterns. "
                 "You find a piece of wood half-buried in the mud. It's a small piece, but it might be useful.\n\n"
                 "Ermengarde watches you for a moment before returning to her work.")
        result = {"narration": prose, "narration_segments": [{"label": "paragraph", "text": p} for p in prose.split("\n\n")]}
        with connect() as conn:
            world._reconcile_prose_with_state(
                conn, result, rejected=[{"name": "piece of wood", "tokens": ["piece", "wood"], "outcome": "gain"}],
                movement_report={}, gold_note=None, purse_note=None,
            )
        text = world._narration_text(result)
        self.assertNotIn("piece", text)
        self.assertIn("Ermengarde watches you", text)


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
