"""Capture and restraint: movement hard-block, in-place play, release conditions, trusted position set.

Status: built, not wired (TODO n13).

When the player is captured the engine, not the prose, must hold them: free steps, town walks, Travel
presses and typed MOVE ops are refused with one verdict, in-place play (talk, wait, rest, train, look,
status windows, escape attempts) stays open, and release comes from world time or a condition (a skill
level, a quest stage, a payment, a world event, the captor letting go). Guards taking the player
somewhere is a planned path over the existing map walkers, not a teleport, and the position write is a
plan the engine applies with its own writers. A capture counts only when the prose signal is backed by
an engine fact (a lost opposed check, a lost fight, an outnumbered ambush, the player's own surrender,
or an engine event); flavour alone never locks anyone. State is one settings row (`restraint`) and one
audit table (`restraint_log`); nothing here writes the player row, the map, town_position or the
existing movement_locked / map_blank keys, and the live game does not call this module.

Wiring (not done):
  app/db.py:_migrate_columns() tail -> try: restraint.ensure_schema(conn) except Exception: pass
  app/world.py:SNAPSHOT_SETTING_KEYS -> add "restraint" (rewind restores it; _clear_playthrough deletes it)
  app/world.py:WORLD_TABLES + RESTORE_ORDER + AUTOINC_TABLES + the tuple in _restore_snapshot_rows() -> "restraint_log"
  app/world.py:_clear_playthrough() -> DELETE FROM restraint_log (not keyed by campaign_id)
  app/main.py:_location_special_runtime() -> merge restraint.runtime_flags() (movement_locked |= flags["movement_locked"], label, hint, reason)
  app/world.py:_map_is_locked() -> `or restraint.is_locked(conn)` (covers the story walk and town_moves.plan_turn)
  app/world.py:_apply_player() before _find_location_id -> v = restraint.may_move(conn, "location_move", {"location_code": code}); blocked -> patch["move_to_location"] = patch["move_to_location_code"] = None, journal v["message"]
  app/world.py:apply_turn() after resolve_movement -> movement_report["status"] = "blocked_restrained" when blocked so _cut_prose_at_refused_move trims the prose
  app/town_moves.py:plan_exit() / walk_out() / walk_to_cell() / click_walk() -> restraint.may_move(conn, "town_leave" | "town_walk", target); blocked -> raise PermissionError(v["message"]) (the "too tired" path)
  app/turn_prompts.py:walk_in_town() and app/main.py:_travel_press() -> restraint.may_move(conn, "travel_press", None) first
  app/main.py:api_tile_map_move() -> restraint.may_move(conn, "map_step", {"x": tx, "y": ty}) beside the 409 guard
  app/world.py:play_turn() before the prompt -> a = restraint.allowed_actions(state, player_input); refused -> mechanics_context["restraint"] = a and the draft is told
  app/world.py:build_prompt_context() -> restraint.prompt_block(state, world_time) beside the resource lines
  app/world.py:play_wait_turn() -> restraint.wait_allowed(state, minutes) (always allowed; clamps nothing today)
  app/world.py:advance_world_time() after tick_weather -> restraint.tick(conn, world_time=after) (time conditions)
  app/world.py:apply_turn() after quests are applied -> restraint.tick(conn) again (quest, skill, payment, event conditions change without minutes passing)
  app/world.py:play_turn() after the skill checks -> verdict = restraint.classify_capture(narration=..., checks=..., combat=..., player_input=...); verdict["verdict"] == "capture" -> restraint.capture(conn, restraint.propose_capture(verdict, ...), turn=, world_time=) with _capture_pre_turn_rows(..., setting_keys=("restraint",)) first
  app/world.py:apply_map_travel_step() encounter branch -> classify_capture(encounter=travel["encounter"], ...) for an ambush that takes the player
  app/world.py:play_world_event_turn() -> payload["restrain"] / payload["escort"] handled through capture() / plan_escort(); WORLD_EVENT_KINDS gains "restraint"
  app/turn_dsl.py:_apply_op() -> RESTRAIN / RELEASE / ESCORT lines parsed by restraint.parse_restraint_op(entry) into turn["_dsl"]["restraint"] once OPCODES lists them; apply_turn reads them as model assertions (prose signal, never corroboration)
  app/world.py:get_state() near the turn_prompts.state_view merge -> state.update(restraint.state_view(conn))
  escort apply: restraint.apply_position(conn, plan, writers={"location": ..., "token": ..., "town": ...}) with tile_world.restore_player_position / town_moves._set_marker / town_moves.enter_town / the player UPDATE as the writers; the leg loop copies main._travel_press and feeds restraint.escort_travel_dict(leg) to _spend_travel

Turn on:
  [ ] playthrough_options.restraint_enabled (default off), read by the wiring at every hook
  [ ] init_db: ensure_schema call in _migrate_columns; "restraint" in SNAPSHOT_SETTING_KEYS; "restraint_log" in WORLD_TABLES / RESTORE_ORDER / AUTOINC_TABLES and the rewind tuple; _clear_playthrough delete
  [ ] movement guards: _location_special_runtime, _map_is_locked, _apply_player, town_moves walks, walk_in_town / _travel_press, api_tile_map_move
  [ ] turn hooks: allowed_actions + prompt_block in play_turn / build_prompt_context; tick in advance_world_time and apply_turn; classify_capture after checks and in the encounter branch
  [ ] events: "restraint" kind in WORLD_EVENT_KINDS; play_world_event_turn payload lines for restrain / escort
  [ ] DSL: RESTRAIN / RELEASE / ESCORT in OPCODES and the legend; _apply_op writes _dsl.restraint
  [ ] routes: none new; GET /api/travel-status already returns the 409 fields (add label / hint from runtime_flags)
  [ ] UI: updateTravelStatus reads state.restraint.label for the banner; nothing else
  [ ] prompt lines: the three op legend lines; one SYSTEM_PROMPT rule that a capture is an outcome the engine confirms, not a choice the prose makes

Tests: tests/test_restraint.py
"""
from __future__ import annotations

import json
import re
from typing import Any

from app.player_resources import world_abs_minutes

# ---------------------------------------------------------------------------
# Storage names
# ---------------------------------------------------------------------------

STATE_KEY = "restraint"
STATE_VERSION = 1
LOG_TABLE = "restraint_log"
LOG_KEEP = 200
DETAIL_MAX_CHARS = 4000

_LOG_SQL = """
CREATE TABLE IF NOT EXISTS restraint_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    turn INTEGER NOT NULL DEFAULT 0,
    abs_minute INTEGER NOT NULL DEFAULT 0,
    event TEXT NOT NULL DEFAULT '',
    mode TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    actor_code TEXT NOT NULL DEFAULT '',
    from_location_id INTEGER NOT NULL DEFAULT 0,
    to_location_id INTEGER NOT NULL DEFAULT 0,
    detail TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""
_LOG_INDEX_SQL = "CREATE INDEX IF NOT EXISTS idx_restraint_log_turn ON restraint_log(turn)"

# Log event words (the `event` column).
LOG_EVENTS = (
    "captured", "transferred", "released", "escaped", "escape_failed", "blocked", "payment", "position_set",
    "tick_release",
)

# ---------------------------------------------------------------------------
# Rules tables (data, with the numbers)
# ---------------------------------------------------------------------------

MODES = ("free", "restrained", "custody", "confined")
SCOPES = ("person", "location", "plot", "cell")

ACTIONS = ("talk", "wait", "rest", "train", "investigate", "ability", "inventory", "trade", "escape_attempt", "combat", "travel")

# What each mode leaves open. "travel" is never in any locked mode. "combat" while locked is an escape
# attempt (skill melee) and is listed as "escape_attempt".
ALLOWED_BY_MODE = {
    "free": ACTIONS,
    "restrained": ("talk", "wait", "investigate", "ability", "escape_attempt"),
    "custody": ("talk", "wait", "investigate", "ability", "inventory", "trade", "escape_attempt"),
    "confined": ("talk", "wait", "rest", "train", "investigate", "ability", "inventory", "trade", "escape_attempt"),
}

# world._turn_intent primary intent -> ACTION word (read-only import of the existing classifier).
INTENT_TO_ACTION = {
    "conversation": "talk", "claim_check": "talk", "rest": "wait", "training": "train", "investigation": "investigate",
    "ability": "ability", "inventory": "inventory", "trade": "trade", "combat": "escape_attempt", "travel": "travel",
    "general": "talk",
}
ESCAPE_WORDS = ("escape", "break out", "slip free", "pick the lock", "work the knots", "loosen the rope", "squeeze through", "break the bars", "overpower", "bolt", "make a run")

# The verb word a refusal names for each action.
ACTION_VERBS = {
    "talk": "talk", "wait": "wait", "rest": "rest", "train": "train", "investigate": "look around",
    "ability": "use your powers", "inventory": "use your things", "trade": "trade", "escape_attempt": "escape",
    "combat": "fight", "travel": "go anywhere",
}

# Move kinds may_move accepts and what "target" must carry.
MOVE_KINDS = {
    "map_step": ("x", "y"),
    "story_walk": ("x", "y"),
    "town_walk": ("cx", "cy"),
    "town_leave": (),
    "travel_press": (),
    "location_move": ("location_id|location_code",),
    "venue_enter": ("location_id|location_code",),
    "venue_exit": (),
}
MOVE_REASONS = ("restrained", "custody", "confined", "escort_in_progress", "unknown_target")

# Which kinds a scope still permits while locked (everything else is blocked). Checked only for mode
# "confined"; "restrained" and "custody" block every kind.
SCOPE_RULES = {
    "person": (),
    "location": ("venue_exit_same_parent",),
    "plot": ("town_walk_same_plot",),
    "cell": ("town_walk_same_cell", "venue_enter_same_cell"),
}

MESSAGES = {
    "restrained": "You are bound; you cannot go anywhere until you are freed.",
    "custody": "You are being held; {by} does not let you leave.",
    "confined": "You are held in {label}; the way out is shut.",
    "escort_in_progress": "You are being taken somewhere; you do not choose the way.",
    "unknown_target": "That is not a place you can reach from here.",
    "action_refused": "Bound as you are, you cannot {action} right now.",
}

# Default capture proposals by kind. Minutes are world minutes; dc is the escape DC before modifiers.
#  kind: (mode, scope, label, minutes, escape_skill, dc, cooldown_turns, fail_penalty_minutes)
CAPTURE_DEFAULTS = {
    "bonds": ("restrained", "person", "Bound at the wrists", 120, "athletics", 14, 1, 30),
    "custody": ("custody", "person", "In {faction} custody", 0, "stealth", 16, 2, 60),
    "cell": ("confined", "location", "Held in {place}", 1440, "lockpicking", 18, 3, 240),
}
CAPTURE_MINUTES_BY_SEVERITY = {"light": 0.5, "normal": 1.0, "harsh": 3.0}
ESCAPE_DC_BY_CAPTOR_POWER = ((0, -2), (20, 0), (40, 2), (70, 4))
ESCAPE_DC_MIN = 12
ESCAPE_DC_MAX = 22
ESCAPE_MAX_ATTEMPTS_PER_DAY = 3
ESCAPE_COOLDOWN_TURNS = 2
RELEASE_GRACE_MINUTES = 0
ESCAPE_SUCCESS_OUTCOMES = ("success", "critical_success")

# Capture classifier. Second-person patient phrases outside quotes. (regex, kind, weight)
CAPTURE_PHRASES = (
    (r"\byou(?:r wrists| hands)? (?:are|were|get|got) (?:bound|tied|shackled|chained|manacled|fettered)\b", "bonds", 0.4),
    (r"\b(?:bind|binds|bound|tie|ties|tied|shackle|shackles|shackled|chain|chains|chained|manacle|manacled) (?:your (?:hands|wrists|ankles)|you)\b", "bonds", 0.4),
    (r"\byou (?:are|were) (?:seized|arrested|taken into custody|taken prisoner|captured|apprehended|detained)\b", "custody", 0.4),
    (r"\b(?:seize|seizes|seized|arrest|arrests|arrested|apprehend|apprehends|apprehended|detain|detains|detained|take|takes|took|drag|drags|dragged|haul|hauls|hauled|march|marches|marched|escort|escorts|escorted) you (?:away|off|along|to|toward|towards|into|down|up|out)\b", "custody", 0.4),
    (r"\byou (?:are|were) (?:thrown|locked|shut|tossed|flung|pushed|shoved) (?:into|in|inside) (?:a|the) (?:cell|cage|gaol|jail|dungeon|cellar|hold|brig|pit|stocks|wagon|room)\b", "cell", 0.4),
    (r"\b(?:the )?(?:door|gate|bars|grate|hatch|lock) (?:slams?|clangs?|closes?|shuts?|locks?|bolts?)(?: shut)? behind you\b", "cell", 0.3),
    (r"\byou (?:surrender|give (?:up|yourself up)|let them take you|go quietly|offer no resistance)\b", "custody", 0.3),
)
# Prose that looks like a grab but is flavour: never a signal (weight 0); verdict "flavour" when it is all there is.
FLAVOUR_PHRASES = (
    r"\b(?:grabs?|grips?|catches|takes) (?:your|you by the) (?:arm|wrist|sleeve|shoulder|collar|hand)\b",
    r"\bblocks? your (?:way|path)\b",
    r"\b(?:threatens?|threatening) to\b",
    r"\bas if to\b",
    r"\blike a prisoner\b",
    r"\bas though\b",
)
# Any of these inside the same sentence cancels a capture phrase (hypothetical, denied, or narrowly avoided).
NEGATION_WORDS = ("if ", "unless", "would", "could", "might", "almost", "nearly", "tries to", "try to", "attempts to", "fails to", "before you", "but you", "you dodge", "you twist free", "not ", "never ", "no longer")
# Engine corroboration. (check name -> weight)
CORROBORATION = {
    "lost_opposed_check": 0.35,
    "lost_fight": 0.40,
    "outnumbered_ambush": 0.30,
    "player_surrender": 0.40,
    "engine_event": 1.00,
    "model_op": 0.00,
}
PROSE_SIGNAL_WEIGHT = 0.4
CAPTURE_THRESHOLD = 0.7
LOST_OUTCOMES = ("failure", "critical_failure")
CAPTURE_CHECK_SKILLS = ("pursuit", "stealth", "athletics", "melee", "defense", "tactics", "deception", "intimidation", "persuasion", "disguise", "streetwise", "ambush_sense")
# The deterministic combat emits hit | glancing_hit | miss | resolved | unresolved, none of them a loss, so
# today only the health-ratio rule can fire; these words cover model-authored resolution outcomes.
COMBAT_LOSS_OUTCOMES = ("player_down", "player_defeated", "defeated", "knocked_out", "overpowered", "captured", "subdued")
COMBAT_LOSS_HEALTH_RATIO = 0.25
SURRENDER_INPUT = r"\b(?:i (?:surrender|give up|yield|submit)|i (?:let|allow) them (?:take|bind) me|i go quietly|i put (?:my hands|my weapon) (?:up|down)|i do(?:n't| not) resist)\b"
PLACE_HINTS = (("cell", "cell"), ("gaol", "cell"), ("jail", "cell"), ("dungeon", "cell"), ("cellar", "cell"), ("cage", "cell"), ("brig", "cell"),
               ("stocks", "cell"), ("wagon", "custody"), ("camp", "custody"), ("rope", "bonds"), ("chain", "bonds"), ("shackle", "bonds"), ("manacle", "bonds"))
EVIDENCE_CHECKS = ("capture_prose", "flavour_prose", "model_op") + tuple(CORROBORATION)

# Trust for position plans. "model" may only move the player to the captor's own place or at most
# MODEL_MAX_CELLS cells.
TRUSTED_ACTORS = ("engine", "event", "escort", "debug")
MODEL_MAX_CELLS = 12
TRANSFER_MAX_CELLS = 400
ESCORT_CELL_BUDGET = 12          # world cells planned per plan_escort call (3 x tile_world.STEP_BUDGET)
ESCORT_NO_ENCOUNTERS = True

STATUS_LINES = {
    "restrained": ("critical", "You are bound{by_clause}; you cannot walk away or use your hands freely.", ["travel", "inventory", "train"]),
    "custody": ("serious", "You are held{by_clause}; you may speak and wait, but you go where you are taken.", ["travel", "train"]),
    "confined": ("serious", "You are confined to {label}{by_clause}; the way out is shut.", ["travel"]),
    "escort": ("serious", "You are being taken to {to}; {legs_left} more stretch{plural} of road.", ["travel"]),
    "time_left": ("info", "About {hours} hour{plural} before anyone speaks of letting you go.", []),
    "payment": ("info", "A payment of {owed} would see you released.", []),
}
PROMPT_HEADER = "Player restraint (server truth):"
JOURNAL_KINDS = {"captured": "restrained", "released": "released", "escort": "escort", "blocked": "system"}
CONDITION_TYPES = ("time", "skill", "quest_stage", "quest_status", "payment", "event", "turns", "release_word")
RESTRAINT_OPS = ("RESTRAIN", "RELEASE", "ESCORT")
OP_UNTIL_TYPES = ("skill", "quest", "stage", "pay", "event")

_QUOTE_RE = re.compile(r'"[^"\n]*"|“[^”\n]*”|‘[^’\n]*’(?=[\s,.!?;:])')
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_CODE_TAG_RE = re.compile(r"\[\[([A-Za-z]{1,2}\d{0,4})\]\]")
_CAPTURE_RES = tuple((re.compile(pattern, re.IGNORECASE), kind, weight) for pattern, kind, weight in CAPTURE_PHRASES)
_FLAVOUR_RES = tuple(re.compile(pattern, re.IGNORECASE) for pattern in FLAVOUR_PHRASES)
_SURRENDER_RE = re.compile(SURRENDER_INPUT, re.IGNORECASE)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _cheb(a: tuple[int, int] | list[int], b: tuple[int, int] | list[int]) -> int:
    return max(abs(int(a[0]) - int(b[0])), abs(int(a[1]) - int(b[1])))


def _world_time_or_now(conn, world_time: dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(world_time, dict):
        return world_time
    from app.world import get_world_time

    return get_world_time(conn)


def _entity_ref(raw: Any) -> dict[str, Any] | None:
    """A normalised EntityRef (contracts 1.14) or None. `power_rank` rides along when present."""
    if not isinstance(raw, dict):
        return None
    name = _text(raw.get("name") or raw.get("label"), 80)
    code = _text(raw.get("code"), 12).upper()
    if not name and not code:
        return None
    ref: dict[str, Any] = {
        "code": code,
        "name": name or code,
        "kind": str(raw.get("kind") or "person"),
        "role": _text(raw.get("role"), 60),
    }
    if raw.get("power_rank") is not None:
        ref["power_rank"] = _int(raw.get("power_rank"), 10)
    return ref


def _by_name(state: dict[str, Any]) -> str:
    by = state.get("by")
    if isinstance(by, dict) and by.get("name"):
        return str(by["name"])
    return ""


def _place_words(state: dict[str, Any]) -> str:
    """The label as words after "in": "Held in the gaol cell" -> "the gaol cell"."""
    label = str(state.get("label") or "").strip()
    lowered = label.lower()
    for lead in ("held in ", "confined to ", "locked in ", "in "):
        if lowered.startswith(lead):
            return label[len(lead):] or "this place"
    return label or "this place"


def _journal_note(kind: str, content: str) -> dict[str, Any]:
    return {"kind": str(kind)[:40], "content": str(content or "").strip()[:900]}


def _evidence(check: str, ok: bool, evidence: str, severity: str, weight: float) -> dict[str, Any]:
    return {"check": str(check), "ok": bool(ok), "evidence": _text(evidence, 240), "severity": str(severity), "weight": float(weight)}


# ---------------------------------------------------------------------------
# Schema and the settings row
# ---------------------------------------------------------------------------


def ensure_schema(conn) -> None:
    """Create restraint_log and its index. Idempotent; no commit (the caller's connection commits)."""
    conn.execute(_LOG_SQL)
    conn.execute(_LOG_INDEX_SQL)


def normalize_condition(raw: Any) -> dict[str, Any]:
    """One release condition with its fields typed. ValueError on an unknown or malformed type."""
    if not isinstance(raw, dict):
        raise ValueError("a condition must be a dict")
    kind = str(raw.get("type") or "").strip()
    if kind == "time":
        return {"type": "time", "abs_minute": _int(raw.get("abs_minute"), 0)}
    if kind == "skill":
        name = _text(raw.get("name"), 60)
        if not name:
            raise ValueError("skill condition needs a name")
        return {"type": "skill", "name": name, "level": _int(raw.get("level"), 1)}
    if kind == "quest_stage":
        stage = _text(raw.get("stage_id"), 80)
        if not stage:
            raise ValueError("quest_stage condition needs a stage_id")
        return {"type": "quest_stage", "stage_id": stage}
    if kind == "quest_status":
        code = _text(raw.get("code"), 40)
        if not code:
            raise ValueError("quest_status condition needs a code")
        return {"type": "quest_status", "code": code, "status": _text(raw.get("status"), 40) or "completed"}
    if kind == "payment":
        return {"type": "payment", "units": max(0, _int(raw.get("units"), 0)), "currency_set": _text(raw.get("currency_set"), 40)}
    if kind == "event":
        ev_kind = _text(raw.get("kind"), 40)
        if not ev_kind:
            raise ValueError("event condition needs a kind")
        return {"type": "event", "kind": ev_kind, "trigger": _text(raw.get("trigger"), 120)}
    if kind == "turns":
        return {"type": "turns", "turn": _int(raw.get("turn"), 0)}
    if kind == "release_word":
        return {"type": "release_word", "by": _text(raw.get("by"), 12).upper()}
    raise ValueError(f"unknown condition type: {kind!r}")


def _normalize_place(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    cell = raw.get("cell")
    if isinstance(cell, (list, tuple)) and len(cell) == 2:
        cell = [_int(cell[0]), _int(cell[1])]
    else:
        cell = None
    place = {
        "location_id": max(0, _int(raw.get("location_id"), 0)),
        "location_code": _text(raw.get("location_code"), 12).upper(),
        "plot": _text(raw.get("plot"), 40),
        "city_id": _text(raw.get("city_id"), 12),
        "cell": cell,
    }
    if not (place["location_id"] or place["location_code"] or place["plot"] or place["city_id"] or place["cell"]):
        return None
    return place


def _normalize_escape(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    skill = _text(raw.get("skill"), 40) or "athletics"
    return {
        "skill": skill,
        "dc": max(ESCAPE_DC_MIN, min(ESCAPE_DC_MAX, _int(raw.get("dc"), 14))),
        "attempts": max(0, _int(raw.get("attempts"), 0)),
        "last_turn": max(0, _int(raw.get("last_turn"), 0)),
        "cooldown_turns": max(0, _int(raw.get("cooldown_turns"), ESCAPE_COOLDOWN_TURNS)),
        "fail_penalty_minutes": max(0, _int(raw.get("fail_penalty_minutes"), 0)),
    }


def _normalize_escort(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    to = raw.get("to") if isinstance(raw.get("to"), dict) else {}
    return {
        "to": {
            "x": _int(to.get("x"), 0),
            "y": _int(to.get("y"), 0),
            "plot": _text(to.get("plot"), 40),
            "city_id": _text(to.get("city_id"), 12),
            "location_code": _text(to.get("location_code"), 12).upper(),
        },
        "legs_done": max(0, _int(raw.get("legs_done"), 0)),
        "legs_total": max(0, _int(raw.get("legs_total"), 0)),
        "plan_id": _text(raw.get("plan_id"), 80),
    }


def free_state() -> dict[str, Any]:
    """A fresh FREE_STATE copy: mode free, every list empty, every action allowed."""
    return {
        "version": STATE_VERSION,
        "mode": "free",
        "label": "",
        "reason": "",
        "by": None,
        "faction": "",
        "place": None,
        "scope": "person",
        "since": {"turn": 0, "abs_minute": 0},
        "conditions": [],
        "allowed": list(ACTIONS),
        "escape": None,
        "escort": None,
        "set_turn": 0,
        "paid_units": 0,
        "notes": [],
    }


FREE_STATE = free_state()


def normalize_state(raw: Any) -> dict[str, Any]:
    """The RestraintState shape with every key present. Unknown mode -> free; unknown keys dropped;
    escape dc clamped 12..22; conditions of an unknown type dropped."""
    if not isinstance(raw, dict):
        return free_state()
    mode = str(raw.get("mode") or "").strip().lower()
    if mode not in MODES or mode == "free":
        return free_state()
    scope = str(raw.get("scope") or "").strip().lower()
    if scope not in SCOPES:
        scope = "person"
    conditions: list[dict[str, Any]] = []
    for item in raw.get("conditions") or []:
        try:
            conditions.append(normalize_condition(item))
        except ValueError:
            continue
    allowed_raw = raw.get("allowed")
    if isinstance(allowed_raw, (list, tuple)):
        allowed = [str(a) for a in allowed_raw if str(a) in ACTIONS]
    else:
        allowed = list(ALLOWED_BY_MODE[mode])
    if "travel" in allowed:
        allowed.remove("travel")
    since = raw.get("since") if isinstance(raw.get("since"), dict) else {}
    notes = [str(n)[:120] for n in (raw.get("notes") or []) if str(n).strip()][-6:]
    return {
        "version": STATE_VERSION,
        "mode": mode,
        "label": _text(raw.get("label"), 80),
        "reason": _text(raw.get("reason"), 60),
        "by": _entity_ref(raw.get("by")),
        "faction": _text(raw.get("faction"), 60),
        "place": _normalize_place(raw.get("place")),
        "scope": scope,
        "since": {"turn": max(0, _int(since.get("turn"), 0)), "abs_minute": max(0, _int(since.get("abs_minute"), 0))},
        "conditions": conditions,
        "allowed": allowed,
        "escape": _normalize_escape(raw.get("escape")),
        "escort": _normalize_escort(raw.get("escort")) if mode == "custody" else None,
        "set_turn": max(0, _int(raw.get("set_turn"), 0)),
        "paid_units": max(0, _int(raw.get("paid_units"), 0)),
        "notes": notes,
    }


def load_state(conn) -> dict[str, Any]:
    """The `restraint` settings row decoded and normalised; a free state when absent or unreadable."""
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (STATE_KEY,)).fetchone()
    except Exception:
        return free_state()
    if not row:
        return free_state()
    try:
        raw = json.loads(row[0])
    except (TypeError, ValueError):
        return free_state()
    return normalize_state(raw)


def save_state(conn, state: dict[str, Any]) -> None:
    """Write the row; a free state deletes it. The caller's connection commits."""
    clean = normalize_state(state)
    if clean["mode"] == "free":
        conn.execute("DELETE FROM settings WHERE key = ?", (STATE_KEY,))
        return
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (STATE_KEY, json.dumps(clean, ensure_ascii=True, separators=(",", ":"))),
    )


def state_view(conn) -> dict[str, Any]:
    state = load_state(conn)
    return {"restraint": None if state["mode"] == "free" else state}


def is_locked(conn) -> bool:
    return load_state(conn)["mode"] != "free"


def runtime_flags(conn=None) -> dict[str, Any]:
    """The flags main._location_special_runtime would merge. Opens its own connection when conn is None."""
    if conn is None:
        from app.db import connect

        owned = connect()
        try:
            return runtime_flags(owned)
        finally:
            owned.close()
    state = load_state(conn)
    locked = state["mode"] != "free"
    if not locked:
        return {"movement_locked": False, "label": "", "hint": "", "reason": "", "restraint": None}
    reason = state["mode"]
    if state["mode"] == "custody" and state.get("escort"):
        reason = "escort_in_progress"
    return {
        "movement_locked": True,
        "label": state["label"],
        "hint": _message_for(reason, state),
        "reason": reason,
        "restraint": state,
    }


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


def _detail_json(detail: Any) -> str:
    try:
        text = json.dumps(detail if detail is not None else {}, ensure_ascii=True, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        text = "{}"
    if len(text) > DETAIL_MAX_CHARS:
        text = json.dumps({"truncated": True, "chars": len(text)}, separators=(",", ":"))
    return text


def _log(conn, *, turn: int, abs_minute: int, event: str, mode: str, reason: str = "", actor_code: str = "",
         from_location_id: int = 0, to_location_id: int = 0, detail: Any = None) -> int:
    ensure_schema(conn)
    cur = conn.execute(
        "INSERT INTO restraint_log (turn, abs_minute, event, mode, reason, actor_code, from_location_id, to_location_id, detail) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            max(0, _int(turn, 0)), max(0, _int(abs_minute, 0)), str(event)[:40], str(mode)[:20], str(reason or "")[:80],
            str(actor_code or "")[:12], max(0, _int(from_location_id, 0)), max(0, _int(to_location_id, 0)), _detail_json(detail),
        ),
    )
    log_id = int(cur.lastrowid or 0)
    log_prune(conn, keep=LOG_KEEP)
    return log_id


def log_rows(conn, *, limit: int = 40) -> list[dict[str, Any]]:
    ensure_schema(conn)
    rows = conn.execute(
        "SELECT id, turn, abs_minute, event, mode, reason, actor_code, from_location_id, to_location_id, detail, created_at "
        "FROM restraint_log ORDER BY id DESC LIMIT ?",
        (max(1, int(limit)),),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = {key: row[key] for key in row.keys()}
        try:
            item["detail"] = json.loads(item.get("detail") or "{}")
        except (TypeError, ValueError):
            item["detail"] = {}
        out.append(item)
    return out


def log_prune(conn, *, keep: int = LOG_KEEP) -> int:
    """Delete everything but the newest `keep` rows. Returns the number removed."""
    ensure_schema(conn)
    cur = conn.execute(
        "DELETE FROM restraint_log WHERE id NOT IN (SELECT id FROM restraint_log ORDER BY id DESC LIMIT ?)",
        (max(0, int(keep)),),
    )
    return int(cur.rowcount or 0)


# ---------------------------------------------------------------------------
# Movement verdicts
# ---------------------------------------------------------------------------


def _message_for(reason: str, state: dict[str, Any], action: str = "") -> str:
    template = MESSAGES.get(reason, MESSAGES["unknown_target"])
    by = _by_name(state) or "your captor"
    return template.format(by=by, label=_place_words(state), action=action)[:160]


def _verdict(allowed: bool, reason: str, kind: str, state: dict[str, Any]) -> dict[str, Any]:
    return {
        "allowed": bool(allowed),
        "reason": "" if allowed else reason,
        "message": "" if allowed else _message_for(reason, state),
        "label": "" if allowed else str(state.get("label") or ""),
        "kind": kind,
        "movement_locked": not allowed,
    }


def _has_int(target: dict[str, Any], key: str) -> bool:
    value = target.get(key)
    if value is None or isinstance(value, bool):
        return False
    try:
        int(value)
    except (TypeError, ValueError):
        return False
    return True


def _target_ok(kind: str, target: Any) -> bool:
    needs = MOVE_KINDS[kind]
    if not needs:
        return True
    if kind == "story_walk" and target is None:
        return True
    if not isinstance(target, dict):
        return False
    for need in needs:
        if need == "location_id|location_code":
            if not (_has_int(target, "location_id") and int(target["location_id"]) > 0) and not str(target.get("location_code") or "").strip():
                return False
        elif not _has_int(target, need):
            return False
    return True


def _confined_allows(state: dict[str, Any], kind: str, target: dict[str, Any] | None) -> bool:
    place = state.get("place") or {}
    rules = SCOPE_RULES.get(str(state.get("scope") or "person"), ())
    target = target if isinstance(target, dict) else {}
    if "venue_exit_same_parent" in rules:
        if kind == "venue_exit":
            return True
        if kind in ("location_move", "venue_enter"):
            want_id = _int(target.get("location_id"), 0)
            want_code = str(target.get("location_code") or "").strip().upper()
            if want_id and want_id == _int(place.get("location_id"), 0):
                return True
            if want_code and want_code == str(place.get("location_code") or ""):
                return True
    if "town_walk_same_plot" in rules and kind == "town_walk":
        plot = str(target.get("plot") or "").strip()
        if plot and plot == str(place.get("plot") or ""):
            return True
    cell = place.get("cell")
    if cell and "town_walk_same_cell" in rules and kind == "town_walk":
        if (_int(target.get("cx")), _int(target.get("cy"))) == (int(cell[0]), int(cell[1])):
            return True
    if cell and "venue_enter_same_cell" in rules and kind == "venue_enter":
        if _has_int(target, "cx") and _has_int(target, "cy") and (int(target["cx"]), int(target["cy"])) == (int(cell[0]), int(cell[1])):
            return True
    return False


def may_move_state(state: dict[str, Any], kind: str, target: dict[str, Any] | None) -> dict[str, Any]:
    """The MoveVerdict (contracts 1.9) for one move kind. Pure; ValueError on an unknown kind."""
    if kind not in MOVE_KINDS:
        raise ValueError(f"unknown move kind: {kind!r}")
    state = normalize_state(state)
    if not _target_ok(kind, target):
        return _verdict(False, "unknown_target", kind, state)
    mode = state["mode"]
    if mode == "free":
        return _verdict(True, "", kind, state)
    if mode == "restrained":
        return _verdict(False, "restrained", kind, state)
    if mode == "custody":
        return _verdict(False, "escort_in_progress" if state.get("escort") else "custody", kind, state)
    if _confined_allows(state, kind, target):
        return _verdict(True, "", kind, state)
    return _verdict(False, "confined", kind, state)


def may_move(conn, kind: str, target: dict[str, Any] | None) -> dict[str, Any]:
    return may_move_state(load_state(conn), kind, target)


def allowed_actions(state: dict[str, Any], player_input: str) -> dict[str, Any]:
    """ActionVerdict for a typed line: {"allowed", "action", "reason", "message", "escape"}. Pure."""
    from app.world import _turn_intent

    state = normalize_state(state)
    text = str(player_input or "")
    primary, _secondary = _turn_intent(text)
    action = INTENT_TO_ACTION.get(primary, "talk")
    lowered = text.lower()
    escape = any(word in lowered for word in ESCAPE_WORDS)
    if escape:
        action = "escape_attempt"
    if state["mode"] == "free":
        return {"allowed": True, "action": action, "reason": "", "message": "", "escape": escape}
    allowed = action in state["allowed"]
    return {
        "allowed": allowed,
        "action": action,
        "reason": "" if allowed else state["mode"],
        "message": "" if allowed else MESSAGES["action_refused"].format(action=ACTION_VERBS.get(action, action))[:160],
        "escape": escape,
    }


def wait_allowed(state: dict[str, Any], minutes: int) -> dict[str, Any]:
    """Waiting is in-place play and is always allowed; kept as the one place a future rule would live."""
    return {"allowed": True, "minutes": max(0, _int(minutes, 0))}


# ---------------------------------------------------------------------------
# Capture gate (pure)
# ---------------------------------------------------------------------------


def strip_quotes(text: str) -> str:
    """Remove quoted speech so a threat someone says is never a thing that happened."""
    return _QUOTE_RE.sub(" ", str(text or ""))


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_SPLIT_RE.split(str(text or "")) if part and part.strip()]


def _negated(sentence: str) -> bool:
    lowered = " " + sentence.lower() + " "
    return any(word in lowered for word in NEGATION_WORDS)


def _check_skill_code(check: dict[str, Any]) -> str:
    skill = check.get("skill")
    if isinstance(skill, dict):
        return str(skill.get("code") or skill.get("name") or "").strip().lower()
    return str(skill or check.get("skill_code") or "").strip().lower()


def _captor_from_people(sentence: str, people: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    match = _CODE_TAG_RE.search(sentence)
    if not match:
        return None
    code = match.group(1).upper()
    for person in people or []:
        if isinstance(person, dict) and str(person.get("code") or "").upper() == code:
            return _entity_ref(person)
    return None


def classify_capture(*, narration: str, player_input: str = "", ops: list[dict[str, Any]] | None = None,
                     checks: list[dict[str, Any]] | None = None, combat: dict[str, Any] | None = None,
                     encounter: dict[str, Any] | None = None, event: dict[str, Any] | None = None,
                     people: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Decide whether the prose describes a capture that engine facts back. Pure; never reads the DB."""
    evidence: list[dict[str, Any]] = []
    kind = ""
    sentence_hit = ""
    captor: dict[str, Any] | None = None

    body = strip_quotes(narration)
    sentences = _sentences(body)
    for sentence in sentences:
        if _negated(sentence):
            continue
        for regex, phrase_kind, weight in _CAPTURE_RES:
            if regex.search(sentence):
                evidence.append(_evidence("capture_prose", False, sentence, "warn", weight))
                kind = phrase_kind
                sentence_hit = sentence
                break
        if sentence_hit:
            break
    prose_signal = bool(sentence_hit)
    if not prose_signal:
        for sentence in sentences:
            if any(regex.search(sentence) for regex in _FLAVOUR_RES):
                evidence.append(_evidence("flavour_prose", True, sentence, "info", 0.0))
                break

    op_signal = False
    for entry in ops or []:
        if not isinstance(entry, dict) or str(entry.get("op") or "").upper() != "RESTRAIN":
            continue
        parsed = parse_restraint_op(entry)
        line = str(entry.get("raw") or entry.get("line") or "RESTRAIN")
        if prose_signal or op_signal:
            evidence.append(_evidence("model_op", False, line, "info", CORROBORATION["model_op"]))
        else:
            evidence.append(_evidence("model_op", False, line, "warn", PROSE_SIGNAL_WEIGHT))
            op_signal = True
        if not kind and parsed.get("ok") and parsed["proposal"]:
            kind = str(parsed["proposal"].get("kind") or "")
        break

    for check in checks or []:
        if not isinstance(check, dict):
            continue
        opposition = check.get("opposition")
        if (str(check.get("outcome") or "") in LOST_OUTCOMES and isinstance(opposition, dict) and opposition
                and _check_skill_code(check) in CAPTURE_CHECK_SKILLS):
            evidence.append(_evidence(
                "lost_opposed_check", False,
                f"lost {_check_skill_code(check)} against {opposition.get('name') or opposition.get('code') or 'opposition'}",
                "warn", CORROBORATION["lost_opposed_check"],
            ))
            if captor is None:
                captor = _entity_ref(opposition)
            break

    if isinstance(combat, dict):
        resolution = combat.get("resolution") if isinstance(combat.get("resolution"), dict) else {}
        outcome = str(resolution.get("outcome") or "")
        ratio: float | None = None
        after = combat.get("player_health_after")
        max_health = combat.get("player_max_health")
        if after is not None and max_health is not None and _int(max_health, 0) > 0:
            ratio = _int(after, 0) / float(_int(max_health, 1))
        if outcome in COMBAT_LOSS_OUTCOMES or (ratio is not None and ratio <= COMBAT_LOSS_HEALTH_RATIO):
            why = f"combat outcome {outcome}" if outcome in COMBAT_LOSS_OUTCOMES else f"health ratio {ratio:.2f}"
            evidence.append(_evidence("lost_fight", False, why, "warn", CORROBORATION["lost_fight"]))
            if captor is None:
                captor = _entity_ref(combat.get("target"))

    if isinstance(encounter, dict):
        count = _int(encounter.get("count") if encounter.get("count") is not None else encounter.get("size"), 1)
        if bool(encounter.get("hostile_default")) and str(encounter.get("surprise") or "") == "surprised" and count >= 2:
            evidence.append(_evidence("outnumbered_ambush", False, f"ambushed by {count}", "warn", CORROBORATION["outnumbered_ambush"]))
            if captor is None:
                captor = _entity_ref({"code": encounter.get("npc_code"), "name": encounter.get("npc_name")})

    if player_input and _SURRENDER_RE.search(str(player_input)):
        evidence.append(_evidence("player_surrender", False, str(player_input), "warn", CORROBORATION["player_surrender"]))

    restrain_payload: dict[str, Any] | None = None
    if isinstance(event, dict):
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if isinstance(payload.get("restrain"), dict):
            restrain_payload = payload["restrain"]
            evidence.append(_evidence("engine_event", False, str(event.get("summary") or event.get("trigger") or "engine event"), "block", CORROBORATION["engine_event"]))
            event_captor = _entity_ref(restrain_payload.get("by"))
            if event_captor is not None:
                captor = event_captor

    confidence = round(min(1.0, float(sum(row["weight"] for row in evidence if not row["ok"]))), 2)
    if confidence >= CAPTURE_THRESHOLD:
        verdict = "capture"
    elif prose_signal or op_signal or any(row["check"] == "flavour_prose" for row in evidence):
        verdict = "flavour"
    else:
        verdict = "none"

    # Kind: the prose phrase's kind, else the op's, else the event payload's, else a place word, else custody.
    place_hint = ""
    hint_kind = ""
    hint_text = (sentence_hit or body).lower()
    for word, word_kind in PLACE_HINTS:
        if re.search(rf"\b{re.escape(word)}s?\b", hint_text):
            place_hint = word
            hint_kind = word_kind
            break
    if kind not in CAPTURE_DEFAULTS and restrain_payload is not None:
        kind = str(restrain_payload.get("kind") or "")
    if kind not in CAPTURE_DEFAULTS:
        kind = hint_kind
    if kind not in CAPTURE_DEFAULTS:
        kind = "custody"
    if verdict == "none":
        kind = ""

    if captor is None and sentence_hit:
        captor = _captor_from_people(sentence_hit, people)

    return {
        "verdict": verdict,
        "kind": kind,
        "confidence": confidence,
        "evidence": evidence,
        "captor": captor,
        "place_hint": place_hint,
        "sentence": sentence_hit[:240],
    }


def _capture_reason(verdict: dict[str, Any]) -> str:
    checks = {row["check"] for row in verdict.get("evidence") or [] if not row.get("ok")}
    if "engine_event" in checks:
        return "event:restraint"
    for check, word in (("lost_fight", "lost_fight"), ("lost_opposed_check", "lost_check"), ("outnumbered_ambush", "ambush"), ("player_surrender", "surrender")):
        if check in checks:
            return f"capture:{word}"
    if "model_op" in checks:
        return "op:RESTRAIN"
    return "capture:prose"


def propose_capture(verdict: dict[str, Any], *, world_time: dict[str, Any], turn: int, location: dict[str, Any] | None,
                    severity: str = "normal", fine_units: int | None = None, currency_set: str = "",
                    extra_conditions: list[dict[str, Any]] | None = None, allow_escape: bool = True,
                    faction: str = "") -> dict[str, Any]:
    """A RestraintState from a capture verdict and the defaults table. Pure; ValueError unless verdict is a capture."""
    if not isinstance(verdict, dict) or verdict.get("verdict") != "capture":
        raise ValueError("propose_capture needs a verdict of kind capture")
    kind = str(verdict.get("kind") or "custody")
    if kind not in CAPTURE_DEFAULTS:
        kind = "custody"
    mode, scope, label_template, base_minutes, escape_skill, dc, cooldown, penalty = CAPTURE_DEFAULTS[kind]
    mult = CAPTURE_MINUTES_BY_SEVERITY.get(str(severity or "normal"), 1.0)
    minutes = int(round(base_minutes * mult))
    now = world_abs_minutes(world_time)

    conditions: list[dict[str, Any]] = []
    if minutes > 0:
        conditions.append({"type": "time", "abs_minute": now + minutes + RELEASE_GRACE_MINUTES})
    if fine_units is not None:
        conditions.append({"type": "payment", "units": max(0, _int(fine_units, 0)), "currency_set": _text(currency_set, 40)})
    for extra in extra_conditions or []:
        conditions.append(normalize_condition(extra))

    captor = _entity_ref(verdict.get("captor"))
    # The shift needs a captor whose power_rank is known; an unnamed or unranked captor leaves the table dc.
    shift = 0
    if captor and captor.get("power_rank") is not None:
        power = _int(captor.get("power_rank"), 10)
        for threshold, delta in ESCAPE_DC_BY_CAPTOR_POWER:
            if power >= threshold:
                shift = delta
    escape = None
    if allow_escape:
        escape = {
            "skill": escape_skill,
            "dc": max(ESCAPE_DC_MIN, min(ESCAPE_DC_MAX, dc + shift)),
            "attempts": 0,
            "last_turn": 0,
            "cooldown_turns": cooldown,
            "fail_penalty_minutes": penalty,
        }

    place = None
    place_name = ""
    if kind == "cell":
        loc = location if isinstance(location, dict) else {}
        place_name = _text(loc.get("name"), 60)
        place = {
            "location_id": _int(loc.get("id") or loc.get("location_id"), 0),
            "location_code": _text(loc.get("code") or loc.get("location_code"), 12).upper(),
            "plot": _text(loc.get("plot"), 40),
            "city_id": _text(loc.get("city_id"), 12),
            "cell": loc.get("cell") if isinstance(loc.get("cell"), (list, tuple)) and len(loc.get("cell")) == 2 else None,
        }
    faction_word = _text(faction, 60)
    label = label_template.format(faction=faction_word or "their", place=place_name or (verdict.get("place_hint") and f"the {verdict['place_hint']}") or "a cell")
    if captor:
        captor = dict(captor)
        captor.pop("power_rank", None)
    return normalize_state({
        "version": STATE_VERSION,
        "mode": mode,
        "label": label,
        "reason": _capture_reason(verdict),
        "by": captor,
        "faction": faction_word,
        "place": place,
        "scope": scope,
        "since": {"turn": int(turn), "abs_minute": now},
        "conditions": conditions,
        "allowed": list(ALLOWED_BY_MODE[mode]),
        "escape": escape,
        "escort": None,
        "set_turn": int(turn),
        "paid_units": 0,
        "notes": [],
    })


# ---------------------------------------------------------------------------
# Writers (own row and table only)
# ---------------------------------------------------------------------------


def _release_clause(state: dict[str, Any], now: int) -> str:
    parts: list[str] = []
    for cond in state.get("conditions") or []:
        kind = cond["type"]
        if kind == "time":
            left = max(0, int(cond["abs_minute"]) - now)
            hours = max(1, int(round(left / 60.0))) if left else 0
            parts.append(f"time will tell, about {hours} hour{'s' if hours != 1 else ''}" if left else "the time is already up")
        elif kind == "payment":
            parts.append("a payment would free you")
        elif kind == "skill":
            parts.append(f"skill in {cond['name']} might free you")
        elif kind in ("quest_stage", "quest_status"):
            parts.append("the story may turn")
        elif kind == "event":
            parts.append("something may happen")
        elif kind == "turns":
            parts.append("a few turns may change things")
        elif kind == "release_word":
            parts.append("only your captor's word frees you")
    if not parts:
        return "No release is in sight."
    return "Release: " + "; ".join(parts[:3]) + "."


def _capture_journal(state: dict[str, Any], now: int) -> dict[str, Any]:
    by = _by_name(state)
    by_clause = f"Held by {by}." if by else "Held by no one you can name."
    return _journal_note(JOURNAL_KINDS["captured"], f"{state['label']}. {by_clause} {_release_clause(state, now)}")


def capture(conn, proposal: dict[str, Any], *, turn: int, world_time: dict[str, Any] | None = None) -> dict[str, Any]:
    """Write a capture proposal as the live state. Logs captured (or transferred when already held)."""
    ensure_schema(conn)
    state = normalize_state(proposal)
    if state["mode"] == "free":
        raise ValueError("a capture proposal cannot have mode free")
    now = world_abs_minutes(_world_time_or_now(conn, world_time))
    previous = load_state(conn)
    replaced = previous["mode"] != "free"
    if not state["since"]["abs_minute"]:
        state["since"] = {"turn": int(turn), "abs_minute": now}
    state["set_turn"] = int(turn)
    save_state(conn, state)
    log_id = _log(
        conn, turn=turn, abs_minute=now, event="transferred" if replaced else "captured", mode=state["mode"],
        reason=state["reason"], actor_code=(state.get("by") or {}).get("code", "") if state.get("by") else "",
        from_location_id=(previous.get("place") or {}).get("location_id", 0) if previous.get("place") else 0,
        to_location_id=(state.get("place") or {}).get("location_id", 0) if state.get("place") else 0,
        detail={"state": state, "replaced": previous if replaced else None},
    )
    return {"ok": True, "state": state, "journal": [_capture_journal(state, now)], "log_id": log_id, "replaced_previous": replaced}


def transfer(conn, place: dict[str, Any], *, turn: int, world_time: dict[str, Any] | None = None,
             by: dict[str, Any] | None = None, reason: str = "transfer") -> dict[str, Any]:
    """Move a held player's confinement to another place (mode confined). No-op report when free."""
    ensure_schema(conn)
    state = load_state(conn)
    if state["mode"] == "free":
        return {"ok": False, "state": state, "journal": [], "log_id": 0, "replaced_previous": False}
    new_place = _normalize_place(place)
    if new_place is None:
        raise ValueError("transfer needs a place with a location, plot, city or cell")
    now = world_abs_minutes(_world_time_or_now(conn, world_time))
    from_id = (state.get("place") or {}).get("location_id", 0) if state.get("place") else 0
    state["mode"] = "confined"
    state["place"] = new_place
    state["scope"] = "location" if new_place["location_id"] or new_place["location_code"] else ("plot" if new_place["plot"] else "cell")
    state["escort"] = None
    state["reason"] = _text(reason, 60) or "transfer"
    if by is not None:
        state["by"] = _entity_ref(by)
    state["allowed"] = list(ALLOWED_BY_MODE["confined"])
    if not state["label"].lower().startswith("held"):
        state["label"] = f"Held in {new_place['location_code'] or new_place['plot'] or 'a cell'}"[:80]
    state["set_turn"] = int(turn)
    save_state(conn, state)
    state = load_state(conn)
    log_id = _log(
        conn, turn=turn, abs_minute=now, event="transferred", mode=state["mode"], reason=f"transfer:{state['reason']}",
        actor_code=(state.get("by") or {}).get("code", "") if state.get("by") else "",
        from_location_id=from_id, to_location_id=new_place["location_id"], detail={"place": new_place},
    )
    return {"ok": True, "state": state, "journal": [_capture_journal(state, now)], "log_id": log_id, "replaced_previous": True}


def release(conn, *, reason: str, turn: int, world_time: dict[str, Any] | None = None, by_code: str = "") -> dict[str, Any]:
    """Free the player. A no-op report (ok False, was "free") when already free."""
    ensure_schema(conn)
    state = load_state(conn)
    if state["mode"] == "free":
        return {"ok": False, "was": "free", "reason": str(reason or ""), "journal": [], "log_id": 0}
    now = world_abs_minutes(_world_time_or_now(conn, world_time))
    was = state["mode"]
    if by_code:
        state["notes"] = (state.get("notes") or [])[-5:] + [f"released_by:{str(by_code).upper()}"]
    save_state(conn, free_state())
    log_id = _log(
        conn, turn=turn, abs_minute=now, event="released", mode="free", reason=f"release:{reason}",
        actor_code=str(by_code or "").upper()[:12],
        from_location_id=(state.get("place") or {}).get("location_id", 0) if state.get("place") else 0,
        detail={"was": state, "reason": reason},
    )
    word = {"escape": "You got free.", "time": "Time passed and you were let go.", "payment": "The price was paid and you were let go."}.get(str(reason), "You were released.")
    note = _journal_note(JOURNAL_KINDS["released"], f"{word} ({state['label']}, {reason}.)")
    return {"ok": True, "was": was, "reason": str(reason), "journal": [note], "log_id": log_id}


def _unchanged_tick(state: dict[str, Any]) -> dict[str, Any]:
    return {"changed": False, "released": False, "state": state, "met": [], "next_check_abs_minute": None, "journal": [], "log_event": ""}


def record_payment(conn, units: int, *, turn: int, world_time: dict[str, Any] | None = None) -> dict[str, Any]:
    """Add `units` (smallest currency unit) toward a payment condition, then tick."""
    ensure_schema(conn)
    state = load_state(conn)
    if state["mode"] == "free":
        return _unchanged_tick(state)
    wt = _world_time_or_now(conn, world_time)
    now = world_abs_minutes(wt)
    state["paid_units"] = max(0, state["paid_units"] + max(0, _int(units, 0)))
    save_state(conn, state)
    _log(conn, turn=turn, abs_minute=now, event="payment", mode=state["mode"], reason="payment",
         detail={"units": max(0, _int(units, 0)), "paid_units": state["paid_units"]})
    report = tick(conn, world_time=wt, turn=turn)
    report["changed"] = True
    return report


def _attempts_today(conn, now: int) -> int:
    day_start = (now // 1440) * 1440
    row = conn.execute(
        "SELECT COUNT(*) FROM restraint_log WHERE event IN ('escaped', 'escape_failed') AND abs_minute >= ? AND abs_minute < ?",
        (day_start, day_start + 1440),
    ).fetchone()
    return int(row[0] or 0) if row else 0


def record_escape_attempt(conn, check: dict[str, Any], *, turn: int, world_time: dict[str, Any] | None = None) -> dict[str, Any]:
    """Apply a resolved escape check. Success releases; failure adds the penalty minutes and bumps attempts.
    Cooldown and the per-day cap refuse the attempt (attempted False) without writing."""
    ensure_schema(conn)
    state = load_state(conn)
    outcome = str((check or {}).get("outcome") or "") if isinstance(check, dict) else ""
    base = {"attempted": False, "escaped": False, "reason": "", "dc": 0, "outcome": outcome, "penalty_minutes": 0, "journal": [], "state": state}
    if state["mode"] == "free":
        return {**base, "reason": "free"}
    escape = state.get("escape")
    if not escape:
        return {**base, "reason": "no_escape"}
    base["dc"] = int(escape["dc"])
    if escape["attempts"] > 0 and int(turn) - int(escape["last_turn"]) < int(escape["cooldown_turns"]):
        return {**base, "reason": "cooldown"}
    wt = _world_time_or_now(conn, world_time)
    now = world_abs_minutes(wt)
    if _attempts_today(conn, now) >= ESCAPE_MAX_ATTEMPTS_PER_DAY:
        return {**base, "reason": "daily_cap"}
    if outcome in ("", "narrative"):
        return {**base, "reason": "no_dice"}
    if outcome in ESCAPE_SUCCESS_OUTCOMES:
        _log(conn, turn=turn, abs_minute=now, event="escaped", mode=state["mode"], reason=f"escape:{outcome}",
             detail={"check": {"outcome": outcome, "margin": (check or {}).get("margin")}})
        rel = release(conn, reason="escape", turn=turn, world_time=wt)
        return {**base, "attempted": True, "escaped": True, "reason": "escaped", "journal": rel["journal"], "state": load_state(conn)}
    penalty = int(escape["fail_penalty_minutes"])
    applied = 0
    for cond in state["conditions"]:
        if cond["type"] == "time":
            cond["abs_minute"] = int(cond["abs_minute"]) + penalty
            applied = penalty
            break
    escape["attempts"] = int(escape["attempts"]) + 1
    escape["last_turn"] = int(turn)
    state["escape"] = escape
    state["notes"] = (state.get("notes") or [])[-5:] + [f"escape_failed:{turn}"]
    save_state(conn, state)
    _log(conn, turn=turn, abs_minute=now, event="escape_failed", mode=state["mode"], reason=f"escape:{outcome}",
         detail={"attempts": escape["attempts"], "penalty_minutes": applied})
    return {**base, "attempted": True, "escaped": False, "reason": "failed", "penalty_minutes": applied, "state": load_state(conn)}


def escape_check_request(state: dict[str, Any], *, player_skills: list[dict[str, Any]] | None = None,
                         turn: int | None = None) -> dict[str, Any] | None:
    """What the caller hands to skill_checks.resolve_check for an escape attempt; None when there is no
    escape or (with `turn` given) the attempt is on cooldown. Pure."""
    state = normalize_state(state)
    escape = state.get("escape")
    if state["mode"] == "free" or not escape:
        return None
    if turn is not None and escape["attempts"] > 0 and int(turn) - int(escape["last_turn"]) < int(escape["cooldown_turns"]):
        return None
    rank = 0
    for row in player_skills or []:
        if isinstance(row, dict) and str(row.get("name") or row.get("code") or "").strip().lower() == escape["skill"].lower():
            rank = _int(row.get("value") if row.get("value") is not None else row.get("level"), 0)
    note = f"Escape attempt from {_place_words(state)} ({escape['skill']}, attempt {escape['attempts'] + 1})"
    if rank:
        note += f"; rank {rank}"
    return {"skill_code": escape["skill"], "dc": int(escape["dc"]), "context_note": note[:200], "opposition": None}


# ---------------------------------------------------------------------------
# Conditions
# ---------------------------------------------------------------------------


def gather_facts(conn, world_time: dict[str, Any] | None = None) -> dict[str, Any]:
    """The Facts dict evaluate_conditions reads: clock, turn, skills, quest stages, quests, recent events."""
    wt = _world_time_or_now(conn, world_time)
    facts: dict[str, Any] = {"abs_minute": world_abs_minutes(wt), "turn": 0, "skills": [], "quest_stages": {}, "quests": [], "events": []}
    try:
        row = conn.execute("SELECT value FROM pacing WHERE key = 'turn'").fetchone()
        facts["turn"] = _int(row[0], 0) if row else 0
    except Exception:
        pass
    try:
        facts["skills"] = [{"name": str(r["name"] or ""), "value": _int(r["value"], 0)} for r in conn.execute("SELECT name, value FROM player_skills").fetchall()]
    except Exception:
        pass
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = 'quest_stages'").fetchone()
        if row and row[0]:
            loaded = json.loads(row[0])
            facts["quest_stages"] = loaded if isinstance(loaded, dict) else {}
    except Exception:
        pass
    try:
        facts["quests"] = [{"code": str(r["code"] or ""), "status": str(r["status"] or "")} for r in conn.execute("SELECT code, status FROM quests").fetchall()]
    except Exception:
        pass
    try:
        rows = conn.execute("SELECT kind, trigger, status FROM gm_events ORDER BY id DESC LIMIT 200").fetchall()
        facts["events"] = [{"kind": str(r["kind"] or ""), "trigger": str(r["trigger"] or ""), "status": str(r["status"] or "")} for r in rows]
    except Exception:
        try:
            rows = conn.execute("SELECT trigger, status FROM gm_events ORDER BY id DESC LIMIT 200").fetchall()
            facts["events"] = [{"kind": "", "trigger": str(r["trigger"] or ""), "status": str(r["status"] or "")} for r in rows]
        except Exception:
            pass
    return facts


def _skill_matches(cond_name: str, row_name: str) -> bool:
    if cond_name.strip().lower() == row_name.strip().lower():
        return True
    try:
        from app.skill_checks import load_skill_library, resolve_skill_code

        library = load_skill_library()
        want = resolve_skill_code(cond_name, library)
        return want is not None and want == resolve_skill_code(row_name, library)
    except Exception:
        return False


def _condition_met(cond: dict[str, Any], state: dict[str, Any], facts: dict[str, Any]) -> bool:
    kind = cond["type"]
    if kind == "time":
        return _int(facts.get("abs_minute"), 0) >= int(cond["abs_minute"])
    if kind == "turns":
        return _int(facts.get("turn"), 0) >= int(cond["turn"])
    if kind == "skill":
        for row in facts.get("skills") or []:
            if isinstance(row, dict) and _skill_matches(cond["name"], str(row.get("name") or "")) and _int(row.get("value"), 0) >= int(cond["level"]):
                return True
        return False
    if kind == "quest_stage":
        stages = facts.get("quest_stages")
        return isinstance(stages, dict) and cond["stage_id"] in stages
    if kind == "quest_status":
        return any(isinstance(q, dict) and str(q.get("code") or "") == cond["code"] and str(q.get("status") or "") == cond["status"] for q in facts.get("quests") or [])
    if kind == "payment":
        return _int(state.get("paid_units"), 0) >= int(cond["units"])
    if kind == "event":
        for ev in facts.get("events") or []:
            if not isinstance(ev, dict) or str(ev.get("status") or "") != "resolved":
                continue
            if str(ev.get("kind") or "") != cond["kind"]:
                continue
            if cond["trigger"] and not str(ev.get("trigger") or "").startswith(cond["trigger"]):
                continue
            return True
        return False
    if kind == "release_word":
        want = f"released_by:{cond['by']}" if cond["by"] else "released_by:"
        return any(str(note).startswith(want) for note in state.get("notes") or [])
    return False


def evaluate_conditions(state: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    """{"release", "met", "pending", "next_check_abs_minute"}; ANY satisfied condition releases. Pure."""
    state = normalize_state(state)
    facts = facts if isinstance(facts, dict) else {}
    met: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    for cond in state["conditions"]:
        (met if _condition_met(cond, state, facts) else pending).append(cond)
    times = [int(c["abs_minute"]) for c in pending if c["type"] == "time"]
    return {"release": bool(met), "met": met, "pending": pending, "next_check_abs_minute": min(times) if times else None}


def tick(conn, *, world_time: dict[str, Any] | None = None, facts: dict[str, Any] | None = None, turn: int | None = None) -> dict[str, Any]:
    """Evaluate release conditions; free the player when one is met. Returns at once when already free."""
    state = load_state(conn)
    if state["mode"] == "free":
        return _unchanged_tick(state)
    ensure_schema(conn)
    if facts is None:
        facts = gather_facts(conn, world_time)
    if turn is not None:
        facts = {**facts, "turn": int(turn)}
    result = evaluate_conditions(state, facts)
    if not result["release"]:
        return {"changed": False, "released": False, "state": state, "met": [], "next_check_abs_minute": result["next_check_abs_minute"], "journal": [], "log_event": ""}
    now = _int(facts.get("abs_minute"), 0)
    use_turn = int(turn) if turn is not None else _int(facts.get("turn"), 0)
    first = result["met"][0]
    save_state(conn, free_state())
    _log(conn, turn=use_turn, abs_minute=now, event="tick_release", mode="free", reason=f"release:{first['type']}",
         from_location_id=(state.get("place") or {}).get("location_id", 0) if state.get("place") else 0,
         detail={"met": result["met"], "was": state})
    word = {"time": "Time passed and you were let go.", "payment": "The price was paid and you were let go."}.get(first["type"], "Your captivity ended.")
    note = _journal_note(JOURNAL_KINDS["released"], f"{word} ({state['label']}, {first['type']}.)")
    return {"changed": True, "released": True, "state": free_state(), "met": result["met"], "next_check_abs_minute": None, "journal": [note], "log_event": "tick_release"}


# ---------------------------------------------------------------------------
# Position: plans are pure, apply needs injected writers
# ---------------------------------------------------------------------------


def place_from_target(target: dict[str, Any] | None, *, location_id: int = 0, location_code: str = "") -> dict[str, Any] | None:
    """A turn_prompts Target ({x,y} | {x,y,city,location_code?} | {plot,city,x,y,location_code?}) as a place dict."""
    if not isinstance(target, dict) or not target:
        return None
    cell = [int(target["x"]), int(target["y"])] if _has_int(target, "x") and _has_int(target, "y") else None
    return _normalize_place({
        "location_id": _int(location_id, 0) or _int(target.get("location_id"), 0),
        "location_code": str(location_code or target.get("location_code") or ""),
        "plot": str(target.get("plot") or ""),
        "city_id": str(target.get("city") or target.get("city_id") or ""),
        "cell": cell,
    })


def target_from_place(place: dict[str, Any] | None) -> dict[str, Any] | None:
    """The inverse: a Target destination_marker.js and turn_prompts.gate_after_turn can read."""
    place = _normalize_place(place)
    if place is None:
        return None
    out: dict[str, Any] = {}
    if place["plot"]:
        out["plot"] = place["plot"]
        out["city"] = place["city_id"]
    if place["cell"]:
        out["x"] = int(place["cell"][0])
        out["y"] = int(place["cell"][1])
        if place["city_id"] and "city" not in out:
            out["city"] = place["city_id"]
    if place["location_code"]:
        out["location_code"] = place["location_code"]
    if not out:
        out = {"location_code": place["location_code"], "location_id": place["location_id"]}
    elif place["location_id"] and not place["cell"] and not place["plot"]:
        out["location_id"] = place["location_id"]
    return out


def _looks_like_place(target: dict[str, Any]) -> bool:
    return any(key in target for key in ("location_id", "city_id", "cell")) and "x" not in target


def plan_position(state: dict[str, Any], target: dict[str, Any], *, actor: str, trust: str, chart: dict[str, Any] | None,
                  current_location_id: int, current_town: dict[str, Any] | None, locations: list[dict[str, Any]]) -> dict[str, Any]:
    """A PositionPlan: which of the three position records would change and through which existing writer.
    Pure; never writes. ValueError on an unknown trust word."""
    if trust not in TRUSTED_ACTORS + ("model",):
        raise ValueError(f"unknown trust: {trust!r}")
    state = normalize_state(state)
    place = _normalize_place(target) if isinstance(target, dict) and _looks_like_place(target) else place_from_target(target)
    plan: dict[str, Any] = {
        "ok": False, "reason": "", "actor": str(actor or ""), "trust": str(trust),
        "target": place, "as_target": target_from_place(place),
        "layers": {"location": None, "token": None, "town": None},
        "calls": [], "journal": [], "distance_cells": 0,
    }
    if place is None:
        plan["reason"] = "unknown_target"
        return plan

    rows = [row for row in locations or [] if isinstance(row, dict)]
    to_id = int(place["location_id"] or 0)
    to_row: dict[str, Any] | None = None
    if place["location_code"]:
        to_row = next((row for row in rows if str(row.get("code") or "").upper() == place["location_code"]), None)
    if to_row is None and to_id:
        to_row = next((row for row in rows if _int(row.get("id"), 0) == to_id), None)
    if to_row is None and place["plot"]:
        to_row = next((row for row in rows if str(row.get("plot_id") or "") == place["plot"]), None)
    if to_row is not None:
        to_id = _int(to_row.get("id"), 0)
        place["location_id"] = to_id
        if not place["location_code"] and to_row.get("code"):
            place["location_code"] = str(to_row.get("code") or "").upper()
        plan["as_target"] = target_from_place(place)
    if place["location_code"] and to_row is None and not to_id and not place["cell"] and not place["plot"]:
        plan["reason"] = "unknown_target"
        return plan

    cell = place["cell"]
    start: tuple[int, int] | None = None
    if chart is not None and cell is not None:
        from app.tile_world import _player_xy

        start = _player_xy(chart)
        plan["distance_cells"] = _cheb(start, cell)
    elif chart is None and cell is not None and to_id == 0 and not place["plot"]:
        plan["reason"] = "no_map"
        return plan

    if trust == "model":
        own = state.get("place") or {}
        at_captor = bool(own) and (
            (own.get("location_id") and own.get("location_id") == to_id)
            or (own.get("cell") and cell is not None and list(own["cell"]) == list(cell))
        )
        if not at_captor and plan["distance_cells"] > MODEL_MAX_CELLS:
            plan["reason"] = "too_far"
            return plan
    elif trust == "event" and plan["distance_cells"] > TRANSFER_MAX_CELLS:
        plan["reason"] = "too_far"
        return plan

    layers = plan["layers"]
    if to_id and to_id != _int(current_location_id, 0):
        layers["location"] = {"from_id": _int(current_location_id, 0), "to_id": to_id}
        plan["calls"].append("UPDATE player SET current_location_id (town_moves.enter_town style)")
    if chart is not None and cell is not None and start is not None and tuple(cell) != tuple(start):
        layers["token"] = {"map_id": str(chart.get("id") or ""), "from": [start[0], start[1]], "to": [int(cell[0]), int(cell[1])]}
        plan["calls"].append("tile_world.restore_player_position(map_id, x, y)")
    town_action = "keep"
    if chart is not None and cell is not None and chart.get("cities"):
        from app.town_grid import _locate

        probe = dict(chart)
        located = _locate(probe, int(cell[0]), int(cell[1]))
        if located is not None:
            town_action = "enter"
        elif current_town:
            town_action = "clear"
    elif place["plot"]:
        town_action = "enter"
    elif current_town and cell is not None:
        town_action = "clear"
    layers["town"] = {"action": town_action, "came_from": [start[0], start[1]] if (town_action == "enter" and start is not None) else None}
    if town_action == "enter":
        plan["calls"].append("town_moves.enter_town(conn, chart, came_from)")
    elif town_action == "clear":
        plan["calls"].append("town_moves.clear_position(conn)")

    name = (to_row or {}).get("name") or place["location_code"] or place["plot"] or (f"{cell[0]},{cell[1]}" if cell else "another place")
    plan["journal"] = [_journal_note(JOURNAL_KINDS["escort"], f"You are taken to {name}.")]
    plan["ok"] = True
    return plan


def apply_position(conn, plan: dict[str, Any], *, writers: dict[str, Any] | None, turn: int,
                   world_time: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run the engine's writers for each planned layer, in the order location, token, town, then log
    position_set. The writers are injected; this module never moves the player itself."""
    if writers is None:
        raise RuntimeError("restraint.apply_position is not wired: pass the engine's writers")
    if not isinstance(plan, dict) or not plan.get("ok"):
        raise ValueError("apply_position needs a plan with ok True")
    ensure_schema(conn)
    layers = plan.get("layers") or {}
    applied: list[str] = []
    location = layers.get("location")
    if location:
        writer = writers.get("location")
        if writer is None:
            raise RuntimeError("apply_position: the plan needs a 'location' writer")
        writer(conn, int(location["to_id"]))
        applied.append("location")
    token = layers.get("token")
    if token:
        writer = writers.get("token")
        if writer is None:
            raise RuntimeError("apply_position: the plan needs a 'token' writer")
        writer(str(token.get("map_id") or ""), int(token["to"][0]), int(token["to"][1]))
        applied.append("token")
    town = layers.get("town")
    if town and str(town.get("action") or "keep") != "keep":
        writer = writers.get("town")
        if writer is None:
            raise RuntimeError("apply_position: the plan needs a 'town' writer")
        came_from = town.get("came_from")
        writer(conn, str(town["action"]), tuple(came_from) if came_from else None)
        applied.append("town")
    now = world_abs_minutes(_world_time_or_now(conn, world_time))
    state = load_state(conn)
    if state["mode"] != "free" and plan.get("target"):
        state["place"] = _normalize_place(plan["target"])
        save_state(conn, state)
    log_id = _log(
        conn, turn=turn, abs_minute=now, event="position_set", mode=state["mode"], reason=f"position:{plan.get('trust')}",
        actor_code=str(plan.get("actor") or "")[:12],
        from_location_id=(location or {}).get("from_id", 0), to_location_id=(location or {}).get("to_id", 0),
        detail={"applied": applied, "layers": layers, "calls": plan.get("calls") or []},
    )
    return {"applied": applied, "log_id": log_id, "journal": list(plan.get("journal") or [])}


def plan_escort(chart: dict[str, Any] | None, *, start: tuple[int, int], dest: dict[str, Any], town_position: dict[str, Any] | None = None,
                budget: int = ESCORT_CELL_BUDGET) -> dict[str, Any]:
    """Plan an escort path over the world map with the existing step picker. Pure: the chart is probed
    through a shallow copy, nothing moves."""
    if not isinstance(dest, dict) or not _has_int(dest, "x") or not _has_int(dest, "y"):
        raise ValueError("plan_escort needs a dest with x and y")
    sx, sy = int(start[0]), int(start[1])
    tx, ty = int(dest["x"]), int(dest["y"])
    plan_id = f"esc-{sx},{sy}-{tx},{ty}-{int(budget)}"
    plan: dict[str, Any] = {"ok": False, "stopped": "no_map", "from": [sx, sy], "to": [tx, ty], "legs": [], "minutes_total": 0, "cells": 0, "plan_id": plan_id}
    if chart is None:
        return plan
    from app.tile_world import _cell_at, tile_walkable
    from app.turn_prompts import next_world_step

    probe = dict(chart)
    probe["player"] = {"x": sx, "y": sy}
    legs: list[dict[str, Any]] = []

    if isinstance(town_position, dict) and (town_position.get("city_id") or town_position.get("cx") is not None):
        outside = True
        if chart.get("cities"):
            from app.town_grid import _locate

            located = _locate(probe, tx, ty)
            if located is not None and str(located[0].get("id") or "") == str(town_position.get("city_id") or ""):
                outside = False
        elif (_int(town_position.get("cx")), _int(town_position.get("cy"))) == (tx, ty):
            outside = False
        if outside:
            legs.append({"kind": "leave", "target": [tx, ty], "deferred": True, "via": "town_moves.walk_out"})

    if (sx, sy) == (tx, ty):
        stopped = "same_cell"
        path: list[list[int]] = [[sx, sy]]
        terrains: list[str] = []
        minutes = 0
    else:
        x, y = sx, sy
        path = [[x, y]]
        terrains = []
        minutes = 0
        stopped = "budget"
        for _ in range(max(0, int(budget))):
            step = next_world_step(probe, tx, ty)
            if step is None:
                stopped = "blocked"
                break
            nx, ny = int(step[0]), int(step[1])
            here = _cell_at(probe, x, y)
            there = _cell_at(probe, nx, ny)
            if not tile_walkable(there):
                stopped = "blocked"
                break
            minutes += int(_walk_minutes(here, there))
            terrains.append(str((there or {}).get("state") or "plains"))
            path.append([nx, ny])
            x, y = nx, ny
            probe["player"] = {"x": x, "y": y}
            if (x, y) == (tx, ty):
                stopped = "arrived"
                break
        if len(path) > 1:
            legs.append({"kind": "world", "path": path, "terrains": terrains, "minutes": minutes})

    if dest.get("plot"):
        legs.append({
            "kind": "town",
            "target": {"plot": str(dest.get("plot") or ""), "city_id": str(dest.get("city") or dest.get("city_id") or ""), "cx": tx, "cy": ty},
            "deferred": True, "via": "turn_prompts.walk_in_town", "rule": "town_led",
        })

    plan.update({"ok": stopped in ("arrived", "budget", "same_cell"), "stopped": stopped, "legs": legs, "minutes_total": minutes, "cells": len(path) - 1})
    return plan


def _walk_minutes(here: dict[str, Any] | None, there: dict[str, Any] | None) -> int:
    from app.tile_world import walk_minutes_for_step

    return walk_minutes_for_step(here, there)


def escort_travel_dict(leg: dict[str, Any]) -> dict[str, Any]:
    """The travel dict world._spend_travel reads for one escort leg; encounters never happen on an escort."""
    if not isinstance(leg, dict):
        raise ValueError("escort_travel_dict needs a leg dict")
    kind = str(leg.get("kind") or "")
    if kind == "world":
        path = leg.get("path") or []
        terrains = [str(t) for t in leg.get("terrains") or []]
        start = list(path[0]) if path else [0, 0]
        end = list(path[-1]) if path else start
        steps = max(0, len(path) - 1)
        terrain = terrains[-1] if terrains else "plains"
        minutes = _int(leg.get("minutes"), 0)
    else:
        target = leg.get("target")
        if isinstance(target, dict):
            end = [_int(target.get("cx")), _int(target.get("cy"))]
        elif isinstance(target, (list, tuple)) and len(target) == 2:
            end = [int(target[0]), int(target[1])]
        else:
            end = [0, 0]
        start = end
        steps = 0
        terrains = []
        terrain = "town" if kind == "town" else "road"
        minutes = 0
    return {
        "minutes": minutes,
        "terrain": terrain,
        "from": start,
        "to": end,
        "steps": steps,
        "encounter": {"happened": False},
        "escort": True,
        "on_road": bool(terrains) and all(t in ("road", "bridge") for t in terrains),
    }


def begin_escort(conn, plan: dict[str, Any], *, by: dict[str, Any] | None, turn: int, world_time: dict[str, Any] | None = None) -> dict[str, Any]:
    """Put the player in custody with an escort block for a planned path. Logs captured or transferred."""
    if not isinstance(plan, dict) or not plan.get("ok"):
        raise ValueError("begin_escort needs an escort plan with ok True")
    ensure_schema(conn)
    now = world_abs_minutes(_world_time_or_now(conn, world_time))
    previous = load_state(conn)
    replaced = previous["mode"] != "free"
    state = previous if replaced else free_state()
    captor = _entity_ref(by) if by is not None else state.get("by")
    to = plan.get("to") or [0, 0]
    town_leg = next((leg for leg in plan.get("legs") or [] if leg.get("kind") == "town"), None)
    target = (town_leg or {}).get("target") or {}
    state.update({
        "mode": "custody",
        "scope": "person",
        "by": captor,
        "label": state["label"] if replaced and state["label"] else (f"In {captor['name']}'s custody" if captor else "In custody")[:80],
        "reason": state["reason"] if replaced else "escort",
        "allowed": list(ALLOWED_BY_MODE["custody"]),
        "escape": state["escape"] if replaced and state["escape"] else {
            "skill": CAPTURE_DEFAULTS["custody"][4], "dc": CAPTURE_DEFAULTS["custody"][5], "attempts": 0, "last_turn": 0,
            "cooldown_turns": CAPTURE_DEFAULTS["custody"][6], "fail_penalty_minutes": CAPTURE_DEFAULTS["custody"][7],
        },
        "escort": {
            "to": {"x": int(to[0]), "y": int(to[1]), "plot": str(target.get("plot") or ""), "city_id": str(target.get("city_id") or ""), "location_code": ""},
            "legs_done": 0, "legs_total": len(plan.get("legs") or []), "plan_id": str(plan.get("plan_id") or ""),
        },
        "set_turn": int(turn),
    })
    if not replaced:
        state["since"] = {"turn": int(turn), "abs_minute": now}
    save_state(conn, state)
    state = load_state(conn)
    log_id = _log(
        conn, turn=turn, abs_minute=now, event="transferred" if replaced else "captured", mode="custody", reason="escort:begin",
        actor_code=(captor or {}).get("code", "") if captor else "", detail={"plan_id": plan.get("plan_id"), "legs": len(plan.get("legs") or []), "to": list(to)},
    )
    by_clause = f" by {captor['name']}" if captor else ""
    note = _journal_note(JOURNAL_KINDS["escort"], f"You are taken{by_clause} toward {int(to[0])},{int(to[1])}.")
    return {"ok": True, "state": state, "journal": [note], "log_id": log_id, "replaced_previous": replaced}


def advance_escort(conn, *, legs_done: int, turn: int) -> dict[str, Any]:
    """Bump escort.legs_done; at legs_total the escort block is removed (mode stays custody)."""
    state = load_state(conn)
    escort = state.get("escort")
    if state["mode"] != "custody" or not escort:
        return state
    done = max(0, _int(legs_done, 0))
    if done >= int(escort["legs_total"]):
        state["escort"] = None
    else:
        escort["legs_done"] = done
        state["escort"] = escort
    state["set_turn"] = int(turn)
    save_state(conn, state)
    return load_state(conn)


# ---------------------------------------------------------------------------
# Prose and the op grammar
# ---------------------------------------------------------------------------


def _status_line(key: str, severity: str, line: str, blocks: list[str]) -> dict[str, Any]:
    return {"key": key, "severity": severity, "line": line.strip()[:160], "blocks": list(blocks)}


def _owed_words(cond: dict[str, Any], paid: int) -> str:
    owed = max(0, int(cond["units"]) - int(paid))
    try:
        from app import currency

        return currency.format_amount(owed, currency.theme_set(cond["currency_set"]))
    except Exception:
        return f"{owed} {cond['currency_set'] or 'units'}".strip()


def status_lines(state: dict[str, Any], world_time: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """StatusLine rows (contracts 1.10) for the prompt and the UI; [] when free. Pure."""
    state = normalize_state(state)
    if state["mode"] == "free":
        return []
    out: list[dict[str, Any]] = []
    by = _by_name(state)
    by_clause = f" by {by}" if by else ""
    severity, template, blocks = STATUS_LINES[state["mode"]]
    out.append(_status_line("restraint", severity, template.format(by_clause=by_clause, label=_place_words(state)), blocks))
    escort = state.get("escort")
    if escort:
        legs_left = max(0, int(escort["legs_total"]) - int(escort["legs_done"]))
        to = escort["to"]
        where = to.get("location_code") or to.get("plot") or f"{to.get('x')},{to.get('y')}"
        severity, template, blocks = STATUS_LINES["escort"]
        out.append(_status_line("escort", severity, template.format(to=where, legs_left=legs_left, plural="" if legs_left == 1 else "es"), blocks))
    now = world_abs_minutes(world_time) if isinstance(world_time, dict) else None
    if now is not None:
        times = [int(c["abs_minute"]) for c in state["conditions"] if c["type"] == "time" and int(c["abs_minute"]) > now]
        if times:
            left = min(times) - now
            hours = max(1, int(round(left / 60.0)))
            severity, template, blocks = STATUS_LINES["time_left"]
            out.append(_status_line("time_left", severity, template.format(hours=hours, plural="" if hours == 1 else "s"), blocks))
    for cond in state["conditions"]:
        if cond["type"] == "payment" and int(cond["units"]) > int(state["paid_units"]):
            severity, template, blocks = STATUS_LINES["payment"]
            out.append(_status_line("payment", severity, template.format(owed=_owed_words(cond, state["paid_units"])), blocks))
            break
    return out


def prompt_block(state: dict[str, Any], world_time: dict[str, Any] | None = None) -> str:
    """The restraint lines under one header, in the style of player_resources.resources_prompt_block; "" when free."""
    lines = status_lines(state, world_time)
    if not lines:
        return ""
    return "\n".join([PROMPT_HEADER] + [f"- {row['line']}" for row in lines])


_OP_KEYWORDS = ("BY", "AT", "FOR", "UNTIL", "TO")


def _op_parts(entry: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
    """Positionals with the keyword pairs folded into flags, so both tokenizer shapes parse the same."""
    args = [str(a) for a in (entry.get("args") or [])]
    flags = {str(k).upper(): str(v) for k, v in (entry.get("flags") or {}).items()}
    positionals: list[str] = []
    i = 0
    while i < len(args):
        token = args[i]
        if token.upper() in _OP_KEYWORDS and i + 1 < len(args):
            flags.setdefault(token.upper(), args[i + 1])
            i += 2
            continue
        positionals.append(token)
        i += 1
    return positionals, flags


def _until_condition(text: str) -> dict[str, Any]:
    parts = str(text or "").split(":")
    head = parts[0].strip().lower()
    if head == "skill" and len(parts) >= 3:
        return normalize_condition({"type": "skill", "name": parts[1], "level": int(parts[2])})
    if head == "quest" and len(parts) >= 3:
        return normalize_condition({"type": "quest_status", "code": parts[1], "status": parts[2]})
    if head == "stage" and len(parts) >= 2:
        return normalize_condition({"type": "quest_stage", "stage_id": ":".join(parts[1:])})
    if head == "pay" and len(parts) >= 2:
        return normalize_condition({"type": "payment", "units": int(parts[1]), "currency_set": parts[2] if len(parts) > 2 else ""})
    if head == "event" and len(parts) >= 2:
        return normalize_condition({"type": "event", "kind": parts[1], "trigger": ":".join(parts[2:])})
    raise ValueError(f"unknown UNTIL type: {text!r}")


def parse_restraint_op(entry: dict[str, Any]) -> dict[str, Any]:
    """Parse a RESTRAIN / RELEASE / ESCORT op entry (turn_dsl op shape) into a model assertion. Pure.
    Grammar: RESTRAIN bonds|custody|cell "label" [BY code] [AT code|"place"] [FOR minutes]
    [UNTIL skill:<name>:<level> | quest:<code>:<status> | stage:<id> | pay:<units> | event:<kind>];
    RELEASE "reason" [BY code]; ESCORT TO code|"place" [BY code]."""
    if not isinstance(entry, dict):
        return {"ok": False, "op": "", "proposal": None, "error": "not an op entry"}
    op = str(entry.get("op") or "").upper()
    if op not in RESTRAINT_OPS:
        return {"ok": False, "op": op, "proposal": None, "error": f"not a restraint op: {op or 'empty'}"}
    positionals, flags = _op_parts(entry)
    proposal: dict[str, Any] = {"kind": "", "label": "", "by_code": _text(flags.get("BY"), 12).upper(), "place_ref": _text(flags.get("AT") or flags.get("TO"), 80), "minutes": 0, "conditions": []}
    if op == "RESTRAIN":
        kind = positionals[0].strip().lower() if positionals else ""
        if kind not in CAPTURE_DEFAULTS:
            return {"ok": False, "op": op, "proposal": None, "error": f"unknown restraint kind: {kind or 'missing'}"}
        label = " ".join(p for p in positionals[1:]).strip()
        if not label:
            return {"ok": False, "op": op, "proposal": None, "error": "missing label"}
        proposal["kind"] = kind
        proposal["label"] = label[:80]
        if "FOR" in flags:
            raw_minutes = str(flags["FOR"]).strip()
            if not re.fullmatch(r"-?\d+", raw_minutes):
                return {"ok": False, "op": op, "proposal": None, "error": f"FOR needs whole minutes, got {raw_minutes!r}"}
            proposal["minutes"] = max(0, int(raw_minutes))
        if "UNTIL" in flags:
            try:
                proposal["conditions"].append(_until_condition(flags["UNTIL"]))
            except (ValueError, TypeError) as exc:
                return {"ok": False, "op": op, "proposal": None, "error": str(exc)}
        return {"ok": True, "op": op, "proposal": proposal, "error": ""}
    if op == "RELEASE":
        reason = " ".join(positionals).strip()
        if not reason:
            return {"ok": False, "op": op, "proposal": None, "error": "missing reason"}
        proposal["kind"] = "release"
        proposal["label"] = reason[:80]
        return {"ok": True, "op": op, "proposal": proposal, "error": ""}
    if not proposal["place_ref"]:
        return {"ok": False, "op": op, "proposal": None, "error": "ESCORT needs TO"}
    proposal["kind"] = "escort"
    proposal["label"] = f"Taken to {proposal['place_ref']}"[:80]
    return {"ok": True, "op": op, "proposal": proposal, "error": ""}
