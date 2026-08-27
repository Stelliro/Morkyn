"""Do the kit and clothing seed fields leak the way the arrival seeds did?

WF1 finding 3, which was recorded as a hypothesis and NOT a finding:
`kit_seeds_inspiration_only` and `clothing_seeds_inspiration_only` use the same
shape that made `arrival_location_seeds` copy verbatim 24 times out of 24. Same
mechanism is not the same rate, so this measures before anything is touched.

These fields differ from start_location in a way that matters. An arrival name
is a proper noun and any overlap is copying. A kit is a list of common nouns --
"house keys", "light jacket" -- and a modern-isekai kit legitimately overlaps
with any other modern-isekai kit. Raw overlap would therefore look alarming and
mean nothing.

So the instrument is a CONTROL, not a threshold: every roll is scored against
the seeds it was shown AND against the seeds it was not. If the model is
copying, overlap with what it saw is much higher than overlap with what it did
not. If the two are close, the overlap is just the genre's vocabulary and there
is nothing here to fix.

Usage:
    ./.venv/Scripts/python.exe tools/measure_seed_field_leak.py [--n 6]

Config: copies data/world.db to a temp file and points AI_RPG_DB at the copy,
so the run uses SHIPPED model settings without touching the real save.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_tmp = Path(tempfile.mkdtemp(prefix="morkyn-seedleak-"))
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
from app.setup_composer import APPEARANCE_SEED_POOL, STARTER_KIT_SEED_POOL  # noqa: E402

FIELDS = {
    "starter_equipment": ("kit_seeds_inspiration_only", STARTER_KIT_SEED_POOL),
    "appearance": ("clothing_seeds_inspiration_only", APPEARANCE_SEED_POOL),
}

SETUPS = [
    {"world_style": "modern isekai coastal fantasy", "backstory_mode": "transmigrated"},
    {"world_style": "neon megacity under corporate rule", "backstory_mode": "native"},
    {"world_style": "high fantasy kingdom of sorcery", "backstory_mode": "native"},
    {"world_style": "post-collapse irradiated ruin", "backstory_mode": "native"},
]

_STOP = {"a", "an", "the", "of", "and", "or", "with", "over", "in", "on", "to"}


def _spans(text: str) -> set[str]:
    """Adjacent word pairs, stopwords dropped. Two-word spans are the unit a
    person would call 'copied': "house keys", "transit card"."""
    flat = "".join(c if c.isalnum() or c.isspace() else " " for c in str(text or "").lower())
    words = [w for w in flat.split() if w not in _STOP and len(w) > 2]
    return {f"{a} {b}" for a, b in zip(words, words[1:])}


def _roll(field: str, setup: dict) -> tuple[list[str], str]:
    """Return (seeds the prompt showed, the value the model returned)."""
    seen: dict[str, object] = {}
    seed_key = FIELDS[field][0]

    real = llm._chat_json
    captured: dict[str, object] = {}

    def _spy(system, user, **kwargs):
        if kwargs.get("phase") == "setup_randomize":
            captured["prompt"] = json.loads(user)
        return real(system, user, **kwargs)

    llm._chat_json = _spy
    try:
        out = llm.generate_setup_randomization(f"field:{field}", dict(setup))
    except Exception as exc:  # noqa: BLE001
        return [], f"__ERROR__ {type(exc).__name__}: {exc}"[:100]
    finally:
        llm._chat_json = real

    prompt = captured.get("prompt") or {}
    shown = [str(s) for s in (prompt.get(seed_key) or [])]
    value = out.get(field) if isinstance(out, dict) else None
    if isinstance(value, list):
        value = ", ".join(str(v) for v in value)
    seen.clear()
    return shown, str(value or "").strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=6, help="rolls per field")
    args = ap.parse_args()

    cfg = llm.get_model_config()
    print(f"model: {cfg.get('provider')}:{cfg.get('ollama_model')}  (shipped config)")
    print(f"{args.n} rolls per field\n")
    started = time.time()
    verdicts: dict[str, tuple[int, float, float, int]] = {}

    for field, (seed_key, pool) in FIELDS.items():
        print(f"--- {field} ({seed_key}, pool of {len(pool)}) ---")
        shown_scores: list[float] = []
        unshown_scores: list[float] = []
        exact = 0
        rolls = 0
        injected = True
        for i in range(args.n):
            setup = dict(SETUPS[i % len(SETUPS)])
            shown, value = _roll(field, setup)
            if value.startswith("__ERROR__"):
                print(f"  error: {value[:60]}")
                continue
            if not shown:
                # The prompt no longer carries the pool. There is nothing to
                # copy, so there is no leak rate to compute -- but n=0 is not a
                # result, so score against the WHOLE pool instead. That number
                # is the honest post-fix baseline: whatever overlap remains is
                # the genre's own vocabulary, which is what we wanted to keep.
                injected = False
                spans = _spans(value)
                hit: set[str] = set()
                for seed in pool:
                    hit |= spans & _spans(seed)
                score = len(hit) / max(1, len(spans))
                unshown_scores.append(score)
                rolls += 1
                print(f"  no seeds in prompt; whole-pool overlap {score:5.1%}   {value[:52]}")
                continue
            rolls += 1
            value_spans = _spans(value)
            if not value_spans:
                continue
            shown_set = set(shown)
            unshown = [s for s in pool if s not in shown_set]

            def _overlap(seeds):
                hit = set()
                for seed in seeds:
                    hit |= value_spans & _spans(seed)
                return len(hit) / max(1, len(value_spans))

            s_score = _overlap(shown)
            u_score = _overlap(unshown)
            shown_scores.append(s_score)
            unshown_scores.append(u_score)
            if any(value.strip().lower() == s.strip().lower() for s in shown):
                exact += 1
            print(f"  shown-overlap {s_score:5.1%}  unshown-overlap {u_score:5.1%}   {value[:56]}")

        s_avg = sum(shown_scores) / len(shown_scores) if shown_scores else 0.0
        u_avg = sum(unshown_scores) / len(unshown_scores) if unshown_scores else 0.0
        verdicts[field] = (rolls, s_avg, u_avg, exact, injected)
        print()

    print(f"elapsed: {time.time() - started:.0f}s\n")
    print(f"{'field':20s} {'n':>3s} {'shown':>8s} {'unshown':>8s} {'exact':>6s}  verdict")
    print("-" * 78)
    for field, (n, s_avg, u_avg, exact, injected) in verdicts.items():
        if not injected:
            # No seeds in the prompt at all. Say so rather than reporting a
            # clean bill of health the run did not earn.
            print(
                f"{field:20s} {n:>3d} {'--':>8s} {u_avg:>7.1%} {'--':>6s}  "
                f"no seeds injected; nothing to copy"
            )
            continue
        # The pool is only ~4x the sample, so unshown overlap is the floor for
        # "this is just what a kit looks like". Copying means clearing it.
        leaking = exact > 0 or (s_avg > 0.25 and s_avg > u_avg * 2.0)
        verdict = "LEAKING -- fix it" if leaking else "no evidence of copying"
        print(f"{field:20s} {n:>3d} {s_avg:>7.1%} {u_avg:>7.1%} {exact:>6d}  {verdict}")
    print(
        "\nRead the two percentages together, never the first alone: a kit is common\n"
        "nouns and overlap with ANY kit is expected. Only shown >> unshown is copying."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
