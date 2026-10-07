"""What the player is in the middle of: the scene thread.

Playtest #20 (game 2, turns 3-4): the player asked Aria to come along after
the hooded figure, accepted "Find hooded figure", and followed it to a shop.
The next line, "Examine the herbs on the shop counter", was a side action.
The draft had nothing that said a pursuit was under way, so it put Aria
behind the counter as a shopkeeper, brought in a stranger with a well-repair
errand, and closed by deciding the player would see to that later. Everything
the player was doing was gone.

This module keeps one small record of the live thread, decided by the
engine, not the model:

- doing: the player's own words for the pursuit or goal ("follow the hooded
  figure"), or the accepted quest's title and step,
- target: who or what it is after, with an NPC code when it is a person here,
- with: the people who came along (asked in the player's line and shown
  going along in the prose),
- quest: the accepted quest it belongs to, when there is one.

It is updated before the draft from the player's line (a new pursuit, a
companion asked along, the player dropping it) and after the turn from the
quest report (accept, step, complete), the move, and the prose. It ends when
the player drops it, its quest is finished, failed or abandoned, or nothing
has touched it for STALE_TURNS turns. A side action never ends it.

State lives in the settings row ``scene_thread`` (saves and slot loads carry
it; app/world.py snapshots it for rewinds). The draft and verifier get
world_state.scene_thread, the paragraph writer brief.scene_thread, and the
suggestion ask scene.thread.
"""

from __future__ import annotations

import json
import re
from typing import Any

SETTING_KEY = "scene_thread"
STALE_TURNS = 6

# Going after someone or something. "find" is left out on purpose: "find a
# seat" is not a pursuit, and quests that start with it arrive by the quest
# report instead.
_PURSUE_RE = re.compile(
    r"\b(?P<verb>"
    r"follow(?:s|ed|ing)?|chas(?:e|es|ed|ing)|pursu(?:e|es|ed|ing)|tail(?:s|ed|ing)?|"
    r"track(?:s|ed|ing)?(?:\s+down)?|shadow(?:s|ed|ing)?|trail(?:s|ed|ing)?|"
    r"(?:go|goes|going|went|run|runs|running|ran|hurry|hurries|hurried|head|heads|set\s+off)\s+after|"
    r"keep\s+(?:up\s+with|after)|catch\s+up\s+(?:to|with)|"
    r"look(?:s|ing)?\s+for|search(?:es|ing)?\s+for|hunt(?:s|ing)?\s+(?:for|down)|"
    r"investigat(?:e|es|ing)"
    r")\s+(?P<target>[^.,;:!?\"“”]{2,80})",
    re.IGNORECASE,
)
# Pursuit verbs that are just as often nouns: "the frost trail", "deer tracks",
# "a shadow", "its tail". Playtest #28: "I crouch and examine the frost trail on
# the underbrush" was read as following "on the underbrush for tyre", and the
# follow repair moved the player. These count as verbs only where a verb of the
# player's own goes: at the start of a clause, after a subject or a helper
# ("I", "we", "to", "and", "will"), or after an adverb ("quietly").
_NOUN_LIKE_VERB_RE = re.compile(r"^(?:trail|track|shadow|tail)", re.IGNORECASE)
_VERB_LEAD_WORDS = frozenset({
    "i", "we", "you", "they", "he", "she", "to", "and", "then", "will", "shall", "can", "could", "would",
    "should", "must", "might", "may", "let's", "lets", "let", "i'll", "we'll", "i'd", "we'd", "try", "please",
    "now", "so", "or", "but", "also", "still", "just", "again",
})


def _verb_in_clause_position(text: str, start: int) -> bool:
    before = text[:start].rstrip()
    if not before or before[-1] in ".,;:!?(\"“”-—":
        return True
    prev = re.findall(r"[a-z'’]+", before.lower().replace("’", "'"))
    if not prev:
        return True
    word = prev[-1]
    return word in _VERB_LEAD_WORDS or (word.endswith("ly") and len(word) > 3)


# Where a target phrase stops: "follow him down the alley" -> "him".
_TARGET_STOP_RE = re.compile(
    r"\s+(?:and|but|or|to|into|in|inside|through|before|while|until|so|if|because|then|from|"
    r"toward|towards|down|up|across|around|out|along|past|over|at|as|when|without|again|now|quietly|"
    r"carefully|closely|slowly|quickly|near|beside|behind|outside|among|under|by)\b",
    re.IGNORECASE,
)
# Not a target: "follow me" is an invitation, "look for a way" a plan.
_NOT_TARGET_RE = re.compile(
    r"^(?:me|us|myself|yourself|ourselves|it\s+out|out|a\s+way|some|something|anything|what|where|who|how|why|"
    r"if|whether|clues?|signs?|my\b|our\b|your\b|orders|instructions|suit|along)\b",
    re.IGNORECASE,
)
_PRONOUN_RE = re.compile(r"^(?:him|her|them|it|that\s+one|this\s+one)$", re.IGNORECASE)
# Asking someone along. Playtest #32 (live): "Rolf, stay close." and "...with
# Umar beside me." were never read as asking anyone, so nobody was recorded.
_INVITE_RE = re.compile(
    r"\b(?:come\s+(?:with|along\s+with)\s+(?:me|us)|come\s+along|join\s+(?:me|us)|follow\s+me|tag\s+along|"
    r"walk\s+with\s+(?:me|us)|you\s+coming|coming\s+with\s+(?:me|us)|with\s+me\s+on\s+this|"
    r"lead\s+the\s+way|show\s+me\s+(?:the\s+way|where)|"
    r"stay\s+(?:close|near|with\s+(?:me|us)|beside\s+(?:me|us)|behind\s+(?:me|us))|"
    r"stick\s+(?:close|with\s+(?:me|us))|keep\s+close|keep\s+up|"
    r"(?:you['’]?re|you\s+are)\s+with\s+(?:me|us)|"
    r"(?:beside|alongside|behind)\s+(?:me|us)|at\s+my\s+side|by\s+my\s+side)\b",
    re.IGNORECASE,
)
# "with Umar beside me": the one taken along is named inside the phrase.
_WITH_NAMED_RE = re.compile(
    r"\bwith\s+(?P<name>[A-Z][\w'’-]+(?:\s+[A-Z][\w'’-]+)?)\s+(?:beside|alongside|behind|next\s+to)\s+(?:me|us)\b"
)
# Search verbs: looking for a thing is a side action, not a pursuit (playtest
# #32: "looking for footprints or anything dropped" replaced the live thread).
_SEARCH_VERB_RE = re.compile(r"^(?:look|search|hunt|investigat)", re.IGNORECASE)
# Words that make a target a person or a creature: something that can be
# followed or found, rather than marks, clues or a way out.
_BEING_WORDS = frozenset({
    "man", "men", "woman", "women", "figure", "figures", "stranger", "strangers", "person", "people",
    "boy", "girl", "child", "children", "kid", "kids", "youth", "elder", "crone", "widow", "fellow",
    "thief", "thieves", "killer", "murderer", "assassin", "spy", "spies", "scout", "scouts", "rider",
    "riders", "courier", "messenger", "runner", "watcher", "watchers", "guard", "guards", "soldier",
    "soldiers", "hunter", "hunters", "agent", "agents", "smuggler", "smugglers", "bandit", "bandits",
    "raider", "raiders", "brigand", "cultist", "cultists", "priest", "priestess", "witch", "wizard",
    "mage", "merchant", "trader", "peddler", "beggar", "traveler", "traveller", "pilgrim", "survivor",
    "survivors", "deserter", "fugitive", "prisoner", "captive", "culprit", "suspect", "informant",
    "contact", "friend", "friends", "brother", "sister", "mother", "father", "son", "daughter", "wife",
    "husband", "owner", "keeper", "leader", "boss", "captain", "sergeant", "officer", "marshal",
    "sheriff", "doctor", "healer", "medic", "stalker", "shadow", "intruder", "attacker", "arsonist",
    "creature", "creatures", "beast", "beasts", "animal", "animals", "wolf", "wolves", "hound",
    "hounds", "dog", "dogs", "bear", "deer", "stag", "boar", "horse", "rat", "rats", "bird", "crow",
    "raven", "thing", "monster", "ghost", "spirit", "drone", "robot", "android", "watchman",
    "fisherman", "ferryman", "horseman", "huntsman", "swordsman", "lawman", "gunman", "madman",
})
_SOMEONE_RE = re.compile(r"^(?:who(?:m)?ever|someone|somebody|anyone|anybody)\b", re.IGNORECASE)
# The player letting it go.
_DROP_RE = re.compile(
    r"\b(?:forget\s+(?:about\s+)?(?:it|him|her|them|that|the\s+\w+)|give\s+up(?:\s+on)?|"
    r"stop\s+(?:following|chasing|looking|searching|tracking|tailing|pursuing)|"
    r"let\s+(?:it|him|her|them)\s+go|call\s+(?:it|the\s+\w+)\s+off|leave\s+(?:it|him|her|them)\s+be|"
    r"never\s*mind\s+(?:the|him|her|them|that)|lose\s+interest|drop\s+(?:it|the\s+(?:chase|search|matter))|"
    r"abandon\s+(?:the\s+)?(?:chase|search|pursuit|hunt))\b",
    re.IGNORECASE,
)
# A companion shown going along, in one sentence with their name.
_ALONG_RE = re.compile(
    r"\b(?:follow(?:s|ing)?|join(?:s|ing)?|come(?:s)?\s+(?:with|along)|falls?\s+in|beside\s+you|alongside|"
    r"behind\s+you|with\s+you|at\s+your\s+side|by\s+your\s+side|close\s+by|nods?|agrees?|the\s+two\s+of\s+you|"
    r"both\s+of\s+you|together)\b",
    re.IGNORECASE,
)
_REFUSE_RE = re.compile(
    r"\b(?:refus\w*|declin\w*|shakes?\s+(?:her|his|their)\s+head|won['’]?t|will\s+not|can['’]?t|cannot|"
    r"stays?\s+behind|remains?\s+behind|turns?\s+away|goes\s+home|heads?\s+back)\b",
    re.IGNORECASE,
)
# Leading verbs of quest titles: "Find hooded figure" is after "the hooded figure".
_QUEST_VERB_RE = re.compile(
    r"^(?:find|locate|track(?:\s+down)?|follow|catch|hunt(?:\s+down)?|search\s+for|look\s+for|investigate|"
    r"identify|unmask|confront|chase|pursue|stop|rescue|save|recover|retrieve|return|deliver|escort|"
    r"protect|guard|watch|question|meet|ask|talk\s+to|speak\s+(?:to|with)|visit)\s+",
    re.IGNORECASE,
)
_ENDED_QUEST_ACTIONS = {"complete", "fail", "abandon"}
_STOPWORDS = {
    "the", "a", "an", "that", "this", "those", "these", "of", "to", "for", "and", "with", "who", "what",
    "him", "her", "them", "his", "their", "its", "into", "from", "after", "about",
}


# ---------------------------------------------------------------------------
# Reading the player's line
# ---------------------------------------------------------------------------


def own_text(player_input: str) -> str:
    """The player's typed line, without engine notes or internal markers."""
    text = str(player_input or "")
    if text.startswith("__"):
        return ""
    return re.split(r"\n\s*\n", text, maxsplit=1)[0].strip()


def _clean_target(raw: str) -> str:
    text = re.sub(r"@[CILSAE](\w+)", r"\1", str(raw or ""), flags=re.IGNORECASE)
    text = re.sub(r"\[\[[^\]]*\]\]", " ", text)
    text = _TARGET_STOP_RE.split(" " + text.strip(), maxsplit=1)[0].strip()
    words = text.split()
    if len(words) > 5:
        words = words[:5]
    return " ".join(words).strip(" '’-")


def names_a_being(target: str, people: list[dict[str, str]] | None = None) -> bool:
    """A target that is a person or a creature: a name, a pronoun, "whoever ...",
    or a noun phrase whose head is a person or animal word. Footprints, marks
    and clues are not. A structural check on the player's own line."""
    text = str(target or "").strip()
    if not text:
        return False
    if _PRONOUN_RE.match(text) or _SOMEONE_RE.match(text):
        return True
    if people and _person_named(text, people):
        return True
    words = re.findall(r"[A-Za-z][\w'’-]*", text)
    if not words:
        return False
    if words[0][:1].isupper() and words[0].lower() not in _STOPWORDS:
        return True  # a name the player typed: "Carlos Barnes", "Rolf"
    low = [w.lower().replace("’", "'") for w in words]
    if any(re.sub(r"'s$", "", w) in _BEING_WORDS for w in low):
        return True
    roles = {str(p.get("role") or "").lower() for p in people or [] if p.get("role")}
    return any(role and role in text.lower() for role in roles)


def pursuit_in(player_input: str, people: list[dict[str, str]] | None = None) -> dict[str, str] | None:
    """{"doing", "target"} when the player's own line goes after someone or something."""
    text = own_text(player_input)
    if not text:
        return None
    for match in _PURSUE_RE.finditer(text):
        verb_word = match.group("verb")
        noun_like = bool(_NOUN_LIKE_VERB_RE.match(verb_word))
        if noun_like and not _verb_in_clause_position(text, match.start()):
            continue
        target = _clean_target(match.group("target"))
        if not target or _NOT_TARGET_RE.match(target):
            continue
        # Playtest #32: "looking for footprints" and "investigate the marks"
        # search for things; only a person or creature is gone after.
        if (noun_like or _SEARCH_VERB_RE.match(verb_word)) and not names_a_being(target, people):
            continue
        verb = re.sub(r"\s+", " ", match.group("verb").strip().lower())
        return {"doing": f"{verb} {target}", "target": target}
    return None


def follow_target(player_input: str) -> str:
    """The one the player follows or goes after this turn, or ""."""
    found = pursuit_in(player_input)
    if not found:
        return ""
    verb = found["doing"].split(" ", 1)[0]
    if verb.startswith(("look", "search", "investigat", "hunt")):
        return ""
    return found["target"]


def invites_along(player_input: str) -> bool:
    return bool(_INVITE_RE.search(own_text(player_input)))


def asked_along_in(
    player_input: str,
    resolution: dict[str, Any] | None,
    people: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Who the player's own line asks to come along: the addressee of an
    invitation, or the person named in "with <name> beside me"."""
    text = own_text(player_input)
    if not text or not _INVITE_RE.search(text):
        return []
    names = (resolution or {}).get("names") if isinstance(resolution, dict) else {}
    asked: list[dict[str, str]] = []
    for code in (resolution or {}).get("addressed") or []:
        name = str((names or {}).get(code) or "")
        if name:
            asked.append({"code": str(code), "name": name})
    for match in _WITH_NAMED_RE.finditer(text):
        person = _person_named(match.group("name"), people)
        if person and all(row["code"] != person["code"] for row in asked):
            asked.append({"code": person["code"], "name": person["name"]})
    return asked


def drops_thread(player_input: str) -> bool:
    return bool(_DROP_RE.search(own_text(player_input)))


def _words(text: str) -> set[str]:
    return {
        w[:6]
        for w in re.findall(r"[a-z][a-z'’]+", str(text or "").lower())
        if len(w) > 2 and w not in _STOPWORDS
    }


def _same_target(a: str, b: str) -> bool:
    left, right = _words(a), _words(b)
    return bool(left and right and (left <= right or right <= left or len(left & right) >= 2))


def quest_target(title: str) -> str:
    """"Find hooded figure" -> "the hooded figure"; a person's name stays bare."""
    text = _QUEST_VERB_RE.sub("", str(title or "").strip(), count=1).strip()
    if not text or text == str(title or "").strip():
        return ""
    if re.match(r"^(?:the|a|an|his|her|their|my|our)\b", text, re.IGNORECASE) or text[:1].isupper():
        return text
    return "the " + text


# ---------------------------------------------------------------------------
# The record
# ---------------------------------------------------------------------------


def load(settings: dict[str, Any] | None) -> dict[str, Any] | None:
    """The stored thread, or None."""
    raw = (settings or {}).get(SETTING_KEY) if isinstance(settings, dict) else None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = None
    if not isinstance(raw, dict) or not str(raw.get("doing") or "").strip():
        return None
    thread = dict(raw)
    thread["with"] = [row for row in thread.get("with") or [] if isinstance(row, dict) and row.get("name")]
    thread["quest"] = thread.get("quest") if isinstance(thread.get("quest"), dict) else {}
    return thread


def _people_here(context: dict[str, Any]) -> list[dict[str, str]]:
    try:
        from app.conversation import roster

        return [{"code": row["code"], "name": row["name"]} for row in roster(context)]
    except Exception:
        return []


def _companion_doing(player_input: str, shown: list[dict[str, str]]) -> str:
    """What the player is doing with the people who came along: the player's own
    words without the invitation, else plainly who they are with."""
    text = own_text(player_input)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    rest = [s for s in sentences if not _INVITE_RE.search(s)]
    if rest:
        return " ".join(rest)[:160]
    return "go on with " + " and ".join(str(p.get("name") or "") for p in shown[:3])


def _person_named(target: str, people: list[dict[str, str]]) -> dict[str, str] | None:
    low = str(target or "").lower()
    for person in people:
        name = str(person.get("name") or "").lower()
        if name and re.search(rf"\b{re.escape(name)}\b", low):
            return person
        first = name.split(" ")[0] if name else ""
        if len(first) >= 3 and re.search(rf"\b{re.escape(first)}\b", low):
            return person
    return None


def begin_turn(
    context: dict[str, Any],
    player_input: str,
    resolution: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    The thread for this turn's prompts, after the player's line. Pure; nothing is stored.

    ``status`` is "continues" (side action inside it), "started", "updated",
    "dropped" (the player let it go this turn), or "none" (no thread; only
    carries who was asked along, for the after-turn update).
    """
    settings = context.get("settings") if isinstance(context.get("settings"), dict) else {}
    previous = load(settings)
    if previous is None and isinstance(context.get(SETTING_KEY), dict) and context[SETTING_KEY].get("doing"):
        previous = load({SETTING_KEY: context[SETTING_KEY]})
    text = own_text(player_input)
    people = _people_here(context)
    names = (resolution or {}).get("names") if isinstance(resolution, dict) else {}
    asked = asked_along_in(text, resolution, people)
    if text and _DROP_RE.search(text):
        # "stop following him" is the player letting go, never a new pursuit.
        if previous:
            return {**previous, "status": "dropped", "asked_along": asked}
        return {"status": "none", "asked_along": asked} if asked else None
    found = pursuit_in(text, people)
    if found and previous and _SEARCH_VERB_RE.match(found["doing"]) and not _same_target(
        found["target"], str(previous.get("target") or "")
    ):
        # A search while a pursuit is live is a side action inside it; only an
        # explicit new pursuit of someone else replaces it (playtest #32).
        found = None
    if found:
        target = found["target"]
        if _PRONOUN_RE.match(target):
            if previous and previous.get("target"):
                # "follow him" while already after someone: the same pursuit, pressed on.
                return {**previous, "status": "updated", "asked_along": asked}
            else:
                addressed = list((resolution or {}).get("addressed") or [])
                if len(addressed) == 1 and (names or {}).get(addressed[0]):
                    target = str(names[addressed[0]])
                    found = {"doing": found["doing"].rsplit(" ", 1)[0] + " " + target, "target": target}
                else:
                    found = None
    if found:
        person = _person_named(found["target"], people)
        if previous and _same_target(found["target"], str(previous.get("target") or "")):
            thread = {**previous, "status": "updated", "doing": found["doing"]}
        else:
            thread = {
                "version": 1,
                "doing": found["doing"],
                "target": found["target"],
                "target_code": "",
                "with": list(previous.get("with") or []) if previous else [],
                "quest": {},
                "source": "player",
                "started_turn": 0,
                "touched_turn": 0,
                "where": "",
                "status": "started",
            }
        if person:
            thread["target"] = person["name"]
            thread["target_code"] = person["code"]
        thread["asked_along"] = asked
        return thread
    if previous:
        return {**previous, "status": "continues", "asked_along": asked}
    return {"status": "none", "asked_along": asked} if asked else None


# A sentence that goes on about the last person named: "He gestures...",
# or their quoted reply.
_CONTINUES_RE = re.compile(r"^[\"\u201c\u2018']|^(?:he|she|they|his|her|their)\b", re.IGNORECASE)


def _sentences_about(sentences: list[str], name: str) -> list[str]:
    """The sentences that name ``name``, each with the run of "he/she/they" and
    quoted sentences straight after it.

    Live gate N1: "Elias Thorn, come with me." The prose named him once, then
    went on "He gestures toward the group..." and "\u201cCome on, if you're
    determined to follow, we might still catch up.\u201d" Only the sentence with
    his name was read, so his yes was missed and he never joined. The run stops
    at the first sentence that is not his.
    """
    pattern = re.compile(rf"\b{re.escape(name)}\b", re.IGNORECASE)
    out: list[str] = []
    following = False
    for sentence in sentences:
        if pattern.search(sentence):
            out.append(sentence)
            following = True
        elif following and _CONTINUES_RE.match(sentence.strip()):
            out.append(sentence)
        else:
            following = False
    return out


def _companions_shown(asked: list[dict[str, str]], narration: str) -> list[dict[str, str]]:
    """Of those asked along, the ones the prose shows going along and not refusing."""
    sentences = re.split(r"(?<=[.!?])\s+", re.sub(r"\[\[[^\]]*\]\]", "", str(narration or "")))
    out: list[dict[str, str]] = []
    for person in asked:
        name = str(person.get("name") or "")
        if not name:
            continue
        mine = _sentences_about(sentences, name)
        if any(_REFUSE_RE.search(s) for s in mine):
            continue
        if any(_ALONG_RE.search(s) for s in mine):
            out.append({"code": str(person.get("code") or ""), "name": name})
    return out


def companions_shown(asked: list[dict[str, str]], narration: str) -> list[dict[str, str]]:
    return _companions_shown(list(asked or []), narration)


def left_behind(narration: str):
    """A test for a name: does the prose show them refusing or staying behind?"""
    sentences = re.split(r"(?<=[.!?])\s+", re.sub(r"\[\[[^\]]*\]\]", "", str(narration or "")))

    def check(name: str) -> bool:
        if not name:
            return False
        first = name.split()[0]
        pattern = re.compile(rf"\b(?:{re.escape(name)}|{re.escape(first)})\b", re.IGNORECASE)
        return any(_REFUSE_RE.search(s) for s in sentences if pattern.search(s))

    return check


def same_target(a: str, b: str) -> bool:
    return _same_target(a, b)


def person_named(target: str, people: list[dict[str, str]]) -> dict[str, str] | None:
    return _person_named(target, people)


def _quest_row(conn, code: str) -> dict[str, Any] | None:
    try:
        row = conn.execute(
            "SELECT id, code, title, description, status FROM quests WHERE code = ? COLLATE NOCASE", (code,)
        ).fetchone()
    except Exception:
        return None
    if not row:
        return None
    quest = {"code": row[1], "title": row[2], "status": row[4], "step": ""}
    try:
        step = conn.execute(
            "SELECT title, description FROM quest_steps WHERE quest_id = ? AND status = 'active' "
            "ORDER BY step_number LIMIT 1",
            (row[0],),
        ).fetchone()
    except Exception:
        step = None
    if step:
        quest["step"] = str(step[1] or step[0] or "")
    elif row[3]:
        quest["step"] = str(row[3])
    return quest


def next_thread(
    turn_thread: dict[str, Any] | None,
    previous: dict[str, Any] | None,
    *,
    quest_report: dict[str, Any] | None,
    quests: dict[str, dict[str, Any]],
    narration: str,
    player_input: str,
    location: str,
    turn: int,
) -> dict[str, Any] | None:
    """The thread after a turn. Pure: the caller loads quests and saves."""
    status = str((turn_thread or {}).get("status") or "")
    asked = list((turn_thread or {}).get("asked_along") or [])
    if status == "dropped":
        thread = None
    elif status in {"started", "updated", "continues"}:
        thread = {k: v for k, v in (turn_thread or {}).items() if k not in {"status", "asked_along"}}
    else:
        thread = dict(previous) if previous else None
    report = quest_report if isinstance(quest_report, dict) else {}
    touched_by_quest = False
    accepted = [row for row in report.get("updated") or [] if isinstance(row, dict) and row.get("action") == "accept"]
    accepted += [
        row for row in report.get("created") or [] if isinstance(row, dict) and str(row.get("status") or "") == "active"
    ]
    for row in accepted:
        quest = quests.get(str(row.get("code") or "").upper())
        if not quest:
            continue
        link = {"code": quest["code"], "title": quest["title"], "step": quest.get("step") or ""}
        target = quest_target(quest["title"])
        if thread and (
            _same_target(target or quest["title"], str(thread.get("target") or ""))
            or (status in {"started", "updated"} and not thread.get("quest"))
        ):
            thread["quest"] = link
        elif thread and status in {"started", "updated"}:
            continue  # the player's own pursuit this turn outranks a job taken in passing
        else:
            thread = {
                "version": 1,
                "doing": quest["title"],
                "target": target,
                "target_code": "",
                "with": list((thread or {}).get("with") or []),
                "quest": link,
                "source": "quest",
                "started_turn": turn,
                "touched_turn": turn,
                "where": "",
            }
        touched_by_quest = True
    if thread and thread.get("quest"):
        code = str(thread["quest"].get("code") or "").upper()
        for row in report.get("updated") or []:
            if not isinstance(row, dict) or str(row.get("code") or "").upper() != code:
                continue
            if row.get("action") in _ENDED_QUEST_ACTIONS:
                return None
            if row.get("action") == "step_done" and quests.get(code):
                thread["quest"]["step"] = quests[code].get("step") or ""
                touched_by_quest = True
        live = quests.get(code)
        if live and str(live.get("status") or "") in {"completed", "complete", "failed", "abandoned"}:
            return None
    shown = _companions_shown(asked, narration)
    if thread is None and shown:
        # Playtest #32 (live): "Rolf, come with me. I want to find whoever is
        # burning those herbs" has no pursuit verb and no earlier thread, so the
        # companion the prose showed following was computed and thrown away.
        # People who came along are kept on a thread of their own.
        thread = {
            "version": 1,
            "doing": _companion_doing(player_input, shown),
            "target": "",
            "target_code": "",
            "with": [],
            "quest": {},
            "source": "companions",
            "started_turn": turn,
            "touched_turn": turn,
            "where": "",
        }
    if thread is None:
        return None
    if shown:
        have = {str(row.get("code") or row.get("name")) for row in thread.get("with") or []}
        for person in shown:
            if str(person.get("code") or person.get("name")) not in have:
                thread.setdefault("with", []).append(person)
    if not thread.get("started_turn"):
        thread["started_turn"] = turn
    mention = " ".join([own_text(player_input), str(narration or "")])
    touched = (
        status in {"started", "updated"}
        or touched_by_quest
        or bool(shown)
        or _same_target(str(thread.get("target") or thread.get("doing") or ""), mention)
    )
    if touched or not thread.get("touched_turn"):
        thread["touched_turn"] = turn
    elif turn - int(thread.get("touched_turn") or 0) >= STALE_TURNS:
        return None
    if location:
        thread["where"] = location
    thread["with"] = list(thread.get("with") or [])[:4]
    return thread


# ---------------------------------------------------------------------------
# What each stage is told
# ---------------------------------------------------------------------------


def _live(thread: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(thread, dict) or not str(thread.get("doing") or "").strip():
        return None
    if str(thread.get("status") or "") in {"dropped", "none"}:
        return None
    return thread


def world_view(thread: dict[str, Any] | None) -> dict[str, Any] | None:
    """world_state.scene_thread for the draft and verify passes."""
    thread = _live(thread)
    if thread is None:
        return None
    view: dict[str, Any] = {"doing": str(thread["doing"])[:160]}
    if thread.get("target"):
        target: dict[str, Any] = {"name": str(thread["target"])[:80]}
        if thread.get("target_code"):
            target["code"] = thread["target_code"]
        view["target"] = target
    if thread.get("with"):
        view["with_the_player"] = [
            {key: row[key] for key in ("name", "code") if row.get(key)} for row in thread["with"][:4]
        ]
    quest = thread.get("quest") or {}
    if quest.get("title"):
        view["quest"] = {key: quest[key] for key in ("title", "code", "step") if quest.get(key)}
    if thread.get("where"):
        view["where"] = thread["where"]
    status = str(thread.get("status") or "")
    view["this_turn"] = {
        "started": "the player starts it with this action",
        "updated": "the player presses on with it",
    }.get(status, "it is still under way; this action happens inside it")
    return view


def _label(row: dict[str, Any]) -> str:
    name = str(row.get("name") or "")
    code = str(row.get("code") or "")
    return f"{name} [[{code}]]" if name and code else name


def writer_view(thread: dict[str, Any] | None) -> dict[str, Any] | None:
    """brief.scene_thread for the paragraph writer and the consolidator: names, not just codes."""
    thread = _live(thread)
    if thread is None:
        return None
    view: dict[str, Any] = {"player_is_doing": str(thread["doing"])[:160]}
    if thread.get("target"):
        view["after"] = _label({"name": thread["target"], "code": thread.get("target_code")})
    if thread.get("with"):
        view["with_the_player"] = [_label(row) for row in thread["with"][:4]]
    quest = thread.get("quest") or {}
    if quest.get("step"):
        view["quest_step"] = str(quest["step"])[:160]
    return view


def suggestion_view(thread: dict[str, Any] | None) -> dict[str, Any] | None:
    """scene.thread for the suggestion ask: plain words, no codes."""
    thread = _live(thread)
    if thread is None:
        return None
    view: dict[str, Any] = {"doing": str(thread["doing"])[:120]}
    if thread.get("target"):
        view["after"] = str(thread["target"])[:80]
    if thread.get("with"):
        view["with"] = [str(row.get("name") or "") for row in thread["with"][:4] if row.get("name")]
    quest = thread.get("quest") or {}
    if quest.get("step"):
        view["next_step"] = str(quest["step"])[:140]
    return view


# ---------------------------------------------------------------------------
# Database glue (the caller owns the connection and the transaction)
# ---------------------------------------------------------------------------


def read(conn) -> dict[str, Any] | None:
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (SETTING_KEY,)).fetchone()
    except Exception:
        return None
    if not row:
        return None
    return load({SETTING_KEY: row[0]})


def update_after_turn(
    conn,
    *,
    turn_thread: dict[str, Any] | None,
    quest_report: dict[str, Any] | None,
    narration: str,
    player_input: str,
    turn: int,
) -> dict[str, Any] | None:
    previous = read(conn)
    report = quest_report if isinstance(quest_report, dict) else {}
    codes = {
        str(row.get("code") or "").upper()
        for row in list(report.get("updated") or []) + list(report.get("created") or [])
        if isinstance(row, dict) and row.get("code")
    }
    for candidate in (previous, turn_thread):
        code = str(((candidate or {}).get("quest") or {}).get("code") or "").upper()
        if code:
            codes.add(code)
    quests = {code: found for code in codes if (found := _quest_row(conn, code))}
    row = conn.execute(
        "SELECT l.name FROM player p LEFT JOIN locations l ON l.id = p.current_location_id WHERE p.id = 1"
    ).fetchone()
    location = str((row[0] if row else "") or "")
    thread = next_thread(
        turn_thread,
        previous,
        quest_report=report,
        quests=quests,
        narration=narration,
        player_input=player_input,
        location=location,
        turn=turn,
    )
    # Playtest #51: who came along joins the party the UI and combat read.
    try:
        from app.party import sync_scene_companions

        sync_scene_companions(conn, list((thread or {}).get("with") or []), narration, turn)
    except Exception:
        pass  # the party never blocks a turn
    if thread is None:
        if previous is not None:
            conn.execute("DELETE FROM settings WHERE key = ?", (SETTING_KEY,))
        return None
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (SETTING_KEY, json.dumps(thread)),
    )
    return thread
