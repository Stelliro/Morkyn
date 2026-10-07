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
import unicodedata
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
    # Trades of an industrial, modern or far-future world (playtest #33, live).
    # Before these, "Chrome Wrench Garage", "Ito Salvage" and "Bianchi's Clinic"
    # -- names the engine's own pools drew for a sci-fi world -- classified as
    # nothing, so every venue rule (containment, keeper, hours) skipped them.
    "garage":        {"min": "village", "max": 2, "open": 7 * 60,  "close": 19 * 60, "label": "garage"},
    "salvage_yard":  {"min": "hamlet",  "max": 2, "open": 7 * 60,  "close": 19 * 60, "label": "salvage yard"},
    "clinic":        {"min": "village", "max": 2, "open": -1,      "close": -1,      "label": "clinic"},
    "pharmacy":      {"min": "village", "max": 2, "open": 8 * 60,  "close": 20 * 60, "label": "pharmacy"},
    "diner":         {"min": "village", "max": 3, "open": 6 * 60,  "close": 23 * 60, "label": "diner"},
    "bar":           {"min": "village", "max": 4, "open": 16 * 60, "close": 3 * 60,  "label": "bar"},
    "laundromat":    {"min": "village", "max": 2, "open": 6 * 60,  "close": 23 * 60, "label": "laundromat"},
}

# Eras a kind belongs to (example_pools.ERAS). A kind not listed fits every era.
# venue_kinds_possible lists only the world's own trades: a modern village was
# offered a smithy, a mill and a stable and never a garage (playtest #33).
_OLD = ("preindustrial", "industrial")
_NEW = ("industrial", "modern", "future")
_KIND_ERAS: dict[str, tuple[str, ...]] = {
    "smithy": _OLD,
    "mill": _OLD,
    "stable": _OLD,
    "tanner": _OLD,
    "apothecary": _OLD,
    "tavern": _OLD,
    "scribe": ("preindustrial",),
    "alchemist": ("preindustrial",),
    "garage": _NEW,
    "clinic": _NEW,
    "pharmacy": _NEW,
    "bar": _NEW,
    "salvage_yard": ("modern", "future"),
    "diner": ("modern", "future"),
    "laundromat": ("modern", "future"),
}
# The same trade in the other kind of world: a modern bartender works a bar,
# an iron-age mechanic a smithy. Used for an NPC's workplace, never for a name
# the story already gave a place.
_ERA_SWAP: dict[str, str] = {
    "tavern": "bar",
    "apothecary": "pharmacy",
    "alchemist": "pharmacy",
    "smithy": "garage",
    "scribe": "general_store",
    "bar": "tavern",
    "pharmacy": "apothecary",
    "clinic": "apothecary",
    "garage": "smithy",
    "diner": "tavern",
    "salvage_yard": "general_store",
}


def kind_fits_era(kind: str, era: str) -> bool:
    """Does this kind of venue exist in a world of this era? Unknown era: yes."""
    era = str(era or "").strip().lower()
    eras = _KIND_ERAS.get(normalize_kind(kind) or kind)
    return not era or not eras or era in eras


def kind_for_era(kind: str, era: str) -> str:
    """This kind, or the same trade as this era has it ("" when the era has none)."""
    if not kind or kind_fits_era(kind, era):
        return kind
    swapped = _ERA_SWAP.get(kind, "")
    return swapped if swapped and kind_fits_era(swapped, era) else ""

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
    "smithy":        ("smithy", "forge", "blacksmith", "ironworks"),
    "armorer":       ("armorer", "armourer", "armory", "armoury"),
    "inn":           ("inn", "lodge", "lodging house", "roadhouse", "hotel", "motel", "hostel", "bunkhouse"),
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
    "general_store": (
        "general store", "provisioner", "sundries", "trading post", "chandler", "shop", "store",
        "provisions", "chandlery", "dry goods", "mercantile", "mart", "supply", "supplies", "outfitters",
        "hardware", "convenience store", "corner store", "bodega", "pawnshop", "pawn shop",
    ),
    "mill":          ("mill", "millhouse"),
    "stable":        ("stable", "stables", "livery"),
    "bathhouse":     ("bathhouse", "baths"),
    "jeweller":      ("jeweller", "jeweler", "goldsmith", "silversmith"),
    "library":       ("library", "archive"),
    "guild_hall":    ("guild hall", "guildhall", "guild house"),
    "counting_house":("counting house", "bank", "moneylender"),
    "well":          ("well", "cistern", "pump"),
    # Playtest #33: every trade word example_pools._VENUE_TRADE can draw has a
    # kind here, so a venue_name_options pick is always a venue.
    "garage":        (
        # Not "workshop": a fantasy tinker's workshop is no garage.
        "garage", "repairs", "repair shop", "repair bay", "fab shop", "machine shop",
        "auto shop", "body shop", "chop shop", "motor works", "parts",
    ),
    "salvage_yard":  ("salvage", "salvage yard", "scrapyard", "scrap yard", "junkyard", "junk yard"),
    "clinic":        (
        "clinic", "med bay", "medbay", "medical bay", "infirmary", "sickbay", "sick bay", "hospital",
        "med center", "medcenter",
    ),
    "pharmacy":      ("pharmacy", "drugstore", "dispensary"),
    "diner":         (
        "diner", "cafe", "deli", "canteen", "noodle bar", "noodle shop", "noodle stand", "eatery",
        "restaurant", "bistro", "cookshop", "cafeteria", "coffee shop", "food stall",
    ),
    "bar":           ("bar", "saloon", "cantina", "nightclub", "lounge", "speakeasy"),
    "laundromat":    ("laundromat", "launderette", "laundry"),
}


# Kind words that are also everyday nouns and modifiers: "scrap parts", "a
# supply tent", "a bar of rusted girders", "the ruined lounge of the station".
# They name a venue only as the head of a name ("Rustwater Supply", "Kel's
# Parts") or of the thing the prose walks into ("into the bar."), never when
# another word leans on them ("supply tent", "parts bins", "Iron Bar Crossing").
_WEAK_KIND_WORDS = frozenset({
    "mart", "supply", "supplies", "hardware", "repairs", "parts", "deli", "canteen", "bar", "lounge",
})
# Words that may follow a weak kind word in prose while it is still the head:
# punctuation is checked separately.
_WEAK_HEAD_FOLLOW = frozenset({
    "and", "or", "where", "with", "behind", "at", "on", "in", "inside", "as", "while", "is", "was", "are",
    "were", "smells", "hums", "that", "which", "beyond", "before", "after", "near", "by", "from", "itself",
    "stands", "sits", "lies", "has", "had", "seems", "feels", "looks", "you",
})
# A last word that makes a name a street, district or crossing, not a building:
# "Clinic Road", "Smithy Lane", "The Forge Quarter", "Iron Bar Crossing".
_PLACE_TAIL_WORDS = frozenset({
    "road", "lane", "street", "st", "way", "row", "quarter", "district", "crossing", "square", "alley",
    "avenue", "ave", "ward", "gate", "bridge", "hill", "heights", "end", "corner", "junction", "depot",
    "boulevard", "drive", "court", "place", "park", "flats", "fields", "field", "town", "village", "city",
})


def _fold(text: str) -> str:
    """Lower case with accents dropped, so "Café" reads as "cafe"."""
    decomposed = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower().replace("\u2019", "'")

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
    text = re.sub(r"[^a-z' ]+", " ", _fold(name))
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    best_kind, best_len, best_end = "", 0, 0
    for kind, words in _KIND_WORDS.items():
        for word in words:
            if len(word) <= best_len or word not in text:
                continue  # the substring test only skips words that cannot match
            # A weak word counts only as the name's last word ("Rustwater
            # Supply"), not as a modifier ("Supply Depot", "Iron Bar Crossing").
            tail = r"$" if word in _WEAK_KIND_WORDS else r"(?:\s|$)"
            match = re.search(rf"(?:^|\s){re.escape(word)}{tail}", text)
            if match:
                best_kind, best_len, best_end = kind, len(word), match.end()
    if best_kind:
        rest = text[best_end:].split()
        if rest and rest[-1] in _PLACE_TAIL_WORDS:
            return ""  # "Clinic Road", "The Forge Quarter": a street or district
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
    # Playtest #33 (live): the opening's "Victor Silva, mechanic" beside the
    # Chrome Wrench Garage had no trade, so the draft invented a second mechanic.
    "garage":        (
        "mechanic", "rigger", "repairman", "repairwoman", "technician", "fabricator", "machinist",
        "welder", "grease monkey",
    ),
    "salvage_yard":  ("salvager", "scavenger", "scrapper", "junk dealer", "scrap dealer", "salvage dealer"),
    "clinic":        ("doctor", "nurse", "medic", "surgeon", "paramedic", "ripperdoc"),
    "pharmacy":      ("pharmacist", "druggist"),
    "diner":         ("cook", "chef", "waitress", "waiter", "short order cook", "barista", "noodle vendor"),
    "laundromat":    ("laundress", "launderer"),
}

# Kinds that are a place to stand rather than premises someone works in.
_NOT_WORKPLACES = {"well", "shrine", "guardhouse", "market_hall", "guild_hall", "bathhouse", "counting_house"}


def workplace_kind_for_role(role: str, era: str = "") -> str:
    """The venue kind an NPC with this occupation works in, or "" for none.

    Whole words only and the longest phrase wins, so an "off-duty guard" or a
    "message runner" has no shop and a "pastry cook" is not read as a cook.
    With an era, the trade is the one that world has: a modern bartender works
    a bar, an iron-age mechanic a smithy (playtest #33).
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
    if best_kind in _NOT_WORKPLACES:
        return ""
    return kind_for_era(best_kind, era) if era else best_kind


def keeper_role_for_kind(kind: str) -> str:
    """The trade of whoever keeps a venue of this kind ("shopkeeper" for a general store), or ""."""
    words = _ROLE_KINDS.get(normalize_kind(kind) or str(kind or ""), ())
    return words[0] if words else ""


def workplace_kinds_for_role(role: str, era: str = "") -> list[str]:
    """Every kind this trade may already work in: the era's own first, then the role's literal one.

    A mechanic in an iron-age world plans a smithy, but a garage the story
    already built is still his (playtest #33).
    """
    literal = workplace_kind_for_role(role)
    if not literal:
        return []
    fitted = kind_for_era(literal, era) if era else literal
    return [kind for kind in dict.fromkeys((fitted, literal)) if kind]


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
    r"(?P<tail>[^.!?\"\u201c\u201d]{0,100})",
    re.I,
)
_LED_ENTER_RE = re.compile(
    r"\b(?:for|lets?|leads?|ushers?|waves?|beckons?|invites?|pulls?|draws?|shows?|gestures?)\s+you\s+"
    r"(?:to\s+)?(?:come\s+|step\s+|follow\s+\w+\s+)?(?P<tail>(?:in|inside|into|through)\b[^.!?\"\u201c\u201d]{0,100})",
    re.I,
)
_SELF_EXIT_RE = re.compile(
    r"\byou\b[^.!?\"\u201c\u201d]{0,30}?\b(?:step|walk|go|head|leave|exit|slip|duck|come)\w*\b"
    r"[^.!?\"\u201c\u201d]{0,20}?\b(?:out|outside|back\s+out)\b",
    re.I,
)
_INTO_RE = re.compile(r"\b(?:into|inside|in|through)\b(?P<obj>.*)$", re.I | re.S)
# Every preposition of an entry clause, in order (playtest #33).
_PREP_RE = re.compile(r"\b(into|inside|in|through)\b", re.I)
# "through the side door", "through the Iron Gate's side entrance": the way in,
# not the building. A town gate is not on this list: walking through it is not
# going indoors.
_PASS_THROUGH_RE = re.compile(
    r"^(?:(?:the|a|an|its|their|his|her|your)\s+)?(?:[\w'\u2019-]+\s+){0,4}?"
    r"(?:doors?|doorway|entrance|entryway|threshold|archway|hatch|airlock|flap)\b",
    re.I,
)
_PROPER_NAME_RE = re.compile(r"(?:[Tt]he\s+)?[A-Z][\w'\u2019-]*(?:\s+(?:of|at|and|the|on|[A-Z][\w'\u2019-]*))*")
_INSIDE_LEAD_RE = re.compile(r"^\s*inside\b[,\s]+(?:(?:the|a|an)\s+)?(?P<rest>.*)$", re.I | re.S)
_DOOR_CUE_RE = re.compile(r"\b(?:doors?|doorway|entrance|threshold)\b", re.I)
# "in" that is not going inside: "step in front of the bakery", "head in the
# direction of the inn", "lets you in on a secret about the tavern".
_NOT_INSIDE_RE = re.compile(
    r"^(?:front\s+of|the\s+direction\s+of|direction\s+of|(?:full\s+|plain\s+)?(?:view|sight)\s+of|"
    r"search\s+of|pursuit\s+of|the\s+shadow\s+of|the\s+lee\s+of|on\b|time\b|turn\b|line\b|case\b)",
    re.I,
)
# Spoken lines are not the narration moving the player: "Why don't you step
# into my shop?" is an invitation, not an entry.
_SPEECH_RE = re.compile(r"\"[^\"\n]*\"|\u201c[^\u201d\n]*\u201d")


def strip_speech(text: str) -> str:
    """Narration with quoted speech blanked out, including a quote split over paragraphs.

    The live 8B breaks a speech across a paragraph break (playtest #33):
    "\u201cThe Guild's watching the docks.\n\nHe leans in. They think you're
    heading there, but you're not.\u201d" -- an opener with no closer on its
    line runs to the end of that line, and a closer with no opener runs from
    the start of its line.
    """
    out: list[str] = []
    for line in _SPEECH_RE.sub(" ", str(text or "")).split("\n"):
        close = line.find("\u201d")
        if close >= 0 and "\u201c" not in line[:close]:
            line = " " + line[close + 1:]
        open_at = line.find("\u201c")
        if open_at >= 0 and "\u201d" not in line[open_at:]:
            line = line[:open_at]
        out.append(line)
    return "\n".join(out)
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


# A shop's sign, read out with its name set off: 'a sign that reads *The Hare
# and Goose*', 'a sign reading "Trask and Daughters."' (playtest #50, live).
_SIGN_NAME_RE = re.compile(
    r"\bsign(?:board)?\b[^.!?\n]{0,60}?\b(?:reads?|reading|says|saying|bears?|bearing|proclaims?|announces?|declares?)"
    r"\s*:?\s*(?P<open>\*{1,2}|[\"\u201c\u2018'])(?P<name>[A-Z0-9][^*\"\u201d\u2019\n]{1,48}?)[.,!]?(?:\*{1,2}|[\"\u201d\u2019'])",
)


def sign_name(text: str) -> str:
    """The last shop name the prose reads off a sign, or ""."""
    found = ""
    for match in _SIGN_NAME_RE.finditer(str(text or "")):
        name = re.sub(r"\s+", " ", match.group("name")).strip(" .,!;:")
        if 1 <= len(name.split()) <= 6:
            found = name
    return found


def _sentences(text: str) -> list[str]:
    flat = re.sub(r"\s*\[\[[A-Za-z0-9]+\]\]", "", str(text or ""))
    return [s for s in re.split(r"(?<=[.!?\"\u201d])\s+", flat) if s.strip()]


def _weak_is_head(folded: str, end: int) -> bool:
    """A weak kind word ending at `end` is the head noun: nothing leans on it."""
    rest = folded[end:]
    if not rest.strip() or re.match(r"\s*[^\w\s']", rest):
        return True  # end of text or punctuation: "into the bar." / "the bar, where"
    nxt = re.match(r"\s*([a-z']+)", rest)
    return bool(nxt) and nxt.group(1) in _WEAK_HEAD_FOLLOW


def _venue_noun(text: str) -> tuple[str, str]:
    """(kind, the words that said so) for the first building noun in text, or ("", "")."""
    folded = _fold(text)
    # Punctuation kept for the weak-word head check, same length as `low`.
    marked = re.sub(r"[^a-z' ]", lambda m: m.group(0) if m.group(0) in ",.;:!?" else " ", folded)
    low = re.sub(r"[^a-z' ]", " ", folded)
    best: tuple[int, int, str, str] | None = None
    for kind, words in _KIND_WORDS.items():
        # A well is not a door, and "bank" is a river's as often as a lender's.
        if kind in {"well", "counting_house"}:
            continue
        for word in words:
            for match in re.finditer(rf"(?:^|\s){re.escape(word)}(?=\s|$)", low):
                if word in _WEAK_KIND_WORDS and not _weak_is_head(marked, match.end()):
                    continue  # "scrap parts piled", "the supply tent", "a bar of girders"
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


def _proper_name(obj: str) -> str:
    """The capitalised name an entry lands on ("into Ito Salvage, a cramped shop" -> "Ito Salvage"), or ""."""
    match = _PROPER_NAME_RE.match(str(obj or "").strip())
    if not match:
        return ""
    name = re.sub(r"(?:\s+(?:of|at|and|the|on|in))+$", "", match.group(0).strip(), flags=re.I).strip(" ,;:")
    words = [w for w in name.split() if w.lower() != "the"]
    if not words or not any(w[:1].isupper() for w in words):
        return ""
    return name


def _entry_from(word: str, obj: str, sentences: list[str], index: int) -> tuple[str, str, str] | None:
    """(kind, noun, name) for one preposition's object in an entry clause, or None."""
    word = word.lower()
    if word != "through" and _NOT_INSIDE_RE.match(obj):
        return None
    door = word == "through" and _PASS_THROUGH_RE.match(obj) is not None
    # "through the gap between the scrap parts": what "through" crosses is the
    # first thing named, not a noun further along the clause.
    head = " ".join(obj.split()[: 3 if word == "through" else 6])
    kind, noun = ("", "") if door else _venue_noun(head)
    ground = _OPEN_GROUND_RE.search(head)
    if kind and ground and ground.start() < _fold(head).find(noun):
        return None  # "into the street outside the inn" lands in the street
    if kind:
        return kind, noun, _proper_name(obj)
    # "Gestures for you to come in." / "You push through the creaking door":
    # the building is named in the sentence around it.
    bare = not obj or obj[0] in ",;:" or re.match(r"(?:and|after|behind|with|as|while|to)\b", obj, re.I)
    if not (bare or door) or (not door and _OPEN_GROUND_RE.search(" ".join(obj.split()[:4]))):
        return None
    window = " ".join(sentences[max(0, index - 1): index + 2])
    kind, noun = _venue_noun(window)
    return (kind, noun, "") if kind else None


def entry_in_prose(text: str, people: list[str] | tuple[str, ...] = ()) -> dict[str, Any] | None:
    """Where the prose takes the player indoors, or None.

    Returns {"kind", "noun", "name", "keeper", "with"}: the venue kind (a
    generic shop takes its trade from its goods, else general_store), the
    building word the prose used, the building's own name when the prose gives
    one ("into Ito Salvage"), the person shown letting the player in or keeping
    the place, and the other people shown inside with the player. The last
    entry wins, and one the player walks back out of afterwards does not count.

    Every preposition of the clause is read, not only the first (playtest #33,
    live): "You slip through the Iron Gate's side entrance and into Ito
    Salvage" goes through a door and into the shop, and "You push through the
    creaking door ... Inside, the garage is dimly lit" enters the garage.
    """
    sentences = _sentences(strip_speech(text))
    found: tuple[int, str, str, str] | None = None
    for index, sentence in enumerate(sentences):
        for match in list(_SELF_ENTER_RE.finditer(sentence)) + list(_LED_ENTER_RE.finditer(sentence)):
            tail = match.group("tail") or ""
            verb = (match.groupdict().get("verb") or "").lower()
            preps = [(p.group(1), tail[p.end():].strip()) for p in _PREP_RE.finditer(tail)]
            if not preps and not verb.startswith("enter"):
                continue
            # The last "into"/"inside"/"in" lands in the building; a leading
            # "through the door" is only the way in.
            ordered = [p for p in reversed(preps) if p[0].lower() != "through"]
            ordered += [p for p in preps if p[0].lower() == "through"]
            hit = None
            for word, obj in ordered:
                hit = _entry_from(word, obj, sentences, index)
                if hit:
                    break
            if hit is None and not preps:
                hit = _entry_from("into", tail.strip(), sentences, index)
            if hit:
                found = (index, *hit)
        # "Inside, the garage is dimly lit" right after the player is at the door.
        inside = _INSIDE_LEAD_RE.match(sentence)
        if inside and index and not (found and found[0] == index):
            before = " ".join(sentences[max(0, index - 2): index])
            if _DOOR_CUE_RE.search(before) or _SELF_ENTER_RE.search(before):
                kind, noun = _venue_noun(" ".join(inside.group("rest").split()[:4]))
                if kind:
                    found = (index, kind, noun, "")
        if found and found[0] < index and _SELF_EXIT_RE.search(sentence):
            found = None
    if found is None:
        return None
    index, kind, noun, name = found
    if not name:
        # The prose names the place on its sign rather than in the entry clause.
        name = sign_name(text)
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
    inside_text = " ".join(sentences[max(0, index - 1): index + 3])
    along = [
        n for n in names
        if n != keeper and re.search(rf"\b{re.escape(n)}\b", inside_text, re.I)
    ]
    return {"kind": kind, "noun": noun, "name": name, "keeper": keeper, "with": along}


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


def plausible_kinds(settlement_size: str, era: str = "") -> list[str]:
    """Kinds a settlement this size could hold, in this world's era when one is given."""
    rank = size_rank(settlement_size)
    return [
        k for k, spec in VENUE_KINDS.items()
        if size_rank(str(spec["min"])) <= rank and kind_fits_era(k, era)
    ]


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


def row_kind(row: Any) -> str:
    """A location row's venue kind: the stamped ``kind``, else what its name says.

    A row made from a town plot (docs/TownGrid.md 4.4) is never read from its
    name: "The Crooked Lantern on Wheel Street" ends on a place-tail word and
    would classify as nothing, so its stamped kind is the only answer.
    """
    kind = str(_field(row, "kind", "") or "")
    if kind or str(_field(row, "plot_id", "") or ""):
        return kind
    return venue_kind_from_name(str(_field(row, "name", "") or ""))


def _field(row: Any, key: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default
