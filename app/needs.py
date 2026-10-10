"""Hunger and thirst over world time.

Status: built, not wired (TODO n16).

Two needs, hunger and thirst, as 0..100 values stored in one settings row (`player_needs`). They fall as
world minutes pass (faster when travelling, slower asleep, thirst faster in heat) and rise when the
player eats or drinks an inventory item the word tables recognise. Bands on each value map to effects:
a recovery multiplier that slows energy, fatigue and wound recovery, fatigue gained per hour, energy and
health lost per hour, and a sustained-low penalty once a need has sat under 25 for twelve hours. Every
decision is a pure function over the state dict; the writers (`load_state`, `save_state`,
`tick_and_save`, `consume_from_inventory`) touch only the `player_needs` row. Nothing here changes the
player row, the inventory or any prompt, and the live game does not call this module.

Wiring (not done):
  app/world.py:advance_world_time() after tick_weather() -> needs.tick_and_save(conn, minutes=add, world_time=after,
      activity="wait", weather=get_weather(conn)), mirroring the tick_quest_clocks call (try/except, gated by
      playthrough_options.needs_enabled).
  app/world.py:_spend_travel() and app/world.py:play_wait_turn() (right after apply_regen) -> pass the real activity
      ("travel", or kind_l), fold the returned deltas into res_delta / res_block, append needs.prompt_block(state) to
      model_input next to resource_regen.
  app/world.py:play_turn() after advance_world_time(c_time, spent) -> intent = needs.detect_intent(player_line); when
      intent["action"]: needs.consume_from_inventory(conn, intent, rows=state["inventory"], world_time=...) and append its
      consume InventoryChange to result["inventory_changes"], its line to mechanics_context["needs"].
  app/player_resources.py:apply_regen() -> multiply the *_exact regen values by
      needs.merge_recovery(needs.recovery_modifier(ns), body_health.recovery_modifier(body))["mult"] before settle_resource_carry.
  app/world.py:apply_turn() beside _apply_player() -> add tick deltas["health"] to result["player"]["health_delta"] and list
      "player.health_delta" in result["_server_authored"]; energy/fatigue deltas through
      player_resources.spend_resources(conn, energy=-d, fatigue=d).
  app/world.py:get_state() near the turn_prompts.state_view merge -> state["needs"] = needs.state_view(needs.load_state(conn)).
  app/world.py:build_prompt_context() -> append needs.prompt_block(state) beside the resource lines.

Turn on:
  [ ] playthrough_options.needs_enabled (default off), read by the wiring
  [ ] app/world.py:SNAPSHOT_SETTING_KEYS += "player_needs" (rewind and new game); no init_db change (settings row only)
  [ ] the advance_world_time tick; the eat/drink detection in play_turn; the apply_regen multiplier
  [ ] prompt: the prompt block line in build_prompt_context
  [ ] UI: two chips under the resource bars from state.needs

Tests: tests/test_needs.py
"""
from __future__ import annotations

import json
import re
from typing import Any

from app.player_resources import _float, _int, world_abs_minutes
from app.prose_state import strip_negated_clauses

# ---------------------------------------------------------------------------
# Storage names
# ---------------------------------------------------------------------------

NEEDS_KEY = "player_needs"
STATE_VERSION = 1

DEFAULT_NEEDS_SETTINGS: dict[str, Any] = {
    "enabled": False,            # the turn-on flag a wiring pass reads
    "start_value": 85.0,
    "hunger_rate_mult": 1.0,     # scales HUNGER_PER_HOUR
    "thirst_rate_mult": 1.0,
    "effects_scale": 1.0,        # scales every per-hour effect (not the recovery multiplier)
    "sustained_penalty": True,
}

# ---------------------------------------------------------------------------
# Rules tables (data). Reshape numbers here, not in the functions below.
# ---------------------------------------------------------------------------

LOW_THRESHOLD = 25.0                    # below this a need counts as "low" for the sustained penalty

HUNGER_PER_HOUR = 2.0                   # 100 -> 0 in 50 world hours at rest
THIRST_PER_HOUR = 4.0                   # 100 -> 0 in 25 world hours at rest

ACTIVITY_MULT = {                       # multiplies both rates for the minutes ticked
    "sleep": 0.5, "meditate": 0.8, "wait": 0.9, "none": 1.0, "talk": 1.0,
    "travel": 1.5, "fight": 1.4, "climb": 1.4, "work": 1.2,
}
WEATHER_THIRST_MULT = {"heat": 1.6, "wind": 1.15, "clear": 1.0, "cloudy": 1.0, "rain": 0.9, "fog": 1.0, "storm": 1.0, "snow": 1.0}
WEATHER_HUNGER_MULT = {"snow": 1.25, "storm": 1.1}      # missing kind = 1.0

# Bands: (min_value, key, label); scanned from the top, first min_value <= value wins.
HUNGER_BANDS = (
    (75.0, "sated",       "well fed"),
    (50.0, "fine",        "fed"),
    (25.0, "hungry",      "hungry"),
    (10.0, "very_hungry", "very hungry"),
    (0.0,  "starving",    "starving"),
)
THIRST_BANDS = (
    (75.0, "sated",      "well watered"),
    (50.0, "fine",       "fine"),
    (25.0, "thirsty",    "thirsty"),
    (10.0, "parched",    "parched"),
    (0.0,  "dehydrated", "dehydrated"),
)

# Effects per band. Per-hour numbers are in player-row points per world hour (positive fatigue = gain).
HUNGER_EFFECTS = {
    "sated":       {"recovery_mult": 1.05, "fatigue_per_hour": 0.0,  "energy_per_hour": 0.0,   "health_per_hour": 0.0,  "severity": None},
    "fine":        {"recovery_mult": 1.0,  "fatigue_per_hour": 0.0,  "energy_per_hour": 0.0,   "health_per_hour": 0.0,  "severity": None},
    "hungry":      {"recovery_mult": 0.85, "fatigue_per_hour": 0.25, "energy_per_hour": 0.0,   "health_per_hour": 0.0,  "severity": "mild"},
    "very_hungry": {"recovery_mult": 0.6,  "fatigue_per_hour": 0.5,  "energy_per_hour": -0.25, "health_per_hour": 0.0,  "severity": "serious"},
    "starving":    {"recovery_mult": 0.35, "fatigue_per_hour": 1.0,  "energy_per_hour": -0.5,  "health_per_hour": -0.5, "severity": "critical"},
}
THIRST_EFFECTS = {
    "sated":      {"recovery_mult": 1.0,  "fatigue_per_hour": 0.0, "energy_per_hour": 0.0,   "health_per_hour": 0.0,  "severity": None},
    "fine":       {"recovery_mult": 1.0,  "fatigue_per_hour": 0.0, "energy_per_hour": 0.0,   "health_per_hour": 0.0,  "severity": None},
    "thirsty":    {"recovery_mult": 0.9,  "fatigue_per_hour": 0.5, "energy_per_hour": -0.25, "health_per_hour": 0.0,  "severity": "mild"},
    "parched":    {"recovery_mult": 0.7,  "fatigue_per_hour": 1.0, "energy_per_hour": -0.75, "health_per_hour": -0.5, "severity": "serious"},
    "dehydrated": {"recovery_mult": 0.4,  "fatigue_per_hour": 2.0, "energy_per_hour": -1.5,  "health_per_hour": -2.0, "severity": "critical"},
}

# Sustained-low penalty: extra recovery multiplier once a need has stayed under LOW_THRESHOLD this long.
SUSTAINED_LOW = (            # (minutes_low, extra recovery mult), scanned from the top
    (2880, 0.4),             # two days
    (720,  0.6),             # twelve hours
)
RECOVERY_MULT_FLOOR = 0.1
RECOVERY_MULT_CEIL = 1.25

# The same tuple lives in app/body_health.py (the clean treatment's item); both tests assert the literal.
WATER_WORDS = ("water", "waterskin", "water skin", "canteen", "flask", "bottle", "skin", "gourd")

# Food and drink recognition. Each row: (words, kind, hunger_gain, thirst_gain). First row whose word
# matches wins; soup rows feed both needs through eat().
FOOD_TABLE = (
    (("meal", "stew", "roast", "pie", "feast", "supper", "dinner", "breakfast", "platter", "pottage"), "meal",   45.0, 10.0),
    (("soup", "broth", "porridge", "gruel"),                                                                 "soup",   30.0, 20.0),
    (("bread", "loaf", "ration", "rations", "cheese", "jerky", "meat", "fish", "rice", "dumpling", "sausage",
      "hardtack", "biscuit", "bannock", "tortilla", "provisions", "trail mix"),                             "staple", 30.0, 0.0),
    (("fruit", "apple", "pear", "berries", "berry", "nuts", "nut", "snack", "egg", "honey", "cake", "sweet",
      "dried", "roots", "mushroom"),                                                                        "light",  15.0, 5.0),
)
DRINK_TABLE = (
    (WATER_WORDS,                                                                   "water", 0.0, 40.0),
    (("tea", "milk", "juice", "cider", "broth"),                                     "drink", 5.0, 30.0),
    (("ale", "beer", "wine", "mead", "spirits", "whisky", "whiskey", "rum", "grog"), "drink", 5.0, 25.0),
)
FOOD_ITEM_TYPES = ("food", "ration", "rations", "provisions", "meal")
DRINK_ITEM_TYPES = ("drink", "beverage", "water")
CONSUMABLE_ITEM_TYPES = ("consumable", "food", "drink", "ration", "rations", "provisions", "meal", "beverage", "water", "")
# Item types whose description is read for food words (design_survival 0.6, shared with body_health).
DESCRIPTION_ITEM_TYPES = ("consumable", "food", "drink", "provisions", "medical", "medicine", "kit", "supplies", "")
NOT_FOOD_WORDS = ("oil", "poison", "ink", "powder", "acid", "lamp", "iron", "steel", "soap", "potion",
                  "elixir", "tonic", "bar of", "ingot", "glass", "empty", "paint", "dye", "tar", "pitch")
# "bar" and "skin" only count when the item_type is consumable-ish, because "iron bar" and "wolf skin" exist.
AMBIGUOUS_WORDS = ("bar", "skin", "flask", "bottle")

FULL_REFUSE_AT = 95.0           # eat()/drink() refuse when the need is already at or above this
PORTION_FRACTION = 1.0          # multiplies gains; "a bite" intents use 0.5

EAT_WORDS = ("eat", "eats", "eating", "chew", "bite", "devour", "dine", "breakfast", "lunch", "supper", "snack on", "nibble")
DRINK_WORDS_INTENT = ("drink", "drinks", "drinking", "sip", "gulp", "swig", "quench", "quaff")
SMALL_PORTION_WORDS = ("bite", "sip", "nibble", "a little", "a bit")
# Filler dropped from the noun phrase after the verb when reading an item hint.
HINT_FILLER_WORDS = ("some", "of", "my", "the", "a", "an", "from", "this", "that", "these", "those", "it",
                     "up", "on", "at", "bit", "little", "piece", "mouthful", "i", "we", "quickly", "slowly")

# Prose templates. {name} is the lower-cased item name.
CONSUME_LINES = {
    "meal":   "You eat the {name} and feel the hunger ease.",
    "soup":   "You eat the {name}; it warms you and settles the hunger.",
    "staple": "You eat the {name}; the hunger eases.",
    "light":  "You eat the {name}; it takes the edge off.",
    "water":  "You drink from the {name}.",
    "drink":  "You drink the {name}.",
}
STATUS_LINES = {
    "hunger": {
        "hungry":      "You are hungry; your stomach is tight and your attention drifts to food.",
        "very_hungry": "You are very hungry; you tire quickly and your strength is fading.",
        "starving":    "You are starving; you are weak, cold and losing ground every hour.",
    },
    "thirst": {
        "thirsty":    "You are thirsty; your mouth is dry and you tire faster than usual.",
        "parched":    "You are parched; your head aches and every effort costs more than it should.",
        "dehydrated": "You are dehydrated; you are dizzy, weak and failing fast without water.",
    },
    "sustained": {
        "hunger": "Long hunger has worn you down; you mend slowly.",
        "thirst": "Long thirst has worn you down; you mend slowly.",
    },
}
SEVERITY_RANK = {"critical": 3, "serious": 2, "mild": 1, "info": 0}
MAX_LAST_LINES = 4
TICK_SLICE_MINUTES = 60

# ---------------------------------------------------------------------------
# Small local helpers (copies, so this module does not import app.world or app.venues)
# ---------------------------------------------------------------------------


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _field(row: Any, key: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


def _flag(value: Any, default: bool) -> bool:
    """Flag semantics of world._setup_flag_enabled: blank keeps the default, words and booleans are honoured."""
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    lowered = str(value).strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    return default


def _word_re(word: str) -> re.Pattern[str]:
    return re.compile(r"(?<![a-z0-9])" + re.escape(word.lower()) + r"(?![a-z0-9])")


def _has_word(text: str, word: str) -> bool:
    return bool(text) and bool(_word_re(word).search(text))


def _round(value: float) -> float:
    return round(float(value), 4)


# ---------------------------------------------------------------------------
# Schema (nothing to create)
# ---------------------------------------------------------------------------


def ensure_schema(conn) -> None:
    """No tables: the state is one settings row. Kept so a wiring pass can call every module's ensure_schema."""
    return None


# ---------------------------------------------------------------------------
# Settings and state
# ---------------------------------------------------------------------------


def needs_settings(options: dict | None) -> dict[str, Any]:
    """DEFAULT_NEEDS_SETTINGS merged with playthrough_options.needs_settings (or a bare settings dict), clamped."""
    raw: dict[str, Any] = {}
    if isinstance(options, dict):
        nested = options.get("needs_settings")
        raw = nested if isinstance(nested, dict) else options
    out = dict(DEFAULT_NEEDS_SETTINGS)
    out["enabled"] = _flag(raw.get("enabled"), bool(DEFAULT_NEEDS_SETTINGS["enabled"]))
    out["start_value"] = _clamp(_float(raw.get("start_value"), DEFAULT_NEEDS_SETTINGS["start_value"]), 0.0, 100.0)
    out["hunger_rate_mult"] = _clamp(_float(raw.get("hunger_rate_mult"), 1.0), 0.25, 3.0)
    out["thirst_rate_mult"] = _clamp(_float(raw.get("thirst_rate_mult"), 1.0), 0.25, 3.0)
    out["effects_scale"] = _clamp(_float(raw.get("effects_scale"), 1.0), 0.0, 3.0)
    out["sustained_penalty"] = _flag(raw.get("sustained_penalty"), True)
    return out


def default_state(abs_minute: int = 0, *, settings: dict | None = None) -> dict[str, Any]:
    cfg = settings if isinstance(settings, dict) and "start_value" in settings else needs_settings(settings)
    start = _clamp(_float(cfg.get("start_value"), 85.0), 0.0, 100.0)
    at = max(0, _int(abs_minute, 0))
    return {
        "version": STATE_VERSION,
        "hunger": start,
        "thirst": start,
        "updated_abs": at,
        "last_meal_abs": 0,
        "last_drink_abs": 0,
        "low_hunger_minutes": 0,
        "low_thirst_minutes": 0,
        "carry": {"energy": 0.0, "fatigue": 0.0, "health": 0.0},
        "last_lines": [],
    }


def normalize_state(raw: object, *, settings: dict | None = None) -> dict[str, Any]:
    """Any junk in, a valid NeedsState out: missing keys defaulted, numbers coerced, carry clamped."""
    base = default_state(0, settings=settings)
    src = raw if isinstance(raw, dict) else {}
    out = dict(base)
    out["hunger"] = _clamp(_float(src.get("hunger"), base["hunger"]), 0.0, 100.0)
    out["thirst"] = _clamp(_float(src.get("thirst"), base["thirst"]), 0.0, 100.0)
    for key in ("updated_abs", "last_meal_abs", "last_drink_abs", "low_hunger_minutes", "low_thirst_minutes"):
        out[key] = max(0, _int(src.get(key), 0))
    carry_src = src.get("carry") if isinstance(src.get("carry"), dict) else {}
    out["carry"] = {k: _clamp(_float(carry_src.get(k), 0.0), -0.9999, 0.9999) for k in ("energy", "fatigue", "health")}
    lines = src.get("last_lines")
    out["last_lines"] = [str(x)[:160] for x in lines if isinstance(x, str) and x.strip()][:MAX_LAST_LINES] if isinstance(lines, list) else []
    return out


# ---------------------------------------------------------------------------
# Bands and effects
# ---------------------------------------------------------------------------


def band_for(value: float, bands: tuple) -> tuple[str, str]:
    v = _float(value, 0.0)
    for low, key, label in bands:
        if v >= low:
            return key, label
    return bands[-1][1], bands[-1][2]


def hunger_band(state: dict) -> str:
    return band_for(_field(state, "hunger", 0.0), HUNGER_BANDS)[0]


def thirst_band(state: dict) -> str:
    return band_for(_field(state, "thirst", 0.0), THIRST_BANDS)[0]


def _effects(need: str, band: str) -> dict[str, Any]:
    table = HUNGER_EFFECTS if need == "hunger" else THIRST_EFFECTS
    return table.get(band) or table["fine"]


def _sustained_mult(minutes_low: int, settings: dict[str, Any]) -> float:
    if not settings.get("sustained_penalty", True):
        return 1.0
    for threshold, mult in SUSTAINED_LOW:
        if minutes_low >= threshold:
            return float(mult)
    return 1.0


def zero_deltas() -> dict[str, Any]:
    return {"energy": 0, "fatigue": 0, "health": 0, "energy_exact": 0.0, "fatigue_exact": 0.0, "health_exact": 0.0, "reasons": []}


def merge_deltas(a: dict, b: dict) -> dict[str, Any]:
    """Sum two PlayerDeltas: the six numbers add, the reasons concatenate. Identical body in body_health."""
    a = a if isinstance(a, dict) else {}
    b = b if isinstance(b, dict) else {}
    out = zero_deltas()
    for key in ("energy", "fatigue", "health"):
        out[key] = _int(a.get(key), 0) + _int(b.get(key), 0)
        out[key + "_exact"] = _float(a.get(key + "_exact"), 0.0) + _float(b.get(key + "_exact"), 0.0)
    out["reasons"] = [str(r) for r in (a.get("reasons") or [])] + [str(r) for r in (b.get("reasons") or [])]
    return out


def _recovery_label(mult: float, factors: list[dict[str, Any]]) -> str:
    if abs(mult - 1.0) < 1e-9 or not factors:
        return ""
    words = []
    for f in factors:
        word = str(f.get("source") or "").replace("_", " ").replace(":", " ").strip()
        if word and word not in words:
            words.append(word)
    head = "recovery slowed" if mult < 1.0 else "recovery eased"
    return f"{head} ({', '.join(words)})"


def merge_recovery(a: dict, b: dict) -> dict[str, Any]:
    """Multiply two RecoveryModifiers, clamp 0.1..1.25, concatenate factors, rebuild the label. Identical body in body_health."""
    a = a if isinstance(a, dict) else {}
    b = b if isinstance(b, dict) else {}
    mult = _clamp(_float(a.get("mult"), 1.0) * _float(b.get("mult"), 1.0), RECOVERY_MULT_FLOOR, RECOVERY_MULT_CEIL)
    factors = [dict(f) for f in (a.get("factors") or []) if isinstance(f, dict)] + [dict(f) for f in (b.get("factors") or []) if isinstance(f, dict)]
    return {"mult": mult, "factors": factors, "label": _recovery_label(mult, factors)}


def recovery_modifier(state: dict, *, settings: dict | None = None) -> dict[str, Any]:
    cfg = needs_settings(settings)
    st = normalize_state(state, settings=cfg)
    h_band = hunger_band(st)
    t_band = thirst_band(st)
    factors: list[dict[str, Any]] = []
    mult = 1.0
    for source, band, part in (
        ("hunger", h_band, float(_effects("hunger", h_band)["recovery_mult"])),
        ("thirst", t_band, float(_effects("thirst", t_band)["recovery_mult"])),
        ("sustained_hunger", h_band, _sustained_mult(st["low_hunger_minutes"], cfg)),
        ("sustained_thirst", t_band, _sustained_mult(st["low_thirst_minutes"], cfg)),
    ):
        mult *= part
        if abs(part - 1.0) > 1e-9:
            factors.append({"source": source, "band": band, "mult": part})
    mult = _clamp(mult, RECOVERY_MULT_FLOOR, RECOVERY_MULT_CEIL)
    return {"mult": mult, "factors": factors, "label": _recovery_label(mult, factors)}


# ---------------------------------------------------------------------------
# The tick
# ---------------------------------------------------------------------------


def _weather_kind(weather: dict | None) -> str:
    return str(_field(weather, "kind", "") or "").strip().lower() if isinstance(weather, dict) else ""


def _minutes_under(before: float, after: float, minutes: int) -> int:
    """Minutes of a falling slice spent under LOW_THRESHOLD."""
    if after >= LOW_THRESHOLD:
        return 0
    if before < LOW_THRESHOLD or before <= after:
        return minutes
    return int(round(minutes * (LOW_THRESHOLD - after) / (before - after)))


def tick(
    state: dict,
    *,
    minutes: int,
    abs_minute: int,
    activity: str = "none",
    weather: dict | None = None,
    settings: dict | None = None,
) -> dict[str, Any]:
    """Age the needs by `minutes` ending at `abs_minute`; pure. Returns the TickResult dict."""
    cfg = needs_settings(settings)
    st = normalize_state(state, settings=cfg)
    span = max(0, _int(minutes, 0))
    before = {"hunger": st["hunger"], "thirst": st["thirst"]}
    deltas = zero_deltas()
    if span <= 0:
        return {
            "state": st,
            "deltas": deltas,
            "before": before,
            "after": dict(before),
            "bands": {"hunger": hunger_band(st), "thirst": thirst_band(st)},
            "recovery": recovery_modifier(st, settings=cfg),
            "lines": [],
            "minutes": 0,
        }
    act = ACTIVITY_MULT.get(str(activity or "none").strip().lower(), 1.0)
    kind = _weather_kind(weather)
    hunger_rate = HUNGER_PER_HOUR * act * WEATHER_HUNGER_MULT.get(kind, 1.0) * cfg["hunger_rate_mult"]
    thirst_rate = THIRST_PER_HOUR * act * WEATHER_THIRST_MULT.get(kind, 1.0) * cfg["thirst_rate_mult"]
    scale = cfg["effects_scale"]
    carry = dict(st["carry"])
    reasons: list[str] = []
    left = span
    while left > 0:
        m = min(TICK_SLICE_MINUTES, left)
        left -= m
        hours = m / 60.0
        h_band = hunger_band(st)
        t_band = thirst_band(st)
        for need, band in (("hunger", h_band), ("thirst", t_band)):
            eff = _effects(need, band)
            carry["fatigue"] += eff["fatigue_per_hour"] * hours * scale
            carry["energy"] += eff["energy_per_hour"] * hours * scale
            carry["health"] += eff["health_per_hour"] * hours * scale
            if eff["severity"] and f"{need}:{band}" not in reasons:
                reasons.append(f"{need}:{band}")
        h_before, t_before = st["hunger"], st["thirst"]
        st["hunger"] = _clamp(h_before - hunger_rate * hours, 0.0, 100.0)
        st["thirst"] = _clamp(t_before - thirst_rate * hours, 0.0, 100.0)
        under_h = _minutes_under(h_before, st["hunger"], m)
        under_t = _minutes_under(t_before, st["thirst"], m)
        st["low_hunger_minutes"] = st["low_hunger_minutes"] + under_h if under_h > 0 else 0
        st["low_thirst_minutes"] = st["low_thirst_minutes"] + under_t if under_t > 0 else 0
    for key in ("energy", "fatigue", "health"):
        total = round(carry[key], 6)
        whole = int(total)  # truncates toward zero; the remainder stays in the carry
        deltas[key] = whole
        deltas[key + "_exact"] = total - st["carry"][key]
        carry[key] = round(total - whole, 6)
    deltas["reasons"] = reasons
    st["hunger"] = _round(st["hunger"])
    st["thirst"] = _round(st["thirst"])
    st["carry"] = carry
    st["updated_abs"] = max(0, _int(abs_minute, 0))
    lines = status_lines(st, settings=cfg)
    st["last_lines"] = [ln["line"] for ln in lines][:MAX_LAST_LINES]
    return {
        "state": st,
        "deltas": deltas,
        "before": before,
        "after": {"hunger": st["hunger"], "thirst": st["thirst"]},
        "bands": {"hunger": hunger_band(st), "thirst": thirst_band(st)},
        "recovery": recovery_modifier(st, settings=cfg),
        "lines": lines,
        "minutes": span,
    }


# ---------------------------------------------------------------------------
# Food and drink recognition
# ---------------------------------------------------------------------------


def _match_table(text: str, table: tuple, consumable_ish: bool) -> tuple | None:
    for words, kind, h_gain, t_gain in table:
        for word in words:
            if word in AMBIGUOUS_WORDS and not consumable_ish:
                continue
            if _has_word(text, word):
                return word, kind, float(h_gain), float(t_gain)
    return None


def classify_item(row: Any) -> dict[str, Any]:
    """Food or drink? ItemClass over an inventory row (dict or sqlite3.Row)."""
    name = str(_field(row, "name", "") or "").strip()
    name_l = name.lower()
    item_type = str(_field(row, "item_type", "") or "").strip().lower()
    description = str(_field(row, "description", "") or "").strip().lower()
    quantity = _int(_field(row, "quantity", 0), 0)
    out: dict[str, Any] = {"food": False, "drink": False, "kind": "none", "hunger_gain": 0.0, "thirst_gain": 0.0, "matched": "", "name": name}
    if any(_has_word(name_l, w) for w in NOT_FOOD_WORDS):
        return out
    consumable_ish = item_type in CONSUMABLE_ITEM_TYPES
    hit = _match_table(name_l, FOOD_TABLE, consumable_ish)
    drink_hit = _match_table(name_l, DRINK_TABLE, consumable_ish)
    if hit is None and drink_hit is None and description and item_type in DESCRIPTION_ITEM_TYPES:
        hit = _match_table(description, FOOD_TABLE, consumable_ish)
        drink_hit = _match_table(description, DRINK_TABLE, consumable_ish)
    if hit is not None:
        word, kind, h_gain, t_gain = hit
        out.update({"food": True, "kind": kind, "hunger_gain": h_gain, "thirst_gain": t_gain, "matched": word})
    elif drink_hit is not None:
        word, kind, h_gain, t_gain = drink_hit
        out.update({"drink": True, "kind": kind, "hunger_gain": h_gain, "thirst_gain": t_gain, "matched": word})
    elif item_type in FOOD_ITEM_TYPES:
        out.update({"food": True, "kind": "staple", "hunger_gain": 30.0, "thirst_gain": 0.0, "matched": f"item_type:{item_type}"})
    elif item_type in DRINK_ITEM_TYPES:
        out.update({"drink": True, "kind": "water", "hunger_gain": 0.0, "thirst_gain": 40.0, "matched": f"item_type:{item_type}"})
    if quantity <= 0:
        out["food"] = False
        out["drink"] = False
    return out


def food_items(rows: Any) -> list[tuple[Any, dict[str, Any]]]:
    out = []
    for row in rows or []:
        cls = classify_item(row)
        if cls["food"]:
            out.append((row, cls))
    return out


def drink_items(rows: Any) -> list[tuple[Any, dict[str, Any]]]:
    out = []
    for row in rows or []:
        cls = classify_item(row)
        if cls["drink"]:
            out.append((row, cls))
    return out


# ---------------------------------------------------------------------------
# Intent
# ---------------------------------------------------------------------------

_QUOTE_SPLIT_RE = re.compile(r'["“”]')
_HINT_STOP_RE = re.compile(r"[,.;:!?\n]|\s+(?:and|then|while|before|after|so)\s+", re.I)


def _outside_quotes(text: str) -> str:
    parts = _QUOTE_SPLIT_RE.split(str(text or ""))
    return " ".join(parts[0::2])


def _first_word_match(text: str, words: tuple) -> tuple[int, int, str] | None:
    best: tuple[int, int, str] | None = None
    for word in words:
        m = _word_re(word).search(text)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), m.end(), word)
    return best


def _hint_after(text: str, end: int) -> str:
    rest = text[end:]
    stop = _HINT_STOP_RE.search(rest)
    if stop:
        rest = rest[: stop.start()]
    tokens = [t for t in re.findall(r"[a-z0-9']+", rest.lower()) if t not in HINT_FILLER_WORDS]
    return " ".join(tokens)[:60].strip()


def detect_intent(player_input: str) -> dict[str, Any]:
    """Does the line say the player eats or drinks? Quoted speech and denied clauses do not count."""
    text = strip_negated_clauses(_outside_quotes(player_input)).lower()
    eat_hit = _first_word_match(text, EAT_WORDS)
    drink_hit = _first_word_match(text, DRINK_WORDS_INTENT)
    out: dict[str, Any] = {"action": None, "item_hint": "", "portion": 1.0, "also_drink": False}
    if eat_hit is None and drink_hit is None:
        return out
    if eat_hit is not None:
        out["action"] = "eat"
        out["item_hint"] = _hint_after(text, eat_hit[1])
        out["also_drink"] = drink_hit is not None
    else:
        out["action"] = "drink"
        out["item_hint"] = _hint_after(text, drink_hit[1])
    if any(_has_word(text, w) for w in SMALL_PORTION_WORDS):
        out["portion"] = 0.5
    return out


def pick_item(rows: Any, action: str, item_hint: str = "") -> tuple[Any, dict[str, Any]] | None:
    """The inventory row to eat or drink: a hint matching half the name wins, else the biggest gain."""
    act = str(action or "").strip().lower()
    if act == "eat":
        candidates = food_items(rows)
        gain_key = "hunger_gain"
    elif act == "drink":
        candidates = drink_items(rows)
        gain_key = "thirst_gain"
    else:
        return None
    candidates = [(row, cls) for row, cls in candidates if _int(_field(row, "quantity", 0), 0) > 0]
    if not candidates:
        return None
    hint_tokens = {t for t in re.findall(r"[a-z0-9']+", str(item_hint or "").lower()) if t not in HINT_FILLER_WORDS}
    best = None
    best_score = 0.0
    if hint_tokens:
        for row, cls in candidates:
            name_tokens = [t for t in re.findall(r"[a-z0-9']+", cls["name"].lower())]
            if not name_tokens:
                continue
            hits = sum(1 for t in name_tokens if t in hint_tokens or any(h in t or t in h for h in hint_tokens if len(h) > 3 and len(t) > 3))
            ratio = hits / len(name_tokens)
            if ratio >= 0.5 and (ratio, cls[gain_key]) > (best_score, best[1][gain_key] if best else -1.0):
                best, best_score = (row, cls), ratio
    if best is not None:
        return best
    return max(candidates, key=lambda pair: pair[1][gain_key])


# ---------------------------------------------------------------------------
# Eating and drinking (pure: a new state and a consume proposal)
# ---------------------------------------------------------------------------


def _consume_result(state: dict, cls: dict, reason: str) -> dict[str, Any]:
    return {"ok": False, "reason": reason, "state": state, "consume": None, "gained": {"hunger": 0.0, "thirst": 0.0}, "line": "", "item": cls}


def _consume(state: dict, row: Any, *, action: str, abs_minute: int, portion: float, settings: dict | None) -> dict[str, Any]:
    cfg = needs_settings(settings)
    st = normalize_state(state, settings=cfg)
    cls = classify_item(row)
    quantity = _int(_field(row, "quantity", 0), 0)
    fits = cls["kind"] in ("meal", "soup", "staple", "light") if action == "eat" else cls["kind"] in ("water", "drink")
    if cls["kind"] == "none" or not fits:
        return _consume_result(st, cls, "not_food" if action == "eat" else "not_drink")
    if quantity <= 0:
        return _consume_result(st, cls, "none_left")
    need = "hunger" if action == "eat" else "thirst"
    if st[need] >= FULL_REFUSE_AT:
        return _consume_result(st, cls, "not_hungry" if action == "eat" else "not_thirsty")
    part = _clamp(_float(portion, 1.0), 0.1, 1.0) * PORTION_FRACTION
    before_h, before_t = st["hunger"], st["thirst"]
    st["hunger"] = _round(_clamp(before_h + cls["hunger_gain"] * part, 0.0, 100.0))
    st["thirst"] = _round(_clamp(before_t + cls["thirst_gain"] * part, 0.0, 100.0))
    at = max(0, _int(abs_minute, 0))
    st["updated_abs"] = at
    if action == "eat":
        st["last_meal_abs"] = at
        if st["hunger"] >= LOW_THRESHOLD:
            st["low_hunger_minutes"] = 0
    else:
        st["last_drink_abs"] = at
        if st["thirst"] >= LOW_THRESHOLD:
            st["low_thirst_minutes"] = 0
    name = cls["name"] or "food"
    line = CONSUME_LINES.get(cls["kind"], CONSUME_LINES["staple"]).format(name=name.lower())
    return {
        "ok": True,
        "reason": "",
        "state": st,
        "consume": {"name": name, "quantity_delta": -1, "source": "needs", "reason": action},
        "gained": {"hunger": _round(st["hunger"] - before_h), "thirst": _round(st["thirst"] - before_t)},
        "line": line,
        "item": cls,
    }


def eat(state: dict, row: Any, *, abs_minute: int, portion: float = 1.0, settings: dict | None = None) -> dict[str, Any]:
    return _consume(state, row, action="eat", abs_minute=abs_minute, portion=portion, settings=settings)


def drink(state: dict, row: Any, *, abs_minute: int, portion: float = 1.0, settings: dict | None = None) -> dict[str, Any]:
    return _consume(state, row, action="drink", abs_minute=abs_minute, portion=portion, settings=settings)


# ---------------------------------------------------------------------------
# Status lines, prompt block, state view
# ---------------------------------------------------------------------------


def _sustained_severity(minutes_low: int) -> str:
    return "critical" if minutes_low >= SUSTAINED_LOW[0][0] else "serious"


def status_lines(state: dict, *, settings: dict | None = None) -> list[dict[str, Any]]:
    """One StatusLine per need worth mentioning, the sustained penalties, and the recovery line; [] when all is well."""
    cfg = needs_settings(settings)
    st = normalize_state(state, settings=cfg)
    out: list[dict[str, Any]] = []
    for need, band in (("hunger", hunger_band(st)), ("thirst", thirst_band(st))):
        severity = _effects(need, band)["severity"]
        if severity:
            out.append({"key": need, "severity": severity, "line": STATUS_LINES[need][band][:160], "blocks": []})
    for need, counter in (("hunger", st["low_hunger_minutes"]), ("thirst", st["low_thirst_minutes"])):
        if _sustained_mult(counter, cfg) < 1.0:
            out.append({"key": f"sustained:{need}", "severity": _sustained_severity(counter), "line": STATUS_LINES["sustained"][need][:160], "blocks": []})
    rec = recovery_modifier(st, settings=cfg)
    if rec["mult"] < 0.95:
        words = ", ".join(_factor_word(f) for f in rec["factors"])
        out.append({"key": "recovery", "severity": "info", "line": f"Your body mends at about {int(round(rec['mult'] * 100))} percent of its usual pace ({words}).", "blocks": []})
    out.sort(key=lambda ln: -SEVERITY_RANK.get(ln["severity"], 0))
    return out


def _factor_word(factor: dict[str, Any]) -> str:
    source = str(factor.get("source") or "")
    band = str(factor.get("band") or "")
    if source == "hunger":
        return dict((k, lbl) for _, k, lbl in HUNGER_BANDS).get(band, band)
    if source == "thirst":
        return dict((k, lbl) for _, k, lbl in THIRST_BANDS).get(band, band)
    if source == "sustained_hunger":
        return "long hunger"
    if source == "sustained_thirst":
        return "long thirst"
    return source.replace("_", " ").replace(":", " ")


def prompt_block(state: dict, *, settings: dict | None = None) -> str:
    """The "Player needs (server truth):" block for a prompt, or "" when there is nothing to say."""
    cfg = needs_settings(settings)
    st = normalize_state(state, settings=cfg)
    h_key, h_label = band_for(st["hunger"], HUNGER_BANDS)
    t_key, t_label = band_for(st["thirst"], THIRST_BANDS)
    rec = recovery_modifier(st, settings=cfg)
    sustained = any(f["source"].startswith("sustained_") for f in rec["factors"])
    if h_key in ("sated", "fine") and t_key in ("sated", "fine") and not sustained:
        return ""
    lines = [
        "Player needs (server truth):",
        f"- Hunger: {int(round(st['hunger']))}/100 ({h_label})",
        f"- Thirst: {int(round(st['thirst']))}/100 ({t_label})",
    ]
    if abs(rec["mult"] - 1.0) > 1e-9:
        words = ", ".join(_factor_word(f) for f in rec["factors"])
        lines.append(f"- Recovery: ×{rec['mult']:.2f} ({words})")
    for ln in status_lines(st, settings=cfg):
        if ln["key"] != "recovery":
            lines.append(f"- {ln['line']}")
    return "\n".join(lines)


def state_view(state: dict, *, settings: dict | None = None) -> dict[str, Any]:
    cfg = needs_settings(settings)
    st = normalize_state(state, settings=cfg)
    h_key, h_label = band_for(st["hunger"], HUNGER_BANDS)
    t_key, t_label = band_for(st["thirst"], THIRST_BANDS)
    return {
        "hunger": int(round(st["hunger"])),
        "thirst": int(round(st["thirst"])),
        "hunger_band": h_key,
        "thirst_band": t_key,
        "hunger_label": h_label,
        "thirst_label": t_label,
        "recovery_mult": recovery_modifier(st, settings=cfg)["mult"],
        "lines": [ln["line"] for ln in status_lines(st, settings=cfg)],
        "last_meal_abs": st["last_meal_abs"],
        "last_drink_abs": st["last_drink_abs"],
        "low_hunger_minutes": st["low_hunger_minutes"],
        "low_thirst_minutes": st["low_thirst_minutes"],
    }


# ---------------------------------------------------------------------------
# Writers: the player_needs settings row only
# ---------------------------------------------------------------------------


def _read_options(conn) -> dict[str, Any]:
    """playthrough_options as a dict, read with one SELECT (the local_intel._play_flag_on way); {} on anything odd."""
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", ("playthrough_options",)).fetchone()
        opts = json.loads(row["value"]) if row and row["value"] else {}
    except Exception:
        return {}
    return opts if isinstance(opts, dict) else {}


def load_state(conn, *, abs_minute: int | None = None) -> dict[str, Any]:
    """The stored NeedsState, or a default built from playthrough_options.needs_settings. Never writes."""
    cfg = needs_settings(_read_options(conn))
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (NEEDS_KEY,)).fetchone()
        raw = json.loads(row["value"]) if row and row["value"] else None
    except Exception:
        raw = None
    if isinstance(raw, dict):
        return normalize_state(raw, settings=cfg)
    return default_state(_int(abs_minute, 0) if abs_minute is not None else 0, settings=cfg)


def save_state(conn, state: dict) -> None:
    clean = normalize_state(state)
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (NEEDS_KEY, json.dumps(clean, ensure_ascii=True, sort_keys=True)),
    )


def tick_and_save(conn, *, minutes: int, world_time: dict, activity: str = "none", weather: dict | None = None) -> dict[str, Any]:
    """load_state, tick to world_abs_minutes(world_time), save_state; returns the TickResult."""
    cfg = needs_settings(_read_options(conn))
    abs_minute = world_abs_minutes(world_time)
    state = load_state(conn, abs_minute=abs_minute)
    result = tick(state, minutes=minutes, abs_minute=abs_minute, activity=activity, weather=weather, settings=cfg)
    save_state(conn, result["state"])
    return result


def consume_from_inventory(conn, intent: dict, *, rows: Any, world_time: dict) -> dict[str, Any]:
    """Pick the item the intent names from `rows`, eat or drink it, save on success. Never touches inventory."""
    cfg = needs_settings(_read_options(conn))
    abs_minute = world_abs_minutes(world_time)
    state = load_state(conn, abs_minute=abs_minute)
    action = str(_field(intent, "action", "") or "").strip().lower()
    empty = {"food": False, "drink": False, "kind": "none", "hunger_gain": 0.0, "thirst_gain": 0.0, "matched": "", "name": ""}
    if action not in ("eat", "drink"):
        return _consume_result(state, empty, "no_action")
    picked = pick_item(rows, action, str(_field(intent, "item_hint", "") or ""))
    if picked is None:
        return _consume_result(state, empty, "no_item")
    row, _cls = picked
    portion = _float(_field(intent, "portion", 1.0), 1.0)
    fn = eat if action == "eat" else drink
    result = fn(state, row, abs_minute=abs_minute, portion=portion, settings=cfg)
    if result["ok"]:
        save_state(conn, result["state"])
    return result
