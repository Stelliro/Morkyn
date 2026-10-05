"""
Setup coherence: the character the player starts with agrees with itself.

Game 2's save (playtest #21) contradicted itself in four places at once:

  * name Miriam and a backstory that said "she", stored as sex male;
  * the backstory arrived at "The Empty Lot" while play began at Eldoria's Edge;
  * appearance said a leather jerkin and sandals while the worn cards were
    boots, tunic and trousers;
  * the backstory's "small, enchanted lantern" was not in the inventory.

Nothing cross-checked any of it. This module holds the checks. The engine
decides; nothing here asks the model anything.

  * Sex and pronouns: ``pronoun_sex`` reads the backstory, ``name_sex`` reads
    the engine's own name pools. A sex the player chose is never changed:
    ``identity_warnings`` flags a disagreement for the setup page.
    ``infer_player_sex`` fills a sex left unset.
  * Arrival: ``align_backstory_arrival`` makes the place the backstory arrives
    at the start location.
  * Clothes: the worn gear cards are the structured truth. An unnamed basic
    takes its name from the appearance tag for its zone
    (``name_basics_from_appearance``); after that, the appearance clothing tags
    are rewritten from the worn cards (``appearance_from_gear``).
  * Carried items: ``backstory_carried_items`` lists what the backstory says
    the character carries, and ``backstory_gear_items`` turns the ones no card
    already covers into carried cards. They then go through the same starter
    fact-check as every other card.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# Sex, pronouns, names
# ---------------------------------------------------------------------------

_FEMALE_PRONOUNS = ("she", "her", "hers", "herself")
_MALE_PRONOUNS = ("he", "him", "his", "himself")


def _count_words(text: str, words: Iterable[str]) -> int:
    return sum(len(re.findall(rf"\b{re.escape(w)}\b", text, flags=re.I)) for w in words)


def pronoun_sex(text: Any) -> str:
    """'female' or 'male' when the text's he/she pronouns clearly lean one way, else ''.

    A backstory names other people too ("the elder trained her", "his
    workshop"), so one stray pronoun of the other kind does not cancel the
    lead: the leading kind needs at least two uses and three times the other.
    """
    body = str(text or "")
    female = _count_words(body, _FEMALE_PRONOUNS)
    male = _count_words(body, _MALE_PRONOUNS)
    if female and not male:
        return "female"
    if male and not female:
        return "male"
    if female >= 2 and female >= 3 * male:
        return "female"
    if male >= 2 and male >= 3 * female:
        return "male"
    return ""


def _given_name_sets() -> tuple[set[str], set[str]]:
    try:
        from app.example_pools import _NAMES
    except Exception:
        return set(), set()
    female: set[str] = set()
    male: set[str] = set()
    for table in _NAMES.values():
        female |= {str(n).lower() for n in table.get("female", ())}
        male |= {str(n).lower() for n in table.get("male", ())}
    return female - male, male - female


def name_sex(name: Any) -> str:
    """The sex the engine's name pools give this name's given part, or '' when unknown."""
    parts = [p for p in re.split(r"[\s\-]+", str(name or "").strip().lower()) if p]
    if not parts:
        return ""
    female, male = _given_name_sets()
    # Family-first cultures put the given name last; try every part, first wins.
    for part in parts:
        if part in female:
            return "female"
        if part in male:
            return "male"
    return ""


def binary_sex(value: Any) -> str:
    low = str(value or "").strip().lower()
    return low if low in ("female", "male") else ""


def pronouns_for_sex(sex: Any) -> str:
    """The pronouns a backstory uses for this character."""
    low = binary_sex(sex)
    if low == "female":
        return "she/her"
    if low == "male":
        return "he/him"
    return "they/them"


def pronouns_for_setup(setup: dict[str, Any] | None) -> str:
    """Pronouns for the backstory ask: the chosen sex, else the name's, else they/them."""
    setup = setup if isinstance(setup, dict) else {}
    sex = binary_sex(setup.get("player_sex"))
    if not sex and not str(setup.get("player_sex") or "").strip():
        sex = name_sex(setup.get("player_name"))
    return pronouns_for_sex(sex)


def infer_player_sex(setup: dict[str, Any] | None) -> str:
    """For an unset sex only: the backstory's pronouns, else the name. '' when neither says."""
    setup = setup if isinstance(setup, dict) else {}
    if str(setup.get("player_sex") or "").strip():
        return ""
    return pronoun_sex(setup.get("character_backstory")) or name_sex(setup.get("player_name"))


def identity_warnings(setup: dict[str, Any] | None) -> list[dict[str, str]]:
    """Disagreements between the chosen sex, the backstory's pronouns and the name.

    The player's chosen sex is theirs: these are shown on the setup page, and
    nothing here changes a field.
    """
    setup = setup if isinstance(setup, dict) else {}
    sex = binary_sex(setup.get("player_sex"))
    warnings: list[dict[str, str]] = []
    if not sex:
        return warnings
    story_sex = pronoun_sex(setup.get("character_backstory"))
    if story_sex and story_sex != sex:
        said = "she/her" if story_sex == "female" else "he/him"
        warnings.append(
            {
                "code": "sex_vs_backstory_pronouns",
                "field": "player_sex",
                "message": (
                    f"Sex is set to {sex}, but the backstory calls the character {said}. "
                    "Change the sex or the backstory, or press Start again to keep both as they are."
                ),
            }
        )
    named = name_sex(setup.get("player_name"))
    if named and named != sex:
        name = str(setup.get("player_name") or "").strip()
        warnings.append(
            {
                "code": "sex_vs_name",
                "field": "player_name",
                "message": (
                    f"Sex is set to {sex}, but {name} is a {named} name in this game's name lists. "
                    "Change one, or press Start again to keep both."
                ),
            }
        )
    return warnings


# ---------------------------------------------------------------------------
# Arrival place
# ---------------------------------------------------------------------------

_ARRIVAL_VERBS = (
    r"arriv(?:e|es|ed|ing)",
    r"(?:a)?wak(?:e|es|ing|ened|ens)(?:\s+up)?",
    r"woke(?:\s+up)?",
    r"awoke",
    r"land(?:s|ed|ing)",
    r"appear(?:s|ed|ing)",
    r"emerg(?:e|es|ed|ing)",
    r"stumbl(?:e|es|ed|ing)(?:\s+out)?",
    r"found\s+(?:herself|himself|themselves|themself)",
    r"finds\s+(?:herself|himself|themselves|themself)",
)
_PLACE = r"(?P<place>(?:[Tt]he\s+)?[A-Z][\w'’\-]*(?:\s+(?:(?:of|the|de|del|la|le|upon|on)\s+)?[A-Z][\w'’\-]*)*)"
_ARRIVAL_RE = re.compile(
    r"\b(?:" + "|".join(_ARRIVAL_VERBS) + r")\s+(?:(?:at|in|on|into|onto|near|outside|beside|by)\s+)" + _PLACE
)


def _place_key(text: Any) -> str:
    low = str(text or "").lower().replace("’", "'")
    low = re.sub(r"^the\s+", "", low.strip())
    return re.sub(r"[^a-z0-9']+", " ", low).strip()


def _place_tokens(text: Any) -> set[str]:
    tokens = {re.sub(r"'s?$", "", t) for t in _place_key(text).split()}
    return {t for t in tokens if len(t) >= 4}


def arrival_place(backstory: Any) -> str:
    """The named place the backstory arrives at ('' when it names none)."""
    match = _ARRIVAL_RE.search(str(backstory or ""))
    return match.group("place").strip() if match else ""


def align_backstory_arrival(backstory: Any, start_location: Any, *, previous: Any = "") -> tuple[str, bool]:
    """Make the backstory arrive where play starts.

    ``previous`` is the start location the backstory was written for, when the
    caller knows it: every mention of it becomes the new one. Otherwise the
    first named arrival place is replaced, unless it already shares a word with
    the start location (a region and a place in it: "Eldoria" and "Eldoria's
    Edge").
    """
    story = str(backstory or "")
    target = re.sub(r"\s+", " ", str(start_location or "")).strip()
    if not story.strip() or not target:
        return story, False
    old = re.sub(r"\s+", " ", str(previous or "")).strip()
    if old and _place_key(old) != _place_key(target) and old in story:
        return story.replace(old, target), True
    if _place_key(target) and _place_key(target) in _place_key(story):
        return story, False
    match = _ARRIVAL_RE.search(story)
    if not match:
        return story, False
    place = match.group("place").strip()
    if _place_key(place) == _place_key(target) or (_place_tokens(place) & _place_tokens(target)):
        return story, False
    start, end = match.span("place")
    return story[:start] + target + story[end:], True


# ---------------------------------------------------------------------------
# Appearance and worn gear
# ---------------------------------------------------------------------------

def _gear():
    from app import gear as gear_mod

    return gear_mod


_ZONE_LABELS = {
    "HEAD": "head",
    "NECK": "neck",
    "TORSO": "torso",
    "UNDER": "under",
    "BACK": "back",
    "WRIST": "wrists",
    "FINGER": "fingers",
    "WAIST": "waist",
    "LEGS": "legs",
    "FEET": "feet",
}


def appearance_parts(appearance: Any) -> list[dict[str, str]]:
    """The appearance field split into parts: {label, slot, text}. ``slot`` is '' for non-clothing."""
    gear_mod = _gear()
    out: list[dict[str, str]] = []
    for chunk in re.split(r"\s*;\s*|\n+", str(appearance or "")):
        chunk = chunk.strip(" .,")
        if not chunk:
            continue
        label, text = "", chunk
        match = re.match(r"^([A-Za-z][A-Za-z _-]{1,20}):\s*(.+)$", chunk)
        if match:
            label, text = match.group(1).strip(), match.group(2).strip()
        slot = ""
        if label:
            mapped = gear_mod.normalize_slot(label)
            slot = mapped if mapped in _ZONE_LABELS else ""
        else:
            by_name = gear_mod.slot_for_name(text)
            slot = by_name if by_name in _ZONE_LABELS else ""
        out.append({"label": label, "slot": slot, "text": text})
    return out


def _render_parts(parts: list[dict[str, str]]) -> str:
    return "; ".join(f"{p['label']}: {p['text']}" if p["label"] else p["text"] for p in parts if p["text"])


def _is_unnamed_basic(raw: Any) -> bool:
    if not isinstance(raw, dict):
        return False
    if raw.get("keep") or raw.get("locked_card"):
        return False
    if not str(raw.get("name") or "").strip():
        return True
    if raw.get("engine_default"):
        return True
    return _gear().is_placeholder_basic(raw)


def name_basics_from_appearance(raw_gear: Any, appearance: Any) -> tuple[list[Any], list[str]]:
    """Name each unnamed worn basic after the appearance tag for its zone.

    An unnamed basic is a required card with no name, a legacy placeholder
    ("boots"), or one the page filled with engine defaults (``engine_default``).
    Returns (gear, names given).
    """
    gear_mod = _gear()
    items = list(raw_gear) if isinstance(raw_gear, list) else []
    by_slot: dict[str, str] = {}
    for part in appearance_parts(appearance):
        if part["slot"] in gear_mod.REQUIRED_GEAR_SLOTS and part["slot"] not in by_slot:
            by_slot[part["slot"]] = part["text"][:80]
    named: list[str] = []
    seen_slots: set[str] = set()
    for index, raw in enumerate(items):
        if not isinstance(raw, dict):
            continue
        slot_in = str(raw.get("slot") or "").strip()
        slot = gear_mod.normalize_slot(slot_in) if slot_in else gear_mod.slot_for_name(str(raw.get("name") or ""))
        if slot not in gear_mod.REQUIRED_GEAR_SLOTS or slot in seen_slots:
            continue
        seen_slots.add(slot)
        if slot in by_slot and _is_unnamed_basic(raw):
            items[index] = {**raw, "name": by_slot[slot], "slot": slot, "required": True}
            items[index].pop("engine_default", None)
            named.append(by_slot[slot])
    for slot in gear_mod.REQUIRED_GEAR_SLOTS:
        if slot not in seen_slots and slot in by_slot:
            items.append({"name": by_slot[slot], "slot": slot, "required": True})
            named.append(by_slot[slot])
    return items, named


def _agrees(part_text: str, card_name: str) -> bool:
    a = re.sub(r"[^a-z0-9 ]+", " ", part_text.lower())
    b = re.sub(r"[^a-z0-9 ]+", " ", card_name.lower())
    a, b = " ".join(a.split()), " ".join(b.split())
    return bool(a and b) and (b in a or a in b)


def appearance_from_gear(appearance: Any, gear_items: Iterable[dict[str, Any]] | None) -> tuple[str, list[str]]:
    """Rewrite the appearance clothing tags so they name the worn cards.

    A tag that already names its card ("torso: rust-red wool tunic" for the
    card "wool tunic") is kept; one that names something else is replaced by
    the card. A worn basic with no tag gets one. Non-clothing parts (face,
    expression) stay. Returns (appearance, slots changed).
    """
    worn: dict[str, str] = {}
    for item in gear_items or []:
        if not isinstance(item, dict):
            continue
        slot = str(item.get("slot") or "")
        name = str(item.get("name") or "").strip()
        if slot in _ZONE_LABELS and name and slot not in worn:
            worn[slot] = name
    parts = appearance_parts(appearance)
    changed: list[str] = []
    covered: set[str] = set()
    for part in parts:
        slot = part["slot"]
        if not slot or slot not in worn:
            continue
        if slot in covered:
            # A second tag for a slot that holds one worn item.
            part["text"] = ""
            changed.append(slot)
            continue
        covered.add(slot)
        if not _agrees(part["text"], worn[slot]):
            part["text"] = worn[slot]
            changed.append(slot)
        if not part["label"]:
            part["label"] = _ZONE_LABELS[slot]
    gear_mod = _gear()
    for slot in gear_mod.REQUIRED_GEAR_SLOTS:
        if slot in worn and slot not in covered:
            parts.append({"label": _ZONE_LABELS[slot], "slot": slot, "text": worn[slot]})
            changed.append(slot)
    if not changed:
        return str(appearance or ""), []
    return _render_parts(parts), changed


# ---------------------------------------------------------------------------
# Items the backstory carries
# ---------------------------------------------------------------------------

_CARRY_RE = re.compile(
    r"\b(?:carr(?:y|ies|ied|ying)|clutch(?:es|ed|ing)?|cradl(?:es|ed|ing)|clasp(?:s|ed|ing)?|"
    r"(?:has|had|have|with)\s+(?:only|nothing but|just))\s+"
    r"(?:only\s+|nothing\s+but\s+|just\s+)?(?P<items>[^.;:!?]+)",
    re.I,
)
_DET = r"(?:a|an|the|her|his|their|its|one|two|three|some|a\s+pair\s+of|a\s+few)"
_ITEM_SPLIT_RE = re.compile(rf",?\s+(?:and|plus)\s+(?={_DET}\b)|,\s+(?={_DET}\b)", re.I)
_CLAUSE_CUT_RE = re.compile(
    r"\s+(?:that|which|who|whose|seemingly|as|while|when|because|to|from|for|into|through|across|"
    r"toward|towards|with|after|before|since|until|where)\b",
    re.I,
)
_LEAD_DET_RE = re.compile(rf"^{_DET}\s+", re.I)
_ABSTRACT_HEADS = frozenset(
    {
        "grudge", "secret", "secrets", "memory", "memories", "burden", "weight", "scar", "scars",
        "hope", "hopes", "fear", "fears", "name", "reputation", "knowledge", "skill", "skills",
        "title", "debt", "debts", "guilt", "grief", "dream", "dreams", "curse", "past", "promise",
        "promises", "regret", "regrets", "doubt", "doubts", "wound", "wounds", "legacy", "pride",
        "anger", "trauma", "habit", "habits", "sense", "feeling", "air", "heart", "mind", "soul",
        "story", "stories", "message", "news", "word", "words", "vow", "oath", "talent", "gift",
        "himself", "herself", "themselves", "themself",
    }
)


def backstory_carried_items(backstory: Any, *, limit: int = 4) -> list[str]:
    """Item names the backstory says the character carries ("a small, enchanted lantern" -> "small enchanted lantern")."""
    out: list[str] = []
    seen: set[str] = set()
    for match in _CARRY_RE.finditer(str(backstory or "")):
        chunk = match.group("items")
        cut = _CLAUSE_CUT_RE.search(chunk)
        if cut:
            chunk = chunk[: cut.start()]
        if not re.match(rf"^\s*{_DET}\b", chunk, flags=re.I):
            continue
        for piece in _ITEM_SPLIT_RE.split(chunk):
            piece = _LEAD_DET_RE.sub("", piece.strip())
            # "a small, enchanted lantern" keeps its comma'd adjectives; a long
            # tail after a comma ("a lantern, glowing faintly in the dark") is a clause.
            if len(piece.split()) > 5 and "," in piece:
                piece = piece.split(",", 1)[0]
            piece = re.sub(r"\s*,\s*", " ", piece)
            piece = re.sub(r"[^\w\s'\-]", "", piece)
            piece = re.sub(r"\s+", " ", piece).strip().lower()
            words = piece.split()
            if not words or len(words) > 5:
                continue
            if words[-1] in _ABSTRACT_HEADS or words[0] in _ABSTRACT_HEADS:
                continue
            if piece in seen:
                continue
            seen.add(piece)
            out.append(piece)
            if len(out) >= limit:
                return out
    return out


def _head(name: str) -> str:
    words = re.sub(r"[^a-z\s]", " ", str(name or "").lower()).split()
    return words[-1].rstrip("s") if words else ""


def backstory_gear_items(backstory: Any, existing: Iterable[Any] | None = None) -> list[dict[str, Any]]:
    """Carried cards for backstory items no existing card already covers. No stats: the engine rolls any."""
    heads = {_head(str(item.get("name") if isinstance(item, dict) else item or "")) for item in existing or []}
    heads.discard("")
    cards: list[dict[str, Any]] = []
    for name in backstory_carried_items(backstory):
        head = _head(name)
        if not head or head in heads:
            continue
        heads.add(head)
        cards.append(
            {
                "name": name,
                "slot": "",
                "required": False,
                "keep": False,
                "description": "Named in the backstory: carried on arrival.",
                "stats": {},
                "abilities": [],
                "from_backstory": True,
            }
        )
    return cards
