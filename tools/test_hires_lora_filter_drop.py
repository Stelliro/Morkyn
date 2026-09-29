"""Prove: LoRA filter / 120-cap re-render drops selected LoRAs from collect.

Bug class (correctness-lora-filter-drop):
  renderSetupLoraList captures live checks (or hydrates from
  imageConfig.forge_active_loras), then rebuilds #setupArtLoraList from
  filter + slice(0, 120) only. Selected names that miss the filter, sit
  past the cap, or are absent from the current catalog are not re-emitted
  as inputs. collectSetupLoras reads only live checkboxes.
  _flushArtQualitySettings POSTs collect when any data-lora-name input
  exists (loraUiReady). A hires/quality persist after filter therefore
  wipes stack members the user did not uncheck.

  Empty-filter (zero matching rows) currently destroys all checkboxes, so
  loraUiReady is false and the empty-collect omit path protects that one
  case. Partial filter and the 120-cap do not.

Contradiction: renderSetupLoraList comments say preserve checks / do not
wipe the saved stack; collect is the source for quality flush + generate.

This harness (CPU parse + logic sim, no Forge / no server):
  1) Static-checks renderSetupLoraList for offlist stash or pin-selected
     so names not in the filtered slice remain collectable.
  2) Simulates render → collect → flush patch and observes wipe.

Exit 0 = invariant holds (off-filter / off-cap selected survive collect)
Exit 1 = drop path still present (bug proven)
Exit 2 = harness/setup error
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "static" / "app.js"


def _fn_body(text: str, sig: str, window: int = 8000) -> str | None:
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


def check_static(render: str, collect: str, flush: str) -> dict:
    has_filter = bool(re.search(r"filter\s*=\s*\"\"|const\s+q\s*=", render))
    has_cap = bool(re.search(r"\.slice\s*\(\s*0\s*,\s*120\s*\)", render))
    # Off-list stash: selected names not in the visible slice stay as inputs.
    has_offlist = bool(
        re.search(
            r"loraOfflistStash|data-lora-offlist|hiddenSelected|offlist",
            render,
            re.I,
        )
    )
    # Pin selected catalog rows before the 120-cap so cap cannot hide checks.
    has_pin_selected = bool(
        re.search(
            r"selected(Matched|Rows|FromCatalog)|selected\.has\s*\([^)]+\)[\s\S]{0,400}slice\s*\(\s*0\s*,\s*120",
            render,
            re.I,
        )
    )
    # Early empty rebuild that returns without emitting selected as data-lora-name.
    early_empty = bool(
        re.search(
            r"if\s*\(\s*!items\.length\s*\)\s*\{[\s\S]{0,400}?innerHTML[\s\S]{0,200}?return",
            render,
        )
    )
    early_empty_ignores_selected = early_empty and not bool(
        re.search(
            r"if\s*\(\s*!items\.length\s*&&\s*!hiddenSelected",
            render,
        )
        or re.search(
            r"if\s*\(\s*!items\.length\s*&&\s*![\w]*offlist",
            render,
            re.I,
        )
        or re.search(
            r"if\s*\(\s*!items\.length\s*&&\s*![\w]*hidden",
            render,
            re.I,
        )
    )
    collect_dom_only = bool(
        re.search(r"input\[data-lora-name\]:checked", collect)
    ) and not bool(
        re.search(r"imageConfig\s*\??\.\s*forge_active_loras", collect)
    )
    flush_posts_when_ui_ready = bool(
        re.search(
            r"if\s*\(\s*loras\.length\s*\|\|\s*loraUiReady\s*\)[\s\S]{0,80}forge_active_loras",
            flush,
        )
    ) or bool(re.search(r"forge_active_loras\s*:\s*loras", flush))
    preserves = has_offlist and not early_empty_ignores_selected
    return {
        "has_filter": has_filter,
        "has_cap": has_cap,
        "has_offlist": has_offlist,
        "has_pin_selected": has_pin_selected,
        "early_empty_ignores_selected": early_empty_ignores_selected,
        "collect_dom_only": collect_dom_only,
        "flush_posts_when_ui_ready": flush_posts_when_ui_ready,
        "preserves_offlist_selected": preserves,
    }


def simulate_current_product_render_collect(
    catalog: list[str],
    selected: list[str],
    filter_q: str,
    *,
    cap: int = 120,
    preserve_offlist: bool,
    pin_selected: bool,
) -> list[str]:
    """Mirror renderSetupLoraList → collectSetupLoras checkbox set."""
    q = filter_q.lower().strip()
    selected_set = list(selected)
    if pin_selected:
        pinned = [n for n in selected_set if n in catalog]
        rest = [n for n in catalog if (not q or q in n.lower()) and n not in pinned]
        items = (pinned + rest)[:cap]
    else:
        items = [n for n in catalog if not q or q in n.lower()][:cap]
    shown = set(items)
    collected = [n for n in selected_set if n in shown]
    if preserve_offlist:
        for n in selected_set:
            if n not in collected:
                collected.append(n)
    elif not items:
        # Product early-return: innerHTML empty message, no checkboxes.
        collected = []
    return collected


def simulate_flush_patch(collected: list[str], config_stack: list[str]) -> dict:
    """Mirror _flushArtQualitySettings LoRA patch rules."""
    lora_ui_ready = bool(collected) or True  # partial filter still has rows
    if not collected and not lora_ui_ready:
        return {"forge_enable_hr": True}
    # Partial filter: list has inputs (matching rows) → UI ready, POST collect.
    if collected or lora_ui_ready:
        return {"forge_enable_hr": True, "forge_active_loras": list(collected)}
    return {"forge_enable_hr": True}


def main() -> int:
    if not APP_JS.is_file():
        print("FAIL harness: static/app.js missing", file=sys.stderr)
        return 2
    text = APP_JS.read_text(encoding="utf-8")
    render = _fn_body(text, "function renderSetupLoraList", window=9000)
    collect = _fn_body(text, "function collectSetupLoras", window=2500)
    flush = _fn_body(text, "async function _flushArtQualitySettings", window=6000)
    if not render or not collect or not flush:
        missing = [
            n
            for n, b in (
                ("renderSetupLoraList", render),
                ("collectSetupLoras", collect),
                ("_flushArtQualitySettings", flush),
            )
            if not b
        ]
        print(f"FAIL harness: missing {', '.join(missing)}", file=sys.stderr)
        return 2

    flags = check_static(render, collect, flush)
    print("=== correctness-lora-filter-drop ===")
    print("static flags:", flags)

    catalog = [f"lora_{i:03d}" for i in range(140)]
    catalog[0] = "character_lock_v1"
    catalog[1] = "detail_tweaker"
    catalog[80] = "age_slider_v2"
    selected = ["character_lock_v1", "detail_tweaker", "age_slider_v2"]

    # Partial filter: only character_lock matches.
    collected_filter = simulate_current_product_render_collect(
        catalog,
        selected,
        "character_lock",
        preserve_offlist=flags["has_offlist"],
        pin_selected=flags["has_pin_selected"],
    )
    patch_filter = {
        "forge_enable_hr": True,
        "forge_active_loras": collected_filter,
    }

    # 120-cap: age_slider_v2 is index 80 — still inside 120 unordered; put a
    # selected name at index 130 so cap drops it unless pinned/stashed.
    catalog[130] = "outfit_lock_xl"
    selected_cap = ["character_lock_v1", "outfit_lock_xl"]
    collected_cap = simulate_current_product_render_collect(
        catalog,
        selected_cap,
        "",
        preserve_offlist=flags["has_offlist"],
        pin_selected=flags["has_pin_selected"],
    )
    patch_cap = {
        "forge_enable_hr": True,
        "forge_active_loras": collected_cap,
    }

    print("partial-filter collect:", collected_filter)
    print("partial-filter patch loras:", patch_filter["forge_active_loras"])
    print("120-cap collect:", collected_cap)
    print("120-cap patch loras:", patch_cap["forge_active_loras"])

    filter_wiped = "detail_tweaker" not in collected_filter or "age_slider_v2" not in collected_filter
    cap_wiped = "outfit_lock_xl" not in collected_cap
    product_drops = (
        flags["has_filter"]
        and flags["has_cap"]
        and flags["collect_dom_only"]
        and flags["flush_posts_when_ui_ready"]
        and not flags["preserves_offlist_selected"]
        and (filter_wiped or cap_wiped or flags["early_empty_ignores_selected"])
    )

    if product_drops or filter_wiped or cap_wiped:
        print(
            "FAIL: renderSetupLoraList filter/120-cap rebuild drops selected LoRAs "
            "from collectSetupLoras; quality flush POSTs the partial stack "
            f"(filter_wiped={filter_wiped}, cap_wiped={cap_wiped}, "
            f"early_empty_ignores_selected={flags['early_empty_ignores_selected']}, "
            f"has_offlist={flags['has_offlist']}, has_pin_selected={flags['has_pin_selected']})."
        )
        return 1

    if not flags["has_offlist"] and not flags["has_pin_selected"]:
        print("FAIL: no offlist stash and no pin-selected-before-cap in renderSetupLoraList")
        return 1

    print("OK: off-filter / off-cap selected LoRAs remain collectable after re-render")
    return 0


if __name__ == "__main__":
    sys.exit(main())
