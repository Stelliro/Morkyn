"""Assert the start_location prompt never hands the model a bank name.

WF1. The arrival randomizer used to ship six real entries out of
`LOCATION_SEEDS_BY_THEME` as a prompt key, plus four of them again inside a
rule that said "adapt, invent similar". ~44% of live arrival names came back a
verbatim member of the bank it had just been shown.

This harness builds the real prompt for several themes with the model stubbed
out, and fails if any bank entry -- from any theme, not just the selected one --
appears anywhere in the serialized prompt.

It also asserts the *shape* hint survives. Removing the names is the fix;
removing the theme hint along with them would be a different bug, and this
harness is what stops that.

Run:  ./.venv/Scripts/python.exe tools/test_arrival_seed_leak.py
Exit 0 = clean, 1 = a bank name reached the prompt.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-arrivalleak-"))
os.environ.setdefault("AI_RPG_DB", str(_TMP / "world.db"))
os.environ.setdefault("AI_RPG_PACK_DIR", str(_TMP / "packs"))
os.environ.setdefault("AI_RPG_SOURCE_INDEX", str(_TMP / "source_index"))
os.environ.setdefault("AI_RPG_HISTORY_SUMMARY", str(_TMP / "history.jsonl"))
os.environ.setdefault("AI_RPG_MODEL_TRACE_DIR", str(_TMP / "traces"))
os.environ.setdefault("AI_RPG_SKILL_LIBRARY", str(_TMP / "skill_library.json"))

from app import llm  # noqa: E402
from app.setup_composer import (  # noqa: E402
    APPEARANCE_SEED_POOL,
    LOCATION_SEEDS_BY_THEME,
    STARTER_KIT_SEED_POOL,
)

# The other two fields that shipped their own pool into the prompt under an
# "inspiration only" label. Measured on qwen3:8b: the kit came back a verbatim
# copy of a shown seed 4 times in 6, the clothing 2 times in 6. Same shape, same
# removal, each on its own evidence.
SIBLING_FIELDS: dict[str, tuple[str, tuple[str, ...]]] = {
    "starter_equipment": ("kit_seeds_inspiration_only", STARTER_KIT_SEED_POOL),
    "appearance": ("clothing_seeds_inspiration_only", APPEARANCE_SEED_POOL),
}

# One world_style per theme that detect_location_theme resolves to that theme.
THEME_PROBES: dict[str, str] = {
    "space": "hard sci-fi orbital station",
    "cyberpunk": "neon megacity under corporate rule",
    "wasteland": "post-collapse irradiated ruin",
    "fantasy": "high fantasy kingdom of sorcery",
    "generic": "a quiet coastal town where nothing unusual has happened",
    # NB: probe strings must not themselves contain a bank entry -- the prompt
    # echoes world_style back, so "a prison of light" would fail as a false hit.
    "celestial": "the heavens, a divine court beyond the afterlife",
    "desert": "endless dune sea and salt flat caravans",
    "gothic": "a haunted manor of the blood court",
}


def _capture_prompt(world_style: str, field: str = "start_location") -> dict:
    """Run the real randomizer with the model stubbed; return the prompt dict."""
    seen: dict[str, object] = {}

    def _fake_chat_json(system, user, **kwargs):
        if kwargs.get("phase") == "setup_randomize":
            seen["prompt"] = json.loads(user)
        return {field: "Stub"}

    real = llm._chat_json
    llm._chat_json = _fake_chat_json
    try:
        llm.generate_setup_randomization(
            f"field:{field}",
            # backstory_mode alone makes this isekaiish. Deliberately NOT
            # putting "isekai" in the idea: it is itself a fantasy keyword and
            # would drag every probe to the fantasy theme.
            {
                "world_style": world_style,
                "backstory_mode": "transmigrated",
                "_randomize_idea": world_style,
            },
        )
    finally:
        llm._chat_json = real
    return dict(seen.get("prompt") or {})


def _all_bank_entries() -> list[str]:
    out: set[str] = set()
    for entries in LOCATION_SEEDS_BY_THEME.values():
        for entry in entries:
            text = str(entry or "").strip()
            if len(text) >= 4:
                out.add(text)
    return sorted(out)


def main() -> int:
    banks = _all_bank_entries()
    failures: list[str] = []
    checked = 0

    for theme, world_style in THEME_PROBES.items():
        prompt = _capture_prompt(world_style)
        if not prompt:
            failures.append(f"{theme}: randomizer never reached the model call")
            continue
        checked += 1

        blob = json.dumps(prompt, ensure_ascii=True).lower()

        # 1. No bank entry anywhere in the prompt, from any theme's bank.
        hits = [b for b in banks if b.lower() in blob]
        if hits:
            failures.append(
                f"{theme}: {len(hits)} bank name(s) reached the prompt -> {hits[:6]}"
            )

        # 2. The key itself must be gone, not merely emptied.
        if "arrival_location_seeds" in prompt:
            failures.append(f"{theme}: prompt still carries an arrival_location_seeds key")

        # 3. The exemplar rule must be gone.
        if re.search(r"example arrival names", blob):
            failures.append(f"{theme}: the 'Example arrival names' rule is still present")

        # 4. Positive: the label and the shape hint must survive.
        if str(prompt.get("arrival_location_theme") or "") != theme:
            failures.append(
                f"{theme}: arrival_location_theme is "
                f"{prompt.get('arrival_location_theme')!r}, expected {theme!r}"
            )
        rules = " ".join(str(r) for r in (prompt.get("rules") or [])).lower()
        if f"theme '{theme}'" not in rules:
            failures.append(f"{theme}: the theme rule no longer names the theme")
        if "arrival" not in rules:
            failures.append(f"{theme}: no arrival guidance left in rules at all")

    # The same shape on the two sibling fields.
    for field, (seed_key, pool) in SIBLING_FIELDS.items():
        entries = [str(p).strip() for p in pool if len(str(p).strip()) >= 12]
        for world_style in ("modern isekai coastal fantasy", "neon megacity under corporate rule"):
            prompt = _capture_prompt(world_style, field=field)
            if not prompt:
                failures.append(f"{field}: randomizer never reached the model call")
                continue
            checked += 1
            blob = json.dumps(prompt, ensure_ascii=True).lower()
            if seed_key in prompt:
                failures.append(f"{field}: prompt still carries a {seed_key} key")
            hits = [e for e in entries if e.lower() in blob]
            if hits:
                failures.append(f"{field}: {len(hits)} pool entry/entries reached the prompt -> {hits[:3]}")
            # Positive: the field must still be asked for with real guidance.
            rules = " ".join(str(r) for r in (prompt.get("rules") or [])).lower()
            if "diversity seed" not in rules:
                failures.append(f"{field}: lost its diversity seed rule")

    if failures:
        print("arrival seed leak: FAILED")
        for line in failures:
            print(f"  - {line}")
        return 1
    print(f"arrival seed leak: ok ({checked} themes, {len(banks)} bank entries checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
