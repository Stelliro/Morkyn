"""Prove: mid-edit dirty flag is cleared by an in-flight _flushArtQualitySettings.

Bug class (correctness-2):
  User types hr_scale 1.5 → 2.5 across the debounce/POST window.
  Flush captured scale=1.5 before await fetch; on res.ok it always sets
  dataset.dirty='0' and writes the mid-flight patch into imageConfig.
  resolveArtHiresSettings then sees dirty=0 + imageConfig and prefers config
  over live DOM → gen flush sends forge_hr_scale 1.5 instead of DOM 2.5.

This harness:
  1) Static-checks app.js for unconditional dirty clear after POST success.
  2) Simulates resolveArtHiresSettings + flush success merge (no browser).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_JS = ROOT / "static" / "app.js"


def _flush_fn_body(text: str) -> str | None:
    """Extract _flushArtQualitySettings body; ignore default-param object braces."""
    idx = text.find("async function _flushArtQualitySettings")
    if idx < 0:
        return None
    window = text[idx : idx + 4000]
    # Signature uses ({ silent = true } = {}) { ... } — find body '{' after ')'.
    paren = window.find("(")
    if paren < 0:
        return window
    depth = 0
    close_paren = -1
    for i, ch in enumerate(window[paren:], paren):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                close_paren = i
                break
    if close_paren < 0:
        return window
    body_open = window.find("{", close_paren)
    if body_open < 0:
        return window
    depth = 0
    for i, ch in enumerate(window[body_open:], body_open):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return window[: i + 1]
    return window


def check_static_unconditional_dirty_clear(text: str, fails: list[str]) -> None:
    body = _flush_fn_body(text)
    if not body:
        fails.append("_flushArtQualitySettings missing")
        return

    # After res.ok, must not blindly assign dirty='0' without re-checking mid-flight edits.
    # Acceptable patterns (any one):
    #  - re-read dirty after await and skip clear if still dirty with newer DOM
    #  - compare live DOM/readArtHiresControls() to patch before clear
    #  - generation/token counter that invalidates stale flushes
    # Fail pattern: unconditional bar.dataset.dirty = "0" on success path.

    success = re.search(r"if\s*\(\s*res\.ok\s*\)\s*\{", body)
    if not success:
        fails.append("_flushArtQualitySettings missing res.ok success branch")
        return
    success_body = body[success.start() :]

    # Find dirty clears in success path
    clears = list(
        re.finditer(
            r"""(?:bar|el|qualityBar)?\.?dataset\.dirty\s*=\s*["']0["']""",
            success_body,
        )
    )
    if not clears:
        # Fixed: no blind clear, or clear lives elsewhere with guards — static ok
        return

    for clr in clears:
        # Look backward ~400 chars for a guard that compares DOM / re-checks dirty / token
        pre = success_body[max(0, clr.start() - 450) : clr.start()]
        # Strip comments for guard detection
        pre_code = re.sub(r"//.*?$", "", pre, flags=re.M)
        pre_code = re.sub(r"/\*.*?\*/", "", pre_code, flags=re.S)

        has_dom_match = bool(
            re.search(
                r"readArtHiresControls|hrScale\s*===|forge_hr_scale|matchesSaved|domMatches|sameAsPatch",
                pre_code,
            )
        )
        # Guard like: if (bar.dataset.dirty !== '1') or if still dirty skip
        has_dirty_recheck = bool(
            re.search(
                r"""dataset\.dirty\s*(?:===|!==|==|!=)\s*["'][01]["']""",
                pre_code,
            )
        )
        has_token = bool(
            re.search(r"flush(Id|Token|Gen|Generation)|_artQualityFlush", pre_code, re.I)
        )
        # Conditional clear: if (...) bar.dataset.dirty = '0' where condition is not just `bar`
        line_start = success_body.rfind("\n", 0, clr.start()) + 1
        line = success_body[line_start : success_body.find("\n", clr.start())]
        line_code = line.split("//", 1)[0].strip()
        # `if (bar) bar.dataset.dirty = "0"` is NOT a real guard against mid-edit
        only_bar_truthy = bool(
            re.match(
                r"""if\s*\(\s*(bar|el|qualityBar)\s*\)\s*(bar|el|qualityBar)\.dataset\.dirty\s*=\s*["']0["']""",
                line_code,
            )
        )
        bare_assign = bool(
            re.match(
                r"""(?:bar|el|qualityBar)\.dataset\.dirty\s*=\s*["']0["']""",
                line_code,
            )
        )

        if only_bar_truthy or (bare_assign and not (has_dom_match or has_dirty_recheck or has_token)):
            fails.append(
                "_flushArtQualitySettings clears dataset.dirty='0' unconditionally after "
                "successful POST (mid-flight edits lose DOM authority; comment claims "
                "conditional clear but code does not re-check dirty/DOM/token)"
            )
            return
        if not (has_dom_match or has_dirty_recheck or has_token or not (only_bar_truthy or bare_assign)):
            fails.append(
                "_flushArtQualitySettings dirty clear lacks DOM-match / dirty recheck / flush-token guard"
            )
            return


def simulate_race() -> list[str]:
    """Port resolve + flush success merge; return failure strings if race loses latest DOM."""
    fails: list[str] = []

    def cfg_hires_on(cfg: dict | None) -> bool:
        if not cfg:
            return False
        v = cfg.get("forge_enable_hr")
        return v is True or v == 1 or v == "true"

    def resolve(dom: dict, dirty: bool, image_config: dict | None) -> dict:
        if dirty or not image_config:
            return {**dom, "source": "dom-dirty" if dirty else "dom"}
        hr_scale = dom["hrScale"]
        if image_config.get("forge_hr_scale") is not None:
            n = float(image_config["forge_hr_scale"])
            if n >= 1:
                hr_scale = max(1.0, min(4.0, n))
        return {
            "enableHr": cfg_hires_on(image_config),
            "hrScale": hr_scale,
            "hrDenoise": dom["hrDenoise"],
            "hrSteps": dom["hrSteps"],
            "hrUpscaler": image_config.get("forge_hr_upscaler") or dom["hrUpscaler"],
            "source": "config",
        }

    # --- timeline matching app.js ---
    image_config = {
        "forge_enable_hr": True,
        "forge_hr_scale": 1.5,
        "forge_denoising_strength": 0.45,
        "forge_hr_second_pass_steps": 0,
        "forge_hr_upscaler": "R-ESRGAN 4x+",
    }
    # User has typed 1.5, dirty, flush starts (resolve captures 1.5)
    dom = {
        "enableHr": True,
        "hrScale": 1.5,
        "hrDenoise": 0.45,
        "hrSteps": 0,
        "hrUpscaler": "R-ESRGAN 4x+",
    }
    dirty = True
    resolved = resolve(dom, dirty, image_config)
    enable_hr = resolved["enableHr"]
    hr_scale = resolved["hrScale"]
    hr_denoise = resolved["hrDenoise"]
    hr_steps = resolved["hrSteps"]
    hr_upscaler = resolved["hrUpscaler"]
    assert hr_scale == 1.5

    # await fetch in flight… user continues typing → DOM 2.5, dirty re-set
    dom["hrScale"] = 2.5
    dirty = True
    # mirrorArtHiresControlsToImageConfig would push 2.5 into imageConfig
    image_config["forge_hr_scale"] = 2.5

    # Fixed res.ok path: re-read DOM vs flushed snapshot; only merge/clear when match.
    flushed_snap = {
        "enableHr": enable_hr,
        "hrScale": hr_scale,
        "hrDenoise": hr_denoise,
        "hrSteps": hr_steps,
        "hrUpscaler": hr_upscaler,
    }
    dom_matches = (
        bool(dom["enableHr"]) == bool(flushed_snap["enableHr"])
        and float(dom["hrScale"]) == float(flushed_snap["hrScale"])
        and float(dom["hrDenoise"]) == float(flushed_snap["hrDenoise"])
        and int(dom["hrSteps"]) == int(flushed_snap["hrSteps"])
        and str(dom["hrUpscaler"]) == str(flushed_snap["hrUpscaler"])
    )
    if dom_matches:
        image_config = {
            **image_config,
            "forge_enable_hr": enable_hr,
            "forge_hr_scale": hr_scale,
            "forge_denoising_strength": hr_denoise,
            "forge_hr_second_pass_steps": hr_steps,
            "forge_hr_upscaler": hr_upscaler,
        }
        dirty = False
    else:
        # Keep live mirror; leave dirty so resolve prefers DOM
        image_config = {
            **image_config,
            "forge_enable_hr": dom["enableHr"],
            "forge_hr_scale": dom["hrScale"],
            "forge_denoising_strength": dom["hrDenoise"],
            "forge_hr_second_pass_steps": dom["hrSteps"],
            "forge_hr_upscaler": dom["hrUpscaler"],
        }
        dirty = True

    # Immediate Generate uses artHiresRequestFields → resolveArtHiresSettings
    out = resolve(dom, dirty, image_config)
    if out["hrScale"] != 2.5:
        fails.append(
            f"RACE: after mid-edit during flush, resolve/gen would send forge_hr_scale="
            f"{out['hrScale']} (source={out['source']}) but live DOM is 2.5"
        )
    if out["source"] != "dom-dirty":
        fails.append(
            f"RACE: expected DOM authority (dom-dirty) after mid-edit; got source={out['source']}"
        )
    return fails


def main() -> int:
    text = APP_JS.read_text(encoding="utf-8")
    fails: list[str] = []

    check_static_unconditional_dirty_clear(text, fails)
    fails.extend(simulate_race())

    # resolve must prefer DOM when dirty (sanity — if this breaks, race analysis invalid)
    if "dataset?.dirty === \"1\"" not in text and 'dataset.dirty === "1"' not in text:
        fails.append("resolveArtHiresSettings dirty check missing (cannot trust race model)")
    idx = text.find("function resolveArtHiresSettings")
    if idx < 0:
        fails.append("resolveArtHiresSettings missing")
    else:
        body = text[idx : idx + 900]
        if 'source: dirty ? "dom-dirty"' not in body and 'source: "dom-dirty"' not in body:
            # still OK if it returns DOM when dirty without that exact string
            if "if (dirty" not in body and "if(dirty" not in body:
                fails.append("resolveArtHiresSettings does not branch on dirty")

    if fails:
        print("FAIL: hires dirty race (correctness-2)")
        for f in fails:
            print(" -", f)
        return 1
    print("OK: hires dirty race not present (flush guards dirty clear)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
