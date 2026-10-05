"""
Playtest #3, #5 and #6(b): the paragraph writer (narration_para_N).

All three came from one stage. The writer is a separate model call per beat,
and it was given a 120-character op summary, bare entity codes and the
player's input as fresh text on every beat. So it:

  #3  invented "the Inkwell Inn", tagged it with [[I1]] (the player's boots),
      and code expansion printed "Inkwell Inn Well-Worn Boots"; it also made
      the draft's baker a cartographer, and a near-copy sentence crossed the
      paragraph boundary ("grows" / "growing");
  #5  answered one remark three times, because already_said held only each
      paragraph's first sentence and every beat was told to respond;
  #6b put the player's own threat in Aria's mouth, because nothing marked
      the quote as the player's.

Shapes and text below are from data/model_traces/turn-00000{1,3,6}.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import llm
from app.narration_pipeline import (
    NarrationLedger,
    build_paragraph_briefs,
    drop_repeated_sentences,
    drop_repeated_speech,
    entity_roster,
    is_near_restatement,
    plan_paragraph_budget,
    player_quotes,
    player_words_misattributed,
    quoted_spans,
    run_narration_pipeline,
)

CONFIG = {"mle_model": "qwen3:8b", "context_window": 32768, "response_token_cap": 800}

CONTEXT = {
    "current_location": {"name": "The Back Lane", "code": "L1"},
    "locations": [{"name": "The Back Lane", "code": "L1"}],
    "npcs": [
        {"code": "A", "name": "Aria", "role": "baker", "location": "L1"},
        {"code": "B", "name": "Quillwatch", "role": "porter", "location": "L1"},
        {"code": "C", "name": "Ashwalker", "role": "rag picker", "location": "L1"},
        # A code with no name is useless to the writer (the CAR leak of #9).
        {"code": "CAR", "location": "L1"},
    ],
    "inventory": [
        {"code": "I1", "name": "Well-Worn Boots"},
        {"code": "I2", "name": "Weathered Leather Tunic"},
    ],
}

OPENING_DRAFT = {
    "narration": (
        "You stand in the Back Lane, a narrow passage between low stone buildings. "
        "The morning sun slants through gaps in the cobblestone street, casting long shadows.\n\n"
        "A figure leans against the wall, a young woman with a patched tunic and a weathered look. "
        "Her eyes narrow as they take in your presence, then she steps forward, her voice low and cautious. "
        "\"You're new here, aren't you? I'm Aria, the baker. Welcome to Low Gate.\""
    ),
    "npcs": [{"code": None, "name": "Aria", "role": "baker", "location": "L1"}],
    "conversations": [{"npc_code": "ARIA", "topic": "Welcome to Low Gate. What brings you here, stranger?"}],
}

TURN6_INPUT = (
    'i say "state your business, if you came to intimidate you came to the wrong place, '
    "standing in dark alleys is a quick way to get hurt, so its not the smartest idea, "
    'i wont hold it against you if you didn\'t know any better" essentially insulting them.'
    "\n\nResolved player references: Active scene — interacting (replies to the player): Aria [[A]]."
)
TURN6_DRAFT = {
    "narration": (
        "You approach Aria, the baker, with a sharp and mocking tone. \"State your business, if you came "
        "to intimidate, you came to the wrong place. Standing in dark alleys is a quick, easy path to "
        "getting hurt. So, if you didn't know any better, I won't hold it against you.\" Aria's expression "
        "hardens slightly, but she steps back from you. Ashwalker, a rag picker, watches the exchange with "
        "a wary eye.\n\n\"Perhaps we should continue,\" you suggest, stepping towards the northeast exit. "
        "Ashwalker nods and follows, keeping a watchful distance."
    ),
    "player": {"move_to_location": "Plains2"},
}
# Paragraph 1 as the writer produced it in turn 6: the player's words, Aria speaking.
TURN6_P1 = (
    "Aria narrows her icy blue stare at you, arms crossed over her chest. \"State your business, if you "
    "came to intimidate, you came to the wrong place. Standing in dark alleys is a quick, foolhardy move. "
    "It's not the smartest idea, I won't hold it against you if you didn't know any better.\" She leans "
    "back against the brick wall, one eyebrow raised."
)

TURN3_INPUT = 'i say to Aria [[A]] "you are the only thing peculiar around these parts."'
TURN3_DRAFT = {
    "narration": (
        "You approach Aria, the baker, and point out her peculiar presence. \"You are the only thing "
        "peculiar around these parts.\"\n\nAria narrows her gaze, her expression a mix of curiosity and "
        "caution. \"Do you often see what others don't?\" she asks, her voice soft but watchful.\n\n"
        "Ashwalker, the rag picker, watches from a distance, his attention caught by the exchange."
    ),
    "conversations": [{"npc_code": "A", "topic": "Do you often see what others don't?"}],
}
# The three paragraphs that each re-answered the remark.
TURN3_P = [
    "Aria tilts her head, a wry smile playing on her lips. \"I suppose that's a compliment,\" she says, "
    "her voice soft yet carrying a hint of amusement. \"But then again, these parts aren't exactly known "
    "for their variety.\" \"Maybe it's just that everyone else is too busy or too ordinary.\"",
    "Aria raises an eyebrow, her smile widening slightly. \"Peculiar, you say? Well, perhaps it's just "
    "that everyone else here is a bit too... predictable.\" She leans against a stone wall, her gaze "
    "flicking to a passing cart before returning to you. \"But then again, isn't everyone a bit peculiar "
    "in their own way?\"",
    "Aria leans away from the wall, her gaze steady and unsmiling. \"Predictable, huh? I suppose that's "
    "one way to look at it.\" She flicks a glance at a nearby carter, then back to you, her voice "
    "softening ever so slightly. \"But then again, isn't everyone just trying to find their own peculiar "
    "rhythm?\"",
]


def _briefs(player_input, draft, paragraphs=None):
    budget = plan_paragraph_budget(CONTEXT, player_input, CONFIG)
    if paragraphs:
        budget["paragraphs"] = paragraphs
        budget["beat_roles"] = ["establish", "act", "consequence", "pressure"][:paragraphs]
    ledger = NarrationLedger(turn=1, player_input=player_input, budget=budget)
    return build_paragraph_briefs(budget, CONTEXT, player_input, ledger, "move:Plains2", draft=draft)


class MayMentionTests(unittest.TestCase):
    def test_codes_come_with_name_and_kind(self):
        brief = _briefs("__opening_scene_request__: begin", OPENING_DRAFT)[0]
        rows = brief["may_mention"]
        self.assertTrue(rows)
        for row in rows:
            self.assertIsInstance(row, dict)
            self.assertTrue(row["code"] and row["name"] and row["kind"])
        by_code = {row["code"]: row for row in rows}
        # Playtest #35: the player's items ride only on beats that name them,
        # marked as the player's ("Well-Worn Boots" is not in this draft).
        self.assertNotIn("I1", by_code)
        named = entity_roster(CONTEXT, OPENING_DRAFT, player_input="I check my boots")
        boots = next(row for row in named if row["code"] == "I1")
        self.assertEqual(boots["name"], "Well-Worn Boots")
        self.assertEqual(boots["kind"], "carried by the player (you)")
        self.assertIn("place", by_code["L1"]["kind"])
        self.assertEqual(by_code["A"]["role"], "baker")

    def test_a_code_without_a_name_is_not_offered(self):
        codes = {row["code"] for row in entity_roster(CONTEXT)}
        self.assertNotIn("CAR", codes)


class DraftFactsTests(unittest.TestCase):
    def test_writer_gets_the_draft_and_who_is_who(self):
        briefs = _briefs("__opening_scene_request__: begin", OPENING_DRAFT)
        facts = briefs[0]["scene_facts"]
        cast = {row["name"]: row.get("role") for row in facts["cast"]}
        self.assertEqual(cast.get("Aria"), "baker")
        self.assertEqual(facts["where"], "The Back Lane")
        self.assertIn("Low Gate", briefs[0]["scene_draft"])
        spoken = facts["spoken"]
        self.assertEqual(spoken[0]["speaker"], "Aria")

    def test_slices_cover_the_draft_in_order(self):
        briefs = _briefs("__opening_scene_request__: begin", OPENING_DRAFT)
        slices = [b["draft_slice"] for b in briefs]
        joined = " ".join(s for s in slices if s)
        self.assertTrue(joined.startswith("You stand in the Back Lane"))
        self.assertIn("Welcome to Low Gate.\"", slices[-1])
        # No slice cuts a quotation in half.
        for piece in slices:
            self.assertEqual(piece.count('"') % 2, 0, piece)

    def test_ops_summary_no_longer_carries_the_prose_echo(self):
        brief = _briefs("__opening_scene_request__: begin", OPENING_DRAFT)[0]
        self.assertNotIn("summary:", brief["ops_summary"])

    def test_bystander_not_in_the_draft_is_not_a_must_cover(self):
        """Turn 3 beat 4 was told to stage 'NPC presence: Quillwatch', who was not in the scene."""
        for brief in _briefs(TURN3_INPUT, TURN3_DRAFT, paragraphs=4):
            for item in brief["must_cover"]:
                self.assertNotIn("Quillwatch", item)


class PlayerSpeechTests(unittest.TestCase):
    def test_player_quote_is_marked_as_the_players(self):
        quotes = player_quotes(TURN6_INPUT)
        self.assertEqual(len(quotes), 1)
        self.assertTrue(quotes[0].startswith("state your business"))
        brief = _briefs(TURN6_INPUT, TURN6_DRAFT)[0]
        self.assertEqual(brief["player_speech"][0]["speaker"], "player")
        self.assertEqual(brief["scene_facts"]["spoken"][0]["speaker"], "player")

    def test_engine_notes_after_the_input_are_not_player_words(self):
        quotes = player_quotes('i nod\n\nResolved: "not the player"')
        self.assertEqual(quotes, [])

    def test_only_one_beat_answers_and_later_beats_are_told_it_is_done(self):
        briefs = _briefs(TURN3_INPUT, TURN3_DRAFT, paragraphs=4)
        responders = [b for b in briefs if any(c.startswith("Respond to player intent") for c in b["must_cover"])]
        self.assertEqual(len(responders), 1)
        answer = responders[0]["beat_index"]
        for brief in briefs:
            if brief["beat_index"] > answer:
                self.assertIn("already given", brief["reply_status"])
                self.assertTrue(brief["player_intent"].startswith("Already answered"))
            else:
                self.assertNotIn("reply_status", brief)

    def test_npc_speaking_the_players_words_is_caught(self):
        quotes = player_quotes(TURN6_INPUT)
        self.assertTrue(player_words_misattributed(TURN6_P1, quotes))

    def test_player_speaking_their_own_words_is_fine(self):
        quotes = player_quotes(TURN6_INPUT)
        text = (
            "You fold your arms. \"State your business, if you came to intimidate, you came to the wrong "
            "place,\" you say, loud enough for the lane to hear. Aria steps back."
        )
        self.assertFalse(player_words_misattributed(text, quotes))

    def test_an_unrelated_npc_line_is_fine(self):
        quotes = player_quotes(TURN6_INPUT)
        text = "Aria narrows her eyes. \"I was looking for someone else, and I got a little lost.\""
        self.assertFalse(player_words_misattributed(text, quotes))


class RepeatTests(unittest.TestCase):
    # Turn 1 final prose, across the paragraph boundary.
    END_P1 = "You follow Aria [[A]], and the scent of ink grows stronger with each step."
    START_P2 = "You follow Aria [[A]] down the lane, the scent of ink growing stronger with each step."

    def test_reworded_sentence_across_paragraphs_is_dropped(self):
        kept, dropped = drop_repeated_sentences(
            [f"The morning sun slants through the gaps. {self.END_P1}", f"{self.START_P2} She leads you to a cluttered table."]
        )
        self.assertEqual(dropped, [self.START_P2])
        self.assertIn(self.END_P1, kept[0])
        self.assertEqual(kept[1], "She leads you to a cluttered table.")

    def test_reordered_words_count_too(self):
        self.assertTrue(
            is_near_restatement(
                "The scent of ink grows stronger with each step as you follow Aria down the lane.",
                self.START_P2,
            )
        )

    def test_same_people_and_place_doing_different_things_survive(self):
        paragraphs = [
            "Aria leans against the stone wall, her eyes on the street beyond the lane.",
            "Aria pushes away from the stone wall and steps out into the street.",
            "Ashwalker shoulders his sack and follows the street toward the gate.",
        ]
        kept, dropped = drop_repeated_sentences(paragraphs)
        self.assertEqual(dropped, [])
        self.assertEqual(kept, paragraphs)

    def test_a_reply_that_reanswers_the_same_remark_is_dropped(self):
        kept, dropped = drop_repeated_speech(list(TURN3_P))
        self.assertEqual(kept[0], TURN3_P[0], "the first answer stays whole")
        self.assertNotIn("everyone else here is a bit too", kept[1])
        self.assertNotIn("isn't everyone just trying", kept[2])
        self.assertEqual(len(dropped), 2)
        for para in kept:
            self.assertEqual(para.count('"') % 2, 0, f"unbalanced quotes left behind: {para}")
        # The narration around the dropped lines stays.
        self.assertIn("She leans against a stone wall", kept[1])
        self.assertIn("Predictable, huh?", kept[2])

    def test_everyday_shared_words_in_speech_are_not_a_repeat(self):
        paragraphs = [
            'Aria frowns. "I don\'t know what you mean by that, stranger."',
            'Ashwalker shrugs. "I don\'t know what you want from me here."',
        ]
        kept, dropped = drop_repeated_speech(paragraphs)
        self.assertEqual(dropped, [])
        self.assertEqual(kept, paragraphs)

    def test_lines_within_one_paragraph_are_not_compared(self):
        para = '"Bread, fresh this morning, two coins a loaf," she says. "Bread, fresh this morning, two coins a loaf!"'
        kept, dropped = drop_repeated_speech([para])
        self.assertEqual(dropped, [])


class PipelineTests(unittest.TestCase):
    def _run(self, player_input, draft, outputs, paragraphs=4):
        calls = []
        queue = list(outputs)

        def writer(brief, previous, ledger):
            calls.append({"brief": json.loads(json.dumps(brief)), "said": list(ledger.forbidden_repeats())})
            return queue.pop(0) if queue else "The lane holds its breath while a cart rattles past the far corner."

        context = dict(CONTEXT)
        with tempfile.TemporaryDirectory() as tmp, mock.patch(
            "app.narration_pipeline.plan_paragraph_budget",
            side_effect=lambda *a, **k: {
                **plan_paragraph_budget(*a, **k),
                "paragraphs": paragraphs,
                "beat_roles": ["establish", "act", "consequence", "pressure"][:paragraphs],
                "skip_consolidator": True,
            },
        ):
            out = run_narration_pipeline(
                context,
                player_input,
                config=CONFIG,
                turn_number=3,
                writer=writer,
                ledger_path=Path(tmp) / "ledger.json",
                draft=draft,
            )
        return out, calls

    def test_already_said_carries_spoken_lines(self):
        out, calls = self._run(TURN3_INPUT, TURN3_DRAFT, TURN3_P, paragraphs=3)
        second_said = calls[1]["said"]
        self.assertTrue(any("compliment" in s for s in second_said), second_said)
        self.assertTrue(any("everyone else is too busy" in s for s in second_said), second_said)

    def test_turn3_final_scene_answers_once(self):
        out, _ = self._run(TURN3_INPUT, TURN3_DRAFT, TURN3_P, paragraphs=3)
        text = out["narration"]
        self.assertEqual(text.count("But then again, isn't everyone"), 1, text)
        self.assertNotIn("everyone else here is a bit too", text)

    def test_misattributed_beat_is_rewritten_once(self):
        fixed = (
            "You fold your arms. \"State your business, if you came to intimidate, you came to the wrong "
            "place,\" you say. Aria's jaw tightens, and she takes one step back."
        )
        out, calls = self._run(TURN6_INPUT, TURN6_DRAFT, [TURN6_P1, fixed], paragraphs=2)
        self.assertIn("player's own", " ".join(calls[1]["brief"].get("rules_extra") or []))
        self.assertIn("you say", out["narration"])
        self.assertFalse(player_words_misattributed(out["narration"], player_quotes(TURN6_INPUT)))

    def test_misattributed_beat_that_stays_wrong_is_dropped(self):
        out, _ = self._run(TURN6_INPUT, TURN6_DRAFT, [TURN6_P1, TURN6_P1], paragraphs=2)
        self.assertFalse(player_words_misattributed(out["narration"], player_quotes(TURN6_INPUT)))


class CodeExpansionTests(unittest.TestCase):
    CMAP = {"I1": "Well-Worn Boots", "A": "Aria", "L1": "The Back Lane"}

    def test_item_code_on_an_invented_place_is_dropped(self):
        prose = "Aria gestures down the lane toward the Inkwell Inn [[I1]]. \"This way,\" she says."
        out = llm._repair_prose_entity_labels(prose, self.CMAP)
        self.assertNotIn("Well-Worn Boots", out)
        self.assertNotIn("[[I1]]", out)
        self.assertIn("toward the Inkwell Inn.", out)

    def test_lowercase_other_noun_also_drops(self):
        out = llm._repair_prose_entity_labels("She points at the old inn [[I1]] across the way.", self.CMAP)
        self.assertNotIn("Well-Worn Boots", out)
        self.assertIn("the old inn across the way", out)

    def test_bare_code_after_glue_still_expands(self):
        out = llm._repair_prose_entity_labels("Aria hands you [[I1]] without a word.", self.CMAP)
        self.assertIn("hands you Well-Worn Boots [[I1]]", out)

    def test_code_after_part_of_its_own_name_is_kept_as_is(self):
        out = llm._repair_prose_entity_labels("You tighten the boots [[I1]] and stand.", self.CMAP)
        self.assertIn("the boots [[I1]]", out)
        self.assertNotIn("Well-Worn Boots", out)

    def test_role_before_a_person_code_still_expands(self):
        out = llm._repair_prose_entity_labels("You nod to the baker [[A]] and wait.", self.CMAP)
        self.assertIn("the baker Aria [[A]]", out)

    def test_wrong_proper_name_on_a_person_code_is_dropped(self):
        out = llm._repair_prose_entity_labels("Quillwatch [[A]] shifts his weight.", self.CMAP)
        self.assertNotIn("Aria", out)
        self.assertIn("Quillwatch shifts his weight.", out)

    def test_the_turn1_sentence_end_to_end(self):
        turn = {
            "narration": (
                "Aria [[A]], the young cartographer with a map tucked under her arm, gestures down the "
                "lane toward the Inkwell Inn [[I1]]. \"This way,\" she says, her voice a soft whisper."
            ),
            "npcs": [],
        }
        out = llm._repair_entity_names_in_turn(turn, CONTEXT)
        self.assertNotIn("Inkwell Inn Well-Worn Boots", out["narration"])
        self.assertNotIn("[[I1]]", out["narration"])


class WriterPromptTests(unittest.TestCase):
    def test_writer_is_told_the_rules_and_gets_the_facts(self):
        captured = {}

        def fake_chat(system, user, **kwargs):
            captured["system"] = system
            captured["payload"] = json.loads(user)
            return "Aria folds her arms and studies you for a long moment before she answers."

        brief = _briefs(TURN3_INPUT, TURN3_DRAFT, paragraphs=4)[-1]
        ledger = NarrationLedger(turn=3, player_input=TURN3_INPUT, budget={})
        ledger.add_said_fact('"I suppose that\'s a compliment"', 0)
        with mock.patch.object(llm, "_chat_text", side_effect=fake_chat), mock.patch.object(
            llm, "_narration_sample_cover", return_value=(None, None)
        ):
            writer = llm._make_pipeline_paragraph_writer([], None, 60, CONTEXT)
            writer(brief, "", ledger)
        system = captured["system"]
        self.assertIn("Never add a named place", system)
        self.assertIn("player_speech", system)
        payload = captured["payload"]
        self.assertIn(brief["reply_status"], payload["rules"])
        self.assertIn('"I suppose that\'s a compliment"', payload["already_said"])
        self.assertIn("scene_facts", payload["brief"])
        # The system prompt names no one: examples get pasted verbatim.
        for name in ("Aria", "Quillwatch", "Ashwalker", "Inkwell"):
            self.assertNotIn(name, system)


if __name__ == "__main__":
    unittest.main()
