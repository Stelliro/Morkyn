"""Regression: quality hires uses diffusion second pass, not soft size-only enlarge."""
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
    _forge_raw_b64,
    _generate_forge,
    _image_b64_size,
    _is_latent_upscaler,
)


def _png_b64(w: int, h: int, color=(30, 60, 90)) -> str:
    img = Image.new("RGB", (w, h), color)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def test_latent_detect():
    assert _is_latent_upscaler("Latent")
    assert _is_latent_upscaler("Latent (nearest-exact)")
    assert not _is_latent_upscaler("4x-UltraSharp")
    assert not _is_latent_upscaler("R-ESRGAN 4x+")


def test_hires_uses_img2img_second_pass_when_native_fails():
    base_img = _png_b64(512, 512)
    big_img = _png_b64(768, 768, (40, 80, 120))
    calls: list[str] = []

    def fake_http(method, url, body=None, timeout=30):
        calls.append(url)
        body = body or {}
        # Native HR attempts → fail
        if body.get("enable_hr") is True:
            raise RuntimeError("HTTP 500 native HR broken")
        # First pass txt2img
        if url.endswith("/txt2img"):
            return {"images": [base_img]}
        # Diffusion second pass img2img — must run at larger canvas
        if url.endswith("/img2img"):
            assert int(body.get("width") or 0) >= 700, body.get("width")
            assert float(body.get("denoising_strength") or 0) >= 0.28, body.get(
                "denoising_strength"
            )
            return {"images": [big_img]}
        # extras
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
            seed=1,
            timeout=30,
            enable_hr=True,
            hr_scale=1.5,
            hr_upscaler="Latent",  # skip extras, force img2img pass
            hr_denoising_strength=0.45,
        )
    assert out.get("hires_requested") is True
    assert out.get("hires_post_upscale") is True
    assert out.get("hires_method") == "img2img_hires_pass"
    assert out.get("hires_quality") is True
    w, h = _image_b64_size(out["image_base64"])
    assert w >= 700 and h >= 700
    assert any(u.endswith("/img2img") for u in calls)


def test_extras_then_refine_when_pixel_upscaler():
    base_img = _png_b64(512, 512)
    mid_img = _png_b64(768, 768, (50, 50, 50))
    final_img = _png_b64(768, 768, (90, 90, 90))
    stage = {"n": 0}

    def fake_http(method, url, body=None, timeout=30):
        body = body or {}
        if body.get("enable_hr") is True:
            raise RuntimeError("HTTP 500 native")
        if url.endswith("/txt2img"):
            return {"images": [base_img]}
        if "extra-single" in url:
            return {"image": mid_img}
        if url.endswith("/img2img"):
            # refine after extras should keep size, use quality denoise
            assert float(body.get("denoising_strength") or 0) >= 0.28
            stage["n"] += 1
            return {"images": [final_img]}
        raise RuntimeError(url)

    with patch("app.image_backends._http_json", side_effect=fake_http):
        out = _generate_forge(
            base_url="http://127.0.0.1:7861",
            prompt="test",
            negative_prompt="",
            width=512,
            height=512,
            steps=16,
            cfg_scale=6,
            seed=2,
            timeout=30,
            enable_hr=True,
            hr_scale=1.5,
            hr_upscaler="4x-UltraSharp",
            hr_denoising_strength=0.45,
        )
    assert out.get("hires_method") == "extras_then_img2img"
    assert out.get("hires_quality") is True
    assert stage["n"] >= 1


def test_hires_off_no_second_pass():
    base_img = _png_b64(512, 512)
    calls: list[str] = []

    def fake_http(method, url, body=None, timeout=30):
        calls.append(url)
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
            seed=3,
            timeout=30,
            enable_hr=False,
            hr_scale=1.5,
        )
    assert out.get("hires_requested") is False
    assert not out.get("hires_post_upscale")
    assert not any("extra-single" in u for u in calls)
    assert sum(1 for u in calls if u.endswith("/img2img")) == 0


def test_face_ref_img2img_first_pass_still_runs_quality_hires():
    """Fullbody nearly always uses face-ref init_images; native enable_hr is skipped.

    Quality hires must still run the post-pass (img2img_hires_pass / extras_then_img2img).
    Gating post-upscale with `if hr_on and not use_img2img` (mirroring native-HR) would
    silently drop fullbody hires while pure-txt2img tests still pass.
    """
    face_ref = _png_b64(512, 512, (80, 40, 40))
    first_pass = _png_b64(512, 768, (30, 60, 90))
    big_img = _png_b64(768, 1152, (40, 80, 120))
    img2img_calls: list[dict] = []

    def fake_http(method, url, body=None, timeout=30):
        body = body or {}
        # Native HR must never be attempted on face-ref img2img first path
        if body.get("enable_hr") is True:
            raise RuntimeError("native enable_hr should be skipped for use_img2img")
        if url.endswith("/txt2img"):
            raise RuntimeError("face-ref fullbody must use /img2img first pass, not /txt2img")
        if url.endswith("/img2img"):
            img2img_calls.append(dict(body))
            # First pass: face-ref at base canvas + high face-ref denoise
            if len(img2img_calls) == 1:
                assert body.get("init_images"), "first pass needs face ref init_images"
                assert int(body.get("width") or 0) == 512
                assert float(body.get("denoising_strength") or 0) >= 0.8
                return {"images": [first_pass]}
            # Second pass: quality hires at larger canvas
            assert int(body.get("width") or 0) >= 700, body.get("width")
            assert float(body.get("denoising_strength") or 0) >= 0.28, body.get(
                "denoising_strength"
            )
            return {"images": [big_img]}
        if "extra-single" in url:
            raise RuntimeError("HTTP 422 extras")
        raise RuntimeError(f"unexpected {url}")

    with patch("app.image_backends._http_json", side_effect=fake_http):
        out = _generate_forge(
            base_url="http://127.0.0.1:7861",
            prompt="full body character",
            negative_prompt="",
            width=512,
            height=768,
            steps=16,
            cfg_scale=6,
            seed=4,
            timeout=30,
            enable_hr=True,
            hr_scale=1.5,
            hr_upscaler="Latent",
            hr_denoising_strength=0.45,
            img2img_denoising_strength=0.85,
            init_images=[face_ref],
        )
    assert out.get("mode") == "img2img"
    assert out.get("hires_requested") is True
    assert out.get("hires_post_upscale") is True
    assert out.get("hires_method") == "img2img_hires_pass"
    assert out.get("hires_quality") is True
    assert not out.get("hires_native")
    w, h = _image_b64_size(out["image_base64"])
    assert w >= 700 and h >= 700
    assert len(img2img_calls) >= 2, f"expected first face-ref + hires pass, got {len(img2img_calls)}"


def test_extras_only_soft_is_not_quality():
    """Pixel extras succeed but every diffusion refine fails → soft enlarge, not quality hires."""
    base_img = _png_b64(512, 512)
    big_img = _png_b64(768, 768, (70, 70, 100))
    calls: list[str] = []

    def fake_http(method, url, body=None, timeout=30):
        calls.append(url)
        body = body or {}
        if body.get("enable_hr") is True:
            raise RuntimeError("HTTP 500 native HR broken")
        if url.endswith("/txt2img"):
            return {"images": [base_img]}
        if "extra-single" in url:
            return {"image": big_img}
        if url.endswith("/img2img"):
            # Path A refine + Path B img2img_hires_pass must both fail
            raise RuntimeError("HTTP 500 img2img broken")
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
            seed=5,
            timeout=30,
            enable_hr=True,
            hr_scale=1.5,
            hr_upscaler="4x-UltraSharp",
            hr_denoising_strength=0.45,
        )
    assert out.get("hires_requested") is True
    assert out.get("hires_method") == "extras_only_soft"
    assert out.get("hires_quality") is False
    assert out.get("hires_post_upscale") is True
    note = str(out.get("hires_note") or out.get("hires_error") or "").lower()
    assert note, "soft-only path should surface a note"
    assert "soft" in note or "no diffusion" in note or "only" in note
    # Must not claim quality refine language
    assert "quality hires" not in note
    w, h = _image_b64_size(out["image_base64"])
    assert w >= 700 and h >= 700
    assert any("extra-single" in u for u in calls)
    assert any(u.endswith("/img2img") for u in calls)


def test_raw_b64():
    pure = _png_b64(32, 32)
    assert _forge_raw_b64(f"data:image/png;base64,{pure}") == pure


def main() -> int:
    fails: list[str] = []
    for name, fn in [
        ("latent_detect", test_latent_detect),
        ("raw_b64", test_raw_b64),
        ("img2img_pass", test_hires_uses_img2img_second_pass_when_native_fails),
        ("extras_refine", test_extras_then_refine_when_pixel_upscaler),
        ("extras_only_soft_not_quality", test_extras_only_soft_is_not_quality),
        ("hires_off", test_hires_off_no_second_pass),
        ("face_ref_hires", test_face_ref_img2img_first_pass_still_runs_quality_hires),
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
    print("OK: quality hires path")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
