"""
Starting gear: one item shape shared by the setup form, the model, SQLite and play.

An item is a dict:

    {
      "name": "travel-worn cloak",
      "slot": "BACK",                 # a body slot code from GEAR_SLOTS, or "" for carried
      "required": False,              # the three basics (FEET, TORSO, LEGS) are required
      "keep": False,                  # setup lock: Randomize must not rewrite it
      "description": "...",           # what it is, in this world
      "stats": {"dexterity": 1},      # bonuses to the wearer while worn; canonical STAT_KEYS
      "item_stats": {                 # the item's own numbers
          "weight": 1.2, "durability": 62, "protection": 1, "value": 6, "rarity": "common"
      },
      "abilities": [ {ability dict, same shape as a special ability} ],
    }

The model may fill any of it. Whatever it leaves blank the engine rolls from the
world (``roll_item_stats`` / ``roll_stat_bonuses``), and whatever it over-fills the
engine clamps (``normalize_gear_item``). ``normalize_gear_list`` is the one entry
point setup, the randomizer and ``start_playthrough`` all go through.
"""
from __future__ import annotations

import random
import re
from typing import Any

from app.content_packs import STAT_KEYS, normalize_stat_key

# (code, label, keywords that map a name onto this slot)
GEAR_SLOTS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("HEAD", "Head", ("helm", "helmet", "hat", "hood", "mask", "cap", "veil", "headband", "visor", "goggles")),
    ("NECK", "Neck", ("amulet", "necklace", "collar", "scarf", "pendant", "locket", "torc")),
    ("TORSO", "Torso", ("coat", "robe", "jacket", "armor", "armour", "tunic", "dress", "shirt", "vest", "hoodie", "jerkin", "mail", "cuirass", "blouse", "sweater", "parka", "gown", "apron")),
    ("UNDER", "Under layer", ("undershirt", "underlayer", "undersuit", "lining", "shift", "camisole")),
    ("BACK", "Back", ("cloak", "cape", "backpack", "pack", "rucksack", "satchel", "knapsack", "wings", "quiver")),
    ("MAIN", "Main hand", ("knife", "blade", "sword", "axe", "dagger", "staff", "spear", "club", "hammer", "pistol", "rifle", "bow", "wand", "cane", "crowbar", "tool", "wrench", "sickle", "machete", "baton")),
    ("OFF", "Off hand", ("shield", "lantern", "torch", "buckler")),
    ("WRIST", "Wrists", ("glove", "bracer", "bracelet", "gauntlet", "wristband", "cuff", "watch", "mitten")),
    ("FINGER", "Fingers", ("ring", "signet", "band")),
    ("WAIST", "Waist", ("belt", "sash", "sheath", "holster", "girdle", "bandolier")),
    ("LEGS", "Legs", ("trousers", "pants", "leggings", "breeches", "jeans", "skirt", "kilt", "greaves", "slacks", "shorts", "hose", "chaps")),
    ("FEET", "Feet", ("boot", "boots", "shoe", "shoes", "sandal", "sandals", "sneaker", "sneakers", "slipper", "slippers", "moccasin", "clog")),
)
GEAR_SLOT_CODES: tuple[str, ...] = tuple(code for code, _label, _keys in GEAR_SLOTS)
GEAR_SLOT_LABELS: dict[str, str] = {code: label for code, label, _keys in GEAR_SLOTS}
CARRIED = ""
"""Slot value for an item that is carried, not worn."""

REQUIRED_GEAR_SLOTS: tuple[str, ...] = ("FEET", "TORSO", "LEGS")
"""Every character starts clothed: boots, torso, legs. These cards cannot be removed."""

LEGACY_PLACEHOLDER_NAMES: frozenset[str] = frozenset({"boots", "tunic", "trousers"})
"""The bare names the setup page once gave the basics when the engine did not answer.

Saves kept them in the start form's ``starter_equipment`` string, so a later
start restored them and they became the kit (playtest #17). On an unlocked
required card with nothing else written, they mean "not named yet"."""

EXCLUSIVE_SLOTS: frozenset[str] = frozenset({"HEAD", "TORSO", "UNDER", "BACK", "MAIN", "OFF", "WAIST", "LEGS", "FEET"})
"""One worn item each at Start; a second item for the same slot is carried."""

RARITIES: tuple[str, ...] = ("common", "uncommon", "rare", "unique", "legendary")
START_RARITY_CAP = {"near_useless": "common", "weak": "uncommon", "normal": "uncommon", "strong": "rare", "overpowered": "rare"}

MAX_GEAR_ITEMS = 12
MAX_GEAR_ABILITIES = 4
PER_ITEM_BONUS_MIN = -2
PER_ITEM_BONUS_MAX = 3
START_BONUS_TOTAL_CAP = {"near_useless": 1, "weak": 1, "normal": 2, "strong": 4, "overpowered": 6}
"""Sum of positive stat bonuses across all starting gear, by start power."""

ITEM_STAT_KEYS: tuple[str, ...] = ("weight", "durability", "protection", "value", "rarity")
ABILITY_POWER_TYPES = ("compounding", "passive", "linear", "soft_cap", "breakthrough", "flat", "item_bound")

_SLOT_ALIASES = {
    "": CARRIED,
    "carried": CARRIED,
    "carry": CARRIED,
    "pocket": CARRIED,
    "pockets": CARRIED,
    "bag": CARRIED,
    "none": CARRIED,
    "inventory": CARRIED,
    "packed": CARRIED,
    "hand": "MAIN",
    "hands": "WRIST",
    "main_hand": "MAIN",
    "mainhand": "MAIN",
    "off_hand": "OFF",
    "offhand": "OFF",
    "body": "TORSO",
    "chest": "TORSO",
    "armor": "TORSO",
    "armour": "TORSO",
    "upper": "TORSO",
    "under": "UNDER",
    "underarmor": "UNDER",
    "shoulders": "BACK",
    "feet": "FEET",
    "foot": "FEET",
    "boots": "FEET",
    "shoes": "FEET",
    "legs": "LEGS",
    "leg": "LEGS",
    "lower": "LEGS",
    "pants": "LEGS",
    "trousers": "LEGS",
    "head": "HEAD",
    "neck": "NECK",
    "wrist": "WRIST",
    "wrists": "WRIST",
    "finger": "FINGER",
    "fingers": "FINGER",
    "ring": "FINGER",
    "waist": "WAIST",
    "belt": "WAIST",
    "back": "BACK",
}

_WORN_WORDS = ("worn", "patched", "frayed", "cracked", "threadbare", "secondhand", "second-hand", "old", "scuffed", "faded", "mended", "travel-worn", "stained", "salt-stained", "rough", "tattered")
_FINE_WORDS = ("new", "fine", "sturdy", "well-made", "well made", "polished", "quality", "tailored", "reinforced", "pressed")


def _float(value: Any, default: float) -> float:
    try:
        if isinstance(value, bool):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int) -> int:
    try:
        if isinstance(value, bool):
            return default
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _clean_text(value: Any, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


# ---------------------------------------------------------------------------
# Slots
# ---------------------------------------------------------------------------
def normalize_slot(value: Any) -> str:
    """Coerce a model's or user's slot word onto a slot code, or CARRIED."""
    text = str(value or "").strip()
    if not text:
        return CARRIED
    key = re.sub(r"[^a-z_]+", "_", text.lower()).strip("_")
    if key.upper() in GEAR_SLOT_CODES:
        return key.upper()
    if key in _SLOT_ALIASES:
        return _SLOT_ALIASES[key]
    for code, label, keywords in GEAR_SLOTS:
        if key == label.lower().replace(" ", "_") or key in keywords:
            return code
    return CARRIED


def slot_for_name(name: str) -> str:
    """Best body slot for an item name, or CARRIED when it is not worn."""
    low = f" {str(name or '').lower()} "
    for code, _label, keywords in GEAR_SLOTS:
        for word in keywords:
            if re.search(rf"\b{re.escape(word)}s?\b", low):
                return code
    return CARRIED


# ---------------------------------------------------------------------------
# World context
# ---------------------------------------------------------------------------
def gear_context_from_setup(setup: dict[str, Any] | None) -> dict[str, Any]:
    """The slice of a setup (form snapshot or playthrough options) gear rolls read."""
    setup = setup if isinstance(setup, dict) else {}
    intent = setup.get("_compose_intent") if isinstance(setup.get("_compose_intent"), dict) else {}
    pf = intent.get("power_fantasy") if isinstance(intent.get("power_fantasy"), dict) else {}
    theme = setup.get("session_theme") if isinstance(setup.get("session_theme"), dict) else {}
    difficulty = str(setup.get("difficulty") or "normal").strip().lower()
    start_power = str(pf.get("start_power") or "").strip().lower()
    if start_power not in START_BONUS_TOTAL_CAP:
        start_power = {"brutal": "weak", "hard": "weak", "easy": "strong"}.get(difficulty, "normal")
    return {
        "world_style": str(setup.get("world_style") or intent.get("genre") or theme.get("genre") or "").strip(),
        "custom_style": str(setup.get("custom_style") or "").strip(),
        "tech_level": str(setup.get("tech_level") or "").strip().lower(),
        "magic_level": str(setup.get("magic_level") or "").strip().lower(),
        "economy": str(setup.get("economy") or "").strip().lower(),
        "loot_rarity": str(setup.get("loot_rarity") or "").strip().lower(),
        "difficulty": difficulty,
        "start_power": start_power,
        "start_location": str(setup.get("start_location") or "").strip(),
        "player_sex": str(setup.get("player_sex") or "").strip(),
        "world_races": str(setup.get("world_races") or "").strip(),
        "backstory_mode": str(setup.get("backstory_mode") or "").strip().lower(),
        "isekai": bool(intent.get("isekai") or theme.get("isekai")),
    }


def _is_modern(ctx: dict[str, Any]) -> bool:
    blob = f"{ctx.get('tech_level', '')} {ctx.get('world_style', '')}".lower()
    return any(k in blob for k in ("modern", "near future", "near-future", "cyber", "urban", "contemporary", "present day", "industrial", "20", "sci-fi", "space", "starship", "digital"))


def _is_ancient(ctx: dict[str, Any]) -> bool:
    blob = f"{ctx.get('tech_level', '')} {ctx.get('world_style', '')}".lower()
    return any(k in blob for k in ("ancient", "bronze", "stone age", "tribal", "classical"))


def _is_spacefaring(ctx: dict[str, Any]) -> bool:
    blob = f"{ctx.get('tech_level', '')} {ctx.get('world_style', '')}".lower()
    return any(k in blob for k in ("space", "starship", "orbital", "interstellar", "sci-fi", "scifi"))


def _is_cold(ctx: dict[str, Any]) -> bool:
    blob = f"{ctx.get('world_style', '')} {ctx.get('custom_style', '')} {ctx.get('start_location', '')}".lower()
    return any(k in blob for k in ("snow", "frost", "tundra", "winter", "ice", "glacier", "north", "cold"))


# ---------------------------------------------------------------------------
# Required basics
# ---------------------------------------------------------------------------
def required_gear_defaults(context: dict[str, Any] | None = None, rng: random.Random | None = None) -> list[dict[str, Any]]:
    """The three basics, named for this world's tech and climate. Mundane on purpose."""
    ctx = context or {}
    rng = rng or random.Random()
    if _is_spacefaring(ctx):
        feet, torso, legs = ("ship boots", "work jacket", "utility trousers")
    elif _is_modern(ctx):
        feet = rng.choice(("canvas sneakers", "scuffed trainers", "work shoes"))
        torso = rng.choice(("hooded jacket", "zip hoodie", "light jacket"))
        legs = rng.choice(("denim trousers", "work trousers", "jeans"))
    elif _is_ancient(ctx):
        feet, torso, legs = ("leather sandals", "linen tunic", "linen wrap")
    else:
        feet = rng.choice(("leather boots", "worn boots", "soft-soled boots"))
        torso = rng.choice(("wool tunic", "linen shirt", "patched tunic"))
        legs = rng.choice(("wool trousers", "patched trousers", "rough breeches"))
    if _is_cold(ctx):
        torso = rng.choice(("fur-lined coat", "wool coat", "quilted jacket"))
    return [
        _blank_item(feet, "FEET", required=True),
        _blank_item(torso, "TORSO", required=True),
        _blank_item(legs, "LEGS", required=True),
    ]


def _blank_item(name: str, slot: str, *, required: bool = False) -> dict[str, Any]:
    return {
        "name": name,
        "slot": slot,
        "required": required,
        "keep": False,
        "description": "",
        "stats": {},
        "item_stats": {},
        "abilities": [],
    }


# ---------------------------------------------------------------------------
# Rolls
# ---------------------------------------------------------------------------
_SLOT_BASE_WEIGHT = {"HEAD": 0.3, "NECK": 0.1, "TORSO": 1.2, "UNDER": 0.4, "BACK": 1.0, "MAIN": 1.0, "OFF": 1.0, "WRIST": 0.2, "FINGER": 0.05, "WAIST": 0.4, "LEGS": 0.7, "FEET": 0.8, CARRIED: 0.5}
_SLOT_BASE_VALUE = {"HEAD": 3, "NECK": 4, "TORSO": 8, "UNDER": 3, "BACK": 5, "MAIN": 5, "OFF": 4, "WRIST": 3, "FINGER": 4, "WAIST": 3, "LEGS": 5, "FEET": 6, CARRIED: 2}
_RARITY_VALUE_MULT = {"common": 1.0, "uncommon": 3.0, "rare": 9.0, "unique": 20.0, "legendary": 40.0}
_SLOT_BONUS_STAT = {
    "FEET": ("dexterity",),
    "TORSO": ("constitution",),
    "LEGS": ("dexterity", "constitution"),
    "HEAD": ("wisdom", "intelligence"),
    "NECK": ("charisma", "wisdom"),
    "FINGER": ("charisma", "intelligence"),
    "MAIN": ("strength", "dexterity"),
    "OFF": ("strength", "constitution"),
    "WRIST": ("dexterity",),
    "WAIST": ("constitution",),
    "BACK": ("constitution",),
    "UNDER": ("constitution",),
}
_BONUS_CHANCE = {"near_useless": 0.06, "weak": 0.10, "normal": 0.18, "strong": 0.35, "overpowered": 0.5}


def _weight_for(name: str, slot: str, rng: random.Random) -> float:
    low = name.lower()
    base = _SLOT_BASE_WEIGHT.get(slot, 0.5)
    if slot == "TORSO":
        if any(k in low for k in ("plate", "mail", "cuirass", "armor", "armour")):
            base = 6.0
        elif any(k in low for k in ("coat", "parka", "fur")):
            base = 1.6
        elif any(k in low for k in ("leather", "quilted", "padded", "jerkin")):
            base = 2.2
    elif slot == "MAIN":
        if any(k in low for k in ("knife", "dagger", "wand")):
            base = 0.3
        elif any(k in low for k in ("staff", "spear", "rifle", "hammer")):
            base = 1.5
    elif slot == "BACK" and any(k in low for k in ("pack", "rucksack", "knapsack")):
        base = 1.5
    elif slot == CARRIED:
        if any(k in low for k in ("rope", "coil")):
            base = 1.5
        elif any(k in low for k in ("vial", "coin", "key", "card", "note", "chalk", "pen", "needle", "charm", "mints")):
            base = 0.1
        elif any(k in low for k in ("bread", "ration", "loaf", "fish", "snack", "bar")):
            base = 0.3
        elif any(k in low for k in ("water", "flask", "skin", "bottle", "cup")):
            base = 0.7
        elif any(k in low for k in ("tool", "wrench", "hammer", "pouch", "bag")):
            base = 0.8
    return round(base * rng.uniform(0.85, 1.15), 2)


def _protection_for(name: str, slot: str) -> int:
    low = name.lower()
    if slot == "TORSO":
        if any(k in low for k in ("plate", "cuirass")):
            return 5
        if any(k in low for k in ("mail", "armor", "armour", "brigandine")):
            return 4
        if any(k in low for k in ("leather", "padded", "quilted", "gambeson", "jerkin")):
            return 2
        if any(k in low for k in ("coat", "jacket", "vest", "parka", "cloak")):
            return 1
        return 0
    if slot == "LEGS":
        if "greave" in low or "plate" in low:
            return 2
        if "leather" in low or "reinforced" in low:
            return 1
        return 0
    if slot == "FEET":
        return 1 if "boot" in low else 0
    if slot == "HEAD":
        if any(k in low for k in ("helm", "helmet")):
            return 2
        if any(k in low for k in ("cap", "hood")):
            return 1 if "leather" in low else 0
        return 0
    if slot == "OFF" and "shield" in low:
        return 3 if any(k in low for k in ("iron", "steel", "tower")) else 2
    if slot == "WRIST" and any(k in low for k in ("bracer", "gauntlet")):
        return 1
    return 0


def _durability_for(name: str, ctx: dict[str, Any], rng: random.Random) -> int:
    low = name.lower()
    if any(k in low for k in _FINE_WORDS):
        return rng.randint(75, 98)
    if any(k in low for k in _WORN_WORDS):
        return rng.randint(30, 60)
    if "scarce" in str(ctx.get("economy") or "") or ctx.get("start_power") in {"near_useless", "weak"}:
        return rng.randint(40, 72)
    return rng.randint(55, 90)


def _rarity_for(name: str, ctx: dict[str, Any], rng: random.Random) -> str:
    low = name.lower()
    if any(k in low for k in ("bread", "loaf", "ration", "food", "fish", "snack", "bar", "water", "flask", "bottle", "cup", "mints", "meal", "fruit", "cheese")):
        return "common"
    cap = START_RARITY_CAP.get(str(ctx.get("start_power") or "normal"), "uncommon")
    chance = 0.12
    if any(k in low for k in ("charm", "amulet", "rune", "sigil", "relic", "talisman", "enchanted", "glowing")):
        chance = 0.45
    if "legend" in str(ctx.get("loot_rarity") or "") or "generous" in str(ctx.get("loot_rarity") or ""):
        chance += 0.1
    if "rare" in str(ctx.get("loot_rarity") or "") or "earned" in str(ctx.get("loot_rarity") or ""):
        chance -= 0.05
    rolled = "uncommon" if rng.random() < max(0.0, chance) else "common"
    if rolled == "uncommon" and cap == "common":
        rolled = "common"
    return rolled


def _value_for(slot: str, rarity: str, ctx: dict[str, Any], rng: random.Random) -> int:
    base = _SLOT_BASE_VALUE.get(slot, 2) * _RARITY_VALUE_MULT.get(rarity, 1.0)
    economy = str(ctx.get("economy") or "")
    if "scarce" in economy or "barter" in economy:
        base *= 0.7
    elif any(k in economy for k in ("coin", "prosper", "rich", "wealth", "trade")):
        base *= 1.4
    return max(0, int(round(base * rng.uniform(0.7, 1.3))))


def roll_item_stats(item: dict[str, Any], context: dict[str, Any] | None = None, rng: random.Random | None = None, *, force: bool = False) -> dict[str, Any]:
    """
    The item's own numbers, from its name, slot and the world.

    Keys the item already carries are kept unless ``force``. Returns a complete
    ``item_stats`` dict.
    """
    ctx = context or {}
    rng = rng or random.Random()
    name = str(item.get("name") or "")
    slot = normalize_slot(item.get("slot"))
    have = item.get("item_stats") if isinstance(item.get("item_stats"), dict) and not force else {}
    out: dict[str, Any] = {}
    rarity = str(have.get("rarity") or "").strip().lower()
    out["rarity"] = rarity if rarity in RARITIES else _rarity_for(name, ctx, rng)
    out["weight"] = round(max(0.0, min(200.0, _float(have.get("weight"), -1.0))), 2) if _float(have.get("weight"), -1.0) >= 0 else _weight_for(name, slot, rng)
    dur = _int(have.get("durability"), -1)
    out["durability"] = max(0, min(100, dur)) if dur >= 0 else _durability_for(name, ctx, rng)
    prot = _int(have.get("protection"), -1)
    out["protection"] = max(0, min(10, prot)) if prot >= 0 else _protection_for(name, slot)
    val = _int(have.get("value"), -1)
    out["value"] = max(0, min(100000, val)) if val >= 0 else _value_for(slot, out["rarity"], ctx, rng)
    return out


def roll_stat_bonuses(item: dict[str, Any], context: dict[str, Any] | None = None, rng: random.Random | None = None) -> dict[str, int]:
    """
    Bonuses to the wearer. Usually nothing; sometimes one +1 that fits the slot.

    Carried items grant nothing. The list-level cap in ``normalize_gear_list``
    keeps the total modest for a weak start.
    """
    ctx = context or {}
    rng = rng or random.Random()
    slot = normalize_slot(item.get("slot"))
    if slot == CARRIED or slot not in _SLOT_BONUS_STAT:
        return {}
    chance = _BONUS_CHANCE.get(str(ctx.get("start_power") or "normal"), 0.18)
    rarity = str((item.get("item_stats") or {}).get("rarity") or "common")
    if rarity != "common":
        chance += 0.25
    if rng.random() >= chance:
        return {}
    stat = rng.choice(_SLOT_BONUS_STAT[slot])
    amount = 2 if rarity in {"rare", "unique", "legendary"} and rng.random() < 0.5 else 1
    return {stat: amount}


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------
def normalize_stat_bonuses(value: Any) -> dict[str, int]:
    """Canonical stat keys only, integers, clamped per item; zero entries dropped."""
    raw = value
    if isinstance(raw, str):
        parts: dict[str, Any] = {}
        for piece in re.split(r"[,;]+", raw):
            m = re.match(r"\s*([A-Za-z ]+?)\s*[:=]?\s*([+-]?\d+)\s*$", piece) or re.match(r"\s*([+-]?\d+)\s*([A-Za-z ]+?)\s*$", piece)
            if not m:
                continue
            a, b = m.group(1), m.group(2)
            key, num = (a, b) if not re.match(r"[+-]?\d+", a) else (b, a)
            parts[key.strip()] = num
        raw = parts
    if isinstance(raw, list):
        merged: dict[str, Any] = {}
        for entry in raw:
            if isinstance(entry, dict):
                key = entry.get("stat") or entry.get("name") or entry.get("key")
                val = entry.get("delta", entry.get("value", entry.get("bonus", entry.get("modifier"))))
                if key is not None:
                    merged[str(key)] = val
        raw = merged
    if not isinstance(raw, dict):
        return {}
    out: dict[str, int] = {}
    for key, val in raw.items():
        canon = normalize_stat_key(key)
        if canon not in STAT_KEYS:
            continue
        amount = _int(val, 0)
        amount = max(PER_ITEM_BONUS_MIN, min(PER_ITEM_BONUS_MAX, amount))
        if amount:
            out[canon] = out.get(canon, 0) + amount
    return {k: max(PER_ITEM_BONUS_MIN, min(PER_ITEM_BONUS_MAX, v)) for k, v in out.items() if v}


def normalize_gear_ability(raw: Any, item_name: str = "") -> dict[str, Any] | None:
    """One ability on an item, in the special-ability shape. ``None`` when empty."""
    if isinstance(raw, str):
        raw = {"name": raw}
    if not isinstance(raw, dict):
        return None
    name = _clean_text(raw.get("name"), 100)
    description = _clean_text(raw.get("description") or raw.get("base_description"), 800)
    if not name and not description:
        return None
    if not name:
        name = _clean_text(description.split(".")[0], 60) or "Item trick"
    power_type = str(raw.get("power_type") or "item_bound").strip().lower().replace("-", "_").replace(" ", "_")
    if power_type not in ABILITY_POWER_TYPES:
        power_type = "item_bound"
    cost = _clean_text(raw.get("cost"), 300)
    return {
        "name": name,
        "description": description or (f"Granted by {item_name}." if item_name else "Granted by this item."),
        "locked": bool(raw.get("locked")),
        "prerequisites": _clean_text(raw.get("prerequisites"), 500),
        "cost": cost,
        "growth_math": _clean_text(raw.get("growth_math"), 800),
        "power_type": power_type,
    }


def normalize_gear_item(
    raw: Any,
    *,
    context: dict[str, Any] | None = None,
    rng: random.Random | None = None,
    roll_missing: bool = True,
    trust: bool = True,
) -> dict[str, Any] | None:
    """
    One item, validated. Blank numbers are rolled from the world when ``roll_missing``.

    Returns ``None`` for an entry with no usable name.
    """
    if isinstance(raw, str):
        raw = {"name": raw}
    if not isinstance(raw, dict):
        return None
    name = _clean_text(raw.get("name") or raw.get("item"), 80).strip(" .,;:")
    if len(name) < 2:
        return None
    slot_in = raw.get("slot", raw.get("worn", raw.get("zone")))
    slot = normalize_slot(slot_in) if str(slot_in or "").strip() else slot_for_name(name)
    # A worn word in the slot box the model made up ("legs/feet") still lands on the name's slot.
    if slot == CARRIED and str(slot_in or "").strip():
        slot = slot_for_name(name)
    # Model output (trust=False): the item's own name outranks the slot the
    # model picked. Qwen3 8B put a pocket knife on WRIST and a satchel on
    # WAIST. A player's card keeps whatever slot the player chose.
    if not trust:
        by_name = slot_for_name(name)
        if by_name and by_name != slot:
            slot = by_name
        elif not by_name and slot in {"FINGER", "NECK", "WRIST"}:
            # Jewellery slots need a name that fits them; "wooden comb" went on FINGER.
            slot = CARRIED
    item = {
        "name": name,
        "slot": slot,
        "required": bool(raw.get("required")),
        "keep": bool(raw.get("keep") or raw.get("locked_card")),
        "description": _clean_text(raw.get("description") or raw.get("effect") or raw.get("rules"), 300),
        "stats": normalize_stat_bonuses(raw.get("stats") if "stats" in raw else raw.get("stat_bonuses", raw.get("stat_modifiers", raw.get("bonuses")))),
        "item_stats": {},
        "abilities": [],
    }
    raw_stats = raw.get("item_stats") if isinstance(raw.get("item_stats"), dict) else {}
    # Flat keys the model may use instead of the nested block.
    for key in ITEM_STAT_KEYS:
        if key not in raw_stats and key in raw:
            raw_stats = {**raw_stats, key: raw.get(key)}
    item["item_stats"] = roll_item_stats({**item, "item_stats": raw_stats}, context, rng) if roll_missing else {k: raw_stats[k] for k in ITEM_STAT_KEYS if k in raw_stats}
    if not trust and "weight" in item["item_stats"]:
        # Boots at 6 kg and an empty satchel at 4 kg came back from the model.
        # Far from the engine's estimate for this name and slot, the estimate wins.
        estimate = _weight_for(name, slot, random.Random(0))
        given = _float(item["item_stats"].get("weight"), estimate)
        if estimate > 0 and not (estimate / 3.0 <= given <= estimate * 3.0):
            item["item_stats"]["weight"] = round(estimate, 2)
    if roll_missing and "stats" not in raw and not item["stats"] and not any(k in raw for k in ("stat_bonuses", "stat_modifiers", "bonuses")):
        item["stats"] = roll_stat_bonuses(item, context, rng)
        item["_stats_rolled"] = True
    if item["slot"] == CARRIED:
        # Stat bonuses apply to the wearer while worn; a carried item gives none.
        item["stats"] = {}
    abilities_raw = raw.get("abilities") if raw.get("abilities") is not None else raw.get("granted_abilities")
    if isinstance(abilities_raw, (str, dict)):
        abilities_raw = [abilities_raw]
    for entry in abilities_raw or []:
        ability = normalize_gear_ability(entry, name)
        if ability:
            item["abilities"].append(ability)
        if len(item["abilities"]) >= MAX_GEAR_ABILITIES:
            break
    return item


def is_placeholder_basic(raw: Any) -> bool:
    """
    True for a basic the page named with a placeholder: a bare
    ``LEGACY_PLACEHOLDER_NAMES`` word on a worn basic slot, unlocked, with no
    description and no abilities. A player's own card has more than that, or
    a lock.
    """
    if isinstance(raw, str):
        raw = {"name": raw}
    if not isinstance(raw, dict):
        return False
    name = _clean_text(raw.get("name") or raw.get("item"), 80).strip(" .,;:").lower()
    if name not in LEGACY_PLACEHOLDER_NAMES:
        return False
    if raw.get("keep") or raw.get("locked_card"):
        return False
    if _clean_text(raw.get("description") or raw.get("effect"), 300) or raw.get("abilities"):
        return False
    slot_in = str(raw.get("slot") or "").strip()
    slot = normalize_slot(slot_in) if slot_in else slot_for_name(name)
    return slot in REQUIRED_GEAR_SLOTS


def normalize_gear_list(
    raw_list: Any,
    *,
    context: dict[str, Any] | None = None,
    rng: random.Random | None = None,
    fill_required: bool = True,
    roll_missing: bool = True,
    trust: bool = True,
) -> list[dict[str, Any]]:
    """
    The whole starting kit, validated.

    * Entries with no name are dropped; names are unique (case-insensitive).
    * The three required slots are always present (engine basics fill a gap).
      A placeholder basic (``is_placeholder_basic``) counts as a gap.
    * One worn item per exclusive slot; a second one is carried.
    * Positive stat bonuses across the kit are capped by start power.
    * At most ``MAX_GEAR_ITEMS`` items; required ones are never the ones cut.
    """
    ctx = context or {}
    rng = rng or random.Random()
    if isinstance(raw_list, dict):
        raw_list = raw_list.get("starter_gear") or raw_list.get("items") or [raw_list]
    if isinstance(raw_list, str):
        raw_list = gear_from_legacy_text(raw_list)
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in raw_list if isinstance(raw_list, list) else []:
        if fill_required and is_placeholder_basic(entry):
            continue
        item = normalize_gear_item(entry, context=ctx, rng=rng, roll_missing=roll_missing, trust=trust)
        if not item or item["name"].lower() in seen:
            continue
        seen.add(item["name"].lower())
        items.append(item)

    # One worn item per exclusive slot; a required card keeps its slot.
    worn: dict[str, int] = {}
    for index, item in enumerate(items):
        slot = item["slot"]
        if slot in EXCLUSIVE_SLOTS:
            holder = worn.get(slot)
            if holder is None or (item["required"] and not items[holder]["required"]):
                if holder is not None:
                    items[holder]["slot"] = CARRIED
                    items[holder]["required"] = False
                worn[slot] = index
            else:
                item["slot"] = CARRIED
                item["required"] = False
    for slot in REQUIRED_GEAR_SLOTS:
        if slot in worn:
            items[worn[slot]]["required"] = True

    if fill_required:
        defaults = {d["slot"]: d for d in required_gear_defaults(ctx, rng)}
        for slot in REQUIRED_GEAR_SLOTS:
            if slot in worn:
                continue
            basic = defaults[slot]
            if basic["name"].lower() in seen:
                basic["name"] = f"plain {basic['name']}"
            basic = normalize_gear_item(basic, context=ctx, rng=rng, roll_missing=roll_missing) or basic
            basic["required"] = True
            seen.add(basic["name"].lower())
            items.append(basic)
            worn[slot] = len(items) - 1

    # Required basics first in slot order, then the rest as given.
    order = {slot: i for i, slot in enumerate(REQUIRED_GEAR_SLOTS)}
    items.sort(key=lambda it: (0, order[it["slot"]]) if it["required"] and it["slot"] in order else (1, 0))
    if len(items) > MAX_GEAR_ITEMS:
        keep = [it for it in items if it["required"]]
        rest = [it for it in items if not it["required"]]
        items = keep + rest[: MAX_GEAR_ITEMS - len(keep)]

    # Cap the kit's total positive bonus by start power.
    # Engine-rolled bonuses give way first (last rolled first), then the ones
    # the model or the player wrote, from the end of the kit.
    cap = START_BONUS_TOTAL_CAP.get(str(ctx.get("start_power") or "normal"), 2)
    total = sum(v for it in items for v in it["stats"].values() if v > 0)
    rolled = [it for it in reversed(items) if it.get("_stats_rolled")]
    given = [it for it in reversed(items) if not it.get("_stats_rolled")]
    for item in rolled + given:
        if total <= cap:
            break
        for stat in list(item["stats"]):
            while item["stats"].get(stat, 0) > 0 and total > cap:
                item["stats"][stat] -= 1
                total -= 1
            if item["stats"].get(stat) == 0:
                del item["stats"][stat]
    for item in items:
        item.pop("_stats_rolled", None)
    return items


# ---------------------------------------------------------------------------
# Back-compat with the comma-separated string
# ---------------------------------------------------------------------------
def gear_names(items: list[dict[str, Any]] | None) -> str:
    """The legacy ``starter_equipment`` string: names only, comma-separated."""
    names: list[str] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        name = _clean_text(item.get("name"), 80)
        if name and name.lower() not in {n.lower() for n in names}:
            names.append(name)
    return ", ".join(names)[:500]


def gear_from_legacy_text(text: Any) -> list[dict[str, Any]]:
    """Items from the old comma-separated string (or the old 'name (slot) [type] — effect' lines)."""
    raw = str(text or "").strip()
    if not raw:
        return []
    items: list[dict[str, Any]] = []
    for line in re.split(r"[;\n]+|,(?![^()]*\))", raw):
        line = line.strip()
        if not line:
            continue
        slot_m = re.search(r"\(([^)]+)\)", line)
        effect = ""
        split = re.split(r"\s*[—–]\s*|\s+-\s+", line, maxsplit=1)
        if len(split) == 2:
            line, effect = split[0], split[1]
        name = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", line)
        name = _clean_text(name, 80).strip(" .,;:")
        if len(name) < 2:
            continue
        items.append({"name": name, "slot": slot_m.group(1) if slot_m else "", "description": effect.strip()})
    return items[:MAX_GEAR_ITEMS]


def gear_prompt_contract() -> dict[str, Any]:
    """What the model is told about the shape. No example item names: a 7B pastes them."""
    return {
        "return_shape": {
            "starter_gear": [
                {
                    "name": "item name, 1-4 words",
                    "slot": "one of " + "/".join(GEAR_SLOT_CODES) + " for worn items, or empty string when carried",
                    "description": "one sentence: what it is in this world, its material and condition",
                    "stats": {"<one of " + "/".join(STAT_KEYS) + ">": "integer bonus to the wearer while worn; usually omit"},
                    "item_stats": {"weight": "kg", "durability": "0-100", "protection": "0-10", "value": "coins", "rarity": "/".join(RARITIES[:3])},
                    "abilities": [],
                }
            ]
        },
        "slot_codes": list(GEAR_SLOT_CODES),
        "required_slots": list(REQUIRED_GEAR_SLOTS),
        "stat_keys": list(STAT_KEYS),
        "item_stat_keys": list(ITEM_STAT_KEYS),
        "rules": [
            "Every kit has one worn item in each of FEET, TORSO and LEGS. Those three cards exist already; rewrite their name and description for this world unless they are locked.",
            "Fit the world_style, tech_level, climate, the character's sex and race, their origin and backstory, their clothes in appearance, and start_location. Use local materials and local names for things.",
            "Mundane at Start: ordinary cloth, leather, wood, iron, or this world's everyday tech. No legendary, enchanted, or military-grade gear unless the setup says the character starts strong.",
            "stats and item_stats may be left out; the engine rolls them from the world. When you give stats, keep them to one +1 on at most one item for a weak start.",
            "abilities stays an empty list unless the setup explicitly gives an item a power.",
            "Return 3 to 7 items in total: the three worn basics plus a few carried or worn extras that fit the character.",
        ],
    }
