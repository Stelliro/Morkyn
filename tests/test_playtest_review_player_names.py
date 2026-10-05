"""Review of playtest #21/#26: no fixed list names the player character.

Two saves running were "Miriam Shaw". The pools fix drew fresh name_options
for the model, but three paths still picked from a fixed 20-name list that
holds "Miriam Shaw":

  * app/llm.py _sanitize_player_name: a nickname, or a re-roll that came back
    with the unchanged name, was replaced from SETUP_RANDOMIZER_FALLBACKS;
  * static/app.js RANDOM_SETUP.player_name: the page's own fallback whenever
    the roll failed, came back blank (Simple mode), or was a nickname;
  * the group (identity) roll had no name_options or avoid_names at all, and
    nothing kept a recent game's character name from coming back.
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-review-player-names-"))
os.environ.update(isolated_data_env(str(_TMP)))

from app import db, example_pools, llm  # noqa: E402
from app.db import connect  # noqa: E402
from app.main import NameDrawRequest, api_setup_name_draw  # noqa: E402

FIXED = set(llm.SETUP_RANDOMIZER_FALLBACKS["player_name"])
SETUP = {"world_style": "misty frontier fantasy", "tech_level": "medieval", "player_sex": "female"}


def setUpModule():
    os.environ.update(isolated_data_env(str(_TMP)))
    db.init_db()
    with connect() as conn:
        example_pools.remember_player_name(conn, "Miriam Shaw")


def _pool(culture: str = "common") -> set[str]:
    return set(example_pools._NAMES[culture]["female"]) | set(example_pools._NAMES[culture]["male"])


def _given(name: str) -> str:
    return name.split(" ")[0]


class TheReplacementNameIsDrawn(unittest.TestCase):
    def test_a_nickname_is_replaced_by_a_drawn_name(self):
        for _ in range(20):
            name = llm._sanitize_player_name("The Silent Blade", setup=SETUP)
            self.assertNotIn(name, FIXED)
            self.assertIn(_given(name), _pool())
            self.assertNotEqual(name, "Miriam Shaw")

    def test_an_unchanged_reroll_is_replaced_by_a_drawn_name(self):
        current = dict(SETUP, player_name="Agnes Thorne")
        replies = iter([{"player_name": "Agnes Thorne"}, {"player_name": "Agnes Thorne"}])
        original = llm._chat_json
        llm._chat_json = lambda *a, **k: next(replies)
        try:
            out = llm.generate_setup_randomization("field:player_name", current)
        finally:
            llm._chat_json = original
        self.assertNotEqual(out["player_name"], "Agnes Thorne")
        self.assertNotIn(out["player_name"], FIXED)
        self.assertIn(_given(out["player_name"]), _pool())

    def test_a_recent_games_character_is_not_handed_back(self):
        out = llm._cohere_identity_fields(dict(SETUP), {"player_name": "Miriam Shaw"})
        self.assertNotEqual(out["player_name"], "Miriam Shaw")
        self.assertIn(_given(out["player_name"]), _pool())

    def test_a_locked_name_is_left_alone(self):
        out = llm._cohere_identity_fields(dict(SETUP), {"player_name": "Miriam Shaw"}, {"player_name"})
        self.assertEqual(out["player_name"], "Miriam Shaw")

    def test_the_group_roll_carries_drawn_options_and_names_to_avoid(self):
        contracts = llm._field_contracts_for_prompt(["player_name"], dict(SETUP), set())
        entry = contracts["player_name"]
        self.assertTrue(3 <= len(entry["name_options"]) <= 5, entry)
        self.assertIn("Miriam Shaw", entry["avoid_names"])
        self.assertFalse(set(entry["name_options"]) & FIXED)


class ThePageAsksTheServer(unittest.TestCase):
    def test_the_name_draw_route(self):
        seen = set()
        for _ in range(8):
            got = api_setup_name_draw(NameDrawRequest(**dict(SETUP, world_style="feudal japan samurai village")))
            name = got["name"]
            self.assertTrue(name)
            self.assertNotIn(name, FIXED)
            self.assertTrue(set(name.split(" ")) & _pool("japanese"), name)
            seen.add(name)
        self.assertGreater(len(seen), 4)

    def test_the_page_has_no_fixed_player_name_list(self):
        source = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        start = source.index("const RANDOM_SETUP = {")
        block = source[start:source.index("};", start)]
        self.assertNotIn("player_name:", block)
        self.assertNotIn("Miriam Shaw", source)
        self.assertIn("/api/setup/name-draw", source)


if __name__ == "__main__":
    unittest.main()
