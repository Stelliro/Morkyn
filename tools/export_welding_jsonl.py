#!/usr/bin/env python3
"""
Export Morkyn theme-training rows as welding-rig compatible JSONL.

neural-welding-rig (https://github.com/Stelliro/neural-welding-rig) expects:

    {"instruction": "...", "output": "..."}

This tool does NOT train, does NOT call Unsloth, and does NOT inject Golden Record /
AI-OR chamber data. It only builds seed rows (and optional harvested playtest lines)
you can copy into the welding lab as theme-adapter training data.

Usage:
  python tools/export_welding_jsonl.py --out data/welding/morkyn_theme_seed.jsonl
  python tools/export_welding_jsonl.py --out data/welding/out.jsonl --include-playtests
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]


def row(instruction: str, output: str) -> dict[str, str]:
    return {
        "instruction": " ".join(str(instruction).split()),
        "output": str(output).strip(),
    }


def setup_hygiene_seed() -> list[dict[str, str]]:
    """Positive structure-field fills + explicit negatives as separate rows."""
    positives = [
        ("difficulty", "normal", "hard isekai with compounding skill fantasy"),
        ("quest_style", "job board and personal mysteries", "isekai compounding skill system"),
        ("economy", "scarce coin markets", "near-useless skill that compounds hourly"),
        ("world_races", "human, elf, beastfolk", "Low-Power Human only isekai"),
        ("faction_pressure", "local guild disputes", "player skill growth slogans"),
        ("npc_stat_scaling", "mostly weaker near player", "level delay timers for player skill"),
        ("skill_style", "training-heavy", "full compounding essay"),
        (
            "custom_skills",
            "seed skill Ropework rank F, track ranks via subtle system UI, practice and risk earn progress, no second combat toolkit",
            "put all XP formulas only in custom_skills and invent weather Observation default",
        ),
    ]
    rows: list[dict[str, str]] = []
    for field, good, idea in positives:
        rows.append(
            row(
                f"Fill setup field `{field}` for this director idea: {idea}. "
                "Return only the field value. Keep structure fields free of skill-growth slogans.",
                good,
            )
        )
        rows.append(
            row(
                f"Reject a contaminated `{field}` value and replace it with a clean structure-only fill. "
                f"Idea: {idea}. Contaminated draft: near-useless skill compounds every hour, level delay 50.",
                good,
            )
        )
    rows.append(
        row(
            "Write ability growth_math for a weak one-skill seed (Ropework). "
            "Include concrete numbers: thresholds or XP_to_next, per-use XP with risk mult, soft cap, rank bonus.",
            "rank F→E@80 E→D@200 D→C@450; domain use 5-12 XP × risk (1 safe/2 contested/3 life-risk); "
            "XP_to_next = 50 * rank_index^1.4; after C practice XP ×0.5 until mentor breakthrough; "
            "+1 domain check per rank above F",
        )
    )
    return rows


def isekai_dm_seed() -> list[dict[str, str]]:
    return [
        row(
            "Write opening narration for a hardcore one-skill isekai. Ordinary person, one weak seed ability, "
            "subtle system UI once, local stakes, fair DM, clear English prose. No chosen-one, no free toolkit, "
            "no AI-OR lab metrics format.",
            "Rain beads on the market awning. A thin blue pane blinks once at the edge of vision:\n"
            "[ STATUS ] Body: whole  |  Seed: Ropework F  |  Note: nearly useless\n"
            "A porter swears at a jammed cart rope. A clerk waves a delivery slate. "
            "Nobody treats you like a hero. The wet street smells of tar and fried dough.",
        ),
        row(
            "Continue a turn after the player tries and fails a simple Ropework use. Award tiny skill XP "
            "using growth_math numbers, keep stakes local, no god-mode.",
            "The knot slips. Your palms burn. A quiet tick against the seed — +6 skill XP (safe practice). "
            "Still rank F. The porter laughs without cruelty and shows you the hitch again.",
        ),
        row(
            "Negative example — rewrite this bad narration into fair local DM prose: "
            "'You are the destined hero. All skills unlocked. LEVEL 99. System windows flood the sky.'",
            "You remain an ordinary traveler. One weak seed skill. No flood of windows. "
            "A single muted status blink if the system is on — then the street, the weather, and a choice.",
        ),
    ]


def harvest_playtest_jsonl(paths: Iterable[Path]) -> list[dict[str, str]]:
    """Best-effort harvest from Morkyn playtest dumps if present."""
    out: list[dict[str, str]] = []
    for path in paths:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # JSON array of turns, or JSONL
        payloads: list[Any] = []
        try:
            data = json.loads(text)
            if isinstance(data, list):
                payloads = data
            elif isinstance(data, dict):
                payloads = [data]
        except json.JSONDecodeError:
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    payloads.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        for item in payloads:
            if not isinstance(item, dict):
                continue
            narration = str(item.get("narration") or item.get("good_narration") or "").strip()
            player = str(item.get("player_input") or item.get("input") or "Continue the scene.").strip()
            if len(narration) < 80:
                continue
            # Skip lab dialect
            if re.search(r"\[STATE\]|\[METRICS\]|SYSTEM RESTORED", narration, re.I):
                continue
            out.append(
                row(
                    f"Write the next RPG turn narration for player input: {player[:400]}",
                    narration[:3500],
                )
            )
    return out


def default_playtest_globs() -> list[Path]:
    candidates: list[Path] = []
    for folder in (ROOT / "data", ROOT / "benchmarks", ROOT / "logs"):
        if not folder.is_dir():
            continue
        candidates.extend(folder.rglob("*playtest*.json"))
        candidates.extend(folder.rglob("*playtest*.jsonl"))
        candidates.extend(folder.rglob("*turn*.jsonl"))
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Morkyn theme rows for neural-welding-rig JSONL.")
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "data" / "welding" / "morkyn_theme_seed.jsonl",
        help="Output JSONL path",
    )
    parser.add_argument(
        "--include-playtests",
        action="store_true",
        help="Also harvest narration from local playtest dumps if found",
    )
    parser.add_argument(
        "--playtest",
        action="append",
        type=Path,
        default=[],
        help="Extra playtest file(s) to harvest (repeatable)",
    )
    args = parser.parse_args()

    rows = setup_hygiene_seed() + isekai_dm_seed()
    if args.include_playtests or args.playtest:
        paths = list(args.playtest) if args.playtest else default_playtest_globs()
        harvested = harvest_playtest_jsonl(paths)
        rows.extend(harvested)

    # Dedupe by instruction+output
    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for item in rows:
        key = f"{item['instruction']}\n{item['output']}".lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        for item in unique:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"Wrote {len(unique)} rows → {args.out}")
    print("Next: copy into neural-welding-rig lab workspace and weld WITHOUT Golden Record / EPC data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
