"""
Quest parser: the narrator offers work in the story; this pass instates it.

Division of labour
------------------
* The turn model (narrator) writes the scene. It may offer a job, hand over a
  task, or finish a step, in prose. It may also *mark* one with the DSL op
  ``QUEST`` / ``QUEST_DONE`` (see app/turn_dsl.py), but a mark is optional.
* After the narration is final (the narration pipeline can still add a job
  after the ops stage), ``needs_quest_parse`` decides cheaply whether this turn
  could hold quest material. Only then does a small, focused parser call run:
  ``build_parser_prompt`` -> model -> ``parse_reply``.
* The engine owns the outcome. ``validate_quest_changes`` grounds every
  proposal in the turn's own text (the evidence quote must be in the narration
  or the player's words), resolves the giver and places against known rows,
  drops duplicates of open quests, and clamps rewards. ``apply_quest_changes``
  creates the rows through ``app.quests.create_quest``, advances or closes steps,
  and logs every accepted and every rejected proposal (journal + the returned
  report, which goes into the turn trace).

The turn carries the proposals under ``turn["quest_changes"]``:

    {
      "source": "parser" | "marks" | "parser+marks",
      "new": [
        {
          "title": "Escort the silk to the western border",   # 3-80 chars
          "summary": "one sentence: what is asked and why",
          "giver": "A1" | "Carter" | "",                      # NPC code or name, or a notice/board
          "status": "offered",                                 # always; Accept makes it active (TODO n20)
          "steps": [ {"title": "...", "description": "...", "location": "L3" | "Western Border" | ""} ],  # 1-6
          "reward": {"gold": 0, "xp": 0, "items": ["..."], "text": "as promised in the story"},
          "difficulty": "easy" | "normal" | "hard" | "deadly",
          "timer_turns": 0,
          "offer_line": "the giver's own words offering or agreeing to it",
          "evidence": "exact words from the narration or the player's line",
        }
      ],
      "updates": [
        {"quest": "Q3" | "<title>", "action": "accept" | "decline" | "step_done" | "complete" | "fail" | "abandon",
         "evidence": "exact words"}
      ],
    }

Nothing here talks to the model directly: app/llm.py makes the call so the
provider, timeouts, token caps and tracing stay in one place.
"""
from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from typing import Any

PARSER_PHASE = "quest_parser"
"""Trace / usage phase name for the parser call."""

PARSER_MAX_TOKENS = 450
MAX_NEW_PER_TURN = 2
MAX_UPDATES_PER_TURN = 4

QUEST_ACTIONS = ("accept", "decline", "step_done", "complete", "fail", "abandon")
DIFFICULTIES = ("trivial", "easy", "normal", "hard", "deadly")
MAX_STEPS = 6
REWARD_GOLD_CAP = 500
REWARD_XP_CAP = 1000
REWARD_ITEMS_CAP = 3

# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------
# Words that make a sentence about work. Alone they are not enough ("the job of
# a gatehouse"); the sentence must also address the player or name something
# to hand over, fetch, escort, or find.
_JOB_RE = re.compile(
    r"\b(?:hire[sd]?|hiring|pay(?:s|ing)?|paid|reward(?:s|ed)?|bount(?:y|ies)|jobs?|tasks?|tasked|errands?|"
    r"contracts?|quests?|work for|coins? for|silver for|gold for|deliver(?:y|ed|ing)?|escort(?:s|ed|ing)?|"
    r"bring (?:me|us|it|this|that|back)|fetch|retrieve|recover|find (?:my|our|the|him|her|them|out)|"
    r"track down|clear out|investigate|i need (?:someone|somebody|you|a hand|help)|we need (?:someone|you|help)|"
    r"in exchange|owe you|make it worth|wanted:|notice (?:is|was) (?:up|posted|pinned|nailed)|"
    r"posted (?:on|at) the|board (?:reads|says|lists)|"
    # Live Qwen3 8B phrasing the list missed: "the ferryman's looking for a hand
    # with the nets", "The captain needs help loading cargo".
    r"(?:looking|asking) for (?:a hand|hands|help|someone|somebody|workers?|a crew)|"
    r"needs? (?:a hand|hands|help|someone|somebody|workers?)|could use (?:a hand|help|someone)|"
    r"wants? (?:someone|somebody|a hand)|lend (?:a|me a|us a) hand|hands? you (?:a|the) (?:pouch|purse|coins?|advance)|"
    # Playtest #81 (live): ordinary determiners and plurals slipped past the
    # fixed phrasings, so three real offers never reached the parser: "needs a
    # bit of help", "could use an extra hand", "the deliveries", "a bit of work
    # here and there", "agrees to teach you". The gate and the offer check
    # share this one list, so they cannot fall out of step.
    r"needs? (?:a bit of|a little|some|any|an extra|extra|more) (?:help|hands?)|"
    r"could use (?:an extra|another|a|some|your|a bit of|an extra set of) (?:hands?|help|skills?|set of hands)|"
    r"(?:extra|spare) (?:set of )?hands|every hand helps|deliver\w*|"
    r"(?:any|some|a bit of|odd|plenty of|honest|steady|paying) work|work (?:here|to do|for you|for me|for us)|"
    r"(?:teach|train) you|show you how|apprentic\w*|take you on|"
    r"(?:start|begin) (?:there|tomorrow|today|in the morning|at dawn|first thing))\b",
    re.I,
)
# The player asking for work or training. A conversation trigger for the gate:
# when the player asks, the answer is worth reading even if it is phrased in
# words the job list has never seen (playtest #81: "any work i can do?" was
# answered with an offer on T10, and nothing read it).
_ASKS_WORK_RE = re.compile(
    r"\b(?:any|some|a|the|honest|paying|more) (?:work|jobs?|tasks?|errands?|employment)\b|"
    r"\b(?:need|needs|want|wanted|use) (?:a |an |an extra |another |some |any )?(?:help|hand|hands|set of hands|helper|worker)\b|"
    r"\b(?:can|could|may|shall) i (?:help|assist|lend|work|be of use)\b|"
    r"\b(?:hire|employ) me\b|\bhiring\b|\bapprentic\w*|\b(?:teach|train|show) me\b|\blearn (?:to|how|the|your)\b|"
    r"\bearn (?:some |a |my )?(?:coin|money|gold|silver|keep|living|wage)\b|\bwork for (?:you|coin|pay|food)\b|"
    r"\blooking for (?:work|a job|employment)\b",
    re.I,
)
# A giver saying yes to what the player asked for. Counts as an offer only
# beside a player line that asked for work (see judge_offer).
_AGREES_RE = re.compile(
    r"\b(?:agree[sd]?|says? yes|said yes|nods?|nodded|nodding|you'?re hired|welcome aboard|it'?s settled|"
    r"accepts? your offer|take you on|(?:start|begin) (?:there|tomorrow|today|in the morning))\b",
    re.I,
)
_ADDRESS_RE = re.compile(
    r"\b(?:you|your|yourself|stranger|traveller|traveler|anyone|whoever|someone)\b|\?|\b(?:if you|would you|could you|will you|can you)\b",
    re.I,
)
_DELIVERABLE_RE = re.compile(
    r"\b(?:to the|from the|before (?:dawn|dusk|nightfall|morning|the)|by (?:dawn|dusk|nightfall|morning)|"
    r"shipment|cargo|parcel|package|letter|crate|message|body|head|proof|herb|medicine|debt|thief|missing)\b",
    re.I,
)
_PROGRESS_RE = re.compile(
    r"\b(?:done|delivered|handed (?:it )?over|hand(?:s|ed)? (?:it|them|the \w+) (?:over|back)|finished|completed?|"
    r"failed|too late|paid you|pays you|counts out|reward(?:ed)?|returned|brought (?:it|them|back)|safe(?:ly)? (?:home|back))\b",
    re.I,
)
_DECLINE_RE = re.compile(r"\b(?:decline|refuse|turn (?:it|them|the \w+) down|no thanks|not interested|pass on)\b", re.I)
# A sentence also ends after a closing quote: 'all I know." Later a woman says'
# used to stay one sentence, so a refusal borrowed the next speaker's paid offer.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|(?<=[.!?][\"'\u201d\u2019)])\s+|\n+")


def _accept_re() -> re.Pattern[str]:
    try:
        from app.local_intel import _ACCEPT_RE

        return _ACCEPT_RE
    except Exception:  # pragma: no cover - local_intel always importable in the app
        return re.compile(
            r"\b(?:i(?:'ll| will) (?:take|do)|i accept|take|accept)\b(?:\s+\w+){0,4}\s+\b(?:quest|job|notice|errand|contract|work)\b",
            re.I,
        )


# Plain acceptance a player types back to an offer ("I'll do it", "deal").
_SIMPLE_ACCEPT_RE = re.compile(
    r"\b(?:i(?:'ll| will) (?:do it|take it|help|go)|deal|you have a deal|i accept|count me in|agreed|"
    r"i(?:'ll| will) (?:escort|deliver|find|bring|fetch|carry)|accept(?:s|ed)? the)\b",
    re.I,
)


def player_accepts(player_input: str) -> bool:
    text = str(player_input or "")
    return bool(_accept_re().search(text) or _SIMPLE_ACCEPT_RE.search(text))


def _title_words(title: str) -> set[str]:
    stop = {"the", "a", "an", "of", "to", "for", "and", "in", "on", "at", "from", "with", "word"}
    return {w for w in re.findall(r"[a-z]{4,}", str(title or "").lower()) if w not in stop}


def player_asks_for_work(text: str) -> bool:
    """The player's line asks for work, a hand to lend, or to be taught."""
    return bool(_ASKS_WORK_RE.search(str(text or "")))


def quest_parse_gate(
    narration: str,
    player_input: str = "",
    *,
    marks: list[dict[str, Any]] | None = None,
    active_quests: list[dict[str, Any]] | None = None,
    open_offers: list[dict[str, Any]] | None = None,
    previous_input: str = "",
    talking_to_someone: bool = False,
) -> str:
    """
    Cheap gate: the reason this turn may hold quest material, or "" when not.

    Recall comes first (playtest #81). A wasted parser call costs a few
    seconds; a missed offer is lost for good, because nothing reads the turn
    again. So the player asking for work opens the gate on its own, and so does
    an answer to last turn's ask while the same conversation goes on.
    """
    if marks:
        return "marks"
    narration = str(narration or "")
    player_input = str(player_input or "")
    for sentence in _SENTENCE_SPLIT.split(narration):
        if _JOB_RE.search(sentence) and (_ADDRESS_RE.search(sentence) or _DELIVERABLE_RE.search(sentence)):
            return "narration_offer"
    if player_asks_for_work(player_input):
        return "player_asks_work"
    if _JOB_RE.search(player_input) and (_ADDRESS_RE.search(player_input) or _DELIVERABLE_RE.search(player_input)):
        # The player names a job ("any work for me?").
        if re.search(r"\b(?:job|work|task|errand|bounty|contract|hire|quest)\b", player_input, re.I):
            return "player_names_job"
    if talking_to_someone and player_asks_for_work(previous_input):
        # The giver may answer a turn late ("I go into the forge" after asking
        # Bertram for work on the turn before).
        return "answer_to_last_ask"
    open_rows = list(active_quests or []) + list(open_offers or [])
    if open_rows:
        if player_accepts(player_input) or _DECLINE_RE.search(player_input):
            return "answer_to_open_quest"
        if _PROGRESS_RE.search(narration):
            return "open_quest_progress"
        low = narration.lower()
        for quest in open_rows:
            words = _title_words(str(quest.get("title") or ""))
            if words and sum(1 for w in words if w in low) >= max(1, min(2, len(words))):
                return "open_quest_named"
    return ""


def needs_quest_parse(
    narration: str,
    player_input: str = "",
    *,
    marks: list[dict[str, Any]] | None = None,
    active_quests: list[dict[str, Any]] | None = None,
    open_offers: list[dict[str, Any]] | None = None,
    previous_input: str = "",
    talking_to_someone: bool = False,
) -> bool:
    """Cheap gate: True when this turn may hold quest material worth a parser call."""
    return bool(
        quest_parse_gate(
            narration,
            player_input,
            marks=marks,
            active_quests=active_quests,
            open_offers=open_offers,
            previous_input=previous_input,
            talking_to_someone=talking_to_someone,
        )
    )


# ---------------------------------------------------------------------------
# The prompt
# ---------------------------------------------------------------------------
_SYSTEM = (
    "You record quests for a role-playing game engine. Return JSON only, one object, no prose. "
    "You never invent: you copy what the story already offered, accepted, finished or failed."
)


def _slim(rows: list[dict[str, Any]] | None, keys: tuple[str, ...], cap: int) -> list[dict[str, Any]]:
    out = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        item = {k: row.get(k) for k in keys if row.get(k) not in (None, "")}
        if item:
            out.append(item)
        if len(out) >= cap:
            break
    return out


def build_parser_prompt(
    narration: str,
    player_input: str = "",
    *,
    marks: list[dict[str, Any]] | None = None,
    npcs: list[dict[str, Any]] | None = None,
    locations: list[dict[str, Any]] | None = None,
    active_quests: list[dict[str, Any]] | None = None,
    open_offers: list[dict[str, Any]] | None = None,
) -> tuple[str, str]:
    """(system_prompt, user_prompt) for the parser call. JSON-only reply in the shape above, no example titles."""
    open_rows = []
    for row in list(active_quests or []) + list(open_offers or []):
        if not isinstance(row, dict):
            continue
        open_rows.append(
            {
                "code": row.get("code") or (f"Q{row['id']}" if row.get("id") else ""),
                "title": row.get("title") or "",
                # "declined": the player turned it down; the rules below say
                # not to propose it again (TODO n20).
                "status": row.get("status") or ("offered" if row in (open_offers or []) else "active"),
                "current_step": row.get("current_objective") or row.get("current_step_title") or "",
            }
        )
    payload = {
        "task": (
            "Read this turn. List quests the story offers to the player, quests the player takes, and changes to "
            "the open quests listed below. Most turns have none: then return empty lists."
        ),
        "player_input": str(player_input or "")[:600],
        "narration": str(narration or "")[:3200],
        "narrator_marks": list(marks or [])[:4],
        "known_npcs": _slim(npcs, ("code", "name", "role"), 12),
        "known_places": _slim(locations, ("code", "name"), 12),
        "open_quests": open_rows[:8],
        "return_shape": {
            "new": [
                {
                    "title": "short name of the job, 3-8 words",
                    "summary": "one sentence: what is asked and why",
                    "giver": "known_npcs code or name of whoever offers it; empty for a notice or board",
                    "steps": [{"title": "concrete action", "description": "what doing it means", "location": "known_places code or the place name the story gives, else empty"}],
                    "reward": {"gold": "number only if the story names an amount, else 0", "xp": 0, "items": ["only items the story promises"], "text": "the promise in the story's words"},
                    "difficulty": "easy, normal, hard or deadly",
                    "timer_turns": "0 unless the story sets a deadline",
                    "offer_line": "the giver's own words, or the sentence where the giver offers or agrees to the work, copied word for word",
                    "evidence": "a phrase copied word for word from narration or player_input",
                }
            ],
            "updates": [
                {"quest": "open_quests code", "action": "accept, decline, step_done, complete, fail or abandon", "evidence": "a phrase copied word for word"}
            ],
        },
        "rules": [
            "Only record work the story actually offers or the player actually takes. Scenery, rumours with no ask, and the player's own idle plans are not quests.",
            "evidence and offer_line must be copied word for word from narration or player_input.",
            "For offer_line quote the giver offering or agreeing to the work, not the player's wish or question.",
            "A new quest is always an offer. The player takes it or turns it down later.",
            "At most two new quests. Do not repeat anything already in open_quests; use updates for those.",
            "open_quests with status declined were turned down by the player. Never list them again under new.",
            "decline only for an offered quest that player_input turns down.",
            "Steps are concrete actions, one to six, each with the place the story names when it names one.",
            "Rewards only as the story states them; leave gold and xp at 0 when no amount is named.",
            "updates only for quests listed in open_quests, and only when the story shows the change.",
            "narrator_marks are hints from the narrator; still copy evidence from the text.",
            "Return {\"new\": [], \"updates\": []} when nothing applies.",
        ],
    }
    return _SYSTEM, json.dumps(payload, ensure_ascii=True)


# ---------------------------------------------------------------------------
# Reply coercion
# ---------------------------------------------------------------------------
def _loads_loose(raw: str) -> Any:
    text = str(raw or "").strip()
    if not text:
        return {}
    text = re.sub(r"^```(?:json)?\s*|\s*```\s*$", "", text, flags=re.I | re.M).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    start = text.find("{")
    if start < 0:
        return {}
    depth = 0
    in_str = False
    escape = False
    for index in range(start, len(text)):
        ch = text[index]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : index + 1])
                except Exception:
                    return {}
    return {}


def _as_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return []
    return [v for v in value if isinstance(v, dict)]


def parse_reply(raw: Any) -> dict[str, Any]:
    """Coerce a parser reply (dict or JSON text) into {"new": [...], "updates": [...]}; never raises."""
    try:
        data = raw if isinstance(raw, (dict, list)) else _loads_loose(str(raw or ""))
        if isinstance(data, list):
            data = {"new": data}
        if not isinstance(data, dict):
            data = {}
        new = data.get("new")
        if new is None:
            new = data.get("quests", data.get("new_quests", data.get("quest")))
        updates = data.get("updates")
        if updates is None:
            updates = data.get("quest_updates", data.get("changes"))
        return {
            "new": _as_list(new)[:MAX_NEW_PER_TURN],
            "updates": _as_list(updates)[:MAX_UPDATES_PER_TURN],
        }
    except Exception:
        return {"new": [], "updates": []}


def _norm(text: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def merge_marks(parsed: dict[str, Any], marks: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Fold narrator marks (from the QUEST / QUEST_DONE ops) into parsed proposals; set "source"."""
    out = {
        "new": [dict(item) for item in (parsed or {}).get("new") or [] if isinstance(item, dict)],
        "updates": [dict(item) for item in (parsed or {}).get("updates") or [] if isinstance(item, dict)],
    }
    had_parser = bool((parsed or {}).get("_parser_ran")) or bool(out["new"] or out["updates"])
    used_marks = False
    titles = {_norm(item.get("title")) for item in out["new"]}
    for mark in marks or []:
        if not isinstance(mark, dict):
            continue
        op = str(mark.get("op") or "").upper()
        if op == "QUEST":
            title = str(mark.get("title") or "").strip()
            if title and _norm(title) in titles:
                for item in out["new"]:
                    if _norm(item.get("title")) == _norm(title):
                        item["_from_mark"] = True
                used_marks = True
                continue
            if not title:
                continue
            step_text = str(mark.get("step") or "").strip()
            reward_text = str(mark.get("reward") or "").strip()
            out["new"].append(
                {
                    "title": title,
                    "summary": step_text or title,
                    "giver": str(mark.get("giver") or "").strip(),
                    "status": "offered",
                    "steps": [{"title": step_text or title, "description": step_text, "location": str(mark.get("location") or "")}],
                    "reward": {"text": reward_text},
                    "evidence": str(mark.get("evidence") or "").strip(),
                    "_from_mark": True,
                }
            )
            titles.add(_norm(title))
            used_marks = True
        elif op in {"QUEST_DONE", "QUEST_UPDATE"}:
            action = str(mark.get("action") or "step_done").strip().lower()
            ref = str(mark.get("quest") or "").strip()
            if not ref:
                continue
            if any(_norm(u.get("quest")) == _norm(ref) and u.get("action") == action for u in out["updates"]):
                used_marks = True
                continue
            out["updates"].append({"quest": ref, "action": action, "evidence": str(mark.get("evidence") or ""), "_from_mark": True})
            used_marks = True
    out["new"] = out["new"][:MAX_NEW_PER_TURN]
    out["updates"] = out["updates"][:MAX_UPDATES_PER_TURN]
    if used_marks and had_parser:
        out["source"] = "parser+marks"
    elif used_marks:
        out["source"] = "marks"
    else:
        out["source"] = str((parsed or {}).get("source") or "parser")
    return out


# ---------------------------------------------------------------------------
# Validation (pure)
# ---------------------------------------------------------------------------
def _ws(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


_NO_WORK_RE = re.compile(
    r"\b(?:no one|nobody|no-one|none)(?:'s| is| are)? (?:hiring|paying|needs? (?:help|hands|anyone))\b|"
    r"\bno (?:work|jobs?|hiring|coin to spare)\b|\bnot hiring\b|\bnothing (?:for you|to do)\b",
    re.I,
)


def _quote_sentences(quote_text: str, *texts: str) -> list[str]:
    quote = re.sub(r"\s+", " ", str(quote_text or "")).strip().lower()
    if not quote:
        return []
    sentences: list[str] = []
    for text in texts:
        for sentence in _SENTENCE_SPLIT.split(str(text or "")):
            flat = re.sub(r"\s+", " ", sentence).strip()
            if flat and (quote[:40] in flat.lower() or flat.lower() in quote):
                sentences.append(flat)
    return sentences


def _giver_sentences(narration: str, player_input: str, giver: dict[str, Any] | None, giver_ref: str, npcs: list[dict[str, Any]] | None) -> list[str]:
    """What the giver says in the prose, and the narration sentences that name them."""
    out: list[str] = []
    code = str((giver or {}).get("code") or "").strip()
    name = str((giver or {}).get("name") or "").strip()
    if code:
        try:
            from app.conversation import spoken_lines

            rows = [n for n in npcs or [] if isinstance(n, dict) and str(n.get("code") or "").strip()]
            if giver and not any(str(r.get("code")) == code for r in rows):
                rows.append(giver)
            for entry in spoken_lines(narration, rows, player_input):
                if entry.get("code") == code:
                    out.extend(_SENTENCE_SPLIT.split(str(entry.get("unit") or "")))
        except Exception:
            pass
    forms = []
    if code:
        forms.append(re.compile(r"\[\[\s*" + re.escape(code) + r"\s*\]\]"))
    for form in {name, name.split()[0] if name else "", re.sub(r"^the\s+", "", str(giver_ref or "").strip(), flags=re.I)}:
        if form and len(form) >= 3 and not re.fullmatch(r"[A-Z]\d*", form):
            forms.append(re.compile(r"(?<!\w)" + re.escape(form) + r"(?!\w)", re.I))
    if forms:
        for sentence in _SENTENCE_SPLIT.split(str(narration or "")):
            # "You approach Bertram and ask if he needs a hand" is the
            # player's ask, not the giver's offer.
            if re.match(r"\s*[\"'“]?you\b", sentence, re.I):
                continue
            if any(p.search(sentence) for p in forms):
                out.append(sentence)
    return [re.sub(r"\s+", " ", s).strip() for s in out if str(s or "").strip()]


def judge_offer(
    evidence: str,
    narration: str = "",
    player_input: str = "",
    *,
    offer_line: str = "",
    giver: dict[str, Any] | None = None,
    giver_ref: str = "",
    npcs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Does the exchange offer, ask for, or take on work? {"ok", "why", "checked"}.

    Playtest #81 (live, T11): the parser rightly proposed "Learn to forge
    steel", but quoted the player's wish ("you explain your desire to learn")
    instead of Bertram agreeing to teach, and a sentence-local check overruled
    it on that one sentence. The offer is judged on the exchange: the quote's
    own sentence, the parser's offer_line, and what the giver says or does in
    the prose. A player who asked for work plus a giver who agrees is an offer.
    A refusal in the quote's own sentence still vetoes ("no one is hiring").
    ``checked`` is the sentence the verdict rests on, for the turn report.
    """
    own = _quote_sentences(evidence, narration, player_input)
    quote = re.sub(r"\s+", " ", str(evidence or "")).strip()
    if not quote:
        return {"ok": False, "why": "no_quote", "checked": ""}
    pool = own or [quote]
    for sentence in pool:
        if _NO_WORK_RE.search(sentence):
            return {"ok": False, "why": "refusal", "checked": sentence[:240]}
    for sentence in pool:
        if _JOB_RE.search(sentence) or _ACCEPTS_WORK_RE.search(sentence):
            return {"ok": True, "why": "quote", "checked": sentence[:240]}
    if offer_line and evidence_found(offer_line, narration, player_input):
        for sentence in _quote_sentences(offer_line, narration, player_input) or [offer_line]:
            if not _NO_WORK_RE.search(sentence) and (_JOB_RE.search(sentence) or _ACCEPTS_WORK_RE.search(sentence)):
                return {"ok": True, "why": "offer_line", "checked": sentence[:240]}
    giver_lines = [s for s in _giver_sentences(narration, player_input, giver, giver_ref, npcs) if not _NO_WORK_RE.search(s)]
    for sentence in giver_lines:
        if _JOB_RE.search(sentence):
            return {"ok": True, "why": "giver_offers", "checked": sentence[:240]}
    if player_asks_for_work(player_input):
        for sentence in giver_lines:
            if _AGREES_RE.search(sentence):
                return {"ok": True, "why": "giver_agrees_to_ask", "checked": sentence[:240]}
    return {"ok": False, "why": "no_offer_in_exchange", "checked": pool[0][:240]}


def evidence_offers_work(
    evidence: str,
    narration: str = "",
    player_input: str = "",
    *,
    offer_line: str = "",
    giver: dict[str, Any] | None = None,
    giver_ref: str = "",
    npcs: list[dict[str, Any]] | None = None,
) -> bool:
    """
    The exchange around the evidence offers, asks for, or takes on work.

    The quote's sentence must carry job language (_JOB_RE) and must not be a
    refusal ("no one is hiring"); failing that, the offer_line or the giver's
    own words can carry it (see judge_offer). The sentence is read whole, so
    "if you bring the shipment up from the cellar" counts and "the shipment is
    in the cellar" alone does not.
    """
    return bool(
        judge_offer(
            evidence, narration, player_input, offer_line=offer_line, giver=giver, giver_ref=giver_ref, npcs=npcs
        )["ok"]
    )


_ACCEPTS_WORK_RE = re.compile(
    r"\b(?:i'?ll (?:take|do) (?:it|the job|the work|this)|i accept|deal\b|you'?re hired|it'?s yours|take the job)\b",
    re.I,
)


def evidence_found(evidence: str, *texts: str) -> bool:
    """The quote, whitespace- and case-normalized, is in one of the texts (or a 12+ char run of it is)."""
    quote = _ws(evidence).strip(" \"'“”‘’.,;:!?")
    if len(quote) < 4:
        return False
    haystacks = [_ws(t) for t in texts if t]
    if any(quote in hay for hay in haystacks):
        return True
    # Quote marks and punctuation drift: compare on letters and digits only.
    q = _norm(quote)
    if len(q) >= 4 and any(q in _norm(hay) for hay in haystacks):
        return True
    if len(q) < 12:
        return False
    for hay in haystacks:
        h = _norm(hay)
        match = SequenceMatcher(None, q, h, autojunk=False).find_longest_match(0, len(q), 0, len(h))
        if match.size >= 12 and match.size >= len(q) * 0.5:
            return True
    return False


def _int(value: Any, default: int = 0) -> int:
    try:
        if isinstance(value, bool):
            return default
        if isinstance(value, str):
            m = re.search(r"-?\d+", value)
            return int(m.group(0)) if m else default
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _resolve_npc(ref: Any, npcs: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    key = str(ref or "").strip()
    if not key:
        return None
    key = re.sub(r"^\[\[|\]\]$", "", key).strip()
    low = key.lower()
    for npc in npcs or []:
        if str(npc.get("code") or "").lower() == low:
            return npc
    for npc in npcs or []:
        name = str(npc.get("name") or "").strip().lower()
        if name and (name == low or re.sub(r"\s*\[\[.*?\]\]", "", name) == low):
            return npc
    for npc in npcs or []:
        name = str(npc.get("name") or "").strip().lower()
        first = name.split()[0] if name else ""
        if first and len(first) >= 3 and (low == first or low.split()[0] == first):
            return npc
    return None


def _resolve_place(ref: Any, locations: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    key = re.sub(r"^\[\[|\]\]$", "", str(ref or "").strip()).strip()
    if not key:
        return None
    low = key.lower()
    for loc in locations or []:
        if str(loc.get("code") or "").lower() == low or str(loc.get("name") or "").strip().lower() == low:
            return loc
    return None


_BOARD_RE = re.compile(r"\b(?:notice|board|posting|poster|sign|guild|bounty)\b", re.I)


def _resolve_quest(ref: Any, existing: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    key = str(ref or "").strip()
    if not key:
        return None
    low = key.lower()
    for quest in existing or []:
        if str(quest.get("code") or "").lower() == low or (quest.get("id") and f"q{quest['id']}" == low):
            return quest
    norm = _norm(key)
    best, best_score = None, 0.0
    for quest in existing or []:
        score = SequenceMatcher(None, norm, _norm(quest.get("title"))).ratio()
        if score > best_score:
            best, best_score = quest, score
    return best if best_score >= 0.6 else None


def _is_duplicate(item: dict[str, Any], existing: list[dict[str, Any]] | None, giver_id: Any, first_place: str) -> dict[str, Any] | None:
    title = _norm(item.get("title"))
    for quest in existing or []:
        status = str(quest.get("status") or "active")
        if status not in {"active", "offered", "declined"}:
            continue
        ratio = SequenceMatcher(None, title, _norm(quest.get("title"))).ratio()
        if ratio >= 0.6:
            return quest
        if status == "declined" and giver_id and quest.get("giver_npc_id") == giver_id and ratio >= 0.4:
            # The same giver rewording a job the player turned down (TODO n20).
            return quest
        if (
            giver_id
            and quest.get("giver_npc_id") == giver_id
            and first_place
            and _norm(first_place) == _norm(quest.get("first_step_location") or "")
        ):
            return quest
    return None


_LEGAL = {
    "accept": {"offered"},
    "decline": {"offered"},
    "step_done": {"active"},
    "complete": {"active"},
    "fail": {"active", "offered"},
    "abandon": {"active", "offered"},
}


def validate_quest_changes(
    changes: dict[str, Any],
    *,
    narration: str,
    player_input: str = "",
    npcs: list[dict[str, Any]] | None = None,
    locations: list[dict[str, Any]] | None = None,
    existing: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Pure check. Returns (accepted_changes, rejected) where each rejected row is {"kind", "item", "reasons"}."""
    accepted: dict[str, Any] = {"source": (changes or {}).get("source") or "parser", "new": [], "updates": []}
    rejected: list[dict[str, Any]] = []
    accepts_now = player_accepts(player_input)
    npc_names = {str(n.get("name") or "").strip().lower() for n in npcs or []}
    place_names = {str(p.get("name") or "").strip().lower() for p in locations or []}
    seen_titles: set[str] = set()

    for raw in list((changes or {}).get("new") or [])[: MAX_NEW_PER_TURN * 2]:
        if not isinstance(raw, dict):
            continue
        reasons: list[str] = []
        title = re.sub(r"\s+", " ", str(raw.get("title") or "")).strip(" .\"'")
        if not (3 <= len(title) <= 80):
            reasons.append("title_length")
        elif title.lower() in npc_names or title.lower() in place_names:
            reasons.append("title_is_a_name")
        elif _norm(title) in seen_titles:
            reasons.append("duplicate_in_turn")
        evidence = str(raw.get("evidence") or "").strip()
        offer_line = str(raw.get("offer_line") or "").strip()
        if not evidence_found(evidence, narration, player_input) and evidence_found(offer_line, narration, player_input):
            # The giver's words are grounded even when the other quote drifted.
            evidence = offer_line
        giver_ref = str(raw.get("giver") or "").strip()
        giver = _resolve_npc(giver_ref, npcs)
        checked = ""
        if not evidence_found(evidence, narration, player_input):
            reasons.append("evidence_not_in_text")
        elif not raw.get("_from_mark"):
            # Grounded is not enough: the exchange has to offer or ask for
            # work. Qwen3 8B turned "the shipment is in the cellar" (said right
            # after "no one is hiring") into an offered quest.
            verdict = judge_offer(
                evidence, narration, player_input, offer_line=offer_line, giver=giver, giver_ref=giver_ref, npcs=npcs
            )
            checked = verdict["checked"]
            if not verdict["ok"]:
                reasons.append("evidence_is_not_an_offer")
        giver_named_in_story = bool(giver_ref) and _norm(giver_ref).replace("the ", "", 1) in _norm(f"{narration} {player_input}")
        if giver_ref and giver is None and not _BOARD_RE.search(giver_ref) and not giver_named_in_story:
            reasons.append("unknown_giver")
        steps_in = _as_list(raw.get("steps"))
        steps: list[dict[str, Any]] = []
        for step in steps_in[:MAX_STEPS]:
            step_title = re.sub(r"\s+", " ", str(step.get("title") or step.get("description") or "")).strip()[:120]
            if not step_title:
                continue
            place_ref = str(step.get("location") or step.get("location_name") or "").strip()
            place = _resolve_place(place_ref, locations)
            steps.append(
                {
                    "title": step_title,
                    "description": str(step.get("description") or step_title).strip()[:400],
                    "location_code": str(place.get("code") or "") if place else "",
                    "location_name": str(place.get("name") or "") if place else re.sub(r"^\[\[|\]\]$", "", place_ref)[:100],
                }
            )
        if not steps:
            summary = str(raw.get("summary") or title).strip()
            if summary:
                steps = [{"title": summary[:120], "description": summary[:400], "location_code": "", "location_name": ""}]
            else:
                reasons.append("no_steps")
        first_place = steps[0]["location_name"] if steps else ""
        dup = _is_duplicate({"title": title}, existing, giver.get("id") if giver else None, first_place)
        if dup is not None:
            ref = dup.get("code") or dup.get("id")
            # A job the player turned down is not offered again (TODO n20).
            reasons.append(f"declined_before:{ref}" if str(dup.get("status") or "") == "declined" else f"duplicate_of:{ref}")
        if reasons:
            rejected.append({"kind": "new", "item": raw, "reasons": reasons, "checked": checked})
            continue
        reward = raw.get("reward") if isinstance(raw.get("reward"), dict) else {}
        gold = max(0, min(REWARD_GOLD_CAP, _int(reward.get("gold"), 0)))
        xp = max(0, min(REWARD_XP_CAP, _int(reward.get("xp"), 0)))
        items = [re.sub(r"\s+", " ", str(i)).strip()[:80] for i in (reward.get("items") or []) if str(i or "").strip()]
        difficulty = str(raw.get("difficulty") or "normal").strip().lower()
        if difficulty not in DIFFICULTIES:
            difficulty = "normal"
        # Every new quest is an offer (TODO n20): only Accept, or a later
        # accept the engine can tie to this one offer, makes it the player's.
        status = "offered"
        seen_titles.add(_norm(title))
        accepted["new"].append(
            {
                "title": title,
                "summary": re.sub(r"\s+", " ", str(raw.get("summary") or title)).strip()[:400],
                "giver": giver_ref,
                "giver_npc_id": giver.get("id") if giver else None,
                "giver_name": str(giver.get("name") or "") if giver else (giver_ref if giver_ref else ""),
                "status": status,
                "steps": steps,
                "reward": {
                    # 0 means "let the engine size it" (create_quest's defaults).
                    "gold": gold or None,
                    "xp": xp or None,
                    "items": items[:REWARD_ITEMS_CAP],
                    "text": str(reward.get("text") or "").strip()[:200],
                },
                "difficulty": difficulty,
                "timer_turns": max(0, min(60, _int(raw.get("timer_turns"), 0))),
                "evidence": evidence[:300],
                "target_location_id": None,
            }
        )
        if len(accepted["new"]) >= MAX_NEW_PER_TURN:
            break

    for raw in list((changes or {}).get("updates") or [])[: MAX_UPDATES_PER_TURN * 2]:
        if not isinstance(raw, dict):
            continue
        reasons = []
        action = str(raw.get("action") or "").strip().lower().replace(" ", "_")
        if action == "done":
            action = "step_done"
        elif action in {"refuse", "reject", "turn_down"}:
            action = "decline"
        # Turned-down rows are kept only for the re-offer check; no update may touch them.
        quest = _resolve_quest(raw.get("quest"), [q for q in existing or [] if str(q.get("status") or "") != "declined"])
        if action == "accept" and quest is not None and str(quest.get("status") or "") == "active":
            continue  # already taken this turn (a typed accept or the Accept button)
        if action not in QUEST_ACTIONS:
            reasons.append("unknown_action")
        if quest is None:
            reasons.append("unknown_quest")
        evidence = str(raw.get("evidence") or "").strip()
        if not evidence_found(evidence, narration, player_input):
            # An accept or a refusal the player typed is evidence enough on its own.
            if not ((action == "accept" and accepts_now) or (action == "decline" and _DECLINE_RE.search(str(player_input or "")))):
                reasons.append("evidence_not_in_text")
        if quest is not None and action in _LEGAL and str(quest.get("status") or "") not in _LEGAL[action]:
            reasons.append(f"illegal_transition:{quest.get('status')}->{action}")
        if reasons:
            rejected.append({"kind": "update", "item": raw, "reasons": reasons, "checked": evidence[:240]})
            continue
        accepted["updates"].append(
            {"quest_id": quest.get("id"), "code": quest.get("code"), "title": quest.get("title"), "action": action, "evidence": evidence[:300]}
        )
        if len(accepted["updates"]) >= MAX_UPDATES_PER_TURN:
            break
    return accepted, rejected


# ---------------------------------------------------------------------------
# Apply (DB)
# ---------------------------------------------------------------------------
def _rows(conn, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    except Exception:
        return []


def _journal(conn, turn: int, content: str) -> None:
    conn.execute("INSERT INTO journal (turn, kind, content) VALUES (?, ?, ?)", (int(turn), "quest", str(content)[:1400]))


def load_quest_context(conn, turn: int = 0) -> dict[str, list[dict[str, Any]]]:
    """NPCs, places and open quests from the live DB, in the shapes validation reads.

    Offers turned down in the last DECLINE_MEMORY_TURNS turns come along too, so
    the same job is not filed again every time the giver mentions it (TODO n20).
    """
    from app.quests import DECLINE_MEMORY_TURNS

    npcs = _rows(conn, "SELECT id, code, name, role FROM npcs ORDER BY id DESC LIMIT 200")
    locations = _rows(conn, "SELECT id, code, name FROM locations ORDER BY id DESC LIMIT 200")
    existing = _rows(
        conn,
        """
        SELECT q.id, q.code, q.title, q.status, q.giver_npc_id, q.current_step, q.total_steps,
               (SELECT s.location_name FROM quest_steps s WHERE s.quest_id = q.id AND s.step_number = 1) AS first_step_location
        FROM quests q
        WHERE q.status IN ('active', 'offered')
           OR (q.status = 'declined' AND COALESCE(q.failed_turn, 0) >= ?)
        ORDER BY q.id DESC LIMIT 40
        """,
        (int(turn) - DECLINE_MEMORY_TURNS,),
    )
    return {"npcs": npcs, "locations": locations, "existing": existing}


def apply_quest_changes(conn, changes: dict[str, Any], *, narration: str, player_input: str = "", turn: int = 0) -> dict[str, Any]:
    """Validate against the live DB, create/advance quests, journal + event-log each one. Returns a report for the trace."""
    report: dict[str, Any] = {
        "status": "skipped",
        "source": str((changes or {}).get("source") or "parser"),
        "created": [],
        "updated": [],
        "rejected": [],
    }
    try:
        if not isinstance(changes, dict) or not (changes.get("new") or changes.get("updates")):
            return report
        from app.quests import accept_offered, advance_quest_step, create_quest, decline_offered, fail_quest, pay_quest_completion

        ctx = load_quest_context(conn, int(turn))
        accepted, rejected = validate_quest_changes(
            changes,
            narration=narration,
            player_input=player_input,
            npcs=ctx["npcs"],
            locations=ctx["locations"],
            existing=ctx["existing"],
        )
        report["rejected"] = [
            # "quote": the sentence the offer check judged, so a review can see
            # which words were read (playtest #81).
            {
                "kind": r["kind"],
                "title": str(r["item"].get("title") or r["item"].get("quest") or "")[:80],
                "reasons": r["reasons"],
                "quote": str(r.get("checked") or "")[:240],
            }
            for r in rejected
        ]
        for item in accepted["new"]:
            target_id = None
            first_code = item["steps"][0].get("location_code") if item["steps"] else ""
            if first_code:
                row = conn.execute("SELECT id FROM locations WHERE code = ?", (first_code,)).fetchone()
                target_id = int(row["id"]) if row else None
            description = item["summary"]
            if item["reward"]["text"]:
                description = f"{description} Promised: {item['reward']['text']}"
            quest_id = create_quest(
                conn,
                title=item["title"],
                description=description[:800],
                steps=item["steps"],
                reward_gold=item["reward"]["gold"],
                reward_xp=item["reward"]["xp"],
                reward_items=item["reward"]["items"],
                difficulty=item["difficulty"],
                timer_turns=item["timer_turns"],
                giver_npc_id=item["giver_npc_id"],
                target_location_id=target_id,
                created_turn=int(turn),
                notes=f"parser:{accepted['source']}; evidence: {item['evidence']}"[:900],
                status=item["status"],
            )
            code = f"Q{quest_id}"
            giver = f" (from {item['giver_name']})" if item["giver_name"] else ""
            _journal(conn, turn, f"New job offered: {item['title']}{giver}")
            report["created"].append({"code": code, "title": item["title"], "status": item["status"]})
        for upd in accepted["updates"]:
            qid = int(upd["quest_id"])
            action = upd["action"]
            title = upd["title"] or upd["code"]
            if action == "accept":
                # One path for every accept (TODO n20); it journals.
                if accept_offered(conn, qid, turn=int(turn)) is None:
                    continue
            elif action == "decline":
                if decline_offered(conn, qid, turn=int(turn)) is None:
                    continue
            elif action == "step_done":
                res = advance_quest_step(conn, qid, turn=int(turn))
                pay_quest_completion(conn, qid, res)
                _journal(conn, turn, f"Quest complete: {title}" if res.get("completed") else f"Step done: {title}")
            elif action == "complete":
                for _ in range(MAX_STEPS):
                    res = advance_quest_step(conn, qid, turn=int(turn))
                    pay_quest_completion(conn, qid, res)
                    if not res.get("ok") or res.get("completed"):
                        break
                _journal(conn, turn, f"Quest complete: {title}")
            elif action == "fail":
                fail_quest(conn, qid, turn=int(turn), reason=f"Failed in play: {upd['evidence'][:200]}")
                _journal(conn, turn, f"Quest failed: {title}")
            elif action == "abandon":
                conn.execute("UPDATE quests SET status = 'abandoned', failed_turn = ? WHERE id = ?", (int(turn), qid))
                _journal(conn, turn, f"Quest abandoned: {title}")
            report["updated"].append({"code": upd["code"], "action": action})
        report["status"] = "applied" if (report["created"] or report["updated"]) else ("rejected" if report["rejected"] else "empty")
        return report
    except Exception as exc:  # never break the turn
        report["status"] = "error"
        report["error"] = str(exc)[:300]
        return report
