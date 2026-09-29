"""Prove Simple push skips empty name/world/gear so Start keeps stale values.

Bug class (correctness):
  pushSimpleToForm() always writes hair/face/look/backstory/age (including ""),
  but only writes player_name, world vibe, and starter_equipment when truthy:

    if (name) setFormFieldValue("player_name", name);
    if (world) setWorldStyleSimple(world);
    if (gearText) setFormFieldValue("starter_equipment", gearText);

  After Randomize, the form holds generated name/world/gear. If the user then
  clears #simplePlayerName, #simpleWorld, or removes every #simpleGearList card,
  Start still pushSimpleToForm()s — the empty Simple controls are skipped and
  the playthrough payload keeps the randomized leftovers.

  setWorldStyleSimple also seeds custom_style only when that textarea is empty,
  so a later Simple world edit can leave custom_style stuck on the first vibe
  while world_style_custom already changed (startGame sends both).

This harness:
  1) Static-asserts the truthy-only writes and the empty-only custom_style seed.
  2) Simulates Randomize leftovers vs cleared Simple UI → submitted payload.

Exit 0 only if empty Simple name/world/gear clear the form (bug fixed).
Exit 1 when the skip-empty path is present.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_JS = ROOT / "static" / "app.js"


def _fn_body(text: str, signature: str, max_chars: int = 4000) -> str | None:
    idx = text.find(signature)
    if idx < 0:
        return None
    return text[idx : idx + max_chars]


def _strip_line_comments(block: str) -> str:
    lines = [ln.split("//", 1)[0] for ln in block.splitlines()]
    return "\n".join(lines)


def check_static(text: str) -> list[str]:
    fails: list[str] = []

    push = _fn_body(text, "function pushSimpleToForm()", max_chars=2500)
    if not push:
        fails.append("pushSimpleToForm missing")
        return fails
    pcode = _strip_line_comments(push)

    world_fn = _fn_body(text, "function setWorldStyleSimple(", max_chars=1800)
    if not world_fn:
        fails.append("setWorldStyleSimple missing")
        return fails
    wcode = _strip_line_comments(world_fn)

    # Truthy-only name: if (name) setFormFieldValue("player_name"
    if re.search(
        r'if\s*\(\s*name\s*\)\s*setFormFieldValue\s*\(\s*["\']player_name["\']',
        pcode,
    ):
        fails.append(
            "pushSimpleToForm skips empty #simplePlayerName "
            "(if (name) setFormFieldValue player_name) — randomized name sticks on Start"
        )

    if re.search(r"if\s*\(\s*world\s*\)\s*setWorldStyleSimple\s*\(\s*world\s*\)", pcode):
        fails.append(
            "pushSimpleToForm skips empty #simpleWorld "
            "(if (world) setWorldStyleSimple) — randomized world vibe sticks on Start"
        )

    if re.search(
        r'if\s*\(\s*gearText\s*\)\s*setFormFieldValue\s*\(\s*["\']starter_equipment["\']',
        pcode,
    ):
        fails.append(
            "pushSimpleToForm skips empty Simple gear "
            "(if (gearText) setFormFieldValue starter_equipment) — "
            "removed gear still submitted on Start"
        )

    # After fix: empty Simple values must still be written.
    if 'setFormFieldValue("player_name"' not in pcode and "setFormFieldValue('player_name'" not in pcode:
        fails.append("pushSimpleToForm no longer writes player_name")
    if "setWorldStyleSimple" not in pcode:
        fails.append("pushSimpleToForm no longer calls setWorldStyleSimple")
    if 'setFormFieldValue("starter_equipment"' not in pcode and "setFormFieldValue('starter_equipment'" not in pcode:
        fails.append("pushSimpleToForm no longer writes starter_equipment")

    # custom_style seeded only when empty — later Simple world edits leave stale style.
    empty_only_seed = re.search(
        r"styleEl\s*&&\s*!String\s*\(\s*styleEl\.value",
        wcode,
    ) or re.search(
        r"!\s*String\s*\(\s*styleEl\.value[\s\S]{0,80}\)\s*\.trim\(\)\s*\)\s*\{"
        r"[\s\S]{0,120}styleEl\.value\s*=",
        wcode,
    )
    if empty_only_seed:
        fails.append(
            "setWorldStyleSimple writes custom_style only when empty — "
            "editing #simpleWorld leaves startGame custom_style on the first vibe"
        )

    return fails


def _push_guards(text: str) -> dict[str, bool]:
    push = _fn_body(text, "function pushSimpleToForm()", max_chars=2500) or ""
    pcode = _strip_line_comments(push)
    world_fn = _fn_body(text, "function setWorldStyleSimple(", max_chars=1800) or ""
    wcode = _strip_line_comments(world_fn)
    empty_only_seed = bool(
        re.search(r"styleEl\s*&&\s*!String\s*\(\s*styleEl\.value", wcode)
        or re.search(
            r"!\s*String\s*\(\s*styleEl\.value[\s\S]{0,80}\)\s*\.trim\(\)\s*\)\s*\{"
            r"[\s\S]{0,120}styleEl\.value\s*=",
            wcode,
        )
    )
    return {
        "skip_name": bool(
            re.search(
                r'if\s*\(\s*name\s*\)\s*setFormFieldValue\s*\(\s*["\']player_name["\']',
                pcode,
            )
        ),
        "skip_world": bool(
            re.search(r"if\s*\(\s*world\s*\)\s*setWorldStyleSimple\s*\(\s*world\s*\)", pcode)
        ),
        "skip_gear": bool(
            re.search(
                r'if\s*\(\s*gearText\s*\)\s*setFormFieldValue\s*\(\s*["\']starter_equipment["\']',
                pcode,
            )
        ),
        "empty_only_seed": empty_only_seed,
    }


def simulate_cleared_simple_surface(text: str) -> list[str]:
    """Apply pushSimpleToForm guards from source to a cleared Simple UI."""
    fails: list[str] = []
    g = _push_guards(text)

    form = {
        "player_name": "Kael Ashford",
        "starter_equipment": "worn coat (chest) — warm",
        "world_style": "custom",
        "world_style_custom": "misty frontier",
        "custom_style": "misty frontier",
    }
    simple_name = ""
    simple_world = ""
    gear_text = ""

    if not g["skip_name"] or simple_name:
        form["player_name"] = simple_name
    if not g["skip_gear"] or gear_text:
        form["starter_equipment"] = gear_text
    if not g["skip_world"] or simple_world:
        form["world_style_custom"] = simple_world
        if simple_world:
            form["world_style"] = "custom"
        else:
            form["world_style"] = ""
            if form.get("custom_style") == "misty frontier":
                form["custom_style"] = ""

    if form.get("player_name") == "Kael Ashford":
        fails.append(
            "sim: cleared #simplePlayerName still submitted player_name="
            f"{form.get('player_name')!r} (truthy-only push)"
        )
    if form.get("starter_equipment"):
        fails.append(
            "sim: removed Simple gear still submitted starter_equipment="
            f"{form.get('starter_equipment')!r} (truthy-only push)"
        )
    if form.get("world_style_custom") == "misty frontier":
        fails.append(
            "sim: cleared #simpleWorld still submitted world_style_custom="
            f"{form.get('world_style_custom')!r} (truthy-only push)"
        )
    return fails


def simulate_world_edit_custom_style(text: str) -> list[str]:
    """First vibe seeds custom_style; second vibe must not leave it stale."""
    fails: list[str] = []
    g = _push_guards(text)
    custom_style = ""
    prev_world = ""

    def apply_world(new_text: str) -> None:
        nonlocal custom_style, prev_world
        t = new_text.strip()
        prev = prev_world
        prev_world = t[:120]
        if not t:
            if not custom_style.strip() or custom_style == prev:
                custom_style = ""
            return
        if g["empty_only_seed"]:
            if not custom_style.strip():
                custom_style = t[:200]
            return
        if not custom_style.strip() or custom_style == prev:
            custom_style = t[:200]

    apply_world("misty frontier")
    apply_world("rain-slick megacity")
    if custom_style != "rain-slick megacity":
        fails.append(
            f"sim: custom_style stayed {custom_style!r} after Simple world "
            "changed to 'rain-slick megacity' (empty-only seed)"
        )
    return fails


def main() -> int:
    text = APP_JS.read_text(encoding="utf-8")
    fails = check_static(text)
    fails.extend(simulate_cleared_simple_surface(text))
    fails.extend(simulate_world_edit_custom_style(text))
    if fails:
        print("FAIL: Simple push empty-surface leftovers")
        for f in fails:
            print(f" - {f}")
        return 1
    print("OK: Simple push writes empty name/world/gear so Start does not keep stale randomize values")
    return 0


if __name__ == "__main__":
    sys.exit(main())
