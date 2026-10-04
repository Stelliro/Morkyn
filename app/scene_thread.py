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
# Where a target phrase stops: "follow him down the alley" -> "him".
_TARGET_STOP_RE = re.compile(
    r"\s+(?:and|but|or|to|into|in|inside|through|before|while|until|so|if|because|then|from|"
    r"toward|towards|down|up|across|around|out|along|past|over|at|as|when|without|again|now|quietly|"
    r"carefully|closely|slowly|quickly)\b",
    re.IGNORECASE,
)
# Not a target: "follow me" is an invitation, "look for a way" a plan.
_NOT_TARGET_RE = re.compile(
    r"^(?:me|us|myself|yourself|ourselves|it\s+out|out|a\s+way|some|something|anything|what|where|who|how|why|"
    r"if|whether|clues?|signs?|my\b|our\b|your\b|orders|instructions|suit|along)\b",
    re.IGNORECASE,
)
_PRONOUN_RE = re.compile(r"^(?:him|her|them|it|that\s+one|this\s+one)$", re.IGNORECASE)
# Asking someone along.
_INVITE_RE = re.compile(
    r"\b(?:come\s+(?:with|along\s+with)\s+(?:me|us)|come\s+along|join\s+(?:me|us)|follow\s+me|tag\s+along|"
    r"walk\s+with\s+(?:me|us)|you\s+coming|coming\s+with\s+(?:me|us)|with\s+me\s+on\s+this|"
    r"lead\s+the\s+way|show\s+me\s+(?:the\s+way|where))\b",
    re.IGNORECASE,
)
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


def pursuit_in(player_input: str) -> dict[str, str] | None:
    """{"doing", "target"} when the player's own line goes after someone or something."""
    text = own_text(player_input)
    if not text:
        return None
    for match in _PURSUE_RE.finditer(text):
        target = _clean_target(match.group("target"))
        if not target or _NOT_TARGET_RE.match(target):
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
    asked: list[dict[str, str]] = []
    if text and _INVITE_RE.search(text):
        for code in (resolution or {}).get("addressed") or []:
            name = str((names or {}).get(code) or "")
            if name:
                asked.append({"code": str(code), "name": name})
    if text and _DROP_RE.search(text):
        # "stop following him" is the player letting go, never a new pursuit.
        if previous:
            return {**previous, "status": "dropped", "asked_along": asked}
        return {"status": "none", "asked_along": asked} if asked else None
    found = pursuit_in(text)
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


def _companions_shown(asked: list[dict[str, str]], narration: str) -> list[dict[str, str]]:
    """Of those asked along, the ones the prose shows going along and not refusing."""
    sentences = re.split(r"(?<=[.!?])\s+", re.sub(r"\[\[[^\]]*\]\]", "", str(narration or "")))
    out: list[dict[str, str]] = []
    for person in asked:
        name = str(person.get("name") or "")
        if not name:
            continue
        pattern = re.compile(rf"\b{re.escape(name)}\b", re.IGNORECASE)
        mine = [s for s in sentences if pattern.search(s)]
        if any(_REFUSE_RE.search(s) for s in mine):
            continue
        if any(_ALONG_RE.search(s) for s in mine):
            out.append({"code": str(person.get("code") or ""), "name": name})
    return out


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
    if thread is None:
        return None
    shown = _companions_shown(asked, narration)
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
    if thread is None:
        if previous is not None:
            conn.execute("DELETE FROM settings WHERE key = ?", (SETTING_KEY,))
        return None
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (SETTING_KEY, json.dumps(thread)),
    )
    return thread
