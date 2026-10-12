"""A shard frame is painted as background, so a shard that scrolls its own content
must draw that frame in a transparent border band (static/ui/skin.css, section 02),
or rows scrolling past paint over its edges and cut corners. This finds every
shard selector given overflow: auto/scroll and checks it is in the band list.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "static"
SKIN = (STATIC / "ui" / "skin.css").read_text(encoding="utf-8")
LAYOUT = (STATIC / "styles.css").read_text(encoding="utf-8")


def _rules(css: str):
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        yield [s.strip() for s in match.group(1).split(",") if s.strip()], match.group(2)


def _shard_selectors() -> set[str]:
    """The selectors of the rule that paints the shard (the one with the 135deg corner layer)."""
    for selectors, body in _rules(SKIN):
        if "linear-gradient(135deg" in body and "--shard-line" in body and "border: 0" in body:
            return set(selectors)
    raise AssertionError("shard rule not found in skin.css")


def _band_selectors() -> set[str]:
    for selectors, body in _rules(SKIN):
        if "--shard-band:" in body:
            return set(selectors)
    raise AssertionError("scroll band rule (--shard-band) not found in skin.css")


class ShardScrollTests(unittest.TestCase):
    def test_the_rules_are_found(self):
        shards, band = _shard_selectors(), _band_selectors()
        self.assertIn(".modalPanel", shards)
        self.assertIn(".modalPanel", band)

    def test_every_scrolling_shard_has_the_band(self):
        shards, band = _shard_selectors(), _band_selectors()
        missing = []
        for css in (LAYOUT, SKIN):
            for selectors, body in _rules(css):
                if not re.search(r"overflow(-[xy])?\s*:\s*(auto|scroll)", body):
                    continue
                for selector in selectors:
                    last = selector.split()[-1]
                    if last in shards and last not in band:
                        missing.append(selector)
        self.assertEqual(missing, [], "these shards scroll but draw their frame where content can cover it")


if __name__ == "__main__":
    unittest.main()
