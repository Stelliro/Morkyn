import unittest

from app.ask import accept_memory, ask_voice, resolve_subject
from app.world import _ask_relevant_to_input


class AskGateTests(unittest.TestCase):
    def test_hypothetical_is_not_stored(self):
        remember, edit = accept_memory(
            "what if the shoes were cursed?",
            "Worn leather shoes.",
            "They are secretly cursed.",
            "They are cursed.",
        )
        self.assertEqual(remember, "")
        self.assertEqual(edit, "")

    def test_plain_note_can_be_stored(self):
        remember, edit = accept_memory(
            "what are the non-slip shoes?",
            "Black rubber soles.",
            "The soles are scuffed at the toe.",
            "",
        )
        self.assertIn("scuffed", remember)
        self.assertEqual(edit, "")

    def test_plot_word_is_dropped_unless_already_known(self):
        remember, _edit = accept_memory(
            "what is the key?",
            "A small brass key.",
            "It is an ancient key to a portal.",
            "",
        )
        self.assertEqual(remember, "")

    def test_edit_only_when_the_player_asks_to_change_it(self):
        _remember, refused = accept_memory("what is the coat?", "A grey coat.", "", "A blue coat.")
        self.assertEqual(refused, "")
        _remember, allowed = accept_memory(
            "change the description, call it a grey travel coat",
            "A grey coat.",
            "",
            "A grey travel coat, hem worn thin.",
        )
        self.assertIn("travel coat", allowed)

    def test_first_name_resolves_one_record(self):
        context = {
            "locations": [{"code": "L1", "name": "Low Gate", "npcs": [{"code": "C", "name": "Marta Venn"}]}],
            "inventory": [{"code": "I2", "name": "non-slip shoes", "description": "Black soles."}],
            "events": [],
            "aliases": [],
            "settings": {},
        }
        item = resolve_subject(context, "what are the non-slip shoes?")
        self.assertEqual(item["code"], "I2")
        person = resolve_subject(context, "what is marta wearing?")
        self.assertEqual(person["code"], "C")

    def test_lookup_is_out_of_character_until_they_speak_to_someone(self):
        subject = {"kind": "I", "name": "non-slip shoes", "code": "I2"}
        self.assertEqual(ask_voice("what are the non-slip shoes?", subject), "ooc")
        self.assertEqual(ask_voice("I ask her what she is holding", {"kind": "C", "name": "Marta", "code": "C"}), "scene")

    def test_next_turn_sees_an_ask_only_when_it_names_that_thing(self):
        note = "Q: what are the non-slip shoes?\nA: Black soles."
        self.assertTrue(_ask_relevant_to_input(note, "i look at the non-slip shoes again"))
        self.assertFalse(_ask_relevant_to_input(note, "i walk north"))


if __name__ == "__main__":
    unittest.main()
