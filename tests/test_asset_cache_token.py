"""
The ?v= tokens on app.js and styles.css must track APP_VERSION.

They are hand-written into static/index.html, which is served as a plain
FileResponse with no templating, so nothing was making them move when the
version did. They did not move for 0.9.11: index.html still asked for
`app.js?v=v0-9-1-wip`, which is a URL every returning player already has
cached. Shipping a fix behind an unchanged cache key ships nothing -- the
browser never asks for the new file.

This is the gate for that. A version bump now fails the suite until the
tokens follow it.
"""

import re
import unittest
from pathlib import Path

from app.main import APP_VERSION

INDEX = Path(__file__).resolve().parent.parent / "static" / "index.html"
ASSET_REF_RE = re.compile(r'/static/([\w.\-]+)\?v=([^"\']+)')


def expected_token() -> str:
    """`V0.9.11` -> `v0-9-11`, matching the format already in the file."""
    return APP_VERSION.lower().replace(".", "-")


class AssetCacheTokenTests(unittest.TestCase):
    def setUp(self):
        self.html = INDEX.read_text(encoding="utf-8")
        self.refs = ASSET_REF_RE.findall(self.html)

    def test_index_has_versioned_assets(self):
        """If these disappear, the drift guard below silently passes forever."""
        names = {name for name, _ in self.refs}
        self.assertIn("app.js", names)
        self.assertIn("styles.css", names)

    def test_every_token_matches_the_app_version(self):
        want = expected_token()
        for name, token in self.refs:
            with self.subTest(asset=name):
                self.assertEqual(
                    token,
                    want,
                    f"/static/{name} is cache-busted with {token!r} but APP_VERSION is "
                    f"{APP_VERSION!r}. Returning players keep the file they already "
                    f"cached, so this release reaches nobody. Expected {want!r}.",
                )

    def test_token_format_is_url_safe(self):
        self.assertRegex(expected_token(), r"^v[0-9a-z\-]+$")


if __name__ == "__main__":
    unittest.main()
