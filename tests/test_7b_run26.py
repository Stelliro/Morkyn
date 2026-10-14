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


class OneWordEcho(unittest.TestCase):
    """Run 31 T2: 'Morning. You stop at the edge of the path and ask, "Morning. Whose grave is that ..."'."""

    def test_dropped_when_the_line_is_there(self):
        from app.narration_pipeline import keep_player_words

        line = 'I stop at the edge of the path. "Morning. Whose grave is that, out here on the flats?"'
        text = ('Morning. You stop at the edge of the path and ask, "Morning. Whose grave is that, out here on the '
                'flats?" Ermengarde looks up from her work.')
        out, _changes = keep_player_words(text, line)
        self.assertTrue(out.startswith("You stop at the edge of the path"))
        self.assertIn('"Morning. Whose grave is that', out)


class ThenYouWalkAndAGestureTag(unittest.TestCase):
    """Run 31 T5: ', then you turn and walk back towards the town' ran on, and 'You nod, "..."' was kept."""

    LINE = ('"I will. And if you hear of salvage work, or anyone who needs a runner, send them my way." '
            'I stand and brush the earth from my knees.')

    def test_cut_mid_sentence_walk(self):
        from app import llm

        text = ("You stand and brush the earth from your knees, the morning sun casting a warm glow over the graveyard. "
                "Ermengarde pauses and looks at you, her weathered face a mix of surprise and a hint of a smile.\n\n"
                "Ermengarde nods in response before she returns to her task. You watch for a moment, the morning breeze "
                "carrying the scent of salt and earth, then you turn and walk back towards the town.\n\n"
                "The town square is bustling with activity.")
        turn = {"narration": text, "narration_segments": [{"label": "paragraph", "text": x} for x in text.split("\n\n")]}
        out = llm._cut_scene_after_completed_act(turn, self.LINE)
        self.assertNotIn("walk back", out["narration"])

    def test_gesture_tag_is_the_player(self):
        from app.narration_pipeline import drop_invented_player_speech

        paras = ['"Back so soon?" she asks.', 'You nod, "Just a few things to attend to. Thanks for the offer, Kit."']
        self.assertEqual(len(drop_invented_player_speech(paras, self.LINE)[1]), 1)
        self.assertEqual(drop_invented_player_speech(['You nod, and she says, "Fine."'], self.LINE)[1], [])


class ASearchShownDoneWithoutAFind(unittest.TestCase):
    """Run 31 T7: 'I read the salvage notices ..., looking for the pay' then the prose walked into the reeve's office."""

    def test_cut(self):
        from app import llm

        line = "I read the salvage notices on the board, one by one, looking for the pay and who posted them."
        text = ("You read the notices on the board, one by one, looking for the pay and who posted them. The notices "
                "are mostly in faded ink. You scan the list, noting a few postings but none with a high reward.\n\n"
                "The harbour reeve's office is not far. You push open the door and step inside.\n\n"
                "The office is cluttered with papers and charts.")
        turn = {"narration": text, "narration_segments": [{"label": "paragraph", "text": x} for x in text.split("\n\n")]}
        out = llm._cut_scene_after_completed_act(turn, line)
        self.assertNotIn("step inside", out["narration"])


class Run32Opening(unittest.TestCase):
    """Run 32 T0: a menu split in two sentences, 'Maud Venn [[A]], tallyman: "..."', and a drawn Tamsin."""

    TEXT = ("The morning sun casts sharp shadows over Saltmarrow, a harbour town that time seems to have forgotten. "
            "Saltshards crunch underfoot as you walk along the main street, lined with shops and workshops.\n\n"
            "You could head to the flats now and pull salvage, but the water is still low. Or you might visit the inn "
            "for a cup of tea and a moment's respite.\n\n"
            "A figure steps out from behind Coldwell and Sons, a woman with a warm smile and a familiar look in her "
            "eyes. She is Maud Venn, the town's tallyman.\n\n"
            'Maud Venn [[A]], tallyman: "Good morning. How are you holding up?"')

    def test_split_menu_and_label(self):
        from app.llm import _drop_menu_sentences
        from app.prose_state import repair_meta_leaks

        out, count = _drop_menu_sentences(self.TEXT)
        self.assertEqual(count, 2)
        self.assertNotIn("Or you might", out)
        self.assertIn('Maud Venn [[A]] says, "Good morning.', repair_meta_leaks(out)[0])

    def test_figure_is_the_listed_person(self):
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        with connect() as conn:
            loc = conn.execute("SELECT current_location_id FROM player").fetchone()[0]
            conn.execute("DELETE FROM npcs")
            conn.execute("INSERT INTO npcs (code, location_id, name, role) VALUES ('A', ?, 'Maud Venn', 'tallyman')", (loc,))
            made = world._ensure_npcs_from_narration(
                conn, {"npcs": [{"code": "A", "name": "Maud Venn", "role": "tallyman"}]}, self.TEXT, loc
            )
            names = [r[0] for r in conn.execute("SELECT name FROM npcs").fetchall()]
        self.assertEqual(made, [])
        self.assertEqual(names, ["Maud Venn"])


class GluedThe(unittest.TestCase):
    """Run 32 T1-T2: 'theflats' became a place 'Theflats' and a fact about it."""

    def test_split_only_a_word_that_stands_alone(self):
        from app.turn_dsl import parse_dsl_turn, unglue_the

        self.assertEqual(unglue_the("Run out to theflats today.", "the tallies for the flats"), "Run out to the flats today.")
        self.assertEqual(unglue_the("Theobald waits. There, then, theme.", "the flats"), "Theobald waits. There, then, theme.")
        turn = parse_dsl_turn('===NAR===\nYou look out over theflats.\n===OPS===\nMOVE "Theflats"\n', "I look at the flats.")
        self.assertIn("the flats", turn["narration"])


class AskingThePayOpensTheParser(unittest.TestCase):
    """Run 32 T2: 'what does the run pay?' answered with two runs and 'a few coppers'; the parser was never asked."""

    def test_gate(self):
        from app.quest_parser import quest_parse_gate

        self.assertEqual(quest_parse_gate("She nods.", '"Ready. What are the tallies, and what does the run pay?"'), "player_asks_pay")
        self.assertEqual(quest_parse_gate("She nods.", '"How much for the rope?"'), "")


class TheStorehouseThePlayerNamed(unittest.TestCase):
    """Run 32 T4: 'I walk out to the northernmost storehouse' made 'Saltmarrow Supplies' (from 'goods and supplies')."""

    def test_named_from_the_line(self):
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        prose = ("You walk out onto the firm ground, heading towards the northernmost storehouse. You knock on the door, "
                 "and Maud Venn steps aside to let you in. The storehouse is a small, cozy room filled with various "
                 "goods and supplies.")
        line = "I walk out to the northernmost storehouse with the tally sticks, keeping to the firm ground."
        with connect() as conn:
            shown = world._venue_shown_in_prose(conn, {"npcs": []}, prose, player_input=line)
        self.assertIsNotNone(shown)
        self.assertEqual(shown["name"], "Northernmost Storehouse")


class HandedWhatThePlayerHeldOutAHandFor(unittest.TestCase):
    """Run 32 T3: 'I hold out my hand for the tally sticks' and 'Maud nods and hands you the sticks'; nothing granted."""

    def test_granted_with_the_players_name(self):
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        line = '"I will take both tallies, the storehouse first." I hold out my hand for the tally sticks.'
        prose = ('"I will take both tallies, the storehouse first," you say. You hold out your hand for the tally '
                 "sticks. Maud Venn, the tallyman, nods and hands you the sticks.")
        with connect() as conn:
            added = world._grant_shown_takes(conn, [], prose, line)
            self.assertEqual([a["name"] for a in added], ["tally sticks"])
            self.assertEqual(world._grant_shown_takes(conn, [], "She hands you a nod and the sticks.", "I wait by the door."), [])


class NewPlaceOnlyInTheCutPart(unittest.TestCase):
    """Run 32 T1: LOC_NEW 'Northernmost Flats' named only after the cut was still stored."""

    def test_dropped(self):
        from app import llm

        turn = {"locations": [{"name": "Northernmost Flats"}, {"name": "The Bell's Rest"}]}
        head = 'You tuck the reckoner away. Maud smiles. "Ready?" The Bell\'s Rest stands at the corner.'
        tail = '"Let\'s do it." Maud hands you a book. "These are for the northernmost flats." You walk north.'
        dropped = llm._drop_ops_of_cut_tail(turn, head, tail, '"Do you have any tallies?"')
        self.assertIn("LOC_NEW northernmost flats", dropped)
        self.assertEqual([p["name"] for p in turn["locations"]], ["The Bell's Rest"])


class ATripWithWorkAtItsEnd(unittest.TestCase):
    """Run 33 T2: the wreckage was worked, then the prose walked Isk back to the trading post and moved her."""

    LINE = ("I head down into the lower district along the old sea wall, watching the water line, and start working "
            "through the wreckage of the first drowned house for wood or metal worth hauling back.")
    TEXT = ("You head down into the old sea wall, the wind whipping at your clothes. The first house you enter is a "
            "shadow of its former self. You work through the wreckage, your hands searching for wood or metal.\n\n"
            "Sarra Tolley, the keeper of the Salt Edge Trading Post, watches from the wall. \"Good work,\" she calls.\n\n"
            "With a final piece in hand, you step back out onto the sea wall and make your way back to the trading "
            "post.\n\nSarra is still there. \"You've done well this morning.\"")

    def test_cut_and_move_dropped(self):
        from app import llm

        point = llm._completion_cut_point(self.TEXT, self.LINE)
        self.assertTrue(point and point["trigger"].startswith("With a final piece"))
        turn = {"player": {"move_to_location": "Salt Edge Trading Post"}}
        llm._drop_ops_of_cut_tail(turn, self.TEXT[:point["cut"]], self.TEXT[point["cut"]:], self.LINE)
        self.assertIsNone(turn["player"]["move_to_location"])

    def test_a_plain_trip_is_still_left_to_its_arrival(self):
        from app import llm

        text = ("You walk along the sea wall towards the lower district. The wind is steady. You reach the first "
                "drowned house. With the tide low, you step down into the mud and head for the second house.")
        self.assertIsNone(llm._after_act_cut_point(
            __import__("app.prose_state", fromlist=["x"]).sentence_spans(text), "I walk to the lower district.",
            "I walk to the lower district.", "I walk to the lower district.", travelling=True))


class WalkingOverToAPerson(unittest.TestCase):
    """Run 34 T1: 'I walk over to Kit at the edge of the flats' minted 'The Flats', and the prose walked Isk off."""

    LINE = 'I walk over to Kit at the edge of the flats. "Morning. Find anything worth keeping in that pile?"'

    def test_not_travel(self):
        from app.world import travel_intent

        self.assertFalse(travel_intent(self.LINE))
        self.assertTrue(travel_intent("I walk over to Kit, then head out to the flats."))
        self.assertTrue(travel_intent("I head to the docks."))

    def test_cut_after_the_talk(self):
        from app.llm import _completion_cut_point

        text = ('You walk over to Kit at the edge of the flats. "Morning. Find anything worth keeping in that pile?"\n\n'
                'Kit glances down at the pile. "A few odds and ends, but nothing worth keeping."\n\n'
                "You thank Kit and make your way towards the flats. The mud squelches under your boots.")
        point = _completion_cut_point(text, self.LINE)
        self.assertTrue(point and point["trigger"].startswith("You thank Kit"))


class Run34SunkenRoof(unittest.TestCase):
    """Run 34 T2: the coin pulled from the debris, the voice named only after the cut, and 'The Flats [[L2]]' surface'."""

    LINE = ("I wade out to the first sunken roof I can reach before the water turns, and pry at the loose slates and "
            "gutter metal with my hands, looking for anything worth hauling back.")
    KEPT = ("The water is still at your ankles when you reach the first sunken roof. You pry at the loose slates. "
            "You pull a small, tarnished coin from the debris, your fingers closing around it.\n\n"
            'A voice from the shore calls out, "What are you doing out there?"')

    def _world(self):
        from app import world
        from app.db import init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        return world

    def test_coin_pulled_from_the_debris(self):
        from app.db import connect

        world = self._world()
        with connect() as conn:
            added = world._grant_shown_takes(conn, [], self.KEPT, self.LINE)
        self.assertEqual([a["name"] for a in added], ["small tarnished coin"])

    def test_voice_takes_the_name_from_the_cut_part(self):
        from app.db import connect

        world = self._world()
        tail = 'It is Ivo Garner, a chamber servant who tends to the keeper. He steps closer.\n\n"I found this," you say.'
        with connect() as conn:
            loc = conn.execute("SELECT current_location_id FROM player").fetchone()[0]
            conn.execute("DELETE FROM npcs")
            made = world._ensure_npcs_from_narration(conn, {"npcs": [], "_dsl": {"cut_tail": tail}}, self.KEPT, loc)
        self.assertEqual([(n["name"], n["role"]) for n in made], [("Ivo Garner", "chamber servant")])

    def test_no_code_before_a_possessive(self):
        from app.llm import _inject_entity_codes_for_known_names

        out = _inject_entity_codes_for_known_names("worth hauling back to the Flats' surface. The Flats are wide.",
                                                   {"L2": "The Flats"})
        self.assertIn("the Flats' surface", out)
        self.assertIn("The Flats [[L2]] are wide", out)


class Run35PlankAtTheSeawall(unittest.TestCase):
    """Run 35 T1: single-quoted dialogue from the verifier, and a talk line run on into an invented repair."""

    LINE = 'I walk over to the figure at the seawall. "Morning. That plank work for the harbour master, or your own?"'

    def test_single_quotes_become_double(self):
        from app.turn_dsl import double_single_quoted_speech

        out = double_single_quoted_speech("You show him the tools and explain, 'I'm going to patch up this plank.'")
        self.assertIn('"I\'m going to patch up this plank."', out)
        same = "The flat-runner's boots. 'Tis the tide's way. He said 'no' twice."
        self.assertEqual(double_single_quoted_speech(same), same)
        mixed = "He says \"go\". She said 'Fine.' then left."
        self.assertEqual(double_single_quoted_speech(mixed), mixed)

    def test_talk_line_done_when_said(self):
        from app.llm import _completion_cut_point

        text = ('"Morning. That plank work for the harbour master, or your own?" you ask. You carefully examine the '
                "plank.\n\nThe Leaning Pear Cookshop is just a few steps away. You step inside and find a few tools you "
                'need, then head back to the seawall.\n\nIvo is still there. "What are you doing, flat-runner?"')
        point = _completion_cut_point(text, self.LINE)
        self.assertTrue(point and point["trigger"].startswith("You step inside"))


class PlayerLineTagged(unittest.TestCase):
    """Run 36 T2: '"Do you know who is taking a boat out ...?" Emrys Slade ponders' read as Emrys's line."""

    def test_tag_added(self):
        from app.narration_pipeline import keep_player_words

        line = '"Not trouble. Work." I keep my eyes on the boat. "Do you know who is taking a boat out this early?"'
        text = ('"Not trouble. Work," you say. You keep your eyes on the boat.\n\n'
                '"Do you know who is taking a boat out this early?" Emrys Slade ponders for a moment. "Tobin."')
        out, _ = keep_player_words(text, line)
        self.assertIn('this early?" you ask. Emrys Slade ponders', out)

    def test_statement_gets_a_comma(self):
        from app.narration_pipeline import keep_player_words

        out, _ = keep_player_words('You nod. "I will take my gold now, Jehane." Jehane looks up.',
                                   '"I will take my gold now, Jehane."')
        self.assertIn('"I will take my gold now, Jehane," you say. Jehane looks up.', out)


class ThanksNeverGiven(unittest.TestCase):
    """Run 36 T2: 'You thank Emrys for the information and continue to observe the boat' after a question."""

    LINE = '"Not trouble. Work." I keep my eyes on the boat. "Do you know who is taking a boat out this early?"'

    def test_only_the_thanks_goes(self):
        from app.llm import _strip_player_acts_from_sentence as strip

        self.assertEqual(strip("You thank Emrys for the information and continue to observe the boat.", self.LINE, self.LINE)[0],
                         "You continue to observe the boat.")
        self.assertEqual(strip("You thank Rosamund and Percival, feeling relief.", self.LINE, self.LINE)[0], "")

    def test_kept_when_the_player_thanked(self):
        from app.llm import _strip_player_acts_from_sentence as strip

        line = '"Thanks, Emrys." I keep watching the boat.'
        sentence = "You thank Emrys and keep watching the boat."
        self.assertEqual(strip(sentence, line, line)[0], sentence)


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
