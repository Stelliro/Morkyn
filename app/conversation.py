"""Who the player is talking to: the active speaker engine.

Playtest #6/#7: the target used to be one "active scene / interacting" list
the model grew with CAST ops and nothing ever trimmed. After turn 5 revealed
a hidden figure, interacting was [Aria, Ashwalker]; turn 6's untagged insult
("if you came to intimidate you came to the wrong place") went to the draft
with both named as "replies to the player", and the draft picked Aria. The
paragraph writer then gave Aria the player's own words.

This module decides the addressee deterministically, before any model call,
and every stage that writes gets the same answer:

1. an explicit @tag (code, @C<name>, or an alias),
2. a present NPC named in the player's own words (not merely talked about),
3. a call to someone unseen ("come out", "whoever is hiding", "show
   yourself") -> nobody present; the people here only listen,
   then a group phrase ("everyone", "you all", "both of you") -> all present,
4. the player's pick on the "Talking to" chip,
5. who the last turn left facing the player: someone just revealed or brought
   in, else whoever spoke last, else the one the player was already talking to,
6. the only person present.

Bare "them" is not a group phrase: turn 6 said "insulting them" of one figure.

State lives in the settings row ``conversation`` (so saves, rewinds and slot
loads carry it), and the old ``active_scene`` row is kept in step: its
``interacting`` list is the current target, so fallback prose, Ask and the
cast panel agree with the chip.
"""

from __future__ import annotations

import json
import re
from typing import Any

SETTING_KEY = "conversation"

# Why the addressee was chosen. Shown to the model and on the chip's tooltip.
RULE_TEXT = {
    "tag": "tagged by the player",
    "name": "named in the player's line",
    "group": "the player addresses everyone present",
    "unseen": "the player calls out to someone unseen or not yet in the scene",
    "called": "named by the player but not here yet",
    "chosen": "picked by the player",
    "revealed": "just revealed or stepped in",
    "last_speaker": "spoke to the player last",
    "partner": "the one the player was talking to",
    "only_present": "the only person here",
    "none": "nobody in particular",
}

_GROUP_RE = re.compile(
    r"\b(?:everyone|everybody|every\s+one\s+of\s+you|all\s+of\s+you|you\s+all|y['’]?all|"
    r"you\s+two|you\s+three|you\s+lot|you\s+guys|you\s+people|you\s+folks|both\s+of\s+you|"
    r"the\s+two\s+of\s+you|each\s+of\s+you|all\s+of\s+them|both\s+of\s+them|them\s+all|"
    r"the\s+(?:whole\s+)?(?:group|crowd|room))\b",
    re.IGNORECASE,
)
# A call to someone not in the scene yet. Playtest turn 5: "come out now",
# commanding whatever is hiding to reveal itself, went to Aria as "the one the
# player was talking to", which tells the draft only Aria may answer -- the one
# person the line was not for.
_UNSEEN_RE = re.compile(
    r"\b(?:who|what)(?:ever|soever)?\s*(?:is|['’]s|are|goes)\s+"
    r"(?:there|out\s+there|hiding|lurking|watching|following|in\s+the\s+(?:shadows?|dark(?:ness)?))\b|"
    r"\b(?:show|reveal)\s+(?:yourself|yourselves|itself|themselves|your\s+face)\b|"
    r"\bcome\s+out\b|\bstep\s+(?:out|forward|into\s+the\s+light)\b",
    re.IGNORECASE,
)
_QUOTE_RE = re.compile(r'"([^"]*)"|“([^”]*)”')
_TAG_RE = re.compile(r"@([A-Za-z0-9_'’-]+)")
# Words right before a name that make the name the one being spoken to.
_ADDRESS_CUE_RE = re.compile(
    r"(?:\bto|\bask(?:s|ing)?|\btell(?:s|ing)?|\bgreet(?:s|ing)?|\baddress(?:es|ing)?|\bat|\btowards?|"
    r"\bwith|\bturn(?:s|ing)?\s+to|\bcall(?:s|ing)?(?:\s+out\s+to)?|\banswer(?:s|ing)?|\brepl(?:y|ies|ying)\s+to|"
    r"\binsult(?:s|ing)?|\bthank(?:s|ing)?|\bwarn(?:s|ing)?|\bnudg(?:e|es|ing)|\bbeckon(?:s|ing)?|"
    r"\bquestion(?:s|ing)?|\bconfront(?:s|ing)?|\bhail(?:s|ing)?|\bmock(?:s|ing)?|\bthreaten(?:s|ing)?|"
    r"\bplead(?:s|ing)?\s+with|\bpromise(?:s)?|\bassure(?:s)?|\bcomfort(?:s)?|\bteas(?:e|es|ing))"
    r"\s+(?:the\s+)?$",
    re.IGNORECASE,
)
# Words right before a name that make it the topic, not the listener.
_TOPIC_CUE_RE = re.compile(
    r"(?:\babout|\bof|\bregarding|\bconcerning|\bfor|\bwhere(?:['’]s|\s+is)|\bwhether|\bmention(?:s|ing)?|"
    r"\bfind|\bsearch\s+for|\blook(?:s|ing)?\s+for)\s+(?:the\s+)?$",
    re.IGNORECASE,
)
_CONJUNCTION_RE = re.compile(r"^\s*(?:,|and|&|,\s*and)\s*$", re.IGNORECASE)
# Words right before an absent person's name that call to them: raising the
# voice or speaking straight at them. Spatial words ("to", "at", "towards",
# "with") are not here: walking to someone, or following them, is not a call.
_CALL_CUE_RE = re.compile(
    r"(?:\bcall(?:s|ed|ing)?(?:\s+out)?(?:\s+(?:to|for))?|\bshout(?:s|ed|ing)?(?:\s+(?:to|for|at))?|"
    r"\byell(?:s|ed|ing)?(?:\s+(?:to|for|at))?|\bholler(?:s|ed|ing)?(?:\s+(?:to|for|at))?|"
    r"\bcr(?:y|ies|ied)\s+out\s+(?:to|for)|\bwhistle(?:s|d)?\s+(?:to|for)|\bwave(?:s|d)?\s+(?:to|at)|"
    r"\bhail(?:s|ed|ing)?|\bbeckon(?:s|ed|ing)?|\bsummon(?:s|ed|ing)?|"
    r"\b(?:say|says|said|speak|speaks|talk|talks|whisper|whispers|mutter|mutters|reply|replies|turn|turns)\s+to|"
    r"\bask(?:s|ed)?|\btell(?:s)?|\bgreet(?:s|ed)?|\bthank(?:s|ed)?|\bwarn(?:s|ed)?|\banswer(?:s|ed)?)"
    r"\s+(?:the\s+)?$",
    re.IGNORECASE,
)
# First names that are ordinary words; matched only when the player capitalised them.
_COMMON_WORD_NAMES = {
    "will", "mark", "rose", "grace", "hope", "faith", "may", "june", "bill", "jack", "sue", "frank",
    "dawn", "rob", "pat", "art", "gene", "ray", "wade", "hunter", "reed", "rich", "sky", "summer",
    "the", "and", "for", "are", "was", "how", "your", "you", "what", "who", "when", "where", "why",
    "can", "could", "tell", "ask", "have", "has", "had", "open", "day", "this", "that", "with", "from",
}
_SECOND_PERSON_RE = re.compile(
    r"\b(?:you|your|yours|yourself|reply|replies|answer|answers|respond|responds|retort|retorts)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Roster: who could be spoken to right now
# ---------------------------------------------------------------------------


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text or "").lower().replace("’", "'")).strip("_")


def _current_location(context: dict[str, Any]) -> dict[str, Any]:
    current = context.get("current_location")
    return current if isinstance(current, dict) else {}


def roster(context: dict[str, Any]) -> list[dict[str, Any]]:
    """NPCs at the player's location, plus party members wherever they are."""
    current = _current_location(context)
    cid = current.get("id")
    ccode = str(current.get("code") or "")
    party_ids = {
        int(member.get("npc_id") or 0)
        for member in context.get("party") or []
        if isinstance(member, dict) and member.get("npc_id")
    }
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for location in context.get("locations") or []:
        if not isinstance(location, dict):
            continue
        here = (cid is not None and location.get("id") == cid) or (ccode and str(location.get("code") or "") == ccode)
        for npc in location.get("npcs") or []:
            if not isinstance(npc, dict):
                continue
            code = str(npc.get("code") or "").strip().upper()
            name = str(npc.get("name") or "").strip()
            if not code or not name or code in seen:
                continue
            if not here and int(npc.get("id") or 0) not in party_ids:
                continue
            seen.add(code)
            rows.append({"code": code, "name": name, "aliases": []})
    by_code = {row["code"]: row for row in rows}
    for alias in context.get("aliases") or []:
        if not isinstance(alias, dict) or str(alias.get("entity_type") or "") != "npc":
            continue
        row = by_code.get(str(alias.get("entity_code") or "").upper())
        word = str(alias.get("alias") or "").strip()
        if row is not None and word:
            row["aliases"].append(word)
    return rows


def known_elsewhere(context: dict[str, Any], here: set[str]) -> list[dict[str, Any]]:
    """Known NPCs who are not at the player's location (roster shape)."""
    rows: list[dict[str, Any]] = []
    seen = set(here)
    for location in context.get("locations") or []:
        if not isinstance(location, dict):
            continue
        for npc in location.get("npcs") or []:
            if not isinstance(npc, dict):
                continue
            code = str(npc.get("code") or "").strip().upper()
            name = str(npc.get("name") or "").strip()
            if code and name and code not in seen:
                seen.add(code)
                rows.append({"code": code, "name": name, "aliases": []})
    return rows


def _names(rows: list[dict[str, Any]]) -> dict[str, str]:
    return {row["code"]: row["name"] for row in rows}


def _name_forms(row: dict[str, Any]) -> list[str]:
    """Full name, first name, aliases; longest first so a full name wins over its first word."""
    forms = [row["name"]]
    first = row["name"].split()[0] if row["name"].split() else ""
    if first and first != row["name"] and len(first) >= 3:
        forms.append(first)
    forms.extend(row.get("aliases") or [])
    out: list[str] = []
    for form in sorted(forms, key=len, reverse=True):
        if form and form.lower() not in {f.lower() for f in out}:
            out.append(form)
    return out


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


def _codes(value: Any) -> list[str]:
    out: list[str] = []
    for code in value or []:
        token = str(code or "").strip().upper()
        if token and token not in out:
            out.append(token)
    return out


def _scene(settings: dict[str, Any]) -> dict[str, Any]:
    scene = settings.get("active_scene") if isinstance(settings, dict) else None
    return scene if isinstance(scene, dict) else {}


def load_state(settings: dict[str, Any] | None) -> dict[str, Any]:
    """The stored conversation, or one derived from the old active_scene row."""
    settings = settings if isinstance(settings, dict) else {}
    raw = settings.get(SETTING_KEY)
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = None
    if isinstance(raw, dict):
        state = dict(raw)
        for key in ("target", "present", "revealed", "partner", "here"):
            state[key] = _codes(state.get(key))
        state["last_speaker"] = str(state.get("last_speaker") or "").upper()
        return state
    # A game saved before this module: the newest interacting code is the one
    # the model brought in last (CAST appends), which is who the player faces.
    scene = _scene(settings)
    interacting = _codes(scene.get("interacting"))
    return {
        "target": interacting[-1:],
        "present": _codes(list(scene.get("present") or []) + interacting),
        "why": "partner" if interacting else "none",
        "revealed": [],
        "partner": interacting[-1:],
        "last_speaker": "",
        "group": False,
        "chosen": False,
        "location": "",
        "here": [],
    }


def present_codes(context: dict[str, Any], state: dict[str, Any] | None = None) -> list[str]:
    """Scene members standing here. The roster is where they could be; the scene is who is in it."""
    rows = roster(context)
    here = {row["code"] for row in rows}
    settings = context.get("settings") if isinstance(context.get("settings"), dict) else {}
    scene = _scene(settings)
    state = state if state is not None else load_state(settings)
    out: list[str] = []
    for code in _codes(list(scene.get("present") or []) + list(scene.get("interacting") or []) + list(state.get("target") or [])):
        if code in here and code not in out:
            out.append(code)
    return out


# ---------------------------------------------------------------------------
# Resolving one line
# ---------------------------------------------------------------------------


def own_text(player_input: str) -> str:
    """The player's typed line, without engine notes or internal markers."""
    text = str(player_input or "")
    if text.startswith("__"):
        return ""
    return re.split(r"\n\s*\n", text, maxsplit=1)[0].strip()


def player_name_forms(names: Any) -> list[str]:
    """The player's name as people could say it: full, first and last, longest first."""
    forms: list[str] = []
    for name in names or ():
        text = re.sub(r"\s+", " ", str(name or "")).strip()
        if not text:
            continue
        for form in [text, *text.split()]:
            if len(form) >= 3 and form.lower() not in {f.lower() for f in forms}:
                forms.append(form)
    return sorted(forms, key=len, reverse=True)


def introduces_self(player_input: str, names: Any) -> bool:
    """The player's own line gives their name: "I'm Bartholomew", "my name is
    Hurst", "call me Bart..." (playtest #78)."""
    text = own_text(player_input)
    forms = player_name_forms(names)
    if not text or not forms:
        return False
    alternatives = "|".join(re.escape(form) for form in forms)
    return bool(
        re.search(
            r"\b(?:my\s+name(?:'s|\s+is)|name's|i\s+am|i'm|im|call\s+me|they\s+call\s+me|known\s+as)\s+"
            r"(?:called\s+)?(?:" + alternatives + r")\b(?!['’]s)",
            text,
            re.IGNORECASE,
        )
    )


# Out-of-character text (playtest #79): what the player says to the game, not
# in the story. Bracketed notes always; a clause only on a strong meta marker,
# never on a bare "game" (hunted animals) or "bug" (an insect).
_OOC_BRACKET_RE = re.compile(
    r"\(\(.*?\)\)|\((?:\s*ooc\b|\s*out\s+of\s+character\b)[^)]*\)|(?<!\[)\[(?!\[)[^\[\]]*\](?!\])|\booc\s*:.*$",
    re.IGNORECASE | re.DOTALL,
)
# Words a setting can use in the fiction stay out: a starship's "the AI", an
# "engine error", a "server", a terminal that "glitches".
_OOC_META_RE = re.compile(
    r"\b(?:(?:game|app|ui|save)\s+(?:bug|glitch|error|issue|crash)(?:s|ed|es)?|"
    r"bug(?:ged|gy)?\s+(?:in|with)\s+the\s+(?:game|app|ui)|"
    r"out\s+of\s+character|ooc\b|"
    r"the\s+(?:llm|narrator|dm|gm|game\s+master)\b|"
    r"(?:reload|refresh|restart)\s+(?:the\s+)?(?:game|page|app|browser)|"
    r"(?:in|the)\s+(?:game'?s?\s+)?(?:ui|settings\s+menu)\b|playtest(?:ing)?\b)",
    re.IGNORECASE,
)


def split_out_of_character(text: str) -> tuple[str, str]:
    """
    (in_fiction, ooc) for the player's typed line (playtest #79).

    T9 "its all good, i have no gold, i cant leave the city due to a game bug,
    so i will not be buying anything" was narrated in-world ("You explain that
    you ... cannot leave the city due to a game bug") and its "leave the city"
    walked the player out of the forge. Bracketed notes ("(ooc: ...)", "((...))",
    "[...]", but not "[[L1]]" codes) and clauses with a clear meta marker come
    out; what is left is what the player does in the story. Engine notes after
    a blank line ride with the in-fiction part untouched.
    """
    raw = str(text or "")
    if raw.startswith("__"):
        return raw, ""
    head, sep, tail = raw.partition("\n\n")
    removed: list[str] = []

    def _take(match: re.Match[str]) -> str:
        removed.append(match.group(0).strip(" ()[]"))
        return " "

    working = _OOC_BRACKET_RE.sub(_take, head)
    if _OOC_META_RE.search(working):
        # Clause by clause: a meta clause goes, the rest of the line stays.
        pieces = re.split(r"(?<=[.!?;,])\s+|\s+(?=\b(?:but|so|and\s+so)\b)", working)
        kept: list[str] = []
        for piece in pieces:
            if _OOC_META_RE.search(piece) and not re.search(r'["“”]', piece):
                removed.append(piece.strip(" ,;"))
            else:
                kept.append(piece)
        working = " ".join(kept)
    if not removed:
        return raw, ""
    clean = re.sub(r"\s+([,.;!?])", r"\1", re.sub(r"\s+", " ", working)).strip(" ,;")
    clean = re.sub(r"^(?:so|but|and)\b[\s,]*", "", clean, flags=re.IGNORECASE).strip()
    ooc = "; ".join(r for r in removed if r)
    if not re.search(r"[A-Za-z]{2,}", clean):
        clean = ""
    return (clean + (sep + tail if sep and clean else "")), ooc


def _quote_ranges(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _QUOTE_RE.finditer(text)]


def _inside(pos: int, ranges: list[tuple[int, int]]) -> tuple[int, int] | None:
    for start, end in ranges:
        if start < pos < end:
            return (start, end)
    return None


def _vocative(text: str, start: int, end: int, quote: tuple[int, int]) -> bool:
    """'"Aria, wait"' or '"wait, Aria"': the name is who the line is said to."""
    before = text[quote[0] + 1 : start].strip()
    after = text[end : quote[1] - 1].strip()
    if not before and after.startswith((",", "!", "?", ".")):
        return True
    if before.endswith(",") and (not after or after[0] in ",.!?"):
        return True
    return False


def _mentions(text: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every tag and name in the player's line, with where it sits and how it is used."""
    found: list[dict[str, Any]] = []
    quotes = _quote_ranges(text)
    by_code = {row["code"]: row for row in rows}
    alias_map = {a.lower(): row["code"] for row in rows for a in row.get("aliases") or []}
    slugs: dict[str, list[str]] = {}
    for row in rows:
        for form in {_slug(row["name"]), _slug(row["name"].split()[0])}:
            if form:
                slugs.setdefault(form, []).append(row["code"])

    taken: list[tuple[int, int]] = []
    for match in _TAG_RE.finditer(text):
        token = match.group(1).rstrip("'’-")
        # "@Caria's lantern": the tag is the name; the 's is left for the topic check.
        token = re.sub(r"['’]s$", "", token)
        end = match.start() + 1 + len(token)
        code = ""
        if token.upper() in by_code:
            code = token.upper()
        elif token.lower() in alias_map:
            code = alias_map[token.lower()]
        elif len(token) > 1 and token[0] in "Cc":
            frag = _slug(token[1:])
            exact = slugs.get(frag) or []
            if len(set(exact)) == 1:
                code = exact[0]
            elif len(frag) >= 4:
                starts = {c for slug, codes in slugs.items() if slug.startswith(frag) for c in codes}
                if len(starts) == 1:
                    code = next(iter(starts))
        if code:
            found.append({"code": code, "start": match.start(), "end": end, "tag": True})
            taken.append((match.start(), end))

    for row in rows:
        for form in _name_forms(row):
            pattern = re.compile(r"(?<![\w@])" + re.escape(form) + r"(?![\w])", re.IGNORECASE)
            for match in pattern.finditer(text):
                if any(s <= match.start() < e for s, e in taken):
                    continue
                word = match.group(0)
                if form.lower() in _COMMON_WORD_NAMES and not word[:1].isupper():
                    continue
                found.append({"code": row["code"], "start": match.start(), "end": match.end(), "tag": False})
                taken.append((match.start(), match.end()))

    found.sort(key=lambda item: item["start"])
    previous: dict[str, Any] | None = None
    for item in found:
        quote = _inside(item["start"], quotes)
        before = text[: item["start"]]
        possessive = bool(re.match(r"['’]s\b", text[item["end"] :]))
        if quote is not None:
            item["use"] = "address" if _vocative(text, item["start"], item["end"], quote) else "topic"
        elif possessive or _TOPIC_CUE_RE.search(before):
            item["use"] = "topic"
        elif _ADDRESS_CUE_RE.search(before):
            item["use"] = "address"
        elif (
            previous is not None
            and previous.get("use") == "address"
            and _CONJUNCTION_RE.match(text[previous["end"] : item["start"]])
        ):
            item["use"] = "address"
        else:
            item["use"] = "plain"
        previous = item
    return found


def _pick(mentions: list[dict[str, Any]]) -> list[str]:
    """Addressed codes from a set of mentions, or [] when they are all topics."""
    strong = [m["code"] for m in mentions if m["use"] == "address"]
    if strong:
        return _codes(strong)
    plain = [m["code"] for m in mentions if m["use"] == "plain"]
    return _codes(plain)


def _called_codes(text: str, mentions: list[dict[str, Any]]) -> list[str]:
    """Codes of absent people the line is said or called to.

    Playtest #31 review: any mention used to count ("I give up on Carlos",
    "I follow Carlos Barnes", "the Spindle that Marisol mentioned"), so the
    draft was told they were being called and the prose could pull them in.
    Only an address form counts: a vocative ("Marisol, ..." / "... , Marisol!",
    quoted or not) or a calling or speaking verb right before the name."""
    codes: list[str] = []
    quotes = _quote_ranges(text)
    for m in mentions:
        start, end = m["start"], m["end"]
        if m.get("tag"):
            codes.append(m["code"])
            continue
        if _inside(start, quotes) is not None:
            if m.get("use") == "address":
                codes.append(m["code"])
            continue
        before = text[:start]
        after = text[end:]
        lead = before.rstrip()
        if (not lead or lead[-1] in ".!?:;") and re.match(r"\s*[,!?]", after):
            codes.append(m["code"])  # "Marisol, I woke up ..." / "Carlos! Wait."
            continue
        if lead.endswith(",") and re.match(r"\s*(?:[.!?]|$)", after):
            codes.append(m["code"])  # "Wait up, Carlos!"
            continue
        if _CALL_CUE_RE.search(before) and not re.match(r"['’]s\b", after):
            codes.append(m["code"])
    return _codes(codes)


def is_speech(player_input: str) -> bool:
    text = own_text(player_input)
    if not text:
        return False
    if _QUOTE_RE.search(text):
        return True
    return bool(
        re.match(
            r"^\s*(?:i\s+)?(?:say|says|said|ask|asks|tell|tells|reply|replies|answer|answers|shout|shouts|"
            r"yell|yells|whisper|whispers|call|calls|mutter|mutters|greet|greets)\b",
            text,
            re.IGNORECASE,
        )
    )


def venue_entry_kind(player_input: str) -> str:
    """The kind of venue a line walks the player into ("general_store"), or "".

    Playtest #33 (live, four shop-entry turns): "I go into the first shop I
    can find to see what they sell" carried the previous partner over the
    doorway, so the draft was told the companion was the only one who answers
    and cast them as the shopkeeper.
    """
    text = own_text(player_input)
    if not text:
        return ""
    try:
        from app import venues
        from app.world import venue_move_intent
    except Exception:
        return ""
    if venue_move_intent(text) != "enter":
        return ""
    return str(venues.venue_kind_from_name(text.lower()) or "")


def resolve(context: dict[str, Any], player_input: str, state: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Who this line is said to. Deterministic; no model call.

    Returns addressed codes, the rule that chose them, who else is present
    (listening), and whether the line is speech. ``names`` maps codes to names.
    """
    settings = context.get("settings") if isinstance(context.get("settings"), dict) else {}
    state = state if state is not None else load_state(settings)
    rows = roster(context)
    here = {row["code"] for row in rows}
    present = present_codes(context, state)
    text = own_text(player_input)
    out: dict[str, Any] = {
        "addressed": [],
        "rule": "none",
        "group": False,
        "present": present,
        "listening": [],
        "speech": is_speech(player_input),
        "second_person": bool(_SECOND_PERSON_RE.search(text)),
        "names": _names(rows),
    }

    def done(codes: list[str], rule: str, group: bool = False) -> dict[str, Any]:
        addressed = [c for c in _codes(codes) if c in here]
        out["addressed"] = addressed
        out["rule"] = rule if addressed else "none"
        out["group"] = bool(group and addressed)
        for code in addressed:
            if code not in out["present"]:
                out["present"].append(code)
        out["listening"] = [c for c in out["present"] if c not in addressed]
        return out

    mentions = _mentions(text, rows) if text else []
    tagged = _pick([m for m in mentions if m["tag"]])
    if tagged:
        return done(tagged, "tag")
    named = _pick([m for m in mentions if not m["tag"]])
    if named:
        return done(named, "name")
    # Playtest #31 (live): "Marisol, I woke up in the snow ..." named a known
    # person who was stored somewhere else. The line went to nobody, the writer
    # was told nothing, the prose walked her in anyway and last_speaker won.
    # A named person who is not here is called: the writer is told who, and
    # apply_turn brings her here when the prose shows her (bring_called_here).
    elsewhere = known_elsewhere(context, here) if text else []
    called = _called_codes(text, _mentions(text, elsewhere)) if elsewhere else []
    if called:
        done([], "none")
        out["rule"] = "called"
        out["called"] = called
        out["names"] = {**out["names"], **{row["code"]: row["name"] for row in elsewhere if row["code"] in called}}
        return out
    if text and _UNSEEN_RE.search(text):
        done([], "none")
        out["rule"] = "unseen"
        return out
    if text and _GROUP_RE.search(text):
        group = present or [row["code"] for row in rows]
        if group:
            return done(group, "group", group=len(group) > 1)
    # "You, come into the shop with me" is still said to someone.
    venue_kind = venue_entry_kind(player_input) if text and not out["second_person"] else ""
    if venue_kind:
        try:
            from app.scene_thread import invites_along

            if invites_along(player_input):
                venue_kind = ""
        except Exception:
            pass
    if venue_kind:
        # Through a shop door the line is for whoever works there; the people
        # with the player come in as visitors and listen (playtest #33).
        done([], "none")
        out["rule"] = "venue"
        out["venue_kind"] = venue_kind
        return out
    target = [c for c in state.get("target") or [] if c in here]
    if target:
        if state.get("chosen"):
            return done(target, "chosen", group=bool(state.get("group")))
        why = str(state.get("why") or "partner")
        if why not in RULE_TEXT or why in {"tag", "name", "chosen", "none", "only_present"}:
            why = "partner"
        return done(target, why, group=bool(state.get("group")))
    if len(present) == 1:
        return done(present, "only_present")
    # Playtest #73 (live, T10): the only person on record at the street was
    # Bertram, minted the turn before from a line Juliana spoke at the forge.
    # The player had never seen him, yet "only_present" made him the one who
    # answers. The lone row counts only once the prose has shown that person.
    if not present and len(rows) == 1 and _shown_to_player(context, state, rows[0]):
        return done([rows[0]["code"]], "only_present")
    return done([], "none")


def _last_narration(context: dict[str, Any]) -> str:
    text = str(context.get("last_narration") or "")
    if text.strip():
        return text
    for row in context.get("history") or []:
        if isinstance(row, dict) and str(row.get("kind") or "") == "narration":
            return str(row.get("content") or "")
    return ""


def _shown_to_player(context: dict[str, Any], state: dict[str, Any], row: dict[str, Any]) -> bool:
    """The player has met this person here: the last scene named them, or the
    conversation at this same place already had them in it."""
    code = row["code"]
    location = str(_current_location(context).get("code") or "")
    if location and location == str(state.get("location") or ""):
        seen = _codes(
            list(state.get("present") or [])
            + list(state.get("target") or [])
            + list(state.get("revealed") or [])
            + list(state.get("partner") or [])
            + [state.get("last_speaker") or ""]
        )
        if code in seen:
            return True
    return any(hit_code == code for _pos, hit_code in _names_in(_last_narration(context), [row]))


# ---------------------------------------------------------------------------
# What each writing stage is told
# ---------------------------------------------------------------------------


def _label(code: str, names: dict[str, str]) -> str:
    name = names.get(code)
    return f"{name} [[{code}]]" if name else code


def _venue_label(kind: str) -> str:
    try:
        from app import venues

        label = venues.kind_label(kind) if kind else ""
    except Exception:
        label = ""
    label = label or "the place"
    return label if label.startswith("the ") else f"the {label}"


def model_note(resolution: dict[str, Any] | None) -> str:
    """One line for the draft's "Resolved player references" footer."""
    if not isinstance(resolution, dict):
        return ""
    names = resolution.get("names") or {}
    addressed = list(resolution.get("addressed") or [])
    listening = list(resolution.get("listening") or [])
    called = list(resolution.get("called") or []) if not addressed else []
    if not addressed and not listening and not called and resolution.get("rule") != "venue":
        return ""
    if called:
        who = ", ".join(_label(c, names) for c in called)
        line = (
            f"Conversation (engine decided) - the player calls to {who}, who is not at this location; "
            f"{who} may come over and answer if the scene allows it, and nobody present answers for them."
        )
    elif not addressed and resolution.get("rule") == "unseen":
        line = (
            "Conversation (engine decided) - the player calls out to someone unseen or not yet in the scene; "
            "whoever was called may answer, and nobody present answers for them."
        )
    elif not addressed and resolution.get("rule") == "venue":
        place = _venue_label(str(resolution.get("venue_kind") or ""))
        line = (
            f"Conversation (engine decided) - the player goes into {place} to deal with whoever works there. "
            "Someone who keeps or works in that place answers the player; anyone who came in with the player is "
            "a visitor there and does not serve, sell or speak for the place."
        )
    elif addressed:
        who = ", ".join(_label(c, names) for c in addressed)
        why = RULE_TEXT.get(str(resolution.get("rule") or ""), "")
        line = f"Conversation (engine decided) - the player is talking to {who}" + (f" ({why})" if why else "") + "."
        if resolution.get("group"):
            line += " Any of them may answer."
        else:
            line += f" Only {who} answers the player."
    else:
        line = "Conversation (engine decided) - the player is not talking to anyone in particular; nobody has to answer."
    if listening:
        line += " Also present, listening (may react, does not answer for them): " + ", ".join(
            _label(c, names) for c in listening
        ) + "."
    if resolution.get("speech"):
        line += " The player's quoted words are the player's own; nobody else says them."
    return line


def world_view(resolution: dict[str, Any] | None) -> dict[str, Any] | None:
    """Structured form for world_state.conversation (draft and verify passes)."""
    if not isinstance(resolution, dict):
        return None
    names = resolution.get("names") or {}
    addressed = list(resolution.get("addressed") or [])
    listening = list(resolution.get("listening") or [])
    called = list(resolution.get("called") or []) if not addressed else []
    if not addressed and not listening and not called:
        return None
    unseen = not addressed and resolution.get("rule") in {"unseen", "called"}
    venue = not addressed and resolution.get("rule") == "venue"
    view: dict[str, Any] = {
        "talking_to": [{"name": names.get(c, c), "code": c} for c in addressed],
        "answers": (
            "whoever the player called out to, not the listeners"
            if unseen
            else "whoever works in the place the player enters, not the listeners"
            if venue
            else "any of talking_to" if resolution.get("group") else "talking_to only"
        ),
        "why": RULE_TEXT.get(str(resolution.get("rule") or ""), ""),
    }
    if called:
        view["called"] = [{"name": names.get(c, c), "code": c, "here": False} for c in called]
    if listening:
        view["listening"] = [{"name": names.get(c, c), "code": c} for c in listening]
    return view


def writer_view(resolution: dict[str, Any] | None) -> dict[str, Any] | None:
    """What the paragraph writer and the consolidator get: names, not just codes."""
    if not isinstance(resolution, dict):
        return None
    names = resolution.get("names") or {}
    addressed = list(resolution.get("addressed") or [])
    listening = list(resolution.get("listening") or [])
    called = list(resolution.get("called") or []) if not addressed else []
    if not addressed and not listening and not called:
        return None
    unseen = not addressed and resolution.get("rule") == "unseen"
    venue = not addressed and resolution.get("rule") == "venue"
    view: dict[str, Any] = {
        "player_talks_to": [_label(c, names) for c in addressed]
        or [f"{_label(c, names)} (called; not here yet)" for c in called]
        or (["someone unseen or not yet in the scene"] if unseen else [])
        or (["whoever works in the place the player enters"] if venue else ["nobody in particular"]),
        "who_answers": [_label(c, names) for c in addressed] if addressed else [],
    }
    if listening:
        view["listening_only"] = [_label(c, names) for c in listening]
    return view


# ---------------------------------------------------------------------------
# After the turn: who faces the player next
# ---------------------------------------------------------------------------


def _names_in(text: str, rows: list[dict[str, Any]]) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    taken: list[tuple[int, int]] = []
    for row in rows:
        for form in _name_forms(row):
            for match in re.finditer(r"(?<!\w)" + re.escape(form) + r"(?!\w)", text):
                if any(s <= match.start() < e for s, e in taken):
                    continue
                hits.append((match.start(), row["code"]))
                taken.append((match.start(), match.end()))
        for match in re.finditer(r"\[\[\s*" + re.escape(row["code"]) + r"\s*\]\]", text):
            hits.append((match.start(), row["code"]))
    hits.sort()
    return hits


def spoken_lines(narration: str, rows: list[dict[str, Any]], player_input: str = "") -> list[dict[str, str]]:
    """
    Every line someone other than the player speaks in the prose, in order:
    {code, line, unit}. ``code`` is "" when no known person can be named for it.

    A spoken line goes to the first name outside its quotes; with only a
    pronoun ("she asks") it goes to the last person named before it. The
    player's own lines ("you say", or the player's typed words) are skipped.
    """
    from app.narration_pipeline import (
        _PLAYER_SPEECH_VERB_RE,
        _is_player_line,
        player_quotes,
        quoted_spans,
        speech_units,
    )

    quotes = player_quotes(player_input)
    flat = re.sub(r"\s+", " ", str(narration or "")).strip()
    out: list[dict[str, str]] = []
    last_named = ""
    for unit in speech_units(flat):
        outside = _QUOTE_RE.sub(" ", unit)
        named = [code for _pos, code in _names_in(outside, rows)]
        spans = quoted_spans(unit)
        if spans and not all(_is_player_line(s, quotes) for s in spans) and not _PLAYER_SPEECH_VERB_RE.search(outside):
            out.append({"code": named[0] if named else last_named, "line": " ".join(spans), "unit": unit})
        if named:
            last_named = named[-1]
    return out


def speakers_in(narration: str, rows: list[dict[str, Any]], player_input: str = "") -> list[str]:
    """NPC codes in the order they speak in the final prose (see spoken_lines)."""
    return [entry["code"] for entry in spoken_lines(narration, rows, player_input) if entry["code"]]


def next_state(
    previous: dict[str, Any],
    *,
    context: dict[str, Any],
    resolution: dict[str, Any] | None,
    scene_before: dict[str, Any],
    scene_after: dict[str, Any],
    scene_cast: Any,
    narration: str,
    player_input: str,
    turn: int,
) -> dict[str, Any]:
    """
    The conversation after a turn. Pure: the caller loads and saves.

    Target for the next line, in order: someone the turn revealed or brought
    in to face the player; the player's addressee when they answered; whoever
    spoke last; the player's addressee; the previous target.
    """
    rows = roster(context)
    here = [row["code"] for row in rows]
    location = str(_current_location(context).get("code") or "")
    same_place = bool(location) and location == str(previous.get("location") or "")

    before = set(_codes(list(scene_before.get("present") or []) + list(scene_before.get("interacting") or [])))
    cast = scene_cast if isinstance(scene_cast, dict) else {}
    cast_interacting = [c for c in _codes(cast.get("interacting")) if c in here]
    cast_present = [c for c in _codes(cast.get("present")) if c in here]
    speakers = [c for c in speakers_in(narration, rows, player_input) if c in here]
    named_in_prose = {code for _pos, code in _names_in(str(narration or ""), rows)}

    revealed: list[str] = []
    # CAST interacting is the draft saying "this one now faces the player".
    for code in cast_interacting:
        if code not in before and code not in revealed:
            revealed.append(code)
    for code in cast_present:
        if code not in before and code not in revealed and (code in speakers or code in named_in_prose):
            revealed.append(code)
    if same_place:
        known_here = set(previous.get("here") or [])
        for code in speakers:
            if code not in known_here and code not in before and code not in revealed:
                revealed.append(code)
    # Someone the player called by name who the prose brought here (playtest #31).
    for code in _codes((resolution or {}).get("called")):
        if code in here and (code in named_in_prose or code in speakers):
            if code in revealed:
                revealed.remove(code)
            revealed.append(code)

    addressed = [c for c in _codes((resolution or {}).get("addressed")) if c in here]
    group = bool((resolution or {}).get("group"))
    last_speaker = speakers[-1] if speakers else ""
    if revealed:
        target, why, keep_group = [revealed[-1]], "revealed", False
    elif addressed and not group and any(c in speakers for c in addressed):
        target, why, keep_group = addressed, "partner", False
    elif last_speaker:
        target, why, keep_group = [last_speaker], "last_speaker", False
    elif addressed:
        target, why, keep_group = addressed, "partner", group
    else:
        target = [c for c in previous.get("target") or [] if c in here]
        why = str(previous.get("why") or "partner") if target else "none"
        keep_group = bool(previous.get("group")) and len(target) > 1

    present: list[str] = []
    for code in _codes(
        list(scene_after.get("present") or [])
        + list(scene_after.get("interacting") or [])
        + addressed
        + revealed
        + target
    ):
        if code in here and code not in present:
            present.append(code)

    return {
        "version": 1,
        "turn": int(turn or 0),
        "location": location,
        "here": here,
        "present": present,
        "target": target,
        "group": keep_group,
        "why": why,
        "revealed": revealed,
        "last_speaker": last_speaker,
        "partner": addressed or [c for c in previous.get("partner") or [] if c in here],
        "chosen": False,
    }


def synced_scene(scene: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """active_scene rewritten to agree with the conversation: interacting is the target."""
    keywords = [str(w).lower() for w in scene.get("keywords") or [] if str(w).strip()]
    present = _codes(list(state.get("present") or []) + list(state.get("target") or []))
    return {"present": present[:24], "interacting": list(state.get("target") or [])[:8], "keywords": keywords[:24]}


# ---------------------------------------------------------------------------
# Database glue (the caller owns the connection and the transaction)
# ---------------------------------------------------------------------------


def _read_setting(conn, key: str) -> Any:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if not row:
        return None
    value = row[0]
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value


def _write_setting(conn, key: str, value: Any) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, json.dumps(value)),
    )


def context_from_conn(conn) -> dict[str, Any]:
    """The slice of state the roster needs, read inside the turn's own transaction."""
    row = conn.execute(
        "SELECT l.id, l.code, l.name FROM player p LEFT JOIN locations l ON l.id = p.current_location_id WHERE p.id = 1"
    ).fetchone()
    current = {"id": row[0], "code": row[1], "name": row[2]} if row and row[0] is not None else {}
    by_location: dict[Any, dict[str, Any]] = {}
    for npc in conn.execute("SELECT id, code, name, location_id FROM npcs ORDER BY id").fetchall():
        loc = by_location.setdefault(npc[3], {"id": npc[3], "npcs": []})
        loc["npcs"].append({"id": npc[0], "code": npc[1], "name": npc[2]})
    if current and current["id"] in by_location:
        by_location[current["id"]]["code"] = current.get("code")
    try:
        party = [{"npc_id": r[0]} for r in conn.execute("SELECT npc_id FROM party_members").fetchall()]
    except Exception:
        party = []
    try:
        aliases = [
            {"alias": r[0], "entity_type": r[1], "entity_code": r[2]}
            for r in conn.execute("SELECT alias, entity_type, entity_code FROM aliases").fetchall()
        ]
    except Exception:
        aliases = []
    return {
        "current_location": current,
        "locations": list(by_location.values()),
        "party": party,
        "aliases": aliases,
        "settings": {
            SETTING_KEY: _read_setting(conn, SETTING_KEY),
            "active_scene": read_scene(conn),
        },
    }


# A sentence that shows a named person here: stepping in, standing, speaking.
_SHOWN_HERE_RE = re.compile(
    r"\b(?:steps?|stepped|stands?|stood|comes?|came|walks?|walked|appears?|appeared|arrives?|arrived|"
    r"emerges?|emerged|turns?|turned|looks?\s+up|watches|watched|nods?|nodded|leans?|leaned|waits?|waited|"
    r"approaches|approached|hurries|hurried|says?|said|asks?|asked|answers?|answered|replies|replied|"
    r"beside\s+you|in\s+front\s+of\s+you|before\s+you)\b",
    re.IGNORECASE,
)
_NOT_HERE_RE = re.compile(
    r"\b(?:not\s+here|isn['’]?t\s+here|is\s+not|nowhere|no\s+sign\s+of|absent|gone|away\s+at|elsewhere|"
    r"no\s+answer|does\s+not\s+answer|doesn['’]?t\s+answer|lost\s+to\s+sight|out\s+of\s+sight|"
    r"disappear(?:s|ed)?|vanish(?:es|ed)?|somewhere)\b",
    re.IGNORECASE,
)


def bring_called_here(conn, resolution: dict[str, Any] | None, narration: str) -> list[str]:
    """Move a called NPC (resolution["called"]) to the player's location when the
    prose shows them here. The engine owns where people are; the prose only has
    to agree. Codes moved."""
    called = _codes((resolution or {}).get("called")) if isinstance(resolution, dict) else []
    text = re.sub(r"\s+", " ", str(narration or ""))
    if not called or not text.strip():
        return []
    row = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()
    here_id = row[0] if row else None
    if here_id is None:
        return []
    sentences = re.split(r"(?<=[.!?\"”])\s+", text)
    moved: list[str] = []
    for code in called:
        npc = conn.execute("SELECT id, name, location_id FROM npcs WHERE code = ?", (code,)).fetchone()
        if npc is None or npc[2] == here_id:
            continue
        rows = [{"code": code, "name": str(npc[1] or ""), "aliases": []}]
        shown = False
        if code in speakers_in(text, rows):
            shown = True
        for sentence in sentences:
            if not _names_in(sentence, rows):
                continue
            if _NOT_HERE_RE.search(sentence):
                shown = False
                break
            if _SHOWN_HERE_RE.search(sentence):
                shown = True
        if not shown:
            continue
        try:
            conn.execute("UPDATE npcs SET location_id = ? WHERE id = ?", (here_id, int(npc[0])))
        except Exception:
            continue  # a same-named NPC already stands here
        moved.append(code)
    return moved


def read_scene(conn) -> dict[str, Any]:
    scene = _read_setting(conn, "active_scene")
    return scene if isinstance(scene, dict) else {}


def save_state(conn, state: dict[str, Any]) -> None:
    _write_setting(conn, SETTING_KEY, state)
    _write_setting(conn, "active_scene", synced_scene(read_scene(conn), state))


def update_after_turn(
    conn,
    *,
    resolution: dict[str, Any] | None,
    scene_before: dict[str, Any],
    scene_cast: Any,
    narration: str,
    player_input: str,
    turn: int,
) -> dict[str, Any]:
    settings = {
        SETTING_KEY: _read_setting(conn, SETTING_KEY),
        "active_scene": scene_before,
    }
    if settings[SETTING_KEY] is None:
        settings.pop(SETTING_KEY)
    previous = load_state(settings)
    state = next_state(
        previous,
        context=context_from_conn(conn),
        resolution=resolution,
        scene_before=scene_before,
        scene_after=read_scene(conn),
        scene_cast=scene_cast,
        narration=narration,
        player_input=player_input,
        turn=turn,
    )
    # A turn with nobody in it writes nothing, so a rewind has nothing to undo.
    if not state["target"] and not state["present"] and settings.get(SETTING_KEY) is None and not scene_before:
        return state
    save_state(conn, state)
    return state


def choose(conn, context: dict[str, Any], codes: list[str] | None, *, group: bool = False) -> dict[str, Any]:
    """The player picked on the chip. Empty codes clears the target."""
    settings = dict(context.get("settings") or {})
    state = load_state(settings)
    rows = roster(context)
    here = [row["code"] for row in rows]
    if group:
        picked = present_codes(context, state) or here
    else:
        picked = [c for c in _codes(codes) if c in here]
    if codes and not group and not picked:
        raise ValueError("That person is not here.")
    state.update(
        {
            "target": picked,
            "group": bool(group and len(picked) > 1),
            "why": "chosen" if picked else "none",
            "chosen": bool(picked),
            "location": str(_current_location(context).get("code") or state.get("location") or ""),
            "here": here,
        }
    )
    if not picked:
        state["revealed"] = []
        state["last_speaker"] = ""
    state["present"] = _codes([c for c in list(state.get("present") or []) if c in here] + picked)
    save_state(conn, state)
    return state


def view(context: dict[str, Any]) -> dict[str, Any]:
    """What the "Talking to" chip shows: the target, why, and who else could be picked."""
    settings = context.get("settings") if isinstance(context.get("settings"), dict) else {}
    state = load_state(settings)
    rows = roster(context)
    names = _names(rows)
    present = present_codes(context, state)
    target = [c for c in state.get("target") or [] if c in names]
    options = present + [row["code"] for row in rows if row["code"] not in present]
    why = str(state.get("why") or "none") if target else "none"
    return {
        "target": [{"code": c, "name": names[c]} for c in target],
        "group": bool(state.get("group")) and len(target) > 1,
        "why": why,
        "why_text": RULE_TEXT.get(why, ""),
        "chosen": bool(state.get("chosen")) and bool(target),
        "present": [{"code": c, "name": names[c]} for c in present],
        "options": [{"code": c, "name": names[c], "present": c in present} for c in options],
    }
