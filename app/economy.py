"""Settlement market simulation: supply and demand, season, scarcity, a price multiplier per category.

Status: built, not wired (TODO n1).

Every settlement the map knows (a settlements_meta row or a tile_world.list_settlements row) gets one
market_state row per goods category: stock in days of consumption, demand, production and consumption
per day derived from its size and type, a season read from the world day, scarcity events rolled from
the campaign seed and kept in market_events, and a small seeded drift so no two days are identical but a
rewind replays the same market. settlement_multiplier() turns that into the one PriceMultiplier dict that
app.trade reads; tick_day() advances the market by whole days. The module writes only its own two tables
and its own economy_config settings row. It never reads the player, the inventory, prices or currency,
never inserts into gm_events (it returns event proposals) and never touches the map. The live game does
not call it.

Wiring (not done):
  app/world.py:advance_world_time() -> on the days_add > 0 branch after tick_weather, beside the
      tick_quest_clocks call (same try/except shape, gated by playthrough_options economy_enabled and
      economy_sim_enabled): economy.tick_day(conn, from_day=int(before["day"]), to_day=int(new_day),
      settlements=tile_world.list_settlements(tile_world.get_map(None, conn)), options=playthrough_options,
      weather_kind=get_weather(conn)["kind"])
  app/world.py:apply_map_travel_step() -> next to the ensure_settlement_ruler(conn, location_id=, settlement=)
      call: economy.ensure_settlement(conn, settlement, day=int(get_world_time(conn)["day"]), options=playthrough_options)
  app/world.py:queue_world_event() -> for each entry of tick_day(...)["event_proposals"]: queue_world_event(**entry)
  app/world.py:build_prompt_context() -> one or two world facts beside the location facts:
      economy.market_lines(economy.market_snapshot(conn, sid, day=day)["multipliers"], economy.settlement_profile(meta))
  app/trade.py:settlement_price() -> economy.settlement_multiplier(conn, settlement_id, category, day=day)
      (trade is a new module of this same pass; this is the one in-cluster consumer and the only call that
      exists in code today)

Turn on:
  [ ] playthrough_options.economy_sim_enabled (default off); read by the wiring, never by this module
  [ ] app/db.py:_migrate_columns(): try: from app.economy import ensure_schema; ensure_schema(conn) except Exception: pass
  [ ] app/world.py:WORLD_TABLES and RESTORE_ORDER gain market_state and market_events; AUTOINC_TABLES gains
      market_events; market_state (text key) joins _REPLACE_ONLY_WHEN_EXPORTED and the two quest_clocks
      snapshot sites in _save_snapshot and _restore_snapshot_rows; _clear_playthrough deletes from both
  [ ] settings row economy_config is read by the tick (not snapshotted: it is a world rule, not turn state)
  [ ] the tick call and the ensure call above; no route needed (GET /api/market/{settlement_id} optional for Tools)
  [ ] UI: none
  [ ] prompt: the market_lines facts; nothing else

Tests: tests/test_economy.py
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.rng import campaign_seed, rng_for
from app.town_grid import settlement_size_for_band
from app.venues import normalize_settlement_size, size_rank
from app.world import resolve_world_magic

# ---------------------------------------------------------------------------
# Constants and rules tables (data)
# ---------------------------------------------------------------------------

CONFIG_KEY = "economy_config"
EQUILIBRIUM_DAYS = 5.0
STOCK_MIN = 0.1
STOCK_MAX = 30.0
IMPORT_PULL = 0.15
MULT_MIN = 0.40
MULT_MAX = 3.00
MAX_ACTIVE_EVENTS = 2
VENUE_PRODUCTION_BONUS = 0.15
SEED_DEMAND_NUDGE = 0.10
STRENGTH_RANGE = (0.7, 1.3)
LINE_HIGH = 1.25
LINE_LOW = 0.8

GOODS_CATEGORIES: tuple[str, ...] = (
    "food", "drink", "lodging", "cloth", "tools", "weapons", "armor", "medicine",
    "materials", "luxury", "transport", "fuel", "services", "knowledge", "magic", "misc",
)

SETTLEMENT_TYPES: tuple[str, ...] = (
    "city", "town", "village", "harbor", "station", "colony", "shipyard", "farm", "hamlet",
)

SEASONS: tuple[str, ...] = ("spring", "summer", "autumn", "winter")

POPULATION_BANDS: tuple[str, ...] = ("tiny", "small", "medium", "large")

# Words a record may carry for its population, mapped to the four bands this module works in.
BAND_TO_POPULATION: dict[str, str] = {
    "tiny": "tiny", "small": "small", "medium": "medium", "large": "large",
    "hamlet": "tiny", "village": "small", "town": "medium",
    "city": "large", "large_city": "large", "metropolis": "large",
}
# The world_scale.population_band words; settlement_size_for_band knows exactly these.
WORLD_BAND_WORDS: tuple[str, ...] = ("hamlet", "village", "town", "city", "large_city", "metropolis")

SIZE_BY_POPULATION: dict[str, str] = {"tiny": "hamlet", "small": "village", "medium": "town", "large": "city"}

POPULATION_FACTOR: dict[str, float] = {"tiny": 1.0, "small": 3.0, "medium": 10.0, "large": 30.0}

# When a record carries no population word, its type says how many people live there.
TYPE_TO_POPULATION: dict[str, str] = {
    "city": "large", "colony": "large", "shipyard": "large",
    "town": "medium", "harbor": "medium", "station": "medium",
    "village": "small",
    "farm": "tiny", "hamlet": "tiny",
}

# Consumption per day in abstract units, before the population factor.
CONSUMPTION_BASE: dict[str, float] = {
    "food": 1.00, "drink": 0.80, "lodging": 0.30, "cloth": 0.25,
    "tools": 0.20, "weapons": 0.08, "armor": 0.05, "medicine": 0.15,
    "materials": 0.30, "luxury": 0.05, "transport": 0.10, "fuel": 0.60,
    "services": 0.40, "knowledge": 0.05, "magic": 0.03, "misc": 0.20,
}

# Production as a share of consumption (1.0 = self-sufficient). A category missing from a row is 0.9.
PRODUCTION_DEFAULT = 0.9
_PRODUCTION_COLUMNS: tuple[str, ...] = (
    "food", "drink", "lodging", "cloth", "tools", "weapons", "armor", "medicine",
    "materials", "luxury", "transport", "fuel", "services", "knowledge", "magic",
)
_PRODUCTION_ROWS: dict[str, tuple[float, ...]] = {
    "farm":    (2.0, 1.2, 0.5, 0.6, 0.4, 0.1, 0.0, 0.5, 1.3, 0.0, 0.6, 1.5, 0.5, 0.0, 0.0),
    "village": (1.4, 1.1, 0.9, 0.8, 0.8, 0.5, 0.2, 0.7, 1.2, 0.2, 0.8, 1.3, 0.9, 0.2, 0.3),
    "town":    (1.0, 1.0, 1.1, 1.1, 1.2, 1.0, 0.8, 1.0, 1.0, 0.8, 1.0, 1.0, 1.1, 0.8, 0.8),
    "city":    (0.6, 0.9, 1.3, 1.3, 1.4, 1.3, 1.3, 1.3, 0.8, 1.6, 1.2, 0.7, 1.3, 1.5, 1.3),
    "harbor":  (1.2, 1.0, 1.2, 1.0, 1.0, 0.9, 0.7, 0.9, 1.1, 1.2, 1.8, 0.9, 1.1, 0.9, 0.7),
    "station": (0.5, 0.8, 1.1, 0.9, 1.5, 1.0, 1.0, 1.2, 0.9, 0.6, 1.5, 1.2, 1.2, 1.4, 0.5),
}
PRODUCTION_PROFILE: dict[str, dict[str, float]] = {
    key: dict(zip(_PRODUCTION_COLUMNS, values)) for key, values in _PRODUCTION_ROWS.items()
}
# Which production row a settlement type uses; an unknown type falls back to its size row.
PRODUCTION_KEY_BY_TYPE: dict[str, str] = {
    "farm": "farm", "hamlet": "farm", "village": "village", "town": "town", "city": "city",
    "harbor": "harbor", "shipyard": "harbor", "station": "station", "colony": "station",
}
PRODUCTION_KEY_BY_SIZE: dict[str, str] = {"hamlet": "farm", "village": "village", "town": "town", "city": "city"}

# Venue kind -> the goods categories that kind sells. Keys are venues.VENUE_KINDS ids. This is the one
# copy in the repo; app.trade imports it.
VENUE_CATEGORIES: dict[str, tuple[str, ...]] = {
    "inn": ("lodging", "food", "drink"),
    "tavern": ("food", "drink"),
    "bar": ("food", "drink"),
    "diner": ("food", "drink"),
    "bakery": ("food",),
    "butcher": ("food",),
    "general_store": ("food", "tools", "cloth", "fuel", "misc"),
    "smithy": ("weapons", "tools", "materials", "services"),
    "armorer": ("armor", "weapons", "services"),
    "tailor": ("cloth", "materials", "services"),
    "tanner": ("cloth", "materials", "services"),
    "apothecary": ("medicine", "services"),
    "pharmacy": ("medicine", "services"),
    "clinic": ("medicine", "services"),
    "alchemist": ("medicine", "services"),
    "carpenter": ("materials", "tools", "services"),
    "mill": ("materials", "tools", "services"),
    "stable": ("transport", "services", "fuel"),
    "garage": ("transport", "services", "fuel"),
    "scribe": ("knowledge", "services"),
    "library": ("knowledge", "services"),
    "jeweller": ("luxury",),
    "market_hall": ("food", "cloth", "tools", "luxury", "materials"),
    "salvage_yard": ("materials", "tools", "misc"),
    "temple": ("services",),
    "shrine": ("services",),
    "bathhouse": ("services",),
    "laundromat": ("services",),
    "counting_house": (),
    "guild_hall": (),
    "guardhouse": (),
    "well": (),
}

# Season effect on demand and price per category; a category missing from a row is 1.0.
SEASON_EFFECTS: dict[str, dict[str, float]] = {
    "spring": {"food": 1.10, "drink": 1.00, "lodging": 1.00, "cloth": 0.95, "fuel": 0.90,
               "medicine": 1.10, "transport": 1.00, "materials": 1.05},
    "summer": {"food": 0.90, "drink": 1.15, "lodging": 1.10, "cloth": 0.90, "fuel": 0.70,
               "medicine": 1.00, "transport": 1.10, "materials": 1.00},
    "autumn": {"food": 0.85, "drink": 1.00, "lodging": 1.00, "cloth": 1.05, "fuel": 1.00,
               "medicine": 1.00, "transport": 1.00, "materials": 1.00},
    "winter": {"food": 1.25, "drink": 1.00, "lodging": 1.15, "cloth": 1.20, "fuel": 1.40,
               "medicine": 1.20, "transport": 1.20, "materials": 0.95},
}

# Weather nudges added to the scarcity term, by world weather kind.
WEATHER_NUDGE: dict[str, dict[str, float]] = {
    "storm": {"transport": 0.15, "fuel": 0.10, "lodging": 0.10},
    "snow": {"transport": 0.15, "fuel": 0.10, "lodging": 0.10},
    "fog": {"transport": 0.05},
}

# Scarcity events. "categories" () means every category. "min_size" is the smallest settlement size
# the event can happen in (None = anywhere). "weight" is the pick weight once an event fires.
SCARCITY_EVENTS: dict[str, dict[str, Any]] = {
    "blight": {"categories": ("food",), "price_delta": 0.60, "duration": (20, 40), "import_block": True,
               "weight": 3, "min_size": None, "news": "A blight has taken the grain around {name}."},
    "drought": {"categories": ("food", "drink"), "price_delta": 0.40, "duration": (15, 30), "import_block": True,
                "weight": 2, "min_size": None, "news": "The wells run low at {name}."},
    "road_bandits": {"categories": (), "price_delta": 0.25, "duration": (5, 15), "import_block": True,
                     "weight": 3, "min_size": None, "news": "Bandits on the roads: little comes in to {name}."},
    "plague": {"categories": ("medicine",), "price_delta": 0.90, "duration": (10, 25), "import_block": False,
               "weight": 1, "min_size": "town", "news": "Sickness in {name}; physic is scarce."},
    "festival": {"categories": ("luxury", "lodging", "drink"), "price_delta": 0.30, "duration": (2, 5),
                 "import_block": False, "weight": 3, "min_size": "village",
                 "news": "{name} keeps a festival; beds and wine are dear."},
    "strike": {"categories": ("tools", "services"), "price_delta": 0.35, "duration": (5, 12), "import_block": False,
               "weight": 1, "min_size": None, "news": "The guilds of {name} have downed tools."},
    "glut": {"categories": ("food",), "price_delta": -0.35, "duration": (7, 14), "import_block": False,
             "weight": 3, "min_size": None, "news": "A fat harvest: grain is cheap in {name}."},
    "caravan": {"categories": ("luxury", "cloth", "knowledge"), "price_delta": -0.25, "duration": (3, 8),
                "import_block": False, "weight": 3, "min_size": None,
                "news": "A caravan has come to {name} with goods to sell."},
    "mine_find": {"categories": ("materials",), "price_delta": -0.30, "duration": (10, 20), "import_block": False,
                  "weight": 1, "min_size": None, "news": "A new seam near {name}: ore is cheap."},
    "war_levy": {"categories": ("weapons", "armor", "transport"), "price_delta": 0.50, "duration": (10, 30),
                 "import_block": True, "weight": 1, "min_size": "town",
                 "news": "A levy is raised at {name}; arms and horses are dear."},
}

# Flavour from the free-text playthrough_options.economy string; first substring hit wins.
FLAVOUR_MULT: tuple[tuple[tuple[str, ...], float], ...] = (
    (("scarce",), 1.15),
    (("barter",), 1.05),
    (("coin",), 0.95),
    (("guild",), 1.05),
    (("prosper", "rich", "wealth", "trade"), 0.90),
)
GUILD_STRIKE_WEIGHT_MULT = 2

DEFAULT_CONFIG: dict[str, Any] = {
    "season_days": 30,
    "first_season": "spring",
    "drift": 0.04,
    "elasticity": 0.5,
    "event_chance": 0.03,
    "enabled": True,
}
CONFIG_RANGES: dict[str, tuple[float, float]] = {
    "season_days": (7, 120),
    "drift": (0.0, 0.25),
    "elasticity": (0.1, 1.0),
    "event_chance": (0.0, 0.2),
}

# Words for market_lines: what the category is called in a world fact, and its verb.
CATEGORY_WORDS: dict[str, tuple[str, str]] = {
    "food": ("Grain", "is"), "drink": ("Drink", "is"), "lodging": ("A bed", "is"), "cloth": ("Cloth", "is"),
    "tools": ("Tools", "are"), "weapons": ("Arms", "are"), "armor": ("Armour", "is"), "medicine": ("Physic", "is"),
    "materials": ("Timber and ore", "are"), "luxury": ("Fine goods", "are"), "transport": ("Horses and passage", "are"),
    "fuel": ("Fuel", "is"), "services": ("Hired work", "is"), "knowledge": ("Books", "are"),
    "magic": ("Charms", "are"), "misc": ("Sundries", "are"),
}

_MARKET_STATE_SQL = """
CREATE TABLE IF NOT EXISTS market_state (
    settlement_id TEXT NOT NULL,
    category TEXT NOT NULL,
    stock REAL NOT NULL DEFAULT 5.0,
    demand REAL NOT NULL DEFAULT 1.0,
    production REAL NOT NULL DEFAULT 1.0,
    consumption REAL NOT NULL DEFAULT 1.0,
    price_mult REAL NOT NULL DEFAULT 1.0,
    updated_day INTEGER NOT NULL DEFAULT 1,
    seeded_day INTEGER NOT NULL DEFAULT 1,
    size TEXT NOT NULL DEFAULT 'village',
    type TEXT NOT NULL DEFAULT 'village',
    name TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (settlement_id, category)
)
"""
_MARKET_EVENTS_SQL = """
CREATE TABLE IF NOT EXISTS market_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    settlement_id TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL,
    strength REAL NOT NULL DEFAULT 1.0,
    start_day INTEGER NOT NULL,
    end_day INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    note TEXT NOT NULL DEFAULT ''
)
"""
_MARKET_EVENTS_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_market_events_settlement ON market_events(settlement_id, status)"
)

_MARKET_ROW_KEYS: tuple[str, ...] = (
    "settlement_id", "category", "stock", "demand", "production", "consumption",
    "price_mult", "updated_day", "seeded_day", "size", "type", "name",
)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def _text(value: Any) -> str:
    return str(value or "").strip().lower()


def _flag_value(value: Any, default: bool) -> bool:
    """The _setup_flag_enabled semantics: blank means default, common yes/no words are honoured."""
    if value is None or value == "":
        return default
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
        return default
    return bool(value)


def _option_text(options: dict | None, key: str) -> str:
    if not isinstance(options, dict):
        return ""
    return str(options.get(key) or "")


def _root_seed(conn: sqlite3.Connection, seed: int | None) -> int:
    """An explicit seed, else the campaign seed (which creates its settings row when absent)."""
    if seed is not None:
        return int(seed)
    return int(campaign_seed(conn))


def _check_category(category: str) -> str:
    cat = _text(category)
    if cat not in GOODS_CATEGORIES:
        raise ValueError(f"unknown goods category: {category!r}")
    return cat


def _check_day(day: Any) -> int:
    try:
        value = int(day)
    except (TypeError, ValueError):
        raise ValueError(f"day must be a positive integer, got {day!r}") from None
    if value < 1:
        raise ValueError(f"day must be a positive integer, got {day!r}")
    return value


def event_spec(kind: str) -> dict[str, Any] | None:
    """The SCARCITY_EVENTS row for a kind, or None."""
    return SCARCITY_EVENTS.get(_text(kind))


def event_categories(event: dict) -> set[str] | None:
    """The categories an event touches; None means every category (the '' row)."""
    raw = str(event.get("category") or "").strip()
    if not raw:
        return None
    return {part.strip() for part in raw.split(",") if part.strip()}


def event_matches(event: dict, category: str) -> bool:
    cats = event_categories(event)
    return cats is None or category in cats


def event_is_active(event: dict, day: int) -> bool:
    if _text(event.get("status") or "active") == "ended":
        return False
    try:
        return int(event.get("start_day") or 0) <= int(day) <= int(event.get("end_day") or 0)
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Schema and config
# ---------------------------------------------------------------------------


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create market_state and market_events when missing. Idempotent; no commit here."""
    conn.execute(_MARKET_STATE_SQL)
    conn.execute(_MARKET_EVENTS_SQL)
    conn.execute(_MARKET_EVENTS_INDEX_SQL)


def _normalize_config(raw: Any, *, strict: bool) -> dict[str, Any]:
    """Defaults filled in, unknown keys dropped. strict raises ValueError; otherwise bad values fall back."""
    source = raw if isinstance(raw, dict) else {}
    clean = dict(DEFAULT_CONFIG)
    for key, default in DEFAULT_CONFIG.items():
        if key not in source:
            continue
        value = source.get(key)
        if key == "enabled":
            clean[key] = _flag_value(value, bool(default))
            continue
        if key == "first_season":
            season = _text(value)
            if season in SEASONS:
                clean[key] = season
            elif strict:
                raise ValueError(f"first_season must be one of {SEASONS}, got {value!r}")
            continue
        low, high = CONFIG_RANGES[key]
        try:
            number = int(value) if key == "season_days" else float(value)
        except (TypeError, ValueError):
            if strict:
                raise ValueError(f"{key} must be a number, got {value!r}") from None
            continue
        if number < low or number > high:
            if strict:
                raise ValueError(f"{key} must be between {low} and {high}, got {value!r}")
            continue
        clean[key] = number
    return clean


def get_economy_config(conn: sqlite3.Connection) -> dict[str, Any]:
    """The economy_config settings row with defaults; bad JSON or bad values give the defaults."""
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (CONFIG_KEY,)).fetchone()
    stored: Any = {}
    if row and row["value"]:
        try:
            stored = json.loads(row["value"])
        except (TypeError, ValueError):
            stored = {}
    return _normalize_config(stored, strict=False)


def update_economy_config(conn: sqlite3.Connection, payload: dict) -> dict[str, Any]:
    """Partial update of the economy_config row; ranges are validated and ValueError names the field."""
    if not isinstance(payload, dict):
        raise ValueError("payload must be a dict")
    current = get_economy_config(conn)
    merged = dict(current)
    merged.update({key: payload[key] for key in DEFAULT_CONFIG if key in payload})
    clean = _normalize_config(merged, strict=True)
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (CONFIG_KEY, json.dumps(clean, ensure_ascii=True)),
    )
    return clean


# ---------------------------------------------------------------------------
# Pure: settlement profile, season, production and consumption
# ---------------------------------------------------------------------------


def population_factor(population_band: str) -> float:
    """tiny 1, small 3, medium 10, large 30; an unknown word counts as small."""
    return POPULATION_FACTOR.get(_text(population_band), POPULATION_FACTOR["small"])


def settlement_profile(meta: dict | None, location_row: dict | None = None) -> dict[str, Any]:
    """The SettlementRef for a settlements_meta row, a list_settlements row or a world city record.

    This is the one producer of that shape in the repo; settlement_visits delegates to it.
    """
    source = meta if isinstance(meta, dict) else {}
    settlement_id = str(source.get("id") or "").strip()
    name = str(source.get("name") or "").strip()
    type_word = _text(source.get("state") or source.get("class"))
    settlement_type = type_word if type_word in SETTLEMENT_TYPES else ""
    band_raw = _text(source.get("population_band") or source.get("band"))
    population_band = BAND_TO_POPULATION.get(band_raw) or TYPE_TO_POPULATION.get(settlement_type) or "small"
    size = SIZE_BY_POPULATION[population_band]
    if band_raw in WORLD_BAND_WORDS:
        size = settlement_size_for_band(band_raw)
    location_id = 0
    if isinstance(location_row, dict):
        try:
            location_id = int(location_row.get("id") or 0)
        except (TypeError, ValueError):
            location_id = 0
        stored_size = normalize_settlement_size(str(location_row.get("settlement_size") or ""))
        if stored_size in SIZE_BY_POPULATION.values():
            size = stored_size
    if not location_id:
        try:
            location_id = int(source.get("location_id") or 0)
        except (TypeError, ValueError):
            location_id = 0
    return {
        "settlement_id": settlement_id,
        "name": name,
        "size": size,
        "type": settlement_type,
        "band_raw": band_raw,
        "population_band": population_band,
        "population_factor": population_factor(population_band),
        "location_id": location_id,
    }


def season_for_day(day: int, *, season_days: int = 30, first_season: str = "spring") -> dict[str, Any]:
    """Which season a 1-based world day falls in, with its position inside the season and the year."""
    value = _check_day(day)
    length = int(season_days)
    if length < 1:
        raise ValueError(f"season_days must be at least 1, got {season_days!r}")
    first = _text(first_season)
    if first not in SEASONS:
        raise ValueError(f"unknown season: {first_season!r}")
    offset = SEASONS.index(first)
    index = ((value - 1) // length + offset) % len(SEASONS)
    day_in_season = (value - 1) % length + 1
    return {
        "season": SEASONS[index],
        "index": index,
        "day_in_season": day_in_season,
        "progress": (day_in_season - 1) / length,
        "year": (value - 1) // (len(SEASONS) * length) + 1,
    }


def season_effect(season: str, category: str) -> float:
    """SEASON_EFFECTS lookup; 1.0 when the table says nothing. Unknown season raises."""
    key = _text(season)
    if key not in SEASON_EFFECTS:
        raise ValueError(f"unknown season: {season!r}")
    return SEASON_EFFECTS[key].get(_text(category), 1.0)


def categories_for(options: dict | None) -> list[str]:
    """The goods categories a world has: every category, minus magic when the world has none."""
    magic = resolve_world_magic(
        _option_text(options, "magic_level"),
        _option_text(options, "world_style"),
        _option_text(options, "custom_style"),
    )
    if magic == "none":
        return [cat for cat in GOODS_CATEGORIES if cat != "magic"]
    return list(GOODS_CATEGORIES)


def _production_key(profile: dict) -> str:
    key = PRODUCTION_KEY_BY_TYPE.get(_text(profile.get("type")))
    if key:
        return key
    return PRODUCTION_KEY_BY_SIZE.get(_text(profile.get("size")), "village")


def consumption_for(profile: dict, category: str) -> float:
    """Units consumed per day: the population factor times the category base."""
    cat = _check_category(category)
    factor = float(profile.get("population_factor") or population_factor(str(profile.get("population_band") or "")))
    return factor * CONSUMPTION_BASE[cat]


def production_for(profile: dict, category: str, venue_kinds: list[str] | None = None) -> float:
    """Units produced per day: consumption times the type's profile share, plus 0.15 per venue kind selling it."""
    cat = _check_category(category)
    share = PRODUCTION_PROFILE[_production_key(profile)].get(cat, PRODUCTION_DEFAULT)
    kinds = {_text(kind) for kind in (venue_kinds or []) if _text(kind)}
    sellers = sum(1 for kind in kinds if cat in VENUE_CATEGORIES.get(kind, ()))
    return consumption_for(profile, cat) * (share + VENUE_PRODUCTION_BONUS * sellers)


def initial_rows(
    profile: dict,
    *,
    day: int,
    seed: int,
    categories: list[str] | None = None,
    venue_kinds: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Fresh market rows at equilibrium stock, with demand nudged by up to ten percent from the seed."""
    value = _check_day(day)
    settlement_id = str(profile.get("settlement_id") or "")
    rows: list[dict[str, Any]] = []
    for category in (categories if categories is not None else GOODS_CATEGORIES):
        cat = _check_category(category)
        consumption = consumption_for(profile, cat)
        nudge = rng_for("economy_seed", turn=value, seed=int(seed), salt=f"{settlement_id}:{cat}").random()
        demand = consumption * (1.0 + SEED_DEMAND_NUDGE * (nudge - 0.5) * 2.0)
        rows.append(
            {
                "settlement_id": settlement_id,
                "category": cat,
                "stock": EQUILIBRIUM_DAYS,
                "demand": demand,
                "production": production_for(profile, cat, venue_kinds),
                "consumption": consumption,
                "price_mult": 1.0,
                "updated_day": value,
                "seeded_day": value,
                "size": str(profile.get("size") or "village"),
                "type": str(profile.get("type") or profile.get("size") or "village"),
                "name": str(profile.get("name") or ""),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Pure: chance, drift, flavour
# ---------------------------------------------------------------------------


def flavour_multiplier(economy_option: str) -> float:
    """The FLAVOUR_MULT table over the free-text economy option; 1.0 when nothing matches."""
    text = _text(economy_option)
    if not text:
        return 1.0
    for words, mult in FLAVOUR_MULT:
        if any(word in text for word in words):
            return mult
    return 1.0


def drift_multiplier(settlement_id: str, category: str, *, day: int, seed: int, drift: float = 0.04) -> float:
    """1 plus or minus drift, fixed for a seed, day, settlement and category."""
    value = _check_day(day)
    roll = rng_for("economy_drift", turn=value, seed=int(seed), salt=f"{settlement_id}:{category}").random()
    return 1.0 + float(drift) * (roll - 0.5) * 2.0


def roll_scarcity(
    profile: dict,
    *,
    day: int,
    seed: int,
    active: list[dict],
    event_chance: float = 0.03,
    flavour: str = "",
) -> dict[str, Any] | None:
    """One roll per settlement per day for a new scarcity event; None most days.

    At most MAX_ACTIVE_EVENTS run at once, a kind already running is not started again, plague and
    war_levy need a town or larger, a festival a village or larger. A guild flavour doubles the strike weight.
    """
    value = _check_day(day)
    settlement_id = str(profile.get("settlement_id") or "")
    rng = rng_for("economy_event", turn=value, seed=int(seed), salt=settlement_id)
    if rng.random() >= float(event_chance):
        return None
    running = [event for event in active if event_is_active(event, value)]
    if len(running) >= MAX_ACTIVE_EVENTS:
        return None
    running_kinds = {_text(event.get("kind")) for event in running}
    size = str(profile.get("size") or "village")
    guild = "guild" in _text(flavour)
    kinds: list[str] = []
    weights: list[int] = []
    for kind, spec in SCARCITY_EVENTS.items():
        if kind in running_kinds:
            continue
        min_size = spec.get("min_size")
        if min_size and size_rank(size) < size_rank(min_size):
            continue
        weight = int(spec["weight"])
        if kind == "strike" and guild:
            weight *= GUILD_STRIKE_WEIGHT_MULT
        kinds.append(kind)
        weights.append(weight)
    if not kinds:
        return None
    kind = rng.choices(kinds, weights=weights, k=1)[0]
    spec = SCARCITY_EVENTS[kind]
    low, high = spec["duration"]
    duration = rng.randint(int(low), int(high))
    strength = rng.uniform(*STRENGTH_RANGE)
    name = str(profile.get("name") or "").strip() or "the settlement"
    return {
        "id": 0,
        "settlement_id": settlement_id,
        "kind": kind,
        "category": ",".join(spec["categories"]),
        "strength": round(strength, 3),
        "start_day": value,
        "end_day": value + duration,
        "status": "active",
        "label": kind.replace("_", " "),
        "news": str(spec["news"]).format(name=name),
    }


# ---------------------------------------------------------------------------
# Pure: the multiplier and the day step
# ---------------------------------------------------------------------------


def neutral_multiplier(settlement_id: str, category: str, *, day: int, reason: str, season: str = "") -> dict[str, Any]:
    """A PriceMultiplier of 1.0 with every part 1.0 and the given reason."""
    return {
        "settlement_id": str(settlement_id or ""),
        "category": str(category or ""),
        "day": int(day),
        "mult": 1.0,
        "supply": 1.0,
        "demand": 1.0,
        "season": str(season or ""),
        "season_mult": 1.0,
        "scarcity_mult": 1.0,
        "drift_mult": 1.0,
        "flavour_mult": 1.0,
        "events": [],
        "reason": str(reason or "ok"),
    }


def price_multiplier(
    row: dict,
    *,
    events: list[dict],
    season: dict,
    day: int,
    seed: int,
    flavour_mult: float = 1.0,
    weather_kind: str = "",
    elasticity: float = 0.5,
    drift: float = 0.04,
) -> dict[str, Any]:
    """The PriceMultiplier for one market row on one day."""
    value = _check_day(day)
    cat = _check_category(str(row.get("category") or ""))
    settlement_id = str(row.get("settlement_id") or "")
    season_name = _text(season.get("season") if isinstance(season, dict) else season)
    if season_name not in SEASONS:
        raise ValueError(f"unknown season: {season_name!r}")
    if cat == "misc":
        return neutral_multiplier(settlement_id, cat, day=value, reason="ok", season=season_name)
    s_mult = season_effect(season_name, cat)
    consumption = max(float(row.get("consumption") or 0.0), 1e-6)
    demand_now = float(row.get("demand") or consumption) * s_mult
    supply_ratio = _clamp(float(row.get("stock") or EQUILIBRIUM_DAYS) / EQUILIBRIUM_DAYS, 0.1, 4.0)
    base = (demand_now / consumption / supply_ratio) ** float(elasticity)
    matched: list[str] = []
    scarcity = 1.0
    for event in events or []:
        if not event_is_active(event, value) or not event_matches(event, cat):
            continue
        spec = event_spec(str(event.get("kind") or ""))
        if not spec:
            continue
        scarcity += float(spec["price_delta"]) * float(event.get("strength") or 1.0)
        matched.append(str(event.get("kind")))
    nudge = WEATHER_NUDGE.get(_text(weather_kind), {}).get(cat, 0.0)
    if nudge:
        scarcity += nudge
        matched.append(f"weather:{_text(weather_kind)}")
    scarcity = max(scarcity, 0.1)
    d_mult = drift_multiplier(settlement_id, cat, day=value, seed=seed, drift=drift)
    mult = _clamp(base * s_mult * scarcity * d_mult * float(flavour_mult), MULT_MIN, MULT_MAX)
    return {
        "settlement_id": settlement_id,
        "category": cat,
        "day": value,
        "mult": round(mult, 4),
        "supply": round(supply_ratio, 4),
        "demand": round(demand_now / consumption, 4),
        "season": season_name,
        "season_mult": s_mult,
        "scarcity_mult": round(scarcity, 4),
        "drift_mult": round(d_mult, 4),
        "flavour_mult": float(flavour_mult),
        "events": matched,
        "reason": "ok",
    }


def advance_market_row(row: dict, *, season: dict, events: list[dict], day: int) -> dict[str, Any]:
    """One day of stock dynamics; returns a new row with stock and updated_day changed.

    Stock is kept in days of consumption, so the day's net is (production - consumption x season
    demand - trade drain) / consumption. Roads pull the stock toward EQUILIBRIUM_DAYS unless an active
    import-blocking event touches the category. Trade drain is 0 in this pass.
    """
    value = _check_day(day)
    cat = _check_category(str(row.get("category") or ""))
    season_name = _text(season.get("season") if isinstance(season, dict) else season)
    s_demand = season_effect(season_name, cat)
    consumption = max(float(row.get("consumption") or 0.0), 1e-6)
    production = float(row.get("production") or 0.0)
    trade_drain = 0.0
    net_days = (production - consumption * s_demand - trade_drain) / consumption
    stock = _clamp(float(row.get("stock") or EQUILIBRIUM_DAYS) + net_days, STOCK_MIN, STOCK_MAX)
    import_block = False
    for event in events or []:
        if not event_is_active(event, value) or not event_matches(event, cat):
            continue
        spec = event_spec(str(event.get("kind") or ""))
        if spec and spec["import_block"]:
            import_block = True
            break
    if not import_block:
        stock = _clamp(stock + (EQUILIBRIUM_DAYS - stock) * IMPORT_PULL, STOCK_MIN, STOCK_MAX)
    new_row = dict(row)
    new_row["stock"] = round(stock, 6)
    new_row["updated_day"] = value
    return new_row


def event_proposal(event: dict) -> dict[str, Any]:
    """The WorldEventProposal for a scarcity event: queue_world_event's keyword arguments."""
    kind = str(event.get("kind") or "")
    return {
        "kind": "custom",
        "summary": str(event.get("news") or ""),
        "trigger": f"economy:{kind}",
        "due_turn": None,
        "force": False,
        "priority": 4,
        "payload": {
            "economy_event": kind,
            "settlement_id": str(event.get("settlement_id") or ""),
            "category": str(event.get("category") or ""),
            "start_day": int(event.get("start_day") or 0),
            "end_day": int(event.get("end_day") or 0),
        },
    }


def tick_day_proposal(
    rows: list[dict],
    events: list[dict],
    *,
    profile: dict,
    from_day: int,
    to_day: int,
    seed: int,
    config: dict | None = None,
    flavour: str = "",
    weather_kind: str = "",
) -> dict[str, Any]:
    """Advance one settlement's rows and events from from_day to to_day, pure.

    Returns {"rows", "events", "new_events", "multipliers", "lines", "event_proposals"}. When to_day is
    not after from_day nothing changes and the lists are empty.
    """
    cfg = _normalize_config(config, strict=False)
    rows_now = [dict(row) for row in rows]
    events_now = [dict(event) for event in events]
    if int(to_day) <= int(from_day):
        return {
            "rows": rows_now,
            "events": events_now,
            "new_events": [],
            "multipliers": {},
            "lines": [],
            "event_proposals": [],
        }
    new_events: list[dict[str, Any]] = []
    season: dict[str, Any] = season_for_day(max(1, int(from_day)), season_days=cfg["season_days"], first_season=cfg["first_season"])
    for day in range(int(from_day) + 1, int(to_day) + 1):
        season = season_for_day(day, season_days=cfg["season_days"], first_season=cfg["first_season"])
        for event in events_now:
            if _text(event.get("status") or "active") != "ended" and int(event.get("end_day") or 0) < day:
                event["status"] = "ended"
        active = [event for event in events_now if event_is_active(event, day)]
        started = roll_scarcity(
            profile, day=day, seed=seed, active=active, event_chance=cfg["event_chance"], flavour=flavour
        )
        if started is not None:
            events_now.append(started)
            new_events.append(started)
            active.append(started)
        rows_now = [advance_market_row(row, season=season, events=active, day=day) for row in rows_now]
    active = [event for event in events_now if event_is_active(event, int(to_day))]
    f_mult = flavour_multiplier(flavour)
    multipliers: dict[str, dict[str, Any]] = {}
    for row in rows_now:
        mult = price_multiplier(
            row,
            events=active,
            season=season,
            day=int(to_day),
            seed=seed,
            flavour_mult=f_mult,
            weather_kind=weather_kind,
            elasticity=cfg["elasticity"],
            drift=cfg["drift"],
        )
        row["price_mult"] = mult["mult"]
        multipliers[row["category"]] = mult
    return {
        "rows": rows_now,
        "events": events_now,
        "new_events": new_events,
        "multipliers": multipliers,
        "lines": market_lines(multipliers, profile),
        "event_proposals": [event_proposal(event) for event in new_events],
    }


def market_lines(multipliers: dict[str, dict], profile: dict, *, limit: int = 2) -> list[str]:
    """World facts for the largest price deviations (mult >= 1.25 or <= 0.8); [] when all is near 1."""
    name = str(profile.get("name") or "").strip() or "the market"
    picks: list[tuple[float, str, dict]] = []
    for category, mult in (multipliers or {}).items():
        if not isinstance(mult, dict) or mult.get("reason", "ok") != "ok":
            continue
        value = float(mult.get("mult") or 1.0)
        if value >= LINE_HIGH or value <= LINE_LOW:
            picks.append((abs(value - 1.0), str(category), mult))
    picks.sort(key=lambda item: (-item[0], item[1]))
    lines: list[str] = []
    for _, category, mult in picks[: max(0, int(limit))]:
        word, verb = CATEGORY_WORDS.get(category, (category.capitalize(), "is"))
        tone = "dear" if float(mult["mult"]) > 1.0 else "cheap"
        season = str(mult.get("season") or "").strip()
        when = f" this {season}" if season else ""
        reasons = [str(kind).replace("weather:", "").replace("_", " ") for kind in mult.get("events") or []]
        suffix = f" ({', '.join(reasons)})" if reasons else ""
        lines.append(f"{word} {verb} {tone} in {name}{when}{suffix}.")
    return lines


# ---------------------------------------------------------------------------
# Writers (conn passed in; the caller's transaction commits)
# ---------------------------------------------------------------------------


def _rows_for(conn: sqlite3.Connection, settlement_id: str) -> list[dict[str, Any]]:
    cur = conn.execute(
        "SELECT * FROM market_state WHERE settlement_id = ? ORDER BY category", (str(settlement_id),)
    )
    return [dict(row) for row in cur.fetchall()]


def _events_for(conn: sqlite3.Connection, settlement_id: str, *, status: str = "active") -> list[dict[str, Any]]:
    cur = conn.execute(
        "SELECT * FROM market_events WHERE settlement_id = ? AND status = ? ORDER BY id",
        (str(settlement_id), str(status)),
    )
    return [dict(row) for row in cur.fetchall()]


def _write_rows(conn: sqlite3.Connection, rows: list[dict]) -> None:
    for row in rows:
        conn.execute(
            """
            INSERT OR REPLACE INTO market_state
                (settlement_id, category, stock, demand, production, consumption, price_mult,
                 updated_day, seeded_day, size, type, name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tuple(row.get(key) for key in _MARKET_ROW_KEYS),
        )


def _write_events(conn: sqlite3.Connection, events: list[dict]) -> None:
    for event in events:
        event_id = int(event.get("id") or 0)
        if event_id:
            conn.execute(
                "UPDATE market_events SET status = ? WHERE id = ?",
                (str(event.get("status") or "active"), event_id),
            )
            continue
        cur = conn.execute(
            """
            INSERT INTO market_events (settlement_id, category, kind, strength, start_day, end_day, status, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(event.get("settlement_id") or ""),
                str(event.get("category") or ""),
                str(event.get("kind") or ""),
                float(event.get("strength") or 1.0),
                int(event.get("start_day") or 0),
                int(event.get("end_day") or 0),
                str(event.get("status") or "active"),
                str(event.get("news") or event.get("note") or ""),
            ),
        )
        event["id"] = int(cur.lastrowid or 0)


def ensure_settlement(
    conn: sqlite3.Connection,
    meta: dict,
    *,
    day: int,
    seed: int | None = None,
    options: dict | None = None,
    venue_kinds: list[str] | None = None,
    location_row: dict | None = None,
) -> list[dict[str, Any]]:
    """Insert the settlement's market rows when missing (INSERT OR IGNORE); returns the rows now stored."""
    ensure_schema(conn)
    value = _check_day(day)
    profile = settlement_profile(meta, location_row)
    if not profile["settlement_id"]:
        return []
    root = _root_seed(conn, seed)
    rows = initial_rows(
        profile, day=value, seed=root, categories=categories_for(options), venue_kinds=venue_kinds
    )
    for row in rows:
        conn.execute(
            """
            INSERT OR IGNORE INTO market_state
                (settlement_id, category, stock, demand, production, consumption, price_mult,
                 updated_day, seeded_day, size, type, name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tuple(row.get(key) for key in _MARKET_ROW_KEYS),
        )
    return _rows_for(conn, profile["settlement_id"])


def tick_day(
    conn: sqlite3.Connection,
    *,
    from_day: int,
    to_day: int,
    settlements: list[dict],
    options: dict | None = None,
    seed: int | None = None,
    weather_kind: str = "",
) -> dict[str, Any]:
    """Advance every given settlement's market from from_day to to_day and store the result.

    Returns {"ticked", "days", "new_events", "lines", "event_proposals"}. to_day <= from_day is a no-op,
    and so is a config row with enabled false ("disabled": True in the result).
    """
    empty = {"ticked": 0, "days": 0, "new_events": [], "lines": [], "event_proposals": []}
    if int(to_day) <= int(from_day):
        return dict(empty)
    ensure_schema(conn)
    config = get_economy_config(conn)
    if not config.get("enabled", True):
        return {**empty, "disabled": True}
    root = _root_seed(conn, seed)
    flavour = _option_text(options, "economy")
    out: dict[str, Any] = {
        "ticked": 0,
        "days": int(to_day) - int(from_day),
        "new_events": [],
        "lines": [],
        "event_proposals": [],
    }
    for meta in settlements or []:
        profile = settlement_profile(meta)
        if not profile["settlement_id"]:
            continue
        rows = ensure_settlement(conn, meta, day=max(1, int(from_day)), seed=root, options=options)
        if not rows:
            continue
        events = _events_for(conn, profile["settlement_id"], status="active")
        proposal = tick_day_proposal(
            rows,
            events,
            profile=profile,
            from_day=int(from_day),
            to_day=int(to_day),
            seed=root,
            config=config,
            flavour=flavour,
            weather_kind=weather_kind,
        )
        _write_rows(conn, proposal["rows"])
        _write_events(conn, proposal["events"])
        out["ticked"] += 1
        out["new_events"].extend(proposal["new_events"])
        out["lines"].extend(proposal["lines"])
        out["event_proposals"].extend(proposal["event_proposals"])
    return out


def active_events(conn: sqlite3.Connection, settlement_id: str, *, day: int) -> list[dict[str, Any]]:
    """The market_events rows active on the given day for one settlement."""
    ensure_schema(conn)
    value = _check_day(day)
    cur = conn.execute(
        """
        SELECT * FROM market_events
        WHERE settlement_id = ? AND status = 'active' AND start_day <= ? AND end_day >= ?
        ORDER BY id
        """,
        (str(settlement_id), value, value),
    )
    return [dict(row) for row in cur.fetchall()]


def settlement_multiplier(
    conn: sqlite3.Connection,
    settlement_id: str,
    category: str,
    *,
    day: int,
    options: dict | None = None,
    seed: int | None = None,
    weather_kind: str = "",
) -> dict[str, Any]:
    """The PriceMultiplier for one settlement and category; never raises for an unknown id or category."""
    ensure_schema(conn)
    value = _check_day(day)
    cat = _text(category)
    config = get_economy_config(conn)
    season = season_for_day(value, season_days=config["season_days"], first_season=config["first_season"])
    if cat not in GOODS_CATEGORIES:
        return neutral_multiplier(settlement_id, category, day=value, reason="unknown_category", season=season["season"])
    if not config.get("enabled", True):
        return neutral_multiplier(settlement_id, cat, day=value, reason="disabled", season=season["season"])
    row = conn.execute(
        "SELECT * FROM market_state WHERE settlement_id = ? AND category = ?", (str(settlement_id), cat)
    ).fetchone()
    if not row:
        return neutral_multiplier(settlement_id, cat, day=value, reason="unknown_settlement", season=season["season"])
    return price_multiplier(
        dict(row),
        events=active_events(conn, settlement_id, day=value),
        season=season,
        day=value,
        seed=_root_seed(conn, seed),
        flavour_mult=flavour_multiplier(_option_text(options, "economy")),
        weather_kind=weather_kind,
        elasticity=config["elasticity"],
        drift=config["drift"],
    )


def market_snapshot(
    conn: sqlite3.Connection,
    settlement_id: str,
    *,
    day: int,
    options: dict | None = None,
    seed: int | None = None,
    weather_kind: str = "",
) -> dict[str, Any]:
    """{"settlement_id", "rows", "events", "multipliers"} for a Tools view; empty lists for an unknown id."""
    ensure_schema(conn)
    value = _check_day(day)
    rows = _rows_for(conn, settlement_id)
    events = active_events(conn, settlement_id, day=value)
    multipliers: dict[str, dict[str, Any]] = {}
    if rows:
        config = get_economy_config(conn)
        season = season_for_day(value, season_days=config["season_days"], first_season=config["first_season"])
        root = _root_seed(conn, seed)
        f_mult = flavour_multiplier(_option_text(options, "economy"))
        for row in rows:
            multipliers[row["category"]] = price_multiplier(
                row,
                events=events,
                season=season,
                day=value,
                seed=root,
                flavour_mult=f_mult,
                weather_kind=weather_kind,
                elasticity=config["elasticity"],
                drift=config["drift"],
            )
    return {
        "settlement_id": str(settlement_id or ""),
        "rows": rows,
        "events": events,
        "multipliers": multipliers,
    }
