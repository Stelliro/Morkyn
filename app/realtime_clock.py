"""Wall clock to world clock: ratio, pause and resume, catch-up ticks in Wait-sized slices.

Status: built, not wired (TODO n2).

One settings row, realtime_clock, holds the ratio (world minutes per real minute), the enabled and
paused flags and an anchor (a wall time and the abs world minute it corresponded to). No table is
created; ensure_schema() is a documented no-op. elapsed_world_minutes() says how many world minutes
real time owes the world since the anchor; plan_catch_up() turns the part not already covered by play
into slices of slice_minutes, each listed with the effects a Wait of that length has (advance_world_time,
apply_regen, roll_wait_events), capped at max_catch_up_minutes with the rest dropped and the anchor
re-based. catch_up() without an apply callable only returns that plan and writes nothing; with one (the
wiring passes wait_effects(conn), which calls the real advance_world_time, apply_regen and
roll_wait_events) it runs the slices and moves the anchor. It never moves the clock while a turn is in
flight (generation_progress / gpu_gate) or while travel_ready is false. The module writes only its own
settings row: never pacing, never travel_ready, never journal. Non-goal: hosted multiplayer. This is one
campaign's clock in one process; there is no networking, no session and no arbitration between players
here, and none is planned by this item. The live game does not call this module.

Wiring (not done):
  app/main.py:api_tts_config() / api_update_tts_config() -> the pattern for GET/POST /api/realtime-clock
      (realtime_clock.get_config() / realtime_clock.update_config(conn, payload)); a new POST
      /api/realtime-clock/tick calls realtime_clock.catch_up(conn, now_wall=time.time(),
      apply=realtime_clock.wait_effects(conn)) and returns the report plus state_view(conn).
  app/world.py:advance_world_time() -> the clock writer every slice uses, reached only through the apply
      callable (no change inside it).
  app/player_resources.py:apply_regen() and app/world.py:roll_wait_events() -> the other two slice effects,
      also reached only through the apply callable (wait_effects builds it).
  app/world.py:play_turn() / play_wait_turn() -> realtime_clock.pause(conn, reason="turn_in_flight") before
      the model call and realtime_clock.resume(conn, world_abs_now=world_abs_minutes(get_world_time(conn)))
      after apply_turn, so play minutes and real minutes never double count.
  app/world.py:start_playthrough() -> realtime_clock.reset_anchor(conn, world_abs_now=480) right after the
      init_world_clock call.
  app/world.py:rewind_last_turn() -> realtime_clock.resume(conn, world_abs_now=world_abs_minutes(get_world_time(conn)))
      when the clock is running, else realtime_clock.reset_anchor(conn, world_abs_now=...) with the same
      value, after the pacing rows are restored. The anchor is not in the snapshot (the row is a table rule,
      not turn state), so without this line a rewound turn's minutes would be owed again at the next tick.
  app/world.py:get_state() -> state.update(realtime_clock.state_view(conn)).
  static/app.js:startGenerationProgressPolling() -> the pattern for a poller hitting the tick route while the
      tab is visible and aiBusy is false; the wait summary line for each applied slice.

Turn on:
  [ ] settings row realtime_clock with enabled true (default off; AI_RPG_REALTIME_ENABLED overrides on read);
      not in SNAPSHOT_SETTING_KEYS (a table rule, like tts_config); no init_db / WORLD_TABLES / export entry
      because there is no table
  [ ] the tick route and the config routes
  [ ] pause/resume around play_turn, reset_anchor in start_playthrough, re-anchor in rewind_last_turn
  [ ] UI: ratio and pause controls in Settings; the poller
  [ ] prompt: none (the world_time line already carries the clock)

Tests: tests/test_realtime_clock.py
"""
from __future__ import annotations

import json
import math
import os
import time
from typing import Any, Callable

from app.db import connect
from app.player_resources import world_abs_minutes

# ---------------------------------------------------------------------------
# Rules tables (data)
# ---------------------------------------------------------------------------

SETTING_KEY = "realtime_clock"
RATIO_PRESETS: dict[str, float] = {
    "real": 1.0,
    "brisk": 4.0,
    "day_in_two_hours": 12.0,
    "day_in_hour": 24.0,
    "day_in_quarter_hour": 96.0,
}
RATIO_DEFAULT = 12.0
RATIO_MIN, RATIO_MAX = 0.1, 1440.0
SLICE_DEFAULT, SLICE_MIN, SLICE_MAX = 60, 5, 360  # SLICE_MAX = the largest WAIT_MINUTE_CHOICES entry
MAX_CATCH_UP_DEFAULT, MAX_CATCH_UP_MIN, MAX_CATCH_UP_MAX = 1440, 60, 10080  # one world day; a week at most
WORLD_DAY_MINUTES = 1440
PAUSE_REASONS = ("player", "turn_in_flight", "travel_pending", "setup", "disabled")
SLICE_EFFECTS = ("advance_world_time", "apply_regen", "roll_wait_events")  # what a Wait does, in order
SLICE_KIND = "wait"  # apply_regen kind; never "sleep" (the player did not choose to)
SKIP_REASONS = ("disabled", "paused", "no_anchor", "busy", "travel_pending", "nothing_due")
ENV_ENABLED, ENV_RATIO = "AI_RPG_REALTIME_ENABLED", "AI_RPG_REALTIME_RATIO"

# Keys update_config accepts from a payload; the anchor fields move only through the writers below.
CONFIG_KEYS = ("enabled", "ratio", "preset", "slice_minutes", "max_catch_up_minutes")

# Neutral crowd and danger for a slice when the wiring passes none (the live Wait reads them from
# world._local_crowd_danger; a wired tick route passes those values in).
DEFAULT_CROWD, DEFAULT_DANGER = 0.5, 0.2

# elapsed world minutes owed since the anchor:  floor((now_wall - anchor_wall) * ratio / 60)
# expected world minute now:                    anchor_world_minute + elapsed
# due:                                          expected - world_abs_now   (play minutes since the anchor count as paid)
# due <= 0 -> "nothing_due"; when play ran ahead the anchor is re-based to (now_wall, world_abs_now) so play
#             never runs ahead forever; when only a fraction of a world minute has passed the anchor is kept.


def _defaults() -> dict[str, Any]:
    return {
        "enabled": False,
        "paused": True,
        "ratio": RATIO_DEFAULT,
        "preset": "day_in_two_hours",
        "anchor_wall": None,
        "anchor_world_minute": None,
        "last_tick_wall": None,
        "slice_minutes": SLICE_DEFAULT,
        "max_catch_up_minutes": MAX_CATCH_UP_DEFAULT,
        "pause_reason": "",
        "paused_at_wall": None,
    }


# ---------------------------------------------------------------------------
# Small parsers
# ---------------------------------------------------------------------------


def _as_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off", ""}:
        return False
    return default


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _as_int(value: Any, default: int) -> int:
    parsed = _as_float(value)
    if parsed is None or math.isnan(parsed) or math.isinf(parsed):
        return default
    return int(parsed)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _opt_float(value: Any) -> float | None:
    parsed = _as_float(value)
    if parsed is None or math.isnan(parsed) or math.isinf(parsed):
        return None
    return parsed


def _opt_int(value: Any) -> int | None:
    parsed = _opt_float(value)
    return None if parsed is None else int(parsed)


def _preset_for(ratio: float) -> str:
    for key, value in RATIO_PRESETS.items():
        if abs(float(value) - float(ratio)) < 1e-9:
            return key
    return "custom"


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def resolve_ratio(value: Any) -> float:
    """A preset key or a number -> world minutes per real minute, clamped; RATIO_DEFAULT when unreadable."""
    if isinstance(value, str) and value.strip().lower() in RATIO_PRESETS:
        return float(RATIO_PRESETS[value.strip().lower()])
    parsed = _opt_float(value)
    if parsed is None or parsed <= 0:
        return RATIO_DEFAULT
    return float(_clamp(parsed, RATIO_MIN, RATIO_MAX))


def normalize_config(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Every key present with its type fixed; ratio, slice and cap clamped; preset derived from the ratio."""
    src = dict(raw) if isinstance(raw, dict) else {}
    cfg = _defaults()
    cfg["enabled"] = _as_bool(src.get("enabled"), default=False)
    cfg["paused"] = _as_bool(src.get("paused"), default=True)
    ratio_raw = src.get("ratio")
    preset_raw = str(src.get("preset") or "").strip().lower()
    if ratio_raw is None and preset_raw in RATIO_PRESETS:
        ratio_raw = RATIO_PRESETS[preset_raw]
    cfg["ratio"] = resolve_ratio(ratio_raw)
    cfg["preset"] = _preset_for(cfg["ratio"])
    cfg["anchor_wall"] = _opt_float(src.get("anchor_wall"))
    cfg["anchor_world_minute"] = _opt_int(src.get("anchor_world_minute"))
    if cfg["anchor_world_minute"] is not None and cfg["anchor_world_minute"] < 0:
        cfg["anchor_world_minute"] = 0
    cfg["last_tick_wall"] = _opt_float(src.get("last_tick_wall"))
    cfg["slice_minutes"] = int(_clamp(_as_int(src.get("slice_minutes"), SLICE_DEFAULT), SLICE_MIN, SLICE_MAX))
    cfg["max_catch_up_minutes"] = int(
        _clamp(_as_int(src.get("max_catch_up_minutes"), MAX_CATCH_UP_DEFAULT), MAX_CATCH_UP_MIN, MAX_CATCH_UP_MAX)
    )
    reason = str(src.get("pause_reason") or "").strip().lower()
    cfg["pause_reason"] = reason if reason in PAUSE_REASONS else ""
    cfg["paused_at_wall"] = _opt_float(src.get("paused_at_wall"))
    return cfg


def _anchored(cfg: dict[str, Any]) -> bool:
    return cfg.get("anchor_wall") is not None and cfg.get("anchor_world_minute") is not None


def _running(cfg: dict[str, Any]) -> bool:
    return bool(cfg.get("enabled")) and not bool(cfg.get("paused")) and _anchored(cfg)


def elapsed_world_minutes(cfg: dict[str, Any], now_wall: float) -> int:
    """World minutes real time owes since the anchor; 0 when disabled, paused or unanchored. Floors."""
    if not _running(cfg):
        return 0
    real_seconds = max(0.0, float(now_wall) - float(cfg["anchor_wall"]))
    return int(math.floor(real_seconds * float(cfg["ratio"]) / 60.0))


def wall_to_world(cfg: dict[str, Any], wall: float) -> int | None:
    """The abs world minute real time `wall` maps to under the anchor; None without an anchor."""
    if not _anchored(cfg):
        return None
    real_seconds = float(wall) - float(cfg["anchor_wall"])
    return int(cfg["anchor_world_minute"]) + int(math.floor(real_seconds * float(cfg["ratio"]) / 60.0))


def world_to_wall(cfg: dict[str, Any], world_abs_minute: int) -> float | None:
    """The real time at which abs world minute `world_abs_minute` falls due; None without an anchor."""
    if not _anchored(cfg):
        return None
    minutes = int(world_abs_minute) - int(cfg["anchor_world_minute"])
    return float(cfg["anchor_wall"]) + minutes * 60.0 / float(cfg["ratio"])


def slice_plan(total_minutes: int, slice_minutes: int) -> list[int]:
    """Full slices then the remainder; [] for a total of 0 or less."""
    total = int(total_minutes)
    if total <= 0:
        return []
    size = max(1, int(slice_minutes))
    full, rest = divmod(total, size)
    out = [size] * full
    if rest:
        out.append(rest)
    return out


def make_slice(minutes: int) -> dict[str, Any]:
    """One Slice: the effects of a Wait of that length, in order (contracts.md 1.18)."""
    return {"minutes": int(minutes), "kind": SLICE_KIND, "effects": list(SLICE_EFFECTS)}


def _fraction_seconds(cfg: dict[str, Any], now_wall: float) -> float:
    """Real seconds since the anchor not yet worth a whole world minute (kept when re-basing)."""
    real_seconds = max(0.0, float(now_wall) - float(cfg["anchor_wall"]))
    whole = math.floor(real_seconds * float(cfg["ratio"]) / 60.0)
    return max(0.0, real_seconds - whole * 60.0 / float(cfg["ratio"]))


def rebase_after(
    cfg: dict[str, Any], plan: dict[str, Any], *, applied_minutes: int, now_wall: float
) -> dict[str, Any]:
    """The anchor after `applied_minutes` of a tick plan ran: the world sits at world_abs_now + applied; the
    planned minutes still unapplied stay owed; the sub-minute fraction of real time is kept."""
    applied = max(0, min(int(applied_minutes), int(plan.get("apply_minutes") or 0)))
    world_minute = int(plan.get("world_abs_now") or 0) + applied
    still_owed = int(plan.get("apply_minutes") or 0) - applied
    fraction = _fraction_seconds(cfg, now_wall) if _anchored(cfg) else 0.0
    wall = float(now_wall) - still_owed * 60.0 / float(cfg["ratio"]) - fraction
    return {"wall": wall, "world_minute": world_minute}


def plan_catch_up(
    cfg: dict[str, Any],
    *,
    now_wall: float,
    world_abs_now: int,
    busy: bool = False,
    travel_pending: bool = False,
) -> dict[str, Any]:
    """The CatchUpPlan for one tick. Pure: nothing is read or written."""
    cfg = normalize_config(cfg)
    world_abs_now = max(0, int(world_abs_now))
    plan: dict[str, Any] = {
        "status": "skip",
        "reason": "",
        "due_minutes": 0,
        "apply_minutes": 0,
        "capped": False,
        "dropped_minutes": 0,
        "slices": [],
        "anchor_after": {
            "wall": cfg["anchor_wall"] if cfg["anchor_wall"] is not None else float(now_wall),
            "world_minute": cfg["anchor_world_minute"] if cfg["anchor_world_minute"] is not None else world_abs_now,
        },
        "world_abs_now": world_abs_now,
        "expected_world_minute": world_abs_now,
    }
    if not cfg["enabled"]:
        plan["reason"] = "disabled"
        return plan
    if cfg["paused"]:
        plan["reason"] = "paused"
        return plan
    if not _anchored(cfg):
        plan["reason"] = "no_anchor"
        return plan
    elapsed = elapsed_world_minutes(cfg, now_wall)
    expected = int(cfg["anchor_world_minute"]) + elapsed
    due = expected - world_abs_now
    plan["expected_world_minute"] = expected
    plan["due_minutes"] = due
    if busy:
        plan["reason"] = "busy"
        return plan
    if travel_pending:
        plan["reason"] = "travel_pending"
        return plan
    if due <= 0:
        plan["reason"] = "nothing_due"
        if world_abs_now > expected:
            plan["anchor_after"] = {"wall": float(now_wall), "world_minute": world_abs_now}
        return plan
    cap = int(cfg["max_catch_up_minutes"])
    apply_minutes = min(due, cap)
    plan["status"] = "tick"
    plan["apply_minutes"] = apply_minutes
    plan["capped"] = due > cap
    plan["dropped_minutes"] = due - apply_minutes
    plan["slices"] = [make_slice(m) for m in slice_plan(apply_minutes, cfg["slice_minutes"])]
    if plan["capped"]:
        # The dropped minutes are forgiven: the anchor jumps to now.
        plan["anchor_after"] = {"wall": float(now_wall), "world_minute": world_abs_now + apply_minutes}
    else:
        plan["anchor_after"] = rebase_after(cfg, plan, applied_minutes=apply_minutes, now_wall=now_wall)
    return plan


def describe(cfg: dict[str, Any]) -> str:
    """One plain sentence or two about the mapping and whether it is running."""
    cfg = normalize_config(cfg)
    ratio = float(cfg["ratio"])
    real_hours = 24.0 / ratio
    if real_hours >= 1.0:
        count = f"{real_hours:.1f}"
        span = f"{count} real hour" if count == "1.0" else f"{count} real hours"
    else:
        count = f"{real_hours * 60.0:.0f}"
        span = f"{count} real minute" if count == "1" else f"{count} real minutes"
    ratio_text = f"{ratio:.2f}".rstrip("0")
    if ratio_text.endswith("."):
        ratio_text += "0"
    text = f"One world day passes in {span} (ratio {ratio_text})."
    if not cfg["enabled"]:
        return f"Real-time clock is off. {text}"
    if cfg["paused"]:
        reason = str(cfg["pause_reason"] or "").replace("_", " ")
        return f"{text} Paused: {reason}." if reason else f"{text} Paused."
    if not _anchored(cfg):
        return f"{text} Not anchored yet."
    return f"{text} Running."


def next_tick_seconds(cfg: dict[str, Any], now_wall: float) -> int | None:
    """Real seconds until one more full slice is owed; None when the clock is not running."""
    cfg = normalize_config(cfg)
    if not _running(cfg):
        return None
    elapsed = elapsed_world_minutes(cfg, now_wall)
    size = int(cfg["slice_minutes"])
    owed_next = (elapsed // size + 1) * size
    due_wall = float(cfg["anchor_wall"]) + owed_next * 60.0 / float(cfg["ratio"])
    return max(0, int(math.ceil(due_wall - float(now_wall))))


# ---------------------------------------------------------------------------
# Busy signal (read-only)
# ---------------------------------------------------------------------------


def turn_in_flight() -> bool:
    """True while the draft pipeline reports a job or the gpu gate holds a model session; False on error."""
    try:
        from app.generation_progress import snapshot

        if bool(snapshot().get("active")):
            return True
    except Exception:
        return False
    try:
        from app.gpu_gate import gate_status

        active = gate_status().get("active") or {}
        return "llm" in active
    except Exception:
        return False


def travel_pending(conn) -> bool:
    """True when settings.travel_ready holds a false value (a long trip is held for a scene)."""
    row = conn.execute("SELECT value FROM settings WHERE key = ?", ("travel_ready",)).fetchone()
    if not row or row["value"] is None:
        return False
    raw = row["value"]
    try:
        decoded = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError, ValueError):
        decoded = raw
    if isinstance(decoded, bool):
        return not decoded
    return not _as_bool(decoded, default=True)


# ---------------------------------------------------------------------------
# Persistence: the one settings row
# ---------------------------------------------------------------------------


def ensure_schema(conn) -> None:
    """No table: the module keeps one settings row (SETTING_KEY). Kept so a wiring loop can call every
    module's ensure_schema the same way."""
    return None


def _read_row(conn) -> dict[str, Any]:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (SETTING_KEY,)).fetchone()
    if not row:
        return {}
    try:
        stored = json.loads(row["value"])
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    if not isinstance(stored, dict):
        return {}
    return {k: v for k, v in stored.items() if k in _defaults()}


def _write_row(conn, cfg: dict[str, Any]) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (SETTING_KEY, json.dumps(normalize_config(cfg), ensure_ascii=True)),
    )


def _apply_env(cfg: dict[str, Any]) -> dict[str, Any]:
    out = dict(cfg)
    enabled = os.getenv(ENV_ENABLED)
    if enabled is not None and str(enabled).strip():
        out["enabled"] = _as_bool(enabled, default=out["enabled"])
    ratio = os.getenv(ENV_RATIO)
    if ratio is not None and str(ratio).strip():
        out["ratio"] = resolve_ratio(ratio)
        out["preset"] = _preset_for(out["ratio"])
    return out


def _stored_config(conn) -> dict[str, Any]:
    """The row as stored, normalised, without env overrides (what the writers build on)."""
    return normalize_config({**_defaults(), **_read_row(conn)})


def get_config(conn=None) -> dict[str, Any]:
    """The stored row over the defaults, env overrides applied, every key present."""
    if conn is None:
        with connect() as owned:
            return get_config(owned)
    return normalize_config(_apply_env(_stored_config(conn)))


def _now(now_wall: float | None) -> float:
    return float(now_wall) if now_wall is not None else float(time.time())


def _world_abs_now(conn) -> int:
    from app.world import get_world_time  # read-only; lazy so importing this module stays light

    return int(world_abs_minutes(get_world_time(conn)))


def _playthrough_options(conn) -> dict[str, Any]:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", ("playthrough_options",)).fetchone()
    if not row:
        return {}
    try:
        decoded = json.loads(row["value"])
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


# ---------------------------------------------------------------------------
# Writers (own row only)
# ---------------------------------------------------------------------------


def _payload_value_readable(key: str, value: Any) -> bool:
    """True when a payload value for `key` parses; an unreadable one leaves the stored value alone."""
    if key == "ratio":
        if isinstance(value, str) and value.strip().lower() in RATIO_PRESETS:
            return True
        parsed = _opt_float(value)
        return parsed is not None and parsed > 0
    if key in ("slice_minutes", "max_catch_up_minutes"):
        return _opt_int(value) is not None
    if key == "enabled":
        if isinstance(value, (bool, int, float)):
            return True
        return str(value).strip().lower() in {"1", "true", "yes", "on", "0", "false", "no", "off"}
    return True


def update_config(conn, payload: dict[str, Any], *, now_wall: float | None = None) -> dict[str, Any]:
    """Partial update of the config keys; unknown keys and unreadable values are ignored. A ratio change on
    a running clock re-anchors at the world minute the old ratio had reached, so no owed minute is lost or
    doubled."""
    if not isinstance(payload, dict):
        raise ValueError("realtime_clock.update_config needs a dict payload")
    stored = _stored_config(conn)
    merged = dict(stored)
    used: set[str] = set()
    for key in CONFIG_KEYS:
        if key not in payload or payload[key] is None or not _payload_value_readable(key, payload[key]):
            continue
        merged[key] = payload[key]
        used.add(key)
    if "preset" in payload and "ratio" not in used:
        preset = str(payload.get("preset") or "").strip().lower()
        if preset in RATIO_PRESETS:
            merged["ratio"] = RATIO_PRESETS[preset]
    nxt = normalize_config(merged)
    now = _now(now_wall)
    if _running(stored) and abs(nxt["ratio"] - stored["ratio"]) > 1e-9:
        reached = wall_to_world(stored, now)
        nxt["anchor_wall"] = now
        nxt["anchor_world_minute"] = int(reached if reached is not None else stored["anchor_world_minute"])
    if stored["enabled"] and not nxt["enabled"]:
        nxt["paused"] = True
        nxt["pause_reason"] = "disabled"
        nxt["paused_at_wall"] = now
    elif not stored["enabled"] and nxt["enabled"] and nxt["pause_reason"] == "disabled":
        nxt["pause_reason"] = ""
    _write_row(conn, nxt)
    return get_config(conn)


def pause(conn, *, reason: str = "player", now_wall: float | None = None) -> dict[str, Any]:
    """Stop the mapping; the paused span owes nothing once resume() re-anchors."""
    cfg = _stored_config(conn)
    word = str(reason or "player").strip().lower()
    cfg["paused"] = True
    cfg["pause_reason"] = word if word in PAUSE_REASONS else "player"
    cfg["paused_at_wall"] = _now(now_wall)
    _write_row(conn, cfg)
    return get_config(conn)


def resume(conn, *, now_wall: float | None = None, world_abs_now: int | None = None) -> dict[str, Any]:
    """Anchor at (now, world_abs_now or the stored world clock) and run. A disabled row is left as it is and
    comes back with pause_reason "disabled"."""
    cfg = get_config(conn)
    if not cfg["enabled"]:
        out = dict(cfg)
        out["pause_reason"] = "disabled"
        return out
    stored = _stored_config(conn)
    world_minute = int(world_abs_now) if world_abs_now is not None else _world_abs_now(conn)
    stored["paused"] = False
    stored["pause_reason"] = ""
    stored["paused_at_wall"] = None
    stored["anchor_wall"] = _now(now_wall)
    stored["anchor_world_minute"] = max(0, world_minute)
    _write_row(conn, stored)
    return get_config(conn)


def reset_anchor(conn, *, now_wall: float | None = None, world_abs_now: int = 480) -> dict[str, Any]:
    """New game: anchor at (now, world_abs_now) and forget the last tick; enabled and paused stay as set."""
    cfg = _stored_config(conn)
    cfg["anchor_wall"] = _now(now_wall)
    cfg["anchor_world_minute"] = max(0, int(world_abs_now))
    cfg["last_tick_wall"] = None
    _write_row(conn, cfg)
    return get_config(conn)


def commit_tick(conn, plan: dict[str, Any], *, now_wall: float) -> dict[str, Any]:
    """Move anchor_* (and last_tick_wall) after a tick; a skip plan re-bases only for nothing_due. A tick plan
    carrying applied_minutes of 0 (every slice failed) moves the anchor but does not stamp last_tick_wall."""
    plan = plan if isinstance(plan, dict) else {}
    status = str(plan.get("status") or "")
    reason = str(plan.get("reason") or "")
    after = plan.get("anchor_after") if isinstance(plan.get("anchor_after"), dict) else None
    if after is None or not (status == "tick" or (status == "skip" and reason == "nothing_due")):
        return get_config(conn)
    cfg = _stored_config(conn)
    wall = _opt_float(after.get("wall"))
    minute = _opt_int(after.get("world_minute"))
    if wall is None or minute is None:
        return get_config(conn)
    cfg["anchor_wall"] = wall
    cfg["anchor_world_minute"] = max(0, minute)
    applied = _as_int(plan.get("applied_minutes", plan.get("apply_minutes")), 0)
    if status == "tick" and applied > 0:
        cfg["last_tick_wall"] = float(now_wall)
    _write_row(conn, cfg)
    return get_config(conn)


# ---------------------------------------------------------------------------
# The tick
# ---------------------------------------------------------------------------


def catch_up(
    conn,
    *,
    now_wall: float | None = None,
    apply: Callable[[dict[str, Any]], Any] | None = None,
    busy: bool | None = None,
) -> dict[str, Any]:
    """Plan the owed slices and, when `apply` is given, run them in order and commit the anchor. Without
    `apply` nothing is written. An exception from `apply` stops the loop; the slices already applied are
    committed and the rest stays owed. Never raises for a busy, paused or disabled clock."""
    cfg = get_config(conn)
    now = _now(now_wall)
    world_abs_now = _world_abs_now(conn)
    is_busy = bool(busy) if busy is not None else turn_in_flight()
    plan = plan_catch_up(
        cfg, now_wall=now, world_abs_now=world_abs_now, busy=is_busy, travel_pending=travel_pending(conn)
    )
    report: dict[str, Any] = {"plan": plan, "applied": [], "applied_minutes": 0, "error": "", "config": cfg}
    if apply is None:
        return report
    applied: list[Any] = []
    applied_minutes = 0
    error = ""
    for item in plan["slices"]:
        try:
            applied.append(apply(item))
        except Exception as exc:  # the slices already applied are kept; the rest stays owed
            error = f"{type(exc).__name__}: {exc}"[:240]
            break
        applied_minutes += int(item["minutes"])
    commit_plan = plan
    if plan["status"] == "tick" and applied_minutes < plan["apply_minutes"]:
        commit_plan = dict(plan)
        commit_plan["applied_minutes"] = applied_minutes
        commit_plan["anchor_after"] = rebase_after(cfg, plan, applied_minutes=applied_minutes, now_wall=now)
    report["applied"] = applied
    report["applied_minutes"] = applied_minutes
    report["error"] = error
    report["config"] = commit_tick(conn, commit_plan, now_wall=now)
    return report


def wait_effects(
    conn,
    *,
    options: dict[str, Any] | None = None,
    crowd: float | None = None,
    danger: float | None = None,
    seed: int | None = None,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """The apply callable a wiring passes to catch_up: for one Slice it runs advance_world_time, apply_regen
    (kind "wait") and roll_wait_events, in that order, and returns their results. The three writers are
    imported here, not at module level, so importing this module stays light. Crowd and danger default to
    neutral values when the wiring passes none; the seed defaults to a mix of the world minute before the
    slice and its length, so a replay rolls the same events."""
    from app.player_resources import apply_regen  # lazy on purpose; see the docstring
    from app.world import advance_world_time, get_world_time, roll_wait_events

    opts = options if isinstance(options, dict) else _playthrough_options(conn)
    crowd_value = float(_clamp(float(crowd), 0.0, 1.0)) if crowd is not None else DEFAULT_CROWD
    danger_value = float(_clamp(float(danger), 0.0, 1.0)) if danger is not None else DEFAULT_DANGER

    def _apply(item: dict[str, Any]) -> dict[str, Any]:
        minutes = max(1, int((item or {}).get("minutes") or 0))
        before_abs = int(world_abs_minutes(get_world_time(conn)))
        roll_seed = int(seed) if seed is not None else ((before_abs * 10007) ^ (minutes * 17))
        time_pack = advance_world_time(conn, minutes)
        regen_pack = apply_regen(conn, minutes=minutes, kind=SLICE_KIND, options=opts)
        events_pack = roll_wait_events(minutes=minutes, crowd=crowd_value, danger=danger_value, seed=roll_seed)
        return {"time": time_pack, "regen": regen_pack, "events": events_pack}

    return _apply


def state_view(conn, *, now_wall: float | None = None) -> dict[str, Any]:
    """The slice of state a wired get_state() would merge in."""
    cfg = get_config(conn)
    now = _now(now_wall)
    return {
        "realtime_clock": {
            "enabled": bool(cfg["enabled"]),
            "paused": bool(cfg["paused"]),
            "ratio": float(cfg["ratio"]),
            "preset": str(cfg["preset"]),
            "pause_reason": str(cfg["pause_reason"]),
            "next_tick_seconds": next_tick_seconds(cfg, now),
            "label": describe(cfg),
        }
    }
