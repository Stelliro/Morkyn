"""
The cache-busting token is computed from the bundle, not copied from the version.

History, because the replacement only makes sense against it. static/index.html
used to carry a hand-written token:

    <script src="/static/app.js?v=v0-9-1-wip"></script>

Nothing moved it when the version moved, and for 0.9.11 it did not: every
browser that had already loaded the game re-requested the exact URL it had
cached, got its stored copy, and the release reached those players as nothing
at all. From the server the deploy looked perfect.

The first fix was a test asserting token == APP_VERSION. That is narrower than
it looks: it says nothing about whether the token moved when app.js moved, so
a second fix at the same version would have gone missing the same way with the
suite green.

Now app/main.py derives the token from the bytes of app.js and styles.css and
substitutes it into the page at serve time. Change either file and the URL
changes by itself. There is no rule left to follow and nothing to remember,
which is the only reason to prefer it over a louder gate.
"""

import re
import unittest
from pathlib import Path

from app.main import BUNDLE_ASSETS, BUNDLE_PLACEHOLDER, bundle_token, index_html

STATIC = Path(__file__).resolve().parent.parent / "static"
INDEX = STATIC / "index.html"
ASSET_REF_RE = re.compile(r'/static/([\w.\-]+)\?v=([^"\']+)')


class SourceTemplateTests(unittest.TestCase):
    def test_index_ships_the_placeholder_not_a_baked_token(self):
        html = INDEX.read_text(encoding="utf-8")
        refs = ASSET_REF_RE.findall(html)
        self.assertTrue(refs, "no versioned assets found; the guard would pass vacuously")
        for name, token in refs:
            with self.subTest(asset=name):
                self.assertEqual(
                    token,
                    BUNDLE_PLACEHOLDER,
                    f"/static/{name} carries a hard-coded token again; it will go stale",
                )

    def test_both_bundle_assets_are_versioned(self):
        names = {name for name, _ in ASSET_REF_RE.findall(INDEX.read_text(encoding="utf-8"))}
        for asset in BUNDLE_ASSETS:
            self.assertIn(asset, names)


class BundleTokenTests(unittest.TestCase):
    def test_token_is_a_short_url_safe_digest(self):
        self.assertRegex(bundle_token(), r"^[0-9a-f]{16}$")

    def test_token_is_stable_while_the_files_are(self):
        self.assertEqual(bundle_token(), bundle_token())

    def test_token_follows_the_content(self):
        """The whole point: edit an asset, get a different URL."""
        target = STATIC / BUNDLE_ASSETS[0]
        before = bundle_token()
        original = target.read_bytes()
        try:
            target.write_bytes(original + b"\n// cache token probe\n")
            after = bundle_token()
        finally:
            target.write_bytes(original)
        self.assertNotEqual(before, after, "an edited asset produced the same URL")
        self.assertEqual(bundle_token(), before, "restoring the file must restore the token")


class ServedPageTests(unittest.TestCase):
    def test_no_placeholder_survives_into_the_served_page(self):
        html, _ = index_html()
        self.assertNotIn(BUNDLE_PLACEHOLDER, html)

    def test_served_page_points_at_the_current_token(self):
        html, token = index_html()
        for asset in BUNDLE_ASSETS:
            self.assertIn(f"/static/{asset}?v={token}", html)

    def test_served_html_is_otherwise_the_file_on_disk(self):
        """Substitution only; nothing else about the page may change."""
        html, token = index_html()
        raw = INDEX.read_text(encoding="utf-8")
        self.assertEqual(html, raw.replace(BUNDLE_PLACEHOLDER, token))

    def test_the_page_is_rebuilt_when_an_asset_changes(self):
        """Guards the mtime/size cache: a stale page would name a stale token."""
        target = STATIC / BUNDLE_ASSETS[0]
        original = target.read_bytes()
        _, before = index_html()
        try:
            target.write_bytes(original + b"\n// cache rebuild probe\n")
            html, after = index_html()
            self.assertNotEqual(before, after, "cached page survived an asset change")
            self.assertIn(f"?v={after}", html)
        finally:
            target.write_bytes(original)
        _, restored = index_html()
        self.assertEqual(restored, before)


if __name__ == "__main__":
    unittest.main()
