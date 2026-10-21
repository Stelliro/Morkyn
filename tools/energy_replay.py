"""Replay a run's turns through the engine's energy model and print the energy curve.

Reads a model-trace dir read-only (``<run dir>/data/model_traces`` or
``data/model_traces``) and, for every player turn, takes the line, the
minutes the clock moved and the action kind the engine charged. Each turn is
then charged again through ``app.player_resources.apply_action_spend`` on a
throwaway in-memory database, so the curve is the engine's own arithmetic
with whatever costs and regen the code has now.

    python tools/energy_replay.py <trace dir> [<trace dir> ...]
        [--from T] [--to T] [--reread] [--start-full] [--synthetic] [--json]

--reread    charge the kind the current code reads from the line
            (world._action_cost_kind), not the kind the run recorded
--synthetic replay the built-in "ordinary day" and "heavy labour" sequences
            (no traces needed)

Each row: turn, kind, minutes, the energy the run recorded after the turn,
the replayed energy, and a bar. Walks on a town map are charged by the walk
itself (_spend_travel), not here; a row whose recorded energy moved by more
than the replay explains is marked "*".
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import player_resources as pr  # noqa: E402

# An ordinary day (fault log F153 cont.): 8B run 150's second day after the
# reef dive, T17-T101, each line read by the current code (kind:minutes per
# turn): talk at the counters, two crates and a breather, five walks between
# town places, handling and looking round. Kept here so the balance can be
# checked without the archive.
_RUN150_DAY = (
    "talk:6 talk:6 talk:6 talk:6 investigate:15 talk:6 talk:6 talk:5 talk:6 journey:6 general:6 talk:5 general:6 "
    "talk:5 talk:5 wait:15 investigate:15 talk:6 talk:5 talk:6 wait:15 talk:6 general:6 investigate:6 talk:5 "
    "wait:15 general:6 talk:6 talk:6 physical:25 general:6 physical:25 rest:20 general:6 talk:5 general:6 "
    "general:6 talk:5 talk:5 journey:6 general:6 wait:15 general:6 talk:5 talk:6 talk:6 journey:6 general:6 "
    "investigate:6 journey:6 talk:5 talk:5 talk:5 talk:6 wait:15 wait:15 wait:15 talk:6 general:6 talk:5 "
    "wait:15 talk:6 wait:15 talk:5 talk:5 general:6 general:6 journey:15 talk:5 investigate:15 investigate:6 "
    "general:10 investigate:15 talk:6 general:6 talk:6 general:6 general:6 wait:15 general:6 talk:6 "
    "investigate:6 wait:15 general:6 talk:5"
)
ORDINARY_DAY: list[tuple[str, int]] = [
    (step.split(":")[0], int(step.split(":")[1])) for step in _RUN150_DAY.split()
]
# Heavy labour: a morning of hauling with no breather.
HEAVY_LABOUR: list[tuple[str, int]] = [("physical", 25)] * 8


def _memory_db(energy: int, max_energy: int, fatigue: int, max_fatigue: int, carry: dict[str, float] | None) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE player (
          id INTEGER PRIMARY KEY CHECK (id = 1),
          health INTEGER, max_health INTEGER, level INTEGER,
          energy INTEGER, max_energy INTEGER,
          mana INTEGER, max_mana INTEGER,
          fatigue INTEGER, max_fatigue INTEGER
        );
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT);
        """
    )
    conn.execute(
        "INSERT INTO player VALUES (1, 20, 20, 1, ?, ?, 0, 0, ?, ?)",
        (int(energy), int(max_energy), int(fatigue), int(max_fatigue)),
    )
    if carry:
        pr.save_resource_carry(conn, {k: float(carry.get(k) or 0.0) for k in ("energy", "fatigue", "mana")})
    return conn


def replay_kinds(
    steps: Iterable[tuple[str, int]],
    *,
    energy: int,
    max_energy: int,
    fatigue: int = 0,
    max_fatigue: int = pr.BASE_FATIGUE_CAP,
    carry: dict[str, float] | None = None,
    stats: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Charge each (kind, minutes) through apply_action_spend; one row per step."""
    conn = _memory_db(energy, max_energy, fatigue, max_fatigue, carry)
    rows: list[dict[str, Any]] = []
    try:
        for kind, minutes in steps:
            pack = pr.apply_action_spend(conn, kind=kind, minutes=max(1, int(minutes or 6)), options={}, stats=stats, hard_block=True)
            after = pack.get("after") or pr.get_player_resources(conn, {})
            rows.append({
                "kind": kind,
                "minutes": int(minutes or 6),
                "energy": int(after.get("energy") or 0),
                "fatigue": int(after.get("fatigue") or 0),
                "blocked": bool(pack.get("blocked")),
            })
    finally:
        conn.close()
    return rows


def _abs_minutes(wt: dict[str, Any] | None) -> int | None:
    if not isinstance(wt, dict) or wt.get("minute") is None:
        return None
    try:
        return (int(wt.get("day") or 1) - 1) * 24 * 60 + int(wt.get("minute") or 0)
    except (TypeError, ValueError):
        return None


def load_run(trace_dir: Path) -> dict[str, Any]:
    """The turns of one run, in order, with what the engine recorded about energy."""
    files = sorted(trace_dir.glob("turn-*-player.json"), key=lambda p: p.name)
    opening = sorted(trace_dir.glob("turn-*-opening.json"))
    start: dict[str, Any] = {}
    prev_abs: int | None = None
    if opening:
        try:
            pc = json.loads(opening[0].read_text(encoding="utf-8")).get("prompt_context") or {}
            start = dict(pc.get("resources") or {})
            prev_abs = _abs_minutes(pc.get("world_time"))
        except (OSError, json.JSONDecodeError):
            start = {}
    turns: list[dict[str, Any]] = []
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        pc = data.get("prompt_context") or {}
        tel = ((data.get("engine") or {}).get("telemetry")) or {}
        spend = tel.get("action_spend") or {}
        after = spend.get("resources_after") or pc.get("resources") or {}
        clock = (((data.get("engine") or {}).get("ledger") or {}).get("delta") or {}).get("clock") or {}
        minutes = None
        try:
            if clock:
                a = (int(clock["from"]["world_day"]) - 1) * 1440 + int(clock["from"]["world_minute"])
                b = (int(clock["to"]["world_day"]) - 1) * 1440 + int(clock["to"]["world_minute"])
                minutes = b - a
        except (KeyError, TypeError, ValueError):
            minutes = None
        now_abs = _abs_minutes(pc.get("world_time"))
        if minutes is None and now_abs is not None and prev_abs is not None:
            minutes = now_abs - prev_abs
        prev_abs = now_abs if now_abs is not None else prev_abs
        if not start:
            start = dict(pc.get("resources") or {})
        turns.append({
            "turn": int(data.get("turn") or 0),
            "line": str(data.get("player_input") or ""),
            "minutes": max(1, int(minutes or 6)),
            "kind": str(spend.get("kind") or "general"),
            "energy": after.get("energy"),
            "fatigue": after.get("fatigue"),
            "max_energy": after.get("max_energy"),
            "max_fatigue": after.get("max_fatigue"),
            "map_status": str((tel.get("map_walk") or {}).get("status") or ""),
            "prompt_context": pc,
        })
    return {"dir": str(trace_dir), "start": start, "turns": turns}


def reread_kind(turn: dict[str, Any]) -> str:
    """The kind the current code charges for this line (world._action_cost_kind)."""
    if turn.get("kind") == "ability":
        return "ability"
    from app.world import _action_cost_kind

    try:
        kind = _action_cost_kind(turn["line"], dict(turn.get("prompt_context") or {}), None)
    except Exception:
        return str(turn.get("kind") or "general")
    if kind == "travel" and turn.get("map_status") in {"no_map", ""}:
        kind = "journey"  # no town grid: the line pays its own walk (play_turn)
    return kind


def replay_run(
    run: dict[str, Any],
    *,
    first: int = 0,
    last: int = 10**9,
    reread: bool = False,
    start_full: bool = False,
) -> list[dict[str, Any]]:
    turns = [t for t in run["turns"] if first <= t["turn"] <= last]
    if not turns:
        return []
    before = [t for t in run["turns"] if t["turn"] < turns[0]["turn"]]
    seed = before[-1] if before else run.get("start") or {}
    max_energy = int(turns[0].get("max_energy") or seed.get("max_energy") or pr.BASE_ENERGY)
    max_fatigue = int(turns[0].get("max_fatigue") or seed.get("max_fatigue") or pr.BASE_FATIGUE_CAP)
    energy = int(seed.get("energy") if seed.get("energy") is not None else max_energy)
    fatigue = int(seed.get("fatigue") or 0)
    if start_full:
        # The window as a day of its own: rested, fatigue clear.
        energy, fatigue = max_energy, 0
    kinds = [(reread_kind(t) if reread else t["kind"], t["minutes"]) for t in turns]
    rows = replay_kinds(kinds, energy=energy, max_energy=max_energy, fatigue=fatigue, max_fatigue=max_fatigue)
    out = []
    prev_recorded = energy
    prev_replayed = energy
    for t, row in zip(turns, rows):
        recorded = t.get("energy")
        unexplained = (
            recorded is not None and not reread
            and abs((int(recorded) - prev_recorded) - (row["energy"] - prev_replayed)) >= 2
        )
        out.append({
            "turn": t["turn"],
            "kind": row["kind"],
            "recorded_kind": t["kind"],
            "minutes": row["minutes"],
            "recorded": recorded,
            "energy": row["energy"],
            "max_energy": max_energy,
            "fatigue": row["fatigue"],
            "blocked": row["blocked"],
            "unexplained": unexplained,
            "line": t["line"],
        })
        prev_recorded = int(recorded) if recorded is not None else prev_recorded
        prev_replayed = row["energy"]
    return out


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"turns": 0}
    max_e = max(1, int(rows[0].get("max_energy") or pr.BASE_ENERGY))
    energies = [r["energy"] for r in rows]
    return {
        "turns": len(rows),
        "end": energies[-1],
        "end_fraction": round(energies[-1] / max_e, 2),
        "min": min(energies),
        "turns_at_zero": sum(1 for e in energies if e <= 0),
        "blocked": sum(1 for r in rows if r.get("blocked")),
        "max_energy": max_e,
    }


def _bar(energy: int, max_energy: int, width: int = 20) -> str:
    filled = int(round(width * max(0, energy) / max(1, max_energy)))
    return "#" * filled + "." * (width - filled)


def print_rows(title: str, rows: list[dict[str, Any]], *, show_lines: bool = True) -> None:
    print(f"== {title}")
    for r in rows:
        rec = r.get("recorded")
        rec_s = f"{rec:>3}" if isinstance(rec, int) else "  -"
        kind = r["kind"] if r.get("recorded_kind") in (None, r["kind"]) else f"{r['kind']}<{r['recorded_kind']}"
        mark = "*" if r.get("unexplained") else " "
        line = ("  " + r["line"][:70].replace("\n", " ")) if show_lines and r.get("line") else ""
        turn = r.get("turn", "")
        print(f"T{turn!s:>4} {kind:<22} {r['minutes']:>4}m rec {rec_s} replay {r['energy']:>3}{mark} "
              f"{_bar(r['energy'], r['max_energy'])}{line}")
    print("   summary:", json.dumps(summarise(rows)))


def synthetic_rows(steps: list[tuple[str, int]], *, max_energy: int = 16) -> list[dict[str, Any]]:
    rows = replay_kinds(steps, energy=max_energy, max_energy=max_energy)
    return [dict(r, turn=i + 1, max_energy=max_energy, recorded=None, line="") for i, r in enumerate(rows)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("trace_dirs", nargs="*", type=Path)
    ap.add_argument("--from", dest="first", type=int, default=0)
    ap.add_argument("--to", dest="last", type=int, default=10**9)
    ap.add_argument("--reread", action="store_true")
    ap.add_argument("--start-full", action="store_true", help="start the window at full energy, fatigue 0")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    report: dict[str, Any] = {}
    if args.synthetic or not args.trace_dirs:
        day = synthetic_rows(ORDINARY_DAY)
        heavy = synthetic_rows(HEAVY_LABOUR)
        report["ordinary_day"] = summarise(day)
        report["heavy_labour"] = summarise(heavy)
        if not args.json:
            print_rows("synthetic ordinary day (max 16)", day, show_lines=False)
            print_rows("synthetic heavy labour (max 16)", heavy, show_lines=False)
    for trace_dir in args.trace_dirs:
        run = load_run(trace_dir)
        rows = replay_run(run, first=args.first, last=args.last, reread=args.reread, start_full=args.start_full)
        report[str(trace_dir)] = summarise(rows)
        if not args.json:
            print_rows(f"{trace_dir} ({'reread' if args.reread else 'recorded'} kinds)", rows)
    if args.json:
        print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
