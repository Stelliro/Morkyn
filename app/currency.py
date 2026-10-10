"""Currency sets by theme: smallest-unit storage, format, parse, convert.

Status: built, not wired (TODO n17).

A world's money is a currency set chosen from its theme: medieval or fantasy coin (100 copper = 1 silver,
100 silver = 1 gold, 100 gold = 1 platinum), sci-fi credits, modern cash, post-collapse scrip that leans
on goods. Every amount this module handles is an int of the set's smallest unit. The only storage is the
settings row ``currency_config`` (a world rule, not turn state, so it is not snapshotted), written by
``update_currency_config`` alone. The live game still keeps one unitless ``player.gold`` number; nothing
here reads or writes it, and no function here touches any other table. The migration of that number is
written down in ``MIGRATION_PLAN`` below and is not executed by this module. The live game does not call
anything in this file.

Wiring (not done):
  app/world.py:_apply_player() -> units = currency.from_legacy_gold(player_patch["gold_delta"], cset) before
      the gold clamp, once player.purse_units exists (MIGRATION_PLAN step 1).
  app/prose_state.py:stated_coin_amounts() -> currency.parse_all_amounts(text, cset) in place of the _COIN regex.
  app/world.py:_reconcile_prose_with_state() -> currency.format_amount(units, cset) for the "You have N gold"
      sentence and currency.coin_pattern(cset) for the clamp regex.
  app/world.py:resolve_turn_bands() -> money_delta = currency.from_legacy_gold(gold_delta, cset); the dice in
      app/rng.py DEFAULT_MAGNITUDE_TABLES["gold"] stay in the display denomination (step 3).
  app/quests.py:pay_quest_completion() / create_quest() -> reward_units = currency.from_legacy_gold(reward_gold, cset) (step 6).
  app/world.py:start_playthrough() -> cset["starting_purse"] instead of the literal 12 (step 7).
  app/world.py:get_state() -> state["purse"] = currency.purse_view(units, cset) for the UI and the prompt packet.
  app/world.py:build_prompt_context() -> one line naming the coin words, currency.coin_words(cset).

Turn on:
  [ ] settings row currency_config is read by get_state through currency.active_set(conn) (no snapshot:
      it is a world rule, not turn state)
  [ ] MIGRATION_PLAN steps 1-12 in order; step 1 is the only schema change (additive player columns);
      ensure_schema here is a no-op, so no WORLD_TABLES / AUTOINC_TABLES / snapshot / export entry is needed
  [ ] route GET/POST /api/currency-config (pattern: /api/tts-config) if the user should pick a set
  [ ] UI: purse display reads state.purse.display; the bands text in band_contract_block names the coin words
  [ ] prompt: the coin words line; nothing else

Tests: tests/test_currency.py
"""
from __future__ import annotations

import copy
import json
import math
import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.prose_state import _NUMBER_WORDS

CONFIG_KEY = "currency_config"
DEFAULT_SET = "coin_medieval"

# A real count is a positive whole number of a denomination; a count of 1 picks
# the singular word, everything else the plural.
_COIN_ACCEPTANCE = ("always", "usually", "sometimes")

# The presets. Values are counts of the set's smallest unit. The denominations
# of a set are ascending and the first always has value 1. ``compound`` says
# whether the long and short styles list several denominations ("12 gold, 34
# silver") or one number in the display denomination with a thousands
# separator ("1,234 credits"); the largest style names the biggest unit either
# way. ``per_legacy_gold`` is how many units one old ``player.gold`` is worth,
# and ``starting_purse`` is what today's literal 12 gold becomes.
CURRENCY_SETS: dict[str, dict[str, Any]] = {
    "coin_medieval": {
        "id": "coin_medieval",
        "label": "coins",
        "smallest": "copper",
        "denominations": [
            {"id": "copper", "value": 1, "singular": "copper", "plural": "copper", "short": "c",
             "words": ["copper", "coppers", "cp", "penny", "pennies"]},
            {"id": "silver", "value": 100, "singular": "silver", "plural": "silver", "short": "s",
             "words": ["silver", "silvers", "sp"]},
            {"id": "gold", "value": 10000, "singular": "gold", "plural": "gold", "short": "g",
             "words": ["gold", "golds", "gp", "gold coin", "gold coins", "gold piece", "gold pieces",
                       "crown", "crowns"]},
            {"id": "platinum", "value": 1000000, "singular": "platinum", "plural": "platinum", "short": "p",
             "words": ["platinum", "pp"]},
        ],
        "generic_words": ["coin", "coins", "money", "purse"],
        "display": "gold",
        "per_legacy_gold": 10000,
        "decimal": False,
        "symbol": "",
        "accepts_goods": False,
        "coin_acceptance": "always",
        "starting_purse": 120000,
        "compound": True,
    },
    "credits": {
        "id": "credits",
        "label": "credits",
        "smallest": "credit",
        "denominations": [
            {"id": "credit", "value": 1, "singular": "credit", "plural": "credits", "short": "cr",
             "words": ["credit", "credits", "cr"]},
            {"id": "kilocredit", "value": 1000, "singular": "kilocredit", "plural": "kilocredits", "short": "k",
             "words": ["kilocredit", "kilocredits", "kc"]},
        ],
        "generic_words": ["credit", "credits", "cr", "creds"],
        "display": "credit",
        "per_legacy_gold": 10,
        "decimal": False,
        "symbol": "",
        "accepts_goods": False,
        "coin_acceptance": "always",
        "starting_purse": 120,
        "compound": False,
    },
    "cash": {
        "id": "cash",
        "label": "cash",
        "smallest": "cent",
        "denominations": [
            {"id": "cent", "value": 1, "singular": "cent", "plural": "cents", "short": "c",
             "words": ["cent", "cents"]},
            {"id": "dollar", "value": 100, "singular": "dollar", "plural": "dollars", "short": "$",
             "words": ["dollar", "dollars", "buck", "bucks", "note", "notes"]},
        ],
        "generic_words": ["cash", "money"],
        "display": "dollar",
        "per_legacy_gold": 1000,
        "decimal": True,
        "symbol": "$",
        "accepts_goods": False,
        "coin_acceptance": "always",
        "starting_purse": 12000,
        "compound": True,
    },
    "scrip": {
        "id": "scrip",
        "label": "scrip",
        "smallest": "scrip",
        "denominations": [
            {"id": "scrip", "value": 1, "singular": "scrip", "plural": "scrip", "short": "scrip",
             "words": ["scrip"]},
            {"id": "bundle", "value": 50, "singular": "bundle", "plural": "bundles", "short": "b",
             "words": ["bundle", "bundles", "ration chit", "chits"]},
        ],
        "generic_words": ["scrip", "chits", "trade goods"],
        "display": "scrip",
        "per_legacy_gold": 5,
        "decimal": False,
        "symbol": "",
        "accepts_goods": True,
        "coin_acceptance": "sometimes",
        "starting_purse": 60,
        "compound": True,
    },
}

# Theme detection, first match wins. The words below mark a post-collapse
# world whatever its tech level says.
SCRIP_WORDS = (
    "post-collapse", "post collapse", "wasteland", "apocalypse", "after the fall",
    "scavenger", "ruined world", "fallout",
)
# Which set each era from app.world.resolve_world_era falls to when no earlier rule fired.
ERA_SETS = {
    "future": "credits",
    "modern": "cash",
    "industrial": "cash",
    "preindustrial": "coin_medieval",
    "": "coin_medieval",
}

# The settings row shape. ``set`` is "auto" or a CURRENCY_SETS id; ``symbol``
# overrides a decimal set's prefix; ``starting_purse`` is an override in units.
_CONFIG_DEFAULTS: dict[str, Any] = {"set": "auto", "symbol": "", "starting_purse": None}


# ---------------------------------------------------------------------------
# Sets and config
# ---------------------------------------------------------------------------


def ensure_schema(conn) -> None:
    """No tables: the one settings row needs no CREATE. Exists so a wiring pass can call every module's
    ensure_schema in one loop."""
    return None


def theme_set(set_id: str) -> dict[str, Any]:
    """A deep copy of the preset, so a caller may patch it without touching the table."""
    key = str(set_id or "").strip().lower()
    if key not in CURRENCY_SETS:
        raise ValueError(f"unknown currency set: {set_id!r}")
    return copy.deepcopy(CURRENCY_SETS[key])


def _option_text(options: dict[str, Any] | None, key: str) -> str:
    if not isinstance(options, dict):
        return ""
    value = options.get(key)
    if value is None:
        return ""
    return str(value).strip().lower()


def detect_theme_set(options: dict[str, Any] | None) -> str:
    """The set id a playthrough_options dict asks for (the table in the design). None or {} gives the default."""
    if not isinstance(options, dict) or not options:
        return DEFAULT_SET
    world_style = _option_text(options, "world_style")
    custom_style = _option_text(options, "custom_style")
    economy = _option_text(options, "economy")
    tech_level = _option_text(options, "tech_level")
    blob = " ".join((world_style, custom_style, economy, tech_level))
    if any(word in blob for word in SCRIP_WORDS):
        return "scrip"
    # Imported here, not at module level, so a later wiring from app.world does not loop.
    from app.world import resolve_world_era

    era = resolve_world_era(tech_level, world_style, custom_style)
    if "barter" in economy:
        return "scrip" if era in ("modern", "future") else "coin_medieval"
    return ERA_SETS.get(era, DEFAULT_SET)


def set_for_options(options: dict[str, Any] | None) -> dict[str, Any]:
    """The CurrencySet for a playthrough_options dict. A barter economy on a coin world keeps the coin set
    with ``accepts_goods`` forced on."""
    cset = theme_set(detect_theme_set(options))
    if "barter" in _option_text(options, "economy"):
        cset["accepts_goods"] = True
    return cset


def _normalize_config(raw: dict[str, Any]) -> dict[str, Any]:
    clean = dict(_CONFIG_DEFAULTS)
    set_id = str(raw.get("set") or "auto").strip().lower()
    clean["set"] = set_id if set_id == "auto" or set_id in CURRENCY_SETS else "auto"
    clean["symbol"] = str(raw.get("symbol") or "")[:8]
    purse = raw.get("starting_purse")
    if purse is None or purse == "":
        clean["starting_purse"] = None
    else:
        try:
            clean["starting_purse"] = max(0, int(purse))
        except (TypeError, ValueError):
            clean["starting_purse"] = None
    return clean


def get_currency_config(conn) -> dict[str, Any]:
    """The stored row over the defaults; unknown keys dropped; bad JSON or a missing row gives the defaults."""
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (CONFIG_KEY,)).fetchone()
    except Exception:
        return dict(_CONFIG_DEFAULTS)
    if not row or not row["value"]:
        return dict(_CONFIG_DEFAULTS)
    try:
        stored = json.loads(row["value"])
    except (json.JSONDecodeError, TypeError):
        return dict(_CONFIG_DEFAULTS)
    if not isinstance(stored, dict):
        return dict(_CONFIG_DEFAULTS)
    merged = {**_CONFIG_DEFAULTS, **{k: v for k, v in stored.items() if k in _CONFIG_DEFAULTS}}
    return _normalize_config(merged)


def update_currency_config(conn, payload: dict[str, Any]) -> dict[str, Any]:
    """Partial update of the config row: only keys present in ``payload`` change. ``set`` must be "auto" or a
    known id and ``starting_purse`` may not be negative, else ValueError. Writes the row, returns the clean
    config. The caller's connection commits."""
    current = get_currency_config(conn)
    payload = dict(payload or {})
    if "set" in payload:
        set_id = str(payload.get("set") or "auto").strip().lower()
        if set_id != "auto" and set_id not in CURRENCY_SETS:
            raise ValueError(f"unknown currency set: {payload.get('set')!r}")
        current["set"] = set_id
    if "symbol" in payload:
        current["symbol"] = str(payload.get("symbol") or "")[:8]
    if "starting_purse" in payload:
        purse = payload.get("starting_purse")
        if purse is None or purse == "":
            current["starting_purse"] = None
        else:
            try:
                purse_int = int(purse)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"starting_purse must be a whole number of units: {purse!r}") from exc
            if purse_int < 0:
                raise ValueError("starting_purse may not be negative")
            current["starting_purse"] = purse_int
    clean = _normalize_config(current)
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (CONFIG_KEY, json.dumps(clean, ensure_ascii=True)),
    )
    return clean


def _playthrough_options(conn) -> dict[str, Any]:
    """One SELECT of the playthrough_options row, decoded; {} on any trouble (the local_intel._play_flag_on way)."""
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = 'playthrough_options'").fetchone()
        opts = json.loads(row["value"]) if row and row["value"] else {}
    except Exception:
        return {}
    return opts if isinstance(opts, dict) else {}


def active_set(conn) -> dict[str, Any]:
    """The world's CurrencySet: the config row's ``set`` when chosen, else detection from playthrough_options,
    with the row's symbol and starting_purse overrides applied."""
    cfg = get_currency_config(conn)
    if cfg["set"] != "auto":
        cset = theme_set(cfg["set"])
    else:
        cset = set_for_options(_playthrough_options(conn))
    if cfg["symbol"]:
        cset["symbol"] = cfg["symbol"]
    if cfg["starting_purse"] is not None:
        cset["starting_purse"] = int(cfg["starting_purse"])
    return cset


# ---------------------------------------------------------------------------
# Denominations and conversion
# ---------------------------------------------------------------------------


def denomination(cset: dict[str, Any], ref: str) -> dict[str, Any] | None:
    """A denomination by id, word, singular, plural or short form; case does not matter."""
    key = " ".join(str(ref or "").strip().lower().split())
    if not key:
        return None
    for denom in cset.get("denominations") or []:
        names = {str(denom.get("id") or "").lower(), str(denom.get("singular") or "").lower(),
                 str(denom.get("plural") or "").lower(), str(denom.get("short") or "").lower()}
        names.update(str(w).lower() for w in denom.get("words") or [])
        names.discard("")
        if key in names:
            return denom
    return None


def _denom_by_id(cset: dict[str, Any], denom_id: str) -> dict[str, Any]:
    for denom in cset.get("denominations") or []:
        if denom.get("id") == denom_id:
            return denom
    return (cset.get("denominations") or [{"id": "", "value": 1, "singular": "", "plural": "", "short": ""}])[0]


def _smallest(cset: dict[str, Any]) -> dict[str, Any]:
    return (cset.get("denominations") or [{"id": "", "value": 1, "singular": "unit", "plural": "units", "short": ""}])[0]


def _display(cset: dict[str, Any]) -> dict[str, Any]:
    return _denom_by_id(cset, str(cset.get("display") or _smallest(cset).get("id")))


def to_units(cset: dict[str, Any], count: int | float, denom: str) -> int:
    """``3 "silver"`` is 300. Fractions floor after the multiply. A negative count or an unknown
    denomination raises ValueError."""
    found = denomination(cset, denom)
    if found is None:
        raise ValueError(f"unknown denomination: {denom!r}")
    if isinstance(count, bool) or not isinstance(count, (int, float)):
        raise ValueError(f"count must be a number: {count!r}")
    if count < 0:
        raise ValueError("count may not be negative")
    exact = Decimal(str(count)) * Decimal(int(found["value"]))
    return int(exact.to_integral_value(rounding="ROUND_FLOOR"))


def breakdown(cset: dict[str, Any], units: int) -> list[dict[str, Any]]:
    """Greedy, largest denomination first, zero counts omitted. A negative amount is the breakdown of its
    absolute value with every count negated."""
    units = int(units)
    sign = -1 if units < 0 else 1
    remaining = abs(units)
    parts: list[dict[str, Any]] = []
    for denom in sorted(cset.get("denominations") or [], key=lambda d: int(d["value"]), reverse=True):
        value = int(denom["value"])
        if value <= 0:
            continue
        count, remaining = divmod(remaining, value)
        if count:
            parts.append({"id": str(denom["id"]), "count": sign * count})
    return parts


def _round_half_up(value: Decimal) -> int:
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def from_legacy_gold(gold: int | float, cset: dict[str, Any]) -> int:
    """One old ``player.gold`` into units: round(gold * per_legacy_gold). 12 -> 120000 copper; 0.05 -> 500."""
    per = Decimal(int(cset.get("per_legacy_gold") or 1))
    return _round_half_up(Decimal(str(gold)) * per)


def to_legacy_gold(units: int, cset: dict[str, Any]) -> int:
    """Units into the old gold number, whole gold only, fractions dropped toward zero."""
    per = max(1, int(cset.get("per_legacy_gold") or 1))
    units = int(units)
    whole = abs(units) // per
    return -whole if units < 0 else whole


def convert(units: int, from_set: dict[str, Any], to_set: dict[str, Any]) -> int:
    """Between sets through legacy gold as the exchange base: round(units / from.per_legacy_gold * to.per_legacy_gold)."""
    from_per = Decimal(max(1, int(from_set.get("per_legacy_gold") or 1)))
    to_per = Decimal(max(1, int(to_set.get("per_legacy_gold") or 1)))
    return _round_half_up(Decimal(int(units)) * to_per / from_per)


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def _name(denom: dict[str, Any], count: int) -> str:
    return str(denom.get("singular") if abs(count) == 1 else denom.get("plural")) or str(denom.get("id") or "")


def _trim_decimal(text: str) -> str:
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _decimal_text(units: int, cset: dict[str, Any], *, places: int = 2) -> str:
    """"$12.34" for a decimal set; the symbol is the set's prefix."""
    display = _display(cset)
    value = max(1, int(display["value"]))
    whole, frac = divmod(abs(int(units)), value)
    digits = len(str(value)) - 1
    frac_text = str(frac).rjust(digits, "0")[:places].ljust(places, "0") if places else ""
    body = f"{whole:,}" + (f".{frac_text}" if places else "")
    return str(cset.get("symbol") or "") + body


def format_amount(units: int, cset: dict[str, Any], style: str = "long") -> str:
    """Money as text. Styles: "long" ("12 gold, 34 silver, 56 copper", "1,234 credits", "$12.34",
    "24 bundles, 34 scrip"; zero is "no copper" / "$0.00"), "short" ("12g 34s 56c", "1,234 cr", "$12.34",
    "24b 34 scrip"), "largest" (only the biggest non-zero denomination, rounded down: "12 gold",
    "1 kilocredit", "$12", "24 bundles") and "display" (the display denomination as a decimal with trailing
    zeros trimmed: "12.35 gold", "1,234 credits", "$12.34", "1,234 scrip"). Negative amounts get a leading "-"."""
    units = int(units)
    style = str(style or "long").strip().lower()
    if style not in ("long", "short", "largest", "display"):
        raise ValueError(f"unknown style: {style!r}")
    sign = "-" if units < 0 else ""
    magnitude = abs(units)
    smallest = _smallest(cset)
    display = _display(cset)
    decimal_set = bool(cset.get("decimal"))

    if decimal_set:
        if style == "largest":
            return sign + _decimal_text(magnitude, cset, places=0)
        return sign + _decimal_text(magnitude, cset)

    if magnitude == 0:
        if style == "display" and int(display["value"]) != 1:
            return f"0 {_name(display, 0)}"
        return f"no {_name(smallest, 0)}"

    if style == "display":
        value = int(display["value"])
        if value == 1:
            return f"{sign}{magnitude:,} {_name(display, magnitude)}"
        quantized = (Decimal(magnitude) / Decimal(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        text = _trim_decimal(f"{quantized:,.2f}")
        count_for_name = magnitude // value if magnitude % value == 0 else 2
        return f"{sign}{text} {_name(display, count_for_name)}"

    parts = breakdown(cset, magnitude)
    if style == "largest":
        denom = _denom_by_id(cset, parts[0]["id"])
        return f"{sign}{parts[0]['count']:,} {_name(denom, parts[0]['count'])}"

    if not cset.get("compound", True):
        count = magnitude // max(1, int(display["value"]))
        denom = display
        if style == "short":
            return f"{sign}{count:,} {denom.get('short') or _name(denom, count)}"
        return f"{sign}{count:,} {_name(denom, count)}"

    if style == "short":
        tokens = []
        for part in parts:
            denom = _denom_by_id(cset, part["id"])
            short = str(denom.get("short") or _name(denom, part["count"]))
            glue = "" if len(short) == 1 else " "
            tokens.append(f"{part['count']:,}{glue}{short}")
        return sign + " ".join(tokens)

    words = []
    for part in parts:
        denom = _denom_by_id(cset, part["id"])
        words.append(f"{part['count']:,} {_name(denom, part['count'])}")
    return sign + ", ".join(words)


def format_delta(units: int, cset: dict[str, Any]) -> str:
    """"+2 silver" / "-7 gold, 50 silver": the long style with a sign; zero is "no change"."""
    units = int(units)
    if units == 0:
        return "no change"
    sign = "+" if units > 0 else "-"
    return sign + format_amount(abs(units), cset, "long")


# ---------------------------------------------------------------------------
# Words and parsing
# ---------------------------------------------------------------------------


def coin_words(cset: dict[str, Any]) -> list[str]:
    """Every denomination word (the word list, singular and plural) plus the generic words, longest first,
    unique, lower case. Short forms are left out: a single letter is not a word in prose."""
    seen: set[str] = set()
    out: list[str] = []
    for denom in cset.get("denominations") or []:
        for word in list(denom.get("words") or []) + [denom.get("singular"), denom.get("plural")]:
            key = " ".join(str(word or "").strip().lower().split())
            if key and key not in seen:
                seen.add(key)
                out.append(key)
    for word in cset.get("generic_words") or []:
        key = " ".join(str(word or "").strip().lower().split())
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    out.sort(key=lambda w: (-len(w), w))
    return out


def coin_pattern(cset: dict[str, Any]) -> str:
    """A regex alternation of coin_words, escaped, spaces as ``\\s+``, longest first, for a later _COIN replacement."""
    parts = [re.escape(word).replace(r"\ ", r"\s+") for word in coin_words(cset)]
    if not parts:
        return r"(?!x)x"
    return r"(?:" + "|".join(parts) + r")\b"


_NUMBER_WORD_ALTERNATION = "|".join(
    sorted((w.replace(" ", r"\s+") for w in _NUMBER_WORDS), key=len, reverse=True)
)
_AMOUNT_RE = r"(?:\d{1,3}(?:,\d{3}){1,2}|\d{1,7}(?:\.\d{1,2})?|" + _NUMBER_WORD_ALTERNATION + r")"
_JOIN_RE = r"(?:\s*,\s*and\s+|\s*,\s*|\s+and\s+)"


def _amount_value(text: str) -> Decimal | None:
    key = " ".join(text.strip().lower().split())
    if key in _NUMBER_WORDS:
        return Decimal(_NUMBER_WORDS[key])
    key = key.replace(",", "")
    try:
        return Decimal(key)
    except Exception:
        return None


def _compiled(cset: dict[str, Any]) -> tuple[re.Pattern[str], re.Pattern[str], re.Pattern[str] | None]:
    words = coin_pattern(cset)
    first = re.compile(r"(?<![\w$])(?P<n>" + _AMOUNT_RE + r")\s+(?P<w>" + words + r")", re.I)
    more = re.compile(_JOIN_RE + r"(?P<n>" + _AMOUNT_RE + r")\s+(?P<w>" + words + r")", re.I)
    symbol = None
    if cset.get("decimal") and cset.get("symbol"):
        symbol = re.compile(
            r"(?<!\w)" + re.escape(str(cset["symbol"])) + r"\s?(?P<d>\d{1,3}(?:,\d{3}){1,2}(?:\.\d{1,2})?|\d{1,7}(?:\.\d{1,2})?)(?!\d)",
            re.I,
        )
    return first, more, symbol


def _clause_units(cset: dict[str, Any], amount_text: str, word: str) -> tuple[int, dict[str, Any]] | None:
    amount = _amount_value(amount_text)
    if amount is None:
        return None
    denom = denomination(cset, word)
    if denom is None:
        key = " ".join(word.strip().lower().split())
        if key not in {str(w).lower() for w in cset.get("generic_words") or []}:
            return None
        denom = _display(cset)
    exact = amount * Decimal(int(denom["value"]))
    return int(exact.to_integral_value(rounding="ROUND_FLOOR")), denom


def _parse_at(text: str, cset: dict[str, Any], start: int, compiled) -> dict[str, Any] | None:
    first, more, symbol = compiled
    candidates = []
    m = first.search(text, start)
    if m:
        candidates.append(("words", m))
    if symbol is not None:
        s = symbol.search(text, start)
        if s:
            candidates.append(("symbol", s))
    if not candidates:
        return None
    kind, m = min(candidates, key=lambda c: c[1].start())
    if kind == "symbol":
        display = _display(cset)
        amount = _amount_value(m.group("d"))
        if amount is None:
            return None
        units = int((amount * Decimal(int(display["value"]))).to_integral_value(rounding="ROUND_FLOOR"))
        return {"units": units, "parts": breakdown(cset, units), "text": m.group(0), "span": [m.start(), m.end()]}
    clause = _clause_units(cset, m.group("n"), m.group("w"))
    if clause is None:
        # A bare number before a word this set does not know is not money; look further on.
        return _parse_at(text, cset, m.end(), compiled)
    units, denom = clause
    parts = _parts_for(cset, m.group("n"), denom, units)
    end = m.end()
    while True:
        nxt = more.match(text, end)
        if not nxt:
            break
        extra = _clause_units(cset, nxt.group("n"), nxt.group("w"))
        if extra is None:
            break
        units += extra[0]
        parts.extend(_parts_for(cset, nxt.group("n"), extra[1], extra[0]))
        end = nxt.end()
    return {"units": units, "parts": parts, "text": text[m.start():end], "span": [m.start(), end]}


def _parts_for(cset: dict[str, Any], amount_text: str, denom: dict[str, Any], units: int) -> list[dict[str, Any]]:
    amount = _amount_value(amount_text)
    if amount is not None and amount == amount.to_integral_value():
        return [{"id": str(denom["id"]), "count": int(amount)}]
    return breakdown(cset, units)


def parse_amount(text: str, cset: dict[str, Any]) -> dict[str, Any] | None:
    """The first money phrase in ``text`` as {"units", "parts": [{"id", "count"}], "text", "span": [start, end]},
    or None. Grammar: "<amount> <coin word>" repeated with "and" or "," between parts ("3 gold and 20 silver"
    is 30200 copper), "<symbol><decimal>" for decimal sets ("$4.50" is 450), and a bare "<amount> <generic
    word>" meaning the display denomination ("7 coins" is 70000 copper). Amounts are digits or the number
    words prose_state knows; "a few coins" has no amount and gives None. Negated clauses are not handled
    here; callers strip them with prose_state.strip_negated_clauses first."""
    if not text:
        return None
    return _parse_at(str(text), cset, 0, _compiled(cset))


def parse_all_amounts(text: str, cset: dict[str, Any]) -> list[dict[str, Any]]:
    """Every non-overlapping money phrase in ``text``, left to right, each as parse_amount returns it."""
    if not text:
        return []
    text = str(text)
    compiled = _compiled(cset)
    out: list[dict[str, Any]] = []
    pos = 0
    while pos <= len(text):
        found = _parse_at(text, cset, pos, compiled)
        if not found:
            break
        out.append(found)
        pos = max(found["span"][1], pos + 1)
    return out


# ---------------------------------------------------------------------------
# Prices and views
# ---------------------------------------------------------------------------


def round_price(units: int) -> int:
    """Set independent: under 100 units stays as it is; otherwise round half up to three significant figures
    (123456 -> 123000; 1234 -> 1230; 999 -> 999). Never below 1 for a positive input."""
    units = int(units)
    sign = -1 if units < 0 else 1
    magnitude = abs(units)
    if magnitude < 100:
        return units
    digits = len(str(magnitude))
    step = 10 ** (digits - 3)
    rounded = int(math.floor(magnitude / step + 0.5)) * step
    return sign * max(1, rounded)


def purse_view(units: int, cset: dict[str, Any]) -> dict[str, Any]:
    """What a UI or prompt packet shows for a purse: {"units", "set", "display", "short", "long",
    "breakdown", "legacy_gold"}."""
    units = int(units)
    return {
        "units": units,
        "set": str(cset.get("id") or ""),
        "display": format_amount(units, cset, "display"),
        "short": format_amount(units, cset, "short"),
        "long": format_amount(units, cset, "long"),
        "breakdown": breakdown(cset, units),
        "legacy_gold": to_legacy_gold(units, cset),
    }


# ---------------------------------------------------------------------------
# The migration of the single gold number (documented, not executed)
# ---------------------------------------------------------------------------

MIGRATION_PLAN: tuple[dict[str, Any], ...] = (
    {"step": 1, "file": "app/db.py", "function": "_migrate_columns", "schema": True,
     "change": "Add player.purse_units INTEGER NOT NULL DEFAULT 0 and player.currency_set TEXT NOT NULL "
               "DEFAULT '' with the PRAGMA-guarded ALTER pattern. Backfill once: purse_units = gold * "
               "per_legacy_gold of the active set, currency_set = the set id, guarded by currency_set = ''. "
               "Old exports load through the same backfill in _restore_world after the INSERT."},
    {"step": 2, "file": "app/world.py", "function": "get_state", "schema": False,
     "change": "state['purse'] = currency.purse_view(row['purse_units'], cset); player['gold'] becomes "
               "to_legacy_gold(purse_units), derived and no longer authoritative; player_limits_snapshot "
               "gains 'purse' = state['purse']['display']."},
    {"step": 3, "file": "app/world.py", "function": "resolve_turn_bands", "schema": False,
     "change": "rng.DEFAULT_MAGNITUDE_TABLES['gold'] keeps its dice (they are in the display denomination); "
               "the resolved gold_delta is multiplied by per_legacy_gold into money_delta (units); "
               "band_contract_block names the display denomination from coin_words."},
    {"step": 4, "file": "app/turn_dsl.py", "function": "_amount", "schema": False,
     "change": "GOLD keeps its name (COIN and MONEY already alias it); a number followed by a coin word "
               "goes through currency.parse_amount, so GOLD -5 silver means -500 copper. Result key "
               "player['money_delta'] (units) beside the old gold_delta for one release."},
    {"step": 5, "file": "app/prose_state.py", "function": "stated_coin_amounts", "schema": False,
     "change": "With a currency set, use currency.parse_all_amounts and return units; without one keep "
               "today's behaviour. _settle_stated_gold passes the active set and writes money_delta."},
    {"step": 6, "file": "app/quests.py", "function": "pay_quest_completion", "schema": False,
     "change": "reward_gold stays and is read as the display denomination; create_quest also computes "
               "reward_units; pay_quest_completion adds to purse_units, mirrors gold, and goes through the "
               "same clamp helper _apply_player uses; quest_context_for_llm shows format_amount(reward_units, "
               "cset, 'short')."},
    {"step": 7, "file": "app/world.py", "function": "start_playthrough", "schema": False,
     "change": "The literal 12 becomes cset['starting_purse'] in purse_units and to_legacy_gold(...) in gold; "
               "currency_set is written from detect_theme_set(options)."},
    {"step": 8, "file": "app/world.py", "function": "_apply_player", "schema": False,
     "change": "Accept money_delta (units) or gold_delta (display denomination, converted); clamp per turn to "
               "from_legacy_gold(-50000)..from_legacy_gold(5000) and the total to 0..from_legacy_gold(1000000); "
               "one UPDATE of both columns. _settle_purse compares in units; _reconcile_prose_with_state "
               "rewrites with format_amount and its clamp regex uses coin_pattern(cset)."},
    {"step": 9, "file": "app/local_intel.py", "function": "_record_hint", "schema": False,
     "change": "BRIBE_GOLD = 2 becomes from_legacy_gold(2); every other UPDATE player SET gold found by "
               "grep -n 'SET gold' app/ goes through the step 8 helper."},
    {"step": 10, "file": "static/app.js", "function": "appendTurnMeta", "schema": False,
     "change": "Every player.gold read (character sheet, play dock, the rewards line) reads "
               "state.purse.display; offer and quest cards show reward strings as given. No new fetch."},
    {"step": 11, "file": "app/world.py", "function": "export_world", "schema": False,
     "change": "The new columns ride with the player row in WORLD_TABLES; _save_snapshot already snapshots "
               "the whole player row, so rewind is covered; currency_config exports with every settings row."},
    {"step": 12, "file": "app/world.py", "function": "_apply_player", "schema": False,
     "change": "After one release drop the gold_delta handling and keep the gold column as a derived mirror, "
               "or leave it unused in a later additive-only pass."},
)


def migration_plan_text() -> str:
    """The plan as numbered lines, for the TODO note."""
    lines = []
    for step in MIGRATION_PLAN:
        flag = " (schema change)" if step["schema"] else ""
        lines.append(f"{step['step']}. {step['file']}:{step['function']}(){flag}: {step['change']}")
    return "\n".join(lines)
