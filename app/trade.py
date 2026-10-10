"""Price ledger, settlement prices, trade offers and haggling.

Status: built, not wired (TODO n15).

The first time an item is priced the engine records it in price_ledger and price_index; later sales of
the same item in the same settlement start from that first price, other settlements start from the
running average, and both are moved by app.economy's per-settlement multiplier. A purchase becomes a
trade_offers row (status offered) that only accept_offer() turns into a purse and inventory proposal;
haggling and alternatives are pure functions over the offer, the keeper's npcs row, the relationship
summary and a skill check result. Every amount is an int of the active currency set's smallest unit
(app.currency). The module writes only its own three tables and no settings row of its own; a seed=None
default on settlement_price, run_haggle or alternatives_for lets app.economy fall back to the campaign seed,
which creates the campaign_rng_seed settings row once when it is absent. Nothing here moves gold or items,
inserts a journal line or touches the player, inventory, npcs or quests: fulfilment_proposal() returns the
changes and the wiring pass applies them. The live game does not call anything in this file.

Wiring (not done):
  app/world.py:apply_turn() -> between the gold_note = _settle_stated_gold(result, player_input) line and the
      resolve_turn_bands(...) call: trade.record_turn_prices(conn, result=result, narration=_narration_text(result),
      gold_note=gold_note, seller=seller, turn=turn, day=day, cset=cset) and, when the prose names no price,
      trade.settlement_price(conn, name, settlement_id, day=day, cset=cset) for the GOLD op's amount. Only conn,
      result, gold_note and turn are locals there; the hook adds cset = currency.active_set(conn),
      day = get_world_time(conn)["day"] and seller = {"settlement_id", "location_id", "npc_id"} built from the
      scene keeper (the npcs row the purchase names, or None when there is no keeper).
  app/world.py:_settle_purse() -> instead of applying a named purchase: trade.open_offer(conn, trade.make_offer(
      kind="buy", item_name=..., quantity=..., unit_price=..., cset=currency.active_set(conn), seller_npc_id=...,
      location_id=..., settlement_id=..., turn=_turn_value(conn))) and park result["player"]["gold_delta"] = 0 with
      gold_note["source"] = "offer_parked". That function has no turn or cset local; it already calls _turn_value(conn)
      for its journal line.
  app/world.py:get_state() -> beside state["open_quest_offers"]: state["open_trade_offers"] =
      trade.state_view(conn, cset=currency.active_set(conn))["open_trade_offers"].
  app/main.py:_answer_offer() -> the same shape for POST /api/trade/{id}/accept|decline|haggle|alternatives through
      trade.accept_offer / trade.decline_offer / trade.run_haggle / trade.alternatives_for, 409 when the helper returns None.
  app/world.py:apply_turn() -> beside the apply_turn_intel(conn, player_input, turn) call: answer =
      trade.answer_from_line(trade.open_offers(conn), player_input, cset=cset) and the accept / decline / run_haggle call it names.
  app/world.py:_apply_turn_npc_relationship_deltas() -> for a HaggleResult with relationship_event:
      relationships.update_relationship(conn, npc_id, reason="haggle", **RELATIONSHIP_EVENTS[result["relationship_event"]]).
  app/world.py:_apply_inventory() and _apply_player() -> fulfilment_proposal(offer, cset=cset): its inventory_changes go to
      _apply_inventory(conn, changes) and its gold_delta_legacy to result["player"]["gold_delta"]; then trade.mark_settled(conn, id, turn=turn).
  app/world.py:apply_turn() -> after the SELECT current_location_id FROM player WHERE id = 1 that sets _cur_loc_id
      (there is no player object in apply_turn): trade.expire_stale(conn, turn=turn, location_id=_cur_loc_id).

Turn on:
  [ ] playthrough_options.trade_offers_enabled (default off) gates all of it; read by the wiring, never here
  [ ] app/db.py:_migrate_columns(): try: from app.trade import ensure_schema; ensure_schema(conn) except Exception: pass
  [ ] app/world.py:WORLD_TABLES and RESTORE_ORDER gain price_ledger, price_index, trade_offers; AUTOINC_TABLES gains
      price_ledger and trade_offers; price_index (text key) joins _REPLACE_ONLY_WHEN_EXPORTED and the two quest_clocks
      snapshot sites in _save_snapshot and _restore_snapshot_rows; _clear_playthrough deletes from all three
  [ ] routes: POST /api/trade/{id}/accept, /decline, /haggle, /alternatives on the _answer_offer pattern
  [ ] UI: an offer strip in the renderOfferPrompt style with Accept / Refuse / Haggle / Other options cards
  [ ] prompt: one line in the DSL user prompt listing open trade offers; "a price only offered is not paid" is already there for GOLD

Tests: tests/test_trade.py
"""
from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from app import currency, economy
from app.local_intel import typed_offer_choice
from app.prose_state import strip_negated_clauses
from app.relationships import affinity_band, get_relationship_summary
from app.skill_checks import OUTCOME_RANK, resolve_check
from app.venues import normalize_kind

# ---------------------------------------------------------------------------
# Constants and rules tables (data)
# ---------------------------------------------------------------------------

OFFER_STATES: tuple[str, ...] = ("offered", "countered", "accepted", "declined", "refused", "expired", "settled")
OPEN_STATES: tuple[str, ...] = ("offered", "countered")
OFFER_KINDS: tuple[str, ...] = ("buy", "sell", "service", "barter")

OFFER_TTL_TURNS = 3
MAX_OPEN_OFFERS = 4
MAX_ROUNDS = 2
TRUSTED_MAX_ROUNDS = 3
LOWBALL_FRACTION = 0.5
INSULT_RAISE = 0.10
COUNTER_STEP_MIN = 1
CRIT_SUCCESS_FLOOR_MULT = 0.95

# A sample this far from the running average (after OUTLIER_MIN_SAMPLES samples) is kept in the ledger
# but does not move the index.
OUTLIER_RANGE: tuple[float, float] = (0.2, 5.0)
OUTLIER_MIN_SAMPLES = 3

MAX_ITEM_NAME = 100
MAX_ITEM_KEY = 60
MAX_LEDGER_ROWS = 20
STATE_VIEW_LIMIT = 8
MAX_ALTERNATIVES = 3

# Phrases that fold onto one item key, first match wins. Applied to the normalised name (lower case, tags
# and leading articles gone).
ITEM_ALIASES: tuple[tuple[str, str], ...] = (
    (r"night'?s? (?:lodging|stay|room)|room for the night|(?:a )?bed for the night|bed and board", "lodging:night"),
    (r"(?:bowl|plate) of (?:stew|soup|pottage)|hot meal|\bmeal\b", "meal"),
    (r"loaf of bread|\bloaf\b|\bbread\b", "bread"),
    (r"wedge of cheese|\bcheese\b", "cheese"),
    (r"(?:mug|pint|tankard) of (?:ale|beer)|\bale\b|\bbeer\b", "ale"),
    (r"(?:cup|glass) of wine|\bwine\b", "wine"),
    (r"(?:length|coil) of rope|\brope\b", "rope"),
    (r"\btorch(?:es)?\b", "torch"),
    (r"\barrows?\b", "arrow"),
    (r"(?:healing|health) (?:potion|draught)|potion of healing", "healing_potion"),
    (r"\bbandages?\b|linen strips?", "bandage"),
    (r"\bwaterskin\b|water skin", "waterskin"),
    (r"\b(?:trail )?rations?\b|travel food", "ration"),
    (r"\bpassage\b|\bferry\b|\btoll\b", "passage"),
)
_ITEM_ALIAS_RES: tuple[tuple[re.Pattern[str], str], ...] = tuple((re.compile(p), k) for p, k in ITEM_ALIASES)

# The category of each alias key; categorize() answers these before it reads any keyword.
KEY_CATEGORIES: dict[str, str] = {
    "lodging:night": "lodging", "meal": "food", "bread": "food", "cheese": "food", "ale": "drink",
    "wine": "drink", "rope": "tools", "torch": "tools", "arrow": "weapons", "healing_potion": "medicine",
    "bandage": "medicine", "waterskin": "tools", "ration": "food", "passage": "transport",
}

# An inventory item_type that names a category outright. "consumable" is food or drink by its words.
ITEM_TYPE_CATEGORIES: dict[str, str] = {
    "clothing": "cloth", "tool": "tools", "weapon": "weapons", "armor": "armor", "armour": "armor",
    "medical": "medicine", "food": "food", "drink": "drink",
}

# Name keywords per category, in the order categorize() prefers them: a two-word phrase ("lamp oil",
# "fuel cell") beats a single word, and among single words the first category in this table wins. Keys
# are economy.GOODS_CATEGORIES ids; misc has no words and is the fallback. "wine" is an alias key, so a
# fine wine is drink here, not luxury.
CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "food": ("bread", "loaf", "cheese", "meat", "stew", "soup", "meal", "ration", "fish", "fruit", "grain",
             "flour", "jerky", "egg", "apple", "honey"),
    "drink": ("ale", "beer", "wine", "mead", "water", "milk", "spirits", "cider", "coffee", "tea"),
    "lodging": ("lodging", "room", "bed", "stay", "night"),
    "cloth": ("cloak", "coat", "tunic", "boots", "shirt", "trousers", "dress", "wool", "linen", "hat",
              "gloves", "belt"),
    "tools": ("rope", "torch", "lantern", "hammer", "knife", "pick", "shovel", "saw", "nails", "flint", "kit",
              "lockpick", "needle"),
    "weapons": ("sword", "blade", "dagger", "bow", "arrow", "spear", "axe", "mace", "club", "pistol",
                "rifle", "blaster"),
    "armor": ("armor", "armour", "mail", "shield", "helm", "plate", "vest", "breastplate"),
    "medicine": ("potion", "salve", "bandage", "poultice", "tonic", "herb", "medkit", "stim", "antidote"),
    "materials": ("ore", "ingot", "iron", "steel", "leather", "hide", "timber", "plank", "stone", "coal",
                  "cloth bolt", "thread", "wire", "scrap"),
    "luxury": ("ring", "necklace", "gem", "jewel", "silk", "perfume", "spice", "rare book"),
    "transport": ("horse", "mule", "saddle", "cart", "wagon", "boat", "passage", "ferry", "fuel cell",
                  "ticket"),
    "fuel": ("firewood", "charcoal", "oil", "lamp oil", "fuel", "battery", "cell"),
    "services": ("repair", "mend", "sharpen", "forge", "guide", "lesson", "healing", "bath", "wash", "fee"),
    "knowledge": ("book", "scroll", "map", "chart", "tome", "letter", "data", "chip"),
    "magic": ("wand", "charm", "amulet", "rune", "spell scroll", "reagent", "focus", "crystal"),
}
_CATEGORY_RES: tuple[tuple[str, str, re.Pattern[str]], ...] = tuple(
    (category, word, re.compile(r"\b" + re.escape(word) + r"(?:e?s)?\b"))
    for category, words in CATEGORY_KEYWORDS.items()
    for word in words
)

# Reference prices in legacy gold (one old player.gold), fitted to today's prose where a loaf is "a couple
# of coins" and the player starts with 12. Only used when the ledger knows nothing for the key or category.
REFERENCE_GOLD: dict[str, dict[str, float]] = {
    "items": {
        "bread": 0.5, "cheese": 1.0, "meal": 1.5, "ale": 0.5, "wine": 2.0, "ration": 1.0, "waterskin": 2.0,
        "rope": 1.5, "torch": 0.5, "arrow": 0.2, "bandage": 1.0, "healing_potion": 12.0,
        "lodging:night": 2.0, "passage": 3.0,
    },
    "categories": {
        "food": 1.0, "drink": 1.0, "lodging": 2.0, "cloth": 4.0, "tools": 2.0, "weapons": 15.0, "armor": 25.0,
        "medicine": 6.0, "materials": 2.0, "luxury": 40.0, "transport": 30.0, "fuel": 1.0, "services": 3.0,
        "knowledge": 8.0, "magic": 60.0, "misc": 2.0,
    },
}

# The inventory item_type a bought category becomes; categories that are not things stay out of the pack.
ITEM_TYPE_BY_CATEGORY: dict[str, str] = {
    "food": "consumable", "drink": "consumable", "cloth": "clothing", "tools": "tool", "weapons": "weapon",
    "armor": "armor", "medicine": "medical",
}
NON_ITEM_CATEGORIES: frozenset[str] = frozenset({"lodging", "services"})
NON_ITEM_KEYS: frozenset[str] = frozenset({"passage"})

# Keeper mood from the npcs row (there is no mood column anywhere; attitude, personality and trust stand in).
MOODS: tuple[str, ...] = ("hostile", "cold", "neutral", "warm")
HOSTILE_ATTITUDES: frozenset[str] = frozenset({"hostile", "antagonistic", "angry", "furious", "violent"})
COLD_ATTITUDES: frozenset[str] = frozenset(
    {"dismissive", "apprehensive", "condescending", "cold", "wary", "suspicious", "sullen", "guarded"}
)
COLD_PERSONALITY: frozenset[str] = frozenset({"cold", "stoic", "secretive", "greedy", "miserly", "grasping"})
WARM_ATTITUDES: frozenset[str] = frozenset({"warm", "cordial", "friendly", "cheerful", "kind", "welcoming", "grateful"})
WARM_PERSONALITY: frozenset[str] = frozenset({"warm", "kind", "open", "generous", "cheerful"})
TRUST_WARMER_AT = 40
TRUST_COLDER_AT = -20

# Discount ceiling by relationships.affinity_band word, then the mood shift and the market adjustment.
BAND_CEILING: dict[str, float] = {
    "Hostile": 0.00, "Unfriendly": 0.03, "Neutral": 0.10, "Friendly": 0.15, "Trusted": 0.20, "Devoted": 0.25,
}
MOOD_CEILING_SHIFT: dict[str, float] = {"cold": -0.05, "neutral": 0.0, "warm": 0.05}
CEILING_MAX = 0.30
MARKET_SCARCE_ABOVE = 1.3
MARKET_GLUT_BELOW = 0.8
MARKET_GLUT_BONUS = 0.05

# Typed answers. Decline words are read before accept words ("no deal" holds "deal"). The phrases accept
# wherever they appear; the bare words (deal, done, agreed) only when the line is not a question and is
# short, names the item or names a coin, so "What have you done?" does not buy the bread.
_ACCEPT_PHRASES_RE = re.compile(r"\b(?:i(?:'| wi)ll take it|i(?:'| wi)ll pay|i accept|i(?:'| wi)ll buy it)\b", re.I)
_ACCEPT_BARE_RE = re.compile(r"\b(?:deal|done|agreed)\b", re.I)
ACCEPT_BARE_MAX_WORDS = 6
_DECLINE_WORDS_RE = re.compile(
    r"\b(?:no deal|too much|too dear|i(?:'| wi)ll pass|not today|keep it|no thanks|no thank you|forget it)\b", re.I
)
_APPRAISE_RE = re.compile(r"\b(?:apprais\w*|inspect\w*|worth|examine\w*|look\w* (?:it )?over)\b", re.I)

_PRICE_LEDGER_SQL = """
CREATE TABLE IF NOT EXISTS price_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_key TEXT NOT NULL,
    item_name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'misc',
    unit_price INTEGER NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    settlement_id TEXT NOT NULL DEFAULT '',
    location_id INTEGER NOT NULL DEFAULT 0,
    npc_id INTEGER NOT NULL DEFAULT 0,
    turn INTEGER NOT NULL DEFAULT 0,
    day INTEGER NOT NULL DEFAULT 1,
    source TEXT NOT NULL DEFAULT '',
    currency_set TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""
_PRICE_LEDGER_INDEX_SQL = "CREATE INDEX IF NOT EXISTS idx_price_ledger_item ON price_ledger(item_key, settlement_id)"
_PRICE_INDEX_SQL = """
CREATE TABLE IF NOT EXISTS price_index (
    item_key TEXT PRIMARY KEY,
    item_name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'misc',
    first_price INTEGER NOT NULL,
    avg_price REAL NOT NULL,
    sample_count INTEGER NOT NULL DEFAULT 1,
    min_price INTEGER NOT NULL,
    max_price INTEGER NOT NULL,
    last_price INTEGER NOT NULL,
    last_turn INTEGER NOT NULL DEFAULT 0,
    currency_set TEXT NOT NULL DEFAULT ''
)
"""
_TRADE_OFFERS_SQL = """
CREATE TABLE IF NOT EXISTS trade_offers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE DEFAULT '',
    status TEXT NOT NULL DEFAULT 'offered',
    kind TEXT NOT NULL DEFAULT 'buy',
    item_key TEXT NOT NULL DEFAULT '',
    item_name TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'misc',
    quantity INTEGER NOT NULL DEFAULT 1,
    unit_price INTEGER NOT NULL DEFAULT 0,
    total_price INTEGER NOT NULL DEFAULT 0,
    asking_price INTEGER NOT NULL DEFAULT 0,
    currency_set TEXT NOT NULL DEFAULT '',
    seller_npc_id INTEGER NOT NULL DEFAULT 0,
    location_id INTEGER NOT NULL DEFAULT 0,
    settlement_id TEXT NOT NULL DEFAULT '',
    offered_turn INTEGER NOT NULL DEFAULT 0,
    answered_turn INTEGER NOT NULL DEFAULT 0,
    expires_turn INTEGER NOT NULL DEFAULT 0,
    rounds INTEGER NOT NULL DEFAULT 0,
    max_rounds INTEGER NOT NULL DEFAULT 2,
    last_player_bid INTEGER NOT NULL DEFAULT 0,
    counter_price INTEGER NOT NULL DEFAULT 0,
    goods_given TEXT NOT NULL DEFAULT '[]',
    terms_id INTEGER NOT NULL DEFAULT 0,
    price_basis TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""
_TRADE_OFFERS_INDEX_SQL = "CREATE INDEX IF NOT EXISTS idx_trade_offers_status ON trade_offers(status, id)"

_OFFER_INT_KEYS: tuple[str, ...] = (
    "id", "quantity", "unit_price", "total_price", "asking_price", "seller_npc_id", "location_id",
    "offered_turn", "answered_turn", "expires_turn", "rounds", "max_rounds", "last_player_bid",
    "counter_price", "terms_id",
)
_OFFER_TEXT_KEYS: tuple[str, ...] = (
    "code", "status", "kind", "item_key", "item_name", "category", "currency_set", "settlement_id", "note",
    "price_basis",
)
_OFFER_COLUMNS: tuple[str, ...] = (
    "status", "kind", "item_key", "item_name", "category", "quantity", "unit_price", "total_price",
    "asking_price", "currency_set", "seller_npc_id", "location_id", "settlement_id", "offered_turn",
    "answered_turn", "expires_turn", "rounds", "max_rounds", "last_player_bid", "counter_price",
    "goods_given", "terms_id", "price_basis", "note",
)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _field(row: Any, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


def _words(text: Any) -> set[str]:
    return set(re.findall(r"[a-z]+", str(text or "").lower()))


def _mult_value(multiplier: dict | None) -> float:
    """The market multiplier a PriceMultiplier carries; 1.0 for None or any reason other than ok."""
    if not isinstance(multiplier, dict) or str(multiplier.get("reason") or "ok") != "ok":
        return 1.0
    try:
        return float(multiplier.get("mult") or 1.0)
    except (TypeError, ValueError):
        return 1.0


def _neutral_multiplier(settlement_id: str, category: str, *, day: int = 1) -> dict[str, Any]:
    return economy.neutral_multiplier(settlement_id, category, day=max(1, int(day or 1)), reason="unknown_settlement")


def _clean_name(name: str) -> str:
    text = re.sub(r"\[[^\]]*\]", " ", str(name or ""))
    text = " ".join(text.split())
    return text[:MAX_ITEM_NAME]


def _price_round(value: float) -> int:
    return currency.round_price(max(1, int(round(value))))


def _display(units: int, cset: dict) -> str:
    return currency.format_amount(int(units), cset, "long")


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create price_ledger, price_index and trade_offers when missing. Idempotent; no commit here."""
    conn.execute(_PRICE_LEDGER_SQL)
    conn.execute(_PRICE_LEDGER_INDEX_SQL)
    conn.execute(_PRICE_INDEX_SQL)
    conn.execute(_TRADE_OFFERS_SQL)
    conn.execute(_TRADE_OFFERS_INDEX_SQL)


# ---------------------------------------------------------------------------
# Pure: keys, categories, reference prices
# ---------------------------------------------------------------------------


def item_key(name: str) -> str:
    """The ledger key for an item name: lower case, tags and leading articles gone, possessives dropped,
    spaces collapsed, cut at 60 characters, then the first ITEM_ALIASES match."""
    text = str(name or "").lower().replace("’", "'")
    text = re.sub(r"\[[^\]]*\]", " ", text)
    text = re.sub(r"[^a-z0-9':\- ]+", " ", text)
    text = re.sub(r"'s\b|s'(?=\s|$)", "", text)
    text = text.replace("'", "")
    phrase = " ".join(text.split())
    for pattern, key in _ITEM_ALIAS_RES:
        if pattern.search(phrase):
            return key
    text = re.sub(r"\b(?:a|an|the|some|one|my|your|his|her|their|our)\b", " ", phrase)
    return " ".join(text.split())[:MAX_ITEM_KEY].strip()


def categorize(name: str, item_type: str = "") -> str:
    """The economy.GOODS_CATEGORIES id for a name: an alias key's category first, then the item_type when
    it maps, then the longest keyword hit (ties by category order), else misc."""
    key = item_key(name)
    if key in KEY_CATEGORIES:
        return KEY_CATEGORIES[key]
    kind = str(item_type or "").strip().lower()
    if kind in ITEM_TYPE_CATEGORIES:
        return ITEM_TYPE_CATEGORIES[kind]
    text = " " + key + " "
    best: tuple[int, int, str] | None = None
    for order, (category, word, pattern) in enumerate(_CATEGORY_RES):
        if not pattern.search(text):
            continue
        if kind == "consumable" and category not in ("food", "drink"):
            continue
        # A phrase ("lamp oil") beats a single word; among words the table's category order decides.
        score = (1 if " " in word else 0, -order, category)
        if best is None or score > best:
            best = score
    if best is not None:
        return best[2]
    if kind == "consumable":
        return "food"
    return "misc"


def reference_price(name: str, cset: dict, *, category: str = "") -> int | None:
    """Units for an item the ledger has never seen: the key's row in REFERENCE_GOLD, else the category's.
    None when neither the key nor the (given or derived) category is known."""
    key = item_key(name)
    gold = REFERENCE_GOLD["items"].get(key)
    if gold is None:
        cat = str(category or "").strip().lower() or categorize(name)
        gold = REFERENCE_GOLD["categories"].get(cat)
    if gold is None:
        return None
    return currency.round_price(max(1, currency.from_legacy_gold(gold, cset)))


# ---------------------------------------------------------------------------
# Ledger (writers take conn; readers return plain dicts)
# ---------------------------------------------------------------------------


def record_price(
    conn: sqlite3.Connection,
    *,
    item_name: str,
    unit_price: int,
    quantity: int = 1,
    settlement_id: str = "",
    location_id: int = 0,
    npc_id: int = 0,
    turn: int = 0,
    day: int = 1,
    source: str = "manual",
    category: str = "",
    currency_set: str = "",
) -> dict[str, Any]:
    """Insert one price_ledger row and move price_index: the first price of a key is kept for good, later
    samples move the running mean unless they are outliers. unit_price <= 0 or quantity < 1 is ValueError."""
    price = _int(unit_price)
    qty = _int(quantity, 1)
    if price <= 0:
        raise ValueError(f"unit_price must be positive, got {unit_price!r}")
    if qty < 1:
        raise ValueError(f"quantity must be at least 1, got {quantity!r}")
    name = _clean_name(item_name)
    if not name:
        raise ValueError("item_name may not be empty")
    ensure_schema(conn)
    key = item_key(name)
    cat = str(category or "").strip().lower() or categorize(name)
    cur = conn.execute(
        """
        INSERT INTO price_ledger
            (item_key, item_name, category, unit_price, quantity, settlement_id, location_id, npc_id,
             turn, day, source, currency_set)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (key, name, cat, price, qty, str(settlement_id or ""), _int(location_id), _int(npc_id), _int(turn),
         max(1, _int(day, 1)), str(source or "manual")[:40], str(currency_set or "")),
    )
    ledger_id = int(cur.lastrowid or 0)
    row = conn.execute("SELECT * FROM price_index WHERE item_key = ?", (key,)).fetchone()
    if row is None:
        conn.execute(
            """
            INSERT INTO price_index
                (item_key, item_name, category, first_price, avg_price, sample_count, min_price, max_price,
                 last_price, last_turn, currency_set)
            VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
            """,
            (key, name, cat, price, float(price), price, price, price, _int(turn), str(currency_set or "")),
        )
        return {
            "ledger_id": ledger_id, "item_key": key, "first": True, "first_price": price,
            "avg_price": float(price), "sample_count": 1, "outlier": False,
        }
    avg = float(row["avg_price"])
    count = int(row["sample_count"])
    low, high = OUTLIER_RANGE
    outlier = count >= OUTLIER_MIN_SAMPLES and (price < avg * low or price > avg * high)
    if outlier:
        conn.execute(
            "UPDATE price_index SET last_price = ?, last_turn = ? WHERE item_key = ?",
            (price, _int(turn), key),
        )
    else:
        avg = (avg * count + price) / (count + 1)
        count += 1
        conn.execute(
            """
            UPDATE price_index
            SET avg_price = ?, sample_count = ?, min_price = MIN(min_price, ?), max_price = MAX(max_price, ?),
                last_price = ?, last_turn = ?
            WHERE item_key = ?
            """,
            (avg, count, price, price, price, _int(turn), key),
        )
    return {
        "ledger_id": ledger_id, "item_key": key, "first": False, "first_price": int(row["first_price"]),
        "avg_price": avg, "sample_count": count, "outlier": bool(outlier),
    }


def known_price(conn: sqlite3.Connection, item_name: str) -> dict[str, Any] | None:
    """The price_index row for an item name as a dict, or None."""
    ensure_schema(conn)
    row = conn.execute("SELECT * FROM price_index WHERE item_key = ?", (item_key(item_name),)).fetchone()
    return dict(row) if row else None


def ledger_for(
    conn: sqlite3.Connection, item_name: str, *, settlement_id: str = "", limit: int = MAX_LEDGER_ROWS
) -> list[dict[str, Any]]:
    """price_ledger rows for an item, newest first, in one settlement when given."""
    ensure_schema(conn)
    key = item_key(item_name)
    cap = max(1, _int(limit, MAX_LEDGER_ROWS))
    if settlement_id:
        cur = conn.execute(
            "SELECT * FROM price_ledger WHERE item_key = ? AND settlement_id = ? ORDER BY id DESC LIMIT ?",
            (key, str(settlement_id), cap),
        )
    else:
        cur = conn.execute("SELECT * FROM price_ledger WHERE item_key = ? ORDER BY id DESC LIMIT ?", (key, cap))
    return [dict(row) for row in cur.fetchall()]


def prices_from_turn(result: dict, *, narration: str, gold_note: dict | None, cset: dict) -> list[dict[str, Any]]:
    """Pure: the one (item, price) pair a turn shows, or [].

    Items are the kept gains in result["inventory_changes"] (quantity_delta > 0); prices are the money
    phrases in the narration (negated clauses stripped, the same amount restated counts once), falling back
    to a negative gold_note["gold_delta"] converted from legacy gold. One item and one price give one entry;
    two items or two prices are ambiguous and nothing is recorded.
    """
    changes = result.get("inventory_changes") if isinstance(result, dict) else None
    gains: list[dict[str, Any]] = []
    for change in changes or []:
        if not isinstance(change, dict):
            continue
        name = _clean_name(change.get("name") or "")
        if name and _int(change.get("quantity_delta")) > 0:
            gains.append({"name": name, "quantity": _int(change.get("quantity_delta"), 1)})
    if len(gains) != 1:
        return []
    prices: list[int] = []
    for found in currency.parse_all_amounts(strip_negated_clauses(narration or ""), cset):
        units = _int(found.get("units"))
        if units > 0 and units not in prices:
            prices.append(units)
    note = gold_note if isinstance(gold_note, dict) else {}
    if not prices:
        delta = _int(note.get("gold_delta"))
        if delta < 0:
            prices.append(currency.from_legacy_gold(-delta, cset))
    if len(prices) != 1:
        return []
    source = str(note.get("source") or "")
    if source not in ("prose", "prose_paid", "stated"):
        source = "prose"
    quantity = max(1, gains[0]["quantity"])
    return [{
        "item_name": gains[0]["name"],
        "unit_price": max(1, prices[0] // quantity),
        "quantity": quantity,
        "source": source,
    }]


def record_turn_prices(
    conn: sqlite3.Connection,
    *,
    result: dict,
    narration: str,
    gold_note: dict | None,
    seller: dict | None,
    turn: int,
    day: int,
    cset: dict,
) -> list[dict[str, Any]]:
    """record_price for each prices_from_turn entry, tagged with the seller's settlement, location and npc."""
    who = seller if isinstance(seller, dict) else {}
    out: list[dict[str, Any]] = []
    for entry in prices_from_turn(result, narration=narration, gold_note=gold_note, cset=cset):
        recorded = record_price(
            conn,
            item_name=entry["item_name"],
            unit_price=entry["unit_price"],
            quantity=entry["quantity"],
            settlement_id=str(who.get("settlement_id") or ""),
            location_id=_int(who.get("location_id")),
            npc_id=_int(who.get("npc_id")),
            turn=_int(turn),
            day=max(1, _int(day, 1)),
            source=entry["source"],
            currency_set=str(cset.get("id") or ""),
        )
        recorded["item_name"] = entry["item_name"]
        out.append(recorded)
    return out


# ---------------------------------------------------------------------------
# Quotes
# ---------------------------------------------------------------------------


def settlement_price(
    conn: sqlite3.Connection,
    item_name: str,
    settlement_id: str,
    *,
    day: int,
    cset: dict,
    multiplier: dict | None = None,
    quantity: int = 1,
    category: str = "",
    seed: int | None = None,
) -> dict[str, Any]:
    """The PriceQuote for an item in a settlement.

    The anchor is the first ledger price in this settlement, else the running average, else the reference
    price; the economy multiplier (given, or economy.settlement_multiplier) moves it, and 1.0 stands in
    when the multiplier's reason is not ok. Basis "none" means no price is known at all.
    """
    ensure_schema(conn)
    name = _clean_name(item_name)
    key = item_key(name)
    index = known_price(conn, name)
    cat = str(category or "").strip().lower() or (str(index["category"]) if index else categorize(name))
    qty = max(1, _int(quantity, 1))
    day_value = max(1, _int(day, 1))
    first_here = None
    if settlement_id:
        first_here = conn.execute(
            "SELECT unit_price FROM price_ledger WHERE item_key = ? AND settlement_id = ? ORDER BY id ASC LIMIT 1",
            (key, str(settlement_id)),
        ).fetchone()
    anchor = 0
    basis = "none"
    if first_here is not None:
        anchor = int(first_here["unit_price"])
        basis = "ledger_first"
    elif index:
        anchor = max(1, int(round(float(index["avg_price"]))))
        basis = "ledger_avg"
    else:
        ref = reference_price(name, cset, category=cat)
        if ref is not None:
            anchor = int(ref)
            basis = "reference"
    if multiplier is None:
        multiplier = economy.settlement_multiplier(conn, settlement_id, cat, day=day_value, seed=seed)
    mult = _mult_value(multiplier)
    unit = _price_round(anchor * mult) if basis != "none" else 0
    return {
        "item_key": key,
        "item_name": str(index["item_name"]) if index else name,
        "category": cat,
        "unit_price": unit,
        "quantity": qty,
        "total": unit * qty,
        "basis": basis,
        "anchor": anchor,
        "multiplier": multiplier,
        "known_here": first_here is not None,
        "samples": int(index["sample_count"]) if index else 0,
        "display": _display(unit, cset) if unit else "",
    }


def _market_phrase(multiplier: dict | None) -> str:
    if not isinstance(multiplier, dict) or str(multiplier.get("reason") or "ok") != "ok":
        return "no market data"
    mult = _mult_value(multiplier)
    if mult >= 1.5:
        word = "market very dear"
    elif mult > 1.1:
        word = "market a little dear"
    elif mult <= 0.6:
        word = "market very cheap"
    elif mult < 0.9:
        word = "market a little cheap"
    else:
        word = "market steady"
    season = _text(multiplier.get("season"))
    return f"{word}, {season}" if season else word


def quote_text(quote: dict, cset: dict) -> str:
    """One engine line for a quote: "bread: 5 silver each (market a little dear, winter)"."""
    name = _text(quote.get("item_name")) or _text(quote.get("item_key")) or "item"
    if str(quote.get("basis") or "none") == "none" or not _int(quote.get("unit_price")):
        return f"{name}: no known price"
    each = _display(_int(quote.get("unit_price")), cset)
    return f"{name}: {each} each ({_market_phrase(quote.get('multiplier'))})"


# ---------------------------------------------------------------------------
# Offers
# ---------------------------------------------------------------------------


def _goods_list(goods: list | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in goods or []:
        if not isinstance(entry, dict):
            continue
        name = _clean_name(entry.get("item_name") or entry.get("name") or "")
        if not name:
            continue
        out.append({
            "item_key": str(entry.get("item_key") or item_key(name)),
            "item_name": name,
            "quantity": max(1, _int(entry.get("quantity"), 1)),
        })
    return out


def make_offer(
    *,
    kind: str,
    item_name: str,
    quantity: int,
    unit_price: int,
    cset: dict,
    seller_npc_id: int = 0,
    location_id: int = 0,
    settlement_id: str = "",
    turn: int = 0,
    category: str = "",
    goods_given: list | None = None,
    price_basis: str = "",
    note: str = "",
    max_rounds: int | None = None,
) -> dict[str, Any]:
    """A pure Offer dict with id 0 and code "". kind outside OFFER_KINDS, quantity < 1 or a negative
    unit_price is ValueError."""
    kind_word = str(kind or "").strip().lower()
    if kind_word not in OFFER_KINDS:
        raise ValueError(f"unknown offer kind: {kind!r}")
    qty = _int(quantity, 0)
    if qty < 1:
        raise ValueError(f"quantity must be at least 1, got {quantity!r}")
    price = _int(unit_price, -1)
    if price < 0:
        raise ValueError(f"unit_price may not be negative, got {unit_price!r}")
    name = _clean_name(item_name)
    if not name:
        raise ValueError("item_name may not be empty")
    total = price * qty
    rounds_cap = _int(max_rounds, MAX_ROUNDS) if max_rounds is not None else MAX_ROUNDS
    turn_value = _int(turn)
    return {
        "id": 0,
        "code": "",
        "status": "offered",
        "kind": kind_word,
        "item_key": item_key(name),
        "item_name": name,
        "category": str(category or "").strip().lower() or categorize(name),
        "quantity": qty,
        "unit_price": price,
        "total_price": total,
        "asking_price": total,
        "currency_set": str(cset.get("id") or ""),
        "seller_npc_id": _int(seller_npc_id),
        "location_id": _int(location_id),
        "settlement_id": str(settlement_id or ""),
        "offered_turn": turn_value,
        "answered_turn": 0,
        "expires_turn": turn_value + OFFER_TTL_TURNS,
        "rounds": 0,
        "max_rounds": max(1, rounds_cap),
        "last_player_bid": 0,
        "counter_price": 0,
        "goods_given": _goods_list(goods_given),
        "terms_id": 0,
        "note": str(note or "")[:300],
        "price_basis": str(price_basis or "")[:20],
    }


def _decode_offer(row: Any) -> dict[str, Any]:
    source = dict(row)
    offer: dict[str, Any] = {}
    for key in _OFFER_INT_KEYS:
        offer[key] = _int(source.get(key))
    for key in _OFFER_TEXT_KEYS:
        offer[key] = str(source.get(key) or "")
    try:
        goods = json.loads(source.get("goods_given") or "[]")
    except (TypeError, ValueError):
        goods = []
    offer["goods_given"] = _goods_list(goods if isinstance(goods, list) else [])
    return offer


def get_offer(conn: sqlite3.Connection, offer_id: int) -> dict[str, Any] | None:
    """The Offer dict for a trade_offers id, or None."""
    ensure_schema(conn)
    row = conn.execute("SELECT * FROM trade_offers WHERE id = ?", (_int(offer_id),)).fetchone()
    return _decode_offer(row) if row else None


def open_offers(conn: sqlite3.Connection, *, limit: int = STATE_VIEW_LIMIT) -> list[dict[str, Any]]:
    """Offers in OPEN_STATES, newest first."""
    ensure_schema(conn)
    cur = conn.execute(
        "SELECT * FROM trade_offers WHERE status IN ('offered', 'countered') ORDER BY id DESC LIMIT ?",
        (max(1, _int(limit, STATE_VIEW_LIMIT)),),
    )
    return [_decode_offer(row) for row in cur.fetchall()]


def open_offer(conn: sqlite3.Connection, offer: dict) -> dict[str, Any]:
    """Insert an Offer, stamp its code T{id} and expiry, expire the oldest open offers past MAX_OPEN_OFFERS,
    and return the stored row."""
    ensure_schema(conn)
    if not isinstance(offer, dict):
        raise ValueError("offer must be a dict from make_offer")
    kind_word = str(offer.get("kind") or "").strip().lower()
    if kind_word not in OFFER_KINDS:
        raise ValueError(f"unknown offer kind: {offer.get('kind')!r}")
    offered_turn = _int(offer.get("offered_turn"))
    values = {
        "status": "offered",
        "kind": kind_word,
        "item_key": str(offer.get("item_key") or item_key(str(offer.get("item_name") or ""))),
        "item_name": _clean_name(offer.get("item_name") or ""),
        "category": str(offer.get("category") or "misc"),
        "quantity": max(1, _int(offer.get("quantity"), 1)),
        "unit_price": max(0, _int(offer.get("unit_price"))),
        "total_price": max(0, _int(offer.get("total_price"))),
        "asking_price": max(0, _int(offer.get("asking_price"))),
        "currency_set": str(offer.get("currency_set") or ""),
        "seller_npc_id": _int(offer.get("seller_npc_id")),
        "location_id": _int(offer.get("location_id")),
        "settlement_id": str(offer.get("settlement_id") or ""),
        "offered_turn": offered_turn,
        "answered_turn": 0,
        "expires_turn": offered_turn + OFFER_TTL_TURNS,
        "rounds": max(0, _int(offer.get("rounds"))),
        "max_rounds": max(1, _int(offer.get("max_rounds"), MAX_ROUNDS)),
        "last_player_bid": max(0, _int(offer.get("last_player_bid"))),
        "counter_price": max(0, _int(offer.get("counter_price"))),
        "goods_given": json.dumps(_goods_list(offer.get("goods_given")), ensure_ascii=True),
        "terms_id": _int(offer.get("terms_id")),
        "price_basis": str(offer.get("price_basis") or "")[:20],
        "note": str(offer.get("note") or "")[:300],
    }
    if not values["item_name"]:
        raise ValueError("item_name may not be empty")
    cur = conn.execute(
        """
        INSERT INTO trade_offers
            (status, kind, item_key, item_name, category, quantity, unit_price, total_price, asking_price,
             currency_set, seller_npc_id, location_id, settlement_id, offered_turn, answered_turn, expires_turn,
             rounds, max_rounds, last_player_bid, counter_price, goods_given, terms_id, price_basis, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        tuple(values[key] for key in _OFFER_COLUMNS),
    )
    new_id = int(cur.lastrowid or 0)
    conn.execute("UPDATE trade_offers SET code = ? WHERE id = ?", (f"T{new_id}", new_id))
    open_ids = [
        int(row["id"])
        for row in conn.execute(
            "SELECT id FROM trade_offers WHERE status IN ('offered', 'countered') ORDER BY id ASC"
        ).fetchall()
    ]
    for stale_id in open_ids[: max(0, len(open_ids) - MAX_OPEN_OFFERS)]:
        conn.execute(
            "UPDATE trade_offers SET status = 'expired', answered_turn = ? WHERE id = ? AND status IN ('offered', 'countered')",
            (offered_turn, stale_id),
        )
    stored = get_offer(conn, new_id)
    assert stored is not None
    return stored


def accept_offer(
    conn: sqlite3.Connection, offer_id: int, *, turn: int = 0, price: int | None = None
) -> dict[str, Any] | None:
    """offered | countered -> accepted at the price on the table (or the given one; a given price that
    differs from the table price sets price_basis to counter). None when not open."""
    ensure_schema(conn)
    offer = get_offer(conn, offer_id)
    if offer is None or offer["status"] not in OPEN_STATES:
        return None
    on_table = offer["counter_price"] if offer["status"] == "countered" and offer["counter_price"] else offer["total_price"]
    if price is not None:
        agreed = _int(price, -1)
        if agreed < 0:
            raise ValueError(f"price may not be negative, got {price!r}")
    else:
        agreed = on_table
    basis = "counter" if agreed != on_table else offer["price_basis"]
    cur = conn.execute(
        """
        UPDATE trade_offers SET status = 'accepted', total_price = ?, unit_price = ?, price_basis = ?, answered_turn = ?
        WHERE id = ? AND status IN ('offered', 'countered')
        """,
        (agreed, max(0, agreed // max(1, offer["quantity"])), basis, _int(turn), offer["id"]),
    )
    if not cur.rowcount:
        return None
    return get_offer(conn, offer["id"])


def _close_offer(conn: sqlite3.Connection, offer_id: int, *, status: str, turn: int, note: str = "") -> dict[str, Any] | None:
    cur = conn.execute(
        """
        UPDATE trade_offers
        SET status = ?, answered_turn = ?, note = CASE WHEN ? = '' THEN note ELSE ? END
        WHERE id = ? AND status IN ('offered', 'countered')
        """,
        (status, _int(turn), note, note[:300], _int(offer_id)),
    )
    if not cur.rowcount:
        return None
    return get_offer(conn, offer_id)


def decline_offer(conn: sqlite3.Connection, offer_id: int, *, turn: int = 0) -> dict[str, Any] | None:
    """The player refuses: open -> declined. None when not open."""
    ensure_schema(conn)
    return _close_offer(conn, offer_id, status="declined", turn=turn)


def withdraw_offer(conn: sqlite3.Connection, offer_id: int, *, turn: int = 0, reason: str = "") -> dict[str, Any] | None:
    """The seller withdraws (or was insulted): open -> refused. None when not open."""
    ensure_schema(conn)
    return _close_offer(conn, offer_id, status="refused", turn=turn, note=str(reason or ""))


def counter_offer(
    conn: sqlite3.Connection, offer_id: int, *, price: int, turn: int = 0, bid: int = 0
) -> dict[str, Any] | None:
    """The seller names a new total: open -> countered, rounds + 1, the player's bid remembered, price_basis
    counter. None when not open; price < 1 is ValueError."""
    ensure_schema(conn)
    new_price = _int(price, 0)
    if new_price < 1:
        raise ValueError(f"price must be at least 1, got {price!r}")
    offer = get_offer(conn, offer_id)
    if offer is None or offer["status"] not in OPEN_STATES:
        return None
    cur = conn.execute(
        """
        UPDATE trade_offers
        SET status = 'countered', counter_price = ?, total_price = ?, unit_price = ?, price_basis = 'counter',
            rounds = rounds + 1, last_player_bid = ?, answered_turn = ?
        WHERE id = ? AND status IN ('offered', 'countered')
        """,
        (new_price, new_price, max(1, new_price // max(1, offer["quantity"])), max(0, _int(bid)), _int(turn), offer["id"]),
    )
    if not cur.rowcount:
        return None
    return get_offer(conn, offer["id"])


def _note_round(conn: sqlite3.Connection, offer_id: int, *, bid: int, turn: int) -> dict[str, Any] | None:
    """A refused round: the offer stays open at its price, but the round is spent."""
    cur = conn.execute(
        """
        UPDATE trade_offers SET rounds = rounds + 1, last_player_bid = ?, answered_turn = ?
        WHERE id = ? AND status IN ('offered', 'countered')
        """,
        (max(0, _int(bid)), _int(turn), _int(offer_id)),
    )
    if not cur.rowcount:
        return None
    return get_offer(conn, offer_id)


def mark_settled(conn: sqlite3.Connection, offer_id: int, *, turn: int = 0) -> dict[str, Any] | None:
    """accepted -> settled, once the wiring has applied the fulfilment proposal. None otherwise."""
    ensure_schema(conn)
    cur = conn.execute(
        "UPDATE trade_offers SET status = 'settled', answered_turn = ? WHERE id = ? AND status = 'accepted'",
        (_int(turn), _int(offer_id)),
    )
    if not cur.rowcount:
        return None
    return get_offer(conn, offer_id)


def expire_stale(conn: sqlite3.Connection, *, turn: int, location_id: int | None = None) -> list[int]:
    """Expire open offers whose expires_turn has passed, or whose location is not the given one (an offer
    with location_id 0 has no place and only expires by time). Returns the ids expired."""
    ensure_schema(conn)
    now = _int(turn)
    expired: list[int] = []
    for row in conn.execute(
        "SELECT id, expires_turn, location_id FROM trade_offers WHERE status IN ('offered', 'countered') ORDER BY id"
    ).fetchall():
        by_time = int(row["expires_turn"]) <= now
        by_place = location_id is not None and int(row["location_id"]) != 0 and int(row["location_id"]) != _int(location_id)
        if by_time or by_place:
            expired.append(int(row["id"]))
    for offer_id in expired:
        conn.execute(
            "UPDATE trade_offers SET status = 'expired', answered_turn = ? WHERE id = ? AND status IN ('offered', 'countered')",
            (now, offer_id),
        )
    return expired


def _rounds_cap(offer: dict, band: str) -> int:
    base = max(1, _int(offer.get("max_rounds"), MAX_ROUNDS))
    if band in ("Trusted", "Devoted"):
        return max(base, TRUSTED_MAX_ROUNDS)
    return base


def state_view(conn: sqlite3.Connection, *, cset: dict) -> dict[str, Any]:
    """{"open_trade_offers": [...]} for get_state, at most STATE_VIEW_LIMIT rows, newest first."""
    rows = []
    for offer in open_offers(conn, limit=STATE_VIEW_LIMIT):
        rows.append({
            "id": offer["id"],
            "code": offer["code"],
            "kind": offer["kind"],
            "item_name": offer["item_name"],
            "quantity": offer["quantity"],
            "price": _display(offer["total_price"], cset),
            "units": offer["total_price"],
            "seller_npc_id": offer["seller_npc_id"],
            "status": offer["status"],
            "rounds_left": max(0, offer["max_rounds"] - offer["rounds"]),
            "offered_turn": offer["offered_turn"],
        })
    return {"open_trade_offers": rows}


# ---------------------------------------------------------------------------
# Haggling (pure)
# ---------------------------------------------------------------------------


def keeper_mood(npc_row: dict | None) -> str:
    """warm | neutral | cold | hostile from the npcs row's attitude, personality and trust; None is neutral."""
    if npc_row is None:
        return "neutral"
    attitude = _words(_field(npc_row, "attitude", ""))
    personality = _words(_field(npc_row, "personality", ""))
    if attitude & HOSTILE_ATTITUDES:
        mood = "hostile"
    elif attitude & COLD_ATTITUDES or personality & COLD_PERSONALITY:
        mood = "cold"
    elif attitude & WARM_ATTITUDES or personality & WARM_PERSONALITY:
        mood = "warm"
    else:
        mood = "neutral"
    trust = _int(_field(npc_row, "trust", 0))
    index = MOODS.index(mood)
    if trust >= TRUST_WARMER_AT:
        index = min(len(MOODS) - 1, index + 1)
    elif trust <= TRUST_COLDER_AT:
        index = max(0, index - 1)
    return MOODS[index]


def discount_ceiling(*, band: str, mood: str, multiplier: dict | None = None) -> float:
    """The largest share off the asking price this seller would ever take: the band ceiling, shifted by
    mood, halved in a scarce market, raised a little in a glut, clamped 0..CEILING_MAX. Hostile is 0."""
    band_word = str(band or "Neutral")
    mood_word = str(mood or "neutral").lower()
    if band_word == "Hostile" or mood_word == "hostile":
        return 0.0
    ceiling = BAND_CEILING.get(band_word, BAND_CEILING["Neutral"])
    ceiling += MOOD_CEILING_SHIFT.get(mood_word, 0.0)
    mult = _mult_value(multiplier)
    if mult > MARKET_SCARCE_ABOVE:
        ceiling *= 0.5
    elif mult < MARKET_GLUT_BELOW:
        ceiling += MARKET_GLUT_BONUS
    return round(max(0.0, min(CEILING_MAX, ceiling)), 4)


def _stat_profile(keeper_row: dict | None) -> dict[str, Any]:
    raw = _field(keeper_row, "stat_profile", {})
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def haggle_check_inputs(offer: dict, keeper_row: dict | None, *, player_line: str = "", cset: dict) -> dict[str, Any]:
    """Keyword arguments for skill_checks.resolve_check: persuasion (appraise when the line asks what it is
    worth), the keeper as opposition, a context note naming the item and the price."""
    skill = "appraise" if _APPRAISE_RE.search(str(player_line or "")) else "persuasion"
    name = _text(_field(keeper_row, "name", "")) or "the seller"
    asking = _int(offer.get("asking_price")) or _int(offer.get("total_price"))
    return {
        "skill_code": skill,
        "opposition": {
            "name": name,
            "rank": _text(_field(keeper_row, "rank", "")) or "F",
            "attitude": _text(_field(keeper_row, "attitude", "")) or "neutral",
            "stats": _stat_profile(keeper_row),
        },
        "context_note": f"haggling over {offer.get('item_name') or 'the goods'} at {_display(asking, cset)}",
        "weapon_or_tool": "",
    }


def _band_from(relationship: dict | None) -> str:
    if not isinstance(relationship, dict):
        return "Neutral"
    band = _text(relationship.get("affinity_band"))
    if band in BAND_CEILING:
        return band
    return affinity_band(_int(relationship.get("affinity")))


def _haggle_line(decision: str, *, who: str, price: int, cset: dict) -> str:
    shown = _display(price, cset)
    if decision == "accept":
        return f"{who} takes {shown}."
    if decision == "counter":
        return f"{who} considers it, then names {shown}."
    if decision == "insulted":
        return f"{who} is insulted by the offer and will not sell."
    return f"{who} will not bargain; the price stays {shown}."


def resolve_haggle(
    offer: dict,
    *,
    bid: int,
    check: dict | None,
    relationship: dict | None,
    keeper_row: dict | None,
    cset: dict,
    multiplier: dict | None = None,
) -> dict[str, Any]:
    """The HaggleResult for one round, pure. bid <= 0 is ValueError.

    Hostile band or mood refuses before any roll, and a bid at or above the price on the table is taken at
    that price (outcome not_rolled in both cases, so check may be None there); a bid under LOWBALL_FRACTION
    of the asking price insults unless the band is Devoted; otherwise the check outcome decides against the
    floor (asking less the discount ceiling). An accept names relationship_event traded_npc, a lowball
    insult lied_to_npc_caught.
    """
    bid_value = _int(bid, 0)
    if bid_value <= 0:
        raise ValueError(f"bid must be positive, got {bid!r}")
    asking = _int(offer.get("asking_price")) or _int(offer.get("total_price"))
    on_table = _int(offer.get("counter_price")) or _int(offer.get("total_price")) or asking
    band = _band_from(relationship)
    mood = keeper_mood(keeper_row)
    who = _text(_field(keeper_row, "name", "")) or "The seller"
    round_number = max(0, _int(offer.get("rounds"))) + 1
    cap = _rounds_cap(offer, band)
    rounds_left = max(0, cap - round_number)
    ceiling = discount_ceiling(band=band, mood=mood, multiplier=multiplier)
    floor = _price_round(asking * (1.0 - ceiling)) if asking > 0 else 1
    floor = min(floor, asking) if asking > 0 else floor

    def result(decision: str, price: int, *, outcome: str, left: int, event: str | None) -> dict[str, Any]:
        return {
            "decision": decision,
            "price": int(price),
            "floor": int(floor),
            "ceiling_pct": float(ceiling),
            "mood": mood,
            "band": band,
            "outcome": outcome,
            "round": round_number,
            "rounds_left": int(left),
            "relationship_event": event,
            "line": _haggle_line(decision, who=who, price=price, cset=cset),
        }

    if band == "Hostile" or mood == "hostile":
        return result("refuse", on_table, outcome="not_rolled", left=rounds_left, event=None)
    if bid_value >= on_table:
        return result("accept", on_table, outcome="not_rolled", left=rounds_left, event="traded_npc")
    lowball = asking > 0 and bid_value < asking * LOWBALL_FRACTION and band != "Devoted"
    outcome = _text((check or {}).get("outcome") if isinstance(check, dict) else "").lower()
    if outcome not in OUTCOME_RANK:
        outcome = "partial"
    if lowball or outcome == "critical_failure":
        raised = _price_round(asking * (1.0 + INSULT_RAISE))
        return result("insulted", raised, outcome=outcome, left=0, event="lied_to_npc_caught" if lowball else None)

    def counter_at(value: float) -> dict[str, Any]:
        price = _price_round(value)
        price = max(price, bid_value + COUNTER_STEP_MIN)
        price = min(price, on_table)
        if price <= bid_value:
            return result("accept", bid_value, outcome=outcome, left=rounds_left, event="traded_npc")
        return result("counter", price, outcome=outcome, left=rounds_left, event=None)

    if outcome == "failure":
        if rounds_left > 0:
            return result("counter", on_table, outcome=outcome, left=rounds_left, event=None)
        return result("refuse", on_table, outcome=outcome, left=0, event=None)
    if outcome == "partial":
        return counter_at(max(float(floor), (bid_value + asking) / 2.0))
    if outcome == "success":
        if bid_value >= floor:
            return result("accept", bid_value, outcome=outcome, left=rounds_left, event="traded_npc")
        return counter_at(float(floor))
    crit_floor = floor * CRIT_SUCCESS_FLOOR_MULT
    if bid_value >= crit_floor:
        return result("accept", bid_value, outcome=outcome, left=rounds_left, event="traded_npc")
    return counter_at(crit_floor)


def run_haggle(
    conn: sqlite3.Connection,
    offer_id: int,
    *,
    bid: int,
    turn: int,
    cset: dict,
    player_stats: dict | None,
    player_skills: list | None,
    check_settings: dict | None,
    rng: Any,
    player_line: str = "",
    day: int | None = None,
    seed: int | None = None,
    multiplier: dict | None = None,
) -> dict[str, Any] | None:
    """One haggle round against the stored offer: loads the keeper (npcs), the relationship summary
    (relationships.get_relationship_summary, which creates the row when missing) and the market multiplier
    (the given one, else economy.settlement_multiplier for the given day, else neutral), rolls
    skill_checks.resolve_check with the caller's rng, resolves, then moves the row by the decision.
    No roll is made, and the rng is left untouched, when the answer needs none: a Hostile band or a hostile
    keeper refuses, and a bid at or above the price on the table is taken; "check" is then None.
    None when the offer is not open; ValueError when its rounds are spent or the bid is not positive.
    Returns {"offer", "haggle", "check"}. dice_rolls is not written here; the wiring records the check
    when there is one.
    """
    ensure_schema(conn)
    bid_value = _int(bid, 0)
    if bid_value <= 0:
        raise ValueError(f"bid must be positive, got {bid!r}")
    offer = get_offer(conn, offer_id)
    if offer is None or offer["status"] not in OPEN_STATES:
        return None
    keeper = None
    relationship = None
    if offer["seller_npc_id"]:
        row = conn.execute("SELECT * FROM npcs WHERE id = ?", (offer["seller_npc_id"],)).fetchone()
        keeper = dict(row) if row else None
        if keeper is not None:
            relationship = get_relationship_summary(conn, offer["seller_npc_id"])
    band = _band_from(relationship)
    if offer["rounds"] >= _rounds_cap(offer, band):
        raise ValueError("no haggling rounds left on this offer")
    if multiplier is None:
        if day is not None:
            multiplier = economy.settlement_multiplier(
                conn, offer["settlement_id"], offer["category"], day=max(1, _int(day, 1)), seed=seed
            )
        else:
            multiplier = _neutral_multiplier(offer["settlement_id"], offer["category"])
    on_table = offer["counter_price"] or offer["total_price"] or offer["asking_price"]
    check = None
    if band != "Hostile" and keeper_mood(keeper) != "hostile" and bid_value < on_table:
        inputs = haggle_check_inputs(offer, keeper, player_line=player_line, cset=cset)
        check = resolve_check(
            skill_code=inputs["skill_code"],
            opposition=inputs["opposition"],
            context_note=inputs["context_note"],
            weapon_or_tool=inputs["weapon_or_tool"],
            settings=check_settings,
            rng=rng,
            player_stats=player_stats,
            player_skills=player_skills,
        )
    haggle = resolve_haggle(
        offer, bid=bid_value, check=check, relationship=relationship, keeper_row=keeper, cset=cset,
        multiplier=multiplier,
    )
    decision = haggle["decision"]
    if decision == "accept":
        stored = accept_offer(conn, offer["id"], turn=turn, price=haggle["price"])
    elif decision == "counter":
        stored = counter_offer(conn, offer["id"], price=haggle["price"], turn=turn, bid=bid_value)
    elif decision == "insulted":
        stored = withdraw_offer(conn, offer["id"], turn=turn, reason="insulted")
    else:
        stored = _note_round(conn, offer["id"], bid=bid_value, turn=turn)
    return {"offer": stored if stored is not None else get_offer(conn, offer["id"]), "haggle": haggle, "check": check}


# ---------------------------------------------------------------------------
# Alternatives (pure over rows the caller fetched)
# ---------------------------------------------------------------------------


def _reference_rows(category: str, cset: dict) -> list[dict[str, Any]]:
    rows = []
    for key, gold in REFERENCE_GOLD["items"].items():
        if KEY_CATEGORIES.get(key) != category:
            continue
        rows.append({
            "item_key": key,
            "item_name": key.replace("_", " ").replace("lodging:night", "a night's lodging"),
            "category": category,
            "avg_price": float(currency.from_legacy_gold(gold, cset)),
        })
    return rows


def alternatives(
    offer: dict, *, index_rows: list[dict], venue_kind: str, cset: dict, multiplier: dict | None = None
) -> list[dict[str, Any]]:
    """Up to MAX_ALTERNATIVES suggestions: a cheaper item of the same category (unit price under 0.8 of the
    asking unit), a better one (over 1.25), then the other categories this venue kind sells."""
    category = str(offer.get("category") or "misc")
    own_key = str(offer.get("item_key") or "")
    quantity = max(1, _int(offer.get("quantity"), 1))
    asking_unit = _int(offer.get("asking_price")) // quantity if _int(offer.get("asking_price")) else _int(offer.get("unit_price"))
    mult = _mult_value(multiplier)
    seen = {own_key}
    candidates: list[dict[str, Any]] = []
    for row in list(index_rows or []) + _reference_rows(category, cset):
        key = str(_field(row, "item_key", "") or "")
        if not key or key in seen or str(_field(row, "category", "") or "") != category:
            continue
        seen.add(key)
        price = _price_round(float(_field(row, "avg_price", 0) or 0) * mult)
        candidates.append({
            "item_key": key,
            "item_name": str(_field(row, "item_name", "") or key),
            "category": category,
            "unit_price": price,
        })
    cheaper = sorted((c for c in candidates if c["unit_price"] < asking_unit * 0.8), key=lambda c: c["unit_price"])
    better = sorted((c for c in candidates if c["unit_price"] > asking_unit * 1.25), key=lambda c: c["unit_price"])
    out: list[dict[str, Any]] = []
    if cheaper:
        pick = cheaper[0]
        out.append({**pick, "kind": "cheaper", "display": _display(pick["unit_price"], cset),
                    "reason": f"{pick['item_name']} is cheaper at {_display(pick['unit_price'], cset)}"})
    if better:
        pick = better[0]
        out.append({**pick, "kind": "better", "display": _display(pick["unit_price"], cset),
                    "reason": f"{pick['item_name']} is the finer article at {_display(pick['unit_price'], cset)}"})
    kind = normalize_kind(venue_kind) or str(venue_kind or "").strip().lower()
    for other in economy.VENUE_CATEGORIES.get(kind, ()):
        if len(out) >= MAX_ALTERNATIVES:
            break
        if other == category:
            continue
        gold = REFERENCE_GOLD["categories"].get(other)
        price = _price_round(currency.from_legacy_gold(gold, cset) * mult) if gold is not None else 0
        out.append({
            "kind": "other",
            "item_name": other,
            "item_key": "",
            "category": other,
            "unit_price": price,
            "display": _display(price, cset) if price else "",
            "reason": f"this {kind.replace('_', ' ')} also sells {other}",
        })
    return out[:MAX_ALTERNATIVES]


def alternatives_for(
    conn: sqlite3.Connection, offer_id: int, *, venue_kind: str, cset: dict, day: int, seed: int | None = None
) -> list[dict[str, Any]]:
    """Fetch the same-category price_index rows and the market multiplier, then alternatives(). [] when
    the offer does not exist."""
    ensure_schema(conn)
    offer = get_offer(conn, offer_id)
    if offer is None:
        return []
    rows = [
        dict(row)
        for row in conn.execute("SELECT * FROM price_index WHERE category = ? ORDER BY avg_price", (offer["category"],)).fetchall()
    ]
    multiplier = economy.settlement_multiplier(
        conn, offer["settlement_id"], offer["category"], day=max(1, _int(day, 1)), seed=seed
    )
    return alternatives(offer, index_rows=rows, venue_kind=venue_kind, cset=cset, multiplier=multiplier)


# ---------------------------------------------------------------------------
# Typed answers (pure)
# ---------------------------------------------------------------------------


def _pick_offer(open_rows: list[dict], line: str) -> dict | None:
    rows = [{**row, "title": str(row.get("item_name") or "")} for row in open_rows if isinstance(row, dict)]
    if not rows:
        return None
    chosen = typed_offer_choice(rows, line)
    if chosen is not None:
        return chosen
    low = line.lower()
    for row in rows:
        title = row["title"].lower()
        if title and title in low:
            return row
    if len(rows) == 1:
        return rows[0]
    return None


def answer_from_line(open_rows: list[dict], line: str, *, cset: dict) -> dict[str, Any] | None:
    """{"offer_id", "action": accept | decline | haggle, "bid"} for a typed answer, or None.

    The row is the one local_intel.typed_offer_choice picks (the line names its item, or it is the only
    open offer). Decline words are read first, then an amount under the price on the table is a haggle
    bid, then accept words; an amount at or above the price is an accept. A bare "deal", "done" or
    "agreed" only accepts when the line is not a question and is short (ACCEPT_BARE_MAX_WORDS words at
    most), names the item or names a coin; the longer accept phrases accept wherever they stand.
    """
    text = strip_negated_clauses(str(line or ""))
    if not text.strip():
        return None
    row = _pick_offer(open_rows, text)
    if row is None:
        return None
    on_table = _int(row.get("counter_price")) or _int(row.get("total_price"))
    if _DECLINE_WORDS_RE.search(text):
        return {"offer_id": _int(row.get("id")), "action": "decline", "bid": None}
    found = currency.parse_amount(text, cset)
    if found and _int(found.get("units")) > 0:
        units = _int(found.get("units"))
        if units < on_table:
            return {"offer_id": _int(row.get("id")), "action": "haggle", "bid": units}
        return {"offer_id": _int(row.get("id")), "action": "accept", "bid": None}
    if _ACCEPT_PHRASES_RE.search(text):
        return {"offer_id": _int(row.get("id")), "action": "accept", "bid": None}
    if _ACCEPT_BARE_RE.search(text) and "?" not in text:
        low = text.lower()
        words = _words(low)
        short = len(re.findall(r"[a-z']+", low)) <= ACCEPT_BARE_MAX_WORDS
        names_item = bool(_text(row.get("item_name"))) and _text(row.get("item_name")).lower() in low
        names_coin = any(word in words for word in currency.coin_words(cset) if " " not in word)
        if short or names_item or names_coin:
            return {"offer_id": _int(row.get("id")), "action": "accept", "bid": None}
    return None


# ---------------------------------------------------------------------------
# Fulfilment (pure)
# ---------------------------------------------------------------------------


def _is_thing(offer: dict) -> bool:
    return str(offer.get("category") or "") not in NON_ITEM_CATEGORIES and str(offer.get("item_key") or "") not in NON_ITEM_KEYS


def fulfilment_proposal(offer: dict, *, cset: dict, seller_name: str = "") -> dict[str, Any]:
    """What an accepted offer changes, as proposals the wiring applies: money in units and in legacy gold,
    InventoryChange rows, the relationship event, a JournalNote and the ledger entry. A service or barter
    offer hands the goods over and leaves the money to agreements. Not accepted gives {"error": ...}."""
    status = str(offer.get("status") or "")
    if status != "accepted":
        return {"error": "not_accepted", "status": status}
    kind = str(offer.get("kind") or "buy")
    quantity = max(1, _int(offer.get("quantity"), 1))
    total = max(0, _int(offer.get("total_price")))
    name = str(offer.get("item_name") or "")
    who = _text(seller_name) or "the seller"
    shown = _display(total, cset)
    item_type = ITEM_TYPE_BY_CATEGORY.get(str(offer.get("category") or ""), "misc")
    if kind in ("service", "barter"):
        return {
            "money_delta_units": 0,
            "gold_delta_legacy": 0,
            "inventory_changes": [
                {"name": g["item_name"], "quantity_delta": -g["quantity"], "source": "trade", "reason": "hand_over"}
                for g in offer.get("goods_given") or []
            ],
            "relationship_event": "traded_npc",
            "npc_id": _int(offer.get("seller_npc_id")),
            "journal": {"kind": "trade", "content": f"Agreed {kind} terms with {who} for {name}."[:900]},
            "ledger": None,
            "agreement": True,
        }
    sign = -1 if kind == "buy" else 1
    changes: list[dict[str, Any]] = []
    if _is_thing(offer):
        change: dict[str, Any] = {
            "name": name,
            "quantity_delta": quantity if kind == "buy" else -quantity,
            "source": "trade",
            "reason": "offer_accepted",
        }
        if kind == "buy":
            change["item_type"] = item_type
        changes.append(change)
    verb = "Bought" if kind == "buy" else "Sold"
    preposition = "from" if kind == "buy" else "to"
    return {
        "money_delta_units": sign * total,
        "gold_delta_legacy": currency.to_legacy_gold(sign * total, cset),
        "inventory_changes": changes,
        "relationship_event": "traded_npc",
        "npc_id": _int(offer.get("seller_npc_id")),
        "journal": {"kind": "trade", "content": f"{verb} {quantity} {name} for {shown} {preposition} {who}."[:900]},
        "ledger": {
            "item_name": name,
            "unit_price": max(1, total // quantity),
            "quantity": quantity,
            "source": "offer_accepted",
        },
        "agreement": False,
    }
