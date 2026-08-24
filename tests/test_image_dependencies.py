"""Regression tests: Pillow is a real dependency, not a lucky accident.

`app/image_backends.py` imports PIL in several places, but `requirements.txt`
never listed it and neither bootstrapper installed it. Every use is a
function-local import inside `except Exception`, so on a clean install the art
checks did not fail -- they quietly returned "fine":

    _image_looks_abstract_failure()  -> False for every image ever generated

which is indistinguishable from a good image, so the near-black / low-structure
retry simply never fired.

Nobody noticed because the two harnesses that cover this surface --
`tools/test_hires_upscale_path.py` and `tools/test_as_bool_hires.py`, both
listed as must-stay-green locks -- `import PIL` at module scope and so exited 1
on import in the project's own venv. A lock that cannot load is not a lock.

This file asserts the dependency is declared and importable, so the failure mode
is a red test naming the missing package rather than an art gate that passes
everything.

Run:  python -m unittest tests.test_image_dependencies
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class TestPillowIsDeclared(unittest.TestCase):
    def test_requirements_lists_pillow(self):
        text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertRegex(
            text,
            r"(?im)^\s*pillow\b",
            "app/image_backends.py imports PIL; requirements.txt must say so",
        )

    def test_pillow_is_actually_importable(self):
        try:
            from PIL import Image, ImageFilter, ImageStat  # noqa: F401
        except ImportError as exc:  # pragma: no cover - only on a broken env
            self.fail(f"Pillow is declared but not installed: {exc}")

    def test_every_pil_import_in_the_app_is_covered_by_the_declaration(self):
        src = (ROOT / "app" / "image_backends.py").read_text(encoding="utf-8", errors="replace")
        self.assertTrue(
            re.search(r"^\s*from PIL import ", src, re.M),
            "expected image_backends.py to import PIL",
        )


class TestAMissingPillowIsNotSilent(unittest.TestCase):
    def test_the_abstract_failure_check_warns_instead_of_passing_quietly(self):
        import app.image_backends as ib

        src = (ROOT / "app" / "image_backends.py").read_text(encoding="utf-8", errors="replace")
        self.assertIn("_warn_pil_missing", src)
        self.assertTrue(hasattr(ib, "_warn_pil_missing"))
        # ImportError must be handled separately from the catch-all, or a
        # missing package looks exactly like a clean image again.
        body = src[src.index("def _image_looks_abstract_failure") :]
        body = body[: body.index("\ndef ", 1)]
        self.assertIn("except ImportError:", body)
        self.assertLess(
            body.index("except ImportError:"),
            body.index("except Exception:"),
            "the catch-all must not shadow the ImportError branch",
        )


class TestNoUnwiredPromises(unittest.TestCase):
    def test_the_pil_upscale_fallback_is_not_claimed_unless_it_exists(self):
        # `_pil_upscale_b64` was documented "Guaranteed LANCZOS upscale so hires
        # is never a no-op when Forge APIs fail" and had no caller anywhere, and
        # the extras-failure message told the user a PIL fallback would run.
        src = (ROOT / "app" / "image_backends.py").read_text(encoding="utf-8", errors="replace")
        if "_pil_upscale_b64" in src:
            self.assertGreater(
                src.count("_pil_upscale_b64"),
                1,
                "_pil_upscale_b64 is defined but never called; wire it or drop it",
            )
        else:
            self.assertNotIn("PIL fallback will still run", src)


if __name__ == "__main__":
    unittest.main()
