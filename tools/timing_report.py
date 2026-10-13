"""Summarise how long a game took: setup to first turn, each turn, and the gaps between turns.

Reads the two files the engine appends to in its model-trace dir
(app/turn_ledger.py): ``timings.jsonl`` (one line per turn or setup) and
``requests.jsonl`` (one line per state-changing API call, setup page included).

    python tools/timing_report.py <trace dir> [--campaign ID] [--json]

The trace dir is ``data/model_traces`` for normal play, or
``<run dir>/data/model_traces`` for an api_bridge_playtest run.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def _read(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _stats(values: list[float]) -> dict[str, Any]:
    values = [v for v in values if isinstance(v, (int, float))]
    if not values:
        return {"n": 0}
    ordered = sorted(values)
    p90 = ordered[min(len(ordered) - 1, int(round(0.9 * (len(ordered) - 1))))]
    return {
        "n": len(values),
        "mean": round(statistics.fmean(values), 2),
        "median": round(statistics.median(values), 2),
        "p90": round(p90, 2),
        "max": round(max(values), 2),
        "total": round(sum(values), 1),
    }


def _ts(value: str) -> float:
    return datetime.fromisoformat(value).timestamp()


def report(trace_dir: Path, campaign: str = "") -> dict[str, Any]:
    timings = _read(trace_dir / "timings.jsonl")
    requests = _read(trace_dir / "requests.jsonl")
    if not campaign and timings:
        campaign = str(timings[-1].get("campaign") or "")
    rows = [t for t in timings if not campaign or t.get("campaign") == campaign]
    out: dict[str, Any] = {"campaign": campaign, "trace_dir": str(trace_dir)}

    start = next((t for t in rows if t.get("label") == "start"), None)
    if start:
        out["start"] = {
            "seconds": start.get("seconds"),
            "model_seconds": start.get("model_seconds"),
            "phases": {p["phase"]: p["seconds"] for p in start.get("phases") or []},
        }
        # The setup page: API calls from the first setup request before Start to Start's end.
        start_begin = _ts(start["started"])
        setup_calls = [
            r for r in requests
            if r.get("path", "").startswith(("/api/setup", "/api/randomize-setup"))
            and _ts(r["finished"]) <= _ts(start["finished"]) + 1
            and _ts(r["started"]) >= start_begin - 6 * 3600
        ]
        if setup_calls:
            first = min(_ts(r["started"]) for r in setup_calls)
            out["setup_page"] = {
                "first_setup_call": min(r["started"] for r in setup_calls),
                "calls": len(setup_calls),
                "call_seconds": _stats([r["seconds"] for r in setup_calls]),
                "seconds_until_start_pressed": round(start_begin - first, 1),
            }
        first_turn = next((t for t in rows if t.get("label") != "start" and _ts(t["started"]) > start_begin), None)
        if first_turn:
            out["start_to_first_turn"] = {
                "opening_ready_to_first_turn_sent": first_turn.get("gap_since_previous"),
                "start_pressed_to_first_turn_done": round(_ts(first_turn["finished"]) - start_begin, 1),
            }

    turns = [t for t in rows if t.get("label") != "start"]
    by_label: dict[str, list[dict[str, Any]]] = {}
    for t in turns:
        by_label.setdefault(str(t.get("label")), []).append(t)
    out["turns"] = {
        label: {
            "seconds": _stats([t.get("seconds") for t in items]),
            "model_seconds": _stats([t.get("model_seconds") for t in items]),
            "gpu_wait_seconds": _stats([t.get("gpu_wait_seconds") for t in items]),
            "engine_seconds": _stats([t.get("engine_seconds") for t in items]),
            "model_calls": _stats([t.get("model_call_count") for t in items]),
        }
        for label, items in by_label.items()
    }
    gaps = [t.get("gap_since_previous") for t in turns if t.get("gap_since_previous") is not None]
    out["gap_between_turns"] = _stats(gaps)
    # Long gaps are breaks, not reading time; reported apart so they do not skew estimates.
    out["gap_between_turns_under_10min"] = _stats([g for g in gaps if g < 600])
    if turns:
        out["wall_clock_first_to_last_turn"] = round(_ts(turns[-1]["finished"]) - _ts(turns[0]["started"]), 1)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("trace_dir", type=Path)
    parser.add_argument("--campaign", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    data = report(args.trace_dir, args.campaign)
    if args.json:
        print(json.dumps(data, indent=1))
        return 0
    print(f"campaign {data['campaign'] or '(any)'}")
    if "setup_page" in data:
        s = data["setup_page"]
        print(f"setup page: {s['calls']} calls, {s['seconds_until_start_pressed']} s from first setup call to Start")
    if "start" in data:
        s = data["start"]
        phases = ", ".join(f"{k} {v}s" for k, v in s["phases"].items())
        print(f"start -> opening shown: {s['seconds']} s ({phases})")
    if "start_to_first_turn" in data:
        s = data["start_to_first_turn"]
        print(f"opening shown -> first line sent: {s['opening_ready_to_first_turn_sent']} s; "
              f"Start -> first turn done: {s['start_pressed_to_first_turn_done']} s")
    for label, block in data["turns"].items():
        sec = block["seconds"]
        if not sec.get("n"):
            continue
        print(f"{label}: n={sec['n']} mean {sec['mean']} s, median {sec['median']}, p90 {sec['p90']}, max {sec['max']} "
              f"(model {block['model_seconds'].get('mean')}, gpu wait {block['gpu_wait_seconds'].get('mean')}, "
              f"engine {block['engine_seconds'].get('mean')}; calls {block['model_calls'].get('mean')})")
    gap = data["gap_between_turns_under_10min"]
    if gap.get("n"):
        print(f"between turns (<10 min): mean {gap['mean']} s, median {gap['median']} s")
    if "wall_clock_first_to_last_turn" in data:
        print(f"wall clock, first to last turn: {data['wall_clock_first_to_last_turn']} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
