"""Prose and state agreement: the facts a turn's narration states (playtests #69, #75, #76, #77).

The engine decides what is true and the model writes the words. Live game
a0eb2e27 showed the same defect four ways: the prose said "pay 7 gold" and the
dice took 9; cleanup cut an invented request and kept the goods it bought; the
prose led the player to a forge the state never reached; the player offered
his last 3 gold and kept it. Each time one part of the turn decided a fact and
another part decided it again, or threw away its half.

These readers pull out what the prose and the player's own line state (a price
paid, an offer made, the act the player declared) so the engine can own it,
and the trimmers take out prose that shows what the state refused. Pure
functions over text: no database, no model.
"""

from __future__ import annotations

import re
from typing import Any, Callable

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "a hundred": 100, "hundred": 100,
}
_AMOUNT = r"(?P<n>\d{1,5}|" + "|".join(sorted((w.replace(" ", r"\s+") for w in _NUMBER_WORDS), key=len, reverse=True)) + r")"
# The player's purse is "gold" (player.gold). Silver and copper are other
# units, so a "5 silver" fee is not read as 5 gold.
_COIN = r"(?:gold(?:\s+(?:coins?|pieces?|crowns?))?|coins?|crowns?)\b"
_AP = r"['\u2019]"

# The player pays: "you pay 7 gold", "You thank him and pay 7 gold", "you
# hand over three coins". A third-person subject in the gap ("you watch as she
# pays") is someone else paying.
_PAID_RE = re.compile(
    r"\byou\s+(?:(?!(?:he|she|they|we)\b)[\w']+,?\s+){0,4}?"
    r"(?:pay|paid|hand(?:ed)?(?:\s+over)?|give|gave|count(?:ed)?\s+out|slide|slid|place[sd]?|drop(?:ped)?|"
    r"spend|spent|part(?:ed)?\s+with|fish(?:ed)?\s+out|dig\s+out|dug\s+out|press(?:ed)?)\b"
    r"[^.!?\n\"\u201c\u201d]{0,40}?\b" + _AMOUNT + r"\s+" + _COIN,
    re.I,
)
# A price named: "That'll be 7 gold", "it costs seven coins", "seven gold for the lot".
_PRICED_RE = re.compile(
    r"(?:\b(?:costs?|cost\s+you|price\s+(?:is|of)|priced\s+at|that" + _AP + r"?ll\s+be|it" + _AP + r"?s|comes\s+to|"
    r"charges?(?:\s+you)?|fee\s+(?:is|of)|toll\s+(?:is|of)|owe\s+(?:me|us|him|her)?|for)\s+"
    r"(?:just\s+|only\s+|a\s+mere\s+)?" + _AMOUNT + r"\s+" + _COIN + r")"
    r"|(?:\b" + _AMOUNT.replace("?P<n>", "?P<n2>") + r"\s+" + _COIN + r"\s+(?:for|each|apiece|a\s+piece)\b)",
    re.I,
)
# Coins that reach the player: "hands you 20 gold", "you receive 5 coins".
# "I'll pay you 20 gold" is a promise, so only the -s and past forms count.
_RECEIVED_RE = re.compile(
    r"\b(?:hands|handed|gives|gave|pays|paid|tosses|tossed|passes|passed|slides|slid|presses|pressed|"
    r"counts\s+out|counted\s+out|drops|dropped)\s+you\b[^.!?\n\"\u201c\u201d]{0,30}?\b" + _AMOUNT + r"\s+" + _COIN
    + r"|\byou\s+(?:receive|received|earn|earned|are\s+paid|were\s+paid|get|got|pocket|pocketed|collect|collected)\s+"
    r"[^.!?\n\"\u201c\u201d]{0,20}?\b" + _AMOUNT.replace("?P<n>", "?P<n2>") + r"\s+" + _COIN,
    re.I,
)


def _number(token: str | None) -> int | None:
    text = " ".join(str(token or "").lower().split())
    if not text:
        return None
    if text.isdigit():
        return int(text)
    return _NUMBER_WORDS.get(text)


def _match_number(match: re.Match) -> int | None:
    groups = match.groupdict()
    return _number(groups.get("n") or groups.get("n2"))


def stated_coin_amounts(text: str) -> dict[str, list[int]]:
    """The gold amounts the prose names: paid by the player, priced, and received.

    A price is read across quotes too: a shopkeeper's "That'll be 7 gold" is
    the price. Paid and received are read from the narration outside quotes
    only: "You pay me five gold and the sword is yours," is terms, not a
    payment, and an offer stays open until the player agrees (#77).
    Each list holds distinct amounts in order of first appearance.
    """
    out: dict[str, list[int]] = {"paid": [], "priced": [], "received": []}
    body = str(text or "")
    unquoted = _QUOTE_RE.sub(" ", body)
    for key, pattern in (("paid", _PAID_RE), ("priced", _PRICED_RE), ("received", _RECEIVED_RE)):
        for match in pattern.finditer(body if key == "priced" else unquoted):
            value = _match_number(match)
            if value and value not in out[key]:
                out[key].append(value)
    return out


# The player's own offer: "I'll give you my last 3 gold for that", "I pay
# him five coins", "I'll buy it for 4 gold" (playtest #75, T7).
_OFFER_RE = re.compile(
    r"\b(?:give|pay|offer|hand(?:\s+over)?|trade|slide|toss)\s+(?:(?:you|him|her|them|[A-Z][\w'\u2019-]*)\s+)?"
    r"(?:(?:my|the|all\s+my)\s+)?(?:(?:last|remaining|only|spare)\s+)?" + _AMOUNT + r"\s+" + _COIN
    # "I'll take the job for 10 gold" asks to be paid: only taking the thing
    # on sale ("I'll take it for 4 gold") is an offer to pay.
    + r"|\b(?:buy|purchase|take\s+(?:it|that|this|them|those|these|one))\b[^.!?\n]{0,40}?\bfor\s+" + _AMOUNT.replace("?P<n>", "?P<n2>") + r"\s+" + _COIN,
    re.I,
)
_NEGATION_RE = re.compile(
    r"\b(?:can" + _AP + r"?t|cannot|can\s+not|couldn" + _AP + r"?t|could\s+not|won" + _AP + r"?t|will\s+not|"
    r"wouldn" + _AP + r"?t|would\s+not|don" + _AP + r"?t|do\s+not|didn" + _AP + r"?t|did\s+not|never|"
    r"not\s+going\s+to|unable\s+to|shouldn" + _AP + r"?t|should\s+not|refuse\s+to)\b"
    # "I can't wait to go" and "can't help but" are not refusals.
    r"(?!\s+(?:wait|help|resist|stop\s+(?:myself|thinking))\b)",
    re.I,
)


def player_trade_offer(own_line: str) -> int | None:
    """Gold the player's own words offer to pay this turn, or None. A denied offer is none."""
    text = str(own_line or "")
    for match in _OFFER_RE.finditer(text):
        clause_start = max(text.rfind(mark, 0, match.start()) for mark in (",", ".", ";", "!", "?", "\n"))
        if _NEGATION_RE.search(text[clause_start + 1: match.start()]):
            continue
        value = _match_number(match)
        if value:
            return value
    return None


_QUOTE_RE = re.compile(r'"([^"]*)"|\u201c([^\u201d]*)\u201d')
_REFUSE_RE = re.compile(
    r"\bkeep\s+your\s+(?:coin|coins|gold|money)\b|\bput\s+(?:your|that|the)\s+(?:coin|coins|gold|money)\s+away\b|"
    r"\bno\s+charge\b|\bfree\s+of\s+charge\b|\bon\s+the\s+house\b|\bno\s+need\s+to\s+pay\b|"
    r"\b(?:won" + _AP + r"?t|will\s+not|can" + _AP + r"?t|cannot)\s+(?:take|accept)\s+your\s+(?:coin|coins|gold|money)\b|"
    r"\b(?:refuses|declines|waves\s+(?:off|away)|pushes\s+(?:back|away))\s+(?:the|your)\s+(?:coin|coins|gold|money|offer)\b|"
    r"\bnot\s+for\s+sale\b|\bno\s+deal\b|\bnot\s+enough\b",
    re.I,
)
_ACCEPT_WORDS_RE = re.compile(
    r"\b(?:certainly|deal|agreed|done|very\s+well|fair\s+enough|of\s+course|sure|yes|alright|all\s+right|gladly)\b",
    re.I,
)
# Taking the coin, or handing over a thing: "gives you a warm nod" (T5) and
# "passes you by" are gestures, not a deal.
_ACCEPT_ACT_RE = re.compile(
    r"\b(?:takes|took|accepts|accepted|pockets|pocketed|sweeps\s+up|swept\s+up)\s+(?:the|your)\s+(?:coin|coins|gold|money)\b|"
    r"\b(?:hands|handed|gives|gave|passes|passed|slides|slid|tosses|tossed)\s+"
    r"(?:you\s+(?!(?:a|an|one)\s+(?:\w+\s+)?(?:nod|smile|look|glance|wink|shrug|grin|frown|sigh|stare|pat|warning)\b)"
    r"(?:the|a|an|it|them|his|her|their|your)\b|"
    r"(?:it|them|(?:the|a|an|his|her|their)\s+\w+(?:\s+\w+){0,2})\s+(?:over\s+)?to\s+you\b)",
    re.I,
)


def offer_answer(narration: str, own_line: str = "") -> str:
    """How the prose answers the player's offer: "refused", "accepted" or "" (not answered).

    The player's own words echoed in the prose are neither ("I know 3 gold is
    not enough"), and only the first quote that answers counts: a stock
    "what's done is done" later in the scene is not the reply.
    """
    text = str(narration or "")
    own_words = set(re.findall(r"[a-z']+", str(own_line or "").lower()))

    def echo(span: str) -> bool:
        words = set(re.findall(r"[a-z']+", span.lower()))
        return bool(words) and len(words & own_words) * 2 >= len(words)

    answers = [m.group(1) or m.group(2) or "" for m in _QUOTE_RE.finditer(text)]
    answers = [span for span in answers if not echo(span)]
    unechoed = _QUOTE_RE.sub(lambda m: " " if echo(m.group(1) or m.group(2) or "") else m.group(0), text)
    if _REFUSE_RE.search(unechoed):
        return "refused"
    if answers and _ACCEPT_WORDS_RE.search(answers[0]):
        return "accepted"
    if _ACCEPT_ACT_RE.search(_QUOTE_RE.sub(" ", text)):
        return "accepted"
    return ""


def shows_payment(sentence: str) -> bool:
    """Whether a sentence shows the player paying coin (outside quotes)."""
    return bool(_PAID_RE.search(_QUOTE_RE.sub(" ", str(sentence or ""))))


# A denied clause ends at a comma or stop, or where a conjunction starts a new
# subject: "i dont have the coin so i head to the bakery" still heads there.
_NEGATED_CLAUSE_RE = re.compile(
    _NEGATION_RE.pattern + r"[^,.;:!?\n]*?(?=\s+(?:so|and|but|then|yet)\s+(?:i|we)\b|[,.;:!?\n]|$)", re.I
)


def strip_negated_clauses(text: str) -> str:
    """The text with each denied clause blanked, from the negation to the next comma, stop or new clause.

    Playtest #76 (T9): "i cant leave the city due to a game bug" walked the
    player to the south gate. A clause the player denies is not something they do.
    """
    return _NEGATED_CLAUSE_RE.sub(" ", str(text or ""))


# ---------------------------------------------------------------------------
# Trimming prose to the state
# ---------------------------------------------------------------------------

_SENTENCE_SPLIT_RE = re.compile(r"(?:(?<=[.!?])|(?<=[.!?][\"\u201d\u2019]))\s+")


def sentence_spans(text: str) -> list[tuple[int, int, str]]:
    """(start, end, sentence) for every sentence, paragraph by paragraph, offsets into text."""
    body = str(text or "")
    out: list[tuple[int, int, str]] = []
    for para in re.finditer(r"[^\n]+(?:\n(?!\s*\n)[^\n]+)*", body):
        start = para.start()
        for piece in _SENTENCE_SPLIT_RE.split(para.group(0)):
            if not piece.strip():
                continue
            at = body.find(piece, start)
            if at < 0:
                continue
            out.append((at, at + len(piece), piece))
            start = at + len(piece)
    return out


def cut_from(text: str, index: int, *, floor: int = 200) -> str | None:
    """The prose up to ``index``, or None when that leaves less than ``floor`` characters."""
    head = str(text or "")[: max(0, int(index))].rstrip()
    return head if len(head) >= floor else None


def drop_sentences(text: str, should_drop: Callable[[str], bool], *, floor: int = 200) -> tuple[str, list[str]]:
    """Remove every sentence ``should_drop`` picks; paragraphs keep their breaks.

    Returns the text unchanged and no drops when the rest would fall under ``floor``.
    """
    body = str(text or "")
    dropped: list[str] = []
    paragraphs: list[str] = []
    for para in re.split(r"\n\s*\n", body):
        kept: list[str] = []
        for piece in _SENTENCE_SPLIT_RE.split(para.strip()):
            if not piece.strip():
                continue
            if should_drop(piece):
                dropped.append(piece.strip())
            else:
                kept.append(piece.strip())
        if kept:
            paragraphs.append(" ".join(kept) if len(kept) > 1 or dropped else para.strip())
    if not dropped:
        return body, []
    joined = "\n\n".join(paragraphs).strip()
    if len(joined) < floor:
        return body, []
    return joined, dropped


# ---------------------------------------------------------------------------
# The player's declared act (playtest #77)
# ---------------------------------------------------------------------------

# Hands-on work a player declares. The prose often swaps the verb for a
# neighbour ("fix a rusty sword" came back as "begins to sharpen the sword"),
# so each family is read as one act.
_ACT_FAMILIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("mend", ("fix", "repair", "mend", "sharpen", "hone", "patch", "restore", "polish", "whet", "grind")),
    ("smith", ("forge", "hammer", "smith", "temper", "quench", "smelt", "anneal")),
    ("cook", ("cook", "bake", "brew", "roast", "knead")),
    ("make", ("craft", "build", "carve", "sew", "stitch", "weave", "whittle", "assemble", "fletch")),
    ("labour", ("dig", "chop", "haul", "split", "scrub", "sweep", "clean", "unload", "stack")),
    ("treat", ("bandage", "treat", "splint")),
    ("perform", ("sing", "dance", "perform", "recite")),
)


def _verb_forms(verb: str) -> str:
    """A regex for a verb's own forms: forge/forged/forging, dig/digs/digging. Not "health" for "heal"."""
    if verb.endswith("e"):
        return verb[:-1] + r"(?:e|es|ed|ing)"
    return verb + r"(?:s|es|ed|ing|" + verb[-1] + r"ed|" + verb[-1] + r"ing)?"


_PLAYER_SUBJECT_RE = re.compile(r"\byou\b", re.I)
_OTHER_SUBJECT_RE = re.compile(r"\b(?:he|she|they)\b|\b[A-Z][a-z][\w'\u2019-]*\b")
_NOT_A_SUBJECT = frozenset({
    "The", "A", "An", "As", "When", "While", "Then", "But", "And", "Inside", "Outside", "Here", "There", "With",
    "Without", "After", "Before", "Once", "If", "It", "Its", "This", "That", "These", "Those", "Her", "His",
})


# A family word used as a noun ("the forge", "a hammer", "my temper").
_NOUN_BEFORE_RE = re.compile(
    r"\b(?:a|an|the|my|your|his|her|their|our|its|this|that|these|those|some|any|every|each)\s+(?:[\w'-]+\s+)?$", re.I
)
# A wish or a lesson is not a declared act: "i would love to learn how to forge steel" (T11).
_WISH_BEFORE_RE = re.compile(
    r"\b(?:would\s+(?:love|like)|want|wanted|wish|hope|hoping|like|learn|learning|teach\s+me|show\s+me|"
    r"know|knows)\s+(?:how\s+)?to\s+(?:[\w'-]+\s+){0,2}$",
    re.I,
)


def _act_word_is_verb(text: str, match: re.Match) -> bool:
    """Whether a family word heads something done, not a name, a noun or a wish."""
    before = text[: match.start()]
    if _NOUN_BEFORE_RE.search(before):
        return False
    # "Blind Owl Forge": a capital inside a name, not the first word of a clause.
    if match.group(0)[:1].isupper() and re.search(r"\b[A-Z][\w'-]*\s+$", before):
        return False
    return True


# Since #85a this reading also rolls the dice, costs the energy, passes the
# clock and finishes quest steps, so a line that only names work is not the
# player doing it (#85 review): "I ask Finnian to sharpen my sword", "I watch
# Finnian polish the swords", "I tell Finnian I'll polish them after lunch".
# A request, a look or a promise before the verb hands the act to someone or
# to later, unless a fresh "I" takes it back ("I watch closely as I polish").
_HANDED_OFF_BEFORE_RE = re.compile(
    r"\b(?:ask|asks|asked|asking|tell|tells|told|telling|order|orders|ordered|beg|begs|begged|let|lets|"
    r"watch|watches|watched|watching|observe|observes|observed|see|sees|saw|say|says|said|"
    r"promise|promises|promised|agree|agrees|agreed|offer|offers|offered|plan|plans|planned|"
    r"intend|intends|wait(?:s|ed)?\s+for)\b",
    re.I,
)
_FRESH_PLAYER_SUBJECT_RE = re.compile(
    r"\b(?:i|we)\b(?!['\u2019](?:ll|d)\b|\s+(?:will|shall|would|could|might|can|may)\b)", re.I
)
# Someone else as the subject right before the verb: "as Finnian forges", "while he polishes".
_OTHER_DOER_BEFORE_RE = re.compile(r"\b(?:he|she|they)\s+(?:\w+ly\s+)?$|\b([A-Z][\w'\u2019-]*)\s+(?:\w+ly\s+)?$")
# Work put off to later in the same sentence: "I'll polish them after lunch".
_FUTURE_BEFORE_RE = re.compile(r"\b(?:i['\u2019]ll|we['\u2019]ll|i\s+will|we\s+will|going\s+to|gonna)\s+(?:[\w'-]+\s+){0,2}$", re.I)
_LATER_AFTER_RE = re.compile(
    r"\b(?:later|tomorrow|tonight|soon|next|after\s+(?:lunch|dinner|supper|breakfast|this|that|we|i)|in\s+the\s+morning)\b", re.I
)


def _act_is_players_now(text: str, match: re.Match, clause: str) -> bool:
    """Whether the player does this act now, in their own voice (#85 review).

    Not when it is inside quoted speech, in a question ("can I help you
    polish the blades?"), asked of or watched in someone else, done by a
    named or pronoun subject, or promised for later.
    """
    before = text[: match.start()]
    if before.count('"') % 2 == 1 or before.count("\u201c") > before.count("\u201d"):
        return False
    after = text[match.end():]
    clause_end = re.search(r"[,.;!?\n]", after)
    if clause_end and clause_end.group(0) == "?":
        return False
    if not clause_end and after.rstrip().endswith("?"):
        return False
    lead = re.split(r"\s+(?:and|then|but)\s+", clause)[-1]
    handed = None
    for handed in _HANDED_OFF_BEFORE_RE.finditer(lead):
        pass
    if handed is not None and not _FRESH_PLAYER_SUBJECT_RE.search(lead[handed.end():]):
        return False
    other = _OTHER_DOER_BEFORE_RE.search(lead)
    name = other.group(1) if other else ""
    # "I help Finnian polish the swords" is the player's work too (Q1's own step).
    helping = re.search(r"\bhelp(?:s|ed|ing)?\s+(?:[\w'\u2019-]+\s+){1,3}(?:to\s+)?$", lead, re.I)
    if other and not helping and (not name or (name not in _NOT_A_SUBJECT and name not in {"I", "You", "We"} and not name.lower().endswith("ly"))):
        return False
    sentence_rest = re.split(r"[.!?\n]", after, maxsplit=1)[0]
    if _FUTURE_BEFORE_RE.search(lead) and _LATER_AFTER_RE.search(sentence_rest):
        return False
    return True


def declared_act(own_line: str) -> dict[str, Any] | None:
    """The hands-on act the player's own line declares: {"verb", "family", "phrase"}, or None."""
    text = str(own_line or "")
    best: tuple[int, str, str] | None = None
    for family, verbs in _ACT_FAMILIES:
        for verb in verbs:
            for match in re.finditer(rf"\b{_verb_forms(verb)}\b", text, re.I):
                clause_start = max(text.rfind(mark, 0, match.start()) for mark in (",", ".", ";", "!", "?", "\n"))
                clause = text[clause_start + 1: match.start()]
                if _NEGATION_RE.search(clause) or _WISH_BEFORE_RE.search(clause):
                    continue
                if not _act_word_is_verb(text, match):
                    continue
                if not _act_is_players_now(text, match, clause):
                    continue
                if best is None or match.start() < best[0]:
                    best = (match.start(), family, verb)
                break
    if best is None:
        return None
    start, family, verb = best
    rest = text[start:]
    end = re.search(r"[,.;!?\n]|\s+(?:and|while|then|but)\s+", rest)
    phrase = (rest[: end.start()] if end else rest).strip()[:100]
    return {"verb": verb, "family": family, "phrase": phrase}


# What each family is to the engine (playtest #85a). "i polish the blades the
# best i can" was read here as a "mend" act, but the check table had no
# polish, and the cost table had none either, so the work rolled no dice and
# was costed like a glance. One reading now answers all three: which skill
# rolls, what kind of exertion it costs, and how long it takes.
ACT_FAMILY_RULES: dict[str, dict[str, Any]] = {
    "mend": {"skill": "craft", "kind": "physical", "minutes": 20},
    "smith": {"skill": "smithing", "kind": "physical", "minutes": 30},
    "cook": {"skill": "cooking", "kind": "general", "minutes": 20},
    "make": {"skill": "craft", "kind": "physical", "minutes": 30},
    "labour": {"skill": "athletics", "kind": "physical", "minutes": 25},
    "treat": {"skill": "healing", "kind": "general", "minutes": 10},
    "perform": {"skill": "performance", "kind": "talk", "minutes": 10},
}

# Work on metal is smithing, whatever the verb: polishing a blade at an armory
# is metalwork, and a player with no smithing rolls it untrained (#85a).
_METAL_OBJECT_RE = re.compile(
    r"\b(?:blades?|swords?|axes?|knife|knives|daggers?|armou?rs?|mail|helms?|helmets?|horseshoes?|nails?|"
    r"steel|iron|bronze|metal|spears?|tongs|chains?|shields?|greaves|gauntlets?|hinges?)\b",
    re.I,
)
_MECHANISM_RE = re.compile(r"\b(?:mechanisms?|gadgets?|traps?|locks?|gears?|springs?|clockwork|pulleys?|winch(?:es)?)\b", re.I)
_POTION_RE = re.compile(r"\b(?:potions?|tinctures?|elixirs?|salves?|poultices?)\b", re.I)
_ORE_RE = re.compile(r"\b(?:ore|veins?|tunnels?|shafts?)\b", re.I)
# Routine work is still a roll, at an easier mark, and only a fumble hurts:
# a novice polishing a sword should not cut themselves two times in five.
_ROUTINE_VERBS = frozenset({"polish", "whet", "clean", "scrub", "sweep", "stack", "unload", "haul", "patch"})
# Family words that are not work in this line: "we split up", "fix my gaze on
# him", "treat her to a drink". Since #85a this list also keeps idioms off the
# dice, the energy and the clock (#85 review): "split the gold", "stack the
# coins", "build up my courage", "fix him with a look", "dig through my bag",
# "treat the innkeeper with respect".
_NOT_WORK_RE = re.compile(
    r"^(?:split\w*\s+(?:up|off)\b|fix\w*\s+(?:\w+\s+)?(?:gaze|eyes|stare|attention)\b|treat\w*\s+\w+(?:\s+\w+)?\s+to\s+"
    r"|split\w*\s+(?:it\b|(?:the|our|my)\s+(?:gold|coins?|money|silver|cost|bill|loot|take|pay|difference|reward)\b)"
    r"|stack\w*\s+(?:\w+\s+)?(?:coins?|gold|silver|chips?|cards?)\b"
    r"|sweep\w*\s+(?:my|his|her|their|a|the)\s+(?:\w+\s+)?(?:gaze|eyes|look|glance|hand|arm)\b"
    r"|hammer\w*\s+(?:on|at)\s+(?:the|a|his|her|their)\s+(?:\w+\s+)?(?:door|gate|wall|table|shutters?)\b"
    r"|build\w*\s+(?:up\b|(?:\w+\s+)?(?:courage|nerve|trust|rapport|confidence|reputation|hopes?)\b)"
    r"|fix\w*\s+\w+(?:\s+\w+)?\s+with\s+(?:a|an|my|the)\s+(?:\w+\s+)?(?:look|glare|stare|gaze|glance|eye)\b"
    r"|dig\w*\s+(?:through|in|into|around\s+in)\s+(?:my|his|her|their|the|a)\s+(?:\w+\s+)?"
    r"(?:bag|pack|pockets?|purse|satchel|pouch|memory|memories|notes)\b"
    r"|treat\w*\s+\w+(?:\s+\w+)?\s+(?:like|as|kindly|fairly|badly|with\s+(?:\w+\s+)?"
    r"(?:respect|kindness|contempt|suspicion|disdain|courtesy|caution|scorn|deference))\b)",
    re.I,
)


def act_rules(own_line: str) -> dict[str, Any] | None:
    """The declared act with its check skill, cost kind and minutes, or None (playtest #85a).

    {"verb", "family", "phrase", "skill_code", "kind", "minutes", "routine"}.
    The single reading of a hands-on act that the dice (skill_checks), the
    body cost (player_resources) and the clock (world) all share.
    """
    act = declared_act(own_line)
    if not act:
        return None
    phrase = str(act.get("phrase") or "")
    if _NOT_WORK_RE.search(phrase):
        return None
    rules = ACT_FAMILY_RULES.get(act["family"])
    if not rules:
        return None
    skill = rules["skill"]
    if act["family"] in {"mend", "make"}:
        if _MECHANISM_RE.search(phrase):
            skill = "tinkering"
        elif _METAL_OBJECT_RE.search(phrase):
            skill = "smithing"
    elif act["family"] == "cook" and _POTION_RE.search(phrase):
        skill = "alchemy"
    elif act["family"] == "labour" and _ORE_RE.search(phrase):
        skill = "mining"
    return {
        **act,
        "skill_code": skill,
        "kind": rules["kind"],
        "minutes": int(rules["minutes"]),
        "routine": act["verb"] in _ROUTINE_VERBS,
    }


def act_handed_off(narration: str, own_line: str) -> dict[str, Any] | None:
    """The player's declared act done in the prose by someone else and never by "you".

    A measurement (playtest #77, T13: "fix a rusty sword for Bertram" became
    "Juliana takes the sword ... begins to sharpen the sword"). Returns
    {"verb", "family", "by", "sentence"} or None.
    """
    act = declared_act(own_line)
    if not act:
        return None
    verbs = dict(_ACT_FAMILIES)[act["family"]]
    verb_re = re.compile(r"\b(?:" + "|".join(_verb_forms(v) for v in verbs) + r")\b", re.I)
    unquoted = _QUOTE_RE.sub(" ", str(narration or ""))
    other: tuple[str, str, bool] | None = None  # (who, sentence, named)
    for _start, _end, sentence in sentence_spans(unquoted):
        for match in verb_re.finditer(sentence):
            if not _act_word_is_verb(sentence, match):
                continue  # "Bertram is at the forge" hands nothing off
            before = sentence[: match.start()]
            mine = list(_PLAYER_SUBJECT_RE.finditer(before))
            theirs = [m for m in _OTHER_SUBJECT_RE.finditer(before) if m.group(0) not in _NOT_A_SUBJECT]
            last_mine = mine[-1].start() if mine else -1
            last_theirs = theirs[-1].start() if theirs else -1
            if last_mine > last_theirs:
                return None
            if last_theirs >= 0 and (other is None or not other[2]):
                named = [m.group(0) for m in theirs if m.group(0)[:1].isupper() and m.group(0).lower() not in {"he", "she", "they"}]
                # A name beats a pronoun: "Juliana ... continues to sharpen" over "she begins to sharpen".
                if other is None or named:
                    other = (named[-1] if named else theirs[-1].group(0), sentence.strip()[:200], bool(named))
    if other is None:
        return None
    return {"verb": act["verb"], "family": act["family"], "by": other[0], "sentence": other[1]}
