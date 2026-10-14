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

        self.assertIn('the player is "you" and needs no name', prompts.VERIFY_PROMPT)


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
