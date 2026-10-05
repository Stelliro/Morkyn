"""Review of playtest #22: Start settles custom_skills, not only the setup roll.

Game 2's saved form, started offline, still put "master the dance of shadows
(E), learn from the ancients (C), forge unbreakable bonds (D)" into the game
for an idea that asks to start ordinary with one weak compounding seed: the
settle ran only on a fresh roll, and the post-start pass needs a model.
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-review-start-settle-"))
os.environ.update(isolated_data_env(str(_TMP)))
os.environ.update({"AI_RPG_POST_START_MODEL": "off"})

from app import db, world  # noqa: E402
from app.db import connect  # noqa: E402

SLOGANS = "master the dance of shadows (E), learn from the ancients (C), forge unbreakable bonds (D)"
IDEA = (
    "Overpowered progression in any setting: start ordinary with one weak compounding seed power that "
    "snowballs toward late-game OP (rank F up through S/SS/SSS)."
)


def _start(locks: list[str]) -> tuple[str, list[str], dict]:
    db.init_db()
    world.start_playthrough(
        {
            "player_name": "Wenna Tull",
            "start_location": "Eldoria's Edge",
            "special_ability_origin": "none",
            "rank_scale": "F,E,D,C,B,A,S,SS,SSS",
            "custom_skills": SLOGANS,
            "setup_form": {"randomize_idea": IDEA, "locks": locks},
        }
    )
    with connect() as conn:
        options = json.loads(conn.execute("SELECT value FROM settings WHERE key = 'playthrough_options'").fetchone()[0])
        notes = json.loads(conn.execute("SELECT value FROM settings WHERE key = 'setup_coherence'").fetchone()[0])
    return options["custom_skills"], notes, options


class StartSettlesCustomSkills(unittest.TestCase):
    def test_game2_slogans_become_a_noun_at_the_bottom_rank(self):
        text, notes, options = _start([])
        self.assertNotIn("master the", text)
        self.assertIn("Dance of Shadows (F)", text)
        for rank in ("(E)", "(D)", "(C)"):
            self.assertNotIn(rank, text)
        # No model at Start: a phrase the engine cannot name is kept, rank
        # capped, for the post-start pass; nothing the player wrote is lost.
        self.assertIn("learn from the ancients (F)", text)
        self.assertEqual(options["custom_skills_setup"], SLOGANS)
        self.assertTrue(any("custom_skills settled at Start" in note for note in notes), notes)

    def test_a_locked_field_is_kept_as_written(self):
        text, _notes, options = _start(["custom_skills"])
        self.assertEqual(text, SLOGANS)
        self.assertNotIn("custom_skills_setup", options)


if __name__ == "__main__":
    unittest.main()
