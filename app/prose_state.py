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
    r"(?:pay|paid|hand(?:ed)?(?:\s+over)?|give|gave|count(?:ed|s)?(?:\s+out)?|slide|slid|place[sd]?|drop(?:ped)?|"
    r"spend|spent|part(?:ed)?\s+with|fish(?:ed)?\s+out|dig\s+out|dug\s+out|press(?:ed)?)\b"
    r"[^.!?\n\"\u201c\u201d]{0,40}?\b" + _AMOUNT + r"\s+" + _COIN,
    re.I,
)
# Money put down: "You put two gold coins on the bar" (7B run 5, T94). The
# amount has to follow the verb at once: "you set out with ten gold" is not it.
_PAID_PUT_RE = re.compile(
    r"\byou\s+(?:\w+ly\s+)?(?:put|puts|set|sets|lay|lays|laid|push|pushes|pushed|toss|tosses|tossed)\s+"
    r"(?:down\s+)?(?:(?:the|your|my)\s+)?(?:(?:last|remaining|only|spare)\s+)?" + _AMOUNT.replace("?P<n>", "?P<n2>")
    + r"\s+" + _COIN + r"(?![^.!?\n]{0,30}\b(?:into|in)\s+your\b)",
    re.I,
)
# A price named: "That'll be 7 gold", "it costs seven coins", "seven gold for the lot".
_PRICED_RE = re.compile(
    r"(?:\b(?:costs?|cost\s+you|price\s+(?:is|of)|priced\s+at|that" + _AP + r"?ll\s+be|it" + _AP + r"?s|comes\s+to|"
    r"charges?(?:\s+you)?|fee\s+(?:is|of)|toll\s+(?:is|of)|owe\s+(?:me|us|him|her)?|for)\s+"
    r"(?:just\s+|only\s+|a\s+mere\s+)?" + _AMOUNT + r"\s+" + _COIN + r")"
    # A day rate is a price too: "Three gold a day, paid at dusk" (7B run 18, T7).
    r"|(?:\b" + _AMOUNT.replace("?P<n>", "?P<n2>") + r"\s+" + _COIN
    + r"\s+(?:for|each|apiece|a\s+piece|a\s+day|per\s+day|each\s+day|a\s+shift|per\s+shift|daily)\b)",
    re.I,
)
# Coins that reach the player: "hands you 20 gold", "you receive 5 coins".
# "I'll pay you 20 gold" is a promise, so only the -s and past forms count.
_RECEIVED_RE = re.compile(
    r"\b(?:hands|handed|handing|gives|gave|giving|pays|paid|paying|tosses|tossed|passes|passed|slides|slid|presses|pressed|"
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


_MENTION_RE = re.compile(r"\b" + _AMOUNT + r"\s+" + _COIN, re.I)


def coin_mentions(text: str) -> list[int]:
    """Every gold amount the prose names anywhere, in order: "Nine coins." counts.

    A GOLD op whose number the prose names this way is the scene's number, not
    a band hint (Saltmarrow run: "Nine coins" and GOLD -9 were re-rolled).
    """
    out: list[int] = []
    for match in _MENTION_RE.finditer(str(text or "")):
        value = _match_number(match)
        if value and value not in out:
            out.append(value)
    return out


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
    for key, pattern in (("paid", _PAID_RE), ("paid", _PAID_PUT_RE), ("priced", _PRICED_RE), ("received", _RECEIVED_RE)):
        source = body if key == "priced" else unquoted
        for match in pattern.finditer(source):
            value = _match_number(match)
            if not value:
                continue
            if key == "paid":
                # "You count the sixteen gold Warin handed you and slip them into
                # your purse" counts coin coming in (7B run 5, T56: read as -16).
                ends = [i for i in (source.find(mark, match.end()) for mark in (".", "!", "?", "\n")) if i >= 0]
                after = source[match.end():min(ends) if ends else len(source)]
                if _COIN_COMING_IN_RE.match(after) or (
                    _INTO_YOUR_PURSE_RE.search(after) and not _TO_SOMEONE_RE.search(after)
                ):
                    if value not in out["received"]:
                        out["received"].append(value)
                    continue
            if value not in out[key]:
                out[key].append(value)
    return out


# Right after the amount: "sixteen gold Warin Croft [[F]] handed you".
_COIN_COMING_IN_RE = re.compile(
    r"\s*(?:that\s+|which\s+)?(?:[\w'’\[\]-]+\s+){0,4}?"
    r"(?:handed|gave|paid|passed|tossed|slid|pressed|counted\s+out\s+for)\s+you\b",
    re.I,
)
_INTO_YOUR_PURSE_RE = re.compile(
    r"\b(?:into|in)\s+your\s+(?:own\s+)?(?:purse|pocket|pouch|coin\s*purse|belt\s*pouch|money\s*pouch)\b", re.I
)
_TO_SOMEONE_RE = re.compile(r"\b(?:to|for)\s+(?:him|her|them|the|a|an|[A-Z][\w'’-]*)\b|\bhand\s+over\b|\bpay\b")


# The player's own offer: "I'll give you my last 3 gold for that", "I pay
# him five coins", "I'll buy it for 4 gold" (playtest #75, T7).
_OFFER_RE = re.compile(
    # "I put three coin on the counter for the rope" (Saltmarrow run, T8) puts
    # the money down: put/set/lay/place/count out are offers too.
    r"\b(?:give|pay|offer|hand(?:\s+over)?|trade|slide|toss|put|set|lay|place|count(?:\s+out)?)\s+(?:(?:you|him|her|them|[A-Z][\w'\u2019-]*)\s+)?"
    r"(?:(?:my|the|all\s+my)\s+)?(?:(?:last|remaining|only|spare)\s+)?" + _AMOUNT + r"\s+" + _COIN
    # "I'll take the job for 10 gold" asks to be paid: only taking the thing
    # on sale ("I'll take it for 4 gold") is an offer to pay.
    + r"|\b(?:buy|purchase|take\s+(?:it|that|this|them|those|these|one))\b[^.!?\n]{0,40}?\bfor\s+" + _AMOUNT.replace("?P<n>", "?P<n2>") + r"\s+" + _COIN,
    re.I,
)
_NEGATION_RE = re.compile(
    r"\b(?:can" + _AP + r"?t|cannot|can\s+not|couldn" + _AP + r"?t|could\s+not|won" + _AP + r"?t|will\s+not|"
    r"wouldn" + _AP + r"?t|would\s+not|don" + _AP + r"?t|do\s+not|didn" + _AP + r"?t|did\s+not|never|"
    # "I'm not going anywhere" (Saltmarrow #112) is staying put, not a move.
    r"not\s+going\s+to|not\s+(?:going|leaving|moving|coming)\s+anywhere|unable\s+to|shouldn" + _AP + r"?t|"
    r"should\s+not|refuse\s+to)\b"
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
    plain = _QUOTE_RE.sub(" ", str(sentence or ""))
    return bool(_PAID_RE.search(plain) or _PAID_PUT_RE.search(plain))


# A payment with no number (7B run 5): "You pay her the agreed price" (T47),
# "counting out the gold pieces he asks for" (T48), "you pay for the lantern".
_UNPRICED_PAYMENT_RE = re.compile(
    r"\byou\s+(?:\w+ly\s+)?(?:pay|paid)\s+(?:(?:him|her|them|the\s+\w+|(?-i:[A-Z][\w'’-]*))\s+)?"
    r"(?:the\s+|what\s+)?(?:(?:agreed|asking|full|fair|requested|quoted|stated|usual)\s+)?"
    r"(?:price|sum|fee|amount|cost|toll|rate|coin|coins|gold|money|due)\b"
    r"|\byou\s+(?:\w+ly\s+)?(?:pay|paid)\s+(?:him|her|them|(?-i:[A-Z][\w'’-]*))\s*(?=[,.;!?]|\s+(?:and|for|then)\b)"
    r"|\byou\s+(?:\w+ly\s+)?(?:pay|paid)\s+for\s+(?:it|them|the\s+\w+|your\s+\w+)"
    # "Counting out" is the player's only in a clause of theirs: "Alditha's
    # fingers tap the counter, counting out the twenty-two gold coins she'd
    # promised" took 2 gold from the player (8B run 98, T4).
    r"|\b(?:you\s+(?:\w+ly\s+)?count(?:ed)?|you\b(?:(?!\b(?:he|she|they|his|her|their)\b)[^.!?\n]){0,60}?,\s*counting)"
    r"\s+out\s+(?:the|what|his|her|their)\b[^.!?\n]{0,40}?"
    r"\b(?:asks?|asked|owed?|price|gold|coins?|pieces|fee|due)\b",
    re.I,
)


def shows_unpriced_payment(text: str) -> bool:
    """The player pays in the narration (outside quotes) and the clause names no sum."""
    plain = _QUOTE_RE.sub(" ", str(text or ""))
    return bool(_UNPRICED_PAYMENT_RE.search(plain))


# Coin reaching the player with no number: "Abel hands over a moderate bag of
# coin for your efforts" (T72), "reaching into his pouch and handing you the
# coins" (T55), "You take the coins" (T41). The giver is someone else: a give
# right after "you" is the player paying.
_COIN_HANDED_RE = re.compile(
    r"\b(?P<verb>hands?|handed|handing|gives|gave|giving|pays|paid|paying|tosses|tossed|tossing|passes|passed|passing|"
    r"slides|slid|sliding|presses|pressed|pressing|counts\s+out|counted\s+out|counting\s+out|drops|dropped|dropping|"
    # 7B run 10, T7: "She places a handful of polished coins in your palm".
    r"places|placed|placing|puts|putting|sets|setting|lays|laid|laying|tips|tipped|tipping)\s+"
    r"(?P<rest>(?:you\s+|over\s+(?:to\s+you\s+)?)?[^.!?\n]{0,50})",
    re.I,
)
_COIN_TAKEN_RE = re.compile(
    r"\byou\s+(?:\w+ly\s+)?(?:take|took|pocket|pocketed|accept|accepted|collect|collected|receive|received|"
    r"sweep\s+up|swept\s+up)\s+(?:the|your|his|her|their)\s+(?:\w+\s+)?(?:coins?|gold|money|wages?|pay|payment|purse|pouch)\b",
    re.I,
)
_COIN_STUFF_RE = re.compile(
    # Silver and copper are other units, not the gold purse (see _COIN above).
    r"(?<!silver\s)(?<!copper\s)\b(?:coins?|gold|money|wages?|(?:purse|pouch|bag|sack|handful|stack|pile)\s+of\s+(?:coins?|gold|money))\b",
    re.I,
)
_FOR_YOU_RE = re.compile(
    r"^you\b|\bto\s+you\b|\bfor\s+your\s+(?:efforts?|work|trouble|help|labou?r|time|services?|pains)\b|"
    r"\byour\s+(?:wages?|pay|payment|share|cut|due|earnings|reward)\b|"
    r"\b(?:in|into|onto)\s+your\s+(?:open\s+|outstretched\s+|waiting\s+)?(?:palm|palms|hand|hands|purse|pouch)\b",
    re.I,
)
_BAND_WORDS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("trivial", re.compile(r"\b(?:a\s+few|few|couple|meagre|meager|trivial|paltry)\b", re.I)),
    ("small", re.compile(r"\b(?:small|modest|little|light|thin)\b", re.I)),
    ("moderate", re.compile(r"\b(?:moderate|fair|decent|tidy|reasonable)\b", re.I)),
    ("large", re.compile(r"\b(?:large|hefty|heavy|fat|generous|fine|good|sizeable|sizable|full)\b", re.I)),
    ("huge", re.compile(r"\b(?:huge|fortune|enormous|vast)\b", re.I)),
)


def coin_handed_to_player(text: str) -> dict[str, Any] | None:
    """Coin the narration shows reaching the player, outside quotes: {"span", "band"} or None.

    ``band`` is the size word the prose used ("a moderate bag of coin" ->
    "moderate"), or "" when it used none.
    """
    plain = _QUOTE_RE.sub(" ", str(text or ""))
    for match in _COIN_HANDED_RE.finditer(plain):
        before = plain[max(0, match.start() - 24):match.start()]
        if re.search(r"\byou\s+(?:\w+ly\s+)?$", before, re.I):
            continue  # "you hand over three coins": the player pays
        if match.group("verb").lower().endswith("ing") and _nearest_doer(plain[:match.start()]) == "you":
            continue  # "You comment, counting out the gold": still the player
        rest = match.group("rest")
        stuff = _COIN_STUFF_RE.search(rest)
        if not stuff:
            continue
        if not _FOR_YOU_RE.search(rest):
            continue
        span = (match.group("verb") + " " + rest)[:120]
        return {"span": span, "band": _band_word(rest[: stuff.end() + 1])}
    taken = _COIN_TAKEN_RE.search(plain)
    if taken:
        return {"span": taken.group(0)[:120], "band": _band_word(taken.group(0))}
    return None


# A purse handed over whose contents the prose never names: "He hands you a
# small pouch. 'This should cover it.'" (7B run 30, T5). Read only when the
# turn's own GRANT says the thing is coin; a pouch alone could hold anything.
_PURSE_HANDED_RE = re.compile(r"\b(?:purse|pouch|coin[\s-]?purse|money[\s-]?bag|bag|sack|packet)\b", re.I)


def purse_handed_to_player(text: str) -> dict[str, Any] | None:
    """A purse or pouch the narration shows handed to the player, outside quotes: {"span", "band"} or None."""
    plain = _QUOTE_RE.sub(" ", str(text or ""))
    for match in _COIN_HANDED_RE.finditer(plain):
        before = plain[max(0, match.start() - 24):match.start()]
        if re.search(r"\byou\s+(?:\w+ly\s+)?$", before, re.I):
            continue
        if match.group("verb").lower().endswith("ing") and _nearest_doer(plain[:match.start()]) == "you":
            continue
        rest = match.group("rest")
        thing = _PURSE_HANDED_RE.search(rest)
        if not thing or not _FOR_YOU_RE.search(rest):
            continue
        return {"span": (match.group("verb") + " " + rest)[:120], "band": _band_word(rest[: thing.end() + 1])}
    return None


def _nearest_doer(before: str) -> str:
    """"you", "other" or "" for the last subject in the sentence before a participle."""
    sentence = re.split(r"[.!?\n]", before)[-1]
    best = ""
    best_at = -1
    for m in re.finditer(r"\b(you|he|she|they)\b", sentence, re.I):
        best, best_at = ("you" if m.group(1).lower() == "you" else "other"), m.start()
    for m in re.finditer(r"(?<!^)(?<![.!?]\s)\b(?-i:[A-Z][a-z][\w'’-]*)\b", sentence):
        if m.start() > best_at and m.group(0) not in {"You", "I"}:
            best, best_at = "other", m.start()
    return best


_COUNTED_COIN_RE = re.compile(
    r"\b(?P<count>a\s+single|a\s+pair\s+of|an?|single|\d{1,5}|"
    + "|".join(sorted((w.replace(" ", r"\s+") for w in _NUMBER_WORDS), key=len, reverse=True))
    + r")\s+(?P<mods>(?:[\w'’-]+\s+){0,2}?)(?:gold\s+)?(?:coins?|gold\s+pieces?|pieces?\s+of\s+gold|crowns?)\b",
    re.I,
)
# Words that make a count vague: "a handful of coins" is not one coin.
_VAGUE_COUNT_WORDS = frozenset({
    "handful", "fistful", "bag", "purse", "pouch", "sack", "stack", "pile", "heap", "few", "couple",
    "some", "number", "lot", "more", "of", "silver", "copper", "rolls", "roll",
})


def counted_coins(text: str) -> int | None:
    """The number of coins a handed-over span states: "hands you a coin" -> 1, "two coins" -> 2.

    7B run 11, T2: "Iseult nods and hands you a coin" rolled a small band
    (+7). A count the prose states is the amount, one gold a coin; a vague
    amount ("a handful of coins", "a few coins", "a bag of coin") is None and
    takes a band. Silver and copper are other units (None).
    """
    # "You take the coin" after "We'll pay you a small coin" is one coin, not a
    # rolled band (7B run 40, T2: +10).
    if re.search(r"\bthe\s+(?:(?:small|single|lone|one|little|thin|worn|old|silver|copper|gold)\s+)?coin\b(?!s)",
                 str(text or ""), re.I) and not re.search(r"\b(?:silver|copper)\s+coin\b", str(text or ""), re.I):
        return 1
    for match in _COUNTED_COIN_RE.finditer(str(text or "")):
        mods = {w.lower() for w in re.findall(r"[\w'’-]+", match.group("mods") or "")}
        if mods & _VAGUE_COUNT_WORDS:
            continue
        count = " ".join(match.group("count").lower().split())
        if count in {"a", "an", "one", "a single", "single"}:
            return 1
        if count == "a pair of":
            return 2
        value = _number(count)
        if value:
            return value
    return None


def _band_word(text: str) -> str:
    for band, pattern in _BAND_WORDS:
        if pattern.search(text):
            return band
    return ""


# The player's own line puts the money down, as a deed: "I put two gold on the
# bar for the room" (T94), "I pay him three coins". Not an offer to haggle over:
# "I'll give you 3 gold for that", "would you take 4 gold?".
_PAYS_OUTRIGHT_RE = re.compile(
    r"(?:^|[.;!]\s*|\band\s+|\bthen\s+)i\s+(?:\w+ly\s+)?(?:put|set|lay|place|slide|toss|pay|hand(?:\s+over)?|"
    r"count\s+out|leave|drop)\s+(?:(?:him|her|them|(?-i:[A-Z][\w'’-]*))\s+)?(?:(?:my|the)\s+)?"
    r"(?:(?:last|remaining|only|spare)\s+)?" + _AMOUNT + r"\s+" + _COIN,
    re.I,
)
# The same deed after "and" in an "I ..." sentence: "I set a copper-worth of
# thought aside and put one gold on the counter" (7B run 18, T5).
_PAYS_OUTRIGHT_AND_RE = re.compile(
    r"\bi\s+[^.!?\n]{0,80}?\band\s+(?:\w+ly\s+)?(?:put|set|lay|place|slide|toss|pay|hand(?:\s+over)?|"
    r"count\s+out|leave|drop)\s+(?:(?:him|her|them)\s+)?(?:(?:my|the)\s+)?"
    r"(?:(?:last|remaining|only|spare)\s+)?" + _AMOUNT + r"\s+" + _COIN,
    re.I,
)


def player_pays_outright(own_line: str) -> int | None:
    """Gold the player's line hands over as a deed (not an offer), outside the player's quoted speech."""
    text = _QUOTE_RE.sub(" ", str(own_line or ""))
    for match in list(_PAYS_OUTRIGHT_RE.finditer(text)) + list(_PAYS_OUTRIGHT_AND_RE.finditer(text)):
        clause_start = max(text.rfind(mark, 0, match.start()) for mark in (",", ".", ";", "!", "?", "\n"))
        if _NEGATION_RE.search(text[clause_start + 1: match.start() + 4]):
            continue
        tail = text[match.end():match.end() + 60]
        if "?" in tail.split(".")[0]:
            continue  # "I put two gold down, is that enough?" asks
        value = _match_number(match)
        if value:
            return value
    return None


# The player's own line only puts coin away: "I pocket the two gold" (7B run
# 6, T10, the line after Oldfield paid). "The", "my", "those" name coin
# already in hand; "I pocket two gold from the till" is a take, not this.
_PUTS_AWAY_COIN_RE = re.compile(
    r"(?:^|[.;!]\s*|\band\s+|\bthen\s+)i\s+(?:\w+ly\s+)?(?:pocket|stow|tuck(?:\s+away)?|put\s+away|slip|count|"
    r"stash|bag|keep)\s+(?:the|my|those|these|that|this|his|her|their)\s+(?:" + _AMOUNT + r"\s+)?"
    r"(?:(?:small\s+|heavy\s+|few\s+)?(?:pouch|purse|bag)\s+of\s+)?" + _COIN
    + r"(?![^.!?\n]{0,40}\b(?:from|off|out\s+of)\s+(?:the|a|his|her|their)\s+(?:till|table|counter|chest|box|floor|ground|body|corpse)\b)",
    re.I,
)


def player_puts_away_coin(own_line: str) -> int | None:
    """The player's line (outside their quoted speech) only puts coin already in hand away.

    Returns the amount it names, 0 when it names none ("I pocket the coins"),
    or None when the line does not do that.
    """
    text = _QUOTE_RE.sub(" ", str(own_line or ""))
    match = _PUTS_AWAY_COIN_RE.search(text)
    if not match:
        return None
    return _match_number(match) or 0


def coin_reached_player(text: str, amount: int = 0) -> bool:
    """Whether a scene shows coin reaching the player (the named amount, when given)."""
    said = stated_coin_amounts(text)
    if amount and amount in said["received"]:
        return True
    if coin_handed_to_player(text) is None and not said["received"]:
        return False
    return not amount or amount in coin_mentions(text)


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
    # A dive on a wreck rolled nothing and finished no step (8B run 145, T9).
    ("swim", ("swim", "dive")),
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
    "swim": {"skill": "athletics", "kind": "physical", "minutes": 20},
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


# --- Pronouns keep the sex the story set (8B #55) ---------------------------
# "Min is a woman in T1/T2 and 'his weathered face' in T4." The pin is in the
# contract, and the 8B still drifts. Only the sure case is mended: a sentence
# about one pinned person and nobody else (or the sentence right after it),
# outside speech, that uses only the other set. Anything with a second person
# in it, a "the man"/"the boy", or both sets is left as written.
_PERSON_NOUN_RE = re.compile(
    r"\b(?:man|men|woman|women|boy|boys|girl|girls|lad|lass|child|children|kid|baby|father|mother|son|daughter|"
    r"brother|sister|husband|wife|uncle|aunt|king|queen|prince|princess|lord|lady|sir|madam|gentleman|fellow|"
    r"stranger|figure|guard|guards|soldier|sailor|merchant|priest|priestess|widow|keeper|clerk|captain|youth|"
    r"elder|innkeeper|smith|fisherman|fishwife|someone|somebody|anyone|everyone|nobody|people|crowd|others?)\b",
    re.I,
)
_SETS = {
    "he": {"subject": "he", "object": "him", "possessive": "his", "reflexive": "himself"},
    "she": {"subject": "she", "object": "her", "possessive": "her", "reflexive": "herself"},
}
_WORDS_OF = {
    "he": re.compile(r"\b(?:he|him|his|himself)\b", re.I),
    "she": re.compile(r"\b(?:she|her|hers|herself)\b", re.I),
}
_OBJECT_FOLLOWERS = frozenset({
    "the", "a", "an", "some", "this", "that", "these", "those", "your", "my", "his", "their", "our", "its", "one",
    "two", "three", "no", "every", "each", "any", "all", "more", "what", "something", "anything", "nothing",
    "everything", "and", "or", "but", "to", "for", "with", "in", "into", "on", "onto", "at", "by", "from", "of",
    "off", "out", "up", "down", "over", "away", "back", "aside", "close", "closer", "again", "now", "too", "as",
    "then", "a", "go", "be", "is", "was", "you", "if", "so", "until", "while", "before", "after", "about",
})
_NOT_A_NOUN_AFTER_HIS = frozenset({
    "and", "or", "but", "to", "for", "with", "in", "on", "at", "by", "from", "of", "is", "was", "too", "now",
    "alone", "again", "as", "then",
})


def _mask_speech(text: str) -> str:
    """The text with quoted speech blanked to spaces, same length (a quote ends at a line break)."""
    out: list[str] = []
    inside = False
    for ch in text:
        if ch == "\n":
            inside = False
            out.append(ch)
            continue
        if ch == '"':
            inside = not inside
            out.append(" ")
            continue
        if ch == "“":
            inside = True
            out.append(" ")
            continue
        if ch == "”":
            inside = False
            out.append(" ")
            continue
        out.append(" " if inside else ch)
    return "".join(out)


def _next_word(text: str, end: int) -> str:
    match = re.match(r"\s*([A-Za-z']+)", text[end:])
    if not match or re.match(r"\s*[.,;:!?—-]", text[end:]):
        return ""
    return match.group(1).lower()


def _swap(word: str, target: str, text: str, end: int) -> str:
    low = word.lower()
    to = _SETS[target]
    if target == "she":
        if low == "his":
            nxt = _next_word(text, end)
            new = to["possessive"] if nxt and nxt not in _NOT_A_NOUN_AFTER_HIS else "hers"
        else:
            new = {"he": to["subject"], "him": to["object"], "himself": to["reflexive"]}.get(low, low)
    else:
        if low == "her":
            nxt = _next_word(text, end)
            new = to["object"] if (not nxt or nxt in _OBJECT_FOLLOWERS) else to["possessive"]
        else:
            new = {"she": to["subject"], "hers": to["possessive"], "herself": to["reflexive"]}.get(low, low)
    return new[:1].upper() + new[1:] if word[:1].isupper() else new


_GENDERED_THING_RE = re.compile(
    r"\b(?:mare|mares|filly|cow|cows|ewe|hen|sow|doe|nanny|stallion|colt|gelding|bull|ram|boar|buck|horse|horses|"
    r"pony|mule|donkey|dog|hound|bitch|cat|goat|ship|boat|skiff|vessel|barge|sloop|cutter|ketch)\b",
    re.I,
)


def repair_pinned_pronouns(
    text: str, cast: list[dict[str, Any]], *, not_people: tuple[str, ...] | list[str] = ()
) -> tuple[str, list[dict[str, Any]]]:
    """Mend a pinned he/she that flipped, in sentences only about that one person.

    ``cast``: [{"names": ["Min Yardley", "Min"], "key": "she"}, ...]. ``not_people``:
    capitalised names that are places or things, so they do not count as a
    second person. Returns the text and one entry per mended sentence.
    """
    source = str(text or "")
    people = []
    for entry in cast or []:
        key = str((entry or {}).get("key") or "").strip().lower()
        names = [str(n).strip() for n in (entry or {}).get("names") or [] if str(n or "").strip()]
        if key in _SETS and names:
            pattern = re.compile(r"\b(?:" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + r")\b")
            people.append({"name": names[0], "key": key, "re": pattern})
    if not source or not people:
        return source, []
    known_caps = set()
    for entry in cast or []:
        for name in (entry or {}).get("names") or []:
            known_caps.update(w for w in re.findall(r"[A-Z][\w'’-]*", str(name)))
    for name in not_people or ():
        known_caps.update(w for w in re.findall(r"[A-Z][\w'’-]*", str(name)))
    known_caps.update({"You", "Your", "Yours", "I", "God", "Gods"})
    masked = _mask_speech(source)
    pieces: list[tuple[int, int]] = []
    start = 0
    for match in re.finditer(r"(?<=[.!?])[\"”’)]*[ \t]+|\n+", masked):
        pieces.append((start, match.start()))
        start = match.end()
    pieces.append((start, len(masked)))
    edits: list[tuple[int, int, str]] = []
    fixes: list[dict[str, Any]] = []
    focus: dict[str, Any] | None = None
    carried = 0
    previous_end = 0
    for begin, end in pieces:
        if "\n" in masked[previous_end:begin]:
            focus = None
        previous_end = end
        plain = masked[begin:end]
        if not plain.strip():
            continue
        named = [p for p in people if p["re"].search(plain)]
        stripped = plain.lstrip()
        lead = len(plain) - len(stripped)
        # An animal or a boat can be the "her": "Odo finishes grooming the mare
        # and steps back, patting her gently" became "patting his" (7B run 39, T2).
        stranger = bool(_PERSON_NOUN_RE.search(plain) or _GENDERED_THING_RE.search(plain))
        if not stranger:
            # A code tag is not a second person: "She gestures towards the inn,
            # The Gilded Heron [[L2]]" (7B run 20, T1) kept the wrong "She".
            capped = re.sub(r"\[\[[^\]]*\]\]", lambda m: " " * len(m.group(0)), plain)
            for cap in re.finditer(r"\b[A-Z][\w'’-]*", capped):
                if cap.start() == lead or cap.group(0) in known_caps:
                    continue
                if cap.group(0).lower() in {"he", "she", "his", "her", "him", "it", "they", "the", "a", "an"}:
                    continue
                stranger = True
                break
        # Both sets of pronouns in one sentence: a second person is in it. "She's
        # not Elias [[A]], but she knows him well" set the focus on Elias, and
        # the woman's next "she says, her voice" became "he says, his voice"
        # (8B run 135, T7).
        if len(named) == 1 and not stranger:
            has_he = bool(re.search(r"\b(?:he|him|his|himself)\b", plain, re.I))
            has_she = bool(re.search(r"\b(?:she|her|hers|herself)\b", plain, re.I))
            if has_he and has_she:
                focus = None
                continue
        if len(named) == 1 and not stranger:
            focus, carried, person = named[0], 0, named[0]
        elif not named and not stranger and focus is not None and carried < 1:
            carried += 1
            person = focus
        else:
            focus = None
            continue
        target = person["key"]
        wrong = "she" if target == "he" else "he"
        if _WORDS_OF[target].search(plain) or not _WORDS_OF[wrong].search(plain):
            continue
        changed = []
        for word in _WORDS_OF[wrong].finditer(plain):
            new = _swap(word.group(0), target, plain, word.end())
            edits.append((begin + word.start(), begin + word.end(), new))
            changed.append(f"{word.group(0)}->{new}")
        fixes.append({"name": person["name"], "pronouns": target, "changed": changed, "sentence": source[begin:end].strip()[:160]})
    if not edits:
        return source, []
    out = source
    for a, b, new in sorted(edits, reverse=True):
        out = out[:a] + new + out[b:]
    return out, fixes


# ---------------------------------------------------------------------------
# Op, packet and meta text in the prose (7B run 5, #131 and #83)
# ---------------------------------------------------------------------------

# A DSL op written out as prose: "The GOAL is to finish the task." The op
# keywords are capitals in the ask; prose never capitalises them.
_OP_KEYWORD_LINE_RE = re.compile(r"^\s*The (?:GOAL|FOCUS|NPC|SCENE|PLACE|ROLE|MOOD) is\b")
# A roster label left on its own line: "Roger [[A]]", "The Blind Pike [[L7]]",
# "Abel Hollis [[D]] (D) - woodcutter (on duty (shift 08:00-18:00))". A name
# (a few capitalised words) and a code, then at most a parenthetical and a
# dash tail, with no sentence end and no speech. A list line ("- Name [[D]]:
# three barrels") starts with its marker and is not touched.
_LABEL_LINE_RE = re.compile(
    r"^\s*(?:The\s+)?[A-Z][\w'’-]*(?:\s+[A-Z][\w'’-]*){0,4}\s*\[\[[A-Z][A-Z0-9]{0,4}\]\]"
    r"(?:\s*\((?:[^()]|\([^()]*\))*\))*"
    r"(?:\s*[-–—]\s*[^.!?\"“\n]*)?\s*$"
)
# Stage directions about the scene itself, not about what happens in it.
_STAGE_SENTENCE_RE = re.compile(
    # A shift to somewhere, or a shift and nothing else, is about the scene as
    # a construct. "The scene shifts slightly, the light from the oil lamps
    # shifting with ..." describes the room and stays (7B run 10, T3).
    # 7B run 30, T0: "The tannery and the mole catcher offer two concrete
    # hooks: assist in mole control or ignore him." (the prompt's own word).
    r"^.*?\b(?:concrete\s+hooks?|(?:offer|offers|present|presents|provide|provides)\s+(?:\w+\s+){0,2}hooks?\s*:)"
    r"|^\s*The\s+(?:focus|scene)\s+(?:now\s+)?(?:shifts|changes)(?:\s+\w+ly)?"
    r"(?=\s*[.!]|\s+(?:to|towards?|back|again|away|from|elsewhere)\b)"
    r"|^\s*The\s+(?:focus|scene)\s+(?:now\s+)?is\s+about\s+to\s+(?:change|shift)\b"
    # 7B run 6, T6: "The scene ends with you standing in the town square, the
    # deal made and the clock ticking."
    r"|^\s*The\s+scene\s+(?:now\s+)?(?:ends|closes|draws\s+to\s+a\s+close|comes\s+to\s+an?\s+(?:end|close))\b"
    # 7B run 7, T3: "The scene is focused on the job of cleaning the decks,
    # with Oriel Rendle [[A]] as the central figure."
    r"|^\s*The\s+(?:scene|focus)\s+(?:is|remains|stays)\s+(?:now\s+)?(?:focused|centred|centered|fixed)\s+on\b"
    # 7B run 18, T1: "The conversation with Wymarc ends here."
    r"|^\s*The\s+(?:conversation|exchange|scene)(?:\s+with\s+[A-Z][\w'’-]*(?:\s+[A-Z][\w'’-]*)?)?"
    r"\s+(?:ends|is\s+over|closes)\s+(?:here|now|for\s+now)\b",
    re.I,
)
# A quotation closed twice: '"Thanks, Oldfield.""' (7B run 6, T9).
_DOUBLE_CLOSE_RE = re.compile(r"([.!?,…—-])([\"”])[\"”](?=\s|$)")
# The engine's status line: "You are fine, with 19/20 health."
_STATUS_SENTENCE_RE = re.compile(r"\bwith\s+\d+\s*/\s*\d+\s+health\b", re.I)
# Packet keys and item ids: open_offers, brass_key.
_SNAKE_RE = re.compile(r"\b[a-z]+(?:_[a-z]+)+\b")
# Markdown emphasis, which the page shows as raw marks: _Sea Sprite_, *Saltsort*.
_MD_BOLD_RE = re.compile(r"\*\*([^*\n]+?)\*\*")
_MD_STAR_RE = re.compile(r"(?<![\w*])\*([^*\s][^*\n]*?)\*(?![\w*])")
_MD_UNDER_RE = re.compile(r"(?<![\w])_([^_\s][^_\n]*?)_(?![\w])")
# A play-script speaker label: 'Dunstan [[A]]: "I'll fetch a few more."' (7B
# run 30, T6; run 5 T14, T47, T90). It becomes 'Dunstan [[A]] says, "..."'.
_SCRIPT_LABEL_RE = re.compile(
    r"(?m)^(?P<lead>[ \t]*)(?P<who>(?!You\b)[A-Z][\w'’-]+(?:[ \t]+[A-Z][\w'’-]+){0,2}(?:[ \t]*\[\[[A-Z][A-Z0-9]{0,4}\]\])?)"
    # 'Maud Venn [[A]], tallyman: "Good morning."' (run 32 T0): the role goes with the colon.
    r"(?:,[ \t]*(?:the[ \t]+)?[a-z][a-z'’ -]{0,40}?)?"
    r"[ \t]*:[ \t]*(?P<q>[\"“])"
)
# A full stop closing a line that a lowercase tag follows: '...before noon."
# you ask Dunstan' (7B run 30, T8) reads '...before noon," you ask Dunstan'.
_PERIOD_BEFORE_TAG_RE = re.compile(
    r"(?P<pre>[^\s,?!.…])\.(?P<q>[\"”])(?P<tag>\s+(?:you|he|she|they)\s+(?:say|says|ask|asks|reply|replies|answer|answers|"
    r"add|adds|call|calls|murmur|murmurs|whisper|whispers)\b)"
)
# One underscore glued to the front of a plain word: "Is the _hull worth patching" (7B run 29).
_STRAY_UNDERSCORE_RE = re.compile(r"(?<![\w\[_])_([A-Za-z][a-z]+)\b(?!_)")
# An attitude label pasted as an adjective: "gives you a Dismissive look".
_ATTITUDE_WORDS = (
    "Antagonistic", "Apprehensive", "Condescending", "Cordial", "Dismissive", "Neutral", "Warm", "Hostile",
)
_ATTITUDE_LABEL_RE = re.compile(
    r"\b((?:a|an|the|his|her|their)\s+)(" + "|".join(_ATTITUDE_WORDS) + r")(\s+(?:\w+\s+)?"
    r"(?:look|glance|stare|smile|nod|tone|expression|air|frown|scowl|shrug|silence|manner|voice)s?)\b"
)
# A band word used as an amount of coin: "a moderate bag of coin".
_BAND_COIN_RE = re.compile(
    r"\b(?:a|an)\s+(?:trivial|small|moderate|large|huge)\s+(?:bag|purse|pouch|sum|amount|handful|pile|stack)"
    r"\s+of\s+(?:coins?|gold)\b",
    re.I,
)


def repair_meta_leaks(text: str) -> tuple[str, list[dict[str, Any]]]:
    """
    Narrow repairs of exact engine shapes in the prose; the rest is left as written.

    Lines that are an op or a roster label go; stage-direction and status-line
    sentences go; packet keys lose their underscores; markdown marks go and
    keep their words; a pasted attitude label is lowercased. Returns the text
    and one entry per repair. Nothing is cut when the cut would leave no prose.
    """
    source = str(text or "")
    if not source.strip():
        return source, []
    fixes: list[dict[str, Any]] = []
    lines = source.split("\n")
    kept_lines: list[str] = []
    for line in lines:
        if _OP_KEYWORD_LINE_RE.match(line):
            fixes.append({"why": "op_line", "text": line.strip()[:160]})
            continue
        if line.strip() and "[[" in line and _LABEL_LINE_RE.match(line):
            fixes.append({"why": "label_line", "text": line.strip()[:160]})
            continue
        kept_lines.append(line)
    out = re.sub(r"\n{3,}", "\n\n", "\n".join(kept_lines)).strip()
    if not out:
        return source, []
    # The engine's clock and duty shifts, outside speech: "It is morning,
    # 08:00." (7B run 40, T0), "the sun high in the clear sky at 08:30" (run
    # 29), "on duty from 08:00 to 18:00" and "(on duty (shift 08:00-18:00))"
    # (run 5, T12). The words around them stay.
    clock_pieces = re.split(r"(\"[^\"\n]*\"|“[^”\n]*”)", out)
    for index in range(0, len(clock_pieces), 2):
        piece = clock_pieces[index]
        for pattern in (
            r"\s*\((?:on|off)\s+duty\b[^()]*(?:\([^()]*\))?[^()]*\)",
            r",?\s+(?:on|off)\s+duty\s+from\s+\d{1,2}:\d{2}\s+(?:to|until|-)\s+\d{1,2}:\d{2}",
            r",\s*\d{1,2}:\d{2}(?=[.!?,;])",
            r"\s+at\s+\d{1,2}:\d{2}(?=[.!?,;])",
            # After a dash or "of": "A distant bell rings, marking the hour—08:17." (8B run 125, T3).
            r"\s*(?:[—–]|\s-|:|\bof\b|\bis\b)\s*\d{1,2}:\d{2}(?=[.!?,;])",
        ):
            new, n = re.subn(pattern, "", piece, flags=re.I)
            if n:
                fixes.append({"why": "engine_clock", "count": n})
                piece = new
        clock_pieces[index] = piece
    out = "".join(clock_pieces)

    def _meta_sentence(sentence: str) -> bool:
        return bool(_STAGE_SENTENCE_RE.match(sentence) or _STATUS_SENTENCE_RE.search(sentence))

    if any(_meta_sentence(s) for _a, _b, s in sentence_spans(out)):
        trimmed, dropped = drop_sentences(out, _meta_sentence, floor=1)
        if dropped:
            out = trimmed
            for sentence in dropped:
                why = "status_line" if _STATUS_SENTENCE_RE.search(sentence) else "stage_direction"
                fixes.append({"why": why, "text": sentence[:160]})

    for pattern, why in ((_MD_BOLD_RE, "markdown"), (_MD_STAR_RE, "markdown"), (_MD_UNDER_RE, "markdown")):
        found = [m.group(0) for m in pattern.finditer(out)]
        if found:
            out = pattern.sub(r"\1", out)
            fixes.append({"why": why, "text": ", ".join(found[:4])[:160]})
    scripted = [m.group("who") for m in _SCRIPT_LABEL_RE.finditer(out)]
    if scripted:
        out = _SCRIPT_LABEL_RE.sub(lambda m: f"{m.group('lead')}{m.group('who')} says, {m.group('q')}", out)
        fixes.append({"why": "script_label", "text": ", ".join(scripted[:4])[:160]})
    tagged = [m.group(0) for m in _PERIOD_BEFORE_TAG_RE.finditer(out)]
    if tagged:
        out = _PERIOD_BEFORE_TAG_RE.sub(r"\g<pre>,\g<q>\g<tag>", out)
        fixes.append({"why": "period_before_tag", "text": ", ".join(tagged[:4])[:160]})
    stray = [m.group(0) for m in _STRAY_UNDERSCORE_RE.finditer(out)]
    if stray:
        out = _STRAY_UNDERSCORE_RE.sub(r"\1", out)
        fixes.append({"why": "stray_underscore", "text": ", ".join(stray[:4])[:160]})
    keys = [m.group(0) for m in _SNAKE_RE.finditer(out)]
    if keys:
        out = _SNAKE_RE.sub(lambda m: m.group(0).replace("_", " "), out)
        fixes.append({"why": "packet_key", "text": ", ".join(keys[:4])[:160]})
    doubled = [m.group(0) for m in _DOUBLE_CLOSE_RE.finditer(out)]
    if doubled:
        out = _DOUBLE_CLOSE_RE.sub(r"\1\2", out)
        fixes.append({"why": "doubled_quote", "text": ", ".join(doubled[:4])})
    labels = [m.group(2) for m in _ATTITUDE_LABEL_RE.finditer(out)]
    if labels:
        out = _ATTITUDE_LABEL_RE.sub(lambda m: m.group(1) + m.group(2).lower() + m.group(3), out)
        fixes.append({"why": "attitude_label", "text": ", ".join(labels[:4])})
    # A bracket glued to a word: "up to the(guild's storehouse", "I owe the(guild)
    # a winter's credit" (8B runs 63 and 79).
    glued = [m.group(0) for m in re.finditer(r"\b(?:the|a|an|your|his|her|their|my|our)\((?=[a-z])", out)]
    if glued:
        out = re.sub(r"\b(the|a|an|your|his|her|their|my|our)\(([a-z][\w'’-]*)\)?", r"\1 \2", out)
        fixes.append({"why": "glued_bracket", "text": ", ".join(glued[:4])})
    # The packet's word for the reader, outside speech: "pushed a stack of papers
    # toward the player", "the player's patched tunic" (8B run 68, T2).
    pieces = re.split(r"(\"[^\"\n]*\"|“[^”\n]*”)", out)
    named_player = False
    for index in range(0, len(pieces), 2):
        piece = pieces[index]
        new = re.sub(r"\bthe player['’]s\b", "your", piece)
        new = re.sub(r"\bThe player['’]s\b", "Your", new)
        new = re.sub(r"\bthe player\b", "you", new)
        new = re.sub(r"\bThe player\b", "You", new)
        if new != piece:
            named_player = True
            pieces[index] = new
    if named_player:
        out = "".join(pieces)
        fixes.append({"why": "the_player", "text": "the player -> you"})
    return out, fixes


# Part-of-day words that say what time it is *now* in the narration (#132).
# Only these shapes are read: the present moment ("as the night progresses",
# "the night is still young", "the evening light", "it is morning"). Speech is
# masked first; people may talk about other times.
_PART_WORDS = r"night|evening|morning|afternoon|dawn|dusk|midday|noon|midnight"
_CLOCK_PHRASE_RE = re.compile(
    r"\b(?:"
    r"as\s+the\s+(?P<a>night|evening|morning|afternoon)\s+(?:progresses|wears\s+on|deepens|draws\s+on|goes\s+on|grows\s+late|settles\s+in)"
    r"|the\s+(?P<b>night|evening|morning|afternoon)\s+is\s+(?:still\s+|now\s+)?(?:young|calm|quiet|still|cool|warm|cold|dark|bright|clear|late|early)\b"
    r"|(?:it\s+is|it['’]s)\s+(?:now\s+|already\s+|still\s+)?(?:early\s+|late\s+)?(?P<c>" + _PART_WORDS + r")\b(?!\s+(?:when|before|after))"
    r"|the\s+(?:early\s+|late\s+)?(?P<d>" + _PART_WORDS + r")\s+(?P<noun>light|sun|sunlight|air|chill|breeze|mist|fog|shadows|glow|stillness|quiet|hush|bustle|crowd|rush|darkness|gloom|sky)"
    # "a comforting presence in the cool evening" at 13:31 (7B run 27, T7).
    r"|(?:in|into|through)\s+the\s+(?:cool|warm|cold|quiet|still|dark|crisp|soft|grey|gray|mild|bright)\s+"
    r"(?P<e>evening|night|morning|afternoon)\b(?!\s+(?:before|after|when|of|to\s+come))"
    r")",
    re.I,
)
# Hours (0-23) at which each word can describe the present; generous edges.
_PART_HOURS = {
    "morning": set(range(4, 13)),
    "dawn": set(range(4, 9)),
    "noon": set(range(11, 15)),
    "midday": set(range(11, 15)),
    "afternoon": set(range(11, 19)),
    "evening": set(range(16, 23)),
    "dusk": set(range(16, 22)),
    "night": set(range(19, 24)) | set(range(0, 6)),
    "midnight": {23, 0, 1},
}
_DAYLIGHT_NOUNS = {"sun", "sunlight"}


def _clock_part(hour: int) -> str:
    hour = int(hour) % 24
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 21:
        return "evening"
    return "night"


def clock_clashes(text: str, hour: int) -> list[dict[str, Any]]:
    """Present-moment part-of-day phrases outside quotes that the clock's hour rules out."""
    source = str(text or "")
    masked = _mask_speech(source)
    out: list[dict[str, Any]] = []
    for match in _CLOCK_PHRASE_RE.finditer(masked):
        group = next(g for g in ("a", "b", "c", "d", "e") if match.group(g))
        word = match.group(group).lower()
        if int(hour) % 24 in _PART_HOURS.get(word, set(range(24))):
            continue
        out.append({
            "phrase": source[match.start():match.end()],
            "word": word,
            "start": match.start(group),
            "end": match.end(group),
            "noun": (match.group("noun") or "").lower(),
        })
    return out


def repair_clock_words(text: str, hour: int) -> tuple[str, list[dict[str, Any]]]:
    """
    Swap a part-of-day word that contradicts the clock for the clock's own (#132).

    "As the night progresses" at 08:20 becomes "As the morning progresses";
    "the evening light" at noon becomes "the afternoon light". Only the one word
    changes. A daylight noun at night ("the morning sun" at 23:00) has no safe
    swap and is left, as is anything in speech.
    """
    source = str(text or "")
    target = _clock_part(hour)
    fixes: list[dict[str, Any]] = []
    out = source
    for clash in sorted(clock_clashes(source, hour), key=lambda c: c["start"], reverse=True):
        if target == "night" and clash["noun"] in _DAYLIGHT_NOUNS:
            continue
        old = out[clash["start"]:clash["end"]]
        new = target.capitalize() if old[:1].isupper() else target
        out = out[: clash["start"]] + new + out[clash["end"]:]
        fixes.append({"why": "clock_word", "from": clash["phrase"], "to": new, "hour": int(hour) % 24})
    fixes.reverse()
    out, sun_fixes = repair_sun_words(out, hour)
    return out, fixes + sun_fixes


# Where the sun is, said of the present (7B run 10, T9: "The sun begins to dip
# lower in the sky" at 10:57). A setting sun before 14:00 or a rising one after
# noon contradicts the clock; at night there is no sun to move and nothing is
# swapped. Only the verb (and a "lower"/"higher" right after it) changes.
_SUN_MOTION_RE = re.compile(
    r"\bthe\s+sun\s+(?:(?:begins|began|starts|started|continues|continued)\s+to\s+|is\s+|has\s+begun\s+to\s+)?"
    r"(?P<verb>dip|dips|dipped|dipping|sink|sinks|sank|sinking|set|sets|setting|descend|descends|descended|descending|"
    r"rise|rises|rose|rising|climb|climbs|climbed|climbing)\b(?P<rest>[^.!?\n]{0,40})"
    r"|\bthe\s+(?P<adj>setting|sinking|rising)\s+sun\b",
    re.I,
)
_SUN_DOWN = {"dip", "dips", "dipped", "dipping", "sink", "sinks", "sank", "sinking", "set", "sets", "setting",
             "descend", "descends", "descended", "descending"}
_SUN_TO_UP = {
    "dip": "climb", "dips": "climbs", "dipped": "climbed", "dipping": "climbing",
    "sink": "climb", "sinks": "climbs", "sank": "climbed", "sinking": "climbing",
    "set": "rise", "sets": "rises", "setting": "rising",
    "descend": "climb", "descends": "climbs", "descended": "climbed", "descending": "climbing",
}
_SUN_TO_DOWN = {
    "rise": "sink", "rises": "sinks", "rose": "sank", "rising": "sinking",
    "climb": "sink", "climbs": "sinks", "climbed": "sank", "climbing": "sinking",
}


# Fair-weather claims about the present sky or sea (7B run 29, T9: "The sea
# outside is calm, the waves barely lapping" under a heavy storm). Read only in
# the narrator's sentences, and only while the engine has storm, rain or snow.
_FAIR_WEATHER_RE = re.compile(
    r"\b(?:clear(?:\s+blue)?\s+skys?|cloudless|blue\s+sky|"
    r"(?:sea|water|waters|harbou?r|bay|air)\s+(?:outside\s+)?(?:is|lies|sits|remains)\s+(?:calm|still|glassy|quiet)|"
    r"calm\s+(?:sea|water|waters)|waves\s+(?:barely|gently|softly)|gentle\s+breeze|still\s+air|"
    r"sun\s+(?:shines|is\s+shining|beats|blazes|warms))\b",
    re.I,
)
_FAIR_WEATHER_ASIDE_RE = re.compile(
    r"\b(?:despite|unlike|no\s+longer|once|used\s+to|would|if|until|remember|before\s+the|hope|wish|tomorrow|yesterday)\b",
    re.I,
)
_ROUGH_WEATHER = {"storm", "rain", "snow"}


def repair_fair_weather(text: str, kind: str) -> tuple[str, list[dict[str, Any]]]:
    """Drop narrator sentences that put fair weather into a storm, rain or snow scene."""
    source = str(text or "")
    if str(kind or "").lower() not in _ROUGH_WEATHER:
        return source, []

    def _clash(sentence: str) -> bool:
        if re.search(r"[\"“”]", sentence):
            return False
        return bool(_FAIR_WEATHER_RE.search(sentence)) and not _FAIR_WEATHER_ASIDE_RE.search(sentence)

    out, dropped = drop_sentences(source, _clash)
    return out, [{"why": "fair_weather", "kind": str(kind).lower(), "text": s[:160]} for s in dropped]


# A weapon the prose puts in the player's hand that the player does not own:
# "one hand resting near the hilt of your knife" with no knife (7B run 30,
# T12; run 5 T35, T79). Only that clause goes; speech is left alone.
_WITH_A_TOOL_RE = re.compile(
    r"\s+with\s+(?:a|an)\s+(?:[\w'’-]+\s+){0,2}?(?P<w>knife|dagger|sword|blade|axe|hatchet|spear|club|cudgel|"
    r"lantern|torch|lamp|crowbar|pry\s+bar|shovel|spade|pickaxe|grapnel|hook)\b",
    re.I,
)
_YOUR_WEAPON_RE = re.compile(
    r"\byour\s+(?:[\w'’-]+\s+){0,2}?(?P<w>knife|knives|dagger|daggers|sword|swords|blade|blades|axe|hatchet|spear|"
    r"club|cudgel|mace|crossbow|pistol|bow|"
    # Carried tools too: "your lantern's glow cutting through the gloom" with no
    # lantern (8B run 3, T8).
    # Not "your pack": that is the inventory itself.
    r"lantern|lanterns|torch|lamp|crowbar|pry\s+bar|shovel|spade|pickaxe|grapnel|hook|rope)\b",
    re.I,
)
_WEAPON_STEMS = {"knives": "knife", "daggers": "dagger", "swords": "sword", "blades": "blade", "lanterns": "lantern"}
_LIGHT_WORDS = ("lantern", "lamp", "torch")


_KIN_WORDS = ("mother", "father", "mam", "mum", "ma", "da", "dad", "grandmother", "grandfather", "sister", "brother",
              "aunt", "uncle", "wife", "husband")


def repair_kin_item_article(text: str, owned: list[str]) -> tuple[str, list[dict[str, Any]]]:
    """'the mother's brass tide-reckoner' is your mother's, when the player owns an item named that way.

    8B run 18, T0: the item is stored as "mother's brass tide-reckoner" and
    the model pasted the name after "the". Outside speech only.
    """
    kin = {
        m.group(1).lower()
        for name in owned
        for m in [re.match(rf"\s*({'|'.join(_KIN_WORDS)})['’]s\s", str(name or ""), re.I)]
        if m
    }
    if not kin or not str(text or "").strip():
        return str(text or ""), []
    changes: list[dict[str, Any]] = []
    pattern = re.compile(rf"\b([Tt])he\s+({'|'.join(sorted(kin))})(['’]s)\b")
    parts = re.split(r"(\"[^\"\n]*\"|“[^”\n]*”)", str(text))
    for i in range(0, len(parts), 2):
        def fix(m: re.Match[str]) -> str:
            changes.append({"why": "kin_item_article", "text": m.group(0)})
            return ("Your " if m.group(1) == "T" else "your ") + m.group(2) + m.group(3)
        parts[i] = pattern.sub(fix, parts[i])
    return "".join(parts), changes


_RESTRAINT_RE = re.compile(
    r"\b(?:without\s+touching|keep(?:ing)?\s+my\s+hands\s+off|(?:do\s+not|don['’]t|won['’]t|never)\s+(?:touch|take|pick\s+up))"
    r"\s+(?P<obj>it|them|the\s+[\w'’-]+(?:\s+[\w'’-]+)?)"
    r"|\bleav(?:e|ing)\s+(?P<obj2>it|them|the\s+[\w'’-]+(?:\s+[\w'’-]+)?)\s+(?:be|alone|where)\b",
    re.I,
)
_IN_HAND_RE = re.compile(
    r"\b(?:in|into|on|across)\s+your\s+(?:palm|palms|hand|hands|fingers|grip|grasp)\b"
    r"|\byour\s+(?:fingers|hand|hands|palm)\s+(?:close|closes|closing|brush|brushes|brushing|curl|curls|tighten|tightens)\b"
    r"|\byou\s+(?:\w+ly\s+)?(?:touch|touches|touched|pick|picks|picked|grab|grabs|grabbed|take|takes|took|hold|holds|held|"
    r"pocket|pockets|pocketed)\b",
    re.I,
)


def repair_restraint_undone(text: str, player_input: str) -> tuple[str, list[dict[str, Any]]]:
    """The thing the player's line keeps their hands off is not put in their hand by the narrator.

    8B run 33, T3: "I keep my hands off the coin" came back with "His eyes flick
    to the coin in your palm" (and run 15, T4: "without touching it"). The
    player's choice is theirs; the narrator sentence that undoes it goes.
    """
    line = re.split(r"\n\s*\n", str(player_input or ""), maxsplit=1)[0]
    acts = re.sub(r"\"[^\"]*\"|“[^”]*”", " ", line)
    heads: set[str] = set()
    for m in _RESTRAINT_RE.finditer(acts):
        obj = (m.group("obj") or m.group("obj2") or "").lower()
        if obj in {"it", "them"}:
            before = re.findall(r"\bthe\s+(?:[\w'’-]+\s+)?([\w'’-]+)", acts[: m.start()].lower())
            if before:
                heads.add(before[-1])
        else:
            heads.add(obj.split()[-1])
    heads = {h for h in heads if len(h) >= 3}
    if not heads or not str(text or "").strip():
        return str(text or ""), []
    changes: list[dict[str, Any]] = []

    def undoes(sentence: str) -> bool:
        if re.search(r"[\"“”]", sentence):
            return False
        low = sentence.lower()
        if any(re.search(rf"\b{re.escape(h)}", low) for h in heads) and _IN_HAND_RE.search(sentence):
            changes.append({"why": "restraint_undone", "text": sentence.strip()[:160]})
            return True
        return False

    fixed, dropped = drop_sentences(str(text), undoes)
    return (fixed, changes) if dropped else (str(text), [])


def repair_inverted_debt(text: str, backstory: str, player_name: str) -> tuple[str, list[dict[str, Any]]]:
    """'The tallyman owes you' when the backstory says the player owes the tallyman: turned back around.

    8B runs 19, 24 (and 7B before): "Isk owes the guild's tallyman for a
    winter of credit" came back as "the guild's tallyman still owes you a
    winter's credit". A narrow repair of that one shape, outside speech.
    """
    first = (str(player_name or "").split() or [""])[0]
    if not first or not str(text or "").strip():
        return str(text or ""), []
    owed = re.search(rf"\b{re.escape(first)}\s+owes\s+(?P<who>(?:the\s+)?[\w'’ -]{{3,40}}?)\s+(?:for|a|an|some|\d|money|coin|gold)\b",
                     str(backstory or ""), re.I)
    if not owed:
        return str(text), []
    head = owed.group("who").split()[-1]
    changes: list[dict[str, Any]] = []
    pattern = re.compile(
        rf"(?P<np>\b[Tt]he\s+(?:[\w'’-]+\s+){{0,3}}?{re.escape(head)}|\b{re.escape(head)})\s+(?P<still>still\s+)?owes\s+you\b"
    )
    parts = re.split(r"(\"[^\"\n]*\"|“[^”\n]*”)", str(text))
    for i in range(0, len(parts), 2):
        def fix(m: re.Match[str]) -> str:
            np = m.group("np")
            at_start = not parts[i][: m.start()].strip() or bool(re.search(r"[.!?]\s*$", parts[i][: m.start()]))
            np_low = np[0].lower() + np[1:] if np[:3].lower() == "the" else np
            out = f"you {m.group('still') or ''}owe {np_low}"
            changes.append({"why": "inverted_debt", "was": m.group(0)})
            return out[0].upper() + out[1:] if at_start else out
        parts[i] = pattern.sub(fix, parts[i])
    return "".join(parts), changes


def repair_unowned_weapon(text: str, owned: list[str], player_input: str = "") -> tuple[str, list[dict[str, Any]]]:
    """Drop the clause that gives the player a weapon their inventory does not hold.

    A weapon the player's own line names is theirs to describe ("I pry the lid
    off with my knife", run 5 T79): the prose keeps it.
    """
    source = str(text or "")
    have = " ".join(str(o or "").lower() for o in [*(owned or ()), player_input])
    fixes: list[dict[str, Any]] = []
    out = source
    for start, end, sentence in reversed(sentence_spans(source)):
        if re.search(r"[\"“”]", sentence):
            continue
        # "You pry at the links with a crowbar" with no crowbar (8B run 24, T3):
        # in the player's own sentence the tool phrase goes, the act stays.
        w = _WITH_A_TOOL_RE.search(sentence) if re.match(r"\W*you\b", sentence, re.I) else None
        if w and not re.search(rf"\b{_WEAPON_STEMS.get(w.group('w').lower(), w.group('w').lower())}", have) and not (
            w.group("w").lower() in _LIGHT_WORDS and any(re.search(rf"\b{x}", have) for x in _LIGHT_WORDS)
        ):
            new = (sentence[: w.start()] + sentence[w.end():]).replace(" ,", ",")
            out = out[:start] + new + out[end:]
            fixes.append({"why": "unowned_tool_phrase", "weapon": w.group("w").lower(), "text": sentence[:160]})
            continue
        m = _YOUR_WEAPON_RE.search(sentence)
        if not m:
            continue
        word = m.group("w").lower()
        stem = _WEAPON_STEMS.get(word, word)
        if re.search(rf"\b{stem}", have):
            continue
        # One light by any name: "your lamp" for the lantern the player carries.
        if word in _LIGHT_WORDS and any(re.search(rf"\b{w}", have) for w in _LIGHT_WORDS):
            continue
        parts = re.split(r"(,\s+)", sentence)
        clauses = parts[0::2]
        hit = next((i for i, c in enumerate(clauses) if _YOUR_WEAPON_RE.search(c)), -1)
        if hit > 0:
            kept = [c for i, c in enumerate(clauses) if i != hit]
            new = ", ".join(kept).rstrip(",; ")
            if not re.search(r"[.!?]$", new):
                new += sentence.rstrip()[-1] if sentence.rstrip()[-1:] in ".!?" else "."
        else:
            new = ""
        out = out[:start] + new + out[end:]
        fixes.append({"why": "unowned_weapon", "weapon": word, "text": sentence[:160]})
    if fixes:
        out = re.sub(r"[ \t]{2,}", " ", out)
        out = re.sub(r" +\n", "\n", out).strip()
        if len(out) < 80:
            return source, []
    return out, fixes


# An animal's body on the player (7B run 30, T7: a degenerate draft about
# moles wrote "You dig at the earth with your claws" for a human). Only the
# part right after "your", only in the narrator's sentences, and only for a
# people the setup gives no such parts.
_PLAYER_ANIMAL_PART_RE = re.compile(
    r"\byour\s+(?:claws?|snouts?|paws?|fur|tails?|whiskers|wings?|feathers|scales|hooves|talons|muzzle|antennae|fangs)\b",
    re.I,
)
_PLAIN_BODIED_RACES = frozenset({
    "", "human", "humans", "elf", "elves", "half-elf", "dwarf", "dwarves", "halfling", "halflings", "gnome", "gnomes",
    "orc", "orcs", "half-orc",
})


def repair_player_body(text: str, race: str) -> tuple[str, list[dict[str, Any]]]:
    """Drop narrator sentences that give a plain-bodied player claws, a snout or a tail."""
    source = str(text or "")
    if str(race or "").strip().lower() not in _PLAIN_BODIED_RACES:
        return source, []

    def _clash(sentence: str) -> bool:
        return not re.search(r"[\"“”]", sentence) and bool(_PLAYER_ANIMAL_PART_RE.search(sentence))

    out, dropped = drop_sentences(source, _clash)
    return out, [{"why": "player_body", "race": str(race or "").lower(), "text": s[:160]} for s in dropped]


# A spoken line cut off inside its last word: '"...they'll start eating
# through the t."' (7B run 30, T7). One stray lowercase letter (not "a" or
# "i"; "Plan B." is a name) right before the closing mark goes, with the
# article in front of it.
_CUT_WORD_IN_QUOTE_RE = re.compile(r"(?:\s+(?:the|a|an))?\s+(?<![\w'’])[b-hj-z](?=\s*[.!?…]+[\"”])")


# A sentence whose whole job is to bring in a spoken line: "Emrys Slade [[A]]'s
# voice cuts through the silence." (7B run 36, T3: the line itself, a repeat of
# his T1 line, was dropped and the lead stayed).
_SPEECH_LEAD_RE = re.compile(
    # An opening clause may come first: "Then, with a slow exhale, he speaks."
    # ended a scene with no line after it (8B run 91, T3).
    r"^\W*(?:[^.!?\"“”,]{1,40},\s*(?:[^.!?\"“”,]{1,40},\s*)?)?"
    r"(?:[A-Z][\w'’-]*(?:\s+[A-Z][\w'’-]*){0,2}(?:\s*\[\[[A-Z0-9]+\]\])?(?:['’]s)?|(?:his|her|their|a)\s*|he|she|they)\s+"
    r"(?:voice\s+(?:cuts|breaks|rings|carries|comes|calls)\s*(?:through|out|across|over)?(?:\s+the\s+\w+)?"
    r"|(?:speaks|calls)\s+(?:up|out)|clears\s+(?:his|her|their)\s+throat"
    r"|(?:finally\s+)?(?:speaks|answers|begins(?:\s+to\s+speak)?)"
    # A bare speech tag whose line was dropped: "Emrys asks, his tone shifting
    # subtly." (7B run 36, T7).
    r"|(?:asks|says|adds|replies|continues|mutters|murmurs|whispers)(?:,\s+(?:his|her|their)\s+[^.!?\"“”]{0,50})?)"
    r"\s*[.!]?\s*$",
)


def drop_unfinished_tail(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Cut a scene that stops mid-sentence back to its last finished sentence.

    8B run 4, T5 ended "... You're not here for the bones, are you? He": the
    reply ran out of tokens. Nothing is cut when that would leave too little.
    """
    source = str(text or "").rstrip()
    if not source or re.search(r"[.!?…\"”’')\]*]\s*$", source):
        return str(text or ""), []
    ends = [m.end() for m in re.finditer(r"[.!?…][\"”’']?(?=\s)", source)]
    if not ends or ends[-1] < 80:
        return str(text or ""), []
    cut = ends[-1]
    return source[:cut].rstrip(), [{"why": "unfinished_tail", "text": source[cut:].strip()[:80]}]


def drop_bare_name_paragraph(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Drop a paragraph that is nothing but a name: "The Pear's Rest." closing the scene (7B run 43, T0)."""
    paragraphs = re.split(r"(\n\s*\n)", str(text or ""))
    fixes: list[dict[str, Any]] = []
    for index in range(0, len(paragraphs), 2):
        para = paragraphs[index].strip()
        bare = re.sub(r"\s*\[\[[A-Z0-9]+\]\]", "", para)
        nxt = paragraphs[index + 2].lstrip() if index + 2 < len(paragraphs) else ""
        if nxt and nxt[0] in "\"“":
            continue  # a speaker label over the line it brings in
        if bare and re.fullmatch(r"(?:The\s+)?[A-Z][\w'’-]*(?:\s+(?:of|at|the|and|on)?\s*[A-Z][\w'’-]*){0,4}\s*[.!]?", bare) \
                and len(bare.split()) <= 6 and len([p for p in paragraphs[0::2] if p.strip()]) > 1:
            fixes.append({"why": "bare_name_paragraph", "text": para[:80]})
            paragraphs[index] = ""
    if not fixes:
        return str(text or ""), []
    out = re.sub(r"\n{3,}", "\n\n", "".join(paragraphs)).strip()
    return out, fixes


def drop_orphan_speech_lead(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Drop a sentence that only brings in a line when no line follows it."""
    source = str(text or "")
    fixes: list[dict[str, Any]] = []
    out = source
    spans = sentence_spans(source)
    for index in range(len(spans) - 1, -1, -1):
        start, end, sentence = spans[index]
        if re.search(r"[\"“”]", sentence) or not _SPEECH_LEAD_RE.match(sentence.strip()):
            continue
        after = source[end:]
        # Its line follows in the same paragraph, or opens the next one.
        nxt = re.match(r"\s*(\n\s*\n)?\s*(.)", after)
        if nxt and nxt.group(2) in "\"“":
            continue
        # A tag right after its line ('"Go." Emrys says.') is that line's.
        if re.search(r"[\"”]\s*$", source[:start]):
            continue
        out = out[:start] + out[end:]
        fixes.append({"why": "orphan_speech_lead", "text": sentence[:160]})
    if fixes:
        out = re.sub(r"[ \t]{2,}", " ", out)
        out = re.sub(r"[ \t]*\n[ \t]*", "\n", out)
        out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out, fixes


def repair_cut_word_in_quote(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Take a one-letter fragment off the end of a spoken line."""
    source = str(text or "")
    found = [m.group(0).strip() for m in _CUT_WORD_IN_QUOTE_RE.finditer(source)]
    if not found:
        return source, []
    return _CUT_WORD_IN_QUOTE_RE.sub("", source), [{"why": "cut_word_in_quote", "text": ", ".join(found[:4])}]


def _match_case(old: str, new: str) -> str:
    return new.capitalize() if old[:1].isupper() else new


def repair_sun_words(text: str, hour: int) -> tuple[str, list[dict[str, Any]]]:
    """Swap the motion of a sun that contradicts the clock: setting before 14:00, rising after noon."""
    source = str(text or "")
    hour = int(hour) % 24
    if hour < 5 or hour >= 20:
        return source, []
    masked = _mask_speech(source)
    edits: list[tuple[int, int, str]] = []
    fixes: list[dict[str, Any]] = []
    for match in _SUN_MOTION_RE.finditer(masked):
        group = "verb" if match.group("verb") else "adj"
        word = match.group(group)
        low = word.lower()
        going_down = low in _SUN_DOWN
        # Midday is either way: "the sun climbs higher" at 12:18 was turned to
        # "sinks" (7B run 27, T5). Down before 13:00, up from 14:00, are wrong.
        if going_down and hour < 13:
            new = _SUN_TO_UP.get(low)
        elif not going_down and hour >= 14:
            new = _SUN_TO_DOWN.get(low)
        else:
            continue
        if not new:
            continue
        edits.append((match.start(group), match.end(group), _match_case(word, new)))
        rest = match.group("rest") if group == "verb" else ""
        if rest:
            comp = re.match(r"\s+(lower|higher)\b", rest, re.I)
            if comp and ((comp.group(1).lower() == "lower") == going_down):
                swap = "higher" if going_down else "lower"
                at = match.start("rest") + comp.start(1)
                edits.append((at, at + len(comp.group(1)), _match_case(comp.group(1), swap)))
        fixes.append({"why": "sun_position", "from": source[match.start():match.end()].strip()[:120],
                      "to": new, "hour": hour})
    out = source
    for a, b, new in sorted(edits, reverse=True):
        out = out[:a] + new + out[b:]
    return out, fixes


# A closing sentence with no finite verb: "The pressure of the day settling in."
# (7B run 8 T0). Determiner, a short noun phrase (an "of the X" tail allowed),
# then a present participle. Anything with a finite verb is not matched.
_FRAGMENT_RE = re.compile(
    r"^(?P<np>(?:The|A|An|Your|His|Her|Their|Its)\s+(?P<head>[A-Za-z'-]+(?:\s+[a-z'-]+){0,2}?)"
    r"(?:\s+of\s+(?:the|a|an|your|his|her|their)\s+[a-z'-]+(?:\s+[a-z'-]+)?)?)"
    r"\s+(?P<ing>[a-z]+ing)\b(?P<rest>[^.!?\"]*)[.!?]$"
)
_FRAGMENT_TAIL_RE = re.compile(
    r"^(?:in|on|out|over|down|up|away|across|through|around|into|onto|off|behind|along|back|low|"
    r"still|slowly|quietly|softly|steadily|heavily|again|overhead|nearby|above|below|past|by|beyond)\b",
    re.I,
)
_FINITE_RE = re.compile(
    r"\b(?:is|are|was|were|has|have|had|does|do|did|can|could|will|would|shall|should|may|might|must|"
    r"seems?|remains?|hangs?|lingers?|stays?|feels?|looks?|sounds?|grows?|becomes?)\b",
    re.I,
)


def trailing_fragment(text: str) -> dict[str, Any] | None:
    """The last sentence when it is a noun phrase plus a participle with no finite verb."""
    source = str(text or "").rstrip()
    tail = re.split(r"(?:(?<=[.!?])|(?<=[.!?][\"”]))\s+", source)[-1].strip() if source else ""
    if not tail or len(tail.split()) > 12 or _FINITE_RE.search(tail):
        return None
    match = _FRAGMENT_RE.match(tail)
    if not match:
        return None
    # "The ship's gentle rocking lulls you ..." has its verb after the -ing
    # word; a fragment's tail is only a particle or adverb phrase, or nothing.
    rest = match.group("rest").strip()
    if rest and (not _FRAGMENT_TAIL_RE.match(rest) or "," in rest or ";" in rest):
        # "Your boots squelching in the mud, you head for the yard": the main
        # clause comes after the comma.
        return None
    head = match.group("head").split()[-1].lower()
    verb = "are" if head.endswith("s") and not head.endswith("ss") else "is"
    fixed = f"{match.group('np')} {verb} {match.group('ing')}{match.group('rest')}{tail[-1]}"
    return {"sentence": tail, "to": fixed}


_BRACKETED_WORD_RE = re.compile(r"(\w?)\((?P<words>[a-z][\w'’-]*(?:\s[a-z][\w'’-]*)?)\)")


def repair_bracketed_words(text: str) -> tuple[str, dict[str, Any] | None]:
    """Unwrap one- and two-word lowercase brackets when the scene has two or more (7B run 13, T3).

    "I know you've been in the (docks) for some time ... the (tally) stands at
    125 coins" is broken text, not asides. A lone "(barely)" stays.
    """
    source = str(text or "")
    hits = list(_BRACKETED_WORD_RE.finditer(source))
    if len(hits) < 2:
        return source, None

    def fix(match: re.Match[str]) -> str:
        glued = match.group(1)
        return f"{glued} {match.group('words')}" if glued else match.group("words")

    fixed = _BRACKETED_WORD_RE.sub(fix, source)
    return fixed, {"why": "bracketed_words", "count": len(hits), "words": [h.group("words") for h in hits][:12]}


def repair_trailing_fragment(text: str) -> tuple[str, dict[str, Any] | None]:
    """Give a closing verbless fragment its 'is'/'are' ("The pressure of the day is settling in.")."""
    source = str(text or "")
    found = trailing_fragment(source)
    if not found:
        return source, None
    stripped = source.rstrip()
    index = stripped.rfind(found["sentence"])
    if index < 0:
        return source, None
    out = stripped[:index] + found["to"] + source[len(stripped):]
    return out, {"why": "trailing_fragment", "from": found["sentence"], "to": found["to"]}


def settle_band_coin(text: str, amount: int) -> tuple[str, dict[str, Any] | None]:
    """
    "Hands over a moderate bag of coin" when the engine moved ``amount`` gold.

    A band word is the op's size, not the scene's: when exactly one such phrase
    stands for coin that changed hands this turn, it becomes the amount that
    moved (the state and the prose then say the same thing). Otherwise the
    prose is left as written.
    """
    source = str(text or "")
    found = list(_BAND_COIN_RE.finditer(source))
    if len(found) != 1 or int(amount or 0) <= 0:
        return source, None
    match = found[0]
    new = f"{int(amount)} gold"
    return source[: match.start()] + new + source[match.end():], {"why": "band_coin", "from": match.group(0), "to": new}
