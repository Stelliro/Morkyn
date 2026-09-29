"""Wait crowd/danger place names are whole tokens, not substrings.

"Flash Inn" used to count as ash-wild and "Scarcity Ridge" / "Warden Keep" /
"Forward Camp" as settlements, because _local_crowd_danger did `word in name`.
That moved night danger and market-hour crowd the wrong way.

Run: python -m unittest tests.test_wait_place_tokens
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-wait-tokens-"))
_ENV = {
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
}
os.environ.update(_ENV)

import app.encounters as encounters  # noqa: E402
import app.world as world  # noqa: E402
from app.db import db_path  # noqa: E402


def _assert_isolated() -> None:
    if not str(db_path()).startswith(str(_TMP)):
        raise AssertionError(f"test isolation failed: AI_RPG_DB resolves to {db_path()!r}")


def setUpModule() -> None:
    os.environ.update(_ENV)
    _assert_isolated()


_assert_isolated()


def _no_snapshot(*_args, **_kwargs):
    raise RuntimeError("crowd heuristic must not need a player snapshot")


class TestWaitPlaceNameTokens(unittest.TestCase):
    def setUp(self) -> None:
        self._snapshot = encounters.player_snapshot
        encounters.player_snapshot = _no_snapshot

    def tearDown(self) -> None:
        encounters.player_snapshot = self._snapshot

    def _pack(self, name: str, *, tile: str = "plains", hour: int = 12) -> dict:
        return world._local_crowd_danger(
            {
                "settings": {"playthrough_options": {"npc_density": "moderate", "difficulty": "normal"}},
                "current_location": {"name": name, "id": 1},
                "locations": [],
                "world_time": {"hour": hour},
                "map_tile": {"state": tile},
                "weather": {"kind": "clear"},
            }
        )

    def test_substring_names_do_not_flip_settlement_feel(self) -> None:
        lamp = self._pack("Lamp Inn", tile="town", hour=23)
        flash = self._pack("Flash Inn", tile="town", hour=23)
        self.assertEqual(flash["crowd"], lamp["crowd"])
        self.assertEqual(flash["danger"], lamp["danger"])

        bare = self._pack("Bare Ridge")
        for name in ("Scarcity Ridge", "Warden Keep", "Forward Camp"):
            other = self._pack(name)
            self.assertEqual(other["crowd"], bare["crowd"], name)
            self.assertEqual(other["danger"], bare["danger"], name)

    def test_real_place_words_still_move_crowd_and_danger(self) -> None:
        bare = self._pack("Bare Ridge")
        ward = self._pack("East Ward")
        market = self._pack("Market Square")
        ash = self._pack("Ash Wastes")
        ruined = self._pack("Ruined Chapel")
        self.assertGreater(ward["crowd"], bare["crowd"])
        self.assertGreater(market["crowd"], ward["crowd"])
        self.assertGreater(ash["danger"], bare["danger"])
        self.assertGreater(ruined["danger"], bare["danger"])
        # A town tile stays settlement-like at night; an ash name does not.
        town = self._pack("Lamp Inn", tile="town", hour=23)
        ash_town = self._pack("Ashen Court", tile="town", hour=23)
        self.assertGreater(ash_town["danger"], town["danger"])


if __name__ == "__main__":
    unittest.main()
