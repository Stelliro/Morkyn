"""Prove: hires/quality flush can wipe forge_active_loras when LoRA UI is empty.

Bug class (robustness-4):
  _flushArtQualitySettings always POSTs forge_active_loras: collectSetupLoras().
  collectSetupLoras() returns [] when #setupArtLoraList is missing or has no
  checked boxes. renderSetupLoraList never hydrates checks from
  imageConfig.forge_active_loras (only live DOM). After reload/re-entry, or
  before the catalog paints rows, a hires-only input/change/debounce flush
  therefore persists forge_active_loras: [] and clears the server stack used
  for shared/NPC gens — partial quality write clobbering unrelated persistence.

This harness:
  1) Static-checks app.js for always-posting forge_active_loras from collect
     without a config-wins / omit-when-empty guard.
  2) Static-checks renderSetupLoraList does not hydrate from saved config.
  3) Runs update_image_config with the empty-collect patch and observes wipe.

Exit 0 = invariant holds (bug fixed or absent)
Exit 1 = wipe path still present (bug proven)
Exit 2 = harness/setup error
"""
from __future__ import annotations

import re
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

APP_JS = ROOT / "static" / "app.js"


def _fn_body(text: str, sig: str, window: int = 5000) -> str | None:
    idx = text.find(sig)
    if idx < 0:
        return None
    chunk = text[idx : idx + window]
    paren = chunk.find("(")
    if paren < 0:
        return chunk
    depth = 0
    close_paren = -1
    for i, ch in enumerate(chunk[paren:], paren):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                close_paren = i
                break
    if close_paren < 0:
        return chunk
    body_open = chunk.find("{", close_paren)
    if body_open < 0:
        return chunk
    depth = 0
    for i, ch in enumerate(chunk[body_open:], body_open):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return chunk[: i + 1]
    return chunk


def check_static_product(text: str) -> dict:
    flush = _fn_body(text, "async function _flushArtQualitySettings")
    collect = _fn_body(text, "function collectSetupLoras")
    render = _fn_body(text, "function renderSetupLoraList", window=4500)
    if not flush or not collect or not render:
        missing = [
            n
            for n, b in (
                ("_flushArtQualitySettings", flush),
                ("collectSetupLoras", collect),
                ("renderSetupLoraList", render),
            )
            if not b
        ]
        raise RuntimeError(f"missing: {', '.join(missing)}")

    always_posts_loras = bool(
        re.search(r"const\s+loras\s*=\s*collectSetupLoras\s*\(\s*\)", flush)
    ) and bool(re.search(r"forge_active_loras\s*:\s*loras", flush))

    # Real guards (RHS / conditional omit) — NOT mere assignment imageConfig.forge_active_loras = loras
    has_config_wins_or_omit = bool(
        re.search(
            r"""
            loras\s*=\s*[^\n;]*imageConfig\s*\??\.\s*forge_active_loras
            | loras\.length\s*\?\s*loras\s*:\s*[^\n;]*imageConfig
            | !\s*loras\.length[\s\S]{0,240}?imageConfig\s*\??\.\s*forge_active_loras
            | delete\s+patch\.forge_active_loras
            | if\s*\(\s*loras\.length\s*\)[\s\S]{0,120}patch\[?['\"]?forge_active_loras
            | if\s*\(\s*loras\.length\s*\)[\s\S]{0,80}forge_active_loras\s*:
            | \(\s*loras\.length\s*\?\s*\{[^}]*forge_active_loras
            """,
            flush,
            re.X,
        )
    )

    collect_returns_empty = bool(
        re.search(r"if\s*\(\s*!?\s*list\s*\)\s*\{[^}]*return\s*\[\s*\]", collect, re.S)
        or re.search(r"return\s*\[\s*\]", collect)
    )

    # Hydration would *read* imageConfig.forge_active_loras into selected Map / checked
    render_hydrates_config = bool(
        re.search(
            r"""
            (?:imageConfig\s*\??\.\s*forge_active_loras)
            [\s\S]{0,200}?
            (?:selected\.set|\.checked\s*=|data-lora-name)
            |
            for\s*\([^)]*(?:imageConfig\s*\??\.\s*forge_active_loras|savedLoras|activeLoras)
            """,
            render,
            re.X,
        )
    )
    # Explicit "only live DOM" policy still present
    render_dom_only_policy = bool(
        re.search(
            r"Only preserve checks already in the live DOM|never auto-enable from saved config",
            render,
            re.I,
        )
    )

    return {
        "always_posts_loras": always_posts_loras,
        "has_config_wins_or_omit": has_config_wins_or_omit,
        "collect_returns_empty": collect_returns_empty,
        "render_hydrates_config": render_hydrates_config,
        "render_dom_only_policy": render_dom_only_policy,
    }


def simulate_product_flush_patch(checked_loras: list) -> dict:
    """Mirror current product patch construction (collect → always include)."""
    loras = list(checked_loras)
    return {
        "forge_active_loras": loras,
        "forge_enable_hr": True,
        "forge_hr_scale": 1.75,
        "forge_denoising_strength": 0.4,
        "forge_hr_second_pass_steps": 0,
        "forge_hr_upscaler": "R-ESRGAN 4x+",
    }


@contextmanager
def _fake_db_connect():
    class _Conn:
        def execute(self, *args, **kwargs):
            return None

    class _CM:
        def __enter__(self):
            return _Conn()

        def __exit__(self, *args):
            return False

    yield _CM()


def apply_server_patch(seed_cfg: dict, client_patch: dict) -> dict:
    """Call real update_image_config with DB side effects stubbed."""
    from app.image_backends import update_image_config

    base = dict(seed_cfg)

    def _get():
        return dict(base)

    # connect() is used as `with connect() as conn`
    def _connect():
        class _Conn:
            def execute(self, *a, **k):
                return None

        class _CM:
            def __enter__(self):
                return _Conn()

            def __exit__(self, *a):
                return False

        return _CM()

    with (
        patch("app.image_backends.get_image_config", side_effect=_get),
        patch("app.image_backends.connect", side_effect=_connect),
        patch("app.image_backends.load_image_presets", return_value={"launch": {}}),
        patch("app.image_backends.save_image_presets"),
    ):
        return update_image_config(client_patch)


def main() -> int:
    if not APP_JS.is_file():
        print("FAIL harness: static/app.js missing", file=sys.stderr)
        return 2

    text = APP_JS.read_text(encoding="utf-8")
    try:
        flags = check_static_product(text)
    except Exception as e:
        print(f"FAIL harness: static parse: {e}", file=sys.stderr)
        return 2

    print("=== robustness-4 hires flush LoRA wipe ===")
    print("static flags:", flags)

    seed_loras = [
        {"name": "character_lock_v1", "weight": 0.8},
        {"name": "detail_tweaker", "weight": 0.55},
    ]
    seed_cfg = {
        "provider": "forgesd",
        "forge_enable_hr": False,
        "forge_active_loras": seed_loras,
        "forge_hr_scale": 1.5,
        "forge_denoising_strength": 0.45,
        "forge_hr_second_pass_steps": 0,
        "forge_hr_upscaler": "R-ESRGAN 4x+",
        "default_width": 512,
        "default_height": 512,
        "default_steps": 20,
        "default_cfg": 7,
        "timeout_seconds": 180,
        "forge_clip_skip": 1,
        "fullbody_ref_denoise": 0.88,
        "character_lock_weight": 0.65,
        "adetailer_denoise": 0.4,
        "character_consistency": "light",
        "auto_launch_if_offline": False,
        "forge_restore_faces": False,
        "forge_tiling": False,
        "fullbody_use_face_ref": True,
        "adetailer_enable": False,
        "adetailer_on_face": False,
        "adetailer_on_fullbody": False,
        "adetailer_use_face_ref": False,
        "auto_generate_npc_portraits": False,
        "lora_dirs": [],
        "checkpoint_dirs": [],
    }

    # Client: no checked LoRAs (reload / list not hydrated) + hires toggle flush
    patch = simulate_product_flush_patch(checked_loras=[])
    print("client hires-only flush patch:", patch)

    try:
        after = apply_server_patch(seed_cfg, patch)
    except Exception as e:
        print(f"FAIL harness: server apply error: {e}", file=sys.stderr)
        return 2

    after_loras = after.get("forge_active_loras")
    print("seed forge_active_loras:", seed_loras)
    print("after forge_active_loras:", after_loras)
    print("after forge_enable_hr:", after.get("forge_enable_hr"))

    wiped = after_loras == [] or after_loras is None
    if not wiped:
        # Server rejected empty wipe somehow — not this bug class
        print("NOTE: server did not clear LoRAs for empty list patch")

    product_wipes = (
        flags["always_posts_loras"]
        and not flags["has_config_wins_or_omit"]
        and flags["collect_returns_empty"]
        and not flags["render_hydrates_config"]
        and wiped
    )

    # Desired invariant (correctness): hires-only quality flush with empty UI
    # collect must not clear a non-empty saved forge_active_loras stack.
    if product_wipes:
        print(
            "FAIL: quality flush always POSTs collectSetupLoras() (empty when no DOM checks); "
            "renderSetupLoraList does not hydrate from imageConfig.forge_active_loras; "
            f"update_image_config applied forge_active_loras=[] and wiped seed stack "
            f"({len(seed_loras)} LoRAs) while still applying hires fields."
        )
        return 1

    if wiped and flags["always_posts_loras"] and not flags["has_config_wins_or_omit"]:
        print("FAIL: empty-collect wipe still reachable (server accepted []; no client guard)")
        return 1

    print("OK: empty-collect quality flush does not wipe saved forge_active_loras")
    return 0


if __name__ == "__main__":
    sys.exit(main())
