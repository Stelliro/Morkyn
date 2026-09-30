"""The game counts content words and drops the ones that pile up."""

from __future__ import annotations

import unittest

from app.narration_pipeline import (
    WORD_REPEAT_CAP,
    count_content_words,
    narration_keep_words,
    words_past_cap,
)


class WordCountTests(unittest.TestCase):
    def test_glue_letters_and_numbers_are_not_counted(self):
        counts = count_content_words(
            ["The hooded man and a dog. L1 stays. A 3 sits. Hooded again."]
        )
        self.assertEqual(counts.get("hooded"), 2)
        self.assertNotIn("the", counts)
        self.assertNotIn("and", counts)
        self.assertNotIn("a", counts)

    def test_a_word_past_the_cap_is_listed_for_the_middle(self):
        counts = count_content_words(
            ["The hooded baker saw a hooded cart, a hooded door, and a hooded sign."]
        )
        names, titles = narration_keep_words(
            {"npcs": [{"name": "Mara", "role": "baker"}], "current_location": {"name": "Low Gate"}},
        )
        self.assertGreater(counts["hooded"], WORD_REPEAT_CAP)
        self.assertEqual(counts["baker"], 1)
        self.assertIn("hooded", words_past_cap(counts, names=names, titles=titles))
        self.assertNotIn("baker", words_past_cap({"baker": 8, "hooded": 8}, names=names, titles=titles))

    def test_a_known_name_is_never_on_the_list(self):
        names, titles = narration_keep_words({"npcs": [{"name": "Mara", "role": "baker"}]})
        blocked = words_past_cap({"mara": 9, "hooded": 4}, names=names, titles=titles)
        self.assertEqual(blocked, ["hooded"])

    def test_a_title_can_pass_the_cap_and_stay_off_the_list(self):
        names, titles = narration_keep_words({"npcs": [{"name": "Mara", "role": "baker"}]})
        self.assertEqual(count_content_words(["baker baker baker baker"])["baker"], 4)
        self.assertEqual(words_past_cap({"baker": 4}, names=names, titles=titles), [])


if __name__ == "__main__":
    unittest.main()
