"""
Where does the turn prompt's budget actually go?

Splits each turn's prompt context into *static* content (setup options, the
skill catalog — identical every turn) and *dynamic* content (world state that
grows as the campaign accumulates). Answers two different questions that get
conflated:

  1. Is the database crowding the window?   -> dynamic growth over the run
  2. Is the window being wasted?            -> static share of every prompt

    python tools/analyze_prompt_budget.py <trace_dir>
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

# Slices that are the same every turn regardless of what has happened.
STATIC_SLICES = {"settings", "skill_check_context", "amount_contract"}

# Slices that accumulate with play.
ACCUMULATING = {
    "turn_summaries", "events", "conversations", "relevant_sources",
    "locations", "npcs", "relationships", "gm_events", "karma_history",
    "verification_memory", "inventory", "skills", "abilities",
}


def load(trace_dir: Path) -> list[dict]:
    rows = []
    for path in sorted(trace_dir.glob("*.json")):
        try:
            trace = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        ctx = trace.get("prompt_context")
        if not isinstance(ctx, dict):
            continue
        sizes = {}
        for key, value in ctx.items():
            try:
                sizes[key] = len(json.dumps(value, ensure_ascii=True, default=str))
            except Exception:
                sizes[key] = 0
        prompt_tokens = None
        for entry in trace.get("model_trace") or []:
            if (
                isinstance(entry, dict)
                and entry.get("event") == "request"
                and entry.get("phase") in ("draft", "draft_dsl")
            ):
                prompt_tokens = entry.get("prompt_estimated_tokens")
                break
        rows.append({"turn": trace.get("turn"), "sizes": sizes, "prompt_tokens": prompt_tokens})
    return sorted(rows, key=lambda r: r["turn"] or 0)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    rows = load(Path(sys.argv[1]))
    if not rows:
        print("no traces with prompt_context found")
        return 1

    print(f"turns analysed: {len(rows)}\n")
    print(f"{'turn':>5} {'total':>8} {'static':>8} {'dynamic':>8} {'static%':>8} {'ptok':>7}")
    static_share = []
    dynamic_totals = []
    for row in rows:
        sizes = row["sizes"]
        total = sum(sizes.values())
        static = sum(v for k, v in sizes.items() if k in STATIC_SLICES)
        dynamic = total - static
        share = 100.0 * static / total if total else 0
        static_share.append(share)
        dynamic_totals.append(dynamic)
        print(f"{row['turn']:>5} {total:>8} {static:>8} {dynamic:>8} {share:>7.0f}% "
              f"{str(row['prompt_tokens'] or '-'):>7}")

    print()
    print(f"mean static share of context : {statistics.fmean(static_share):.0f}%")
    if len(dynamic_totals) >= 6:
        cut = max(1, len(dynamic_totals) // 3)
        early = statistics.fmean(dynamic_totals[:cut])
        late = statistics.fmean(dynamic_totals[-cut:])
        print(f"dynamic context early -> late: {early:.0f} -> {late:.0f} bytes "
              f"({(late - early) / max(1, early) * 100:+.0f}%)")

    # Which accumulating slices actually grew?
    print("\naccumulating slices (early -> late bytes):")
    if len(rows) >= 6:
        cut = max(1, len(rows) // 3)
        early_rows, late_rows = rows[:cut], rows[-cut:]
        deltas = []
        for key in sorted(ACCUMULATING):
            e = statistics.fmean([r["sizes"].get(key, 0) for r in early_rows])
            l = statistics.fmean([r["sizes"].get(key, 0) for r in late_rows])
            if e or l:
                deltas.append((key, e, l, l - e))
        for key, e, l, d in sorted(deltas, key=lambda t: -t[3]):
            print(f"  {key:24s} {e:>8.0f} -> {l:>8.0f}  {d:>+8.0f}")

    # Static waste, ranked.
    print("\nstatic slices (same every turn):")
    last = rows[-1]["sizes"]
    for key in sorted(STATIC_SLICES, key=lambda k: -last.get(k, 0)):
        if last.get(key):
            print(f"  {key:24s} {last[key]:>8} bytes  (~{last[key] // 4} tokens)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
