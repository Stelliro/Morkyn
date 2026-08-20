"""
Did the structured changes the model drafted survive into the applied turn?

Reads model traces and compares, per turn, the amount ops present in the raw
DSL draft against what ended up in `final_turn`. Used to tell a band-contract
problem apart from a verifier that drops structured state regardless of format.

    python tools/check_trace_ops_survival.py <trace_dir>
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

AMOUNT_OP = re.compile(r"^(XP|GOLD|HP|KARMA|GRANT|TAKE|SKILL)\b(.*)$")


def draft_ops(trace: dict) -> list[str]:
    for entry in trace.get("model_trace") or []:
        if not isinstance(entry, dict) or entry.get("phase") != "draft_dsl":
            continue
        raw = entry.get("raw_content") or ""
        if "===OPS===" not in raw:
            continue
        block = raw.split("===OPS===")[-1]
        return [
            line.strip()
            for line in block.splitlines()
            if AMOUNT_OP.match(line.strip())
        ]
    return []


def final_changes(trace: dict) -> dict:
    final = trace.get("final_turn") or {}
    player = final.get("player") or {}
    return {
        "xp_delta": player.get("xp_delta"),
        "gold_delta": player.get("gold_delta"),
        "health_delta": player.get("health_delta"),
        "karma_delta": player.get("karma_delta"),
        "inventory": len(final.get("inventory_changes") or []),
        "skills": len(final.get("skill_changes") or []),
        "phases": [
            e.get("phase")
            for e in (trace.get("model_trace") or [])
            if isinstance(e, dict) and e.get("event") == "response"
        ],
    }


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    trace_dir = Path(sys.argv[1])
    if not trace_dir.is_dir():
        print(f"not a directory: {trace_dir}")
        return 1

    total_drafted = 0
    total_lost = 0
    for path in sorted(trace_dir.glob("*.json")):
        try:
            trace = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        ops = draft_ops(trace)
        if not ops:
            continue
        final = final_changes(trace)
        applied = any(
            final.get(k) for k in ("xp_delta", "gold_delta", "karma_delta")
        ) or final["inventory"] or final["skills"]
        total_drafted += len(ops)
        status = "APPLIED" if applied else "LOST"
        if not applied:
            total_lost += len(ops)
        print(f"{path.name}  turn={trace.get('turn')}  {status}")
        for op in ops:
            print(f"    drafted: {op[:90]}")
        print(f"    final  : { {k: v for k, v in final.items() if k != 'phases'} }")
        print(f"    phases : {final['phases']}")

    print()
    print(f"amount ops drafted: {total_drafted}")
    print(f"amount ops lost   : {total_lost}")
    if total_drafted:
        print(f"survival rate     : {100.0 * (total_drafted - total_lost) / total_drafted:.0f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
