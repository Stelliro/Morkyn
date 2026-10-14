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

    def test_no_second_tag(self):
        from app.narration_pipeline import keep_player_words

        line = '"Morning. Nothing yet, the tide is still too high." I nod. "Moles out on the flats? I thought they kept to the gardens."'
        text = ('"Morning. Nothing yet, the tide is still too high," you reply. "Moles out on the flats? I thought they '
                'kept to the gardens."\n\nOrabel hums.')
        self.assertNotIn("you ask", keep_player_words(text, line)[0])

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


class OrphanSpeechLead(unittest.TestCase):
    """Run 36 T3: "Emrys Slade [[A]]'s voice cuts through the silence." with his repeated line dropped."""

    def test_dropped_only_when_no_line_follows(self):
        from app.prose_state import drop_orphan_speech_lead

        text = ("You pace back and forth on the dock.\n\nEmrys Slade [[A]]'s voice cuts through the silence.\n\n"
                "You nod, keeping your eyes on the harbour.")
        out, fixes = drop_orphan_speech_lead(text)
        self.assertNotIn("voice cuts", out)
        self.assertEqual(len(fixes), 1)
        kept = "Emrys Slade [[A]]'s voice cuts through the silence. \"Aye, the tide is turning.\""
        self.assertEqual(drop_orphan_speech_lead(kept)[0], kept)


class CheckAgainstTheOneAddressed(unittest.TestCase):
    """Run 36 T6: 'not Emrys. "Tobin, what is under the tarpaulin?"' rolled persuasion vs Emrys."""

    CTX = {"npcs": [{"code": "A", "name": "Emrys Slade", "rank": "F"}], "conversation_turn": {"addressed": ["A"]}}

    def test_turned_away_and_stranger(self):
        from app.skill_checks import _check_with_opposition

        line = 'I keep my eyes on the man in the skiff, not Emrys. "I asked him. Tobin, what is under the tarpaulin?"'
        self.assertIsNone(_check_with_opposition("persuasion", line, self.CTX)["opposition"])
        self.assertEqual(_check_with_opposition("persuasion", '"Emrys, what is under it?"', self.CTX)["opposition"]["name"],
                         "Emrys Slade")


class CoinOnlyInTheCutPart(unittest.TestCase):
    """Run 36 T7: 'Emrys Slade hands you a silver coin' was cut, and the purse still went 12 -> 16."""

    def test_gain_dropped(self):
        from app import llm

        head = '"What would you pay me?" Emrys watches you. "Tobin, that is a serious matter."'
        tail = '"Agreed. I will give you a coin." Emrys Slade hands you a silver coin. You take the coin.'
        turn = {"player": {"gold_delta": 1}}
        self.assertIn("GOLD (received only in the cut part)", llm._drop_ops_of_cut_tail(turn, head, tail, "Pay me?"))
        self.assertNotIn("gold_delta", turn["player"])

    def test_bare_tag_dropped(self):
        from app.prose_state import drop_orphan_speech_lead

        out, _ = drop_orphan_speech_lead("Emrys watches you. Emrys asks, his tone shifting subtly.\n\nTobin shifts.")
        self.assertNotIn("asks", out)
        kept = '"Go," Emrys says. Emrys asks, his tone low. "Now?"'
        self.assertEqual(drop_orphan_speech_lead(kept)[0], kept)


class OneWordEchoAfterTheTag(unittest.TestCase):
    """Run 37 T1: '... before the water turns," you ask. Morning. Delphine looks up'."""

    def test_dropped(self):
        from app.narration_pipeline import keep_player_words

        line = 'I go over to Delphine. "Morning. Need any old timber pulled out? I can haul it back before the water turns."'
        text = ('“Morning. Need any old timber pulled out? I can haul it back before the water turns,” you ask. '
                "Morning. Delphine looks up from her workbench.")
        out, _ = keep_player_words(text, line)
        self.assertIn("you ask. Delphine looks up", out)


class Run37Planks(unittest.TestCase):
    """Run 37 T3: the planks moved and paid, the job logged as paid ahead; a new 'Saltmarrow Shop' beside the named one."""

    LINE = ('"A few coins will do. I will take the job." I go through to the back and start carrying the old planks '
            "out to the shed, two at a time, stacking them flat against the wall.")

    def test_work_done_in_the_line(self):
        from app.quest_parser import work_done_in_line

        prose = "You go through to the back. You stack the old planks flat against the wall, two at a time."
        quest = {"title": "Move old planks to the shed"}
        self.assertTrue(work_done_in_line(quest, prose, self.LINE))
        self.assertFalse(work_done_in_line(quest, prose, '"I will take the job." I head to the back.'))
        self.assertFalse(work_done_in_line(quest, prose, self.LINE + " Not done yet, though."))

    def test_existing_shop_named_in_the_entry(self):
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        with connect() as conn:
            here = conn.execute("SELECT current_location_id FROM player").fetchone()[0]
            shop = world._upsert_location(conn, "Delphine Cotteray's Carpenter's Shop", "", parent_id=here, kind="workshop")
            code = conn.execute("SELECT code FROM locations WHERE id = ?", (shop,)).fetchone()[0]
            world._upsert_location(conn, "The Mermaid's Rest", "", parent_id=here, kind="inn")
            prose = (f"You go through to the back of Delphine Cotteray's Carpenter's Shop [[{code}]]. The Mermaid's Rest "
                     "is quiet across the way. The shop is filled with sawdust and tools.")
            shown = world._venue_shown_in_prose(conn, {"npcs": []}, prose, player_input="I go through to the back.")
        self.assertEqual(shown["name"], "Delphine Cotteray's Carpenter's Shop")
        self.assertFalse(shown["minted"])


class OptionListAfterAQuote(unittest.TestCase):
    """Run 38 T0: the list's lead-in took the question before it, and the line was left unclosed."""

    def test_question_kept(self):
        from app.llm import _trim_option_list

        text = ("You stand on the salt-swept flats of Saltmarrow, the harbour town the sea left behind, and the morning "
                "sun casts long shadows over the mud. Nearby, a mole catcher looks up. \"Good morning, flat-runner,\" "
                "she says. \"Have you picked up anything interesting today?\"\n\nYou could:\n- Enter the inn.\n"
                "- Approach her.\n- Walk to the water's edge.")
        out, removed = _trim_option_list(text, floor=50)
        self.assertTrue(out.endswith('anything interesting today?"'), out[-80:])
        self.assertGreater(removed, 0)


class AHorseNamedIsNoHandling(unittest.TestCase):
    """Run 39 T1: 'Is that horse going anywhere near the guild today?' rolled animal handling, a critical failure."""

    def test_trigger(self):
        from app.skill_checks import infer_check_from_action

        line = 'I go over to Odo and the horse. "Morning, Odo. Is that horse going anywhere near the guild today?"'
        self.assertNotEqual((infer_check_from_action(line) or {}).get("skill_code"), "animal_handling")
        self.assertEqual((infer_check_from_action("I try to calm the horse before it bolts.") or {}).get("skill_code"),
                         "animal_handling")


class TheStableMare(unittest.TestCase):
    """Run 39 T2: the mare granted on a price question; 'patting her gently' (the mare) became 'patting his'."""

    def test_price_asked_is_for_sale(self):
        from app.world import _for_sale_context

        self.assertTrue(_for_sale_context("", '"The stable mare will do. What do you want for her for the afternoon?"'))
        self.assertFalse(_for_sale_context("", '"The stable mare will do."'))

    def test_pronoun_of_the_mare_kept(self):
        from app.prose_state import repair_pinned_pronouns

        cast = [{"names": ["Odo Wick", "Odo"], "key": "he"}]
        text = "Odo finishes grooming the mare and steps back, patting her gently."
        self.assertEqual(repair_pinned_pronouns(text, cast)[0], text)


class EngineClockInTheProse(unittest.TestCase):
    """Run 40 T0: 'It is morning, 08:00.'; run 5 T12: 'on duty from 08:00 to 18:00'."""

    def test_repaired_outside_speech(self):
        from app.prose_state import repair_meta_leaks

        self.assertEqual(repair_meta_leaks("It is morning, 08:00. The sun rises.")[0], "It is morning. The sun rises.")
        self.assertEqual(repair_meta_leaks("Abel is a woodcutter, on duty from 08:00 to 18:00.")[0], "Abel is a woodcutter.")
        said = '"Meet me at 08:00," she says.'
        self.assertEqual(repair_meta_leaks(said)[0], said)


class TheOneYouWentToIsTalking(unittest.TestCase):
    """Run 40 T1: Rohese answered Isk's invented 'I can help'; the trip guard skipped the cut."""

    def test_cut_at_her_offer(self):
        from app.llm import _cut_scene_at_invented_request

        line = ('I cross the street to the tannery yard, where Rohese is sharpening her knife. "Morning, Rohese. Rats '
                'bad in the tannery again?"')
        nar = ('"Morning, Rohese. Rats bad in the tannery again?" you ask. Rohese glances up from her knife. "Worse '
               'than usual. A pack of them in the cellar." She sheaths her knife and steps back.\n\n'
               "The air is sharp, carrying the scent of salt and leather, and carts and baskets stand around the yard "
               "as if the workers have been busy since dawn.\n\n"
               'Rohese continues, "If you want, you can help me tonight. I\'m short a hand."\n\n'
               'You consider for a moment. "I can help. What time do you need me?"\n\n'
               '"Meet me at the tannery gate at dusk." She nods.')
        turn = {"narration": nar, "narration_segments": [{"label": "paragraph", "text": p} for p in nar.split("\n\n")]}
        out = _cut_scene_at_invented_request(turn, line, floor=50)
        self.assertNotIn("Meet me at the tannery gate", out["narration"])
        self.assertIn("you can help me tonight", out["narration"])


class TheCoinIsOneCoin(unittest.TestCase):
    """Run 40 T2: 'We'll pay you a small coin' and 'You take the coin' rolled the small band, +10 gold."""

    def test_counted(self):
        from app.prose_state import counted_coins

        self.assertEqual(counted_coins("You take the coin"), 1)
        self.assertIsNone(counted_coins("You take the coins"))
        self.assertIsNone(counted_coins("You take the silver coin"))


class AFreeHandover(unittest.TestCase):
    """Run 41 T1: 'What would a heel of bread cost me?' and 'Here you go. Enjoy your breakfast.' with no price."""

    def test_reads_as_given(self):
        from app.world import _FREE_HANDOVER_RE

        self.assertTrue(_FREE_HANDOVER_RE.search('Margery hands you a heel of bread. "Here you go. Enjoy your breakfast."'))
        self.assertFalse(_FREE_HANDOVER_RE.search('Margery hands you a heel of bread. "That will be two coppers."'))


class NoBuildingAfterTheArrival(unittest.TestCase):
    """Run 41 T3: after reaching the lower district the prose pushed open a door and stepped inside."""

    def test_cut_at_the_entry(self):
        from app.llm import _completion_cut_point

        line = "I pull my hood up and head across the mud toward the drowned lower district."
        text = ("You pull your hood up and head across the mud. You reach the edge of the lower district, where the "
                "ground is firmer. The buildings here are older. You reach a small, abandoned building. The door is "
                "ajar, and you push it open, stepping inside. The interior is dim.")
        point = _completion_cut_point(text, line)
        self.assertTrue(point and point["trigger"].startswith("The door is ajar"))


class Run41DrownedHouse(unittest.TestCase):
    """Run 41 T4: 'small x1' for 'you pull out a small, rusted iron key'; 'The Wren' beside 'The Wren at Saltmarrow'."""

    def test_key_and_inn(self):
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        line = "I stop at the first drowned house and search the mud around its doorstep for anything metal worth hauling back."
        prose = "You crouch and search the mud. After a moment, you pull out a small, rusted iron key."
        with connect() as conn:
            added = world._grant_shown_takes(conn, [], prose, line)
            self.assertEqual([a["name"] for a in added], ["small rusted iron key"])
            here = conn.execute("SELECT current_location_id FROM player").fetchone()[0]
            wren = world._upsert_location(conn, "The Wren at Saltmarrow", "", parent_id=here, kind="inn")
            self.assertEqual(int(world._match_location_by_name(conn, "The Wren")["id"]), int(wren))


class AMenuWrittenAsAnAct(unittest.TestCase):
    """Run 42 T0: 'You approach the Gilded Key Bakehouse, ..., or continue towards the Spindle's Rest ...'."""

    def test_matched(self):
        from app.llm import _MENU_TWO_WAY_RE

        self.assertTrue(_MENU_TWO_WAY_RE.match(
            "You approach the Gilded Key Bakehouse, where Elsabet and Jory work, or continue towards the Spindle's "
            "Rest to see if it is open."))
        self.assertFalse(_MENU_TWO_WAY_RE.match("You approach the bakehouse, its red door bright in the light."))


class TheFieldFence(unittest.TestCase):
    """Run 42 T1: 'I walk over to the field fence where Elsabet is milking' rolled streetwise and read as travel."""

    LINE = 'I walk over to the field fence where Elsabet is milking. "Morning. Any of your cows wander out lately?"'

    def test_no_streetwise_no_travel(self):
        from app.skill_checks import infer_check_from_action
        from app.world import travel_intent

        self.assertNotEqual((infer_check_from_action(self.LINE) or {}).get("skill_code"), "streetwise")
        self.assertFalse(travel_intent(self.LINE))
        self.assertEqual((infer_check_from_action("I try to fence the goods down at the docks.") or {}).get("skill_code"),
                         "streetwise")


class Run42BlackWheel(unittest.TestCase):
    """Run 42 T2: GOLD 5 rolled to +10 with no coin shown; 'Mind the tides' made a job; an invented walk into the forge."""

    LINE = '"I will mind the tides. Do you know anyone in town who buys old brass or copper? The salvage guild pays badly."'

    def test_gain_without_coin_dropped(self):
        from app import world

        prose = ('Elsabet looks up. "No, my dear. Not that I know of." Jory leans in the doorway. "The Black Wheel could '
                 'use an extra hand today." Jory hands you a set of pliers and a scrap of copper.')
        result = {"narration": prose, "player": {"gold_delta": 5}}
        note = world._settle_stated_gold(result, self.LINE)
        self.assertEqual(note["source"], "gain_without_coin_dropped")
        self.assertNotIn("gold_delta", result["player"])

    def test_players_words_are_no_offer(self):
        from app.quest_parser import _players_words_only

        self.assertTrue(_players_words_only("You decide to mind the tides.", "I will mind the tides.", self.LINE))
        self.assertFalse(_players_words_only("Jory hands you a set of pliers.", "We've got a few old parts that need fixing.",
                                             self.LINE))

    def test_walk_into_the_forge_is_movement(self):
        from app.llm import _invented_unit_family

        sentence = "You step closer to The Black Wheel, the door creaking slightly as you push it open."
        self.assertEqual(_invented_unit_family(sentence, self.LINE, self.LINE), "movement")


class BareNameParagraph(unittest.TestCase):
    """Run 43 T0: the scene closed on a paragraph that was only "The Pear's Rest." (also run 5 T18, T19, T27)."""

    def test_dropped_unless_a_label(self):
        from app.prose_state import drop_bare_name_paragraph

        text = "Una calls out, spotting you. \"You're out early today.\"\n\nThe Pear's Rest."
        self.assertEqual(drop_bare_name_paragraph(text)[0], "Una calls out, spotting you. \"You're out early today.\"")
        label = "You wait by the door.\n\nRoger [[A]]\n\n\"You owe the guild.\""
        self.assertEqual(drop_bare_name_paragraph(label)[0], label)


class InventedInnerLife(unittest.TestCase):
    """8B run 2 (T1-T7): resolve, memories and feelings the player never gave; perception and touch stay."""

    LINE = '"I know what I owe. I am asking what you want from me this morning, Colm. Work, or a warning?"'

    def test_dropped_and_kept(self):
        from app.llm import _strip_player_acts_from_sentence as strip

        for gone in ("But today, you're not here to beg.", "You're not ready to let the guild dictate your life any longer.",
                     "You could feel the weight of his words, the unspoken threat lurking beneath them.",
                     "A part of you knows this is true, but the weight of it is undeniable.",
                     "You've been careful not to draw their attention."):
            self.assertEqual(strip(gone, self.LINE, self.LINE)[0], "", gone)
        # 8B writes curly apostrophes (run 3, T3: "You don’t ask why he’s carrying it" passed).
        self.assertEqual(strip("You don’t ask why he’s carrying it; you just keep moving.", "I help him push the cart.",
                               "I help him push the cart.")[0], "")
        for kept in ("You feel the cold wind on your face.", "You feel the weight of the coins in your palm.",
                     "You've heard that the ship's captain frequents the salvage yard.",
                     "As you climb, you can feel the weight of your injuries from the previous day.",
                     "You're in the warehouse now.", "You see the ledger on the desk."):
            self.assertEqual(strip(kept, self.LINE, self.LINE)[0], kept, kept)


class AMisspelledNameIsTheSamePerson(unittest.TestCase):
    """8B run 2 T7: NPC_NEW 'Harbour Reevec' beside the known 'Harbour Reeve' made a second person."""

    def test_near_names(self):
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        with connect() as conn:
            loc = conn.execute("SELECT current_location_id FROM player").fetchone()[0]
            conn.execute("DELETE FROM npcs")
            for code, name in (("A", "Harbour Reeve"), ("B", "Mara")):
                conn.execute("INSERT INTO npcs (code, location_id, name, role) VALUES (?, ?, ?, 'local')", (code, loc, name))
            self.assertEqual([r["name"] for r in world._near_name_matches(conn, "Harbour Reevec")], ["Harbour Reeve"])
            self.assertEqual(world._near_name_matches(conn, "Maria"), [])


class AnyGoingCountsForTheTripGuard(unittest.TestCase):
    """8B run 3 T1: 'You move down the dockside path' was not read as the going; the reply to a dropped line stayed."""

    def test_cut_at_his_question(self):
        from app.llm import _cut_scene_at_invented_request

        line = 'I go down to the workers hauling crates and fall in beside the nearest one. "Morning. Who is paying?"'
        nar = ("You move down the dockside path, where crates of salted fish are stacked in rows. You fall in beside a "
               "man with a scar running from his temple to his jaw.\n\n"
               '"You\'re early," he grunts. "Morning. Who is paying?" you ask.\n\n'
               'He wipes sweat from his brow. "The guild. You\'re not a guild runner, are you?"\n\n'
               'You shake your head. "Just a flat-runner, looking for work."\n\n'
               'He snorts. "Then you\'re the one hauling it."')
        turn = {"narration": nar, "narration_segments": [{"label": "paragraph", "text": p} for p in nar.split("\n\n")]}
        out = _cut_scene_at_invented_request(turn, line, floor=50)
        self.assertNotIn("He snorts", out["narration"])


class TakeOfAnUnownedItem(unittest.TestCase):
    """8B run 3 T7: TAKE 'fragments of lock mechanism' for what the player pried free; the fragments vanished."""

    def test_read_as_a_gain_and_judged(self):
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        line = ("I wade toward the half-submerged doors and check the nearest one for anything worth hauling back "
                "before the water turns: brass fittings, hinges, anything metal.")
        prose = ("You press your palm against the nearest door. You pry it free, revealing a corroded key and a few "
                 "fragments of what might have been a lock mechanism.")
        with connect() as conn:
            kept = world._filter_inventory_changes(
                conn, [{"name": "fragments of lock mechanism", "quantity_delta": -1}], narration=prose, player_input=line,
            )
        self.assertEqual([(k["name"], k["quantity_delta"]) for k in kept], [("fragments of lock mechanism", 1)])


class Run3DrownedHouse(unittest.TestCase):
    """8B run 3 T8: 'Rusted lock' granted on 'I pocket the key'; 'a strange pull'; 'your lantern's glow' with no lantern."""

    LINE = "I pocket the key and step through the doorway into the drowned house to see what the creak was."
    PROSE = ("You step inside, your lantern's glow cutting through the gloom. Your fingers brush against the cold, "
             "corroded metal of a rusted lock on the far wall, and you feel a strange pull to examine it further.")

    def test_lock_not_granted(self):
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        with connect() as conn:
            kept = world._filter_inventory_changes(conn, [{"name": "Rusted lock", "quantity_delta": 1}],
                                                   narration=self.PROSE, player_input=self.LINE)
        self.assertEqual(kept, [])

    def test_pull_and_lantern(self):
        from app.llm import _strip_player_acts_from_sentence as strip
        from app.prose_state import repair_unowned_weapon

        self.assertEqual(strip("You feel a strange pull to examine it further.", self.LINE, self.LINE)[0], "")
        out, fixes = repair_unowned_weapon(
            "The door creaks open on a narrow passage that smells of mildew and old rope. You step inside, your "
            "lantern's glow cutting through the gloom, and the floor groans.", ["worn boots", "corroded key"], self.LINE)
        self.assertNotIn("lantern", out)
        kept, _ = repair_unowned_weapon("The dim glow of your lamp shows the cave.", ["lantern"], self.LINE)
        self.assertIn("lamp", kept)


class NamedOnlyInSomeonesLine(unittest.TestCase):
    """8B run 2 T6: 'The guild, and the Harbour Reeve. They've been looking for you.' made a person not in the scene."""

    def _kept(self, names, prose):
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        with connect() as conn:
            conn.execute("DELETE FROM npcs")
            return [n["name"] for n in world._npcs_shown_in_prose(conn, [{"name": n, "role": "local"} for n in names], prose)]

    def test_mention_is_not_shown_but_address_is(self):
        prose = ('Colm sits by the harbour stores. "The guild," he says, "and the Harbour Reeve. They have been looking '
                 'for you." You turn to the boy at the door. "Not yet, Hargrave," you say.')
        kept = self._kept(["Harbour Reeve", "Hargrave"], prose)
        self.assertNotIn("Harbour Reeve", kept)
        self.assertIn("Hargrave", kept)


class ThePlayersDebtIsNoOffer(unittest.TestCase):
    """8B run 2 T1: 'And if you don't pay your share, they don't let you walk away' made the job 'Collect the Debt'."""

    def test_refused_and_a_real_offer_still_passes(self):
        from app.quest_parser import judge_offer

        colm = {"code": "A", "name": "Colm Woodall", "role": "tallyman"}
        warning = ('Colm leans back. "Funny how the debt works, isn\'t it? You owe them a month\'s wages. And if you '
                   'don\'t pay your share, they don\'t let you walk away," Colm says.')
        self.assertFalse(judge_offer("Funny how the debt works, isn't it?", warning, '"Watching me for the guild?"',
                                     giver=colm, giver_ref="A", npcs=[colm])["ok"])
        offer = 'Colm taps the ledger. "There\'s a cargo to haul to the north wharf. The guild pays two coppers," Colm says.'
        self.assertTrue(judge_offer("There's a cargo to haul to the north wharf.", offer, '"Any work?"',
                                    giver=colm, giver_ref="A", npcs=[colm])["ok"])


class Run4Opening(unittest.TestCase):
    """8B run 4 T0: 'She wears a patched tunic [[I2]], the same as yours'; 'The thought of leaving ... yourself behind.'"""

    def test_item_code_only_on_the_players_thing(self):
        from app.llm import _inject_entity_codes_for_known_names as inject

        out = inject("She wears a patched tunic, the same as yours. You pick up a rusty key. His rusty key glints.",
                     {"I2": "patched tunic", "I5": "rusty key"})
        self.assertIn("She wears a patched tunic, the same", out)
        self.assertIn("You pick up a rusty key [[I5]]", out)
        self.assertIn("His rusty key glints", out)

    def test_thought_as_subject(self):
        from app.llm import _strip_player_acts_from_sentence as strip

        self.assertEqual(strip("The thought of leaving this place feels like leaving a part of yourself behind.", "I wait.",
                               "I wait.")[0], "")
        kept = "The thought of the storm keeps the fishermen ashore."
        self.assertEqual(strip(kept, "I wait.", "I wait.")[0], kept)


class Run4RetoldAndPlanned(unittest.TestCase):
    """8B run 4 T3: the player's line retold as narration with a motive; the narrator planning the next steps."""

    LINE = ('"I am here for salvage, same as every dry tide." I shrug. "But if the guild is hauling out of the lower '
            'district, I want to know where they are digging, so I do not waste my night."')

    def test_retold_line_goes(self):
        from app.narration_pipeline import keep_player_words

        text = ('"I am here for salvage, same as every dry tide," you say. Avelina watches you. You\'re here for salvage, '
                "just like every other dry tide, but the guild's hauls have piqued your interest. The bell rings.")
        out, _ = keep_player_words(text, self.LINE)
        self.assertNotIn("piqued", out)
        self.assertIn("The bell rings.", out)

    def test_planning_goes(self):
        from app.llm import _strip_player_acts_from_sentence as strip

        for gone in ("But for now, you have to focus on the immediate task at hand.",
                     "If you can find out where they're digging, you might be able to get ahead of the game."):
            self.assertEqual(strip(gone, self.LINE, self.LINE)[0], "", gone)


class ReportedQuestionTheyNeverAsked(unittest.TestCase):
    """8B run 4 T4: 'You ask if it's dangerous, and she shrugs' after only 'Where is the guild digging?'."""

    def test_new_question_goes_reported_one_stays(self):
        from app.llm import _strip_player_acts_from_sentence as strip

        line = '"You did not answer me, Avelina. Where is the guild digging?"'
        self.assertEqual(strip("You ask if it's dangerous, and she shrugs.", line, line)[0], "")
        self.assertEqual(strip("You ask where the guild is digging.", line, line)[0], "You ask where the guild is digging.")
        own = 'I go into the chandlery. "Tam signed for the bell." Then I ask her for a coil of rope and what it costs.'
        kept = "You ask about the rope, and she pulls down a coil."
        self.assertEqual(strip(kept, own, own)[0], kept)


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
