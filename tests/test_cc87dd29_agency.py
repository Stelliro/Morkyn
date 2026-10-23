"""Whose words and choices the prose shows, and repeats, from the Hermes 3 8B game cc87dd29 (#30, #78, #29).

The strings are the tester's (scratchpad evidence turn-cc87dd29-0000NN) and the
baseline replay's (live/baseline, game 974c9d69). The model is a fake: each
small ask answers the way a test sets it, and every ask is recorded.
"""
import unittest
from unittest import mock

from app import llm
from app.narration_pipeline import (
    drop_invented_player_speech,
    drop_lines_from_earlier_scenes,
    drop_repeated_sentences,
    quoted_spans,
    split_sentences,
    speech_units,
)
from app.player_agency import (
    AgencyAsks,
    choice_taken_cut,
    close_open_quotes,
    drop_retold_paragraphs,
    parse_yes_no,
    plain,
    reply_to_dropped_act_cut,
    strip_refs,
)


def fake(answer):
    asked = []

    def chat(system, user, phase):
        asked.append((phase, user))
        return answer(phase, user) if callable(answer) else answer

    return AgencyAsks(chat), asked


def by_kind(**replies):
    """A fake whose reply depends on the ask: by_kind(choice="Yes", own_act="No.")."""
    return lambda phase, user: replies.get(phase[len("agency_ask_"):], "")


T7_P1 = (
    "Beth [[B]]'s eyes widen in surprise as you aim your rifle directly at her. \"What the hell?\" she exclaims, "
    "hands raised. \"I'm the doctor here, not the enemy!\" You lower the barrel slightly. \"You're not the enemy,\" "
    "you confirm, \"but this is a dangerous place. I have to be careful.\" A flicker of understanding passes between you."
)
T7_P2 = (
    "The early morning light filters in through the clinic's grimy windows, casting long shadows across the room as "
    "the sun begins to rise outside."
)
T7_INPUT = "i shoot at Beth [[B]]"

T14_P1 = (
    "The early post-apocalyptic dawn paints the surrounding forests in shades of gray and blue. You're not alone for "
    "long. \"Hey! calls out a woman's sharp but friendly shout. \"You're just the customer I was hoping for. Doc "
    "Beth's clinic is this way, if you need medical help or just looking for work."
)
T14_P2 = "\"I'm looking for work if you've got something,\" you add, hoping to explore the opportunities she mentioned."
T14_P3 = (
    "As you walk with Doc Beth [[B]], her friendly demeanor shifts to business. \"So, what kind of work were you "
    "thinking about? I've got a few projects in mind that could use some extra help.\""
)
T14_INPUT = "i say hi to Beth [[B]]"

T2_P1 = (
    "You stride purposefully towards New Vegas [[A]], the minigun cradled in your armored fist, when a sudden ping "
    "from your power armor's readouts pulls you up short. A new message blinks into existence: \"New target detected. "
    "2 miles west. Priority high.\" Your gaze swings automatically to the west, tracking the direction of the threat. "
    "Through the armor's visor, the distant wasteland seems to shimmer and shift, as if the very air is charged with "
    "unseen forces."
)
T2_P2 = (
    "You trudge onwards, the minigun held ready in your armored grip, when suddenly the power armor's readouts ping a "
    "priority alert. A flashing arrow points 2 miles west, towards a new Deathclaw target lurking in the ruins. The "
    "decision presses - continue to New Vegas [[A]] or investigate this closer threat first?"
)
T2_P3 = (
    "With a whir of servos, you turn aside from the main road, the minigun held ready as you march west to "
    "investigate the new target. The rusted fence looms ahead, sagging gates swinging in the post-apocalyptic breeze."
)
T2_P4 = (
    "The power armor's readouts flicker, a priority alert ping interrupting your march towards New Vegas [[A]]. A "
    "blinking arrow points 2 miles west, where a new target waits. The minigun swings up to aim, the decision pressing "
    "- continue to the city or turn aside for this closer threat first? The rusted fence looms ahead, a barrier to the "
    "Strip beyond. Your armored form casts a long shadow on the cracked asphalt, the sun glinting off your suit."
)
T2_INPUT = "i get in my power armor, grab my minigun, and set off to New Vegas to fight a Deathclaw"

# Baseline replay T1 ("I go into the clinic."), the draft before the act drop.
B1_DRAFT = (
    "You enter the clinic, a small, dimly lit room with a few beds and a counter where a search-and-rescue volunteer "
    "named Marisol [[A]] is sitting. She looks up at you as you come in. \"Can I help you?\" Marisol [[A]] asks. "
    "You explain that you were bitten by something last night and are seeking treatment. Marisol [[A]] frowns. "
    "\"I'm afraid we're low on supplies here. Radiation Fenced Sanctuary [[L1]] doesn't have the resources for major "
    "injuries. You'll need to head to a larger settlement to get proper care.\" You ask her if she can at least clean "
    "the wound to prevent infection. Marisol [[A]] nods and gestures for you to take a seat on one of the beds. She "
    "disinfects the wound with some antiseptic and wraps it in gauze. \"That's the best I can do here. Be careful out "
    "there.\" You thank her for her help. As you leave the clinic, you catch a glimpse of a mysterious figure watching "
    "you from the shadows. You can't quite make out who it is."
)

# T8's speech memory (prompt_context.speech_memory.recent lines) and its first paragraph.
T8_EARLIER = [
    "What the hell?",
    "I'm the doctor here, not the enemy!",
    "You're not the enemy, but this is a dangerous place. I have to be careful.",
    "Stay safe out there!",
    "And keep an eye out for any radiation hotspots. The ghouls are bad enough without having to deal with that too!",
]
T8_P1 = (
    "The missile explodes against the clinic wall, the blast knocking you off your feet. Shards of metal rain down as "
    "Beth [[B]] stumbles back, raising her hands in shock. \"What the hell?\" she shouts. \"I'm the doctor here, not "
    "the enemy! You're not the enemy, but this is a dangerous place. I have to be careful.\""
)
T9_P1 = (
    "The morning light filters through the grimy clinic windows, casting a dim glow over the tense standoff between "
    "you and Beth [[B]]. \"What the hell?\" she asks, her voice shaking slightly. \"I'm the doctor here, not the damn "
    "hostile! You're not the hostile, but this is a dangerous place. I have to be careful!\""
)


class TheAskReply(unittest.TestCase):
    def test_yes_and_no_and_anything_else(self):
        self.assertTrue(parse_yes_no("Yes."))
        self.assertFalse(parse_yes_no(" no, she does not"))
        self.assertIsNone(parse_yes_no("The player says it."))
        self.assertIsNone(parse_yes_no(""))

    def test_each_text_is_asked_once_and_a_failure_keeps_the_old_rule(self):
        asks, asked = fake("yes")
        asks.speaks(T7_P1)
        asks.speaks(T7_P1)
        self.assertEqual(len(asked), 1)
        self.assertEqual(asked[0][0], "agency_ask_speaks")

        def broken(system, user, phase):
            raise RuntimeError("model down")

        down = AgencyAsks(broken)
        self.assertIsNone(down.speaks(T7_P1))
        self.assertIn("model down", down.log[0]["error"])
        self.assertIsNone(AgencyAsks(None).speaks(T7_P1))


class YouAsTheSpeaker(unittest.TestCase):
    """T7: '"You're not the enemy," you confirm' after a missed shot (#30)."""

    def test_t7_line_given_to_the_player_goes_when_the_ask_says_the_player_speaks(self):
        asks, asked = fake("Yes")
        out, dropped = drop_invented_player_speech([T7_P1, T7_P2], T7_INPUT, says=asks.speaks, voices=asks.voices)
        self.assertEqual(len(dropped), 1)
        self.assertIn("you confirm", dropped[0])
        self.assertNotIn("you confirm", out[0])
        self.assertIn("\"I'm the doctor here, not the enemy!\"", out[0])  # Beth's own line stays
        self.assertEqual([p for p, _u in asked], ["agency_ask_speaks"])
        self.assertIn("Does the player say the words in quotes?", asked[0][1])
        self.assertNotIn("[[B]]", asked[0][1])

    def test_without_the_ask_the_old_verb_list_rules(self):
        # The line got through before: "confirm" is not in the tag list.
        out, dropped = drop_invented_player_speech([T7_P1, T7_P2], T7_INPUT)
        self.assertEqual(dropped, [])

    def test_a_line_the_player_only_hears_stays(self):
        para = "The door bangs open behind you. \"Get down, all of you!\" you hear someone shout from the hall."
        asks, asked = fake("no")
        out, dropped = drop_invented_player_speech([para, T7_P2], "i crouch behind the counter", says=asks.speaks)
        self.assertEqual(dropped, [])
        self.assertEqual(len(asked), 1)

    # Lines the player only hears, reads or is told, with the reply Hermes 3 8B
    # gave to that shape in the live eval (2026-10-23; speaks 39/39), plus the
    # round-2 skeptic's overhear/radio/sign cases.
    HEARD = (
        ("The curtain twitches. \"Get out of my clinic,\" you hear her say from behind the curtain.", "no"),
        ("You hear Beth shout from the gate, \"Stay safe out there!\"", "no"),
        ("\"Welcome to Thornford,\" you are told by the guard at the gate.", "no"),
        ("You remember your mother's words: \"Never trust a doctor who smiles.\"", "No."),
        ("You watch the stranger, who mutters, \"Not today.\"", "no"),
        ("You overhear the guard, \"Gate closes at dusk.\"", "no"),
        ("\"This is Radio Free Wasteland,\" you hear the radio announce.", "no"),
        ("\"Get down!\" you hear someone shout.", "no"),
    )

    def test_lines_the_player_only_hears_stay_on_the_measured_reply(self):
        for para, reply in self.HEARD:
            asks, asked = fake(reply)
            out, dropped = drop_invented_player_speech([para, T7_P2], "i wait by the door", says=asks.speaks)
            self.assertEqual(dropped, [], para)
            self.assertEqual(out[0], para, para)
            self.assertTrue(all(p == "agency_ask_speaks" for p, _ in asked), para)

    def test_a_note_that_reads_is_not_asked_and_stays_even_on_yes(self):
        para = "A scrap of paper is pinned to the door. \"Meet me at the docks,\" it reads."
        asks, asked = fake("Yes")
        out, dropped = drop_invented_player_speech([para, T7_P2], "i read the note", says=asks.speaks)
        self.assertEqual(dropped, [])
        self.assertEqual(asked, [])

    def test_lines_the_player_speaks_go_on_the_measured_reply(self):
        for para, reply in (
            ("\"Hands where I can see them,\" you bark, leveling the rifle.", "Yes"),
            ("You lean in, \"Where is the key, Beth?\"", "yes"),
            ("\"Run,\" you whisper back to the boy, and he bolts.", "yes"),
        ):
            asks, _ = fake(reply)
            out, dropped = drop_invented_player_speech([para, T7_P2], "i wait by the door", says=asks.speaks)
            self.assertEqual(len(dropped), 1, para)

    def test_other_tag_words_go_the_same_way(self):
        for tag in ("you murmur", "you concede", "you breathe out", "you offer quietly"):
            para = f"Beth [[B]] lowers her pistol. \"Fine, we both walk away,\" {tag}, and she nods."
            asks, _ = fake("yes")
            out, dropped = drop_invented_player_speech([para, T7_P2], T7_INPUT, says=asks.speaks)
            self.assertEqual(len(dropped), 1, tag)

    def test_the_players_own_words_stay_and_are_not_asked_about(self):
        para = "Beth [[B]] lowers her pistol. \"Easy, I'm not here to hurt you,\" you confirm, raising a hand."
        asks, asked = fake("yes")
        out, dropped = drop_invented_player_speech(
            [para, T7_P2], "\"Easy, I'm not here to hurt you\" i say to Beth [[B]]", says=asks.speaks
        )
        self.assertEqual(dropped, [])
        self.assertEqual(asked, [])


class AVoicedRequest(unittest.TestCase):
    """T14: '"I'm looking for work if you've got something," you add' on "i say hi" (#30)."""

    def test_t14_line_the_player_did_not_choose_goes_on_two_noes(self):
        # Live: the voices ask answered "no" on this line 3/3 (live-eval T14_hi_work).
        asks, asked = fake(by_kind(speaks="yes", voices="no", could_say="No."))
        out, dropped = drop_invented_player_speech([T14_P1, T14_P2, T14_P3], T14_INPUT, says=asks.speaks, voices=asks.voices)
        self.assertEqual(dropped, [T14_P2])
        self.assertEqual(out[1], "")
        kinds = [p for p, _ in asked]
        self.assertEqual(kinds[-2:], ["agency_ask_voices", "agency_ask_could_say"])
        self.assertIn("The player wanted to: i say hi to Beth\nThe player says:", asked[-2][1])
        self.assertIn("Does saying that do what the player wanted?", asked[-2][1])

    def test_the_raw_reference_is_shown_as_a_name(self):
        asks, asked = fake(by_kind(speaks="yes", voices="no", could_say="No."))
        drop_invented_player_speech([T14_P1, T14_P2, T14_P3], "i say hi to @Cbeth", says=asks.speaks, voices=asks.voices)
        prompts = "\n".join(u for _p, u in asked)
        self.assertNotIn("@C", prompts)
        self.assertIn("The player wanted to: i say hi to Beth", prompts)

    def test_a_no_alone_does_not_drop_a_greeting(self):
        # Live: "Hello there, doc." for "say hi" and "Thanks, doc. I owe you one."
        # for "thank her" drew a wrong "no" 3/3 (live-eval V_hi_hello, V_thank_ok).
        for line, typed in (
            ("\"Hello there, doc,\" you call out with a wave.", "i say hi to Beth [[B]]"),
            ("\"Thanks, doc. I owe you one,\" you say.", "i thank Beth [[B]]"),
        ):
            for second in ("yes", "The player greets her."):
                asks, _ = fake(by_kind(voices="no", could_say=second))
                out, dropped = drop_invented_player_speech([T14_P1, line, T14_P3], typed, says=asks.speaks, voices=asks.voices)
                self.assertEqual(dropped, [], (line, second))

    def test_a_question_on_an_asking_turn_stays_on_yes(self):
        line = "\"Got anything that pays?\" you ask, leaning on the counter."
        asks, _ = fake(by_kind(voices="yes"))
        out, dropped = drop_invented_player_speech([T14_P1, line, T14_P3], "i ask Beth [[B]] about work", says=asks.speaks, voices=asks.voices)
        self.assertEqual(dropped, [])

    def test_without_the_ask_the_length_rule_kept_it(self):
        out, dropped = drop_invented_player_speech([T14_P1, T14_P2, T14_P3], T14_INPUT)
        self.assertEqual(dropped, [])

    def test_a_line_that_is_the_greeting_stays(self):
        para = "\"Morning, Doc. Good to see you up early,\" you call out with a wave."
        asks, _ = fake("yes")
        out, dropped = drop_invented_player_speech([T14_P1, para, T14_P3], T14_INPUT, says=asks.speaks, voices=asks.voices)
        self.assertEqual(dropped, [])


class AScriptLine(unittest.TestCase):
    """Baseline T2: 'You: i shoot Marisol [[A]]' pasted into the prose (#30)."""

    TEXT = (
        "Marisol [[A]] says, \"Oh good, a new volunteer. We could use the help. What's your name?\"\n\n"
        "You: i shoot Marisol [[A]]\n\n"
        "Marisol [[A]]'s eyes widen and she steps back, raising her hands defensively. \"Whoa, easy there! I'm not the enemy.\""
    )

    def test_the_echoed_input_goes(self):
        turn = llm._drop_script_lines({"narration": self.TEXT}, "i shoot Marisol\n\nResolved player references: ...", {}, "x", [])
        self.assertNotIn("You:", turn["narration"])
        self.assertIn("What's your name?", turn["narration"])
        self.assertIn("Whoa, easy there!", turn["narration"])

    def test_other_words_become_the_players_line_and_are_judged_as_speech(self):
        text = self.TEXT.replace("You: i shoot Marisol [[A]]", "You: Name's Will. Where do I start?")
        turn = llm._drop_script_lines({"narration": text}, "i shoot Marisol", {}, "x", [])
        self.assertIn("\"Name's Will. Where do I start?\" you say.", turn["narration"])
        spoken = llm._drop_invented_player_speech(turn, "i shoot Marisol")
        self.assertNotIn("Where do I start?", spoken["narration"])

    def test_the_players_own_typed_words_stay(self):
        text = self.TEXT.replace("You: i shoot Marisol [[A]]", "You: Name's Will.")
        turn = llm._drop_script_lines({"narration": text}, "\"Name's Will.\" i tell her", {}, "x", [])
        spoken = llm._drop_invented_player_speech(turn, "\"Name's Will.\" i tell her")
        self.assertIn("Name's Will.", spoken["narration"])

    def test_a_name_with_a_colon_in_a_sentence_is_not_a_script_line(self):
        text = "The board reads: Work wanted. You: read it twice."
        turn = llm._drop_script_lines({"narration": text}, "i read the board", {}, "x", [])
        self.assertEqual(turn["narration"], text)


class AChoiceMadeForThePlayer(unittest.TestCase):
    """T2: the prose asks 'continue to New Vegas or investigate?' and then turns aside (#30)."""

    TEXT = "\n\n".join([T2_P1, T2_P2, T2_P3, T2_P4])

    def test_t2_scene_ends_before_the_question_that_the_prose_answered(self):
        # Live: choice "Yes" 3/3 on this pair (live-eval T2_turn_west).
        asks, asked = fake(by_kind(choice="Yes", own_act="No."))
        point = choice_taken_cut(self.TEXT, asks, T2_INPUT)
        self.assertIsNotNone(point)
        self.assertTrue(self.TEXT[point["cut"]:].startswith("The decision presses - continue to New Vegas"))
        self.assertTrue(self.TEXT[: point["cut"]].rstrip().endswith("lurking in the ruins."))
        self.assertEqual([p for p, _ in asked], ["agency_ask_choice", "agency_ask_own_act"])
        self.assertIn("continue to New Vegas or investigate", asked[0][1])
        self.assertIn("The player wanted to: " + T2_INPUT, asked[1][1])
        self.assertIn("you turn aside from the main road", asked[1][1])

    def test_the_cut_goes_through_the_turn_and_ends_on_no_menu(self):
        asks, _ = fake(by_kind(choice="Yes", own_act="No."))
        trace = []
        turn = llm._drop_player_overreach({"narration": self.TEXT}, T2_INPUT, "x", trace, {}, asks=asks)
        self.assertNotIn("turn aside from the main road", turn["narration"])
        self.assertNotIn("or investigate this closer threat", turn["narration"])
        self.assertEqual(turn["_scene_cut"]["family"], "choice_taken")
        self.assertIn("scene_ended_before_choice_made_for_player", [e.get("event") for e in trace])

    def test_the_choice_the_player_made_is_never_cut(self):
        # Round-2 reverse case: the player typed the very choice the prose tells.
        own = "i turn aside and head west to investigate the target"
        text = T2_P1 + "\n\nContinue to New Vegas, or investigate the closer threat? You turn aside and march west toward the signal."
        for second in ("Yes", "It does."):
            asks, asked = fake(by_kind(choice="Yes", own_act=second))
            self.assertIsNone(choice_taken_cut(text, asks, own))
            turn = llm._drop_player_overreach({"narration": text}, own, "x", [], {}, asks=asks)
            self.assertIn("You turn aside and march west toward the signal.", turn["narration"])

    def test_no_keeps_the_scene(self):
        asks, asked = fake("no")
        self.assertIsNone(choice_taken_cut(self.TEXT, asks, T2_INPUT))
        self.assertEqual([p for p, _ in asked], ["agency_ask_choice"])

    def test_a_question_with_no_choice_in_it_is_not_asked(self):
        asks, asked = fake("yes")
        text = T2_P1 + "\n\nWhat could be out there? You keep walking, the minigun steady in your grip."
        self.assertIsNone(choice_taken_cut(text, asks))
        self.assertEqual(asked, [])


class AReplyToADroppedAct(unittest.TestCase):
    """Baseline T1: 'You explain that you were bitten' was dropped, and her treatment of the bite stayed (#30)."""

    def test_the_scene_ends_on_her_question(self):
        asks, asked = fake("yes")
        turn = llm._drop_player_overreach({"narration": B1_DRAFT}, "I go into the clinic.", "x", [], {}, asks=asks)
        self.assertTrue(turn["narration"].endswith("\"Can I help you?\" Marisol [[A]] asks."))
        self.assertNotIn("wound", turn["narration"])
        self.assertEqual([p for p, _ in asked], ["agency_ask_reply"])
        # The measured wording (live-eval ALT_reply_no_negation, 33/33).
        self.assertTrue(asked[0][1].startswith("First: You explain that you were bitten"))
        self.assertIn("\nThen: Marisol frowns.", asked[0][1])
        self.assertTrue(asked[0][1].endswith('Is the "then" part an answer to the "first" part? Answer yes or no.'))
        self.assertNotIn("did not do", asked[0][1])

    def test_no_keeps_what_the_act_drop_left(self):
        asks, _ = fake("no")
        turn = llm._drop_player_overreach({"narration": B1_DRAFT}, "I go into the clinic.", "x", [], {}, asks=asks)
        self.assertIn("Marisol [[A]] frowns.", turn["narration"])
        self.assertNotIn("You explain", turn["narration"])

    def test_an_act_with_no_line_after_it_is_not_asked(self):
        asks, asked = fake("yes")
        before = "You walk in. You nod to yourself. The room is quiet and the beds are empty, sheets folded at the ends."
        after = "You walk in. The room is quiet and the beds are empty, sheets folded at the ends."
        self.assertIsNone(reply_to_dropped_act_cut(before, after, ["You nod to yourself."], asks, floor=10))
        self.assertEqual(asked, [])


class ARetoldParagraph(unittest.TestCase):
    """T2: the ping, the arrow two miles west and the choice told again paragraph after paragraph (#29)."""

    def test_t2_retold_sentences_go_and_new_ones_stay(self):
        asks, asked = fake("yes")
        out, dropped = drop_retold_paragraphs([T2_P1, T2_P2], asks)
        self.assertEqual(out[0], T2_P1)
        self.assertTrue(any("ping a priority alert" in s for s in dropped))
        # One ask for the pair, then one per sentence that shares much of it;
        # the question with mostly new words is not put to it and stays.
        self.assertEqual(asked[0][1].split("\n")[1], "Passage 2: " + plain(T2_P2))
        self.assertTrue(all(p == "agency_ask_retell" for p, _ in asked))
        self.assertIn("The decision presses", out[1])

    def test_only_the_sentences_the_ask_confirms_go(self):
        # Round-2 skeptic's continuation: a new act in the same room shares 62%
        # of the earlier paragraph's words. Per sentence, the ask answered the
        # same shape "No." live (live-eval V_same_place_new_act) and "Yes." on
        # a retold one (V_same_other_words).
        p1 = (
            "The clinic's grimy windows let in the morning light. Beth stands behind the examination table, her pistol "
            "holstered, watching you with tired eyes as dust drifts over the rusted surgical tools."
        )
        p2 = (
            "Beth steps out from behind the examination table, unholsters the pistol and sets it on the tray beside the "
            "rusted surgical tools. The morning light catches the dust. \"Fine. Ask your questions,\" she says, tired eyes on you."
        )

        def reply(phase, user):
            later = user.split("\nPassage 2: ", 1)[1]
            if later.startswith("Beth steps out"):
                return "No." if "catches the dust" not in later else "Yes."
            return "Yes."

        asks, asked = fake(reply)
        out, dropped = drop_retold_paragraphs([p1, p2], asks)
        self.assertEqual(dropped, ["The morning light catches the dust."])
        self.assertIn("unholsters the pistol", out[1])
        self.assertIn("\"Fine. Ask your questions,\" she says", out[1])
        self.assertFalse(any("Fine. Ask" in u for _p, u in asked[1:]))  # new words are never put to it

    def test_no_keeps_both(self):
        asks, _ = fake("no")
        out, dropped = drop_retold_paragraphs([T2_P1, T2_P2, T2_P4], asks)
        self.assertEqual(dropped, [])
        self.assertEqual(out, [T2_P1, T2_P2, T2_P4])

    def test_paragraphs_that_share_little_are_not_asked(self):
        asks, asked = fake("yes")
        out, dropped = drop_retold_paragraphs([T7_P1, T7_P2], asks)
        self.assertEqual(asked, [])
        self.assertEqual(dropped, [])


class ATitleIsNotASentenceEnd(unittest.TestCase):
    """T13: 'With surprising speed for someone her age, Dr. Her expression is fierce' (#29)."""

    def test_split_keeps_the_title_with_the_name(self):
        self.assertEqual(
            split_sentences("With surprising speed for someone her age, Dr. Beth [[B]] grabs a scalpel. Mr. Hale nods."),
            ["With surprising speed for someone her age, Dr. Beth [[B]] grabs a scalpel.", "Mr. Hale nods."],
        )
        self.assertEqual(len(speech_units("Ask Dr. Beth. She knows.")), 2)

    def test_t13_repeat_drop_leaves_no_cut_sentence(self):
        p3 = (
            "Dr. Beth [[B]] leans back in her chair, her expression one of pure disbelief. \"You're out of your damn mind "
            "if you think I'm going to let you kill me in my own clinic,\" she snarls, her voice dripping with anger. "
            "With surprising speed for someone her age, she grabs a scalpel from the tray on her desk and points it "
            "directly at you."
        )
        p4 = (
            "\"I'm not afraid to use this if I have to. So is this really just a job interview, or do you have some "
            "more... deadly intentions here today?\" With surprising speed for someone her age, Dr. Beth [[B]] grabs a "
            "scalpel from the tray on her desk and points it directly at you. Her expression is fierce and unwavering."
        )
        kept, dropped = drop_repeated_sentences([p3, p4])
        self.assertNotIn("Dr. Her", kept[1])
        self.assertNotIn(", Dr.", kept[1])
        self.assertEqual(kept[1].count('"') % 2, 0)
        self.assertIn("deadly intentions here today?\"", kept[1])
        self.assertTrue(any("grabs a scalpel" in d for d in dropped))


class AnOpenQuote(unittest.TestCase):
    """T14: '"Hey! calls out a woman's sharp but friendly shout.' (#29)."""

    def test_t14_paragraph_is_closed(self):
        fixed, count = close_open_quotes(T14_P1)
        self.assertGreaterEqual(count, 1)
        self.assertIn("\"Hey!\" calls out a woman's sharp but friendly shout.", fixed)
        self.assertTrue(fixed.endswith("looking for work.\""))
        self.assertEqual(fixed.count('"') % 2, 0)

    def test_balanced_and_trailing_lines_are_left_alone(self):
        for text in (
            "\"Wait... no, not yet,\" she says. \"Hold the door.\"",
            "\"Stop.\" He raises a hand. \"Now.\"",
            "She mutters something under her breath.",
            "the gate creaks shut.\"",
            # Round-2 skeptic: balanced lines with a lower-case word after a stop.
            "\"Help! help me!\" she cries.",
            "\"Who? me?\" Jonah asks.",
            "\"Wait. no, not that one,\" he says.",
            "\"Oh! and bring the rope,\" she adds.",
            "Beth sighs. \"Fine! fine. Take it,\" she says, and \"Go!\" you hear from the hall.",
            # Curly quotes and a mark that cannot be read are not touched.
            "“Hey! calls out a woman.",
            "He wrote \" in the margin.",
        ):
            self.assertEqual(close_open_quotes(text), (text, 0), text)

    def test_only_the_one_bad_shape_in_an_unbalanced_paragraph(self):
        # Balanced line first, then the T14 shape: only the second line changes.
        text = "\"Help! help me!\" she cries. " + T14_P1
        fixed, count = close_open_quotes(text)
        self.assertTrue(fixed.startswith("\"Help! help me!\" she cries. "))
        self.assertIn("\"Hey!\" calls out", fixed)
        # Two openers with no stop and lower-case word between: nothing is guessed.
        text = "\"Wait for me. She runs off. \"Now!\""
        self.assertEqual(close_open_quotes(text), (text, 0))

    def test_the_real_t14_order_with_the_next_paragraph_opening_on_a_quote(self):
        # In the shipped T14 the paragraph after the open one was the player's
        # '"I'm looking for work ..."' line: both of the woman's lines close,
        # and the balanced paragraphs around it are untouched.
        turn = llm._close_open_quotes({"narration": "\n\n".join([T14_P1, T14_P2, T14_P3])}, "x", [])
        paragraphs = turn["narration"].split("\n\n")
        self.assertIn("\"Hey!\" calls out", paragraphs[0])
        self.assertTrue(paragraphs[0].endswith("looking for work.\""))
        self.assertEqual(paragraphs[1:], [T14_P2, T14_P3])

    def test_the_engine_pass_closes_it_on_the_turn(self):
        turn = llm._close_open_quotes(
            {"narration": T14_P1 + "\n\n" + T14_P3, "narration_segments": [{"label": "paragraph", "text": T14_P1}, {"label": "paragraph", "text": T14_P3}]},
            "x",
            [],
        )
        self.assertIn("\"Hey!\" calls out", turn["narration"])
        self.assertIn("\"Hey!\" calls out", turn["narration_segments"][0]["text"])
        self.assertIn(T14_P3, turn["narration"])


class ALineSaidInAnEarlierScene(unittest.TestCase):
    """T8/T9: Beth says, word for word, the line T7's prose gave the player (#78)."""

    def test_t8_stitched_repeat_goes_and_the_short_echo_stays(self):
        out, dropped = drop_lines_from_earlier_scenes([T8_P1], T8_EARLIER, "i shoot a missile at Beth [[B]]")
        self.assertEqual(len(dropped), 1)
        self.assertIn("not the enemy! You're not the enemy", dropped[0])
        self.assertIn("\"What the hell?\" she shouts.", out[0])

    def test_t9_one_word_reskin_goes(self):
        out, dropped = drop_lines_from_earlier_scenes([T9_P1], T8_EARLIER + [T8_P1], "i shoot Beth [[B]] with my laser rifle")
        self.assertEqual(len(dropped), 1)
        self.assertIn("damn hostile", dropped[0])

    def test_new_words_in_the_same_line_stay(self):
        para = (
            "Beth [[B]] steadies herself. \"You're not the enemy, but this is a dangerous place. Now put the launcher "
            "down before someone gets hurt, and tell me why you came here armed like an army.\""
        )
        out, dropped = drop_lines_from_earlier_scenes([para], T8_EARLIER, "i lower the launcher")
        self.assertEqual(dropped, ["You're not the enemy, but this is a dangerous place."])
        self.assertIn("\"Now put the launcher down", out[0])

    def test_a_stock_line_with_one_word_changed_is_a_new_line(self):
        # Round-2 skeptic: whole replies went for merely similar short lines.
        earlier = ["I don't know what you mean.", "Can I help you with something?", "We need to get out of here now."]
        for para in (
            "Jonah shrugs. \"I don't know what you want.\" He turns away.",
            "The clerk looks up. \"Can I help you with anything?\"",
        ):
            out, dropped = drop_lines_from_earlier_scenes([para], earlier, "i wait")
            self.assertEqual(dropped, [], para)
            self.assertEqual(out, [para])
        # The same words are still a repeat.
        out, dropped = drop_lines_from_earlier_scenes(["The clerk looks up. \"Can I help you with something?\""], earlier, "i wait")
        self.assertEqual(len(dropped), 1)

    def test_no_bare_tag_or_empty_quotation_is_left(self):
        earlier = ["You're not the enemy, but this is a dangerous place."]
        para = (
            "Beth [[B]] lowers the pistol. \"You're not the enemy, but this is a dangerous place,\" she says, \"so tell "
            "me what you came to my clinic for and why you brought a launcher with you.\""
        )
        out, dropped = drop_lines_from_earlier_scenes([para], earlier, "i lower the launcher")
        self.assertNotIn("\"\"", out[0])
        self.assertNotRegex(out[0], r"\"[\s,.]*\" she says")
        self.assertTrue(all(any(c.isalpha() for c in s) for s in quoted_spans(out[0])))

    def test_the_players_own_typed_line_is_never_dropped(self):
        para = "\"I'm the doctor here, not the enemy!\" you say, mocking her."
        out, dropped = drop_lines_from_earlier_scenes([para], T8_EARLIER, "\"I'm the doctor here, not the enemy!\" i mock her")
        self.assertEqual(dropped, [])

    def test_through_the_speech_memory_gate(self):
        context = {
            "speech_memory": {"recent": [{"code": "B", "line": l, "unit": f'"{l}"'} for l in T8_EARLIER], "people": [{"code": "B", "name": "Beth", "here": True}]},
            "last_narration": T7_P1,
        }
        turn = llm._apply_speech_memory({"narration": T8_P1}, context, "i shoot a missile at Beth [[B]]", "x", [])
        self.assertNotIn("You're not the enemy", turn["narration"])
        self.assertIn("\"What the hell?\" she shouts.", turn["narration"])

    def test_a_line_only_the_last_narration_holds_counts_too(self):
        context = {"speech_memory": {"recent": [], "people": []}, "last_narration": T7_P1}
        para = "Beth [[B]] glares. \"You're not the enemy, but this is a dangerous place. I have to be careful.\""
        turn = llm._apply_speech_memory({"narration": "You wait.\n\n" + para}, context, "i wait", "x", [])
        self.assertNotIn("dangerous place", turn["narration"])


class AQuoteAndItsTagAreOneSentence(unittest.TestCase):
    """Live eval 2026-10-23: prose_state.sentence_spans numbered '"What the hell?"' apart from 'she exclaims'."""

    def spans(self, text):
        from app.prose_state import sentence_spans

        return [s for _a, _b, s in sentence_spans(text)]

    def test_t7_line_and_its_tag(self):
        self.assertEqual(
            self.spans(T7_P1.replace("Beth [[B]]'s", "Beth's")),
            [
                "Beth's eyes widen in surprise as you aim your rifle directly at her.",
                "\"What the hell?\" she exclaims, hands raised.",
                "\"I'm the doctor here, not the enemy!\"",
                "You lower the barrel slightly.",
                "\"You're not the enemy,\" you confirm, \"but this is a dangerous place.",
                "I have to be careful.\"",
                "A flicker of understanding passes between you.",
            ],
        )

    def test_a_lower_case_tag_after_a_question(self):
        self.assertEqual(self.spans("\"Back so soon?\" she asks from the doorway. She smiles."),
                         ["\"Back so soon?\" she asks from the doorway.", "She smiles."])

    def test_a_new_sentence_after_a_line_still_splits(self):
        # 7B run 28 T2: a capitalised name after the quote starts a sentence an act cut reads.
        self.assertEqual(
            self.spans("\"Where's the reeve keep the tide tables these days?\" Lettice looks up from her notes."),
            ["\"Where's the reeve keep the tide tables these days?\"", "Lettice looks up from her notes."],
        )
        self.assertEqual(self.spans("\"Go now.\" The door slams. \"Run!\" You sprint out."),
                         ["\"Go now.\"", "The door slams.", "\"Run!\"", "You sprint out."])
        self.assertEqual(self.spans("\"Help!\" The guard turns."), ["\"Help!\"", "The guard turns."])
        self.assertEqual(self.spans("\"Fine.\" Beth turns away."), ["\"Fine.\"", "Beth turns away."])


class ThePlayersReferencesInAnAsk(unittest.TestCase):
    """Live eval 2026-10-23: 'i say hi to @Cbeth' reached the asks as typed."""

    def test_a_named_pick_becomes_its_name_and_a_bare_code_goes(self):
        self.assertEqual(plain("i say hi to @Cbeth"), "i say hi to Beth")
        self.assertEqual(plain("i give !I2 to @B at #L1"), "i give to at")
        self.assertEqual(strip_refs("ask @Cold_tom about @Q1"), "ask Old Tom about")
        for prose in ("\"Hey! Beth, over here!\"", "Smith & Sons", "Room #4", "Beth [[B]] nods."):
            self.assertEqual(strip_refs(prose), prose)


class TheAsksAreOnTheCallPath(unittest.TestCase):
    def test_prompt_reply_and_time_reach_trace_and_usage(self):
        trace, usage = [], []
        with mock.patch.object(llm, "_chat_content", return_value="Yes"):
            asks = llm._agency_asks(120, usage, trace)
            self.assertTrue(asks.speaks(T7_P1))
        request = [e for e in trace if e.get("event") == "request"]
        response = [e for e in trace if e.get("event") == "response"]
        self.assertEqual(request[0]["phase"], "agency_ask_speaks")
        self.assertIn("Does the player say the words in quotes?", request[0]["user_prompt"])
        self.assertEqual(response[0]["raw_content"], "Yes")
        self.assertIn("duration_seconds", response[0])
        self.assertEqual(usage[0]["phase"], "agency_ask_speaks")

    def test_no_ask_once_the_model_is_down(self):
        asks = llm._agency_asks(120, [{"phase": "draft", "model_unavailable": True}], [])
        self.assertIsNone(asks.chat)


if __name__ == "__main__":
    unittest.main()
