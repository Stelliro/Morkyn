"""
The repeat-word filter hides content words used more than WORD_REPEAT_CAP
times in recent scenes. Names are exempt. Power names (abilities, skills,
proficiencies, NPC and item abilities) were not, so a power used often had
its name's words hidden from the sampler mid-game.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.narration_pipeline import (  # noqa: E402
    WORD_REPEAT_CAP,
    count_content_words,
    narration_keep_words,
    words_past_cap,
)

CONTEXT = {
    "player": {"name": "Harrow Ames"},
    "abilities": [
        {"code": "AB1", "name": "Luminous Veil"},
        {"code": "AB2", "name": "Whispering Fates"},
    ],
    "skills": [{"name": "Lockcraft", "rank": "F"}],
    "npcs": [{"name": "Aria", "role": "baker", "abilities": [{"name": "Ember Tongue"}]}],
    "inventory": [{"name": "Small, Enchanted Lantern", "granted_abilities": ["Steady Glow"]}],
}


class TestPowerNamesAreNeverHidden(unittest.TestCase):
    def test_power_names_are_keep_words(self):
        names, _titles = narration_keep_words(CONTEXT)
        for word in ("whispering", "fates", "luminous", "veil", "lockcraft", "ember", "tongue", "steady", "glow"):
            self.assertIn(word, names)

    def test_a_power_used_every_scene_stays_writable(self):
        scene = "You call on Whispering Fates and the Luminous Veil shimmers; the street goes quiet."
        texts = [scene] * (WORD_REPEAT_CAP + 2)
        names, titles = narration_keep_words(CONTEXT)
        hidden = words_past_cap(count_content_words(texts), names=names, titles=titles)
        for word in ("whispering", "fates", "luminous", "veil"):
            self.assertNotIn(word, hidden)
        # Ordinary overused words are still hidden.
        self.assertIn("shimmers", hidden)

    def test_a_turn_that_gains_or_changes_a_power_keeps_its_name(self):
        result = {"ability_updates": [{"name": "Mystic Echoes"}], "skill_changes": [{"skill": "Rope Splicing"}]}
        names, _titles = narration_keep_words({}, result)
        for word in ("mystic", "echoes", "rope", "splicing"):
            self.assertIn(word, names)

    def test_odd_shapes_are_ignored(self):
        names, _titles = narration_keep_words({"abilities": "not a list", "skills": [None, 3, {"rank": "F"}]})
        self.assertEqual(names, set())


if __name__ == "__main__":
    unittest.main()
