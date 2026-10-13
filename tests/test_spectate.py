"""Watching a live run: MORKYN_SPECTATE makes the server read-only and /api/live-tick
tells the page when a new turn landed (tools/api_bridge_playtest.py --viewer-port).
Route functions are called directly (the venv has no httpx for TestClient). Every
path is pinned to a temporary directory, so nothing here touches data/."""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-spectate-test-"))
os.environ.update(
    {
        "AI_RPG_DB": str(_TMP / "world.db"),
        "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
        "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
        "AI_RPG_CONSOLIDATED_FACTS": str(_TMP / "facts.jsonl"),
        "AI_RPG_CAMPAIGN_SLOTS": str(_TMP / "slots"),
        "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
        "AI_RPG_PACK_DIR": str(_TMP / "packs"),
        "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
        "AI_RPG_IDEA_BANK": str(_TMP / "idea_bank"),
        "AI_RPG_LAUNCHER_PREFS": str(_TMP / "launcher_prefs.json"),
    }
)

from app.db import connect, init_db  # noqa: E402
from app.main import _spectator_guard, api_live_tick  # noqa: E402


def _guard(method: str, path: str) -> int:
    request = SimpleNamespace(method=method, url=SimpleNamespace(path=path))

    async def passed(_request):
        return SimpleNamespace(status_code=200)

    return asyncio.run(_spectator_guard(request, passed)).status_code


class SpectateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()

    def test_tick_reports_the_newest_turn(self) -> None:
        with connect() as conn:
            conn.execute("INSERT INTO journal (turn, kind, content) VALUES (7, 'narration', 'x')")
            conn.commit()
        with mock.patch.dict(os.environ, {"MORKYN_SPECTATE": "1"}):
            tick = api_live_tick()
        self.assertTrue(tick["spectate"])
        self.assertGreaterEqual(tick["turn"], 7)
        self.assertGreater(tick["journal_id"], 0)

    def test_spectating_refuses_every_write(self) -> None:
        with mock.patch.dict(os.environ, {"MORKYN_SPECTATE": "1"}):
            for path in ("/api/turn", "/api/wait", "/api/campaign-slots/load", "/api/setup"):
                self.assertEqual(_guard("POST", path), 423, path)
            self.assertEqual(_guard("GET", "/api/state"), 200)

    def test_a_normal_server_is_not_spectating(self) -> None:
        with mock.patch.dict(os.environ, {"MORKYN_SPECTATE": ""}):
            self.assertFalse(api_live_tick()["spectate"])
            self.assertEqual(_guard("POST", "/api/turn"), 200)


if __name__ == "__main__":
    unittest.main()
