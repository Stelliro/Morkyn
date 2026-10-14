"""8B run classes (runs 7+): one test per fixed class."""
from __future__ import annotations

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
