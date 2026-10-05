"""Review of playtest #14/#26: names the engine makes itself come from the world's pools.

The pools fix covered the draft's cast_options and the setup rolls, but every
NPC the engine names on its own (shell crowd faces, a settlement's ruler and
local cast, a repaired garbage name) still came from one 20x20 compound list
("Saltbin", "Hearthbin" in game 2) that is the same in every world and never
read name_ledger. A single unsexed draw was also always a woman's name.
"""

from __future__ import annotations

import os
import random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-review-names-"))
os.environ.update(isolated_data_env(str(_TMP)))

from app import db, example_pools, world  # noqa: E402
from app.db import connect  # noqa: E402


def _start(style: str, player: str = "Hana Sato") -> None:
    db.init_db()
    world.start_playthrough(
        {
            "player_name": player,
            "world_style": style,
            "start_location": "Kiso Village",
            "special_ability_origin": "none",
        }
    )


class EngineNamesComeFromThePools(unittest.TestCase):
    def test_shell_npcs_take_this_worlds_names_and_skip_the_ledger(self):
        _start("feudal japan samurai village")
        with connect() as conn:
            conn.execute(
                "INSERT INTO name_ledger (subject, name, source, turn) VALUES ('npc:X', 'Takeshi Mori', 'test', 0)"
            )
            names = [world.create_shell_npc(conn, 1, role="villager", seed=i)["name"] for i in range(20)]
        japanese = set(example_pools._NAMES["japanese"]["female"]) | set(example_pools._NAMES["japanese"]["male"])
        self.assertEqual(len(names), len(set(names)), names)
        self.assertTrue(all(name in japanese for name in names), names)
        self.assertNotIn("Takeshi", names)
        self.assertNotIn("Hana", names)
        compound = tuple(world._SHELL_NAME_PARTS_A)
        self.assertFalse(any(name.startswith(compound) for name in names), names)

    def test_the_same_seed_and_world_give_the_same_name(self):
        _start("misty frontier fantasy")
        with connect() as conn:
            first = world.unique_person_name(conn, 4242)
            second = world.unique_person_name(conn, 4242)
        self.assertEqual(first, second)

    def test_a_single_unsexed_draw_is_not_always_female(self):
        ctx = example_pools.world_context({"world_style": "misty frontier fantasy"})
        female = set(example_pools._given_names(ctx["culture"], "female"))
        picks = [example_pools.draw_names(ctx, 1, random.Random(seed), family=False)[0] for seed in range(60)]
        women = sum(1 for name in picks if name in female)
        self.assertGreater(women, 10, picks)
        self.assertLess(women, 50, picks)


if __name__ == "__main__":
    unittest.main()
