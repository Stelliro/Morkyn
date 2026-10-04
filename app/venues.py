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
    # A bare "shop" or "store" is still a door with a counter behind it. Before
    # playtest #16 a draft's MOVE into "<keeper>'s Shop" resolved as a second
    # top-level town, so the plain words count as the generic kind.
    "general_store": ("general store", "provisioner", "sundries", "trading post", "chandler", "shop", "store"),
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


# What a trade's own premises are, for an NPC's workplace (playtest #16: Aria
# the baker had no bakery, so the model staffed Elara's herb shop with her).
# A role not listed falls back to the kind words above ("blacksmith", "tanner").
_ROLE_KINDS: dict[str, tuple[str, ...]] = {
    "bakery":        ("baker", "pastry cook"),
    "smithy":        ("smith", "blacksmith", "farrier"),
    "inn":           ("innkeeper", "innkeep", "hosteler", "hostler"),
    "tavern":        ("tavern keeper", "tavernkeeper", "barkeep", "bartender", "brewer", "alewife"),
    "apothecary":    ("apothecary", "herbalist", "physician"),
    "butcher":       ("butcher",),
    "tailor":        ("tailor", "seamstress", "weaver", "dressmaker"),
    "tanner":        ("tanner", "leatherworker"),
    "carpenter":     ("carpenter", "joiner", "cooper", "woodworker"),
    "scribe":        ("scribe", "scrivener", "clerk", "notary"),
    "temple":        ("priest", "priestess", "acolyte", "cleric"),
    "mill":          ("miller",),
    "stable":        ("stablehand", "stable hand", "groom", "ostler", "stablemaster"),
    "general_store": ("shopkeeper", "storekeeper", "grocer", "provisioner", "chandler", "trader"),
    "alchemist":     ("alchemist",),
    "jeweller":      ("jeweller", "jeweler", "goldsmith", "silversmith"),
    "armorer":       ("armorer", "armourer"),
    "library":       ("librarian", "archivist"),
}

# Kinds that are a place to stand rather than premises someone works in.
_NOT_WORKPLACES = {"well", "shrine", "guardhouse", "market_hall", "guild_hall", "bathhouse", "counting_house"}


def workplace_kind_for_role(role: str) -> str:
    """The venue kind an NPC with this occupation works in, or "" for none.

    Whole words only and the longest phrase wins, so an "off-duty guard" or a
    "message runner" has no shop and a "pastry cook" is not read as a cook.
    """
    text = re.sub(r"[^a-z' -]+", " ", str(role or "").lower()).replace("-", " ")
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    best_kind, best_len = "", 0
    for kind, words in _ROLE_KINDS.items():
        for word in words:
            if len(word) > best_len and re.search(rf"(?:^|\s){re.escape(word)}(?:\s|$)", text):
                best_kind, best_len = kind, len(word)
    if not best_kind:
        best_kind = venue_kind_from_name(text)
    return "" if best_kind in _NOT_WORKPLACES else best_kind


# ---------------------------------------------------------------------------
# Going indoors in prose (playtest #16)
# ---------------------------------------------------------------------------
# Game 2's draft walked the player and Aria into a herb shop ("gestures for you
# to come in. Inside, the shop is cluttered...") with no MOVE. The shop was
# never a place and nobody kept it, so the next turn Aria sold its herbs as
# her own. These read whether the prose put the player inside a building, which
# kind, who let them in, and who went in with them. Only the player as the one
# going in counts: "the figure disappears into a shop" moves nobody.

_SELF_ENTER_RE = re.compile(
    r"\byou\b(?:\s+and\s+[A-Z][\w'-]*)?\s+(?:\w+ly\s+)?"
    r"(?P<verb>step|walk|go|head|duck|slip|push|enter|move|follow|come|pass|hurry|venture|make\s+your\s+way)\w*\b"
    r"(?P<tail>[^.!?\"\u201c\u201d]{0,60})",
    re.I,
)
_LED_ENTER_RE = re.compile(
    r"\b(?:for|lets?|leads?|ushers?|waves?|beckons?|invites?|pulls?|draws?|shows?|gestures?)\s+you\s+"
    r"(?:to\s+)?(?:come\s+|step\s+|follow\s+\w+\s+)?(?P<tail>(?:in|inside|into|through)\b[^.!?\"\u201c\u201d]{0,60})",
    re.I,
)
_SELF_EXIT_RE = re.compile(
    r"\byou\b[^.!?\"\u201c\u201d]{0,30}?\b(?:step|walk|go|head|leave|exit|slip|duck|come)\w*\b"
    r"[^.!?\"\u201c\u201d]{0,20}?\b(?:out|outside|back\s+out)\b",
    re.I,
)
_INTO_RE = re.compile(r"\b(?:into|inside|in|through)\b(?P<obj>.*)$", re.I | re.S)
# What "into" lands on when it is not a building.
_OPEN_GROUND_RE = re.compile(
    r"\b(?:street|road|lane|alley|square|market|plaza|courtyard|yard|crowd|clearing|forest|wood|field|path|"
    r"night|dark|shadow|light|sun|rain|silence|view|line|place)\w*\b",
    re.I,
)
# A generic shop's trade, from what fills it. Small on purpose: anything else
# stays a general store.
_GOODS_HINTS: dict[str, tuple[str, ...]] = {
    "apothecary": ("herb", "remed", "tincture", "salve", "poultice"),
    "bakery": ("bread", "loaves", "loaf", "pastr", "flour"),
    "smithy": ("anvil", "bellows", "horseshoe"),
    "tailor": ("bolts of cloth", "fabric", "garments"),
}
_KEEPER_CUE_RE = re.compile(
    r"\b(?:gestures?|beckons?|waves?|ushers?|invites?|welcomes?|lets?)\b[^.!?]{0,30}\byou\b"
    r"|\bbehind\s+(?:the|her|his|their)\s+counter\b"
    r"|\b(?:owns?|runs?|keeps?|tends?)\s+(?:the|this|her|his|their)\s+(?:shop|store|counter|bar|forge|inn|tavern|place)\b"
    r"|\b(?:shopkeeper|proprietor|owner|innkeeper)\b",
    re.I,
)


def _sentences(text: str) -> list[str]:
    flat = re.sub(r"\s*\[\[[A-Za-z0-9]+\]\]", "", str(text or ""))
    return [s for s in re.split(r"(?<=[.!?\"\u201d])\s+", flat) if s.strip()]


def _venue_noun(text: str) -> tuple[str, str]:
    """(kind, the words that said so) for the first building noun in text, or ("", "")."""
    low = re.sub(r"[^a-z' ]+", " ", str(text or "").lower())
    best: tuple[int, int, str, str] | None = None
    for kind, words in _KIND_WORDS.items():
        # A well is not a door, and "bank" is a river's as often as a lender's.
        if kind in {"well", "counting_house"}:
            continue
        for word in words:
            for match in re.finditer(rf"(?:^|\s){re.escape(word)}(?=\s|$)", low):
                at = match.start()
                key = (at, -len(word))
                if best is None or key < (best[0], best[1]):
                    best = (at, -len(word), kind, word)
    if best is None:
        return "", ""
    return best[2], best[3]


def _goods_kind(text: str) -> str:
    low = str(text or "").lower()
    for kind, words in _GOODS_HINTS.items():
        if any(word in low for word in words):
            return kind
    return ""


def entry_in_prose(text: str, people: list[str] | tuple[str, ...] = ()) -> dict[str, Any] | None:
    """Where the prose takes the player indoors, or None.

    Returns {"kind", "noun", "keeper", "with"}: the venue kind (a generic shop
    takes its trade from its goods, else general_store), the building word the
    prose used, the person shown letting the player in or keeping the place,
    and the other people shown inside with the player. The last entry wins, and
    one the player walks back out of afterwards does not count.
    """
    sentences = _sentences(text)
    found: tuple[int, str, str] | None = None
    for index, sentence in enumerate(sentences):
        for match in list(_SELF_ENTER_RE.finditer(sentence)) + list(_LED_ENTER_RE.finditer(sentence)):
            tail = match.group("tail") or ""
            verb = (match.groupdict().get("verb") or "").lower()
            into = _INTO_RE.search(tail)
            if into is None and not verb.startswith("enter"):
                continue
            obj = (into.group("obj") if into is not None else tail).strip()
            head = " ".join(obj.split()[:6])
            kind, noun = _venue_noun(head)
            ground = _OPEN_GROUND_RE.search(head)
            if kind and ground and ground.start() < head.lower().find(noun):
                continue  # "into the street outside the inn" lands in the street
            if not kind:
                bare = not obj or obj[0] in ",;:" or re.match(r"(?:and|after|behind|with|as|while|to)\b", obj, re.I)
                if not bare or _OPEN_GROUND_RE.search(" ".join(obj.split()[:4])):
                    continue
                window = " ".join(sentences[max(0, index - 1): index + 2])
                kind, noun = _venue_noun(window)
            if kind:
                found = (index, kind, noun)
        if found and found[0] < index and _SELF_EXIT_RE.search(sentence):
            found = None
    if found is None:
        return None
    index, kind, noun = found
    if kind == "general_store" and noun in {"shop", "store"}:
        kind = _goods_kind(" ".join(sentences[index: index + 3])) or kind
    names = [str(p).strip() for p in people if str(p or "").strip()]
    keeper = ""
    for offset in (0, -1, 1, -2, 2):
        at = index + offset
        if not 0 <= at < len(sentences) or not _KEEPER_CUE_RE.search(sentences[at]):
            continue
        hit = next((n for n in names if re.search(rf"\b{re.escape(n)}\b", sentences[at], re.I)), "")
        if hit:
            keeper = hit
            break
    # The sentence before counts: "Aria knocks ... Elara gestures for you to come in."
    inside = " ".join(sentences[max(0, index - 1): index + 3])
    along = [
        n for n in names
        if n != keeper and re.search(rf"\b{re.escape(n)}\b", inside, re.I)
    ]
    return {"kind": kind, "noun": noun, "keeper": keeper, "with": along}


def normalize_settlement_size(value: str) -> str:
    text = re.sub(r"[^a-z ]+", " ", str(value or "").strip().lower())
    text = re.sub(r"\s+", " ", text).strip()
    if text in SETTLEMENT_ORDER:
        return text
    # Word tokens only. Substring "port" in "portal" / "opportunity" classified
    # a portal camp as a town and then allowed apothecaries a hamlet cannot have.
    for size, words in _SETTLEMENT_WORDS.items():
        for word in words:
            if re.search(rf"(?:^|\s){re.escape(word)}(?:\s|$)", text):
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
