"""
What the engine did during one turn, why, and how long it took.

The model trace shows what the model was asked and what it answered; it did
not show what the engine then wrote. Run 5 bugs (+50 gold on a walk, wages
that never arrived, a payment read the wrong way round) had to be guessed from
before/after numbers. A ledger is opened around each turn entry point
(``@recorded``) and records:

- ``writes``: every INSERT/UPDATE/DELETE on the save, with the app code
  (file:line function, innermost first) that issued it. Captured through the
  SQLite trace callback, so no write site needs instrumenting.
- ``swallowed``: every exception app code caught during the turn (the engine
  has hundreds of ``except Exception: pass``), with where it was raised and
  where it was caught. Captured through ``sys.monitoring``.
- ``notes``: decisions that leave no write (an op refused, a move dropped).
  Added with ``note(area, decision, ...)``.
- ``model_calls`` and ``phases``: the seconds of each model call (and of the
  wait for the GPU before it) and of named steps (``with phase("opening")``).
- ``delta``: player, pack, place, clock and new rows, before vs after, each
  change listing the writes that made it.

The ledger is attached to the turn's model trace file as ``engine``, and one
line per turn goes to ``timings.jsonl`` in the trace dir (never pruned): the
turn's seconds split into model, GPU wait and engine time, and the gap since
the previous turn ended (the player's reading and typing time). Only the
thread that opened the ledger is recorded; other threads (the spectator
server) see none.
"""
from __future__ import annotations

import json
import sys
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Iterator

MAX_WRITES = 1500
MAX_NOTES = 400
MAX_SWALLOWED = 300
SQL_CHARS = 400
FRAMES = 4

_WRITE_VERBS = ("INSERT", "UPDATE", "DELETE", "REPLACE")
_SKIP_FILES = ("turn_ledger.py", "db.py")
_CONVERTERS = frozenset({
    "_int", "_float", "_i", "_f", "_json", "_int_or_none", "_float_or_none", "_int_from_any", "_safe_int",
    "_safe_float", "_to_int", "_to_float", "_as_int", "_as_float",
})
_ROW_TABLES = ("npcs", "locations", "quests", "quest_steps", "world_facts", "events", "gm_events", "titles")


class Ledger:
    def __init__(self, label: str):
        self.label = label
        self.thread = threading.get_ident()
        self.started = time.time()
        self.writes: list[dict[str, Any]] = []
        self.writes_dropped = 0
        self.notes: list[dict[str, Any]] = []
        self.swallowed: dict[str, dict[str, Any]] = {}
        self.model_calls: list[dict[str, Any]] = []
        self.phases: list[dict[str, Any]] = []
        self.before: dict[str, Any] | None = None
        self.trace_paths: list[str] = []

    def on_sql(self, statement: str) -> None:
        if threading.get_ident() != self.thread:
            return
        text = (statement or "").lstrip()
        head = text[:12].upper()
        if not head.startswith(_WRITE_VERBS):
            return
        if len(self.writes) >= MAX_WRITES:
            self.writes_dropped += 1
            return
        verb = head.split()[0] if head.split() else head
        self.writes.append({
            "op": verb,
            "table": _table_of(text, verb),
            "sql": text[:SQL_CHARS],
            "at": _app_frames(),
        })

    def on_swallowed(self, code, exc: BaseException) -> None:
        caught = f"{_short_file(code.co_filename)} {code.co_name}"
        raised = ""
        tb = exc.__traceback__
        while tb is not None and tb.tb_next is not None:
            tb = tb.tb_next
        if tb is not None:
            raised = f"{_short_file(tb.tb_frame.f_code.co_filename)}:{tb.tb_lineno} {tb.tb_frame.f_code.co_name}"
        key = f"{type(exc).__name__}|{raised}|{caught}"
        entry = self.swallowed.get(key)
        if entry is not None:
            entry["count"] += 1
            return
        if len(self.swallowed) >= MAX_SWALLOWED:
            return
        entry = {
            "type": type(exc).__name__,
            "message": str(exc)[:300],
            "raised_at": raised,
            "caught_in": caught,
            "count": 1,
        }
        # A converter falling back on a blank value (_int(None), _json("")) is
        # routine; flagged so the real failures read first.
        if code.co_name in _CONVERTERS and isinstance(exc, (TypeError, ValueError)):
            entry["routine"] = True
        self.swallowed[key] = entry

    def timing(self, finished: float | None = None) -> dict[str, Any]:
        end = finished if finished is not None else time.time()
        seconds = round(end - self.started, 3)
        model = round(sum(c.get("seconds") or 0 for c in self.model_calls), 3)
        gpu = round(sum(c.get("gpu_wait") or 0 for c in self.model_calls), 3)
        return {
            "started": _iso(self.started),
            "finished": _iso(end),
            "seconds": seconds,
            "model_seconds": model,
            "gpu_wait_seconds": gpu,
            "engine_seconds": round(max(0.0, seconds - model - gpu), 3),
            "model_call_count": len(self.model_calls),
            "phases": list(self.phases),
        }

    def dump(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "label": self.label,
            "timing": self.timing(),
            "model_calls": list(self.model_calls),
            "notes": list(self.notes),
            "swallowed": sorted(self.swallowed.values(), key=lambda e: bool(e.get("routine"))),
            "writes": list(self.writes),
        }
        if self.writes_dropped:
            out["writes_dropped"] = self.writes_dropped
        return out


_CURRENT: ContextVar[Ledger | None] = ContextVar("morkyn_turn_ledger", default=None)


def current() -> Ledger | None:
    ledger = _CURRENT.get()
    if ledger is not None and ledger.thread != threading.get_ident():
        return None
    return ledger


def attach(conn) -> None:
    """Called by app.db.connect: route this connection's SQL to the open ledger."""
    ledger = current()
    if ledger is None:
        return
    try:
        conn.set_trace_callback(ledger.on_sql)
    except Exception:
        pass


def note(area: str, decision: str, **detail: Any) -> None:
    """Record an engine decision that may leave no write (a refusal, a drop)."""
    ledger = current()
    if ledger is None or len(ledger.notes) >= MAX_NOTES:
        return
    entry: dict[str, Any] = {"area": area, "decision": decision}
    for key, value in detail.items():
        entry[key] = _short(value)
    entry["at"] = _app_frames(limit=2)
    ledger.notes.append(entry)


def model_call(seconds: float, gpu_wait: float, prompt_chars: int, reply_chars: int, error: str = "") -> None:
    """One model request (app.llm._chat_content): its time, the GPU wait before it, its size."""
    ledger = current()
    if ledger is None:
        return
    entry: dict[str, Any] = {
        "seconds": round(seconds, 3),
        "gpu_wait": round(gpu_wait, 3),
        "prompt_chars": int(prompt_chars),
        "reply_chars": int(reply_chars),
        "at": _app_frames(limit=3, skip_files=_SKIP_FILES + ("llm.py", "gpu_gate.py", "contextlib.py")),
    }
    if error:
        entry["error"] = error[:200]
    ledger.model_calls.append(entry)


@contextmanager
def phase(name: str) -> Iterator[None]:
    """Time a named step of a turn or of the setup (``with phase("opening"):``)."""
    ledger = current()
    started = time.time()
    try:
        yield
    finally:
        if ledger is not None:
            ledger.phases.append({"phase": name, "seconds": round(time.time() - started, 3)})


def recorded(label: str) -> Callable:
    """Open a ledger around a turn entry point; nested entry points join the outer one."""

    def wrap(fn: Callable) -> Callable:
        @wraps(fn)
        def inner(*args, **kwargs):
            if current() is not None:
                return fn(*args, **kwargs)
            ledger = Ledger(label)
            token = _CURRENT.set(ledger)
            _monitor_on(ledger)
            try:
                ledger.before = _safe_snapshot()
                return fn(*args, **kwargs)
            finally:
                _monitor_off(ledger)
                _CURRENT.reset(token)
                _finish(ledger)

        return inner

    return wrap


def engine_section(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """The ``engine`` block for a trace file being written mid-turn."""
    ledger = current()
    section: dict[str, Any] = {"telemetry": extra or {}}
    if ledger is None:
        section["ledger"] = None
        return section
    section["ledger"] = ledger.dump()
    section["ledger"]["complete"] = False
    return section


def remember_trace(path: str) -> None:
    """The open turn's trace file: the full ledger is written into it at turn end."""
    ledger = current()
    if ledger is not None and path:
        ledger.trace_paths.append(str(path))


_LAST: list[dict[str, Any] | None] = [None]


def last_finished() -> dict[str, Any] | None:
    """The most recently closed ledger (the harness copies it into its turn record)."""
    return _LAST[0]


def clear_last() -> None:
    _LAST[0] = None


def _finish(ledger: Ledger) -> None:
    finished = time.time()
    after = _safe_snapshot()
    body = ledger.dump()
    body["timing"] = ledger.timing(finished)
    body["complete"] = True
    body["delta"] = state_delta(ledger.before or {}, after or {}, ledger.writes)
    for raw in ledger.trace_paths:
        path = Path(raw)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            engine = data.get("engine") if isinstance(data.get("engine"), dict) else {}
            engine["ledger"] = body
            data["engine"] = engine
            path.write_text(json.dumps(data, ensure_ascii=True, indent=2, default=str), encoding="utf-8")
        except Exception:
            continue
    try:
        _append_timing(ledger, body, after or {})
    except Exception:
        pass
    _LAST[0] = body


# ---- timings.jsonl -------------------------------------------------------


def timings_path() -> Path:
    from app.world import model_trace_dir

    return model_trace_dir() / "timings.jsonl"


def _last_timing_line(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - 8192))
            tail = handle.read().decode("utf-8", "replace").strip().splitlines()
        return json.loads(tail[-1]) if tail else None
    except Exception:
        return None


def _append_timing(ledger: Ledger, body: dict[str, Any], after: dict[str, Any]) -> None:
    try:
        from app.world import campaign_id

        cid = campaign_id()
    except Exception:
        cid = ""
    path = timings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    timing = dict(body["timing"])
    line: dict[str, Any] = {
        "campaign": cid,
        "label": ledger.label,
        "turn": _int((after.get("clock") or {}).get("turn")),
        **timing,
        "gap_since_previous": None,
        "trace": [Path(p).name for p in ledger.trace_paths],
        "writes": len(ledger.writes),
        "swallowed": sum(e["count"] for e in ledger.swallowed.values() if not e.get("routine")),
        "swallowed_routine": sum(e["count"] for e in ledger.swallowed.values() if e.get("routine")),
    }
    previous = _last_timing_line(path)
    if previous and previous.get("campaign") == cid and previous.get("finished"):
        try:
            gap = ledger.started - datetime.fromisoformat(previous["finished"]).timestamp()
            line["gap_since_previous"] = round(gap, 3)
        except Exception:
            pass
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, ensure_ascii=True, default=str) + "\n")


def log_request(method: str, path: str, status: int, started: float, finished: float) -> None:
    """One line per state-changing API request (app.main middleware), in ``requests.jsonl``.

    Setup-page calls (randomize, compose, name draws, the setup itself) happen
    before any turn ledger exists; with these lines the time from opening the
    setup to the first turn can be read off one timeline.
    """
    try:
        from app.world import model_trace_dir

        path_out = model_trace_dir() / "requests.jsonl"
        path_out.parent.mkdir(parents=True, exist_ok=True)
        line = {
            "method": method,
            "path": path,
            "status": int(status),
            "started": _iso(started),
            "finished": _iso(finished),
            "seconds": round(finished - started, 3),
        }
        with _REQ_LOCK, path_out.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, ensure_ascii=True) + "\n")
    except Exception:
        pass


_REQ_LOCK = threading.Lock()


# ---- swallowed exceptions (sys.monitoring) -------------------------------

_TOOL_ID: list[int | None] = [None]
_ACTIVE: list[Ledger] = []
_MON_LOCK = threading.Lock()


def _on_handled(code, _offset, exc):
    filename = code.co_filename.replace("\\", "/")
    if "/app/" not in filename or filename.endswith("turn_ledger.py"):
        return None
    ledger = current()
    if ledger is not None:
        try:
            ledger.on_swallowed(code, exc)
        except Exception:
            pass
    return None


def _monitor_on(ledger: Ledger) -> None:
    mon = getattr(sys, "monitoring", None)
    if mon is None:
        return
    with _MON_LOCK:
        _ACTIVE.append(ledger)
        if _TOOL_ID[0] is not None:
            return
        for tool in (4, 3, 2):
            try:
                mon.use_tool_id(tool, "morkyn-turn-ledger")
            except ValueError:
                continue  # in use (a debugger, coverage)
            mon.register_callback(tool, mon.events.EXCEPTION_HANDLED, _on_handled)
            mon.set_events(tool, mon.events.EXCEPTION_HANDLED)
            _TOOL_ID[0] = tool
            return


def _monitor_off(ledger: Ledger) -> None:
    mon = getattr(sys, "monitoring", None)
    if mon is None:
        return
    with _MON_LOCK:
        if ledger in _ACTIVE:
            _ACTIVE.remove(ledger)
        tool = _TOOL_ID[0]
        if _ACTIVE or tool is None:
            return
        try:
            mon.set_events(tool, 0)
            mon.register_callback(tool, mon.events.EXCEPTION_HANDLED, None)
            mon.free_tool_id(tool)
        finally:
            _TOOL_ID[0] = None


# ---- snapshot and delta -------------------------------------------------


def _safe_snapshot() -> dict[str, Any] | None:
    try:
        return snapshot()
    except Exception:
        return None


def snapshot() -> dict[str, Any]:
    from app.db import connect

    out: dict[str, Any] = {}
    # A snapshot must not log itself into the ledger it is taken for.
    token = _CURRENT.set(None)
    try:
        with connect().closing() as conn:
            row = conn.execute("SELECT * FROM player LIMIT 1").fetchone()
            out["player"] = {k: row[k] for k in row.keys()} if row else {}
            loc_id = out["player"].get("current_location_id")
            loc = conn.execute("SELECT id, code, name FROM locations WHERE id = ?", (loc_id,)).fetchone() if loc_id else None
            out["location"] = f"{loc['name']} ({loc['code']})" if loc else ""
            out["inventory"] = {
                str(r["name"]): int(r["quantity"] or 0)
                for r in conn.execute("SELECT name, quantity FROM inventory")
            }
            out["clock"] = {
                str(r["key"]): str(r["value"])
                for r in conn.execute("SELECT key, value FROM pacing WHERE key IN ('turn', 'world_day', 'world_minute')")
            }
            maxes: dict[str, int] = {}
            for table in _ROW_TABLES:
                try:
                    maxes[table] = int(conn.execute(f"SELECT COALESCE(MAX(id), 0) FROM {table}").fetchone()[0])
                except Exception:
                    continue
            out["max_ids"] = maxes
    finally:
        _CURRENT.reset(token)
    return out


def _new_rows(table: str, after_id: int) -> list[str]:
    from app.db import connect

    token = _CURRENT.set(None)
    try:
        with connect().closing() as conn:
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
            label = next((c for c in ("name", "title", "fact", "content", "summary", "description", "kind") if c in cols), None)
            pick = f"id, {label}" if label else "id"
            rows = conn.execute(f"SELECT {pick} FROM {table} WHERE id > ? ORDER BY id LIMIT 40", (after_id,)).fetchall()
            return [f"#{r[0]} {str(r[1])[:120]}" if label else f"#{r[0]}" for r in rows]
    except Exception:
        return []
    finally:
        _CURRENT.reset(token)


def state_delta(before: dict[str, Any], after: dict[str, Any], writes: list[dict[str, Any]]) -> dict[str, Any]:
    delta: dict[str, Any] = {}
    if not before or not after:
        return {"error": "no snapshot"}

    def by(table: str, column: str | None = None) -> list[int]:
        hits = []
        for i, w in enumerate(writes):
            if w.get("table") != table:
                continue
            if column and w.get("op") == "UPDATE" and column not in w.get("sql", ""):
                continue
            hits.append(i)
        return hits

    player: dict[str, Any] = {}
    for key, old in (before.get("player") or {}).items():
        new = (after.get("player") or {}).get(key)
        if new != old:
            change: dict[str, Any] = {"from": old, "to": new, "writes": by("player", key)}
            if not change["writes"]:
                change["unattributed"] = True
            player[key] = change
    if player:
        delta["player"] = player
    if before.get("location") != after.get("location"):
        delta["location"] = {"from": before.get("location"), "to": after.get("location")}
    inv_b, inv_a = before.get("inventory") or {}, after.get("inventory") or {}
    inv: dict[str, Any] = {}
    for name in sorted(set(inv_b) | set(inv_a)):
        if inv_b.get(name, 0) != inv_a.get(name, 0):
            inv[name] = {"from": inv_b.get(name, 0), "to": inv_a.get(name, 0)}
    if inv:
        inv["_writes"] = by("inventory")
        delta["inventory"] = inv
    if before.get("clock") != after.get("clock"):
        delta["clock"] = {"from": before.get("clock"), "to": after.get("clock"), "writes": by("pacing")}
    for table, old_max in (before.get("max_ids") or {}).items():
        if int((after.get("max_ids") or {}).get(table, 0)) > int(old_max):
            delta.setdefault("new_rows", {})[table] = {"rows": _new_rows(table, int(old_max)), "writes": by(table)}
    return delta


# ---- helpers -----------------------------------------------------------


def _table_of(sql: str, verb: str) -> str:
    words = sql.replace("(", " ").replace("\n", " ").split()
    upper = [w.upper() for w in words]
    try:
        if verb == "UPDATE":
            i = 1
            if len(upper) > 2 and upper[1] == "OR":
                i = 3
            return words[i].strip('"`[]')
        if verb == "DELETE":
            return words[upper.index("FROM") + 1].strip('"`[]')
        return words[upper.index("INTO") + 1].strip('"`[]')
    except (ValueError, IndexError):
        return ""


def _short_file(name: str) -> str:
    return name.replace("\\", "/").rsplit("/", 1)[-1]


def _app_frames(limit: int = FRAMES, skip_files: tuple[str, ...] = _SKIP_FILES) -> list[str]:
    frames: list[str] = []
    frame = sys._getframe(2)
    while frame is not None and len(frames) < limit:
        name = frame.f_code.co_filename.replace("\\", "/")
        if ("/app/" in name or "/tools/" in name) and not name.endswith(skip_files):
            frames.append(f"{_short_file(name)}:{frame.f_lineno} {frame.f_code.co_name}")
        frame = frame.f_back
    return frames


def _iso(stamp: float) -> str:
    return datetime.fromtimestamp(stamp, timezone.utc).isoformat()


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _short(value: Any) -> Any:
    if isinstance(value, str):
        return value[:600]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    try:
        text = json.dumps(value, ensure_ascii=True, default=str)
    except Exception:
        text = str(value)
    return json.loads(text) if len(text) <= 1500 else text[:1500]
