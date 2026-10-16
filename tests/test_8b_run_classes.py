"""8B run classes (runs 7+): one test per fixed class."""
from __future__ import annotations

import json
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.scene_thread import follow_target, pursuit_in  # noqa: E402
from app.skill_checks import infer_check_from_action, resolve_check  # noqa: E402


class AWayIsWalkedNotFollowed(unittest.TestCase):
    """8B run 7, T1: "I follow the narrow path" logged following a person."""

    def test_ways_are_no_one(self):
        for line in (
            "I follow the narrow path down into the drowned district.",
            "I follow the footprints toward the water.",
            "I follow the old road north.",
        ):
            self.assertEqual(follow_target(line), "", line)

    def test_a_person_is_still_followed(self):
        self.assertIn("fisherman", follow_target("I follow the old fisherman down to the docks.").lower())

    def test_no_pursuit_thread_for_a_way(self):
        # T2 moved the player onto "Saltmarrow's narrow path" after the thread said
        # the player was following it.
        self.assertIsNone(pursuit_in("I follow the narrow path down into the drowned district."))
        self.assertIsNotNone(pursuit_in("I follow Rolf down the narrow path."))


class AReasonIsNotTheAct(unittest.TestCase):
    """8B run 8, T1: "...anything half-buried in the mud that might fetch a price" rolled appraise."""

    def test_what_a_thing_might_fetch_is_no_appraisal(self):
        line = ("I check the tide-reckoner against the sky, then walk out along the single path toward the "
                "Hollow Maw, keeping an eye out for anything half-buried in the mud that might fetch a price.")
        check = infer_check_from_action(line, {})
        self.assertNotEqual((check or {}).get("skill_code"), "appraise")

    def test_a_price_asked_still_appraises(self):
        self.assertEqual(infer_check_from_action("I haggle over the price of the copper.", {})["skill_code"], "appraise")


class NoOneToOffend(unittest.TestCase):
    """8B run 8, T1: "Botched Appraise: you misjudge the moment and give offense" alone on the mud."""

    def _first(self, predicate, **kw):
        for seed in range(4000):
            check = resolve_check(skill_code="appraise", rng=random.Random(seed), **kw)
            if predicate(check):
                return check
        raise AssertionError("no roll matched")

    def test_a_lone_bad_miss_is_no_blunder(self):
        check = self._first(lambda c: c["natural"] != 1 and c["margin"] <= -7)
        self.assertIsNone(check["blunder"])
        self.assertNotIn("offense", check.get("flavor") or "")

    def test_a_bad_miss_against_someone_still_blunders(self):
        check = self._first(lambda c: c["natural"] == 1, opposition={"name": "Vael", "rank": "F", "stats": {}})
        self.assertEqual(check["blunder"]["kind"], "social_blunder")


class APartialPatchKeepsWhatTheProseShows(unittest.TestCase):
    """8B run 8, T2: the verifier patched the tide-reckoner alone and the beam GRANT went."""

    PROSE = ("You pull it free, revealing a broken section of a wooden beam, its edges splintered and worn.")

    def _merge(self, patch_list, draft_list):
        from app import llm

        draft = {"narration": self.PROSE, "inventory_changes": draft_list}
        verdict = {"verdict": "revise", "issues": ["x"], "patch": {"inventory_changes": patch_list}}
        return llm._merge_verifier_verdict(verdict, draft, {})

    def test_the_prose_backed_grant_stays(self):
        merged = self._merge(
            [{"name": "mother's brass tide-reckoner", "quantity_band": "trivial"}],
            [{"name": "broken wooden beam", "quantity_band": "moderate"},
             {"name": "mother's brass tide-reckoner", "quantity_band": "-small"}],
        )
        names = [entry.get("name") for entry in merged.get("inventory_changes") or []]
        self.assertIn("broken wooden beam", names)
        self.assertEqual(names.count("mother's brass tide-reckoner"), 1)

    def test_an_entry_the_prose_never_names_stays_dropped(self):
        merged = self._merge(
            [{"name": "mother's brass tide-reckoner", "quantity_band": "trivial"}],
            [{"name": "silver locket", "quantity_band": "small"},
             {"name": "mother's brass tide-reckoner", "quantity_band": "-small"}],
        )
        names = [entry.get("name") for entry in merged.get("inventory_changes") or []]
        self.assertNotIn("silver locket", names)


class ThePlaceIsWhatStandsThere(unittest.TestCase):
    """8B run 9, T0: an opening naming Saltmarrow "showed" a MOVE into The Boar at Saltmarrow."""

    def test_the_head_is_before_at(self):
        from app import world

        self.assertEqual(world._place_words("The Boar at Saltmarrow"), ["boar"])
        self.assertEqual(world._place_words("Candle at Saltmarrow Forge"), ["candle"])
        self.assertEqual(world._place_words("Hollow Maw Path"), ["hollow", "maw", "path"])

    def test_an_opening_that_never_names_the_inn_does_not_enter_it(self):
        from app import world

        prose = ("You stand at the edge of the flats. The town of Saltmarrow [[L1]] is behind you, and ahead "
                 "the flats stretch out. A rag picker named Ellen Birtle looks up as you pass.")
        rows = [{"id": 1, "code": "L1", "name": "Saltmarrow", "parent_id": None, "kind": ""}]
        patch = {"move_to_location": "The Boar at Saltmarrow"}
        got = world._unasked_unshown_move({"player": patch}, patch, rows, "", intent="opening", narration=prose)
        self.assertEqual(got, "The Boar at Saltmarrow")


class ThePlayerNeedsNoName(unittest.TestCase):
    """8B run 9, T0: the verifier failed the opening for not naming the player (47 s)."""

    def test_the_naming_rule_says_it_is_for_other_people(self):
        from app import prompts

        self.assertIn('the narration calls the player "you" and needs no name for them', prompts.VERIFY_PROMPT)
        # 8B run 33, T1: the shorter clause read as "never name the player"; others may say it.
        self.assertIn("though others may say it", prompts.VERIFY_PROMPT)


class MoneyPromisedIsNotMoneyMoved(unittest.TestCase):
    """8B run 10, T3: GOLD 50 (+29) on a job offer; the prose only said the guild "will pay"."""

    def _settle(self, prose):
        from app import world

        result = {"narration": prose, "player": {"gold_delta": 50}}
        world._settle_stated_gold(result, "\"Then tell me what the guild wants found, and what it pays.\"")
        return result["player"].get("gold_delta")

    def test_a_promise_and_a_want_pay_nothing(self):
        prose = ("You've heard the ones that say the guild will pay handsomely for the right kind of risk. "
                 "The kind of weight that makes your hands itch for a blade, or for a coin.")
        self.assertIn(self._settle(prose), (None, 0))

    def test_a_handover_still_backs_the_gain(self):
        self.assertEqual(self._settle("Petronel hands you the pouch, and it is heavier than you thought."), 50)


class SaidOnceIsSaid(unittest.TestCase):
    """8B run 10, T3: the typed line given in full, then a reworded copy as the player's again."""

    LINE = ("\"Something with value.\" I let go of the bolts and wipe my hands on my breeches. \"Then tell me what "
            "the guild wants found, and what it pays, and I'll tell you if the flats have it.\"")

    def test_the_reworded_copy_goes(self):
        from app.narration_pipeline import drop_invented_player_speech

        paragraphs = [
            "“Something with value,” you say. “Then tell me what the guild wants found, and what it pays, and "
            "I'll tell you if the flats have it.” You let go of the bolts.",
            "\"You're not here for the usual scraps,\" he says. \"The guild wants a piece of the old shipwreck.\"",
            "You cross your arms, the movement deliberate. \"Then tell me what it is, and what it pays,\" you say. "
            "\"And I'll tell you if the flat has it.\"",
        ]
        out, dropped = drop_invented_player_speech(paragraphs, self.LINE)
        self.assertIn("Then tell me what the guild wants found", out[0])
        self.assertNotIn("what it is, and what it pays", " ".join(out))
        self.assertTrue(dropped)


class TheKeptHalfIsAClause(unittest.TestCase):
    """8B run 11, T0: a cut feeling left the sentence "The knowledge that soon, the flats will flood again." """

    def test_no_object_left_standing(self):
        from app import llm

        text = ("The air is thick with brine and the silence is broken only by a gull. You feel the pull of the "
                "water in your bones, the way it calls to you, and the knowledge that soon, the flats will flood again.")
        kept, dropped = llm.drop_invented_player_acts_text(text, "__opening__")
        self.assertNotIn("The knowledge that", kept)

    def test_a_world_clause_still_stays(self):
        from app import llm

        self.assertTrue(llm._tail_is_clause("he gestures toward the shelves, where the jars stand"))
        self.assertTrue(llm._tail_is_clause("the ground beneath your feet shudders"))
        self.assertFalse(llm._tail_is_clause("the knowledge that soon, the flats will flood again"))
        # 8B run 13, T0: "its" is no verb.
        self.assertFalse(llm._tail_is_clause("the brass tide-reckoner at your belt, its face never quite right"))
        # 8B run 40, T1: the verb of "you made" is not the tail's, nor is "tides".
        self.assertFalse(llm._tail_is_clause("the promise you made to the tides."))
        self.assertTrue(llm._tail_is_clause("the salvage you need to recover is deep in the lower district"))


class ACollectionIsNoCollecting(unittest.TestCase):
    """8B run 11, T1: "The last tide has left behind a strange collection of items" read as the jar's arrival."""

    def test_nouns_are_no_gain(self):
        from app import world

        sentence = ("The last tide has left behind a strange collection of items: a rusted iron key, a tattered map, "
                    "and a small, sealed jar that glimmers faintly in the sunlight")
        self.assertEqual(world._sentence_item_events_detail(sentence, "sealed jar", ["sealed", "jar"], owned=False), [])

    def test_the_verb_still_is(self):
        from app import world

        events = world._sentence_item_events_detail("You collect the sealed jar from the mud", "sealed jar",
                                                    ["sealed", "jar"], owned=False)
        self.assertEqual([kind for _, kind, _ in events], ["gain"])


class AWeighingIsThePlayers(unittest.TestCase):
    """8B run 11, T3: "The idea of dealing with them is both tempting and dangerous, but the need for answers is stronger." """

    def test_the_weighing_goes(self):
        from app import llm

        self.assertTrue(llm._PLAYER_INNER_SUBJECT_RE.match(
            "The idea of dealing with them is both tempting and dangerous, but the need for answers is stronger."))
        self.assertTrue(llm._PLAYER_INNER_SUBJECT_RE.match("The need for answers is stronger than the fear."))

    def test_someone_elses_mind_stays(self):
        from app import llm

        self.assertFalse(llm._PLAYER_INNER_SUBJECT_RE.match("The idea of losing the boat is too much for him."))
        self.assertFalse(llm._PLAYER_INNER_SUBJECT_RE.match("The thought of the storm makes his hands shake."))


class TheWomanIsTheOneShownAsAWoman(unittest.TestCase):
    """8B run 11, T5: "I turn to the woman" went to no one; the prose never named Eleanor."""

    LINE = ("I turn to the woman and lower the key. \"More than a key. Like what? And what would it cost me "
            "for you to show me these old locks?\"")

    def _context(self, eleanor="she", eldric="he"):
        npcs = [{"id": 1, "code": "A", "name": "Eldric Thorne", "role": "fisherman", "pronouns": eldric},
                {"id": 2, "code": "B", "name": "Eleanor Vane", "role": "apprentice", "pronouns": eleanor}]
        return {"settings": {}, "current_location": {"id": 1, "code": "L1"},
                "locations": [{"id": 1, "code": "L1", "npcs": npcs}]}

    def test_the_woman_is_eleanor(self):
        from app import conversation

        self.assertEqual(conversation.resolve(self._context(), self.LINE)["addressed"], ["B"])

    def test_two_women_name_nobody(self):
        from app import conversation

        self.assertNotEqual(conversation.resolve(self._context(eldric="she"), self.LINE)["addressed"], ["B"])

    def test_a_woman_bound_to_a_name_gets_her_pronouns(self):
        from app import world

        npcs = world._npcs_shown_in_prose(_ConnStub(), [{"name": "Eleanor Vane", "role": "apprentice"}],
                                          "A flicker of movement catches your eye: a woman with a weathered face "
                                          "leans in. \"I know where the old locks are,\" she says.")
        self.assertEqual(npcs[0].get("_figure_pronouns"), "she")


class AskingTheOtherSideIsNoTaking(unittest.TestCase):
    """8B run 12, T1: "Do you ever buy old clay pots ...?" put a clay pot in the pack."""

    def test_the_asked_one_buying(self):
        from app.llm import player_take_intent

        self.assertFalse(player_take_intent("\"Morning. Do you ever buy old clay pots or jars out of the flats?\""))
        self.assertTrue(player_take_intent("\"I'll buy the rope.\" I count out the coins."))
        self.assertTrue(player_take_intent("\"Would you sell me the lantern?\""))


class AnAsYouLeadIsThePlayersAct(unittest.TestCase):
    """8B run 13, T2: "As you turn to leave, Hubert adds, '...'" left the player walking off."""

    LINE = "\"Fair rate's a slippery word, Hubert.\" I fold my arms. \"How much? I'll take it if the coin's real.\""

    def test_the_lead_goes_and_the_line_stays(self):
        from app import llm

        kept, gone = llm._strip_player_acts_from_sentence(
            "As you turn to leave, Hubert adds, \"Make sure you're not bringing anything back.\"",
            llm.player_line_of(self.LINE), self.LINE)
        self.assertEqual(kept, "Hubert adds, \"Make sure you're not bringing anything back.\"")
        self.assertIn("turn to leave", gone)

    def test_an_asked_act_keeps_its_lead(self):
        from app import llm

        line = "I turn to leave."
        sentence = "As you turn to leave, Hubert calls after you."
        self.assertEqual(llm._strip_player_acts_from_sentence(sentence, llm.player_line_of(line), line)[0], sentence)


class TheOwnQuestionIsNotNarrated(unittest.TestCase):
    """8B run 14, T1: the player's unquoted question came back as the prose's own sentence, and seeded Ivo."""

    LINE = ("I wade over to the fishmonger's stall and crouch to look at the shape beneath it, without touching "
            "anything yet. Is it a person, and how long has it been there?")

    def test_the_question_goes_and_the_answer_stays(self):
        from app.narration_pipeline import drop_echoed_own_questions

        prose = ("You wade over to the fishmonger’s stall and crouch to look at the shape beneath it, without touching "
                 "anything yet. Is it a person, and how long has it been there? The shape there is small, curled "
                 "like a child’s body. It’s been there for at least a day.")
        fixed, changes = drop_echoed_own_questions(prose, self.LINE)
        self.assertNotIn("Is it a person", fixed)
        self.assertIn("The shape there is small", fixed)
        self.assertTrue(changes)

    def test_a_figure_asked_about_is_no_one_shown(self):
        from app import world

        self.assertEqual(world._figure_hints("Is it a person, and how long has it been there?"), [])
        self.assertTrue(world._figure_hints("A woman approaches and asks, \"Need help?\""))


class ACutLeavesNoPronounStranded(unittest.TestCase):
    """8B run 15, T0: the mother's sentence went as a thought and "marked her as lost" pointed at no one."""

    def test_the_person_comes_back(self):
        from app import llm

        text = ("The town is quiet. You remember the last time you ventured this way, six years ago, when your "
                "mother left to gather salvage and never returned. The salvage guild marked her as lost and took "
                "her share, leaving you with a debt.")
        kept, dropped = llm.drop_invented_player_acts_text(text, "__opening__")
        self.assertIn("marked your mother as lost", kept)
        self.assertTrue(dropped)

    def test_a_cut_with_no_one_in_it_changes_nothing(self):
        from app import llm

        self.assertEqual(llm._restore_stranded_referent("He gestures toward the shipyard.", ""),
                         "He gestures toward the shipyard.")

    def test_a_place_is_no_person_and_a_named_one_keeps_his(self):
        # 8B run 46, T2: "looks up from his ledger" became "from Tally House's ledger".
        from app import llm

        self.assertEqual(llm._person_in_cut("You step into the Tally House, the scent of ink thick in the air."), "")
        self.assertEqual(llm._restore_stranded_referent("Kael, the tallyman, looks up from his ledger.", "Mira|"),
                         "Kael, the tallyman, looks up from his ledger.")


class SpeechShowsNothingArriving(unittest.TestCase):
    """8B run 46, T2: the refused goods' trim cut 'Either way, it'll take time."' from the tallyman's line."""

    def test_the_spoken_tail_stays(self):
        from app import world

        prose = ("Kael leans back, considering you. \"The guild has a few jobs available. You could help with the "
                 "docks, sorting through the salvaged goods, or maybe assist in the warehouse. Either way, it’ll "
                 "take time.\" His gaze flickers to the ledger again.")
        result = {"narration": prose}
        report = world._reconcile_prose_with_state(
            None, result, rejected=[{"name": "salvaged goods", "outcome": "gain"}], movement_report=None,
            gold_note=None, purse_note=None)
        self.assertIn("it’ll take time.\"", world._narration_text(result))
        self.assertFalse([t for t in report.get("trimmed") or [] if t.get("why") == "gain_refused"])

    def test_the_players_own_question_stays(self):
        # 8B run 51, T3.
        from app import world

        prose = ("“I'll take the runner's task,” you say. “Whose debt do I collect first, and where do I "
                 "find them?” The Tidewatch's runner's task is yours. Captain Veyra leans against the counter.")
        result = {"narration": prose}
        world._reconcile_prose_with_state(
            None, result, rejected=[{"name": "Runner's Task", "outcome": "gain"}], movement_report=None,
            gold_note=None, purse_note=None)
        self.assertIn("Whose debt do I collect first", world._narration_text(result))

    def test_someone_elses_tagged_line_stays(self):
        # 8B run 51, T4: '"You're here to collect the debt," he says' went as the refused debt note.
        from app import world

        prose = ("A man sits at the table, his face gaunt. He looks up as you enter. “You’re here to collect "
                 "the debt,” he says, his voice rough, like sandpaper. The fire crackles low in the hearth.")
        result = {"narration": prose}
        world._reconcile_prose_with_state(None, result, rejected=[{"name": "Debt note", "outcome": "gain"}],
                                          movement_report=None, gold_note=None, purse_note=None)
        self.assertIn("collect the debt", world._narration_text(result))


class AShrugAfterAQuestionIsTheAnswer(unittest.TestCase):
    """8B run 15, T2: '"What's on your hands?" she asks ... You glance down, noting ...' answered for the player."""

    def test_the_look_goes_and_the_scene_stays(self):
        from app import llm

        line = "\"If the well's dry, where are you getting water? And what's on your hands?\""
        text = ('"What\'s on your hands?" she asks, her eyes narrowing. You glance down, noting the faint trace of salt '
                'and grit clinging to your palms. Behind her, the lantern gutters.')
        kept, dropped = llm.drop_invented_player_acts_text(text, line)
        self.assertNotIn("You glance down", kept)
        self.assertIn("the lantern gutters", kept)

    def test_a_look_the_player_asked_for_stays(self):
        from app import llm

        line = "I glance down at my hands."
        text = "You glance down at your hands. Salt has dried white in the creases."
        kept, _ = llm.drop_invented_player_acts_text(text, line)
        self.assertIn("You glance down", kept)


class WaterIsNoAnimal(unittest.TestCase):
    """8B run 15, T4: "look into the water without touching it" rolled animal handling."""

    LINE = ('"Changing how?" I crouch by the well and look into the water without touching it. '
            '"Since when, and has anyone drunk from it?"')

    def test_a_memory_the_line_asks_for_stays(self):
        from app import llm

        line = "I sit on the crate. What did I find down there?"
        s = "You remember digging through the debris of the old wharf, sorting the broken timbers."
        self.assertEqual(llm._strip_player_acts_from_sentence(s, llm.player_line_of(line), line)[0], s)

    def test_water_is_no_animal(self):
        from app.skill_checks import infer_check_from_action

        self.assertNotEqual((infer_check_from_action(self.LINE, {}) or {}).get("skill_code"), "animal_handling")
        self.assertEqual(infer_check_from_action("I water the mule at the trough.", {})["skill_code"], "animal_handling")
        self.assertEqual(infer_check_from_action("I calm the horse and saddle it.", {})["skill_code"], "animal_handling")


class ARestoredSplitLineIsSaidOnce(unittest.TestCase):
    """8B run 15, T5: the first piece was restored to the whole line, and the second piece stayed beside it."""

    LINE = ("\"Since the last storm.\" I stand and wipe my hands on my tunic. \"Has anyone told the harbour reeve? "
            "If the town's water is going bad, someone should know.\"")

    def test_the_second_piece_goes(self):
        from app.narration_pipeline import keep_player_words

        prose = ("“Since the last storm,” you say. Mira watches you.\n\n"
                 "“Has anyone told the harbour reeve?” you ask again, your own words more pointed now. "
                 "“If the town’s waters are going bad, someone should know.”\n\n"
                 "Mira exhales slowly. “The reeve doesn’t care about the well,” she says.")
        fixed, _ = keep_player_words(prose, self.LINE)
        self.assertEqual(fixed.count("someone should know"), 1)
        self.assertIn("Has anyone told the harbour reeve? If the town's water is going bad, someone should know", fixed)

    def test_an_answer_echoing_a_piece_stays(self):
        from app.narration_pipeline import keep_player_words

        line = "I sit, but I keep my hands on the table. \"Show me, then. Line by line.\""
        prose = ("“Show me, then. Line by line,” you say. He taps the ledger. “Debt's a ledger. Line by line, "
                 "I'll show you what's owed,” he says.")
        fixed, _ = keep_player_words(prose, line)
        self.assertIn("I'll show you what's owed", fixed)


class TheOneLeftBehindThroughTheShippedPath(unittest.TestCase):
    """8B run 15, T6: "I leave Mira at the well and walk up to the reeve's office" rolled vs Mira and moved
    the player to the well. The run 5 fix was tested on the cased line; the real caller lowercases it."""

    LINE = ("\"Then I'll tell him myself.\" I leave Mira at the well and walk up to the harbour reeve's office "
            "to ask whoever is on duty about the water.")
    CTX = {"npcs": [{"code": "A", "name": "Mira", "role": "well keeper"}], "conversation_turn": {"addressed": ["A"]}}

    def test_no_check_against_mira(self):
        from app.skill_checks import infer_check_from_action

        check = infer_check_from_action(self.LINE, self.CTX) or {}
        self.assertNotEqual((check.get("opposition") or {}).get("name"), "Mira")

    def test_asking_mira_still_is(self):
        from app.skill_checks import infer_check_from_action

        check = infer_check_from_action("I ask Mira who keeps the well.", self.CTX) or {}
        self.assertEqual((check.get("opposition") or {}).get("name"), "Mira")

    def test_the_well_left_is_no_destination(self):
        from app import world

        self.assertNotIn("well", world._destination_text(self.LINE))
        self.assertIn("harbour reeve's office", world._destination_text(self.LINE))


class ThePlaceCrossedIsNoDestination(unittest.TestCase):
    """8B run 16, T1: "I cross the square to the hedger" wrote the stayed-put Note in the player's history."""

    def test_no_note_for_a_walk_to_someone(self):
        from app import world

        self.assertFalse(world._line_was_about_going(
            "I cross the square to the hedger leaning on the wall. \"Watching the flats too?\""))
        self.assertTrue(world._line_was_about_going("I head down to the drowned district before the tide turns."))


class TheMothersReckonerIsYours(unittest.TestCase):
    """8B run 18, T0: "You have the mother's brass tide-reckoner in your pocket"."""

    def test_the_article_becomes_your(self):
        from app import prose_state

        owned = ["mother's brass tide-reckoner A brass tide-reckoner that never keeps true time.", "worn boots"]
        text = "You have the mother's brass tide-reckoner in your pocket. \"The mother's hand was steady,\" he says."
        fixed, changes = prose_state.repair_kin_item_article(text, owned)
        self.assertIn("You have your mother's brass tide-reckoner", fixed)
        self.assertIn("\"The mother's hand was steady,\"", fixed)
        self.assertEqual(len(changes), 1)

    def test_nothing_without_such_an_item(self):
        from app import prose_state

        text = "The mother's grave lies past the seawall."
        self.assertEqual(prose_state.repair_kin_item_article(text, ["worn boots"])[0], text)


class TheGiversOfferSentenceGroundsTheJob(unittest.TestCase):
    """8B run 104, T2: "there's a job that might interest you" went uncited; the job was refused."""

    LINE = '"I owe the guild a winter\'s credit and I want to work it off." I stop in front of the desk. "What job have you got that pays against the ledger?"'
    NARRATION = (  # the run's shipped prose
        "“I owe the guild a winter's credit and I want to work it off,” you say. “What job have you got that "
        "pays against the ledger?” The tallyman, a burly man with a scar running from his temple to his jaw, lifts "
        "his head from the ledger. \"You're looking at the wrong kind of work,\" he says, finally. He pushes his chair "
        "back. \"But,\" he adds, \"there's a job that might interest you. It's out on the docks, where the tide's too "
        "high for anyone else to reach.\" He leans forward. \"You're looking for something that's been lost in the "
        "flood. Something valuable.\"")
    REPLY = {"new": [{"title": "Retrieve the Lost Relic from the Flooded Docks", "giver": "Tallyman Darrick",
                      "summary": "Find and recover a valuable item lost in the flood.", "difficulty": "normal",
                      "steps": [{"title": "Locate the Docks", "description": "Go to the docks.", "location": "L2"}],
                      "reward": {"gold": 0, "xp": 0, "items": [], "text": ""},
                      "offer_line": "You're looking for something that's been lost in the flood. Something valuable.",
                      "evidence": "What job have you got that pays against the ledger?"}], "updates": []}

    def test_his_offer_grounds_it(self):
        from app import quest_parser

        npcs = [{"id": 1, "code": "A", "name": "Tallyman Darrick", "role": "Salvage Guild Tallyman"}]
        accepted, rejected = quest_parser.validate_quest_changes(
            json.loads(json.dumps(self.REPLY)), narration=self.NARRATION, player_input=self.LINE, npcs=npcs)
        self.assertEqual([q["giver_npc_id"] for q in accepted["new"]], [1], rejected)

    def test_without_his_offer_nothing(self):
        from app import quest_parser

        npcs = [{"id": 1, "code": "A", "name": "Tallyman Darrick", "role": "Salvage Guild Tallyman"}]
        prose = self.NARRATION.replace("there's a job that might interest you. ", "")
        accepted, _ = quest_parser.validate_quest_changes(
            json.loads(json.dumps(self.REPLY)), narration=prose, player_input=self.LINE, npcs=npcs)
        self.assertEqual(accepted["new"], [])


class TheParserGetsOnlyThePlayersLine(unittest.TestCase):
    """8B run 103, T3: the parser quoted the engine's "Resolved player references" note as its evidence."""

    def test_engine_notes_stay_out(self):
        from app.quest_parser import build_parser_prompt

        line = ('"I am up for it." I rest my hands on the counter.\n\nResolved player references: Conversation '
                '(engine decided) - the player is talking to Garrick Thorne [[A]].')
        _system, user = build_parser_prompt("Garrick looks up.", line)
        self.assertNotIn("Resolved player references", json.loads(user)["player_input"])
        self.assertIn("I am up for it.", json.loads(user)["player_input"])


class ALookAtTheJobIsNoWorkDone(unittest.TestCase):
    """8B run 99, T4: "You nod, your gaze fixed on the distant shipwreck" finished and paid the dive."""

    Q = {"id": 1, "code": "Q1", "title": "Dive into the old shipwreck", "status": "active"}

    def test_a_glance_finishes_nothing(self):
        from app.quest_parser import done_check

        self.assertTrue(done_check("You nod, your gaze fixed on the distant shipwreck.", self.Q))

    def test_the_dive_itself_still_counts(self):
        from app.quest_parser import done_check

        self.assertEqual(done_check("You dive down into the old shipwreck and come up with a bronze bell.", self.Q), [])
        self.assertEqual(done_check("You fixed the net and hand it back.", {"title": "Mend the nets"}), [])


class ACutSceneLeavesTheStateWhereItStops(unittest.TestCase):
    """8B run 98, T4: the scene stopped in the tally house; a boat, a reef and -2 gold came from the cut part."""

    LINE = ('"Half is fair. I accept the salvage run." I straighten up. "I will go down to the harbour and find a '
            'boat out to the eastern reef."')
    PROSE = ('You straighten up, your voice firm as the wind off the reef. "Half is fair. I accept the salvage run." '
             '“I will go down to the harbour and find a boat out to the eastern reef,” you say. Alditha Saxby [[B]]’s '
             'fingers tap the counter, counting out the twenty-two gold coins she’d promised.')

    def test_accepting_the_run_takes_nothing(self):
        from app.world import player_take_intent

        self.assertFalse(player_take_intent(self.LINE))
        self.assertTrue(player_take_intent("I accept the coil of rope she holds out."))

    def test_a_place_only_said_is_not_reached(self):
        from app.world import _new_place_reached

        self.assertFalse(_new_place_reached("eastern reef", self.PROSE, self.LINE))

    def test_her_counting_out_is_no_payment(self):
        from app.prose_state import shows_unpriced_payment

        self.assertFalse(shows_unpriced_payment(self.PROSE))
        self.assertTrue(shows_unpriced_payment("You lean on the bar, counting out the coins he asked for."))


class TakingThatOneIsTakingIt(unittest.TestCase):
    """8B run 97, T3: "I will take that one" left the shipwreck job offered."""

    Q = {"id": 1, "code": "Q1", "title": "Haul Salvage from the Sea", "status": "offered", "giver_npc_id": 2}

    def test_that_one_takes_it(self):
        from app.quest_parser import player_takes_job

        line = ('"You offered me the shipwreck when I came in. Hauling salvage near the old wreck in the east." I put my '
                'hand flat on the desk. "I will take that one. How much comes off per load?"')
        self.assertTrue(player_takes_job(self.Q, line, [self.Q], ""))

    def test_a_hedge_takes_nothing(self):
        from app.quest_parser import player_takes_job

        self.assertFalse(player_takes_job(self.Q, '"I am not sure I will take that one."', [self.Q], ""))
        self.assertFalse(player_takes_job(self.Q, '"I might take it, if the pay is right."', [self.Q], ""))


class SomeoneLeftBehindIsNoOtherSide(unittest.TestCase):
    """8B run 96, T4: "I nod to Thorne and leave the tally house ... to ask the boat owners" rolled vs Thorne."""

    CTX = {"current_location": {"id": 2, "npcs": [{"code": "A", "name": "Thorne", "role": "tallyman", "rank": "F"}]}}

    def test_thorne_is_not_the_other_side(self):
        line = ('"Then I will find a captain." I nod to Thorne and leave the tally house, heading down to the harbour '
                'to ask the boat owners who would take me out.')
        check = infer_check_from_action(line, self.CTX) or {}
        self.assertNotEqual(((check.get("opposition") or {}).get("name")), "Thorne")

    def test_walking_away_from_him(self):
        # 8B run 99, T4.
        ctx = {"current_location": {"id": 2, "npcs": [{"code": "A", "name": "Veyne", "role": "tallyman", "rank": "F"}]}}
        line = "I thank Veyne with a nod and walk down to the docks, looking for the divers near the old mooring posts."
        check = infer_check_from_action(line, ctx) or {}
        self.assertNotEqual(((check.get("opposition") or {}).get("name")), "Veyne")

    def test_named_after_the_leaving_still_counts(self):
        line = "I leave the tally house and find Thorne at the docks to persuade him to lend me a boat."
        check = infer_check_from_action(line, self.CTX) or {}
        if check.get("opposition"):
            self.assertEqual(check["opposition"]["name"], "Thorne")


class AnOpenOfferToldAgainIsThatOffer(unittest.TestCase):
    """8B run 94, T3: "Then I will take the wreck" minted a second wreck job beside Elias's open offer."""

    LINE = '"Then I will take the wreck." I tap the edge of the ledger. "Which pier is it off, and who do I report to when I get there?"'
    NARRATION = (  # the run's shipped prose
        "“Then I will take the wreck,” you say. “Which pier is it off, and who do I report to when I get there?” You "
        "tap the edge of the tally’s worn wood, and Elias Varn [[A]]’s fingers twitch, ink smudging the page. He leans "
        "back, eyes narrowing as if measuring you against the weight of the wreck. “It’s the third pier from the "
        "east,” he says, voice rough with the rasp of sea wind. “You’ll find a sign with the name Marrow’s End—it’s "
        "the only one that still stands. Report to Captain Dain. He’s the one who found the wreck, and he’s not the "
        "kind to waste time on talk.”")
    REPLY = {"new": [{"title": "Salvage the Wreck at Marrow's End", "giver": "Elias Varn [[A]]", "difficulty": "normal",
                      "summary": "Salvage the wreck at Marrow's End and report to Captain Dain.",
                      "steps": [{"title": "Report to Captain Dain at the pier", "description": "Find the sign.",
                                 "location": "Marrow's End"}],
                      "reward": {"gold": 0, "xp": 0, "items": [], "text": "salvage credits"},
                      "offer_line": "It’s the third pier from the east... Report to Captain Dain.",
                      "evidence": "Then I will take the wreck. Which pier is it off, and who do I report to when I get there?",
                      "_from_mark": True}],
             "updates": []}
    NPCS = [{"id": 1, "code": "A", "name": "Elias Varn", "role": "tallyman"}]
    EXISTING = [{"id": 1, "code": "Q1", "title": "salvage contract", "status": "offered", "giver_npc_id": 1,
                 "first_step_location": "docks"}]

    def test_the_open_offer_is_taken(self):
        from app import quest_parser

        accepted, rejected = quest_parser.validate_quest_changes(
            json.loads(json.dumps(self.REPLY)), narration=self.NARRATION, player_input=self.LINE,
            npcs=self.NPCS, existing=self.EXISTING)
        self.assertEqual(accepted["new"], [], rejected)
        self.assertEqual([(u["code"], u["action"]) for u in accepted["updates"]], [("Q1", "accept")])

    def test_with_no_open_offer_it_is_new(self):
        from app import quest_parser

        accepted, _ = quest_parser.validate_quest_changes(
            json.loads(json.dumps(self.REPLY)), narration=self.NARRATION, player_input=self.LINE,
            npcs=self.NPCS, existing=[])
        self.assertEqual([q["status"] for q in accepted["new"]], ["active"])


class AFigureInADescriptionIsNoOne(unittest.TestCase):
    """8B run 93, T2: "the kind of scent that clings to the edges of a man who's seen ..." stored a diver."""

    def test_the_kind_of_clause(self):
        from app.world import _figure_hints

        prose = ("The air smells of salt and rust, the kind of scent that clings to the edges of a man who’s "
                 "seen too many things sink.")
        self.assertEqual(_figure_hints(prose, []), [])

    def test_a_man_in_the_scene_still_counts(self):
        from app.world import _figure_hints

        prose = "The air smells of salt and rust. A man in a tarred coat watches you from the door."
        self.assertTrue(_figure_hints(prose, []))


class TheShapesWordingIsNoValue(unittest.TestCase):
    """8B run 92, T2: the step's description was stored as "what doing it means", the shape's own words."""

    def test_placeholder_fields_are_empty(self):
        from app.quest_parser import parse_reply

        reply = parse_reply({"new": [{"title": "Salvage the shipwreck", "steps": [
            {"title": "recover a valuable item", "description": "what doing it means", "location": "L2"}]}]})
        step = reply["new"][0]["steps"][0]
        self.assertEqual(step["description"], "")
        self.assertEqual(step["title"], "recover a valuable item")
        self.assertEqual(reply["new"][0]["title"], "Salvage the shipwreck")


class ASpeechLeadWithNoLineGoes(unittest.TestCase):
    """8B run 91, T3: the scene ended "Then, with a slow exhale, he speaks." and no line came."""

    def test_the_dangling_lead_goes(self):
        from app.prose_state import drop_orphan_speech_lead

        prose = ('"Tell me who runs that crew," you say. Elias pauses, the silence stretching between you like a '
                 'taut rope. Then, with a slow exhale, he speaks.')
        out, fixes = drop_orphan_speech_lead(prose)
        self.assertTrue(out.endswith("like a taut rope."), out)
        self.assertTrue(fixes)

    def test_a_lead_with_its_line_stays(self):
        from app.prose_state import drop_orphan_speech_lead

        prose = 'Elias pauses. Then, with a slow exhale, he speaks. "Gorran runs them."'
        self.assertEqual(drop_orphan_speech_lead(prose)[0], prose)

    def test_a_plain_act_is_no_lead(self):
        from app.prose_state import drop_orphan_speech_lead

        prose = "Elias pauses, then turns back to the ledger and begins to write."
        self.assertEqual(drop_orphan_speech_lead(prose)[0], prose)


class AGiverNamedByJob(unittest.TestCase):
    """8B run 90, T2: giver "clerk" for Elias Vane, the clerk, left the job with no giver."""

    def test_the_one_holder_is_the_giver(self):
        from app.quest_parser import _resolve_npc

        npcs = [{"id": 1, "code": "A", "name": "Gregory Furlong", "role": "stablehand"},
                {"id": 2, "code": "B", "name": "Elias Vane", "role": "clerk"}]
        self.assertEqual(_resolve_npc("clerk", npcs)["id"], 2)
        self.assertEqual(_resolve_npc("the clerk", npcs)["id"], 2)

    def test_two_holders_is_no_one(self):
        from app.quest_parser import _resolve_npc

        npcs = [{"id": 1, "name": "Ada Pell", "role": "clerk"}, {"id": 2, "name": "Elias Vane", "role": "clerk"}]
        self.assertIsNone(_resolve_npc("clerk", npcs))


class AJobToldToYouIsAnOffer(unittest.TestCase):
    """8B run 89, T3: "You haul the things that sink," she said, read as the player's own act; no job."""

    LINE = ('"Hauling from the docks. I know the tide hours, so I can work around the water." I set both hands on '
            'the desk. "What do I haul, and how much comes off per load?"')
    NARRATION = (  # the run's shipped prose
        "“Hauling from the docks. I know the tide hours, so I can work around the water,” you say. Gunilda [[A]]’s "
        "fingers drummed the wood of the desk as she leaned back in her chair.\n\n“You haul the things that sink,” "
        "she said, voice low and measured. “Broken crates, rusted tools, anything that’s been tossed into the tide and "
        "come back. The reeve’s men take the worth of what’s salvageable, and the rest—well, it’s yours to claim.” Her "
        "gaze flicked to the ledger, then back to you.\n\n“What do I haul, and how much comes off per load?” you ask."
        "\n\nShe tapped the ledger. “A third of the value of what you haul. But the reeve’s men are picky. And if you "
        "bring back something worth more than a third, you get the rest.” Her lips curved into a thin smile. “But "
        "that’s not the only way to earn your way out of debt. The warehouse’s got work for those who’re willing to "
        "risk a little more.”")
    NPCS = [{"id": 1, "code": "A", "name": "Gunilda", "role": "tallyman"}]

    def test_her_words_are_the_offer(self):
        from app import quest_parser

        reply = {"new": [{
            "title": "Haul Salvage from Docks", "giver": "Gunilda", "difficulty": "normal",
            "summary": "Collect broken crates and rusted tools from the tide to reduce debt",
            "steps": [{"title": "Haul the salvage", "description": "Collect items tossed into the tide", "location": "L2"}],
            "reward": {"gold": 0, "xp": 0, "items": [], "text": "A third of the value of what you haul."},
            "offer_line": "You haul the things that sink, broken crates, rusted tools, anything that's been tossed "
                          "into the tide and come back.",
            "evidence": "You haul the things that sink, broken crates, rusted tools, anything that's been tossed "
                        "into the tide and come back.",
        }]}
        accepted, rejected = quest_parser.validate_quest_changes(reply, narration=self.NARRATION,
                                                                 player_input=self.LINE, npcs=self.NPCS)
        self.assertEqual([q["title"] for q in accepted.get("new") or []], ["Haul Salvage from Docks"], rejected)

    def test_the_prose_retelling_the_player_is_still_theirs(self):
        from app import quest_parser

        self.assertTrue(quest_parser._players_words_only(
            "You decide to mind the tides", "You decide to mind the tides", "I will mind the tides",
            "You decide to mind the tides. Hesk nods."))


class AFigureBoundThisTurnIsInTheScene(unittest.TestCase):
    """8B run 19, T0: the masked figure bound to Bertha Radley offered the job; it was filed with no giver."""

    NARRATION = ("A figure steps from the shadows of a collapsed warehouse, their face obscured by a cloth mask. "
                 "\"You're Isk, aren't you?\" they say. \"The guild sent me. They want you to come with them. "
                 "There's something you need to see.\"")
    REPLY = {"new": [{  # the run's own parser proposal
        "title": "Salvage Contract", "giver": "Bertha Radley", "difficulty": "normal",
        "summary": "Follow Bertha to the guild's hall to collect a share of the salvage",
        "steps": [{"title": "Follow Bertha to the guild's hall", "description": "Go to Saltmarrow with Bertha",
                   "location": "Saltmarrow"}],
        "reward": {"gold": 0, "xp": 0, "items": ["A share of the salvage"], "text": "A share of the salvage"},
        "offer_line": "They want you to come with them. There's something you need to see.",
        "evidence": "You're Isk, aren't you? They want you to come with them. There's something you need to see.",
        "_from_mark": True,
    }]}
    NPCS = [{"id": 1, "code": "A", "name": "Bertha Radley", "role": "guild messenger"}]

    def test_the_giver_is_kept(self):
        from app import quest_parser

        accepted, _ = quest_parser.validate_quest_changes(self.REPLY, narration=self.NARRATION, npcs=self.NPCS,
                                                          shown_unnamed=["Bertha Radley"])
        self.assertEqual((accepted.get("new") or [{}])[0].get("giver_npc_id"), 1)

    def test_without_the_binding_it_stays_unplaced(self):
        from app import quest_parser

        accepted, _ = quest_parser.validate_quest_changes(self.REPLY, narration=self.NARRATION, npcs=self.NPCS)
        self.assertNotEqual((accepted.get("new") or [{}])[0].get("giver_npc_id"), 1)


class AKindOfPersonIsNoOneNew(unittest.TestCase):
    """8B run 20, T0: "She is the kind of person who knows what to look for" seeded a second woman."""

    def test_one_woman(self):
        from app import world

        text = ("A woman with a satchel of tools leans against a post, her eyes scanning the flats. She is the kind "
                "of person who knows what to look for.")
        self.assertEqual(world._figure_hints(text), ["A woman"])


class TheyAreTheFigure(unittest.TestCase):
    """8B run 21, T0: "a figure stands ... watching you. They are a lean man in a weathered coat" made two people."""

    def test_one_man(self):
        from app import world

        text = ("A few steps away, a figure stands at the edge of the flats, watching you. They are a lean man in a "
                "weathered coat, his face half-hidden by a scarf.")
        self.assertEqual(world._figure_hints(text), ["a lean man"])


class TheStepsAreOutside(unittest.TestCase):
    """8B run 22, T1: "I walk over to the steps of The Heron" wrote the stayed-put Note."""

    def test_a_walk_to_the_steps_is_no_trip(self):
        from app import world

        self.assertFalse(world.travel_intent('I walk over to the steps of The Heron. "Morning, Esme."'))
        self.assertTrue(world.travel_intent("I walk up the steps into The Heron."))


class HandedItToYou(unittest.TestCase):
    """8B run 22, T2: "picked up a pie ... and handed it to you" read as nothing arriving; "As you bit into it" as no eating."""

    S = "She sighed, picked up a pie wrapped in cloth, and handed it to you with a nod."

    def test_a_hand_over(self):
        from app import world

        self.assertEqual(world._prose_item_outcome(self.S, "pie", ["pie"]), "gain")

    def test_a_bite_on_the_spot(self):
        from app import world

        self.assertEqual(world._prose_item_outcome(self.S + " As you bit into it, the crust was flaky.", "pie", ["pie"]), "loss")


class ATakeThatSlipsIsNoGain(unittest.TestCase):
    """8B run 23, T1: "You reach for it, but ... the can slips from your grip" put the can in the pack."""

    def test_the_slip(self):
        from app import world

        t = ("You spot a rusted tin can near the base of the door. You reach for it, but the effort strains your arms, "
             "and the can slips from your grip, clattering against the floor.")
        self.assertEqual(world._prose_item_outcome(t, "rusty tin can", world._item_name_tokens("rusty tin can")), "loss")

    def test_caught_again_is_kept(self):
        from app import world

        t = "The key slips from your grip. You snatch it up again and pocket it."
        self.assertEqual(world._prose_item_outcome(t, "key", ["key"]), "gain")


class TheDebtRunsTheWayTheBackstorySays(unittest.TestCase):
    """8B runs 19 and 24: "the guild's tallyman owes you a winter of credit"; Isk owes the tallyman."""

    BACK = ("Her mother went out on the flats six years ago and never came back. Isk owes the guild's tallyman for a "
            "winter of credit and carries her mother's brass tide-reckoner.")

    def test_turned_around(self):
        from app import prose_state

        text = "The salvage guild’s tallyman owes you a winter of credit, and you carry their debt like a weight."
        fixed, changes = prose_state.repair_inverted_debt(text, self.BACK, "Isk Tarrow")
        self.assertTrue(fixed.startswith("You owe the salvage guild’s tallyman a winter of credit"), fixed)
        self.assertEqual(len(changes), 1)
        fixed, _ = prose_state.repair_inverted_debt("But the guild's tallyman still owes you a winter's credit.",
                                                    self.BACK, "Isk Tarrow")
        self.assertIn("you still owe the guild's tallyman", fixed)

    def test_speech_and_other_debts_stay(self):
        from app import prose_state

        text = "\"The tallyman owes you nothing,\" Hal says. The baker owes you two coppers."
        self.assertEqual(prose_state.repair_inverted_debt(text, self.BACK, "Isk Tarrow")[0], text)


class AFactTheSceneNeverShows(unittest.TestCase):
    """8B run 24, T2: "The tallow chandler is suspicious of the player's intentions" with no chandler in the scene."""

    PROSE = "You pick up the broken lantern. The brass fittings still hold, and you tuck it into your pack."

    def test_dropped_and_kept(self):
        from app import world

        self.assertFalse(world._fact_shown("The tallow chandler is suspicious of the player's intentions.", self.PROSE, ""))
        self.assertTrue(world._fact_shown("The lantern's brass fittings still hold.", self.PROSE, ""))
        self.assertTrue(world._fact_shown("Esme sells pies at The Heron.", "Esme Everly pushes the tray closer.", ""))


class AMoveToHereWithAWalk(unittest.TestCase):
    """8B run 24, T2: MOVE to the district the player stood in, with a WALK, wrote "MOVE to Drowned Lower District dropped"."""

    def test_only_the_walk_is_judged(self):
        from app import world

        patch = {"move_to_location": "Drowned Lower District"}
        rows = [{"id": 2, "code": "L2", "name": "Drowned Lower District", "parent_id": 1, "kind": ""}]
        got = world._unasked_unshown_move({"player": patch, "map_walk": {"direction": "north", "steps": 1}}, patch, rows,
                                          "I pick up the broken lantern.", intent="investigation",
                                          narration="You pick up the broken lantern.", current_name="Drowned Lower District")
        self.assertEqual(got, "map walk")


class WorthTheHaulAsksForIt(unittest.TestCase):
    """8B run 24, T3: "... attached to anything worth the haul" refused the iron box the prose has her carry."""

    def test_the_article_changes_nothing(self):
        from app.llm import player_take_intent

        self.assertTrue(player_take_intent("I check whether the chain is still attached to anything worth the haul."))
        self.assertFalse(player_take_intent("I wonder if the trip out is worth the risk."))


class ACrowbarFromNowhere(unittest.TestCase):
    """8B run 24, T3: "You pry at the links with a crowbar" with no crowbar."""

    def test_the_tool_phrase_goes(self):
        from app import prose_state

        text = ("The chain is stiff with salt. You pry at the links with a crowbar, feeling the resistance of something "
                "still holding. A creak echoes as the last link gives way, revealing a small iron box.")
        fixed, fixes = prose_state.repair_unowned_weapon(text, ["worn boots"], "I check the chain.")
        self.assertIn("You pry at the links, feeling the resistance", fixed)
        self.assertEqual(fixes[0]["why"], "unowned_tool_phrase")

    def test_someone_elses_knife_stays(self):
        from app import prose_state

        text = ("The chain is stiff with salt. A man with a knife watches you from the wreck. You keep your distance "
                "from him and the water.")
        self.assertEqual(prose_state.repair_unowned_weapon(text, ["worn boots"], "I check the chain.")[0], text)


class TheYardIsNotTheTallyHouse(unittest.TestCase):
    """8B run 25, T1: "You reach the salvage yard" read as arriving at the guild's tally house; "You step inside" was cut."""

    LINE = ("Before the tide turns I walk up into town to the salvage guild's tally house to ask the tallyman what "
            "work he'll take against my debt.")

    def test_the_head_word(self):
        from app import llm

        self.assertEqual(llm._asked_destination_heads(self.LINE), {"house"})

    def test_no_cut_before_the_door(self):
        from app import llm

        prose = ("You walk through the narrow streets. You reach the salvage yard, where the air smells of rust. The "
                 "tally house is a squat building at the edge of the yard. You step inside, and the air is colder.")
        self.assertIsNone(llm._completion_cut_point(prose, self.LINE))


class TheJobTakenByItsSubject(unittest.TestCase):
    """8B run 27, T3: "I'll take the Stormborn." left "Salvage the Wreck of the Stormborn" offered; and the
    short '"The Stormborn," he said' was cut from Eldrin as the player's line."""

    ROWS = [{"title": "Salvage the Wreck of the Stormborn", "giver": "Eldrin Vane"}]

    def test_accepts(self):
        from app import local_intel

        self.assertIsNotNone(local_intel.typed_offer_choice(self.ROWS, "\"I'll take the Stormborn.\" I hold his eye."))
        self.assertIsNone(local_intel.typed_offer_choice(self.ROWS, "\"I'll take the rope, and the lamp.\""))

    def test_a_short_span_is_not_the_players_line(self):
        from app.narration_pipeline import keep_player_words

        line = ("\"I'll take the Stormborn.\" I hold his eye. \"How much comes off the ledger if I bring back what's "
                "left, and where in the harbour is she lying?\"")
        body = ("Eldrin's fingers drummed the desk. \"The Stormborn,\" he said, voice low, \"is a wreck that sank in "
                "the mudflats.\"")
        fixed, _ = keep_player_words(body, line)
        self.assertIn("\"The Stormborn,\" he said", fixed)


class NoOneOfferedIt(unittest.TestCase):
    """8B run 29, T0: "The promise you made to your mother to bring back something from the flats" became a job."""

    def test_a_remembered_promise_is_no_job(self):
        from app import quest_parser

        narration = ("You have a few hours before the water returns. The promise you made to your mother to bring back "
                     "something from the flats.")
        reply = {"new": [{
            "title": "Bring back something from the flats", "giver": "mother", "difficulty": "normal",
            "steps": [{"title": "Explore the flats", "location": "L1"}],
            "offer_line": "You promised your mother you would bring back something from the flats before the water returns.",
            "evidence": "The promise you made to your mother to bring back something from the flats.",
        }]}
        accepted, rejected = quest_parser.validate_quest_changes(reply, narration=narration, npcs=[])
        self.assertEqual(accepted.get("new") or [], [])
        self.assertIn("no_one_offered_it", rejected[0]["reasons"])

    def test_a_spoken_offer_stays_possible(self):
        from app import quest_parser

        self.assertTrue(quest_parser._offer_is_spoken("We'll pay you a small coin for your help tonight.",
                                                      'The keeper nods. "We\'ll pay you a small coin for your help tonight."'))


class ASumSpokenIsNoPay(unittest.TestCase):
    """8B run 30, T3: '"Fifteen gold," he says, "but that's only if you finish the job."' paid 15 at once."""

    def test_spoken_sum_pays_nothing(self):
        from app import world

        prose = ("Gregory's smile is thin. \"Fifteen gold,\" he says, \"but that's only if you finish the job. If you "
                 "fail, you'll be marked.\"")
        result = {"narration": prose, "player": {"gold_delta": 15}}
        world._settle_stated_gold(result, "\"How much comes off my ledger when she's up?\"")
        self.assertIn(result["player"].get("gold_delta"), (None, 0))

    def test_coins_pressed_into_your_hand_pay(self):
        from app import world

        prose = "Gregory counts out nine coins and presses them into your hand. \"Nine,\" he says."
        result = {"narration": prose, "player": {"gold_delta": 9}}
        world._settle_stated_gold(result, "I hold out my hand.")
        self.assertEqual(result["player"].get("gold_delta"), 9)


class GoingInIsPartOfTheErrand(unittest.TestCase):
    """8B run 31, T1: "... to the tally house to ask the tallyman" was cut at "You step inside"."""

    LINE = ("Before the tide turns I walk up into town to the salvage guild's tally house to ask the tallyman what "
            "work he'll take against my debt.")

    def test_no_cut_at_the_door(self):
        from app import llm

        prose = ("You make your way past the rope makers until you reach the salvage guild's tally house. It stands at "
                 "the edge of the town. You step inside, the door creaking, and the dim light falls across the room.")
        self.assertIsNone(llm._completion_cut_point(prose, self.LINE))

    def test_a_walk_with_no_errand_still_stops_at_the_door(self):
        from app import llm

        prose = ("You make your way past the rope makers until you reach the salvage guild's tally house. It stands at "
                 "the edge of the town. You step inside, the door creaking, and the dim light falls across the room.")
        point = llm._completion_cut_point(prose, "I walk up into town to the salvage guild's tally house.")
        self.assertIsNotNone(point)


class WhatWorkAsksForWork(unittest.TestCase):
    """8B run 32, T1: "... to ask the tallyman what work he'll take against my debt" never opened the job parser."""

    def test_the_asks(self):
        from app import quest_parser as qp

        for line in ("Before the tide turns I walk up into town to the salvage guild's tally house to ask the tallyman "
                     "what work he'll take against my debt.",
                     "I ask about work.", "\"I want to work it off.\""):
            self.assertTrue(qp.player_asks_for_work(line), line)
        self.assertFalse(qp.player_asks_for_work("I ask her what the weather will do."))


class TheOtherHalfStaysASentence(unittest.TestCase):
    """8B run 33, T2: '"A silver and a promise," he says, "that's the price ..."' left '"that's the price ...'."""

    def test_capital_back(self):
        from app.narration_pipeline import keep_player_words

        line = ("\"A silver and a promise. That's the one.\" I stop at the table. \"I'd rather work it off than wait "
                "for you to come looking. What have you got?\"")
        body = ("Gregory eyes you. \"A silver and a promise,\" he says, \"that's the price of a man's word in these "
                "parts.\" He pushes a stack of parchment toward you.")
        fixed, _ = keep_player_words(body, line)
        self.assertIn("\"That's the price of a man's word", fixed)
        self.assertNotIn("\"that's the price", fixed)


class TalkEarnsNoXp(unittest.TestCase):
    """8B run 33, T3: XP 17 for a question, kept on outcomes "fight" (status not_combat) and a proposed new job."""

    def test_no_outcome_from_peace_or_an_offer(self):
        from app import world

        result = {"_deterministic_combat": {"status": "not_combat"},
                  "quest_changes": {"new": [{"title": "Salvage Runner"}], "updates": []}, "player": {}}
        outcomes = world._turn_outcomes(_OutcomeConn(), result, player_input="\"Name the job, Gregory.\"")
        self.assertNotIn("fight", outcomes)
        self.assertNotIn("quest_change", outcomes)

    def test_a_step_still_counts(self):
        from app import world

        result = {"_deterministic_combat": {"status": "not_combat"},
                  "quest_changes": {"new": [], "updates": [{"action": "step_done",
                                                             "evidence": "You haul the last crate up; the hold is done."}]},
                  "player": {}}
        self.assertIn("quest_change", world._turn_outcomes(_OutcomeConn(), result, player_input="I haul the crate up."))

    def test_a_step_with_no_result_is_talk(self):
        # 8B run 63, T6: a step proposed on "I owe the guild a winter's credit" kept XP 7.
        from app import world

        result = {"_deterministic_combat": {"status": "not_combat"}, "player": {},
                  "quest_changes": {"new": [], "updates": [
                      {"quest": "Q1", "action": "step_done", "evidence": "I owe the guild a winter's credit."}]}}
        self.assertNotIn("quest_change", world._turn_outcomes(_OutcomeConn(), result, player_input="\"What is it?\""))

    def test_a_job_that_pays_moves_no_coin(self):
        from app import world

        prose = ("Tamsin leans on her ropes. The mention of a job that pays off debts is a thread you can't ignore. "
                 "The wind tugs at your coat.")
        result = {"narration": prose, "player": {"gold_delta": 10}}
        note = world._settle_stated_gold(result, "\"Elias says you've a salvage job that pays against it.\"")
        self.assertEqual(note["source"], "gain_without_coin_dropped")

    def test_an_accept_is_talk(self):
        # 8B run 62, T2: a proposed (and refused) accept kept the model's XP 12.
        from app import world

        result = {"_deterministic_combat": {"status": "not_combat"},
                  "quest_changes": {"new": [], "updates": [{"quest": "Q1", "action": "accept"}]}, "player": {}}
        self.assertNotIn("quest_change", world._turn_outcomes(_OutcomeConn(), result, player_input="\"What job?\""))


class TheRestraintStands(unittest.TestCase):
    """8B run 33, T3: "I keep my hands off the coin" then "His eyes flick to the coin in your palm"."""

    def test_the_undoing_sentence_goes(self):
        from app import prose_state

        line = "\"Prove it how?\" I keep my hands off the coin. \"Name the job, Gregory.\""
        text = ("Gregory leans back, fingers steepled, and the weight of the moment settles on his face. \"A job,\" he "
                "says. His eyes flick to the coin in your palm, then back to you. \"The guild needs a runner,\" he says, "
                "\"someone to fetch things from the old docks before the tide swallows them.\"")
        fixed, changes = prose_state.repair_restraint_undone(text, line)
        self.assertNotIn("coin in your palm", fixed)
        self.assertEqual(changes[0]["why"], "restraint_undone")

    def test_leaving_a_place_is_no_restraint(self):
        from app import prose_state

        text = "You walk out of the tavern and take the lamp from its hook in your hand, the night cold on your face."
        self.assertEqual(prose_state.repair_restraint_undone(text, "I leave the tavern and head home.")[0], text)


class TheTallymanIsAJobNotAName(unittest.TestCase):
    """8B run 34, T1: NPC_NEW NAME "Tallyman" ROLE "Salvage Guild Tallyman" stored a person called Tallyman,
    and "Inside, the tallyman is a grizzled man" made "Inside" the job's giver."""

    def test_role_word_as_name(self):
        from app import world

        self.assertEqual(world._role_phrase("Tallyman", "Salvage Guild Tallyman"), "tallyman")
        # 8B run 43, T1: ROLE "Salvage Tally".
        self.assertEqual(world._role_phrase("Tallyman", "Salvage Tally"), "tallyman")
        self.assertEqual(world._role_phrase("Hugh", "smith"), "")

    def test_inside_is_no_speaker(self):
        from app import quest_parser

        narration = ("You pass a few fishmongers. Inside, the tallyman is a grizzled man with a ledger. \"You're "
                     "late,\" he says. \"The guild needs a runner for the old docks.\"")
        self.assertEqual(quest_parser._unknown_offer_speaker(narration, "The guild needs a runner for the old docks.",
                                                             []), "")


class AMarkOnAQuestionIsNoJob(unittest.TestCase):
    """8B run 35, T1: the draft's QUEST mark on "What work do you want?" became the job "Salvage Contract"."""

    NARRATION = ("You find the tallyman at a desk, a man with a scar. He looks up as you approach. \"You again,\" he "
                 "says. \"What work do you want?\"")

    def _reply(self, offer):
        return {"new": [{
            "title": "Salvage Contract", "giver": "Veyra Morn", "difficulty": "normal",
            "steps": [{"title": "Negotiate work terms", "location": "L2"}], "offer_line": offer,
            "evidence": "The narrator_marks: [ { \"op\": \"QUEST\" } ]", "_from_mark": True,
        }]}

    def test_the_question_is_no_job(self):
        from app import quest_parser

        npcs = [{"id": 1, "code": "A", "name": "Veyra Morn", "role": "salvage guild captain"}]
        accepted, rejected = quest_parser.validate_quest_changes(self._reply("What work do you want?"),
                                                                 narration=self.NARRATION, npcs=npcs)
        self.assertEqual(accepted.get("new") or [], [])
        self.assertIn("mark_on_a_question", rejected[0]["reasons"])


class AMarkWithNoOfferAndNoGiverIsNoJob(unittest.TestCase):
    """8B run 44, T1: QUEST GIVER "A" (Tilda, left in town) on "You're late, Flat-runner" became a job."""

    NARRATION = ("At the far end, behind a desk cluttered with ledgers, a man in a soot-stained coat looks up. "
                 "“You’re late, Flat-runner,” he says. “The tide’s already turned.”")
    NPCS = [{"id": 1, "code": "A", "name": "Tilda", "role": "watcher"},
            {"id": 2, "code": "B", "name": "Eldrin Vane", "role": "tallyman"}]

    def _check(self, narration, evidence):
        from app import quest_parser

        reply = {"new": [{"title": "Salvage Contract", "giver": "A", "difficulty": "normal",
                          "steps": [{"title": "Discuss work against debt", "location": "L1"}],
                          "evidence": evidence, "_from_mark": True}]}
        return quest_parser.validate_quest_changes(reply, narration=narration, npcs=self.NPCS)

    def test_a_greeting_is_no_job(self):
        accepted, rejected = self._check(self.NARRATION, "You’re late, Flat-runner")
        self.assertEqual(accepted.get("new") or [], [])
        self.assertIn("mark_with_no_offer_or_giver", rejected[0]["reasons"])

    def test_an_offer_in_the_words_stands(self):
        narration = self.NARRATION + " “There’s a job hauling wreck-iron, if you want the work.”"
        accepted, _rejected = self._check(narration, "There’s a job hauling wreck-iron, if you want the work.")
        self.assertEqual(len(accepted.get("new") or []), 1)


class HerTunicIsNotYours(unittest.TestCase):
    """8B run 36, T0: "a woman in a patched tunic [[I2]]" linked her tunic to the player's."""

    def test_no_code_on_what_another_wears(self):
        from app.llm import _inject_entity_codes_for_known_names as inject

        out = inject("A woman in a patched tunic pauses at the edge of the square. You pick up a rusty key.",
                     {"I2": "patched tunic", "I5": "rusty key"})
        self.assertIn("a woman in a patched tunic pauses", out.lower())
        self.assertNotIn("tunic [[I2]]", out)
        self.assertIn("rusty key [[I5]]", out)


class WhereAShipLiesIsNoLie(unittest.TestCase):
    """8B run 36, T5: "until I can see where the Stormcaller lies" rolled deception against the tallyman."""

    def test_location_and_lies(self):
        from app.skill_checks import infer_check_from_action as infer

        self.assertNotEqual((infer("I head down to the bay until I can see where the Stormcaller lies.", {}) or {})
                            .get("skill_code"), "deception")
        for line in ("I lie to the guard about where I was.", "\"I was at the tavern,\" I lie.", "I tell a lie."):
            self.assertEqual(infer(line, {})["skill_code"], "deception", line)

    def test_the_partner_left_behind(self):
        from app.skill_checks import infer_check_from_action as infer

        ctx = {"npcs": [{"code": "B", "name": "Wulfstan Glover", "role": "tallyman"}], "conversation_turn": {"addressed": ["B"]}}
        check = infer("I leave the tally house and ask a fisherman on the wall where the Stormcaller is.", ctx) or {}
        self.assertNotEqual((check.get("opposition") or {}).get("name"), "Wulfstan Glover")


class TheWalkEndsAtTheLastPlace(unittest.TestCase):
    """8B run 37, T6: "I climb the seawall steps and carry the shells back to the tally house" stopped at the seawall,
    and "With the water starting to creep back" rolled stealth (a crit)."""

    LINE = ("With the water starting to creep back, I climb the seawall steps and carry the shells back to the tally "
            "house for Verity to count against my ledger.")

    def test_destination(self):
        from app import world

        rows = [{"name": "The Seawall", "code": "L4"}, {"name": "The Salvage Guild's Tally House", "code": "L2"},
                {"name": "The Flats", "code": "L3"}]
        self.assertEqual(world._movement_destination_from_input(rows, self.LINE, "The Flats")["code"], "L2")

    def test_two_yards_name_neither_by_tail(self):
        from app import world

        rows = [{"name": "Saltmarrow Salvage Yard", "code": "L2"}, {"name": "The Blind Pike Salvage Yard", "code": "L5"}]
        got = world._movement_destination_from_input(rows, "I go find Roger at the Saltmarrow Salvage Yard.", "Saltmarrow")
        self.assertEqual(got["code"], "L2")

    def test_no_roll_for_the_water_or_the_stairs(self):
        from app.skill_checks import infer_check_from_action as infer

        self.assertIsNone(infer(self.LINE, {}))
        self.assertEqual(infer("I creep along the wall toward the guard.", {})["skill_code"], "stealth")


class APlaceholderIsNoPlace(unittest.TestCase):
    """8B run 38, T1: "Tide reckoner's Last Known Location" was stored as a place."""

    def test_names(self):
        from app import world

        self.assertFalse(world.is_plausible_place_name("Tide reckoner's Last Known Location"))
        self.assertFalse(world.is_plausible_place_name("Unknown Location"))
        self.assertTrue(world.is_plausible_place_name("The Location Office"))
        self.assertTrue(world.is_plausible_place_name("Hollow Maw Path"))


class ASharedPhraseIsNoRepeat(unittest.TestCase):
    """8B run 38, T2: the job offer shared "a cargo of rare goods" with the turn before and was cut as said before."""

    def test_new_line_with_a_shared_phrase(self):
        from app.narration_pipeline import speech_repeats

        prev = ["You’ll need to retrieve something lost to the sea. A cargo of rare goods, last seen in the "
                "tide-reckoner’s hands. If you bring it back, the debt is yours to settle."]
        new = ("You’ll need to salvage what’s lost in the drowned districts. The guild’s got a contract for a shipwreck "
               "off the northern coast, something with a cargo of rare goods. If you bring it back, you’ll get a fair "
               "share of the salvage.")
        self.assertFalse(speech_repeats(prev, new, mostly_new_stays=True))
        self.assertTrue(speech_repeats(prev, "A cargo of rare goods, last seen in the tide-reckoner's hands. If you "
                                             "bring it back, the debt is yours."))


class TheProseNamesTheNewPerson(unittest.TestCase):
    """8B run 39, T2: NPC_NEW "Isolde Frome" stored the tallyman the prose called Odo Kettle."""

    PROSE = ("Behind the counter sits a thin-faced man with ink on his fingers. His name was Odo Kettle, "
             "and he keeps the guild's tallies. \"Work against a debt?\" he asks.")

    def test_the_prose_name_wins(self):
        from app import world

        npcs = world._npcs_shown_in_prose(_ConnStub(), [{"name": "Isolde Frome", "role": "tallyman"}], self.PROSE)
        self.assertEqual([n["name"] for n in npcs], ["Odo Kettle"])

    def test_two_told_names_leave_the_op_alone(self):
        from app import world

        prose = self.PROSE + " Her name is Mara Sedge, says the clerk beside him."
        npcs = world._npcs_shown_in_prose(_ConnStub(), [{"name": "Isolde Frome", "role": "tallyman"}], prose)
        self.assertNotIn("Odo Kettle", [n.get("name") for n in npcs])


class SomeoneTalkedAboutIsNotShown(unittest.TestCase):
    """8B run 69, T3: "He's not a man who likes delays" bound the foreman at the docks to "a man"."""

    def test_a_figure_in_speech_binds_no_one(self):
        from app import world

        prose = ("Brida points to a shed on the map. \"That's where the goods are. The guild's foreman will check the "
                 "work. He's not a man who likes delays.\"")
        npcs = world._npcs_shown_in_prose(_ConnStub(), [{"name": "Garrik", "role": "foreman"}], prose)
        self.assertEqual(npcs, [])


class ThePlayerIsYou(unittest.TestCase):
    """8B run 68, T2: "pushed a stack of papers toward the player", "the player's patched tunic"."""

    def test_the_word_goes_outside_speech(self):
        from app import prose_state

        out, fixes = prose_state.repair_meta_leaks(
            "She pushed a stack of papers toward the player. Her gaze lingered on the player's patched tunic. "
            "\"The player is new,\" she says.")
        self.assertIn("toward you.", out)
        self.assertIn("on your patched tunic", out)
        self.assertIn("\"The player is new,\"", out)


class WhatHellTakeIsHisTaking(unittest.TestCase):
    """8B run 81, T1: "what work he'll take against my debt" read as the player taking; a second reckoner went in."""

    def test_his_taking_is_not_mine(self):
        from app.llm import player_take_intent

        self.assertFalse(player_take_intent(
            "Before the tide turns I walk up into town to the salvage guild's tally house to ask the tallyman what "
            "work he'll take against my debt."))
        self.assertTrue(player_take_intent("I'll take the rope."))

    def test_morning_is_no_speaker(self):
        from app import quest_parser

        self.assertIn("Morning", quest_parser._NOT_A_SPEAKER)


class HaulingFromTheWharfIsNoAskForTheTallyHouse(unittest.TestCase):
    """8B run 79, T5: "from the wharf up to the guild's storehouse" kept MOVE "The Salvage GUILD's TALLY HOUSE"."""

    def test_the_move_goes(self):
        from app import world

        rows = [{"id": 1, "code": "L1", "name": "Saltmarrow", "parent_id": 0, "kind": ""},
                {"id": 2, "code": "L2", "name": "The Salvage Guild's Tally House", "parent_id": 1, "kind": ""},
                {"id": 3, "code": "L3", "name": "The Old Wharf", "parent_id": 1, "kind": ""}]
        line = ("I don't waste words. I shoulder the first crate and start hauling them from the wharf up to the "
                "guild's storehouse, one after another, until the stack on the wharf is gone.")
        prose = "You shoulder the first crate. Malrik watches from the edge of the dock as the stack goes down."
        patch = {"move_to_location": "The Salvage GUILD's TALLY HOUSE"}
        got = world._unasked_unshown_move({"player": patch}, patch, rows, line, intent="travel", narration=prose,
                                          current_name="The Old Wharf")
        self.assertEqual(got, "The Salvage GUILD's TALLY HOUSE")

    def test_glued_bracket(self):
        from app import prose_state

        out, _ = prose_state.repair_meta_leaks("You haul them up to the(guild's storehouse. A crate (heavy) waits.")
        self.assertIn("to the guild's storehouse", out)
        self.assertIn("(heavy)", out)


class AJobAtTheYardIsAJob(unittest.TestCase):
    """8B run 78, T1: "a job at the salvage yard x1" went into the pack; the tallyman, "a man", was named Gunilda."""

    def test_the_head_is_before_the_place(self):
        from app import world

        self.assertTrue(world._abstract_grant(world._item_name_tokens("a job at the salvage yard"), "a job at the salvage yard"))
        self.assertFalse(world._abstract_grant(world._item_name_tokens("jar of salt"), "jar of salt"))

    def test_a_job_named_person_takes_the_sex_shown(self):
        from app import world

        prose = ("Inside, a man in a soot-streaked coat is hunched over a ledger. He is the tallyman, a man known for "
                 "his exacting nature.")
        npcs = world._npcs_shown_in_prose(_ConnStub(), [{"name": "Tallyman", "role": "tallyman"}], prose)
        self.assertEqual(npcs[0].get("_figure_pronouns"), "he")


class APlaceSaidIsNoPlaceGoneTo(unittest.TestCase):
    """8B run 77, T6: '"The tally house sent me about the dredge sites."' took Isk back to the tally house."""

    def test_a_job_named_in_speech_is_no_walk(self):
        # 8B run 80, T5: '"I'll clear the drowned shipyard."' at the desk kept MOVE "The Drowned Shipyard".
        from app import world

        rows = [{"id": 1, "code": "L1", "name": "Saltmarrow", "parent_id": 0, "kind": ""},
                {"id": 2, "code": "L2", "name": "The Salvage Guild's Tally House", "parent_id": 1, "kind": ""}]
        line = "\"I'll clear the drowned shipyard.\" I meet his eyes. \"Where is it sealed?\""
        prose = "Dorian leans back in his chair. \"The shipyard lies at the edge of the drowned Reach,\" he says."
        patch = {"move_to_location": "The Drowned Shipyard"}
        got = world._unasked_unshown_move({"player": patch}, patch, rows, line, intent="conversation", narration=prose,
                                          current_name="The Salvage Guild's Tally House")
        self.assertEqual(got, "The Drowned Shipyard")

    def test_speech_names_no_destination(self):
        from app import world

        line = ('I stop a few paces off, where the figure can see my empty hands. "You there. Are you Jorin, the '
                'foreman? The tally house sent me about the dredge sites."')
        self.assertNotIn("tally house", world._destination_text(line).lower())
        self.assertIn("docks", world._destination_text('"Take me to the docks," I tell him.').lower())


class TheForemanJorinIsNamedNotCalled(unittest.TestCase):
    """8B run 77, T3: "you'll report to the foreman, Jorin." stored Jorin as one spoken to in the scene."""

    def test_apposition_is_not_address(self):
        from app import world

        prose = "Marion taps the counter. \"You'll report to the foreman, Jorin. He's strict.\""
        self.assertEqual(world._npcs_shown_in_prose(_ConnStub(), [{"name": "Jorin", "role": "foreman"}], prose), [])
        called = world._npcs_shown_in_prose(_ConnStub(), [{"name": "Jorin", "role": "foreman"}], "\"Not yet, Jorin,\" you say.")
        self.assertEqual([n["name"] for n in called], ["Jorin"])


class AFigureInAnotherTrade(unittest.TestCase):
    """8B run 75, T1: the tallyman was bound to the woman at the weaver's stall and pinned "she"."""

    def test_the_weaver_is_not_the_tallyman(self):
        from app import world

        prose = ("You pass a tinker's cart and a weaver's stall where a woman in a soot-stained apron is mending a hem. "
                 "You reach the tally house, and the door creaks open on a dim interior.")
        self.assertEqual(world._npcs_shown_in_prose(_ConnStub(), [{"name": "Elias Vane", "role": "tallyman"}], prose), [])


class TheDebtIsNoJobButATaskIs(unittest.TestCase):
    """8B run 74, T2: "You'll need to work it off" and the player's own question became two jobs;
    run 47, T2: "You'll need to clear a full load" is a job."""

    LINE = "\"I owe the guild a winter's credit and I want to work it off.\" I stop. \"What job have you got that pays against the ledger?\""

    def _judge(self, giver_line, evidence):
        from app import quest_parser

        clerk = {"id": 1, "code": "A", "name": "Ulric Hooper", "role": "clerk"}
        narration = ("“I owe the guild a winter's credit and I want to work it off,” you say. “What job have "
                     "you got that pays against the ledger?” Ulric Hooper looks up. " + giver_line)
        return quest_parser.judge_offer(evidence, narration, self.LINE, offer_line=giver_line, giver=clerk,
                                        giver_ref="Ulric Hooper", npcs=[clerk])

    def test_working_off_ones_debt_is_no_job(self):
        line = "“You've got a debt, and debts aren't paid with promises. You'll need to work it off. What's your skill?”"
        self.assertFalse(self._judge(line, "What job have you got that pays against the ledger?")["ok"])

    def test_telling_back_the_ask_is_no_offer(self):
        # 8B run 76, T2: the player's own question as offer line, then "You're looking for work to pay it off".
        line = "“That's quite a debt. You're looking for work to pay it off, I assume.”"
        self.assertFalse(self._judge(line, "What job have you got that pays against the ledger?")["ok"])

    def test_a_task_set_is_a_job(self):
        line = "“You'll need to clear a full load—something worth at least ten silver.”"
        self.assertTrue(self._judge(line, line.strip("“”"))["ok"])


class AnOfferSpokenWithCurlyApostrophes(unittest.TestCase):
    """8B run 66, T1: "You'll get a fair share" did not match the prose's "You’ll", so no one offered it."""

    def test_spoken_either_way(self):
        from app import quest_parser

        self.assertTrue(quest_parser._offer_is_spoken(
            "You'll get a fair share of the salvage, and the debt'll be cleared.",
            "He nods. “I’ve got a job for you. You’ll get a fair share of the salvage, and the debt’ll be "
            "cleared.”"))

    def test_you_accept_the_offer_is_a_decision(self):
        # 8B run 67, T1: "You accept the offer. Lowen Thatcher gives you a map".
        from app import llm

        line = "I walk to the tally house to ask the tallyman what work he'll take against my debt."
        self.assertTrue(llm._decided_for_player("You accept the offer.", line))
        self.assertFalse(llm._decided_for_player("You accept the offer.", "\"I'll take it.\""))

    def test_you_agree_is_a_decision(self):
        from app import llm

        self.assertTrue(llm._decided_for_player("You agree to take the job, and he gives you a small nod.",
                                                "\"What job have you got?\""))


class WorkOthersAskForIsNoOffer(unittest.TestCase):
    """8B run 65, T1: "You're not the first to come asking for work" became a job."""

    def test_no_offer(self):
        from app import quest_parser

        narration = ("Gregory Cropper looks up. “You’re late,” he says.\n\n“I need to know what work "
                     "you’ll take against my debt.”\n\nGregory leans back. “You’re not the first to come "
                     "asking for work,” he says. “But I don’t take on just anyone.”")
        gregory = {"id": 1, "code": "A", "name": "Gregory Cropper", "role": "tallyman"}
        offer = ("Gregory Cropper [[A]] says: 'You're not the first to come asking for work, but I don't take on just "
                 "anyone. You've got a debt to the guild, and I don't deal in charity.'")
        verdict = quest_parser.judge_offer("You need to know what work you'll take against my debt.", narration,
                                           "I walk to the tally house to ask the tallyman what work he'll take.",
                                           offer_line=offer, giver=gregory, giver_ref="Gregory Cropper", npcs=[gregory])
        self.assertFalse(verdict["ok"], verdict)
        self.assertTrue(quest_parser._ACCEPTS_WORK_RE.search("\"Deal,\" she says."))


class AShorterSayingIsTheLine(unittest.TestCase):
    """8B run 63, T3: '"Whatever pays most," you said ... "Name it."' kept, then the typed lines said again."""

    def test_said_once_in_place(self):
        from app import narration_pipeline as npl

        line = '"Salvage. Out on the flats, whatever pays most against the ledger." I meet his eyes. "Name it and I\'ll go."'
        draft = ("Elias studies you. \"What kind of salvage?\"\n\nYou don't flinch. “Whatever pays most,” you "
                 "said, the words steady. “Name it.”\n\nHe exhales.")
        out, _changes = npl.keep_player_words(draft, line)
        self.assertEqual(out.count("whatever pays most"), 1)
        self.assertEqual(out.count("Name it"), 1)

    def test_a_signs_words_are_no_line(self):
        from app import narration_pipeline as npl

        line = '"Where do I find this Thaddeus, then - the harbour office?"'
        draft = "\"Over there,\" he says, nodding at a building with a sign that reads \"Harbour Office.\""
        out, _changes = npl.keep_player_words(draft, line)
        self.assertIn("reads \"Harbour Office.\"", out)


class ACodeThatNamesNothingGoes(unittest.TestCase):
    """8B run 61, T1: "the guild's tallyman [[TALLYMAN]]"; older runs had "[[N1]]", "[[Bertram Yates]]"."""

    def test_stray_codes_go_and_real_ones_stay(self):
        from app import world

        prose = ("You walk on, knowing the guild's tallyman [[TALLYMAN]] will be out soon. Elsabet Millward [[N1]], a "
                 "dairy hand, tends her pails. A man, [[Bertram Yates]], a sexton, nods. Mira [[A]] waves from "
                 "Saltmarrow [[L1]].")
        result = {"narration": prose}
        world._reconcile_prose_with_state(None, result, rejected=[], movement_report=None, gold_note=None,
                                          purse_note=None)
        out = world._narration_text(result)
        self.assertNotIn("[[TALLYMAN]]", out)
        self.assertNotIn("[[N1]]", out)
        self.assertIn("A man, Bertram Yates, a sexton", out)
        self.assertIn("Mira [[A]]", out)
        self.assertIn("Saltmarrow [[L1]]", out)


class ChoosingTheFirstIsTheirs(unittest.TestCase):
    """8B run 60, T2: "You choose the first, the one that offers the most chance" chose for the player."""

    def test_the_choice_goes(self):
        from app import llm

        line = "\"I owe the guild a winter's credit.\" I stop in front of the desk. \"What job have you got?\""
        self.assertTrue(llm._decided_for_player("You choose the first, the one that offers the most chance.", line))
        self.assertFalse(llm._decided_for_player("You choose the first, the salvage contract.",
                                                 "I choose the first, the salvage contract."))


class AQuoteInTheRewardIsTheJobs(unittest.TestCase):
    """8B run 59, T3: the parser nested "offer_line" and "evidence" in the reward, and the job had no quote."""

    def test_the_quote_is_lifted(self):
        from app import quest_parser

        narration = ("\"The Drowned Mariner,\" he said. \"Her hold's still packed with iron, good coin for a gut job.\"")
        reply = {"new": [{"title": "Gut the Drowned Mariner", "giver": "Everard Tolley", "difficulty": "normal",
                          "steps": [{"title": "Gut the wreck"}],
                          "reward": {"text": "", "offer_line": "Her hold's still packed with iron, good coin for a gut job.",
                                     "evidence": "Her hold's still packed with iron, good coin for a gut job."}}]}
        npcs = [{"id": 1, "code": "A", "name": "Everard Tolley", "role": "tallyman"}]
        accepted, rejected = quest_parser.validate_quest_changes(reply, narration=narration, npcs=npcs)
        self.assertEqual([q["title"] for q in accepted.get("new") or []], ["Gut the Drowned Mariner"], rejected)


class AMerchantShipIsNoMerchant(unittest.TestCase):
    """8B run 58, T3: "a wreck of a merchant ship" bound NPC_NEW "Gervase Grisham" to "a merchant"."""

    def test_the_modifier_is_no_figure(self):
        from app import world

        self.assertEqual(world._figure_hints("A wreck of a merchant ship, found half-sunk in the shallows.", []), [])
        self.assertEqual(world._figure_hints("A merchant waves from his stall.", []), ["A merchant"])


class NoMarkdownInAJobsName(unittest.TestCase):
    """8B run 57, T4: the job "Salvage the *Iron Widow*" kept the prose's markdown."""

    def test_the_stars_go(self):
        from app import quest_parser

        narration = ("“The salvagers are looking for a lost ship, the *Iron Widow*. If you find it, I'll pay you "
                     "for the work and the debt gets paid in full,” Fulk says.")
        reply = {"new": [{"title": "Salvage the *Iron Widow*", "giver": "Fulk Dimmock", "summary": "Find the *Iron Widow*.",
                          "steps": [{"title": "Find the *Iron Widow*"}], "difficulty": "normal",
                          "evidence": "If you find it, I'll pay you for the work and the debt gets paid in full"}]}
        npcs = [{"id": 1, "code": "A", "name": "Fulk Dimmock", "role": "tallyman"}]
        accepted, _rejected = quest_parser.validate_quest_changes(reply, narration=narration, npcs=npcs)
        self.assertEqual([q["title"] for q in accepted.get("new") or []], ["Salvage the Iron Widow"])

    def test_no_code_either(self):
        # 8B run 82, T2: "Debt Settlement: Tam Brooke [A]".
        from app import quest_parser

        narration = "“I'll pay you for the work if you haul the Iron Widow's cargo,” Fulk says."
        reply = {"new": [{"title": "Haul Cargo: Fulk Dimmock [A]", "giver": "Fulk Dimmock", "difficulty": "normal",
                          "steps": [{"title": "Haul the cargo"}],
                          "evidence": "I'll pay you for the work if you haul the Iron Widow's cargo"}]}
        npcs = [{"id": 1, "code": "A", "name": "Fulk Dimmock", "role": "tallyman"}]
        accepted, _rejected = quest_parser.validate_quest_changes(reply, narration=narration, npcs=npcs)
        self.assertEqual([q["title"] for q in accepted.get("new") or []], ["Haul Cargo: Fulk Dimmock"])


class TheJobsOwnVerbTakesIt(unittest.TestCase):
    """8B run 56, T3: "I'll clear the Stormbreaker." took no job; the offer was "Clear the Wreckage"."""

    def test_clear_the_stormbreaker(self):
        from app import local_intel as li
        from app import quest_parser as qp

        quest = {"id": 1, "code": "Q1", "title": "Clear the Wreckage", "status": "offered",
                 "description": "Clear the wreckage from the *Stormbreaker* to pay off a debt.", "giver": "Osbert"}
        line = "\"I'll clear the Stormbreaker.\" I set both hands flat on the desk. \"Which berth is she at?\""
        self.assertTrue(qp.player_takes_job(quest, line, [quest]))
        self.assertIsNotNone(li.typed_offer_choice([quest], line))
        self.assertIsNone(li.typed_offer_choice([quest], "\"I'll clear my throat.\""))


class TheSameNamedJobIsTheJobTaken(unittest.TestCase):
    """8B run 55, T6: "Investigate the Iron Tide's Raids" beside the active "Work for the Iron Tide"."""

    def test_same_subject_is_a_duplicate_but_an_employer_is_not(self):
        from app import quest_parser as qp

        ex = [{"id": 1, "title": "Work for the Iron Tide", "status": "active", "giver_npc_id": 1}]
        self.assertIsNotNone(qp._is_duplicate({"title": "Investigate the Iron Tide's Raids"}, ex, 2, ""))
        guild = [{"id": 1, "title": "Haul Iron for the Salvage Guild", "status": "active", "giver_npc_id": 1}]
        self.assertIsNone(qp._is_duplicate({"title": "Sort Nets for the Salvage Guild"}, guild, 2, ""))


class AndYouDoIsTheActAsked(unittest.TestCase):
    """8B run 55, T5: "He gestures for you to follow him, and you do" had the player follow."""

    def test_the_follow_goes_unless_the_line_follows(self):
        from app import llm

        text = "His expression is unreadable. He gestures for you to follow him, and you do, your steps quickening."
        kept, dropped = llm.drop_invented_player_acts_text(text, "\"Where is Captain Veyra?\" I ask the scarred man.")
        self.assertNotIn("and you do", kept)
        kept2, _ = llm.drop_invented_player_acts_text(text, "I follow him wherever he goes.")
        self.assertIn("and you do", kept2)


class TheEndOfACrateIsNoThing(unittest.TestCase):
    """8B run 54, T5: "I take the end of the nearest crate" put "end x1" in the pack."""

    def test_a_part_held_is_not_taken(self):
        from app import world

        self.assertEqual(world._taken_phrase("the end of the nearest crate with the laborers"), ("", 0))
        self.assertEqual(world._taken_phrase("the rusty key from the drawer"), ("rusty key", 1))


class TheLastOfTheHoldIsDone(unittest.TestCase):
    """8B run 54, T6: "That was the last of the hold. You're clear to go." held the dock job back as travel."""

    def test_the_finished_work_counts(self):
        from app import quest_parser as qp

        ev = "That was the last of the hold. You're clear to go."
        quest = {"id": 1, "code": "Q1", "title": "Unload Cargo at the Docks", "status": "active",
                 "current_step": 1, "total_steps": 1}
        self.assertFalse(qp._travel_only(ev))
        self.assertEqual(qp.done_check(ev, quest), [])
        self.assertTrue(qp._travel_only("You head down to the docks to find the damaged ship."))


class ARepeatIsTheirs(unittest.TestCase):
    """8B run 52, T3: '"The rusted tools," he repeats' was cut from 'the word "tools."' on, breaking the quote."""

    def test_the_echo_and_the_quoted_word_stay(self):
        from app import narration_pipeline as npl

        line = ('"The rusted tools, then." I lean on the desk. "Where do they lie, and what does bringing them up '
                'take off my ledger?"')
        draft = ("The tallyman pauses at the word \"tools.\" His face tightens. \"The rusted tools,\" he repeats. "
                 "\"They lie in the old dockyard.\" He leans back.")
        out, _changes = npl.keep_player_words(draft, line)
        self.assertIn("the word \"tools.\"", out)
        self.assertIn("he repeats", out)


class TheJobsGiverIsShownByTheJob(unittest.TestCase):
    """8B run 52, T3: the prose called Ralph only "the tallyman", and his job was filed under no one."""

    def test_the_tallyman_is_here(self):
        from app import quest_parser

        ralph = {"id": 2, "code": "B", "name": "Ralph", "role": "tallyman"}
        self.assertTrue(quest_parser._shown_by_role("The tallyman’s fingers trace the line.", ralph, [ralph]))
        other = {"id": 3, "code": "C", "name": "Odo", "role": "tallyman"}
        self.assertFalse(quest_parser._shown_by_role("The tallyman’s fingers trace the line.", ralph, [ralph, other]))


class OneLineVoicesTheRequest(unittest.TestCase):
    """8B run 48, T1: two invented player lines stood for "ask the tallyman what work he'll take"."""

    LINE = ("Before the tide turns I walk up into town to the salvage guild's tally house to ask the tallyman what "
            "work he'll take against my debt.")

    def test_the_second_subject_line_goes(self):
        from app.narration_pipeline import drop_invented_player_speech

        paras = ["\"I need to speak with you about my debt,\" you say.",
                 "He looks up. \"You're late,\" he says.",
                 "\"I can work,\" you say, your voice firm. \"I'll do whatever it takes to pay off my debt.\""]
        kept, dropped = drop_invented_player_speech(paras, self.LINE)
        self.assertTrue(dropped)
        self.assertNotIn("whatever it takes", " ".join(kept))


class TheVoicingIsOneLineEvenAfterANarratorBeat(unittest.TestCase):
    """8B run 49, T1: "I need to work ..." and "I'll do it." stood after a narrator sentence led the paragraph."""

    LINE = ("Before the tide turns I walk up into town to the salvage guild's tally house to ask the tallyman what "
            "work he'll take against my debt.")

    def test_only_the_first_line_stays(self):
        from app.narration_pipeline import drop_invented_player_speech

        paras = ["“You’re late,” he says.",
                 "You step forward. “I need to know what work you’ll take against my debt.”",
                 "The tallyman looks up. “Debt?” he says.",
                 "The guild is not known for its generosity. You step closer, your voice low. "
                 "“I need to work. I need to pay what I owe.”",
                 "“There’s work,” he says at last.",
                 "The guild’s work is never easy. You step back, your hands clenched. “I’ll do it.”"]
        kept, dropped = drop_invented_player_speech(paras, self.LINE)
        self.assertIn("I need to know what work", kept[1])
        self.assertEqual(len(dropped), 2)

    def test_someone_elses_line_after_your_act_stays(self):
        from app.narration_pipeline import drop_invented_player_speech

        paras = ["“What have you got?” the captain asks.",
                 "You hand over the rope, and the captain inspects it closely. “This is a quality piece.”"]
        kept, dropped = drop_invented_player_speech(paras, "I ask the captain what he'd pay for the rope.")
        self.assertIn("quality piece", kept[1])


class LeavingWhereTheWalkWentIsANewMove(unittest.TestCase):
    """8B run 49, T1: the line walked to the tally house; "You leave the tally house" walked Isk out again."""

    def test_the_leave_goes_and_a_leave_on_the_way_stays(self):
        from app import llm

        line = ("Before the tide turns I walk up into town to the salvage guild's tally house to ask the tallyman "
                "what work he'll take against my debt.")
        kept, dropped = llm.drop_invented_player_acts_text(
            "The tallyman nods. \"Meet at the dock.\" You leave the tally house, the weight of the debt heavy on "
            "your shoulders. The town is quiet.", line)
        self.assertNotIn("You leave the tally house", kept)
        self.assertTrue(llm._walk_asked("leave the Salvage Yard and head north", "I leave the yard and walk north to the cottage."))


class ANameToldIsAPerson(unittest.TestCase):
    """8B run 48, T1: "His name is Reinald Strand, a sedan bearer by trade" stored no one."""

    def test_the_told_name_is_found(self):
        from app import world

        text = ("Inside, the tallyman sits behind a desk. He is a wiry man with a scar. His name is Reinald Strand, "
                "a sedan bearer by trade, but his true skill lies in keeping track of salvaged goods.")
        self.assertEqual(world._introduced_people(text, ["Isk"], set()),
                         [{"name": "Reinald Strand", "role": "sedan bearer"}])
        self.assertEqual(world._introduced_people("He nods. His name is Odo Kettle.", [], set()),
                         [{"name": "Odo Kettle", "role": ""}])


class TheSoundIsNotThePlayerGoing(unittest.TestCase):
    """8B run 43, T1: "the sound of waves ... echoes through the hollow alleys" moved Isk into "Hollow"."""

    KW = dict(known_names={"Saltmarrow"}, person_names=set(), current_name="Saltmarrow")

    def test_the_sound_goes_nowhere(self):
        from app import world

        text = ("The scent of brine clings to the damp stones, and the sound of waves lapping against the wharf "
                "echoes through the hollow alleys.")
        self.assertEqual(world._movement_destination_from_narration(text, **self.KW), "")

    def test_a_where_clause_is_not_the_player(self):
        # 8B run 61, T1: "where the buildings give way to the ruins" made "Ruins".
        from app import world

        text = "You reach the edge of the town, where the buildings give way to the ruins of the old harbour."
        self.assertEqual(world._movement_destination_from_narration(text, **self.KW), "")

    def test_the_player_still_goes(self):
        from app import world

        self.assertEqual(world._movement_destination_from_narration(
            "You push through the reeds into a clearing.", **self.KW), "Clearing")
        self.assertEqual(world._movement_destination_from_narration(
            "Stepping out onto the driftwood path, you follow the last tide's trace.", **self.KW), "Driftwood Path")


class TheRoleNamesTheFigure(unittest.TestCase):
    """8B run 41, T1: NPC_NEW "Tobin Yates" ROLE "tallyman" was dropped beside "the tallyman sits behind a desk"."""

    PROSE = ("You step inside, the scent of mildew and old iron greeting you. Inside, the tallyman sits behind a "
             "desk cluttered with ledgers and salt-crusted coins, his eyes sharp and unyielding.")

    def test_the_tallyman_is_tobin(self):
        from app import world

        npcs = world._npcs_shown_in_prose(_ConnStub(), [{"name": "Tobin Yates", "role": "tallyman"}], self.PROSE)
        self.assertEqual([n["name"] for n in npcs], ["Tobin Yates"])
        self.assertEqual(npcs[0]["_bound_hint"], "the tallyman")
        self.assertNotIn("tall", str(npcs[0].get("appearance") or ""))

    def test_another_job_is_no_one_shown(self):
        from app import world

        npcs = world._npcs_shown_in_prose(_ConnStub(), [{"name": "Tobin Yates", "role": "ropemaker"}], self.PROSE)
        self.assertEqual(npcs, [])

    def test_the_tally_house_keeps_the_players_name(self):
        from app import world

        line = ("Before the tide turns I walk up into town to the salvage guild's tally house to ask the tallyman "
                "what work he'll take against my debt.")
        self.assertEqual(world._asked_building_phrase(line, "The salvage guild's tally house looms ahead."),
                         "Salvage Guild's Tally House")
        self.assertNotIn("Edge", world._asked_building_phrase("I walk to the edge of the house.", "The house."))


class TheBeatGoesWithTheCutLine(unittest.TestCase):
    """8B run 39, T2: "You leaned forward." stood alone once its invented line was cut."""

    PARAS = ["\"You want to work it off? You'll have to do it well,\" he says.",
             "You leaned forward. \"What kind of job?\"",
             "He glanced at the ledger. \"The guild needs someone at the docks.\""]
    LINE = ("\"Isk Tarrow. I owe the guild a winter's credit.\" I stop in front of his desk. \"I want to work it "
            "off. What job have you got that pays against the ledger?\"")

    def test_the_lone_beat_goes(self):
        from app.narration_pipeline import drop_invented_player_speech

        kept, dropped = drop_invented_player_speech(self.PARAS, self.LINE)
        self.assertEqual(dropped, ["\"What kind of job?\""])
        self.assertEqual(kept[1], "")

    def test_an_act_with_substance_stays(self):
        from app.narration_pipeline import drop_invented_player_speech

        paras = list(self.PARAS)
        paras[1] = ("You set the dripping crate of salvage on the counter between you. \"What kind of job?\"")
        kept, _dropped = drop_invented_player_speech(paras, self.LINE)
        self.assertTrue(kept[1].startswith("You set the dripping crate"))


class BothHalvesOfATakenLineGo(unittest.TestCase):
    """8B run 88, T7: the player's line in the stranger's mouth, split by a tag, left its second half alone."""

    LINE = ('"Late for what? I do not know you." I stay where I am, crouched by the post. '
            '"I am sorting the docks for the guild. What are you carrying there?"')

    def test_no_half_is_left(self):
        from app.narration_pipeline import keep_player_words

        prose = ('"Late for what? I do not know you," you say. You stay where you are, crouched by the post.\n\n'
                 '"I am sorting the docks for the guild," the stranger replies, their gaze flicking to the bundle. '
                 '"What are you carrying there?"\n\nThe wind picks up off the water.')
        fixed, _ = keep_player_words(prose, self.LINE)
        self.assertEqual(fixed.count("What are you carrying there?"), 1)
        self.assertNotIn("the stranger replies", fixed)
        self.assertIn("The wind picks up", fixed)


class TheWayThereIsNoArrival(unittest.TestCase):
    """8B run 87, T1: the rag picker at the yard's edge, before "Inside,", was stood behind the tally desk."""

    PROSE = ("You make your way toward the salvage yard, where the guild's tally house stands like a fortress. "
             "Everard Cobb [[A]] watches you from the edge of the yard. You don't stop for him. The guild's tally "
             "house is your destination.\n\nInside, the air is thick with the scent of oil. At the center stands "
             "the tallyman.")

    def test_inside_is_where_the_walk_ends(self):
        from app.world import _arrival_at

        at = _arrival_at(self.PROSE, "house")
        self.assertGreater(at, self.PROSE.index("Everard"))
        self.assertEqual(self.PROSE[at:].lstrip()[:6], "Inside")

    def test_reaching_it_is_arriving(self):
        from app.world import _arrival_at

        prose = "You reach the salvage guild's tally house. Inside, Milo [[A]] is hunched over a ledger."
        self.assertLess(_arrival_at(prose, "house"), prose.index("Milo"))


class OutOfAnotherVerbIsNoExit(unittest.TestCase):
    """8B run 82, T5: "I walk along the warped planks and call out" left the wharf."""

    def test_calling_out_stays(self):
        from app.world import venue_move_intent

        line = ('I walk along the warped planks and call out to anyone near the moored skiffs. '
                '"Anyone hiring out a boat for the day?"')
        self.assertEqual(venue_move_intent(line), "")

    def test_the_way_out_still_leaves(self):
        from app.world import venue_move_intent

        self.assertEqual(venue_move_intent("I head to the door and out onto the street."), "exit")
        self.assertEqual(venue_move_intent("I finish my drink and walk out."), "exit")


class _OutcomeConn:
    def execute(self, *_a, **_k):
        class _Row:
            def fetchone(self):
                return (0,)

        return _Row()


class _ConnStub:
    """No one known yet."""

    def execute(self, *_a, **_k):
        class _Rows:
            def fetchone(self):
                return None

            def fetchall(self):
                return []

        return _Rows()


if __name__ == "__main__":
    unittest.main()
