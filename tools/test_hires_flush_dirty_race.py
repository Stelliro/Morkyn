"""Regression: _flushArtQualitySettings must not clear dirty if DOM changed mid-flight.

Bug class (robustness-2):
  1) User edits scale → dirty=1 → debounced flush captures scale=1.5 and awaits fetch
  2) User edits scale again mid-flight → DOM=2.0, dirty=1, new debounce scheduled
  3) First flush res.ok → force-merges flush-time 1.5 into imageConfig AND sets dirty='0'
  4) dirty guard on loadImageConfig / syncArtQualityControlsFromConfig is now off
     → stale scale/denoise/enable can wipe mid-edit DOM values

Comment above the clear claims a conditional clear; code must actually gate on
DOM still matching the flushed snapshot (or a generation/token id).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_JS = ROOT / "static" / "app.js"


def _extract_flush_body(text: str) -> str:
    idx = text.find("async function _flushArtQualitySettings")
    if idx < 0:
        return ""
    # Enough span to cover success path + network-fail recovery + closing of function.
    return text[idx : idx + 6000]


def _success_block(body: str) -> str:
    """Slice from `if (res.ok)` through the end of that block (best-effort)."""
    m = re.search(r"if\s*\(\s*res\.ok\s*\)\s*\{", body)
    if not m:
        return ""
    start = m.start()
    # Brace match from the opening of res.ok
    i = body.find("{", m.start())
    depth = 0
    for j in range(i, len(body)):
        if body[j] == "{":
            depth += 1
        elif body[j] == "}":
            depth -= 1
            if depth == 0:
                return body[start : j + 1]
    return body[start:]


def test_static_unconditional_dirty_clear() -> list[str]:
    fails: list[str] = []
    text = APP_JS.read_text(encoding="utf-8")
    body = _extract_flush_body(text)
    if not body:
        return ["_flushArtQualitySettings missing"]

    success = _success_block(body)
    if not success:
        return ["_flushArtQualitySettings has no res.ok success path"]

    # Strip line comments for logic checks
    code_lines = [ln.split("//", 1)[0] for ln in success.splitlines()]
    code = "\n".join(code_lines)

    if "dataset.dirty" not in code and "dataset?.dirty" not in code:
        fails.append("success path never touches dataset.dirty (expected gated clear)")
        return fails

    # Unconditional assignment dirty = "0" (or '0') is the bug.
    unconditional = re.search(
        r"""(?:bar|qualityBar|el)\s*\.\s*dataset\s*\.\s*dirty\s*=\s*['"]0['"]""",
        code,
    )
    if unconditional:
        # Allowed only if guarded by a DOM-vs-snapshot / generation check nearby.
        # Look for comparison of flushed values or dirty still matching before clear.
        guard_patterns = [
            r"resolveArtHiresSettings\s*\(",
            r"readArtHiresControls\s*\(",
            r"hrScale\s*===",
            r"forge_hr_scale",
            r"flush(ed)?(Token|Gen|Id|Snapshot|Seq)",
            r"dirty\s*===?\s*['\"]1['\"]",
            r"dataset\.dirty\s*===?\s*['\"]1['\"]",
            r"matchesFlush",
            r"domMatches",
            r"stillMatches",
        ]
        # Window: lines before the dirty clear assignment
        pre = code[: unconditional.start()]
        # Require an if-condition that references match/DOM/dirty before the clear
        has_guard = False
        # if (...something...) { ... dirty = "0"
        if_blocks = list(
            re.finditer(
                r"if\s*\(([^)]{0,400})\)\s*\{[^}]{0,400}dataset\.dirty\s*=\s*['\"]0['\"]",
                code,
                flags=re.S,
            )
        )
        for ibm in if_blocks:
            cond = ibm.group(1)
            if any(re.search(p, cond, re.I) for p in guard_patterns):
                # Conditional clear is OK only if condition is not trivially always-true
                if re.fullmatch(r"\s*bar\s*", cond) or re.fullmatch(r"\s*true\s*", cond):
                    continue
                # `if (bar) bar.dataset.dirty = "0"` is NOT a semantic guard
                if re.fullmatch(r"\s*bar\s*", cond.strip()):
                    continue
                has_guard = True
        # Also accept: if (bar && <guard>) bar.dataset.dirty = "0"
        assign_ctx = code[max(0, unconditional.start() - 200) : unconditional.end() + 20]
        if re.search(
            r"if\s*\(\s*bar\s*&&\s*[^)]*(dirty|match|flush|hrScale|resolve|readArt)",
            assign_ctx,
            re.I,
        ):
            has_guard = True

        if not has_guard:
            fails.append(
                "_flushArtQualitySettings success path unconditionally sets "
                "dataset.dirty='0' without checking DOM still matches flushed "
                "snapshot (mid-flight edit race)"
            )

    # Force-merge of flush-time hires fields must not run when DOM diverged.
    force_merge = (
        "forge_hr_scale: hrScale" in success
        or "forge_hr_scale:hrScale" in re.sub(r"\s+", "", success)
    )
    if force_merge and not any(
        re.search(p, code, re.I)
        for p in (
            r"resolveArtHiresSettings\s*\(\s*\)",
            r"readArtHiresControls\s*\(\s*\)",
            r"domMatches|matchesFlush|stillMatches",
        )
    ):
        # Pre-fetch resolve is expected; post-await re-check is what matters.
        after_await = code
        # If the only resolveArtHiresSettings is BEFORE the fetch await, flag force-merge risk.
        # We check: no second resolve/read after `await fetch` / `await res.json`
        post_json = re.split(r"await\s+res\.json\s*\(|await\s+fetch\s*\(\s*[\"']/api/image-config", body, maxsplit=1)
        if len(post_json) >= 2:
            after = post_json[-1]
            after_code = "\n".join(ln.split("//", 1)[0] for ln in after.splitlines())
            recheck = re.search(
                r"resolveArtHiresSettings\s*\(|readArtHiresControls\s*\(|domMatches|matchesFlush",
                after_code,
            )
            if not recheck and "dataset.dirty" in after_code:
                # force merge of closed-over hrScale after network wait without recheck
                if re.search(r"forge_hr_scale\s*:\s*hrScale", after_code):
                    fails.append(
                        "success path force-merges closed-over hrScale into imageConfig "
                        "after network wait without re-reading DOM / dirty state"
                    )

    return fails


def test_simulated_midflight_race() -> list[str]:
    """Logical model of fixed gated success path (DOM-match before dirty clear)."""
    fails: list[str] = []

    def gated_flush_success(flushed: dict, image_config: dict, dom: dict, dirty: str):
        # Only clear dirty + force-merge when DOM still matches flushed snapshot
        matches = (
            bool(dom["enableHr"]) == bool(flushed["enableHr"])
            and float(dom["hrScale"]) == float(flushed["hrScale"])
            and float(dom["hrDenoise"]) == float(flushed["hrDenoise"])
            and int(dom["hrSteps"]) == int(flushed["hrSteps"])
            and str(dom["hrUpscaler"]) == str(flushed["hrUpscaler"])
        )
        if not matches:
            # Keep live DOM authoritative in memory; leave dirty set
            live = {
                **image_config,
                "forge_enable_hr": dom["enableHr"],
                "forge_hr_scale": dom["hrScale"],
                "forge_denoising_strength": dom["hrDenoise"],
                "forge_hr_second_pass_steps": dom["hrSteps"],
                "forge_hr_upscaler": dom["hrUpscaler"],
            }
            return live, "1"
        merged = {
            **image_config,
            "forge_enable_hr": flushed["enableHr"],
            "forge_hr_scale": flushed["hrScale"],
            "forge_denoising_strength": flushed["hrDenoise"],
            "forge_hr_second_pass_steps": flushed["hrSteps"],
            "forge_hr_upscaler": flushed["hrUpscaler"],
        }
        return merged, "0"

    flushed = {
        "enableHr": True,
        "hrScale": 1.5,
        "hrDenoise": 0.45,
        "hrSteps": 0,
        "hrUpscaler": "R-ESRGAN 4x+",
    }
    # Mid-flight user edit after capture, before resolve
    dom_mid = {
        "enableHr": True,
        "hrScale": 2.0,
        "hrDenoise": 0.55,
        "hrSteps": 12,
        "hrUpscaler": "4x-UltraSharp",
    }
    image_config = {
        "forge_enable_hr": True,
        "forge_hr_scale": 2.0,  # mirror already pushed live DOM
        "forge_denoising_strength": 0.55,
        "forge_hr_second_pass_steps": 12,
        "forge_hr_upscaler": "4x-UltraSharp",
    }

    good_cfg, good_dirty = gated_flush_success(flushed, dict(image_config), dom_mid, "1")

    if good_dirty != "1":
        fails.append("simulation: gated path should keep dirty=1 when DOM diverged")
    if float(good_cfg["forge_hr_scale"]) != 2.0:
        fails.append("simulation: gated path should keep live hrScale=2.0")
    if good_cfg.get("forge_hr_upscaler") != "4x-UltraSharp":
        fails.append("simulation: gated path should keep live upscaler")

    # Consequence: with dirty kept, syncArtQualityControlsFromConfig preserves DOM.
    def sync_from_config(cfg: dict, dirty: str, dom: dict) -> dict:
        if dirty == "1":
            return dict(dom)  # preserve
        return {
            "enableHr": cfg["forge_enable_hr"],
            "hrScale": cfg["forge_hr_scale"],
            "hrDenoise": cfg["forge_denoising_strength"],
            "hrSteps": cfg["forge_hr_second_pass_steps"],
            "hrUpscaler": cfg["forge_hr_upscaler"],
        }

    preserved = sync_from_config(good_cfg, good_dirty, dom_mid)
    if float(preserved["hrScale"]) != 2.0 or preserved["hrUpscaler"] != "4x-UltraSharp":
        fails.append(
            f"MID-FLIGHT WIPE: after late flush ok, sync would set scale="
            f"{preserved['hrScale']} upscaler={preserved['hrUpscaler']!r} "
            f"(user had scale={dom_mid['hrScale']} upscaler={dom_mid['hrUpscaler']!r}); "
            f"dirty={good_dirty!r}"
        )

    # Matching DOM path still clears dirty and merges flush snapshot.
    matched_cfg, matched_dirty = gated_flush_success(flushed, dict(image_config), dict(flushed), "1")
    if matched_dirty != "0":
        fails.append("simulation: matching DOM should clear dirty after successful flush")
    if float(matched_cfg["forge_hr_scale"]) != 1.5:
        fails.append("simulation: matching DOM should merge flushed hrScale")

    return fails


def main() -> int:
    fails: list[str] = []
    fails.extend(test_static_unconditional_dirty_clear())
    fails.extend(test_simulated_midflight_race())

    if fails:
        print("FAIL: hires flush dirty mid-flight race")
        for f in fails:
            print(" -", f)
        return 1
    print("OK: flush success gates dirty clear / no mid-flight wipe")
    return 0


if __name__ == "__main__":
    sys.exit(main())
