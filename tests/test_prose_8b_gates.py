"""8B prose issues #44, #47, #59, #86 and the reopened #97 and #78.

The fixes keep the model's prose and only cut or re-break the exact bad
shape, or state a fact the model was missing (CLAUDE.md: middle ground,
never limit the LLM).
"""

import unittest
from unittest import mock

from app import llm
from app.conversation import wrote_player_name
from app.narration_pipeline import drop_invented_player_speech
from app.turn_dsl import build_dsl_user_prompt, facts_to_keep


# Live game 83a1ec4c, T6 (dev.8): the player only asked who the blacksmith was.
T6_INPUT = "who is the blacksmith here? im looking for some work aside from adventuring."
T6_PROSE = (
    "You step into the Lucky Heron Armory, where the smell of leather and metal fills the air. Finnian [[C]], "
    "the armorer, looks up from his work and gives you a nod. \"Looking for some work, are you?\" he asks, his "
    "eyes narrowing slightly as he examines you.\n\n"
    "\"Exactly,\" you reply, feeling your resolute expression set. \"I've been adventuring, but I'm ready to "
    "settle down and make something of myself. Maybe you could use an apprentice?\"\n\n"
    "Finnian [[C]] grins, a hint of a smile playing on his lips. \"We could use an extra pair of hands, but I'm "
    "not sure I can afford an apprentice just yet. I'm working on a custom set of armor for a local knight. If you "
    "want to help, we can talk about it.\"\n\n"
    "You nod, appreciating the opportunity. \"I can start small and work my way up. I've learned a bit about "
    "metalworking, and I'm eager to learn more.\""
)


def _run_light_dsl_turn(narration: str, player_input: str, context: dict | None = None) -> dict:
    draft = {
        "narration": narration,
        "narration_segments": [{"label": "paragraph", "text": p} for p in narration.split("\n\n")],
        "self_check": {"corrections_made": []},
    }
    noop = lambda *a, **k: None  # noqa: E731
    with mock.patch.object(llm, "_try_dsl_draft", return_value=draft), mock.patch.object(
        llm, "_verification_policy", return_value={"mode": "skip_model_verifier"}
    ), mock.patch.object(llm, "_ensure_narration_quality", side_effect=AssertionError("no model pass on a light question")):
        return llm._generate_turn_body(
            context or {"player": {"name": "Ash"}},
            player_input,
            usage=[],
            trace=[],
            timeout=30,
            verify_timeout=30,
            config={},
            system_prompt="",
            verify_prompt="",
            progress_update=noop,
            progress_preview=noop,
            progress_end=noop,
            progress_fail=noop,
        )


class LightQuestionStillRunsEngineGates(unittest.TestCase):
    """#47 and #86: a light question skipped every engine gate with the model pass."""

    def test_invented_player_lines_go_on_a_question_turn(self):
        self.assertTrue(llm._is_light_question(T6_INPUT))
        out = _run_light_dsl_turn(T6_PROSE, T6_INPUT)
        text = out["narration"]
        self.assertNotIn("Exactly", text)
        self.assertNotIn("apprentice?\"", text.split("Finnian")[0])
        self.assertNotIn("I've learned a bit about metalworking", text)
        # The world's side stays.
        self.assertIn("Looking for some work, are you?", text)

    def test_wall_of_text_is_broken_into_paragraphs(self):
        wall = (
            "The innkeeper sets down the jug and leans on the counter, thinking it over for a long moment while the "
            "fire crackles behind him and a pair of drovers argue about the price of wool by the window. "
            "\"The old mill?\" he says at last. \"Nobody's worked it since the flood took the wheel, and the miller's "
            "boy went south to the city with what was left of the money.\" He wipes a ring of ale off the wood. "
            "\"If you want to see it, follow the river path past the ford until you hear the water over the weir, "
            "then cut up through the alders. Watch the bank there; it gives way.\" One of the drovers laughs at "
            "something and the innkeeper glances over, then back at you, and lowers his voice so only you hear it. "
            "\"Folk say there's lights in it some nights. I'd not go after dark.\""
        )
        self.assertGreater(len(wall), 600)
        out = _run_light_dsl_turn(wall, "where is the old mill?")
        paragraphs = [p for p in out["narration"].split("\n\n") if p.strip()]
        self.assertGreaterEqual(len(paragraphs), 2)
        self.assertEqual(" ".join(out["narration"].split()), " ".join(wall.split()))

    def test_recap_of_the_question_goes(self):
        prose = (
            "You ask the innkeeper where the old mill lies and whether anyone still works the mill. "
            "He scratches his jaw. \"Nobody's worked it since the flood took the wheel. Follow the river path past "
            "the ford until you hear the weir, then cut up through the alders. Mind the bank; it gives way under "
            "anyone heavier than a child.\""
        )
        out = llm._drop_question_recap({"narration": prose}, "where is the old mill? does anyone still work the mill?", "t", [])
        self.assertTrue(out["narration"].startswith("He scratches his jaw."))

    def test_a_question_that_is_not_retold_stays(self):
        prose = (
            "You ask about the weather. He scratches his jaw. \"Nobody's worked the mill since the flood took the "
            "wheel. Follow the river path past the ford until you hear the weir, then cut up through the alders.\""
        )
        out = llm._drop_question_recap({"narration": prose}, "where is the old mill?", "t", [])
        self.assertEqual(out["narration"], prose)


class SameSpeakerRepeatOnAQuestionTurn(unittest.TestCase):
    """#78 reopened (7B Saltmarrow T22): Helewise's T21 line came back word for word."""

    def test_repeat_is_cut_on_the_light_path(self):
        line = (
            "The Starlight was last seen heading to the Outer Isles. It was a common sight on these roads, but I "
            "never heard a word of it since."
        )
        context = {
            "player": {"name": "Isk"},
            "speech_memory": {
                "recent": [{"code": "H", "line": line, "unit": f"Helewise Pennick [[H]]: \"{line}\""}],
                "people": [{"code": "H", "name": "Helewise Pennick", "here": True}],
                "player_names": [],
                "knows_name": [],
            },
        }
        prose = (
            "The captain's journal lies open on your knees, the ink of its last page faded to brown.\n\n"
            f"Helewise Pennick [[H]] shakes her head. \"{line}\"\n\n"
            "She shifts her weight, as if preparing to walk away."
        )
        out = _run_light_dsl_turn(prose, "Helewise, do you know whose ship the Starlight was?", context)
        self.assertNotIn("common sight on these roads", out["narration"])
        self.assertIn("captain's journal", out["narration"])


class WritingTheNameDownTeachesIt(unittest.TestCase):
    """#78 reopened (7B Saltmarrow T18 -> T86)."""

    ROWS = [{"code": "G", "name": "Ellen Radley", "aliases": []}, {"code": "H", "name": "Hargrave", "aliases": []}]

    def test_the_writer_knows_the_name(self):
        prose = "Ellen Radley [[G]] scribbles your name in her notebook and looks up with a nod. Hargrave watches."
        self.assertEqual(wrote_player_name(prose, self.ROWS), ["G"])

    def test_a_name_said_in_a_quote_is_not_writing(self):
        prose = "Hargrave grins. \"Ellen writes your name in the book when you sign,\" he says."
        self.assertEqual(wrote_player_name(prose, self.ROWS), [])


class PlayerActsTheLineDidNotChoose(unittest.TestCase):
    """#97 reopened (7B Saltmarrow T26, T72, T81)."""

    def _dropped(self, prose, line):
        return llm.drop_invented_player_acts_text(prose, line)[1]

    def test_unasked_work_goes(self):
        line = "I don't wait. I go down to Saltmarrow Dock myself to find old Hargrave and his boat."
        prose = "Hargrave nods at the nets. You assist Hargrave in mending his net, the task taking a few moments."
        self.assertEqual(self._dropped(prose, line), ["You assist Hargrave in mending his net, the task taking a few moments."])

    def test_asked_work_stays(self):
        line = "I help Hargrave mend his net."
        prose = "You help Hargrave with the net, working the twine through the torn mesh."
        self.assertEqual(self._dropped(prose, line), [])

    def test_working_another_thing_goes(self):
        line = (
            "I push the lantern into the tight passage first to see how far it goes, then squeeze through after it "
            "on my side, toward where the whisper came from."
        )
        prose = (
            "You push the lantern into the passage, testing the way. You push the door open, and the whisper stops "
            "abruptly. You open the journal, the pages yellowed."
        )
        dropped = self._dropped(prose, line)
        self.assertIn("You push the door open, and the whisper stops abruptly.", dropped)
        self.assertIn("You open the journal, the pages yellowed.", dropped)
        self.assertNotIn("You push the lantern into the passage, testing the way.", dropped)

    def test_walking_back_is_a_second_journey(self):
        line = "\"The mines. Then that's where I go.\" I ask Tilda the way to the salt mines, and set off there."
        prose = "You set off down the road toward the hills. You return to Saltmarrow as the sun sinks."
        self.assertEqual(self._dropped(prose, line), ["You return to Saltmarrow as the sun sinks."])

    def test_going_back_when_asked_stays(self):
        line = "I head back to Saltmarrow before dark."
        prose = "You return to Saltmarrow as the sun sinks."
        self.assertEqual(self._dropped(prose, line), [])

    def test_a_whisper_in_the_line_is_not_the_player_speaking(self):
        line = "I squeeze through the passage toward where the whisper came from."
        prose = ["The door ahead stands ajar. \"What's in there?\" you ask, your voice barely above a whisper."]
        _kept, dropped = drop_invented_player_speech(prose, line)
        self.assertEqual(len(dropped), 1)

    def test_asking_without_words_still_lets_the_prose_voice_it(self):
        line = "I ask him about the docks."
        prose = ["\"What about the docks?\" you ask."]
        _kept, dropped = drop_invented_player_speech(prose, line)
        self.assertEqual(dropped, [])


class StockLine(unittest.TestCase):
    """#44: the stock 'not the first ... may be the last' flourish."""

    def test_flourish_goes_and_the_point_stays(self):
        cases = {
            "\"You're not the first to follow that path, but you may be the last.\"":
                "\"You're not the first to follow that path.\"",
            "\"You're not the first to come looking. But you may be the last.\"":
                "\"You're not the first to come looking.\"",
        }
        for before, after in cases.items():
            out = llm._soften_stock_lines({"narration": before, "narration_segments": [{"text": before}]})
            self.assertEqual(out["narration"], after)
            self.assertEqual(out["narration_segments"][0]["text"], after)

    def test_other_firsts_stay(self):
        text = "\"You're not the first to ask me that today.\""
        self.assertEqual(llm._soften_stock_lines({"narration": text})["narration"], text)


class FactsToKeep(unittest.TestCase):
    """#59: the hour and the shops' hours as facts in the packet."""

    CONTEXT = {
        "world_time": {"day": 1, "hour": 8, "minute_of_hour": 35, "part_of_day": "morning"},
        "movement_contract": {
            "town": {
                "places_here": [
                    {"name": "Lucky Ox Outfitters", "kind": "general store", "where": "here", "open": True},
                    {"name": "", "kind": "bakery", "where": "a few steps south", "open": False, "hours": "05:00-13:00"},
                    {"name": "Old Well", "kind": "well", "where": "a few steps east"},
                ]
            }
        },
    }

    def test_facts(self):
        facts = facts_to_keep(self.CONTEXT)
        self.assertEqual(facts[0], "It is morning, 08:35.")
        self.assertIn("Lucky Ox Outfitters (here) is open.", facts)
        self.assertIn("The bakery (a few steps south) is closed; its hours are 05:00-13:00.", facts)
        self.assertFalse(any("Old Well" in f for f in facts))

    def test_in_the_dsl_packet(self):
        import json

        packet = json.loads(build_dsl_user_prompt(dict(self.CONTEXT), "I look around the street."))
        self.assertEqual(packet["facts_to_keep"][0], "It is morning, 08:35.")
        self.assertTrue(any("facts_to_keep" in line for line in packet.get("instructions") or []), packet.keys())


if __name__ == "__main__":
    unittest.main()
