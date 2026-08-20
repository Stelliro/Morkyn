"""Regression: forge_enable_hr / enable_hr string 'false' must NOT enable hires.

JSON/settings/partial patches can deliver forge_enable_hr as the string 'false'.
Python bool('false') is True — callers must use _as_bool, not bare bool(...).
Existing tools/test_hires_upscale_path.py only passes real bools True/False.
"""
from __future__ import annotations

import base64
import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

from app.image_backends import (  # noqa: E402
    _as_bool,
    _generate_forge,
)


def _png_b64(w: int = 64, h: int = 64, color=(20, 40, 60)) -> str:
    img = Image.new("RGB", (w, h), color)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def test_as_bool_truth_table():
    # Document the Python footgun the helper exists to prevent
    assert bool("false") is True, "Python bool('false') is True — this is the footgun"

    assert _as_bool("false") is False
    assert _as_bool("False") is False
    assert _as_bool("FALSE") is False
    assert _as_bool("0") is False
    assert _as_bool("off") is False
    assert _as_bool("no") is False
    assert _as_bool("") is False
    assert _as_bool(False) is False
    assert _as_bool(0) is False
    assert _as_bool(None, default=False) is False

    assert _as_bool("true") is True
    assert _as_bool("True") is True
    assert _as_bool("1") is True
    assert _as_bool("on") is True
    assert _as_bool("yes") is True
    assert _as_bool(True) is True
    assert _as_bool(1) is True


def test_generate_forge_string_false_no_hires():
    base_img = _png_b64()
    calls: list[str] = []
    bodies: list[dict] = []

    def fake_http(method, url, body=None, timeout=30):
        calls.append(url)
        bodies.append(body or {})
        return {"images": [base_img]}

    with patch("app.image_backends._http_json", side_effect=fake_http):
        out = _generate_forge(
            base_url="http://127.0.0.1:7861",
            prompt="test",
            negative_prompt="",
            width=512,
            height=512,
            steps=10,
            cfg_scale=5,
            seed=9,
            timeout=30,
            enable_hr="false",  # string from JSON/settings — must stay OFF
            hr_scale=1.5,
            hr_upscaler="Latent",
            hr_denoising_strength=0.45,
        )

    assert out.get("hires_requested") is False, out
    assert not out.get("hires_post_upscale"), out
    assert not any("extra-single" in u for u in calls)
    assert sum(1 for u in calls if u.endswith("/img2img")) == 0
    # Native HR payloads must not appear (enable_hr True in request body)
    assert not any(b.get("enable_hr") is True for b in bodies), bodies


def test_generate_forge_string_true_hires_on():
    base_img = _png_b64(512, 512)
    big_img = _png_b64(768, 768, (40, 80, 120))
    calls: list[str] = []

    def fake_http(method, url, body=None, timeout=30):
        calls.append(url)
        body = body or {}
        if body.get("enable_hr") is True:
            raise RuntimeError("HTTP 500 native HR broken")
        if url.endswith("/txt2img"):
            return {"images": [base_img]}
        if url.endswith("/img2img"):
            return {"images": [big_img]}
        if "extra-single" in url:
            raise RuntimeError("HTTP 422 extras")
        raise RuntimeError(f"unexpected {url}")

    with patch("app.image_backends._http_json", side_effect=fake_http):
        out = _generate_forge(
            base_url="http://127.0.0.1:7861",
            prompt="test",
            negative_prompt="",
            width=512,
            height=512,
            steps=16,
            cfg_scale=6,
            seed=10,
            timeout=30,
            enable_hr="true",  # string true must still opt-in
            hr_scale=1.5,
            hr_upscaler="Latent",
            hr_denoising_strength=0.45,
        )

    assert out.get("hires_requested") is True, out
    assert out.get("hires_post_upscale") is True, out
    assert any(u.endswith("/img2img") for u in calls)


def test_as_bool_vs_bare_bool_divergence():
    """If a caller regresses to bool(x), string 'false' silently enables hires."""
    for truthy_false in ("false", "False", "off", "no", ""):
        bare = bool(truthy_false) if truthy_false != "" else bool("")
        # empty string is falsy for bare bool; non-empty falsey words are the trap
        if truthy_false == "":
            assert bare is False
            assert _as_bool(truthy_false) is False
        else:
            assert bare is True, f"bare bool({truthy_false!r}) should be True"
            assert _as_bool(truthy_false) is False, f"_as_bool({truthy_false!r}) must be False"


def main() -> int:
    fails: list[str] = []
    for name, fn in [
        ("as_bool_table", test_as_bool_truth_table),
        ("bare_bool_divergence", test_as_bool_vs_bare_bool_divergence),
        ("string_false_no_hires", test_generate_forge_string_false_no_hires),
        ("string_true_hires_on", test_generate_forge_string_true_hires_on),
    ]:
        try:
            fn()
            print(f"OK {name}")
        except Exception as exc:
            fails.append(f"{name}: {exc}")
            print(f"FAIL {name}: {exc}")
    if fails:
        print(f"FAILED {len(fails)}")
        return 1
    print("OK: _as_bool string false hires regression")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
