"""Review of playtest #26: the single-field asks still named fixed samples.

FIELD_CONTRACTS lost its "examples" lists, but the per-field notes in
app/llm.py kept their own: hair "(e.g. messy copper curls, cropped black hair,
white undercut)" beside an engine-rolled colour, appearance "'torso: travel
coat; feet: dusty boots'", world_races "(e.g. human; human, elf, beastfolk)",
world_style "(e.g. modern isekai coastal fantasy)" and a starter_equipment
list of banned and allowed items. And a rolled value the model replaced with
its own was put beside it ("auburn hair, long black curls").
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-review-prompt-examples-"))
os.environ.update(isolated_data_env(str(_TMP)))

from app import db, llm  # noqa: E402
from app.example_pools import apply_rolled_values  # noqa: E402

SETUP = {"world_style": "misty frontier fantasy", "tech_level": "medieval", "player_sex": "female"}
FIXED_SAMPLES = (
    "messy copper curls", "cropped black hair", "white undercut", "travel coat", "dusty boots",
    "human, elf, beastfolk", "modern isekai coastal fantasy", "rusted wrench", "copper coins",
    "rain-slicked hoodie", "scuffed sneakers", "transit card",
)


def setUpModule():
    db.init_db()


def _prompt(field: str) -> str:
    captured = {}

    def fake_chat(system, user, **kwargs):
        captured.setdefault("user", user)
        raise RuntimeError("stop after prompt build")

    original = llm._chat_json
    llm._chat_json = fake_chat
    try:
        llm.generate_setup_randomization(f"field:{field}", dict(SETUP))
    except Exception:
        pass
    finally:
        llm._chat_json = original
    return captured.get("user", "")


class NoFixedSamplesInTheAsks(unittest.TestCase):
    def test_the_field_asks_name_no_fixed_samples(self):
        for field in ("hair", "appearance", "world_races", "world_style", "starter_equipment"):
            note = json.loads(_prompt(field)).get("field_note", "")
            self.assertTrue(note, field)
            for sample in FIXED_SAMPLES:
                self.assertNotIn(sample, note, f"{field}: {sample}")

    def test_the_hair_ask_points_at_the_rolled_values(self):
        prompt = json.loads(_prompt("hair"))
        self.assertIn("engine_rolled", prompt)
        self.assertIn("engine_rolled", prompt["field_note"])


class RolledValuesReplaceTheModelsOwn(unittest.TestCase):
    def test_a_different_hair_colour_and_length_are_swapped(self):
        out = apply_rolled_values("hair", "short black curls", {"hair_colour": "auburn", "hair_length": "long"})
        self.assertEqual(out, "long auburn curls")

    def test_a_missing_value_is_still_added(self):
        out = apply_rolled_values("hair", "loose braid", {"hair_colour": "auburn", "hair_length": "long"})
        self.assertEqual(out, "long auburn hair, loose braid")

    def test_long_is_enforced(self):
        out = apply_rolled_values("hair", "auburn braid", {"hair_colour": "auburn", "hair_length": "long"})
        self.assertEqual(out, "long auburn braid")

    def test_a_different_eye_colour_is_swapped_and_other_colours_stay(self):
        out = apply_rolled_values(
            "facial_features", "brown eyes, brown freckles", {"eye_colour": "grey", "notable_mark": "none"}
        )
        self.assertEqual(out, "grey eyes, brown freckles")


if __name__ == "__main__":
    unittest.main()
