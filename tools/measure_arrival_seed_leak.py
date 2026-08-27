"""Measure how often the model returns an arrival name it was just shown.

WF1 steps 1 and 4. Two arms against the same model in the same run:

  legacy   the prompt shape that shipped before this fix -- the six-entry
           `arrival_location_seeds` key plus the "Example arrival names
           (adapt, invent similar)" rule, re-injected onto the real prompt
  shipped  whatever the code builds today

Both arms go through the real `generate_setup_randomization` prompt builder, so
the only difference between them is the two injection points. Anything else
that changes the rate would be noise, and interleaving the arms keeps model
warm-up out of the comparison.

Reports, per arm: verbatim bank hits (case-insensitive exact), distinctive
multi-word span overlaps, and the distinct-name count -- because a fix that
lowers the leak rate by collapsing variety is not a fix.

Usage:
    ./.venv/Scripts/python.exe tools/measure_arrival_seed_leak.py [--n 3]

Config: copies data/world.db to a temp file and points AI_RPG_DB at the copy,
so the run uses SHIPPED model settings (provider/model/base url) without
touching the real save. No model env vars are overridden.
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _use_shipped_config_on_a_copy() -> Path:
    """Point AI_RPG_DB at a copy of the real DB: shipped config, no writes to it."""
    import os

    src = ROOT / "data" / "world.db"
    tmp = Path(tempfile.mkdtemp(prefix="morkyn-arrivalmeasure-"))
    dst = tmp / "world.db"
    if src.exists():
        shutil.copy2(src, dst)
    os.environ["AI_RPG_DB"] = str(dst)
    os.environ.setdefault("AI_RPG_PACK_DIR", str(tmp / "packs"))
    os.environ.setdefault("AI_RPG_SOURCE_INDEX", str(tmp / "source_index"))
    os.environ.setdefault("AI_RPG_HISTORY_SUMMARY", str(tmp / "history.jsonl"))
    os.environ.setdefault("AI_RPG_MODEL_TRACE_DIR", str(tmp / "traces"))
    os.environ.setdefault("AI_RPG_SKILL_LIBRARY", str(tmp / "skill_library.json"))
    return dst


_use_shipped_config_on_a_copy()

from app import llm  # noqa: E402
from app.setup_composer import LOCATION_SEEDS_BY_THEME  # noqa: E402

# Same probes the static harness uses, minus generic (no bank of its own to
# leak from is not true -- generic HAS a bank -- so it stays in).
THEME_PROBES: dict[str, str] = {
    "space": "hard sci-fi orbital station",
    "cyberpunk": "neon megacity under corporate rule",
    "wasteland": "post-collapse irradiated ruin",
    "fantasy": "high fantasy kingdom of sorcery",
    "generic": "a quiet coastal town where nothing unusual has happened",
    "celestial": "the heavens, a divine court beyond the afterlife",
    "desert": "endless dune sea and salt flat caravans",
    "gothic": "a haunted manor of the blood court",
}

_STOP = {"the", "of", "a", "an", "and", "at", "on", "in", "to"}


def _spans(name: str) -> set[str]:
    """Distinctive adjacent word pairs, stopwords dropped."""
    words = [w for w in "".join(c if c.isalnum() or c.isspace() else " " for c in name.lower()).split() if w not in _STOP]
    return {f"{a} {b}" for a, b in zip(words, words[1:])}


def _build_prompt(world_style: str) -> dict:
    seen: dict[str, object] = {}

    def _stub(system, user, **kwargs):
        if kwargs.get("phase") == "setup_randomize":
            seen["prompt"] = json.loads(user)
        return {"start_location": "Stub"}

    real = llm._chat_json
    llm._chat_json = _stub
    try:
        llm.generate_setup_randomization(
            "field:start_location",
            {
                "world_style": world_style,
                "backstory_mode": "transmigrated",
                "_randomize_idea": world_style,
            },
        )
    finally:
        llm._chat_json = real
    return dict(seen.get("prompt") or {})


def _make_legacy(prompt: dict, theme_id: str) -> dict:
    """Re-create the pre-fix prompt shape exactly."""
    out = dict(prompt)
    pool = list(LOCATION_SEEDS_BY_THEME.get(theme_id) or LOCATION_SEEDS_BY_THEME["fantasy"])
    seeds = random.sample(pool, k=min(6, len(pool)))
    out["arrival_location_seeds"] = seeds
    rules = [
        r
        for r in (out.get("rules") or [])
        if "Build the arrival name out of this setting" not in str(r)
    ]
    rules.append(
        f"Example arrival names (adapt, invent similar): {', '.join(seeds[:4])}"
    )
    out["rules"] = rules
    return out


def _roll(prompt: dict) -> str:
    try:
        result = llm._chat_json(
            "Return JSON only. Generate direct values. Do not explain. Do not echo the request.",
            json.dumps(prompt, ensure_ascii=True),
            timeout=180,
            phase="setup_randomize",
            max_tokens=180,
        )
    except Exception as exc:  # noqa: BLE001
        return f"__ERROR__ {type(exc).__name__}: {exc}"[:120]
    value = result.get("start_location") if isinstance(result, dict) else None
    if isinstance(value, list):
        value = value[0] if value else ""
    return str(value or "").strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=3, help="rolls per theme per arm")
    args = ap.parse_args()

    cfg = llm.get_model_config()
    model_id = f"{cfg.get('provider')}:{cfg.get('ollama_model')}"
    print(f"model: {model_id}  (shipped config, read from a copy of data/world.db)")
    print(f"n per theme per arm: {args.n}\n")

    results: dict[str, list[tuple[str, str]]] = {"legacy": [], "shipped": []}
    started = time.time()

    for theme, world_style in THEME_PROBES.items():
        base = _build_prompt(world_style)
        if not base:
            print(f"  {theme}: prompt build failed, skipped")
            continue
        theme_id = str(base.get("arrival_location_theme") or theme)
        for _ in range(args.n):
            # Interleaved: same theme, both arms, back to back.
            for arm in ("legacy", "shipped"):
                prompt = _make_legacy(base, theme_id) if arm == "legacy" else dict(base)
                prompt["diversity_seed"] = random.randint(1000, 999999)
                name = _roll(prompt)
                results[arm].append((theme_id, name))
                print(f"  [{arm:7s}] {theme_id:10s} -> {name}")

    print(f"\nelapsed: {time.time() - started:.0f}s\n")
    print(f"{'arm':9s} {'n':>4s} {'verbatim':>9s} {'span':>6s} {'distinct':>9s}  errors")
    print("-" * 56)
    summary: dict[str, tuple[int, int, int, int, int]] = {}
    for arm, rows in results.items():
        good = [(t, n) for t, n in rows if not n.startswith("__ERROR__")]
        errors = len(rows) - len(good)
        verbatim = 0
        span = 0
        for theme_id, name in good:
            bank = [str(b) for b in (LOCATION_SEEDS_BY_THEME.get(theme_id) or ())]
            low = name.lower()
            if any(low == b.lower() for b in bank):
                verbatim += 1
                continue
            name_spans = _spans(name)
            if name_spans and any(name_spans & _spans(b) for b in bank):
                span += 1
        distinct = len({n.lower() for _, n in good})
        summary[arm] = (len(good), verbatim, span, distinct, errors)
        pct = (100.0 * verbatim / len(good)) if good else 0.0
        print(f"{arm:9s} {len(good):>4d} {verbatim:>4d} ({pct:4.1f}%) {span:>6d} {distinct:>9d}  {errors}")

    lg, sh = summary.get("legacy"), summary.get("shipped")
    if lg and sh and lg[0] and sh[0]:
        print(
            f"\nverbatim rate: legacy {100.0 * lg[1] / lg[0]:.1f}%  ->  "
            f"shipped {100.0 * sh[1] / sh[0]:.1f}%"
        )
        print(f"distinct names: legacy {lg[3]}/{lg[0]}  ->  shipped {sh[3]}/{sh[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
