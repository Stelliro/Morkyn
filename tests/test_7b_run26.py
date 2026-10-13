"""7B run 26 (Qwen2.5 7B on MLE, agent as player): an offered job's pay reaches the narrator."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-7b-run26-"))
_ENV = isolated_data_env(str(_TMP))
_SAVED_ENV: dict[str, str | None] = {}


def setUpModule():
    _SAVED_ENV.update({key: os.environ.get(key) for key in _ENV})
    os.environ.update(_ENV)


def tearDownModule():
    for key, value in _SAVED_ENV.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


class OfferPaysReachesThePacket(unittest.TestCase):
    """T2: "What does it pay?" got "I see" - open_offers carried no sum."""

    def test_list_and_view(self):
        from app import world
        from app.db import connect, init_db
        from app.local_intel import list_open_offers

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        with connect() as conn:
            conn.execute(
                "INSERT INTO quests (code, title, description, status, reward_gold) VALUES ('Q1', 'Tailoring a coat', '', 'offered', 11)"
            )
        offers = list_open_offers()
        self.assertEqual(offers[0]["pays_gold"], 11)

        from app import prompts

        source = Path(prompts.__file__).read_text(encoding="utf-8")
        self.assertIn('slim["pays"]', source)


if __name__ == "__main__":
    unittest.main()
