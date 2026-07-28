"""
Starter gear / clothing fact-check at setup and Start.

Question to answer: "If they have this when the player presses Start, where did it
come from under this arrival story?"

- Native / known life in-world: local mundane gear OK if life fits.
- Reincarnated / aged into this world: gear from *this* life only (no old-world kit).
- Pure isekai / summoned / just-transported: only what could be on them at arrival
  (clothes, pockets) — not fantasy shields/swords unless the world *is* modern LARP.
- Born / native / this-life ordinary starts: no powerful starter items. Clothing and kit
  must match the backstory vocation (no plate for a baker, no mage robes for a clerk).
- Starter pieces stay *mundane at Start* (common, no enchantments, no granted abilities).
  A long-held starter item may later gain a hidden property only as a DM choice mid/late
  campaign special event — never pre-powered at Start.

When origin/backstory/gear clash with world vibe (e.g. near-future maintenance tech
in a low-tech isekai compound), rewrite origin + backstory + kit as one package so
the life matches the world — do not keep every old item, and do not leave a
modern origin hanging in a mismatched setting.

Deterministic rules first; optional LLM polish can still rewrite prose later.
"""
from __future__ import annotations

import re
from typing import Any

# --- arrival classification -------------------------------------------------

ARRIVAL_NATIVE = "native_life"
ARRIVAL_REINCARNATED = "reincarnated_life"  # lived/grew up here after rebirth
ARRIVAL_TRANSMIGRATED_BODY = "transmigrated_body"  # soul into existing body here
ARRIVAL_ISEKAI_ARRIVAL = "isekai_arrival"  # just arrived / summoned / portal this moment
ARRIVAL_AMNESIA = "amnesia_spawn"

# item provenance buckets
BUCKET_WORN = "body_worn"
BUCKET_POCKET = "pocket_mundane"
BUCKET_TOOL = "trade_tool"
BUCKET_COMBAT = "combat_kit"
BUCKET_MAGIC = "fantasy_magic"
BUCKET_MODERN = "modern_tech"
BUCKET_VALUABLE = "valuable"
BUCKET_CONSUMABLE = "consumable"
BUCKET_LEGENDARY = "legendary"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _split_items(raw: str | list[str] | None) -> list[str]:
    if isinstance(raw, list):
        parts = [str(x) for x in raw]
    else:
        parts = re.split(r"[,;|]+", str(raw or ""))
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        # strip zone prefixes for equipment list: "torso: coat" → "coat"
        text = re.sub(r"\s+", " ", part).strip(" .")
        if ":" in text and len(text.split(":", 1)[0]) <= 12:
            left, right = text.split(":", 1)
            if re.fullmatch(r"[a-zA-Z_]+", left.strip()):
                text = right.strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text[:100])
    return out


def classify_arrival(
    *,
    backstory_mode: str = "",
    memory_policy: str = "",
    character_backstory: str = "",
    intent: dict[str, Any] | None = None,
    world_style: str = "",
    tech_level: str = "",
) -> dict[str, Any]:
    """
    Decide when 'now' is relative to arrival.
    Returns arrival kind + flags used by gear rules.
    """
    intent = intent if isinstance(intent, dict) else {}
    mode = _norm(backstory_mode)
    memory = _norm(memory_policy)
    story = _norm(character_backstory)
    genre = _norm(str(intent.get("genre") or ""))
    portal = _norm(str(intent.get("portal_or_rebirth") or ""))
    isekai_flag = bool(intent.get("isekai"))
    blob = " ".join([mode, memory, story, genre, portal, _norm(world_style)])

    reinc_markers = (
        "reincarnat",
        "reborn",
        "rebirth",
        "born again",
        "second life",
        "grew up in this world",
        "grew up here",
        "raised in this",
        "childhood in this",
    )
    transmig_markers = (
        "transmigrat",
        "woke in another body",
        "woke in someone",
        "into a body",
        "body that was not",
        "possessed",
    )
    arrival_markers = (
        "isekai",
        "summoned",
        "transported",
        "portal",
        "fell into",
        "woke up in another world",
        "opened my eyes in",
        "just arrived",
        "other world",
        "another world",
        "truck-kun",
        "died and woke",
        "hospital stair",
        "desk job",
        "former life",
        "previous life",
        "before dying",
        "after dying",
    )
    amnesia_markers = ("amnesia", "nameless", "no memory", "cannot remember", "blank slate")

    # Mode field first
    if any(m in mode for m in ("amnesia", "hidden", "nameless")):
        kind = ARRIVAL_AMNESIA
    elif "reincarnat" in mode or "reborn" in mode:
        kind = ARRIVAL_REINCARNATED
    elif "transmigrat" in mode:
        # transmigration can mean body-swap into existing life OR sudden other-world
        if any(m in blob for m in reinc_markers) and not any(
            x in blob for x in ("just arrived", "summoned", "portal", "transported")
        ):
            kind = ARRIVAL_TRANSMIGRATED_BODY
        elif isekai_flag or portal in {"other_world", "other-world"} or "another world" in blob:
            # sudden drop: treat as isekai arrival unless story clearly aged in-world
            if any(m in story for m in ("grew up", "years as", "worked as", "for years", "raised")):
                kind = ARRIVAL_TRANSMIGRATED_BODY
            else:
                kind = ARRIVAL_ISEKAI_ARRIVAL
        else:
            kind = ARRIVAL_TRANSMIGRATED_BODY
    elif mode in {"known", "known life", "ordinary", "native"} or mode == "":
        if isekai_flag or any(m in blob for m in arrival_markers):
            # idea says isekai but mode known — still check story
            if any(m in story for m in reinc_markers) and any(
                m in story for m in ("grew up", "years", "childhood", "village", "raised")
            ):
                kind = ARRIVAL_REINCARNATED
            elif any(m in story for m in ("just arrived", "summoned", "portal", "woke in another world", "opened my eyes")):
                kind = ARRIVAL_ISEKAI_ARRIVAL
            elif any(m in story for m in transmig_markers):
                kind = ARRIVAL_TRANSMIGRATED_BODY
            elif isekai_flag and not any(m in story for m in ("grew up", "born in a", "born in the", "raised")):
                kind = ARRIVAL_ISEKAI_ARRIVAL
            else:
                kind = ARRIVAL_NATIVE
        else:
            kind = ARRIVAL_NATIVE
    else:
        kind = ARRIVAL_NATIVE

    # Story overrides soft mode
    if kind == ARRIVAL_NATIVE:
        if any(m in story for m in amnesia_markers) and "remember" not in story[:40]:
            kind = ARRIVAL_AMNESIA
        elif any(m in story for m in reinc_markers) and any(
            m in story for m in ("grew up", "years", "childhood", "raised", "apprentice")
        ):
            kind = ARRIVAL_REINCARNATED
        elif any(m in story for m in ("summoned", "transported through", "portal dumped", "just woke in another")):
            kind = ARRIVAL_ISEKAI_ARRIVAL

    tech = _norm(tech_level) + " " + _norm(world_style) + " " + genre
    modern_world = any(
        t in tech
        for t in (
            "modern",
            "near future",
            "cyber",
            "space",
            "industrial",
            "contemporary",
            "urban fantasy",
            "present day",
            "sci-fi",
            "scifi",
            "neon",
            "megacity",
            "corporation",
        )
    )
    cyberpunk_world = any(
        t in tech for t in ("cyber", "neon", "chrome", "megacorp", "street samurai", "netrunner")
    )
    fantasy_world = any(
        t in (genre + " " + _norm(world_style))
        for t in ("fantasy", "isekai", "wuxia", "cultivation", "medieval", "magic", "sect", "kingdom")
    )
    # Pure cyber/modern without urban-fantasy tag is non-magical by default
    urban_fantasy = "urban fantasy" in tech or "magic in the city" in tech
    if modern_world and not urban_fantasy and not fantasy_world:
        fantasy_world = False
    elif not modern_world and fantasy_world:
        pass
    elif kind == ARRIVAL_ISEKAI_ARRIVAL and not modern_world:
        fantasy_world = True

    return {
        "arrival": kind,
        "isekai": bool(isekai_flag or kind == ARRIVAL_ISEKAI_ARRIVAL or "isekai" in blob),
        "modern_world": modern_world,
        "cyberpunk_world": cyberpunk_world or ("cyber" in tech),
        "fantasy_world": fantasy_world or (kind == ARRIVAL_ISEKAI_ARRIVAL and not modern_world),
        "urban_fantasy": urban_fantasy,
        "allows_this_life_gear": kind
        in {ARRIVAL_NATIVE, ARRIVAL_REINCARNATED, ARRIVAL_TRANSMIGRATED_BODY},
        "allows_old_world_pockets": kind == ARRIVAL_ISEKAI_ARRIVAL,
        "minimal_only": kind == ARRIVAL_AMNESIA,
        "notes": _arrival_note(kind),
    }


def _arrival_note(kind: str) -> str:
    return {
        ARRIVAL_NATIVE: "Player has lived in this world; gear must fit that life and tech.",
        ARRIVAL_REINCARNATED: "Reborn/aged into this world — only this-life gear, not former-world kit.",
        ARRIVAL_TRANSMIGRATED_BODY: "Soul in an existing body — gear can be that body's, not god-loot.",
        ARRIVAL_ISEKAI_ARRIVAL: "Just arrived/summoned — only clothes/pockets from the moment of transport; fantasy arms wait until after Start.",
        ARRIVAL_AMNESIA: "Blank/amnesia start — minimal worn clothes only unless backstory earns more.",
    }.get(kind, "Gear must be causally justified at Start.")


# --- world vibe / origin harmonize ------------------------------------------

# Fantasy / low-tech destination: modern Earth origin should usually be localized.
REGISTER_FANTASY = "fantasy_lowtech"
REGISTER_MODERN = "modern"
REGISTER_CYBER = "cyber"
REGISTER_SCIFI = "scifi"
REGISTER_MIXED = "mixed"

# Origin register (who they *were* / where they came from).
ORIGIN_MODERN_EARTH = "modern_earth"
ORIGIN_NEAR_FUTURE = "near_future"
ORIGIN_LOCAL_WORLD = "local_world"
ORIGIN_UNKNOWN = "unknown"

_MODERN_ORIGIN_MARKERS = (
    "near-future",
    "near future",
    "automated",
    "smartphone",
    "office",
    "desk job",
    "tokyo",
    "commute",
    "subway",
    "apartment",
    "corporation",
    "laptop",
    "wifi",
    "internet",
    "email",
    "high school",
    "college",
    "university",
    "salaryman",
    "office worker",
    "truck-kun",
    "hit by a truck",
    "modern city",
    "present day",
    "21st century",
    "smartphone era",
)

_NEAR_FUTURE_MARKERS = (
    "near-future",
    "near future",
    "automated system",
    "cyberdeck",
    "megacity",
    "chrome",
    "netrunner",
    "drone",
    "android",
    "ai system",
    "server farm",
)

_VOCATION_LOCAL: list[tuple[tuple[str, ...], str, str]] = [
    # (markers, local vocation title, backstory seed)
    (
        ("maintenance", "technician", "repair", "mechanic", "engineer", "fix-it"),
        "compound yard mender",
        "A compound yard mender who kept pumps, belts, and cart fittings running in a river compound. "
        "Ordinary work, ordinary debts — the kind of life that fits a gritty isekai yard, not a free arsenal.",
    ),
    (
        ("courier", "delivery", "messenger"),
        "route runner",
        "A route runner who carried sealed slips and small parcels between compound gates and market stalls.",
    ),
    (
        ("clerk", "accountant", "office"),
        "compound clerk",
        "A compound clerk who tallied grain tallies and gate fees with ink-stained fingers.",
    ),
    (
        ("cook", "chef", "kitchen"),
        "pot-hand cook",
        "A pot-hand cook who worked the compound kitchen line and slept above the smokehouse.",
    ),
    (
        ("farmer", "farm", "crop"),
        "field hand",
        "A field hand who worked terrace plots and knew more about mud and seed than steel.",
    ),
    (
        ("student", "school", "university", "college"),
        "apprentice scribe",
        "An apprentice scribe who copied notices for the compound board and dreamed of a wider road.",
    ),
    (
        ("guard", "soldier", "security"),
        "gate watch hand",
        "A junior gate watch hand who walked the wall with a borrowed spear shift and cheap boots.",
    ),
    (
        ("doctor", "nurse", "medic", "healer"),
        "herb-room helper",
        "A herb-room helper who cleaned bowls and learned salves under a busy compound healer.",
    ),
]

# Modern / near-future clothing & kit → local low-tech equivalents (order matters).
_ITEM_LOCALIZE: list[tuple[str, str]] = [
    (r"\bfrayed maintenance vest\b", "patched canvas work vest"),
    (r"\bmaintenance vest\b", "patched work vest"),
    (r"\bhoodie\b", "coarse hooded tunic"),
    (r"\bsweater\b", "wool work jumper"),
    (r"\bjeans\b", "patched trousers"),
    (r"\bsneakers\b", "scuffed leather shoes"),
    (r"\btrainers\b", "scuffed leather shoes"),
    (r"\bt-shirt\b", "plain work shirt"),
    (r"\btee shirt\b", "plain work shirt"),
    # Dead phones can stay as pocket flavor on pure isekai; only strip when fully localizing long-residence lives.
    (r"\bsmartphone\b", "cracked phone"),
    (r"\bphone\b", "cracked phone"),
    (r"\blaptop\b", ""),
    (r"\bearbuds\b", ""),
    (r"\bheadphones\b", ""),
    (r"\bwater flask\b", "water skin"),
    (r"\bwater bottle\b", "water skin"),
    (r"\bthermos\b", "water skin"),
    (r"\bflask\b", "water skin"),
    (r"\bcanteen\b", "water skin"),
    (r"\bsmall tool pouch\b", "small repair pouch"),
    (r"\btool pouch\b", "repair pouch"),
    (r"\btoolbox\b", ""),
    (r"\btool kit\b", ""),
    (r"\btool belt\b", "cord tool belt"),
    (r"\bmultitool\b", "folding work knife"),
    (r"\bmulti-tool\b", "folding work knife"),
    (r"\bscrewdriver\b", "iron awl"),
    (r"\bwrench\b", "small iron spanner"),
    (r"\bflashlight\b", "stub of candle"),
    (r"\blighter\b", "flint striker"),
    (r"\bwallet\b", "coin purse"),
    (r"\bkeys\b", "iron key ring"),
    (r"\bcredit card\b", ""),
    (r"\bid card\b", ""),
    (r"\bpassport\b", ""),
    (r"\bmessenger bag\b", "worn satchel"),
    (r"\bbackpack\b", "travel pack"),
    (r"\bcracked gloves\b", "cracked work gloves"),
    (r"\bworn boots\b", "worn work boots"),
]


def detect_world_register(
    *,
    world_style: str = "",
    tech_level: str = "",
    intent: dict[str, Any] | None = None,
    magic_level: str = "",
) -> str:
    """Coarse tech/vibe register for the destination world."""
    intent = intent if isinstance(intent, dict) else {}
    blob = " ".join(
        [
            _norm(world_style),
            _norm(tech_level),
            _norm(str(intent.get("genre") or "")),
            _norm(str(intent.get("adapter_hint") or "")),
            _norm(magic_level),
        ]
    )
    if any(t in blob for t in ("cyber", "neon", "chrome", "megacorp", "netrunner")):
        return REGISTER_CYBER
    if any(t in blob for t in ("space", "sci-fi", "scifi", "starship", "colony freighter", "hard sci")):
        return REGISTER_SCIFI
    if any(
        t in blob
        for t in (
            "fantasy",
            "isekai",
            "medieval",
            "cultivation",
            "wuxia",
            "kingdom",
            "sect",
            "compound",
            "iron age",
            "bronze",
            "low magic",
            "gritty growth",
        )
    ):
        # "modern isekai" / urban fantasy can still be mixed
        if any(t in blob for t in ("urban fantasy", "modern fantasy", "contemporary")):
            return REGISTER_MIXED
        return REGISTER_FANTASY
    if any(t in blob for t in ("modern", "present day", "contemporary", "near future", "industrial")):
        return REGISTER_MODERN
    return REGISTER_MIXED


def detect_origin_register(
    *,
    character_backstory: str = "",
    backstory_mode: str = "",
    starter_equipment: str = "",
    appearance: str = "",
) -> str:
    """Who they were / where life story comes from.

    Story text dominates. Modern *gear alone* on a local life does not rewrite origin —
    that is a gear localization/strip problem, not an origin rewrite.
    """
    story = " ".join([_norm(character_backstory), _norm(backstory_mode)])
    gear = " ".join([_norm(starter_equipment), _norm(appearance)])
    local_story = any(
        w in story
        for w in (
            "born in",
            "grew up",
            "village",
            "compound",
            "apprentice",
            "guild",
            "sect",
            "raised in",
            "this world",
            "baker",
            "farmer",
            "militia",
            "caravan",
            "canal village",
        )
    )
    if any(m in story for m in _NEAR_FUTURE_MARKERS):
        return ORIGIN_NEAR_FUTURE
    if any(m in story for m in _MODERN_ORIGIN_MARKERS):
        return ORIGIN_MODERN_EARTH
    if local_story:
        return ORIGIN_LOCAL_WORLD
    # No clear local life — modern gear language can still imply Earth-origin isekai kit.
    if any(
        w in gear
        for w in (
            "hoodie",
            "sneaker",
            "smartphone",
            "jeans",
            "t-shirt",
            "maintenance vest",
            "earbuds",
            "laptop",
        )
    ):
        return ORIGIN_MODERN_EARTH
    return ORIGIN_UNKNOWN


def _pick_local_vocation(story: str, equipment: str, appearance: str) -> tuple[str, str]:
    blob = " ".join([_norm(story), _norm(equipment), _norm(appearance)])
    for markers, title, seed in _VOCATION_LOCAL:
        if any(m in blob for m in markers):
            return title, seed
    return (
        "ordinary compound laborer",
        "An ordinary compound laborer who worked odd jobs at the yard gates — "
        "no hero kit, just the clothes and scrap tools of a working life.",
    )


def _localize_item_name(name: str) -> str | None:
    """Map a modern item to a low-tech equivalent. None = drop. Same string = unchanged."""
    text = str(name or "").strip()
    if not text:
        return None
    low = _norm(text)
    # Already local-ish: leave
    if any(
        w in low
        for w in (
            "tunic",
            "cloak",
            "jerkin",
            "satchel",
            "water skin",
            "waterskin",
            "copper",
            "wooden charm",
            "leather",
            "canvas",
            "cord",
            "iron ",
            "repair pouch",
            "work vest",
            "work glove",
            "work boot",
        )
    ) and not any(w in low for w in ("maintenance", "hoodie", "smartphone", "sneaker", "jeans")):
        return text
    out = text
    for pattern, repl in _ITEM_LOCALIZE:
        if re.search(pattern, out, flags=re.I):
            if not repl:
                return None
            out = re.sub(pattern, repl, out, flags=re.I)
    # If still looks modern after map, drop non-worn tech
    low2 = _norm(out)
    if any(w in low2 for w in ("phone", "laptop", "usb", "wifi", "cyber", "neon jacket")):
        return None
    return out.strip() or None


def _localize_appearance(appearance: str) -> str:
    if not appearance:
        return appearance
    parts: list[str] = []
    for chunk in re.split(r"[;|]+", appearance):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ":" in chunk:
            zone, item = chunk.split(":", 1)
            mapped = _localize_item_name(item.strip())
            if mapped:
                parts.append(f"{zone.strip()}: {mapped}")
        else:
            mapped = _localize_item_name(chunk)
            if mapped:
                parts.append(mapped)
    return "; ".join(parts) if parts else "torso: patched work clothes; feet: practical boots"


def _localize_backstory(
    *,
    old_story: str,
    vocation: str,
    seed: str,
    world_style: str,
    keep_faint_otherworld_memory: bool,
) -> str:
    """Rewrite origin/backstory into world-local life; optional faint otherworld memory."""
    place = "the compound yards"
    ws = _norm(world_style)
    if "compound" in ws:
        place = "the river compound yards"
    elif "kingdom" in ws:
        place = "a market town under the local banner"
    elif "frontier" in ws:
        place = "a frontier work camp"
    elif "sect" in ws or "cultivat" in ws:
        place = "the outer work courts of a minor sect compound"

    core = seed
    if vocation and vocation not in core.lower():
        core = f"{seed.rstrip('.')} Known locally as a {vocation}."
    if keep_faint_otherworld_memory:
        core = (
            f"{core.rstrip('.')} "
            "Strange half-memories of another life's machines and glass towers still surface in dreams, "
            "but the body and debts of this life are what matter at dawn."
        )
    # Preserve short player-specific hooks if they were short and non-modern
    old = str(old_story or "").strip()
    if old and len(old) < 80 and not any(m in _norm(old) for m in _MODERN_ORIGIN_MARKERS + _NEAR_FUTURE_MARKERS):
        return f"{core} Hook: {old}"[:1600]
    # Tag place once
    if place not in core.lower():
        core = f"{core.rstrip('.')} Work and sleep are in {place}."
    return core[:1600]


def harmonize_identity_to_world_vibe(
    *,
    character_backstory: str = "",
    backstory_mode: str = "",
    memory_policy: str = "",
    starter_equipment: str | list[str] | None = None,
    appearance: str = "",
    world_style: str = "",
    tech_level: str = "",
    magic_level: str = "",
    intent: dict[str, Any] | None = None,
    arrival: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Align origin + backstory + clothes/kit with destination world vibe.

    When a modern/near-future origin is dropped into fantasy_lowtech, localize the
    life (origin, vocation, clothes, tools) instead of keeping a free modern kit
    or leaving a lore-clashing Earth job intact.

    Pure portal isekai with an *explicit* just-arrived modern life can keep Earth
    origin — but then gear stays thin (worn + tiny pockets), not a full work kit.
    """
    intent = intent if isinstance(intent, dict) else {}
    arrival = arrival if isinstance(arrival, dict) else {}
    register = detect_world_register(
        world_style=world_style,
        tech_level=tech_level,
        intent=intent,
        magic_level=magic_level,
    )
    origin = detect_origin_register(
        character_backstory=character_backstory,
        backstory_mode=backstory_mode,
        starter_equipment=str(starter_equipment or ""),
        appearance=appearance,
    )
    items = _split_items(starter_equipment)
    story = str(character_backstory or "")
    mode = _norm(backstory_mode)
    notes: list[str] = []

    modern_origin = origin in {ORIGIN_MODERN_EARTH, ORIGIN_NEAR_FUTURE}
    fantasy_dest = register == REGISTER_FANTASY
    story_low = _norm(story)
    # Arrival / portal framing — keep Earth (or former-world) origin; never wipe into a local yard-mender template.
    arrival_framing = any(
        m in story_low
        for m in (
            "just arrived",
            "just woke",
            "woke on a dirt",
            "woke in",
            "woke up in",
            "summoned through",
            "summoned by",
            "summoned into",
            "summoned",
            "portal dumped",
            "through a portal",
            "transported through",
            "transported to",
            "hit by a truck",
            "truck-kun",
            "truck crash",
            "truck accident",
            "opened my eyes",
            "opened their eyes",
            "died at a desk",
            "died on the job",
            "after dying",
            "before dying",
            "last night",
            "this morning",
            "into the body",
            "into a body",
            "this body",
            "another body",
            "another world",
            "other world",
            "failed ritual",
            "ritual into",
            "dirt road",
        )
    ) or (
        # Death + new-world wake is enough even if wording varies
        ("died" in story_low or "death" in story_low or "accident" in story_low or "crash" in story_low)
        and any(m in story_low for m in ("woke", "wake", "opened", "found themselves", "found themself", "now in"))
    )
    # Long this-life residence (reincarnation / grew up here) — not a same-day drop.
    lived_here_long = any(
        m in story_low
        for m in (
            "grew up",
            "years as",
            "for years",
            "raised in",
            "childhood",
            "reborn as a child",
            "as a child",
            "years ago",
            "since childhood",
        )
    ) or (
        ("reincarnat" in mode or "reborn" in mode)
        and any(m in story_low for m in ("village", "born in", "raised", "apprentice", "child"))
    )
    modern_resume = modern_origin and any(
        m in story_low
        for m in (
            "technician",
            "maintenance",
            "near-future",
            "near future",
            "automated",
            "office worker",
            "salaryman",
            "specializing in",
            "corporation",
            "forklift",
            "warehouse",
            "desk job",
            "office",
            "night-shift",
            "night shift",
            "logistics",
        )
    )

    # Keep former-world origin when the story is clearly a drop/summon/body-swap arrival.
    keep_earth_origin = bool(
        fantasy_dest
        and (modern_origin or arrival_framing)
        and arrival_framing
        and not lived_here_long
    )
    # Only fully rewrite life fiction when they already lived HERE for years (reincarnated childhood)
    # and the text is still a pure modern CV with no local childhood — not for same-day isekai.
    localize = bool(
        fantasy_dest
        and modern_origin
        and lived_here_long
        and not arrival_framing
        and modern_resume
    )
    # Transmigrated mode + modern CV + no arrival sentence → stitch arrival; do not erase the CV.
    stitch_arrival = bool(
        fantasy_dest
        and modern_origin
        and not arrival_framing
        and not lived_here_long
        and ("transmigrat" in mode or bool(intent.get("isekai")) or modern_resume)
    )
    # Modern gear on an already-local life: map/drop gear only, never rewrite origin story.
    gear_only_modern = bool(
        fantasy_dest
        and not modern_origin
        and any(
            w in " ".join([_norm(str(starter_equipment or "")), _norm(appearance)])
            for w in (
                "hoodie",
                "sneaker",
                "smartphone",
                "jeans",
                "t-shirt",
                "maintenance vest",
                "laptop",
                "earbuds",
            )
        )
    )

    out_story = story
    out_mode = str(backstory_mode or "")
    out_memory = str(memory_policy or "")
    out_items = list(items)
    out_appearance = appearance
    vocation = ""
    path = "none"

    def _map_items(src: list[str]) -> list[str]:
        mapped: list[str] = []
        seen: set[str] = set()
        for name in src:
            loc = _localize_item_name(name)
            if not loc:
                notes.append(f"Dropped “{name}” (no local equivalent / modern tech).")
                continue
            key = loc.lower()
            if key in seen:
                continue
            seen.add(key)
            mapped.append(loc)
            if loc.lower() != name.lower():
                notes.append(f"Localized “{name}” → “{loc}”.")
        return mapped

    if localize:
        path = "localize_origin_to_world"
        vocation, seed = _pick_local_vocation(story, ", ".join(items), appearance)
        faint = bool(intent.get("isekai") or "isekai" in _norm(world_style) or "transmigrat" in mode or "reincarnat" in mode)
        out_story = _localize_backstory(
            old_story=story,
            vocation=vocation,
            seed=seed,
            world_style=world_style,
            keep_faint_otherworld_memory=faint,
        )
        # This path is for long local residence (e.g. reincarnated childhood), not truck-kun day-one.
        if "reincarnat" in mode or "reborn" in mode or lived_here_long:
            out_mode = "reincarnated"
        elif "transmigrat" in mode:
            out_mode = "transmigrated"
        else:
            out_mode = out_mode or "known"
        if faint and _norm(out_memory) in {"", "known", "full", "ordinary memory", "remembers former life"}:
            out_memory = "former life fragments"
        out_items = _map_items(items)
        out_appearance = _localize_appearance(appearance)
        notes.insert(
            0,
            f"Origin/backstory realigned to long local life ({register}) as {vocation}; faint otherworld memory kept.",
        )
    elif stitch_arrival:
        # Build a proper transmigration package: former life + transport + arrival start.
        # Never bolt a generic line onto a native fantasy plot (noble/festival/etc.).
        path = "stitch_arrival_keep_former_life"
        out_mode = "transmigrated" if "reincarnat" not in mode else "reincarnated"
        if _norm(out_memory) in {"", "known", "ordinary memory"}:
            out_memory = "former life fragments"
        try:
            from app.setup_composer import (
                build_transmigration_backstory,
                ensure_isekai_arrival_beat,
                transmigration_story_score,
            )

            if transmigration_story_score(story).get("ok"):
                out_story = story
            else:
                out_story = ensure_isekai_arrival_beat(
                    story,
                    mode="transmigrated",
                    idea=str(intent.get("raw_idea") or intent.get("genre") or ""),
                    world_style=world_style,
                )
                if not transmigration_story_score(out_story).get("ok"):
                    out_story = build_transmigration_backstory(
                        old_story=story,
                        idea=str(intent.get("raw_idea") or ""),
                        world_style=world_style,
                    )
        except Exception:
            out_story = (
                "In their former life they held an ordinary modern job. "
                "Death or forced transport tore them out of that life; they woke in another world "
                "with only clothes and pocket scraps from before transport. The story starts at arrival."
            )
        # Map modern clothes/tools to local equivalents for fantasy destinations, keep thin kit later.
        out_items = _map_items(items) if fantasy_dest else list(items)
        out_appearance = _localize_appearance(appearance) if fantasy_dest else appearance
        notes.insert(
            0,
            "Transmigrated package enforced: former-world life + transport + arrival start.",
        )
    elif keep_earth_origin:
        path = "keep_earth_origin_thin_kit"
        if "transmigrat" not in _norm(out_mode) and "reincarnat" not in _norm(out_mode):
            out_mode = "transmigrated"
        if _norm(out_memory) in {"", "known", "ordinary memory"}:
            out_memory = "remembers former life"
        notes.append(
            "Former-world origin kept (arrival/summon/body-drop is clear). Starter kit stays thin — "
            "clothes and tiny pockets only, not a full work pack."
        )
    elif gear_only_modern:
        # Local life story already matches world. Leave pure modern gadgets for evaluate_item
        # to strip with a clear reason; only map clothing-style modern words.
        path = "localize_gear_only"
        mapped: list[str] = []
        seen: set[str] = set()
        for name in items:
            low = _norm(name)
            if any(
                w in low
                for w in (
                    "phone",
                    "smartphone",
                    "laptop",
                    "earbuds",
                    "headphones",
                    "usb",
                    "credit card",
                    "id card",
                    "passport",
                    "smartwatch",
                    "tablet",
                )
            ):
                # keep name so evaluate_item strips with lore reason
                key = name.lower()
                if key not in seen:
                    seen.add(key)
                    mapped.append(name)
                continue
            loc = _localize_item_name(name)
            if not loc:
                key = name.lower()
                if key not in seen:
                    seen.add(key)
                    mapped.append(name)
                continue
            key = loc.lower()
            if key in seen:
                continue
            seen.add(key)
            mapped.append(loc)
            if loc.lower() != name.lower():
                notes.append(f"Localized “{name}” → “{loc}”.")
        out_items = mapped
        out_appearance = _localize_appearance(appearance)
        if notes:
            notes.insert(
                0,
                "Gear language aligned to world vibe; origin/backstory already fits this world.",
            )
    elif modern_origin and register in {REGISTER_MODERN, REGISTER_CYBER, REGISTER_SCIFI}:
        path = "origin_matches_world"
    elif not modern_origin and fantasy_dest:
        path = "already_local"

    return {
        "register": register,
        "origin": origin,
        "path": path,
        "localized": path == "localize_origin_to_world",
        "keep_earth_origin": keep_earth_origin,
        "vocation": vocation,
        "character_backstory": out_story,
        "backstory_mode": out_mode,
        "memory_policy": out_memory,
        "starter_items": out_items,
        "appearance": out_appearance,
        "notes": notes,
        "player_messages": [n for n in notes if n.startswith("Origin/") or "Earth/modern origin" in n][:6],
    }


def classify_item(name: str) -> dict[str, Any]:
    low = _norm(name)
    # strip quantity prefixes
    low = re.sub(r"^\d+\s*(x|×)?\s*", "", low)
    low = re.sub(r"^\d+\s*days?\s+", "", low)

    if any(
        w in low
        for w in (
            "legendary",
            "artifact",
            "excalibur",
            "god-slayer",
            "infinity",
            "mythic relic",
            "holy grail",
            "one-shot kill",
            "sss-rank",
            "unique divine",
        )
    ):
        bucket = BUCKET_LEGENDARY
    elif any(
        w in low
        for w in (
            "phone",
            "smartphone",
            "laptop",
            "earbuds",
            "headphones",
            "usb",
            "credit card",
            "id card",
            "passport",
            "gun",
            "pistol",
            "rifle",
            "flashlight",
            "lighter",
            "wallet",
            "keys",
            "keychain",
            "smartwatch",
            "tablet",
        )
    ):
        bucket = BUCKET_MODERN
    elif any(
        w in low
        for w in (
            "shield",
            "sword",
            "spear",
            "axe",
            "mace",
            "halberd",
            "bow",
            "crossbow",
            "armor",
            "mail",
            "plate",
            "helm",
            "helmet",
            "gauntlet",
            "warhammer",
            "dagger",
            "katana",
            "blade",
            "scabbard",
            "quiver",
            "lance",
            "greatsword",
            "buckler",
        )
    ):
        # pocket knife is tool-ish; full dagger leans combat
        if "pocket knife" in low or "penknife" in low or "utility knife" in low:
            bucket = BUCKET_POCKET
        else:
            bucket = BUCKET_COMBAT
    elif any(
        w in low
        for w in (
            "potion",
            "wand",
            "staff",
            "grimoire",
            "spellbook",
            "spell book",
            "mana",
            "enchanted",
            "magical",
            "magic ",
            " of magic",
            "rune stone",
            "runestone",
            "magic crystal",
            "mana crystal",
            "talisman of",
            "amulet of power",
            "orb of",
            "focus crystal",
            "spell scroll",
            "scroll of",
            "holy symbol",
            "relic of",
            "arcane",
            "wizard",
            "mage robe",
        )
    ):
        bucket = BUCKET_MAGIC
    elif any(
        w in low
        for w in (
            "gold bar",
            "sack of gold",
            "treasure",
            "jewel",
            "diamond",
            "ruby",
            "ingot",
        )
    ):
        bucket = BUCKET_VALUABLE
    elif any(
        w in low
        for w in (
            "coat",
            "cloak",
            "robe",
            "jacket",
            "tunic",
            "shirt",
            "dress",
            "clothes",
            "clothing",
            "vest",
            "waistcoat",
            "blazer",
            "hoodie",
            "sweater",
            "jumper",
            "cardigan",
            "coverall",
            "overall",
            "jumpsuit",
            "smock",
            "poncho",
            "boot",
            "shoe",
            "sandal",
            "glove",
            "hat",
            "hood",
            "scarf",
            "trousers",
            "pants",
            "skirt",
            "apron",
            "belt",
            "socks",
            "underwear",
            "uniform",
        )
    ):
        bucket = BUCKET_WORN
    elif any(
        w in low
        for w in (
            "ration",
            "bread",
            "food",
            "water",
            "flask",
            "bottle",
            "canteen",
            "skin",
            "wine",
            "tea",
            "jerky",
            "biscuit",
        )
    ):
        bucket = BUCKET_CONSUMABLE
    elif any(
        w in low
        for w in (
            "hammer",
            "wrench",
            "screwdriver",
            "needle",
            "thread",
            "awl",
            "chisel",
            "saw",
            "fishing",
            "net",
            "pickaxe",
            "shovel",
            "trowel",
            "toolbox",
            "tool belt",
            "tool kit",
            "pouch of tools",
            "maintenance kit",
            "repair pouch",
            "repair kit",
        )
    ) or (
        # "tool pouch" / "small tools" — pocket-scale; full "toolbox" already covered
        ("tool" in low or "tools" in low or "repair" in low)
        and not any(w in low for w in ("vest", "shirt", "jacket", "coat", "uniform"))
    ):
        bucket = BUCKET_TOOL
    elif any(
        w in low
        for w in (
            "rope",
            "coil",
            "notebook",
            "journal",
            "chalk",
            "pencil",
            "pen",
            "coin",
            "copper",
            "silver",
            "purse",
            "pouch",
            "bag",
            "satchel",
            "pack",
            "charm",
            "token",
            "map",
            "compass",
            "candle",
            "torch",
            "bandag",
            "cloth",
            "handkerchief",
            "comb",
            "mirror",
            "ring",
            "earring",
            "pendant",
            "simple",
            "wooden",
            "string",
            "multitool",
            "multi-tool",
        )
    ):
        bucket = BUCKET_POCKET
    else:
        # unknown → treat as pocket-scale unless heavy-sounding
        if any(w in low for w in ("crate", "barrel", "anvil", "chest", "cart")):
            bucket = BUCKET_VALUABLE
        else:
            bucket = BUCKET_POCKET

    return {"name": name, "bucket": bucket, "key": low}


# --- clothing / ordinary-power / latent -------------------------------------

_POWER_NAME_MARKERS = (
    "enchanted",
    "enchant",
    "magical",
    "magic ",
    "arcane",
    "legendary",
    "mythic",
    "divine",
    "holy of",
    "cursed",
    "of power",
    "of might",
    "of dominion",
    "of the gods",
    "sss-rank",
    "ss-rank",
    "s-rank",
    "artifact",
    "relic ",
    "god-slayer",
    "infinity",
    "+1 ",
    "+2 ",
    "+3 ",
    "rare ",
    "epic ",
    "unique ",
    "blessed ",
    "runed ",
    "rune-etched",
    "mana-infused",
    "soulbound",
    "bound spirit",
)

_CLOTHING_ROLE_MARKERS: dict[str, tuple[str, ...]] = {
    "martial": (
        "plate",
        "mail",
        "chainmail",
        "armor",
        "breastplate",
        "gauntlet",
        "helm",
        "helmet",
        "greave",
        "war cloak",
        "battle",
        "militia",
        "guard tabard",
        "knight",
    ),
    "mage": (
        "mage robe",
        "wizard robe",
        "wizard hat",
        "sorcer",
        "arcane robe",
        "spellweave",
        "cultivator robe",
        "sect robe",
    ),
    "noble": (
        "silk",
        "velvet",
        "embroidered",
        "gilded",
        "jeweled",
        "court dress",
        "noble",
        "lordly",
        "ermine",
        "brocade",
    ),
    "religious": (
        "vestment",
        "cassock",
        "priest",
        "monk robe",
        "nun",
        "cleric",
        "temple",
    ),
    "work": (
        "work",
        "apron",
        "coverall",
        "overall",
        "smock",
        "glove",
        "maintenance",
        "repair",
        "canvas",
        "patched",
        "frayed",
        "leather apron",
        "smith",
    ),
    "travel": (
        "travel",
        "cloak",
        "coat",
        "hooded",
        "road",
        "dusty",
        "weathered",
    ),
}

_STORY_ROLE_MARKERS: dict[str, tuple[str, ...]] = {
    "martial": (
        "soldier",
        "guard",
        "knight",
        "hunter",
        "mercenary",
        "militia",
        "warrior",
        "duelist",
        "ranger",
        "squire",
        "watchman",
        "caravan guard",
        "trained to fight",
        "spearman",
    ),
    "mage": (
        "mage",
        "wizard",
        "witch",
        "sorcer",
        "cultivat",
        "spell",
        "arcane student",
        "apprentice mage",
        "sect outer",
    ),
    "noble": (
        "noble",
        "lord",
        "lady",
        "heir of",
        "manor",
        "court",
        "aristocrat",
        "baron",
    ),
    "religious": (
        "priest",
        "monk",
        "nun",
        "cleric",
        "temple",
        "acolyte",
        "shrine",
    ),
    "work": (
        "mender",
        "smith",
        "carpenter",
        "fisher",
        "farmer",
        "healer",
        "doctor",
        "technician",
        "mechanic",
        "tailor",
        "cook",
        "apprentice",
        "courier",
        "sailor",
        "miner",
        "clerk",
        "laborer",
        "baker",
        "yard",
        "work",
        "repair",
        "craft",
        "field hand",
    ),
    "travel": (
        "courier",
        "traveler",
        "traveller",
        "wanderer",
        "road",
        "caravan",
        "route",
    ),
}

_LATENT_CANDIDATE_MARKERS = (
    "charm",
    "token",
    "pendant",
    "ring",
    "heirloom",
    "family",
    "wooden",
    "keepsake",
    "locket",
    "bead",
    "ribbon",
    "scarred",
    "patched",
    "frayed",
    "worn",
    "old ",
    "grandmother",
    "grandfather",
    "mother's",
    "father's",
)


def item_has_power_claim(name: str) -> bool:
    low = _norm(name)
    return any(m in low for m in _POWER_NAME_MARKERS)


def demote_powerful_item_name(name: str) -> str:
    """Strip power adjectives so the item stays ordinary at Start."""
    text = str(name or "").strip()
    if not text:
        return text
    out = text
    for pat in (
        r"\benchanted\b",
        r"\bmagical\b",
        r"\bmagic\b",
        r"\barcane\b",
        r"\blegendary\b",
        r"\bmythic\b",
        r"\bdivine\b",
        r"\bcursed\b",
        r"\bblessed\b",
        r"\bruned\b",
        r"\brune-etched\b",
        r"\bmana-infused\b",
        r"\bsoulbound\b",
        r"\bartifact\b",
        r"\bunique\b",
        r"\bepic\b",
        r"\brare\b",
        r"\bsss-rank\b",
        r"\bss-rank\b",
        r"\bs-rank\b",
        r"\+\d+\b",
        r"\bof power\b",
        r"\bof might\b",
        r"\bof dominion\b",
        r"\bof the gods\b",
    ):
        out = re.sub(pat, "", out, flags=re.I)
    out = re.sub(r"\s+", " ", out).strip(" ,.-")
    return out or "plain clothes"


def clothing_roles(name: str) -> set[str]:
    low = _norm(name)
    roles: set[str] = set()
    for role, markers in _CLOTHING_ROLE_MARKERS.items():
        if any(m in low for m in markers):
            roles.add(role)
    if not roles:
        roles.add("ordinary")
    return roles


def story_roles(story: str) -> set[str]:
    low = _norm(story)
    roles: set[str] = set()
    for role, markers in _STORY_ROLE_MARKERS.items():
        if any(m in low for m in markers):
            roles.add(role)
    if not roles:
        roles.add("ordinary")
    return roles


def is_ordinary_this_life_start(arrival: dict[str, Any], story: str) -> bool:
    """Born/local/this-life starts are ordinary unless the story is clearly elite."""
    if not arrival.get("allows_this_life_gear"):
        return False
    if arrival.get("arrival") == ARRIVAL_ISEKAI_ARRIVAL:
        return False
    roles = story_roles(story)
    elite = bool(roles & {"martial", "mage", "noble"})
    # Martial/mage/noble life is still "not free god-loot", but can hold role-appropriate gear.
    # Ordinary = no exceptional station claimed.
    return not elite


def clothing_matches_backstory(name: str, story: str) -> tuple[bool, str]:
    """
    Return (ok, reason). Ordinary clothes always OK.
    Role clothing needs matching story vocation/station.
    """
    c_roles = clothing_roles(name) - {"ordinary", "travel", "work"}
    # work/travel clothes are fine for almost any local life
    soft = clothing_roles(name)
    if soft <= {"ordinary", "travel", "work"} or not c_roles:
        # still block pure martial armor words even if classified worn
        if any(w in _norm(name) for w in ("plate", "mail", "breastplate", "gauntlet", "helm")):
            if "martial" not in story_roles(story):
                return False, "martial armor needs a martial life in the backstory"
        return True, ""
    s_roles = story_roles(story)
    for role in c_roles:
        if role in s_roles:
            return True, ""
    needed = ", ".join(sorted(c_roles))
    return False, f"clothing role ({needed}) does not match backstory"


def may_have_latent_potential(name: str, *, ordinary_start: bool) -> bool:
    """Mundane personal pieces may later hide a power — DM-only, not at Start."""
    low = _norm(name)
    if not low or item_has_power_claim(name):
        return False
    bucket = classify_item(name)["bucket"]
    if bucket in {BUCKET_LEGENDARY, BUCKET_MAGIC, BUCKET_VALUABLE, BUCKET_COMBAT}:
        return False
    # Personal trinkets / heirlooms are always fair latent candidates (still mundane now).
    if any(m in low for m in _LATENT_CANDIDATE_MARKERS):
        return True
    # Ordinary born-in-world kit: worn clothes and tiny pockets can later matter.
    if ordinary_start and bucket in {BUCKET_WORN, BUCKET_POCKET}:
        return True
    return False


def _combat_ok_for_arrival(arrival: dict[str, Any], story: str) -> bool:
    if not arrival.get("allows_this_life_gear"):
        return False
    # Only if life sounds martial / guard / hunter / soldier
    martial = (
        "soldier",
        "guard",
        "knight",
        "hunter",
        "mercenary",
        "militia",
        "warrior",
        "duelist",
        "ranger",
        "squire",
        "watchman",
        "caravan guard",
        "sword",
        "trained to fight",
        "spear",
    )
    return any(m in story for m in martial)


def _tool_ok_for_arrival(arrival: dict[str, Any], story: str, item_key: str) -> bool:
    if arrival.get("minimal_only"):
        return False
    if arrival["arrival"] == ARRIVAL_ISEKAI_ARRIVAL:
        return False
    trade = (
        "clerk",
        "smith",
        "carpenter",
        "fisher",
        "farmer",
        "healer",
        "doctor",
        "technician",
        "mechanic",
        "mender",
        "repair",
        "yard",
        "tailor",
        "cook",
        "apprentice",
        "courier",
        "sailor",
        "miner",
        "laborer",
        "work",
        "trade",
        "craft",
    )
    return any(m in story for m in trade) or arrival["arrival"] == ARRIVAL_NATIVE


def _magic_allowed(arrival: dict[str, Any], *, magic_level: str = "", story: str = "") -> bool:
    """Whether magical starter gear can exist in this world/life at all."""
    ml = _norm(magic_level)
    if any(x in ml for x in ("none", "no magic", "off", "absent", "zero", "disabled")):
        return False
    if arrival.get("cyberpunk_world") and not arrival.get("urban_fantasy"):
        return False
    if arrival.get("modern_world") and not arrival.get("fantasy_world") and not arrival.get("urban_fantasy"):
        # Pure sci-fi / cyber / present-day without magic flavor
        if not any(m in story for m in ("mage", "wizard", "witcher", "occult", "witch")):
            return False
    return True


def evaluate_item(
    item_name: str,
    arrival: dict[str, Any],
    *,
    character_backstory: str = "",
    magic_level: str = "",
    special_ability_origin: str = "",
) -> dict[str, Any]:
    """
    Returns decision: keep | strip | defer
    defer = not in starting inventory; may appear after Start via narration/loot.
    strip = illogical / lore-breaking; do not reintroduce without new story.
    """
    meta = classify_item(item_name)
    bucket = meta["bucket"]
    story = _norm(character_backstory)
    kind = arrival["arrival"]
    magic_ok = _magic_allowed(arrival, magic_level=magic_level, story=story)
    powers_off = _norm(special_ability_origin) in {"none", "off", "no", ""}

    ordinary = is_ordinary_this_life_start(arrival, story)
    original_name = item_name
    power_demoted = False

    if bucket == BUCKET_LEGENDARY:
        return {
            **meta,
            "decision": "strip",
            "reasons": [
                f"“{item_name}” is legendary/god-tier gear — it cannot already be in your pockets at Start."
            ],
            "player_reason": f"Removed “{item_name}”: legendary or god-tier items are not starting gear.",
            "provenance": "invalid",
            "latent_possible": False,
        }

    # Power-claimed names are never free at Start. Demote wording, then continue normal rules
    # on the mundane form (so amnesia / clothing match still apply).
    if item_has_power_claim(item_name) and bucket != BUCKET_LEGENDARY:
        demoted = demote_powerful_item_name(item_name)
        if not demoted or demoted.lower() == _norm(item_name):
            return {
                **meta,
                "decision": "strip",
                "reasons": [f"“{item_name}” claims special power at Start."],
                "player_reason": (
                    f"Removed “{item_name}”: starting gear is ordinary — no free enchanted/powerful items. "
                    "Any hidden property on a long-held starter piece is a later DM event, not pre-powered."
                ),
                "provenance": "ordinary_start",
                "latent_possible": False,
            }
        power_demoted = True
        item_name = demoted
        meta = classify_item(item_name)
        bucket = meta["bucket"]

    # Lore mismatch: magic item in non-magic / cyberpunk / powers-off worlds
    if bucket == BUCKET_MAGIC and not magic_ok:
        return {
            **meta,
            "decision": "strip",
            "reasons": [
                f"“{item_name}” is magical, but this setting does not support starter magic "
                f"(world/tech={arrival.get('cyberpunk_world') and 'cyberpunk/modern' or 'low-magic'}; "
                f"magic_level={magic_level or 'unspecified'})."
            ],
            "player_reason": (
                f"Removed “{item_name}”: magical gear does not fit this world’s lore "
                f"(magic is off or the setting is non-magical, e.g. pure cyberpunk/sci-fi)."
            ),
            "provenance": "lore_mismatch",
        }

    # Fantasy arms in pure cyberpunk / hard sci-fi (not urban fantasy)
    # Street weapons (knife, baton, katana as chrome fashion) may still pass via later martial rules;
    # medieval kit (plate, spear, longsword, bow) is lore-mismatched.
    if bucket == BUCKET_COMBAT and arrival.get("cyberpunk_world") and not arrival.get("urban_fantasy"):
        low = meta["key"]
        fantasy_arm = any(
            w in low
            for w in (
                "spear",
                "axe",
                "mace",
                "bow",
                "crossbow",
                "plate",
                "mail",
                "chainmail",
                "halberd",
                "lance",
                "greatsword",
                "longsword",
                "warhammer",
                "buckler",
                "tower shield",
                "kite shield",
                "wooden shield",
                "iron sword",
                "steel sword",
                "broadsword",
                "claymore",
                "helm",
                "helmet",
                "gauntlet",
            )
        )
        if fantasy_arm:
            return {
                **meta,
                "decision": "strip",
                "reasons": [
                    f"“{item_name}” is medieval fantasy combat gear in a cyberpunk/modern setting."
                ],
                "player_reason": (
                    f"Removed “{item_name}”: fantasy weapons/armor do not match a cyberpunk or pure modern world."
                ),
                "provenance": "lore_mismatch",
            }

    # Explicit "enchanted/magical X" clothing when magic disallowed
    if not magic_ok and any(w in meta["key"] for w in ("enchanted", "magical", "mana-", "arcane", "rune-")):
        return {
            **meta,
            "decision": "strip",
            "reasons": [f"“{item_name}” is labeled magical in a non-magic setting."],
            "player_reason": f"Removed “{item_name}”: enchanted/magical gear does not fit this world’s rules.",
            "provenance": "lore_mismatch",
        }

    # Powers off + magic focus items (even if world is fantasy-ish)
    if powers_off and bucket == BUCKET_MAGIC and kind != ARRIVAL_ISEKAI_ARRIVAL:
        # still allow if magic_ok and mage vocation — but powers off means no free magic kit
        if not any(m in story for m in ("mage", "wizard", "witcher", "cultivat")):
            return {
                **meta,
                "decision": "strip",
                "reasons": [
                    f"Special abilities/powers are off and no magical vocation is in the backstory — "
                    f"“{item_name}” is not justified."
                ],
                "player_reason": (
                    f"Removed “{item_name}”: powers/magic are disabled in setup and your backstory "
                    "does not establish a mage vocation."
                ),
                "provenance": "lore_mismatch",
            }

    def _row(
        decision: str,
        reasons: list[str],
        provenance: str,
        *,
        player: str | None = None,
        name: str | None = None,
        latent: bool | None = None,
    ) -> dict[str, Any]:
        why = player or (reasons[0] if reasons else f"Adjusted “{item_name}” for lore consistency.")
        out_name = name or item_name
        row_meta = classify_item(out_name) if name else meta
        lat = latent
        if lat is None and decision == "keep":
            lat = may_have_latent_potential(out_name, ordinary_start=ordinary)
        if power_demoted and decision == "keep":
            reasons = list(reasons) + [
                f"Demoted power claim “{original_name}” → “{out_name}” (ordinary at Start)."
            ]
            if not player:
                why = (
                    f"Renamed “{original_name}” to “{out_name}”: you start ordinary. "
                    "No free enchanted gear; a long-held starter piece might later hide a power "
                    "only if the DM chooses a special event."
                )
            provenance = "ordinary_demoted"
            lat = may_have_latent_potential(out_name, ordinary_start=True)
        return {
            **row_meta,
            "name": out_name,
            "decision": decision,
            "reasons": reasons,
            "player_reason": why,
            "provenance": provenance,
            "latent_possible": bool(lat) if decision == "keep" else False,
            **({"original_name": original_name} if power_demoted else {}),
        }

    if kind == ARRIVAL_AMNESIA:
        if bucket == BUCKET_WORN:
            return _row("keep", ["Minimal worn clothes OK for blank/amnesia start."], "on_body_unknown")
        if bucket == BUCKET_CONSUMABLE and any(w in meta["key"] for w in ("water", "bread", "ration")):
            return _row("keep", ["One survival scrap OK if already in hand."], "found_on_person")
        return _row(
            "strip",
            ["Amnesia/blank start: no unexplained kit."],
            "invalid",
            player=f"Removed “{item_name}”: amnesia/blank starts only keep worn clothes (and maybe a scrap of food/water).",
        )

    if kind == ARRIVAL_ISEKAI_ARRIVAL:
        # Magic from a non-magic origin world → strip (not even "find later as already owned")
        origin_magic = any(
            m in story
            for m in (
                "from a magic world",
                "from a magical world",
                "was a mage",
                "was a wizard",
                "was a witch",
                "came from a magical",
                "previous world had magic",
                "old world had magic",
                "old world magic",
                "magical previous world",
                "previous life as a mage",
                "previous life as a wizard",
                "trained as a mage before",
                "wizard in their previous",
                "mage in their previous",
                "came from a magic",
            )
        )
        if bucket == BUCKET_MAGIC:
            if not origin_magic:
                return _row(
                    "strip",
                    [
                        "Isekai arrival from a non-magic life: magical items cannot have been "
                        "carried from the old world unless the story says that world had magic."
                    ],
                    "lore_mismatch",
                    player=(
                        f"Removed “{item_name}”: you were transported from a non-magical life — "
                        "a magic item would not have been on you at arrival. "
                        "(If your old world was magical, say so in the backstory.)"
                    ),
                )
            # Origin world was magical: keep pocket-scale foci only (not armories)
            pocket_magic = any(
                w in meta["key"]
                for w in (
                    "wand",
                    "charm",
                    "talisman",
                    "focus",
                    "small",
                    "simple",
                    "notebook",
                    "pendant",
                    "ring",
                    "crystal",
                )
            ) or len(meta["key"]) < 28
            if pocket_magic and not any(
                w in meta["key"] for w in ("staff of", "orb of dominion", "grimoire of power", "legendary")
            ):
                return _row(
                    "keep",
                    ["Old-world magic established — pocket-scale focus could have been on them."],
                    "old_world_magic_pocket",
                    player=(
                        f"Kept “{item_name}”: your backstory says the old world had magic, "
                        "so a small focus could have been on you at transport."
                    ),
                )
            return _row(
                "defer",
                ["Even with old-world magic, oversized magic gear waits until after Start."],
                "post_start_only",
                player=(
                    f"Held back “{item_name}”: even from a magical old world, only pocket-scale "
                    "foci ride along at arrival — larger magic gear is earned in play."
                ),
            )
        if bucket == BUCKET_WORN:
            return _row("keep", ["Worn at moment of transport."], "worn_at_arrival")
        if bucket == BUCKET_MODERN:
            # One pocket gadget max is handled in fact_check; here allow phone/wallet-scale only.
            if any(
                w in meta["key"]
                for w in ("phone", "smartphone", "wallet", "keys", "earbuds", "lighter", "id card")
            ):
                return _row(
                    "keep",
                    ["On-person modern pocket item at arrival."],
                    "old_world_pocket",
                )
            return _row(
                "defer",
                ["Bulky modern kit is not assumed on pure isekai arrival."],
                "post_start_only",
                player=(
                    f"Held back “{item_name}”: pure isekai arrival keeps clothes and tiny pockets, "
                    "not a full modern pack."
                ),
            )
        # Trade tools wait until after Start on pure isekai — not free work kits.
        if bucket == BUCKET_TOOL:
            return _row(
                "defer",
                [
                    "Isekai/summon arrival: trade/work kits cannot pre-exist Start — "
                    "earn after arrival (loot, gift, buy, craft)."
                ],
                "post_start_only",
                player=(
                    f"Held back “{item_name}”: at pure isekai arrival you keep clothes/pockets, "
                    "not a trade kit. Tools can appear later through play."
                ),
            )
        if bucket == BUCKET_POCKET and not any(
            w in meta["key"] for w in ("map of", "kingdom", "dungeon", "mana", "rune")
        ):
            if any(
                w in meta["key"]
                for w in (
                    "notebook",
                    "pen",
                    "pencil",
                    "wallet",
                    "coin",
                    "keys",
                    "charm",
                    "photo",
                    "ring",
                    "handkerchief",
                    "token",
                )
            ):
                return _row("keep", ["Plausible pocket item at transport."], "old_world_pocket")
            # rope / bag / pouch without "tool" — still pocket-scale only if tiny
            if any(w in meta["key"] for w in ("small pouch", "coin purse", "handkerchief")):
                return _row("keep", ["Tiny pocket pouch at transport."], "old_world_pocket")
        if bucket == BUCKET_CONSUMABLE:
            # Food/water is found after arrival unless the story already has them mid-commute with a bag.
            if any(w in meta["key"] for w in ("flask", "bottle", "canteen", "water", "thermos", "skin")) and (
                "backpack" in story or "commute" in story or "traveling with" in story
            ):
                return _row(
                    "keep",
                    ["Travel/commute drink if they were already out when taken."],
                    "old_world_bag",
                )
            return _row(
                "defer",
                ["New-world food/water is found after arrival, not pre-packed at pure isekai arrival."],
                "post_start_only",
                player=(
                    f"Held back “{item_name}”: pure isekai arrival does not pre-pack food/water. "
                    "Find or buy supplies after Start (unless your backstory already has you mid-travel)."
                ),
            )
        if bucket in {BUCKET_COMBAT, BUCKET_VALUABLE}:
            return _row(
                "defer",
                [
                    "Isekai/summon arrival: fantasy combat gear or valuables "
                    "cannot pre-exist Start — earn after arrival (loot, gift, buy, craft)."
                ],
                "post_start_only",
                player=(
                    f"Held back “{item_name}”: at the moment of transport you only keep clothes/pockets. "
                    "Combat gear and valuables can appear later through play (loot, buy, gift, craft)."
                ),
            )
        return _row(
            "defer",
            ["Not clearly on-person at the moment of transport."],
            "post_start_only",
            player=f"Held back “{item_name}”: it was not clearly on you when you arrived.",
        )

    # Native / reincarnated / body transmigration — this-life gear
    if bucket == BUCKET_MODERN and arrival.get("fantasy_world") and not arrival.get("modern_world"):
        return _row(
            "strip",
            ["Modern tech does not fit this world's tech without an old-world arrival."],
            "invalid",
            player=(
                f"Removed “{item_name}”: modern tech does not belong in this fantasy setting "
                "unless you just arrived from a modern world."
            ),
        )

    if bucket == BUCKET_WORN:
        ok, why = clothing_matches_backstory(item_name, story)
        if not ok:
            # Soft-rewrite to ordinary work/travel clothes instead of naked strip
            fallback = "patched work clothes" if "work" in story_roles(story) else "plain travel clothes"
            return _row(
                "keep",
                [f"Clothing mismatched backstory ({why}); demoted to ordinary wear."],
                "clothing_backstory_mismatch",
                name=fallback,
                player=(
                    f"Replaced “{item_name}” with “{fallback}”: clothes must match your backstory "
                    f"({why}). Born/local lives start ordinary — no free hero wardrobe."
                ),
                latent=True,
            )
        return _row(
            "keep",
            ["Worn clothes/gear of this life (mundane at Start)."],
            "this_life_worn",
            latent=may_have_latent_potential(item_name, ordinary_start=ordinary or True),
        )

    if bucket == BUCKET_COMBAT:
        if ordinary:
            return _row(
                "defer",
                ["Ordinary this-life start: no free combat kit at Start."],
                "ordinary_start",
                player=(
                    f"Held back “{item_name}”: born/local ordinary starts have no free weapons or armor. "
                    "Earn combat gear after Start."
                ),
            )
        if _combat_ok_for_arrival(arrival, story):
            return _row(
                "keep",
                ["Backstory supports martial/tool-of-trade arms (still mundane at Start)."],
                "this_life_role",
                latent=False,
            )
        return _row(
            "defer",
            [
                "Combat kit (shield/sword/armor) needs a life that earned it — "
                "or it appears after Start via loot/gift/purchase."
            ],
            "post_start_only",
            player=(
                f"Held back “{item_name}”: your backstory does not establish a martial role. "
                "Weapons/armor can be earned after Start."
            ),
        )

    if bucket == BUCKET_MAGIC:
        if not magic_ok:
            return _row(
                "strip",
                ["Magic gear blocked by world magic rules."],
                "lore_mismatch",
                player=f"Removed “{item_name}”: magic does not fit this world's rules.",
            )
        if ordinary:
            # Ordinary native: no free magic kit — personal charm may stay as mundane pocket later
            return _row(
                "defer",
                ["Ordinary this-life start: no free magic gear at Start."],
                "ordinary_start",
                player=(
                    f"Held back “{item_name}”: ordinary local starts do not begin with magic gear. "
                    "If a long-held mundane starter trinket later hides a power, that is a DM event — not free at Start."
                ),
            )
        if "mage" in story or "wizard" in story or "cultivat" in story or "apprentice" in story:
            return _row(
                "keep",
                ["Magic-student life can hold a minor focus — still ordinary/common at Start, not pre-powered."],
                "this_life_role",
                latent=True,
            )
        return _row(
            "defer",
            ["Magic gear is not free at Start without a magical vocation in the backstory."],
            "post_start_only",
            player=(
                f"Held back “{item_name}”: no mage/wizard vocation in your backstory. "
                "Magical tools can be found or earned after Start."
            ),
        )

    if bucket == BUCKET_TOOL:
        if _tool_ok_for_arrival(arrival, story, meta["key"]):
            return _row("keep", ["Trade tools match a working life."], "this_life_role")
        if kind == ARRIVAL_NATIVE and any(w in meta["key"] for w in ("knife", "needle", "rope", "pouch")):
            return _row("keep", ["Small common tool for a local life."], "this_life_common")
        return _row(
            "defer",
            ["Specialized tools need a job/craft mentioned in backstory."],
            "post_start_only",
            player=f"Held back “{item_name}”: specialized tools need a matching job/craft in your backstory.",
        )

    if bucket == BUCKET_VALUABLE:
        return _row(
            "strip",
            ["Large valuables at Start break scarce-economy openings."],
            "invalid",
            player=f"Removed “{item_name}”: large valuables are not free starting wealth.",
        )

    return _row(
        "keep",
        ["Mundane this-life pocket/consumable item (ordinary at Start)."],
        "this_life_common",
    )


def _cap_isekai_pockets(kept: list[dict[str, Any]], deferred: list[dict[str, Any]]) -> None:
    """Pure isekai: keep all worn, at most 2 pocket/modern trinkets."""
    worn = [r for r in kept if r.get("bucket") == BUCKET_WORN]
    pocketish = [
        r
        for r in kept
        if r.get("bucket") in {BUCKET_POCKET, BUCKET_MODERN, BUCKET_CONSUMABLE}
    ]
    other = [
        r
        for r in kept
        if r not in worn and r not in pocketish
    ]
    keep_pocket = pocketish[:2]
    spill = pocketish[2:]
    for row in spill:
        row = {
            **row,
            "decision": "defer",
            "reasons": list(row.get("reasons") or [])
            + ["Pure isekai pocket cap: only two tiny pocket items ride along."],
            "player_reason": (
                f"Held back “{row.get('name')}”: pure isekai arrival keeps clothes plus at most "
                "two tiny pocket items."
            ),
            "provenance": "post_start_only",
        }
        deferred.append(row)
    kept[:] = worn + keep_pocket + other


def _cap_this_life_kit(
    kept: list[dict[str, Any]],
    deferred: list[dict[str, Any]],
    *,
    vocation: str = "",
) -> None:
    """Localized/this-life: worn OK; at most one tool, one drink, two pocket trinkets."""
    worn = [r for r in kept if r.get("bucket") == BUCKET_WORN]
    tools = [r for r in kept if r.get("bucket") == BUCKET_TOOL]
    drinks = [
        r
        for r in kept
        if r.get("bucket") == BUCKET_CONSUMABLE
        and any(w in _norm(str(r.get("name") or "")) for w in ("water", "flask", "skin", "bottle", "canteen"))
    ]
    other_cons = [r for r in kept if r.get("bucket") == BUCKET_CONSUMABLE and r not in drinks]
    pockets = [r for r in kept if r.get("bucket") in {BUCKET_POCKET, BUCKET_MODERN}]
    rest = [
        r
        for r in kept
        if r not in worn
        and r not in tools
        and r not in drinks
        and r not in other_cons
        and r not in pockets
    ]

    def _spill(rows: list[dict[str, Any]], why: str) -> list[dict[str, Any]]:
        if not rows:
            return []
        head, tail = rows[:1], rows[1:]
        for row in tail:
            deferred.append(
                {
                    **row,
                    "decision": "defer",
                    "reasons": list(row.get("reasons") or []) + [why],
                    "player_reason": (
                        f"Held back “{row.get('name')}”: ordinary working life keeps a thin kit "
                        f"({why})."
                    ),
                    "provenance": "post_start_only",
                }
            )
        return head

    tools_kept = _spill(tools, "one trade tool max at Start")
    drinks_kept = _spill(drinks, "one drink vessel max at Start")
    # other food: keep one scrap max
    food_kept = _spill(other_cons, "one food scrap max at Start")
    pocket_kept = pockets[:2]
    for row in pockets[2:]:
        deferred.append(
            {
                **row,
                "decision": "defer",
                "reasons": list(row.get("reasons") or []) + ["pocket trinket cap"],
                "player_reason": (
                    f"Held back “{row.get('name')}”: only a couple of pocket trinkets for an ordinary start."
                ),
                "provenance": "post_start_only",
            }
        )
    kept[:] = worn + tools_kept + drinks_kept + food_kept + pocket_kept + rest


def fact_check_starter_loadout(
    *,
    starter_equipment: str | list[str] | None = None,
    appearance: str = "",
    backstory_mode: str = "",
    memory_policy: str = "",
    character_backstory: str = "",
    intent: dict[str, Any] | None = None,
    world_style: str = "",
    tech_level: str = "",
    magic_level: str = "",
    special_ability_origin: str = "",
    apply_fixes: bool = True,
) -> dict[str, Any]:
    """
    Fact-check starter_equipment (+ optional clothing phrases from appearance).

    1) Harmonize origin/backstory/gear language to world vibe when they clash.
    2) Classify arrival from the *harmonized* identity.
    3) Keep / defer / strip items; cap pure-isekai and ordinary this-life kits.
    """
    intent = intent if isinstance(intent, dict) else {}
    raw_items = _split_items(starter_equipment)
    pre_arrival = classify_arrival(
        backstory_mode=backstory_mode,
        memory_policy=memory_policy,
        character_backstory=character_backstory,
        intent=intent,
        world_style=world_style,
        tech_level=tech_level,
    )
    harm = harmonize_identity_to_world_vibe(
        character_backstory=character_backstory,
        backstory_mode=backstory_mode,
        memory_policy=memory_policy,
        starter_equipment=starter_equipment,
        appearance=appearance,
        world_style=world_style,
        tech_level=tech_level,
        magic_level=magic_level,
        intent=intent,
        arrival=pre_arrival,
    )

    story = str(harm.get("character_backstory") or character_backstory or "")
    mode = str(harm.get("backstory_mode") or backstory_mode or "")
    memory = str(harm.get("memory_policy") or memory_policy or "")
    items = list(harm.get("starter_items") or raw_items)
    new_appearance = str(harm.get("appearance") or appearance or "")

    arrival = classify_arrival(
        backstory_mode=mode,
        memory_policy=memory,
        character_backstory=story,
        intent=intent,
        world_style=world_style,
        tech_level=tech_level,
    )
    # Localized life is this-world gear even if intent still has isekai flavor.
    if harm.get("localized"):
        arrival = {
            **arrival,
            "arrival": ARRIVAL_TRANSMIGRATED_BODY
            if "transmigrat" in _norm(mode)
            else (
                ARRIVAL_REINCARNATED
                if "reincarnat" in _norm(mode) or "reborn" in _norm(mode)
                else ARRIVAL_NATIVE
            ),
            "allows_this_life_gear": True,
            "allows_old_world_pockets": False,
            "minimal_only": False,
            "notes": (
                "Origin/backstory localized to world vibe — gear must fit this life’s vocation, "
                "not a free modern pack or god-loot."
            ),
        }

    appearance_items = _split_items(new_appearance)

    kept: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    stripped: list[dict[str, Any]] = []

    for name in items:
        row = evaluate_item(
            name,
            arrival,
            character_backstory=story,
            magic_level=magic_level,
            special_ability_origin=special_ability_origin,
        )
        if row["decision"] == "keep":
            kept.append(row)
        elif row["decision"] == "defer":
            deferred.append(row)
        else:
            stripped.append(row)

    # Appearance must match backstory / arrival (clothing check).
    appearance_flags: list[str] = []
    if new_appearance:
        if arrival["arrival"] == ARRIVAL_ISEKAI_ARRIVAL:
            combatish = []
            for name in appearance_items:
                meta = classify_item(name)
                if meta["bucket"] in {BUCKET_COMBAT, BUCKET_MAGIC, BUCKET_LEGENDARY}:
                    combatish.append(name)
                if item_has_power_claim(name):
                    combatish.append(name)
            if combatish:
                appearance_flags.append(
                    "Appearance had combat/magic/powerful wardrobe on isekai arrival — simplified to street/travel clothes."
                )
                if apply_fixes:
                    new_appearance = (
                        "torso: plain travel clothes; feet: practical shoes; bag: small shoulder bag"
                    )
        elif arrival.get("allows_this_life_gear"):
            # Born/local: each worn piece must match backstory; demote power claims.
            rebuilt: list[str] = []
            changed_app = False
            for chunk in re.split(r"[;|]+", new_appearance):
                chunk = chunk.strip()
                if not chunk:
                    continue
                if ":" in chunk:
                    zone, item = chunk.split(":", 1)
                    zone, item = zone.strip(), item.strip()
                else:
                    zone, item = "", chunk
                piece = item
                if item_has_power_claim(piece):
                    piece = demote_powerful_item_name(piece)
                    changed_app = True
                    appearance_flags.append(
                        f"Appearance “{item}” demoted to ordinary “{piece}” (no free power clothes at Start)."
                    )
                ok, why = clothing_matches_backstory(piece, story)
                if not ok:
                    piece = (
                        "patched work clothes"
                        if "work" in story_roles(story)
                        else "plain travel clothes"
                    )
                    changed_app = True
                    appearance_flags.append(
                        f"Appearance clothes mismatched backstory ({why}); set to “{piece}”."
                    )
                rebuilt.append(f"{zone}: {piece}" if zone else piece)
            if apply_fixes and changed_app:
                new_appearance = "; ".join(rebuilt)

    if arrival["arrival"] == ARRIVAL_ISEKAI_ARRIVAL:
        _cap_isekai_pockets(kept, deferred)
    elif harm.get("localized") or arrival.get("allows_this_life_gear"):
        _cap_this_life_kit(kept, deferred, vocation=str(harm.get("vocation") or ""))

    # If isekai arrival and almost nothing left, ensure minimal clothes line
    if arrival["arrival"] == ARRIVAL_ISEKAI_ARRIVAL and not kept:
        kept.append(
            {
                "name": "clothes worn at arrival",
                "bucket": BUCKET_WORN,
                "decision": "keep",
                "reasons": ["Default: whatever they wore when taken."],
                "provenance": "worn_at_arrival",
                "key": "clothes worn at arrival",
            }
        )

    # Ensure every kept row has latent_possible set; never claim powers at Start.
    ordinary_life = is_ordinary_this_life_start(arrival, story) or bool(harm.get("localized"))
    for row in kept:
        if "latent_possible" not in row:
            row["latent_possible"] = may_have_latent_potential(
                str(row.get("name") or ""),
                ordinary_start=ordinary_life,
            )
        # Starter items are never pre-powered
        row["rarity"] = "common"
        row["enchantments"] = []
        row["granted_abilities"] = []

    latent_candidates = [
        str(r.get("name") or "")
        for r in kept
        if r.get("latent_possible") and str(r.get("name") or "").strip()
    ][:12]

    kept_names = [k["name"] for k in kept]
    deferred_names = [d["name"] for d in deferred]
    stripped_names = [s["name"] for s in stripped]

    notes: list[str] = [arrival["notes"]]
    notes.extend(list(harm.get("notes") or []))
    if ordinary_life:
        notes.append(
            "Ordinary this-life start: kit is mundane at Start (common, no enchantments/granted abilities)."
        )
    if latent_candidates:
        notes.append(
            "Latent candidates (DM-only later): "
            + ", ".join(latent_candidates)
            + " — may gain a hidden property deep in play if still held, only as a special event."
        )
    if deferred_names:
        notes.append(
            "Deferred until after Start (earn/find/gift in play): " + ", ".join(deferred_names[:8])
        )
    if stripped_names:
        notes.append("Removed as illogical at Start: " + ", ".join(stripped_names[:8]))
    notes.extend(appearance_flags)

    player_messages: list[str] = []
    for msg in list(harm.get("player_messages") or []):
        if msg and msg not in player_messages:
            player_messages.append(msg)
    for row in stripped + deferred:
        msg = str(row.get("player_reason") or "").strip()
        if msg and msg not in player_messages:
            player_messages.append(msg)
    for flag in appearance_flags:
        if flag not in player_messages:
            player_messages.append(flag)
    demoted_kept = any(r.get("provenance") == "ordinary_demoted" for r in kept)
    clothing_fixed = any(
        r.get("provenance") == "clothing_backstory_mismatch" for r in kept
    )

    # Player-facing notes for demotions / ordinary start (do not spoil which item is latent).
    for row in kept:
        if row.get("provenance") in {"ordinary_demoted", "clothing_backstory_mismatch"}:
            msg = str(row.get("player_reason") or "").strip()
            if msg and msg not in player_messages:
                player_messages.append(msg)
    if ordinary_life and (stripped or demoted_kept or clothing_fixed):
        note = (
            "You start ordinary: no free powerful gear. Long-held starter pieces might later "
            "hide a secret — that is the DM's call deep in the game, not a free power at Start."
        )
        if note not in player_messages:
            player_messages.append(note)

    starter_out = ", ".join(kept_names) if apply_fixes else str(starter_equipment or "")
    story_changed = apply_fixes and story.strip() != str(character_backstory or "").strip()
    mode_changed = apply_fixes and mode.strip() != str(backstory_mode or "").strip()
    memory_changed = apply_fixes and memory.strip() != str(memory_policy or "").strip()
    gear_changed = apply_fixes and (
        starter_out.strip().lower() != ", ".join(raw_items).lower()
        or (new_appearance or "") != (appearance or "")
    )
    summary = (
        f"Arrival={arrival['arrival']}. Vibe={harm.get('path')}. Kept {len(kept_names)}, "
        f"deferred {len(deferred_names)}, stripped {len(stripped_names)}."
        + (f" Latent candidates={len(latent_candidates)}." if latent_candidates else "")
    )
    show_popup = bool(
        stripped
        or deferred
        or appearance_flags
        or story_changed
        or harm.get("localized")
        or demoted_kept
        or clothing_fixed
    )
    popup_title = ""
    if show_popup:
        if harm.get("localized"):
            popup_title = "Origin & gear aligned to world vibe"
        elif demoted_kept or ordinary_life:
            popup_title = "Ordinary start — gear matched to your life"
        else:
            popup_title = "Starting gear adjusted for lore"

    return {
        "ok": True,
        "arrival": arrival,
        "vibe": {
            "register": harm.get("register"),
            "origin": harm.get("origin"),
            "path": harm.get("path"),
            "localized": bool(harm.get("localized")),
            "vocation": harm.get("vocation") or "",
        },
        "ordinary_start": ordinary_life,
        "latent_candidates": latent_candidates,
        "kept": kept,
        "deferred": deferred,
        "stripped": stripped,
        "starter_equipment": starter_out[:500],
        "appearance": (new_appearance if apply_fixes else appearance)[:400],
        "character_backstory": (story if apply_fixes else character_backstory)[:1600],
        "backstory_mode": mode if apply_fixes else backstory_mode,
        "memory_policy": memory if apply_fixes else memory_policy,
        "changed": bool(gear_changed or story_changed or mode_changed or memory_changed),
        "notes": notes,
        "summary": summary,
        "player_messages": player_messages[:20],
        "show_popup": show_popup,
        "popup_title": popup_title,
        "gm_brief": _gm_brief(
            arrival,
            kept_names,
            deferred_names,
            stripped_names,
            vibe=harm,
            ordinary_start=ordinary_life,
            latent_candidates=latent_candidates,
        ),
    }


def _gm_brief(
    arrival: dict[str, Any],
    kept: list[str],
    deferred: list[str],
    stripped: list[str],
    *,
    vibe: dict[str, Any] | None = None,
    ordinary_start: bool = False,
    latent_candidates: list[str] | None = None,
) -> str:
    lines = [
        f"Starter gear fact-check: {arrival['arrival']}.",
        arrival.get("notes") or "",
        "Inventory at Start (only these): " + (", ".join(kept) if kept else "(clothes on body only)"),
    ]
    vibe = vibe if isinstance(vibe, dict) else {}
    if vibe.get("localized"):
        lines.append(
            f"Origin/backstory localized to world vibe"
            + (f" (vocation: {vibe.get('vocation')})" if vibe.get("vocation") else "")
            + ". Treat them as living this life — not as a modern Earth arsenal drop."
        )
    if ordinary_start or arrival.get("allows_this_life_gear"):
        lines.append(
            "Ordinary / this-life start: all starter items are mundane at Start "
            "(rarity=common, enchantments=[], granted_abilities=[]). Clothing must match vocation."
        )
    latent = [x for x in (latent_candidates or []) if x]
    if latent:
        lines.append(
            "LATENT (DM-only): if the player still holds one of these deep into the campaign, "
            "you MAY optionally reveal a hidden property as a special event "
            f"({', '.join(latent[:8])}). Never auto-power them at Start; never guarantee a reveal."
        )
    if deferred:
        lines.append(
            "Do NOT invent these as already owned at opening; they may appear only after play begins "
            f"(loot, gift, buy, craft, quest): {', '.join(deferred)}."
        )
    if stripped:
        lines.append("Never reintroduce stripped items without new causal story: " + ", ".join(stripped))
    if arrival["arrival"] == ARRIVAL_ISEKAI_ARRIVAL:
        lines.append(
            "Isekai/summon: opening is the moment of (or just after) arrival. "
            "No free fantasy arsenal. A god/system gift, if any, happens in-scene after Start."
        )
    if arrival["arrival"] == ARRIVAL_REINCARNATED:
        lines.append(
            "Reincarnation: they have already lived/grown in this world — gear is this-life property, not truck-kun loot."
        )
    return " ".join(x for x in lines if x)[:1600]


def apply_starter_logic_to_setup(
    fields: dict[str, Any],
    *,
    intent: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    """
    Mutate setup field dict: rewrite origin/backstory/gear when needed.
    Returns (fields, dirty_reasons).
    """
    out = dict(fields)
    intent = intent if isinstance(intent, dict) else {}
    if not intent and isinstance(out.get("_compose_intent"), dict):
        intent = out["_compose_intent"]
    report = fact_check_starter_loadout(
        starter_equipment=out.get("starter_equipment"),
        appearance=str(out.get("appearance") or ""),
        backstory_mode=str(out.get("backstory_mode") or ""),
        memory_policy=str(out.get("memory_policy") or ""),
        character_backstory=str(out.get("character_backstory") or ""),
        intent=intent,
        world_style=str(out.get("world_style") or ""),
        tech_level=str(out.get("tech_level") or ""),
        magic_level=str(out.get("magic_level") or ""),
        special_ability_origin=str(out.get("special_ability_origin") or ""),
        apply_fixes=True,
    )
    dirty: dict[str, str] = {}
    if report.get("changed"):
        if str(out.get("starter_equipment") or "").strip() != str(report.get("starter_equipment") or "").strip():
            out["starter_equipment"] = report["starter_equipment"]
            dirty["starter_equipment"] = "starter_logic_arrival"
        if str(out.get("appearance") or "").strip() != str(report.get("appearance") or "").strip():
            out["appearance"] = report["appearance"]
            dirty["appearance"] = "starter_logic_appearance"
        if str(out.get("character_backstory") or "").strip() != str(
            report.get("character_backstory") or ""
        ).strip():
            out["character_backstory"] = report["character_backstory"]
            dirty["character_backstory"] = "starter_logic_origin_vibe"
        if str(out.get("backstory_mode") or "").strip() != str(report.get("backstory_mode") or "").strip():
            out["backstory_mode"] = report["backstory_mode"]
            dirty["backstory_mode"] = "starter_logic_origin_vibe"
        if str(out.get("memory_policy") or "").strip() != str(report.get("memory_policy") or "").strip():
            out["memory_policy"] = report["memory_policy"]
            dirty["memory_policy"] = "starter_logic_origin_vibe"
    out["_starter_logic"] = {
        "arrival": report["arrival"],
        "vibe": report.get("vibe") or {},
        "ordinary_start": bool(report.get("ordinary_start")),
        "latent_candidates": list(report.get("latent_candidates") or [])[:12],
        "summary": report["summary"],
        "notes": report["notes"],
        "show_popup": bool(report.get("show_popup")),
        "popup_title": str(report.get("popup_title") or ""),
        "player_messages": list(report.get("player_messages") or [])[:20],
        "deferred": [
            {
                "name": d["name"],
                "reason": str(d.get("player_reason") or (d.get("reasons") or [""])[0] or ""),
            }
            for d in report["deferred"]
        ],
        "stripped": [
            {
                "name": s["name"],
                "reason": str(s.get("player_reason") or (s.get("reasons") or [""])[0] or ""),
            }
            for s in report["stripped"]
        ],
        "gm_brief": report["gm_brief"],
    }
    return out, dirty
