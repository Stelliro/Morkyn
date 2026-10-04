"""Character art is named in the state and served by its own route, never inlined.

Measured on a live save: `player_portrait` and `player_fullbody` together were
about 1.2 MB of base64 on the state top level, and `/api/state` plus every
turn payload's `state` carried them, so each poll and each turn shipped a
picture the browser already held in localStorage.

Now `get_state()` carries each slot as `{kind, updated_at, token, url, ...}`
with no `data_url`, the token is a digest of the stored image, and
`GET /api/player-art/{kind}?v=<token>` serves the bytes with cache headers
keyed by that token. The browser fetches once per token.

Run:  python -m unittest tests.test_player_art_route
"""
from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-player-art-test-"))
_ENV = {
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
    "AI_RPG_CAMPAIGN_SLOTS": str(_TMP / "slots"),
}
os.environ.update(_ENV)

from fastapi import HTTPException  # noqa: E402

from app import db, world  # noqa: E402
from app.main import (  # noqa: E402
    PLAYER_ART_IMMUTABLE,
    PlayerArtStoreRequest,
    api_player_art,
    api_player_art_store,
    api_state,
)


def setUpModule():
    os.environ.update(_ENV)
    assert str(db.db_path()).startswith(str(_TMP)), db.db_path()
    db.init_db()


FACE_BYTES = b"\x89PNG\r\n\x1a\n" + b"face-pixels"
BODY_BYTES = b"\x89PNG\r\n\x1a\n" + b"body-pixels"
FACE = "data:image/png;base64," + base64.b64encode(FACE_BYTES).decode("ascii")
BODY = "data:image/webp;base64," + base64.b64encode(BODY_BYTES).decode("ascii")


def _store(key: str, value: str | None) -> None:
    with db.connect() as conn:
        if value is None:
            conn.execute("DELETE FROM settings WHERE key = ?", (key,))
        else:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))


def _row(data_url: str, kind: str, updated_at: str = "2026-10-04T10:00:00") -> str:
    return json.dumps({"data_url": data_url, "kind": kind, "updated_at": updated_at, "equipment": ["cloak"]})


class _ArtFixture(unittest.TestCase):
    def setUp(self):
        _store("player_portrait", _row(FACE, "face"))
        _store("player_fullbody", _row(BODY, "fullbody"))

    def tearDown(self):
        _store("player_portrait", None)
        _store("player_fullbody", None)


# ---------------------------------------------------------------------------
# 1. The state names the art and never carries it
# ---------------------------------------------------------------------------
class TestStateNamesTheArt(_ArtFixture):
    def test_entries_carry_kind_updated_at_token_and_url_but_no_data_url(self):
        state = world.get_state()
        face = state["player_portrait"]
        body = state["player_fullbody"]
        for entry, kind in ((face, "face"), (body, "fullbody")):
            with self.subTest(kind=kind):
                self.assertNotIn("data_url", entry)
                self.assertEqual(entry["kind"], kind)
                self.assertEqual(entry["updated_at"], "2026-10-04T10:00:00")
                self.assertRegex(entry["token"], r"^[0-9a-f]{16}$")
                self.assertEqual(entry["url"], f"/api/player-art/{kind}?v={entry['token']}")
                self.assertEqual(entry["equipment"], ["cloak"])
        self.assertNotEqual(face["token"], body["token"])

    def test_no_base64_anywhere_in_the_state_or_the_state_route(self):
        self.assertNotIn("base64,", json.dumps(world.get_state(include_hidden=True)))
        self.assertNotIn("base64,", json.dumps(api_state()))

    def test_token_follows_the_stored_image(self):
        before = world.get_state()["player_portrait"]["token"]
        _store("player_portrait", _row("data:image/png;base64,QUJD", "face"))
        after = world.get_state()["player_portrait"]["token"]
        self.assertNotEqual(before, after, "the picture changed but the token did not")
        _store("player_portrait", _row(FACE, "face", updated_at="2026-10-04T11:11:11"))
        self.assertEqual(
            world.get_state()["player_portrait"]["token"],
            before,
            "the token is a digest of the image, not of the row's timestamp",
        )

    def test_a_slot_without_an_image_is_null(self):
        _store("player_portrait", None)
        _store("player_fullbody", json.dumps({"kind": "fullbody", "path": "x.png"}))
        state = world.get_state()
        self.assertIsNone(state["player_portrait"])
        self.assertIsNone(state["player_fullbody"])

    def test_an_unreadable_row_is_null(self):
        _store("player_portrait", "{not json")
        self.assertIsNone(world.get_state()["player_portrait"])


# ---------------------------------------------------------------------------
# 2. The route serves the stored image, keyed by the token
# ---------------------------------------------------------------------------
class TestPlayerArtRoute(_ArtFixture):
    def test_serves_the_stored_bytes_with_the_stored_media_type(self):
        token = world.get_state()["player_portrait"]["token"]
        response = api_player_art("face", v=token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.body, FACE_BYTES)
        self.assertEqual(response.media_type, "image/png")
        self.assertEqual(response.headers["cache-control"], PLAYER_ART_IMMUTABLE)
        self.assertEqual(response.headers["etag"], f'"{token}"')
        self.assertEqual(response.headers["x-player-art-token"], token)
        body = api_player_art("fullbody", v=world.get_state()["player_fullbody"]["token"])
        self.assertEqual(body.body, BODY_BYTES)
        self.assertEqual(body.media_type, "image/webp")

    def test_a_stale_or_missing_token_still_gets_the_current_picture_but_not_immutably(self):
        for stale in ("", "0123456789abcdef"):
            with self.subTest(v=stale):
                response = api_player_art("face", v=stale)
                self.assertEqual(response.body, FACE_BYTES)
                self.assertEqual(response.headers["cache-control"], "no-cache")

    def test_404_when_nothing_is_stored(self):
        _store("player_portrait", None)
        with self.assertRaises(HTTPException) as caught:
            api_player_art("face")
        self.assertEqual(caught.exception.status_code, 404)

    def test_404_for_an_unknown_slot_or_an_unreadable_image(self):
        with self.assertRaises(HTTPException) as caught:
            api_player_art("hat")
        self.assertEqual(caught.exception.status_code, 404)
        _store("player_portrait", _row("data:image/png;base64,%%%not-base64%%%", "face"))
        with self.assertRaises(HTTPException) as caught:
            api_player_art("face")
        self.assertEqual(caught.exception.status_code, 404)
        _store("player_portrait", _row("data:text/plain;base64,aGVsbG8=", "face"))
        with self.assertRaises(HTTPException) as caught:
            api_player_art("face")
        self.assertEqual(caught.exception.status_code, 404)

    def test_the_store_route_reports_presence_from_the_slim_state(self):
        _store("player_fullbody", None)
        result = api_player_art_store(PlayerArtStoreRequest(face_data_url=FACE))
        self.assertTrue(result["has_face"])
        self.assertFalse(result["has_fullbody"])
        stored = api_player_art("face", v=world.get_state()["player_portrait"]["token"])
        self.assertEqual(stored.body, FACE_BYTES)


if __name__ == "__main__":
    unittest.main()
