"""Written rules for short setup choices, stored before the first scene.

The setup field stays a short selection (``F,E,D,C,B,A,S,SS,SSS``, or a
player-typed list such as ``common, uncommon, rare, epic, legendary, unique
and unknown``). The row in ``setting_templates`` names every label. A custom
list splits on commas and on the word ``and``. Each unknown label gets its own
preset sentence. A known ladder or a known option phrase stays whole.

A new short setting is a ``TEMPLATE_SPECS`` entry plus a ``_MEANINGS`` map.
Rank scale is the special case: every rung has to be named, and a model rule
that glues two neighboring rungs with ``and`` is discarded. Boolean values are
stored as ``on`` or ``off``.

The setting-templates workflow finds custom setup controls and adds settings
that are not in ``TEMPLATE_SPECS`` yet. It must leave the short field short
and must leave this custom-list splitter in place.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

_BANNED = (
    "near-useless",
    "near useless",
    "compounding",
    "hour per level",
    "1 hour each day",
    "must spend 1 hour",
)

TEMPLATE_SPECS: tuple[dict[str, str], ...] = (
    {
        "key": "rank_scale",
        "label": "Rank scale",
        "sample": "F,E,D,C,B,A,S,SS,SSS",
        "ask": (
            "Write the rule for this rank ladder. Name every rung from low to high. "
            "Say that one step up is clearly stronger, and that a higher rung than the player "
            "is stronger than the player. Do not add rungs."
        ),
    },
    {
        "key": "economy",
        "label": "Economy",
        "sample": "scarce",
        "ask": "Write how goods and money move under this economy. Do not describe skills or power growth.",
    },
    {
        "key": "quest_style",
        "label": "Quest style",
        "sample": "emergent",
        "ask": "Write how hooks arrive under this quest structure. Do not describe player skills.",
    },
    {
        "key": "faction_pressure",
        "label": "Faction pressure",
        "sample": "local disputes",
        "ask": "Write who squeezes ordinary life under this faction pressure.",
    },
    {
        "key": "npc_stat_scaling",
        "label": "NPC stat scaling",
        "sample": "relative ranks",
        "ask": "Write how NPC ranks sit against the player under this scaling.",
    },
    {
        "key": "npc_skill_frequency",
        "label": "NPC skill frequency",
        "sample": "some trained NPCs",
        "ask": "Write how often people have a ranked skill under this frequency.",
    },
    {
        "key": "npc_density",
        "label": "NPC density",
        "sample": "moderate",
        "ask": "Write how crowded a scene is under this density.",
    },
    {
        "key": "difficulty",
        "label": "Difficulty",
        "sample": "normal",
        "ask": "Write how often enemies outrank the player under this difficulty.",
    },
    {
        "key": "loot_rarity",
        "label": "Loot rarity",
        "sample": "earned and uncommon",
        "ask": "Write how often mundane, rare, and enchanted goods appear under this loot rule.",
    },
    {
        "key": "magic_level",
        "label": "Magic level",
        "sample": "rare",
        "ask": "Write how common magic is under this level, and what a public spell means.",
    },
    {
        "key": "death_rules",
        "label": "Death rules",
        "sample": "downed, not deleted",
        "ask": "Write what a lost fight does to the player under this death rule.",
    },
    {
        "key": "narration_detail",
        "label": "Narration detail",
        "sample": "rich",
        "ask": "Write how full a scene should be under this narration detail.",
    },
    {
        "key": "skill_style",
        "label": "Skill learning",
        "sample": "standard",
        "ask": "Write how a new skill is earned under this learning rule. Do not write an XP formula.",
    },
    {
        "key": "tone",
        "label": "Tone",
        "sample": "grounded adventure",
        "ask": "Write the tone this playthrough keeps.",
    },
    {
        "key": "tech_level",
        "label": "Tech level",
        "sample": "iron age",
        "ask": "Write what tools and machines exist at this tech level, and what does not.",
    },
    {
        "key": "check_difficulty",
        "label": "Check difficulty",
        "sample": "normal",
        "ask": "Write how often a reasonable act succeeds under this check difficulty.",
    },
    {
        "key": "system_style",
        "label": "System style",
        "sample": "subtle blue-window system",
        "ask": (
            "Write how this in-world system appears and what a notice may reveal. "
            "Define every player-typed label instead of replacing them with a built-in ladder. "
            "Leave the short setup field unchanged, and do not describe skill growth."
        ),
    },
    {
        "key": "leveling_system",
        "label": "Leveling system",
        "sample": "on",
        "ask": (
            "Write whether the player gains levels and XP under this leveling choice. "
            "Define every player-typed label instead of replacing them with a built-in ladder."
        ),
    },
    {
        "key": "game_system",
        "label": "Game system",
        "sample": "off",
        "ask": (
            "Write whether a short in-world interface appears under this game system. "
            "Off means no status window, quest note, achievement, or system prompt. "
            "On means a brief diegetic window or prompt may appear and stays short. "
            "Define every player-typed label instead of replacing them with a built-in ladder. "
            "Leave the setup value short."
        ),
    },
    {
        "key": "proficiency_system",
        "label": "Proficiency system",
        "sample": "on",
        "ask": (
            "Write whether specialized actions require a learned proficiency under this choice. "
            "Define every player-typed label instead of replacing them with a built-in ladder."
        ),
    },
    {
        "key": "dice_checks_enabled",
        "label": "Dice checks",
        "sample": "off",
        "ask": (
            "Write how speech, strength, lore, events, and encounters are settled under this dice-check choice. "
            "Define every player-typed label instead of replacing them with a built-in ladder."
        ),
    },
    {
        "key": "event_check_frequency",
        "label": "Event check frequency",
        "sample": "normal",
        "ask": (
            "Write how often event checks happen under this frequency. "
            "Define every player-typed label instead of replacing them with a built-in ladder."
        ),
    },
    {
        "key": "encounter_check_frequency",
        "label": "Encounter check frequency",
        "sample": "normal",
        "ask": (
            "Write how often an encounter check is called under this frequency. "
            "Define every player-typed label instead of replacing them with a built-in ladder."
        ),
    },
    {
        "key": "new_skill_frequency",
        "label": "New skill frequency",
        "sample": "normal",
        "ask": (
            "Write how often the player discovers or gains an entirely new skill under this frequency. "
            "Define every player-typed label, one sentence each, instead of replacing them with a built-in ladder."
        ),
    },
    {
        "key": "proficiency_access",
        "label": "Proficiency access",
        "sample": "learned",
        "ask": (
            "Write what the player may attempt before a specialized proficiency is reliable under this access rule. "
            "Define every player-typed label. Do not replace those labels with a built-in ladder."
        ),
    },
    {
        "key": "world_races",
        "label": "World races",
        "sample": "human",
        "ask": (
            "Write which peoples commonly exist under this races choice. "
            "Define every player-typed label on its own instead of replacing them with a built-in ladder. "
            "Do not add a people, occupation, or rank the player did not name, and leave the short setup list unchanged."
        ),
    },
)

_RANK_LADDERS = {
    "f,e,d,c,b,a,s,ss,sss": (
        "Ranks run from low to high: F, E, D, C, B, A, S, SS, SSS. "
        "F is untrained. E has some practice. D is competent. C is skilled. "
        "B is notable. A is an expert. S is exceptional. SS is rare mastery. "
        "SSS is the top of this ladder. One step up is clearly stronger than the step below. "
        "A higher rung than the player is stronger than the player. A lower rung is weaker. "
        "Use only these labels. Do not replace a rank with a raw number."
    ),
    "d,c,b,a,s": (
        "Ranks run from low to high: D, C, B, A, S. "
        "D is the ordinary floor. C is trained. B is capable. A is an expert. "
        "S is the top of this shorter ladder. One step up is a clear gain. "
        "A higher rung than the player is stronger than the player. A lower rung is weaker. "
        "Do not add F, SS, or SSS."
    ),
    "common,trained,veteran,elite,mythic": (
        "Tiers run from low to high: Common, Trained, Veteran, Elite, Mythic. "
        "Common is ordinary. Trained has a practiced craft. Veteran has been tested. "
        "Elite is rare skill. Mythic is the top of this ladder. "
        "One step up is a clear gain against the player. Do not swap in letter ranks."
    ),
}

_MEANINGS: dict[str, dict[str, str]] = {
    "economy": {
        "scarce": "Coin and goods are scarce. A price bites, and a full pack is not a shopping trip.",
        "barter-heavy": "Most deals are trade in goods or favors, not a posted coin price.",
        "coin-driven": "Coin is the normal price. A purse is what a seller expects to see.",
        "guild-controlled": "A guild decides who may sell and what the price is allowed to be.",
    },
    "quest_style": {
        "emergent": "Hooks come out of what the player does and who they meet. No board is required.",
        "job board": "Paid work is posted where people look for jobs, and taking one is a choice.",
        "faction chains": "A group offers the next job after the last, and refusing has a social cost.",
        "personal mysteries": "The pull is a private question about a person or a place, not a public bounty.",
    },
    "faction_pressure": {
        "local disputes": "Pressure is neighborhood arguments, debts, and rival streets.",
        "sect hierarchy": "A ranked order of masters and disciples decides who may act.",
        "guild control": "A guild license, fee, or ban is what opens or closes work.",
        "military occupation": "Soldiers, checkpoints, and orders sit on ordinary errands.",
        "hidden cults": "A quiet belief is pulling people, and open talk about it is risky.",
    },
    "npc_stat_scaling": {
        "relative ranks": "Most people sit near the player's rank. Ordinary folk are a step down, and a specialist is a step up.",
        "mostly weaker": "Crowds and common foes are below the player. A named threat can still match them.",
        "near player": "People the player can fight are close to the player's own rank.",
        "swingy ranks": "The same street can hold someone far below the player and someone far above.",
        "elite-heavy": "Trained and ranked people are common. A weak crowd is the exception.",
    },
    "npc_skill_frequency": {
        "some trained npcs": "Some people have a ranked skill. Most do not.",
        "no special npc skills": "People are ordinarily competent. Do not hand out special ranked skills.",
        "rare specialists": "A special skill belongs to a rare specialist, not the crowd.",
        "many trained npcs": "Many people have one ranked skill that fits their work.",
        "almost everyone has skills": "Almost everyone has a ranked skill. Ordinary incompetence is uncommon.",
    },
    "npc_density": {
        "moderate": "A scene has a few named people and a sense of others nearby.",
        "sparse": "Scenes are thin. A second named person is a choice, not a crowd.",
        "dense": "Streets and rooms hold many people. Name only those the scene uses.",
        "faction-heavy": "The people present are there because a faction put them there.",
    },
    "difficulty": {
        "easy": "Enemies above the player's rank are uncommon.",
        "normal": "Enemies mix around the player's rank.",
        "hard": "Higher ranks and specialized skills show up more often.",
        "brutal": "Stronger ranks are common, and a fair fight is not the default.",
    },
    "loot_rarity": {
        "earned and uncommon": "Mundane supplies can be found. Rare or enchanted pieces are earned by risk, and they stay uncommon.",
        "scarce mundane": "Even ordinary supplies are hard to come by. An enchanted piece is exceptional.",
        "generous adventuring": "Useful gear turns up from adventuring, still short of a free legendary every scene.",
        "high-magic loot": "Enchanted and unusual pieces belong to the setting. A legendary piece still needs a reason.",
    },
    "magic_level": {
        "rare": "Magic is rare. A public spell is an event.",
        "forbidden": "Magic is banned or hidden. Using it has a consequence.",
        "common utility": "Small practical magic is ordinary. A great working is not.",
        "cultivation": "Power is trained in stages. A rank is a stage of that training, not a free spell list.",
        "none": "There is no magic. Do not add spells, mana, or enchanted shortcuts.",
    },
    "death_rules": {
        "downed, not deleted": "A lost fight downs the player. It does not erase them.",
        "lasting injuries": "A bad loss leaves an injury that stays.",
        "permadeath threat": "Death can stick when the scene has made that risk plain.",
        "narrative setback": "A loss is a setback in the story. It is not an automatic end.",
    },
    "narration_detail": {
        "rich": "Write a full scene: the place, the people, and the consequence of the action.",
        "balanced": "Keep the scene complete without lingering on every surface.",
        "expansive": "Spend more on what the place feels like, how people react, and what the choice opens.",
        "concise": "Use fewer beats. Still say what happened and what can be done next.",
    },
    "skill_style": {
        "standard": "A skill comes from practice, teaching, or a demonstrated need.",
        "generous": "Repeated use can open a skill sooner.",
        "training-heavy": "A skill wants a teacher, a drill, or a stretch of practice.",
        "strict": "A new skill needs a clear lesson or a hard success. Casual use does not grant one.",
    },
    "tone": {
        "grounded adventure": "Trouble is practical, and people are ordinary until proven otherwise.",
        "survival pressure": "Food, weather, injury, and shelter stay in the scene.",
        "political intrigue": "Who gains, and who is listening, matters as much as the action.",
        "mythic progression": "Deeds can grow into stories people repeat. They are not free power.",
        "grim road story": "The road costs something. Comfort is brief.",
    },
    "tech_level": {
        "iron age": "Tools, weapons, and buildings are iron-age work. There are no engines or firearms.",
        "medieval": "Tools fit a medieval town: iron, timber, cloth, and animal power.",
        "early industrial": "Mills, coal, and early machines exist. They are not modern electronics.",
        "near future": "Personal tech can exist. It is near-future, not starflight.",
        "spacefaring salvage": "Ships, salvage, and worn space gear exist. A working miracle device still needs a reason.",
    },
    "check_difficulty": {
        "easy": "A reasonable act leans toward a success or a partial.",
        "normal": "A check matches the risk. A hard act can fail.",
        "hard": "The same act fails more often, and a partial is narrower.",
        "brutal": "Success is uncommon unless the player has a real advantage.",
    },
    "system_style": {
        "subtle blue-window system": "A subtle blue-window system is a brief status window for stats, prompts, and simple notices.",
        "cold quest-log interface": "A cold quest-log interface lists tasks, rewards, warnings, and failures like a detached ledger.",
        "cultivation status pane": "A cultivation status pane shows realms, breakthroughs, affinities, bottlenecks, and inner state.",
        "diegetic omen prompts": "Diegetic omen prompts arrive as omens, dreams, symbols, coincidences, or intuition rather than a menu.",
    },
    "leveling_system": {
        "on": "On is the yes choice: the player gains levels and XP.",
        "off": "Off is the no choice: the player does not gain levels or XP. Change comes from training, items, and the story.",
    },
    "game_system": {
        "off": "Off means there is no in-world interface, so do not add status windows, quest notes, achievements, or system prompts.",
        "on": "On means a short diegetic interface may appear, such as a status window or a system prompt, and those messages stay brief.",
    },
    "proficiency_system": {
        "on": "On means a specialized action may require a learned proficiency.",
        "off": "Off means an ordinary action is not gated behind a learned proficiency. A check is for exceptional pressure, expert work, combat, deception, or a specialized task.",
    },
    "dice_checks_enabled": {
        "on": "On means speech, strength, lore, events, and encounters can use dice.",
        "off": "Off is pure narrative, so speech, strength, lore, events, and encounters settle in the scene without a roll.",
    },
    "event_check_frequency": {
        "off": "Off means event checks are not called.",
        "rare": "Rare means a hazard, discovery, or omen check is uncommon.",
        "normal": "Normal means event checks arrive at an ordinary pace.",
        "frequent": "Frequent means event checks come up often.",
    },
    "encounter_check_frequency": {
        "off": "Off means encounter checks are not called.",
        "rare": "Rare means a road, ambush, or pursuit check is uncommon.",
        "normal": "Normal means encounter checks happen at a steady pace.",
        "frequent": "Frequent means encounter checks come up often.",
    },
    "new_skill_frequency": {
        "normal": "Normal means a new skill can appear from practice or discovery, without a rush of them.",
        "very rare": "Very rare means a new skill appears only from major training or a major event.",
        "rare": "Rare means a new skill stays uncommon and still needs a clear occasion.",
        "frequent": "Frequent means new skills show up more often from use.",
        "very frequent": "Very frequent means new skills may appear from repeated use and discovery.",
    },
    "proficiency_access": {
        "learned": "Learned means the player must train, observe, practice, or be taught before a specialized proficiency is reliable.",
        "familiar actions free": "Familiar actions free means a familiar act needs no proficiency, while an unfamiliar specialty still does.",
        "only expert tasks require training": "Only expert tasks require training means ordinary work stays open, while expert work still needs training.",
    },
    "world_races": {
        "human": "Human is an ancestry someone is born as, not an occupation, a rank, or a power tier. Humans stay usual unless this selection leaves them out, and only the selected peoples are common.",
        "elf": "Elf is an ancestry someone is born as, not an occupation, a rank, or a power tier, and only the selected peoples are common.",
        "dwarf": "Dwarf is an ancestry someone is born as, not an occupation, a rank, or a power tier, and only the selected peoples are common.",
        "orc": "Orc is an ancestry someone is born as, not an occupation, a rank, or a power tier, and only the selected peoples are common.",
        "beastfolk": "Beastfolk is an ancestry someone is born as, not an occupation, a rank, or a power tier, and only the selected peoples are common.",
        "spirit-touched": "Spirit-touched is an ancestry someone is born as, not an occupation, a rank, or a power tier, and only the selected peoples are common.",
    },
}

_KNOWN_PHRASES = frozenset(
    phrase.strip().lower()
    for table in _MEANINGS.values()
    for phrase in table
)


def ensure_setting_template_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS setting_templates (
            key TEXT PRIMARY KEY,
            choice TEXT NOT NULL,
            rule TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'fallback',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def choice_parts(choice: str) -> list[str]:
    """Split a setup choice into labels.

    Commas, semicolons, slashes, and pipes separate labels. The word ``and``
    separates labels too, so ``unique and unknown`` is two rungs. A built-in
    phrase such as ``earned and uncommon`` stays one label. ``and`` inside a
    word, as in ``android``, is not a separator.
    """
    raw_choice = str(choice or "").strip()
    if not raw_choice:
        return []
    if raw_choice.lower() in _KNOWN_PHRASES:
        return [raw_choice]
    parts: list[str] = []
    for raw in re.split(r"[,;/|]+", raw_choice):
        text = raw.strip()
        if not text or text.lower() in {"custom", "random"}:
            continue
        if text.lower() in _KNOWN_PHRASES:
            parts.append(text)
            continue
        bits = [
            bit.strip()
            for bit in re.split(r"\s+and\s+", text, flags=re.IGNORECASE)
            if bit.strip() and bit.strip().lower() not in {"custom", "random"}
        ]
        if len(bits) > 1:
            parts.extend(bits)
        else:
            parts.append(text)
    if parts:
        return parts
    return [raw_choice]


def choice_text(value: Any) -> str:
    if isinstance(value, bool):
        return "on" if value else "off"
    return str(value or "").strip()[:200]


def resolve_choice(options: dict[str, Any], key: str) -> str:
    """Top-level setup value, then the same key inside skill_check_settings."""
    if not isinstance(options, dict):
        return ""
    sources = [options]
    nested = options.get("skill_check_settings")
    if isinstance(nested, dict):
        sources.append(nested)
    for source in sources:
        if key not in source:
            continue
        value = source.get(key)
        if isinstance(value, (dict, list)):
            continue
        text = choice_text(value)
        if text:
            return text
    return ""


def _mentions_label(text: str, label: str) -> bool:
    token = label.strip()
    if not token:
        return False
    return re.search(
        rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])",
        text,
        re.IGNORECASE,
    ) is not None


def _rank_glued(rule: str, parts: list[str]) -> bool:
    """True when two neighboring rungs are written as one 'left and right' rung."""
    lowered = rule.lower()
    for left, right in zip(parts, parts[1:]):
        pair = f"{left.strip().lower()} and {right.strip().lower()}"
        if pair in lowered:
            return True
    return False


def rule_covers_choice(key: str, choice: str, rule: str) -> bool:
    text = str(rule or "").strip()
    if len(text) < 40 or len(text) > 900:
        return False
    if text.lower() == str(choice or "").strip().lower():
        return False
    lowered = text.lower()
    if any(banned in lowered for banned in _BANNED):
        return False
    parts = choice_parts(choice)
    if not parts:
        return False
    if key == "rank_scale":
        if not all(_mentions_label(text, part) for part in parts):
            return False
        return not _rank_glued(text, parts)
    return all(part.lower() in lowered for part in parts)


def _list_preset(label: str, part: str, index: int, total: int) -> str:
    if index == 0:
        return f"{part} is the first entry on this {label} list."
    if index == total - 1:
        return f"{part} is the last entry on this {label} list."
    return f"{part} is entry {index + 1} of {total} on this {label} list."


def _from_meanings(choice: str, meanings: dict[str, str], label: str) -> str:
    parts = choice_parts(choice)
    sentences: list[str] = []
    total = len(parts)
    for index, part in enumerate(parts):
        known = meanings.get(part.lower())
        if known:
            sentences.append(known)
        elif total > 1:
            sentences.append(_list_preset(label, part, index, total))
        else:
            sentences.append(f"Follow this {label} as the player wrote it.")
    if not sentences:
        sentences.append(f"Follow this {label} as the player wrote it.")
    shown = ", ".join(parts) if parts else str(choice or "").strip()
    sentences.append(f"The chosen {label} is: {shown}. Do not swap in a different {label}.")
    return " ".join(sentences)[:900]


def _rank_rung_lines(parts: list[str]) -> list[str]:
    count = len(parts)
    lines: list[str] = []
    for index, label in enumerate(parts):
        if count == 1:
            lines.append(f"{label} is the only rung on this ladder.")
        elif index == 0:
            lines.append(f"{label} is the bottom of this ladder.")
        elif index == count - 1:
            lines.append(f"{label} is the top of this ladder.")
        else:
            lines.append(f"{label} sits above {parts[index - 1]} and below {parts[index + 1]}.")
    return lines


def _rank_fallback(choice: str) -> str:
    folded = re.sub(r"\s+", "", choice).lower()
    known = _RANK_LADDERS.get(folded)
    if known:
        return known
    parts = choice_parts(choice)
    if not parts:
        return ""
    shown = ", ".join(parts)
    sentences = [f"Ranks run from low to high: {shown}."]
    sentences.extend(_rank_rung_lines(parts))
    sentences.append("Each step up is clearly stronger than the step below.")
    sentences.append(
        "A higher rung than the player is stronger than the player. A lower rung is weaker."
    )
    sentences.append("Use only these labels. Do not add rungs that are not in that list.")
    return " ".join(sentences)[:900]


def fallback_rule(key: str, choice: str) -> str:
    text = str(choice or "").strip()
    if not text:
        return ""
    if key == "rank_scale":
        return _rank_fallback(text)
    spec = next((item for item in TEMPLATE_SPECS if item["key"] == key), None)
    label = str((spec or {}).get("label") or key).lower()
    return _from_meanings(text, _MEANINGS.get(key) or {}, label)


def _candidate_text(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("rule") or "").strip()
    return str(value or "").strip()


def _rules_from_payload(payload: Any) -> dict[str, str]:
    found: dict[str, str] = {}
    if not isinstance(payload, dict):
        return found
    raw = payload.get("templates", payload)
    rows: list[Any]
    if isinstance(raw, dict):
        rows = [{"key": key, "rule": value} for key, value in raw.items()]
    elif isinstance(raw, list):
        rows = raw
    else:
        return found
    known = {spec["key"] for spec in TEMPLATE_SPECS}
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key") or "").strip()
        if key not in known:
            continue
        text = _candidate_text(row.get("rule") if "rule" in row else row)
        if text:
            found[key] = text
    return found


def store_setting_templates(
    conn,
    options: dict[str, Any],
    model_rules: dict[str, Any] | None = None,
) -> dict[str, dict[str, str]]:
    """Replace this playthrough's template rows. A model rule is kept only when it covers the choice."""
    ensure_setting_template_table(conn)
    conn.execute("DELETE FROM setting_templates")
    offered = model_rules if isinstance(model_rules, dict) else {}
    packed: dict[str, dict[str, str]] = {}
    for spec in TEMPLATE_SPECS:
        key = spec["key"]
        choice = resolve_choice(options, key)
        if not choice:
            continue
        accepted = ""
        candidate = _candidate_text(offered.get(key))
        if candidate and rule_covers_choice(key, choice, candidate):
            accepted = candidate[:900]
        if accepted:
            rule, source = accepted, "llm"
        else:
            rule, source = fallback_rule(key, choice), "fallback"
        if not rule:
            continue
        conn.execute(
            """
            INSERT INTO setting_templates (key, choice, rule, source)
            VALUES (?, ?, ?, ?)
            """,
            (key, choice, rule[:900], source),
        )
        packed[key] = {"choice": choice, "rule": rule[:900], "source": source}
    return packed


def overlay_setting_templates(conn, settings: dict[str, Any]) -> None:
    """Table rows win over a stale copy inside playthrough_options."""
    options = settings.get("playthrough_options")
    if not isinstance(options, dict):
        return
    try:
        rows = conn.execute(
            "SELECT key, choice, rule, source FROM setting_templates ORDER BY key"
        ).fetchall()
    except Exception:
        return
    if not rows:
        return
    options["setting_templates"] = {
        str(row["key"]): {
            "choice": str(row["choice"] or ""),
            "rule": str(row["rule"] or ""),
            "source": str(row["source"] or "fallback"),
        }
        for row in rows
    }


def cloud_templates_allowed() -> bool:
    """Cloud story provider only. This never starts a local model server."""
    flag = os.getenv("AI_RPG_SETTING_TEMPLATES", "auto").strip().lower()
    if flag in {"0", "false", "off", "no", "fallback"}:
        return False
    try:
        from app.llm import _normalize_provider, get_model_config, resolve_api_key

        config = get_model_config()
        if _normalize_provider(str(config.get("provider") or "")) != "openai":
            return False
        return bool(resolve_api_key(config))
    except Exception:
        return False


def _field_ask(spec: dict[str, str], choice: str) -> str:
    ask = spec["ask"]
    parts = choice_parts(choice)
    listed = ", ".join(parts)
    if spec["key"] == "rank_scale":
        folded = re.sub(r"\s+", "", choice).lower()
        if folded not in _RANK_LADDERS and listed:
            ask += (
                " These are the player's own rungs, low to high: "
                + listed
                + ". Define each rung on its own. Do not merge two rungs with the word and. "
                "Do not replace them with F to SSS or with Common, Trained, Veteran, Elite, Mythic."
            )
        return ask
    meanings = _MEANINGS.get(spec["key"]) or {}
    if listed and any(part.lower() not in meanings for part in parts):
        ask += (
            " The player's labels are: "
            + listed
            + ". Define each label. Do not replace a player label with a built-in option."
        )
    return ask


def ask_model(options: dict[str, Any]) -> dict[str, str]:
    from app.llm import _chat_content_unlocked, _extract_json

    fields = []
    for spec in TEMPLATE_SPECS:
        choice = resolve_choice(options, spec["key"])
        if not choice:
            continue
        fields.append({"key": spec["key"], "choice": choice, "ask": _field_ask(spec, choice)})
    if not fields:
        return {}
    system = (
        "You write durable rules for one RPG playthrough. Return one JSON object only, "
        'shaped {"templates":[{"key":"...","rule":"..."}]}. '
        "One object per field you were given. Each rule must include the chosen wording itself. "
        "Use at most four short sentences, or one short sentence per player label when that "
        "list is longer. For rank_scale, name every rung from "
        "low to high and say a higher rung is stronger than the player. When the player "
        "wrote their own list, define each label in that order. A list that ends with the "
        "word and is still separate labels. Do not merge two labels into one, and do not "
        "replace the player's labels with a built-in ladder. Do not change the chosen "
        "value, add rungs, or write a skill-growth essay. Do not mention compounding, "
        "near-useless skills, or hour-per-level timers."
    )
    user = json.dumps(
        {
            "world_style": str(options.get("world_style") or "")[:120],
            "difficulty": str(options.get("difficulty") or "")[:60],
            "magic_level": str(options.get("magic_level") or "")[:80],
            "tech_level": str(options.get("tech_level") or "")[:80],
            "tone": str(options.get("tone") or "")[:100],
            "fields": fields,
        },
        ensure_ascii=True,
    )
    content = _chat_content_unlocked(
        system,
        user,
        timeout=40,
        temperature=0.3,
        max_tokens=1600,
        response_format="json",
    )
    return _rules_from_payload(_extract_json(content))


def refresh_setting_templates_from_model() -> dict[str, Any]:
    """Ask the cloud model once, then keep a fallback wherever its rule does not cover the choice."""
    if not cloud_templates_allowed():
        return {"called": False, "updated": 0}
    from app.db import connect

    with connect() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = 'playthrough_options'"
        ).fetchone()
        if not row:
            return {"called": False, "updated": 0}
        try:
            options = json.loads(str(row["value"] or "{}"))
        except json.JSONDecodeError:
            return {"called": False, "updated": 0}
        if not isinstance(options, dict):
            return {"called": False, "updated": 0}
        try:
            model_rules = ask_model(options)
        except Exception:
            return {"called": True, "updated": 0}
        packed = store_setting_templates(conn, options, model_rules=model_rules)
        options["setting_templates"] = packed
        conn.execute(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            ("playthrough_options", json.dumps(options, ensure_ascii=True)),
        )
    updated = sum(1 for item in packed.values() if item.get("source") == "llm")
    return {"called": True, "updated": updated}
