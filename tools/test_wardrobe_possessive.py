"""Regression: possessive gear must not become s_tote-style tags."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.image_backends import (  # noqa: E402
    _clothing_tags,
    _format_forge_phrase,
    _simplify_wardrobe_label,
    build_portrait_prompt,
)


def main() -> int:
    fails: list[str] = []

    cases = {
        "teacher's tote": "tote",
        "teacher’s tote": "tote",  # curly apostrophe
        "child's backpack": "backpack",
        "women's boots": "boots",
        "men's leather jacket": "leather jacket",
        "mechanic's coat": "coat",
        "frayed mechanic's coat": "coat",
        "oil-stained work coat": "work coat",
        "scuffed boots": "boots",
        "worn tool satchel": "satchel",
    }
    for raw, expect in cases.items():
        got = _simplify_wardrobe_label(raw)
        if got != expect:
            fails.append(f"simplify({raw!r})={got!r} expected {expect!r}")

    # Format path must never emit s_tote / lone s_ prefix from possessives
    for raw in ("teacher's tote", "s tote", "teacher's tote bag"):
        simple = _simplify_wardrobe_label(raw) or raw
        tag = _format_forge_phrase(simple, max_words=2)
        if tag.startswith("s_") or tag == "s" or "_s_" in f"_{tag}_":
            fails.append(f"bad tag from {raw!r}: {tag!r}")
        if "s_tote" in tag:
            fails.append(f"s_tote from {raw!r}: {tag!r}")

    clothes = _clothing_tags(
        title="",
        equipment=["teacher's tote", "red pen"],
        extra="",
        appearance="",
        kind="fullbody",
        visibility_mode="full",
    )
    joined = " ".join(clothes).lower()
    if "s_tote" in joined or any(c == "s" or c.startswith("s_") for c in clothes):
        fails.append(f"clothing_tags still broken: {clothes}")
    if "tote" not in joined:
        fails.append(f"clothing_tags missing tote: {clothes}")

    prompt = build_portrait_prompt(
        name="A",
        equipment=["teacher's tote"],
        kind="face",
        sex="female",
    ).lower()
    if "s_tote" in prompt:
        fails.append(f"portrait prompt has s_tote: {prompt}")
    if "tote" not in prompt:
        fails.append(f"portrait prompt missing tote: {prompt}")

    # Direct format of a broken intermediate must drop lone s
    assert _format_forge_phrase("s tote", max_words=2) == "tote"

    if fails:
        for f in fails:
            print("FAIL", f)
        return 1
    print("OK: wardrobe possessive shortening")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
