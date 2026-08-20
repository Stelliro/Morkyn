"""Regression: hires quality bar must not re-sync from stale config on input events.

Reproduces the bug class:
  document input on #setupArtHrScale → syncArtQualityControlsFromConfig()
  which overwrote the user's in-progress value from imageConfig.

Also checks loadImageConfig / flush paths don't full-sync while dirty.

Config-wins (resolveArtHiresSettings):
  Quality-bar checkbox defaults unchecked in HTML. Before loadImageConfig paints
  saved Hires ON, a flush/gen that trusts DOM alone writes forge_enable_hr=false.
  resolveArtHiresSettings must: not-dirty + imageConfig → source 'config' and
  enableHr from _cfgHiresOn(imageConfig); dirty → fromDom; artHiresRequestFields
  builds forge_enable_hr from resolveArtHiresSettings().

Dirty race (_flushArtQualitySettings):
  After successful POST, must not set dataset.dirty='0' blindly — mid-flight
  input/change can re-dirty the bar; clearing drops DOM authority so resolve
  prefers stale imageConfig (forge_hr_scale / denoise / upscaler).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_JS = ROOT / "static" / "app.js"


def _fn_body(text: str, sig: str, max_chars: int = 4000) -> str | None:
    """Return approximate function body starting at `sig` (brace-balanced).

    Skips braces inside the parameter list (e.g. `{ silent = true } = {}`)
    by locating the matching `)` after `sig`, then the body `{`.
    """
    idx = text.find(sig)
    if idx < 0:
        return None
    # Walk from sig to find the parameter-list close paren at depth 0,
    # then the opening body brace (handles default-object params).
    paren = text.find("(", idx)
    if paren < 0 or paren > idx + len(sig) + 80:
        # No params — fall back to first brace
        brace = text.find("{", idx)
    else:
        depth = 0
        i = paren
        brace = -1
        while i < len(text) and i < paren + 500:
            ch = text[i]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    brace = text.find("{", i + 1)
                    break
            i += 1
        if brace < 0:
            brace = text.find("{", idx)
    if brace < 0:
        return None
    depth = 0
    i = brace
    while i < len(text) and i < brace + max_chars:
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[idx : i + 1]
        i += 1
    return text[idx : brace + max_chars]


def check_legacy_ui_reset(text: str) -> list[str]:
    """Original scan: input/change/flush/dirty patterns only (no resolveArtHiresSettings)."""
    fails: list[str] = []

    # 1) No input-handler that pairs hires field ids with syncArtQualityControlsFromConfig
    input_blocks = re.findall(
        r'document\.addEventListener\(\s*["\']input["\']\s*,\s*\(event\)\s*=>\s*\{(.*?)\n\}\);',
        text,
        flags=re.S,
    )
    if not input_blocks:
        fails.append("could not find document input listener")
    for block in input_blocks:
        if "setupArtHrScale" not in block:
            continue
        code_lines = [line.split("//", 1)[0] for line in block.splitlines()]
        code = "\n".join(code_lines)
        if "setupArtHrScale" in code and "syncArtQualityControlsFromConfig(" in code:
            fails.append(
                "input listener still calls syncArtQualityControlsFromConfig while handling setupArtHr*"
            )

    # 2) change listener for hires must mirror, not sync-from-config
    change_blocks = re.findall(
        r'document\.addEventListener\(\s*["\']change["\']\s*,\s*\(event\)\s*=>\s*\{(.*?)\n\}\);',
        text,
        flags=re.S,
    )
    hires_change_ok = False
    for block in change_blocks:
        if "setupArtHrUpscaler" in block and "setupArtEnableHr" in block:
            code_lines = [ln.split("//", 1)[0] for ln in block.splitlines()]
            code = "\n".join(code_lines)
            if "mirrorArtHiresControlsToImageConfig" in code:
                hires_change_ok = True
            if re.search(r"syncArtQualityControlsFromConfig\s*\(", code):
                fails.append("change listener for hires still calls syncArtQualityControlsFromConfig")
    if not hires_change_ok:
        fails.append("change listener missing mirrorArtHiresControlsToImageConfig for hires controls")

    # 3) flush must not call loadImageConfig() (full re-apply race)
    idx = text.find("async function _flushArtQualitySettings")
    if idx < 0:
        fails.append("_flushArtQualitySettings missing")
    else:
        body = text[idx : idx + 2500]
        if re.search(r"\bawait\s+loadImageConfig\s*\(", body):
            fails.append("_flushArtQualitySettings still awaits loadImageConfig (resync race)")
        if "forge_hr_upscaler" not in body:
            fails.append("_flushArtQualitySettings does not patch forge_hr_upscaler")

    # 4) syncArtQualityControlsFromConfig must honor dirty flag
    idx = text.find("function syncArtQualityControlsFromConfig")
    if idx < 0:
        fails.append("syncArtQualityControlsFromConfig missing")
    else:
        body = text[idx : idx + 1800]
        if 'dataset?.dirty === "1"' not in body and 'dataset.dirty === "1"' not in body:
            fails.append("syncArtQualityControlsFromConfig does not check quality bar dirty flag")
        if "preserveDom: true" not in body:
            fails.append("syncArtQualityControlsFromConfig dirty/preserve path should use preserveDom: true")

    # 5) loadImageConfig must not always clobber dirty bar
    idx = text.find("async function loadImageConfig")
    if idx < 0:
        fails.append("loadImageConfig missing")
    else:
        body = text[idx : idx + 1800]
        if "qualityDirty" not in body and "dataset?.dirty" not in body:
            fails.append("loadImageConfig does not protect dirty quality bar")

    return fails


def check_flush_dirty_not_blind(text: str) -> list[str]:
    """Flush success must not clear dirty blindly after await POST (mid-edit race)."""
    fails: list[str] = []
    flush_body = _fn_body(text, "async function _flushArtQualitySettings", max_chars=5000)
    if not flush_body:
        return fails
    ok_m = re.search(r"if\s*\(\s*res\.ok\s*\)\s*\{", flush_body)
    if not ok_m:
        return fails
    success = flush_body[ok_m.start() :]
    for line in success.splitlines():
        code = line.split("//", 1)[0]
        if not re.search(r"""dataset\.dirty\s*=\s*["']0["']""", code):
            continue
        # Accept clear only if same line has a real guard (DOM match / dirty recheck / token).
        # `if (bar) bar.dataset.dirty = "0"` is NOT a mid-edit guard.
        if re.search(
            r"readArtHiresControls|domMatch|flush(Id|Token|Gen)|dirty\s*===",
            code,
        ):
            continue
        if re.search(
            r"""if\s*\(\s*bar\s*\)\s*bar\.dataset\.dirty\s*=\s*["']0["']""",
            code,
        ) or re.match(
            r"""\s*(?:bar|el)\.dataset\.dirty\s*=\s*["']0["']""",
            code,
        ):
            fails.append(
                "_flushArtQualitySettings sets dirty='0' unconditionally after POST "
                "(stale flush can drop mid-edit DOM authority)"
            )
            break
    return fails


def check_config_wins_resolve(text: str) -> list[str]:
    """Config-wins / resolveArtHiresSettings contract (was missing from legacy scan)."""
    fails: list[str] = []

    # _cfgHiresOn must treat true / 1 / "true" as on
    cfg_body = _fn_body(text, "function _cfgHiresOn")
    if not cfg_body:
        fails.append("_cfgHiresOn missing")
    else:
        for needle in (
            "forge_enable_hr === true",
            'forge_enable_hr === "true"',
            "forge_enable_hr === 1",
        ):
            if needle not in cfg_body:
                fails.append(f"_cfgHiresOn missing truthy check: {needle}")

    resolve_body = _fn_body(text, "function resolveArtHiresSettings")
    if not resolve_body:
        fails.append("resolveArtHiresSettings missing")
        return fails

    # Dirty (or no imageConfig) path → DOM / fromDom
    if "readArtHiresControls" not in resolve_body and "fromDom" not in resolve_body:
        fails.append("resolveArtHiresSettings does not read DOM via readArtHiresControls/fromDom")
    if not re.search(r'dataset\??\.dirty\s*===\s*["\']1["\']', resolve_body):
        fails.append("resolveArtHiresSettings does not check quality-bar dirty flag")
    if not re.search(r'source:\s*dirty\s*\?\s*["\']dom-dirty["\']\s*:\s*["\']dom["\']', resolve_body):
        # Accept either ternary source or separate returns with source "dom-dirty"/"dom"
        has_dom_src = (
            'source: "dom-dirty"' in resolve_body
            or "source: 'dom-dirty'" in resolve_body
            or 'source: dirty ? "dom-dirty"' in resolve_body
            or "source: dirty ? 'dom-dirty'" in resolve_body
        )
        if not has_dom_src:
            fails.append(
                "resolveArtHiresSettings dirty/no-config path must return source dom-dirty or dom"
            )

    # Non-dirty + imageConfig → config wins for enableHr via _cfgHiresOn / cfgOn
    if "_cfgHiresOn" not in resolve_body and "cfgOn" not in resolve_body:
        fails.append(
            "resolveArtHiresSettings non-dirty path must use _cfgHiresOn/cfgOn (config wins)"
        )
    if not re.search(r"enableHr:\s*cfgOn", resolve_body) and not re.search(
        r"enableHr:\s*_cfgHiresOn\s*\(", resolve_body
    ):
        fails.append(
            "resolveArtHiresSettings non-dirty path must set enableHr from cfgOn/_cfgHiresOn(imageConfig)"
        )
    if 'source: "config"' not in resolve_body and "source: 'config'" not in resolve_body:
        fails.append("resolveArtHiresSettings non-dirty path must return source 'config'")

    # artHiresRequestFields builds forge_enable_hr from resolveArtHiresSettings
    req_body = _fn_body(text, "function artHiresRequestFields")
    if not req_body:
        fails.append("artHiresRequestFields missing")
    else:
        if "resolveArtHiresSettings" not in req_body:
            fails.append("artHiresRequestFields must call resolveArtHiresSettings")
        if not re.search(r"forge_enable_hr:\s*!!?\s*r\.enableHr", req_body) and not re.search(
            r"forge_enable_hr:\s*!!?\s*.*enableHr", req_body
        ):
            fails.append("artHiresRequestFields must set forge_enable_hr from resolve enableHr")

    # Flush must resolve (not raw DOM checkbox alone)
    flush_body = _fn_body(text, "async function _flushArtQualitySettings", max_chars=5000)
    if flush_body and "resolveArtHiresSettings" not in flush_body:
        fails.append("_flushArtQualitySettings must call resolveArtHiresSettings (not raw DOM only)")

    # imagePayloadFromForm: only name=forge_enable_hr form checkbox, not #setupArtEnableHr
    img_body = _fn_body(text, "function imagePayloadFromForm", max_chars=6000)
    if not img_body:
        fails.append("imagePayloadFromForm missing")
    else:
        if 'input[name="forge_enable_hr"]' not in img_body and "name=\"forge_enable_hr\"" not in img_body:
            fails.append(
                'imagePayloadFromForm must read input[name="forge_enable_hr"] (Images form field)'
            )
        if "#setupArtEnableHr" in img_body or "setupArtEnableHr" in img_body:
            fails.append(
                "imagePayloadFromForm must not use #setupArtEnableHr (quality-bar alone ≠ form field)"
            )

    return fails


def _gut_config_wins(text: str) -> str:
    """Simulate a regression: resolveArtHiresSettings always trusts DOM (wipes saved Hires ON)."""
    body = _fn_body(text, "function resolveArtHiresSettings")
    if not body:
        return text
    gutted = """function resolveArtHiresSettings() {
  const fromDom = readArtHiresControls();
  return {
    enableHr: !!fromDom.enableHr,
    hrScale: fromDom.hrScale,
    hrDenoise: fromDom.hrDenoise,
    hrSteps: fromDom.hrSteps,
    hrUpscaler: fromDom.hrUpscaler,
    source: "dom",
  };
}"""
    return text.replace(body, gutted, 1)


def main() -> int:
    text = APP_JS.read_text(encoding="utf-8")
    fails = (
        check_legacy_ui_reset(text)
        + check_config_wins_resolve(text)
        + check_flush_dirty_not_blind(text)
    )

    # Meta: prove the old scan alone cannot catch a gutted config-wins branch.
    gutted = _gut_config_wins(text)
    if gutted == text:
        fails.append("gap-demo: could not locate resolveArtHiresSettings to gut")
    else:
        legacy_on_gutted = check_legacy_ui_reset(gutted)
        new_on_gutted = check_config_wins_resolve(gutted)
        if legacy_on_gutted:
            fails.append(
                "gap-demo: legacy scan failed on gutted resolveArtHiresSettings "
                f"(unexpected): {legacy_on_gutted}"
            )
        if not new_on_gutted:
            fails.append(
                "gap-demo: config-wins checks did not fail after gutting resolveArtHiresSettings"
            )
        else:
            print(
                "GAP-DEMO OK: legacy scan stays green after gutting config-wins; "
                f"new checks catch: {new_on_gutted[0]}"
            )

    if fails:
        print("FAIL:")
        for f in fails:
            print(" -", f)
        return 1
    print("OK: hires UI reset + resolveArtHiresSettings config-wins covered in static/app.js")
    return 0


if __name__ == "__main__":
    sys.exit(main())
