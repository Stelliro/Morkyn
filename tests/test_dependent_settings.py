"""Settings that do nothing under another setting are greyed (static/ui/interact.js 4b).

Stell (2026-10-23): "some of the settings and menu ui is disabled when some
settings are enabled". DEPENDENT_FIELDS names each dependent control by
selector; a renamed field would quietly stop greying, so every name it lists
must still be in the markup. The controls go inert, not disabled: the launcher
form saves through FormData, which leaves disabled controls out.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INTERACT = ROOT / "static" / "ui" / "interact.js"
APP_JS = ROOT / "static" / "app.js"
INDEX = ROOT / "static" / "index.html"
SKIN = ROOT / "static" / "ui" / "skin.css"
STYLES = ROOT / "static" / "styles.css"


def _table() -> str:
    js = INTERACT.read_text(encoding="utf-8")
    start = js.index("const DEPENDENT_FIELDS = [")
    return js[start : js.index("\n  ];", start)]


class DependentSettingsTest(unittest.TestCase):
    def test_every_target_is_in_the_markup(self):
        markup = APP_JS.read_text(encoding="utf-8") + INDEX.read_text(encoding="utf-8")
        table = _table()
        names = re.findall(r"\[name=\"([a-z_]+)\"\]", table)
        classes = re.findall(r"\"\.([A-Za-z]+)\"", table)
        attrs = re.findall(r"\"\[(data-[a-z-]+)\]\"", table)
        self.assertGreater(len(names), 10)
        for name in names:
            self.assertRegex(markup, rf'name="{name}"', name)
        for cls in classes:
            self.assertRegex(markup, rf'class="[^"]*\b{cls}\b', cls)
        for attr in attrs:
            self.assertIn(attr, markup)
        for name in set(re.findall(r'fieldValue\(form, "([a-z_]+)"\)', table)):
            self.assertRegex(markup, rf'name="{name}"', name)

    def test_fields_go_inert_and_rules_rerun_after_renders(self):
        js = INTERACT.read_text(encoding="utf-8")
        start = js.index("function applyDependentFields")
        body = js[start : js.index("\n  }\n", start)]
        self.assertIn("control.inert = isOff", body)
        self.assertIn("control.dataset.dependentOff", body)
        apply_all = js[js.index("function applyAll()") : js.index("const observer")]
        self.assertIn("applyDependentFields();", apply_all)

    def test_look_in_skin_not_layout(self):
        skin = SKIN.read_text(encoding="utf-8")
        block = skin[skin.index(".uiDependentOff {") :]
        block = block[: block.index("}")]
        self.assertIn("opacity", block)
        for word in ("display", "width", "margin", "position"):
            self.assertNotIn(word, block)
        self.assertNotIn("uiDependentOff", STYLES.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
