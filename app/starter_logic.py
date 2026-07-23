"""
Starter gear / clothing fact-check at setup and Start.

Question to answer: "If they have this when the player presses Start, where did it
come from under this arrival story?"

- Native / known life in-world: local mundane gear OK if life fits.
- Reincarnated / aged into this world: gear from *this* life only (no old-world kit).
- Pure isekai / summoned / just-transported: only what could be on them at arrival
  (clothes, pockets) — not fantasy shields/swords unless the world *is* modern LARP.
- God gifts, quest loot, system packages: **after** Start (deferred), not pre-seeded.

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

    tech = _norm(tech_level) + " " + _norm(world_style)
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
        )
    )
    fantasy_world = not modern_world and any(
        t in (genre + " " + _norm(world_style))
        for t in ("fantasy", "isekai", "wuxia", "cultivation", "medieval", "magic", "sect")
    )

    return {
        "arrival": kind,
        "isekai": bool(isekai_flag or kind == ARRIVAL_ISEKAI_ARRIVAL or "isekai" in blob),
        "modern_world": modern_world,
        "fantasy_world": fantasy_world or (kind == ARRIVAL_ISEKAI_ARRIVAL and not modern_world),
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
            "mana",
            "enchanted",
            "rune stone",
            "magic crystal",
            "talisman of",
            "amulet of power",
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
            "tool",
            "kit",
            "pouch of tools",
        )
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
        # modern tools only if modern-ish item
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
        "tailor",
        "cook",
        "apprentice",
        "courier",
        "sailor",
        "miner",
        "work",
        "trade",
        "craft",
    )
    return any(m in story for m in trade) or arrival["arrival"] == ARRIVAL_NATIVE


def evaluate_item(
    item_name: str,
    arrival: dict[str, Any],
    *,
    character_backstory: str = "",
) -> dict[str, Any]:
    """
    Returns decision: keep | strip | defer
    defer = not in starting inventory; may appear after Start via narration/loot.
    """
    meta = classify_item(item_name)
    bucket = meta["bucket"]
    story = _norm(character_backstory)
    kind = arrival["arrival"]
    reasons: list[str] = []

    if bucket == BUCKET_LEGENDARY:
        return {
            **meta,
            "decision": "strip",
            "reasons": ["Legendary / god-tier gear cannot exist at Start."],
            "provenance": "invalid",
        }

    if kind == ARRIVAL_AMNESIA:
        if bucket == BUCKET_WORN:
            return {
                **meta,
                "decision": "keep",
                "reasons": ["Minimal worn clothes OK for blank/amnesia start."],
                "provenance": "on_body_unknown",
            }
        if bucket == BUCKET_CONSUMABLE and any(w in meta["key"] for w in ("water", "bread", "ration")):
            return {
                **meta,
                "decision": "keep",
                "reasons": ["One survival scrap OK if already in hand."],
                "provenance": "found_on_person",
            }
        return {
            **meta,
            "decision": "strip",
            "reasons": ["Amnesia/blank start: no unexplained kit."],
            "provenance": "invalid",
        }

    if kind == ARRIVAL_ISEKAI_ARRIVAL:
        if bucket == BUCKET_WORN:
            return {
                **meta,
                "decision": "keep",
                "reasons": ["Worn at moment of transport."],
                "provenance": "worn_at_arrival",
            }
        if bucket == BUCKET_MODERN:
            if arrival.get("fantasy_world") and not arrival.get("modern_world"):
                return {
                    **meta,
                    "decision": "keep",
                    "reasons": ["Old-world pocket item carried through the portal."],
                    "provenance": "old_world_pocket",
                }
            return {
                **meta,
                "decision": "keep",
                "reasons": ["On-person modern item at arrival."],
                "provenance": "old_world_pocket",
            }
        if bucket == BUCKET_POCKET and not any(
            w in meta["key"] for w in ("map of", "kingdom", "dungeon", "mana", "rune")
        ):
            # small personal only — no fantasy maps of the new world
            if any(w in meta["key"] for w in ("notebook", "pen", "pencil", "wallet", "coin", "keys", "charm", "photo", "ring", "handkerchief")):
                return {
                    **meta,
                    "decision": "keep",
                    "reasons": ["Plausible pocket item at transport."],
                    "provenance": "old_world_pocket",
                }
            if any(w in meta["key"] for w in ("rope", "rations", "water", "flask")) and "backpack" in story:
                return {
                    **meta,
                    "decision": "keep",
                    "reasons": ["Travel kit only if they were already traveling when taken."],
                    "provenance": "old_world_bag",
                }
        if bucket in {BUCKET_COMBAT, BUCKET_MAGIC, BUCKET_TOOL, BUCKET_VALUABLE}:
            return {
                **meta,
                "decision": "defer",
                "reasons": [
                    "Isekai/summon arrival: fantasy combat gear, magic, or trade kits "
                    "cannot pre-exist Start — earn after arrival (loot, gift, buy, craft)."
                ],
                "provenance": "post_start_only",
            }
        if bucket == BUCKET_CONSUMABLE:
            return {
                **meta,
                "decision": "defer",
                "reasons": ["New-world food/water is found after arrival, not packed beforehand."],
                "provenance": "post_start_only",
            }
        return {
            **meta,
            "decision": "defer",
            "reasons": ["Not clearly on-person at the moment of transport."],
            "provenance": "post_start_only",
        }

    # Native / reincarnated / body transmigration — this-life gear
    if bucket == BUCKET_MODERN and arrival.get("fantasy_world") and not arrival.get("modern_world"):
        return {
            **meta,
            "decision": "strip",
            "reasons": ["Modern tech does not fit this world's tech without an old-world arrival."],
            "provenance": "invalid",
        }

    if bucket == BUCKET_WORN:
        return {
            **meta,
            "decision": "keep",
            "reasons": ["Worn clothes/gear of this life."],
            "provenance": "this_life_worn",
        }

    if bucket == BUCKET_COMBAT:
        if _combat_ok_for_arrival(arrival, story):
            return {
                **meta,
                "decision": "keep",
                "reasons": ["Backstory supports martial/tool-of-trade arms."],
                "provenance": "this_life_role",
            }
        return {
            **meta,
            "decision": "defer",
            "reasons": [
                "Combat kit (shield/sword/armor) needs a life that earned it — "
                "or it appears after Start via loot/gift/purchase."
            ],
            "provenance": "post_start_only",
        }

    if bucket == BUCKET_MAGIC:
        if "mage" in story or "wizard" in story or "cultivat" in story or "apprentice" in story:
            return {
                **meta,
                "decision": "keep",
                "reasons": ["Magic-student life can hold a minor focus — not a legendary."],
                "provenance": "this_life_role",
            }
        return {
            **meta,
            "decision": "defer",
            "reasons": ["Magic gear is not free at Start without a magical vocation in the backstory."],
            "provenance": "post_start_only",
        }

    if bucket == BUCKET_TOOL:
        if _tool_ok_for_arrival(arrival, story, meta["key"]):
            return {
                **meta,
                "decision": "keep",
                "reasons": ["Trade tools match a working life."],
                "provenance": "this_life_role",
            }
        # modest tools often OK for native
        if kind == ARRIVAL_NATIVE and any(w in meta["key"] for w in ("knife", "needle", "rope", "pouch")):
            return {
                **meta,
                "decision": "keep",
                "reasons": ["Small common tool for a local life."],
                "provenance": "this_life_common",
            }
        return {
            **meta,
            "decision": "defer",
            "reasons": ["Specialized tools need a job/craft mentioned in backstory."],
            "provenance": "post_start_only",
        }

    if bucket == BUCKET_VALUABLE:
        return {
            **meta,
            "decision": "strip",
            "reasons": ["Large valuables at Start break scarce-economy openings."],
            "provenance": "invalid",
        }

    # pocket / consumable defaults
    return {
        **meta,
        "decision": "keep",
        "reasons": ["Mundane this-life pocket/consumable item."],
        "provenance": "this_life_common",
    }


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
    apply_fixes: bool = True,
) -> dict[str, Any]:
    """
    Fact-check starter_equipment (+ optional clothing phrases from appearance).

    Returns kept list, deferred list, stripped list, rewritten strings, and human notes.
    """
    arrival = classify_arrival(
        backstory_mode=backstory_mode,
        memory_policy=memory_policy,
        character_backstory=character_backstory,
        intent=intent,
        world_style=world_style,
        tech_level=tech_level,
    )
    items = _split_items(starter_equipment)
    # Clothing from appearance also seeds "what they wear" — check combat clothes
    appearance_items = _split_items(appearance)

    kept: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    stripped: list[dict[str, Any]] = []

    for name in items:
        row = evaluate_item(name, arrival, character_backstory=character_backstory)
        if row["decision"] == "keep":
            kept.append(row)
        elif row["decision"] == "defer":
            deferred.append(row)
        else:
            stripped.append(row)

    # Appearance: if pure isekai arrival wearing plate/shield-like wardrobe, soften
    appearance_flags: list[str] = []
    new_appearance = appearance
    if arrival["arrival"] == ARRIVAL_ISEKAI_ARRIVAL and appearance:
        combatish = []
        for name in appearance_items:
            meta = classify_item(name)
            if meta["bucket"] in {BUCKET_COMBAT, BUCKET_MAGIC, BUCKET_LEGENDARY}:
                combatish.append(name)
        if combatish:
            appearance_flags.append(
                "Appearance had combat/magic wardrobe on isekai arrival — simplified to street/travel clothes."
            )
            if apply_fixes:
                new_appearance = (
                    "torso: plain travel clothes; feet: practical shoes; bag: small shoulder bag"
                )

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

    kept_names = [k["name"] for k in kept]
    deferred_names = [d["name"] for d in deferred]
    stripped_names = [s["name"] for s in stripped]

    notes: list[str] = [arrival["notes"]]
    if deferred_names:
        notes.append(
            "Deferred until after Start (earn/find/gift in play): " + ", ".join(deferred_names[:8])
        )
    if stripped_names:
        notes.append("Removed as illogical at Start: " + ", ".join(stripped_names[:8]))
    notes.extend(appearance_flags)

    starter_out = ", ".join(kept_names) if apply_fixes else str(starter_equipment or "")
    summary = (
        f"Arrival={arrival['arrival']}. Kept {len(kept_names)}, "
        f"deferred {len(deferred_names)}, stripped {len(stripped_names)}."
    )

    return {
        "ok": True,
        "arrival": arrival,
        "kept": kept,
        "deferred": deferred,
        "stripped": stripped,
        "starter_equipment": starter_out[:500],
        "appearance": (new_appearance if apply_fixes else appearance)[:400],
        "changed": bool(
            apply_fixes
            and (
                starter_out.strip().lower() != ", ".join(items).lower()
                or (new_appearance or "") != (appearance or "")
            )
        ),
        "notes": notes,
        "summary": summary,
        "gm_brief": _gm_brief(arrival, kept_names, deferred_names, stripped_names),
    }


def _gm_brief(
    arrival: dict[str, Any],
    kept: list[str],
    deferred: list[str],
    stripped: list[str],
) -> str:
    lines = [
        f"Starter gear fact-check: {arrival['arrival']}.",
        arrival.get("notes") or "",
        "Inventory at Start (only these): " + (", ".join(kept) if kept else "(clothes on body only)"),
    ]
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
    return " ".join(x for x in lines if x)[:1200]


def apply_starter_logic_to_setup(
    fields: dict[str, Any],
    *,
    intent: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    """
    Mutate setup field dict: rewrite starter_equipment / appearance when needed.
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
    out["_starter_logic"] = {
        "arrival": report["arrival"],
        "summary": report["summary"],
        "notes": report["notes"],
        "deferred": [d["name"] for d in report["deferred"]],
        "stripped": [s["name"] for s in report["stripped"]],
        "gm_brief": report["gm_brief"],
    }
    return out, dirty
