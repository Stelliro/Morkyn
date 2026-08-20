"""
Venues: shops, inns, forges and temples as real places you can be inside.

Before this, a shop was prose. A live probe walked into an apothecary on a
square, talked to the keeper, stepped out and went back in -- and the database
recorded one location and zero movement the whole time. Asking to return to it
from two locations away minted a brand-new top-level place called "Apothecary",
unrelated to the square, and teleported the player into it. The keeper was a man,
then a woman, then a different man, because nobody was bound to the shop.

The model here is deliberately small:

  * A venue is a row in ``locations`` whose ``parent_id`` is the place you must be
    standing in to enter it. Entering is an ordinary move, so visit counts, entity
    codes and the map all keep working.
  * ``kind`` says what sort of venue it is, which supplies opening hours and
    decides whether it could plausibly exist in a settlement this size.
  * ``keeper_npc_id`` pins one NPC behind the counter for good.

Hours are minutes past midnight and may wrap (a tavern open 18:00-02:00 has
``close_minute`` < ``open_minute``). ``-1``/``-1`` means never closes.
"""
from __future__ import annotations

import re
from typing import Any

MINUTES_PER_DAY = 24 * 60

# Smallest settlement each kind plausibly appears in, how many of it a place that
# size might hold, and when it is open. A hamlet has no apothecary; asking for one
# should be refused rather than conjuring a shop out of nothing.
SETTLEMENT_ORDER: tuple[str, ...] = ("wilds", "hamlet", "village", "town", "city")

# kind -> (min settlement, max in one settlement, open, close, player-facing label)
VENUE_KINDS: dict[str, dict[str, Any]] = {
    "shrine":        {"min": "hamlet",  "max": 2, "open": -1,      "close": -1,      "label": "shrine"},
    "well":          {"min": "hamlet",  "max": 1, "open": -1,      "close": -1,      "label": "well"},
    "inn":           {"min": "village", "max": 3, "open": 6 * 60,  "close": 1 * 60,  "label": "inn"},
    "tavern":        {"min": "village", "max": 4, "open": 11 * 60, "close": 2 * 60,  "label": "tavern"},
    "smithy":        {"min": "village", "max": 2, "open": 7 * 60,  "close": 17 * 60, "label": "smithy"},
    "general_store": {"min": "village", "max": 2, "open": 7 * 60,  "close": 19 * 60, "label": "general store"},
    "mill":          {"min": "village", "max": 1, "open": 6 * 60,  "close": 18 * 60, "label": "mill"},
    "stable":        {"min": "village", "max": 2, "open": 5 * 60,  "close": 20 * 60, "label": "stable"},
    "bakery":        {"min": "town",    "max": 3, "open": 4 * 60,  "close": 12 * 60, "label": "bakery"},
    "apothecary":    {"min": "town",    "max": 2, "open": 8 * 60,  "close": 18 * 60, "label": "apothecary"},
    "butcher":       {"min": "town",    "max": 2, "open": 6 * 60,  "close": 15 * 60, "label": "butcher"},
    "tailor":        {"min": "town",    "max": 2, "open": 8 * 60,  "close": 18 * 60, "label": "tailor"},
    "tanner":        {"min": "town",    "max": 1, "open": 7 * 60,  "close": 17 * 60, "label": "tannery"},
    "carpenter":     {"min": "town",    "max": 2, "open": 7 * 60,  "close": 17 * 60, "label": "carpenter's shop"},
    "scribe":        {"min": "town",    "max": 1, "open": 9 * 60,  "close": 17 * 60, "label": "scribe's office"},
    "temple":        {"min": "town",    "max": 2, "open": -1,      "close": -1,      "label": "temple"},
    "guardhouse":    {"min": "town",    "max": 2, "open": -1,      "close": -1,      "label": "guardhouse"},
    "market_hall":   {"min": "town",    "max": 1, "open": 6 * 60,  "close": 14 * 60, "label": "market hall"},
    "bathhouse":     {"min": "city",    "max": 3, "open": 9 * 60,  "close": 21 * 60, "label": "bathhouse"},
    "armorer":       {"min": "city",    "max": 2, "open": 8 * 60,  "close": 18 * 60, "label": "armorer"},
    "jeweller":      {"min": "city",    "max": 2, "open": 9 * 60,  "close": 17 * 60, "label": "jeweller"},
    "alchemist":     {"min": "city",    "max": 1, "open": 10 * 60, "close": 20 * 60, "label": "alchemist"},
    "library":       {"min": "city",    "max": 1, "open": 9 * 60,  "close": 18 * 60, "label": "library"},
    "guild_hall":    {"min": "city",    "max": 3, "open": 8 * 60,  "close": 19 * 60, "label": "guild hall"},
    "counting_house":{"min": "city",    "max": 1, "open": 9 * 60,  "close": 16 * 60, "label": "counting house"},
}

# Words in a place name that identify its kind. Longest match wins, so
# "alchemist" is not swallowed by "chemist" and "market hall" beats "hall".
#
# Possessive forms are deliberately absent. "The Alchemist's Rest" and "The
# Smith's Arms" are inn names that borrow a trade word, and "Baker's Row" is a
# street; treating those as shops is worse than not recognising them, because an
# unrecognised venue simply behaves like an ordinary place.
_KIND_WORDS: dict[str, tuple[str, ...]] = {
    "apothecary":    ("apothecary", "herbalist", "physician", "chemist"),
    "alchemist":     ("alchemist", "alchemy"),
    "smithy":        ("smithy", "forge", "blacksmith"),
    "armorer":       ("armorer", "armourer", "armory", "armoury"),
    "inn":           ("inn", "lodge", "lodging house", "roadhouse"),
    "tavern":        ("tavern", "alehouse", "public house", "pub", "beerhall"),
    "bakery":        ("bakery", "bakehouse"),
    "butcher":       ("butcher", "shambles"),
    "tailor":        ("tailor", "seamstress", "clothier", "draper"),
    "tanner":        ("tannery", "tanner"),
    "carpenter":     ("carpenter", "joiner", "woodwright"),
    "scribe":        ("scribe", "scrivener", "notary"),
    "temple":        ("temple", "cathedral", "chapel", "abbey", "minster"),
    "shrine":        ("shrine", "wayshrine", "reliquary"),
    "guardhouse":    ("guardhouse", "watch house", "barracks", "gaol", "jail"),
    "market_hall":   ("market hall", "exchange", "trade hall"),
    "general_store": ("general store", "provisioner", "sundries", "trading post", "chandler"),
    "mill":          ("mill", "millhouse"),
    "stable":        ("stable", "stables", "livery"),
    "bathhouse":     ("bathhouse", "baths"),
    "jeweller":      ("jeweller", "jeweler", "goldsmith", "silversmith"),
    "library":       ("library", "archive"),
    "guild_hall":    ("guild hall", "guildhall", "guild house"),
    "counting_house":("counting house", "bank", "moneylender"),
    "well":          ("well", "cistern", "pump"),
}

_SETTLEMENT_WORDS: dict[str, tuple[str, ...]] = {
    "city":    ("city", "metropolis", "capital", "megacity", "citadel"),
    "town":    ("town", "borough", "market", "square", "port", "harbor", "harbour", "wharf", "quay"),
    "village": ("village", "hamlet-town", "settlement", "commons", "green"),
    "hamlet":  ("hamlet", "camp", "steading", "croft", "farmstead", "waystation", "outpost"),
}


def normalize_kind(value: str) -> str:
    """Fold a loose kind label onto a known key, or "" if it is not a venue kind."""
    text = re.sub(r"[^a-z ]+", " ", str(value or "").strip().lower())
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    key = text.replace(" ", "_")
    if key in VENUE_KINDS:
        return key
    for kind, words in _KIND_WORDS.items():
        if any(word.replace("'", "") == text for word in words):
            return kind
    return ""


def venue_kind_from_name(name: str) -> str:
    """The venue kind a place name implies, or "" for an ordinary open place.

    Longest phrase wins so "market hall" does not resolve as a plain market and
    "alchemist" is not eaten by a shorter word.
    """
    text = re.sub(r"[^a-z' ]+", " ", str(name or "").lower())
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    best_kind, best_len = "", 0
    for kind, words in _KIND_WORDS.items():
        for word in words:
            if len(word) <= best_len:
                continue
            if re.search(rf"(?:^|\s){re.escape(word)}(?:\s|$)", text):
                best_kind, best_len = kind, len(word)
    return best_kind


def normalize_settlement_size(value: str) -> str:
    text = str(value or "").strip().lower()
    if text in SETTLEMENT_ORDER:
        return text
    for size, words in _SETTLEMENT_WORDS.items():
        if any(word in text for word in words):
            return size
    return ""


def settlement_size_from_name(name: str, summary: str = "") -> str:
    """Guess a settlement's size from its name and summary. Defaults to village.

    Deliberately generous: the cost of guessing "village" for a real town is one
    missing shop kind, while guessing "city" for a crossroads camp puts a
    counting house in a field.
    """
    found = normalize_settlement_size(f"{name} {summary}")
    return found or "village"


def size_rank(size: str) -> int:
    normalized = normalize_settlement_size(size) or "village"
    try:
        return SETTLEMENT_ORDER.index(normalized)
    except ValueError:
        return SETTLEMENT_ORDER.index("village")


def kind_allowed(kind: str, settlement_size: str) -> bool:
    """Could a venue of this kind exist in a settlement this size?"""
    spec = VENUE_KINDS.get(normalize_kind(kind) or kind)
    if not spec:
        return True  # unknown kinds are not our business to veto
    return size_rank(settlement_size) >= size_rank(str(spec["min"]))


def kind_capacity(kind: str) -> int:
    spec = VENUE_KINDS.get(normalize_kind(kind) or kind)
    return int(spec["max"]) if spec else 1


def plausible_kinds(settlement_size: str) -> list[str]:
    rank = size_rank(settlement_size)
    return [k for k, spec in VENUE_KINDS.items() if size_rank(str(spec["min"])) <= rank]


def default_hours(kind: str) -> tuple[int, int]:
    spec = VENUE_KINDS.get(normalize_kind(kind) or kind)
    if not spec:
        return (-1, -1)
    return (int(spec["open"]), int(spec["close"]))


def kind_label(kind: str) -> str:
    spec = VENUE_KINDS.get(normalize_kind(kind) or kind)
    return str(spec["label"]) if spec else str(kind or "").replace("_", " ")


def is_open(open_minute: int, close_minute: int, world_minute: int) -> bool:
    """Is a venue with these hours open at this time of day?

    Handles wrap past midnight: a tavern open 18:00-02:00 has close < open, and
    01:00 is inside that window while 15:00 is not.
    """
    try:
        start, end = int(open_minute), int(close_minute)
    except (TypeError, ValueError):
        return True
    if start < 0 or end < 0:
        return True
    now = int(world_minute) % MINUTES_PER_DAY
    start %= MINUTES_PER_DAY
    end %= MINUTES_PER_DAY
    if start == end:
        return True
    if start < end:
        return start <= now < end
    return now >= start or now < end


def clock(minute: int) -> str:
    value = int(minute) % MINUTES_PER_DAY
    return f"{value // 60:02d}:{value % 60:02d}"


def describe_hours(open_minute: int, close_minute: int) -> str:
    try:
        start, end = int(open_minute), int(close_minute)
    except (TypeError, ValueError):
        return "always open"
    if start < 0 or end < 0 or start == end:
        return "always open"
    return f"{clock(start)}-{clock(end)}"


def hours_note(row: Any, world_minute: int) -> str:
    """One-line open/closed status for a venue row, for prompts and the UI."""
    open_minute = _field(row, "open_minute", -1)
    close_minute = _field(row, "close_minute", -1)
    window = describe_hours(open_minute, close_minute)
    if window == "always open":
        return "open at any hour"
    state = "open" if is_open(open_minute, close_minute, world_minute) else "closed"
    return f"{state} now ({window})"


def _field(row: Any, key: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default
