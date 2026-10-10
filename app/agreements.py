"""Goods-for-service agreements with terms, due times, leftovers and a lifecycle over world time.

Status: built, not wired (TODO n18).

"I'll give you these 15 iron ore if you forge me a blade; anything left over you keep." is an agreements
row: what each side gives, the work owed, when it is due (absolute world minutes), the leftovers policy.
It is proposed and haggled as an app.trade offer of kind "service" or "barter", so Accept / Refuse /
Haggle are the same objects; agree() turns the accepted terms into a row. The module writes only its own
two tables, agreements and agreement_events, and no settings row. Handing goods over, the work finishing
and the delivery are proposals (inventory changes, a money delta in units, journal notes and world-event
proposals) that a wiring pass applies; tick() only moves states when the clock says so. Nothing here
touches the player, inventory, npcs, journal or trade tables, and the live game does not call anything in
this file.

Wiring (not done):
  app/world.py:advance_world_time() -> after the tick_weather call and before the return, in the shape of
      the tick_quest_clocks call (try/except, gated by playthrough_options.agreements_enabled):
      result = agreements.tick(conn, world_time=after, turn=_turn_value(conn)); its event_proposals go to
      queue_world_event(**proposal), its journal entries ({kind, content}, one per ready / lapsed / forfeit
      row) to INSERT INTO journal (turn, kind, content), and its lines (engine text and diagnostics) to the log.
  app/world.py:apply_turn() -> where an accepted trade offer of kind service or barter is settled:
      row = agreements.agree(conn, terms=terms, offer_id=offer["id"], turn=turn, world_time=get_world_time(conn)),
      then _apply_inventory(conn, agreements.hand_over_proposal(row)["inventory_changes"]) (engine-authored,
      so it bypasses _filter_inventory_changes) and agreements.mark_handed_over(conn, row["id"], world_time=..., turn=turn).
  app/world.py:apply_turn() -> after the clock has advanced, for each open row in ready or lapsed whose
      location_id is the player's: _apply_inventory(conn, agreements.delivery_proposal(row)["inventory_changes"])
      then agreements.mark_delivered(conn, row["id"], world_time=..., turn=turn).
  app/world.py:get_state() -> beside state["open_quest_offers"]:
      state["agreements"] = agreements.state_view(conn, world_time=state["world_time"], cset=currency.active_set(conn))["agreements"].
  app/world.py:build_prompt_context() -> beside the open_leads block, in its shape (try/except, a short-lived connection):
      with connect() as c_agr: block = agreements.prompt_block(agreements.open_agreements(c_agr), state["world_time"], currency.active_set(c_agr))
      stored as prompt_context["agreements_block"] when it is not ""; the prompt builder prints it where it prints open_leads.
  app/main.py:_answer_offer() -> the same shape for GET /api/agreements (open_agreements + state_view) and
      POST /api/agreements/{id}/cancel through agreements.cancel(conn, id, world_time=..., turn=turn, by="player"), 409 when None.

Turn on:
  [ ] playthrough_options.agreements_enabled (default off; needs trade_offers_enabled); read by the wiring, never here
  [ ] app/db.py:_migrate_columns(): try: from app.agreements import ensure_schema; ensure_schema(conn) except Exception: pass
  [ ] app/world.py:WORLD_TABLES + RESTORE_ORDER + AUTOINC_TABLES gain agreements and agreement_events;
      _clear_playthrough deletes from both; export/import carry them with the other WORLD_TABLES
  [ ] routes: GET /api/agreements, POST /api/agreements/{id}/cancel on the _answer_offer pattern
  [ ] UI: a list in the Quests tab (Offered / Active / Agreements); the offer strip already covers the trade offer
  [ ] prompt: the prompt_block line above; nothing else

Tests: tests/test_agreements.py
"""
from __future__ import annotations

import copy
import json
import math
import re
import sqlite3
from typing import Any

from app import currency, trade
from app.player_resources import world_abs_minutes
from app.relationships import RELATIONSHIP_EVENTS

# ---------------------------------------------------------------------------
# Constants and rules tables (data)
# ---------------------------------------------------------------------------

STATES: tuple[str, ...] = ("agreed", "in_progress", "ready", "lapsed", "delivered", "cancelled", "forfeit", "disputed")
OPEN_STATES: tuple[str, ...] = ("agreed", "in_progress", "ready", "lapsed")
TERMINAL_STATES: tuple[str, ...] = ("delivered", "cancelled", "forfeit", "disputed")
KINDS: tuple[str, ...] = ("goods_for_service", "goods_for_goods", "coin_for_service", "service_for_coin")
LEFTOVER_POLICIES: tuple[str, ...] = ("counterparty_keeps", "returned", "split", "forfeit")

# The transitions of the lifecycle: (from state, event name, to state). Clock events are applied by
# tick(); the others by the writer of the same name.
TRANSITIONS: tuple[tuple[str, str, str], ...] = (
    ("agreed", "hand_over", "in_progress"),
    ("agreed", "forfeit", "forfeit"),
    ("agreed", "cancel", "cancelled"),
    ("in_progress", "cancel", "cancelled"),
    ("in_progress", "ready", "ready"),
    ("in_progress", "dispute", "disputed"),
    ("ready", "deliver", "delivered"),
    ("ready", "lapse", "lapsed"),
    ("lapsed", "deliver", "delivered"),
)

DEFAULT_GRACE_MINUTES = 1440
LAPSE_AFTER_MINUTES = 7 * 1440
QUEUE_MINUTES_PER_JOB = 480
LABOUR_PER_HOUR_LEGACY_GOLD = 0.25
INSULT_WORK_MULT = 1.5
COUNTER_GOODS_RAISE = 0.25
DEFAULT_CONSUME_FRACTION = 0.6
EVENT_PRIORITY = 5
MAX_WORK_TEXT = 200
MAX_ITEM_NAME = 100
MAX_LINE = 160
MAX_JOURNAL = 900
RELATIONSHIP_EVENT_DELIVERED = "traded_npc"

# Work duration by keyword, first hit wins; then the category default.
WORK_KEYWORD_MINUTES: tuple[tuple[tuple[str, ...], int], ...] = (
    (("sharpen", "hone", "mend", "patch", "stitch", "resole"), 120),
    (("repair", "fix", "reforge", "reset", "fit"), 480),
    (("tan", "cure", "dye", "brew", "distil"), 2880),
    (("forge", "smith", "cast", "temper", "make a blade", "make a sword", "make an axe"), 2880),
    (("build", "construct", "carve", "assemble", "saddle", "cart"), 4320),
    (("armor", "armour", "mail", "plate"), 7200),
    (("copy", "scribe", "translate", "chart", "map"), 1440),
    (("heal", "treat", "set a bone", "physic"), 60),
    (("guide", "escort", "carry", "deliver", "ferry"), 240),
    (("teach", "train", "lesson"), 180),
)
CATEGORY_WORK_MINUTES: dict[str, int] = {
    "services": 240, "weapons": 2880, "armor": 7200, "cloth": 1440, "tools": 480, "medicine": 120,
    "knowledge": 1440, "materials": 1440, "transport": 240,
}
DEFAULT_WORK_MINUTES = 480

# What the work consumes from player_gives: product keywords (on the work text and the counterparty's
# goods) to the alternatives, each a list of (material word, quantity). The first alternative whose every
# material is among the given goods is used; with none, DEFAULT_CONSUME_FRACTION of each given item.
MATERIAL_REQUIREMENTS: tuple[tuple[tuple[str, ...], tuple[tuple[tuple[str, int], ...], ...]], ...] = (
    (("mail", "armor", "armour", "plate"), ((("iron ore", 20),), (("ingot", 8),))),
    (("blade", "sword", "dagger", "knife"), ((("iron ore", 8),), (("ingot", 3),), (("steel", 2),))),
    (("axe", "hammer", "mace"), ((("iron ore", 6),), (("ingot", 2),))),
    (("arrow",), ((("wood", 2), ("feather", 1), ("iron", 1)),)),
    (("shield",), ((("wood", 3), ("iron", 1), ("leather", 1)),)),
    (("boots", "gloves", "belt"), ((("leather", 2),),)),
    (("cloak", "coat", "tunic"), ((("cloth", 3),), (("wool", 3),), (("hide", 2),))),
    (("potion", "salve", "tonic"), ((("herb", 3),),)),
)

# A haggle accepted with the player's bid moves the leftovers one step toward the player.
LEFTOVERS_TOWARD_PLAYER: dict[str, str] = {
    "counterparty_keeps": "split", "split": "returned", "returned": "returned", "forfeit": "forfeit",
}

_AGREEMENTS_SQL = """
CREATE TABLE IF NOT EXISTS agreements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE DEFAULT '',
    status TEXT NOT NULL DEFAULT 'agreed',
    kind TEXT NOT NULL DEFAULT 'goods_for_service',
    counterparty_npc_id INTEGER NOT NULL DEFAULT 0,
    location_id INTEGER NOT NULL DEFAULT 0,
    settlement_id TEXT NOT NULL DEFAULT '',
    offer_id INTEGER NOT NULL DEFAULT 0,
    player_gives TEXT NOT NULL DEFAULT '[]',
    player_pays_units INTEGER NOT NULL DEFAULT 0,
    counterparty_gives TEXT NOT NULL DEFAULT '[]',
    counterparty_pays_units INTEGER NOT NULL DEFAULT 0,
    work TEXT NOT NULL DEFAULT '',
    work_category TEXT NOT NULL DEFAULT 'services',
    work_minutes INTEGER NOT NULL DEFAULT 0,
    made_abs_minute INTEGER NOT NULL DEFAULT 0,
    handed_over_abs_minute INTEGER NOT NULL DEFAULT 0,
    due_abs_minute INTEGER NOT NULL DEFAULT 0,
    ready_abs_minute INTEGER NOT NULL DEFAULT 0,
    closed_abs_minute INTEGER NOT NULL DEFAULT 0,
    grace_minutes INTEGER NOT NULL DEFAULT 1440,
    leftovers_policy TEXT NOT NULL DEFAULT 'counterparty_keeps',
    leftovers TEXT NOT NULL DEFAULT '{}',
    made_turn INTEGER NOT NULL DEFAULT 0,
    closed_turn INTEGER NOT NULL DEFAULT 0,
    currency_set TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""
_AGREEMENTS_INDEX_SQL = "CREATE INDEX IF NOT EXISTS idx_agreements_status ON agreements(status, id)"
_EVENTS_SQL = """
CREATE TABLE IF NOT EXISTS agreement_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agreement_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    abs_minute INTEGER NOT NULL DEFAULT 0,
    turn INTEGER NOT NULL DEFAULT 0,
    detail TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (agreement_id) REFERENCES agreements(id) ON DELETE CASCADE
)
"""
_EVENTS_INDEX_SQL = "CREATE INDEX IF NOT EXISTS idx_agreement_events_agreement ON agreement_events(agreement_id, id)"

_ROW_INT_KEYS: tuple[str, ...] = (
    "id", "counterparty_npc_id", "location_id", "offer_id", "player_pays_units", "counterparty_pays_units",
    "work_minutes", "made_abs_minute", "handed_over_abs_minute", "due_abs_minute", "ready_abs_minute",
    "closed_abs_minute", "grace_minutes", "made_turn", "closed_turn",
)
_ROW_TEXT_KEYS: tuple[str, ...] = (
    "code", "status", "kind", "settlement_id", "work", "work_category", "leftovers_policy", "currency_set",
    "note", "created_at",
)
_GOODS_KEYS: tuple[str, ...] = ("item_key", "item_name", "quantity", "category")
_POLICY_TEXT: dict[str, str] = {
    "counterparty_keeps": "leftovers stay with {who}",
    "returned": "leftovers come back to you",
    "split": "leftovers are split between you",
    "forfeit": "leftovers are forfeit",
}


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


def _clean_name(name: Any) -> str:
    text = re.sub(r"\[[^\]]*\]", " ", str(name or ""))
    return " ".join(text.split())[:MAX_ITEM_NAME]


def _word_pattern(phrase: str) -> re.Pattern[str]:
    return re.compile(r"\b" + re.escape(phrase) + r"(?:e?s)?\b", re.I)


_WORK_RES: tuple[tuple[tuple[re.Pattern[str], ...], int], ...] = tuple(
    (tuple(_word_pattern(word) for word in words), minutes) for words, minutes in WORK_KEYWORD_MINUTES
)
_PRODUCT_RES: tuple[tuple[tuple[re.Pattern[str], ...], tuple[tuple[tuple[str, int], ...], ...]], ...] = tuple(
    (tuple(_word_pattern(word) for word in words), options) for words, options in MATERIAL_REQUIREMENTS
)


def _goods(entries: Any) -> list[dict[str, Any]]:
    """Normalise a goods list to [{item_key, item_name, quantity, category}]; a non-positive quantity is
    ValueError, an entry without a name is skipped."""
    out: list[dict[str, Any]] = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        name = _clean_name(entry.get("item_name") or entry.get("name") or "")
        if not name:
            continue
        quantity = _int(entry.get("quantity"), 0)
        if quantity < 1:
            raise ValueError(f"quantity must be at least 1 for {name!r}, got {entry.get('quantity')!r}")
        out.append({
            "item_key": _text(entry.get("item_key")) or trade.item_key(name),
            "item_name": name,
            "quantity": quantity,
            "category": _text(entry.get("category")).lower() or trade.categorize(name),
        })
    return out


def _goods_text(entries: list[dict[str, Any]]) -> str:
    parts = [f"{_int(g.get('quantity'), 1)} {g.get('item_name') or g.get('item_key') or 'goods'}" for g in entries]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def _span_label(minutes: int) -> str:
    """A plain span: "2 days", "1 day 4 hours", "3 hours", "40 minutes"."""
    total = abs(int(minutes))
    if total < 1:
        return "now"
    days, rest = divmod(total, 1440)
    hours, mins = divmod(rest, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days} day" if days == 1 else f"{days} days")
    if hours and (days < 7):
        parts.append(f"{hours} hour" if hours == 1 else f"{hours} hours")
    if not days and not hours:
        parts.append(f"{mins} minute" if mins == 1 else f"{mins} minutes")
    return " ".join(parts)


def _display(units: int, cset: dict) -> str:
    return currency.format_amount(int(units), cset, "long")


def _who(row_or_terms: Any, npc: dict | None = None) -> str:
    name = _text(_field(npc, "name", "")) or _text(_field(row_or_terms, "counterparty_name", ""))
    return name or "the other party"


def _cset_for(row: Any, cset: dict | None) -> dict[str, Any]:
    """The currency set a proposal formats money with: the given one, else the row's own set id, else the
    default set."""
    if isinstance(cset, dict) and cset.get("denominations"):
        return cset
    try:
        return currency.theme_set(_text(_field(row, "currency_set", "")) or currency.DEFAULT_SET)
    except ValueError:
        return currency.theme_set(currency.DEFAULT_SET)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create agreements and agreement_events when missing. Idempotent; no commit here."""
    conn.execute(_AGREEMENTS_SQL)
    conn.execute(_AGREEMENTS_INDEX_SQL)
    conn.execute(_EVENTS_SQL)
    conn.execute(_EVENTS_INDEX_SQL)


# ---------------------------------------------------------------------------
# Terms (pure)
# ---------------------------------------------------------------------------


def estimate_work_minutes(work: str, category: str = "") -> int:
    """Minutes the work takes: the first WORK_KEYWORD_MINUTES hit on the work text, else the category
    default, else DEFAULT_WORK_MINUTES."""
    text = _text(work).lower()
    if text:
        for patterns, minutes in _WORK_RES:
            if any(p.search(text) for p in patterns):
                return minutes
    return CATEGORY_WORK_MINUTES.get(_text(category).lower(), DEFAULT_WORK_MINUTES)


def _match_material(word: str, given: list[dict[str, Any]]) -> dict[str, Any] | None:
    pattern = _word_pattern(word)
    for entry in given:
        if pattern.search(str(entry.get("item_key") or "")) or pattern.search(str(entry.get("item_name") or "")):
            return entry
    return None


def material_requirements(work: str, counterparty_gives: list[dict], player_gives: list[dict]) -> list[dict[str, Any]]:
    """What the work consumes from player_gives, as [{item_key, quantity}] keyed by the given items.

    The product is read from the work text and the counterparty's goods; the first MATERIAL_REQUIREMENTS
    alternative whose every material is among the given goods is used. Otherwise, and for any product the
    table does not know, DEFAULT_CONSUME_FRACTION of each given item is consumed, rounded up.
    """
    given = _goods(player_gives)
    if not given:
        return []
    product_text = " ".join([_text(work)] + [str(g.get("item_name") or "") for g in _goods(counterparty_gives)]).lower()
    for patterns, options in _PRODUCT_RES:
        if not any(p.search(product_text) for p in patterns):
            continue
        for option in options:
            matched: list[dict[str, Any]] = []
            for word, quantity in option:
                entry = _match_material(word, given)
                if entry is None:
                    break
                matched.append({"item_key": entry["item_key"], "quantity": int(quantity)})
            if len(matched) == len(option):
                return matched
        break
    return [{"item_key": g["item_key"], "quantity": int(math.ceil(g["quantity"] * DEFAULT_CONSUME_FRACTION))} for g in given]


def compute_leftovers(given: list[dict], required: list[dict], policy: str) -> dict[str, list[dict[str, Any]]]:
    """given minus required per item (never below 0), routed by the policy: counterparty_keeps and forfeit
    send everything to the counterparty, returned everything to the player, split gives the player
    floor(left / 2). Unknown policy is ValueError."""
    policy_word = _text(policy).lower()
    if policy_word not in LEFTOVER_POLICIES:
        raise ValueError(f"unknown leftovers policy: {policy!r}")
    needed: dict[str, int] = {}
    for entry in required or []:
        if isinstance(entry, dict):
            key = _text(entry.get("item_key"))
            if key:
                needed[key] = needed.get(key, 0) + max(0, _int(entry.get("quantity")))
    to_counterparty: list[dict[str, Any]] = []
    to_player: list[dict[str, Any]] = []
    for entry in _goods(given):
        left = max(0, entry["quantity"] - needed.get(entry["item_key"], 0))
        if left <= 0:
            continue
        if policy_word == "returned":
            player_share, counterparty_share = left, 0
        elif policy_word == "split":
            player_share = left // 2
            counterparty_share = left - player_share
        else:
            player_share, counterparty_share = 0, left
        if player_share:
            to_player.append({"item_key": entry["item_key"], "item_name": entry["item_name"], "quantity": player_share})
        if counterparty_share:
            to_counterparty.append({"item_key": entry["item_key"], "item_name": entry["item_name"], "quantity": counterparty_share})
    return {"to_counterparty": to_counterparty, "to_player": to_player}


def _reference_value(entries: list[dict[str, Any]], cset: dict) -> int:
    total = 0
    for entry in entries:
        price = trade.reference_price(str(entry.get("item_name") or ""), cset, category=str(entry.get("category") or ""))
        if price is None:
            price = trade.reference_price(str(entry.get("item_name") or ""), cset, category="misc") or 0
        total += int(price) * max(1, _int(entry.get("quantity"), 1))
    return total


def queue_minutes(open_count_for_npc: int) -> int:
    """How much later the work starts when the counterparty already has jobs in hand."""
    return QUEUE_MINUTES_PER_JOB * max(0, _int(open_count_for_npc))


def fair_value_units(terms: dict, cset: dict) -> int:
    """The fair value of the deal to the player in units: the reference value of counterparty_gives plus
    labour (work_minutes at LABOUR_PER_HOUR_LEGACY_GOLD an hour), minus the reference value of the
    leftovers the counterparty keeps under the policy; never below 0, rounded with currency.round_price."""
    counterparty_gives = _goods(terms.get("counterparty_gives"))
    player_gives = _goods(terms.get("player_gives"))
    hours = max(0, _int(terms.get("work_minutes"))) / 60.0
    labour = currency.from_legacy_gold(hours * LABOUR_PER_HOUR_LEGACY_GOLD, cset) if hours else 0
    required = terms.get("required")
    if not isinstance(required, list):
        required = material_requirements(str(terms.get("work") or ""), counterparty_gives, player_gives)
    policy = _text(terms.get("leftovers_policy")).lower() or "counterparty_keeps"
    kept = compute_leftovers(player_gives, required, policy)["to_counterparty"]
    kept_value = _reference_value(
        [{**entry, "category": next((g["category"] for g in player_gives if g["item_key"] == entry["item_key"]), "")} for entry in kept],
        cset,
    )
    value = _reference_value(counterparty_gives, cset) + int(labour) - kept_value
    return currency.round_price(max(0, int(value)))


def _infer_kind(*, player_gives: list, player_pays_units: int, counterparty_gives: list, counterparty_pays_units: int, work: str) -> str:
    if counterparty_pays_units > 0 and not player_gives and not counterparty_gives and player_pays_units <= 0:
        return "service_for_coin"
    if player_gives and counterparty_gives and not work:
        return "goods_for_goods"
    if player_pays_units > 0 and not player_gives:
        return "coin_for_service"
    if player_gives:
        return "goods_for_service"
    raise ValueError("an agreement needs something given on at least one side")


def _validate_terms(terms: dict) -> None:
    if not isinstance(terms, dict):
        raise ValueError("terms must be a dict from draft_terms")
    if _text(terms.get("kind")) not in KINDS:
        raise ValueError(f"unknown agreement kind: {terms.get('kind')!r}")
    if _text(terms.get("leftovers_policy")).lower() not in LEFTOVER_POLICIES:
        raise ValueError(f"unknown leftovers policy: {terms.get('leftovers_policy')!r}")
    for key in ("player_pays_units", "counterparty_pays_units"):
        if _int(terms.get(key)) < 0:
            raise ValueError(f"{key} may not be negative")
    player_gives = _goods(terms.get("player_gives"))
    counterparty_gives = _goods(terms.get("counterparty_gives"))
    if not player_gives and not counterparty_gives and _int(terms.get("player_pays_units")) <= 0 and _int(terms.get("counterparty_pays_units")) <= 0:
        raise ValueError("an agreement needs something given on at least one side")
    if _text(terms.get("kind")) != "goods_for_goods" and not _text(terms.get("work")):
        raise ValueError("an agreement for work needs the work named")
    if _int(terms.get("work_minutes")) < 0:
        raise ValueError("work_minutes may not be negative")


def draft_terms(
    *,
    player_gives: list[dict] | None = None,
    player_pays_units: int = 0,
    counterparty_gives: list[dict] | None = None,
    counterparty_pays_units: int = 0,
    work: str,
    counterparty_npc_id: int = 0,
    location_id: int = 0,
    settlement_id: str = "",
    leftovers_policy: str = "counterparty_keeps",
    cset: dict,
    open_jobs_for_npc: int = 0,
    note: str = "",
) -> dict[str, Any]:
    """AgreementTerms: the kind inferred from what each side gives, the work duration, what the work
    consumes, the queue behind the counterparty's other jobs and the fair value. Nothing given on either
    side, a non-positive quantity, a negative amount or an unknown policy is ValueError."""
    gives = _goods(player_gives)
    receives = _goods(counterparty_gives)
    pays = _int(player_pays_units)
    paid = _int(counterparty_pays_units)
    if pays < 0 or paid < 0:
        raise ValueError("amounts may not be negative")
    policy = _text(leftovers_policy).lower() or "counterparty_keeps"
    if policy not in LEFTOVER_POLICIES:
        raise ValueError(f"unknown leftovers policy: {leftovers_policy!r}")
    work_text = _text(work)[:MAX_WORK_TEXT]
    kind = _infer_kind(player_gives=gives, player_pays_units=pays, counterparty_gives=receives,
                       counterparty_pays_units=paid, work=work_text)
    if kind != "goods_for_goods" and not work_text:
        raise ValueError("an agreement for work needs the work named")
    if receives:
        work_category = str(receives[0]["category"])
    elif work_text:
        work_category = trade.categorize(work_text)
    else:
        work_category = "services"
    terms: dict[str, Any] = {
        "kind": kind,
        "player_gives": gives,
        "player_pays_units": pays,
        "counterparty_gives": receives,
        "counterparty_pays_units": paid,
        "work": work_text,
        "work_category": work_category,
        "work_minutes": estimate_work_minutes(work_text, work_category) if work_text else 0,
        "queue_minutes": queue_minutes(open_jobs_for_npc),
        "due_abs_minute": 0,
        "leftovers_policy": policy,
        "required": material_requirements(work_text, receives, gives),
        "grace_minutes": DEFAULT_GRACE_MINUTES,
        "counterparty_npc_id": _int(counterparty_npc_id),
        "location_id": _int(location_id),
        "settlement_id": _text(settlement_id),
        "currency_set": _text(cset.get("id")),
        "value_units": 0,
        "note": _text(note)[:300],
    }
    terms["value_units"] = fair_value_units(terms, cset)
    return terms


def terms_as_offer(terms: dict, *, turn: int, cset: dict) -> dict[str, Any]:
    """The trade Offer (pure, id 0) the terms are haggled as: kind service when work is owed, barter for
    goods for goods; the asking price is value_units and goods_given is player_gives."""
    _validate_terms(terms)
    work_text = _text(terms.get("work"))
    receives = _goods(terms.get("counterparty_gives"))
    item_name = work_text or (receives[0]["item_name"] if receives else "exchange of goods")
    return trade.make_offer(
        kind="service" if work_text else "barter",
        item_name=item_name,
        quantity=1,
        unit_price=max(0, _int(terms.get("value_units"))),
        cset=cset,
        seller_npc_id=_int(terms.get("counterparty_npc_id")),
        location_id=_int(terms.get("location_id")),
        settlement_id=_text(terms.get("settlement_id")),
        turn=_int(turn),
        category=_text(terms.get("work_category")) or "services",
        goods_given=_goods(terms.get("player_gives")),
        price_basis="reference",
        note=_text(terms.get("note")),
    )


def haggle_terms(terms: dict, haggle: dict) -> dict[str, Any]:
    """New terms after one trade HaggleResult: accept takes the bid as value_units and, when the player
    gave more than the work needs, moves the leftovers one step toward the player; counter asks a quarter
    more goods, or split instead of returned; insulted sets forfeit and slows the work by half; refuse
    leaves the terms as they were."""
    out = copy.deepcopy(terms)
    decision = _text(_field(haggle, "decision", "")).lower()
    price = _int(_field(haggle, "price", out.get("value_units")))
    if decision == "accept":
        out["value_units"] = max(0, price)
        given = {g["item_key"]: g["quantity"] for g in _goods(out.get("player_gives"))}
        needed: dict[str, int] = {}
        for entry in out.get("required") or []:
            if isinstance(entry, dict):
                needed[_text(entry.get("item_key"))] = needed.get(_text(entry.get("item_key")), 0) + _int(entry.get("quantity"))
        if any(quantity > needed.get(key, 0) for key, quantity in given.items()):
            out["leftovers_policy"] = LEFTOVERS_TOWARD_PLAYER.get(_text(out.get("leftovers_policy")), "counterparty_keeps")
    elif decision == "counter":
        out["value_units"] = max(0, price)
        if _text(out.get("leftovers_policy")) == "returned":
            out["leftovers_policy"] = "split"
        else:
            out["player_gives"] = [
                {**g, "quantity": int(math.ceil(g["quantity"] * (1.0 + COUNTER_GOODS_RAISE)))}
                for g in _goods(out.get("player_gives"))
            ]
            out["required"] = material_requirements(_text(out.get("work")), _goods(out.get("counterparty_gives")), out["player_gives"])
    elif decision == "insulted":
        out["leftovers_policy"] = "forfeit"
        out["work_minutes"] = int(round(max(0, _int(out.get("work_minutes"))) * INSULT_WORK_MULT))
    return out


def terms_line(terms: dict, cset: dict, *, npc_name: str = "") -> str:
    """One plain sentence for the engine: "You give 15 iron ore; Bertram will forge a blade, taking 2 days;
    leftovers stay with Bertram."."""
    who = _text(npc_name) or "the other party"
    parts: list[str] = []
    gives = _goods(terms.get("player_gives"))
    pays = _int(terms.get("player_pays_units"))
    you: list[str] = []
    if gives:
        you.append(f"give {_goods_text(gives)}")
    if pays > 0:
        you.append(f"pay {_display(pays, cset)}")
    if you:
        parts.append("You " + " and ".join(you))
    work_text = _text(terms.get("work"))
    receives = _goods(terms.get("counterparty_gives"))
    paid = _int(terms.get("counterparty_pays_units"))
    them: list[str] = []
    kind = _text(terms.get("kind"))
    if work_text and kind == "service_for_coin":
        parts.append(f"you will {work_text}")
    elif work_text:
        span = _span_label(_int(terms.get("work_minutes")) + _int(terms.get("queue_minutes")))
        them.append(f"will {work_text}, taking {span}")
    if receives and (kind == "goods_for_goods" or not work_text):
        them.append(f"gives {_goods_text(receives)}")
    if paid > 0:
        them.append(f"pays {_display(paid, cset)}")
    if them:
        parts.append(f"{who} " + " and ".join(them))
    if gives and work_text:
        parts.append(_POLICY_TEXT.get(_text(terms.get("leftovers_policy")), "leftovers stay with {who}").format(who=who))
    return "; ".join(parts) + "."


# ---------------------------------------------------------------------------
# Rows
# ---------------------------------------------------------------------------


def _decode_goods(raw: Any, *, strict: bool) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(raw or "[]")
    except (TypeError, ValueError):
        if strict:
            raise ValueError("goods column is not valid JSON")
        parsed = []
    if not isinstance(parsed, list):
        if strict:
            raise ValueError("goods column is not a list")
        parsed = []
    out: list[dict[str, Any]] = []
    for entry in parsed:
        if not isinstance(entry, dict):
            continue
        name = _clean_name(entry.get("item_name") or "")
        if not name:
            continue
        out.append({
            "item_key": _text(entry.get("item_key")) or trade.item_key(name),
            "item_name": name,
            "quantity": max(1, _int(entry.get("quantity"), 1)),
            "category": _text(entry.get("category")).lower() or trade.categorize(name),
        })
    return out


def _decode_row(row: Any, *, strict: bool = False, counterparty_name: str = "") -> dict[str, Any]:
    source = dict(row)
    out: dict[str, Any] = {}
    for key in _ROW_INT_KEYS:
        out[key] = _int(source.get(key))
    for key in _ROW_TEXT_KEYS:
        out[key] = str(source.get(key) or "")
    out["player_gives"] = _decode_goods(source.get("player_gives"), strict=strict)
    out["counterparty_gives"] = _decode_goods(source.get("counterparty_gives"), strict=strict)
    try:
        leftovers = json.loads(source.get("leftovers") or "{}")
    except (TypeError, ValueError):
        if strict:
            raise ValueError("leftovers column is not valid JSON")
        leftovers = {}
    out["leftovers"] = leftovers if isinstance(leftovers, dict) else {}
    out["required"] = material_requirements(out["work"], out["counterparty_gives"], out["player_gives"])
    out["counterparty_name"] = _text(counterparty_name)
    return out


def _npc_name(conn: sqlite3.Connection, npc_id: int) -> str:
    """The counterparty's name, read only; "" when the id is 0 or unknown."""
    if _int(npc_id) <= 0:
        return ""
    try:
        row = conn.execute("SELECT id, name, role FROM npcs WHERE id = ?", (_int(npc_id),)).fetchone()
    except sqlite3.Error:
        return ""
    return _text(row["name"]) if row else ""


def _load(conn: sqlite3.Connection, agreement_id: int, *, strict: bool = False) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM agreements WHERE id = ?", (_int(agreement_id),)).fetchone()
    if row is None:
        return None
    return _decode_row(row, strict=strict, counterparty_name=_npc_name(conn, row["counterparty_npc_id"]))


def _event(conn: sqlite3.Connection, agreement_id: int, kind: str, *, abs_minute: int, turn: int, detail: dict | None = None) -> None:
    conn.execute(
        "INSERT INTO agreement_events (agreement_id, kind, abs_minute, turn, detail) VALUES (?, ?, ?, ?, ?)",
        (_int(agreement_id), str(kind)[:40], _int(abs_minute), _int(turn), json.dumps(detail or {}, ensure_ascii=True)[:2000]),
    )


def _jobs_ahead(conn: sqlite3.Connection, npc_id: int, *, before_id: int = 0) -> int:
    """Open jobs the counterparty already has in hand (agreed or in progress). With before_id, only the jobs
    ahead of that row count: every job already in progress and the agreed ones made before it; agreed jobs
    made after it stand behind it in the queue."""
    if _int(npc_id) <= 0:
        return 0
    if _int(before_id) > 0:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM agreements WHERE counterparty_npc_id = ? AND id != ? "
            "AND (status = 'in_progress' OR (status = 'agreed' AND id < ?))",
            (_int(npc_id), _int(before_id), _int(before_id)),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM agreements WHERE counterparty_npc_id = ? AND status IN ('agreed', 'in_progress')",
            (_int(npc_id),),
        ).fetchone()
    return int(row["n"]) if row else 0


# ---------------------------------------------------------------------------
# Lifecycle (writers; each touches only agreements and agreement_events)
# ---------------------------------------------------------------------------


def agree(conn: sqlite3.Connection, *, terms: dict, offer_id: int = 0, turn: int, world_time: dict) -> dict[str, Any]:
    """Insert the agreed terms as a row in status agreed with code G{id}: made now, due at made plus the
    queue behind the counterparty's other jobs plus the work, and an "agree" event. Invalid terms are
    ValueError. The queue is the larger of the terms' own queue_minutes and the open jobs counted here."""
    ensure_schema(conn)
    _validate_terms(terms)
    now = world_abs_minutes(world_time)
    gives = _goods(terms.get("player_gives"))
    receives = _goods(terms.get("counterparty_gives"))
    npc_id = _int(terms.get("counterparty_npc_id"))
    queue = max(_int(terms.get("queue_minutes")), queue_minutes(_jobs_ahead(conn, npc_id)))
    work_minutes = max(0, _int(terms.get("work_minutes")))
    due = now + queue + work_minutes
    cur = conn.execute(
        """
        INSERT INTO agreements
            (status, kind, counterparty_npc_id, location_id, settlement_id, offer_id, player_gives,
             player_pays_units, counterparty_gives, counterparty_pays_units, work, work_category, work_minutes,
             made_abs_minute, due_abs_minute, grace_minutes, leftovers_policy, made_turn, currency_set, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "agreed", _text(terms.get("kind")), npc_id, _int(terms.get("location_id")),
            _text(terms.get("settlement_id")), _int(offer_id), json.dumps(gives, ensure_ascii=True),
            max(0, _int(terms.get("player_pays_units"))), json.dumps(receives, ensure_ascii=True),
            max(0, _int(terms.get("counterparty_pays_units"))), _text(terms.get("work"))[:MAX_WORK_TEXT],
            _text(terms.get("work_category")) or "services", work_minutes, now, due,
            max(0, _int(terms.get("grace_minutes"), DEFAULT_GRACE_MINUTES)),
            _text(terms.get("leftovers_policy")).lower(), _int(turn), _text(terms.get("currency_set")),
            _text(terms.get("note"))[:300],
        ),
    )
    new_id = int(cur.lastrowid or 0)
    conn.execute("UPDATE agreements SET code = ? WHERE id = ?", (f"G{new_id}", new_id))
    _event(conn, new_id, "agree", abs_minute=now, turn=turn,
           detail={"offer_id": _int(offer_id), "due_abs_minute": due, "queue_minutes": queue})
    stored = _load(conn, new_id)
    assert stored is not None
    return stored


def get_agreement(conn: sqlite3.Connection, agreement_id: int) -> dict[str, Any] | None:
    """The decoded row (with counterparty_name and the derived required list), or None."""
    ensure_schema(conn)
    return _load(conn, agreement_id)


def open_agreements(conn: sqlite3.Connection, *, npc_id: int | None = None, location_id: int | None = None) -> list[dict[str, Any]]:
    """Rows in OPEN_STATES, oldest first, narrowed by counterparty or location when given."""
    ensure_schema(conn)
    sql = "SELECT * FROM agreements WHERE status IN ('agreed', 'in_progress', 'ready', 'lapsed')"
    params: list[Any] = []
    if npc_id is not None:
        sql += " AND counterparty_npc_id = ?"
        params.append(_int(npc_id))
    if location_id is not None:
        sql += " AND location_id = ?"
        params.append(_int(location_id))
    sql += " ORDER BY id ASC"
    names: dict[int, str] = {}
    out: list[dict[str, Any]] = []
    for row in conn.execute(sql, tuple(params)).fetchall():
        npc = int(row["counterparty_npc_id"] or 0)
        if npc not in names:
            names[npc] = _npc_name(conn, npc)
        out.append(_decode_row(row, counterparty_name=names[npc]))
    return out


def mark_handed_over(conn: sqlite3.Connection, agreement_id: int, *, world_time: dict, turn: int) -> dict[str, Any] | None:
    """agreed -> in_progress once the goods have left the player; the due time is recomputed from now
    (queue behind the counterparty's jobs ahead of this one plus the work). None unless the row is agreed."""
    ensure_schema(conn)
    row = _load(conn, agreement_id)
    if row is None or row["status"] != "agreed":
        return None
    now = world_abs_minutes(world_time)
    queue = queue_minutes(_jobs_ahead(conn, row["counterparty_npc_id"], before_id=row["id"]))
    due = now + queue + row["work_minutes"]
    cur = conn.execute(
        "UPDATE agreements SET status = 'in_progress', handed_over_abs_minute = ?, due_abs_minute = ? WHERE id = ? AND status = 'agreed'",
        (now, due, row["id"]),
    )
    if not cur.rowcount:
        return None
    _event(conn, row["id"], "hand_over", abs_minute=now, turn=turn, detail={"due_abs_minute": due, "queue_minutes": queue})
    return _load(conn, row["id"])


def mark_delivered(conn: sqlite3.Connection, agreement_id: int, *, world_time: dict, turn: int) -> dict[str, Any] | None:
    """ready | lapsed -> delivered, with the leftovers computed and stored. None otherwise."""
    ensure_schema(conn)
    row = _load(conn, agreement_id)
    if row is None or row["status"] not in ("ready", "lapsed"):
        return None
    now = world_abs_minutes(world_time)
    leftovers = compute_leftovers(row["player_gives"], row["required"], row["leftovers_policy"])
    cur = conn.execute(
        """
        UPDATE agreements SET status = 'delivered', closed_abs_minute = ?, closed_turn = ?, leftovers = ?
        WHERE id = ? AND status IN ('ready', 'lapsed')
        """,
        (now, _int(turn), json.dumps(leftovers, ensure_ascii=True), row["id"]),
    )
    if not cur.rowcount:
        return None
    _event(conn, row["id"], "deliver", abs_minute=now, turn=turn, detail={"leftovers": leftovers})
    return _load(conn, row["id"])


def cancel(
    conn: sqlite3.Connection, agreement_id: int, *, world_time: dict, turn: int, by: str = "player", reason: str = ""
) -> dict[str, Any] | None:
    """agreed | in_progress -> cancelled by the player or the counterparty. None otherwise."""
    ensure_schema(conn)
    row = _load(conn, agreement_id)
    if row is None or row["status"] not in ("agreed", "in_progress"):
        return None
    now = world_abs_minutes(world_time)
    cur = conn.execute(
        "UPDATE agreements SET status = 'cancelled', closed_abs_minute = ?, closed_turn = ? WHERE id = ? AND status IN ('agreed', 'in_progress')",
        (now, _int(turn), row["id"]),
    )
    if not cur.rowcount:
        return None
    _event(conn, row["id"], "cancel", abs_minute=now, turn=turn, detail={"by": _text(by) or "player", "reason": _text(reason)[:300]})
    return _load(conn, row["id"])


def dispute(conn: sqlite3.Connection, agreement_id: int, *, world_time: dict, turn: int, reason: str = "") -> dict[str, Any] | None:
    """in_progress -> disputed; the wiring decides when. None otherwise."""
    ensure_schema(conn)
    row = _load(conn, agreement_id)
    if row is None or row["status"] != "in_progress":
        return None
    now = world_abs_minutes(world_time)
    cur = conn.execute(
        "UPDATE agreements SET status = 'disputed', closed_abs_minute = ?, closed_turn = ? WHERE id = ? AND status = 'in_progress'",
        (now, _int(turn), row["id"]),
    )
    if not cur.rowcount:
        return None
    _event(conn, row["id"], "dispute", abs_minute=now, turn=turn, detail={"reason": _text(reason)[:300]})
    return _load(conn, row["id"])


def _event_proposal(row: dict[str, Any], *, turn: int, summary: str) -> dict[str, Any]:
    return {
        "kind": "custom",
        "summary": summary[:1400],
        "trigger": f"agreement:{row['code']}:due",
        "due_turn": _int(turn) + 1,
        "force": False,
        "priority": EVENT_PRIORITY,
        "payload": {"agreement_id": row["id"], "code": row["code"], "status": row["status"]},
    }


def _product_text(row: dict[str, Any]) -> str:
    receives = row.get("counterparty_gives") or []
    if receives:
        return _goods_text(receives)
    return _text(row.get("work")) or "the work"


def tick(conn: sqlite3.Connection, *, world_time: dict, turn: int) -> dict[str, Any]:
    """Apply the clock transitions to every open row: agreed past due plus grace with nothing handed over
    forfeits; in_progress at due becomes ready; ready a week past due lapses. Never raises: a row that
    cannot be read or moved is reported in lines. Returns {ready, lapsed, forfeit, lines, journal,
    event_proposals}: lines is engine text plus diagnostics for the log; journal holds one JournalNote
    {kind "agreement", content} per transition and never a diagnostic."""
    ensure_schema(conn)
    now = world_abs_minutes(world_time)
    out: dict[str, Any] = {"ready": [], "lapsed": [], "forfeit": [], "lines": [], "journal": [], "event_proposals": []}
    try:
        rows = conn.execute(
            "SELECT * FROM agreements WHERE status IN ('agreed', 'in_progress', 'ready') ORDER BY id ASC"
        ).fetchall()
    except sqlite3.Error as exc:
        out["lines"].append(f"Agreements could not be read: {exc}")
        return out
    for raw in rows:
        try:
            row = _decode_row(raw, strict=True, counterparty_name=_npc_name(conn, raw["counterparty_npc_id"]))
            who = _who(row)
            if row["status"] == "agreed" and now >= row["due_abs_minute"] + row["grace_minutes"]:
                cur = conn.execute(
                    "UPDATE agreements SET status = 'forfeit', closed_abs_minute = ?, closed_turn = ? WHERE id = ? AND status = 'agreed'",
                    (now, _int(turn), row["id"]),
                )
                if cur.rowcount:
                    _event(conn, row["id"], "forfeit", abs_minute=now, turn=turn, detail={"due_abs_minute": row["due_abs_minute"]})
                    row = _load(conn, row["id"]) or row
                    out["forfeit"].append(row)
                    line = f"Agreement {row['code']} with {who} is forfeit: nothing was handed over in time."
                    out["lines"].append(line)
                    out["journal"].append({"kind": "agreement", "content": line[:MAX_JOURNAL]})
                    out["event_proposals"].append(_event_proposal(row, turn=turn, summary=line))
                continue
            if row["status"] == "in_progress" and now >= row["due_abs_minute"]:
                cur = conn.execute(
                    "UPDATE agreements SET status = 'ready', ready_abs_minute = ? WHERE id = ? AND status = 'in_progress'",
                    (row["due_abs_minute"], row["id"]),
                )
                if cur.rowcount:
                    _event(conn, row["id"], "ready", abs_minute=now, turn=turn, detail={"due_abs_minute": row["due_abs_minute"]})
                    row = _load(conn, row["id"]) or row
                    out["ready"].append(row)
                    line = f"Agreement {row['code']} with {who} is ready: {_product_text(row)} waits to be collected."
                    out["lines"].append(line)
                    out["journal"].append({"kind": "agreement", "content": line[:MAX_JOURNAL]})
                    out["event_proposals"].append(_event_proposal(row, turn=turn, summary=line))
            if row["status"] == "ready" and now >= row["due_abs_minute"] + LAPSE_AFTER_MINUTES:
                cur = conn.execute(
                    "UPDATE agreements SET status = 'lapsed' WHERE id = ? AND status = 'ready'",
                    (row["id"],),
                )
                if cur.rowcount:
                    _event(conn, row["id"], "lapse", abs_minute=now, turn=turn, detail={"due_abs_minute": row["due_abs_minute"]})
                    row = _load(conn, row["id"]) or row
                    out["lapsed"].append(row)
                    line = f"Agreement {row['code']} with {who} has lapsed: {_product_text(row)} is still held for you."
                    out["lines"].append(line)
                    out["journal"].append({"kind": "agreement", "content": line[:MAX_JOURNAL]})
                    out["event_proposals"].append(_event_proposal(row, turn=turn, summary=line))
        except Exception as exc:  # noqa: BLE001 - a bad row must not stop the clock
            out["lines"].append(f"Agreement {_int(_field(raw, 'id'))} could not be ticked: {exc}")
    return out


def events_for(conn: sqlite3.Connection, agreement_id: int) -> list[dict[str, Any]]:
    """The agreement_events rows of one agreement, oldest first, detail decoded."""
    ensure_schema(conn)
    out: list[dict[str, Any]] = []
    for row in conn.execute(
        "SELECT * FROM agreement_events WHERE agreement_id = ? ORDER BY id ASC", (_int(agreement_id),)
    ).fetchall():
        entry = dict(row)
        try:
            detail = json.loads(entry.get("detail") or "{}")
        except (TypeError, ValueError):
            detail = {}
        entry["detail"] = detail if isinstance(detail, dict) else {}
        out.append(entry)
    return out


# ---------------------------------------------------------------------------
# Proposals (pure)
# ---------------------------------------------------------------------------


def _change(entry: dict[str, Any], sign: int, reason: str) -> dict[str, Any]:
    return {
        "name": str(entry.get("item_name") or entry.get("item_key") or ""),
        "quantity_delta": sign * max(1, _int(entry.get("quantity"), 1)),
        "source": "agreement",
        "reason": reason,
    }


def hand_over_proposal(row: dict, *, npc: dict | None = None, cset: dict | None = None) -> dict[str, Any]:
    """What handing over costs the player: negative InventoryChange rows for player_gives, the coin owed as
    a negative money delta in units, and a JournalNote. Pure; nothing is applied."""
    who = _who(row, npc)
    money = _cset_for(row, cset)
    gives = _goods(row.get("player_gives"))
    pays = max(0, _int(row.get("player_pays_units")))
    handed: list[str] = []
    if gives:
        handed.append(f"Handed {_goods_text(gives)}")
    if pays > 0:
        handed.append(("paid " if handed else "Paid ") + _display(pays, money))
    content = (" and ".join(handed) or "Agreed") + f" to {who} for {_product_text(row)}."
    return {
        "inventory_changes": [_change(g, -1, "hand_over") for g in gives],
        "money_delta_units": -pays,
        "journal": {"kind": "agreement", "content": content[:MAX_JOURNAL]},
    }


def delivery_proposal(row: dict, *, npc: dict | None = None, cset: dict | None = None) -> dict[str, Any]:
    """What the player receives: positive InventoryChange rows for counterparty_gives and the leftovers
    routed to the player, the coin owed to the player, the leftovers, the relationship event and a
    JournalNote. Pure; nothing is applied."""
    who = _who(row, npc)
    money = _cset_for(row, cset)
    gives = _goods(row.get("player_gives"))
    receives = _goods(row.get("counterparty_gives"))
    required = row.get("required")
    if not isinstance(required, list):
        required = material_requirements(str(row.get("work") or ""), receives, gives)
    policy = _text(row.get("leftovers_policy")).lower() or "counterparty_keeps"
    leftovers = compute_leftovers(gives, required, policy)
    changes = [_change(g, +1, "delivery") for g in receives] + [_change(g, +1, "delivery") for g in leftovers["to_player"]]
    paid = max(0, _int(row.get("counterparty_pays_units")))
    work_text = _text(row.get("work")) or "the work"
    if _text(row.get("kind")) == "service_for_coin":
        # The player did the work; the counterparty only pays.
        sentence = f"You finish {work_text} for {who}"
        if paid > 0:
            sentence += f"; {who} pays {_display(paid, money)}"
    else:
        sentence = f"{who} hands you {_goods_text(receives)}" if receives else f"{who} finishes {work_text}"
        if paid > 0:
            sentence += f" and pays {_display(paid, money)}"
    tails: list[str] = []
    if leftovers["to_player"]:
        tails.append(f"{_goods_text(leftovers['to_player'])} come back to you")
    if leftovers["to_counterparty"]:
        tails.append(f"{_goods_text(leftovers['to_counterparty'])} stay with {who}")
    content = sentence + ("; " + "; ".join(tails) if tails else "") + "."
    return {
        "inventory_changes": changes,
        "money_delta_units": paid,
        "leftovers": leftovers,
        "relationship_event": RELATIONSHIP_EVENT_DELIVERED if RELATIONSHIP_EVENT_DELIVERED in RELATIONSHIP_EVENTS else None,
        "npc_id": _int(row.get("counterparty_npc_id")),
        "journal": {"kind": "agreement", "content": content[:MAX_JOURNAL]},
    }


def cancel_proposal(row: dict, *, npc: dict | None = None, now_abs_minute: int | None = None) -> dict[str, Any]:
    """What a cancellation gives back: the goods and coin handed over, unless nothing was handed over, the
    policy is forfeit, or the work was past its halfway point (judged at now_abs_minute, else at the row's
    closed_abs_minute). A row that was handed over but not yet closed needs now_abs_minute; without it the
    progress cannot be judged and ValueError is raised rather than a guess. Pure; nothing is applied."""
    who = _who(row, npc)
    gives = _goods(row.get("player_gives"))
    pays = max(0, _int(row.get("player_pays_units")))
    handed_at = _int(row.get("handed_over_abs_minute"))
    policy = _text(row.get("leftovers_policy")).lower()
    at = _int(now_abs_minute) if now_abs_minute is not None else _int(row.get("closed_abs_minute"))
    if handed_at > 0 and at <= 0:
        raise ValueError("cancel_proposal needs now_abs_minute for a row that is not closed")
    work_minutes = max(0, _int(row.get("work_minutes")))
    past_half = handed_at > 0 and at > 0 and (at - handed_at) * 2 > work_minutes
    returned = handed_at > 0 and policy != "forfeit" and not past_half
    if handed_at <= 0:
        reason = "nothing_handed_over"
    elif policy == "forfeit":
        reason = "forfeit"
    elif past_half:
        reason = "work_past_half"
    else:
        reason = "returned"
    if returned:
        content = f"Agreement with {who} cancelled; {_goods_text(gives) or 'the goods'} come back to you."
    elif handed_at <= 0:
        content = f"Agreement with {who} cancelled before anything changed hands."
    else:
        content = f"Agreement with {who} cancelled; {_goods_text(gives) or 'the goods'} stay with {who}."
    return {
        "inventory_changes": [_change(g, +1, "cancel_return") for g in gives] if returned else [],
        "money_delta_units": pays if returned else 0,
        "returned": returned,
        "reason": reason,
        "journal": {"kind": "agreement", "content": content[:MAX_JOURNAL]},
    }


# ---------------------------------------------------------------------------
# Status (pure)
# ---------------------------------------------------------------------------


def time_left(row: dict, world_time: dict) -> dict[str, Any]:
    """{minutes (negative when overdue), label, phase waiting | ready | overdue} for one row."""
    now = world_abs_minutes(world_time)
    due = _int(row.get("due_abs_minute"))
    status = _text(row.get("status"))
    minutes = due - now
    if status in ("ready", "lapsed"):
        waited = max(0, now - due)
        label = "ready" if waited < 1440 else f"ready, waiting {_span_label(waited)}"
        return {"minutes": minutes, "label": label, "phase": "ready"}
    if status == "agreed":
        minutes = due + _int(row.get("grace_minutes")) - now
    if minutes < 0:
        return {"minutes": minutes, "label": f"overdue {_span_label(-minutes)}", "phase": "overdue"}
    return {"minutes": minutes, "label": _span_label(minutes), "phase": "waiting"}


def _status_line(row: dict, world_time: dict, cset: dict) -> dict[str, Any] | None:
    status = _text(row.get("status"))
    if status not in OPEN_STATES:
        return None
    who = _who(row)
    left = time_left(row, world_time)
    product = _product_text(row)
    head = f"Agreement {row.get('code') or ''} with {who}: "
    if status == "agreed":
        gives = _goods(row.get("player_gives"))
        what = _goods_text(gives) or (_display(_int(row.get("player_pays_units")), cset) if _int(row.get("player_pays_units")) else "the goods")
        if left["phase"] == "overdue":
            severity, text = "serious", f"{what} never handed over; {left['label']}, the deal is about to be forfeit."
        else:
            severity, text = "info", f"{what} not yet handed over; forfeits in {left['label']}."
    elif status == "in_progress":
        if left["phase"] == "overdue":
            severity, text = "serious", f"{product} {left['label']}."
        else:
            severity, text = "info", f"{product} due in {left['label']}."
    elif status == "ready":
        severity, text = "mild", f"ready; collect {product} from {who}."
    else:
        waited = max(0, world_abs_minutes(world_time) - _int(row.get("due_abs_minute")))
        since = f", uncollected for {_span_label(waited)}" if waited >= 1 else ""
        severity, text = "serious", f"lapsed{since}; {product} is still held by {who}."
    line = (head + text).strip()
    if len(line) > MAX_LINE:
        line = line[: MAX_LINE - 1].rstrip() + "."
    return {"key": f"agreement:{row.get('code') or row.get('id')}", "severity": severity, "line": line, "blocks": []}


def status_lines(rows: list[dict], world_time: dict, cset: dict) -> list[dict[str, Any]]:
    """StatusLine rows for the open agreements: info while waiting, mild when ready, serious when overdue
    or lapsed; [] when there is nothing open."""
    out: list[dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        entry = _status_line(row, world_time, cset)
        if entry is not None:
            out.append(entry)
    return out


def prompt_block(rows: list[dict], world_time: dict, cset: dict) -> str:
    """The status lines under "Player agreements (server truth):", one "- " line each; "" when none."""
    lines = status_lines(rows, world_time, cset)
    if not lines:
        return ""
    return "\n".join(["Player agreements (server truth):"] + [f"- {entry['line']}" for entry in lines])


def state_view(conn: sqlite3.Connection, *, world_time: dict, cset: dict) -> dict[str, Any]:
    """{"agreements": [...]} for get_state: one short entry per open row, oldest first."""
    rows = open_agreements(conn)
    out: list[dict[str, Any]] = []
    for row in rows:
        left = time_left(row, world_time)
        gives = _goods_text(row["player_gives"])
        pays = _int(row.get("player_pays_units"))
        if pays > 0:
            gives = (gives + " and " if gives else "") + _display(pays, cset)
        out.append({
            "id": row["id"],
            "code": row["code"],
            "status": row["status"],
            "with_npc_id": row["counterparty_npc_id"],
            "with_name": row["counterparty_name"],
            "work": row["work"],
            "gives": gives,
            "due_label": left["label"],
            "phase": left["phase"],
        })
    return {"agreements": out}
