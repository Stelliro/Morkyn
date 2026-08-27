"""Measure the closed-enum location_theme on settings keywords cannot reach.

WF2 step 6. The keyword table is a floor with a real ceiling: a setting that
describes a genre without naming it ("a generation ship three hundred years
from landfall") matches nothing and resolves to `generic`, which yields a
deliberately placeless arrival name. Asking the model to classify the setting
against a closed set of twelve ids is meant to fill exactly that gap.

Two numbers matter and both are reported:

  corrected     settings that moved from generic to the RIGHT theme
  wrong         settings that moved from generic to the WRONG theme

A confidently wrong classifier is worse than a placeless name, so the second
number is the one that decides whether this was worth doing.

Control settings (ones keywords DO reach) are included to confirm the override
never fires when the player named a genre in their own words.

Usage:
    ./.venv/Scripts/python.exe tools/measure_location_theme_enum.py

Config: copies data/world.db to a temp file and points AI_RPG_DB at the copy,
so the run uses SHIPPED model settings without touching the real save.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_tmp = Path(tempfile.mkdtemp(prefix="morkyn-themeenum-measure-"))
_src = ROOT / "data" / "world.db"
if _src.exists():
    shutil.copy2(_src, _tmp / "world.db")
os.environ["AI_RPG_DB"] = str(_tmp / "world.db")
for _key, _name in (
    ("AI_RPG_PACK_DIR", "packs"),
    ("AI_RPG_SOURCE_INDEX", "source_index"),
    ("AI_RPG_HISTORY_SUMMARY", "history.jsonl"),
    ("AI_RPG_MODEL_TRACE_DIR", "traces"),
    ("AI_RPG_SKILL_LIBRARY", "skill_library.json"),
):
    os.environ.setdefault(_key, str(_tmp / _name))

from app import llm  # noqa: E402
from app.setup_composer import detect_location_theme  # noqa: E402

# (setting, the theme a person would call correct, is it keyword-reachable)
# The unreachable ones are the point. The reachable ones are the control: the
# override must never fire on them.
CASES: list[tuple[str, str, bool]] = [
    # --- keywords reach none of these ---
    ("a generation ship three hundred years from landfall", "space", False),
    ("a derelict hauler drifting past the third moon", "space", False),
    ("first contact goes badly on a survey world", "space", False),
    ("a courier with a cranial shunt and bad debts", "cyberpunk", False),
    ("the rain never stops and everyone owes the same company", "cyberpunk", False),
    ("eighty years after the bombs, the wells are still bad", "wasteland", False),
    ("a diving crew works below the shelf where the light stops", "undersea", False),
    ("the sun has not risen for a month and the radio is dead", "arctic", False),
    ("water is currency and the caravans set the price", "desert", False),
    ("the family has held this house for nine generations and none of them left", "gothic", False),
    ("a man walks into my office with a story I already know is a lie", "noir", False),
    ("a dying king, three heirs, and no good options", "fantasy", False),
    # --- genuinely no genre: generic IS the right answer ---
    ("two rivals inherit the same failing business", "generic", False),
    ("a letter arrives that should have been delivered forty years ago", "generic", False),
    ("an office comedy about expense reports", "generic", False),
    # --- control: the player named the genre, keywords win ---
    ("neon megacity under corporate rule", "cyberpunk", True),
    ("high fantasy kingdom of sorcery", "fantasy", True),
    ("hard sci-fi orbital station running out of water", "space", True),
    ("post-collapse settlement trading scrap for grain", "wasteland", True),
]


def main() -> int:
    cfg = llm.get_model_config()
    print(f"model: {cfg.get('provider')}:{cfg.get('ollama_model')}  (shipped config)")
    print(f"{len(CASES)} settings\n")

    rows: list[tuple[str, str, bool, str, str, str]] = []
    started = time.time()
    for setting, correct, reachable in CASES:
        before = detect_location_theme(world_style=setting)
        try:
            composed = llm.compose_setup_intent(setting)
        except Exception as exc:  # noqa: BLE001
            rows.append((setting, correct, reachable, before, "__ERROR__", f"{type(exc).__name__}", before))
            continue
        plan = dict(composed.get("intent") or {}) if isinstance(composed, dict) else {}
        answered = str(plan.get("location_theme") or "")
        # Three readings, because the plan influences the result by TWO routes
        # and they have to be told apart:
        #   before   keywords on the player's text alone
        #   prose    keywords on the player's text PLUS the model's free-text
        #            genre / tone / style_notes / keywords, which
        #            detect_location_theme has always concatenated into one blob
        #   after    the same, plus the closed-enum location_theme override
        # If prose != before, that is the pre-existing free-text path moving the
        # answer, not this workflow's enum.
        prose_plan = {k: v for k, v in plan.items() if k != "location_theme"}
        prose = detect_location_theme(world_style=setting, session_theme=prose_plan)
        after = detect_location_theme(world_style=setting, session_theme=plan)
        rows.append((setting, correct, reachable, before, after, answered or "(dropped/illegal)", prose))
        flag = "=" if before == after else ("+" if after == correct else "!")
        blame = "" if prose == after else "  [enum]"
        if prose != before:
            blame += "  [free-text moved it]"
        print(
            f"  {flag} {before:9s} -> {after:9s}  model said {answered or '-':9s}  "
            f"{setting[:44]}{blame}"
        )

    print(f"\nelapsed: {time.time() - started:.0f}s\n")

    # Reachability is DERIVED from the keyword-only answer, never from the hand
    # label in CASES. The label went stale the moment "generation ship" and
    # "survey world" were added to the table, and a measurement tool that
    # reports against a stale label is worse than no tool.
    ok = [r for r in rows if r[4] != "__ERROR__"]
    unreachable = [r for r in ok if r[3] == "generic"]
    control = [r for r in ok if r[3] != "generic"]
    errors = [r for r in rows if r[4] == "__ERROR__"]

    right = [r for r in unreachable if r[4] == r[1]]
    wrong = [r for r in unreachable if r[4] != r[1]]
    control_moved = [r for r in control if r[3] != r[4]]

    print(f"settings keywords cannot reach (resolved generic on the player's text alone): {len(unreachable)}")
    print(f"  ended on the right theme : {len(right)}")
    print(f"  ended on a WRONG theme   : {len(wrong)}")
    for r in wrong:
        note = "stayed generic" if r[3] == r[4] else f"got {r[4]}"
        print(f"    wanted {r[1]:9s} {note:16s} model said {r[5]!r}  {r[0][:44]}")

    print(f"\ncontrol settings (keywords reach these): {len(control)}")
    print(f"  moved off the keyword answer          : {len(control_moved)}")
    for r in control_moved:
        cause = "THE ENUM" if r[6] != r[4] else "free-text genre/tone/keywords (pre-existing)"
        print(f"    MOVED: {r[3]} -> {r[4]} by {cause}  {r[0][:42]}")

    by_enum = [r for r in rows if r[4] != "__ERROR__" and r[6] != r[4]]
    by_prose = [r for r in rows if r[4] != "__ERROR__" and r[6] != r[3]]
    print(f"\nattribution across all {len(rows)} settings:")
    print(f"  answer moved by the closed enum      : {len(by_enum)}")
    print(f"  answer moved by free-text genre/tone : {len(by_prose)}  (pre-existing path)")
    if errors:
        print(f"\nerrors: {len(errors)}")
    return 1 if control_moved else 0


if __name__ == "__main__":
    raise SystemExit(main())
