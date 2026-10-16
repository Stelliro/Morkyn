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
REWARD_KARMA_CAP = 10

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
    # Review of #81: a bare "apprentice", "deliveries" or "show you how" also
    # named a smith's helper at the anvil, late carts and street directions.
    r"(?:extra|spare) (?:set of )?hands|every hand helps|deliver (?:this|these|it|them|the)|"
    r"(?:any|some|a bit of|odd|plenty of|honest|steady|paying) work|work (?:here|to do|for you|for me|for us)|"
    r"(?:teach|train) you|show you (?:how (?:it'?s done|to work|the trade|the craft)|the ropes)|"
    r"(?:an|my|as an?|need an?|take on an?) apprentice|apprenticeship|take you on|"
    r"(?:start|begin) (?:there|tomorrow|today|in the morning|at dawn|first thing))\b",
    re.I,
)
# The player asking for work or training. A conversation trigger for the gate:
# when the player asks, the answer is worth reading even if it is phrased in
# words the job list has never seen (playtest #81: "any work i can do?" was
# answered with an offer on T10, and nothing read it).
_ASKS_WORK_RE = re.compile(
    r"\b(?:any|some|a|the|honest|paying|more) (?:work|jobs?|tasks?|errands?|employment)\b|"
    # Asked of the other person: "do you need a hand", "you wanted an extra set
    # of hands" (T11). "I need a hand finding the inn" is not asking for work.
    r"\b(?:you|ya)\s+(?:\w+\s+)?(?:need|needs|want|wanted|use) (?:a |an |an extra |another |some |any )?"
    r"(?:help|hand|hands|set of hands|extra set of hands|helper|worker)\b|"
    r"\b(?:can|could|may|shall) i (?:help|assist|lend|work|be of use)\b|"
    r"\b(?:hire|employ) me\b|\bhiring\b|\bapprentic\w*|\b(?:teach|train) me\b|\bshow me how\b|"
    r"\blearn (?:to|how to|your (?:trade|craft)|the (?:trade|craft))\b|"
    r"\bearn (?:some |a |my )?(?:coin|money|gold|silver|keep|living|wage)\b|\bwork for (?:you|coin|pay|food)\b|"
    r"\blooking for (?:work|a job|employment)\b|"
    # "... to ask the tallyman what work he'll take against my debt" (8B run 32,
    # T1): the offer that answered it was never parsed.
    r"\b(?:what|which|whatever) (?:work|jobs?|tasks?|errands?)\b|"
    r"\b(?:ask\w*|enquir\w*|inquir\w*)\s+(?:\w+\s+){0,3}?(?:about|for|after)\s+(?:work|a job|jobs|employment)\b|"
    r"\bwork (?:it|this|that|my debt|the debt) off\b",
    re.I,
)
# A giver saying yes to what the player asked for. Counts as an offer only
# beside a player line that asked for work (see judge_offer).
_AGREES_RE = re.compile(
    # Not a bare nod: "Bertram nods and points down the lane" agrees to nothing.
    r"\b(?:agree[sd]?|says? yes|said yes|you'?re hired|welcome aboard|it'?s settled|"
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
    if _accept_re().search(text) or _SIMPLE_ACCEPT_RE.search(text):
        return True
    try:
        from app.local_intel import typed_accept

        # Signing for it and "we'll take it" (Saltmarrow #114): one vocabulary
        # for the engine's accept, the prompt and this parser.
        return typed_accept(text)
    except Exception:  # pragma: no cover - local_intel always importable in the app
        return False


_QUOTED_RE = re.compile(r'"[^"]*"|“[^”]*”')
# The player holds off or says no (7B run 7, T4-T5): "I haven't said yes yet",
# "No deal, Oriel. I'll take my chances on the flats."
_HOLDS_OFF_RE = re.compile(
    r"\b(?:(?:haven['’]?t|have\s+not|didn['’]?t|did\s+not|never)\s+(?:said|say|agreed?|accepted?|taken|took)\b|"
    r"not\s+(?:yet|so\s+fast)\b|hold\s+on\b)",
    re.I,
)
_REFUSES_RE = re.compile(
    r"\b(?:no\s+deal|no\s+thanks|not\s+interested|i(?:['’]ll|\s+will)?\s+pass\b|forget\s+it|"
    r"find\s+someone\s+else|(?:i['’]m|i\s+am)\s+not\s+(?:taking|doing)|"
    r"(?:won['’]?t|will\s+not)\s+(?:take|do)\s+(?:it|that|this|the\s+(?:job|work|offer))|"
    r"i(?:['’]ll|\s+will)?\s+decline|turn\s+(?:it|that|this|the\s+(?:job|offer|work|task|errand))\s+down|"
    r"(?:refuse|say\s+no\s+to)\s+(?:it|that|this|the\s+(?:job|offer|work|task|errand)))",
    re.I,
)
# Starting the work in the player's own words: "I'll start", "let's get to it",
# "I grab a broom and start on the deck". Not "I start back toward the door".
_STARTS_WORK_RE = re.compile(
    r"\b(?:(?:i|we)\s+(?:\w+\s+){0,4}?(?:start|begin|set\s+to|make\s+a\s+start)"
    r"(?!\s+(?:to\s+)?(?:walk|leav|back|toward|away|off|out|for\s+the))|"
    r"(?:i['’]ll|we['’]ll|let['’]s)\s+(?:get\s+)?(?:start(?:ed)?|begin|get\s+to\s+(?:it|work))|"
    r"get\s+to\s+work|you['’]re\s+on)\b",
    re.I,
)


def _player_own_line(player_input: str) -> str:
    """The typed line, without engine notes appended below a blank line."""
    return re.split(r"\n\s*\n", str(player_input or ""), maxsplit=1)[0]


def player_refuses(player_input: str) -> bool:
    """The player's line says no to a job (7B run 7, T5: "No deal, Oriel")."""
    return bool(_REFUSES_RE.search(_player_own_line(player_input)))


def player_takes_job(
    quest: dict[str, Any] | None,
    player_input: str,
    existing: list[dict[str, Any]] | None = None,
    narration: str = "",
) -> bool:
    """
    The player's own line takes this job (7B run 7, T3).

    The parser cited Oriel's "Good choice. Let's see what the deck has in
    store for us." as the accept while the player had only said "Give me a
    number, Oriel, or I'm off to the flats on my own." The story may answer
    for the giver, never for the player: a job is taken by the player's words
    (agreeing, signing, "I'll take the job"), or by the player starting the
    work in their own words.
    """
    own = _player_own_line(player_input)
    if not own.strip() or quest is None:
        return False
    if _HOLDS_OFF_RE.search(own) or _REFUSES_RE.search(own):
        return False
    if player_accepts(own) and _means_this_offer(quest, existing, own):
        return True
    # "I'll take the patrol" for "Help with mudflats patrol" (7B run 27, T3):
    # taking the job by a word of its own title.
    title_words = _title_words(str(quest.get("title") or ""))
    for match in re.finditer(r"\bi(?:['’]ll|\s+will)\s+(?:take|do|handle|run|walk)\s+(?:the|this|that|your)\s+([a-z]+)", own, re.I):
        if match.group(1).lower() in title_words:
            return True
    # The job's own verb on its own subject: "I'll clear the Stormbreaker" for
    # "Clear the Wreckage", the wreckage "from the Stormbreaker" (8B run 56, T3).
    lead = re.findall(r"[a-z][a-z']+", str(quest.get("title") or "").lower())
    job_verb = _stem(lead[0]) if lead else ""
    about = title_words | {w for w in re.findall(r"[a-z][a-z']+", str(quest.get("description") or "").lower()) if len(w) >= 4}
    if job_verb and job_verb not in _QUEST_STOP_STEMS:
        for match in re.finditer(r"\bi(?:['’]ll|\s+will)\s+([a-z]+)\s+(?:the|this|that|your|her|it)\b\s*([a-z]*)", own, re.I):
            obj = match.group(2).lower()
            if _stem(match.group(1)) == job_verb and (not obj or obj in about or match.group(0).lower().endswith(" it")):
                return True
    if _STARTS_WORK_RE.search(own):
        return True
    # The player names the price and the giver agrees (7B run 6, T6: "Two gold
    # for the whole pile, sorted by noon. Yes or no?" - "the gold is yours"):
    # the player's terms are the player's yes.
    if narration and agreed_job_price(narration, own)[1] == "player_terms_agreed":
        return True
    # "I sort the pile" for "Sort salvaged goods": the job's own verb, done by the player.
    acts = _QUOTED_RE.sub(" ", own)
    first = re.findall(r"[a-z][a-z']+", str(quest.get("title") or "").lower())
    verb = _stem(first[0]) if first else ""
    if verb and verb not in _QUEST_STOP_STEMS:
        for match in re.finditer(r"\b(?:i|we)\s+(?:\w+\s+){0,2}?([a-z][a-z']+)", acts, re.I):
            if _stem(match.group(1)) == verb:
                return True
    return False


def _title_words(title: str) -> set[str]:
    stop = {"the", "a", "an", "of", "to", "for", "and", "in", "on", "at", "from", "with", "word"}
    # "work", "job", "task" name every job, so they tell none apart (7B run 29, T4).
    try:
        from app.local_intel import JOB_WORDS
    except Exception:  # pragma: no cover - local_intel always importable in the app
        JOB_WORDS = frozenset()
    return {w for w in re.findall(r"[a-z]{4,}", str(title or "").lower()) if w not in stop and w not in JOB_WORDS}


# A typed refusal of the job itself: a bare "pass on" ("I pass on the message")
# or "refuse" is not one (n20 review).
_TYPED_DECLINE_RE = re.compile(
    r"\b(?:i(?:'ll| will)? decline|no thanks|not interested|"
    r"turn (?:it|them|the (?:job|offer|work|task|errand)) down|"
    r"(?:refuse|pass on|say no to) (?:it|that|this|the (?:job|offer|work|task|errand)))\b",
    re.I,
)


def _means_this_offer(quest: dict[str, Any], existing: list[dict[str, Any]] | None, player_input: str) -> bool:
    """A typed answer can only mean ``quest``: it is the one offer open, or the line names its title."""
    words = _title_words(str(quest.get("title") or ""))
    if words and words & set(re.findall(r"[a-z]{4,}", str(player_input or "").lower())):
        return True
    offered = [q for q in existing or [] if str(q.get("status") or "") == "offered"]
    return len(offered) == 1 and offered[0].get("id") == quest.get("id")


_ASKS_PAY_RE = re.compile(
    r"\b(?:what|how\s+much)\s+(?:does|will|would|do)\s+(?:it|that|this|they|you|the\s+[\w'’-]+(?:\s+[\w'’-]+)?)\s+pay\b"
    r"|\bwhat(?:'s|\s+is)\s+the\s+(?:pay|wage|wages|rate|reward)\b|\bhow\s+much\s+is\s+it\s+worth\s+to\s+you\b",
    re.I,
)


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
    # Asking what something pays is job talk (7B run 32, T2: "What are the
    # tallies, and what does the run pay?" was answered with the two runs and
    # "a few coppers", and the parser was never asked).
    if _ASKS_PAY_RE.search(player_input):
        return "player_asks_pay"
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
            "One offer is one quest. A promise of later work in the same offer (an apprenticeship, more jobs) is that quest's reward text, not a second quest.",
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


# Work others ask for is not work offered: "You're not the first to come asking
# for work" made "Settle Debt with Gregory Cropper" (8B run 65, T1).
_ASKED_FOR_WORK_RE = re.compile(
    r"\b(?:ask\w*|com\w*\s+(?:in\s+)?ask\w*)\s+(?:for|after)\s+(?:work|a\s+job|jobs)\b"
    # The giver telling back what the player wants: "You're looking for work to
    # pay it off, I assume" (8B run 76, T2).
    r"|\byou(?:['’]re|\s+are|['’]ve\s+come\s+to|\s+came\s+to|\s+want\s+to)\s+(?:\w+\s+)?look\w*\s+for\s+(?:work|a\s+job|jobs)\b[^,.;!?]*"
    r"|\bpay\s+(?:it|that|the\s+debt|your\s+debt)\s+off\b"
    # ... and work said not to be given: "I don't take on just anyone" (same turn).
    r"|\b(?:don['’]?t|do\s+not|won['’]?t|will\s+not|never)\s+(?:\w+\s+){0,2}?(?:take\s+on|hire|give\s+work|hand\s+out\s+work)\b[^,.;!?]*",
    re.I,
)


def _offer_text(sentence: str) -> str:
    """The sentence with what offers no work taken out: work others ask for, work refused, the player's own debt."""
    return _PLAYER_OWES_RE.sub(" ", _ASKED_FOR_WORK_RE.sub(" ", str(sentence or "")))
_NO_WORK_RE = re.compile(
    r"\b(?:no one|nobody|no-one|none)(?:'s| is| are)? (?:hiring|paying|needs? (?:help|hands|anyone))\b|"
    r"\bno (?:work|jobs?|hiring|coin to spare)\b|\bnot hiring\b|\bnothing (?:for you|to do)\b|"
    r"\b(?:i|we) work alone\b|\b(?:don'?t|do not) need (?:help|a hand|any help|anyone|hands|you)\b|"
    r"\b(?:can'?t|cannot) afford (?:help|a hand|to pay|another)\b",
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


_PLAYER_OWES_RE = re.compile(
    r"\b(?:if\s+)?you\s+(?:\w+\s+){0,2}?(?:pay|paid|pays|owe|owes|owed)\b[^.!?]{0,40}"
    r"|\bpay\s+(?:your|what\s+you\s+owe|the\s+guild|it\s+back|us\s+back|them\s+back|back\s+what)\b[^.!?]{0,30}"
    r"|\b(?:your|the|a|any|old|such)?\s*debts?\b[^.!?]{0,30}"
    # "You'll need to work it off" is the player's own debt, not a job (8B run 74, T2).
    r"|\bwork\s+(?:it|that|this|them|the\s+debt|your\s+debt|the\s+rest)\s+off\b",
    re.I,
)


def _players_words_only(evidence: str, offer_line: str, player_input: str, narration: str = "") -> bool:
    """The parser's quote and offer line are the player's own words, or the prose retelling them ("You ...")."""
    own = _ws(str(player_input or "")).lower()
    prose = _ws(str(narration or "")).lower()

    def _spoken_to_player(flat: str) -> bool:
        # "You haul the things that sink," she said: someone telling the player
        # the job, not the prose retelling the player's act (8B run 89, T3).
        # The parser joins and re-punctuates the line; its opening clause is what the prose holds.
        head = re.split(r"[,.;:!?—–-]", flat, maxsplit=1)[0].strip()
        at = prose.find(head) if len(head) >= 12 else -1
        return at >= 0 and sum(prose[:at].count(mark) for mark in ('"', "“", "”")) % 2 == 1

    def _players(text: str) -> bool:
        flat = _ws(str(text or "")).strip(" \"'“”.,;:!?").lower()
        return not flat or flat in own or (bool(re.match(r"^\W*you\b", flat)) and not _spoken_to_player(flat))

    return _players(evidence) and _players(offer_line)


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
    # The giver's refusal anywhere in this exchange vetoes it: "Sorry, I have
    # nothing for you today" answers "do you have any work?" (#81 review).
    all_giver = _giver_sentences(narration, player_input, giver, giver_ref, npcs)
    for sentence in all_giver:
        if _NO_WORK_RE.search(sentence):
            return {"ok": False, "why": "giver_refuses", "checked": sentence[:240]}
    # The player's own words, or the prose retelling them ("You ask ..."), are
    # the ask, never the offer: job words count only in someone else's
    # sentence. The player taking a job on ("I'll take the job") still counts.
    # Quote marks and apostrophes either way: the prose's “What job have you
    # got ...?” is the player's typed "What job have you got ...?" (8B run 74, T2).
    def bare(text: str) -> str:
        text = str(text or "").replace("’", "'").replace("‘", "'")
        return re.sub(r"\s+", " ", re.sub(r"[\"“”]", "", text)).strip().lower()

    own_flat = bare(player_input)
    for sentence in pool:
        players = bare(sentence) in own_flat or re.match(r"^\W*you\b", sentence, re.I)
        if _ACCEPTS_WORK_RE.search(sentence) or (not players and _JOB_RE.search(_offer_text(sentence))):
            return {"ok": True, "why": "quote", "checked": sentence[:240]}
    if offer_line and evidence_found(offer_line, narration, player_input):
        for sentence in _quote_sentences(offer_line, narration) or [offer_line]:
            # The player's own question is no offer line either (8B run 76, T2).
            if bare(sentence) and bare(sentence) in own_flat:
                continue
            if not _NO_WORK_RE.search(sentence) and (
                _JOB_RE.search(_offer_text(sentence)) or _ACCEPTS_WORK_RE.search(sentence)
            ):
                return {"ok": True, "why": "offer_line", "checked": sentence[:240]}
    giver_lines = all_giver
    for sentence in giver_lines:
        # The player's own debt is not work offered: "And if you don't pay your
        # share, they don't let you walk away" made a job (8B run 2, T1).
        if _JOB_RE.search(_offer_text(sentence)):
            return {"ok": True, "why": "giver_offers", "checked": sentence[:240]}
    if player_asks_for_work(player_input):
        for sentence in giver_lines:
            if _AGREES_RE.search(sentence):
                return {"ok": True, "why": "giver_agrees_to_ask", "checked": sentence[:240]}
            # The task set for one who asked: "You'll need to clear a full load,
            # something worth at least ten silver" (8B run 47, T2); working off
            # one's own debt is no task set (run 74, T2).
            if re.search(r"\byou['’]ll\s+(?:need|have)\s+to\s+(?!work\s+(?:it|that|this|the\s+debt|your\s+debt)\s+off)"
                         r"(?!pay\b|wait\b|be\s+careful|prove)[a-z]+", _offer_text(sentence), re.I):
                return {"ok": True, "why": "giver_sets_the_task", "checked": sentence[:240]}
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
    # "Deal." agrees; "I don't deal in charity" does not (8B run 65, T1).
    r"\b(?:i'?ll (?:take|do) (?:it|the job|the work|this)|i accept|(?<!n't )(?<!not )deal(?=\s*[.!?,\"”'’]|\s*$)|"
    r"you'?re hired|it'?s yours|take the job)\b",
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
    # A job for a name: giver "clerk" for Elias Vane, the clerk behind the desk,
    # left the job with no giver (8B run 90, T2). The one person holding it;
    # two or more is no one.
    job = re.sub(r"^(?:the|a|an)\s+", "", low).strip()
    if job and re.fullmatch(r"[a-z][a-z' -]{2,40}", job):
        holders = [
            npc for npc in npcs or []
            if str(npc.get("role") or "").strip().lower() in (job, job + "s")
            or str(npc.get("role") or "").strip().lower().split()[-1:] == job.split()[-1:]
        ]
        if len(holders) == 1:
            return holders[0]
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


_SPEECH_RE = re.compile(r'"([^"]+)"|“([^”]+)”')


def _offer_speaker(narration: str, quote: str, npcs: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    """The one known person named in the paragraph where the offer is spoken (7B run 6, T3).

    The parser filed Oldfield's spoken offer under Simon, who was only standing
    by. When the offer is a quoted line and its paragraph names exactly one
    known person outside the quotes, that person said it. Anything less certain
    (no quote found, two people named) returns None and the parser's giver stands.
    """
    core = _ws(re.sub(r'^[\s"“”\']+|[\s"“”\']+$', "", str(quote or ""))).lower()
    if len(core) < 12 or not npcs:
        return None
    probe = core[:40]
    for paragraph in re.split(r"\n\s*\n", str(narration or "")):
        spoken = [_ws(m.group(1) or m.group(2) or "").lower() for m in _SPEECH_RE.finditer(paragraph)]
        if not any(probe in s or s in core for s in spoken if len(s) >= 12):
            continue
        outside = _SPEECH_RE.sub(" ", paragraph)
        named = []
        for npc in npcs:
            name = str(npc.get("name") or "").strip()
            code = str(npc.get("code") or "").strip()
            first = name.split()[0] if name else ""
            hit = (code and f"[[{code}]]" in outside) or (
                name and re.search(rf"\b{re.escape(name)}\b", outside)
            ) or (len(first) >= 3 and re.search(rf"\b{re.escape(first)}\b", outside))
            if hit:
                named.append(npc)
        return named[0] if len(named) == 1 else None
    return None


def _named_in(narration: str, npc: dict[str, Any]) -> bool:
    """The person is in the prose: by code, full name or first name."""
    text = str(narration or "")
    name = str(npc.get("name") or "").strip()
    code = str(npc.get("code") or "").strip()
    first = name.split()[0] if name else ""
    return bool(
        (code and f"[[{code}]]" in text)
        or (name and re.search(rf"\b{re.escape(name)}\b", text))
        or (len(first) >= 3 and re.search(rf"\b{re.escape(first)}\b", text))
    )


def _shown_by_role(narration: str, npc: dict[str, Any] | None, npcs: list[dict[str, Any]] | None) -> bool:
    """The prose calls this person by their job ("The tallyman's fingers trace the line"), and no one else
    listed has that job: Ralph's job was filed as offered by no one (8B run 52, T3)."""
    if not npc:
        return False
    words = [w for w in re.findall(r"[a-z]+", str(npc.get("role") or "").lower()) if len(w) >= 4]
    if not words:
        return False
    head = words[-1]
    if not re.search(rf"\b[Tt]he\s+(?:[a-z]+\s+)?{re.escape(head)}\b", str(narration or "")):
        return False
    others = [n for n in npcs or [] if n is not npc and str(n.get("name") or "") != str(npc.get("name") or "")
              and head in str(n.get("role") or "").lower()]
    return not others


_NOT_A_SPEAKER = frozenset({
    "You", "Your", "He", "She", "They", "It", "His", "Her", "Their", "The", "A", "An", "I", "Is", "Was", "This",
    "That", "There", "Then", "But", "And", "As", "When", "With", "Over", "In", "On", "At",
    # Sentence words, not names: "Inside, the tallyman is a grizzled man" made
    # "Inside" the job's giver (8B run 34, T1).
    "Inside", "Outside", "Behind", "Beyond", "Here", "Now", "Still", "Again", "Today", "Tonight", "Meanwhile",
    "Instead", "Above", "Below", "Nearby", "Later", "Soon", "Finally", "Once", "Yes", "No", "Well", "Ahead",
    # "Morning light filters through dusty windows" made "Morning" a job's giver (8B run 81, T2).
    "Morning", "Evening", "Night", "Dawn", "Dusk", "Noon", "Midday", "Afternoon", "Sunlight", "Light", "Silence",
})


def _unknown_offer_speaker(
    narration: str, quote: str, npcs: list[dict[str, Any]] | None, place_names: Any = ()
) -> str:
    """The one capitalised name, not in the roster or the places, in the paragraph holding the offer; or ""."""
    core = _ws(re.sub(r'^[\s"“”\']+|[\s"“”\']+$', "", str(quote or ""))).lower()
    probe = core[:40]
    known = set()
    for npc in npcs or []:
        known.update(str(npc.get("name") or "").split())
    places = set()
    for place in place_names or ():
        places.update(str(place or "").title().split())
    for paragraph in re.split(r"\n\s*\n", str(narration or "")):
        if probe and probe not in _ws(paragraph).lower():
            continue
        outside = re.sub(r"\[\[[^\]]*\]\]", " ", _SPEECH_RE.sub(" ", paragraph))
        names = {
            w for w in re.findall(r"\b[A-Z][a-z]{2,}\b", outside)
            if w not in _NOT_A_SPEAKER and w not in known and w not in places
        }
        return next(iter(names)) if len(names) == 1 else ""
    return ""


_BOARD_RE = re.compile(r"\b(?:notice|board|posting|poster|sign|guild|bounty)\b", re.I)
# The offer is something read: "You read the details aloud", "the notice reads".
_READ_POSTING_RE = re.compile(
    r"\byou\s+(?:\w+ly\s+)?(?:read|reads|scan|scans|study|studies)\b|"
    r"\b(?:notice|posting|poster|sign|board|parchment|bill|handbill)\s+(?:reads|says|lists|announces)\b|"
    r"\bposted\s+(?:on|at|by)\b",
    re.I,
)


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


def _lead_verb(title: str) -> str:
    words = re.findall(r"[a-z]+", _norm(title))
    return words[0] if words else ""


def _is_duplicate(item: dict[str, Any], existing: list[dict[str, Any]] | None, giver_id: Any, first_place: str) -> dict[str, Any] | None:
    title = _norm(item.get("title"))

    def named(text: str) -> set[str]:
        """Word pairs of proper names in a title: "the Iron Tide's Raids" -> {"iron tide", "tide raids"}."""
        pairs: set[str] = set()
        for m in re.finditer(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b", re.sub(r"['’]s\b", "", str(text or ""))):
            words = [w.lower() for w in m.group(0).split() if w not in {"The", "A", "An"}]
            pairs |= {f"{a} {b}" for a, b in zip(words, words[1:])}
        # An employer gives many jobs: "the Salvage Guild" is no one job's subject.
        return {p for p in pairs if not re.search(
            r"\b(?:guild|house|company|office|council|watch|hall|crew|reeve|harbour|harbor|town)\b", p)}

    for quest in existing or []:
        status = str(quest.get("status") or "active")
        if status not in {"active", "offered", "declined", "completed"}:
            continue
        # The job already taken, about the same named thing: "Investigate the
        # Iron Tide's Raids" was offered beside the active "Work for the Iron
        # Tide" when the man it sent the player to gave directions (8B run 55, T6).
        if status == "active" and named(str(item.get("title") or "")) & named(str(quest.get("title") or "")):
            return quest
        ratio = SequenceMatcher(None, title, _norm(quest.get("title"))).ratio()
        # Another giver asking for another thing is another job (Saltmarrow
        # #117): Mara's "Ring the customs bell" was filed as a duplicate of the
        # guild's "Raise the customs-house bell" on the shared words alone.
        # From a different giver the titles must also open on the same verb,
        # or be near-identical.
        other_giver = bool(giver_id) and quest.get("giver_npc_id") != giver_id
        if other_giver and ratio < 0.9 and _lead_verb(title) != _lead_verb(str(quest.get("title") or "")):
            ratio = 0.0
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


# A pointer to where work might be is not a job (7B run 29, T1): "You might want
# to head over to the guild and see if they have any tasks for you" was filed
# as "Visit the guild for work" under the furrier who said it. The speaker has
# no task and names no pay; the job, if any, is the guild's, offered there.
_POINTER_LINE_RE = re.compile(
    r"\b(?:(?:might|may|could|should|better|ought\s+to)\s+(?:want\s+to\s+)?(?:head|go|try|ask|check|look|see|stop\s+by|pop\s+in)|"
    r"(?:head|go|try|ask|check|look)\s+(?:over\s+)?(?:at|in|to|with|around|down|up|by)\b)"
    r"[^.?!]{0,80}?\b(?:see|ask|find\s+out)\s+(?:if|whether)\s+(?:they|he|she|someone|anyone|there)\b"
    r"[^.?!]{0,40}?\b(?:work|tasks?|jobs?|errands?|hands?|help|hiring|need)\b",
    re.I,
)
_SEEK_WORK_TITLE_RE = re.compile(
    r"^(?:visit|go\s+to|head\s+to|check|ask\s+(?:at|around)|seek|look\s+for|find|search\s+for)\b.{0,40}\b(?:for\s+)?"
    r"(?:work|jobs?|tasks?|employment)\s*$",
    re.I,
)
_NAMED_PAY_RE = re.compile(r"\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|a)\s+(?:gold|silver|copper|coins?|crowns?)\b", re.I)


def points_elsewhere_for_work(title: str, offer_line: str = "", evidence: str = "") -> bool:
    """The "offer" only sends the player elsewhere to ask about work; no task, no pay of its own."""
    said = f"{offer_line or ''} {evidence or ''}"
    if _NAMED_PAY_RE.search(said):
        return False
    return bool(_POINTER_LINE_RE.search(said) or _SEEK_WORK_TITLE_RE.search(str(title or "").strip()))


def _offer_is_spoken(line: str, narration: str) -> bool:
    """The offer's words stand inside someone's quotation in the scene (the parser keeps them without marks)."""
    # Apostrophes either way: the parser's "You'll get a fair share" is the
    # prose's "You’ll get a fair share" (8B run 66, T1).
    def flat(text: str) -> str:
        return re.sub(r"\s+", " ", str(text or "").replace("’", "'").replace("‘", "'")).strip().lower()

    probe = flat(line)[:40]
    if len(probe) < 8:
        return False
    for a, b in re.findall(r"\"([^\"]*)\"|“([^”]*)”", str(narration or "")):
        if probe in flat(a or b):
            return True
    return False


def validate_quest_changes(
    changes: dict[str, Any],
    *,
    narration: str,
    player_input: str = "",
    npcs: list[dict[str, Any]] | None = None,
    locations: list[dict[str, Any]] | None = None,
    existing: list[dict[str, Any]] | None = None,
    settled_ids: set[int] | None = None,
    passive: bool = False,
    shown_unnamed: list[str] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Pure check. Returns (accepted_changes, rejected) where each rejected row is {"kind", "item", "reasons"}.

    ``settled_ids``: quests whose step the engine already decided this turn
    from the player's act and its roll (playtest #85b). No step_done or
    complete may touch them, so a failed roll is not completed by the parser
    reading the prose.

    ``passive``: the player did no work this turn (Wait, a plain question,
    looking around); a step is done only on a quote that shows a result and
    is about that job (``done_check``, #130).
    """
    accepted: dict[str, Any] = {"source": (changes or {}).get("source") or "parser", "new": [], "updates": []}
    rejected: list[dict[str, Any]] = []
    accepts_now = player_accepts(player_input)
    npc_names = {str(n.get("name") or "").strip().lower() for n in npcs or []}
    place_names = {str(p.get("name") or "").strip().lower() for p in locations or []}
    seen_titles: set[str] = set()
    # Offers accepted earlier in this turn, in the shape _is_duplicate reads
    # (playtest #85b, T6: one offer sentence became "Polish swords" and
    # "Learn metalworking", same giver, same place, same evidence; only the
    # pre-turn rows were checked, so the second passed).
    taken_this_turn: list[dict[str, Any]] = []
    settled = {int(i) for i in settled_ids or set()}

    for raw in list((changes or {}).get("new") or [])[: MAX_NEW_PER_TURN * 2]:
        if not isinstance(raw, dict):
            continue
        reasons: list[str] = []
        # Fields written inside the reward belong to the job: the 8B closed the
        # reward late and "offer_line" and "evidence" fell into it, so "Gut the
        # Drowned Mariner" had no quote at all (8B run 59, T3).
        nested = raw.get("reward") if isinstance(raw.get("reward"), dict) else {}
        for key in ("evidence", "offer_line", "difficulty", "timer_turns", "giver"):
            if not raw.get(key) and nested.get(key):
                raw[key] = nested.pop(key)
        # Markdown is no part of a name: "Salvage the *Iron Widow*" (8B run 57, T4).
        for key in ("title", "summary", "description"):
            if isinstance(raw.get(key), str):
                raw[key] = re.sub(r"(?<!\w)[*_]{1,2}([^*_\n]+?)[*_]{1,2}(?!\w)", r"\1", raw[key])
                # Nor is an entity code: "Debt Settlement: Tam Brooke [A]" (8B run 82, T2).
                raw[key] = re.sub(r"\s*\[\[?[A-Z]{1,3}\d{0,3}\]\]?", "", raw[key]).strip()
        for step in raw.get("steps") or []:
            if isinstance(step, dict):
                for key in ("title", "description"):
                    if isinstance(step.get(key), str):
                        step[key] = re.sub(r"(?<!\w)[*_]{1,2}([^*_\n]+?)[*_]{1,2}(?!\w)", r"\1", step[key])
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
        # The giver is whoever speaks the offer, when the prose says so plainly
        # and the parser named another known person or no one. A giver it made
        # up, or a notice board, is left to the checks below.
        speaker = _offer_speaker(narration, offer_line or evidence, npcs) if (giver is not None or not giver_ref) else None
        if speaker is not None and (giver is None or int(giver.get("id") or 0) != int(speaker.get("id") or 0)):
            from app import turn_ledger

            turn_ledger.note(
                "quest", "giver_is_the_speaker", title=title, parser_giver=giver_ref,
                speaker=str(speaker.get("name") or ""),
            )
            giver = speaker
            giver_ref = str(speaker.get("code") or speaker.get("name") or "")
        # A known person the scene never mentions did not offer it (7B run 20,
        # T4: "Salvage contracts" was filed under Wat Sallow, who was not there;
        # Thaddeus, met that turn and not yet stored, made the offer).
        here_unnamed = {str(n or "").strip().lower() for n in shown_unnamed or []}
        # The one the prose shows only as a figure this turn is here too: the
        # masked figure bound to Bertha Radley made the offer (8B run 19, T0).
        if (giver is not None and speaker is None and not _named_in(narration, giver)
                and not _shown_by_role(narration, giver, npcs)
                and str(giver.get("name") or "").strip().lower() not in here_unnamed):
            from app import turn_ledger

            stranger = (
                _unknown_offer_speaker(narration, offer_line, npcs, place_names)
                or _unknown_offer_speaker(narration, evidence, npcs, place_names)
            )
            turn_ledger.note(
                "quest", "giver_not_in_scene", title=title, parser_giver=giver_ref, speaker=stranger,
            )
            giver, giver_ref = None, stranger
            giver_absent = True
        else:
            giver_absent = False
        # A job read off a board is the board's, or its poster's (7B run 11,
        # T2: "You read the details aloud: 'Lifting supplies to the upper
        # levels of the market hall'" was filed under Iseult, who only said
        # where the board was).
        if giver is not None and _READ_POSTING_RE.search(evidence):
            posted = " ".join(a or b for a, b in re.findall(r"\"([^\"]*)\"|“([^”]*)”", evidence))
            names = [str(giver.get("name") or "")] + str(giver.get("name") or "").split()[:1]
            if not any(n and re.search(rf"\b{re.escape(n)}\b", posted, re.I) for n in names):
                from app import turn_ledger

                turn_ledger.note("quest", "giver_is_the_board", title=title, parser_giver=giver_ref)
                giver, giver_ref = None, "the notice board"
        checked = ""
        if not evidence_found(evidence, narration, player_input):
            reasons.append("evidence_not_in_text")
        elif raw.get("_from_mark") and re.search(r"\?\s*[\"”]?\s*$", str(offer_line or evidence)) and not judge_offer(
            evidence, narration, player_input, offer_line=offer_line, giver=giver, giver_ref=giver_ref, npcs=npcs
        )["ok"]:
            # The draft's own mark on a question: "What work do you want?" became
            # the job "Salvage Contract" (8B run 35, T1). A question back to the
            # player offers nothing yet.
            reasons.append("mark_on_a_question")
        elif raw.get("_from_mark") and giver_absent and not giver_ref and not judge_offer(
            evidence, narration, player_input, offer_line=offer_line, giver=None, giver_ref="", npcs=npcs
        )["ok"]:
            # The mark's giver is not here, no one else speaks an offer, and the
            # words offer nothing: GIVER "A" pointed at someone left behind, and
            # "You're late, Flat-runner" became the job "Salvage Contract" (8B
            # run 44, T1). A mark with no giver named is still trusted.
            reasons.append("mark_with_no_offer_or_giver")
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
            elif (giver is None and not re.search(r"[\"“”]", evidence)
                  and not _offer_is_spoken(offer_line or evidence, narration)
                  and not _READ_POSTING_RE.search(evidence) and not re.search(r"\b(?:notice|board|posting|bill)\b", evidence, re.I)):
                # No one in the scene offered it: "The promise you made to your
                # mother to bring back something from the flats" became a job
                # from "mother" (8B run 29, T0). An offer is spoken, posted, or
                # made by someone the world holds.
                reasons.append("no_one_offered_it")
            elif verdict.get("why") == "giver_offers" and _players_words_only(evidence, offer_line, player_input, narration):
                # The job is the player's own words ("I will mind the tides",
                # retold "You decide to mind the tides"), and the giver's job
                # sentence is about something else ("Keep an eye on my herd"):
                # no one offered it (7B run 42, T2).
                title_stems = {_stem(w) for w in _title_words(title)}
                giver_stems = {_stem(w) for w in re.findall(r"[a-z]{4,}", str(verdict.get("checked") or "").lower())}
                if not title_stems & giver_stems:
                    reasons.append("players_own_words_not_an_offer")
        if not reasons and points_elsewhere_for_work(title, offer_line, evidence):
            from app import turn_ledger

            turn_ledger.note("quest", "pointer_not_a_job", title=title, quote=(offer_line or evidence)[:200])
            reasons.append("pointer_not_a_job")
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
        # A work job written as only a walk (7B run 30, T0: "Help with moles"
        # with the one step "Go to the tannery") finished on being there: the
        # work itself is its last step, at the last step's place.
        if steps and not _TRAVEL_JOB_RE.search(title) and all(_TRAVEL_STEP_RE.search(s["title"]) for s in steps):
            if len(steps) >= MAX_STEPS:
                steps = steps[: MAX_STEPS - 1]
            last = steps[-1]
            summary = re.sub(r"\s+", " ", str(raw.get("summary") or "")).strip()
            steps.append({
                "title": title[:120],
                "description": (summary or title)[:400],
                "location_code": last["location_code"],
                "location_name": last["location_name"],
            })
            from app import turn_ledger

            turn_ledger.note("quest", "work_step_added", title=title, travel_steps=[s["title"] for s in steps[:-1]])
        first_place = steps[0]["location_name"] if steps else ""
        same_offer = next(
            (
                prior
                for prior in taken_this_turn
                # A sentence, not a stray word or two both quotes happen to share.
                if len(_norm(evidence)) >= 20
                and len(_norm(prior["evidence"])) >= 20
                and (_norm(evidence) in _norm(prior["evidence"]) or _norm(prior["evidence"]) in _norm(evidence))
            ),
            None,
        )
        if same_offer is not None:
            # One offer is one quest. A promise of more work in the same words
            # ("we'll talk about a proper apprenticeship") is that quest's
            # reward, not a second job.
            reasons.append(f"same_offer_as:{same_offer['title']}")
            prior_item = same_offer["item"]
            if offer_line and not prior_item["reward"]["text"] and _norm(offer_line) != _norm(prior_item["evidence"]):
                prior_item["reward"]["text"] = offer_line[:200]
        dup = _is_duplicate({"title": title}, list(existing or []) + taken_this_turn, giver.get("id") if giver else None, first_place)
        if dup is not None and same_offer is None:
            ref = dup.get("code") or dup.get("id")
            # A job the player turned down is not offered again (TODO n20), nor
            # one just finished and paid (#130: a finished job offered and taken again).
            dup_status = str(dup.get("status") or "")
            reasons.append(
                f"declined_before:{ref}" if dup_status == "declined"
                else f"completed_before:{ref}" if dup_status == "completed"
                else f"duplicate_of:{ref}"
            )
        # A deal struck in the scene is the offer (7B run 10, T4): Isk said "Ten
        # knives for one gold", Jehane answered "Very well. Ten for one gold.",
        # and the parser proposed the job but quoted "Jehane Tully takes a deep
        # breath" as its evidence, so it was refused as no offer. When the giver
        # is in the scene and the two sides agree a sum, the agreement grounds it.
        deal_gold = None
        quote_reasons = {"evidence_is_not_an_offer", "evidence_not_in_text"}
        if reasons and set(reasons) <= quote_reasons and giver is not None and _named_in(narration, giver):
            deal_gold, how = agreed_job_price(narration, player_input)
            if deal_gold is not None:
                from app import turn_ledger

                turn_ledger.note("quest", "deal_is_the_offer", title=title, gold=deal_gold, how=how,
                                 dropped_reasons=list(reasons), parser_quote=evidence[:200])
                reasons = []
                evidence = _player_line_text(player_input) or evidence
        if reasons:
            rejected.append({"kind": "new", "item": raw, "reasons": reasons, "checked": checked})
            continue
        reward = raw.get("reward") if isinstance(raw.get("reward"), dict) else {}
        gold = max(0, min(REWARD_GOLD_CAP, _int(reward.get("gold"), 0)))
        if deal_gold is not None:
            gold = max(0, min(REWARD_GOLD_CAP, int(deal_gold)))
        xp = max(0, min(REWARD_XP_CAP, _int(reward.get("xp"), 0)))
        items = [re.sub(r"\s+", " ", str(i)).strip()[:80] for i in (reward.get("items") or []) if str(i or "").strip()]
        # Karma only as the story states it, like gold (playtest #85b).
        karma = max(-REWARD_KARMA_CAP, min(REWARD_KARMA_CAP, _int(reward.get("karma"), 0)))
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
                    "karma": karma,
                    "text": str(reward.get("text") or "").strip()[:200],
                },
                "difficulty": difficulty,
                "timer_turns": max(0, min(60, _int(raw.get("timer_turns"), 0))),
                "evidence": evidence[:300],
                "target_location_id": None,
            }
        )
        taken_this_turn.append(
            {
                "code": title,
                "title": title,
                "status": "offered",
                "giver_npc_id": giver.get("id") if giver else None,
                "first_step_location": first_place,
                "evidence": evidence,
                "item": accepted["new"][-1],
            }
        )
        if len(accepted["new"]) >= MAX_NEW_PER_TURN:
            break

    # An offer made and taken in the same turn: the player's own line takes the
    # one new job ("I'll take the job.") and it starts active (TODO n20 keeps
    # every other new job an offer).
    if len(accepted["new"]) == 1:
        item = accepted["new"][0]
        pseudo = {"id": -1, "title": item["title"], "status": "offered"}
        open_offers = [q for q in existing or [] if str(q.get("status") or "") == "offered"] + [pseudo]
        if player_takes_job(pseudo, player_input, open_offers, narration):
            item["status"] = "active"

    for raw in list((changes or {}).get("updates") or [])[: MAX_UPDATES_PER_TURN * 2]:
        if not isinstance(raw, dict):
            continue
        reasons = []
        action = str(raw.get("action") or "").strip().lower().replace(" ", "_")
        if action == "done":
            action = "step_done"
        elif action in {"refuse", "reject", "turn_down"}:
            action = "decline"
        # Turned-down and finished rows are kept only for the re-offer check; no update may touch them.
        quest = _resolve_quest(
            raw.get("quest"), [q for q in existing or [] if str(q.get("status") or "") not in {"declined", "completed"}]
        )
        if action == "accept" and quest is not None and str(quest.get("status") or "") == "active":
            continue  # already taken this turn (a typed accept or the Accept button)
        if action not in QUEST_ACTIONS:
            reasons.append("unknown_action")
        if quest is None:
            reasons.append("unknown_quest")
        elif int(quest.get("id") or 0) in settled and action in {"step_done", "complete"}:
            # The engine decided this step from the player's act (playtest #85b).
            reasons.append("engine_decided")
        evidence = str(raw.get("evidence") or "").strip()
        if not evidence_found(evidence, narration, player_input):
            # An accept or a refusal the player typed is evidence enough on its
            # own only when it can mean this one offer: the only one open, or
            # the line names it. The rule local_intel.accept_offered_quest uses
            # for a typed accept, so the parser cannot pick a different offer.
            typed = (action == "accept" and accepts_now) or (
                action == "decline" and _TYPED_DECLINE_RE.search(str(player_input or ""))
            )
            if not (typed and quest is not None and _means_this_offer(quest, existing, player_input)):
                reasons.append("evidence_not_in_text")
        if quest is not None and action in _LEGAL and str(quest.get("status") or "") not in _LEGAL[action]:
            reasons.append(f"illegal_transition:{quest.get('status')}->{action}")
        if action == "accept" and quest is not None and not reasons and not player_takes_job(quest, player_input, existing, narration):
            # The prose may agree for the giver, never for the player (7B run 7, T3).
            reasons.append("player_did_not_accept")
        # Setting out is not done (7B Saltmarrow T7): "you head down the
        # slipway onto the northern mudflats to look for the lost cargo"
        # completed and paid the cargo job while the search roll failed.
        if action in {"step_done", "complete"} and _intent_only(evidence):
            reasons.append("evidence_is_intent")
        elif (
            action in {"step_done", "complete"}
            and quest is not None
            and (action == "complete" or _int(quest.get("current_step"), 1) >= _int(quest.get("total_steps"), 1))
            and not _TRAVEL_JOB_RE.search(str(quest.get("title") or "").strip())
            and _travel_only(evidence)
        ):
            # Arriving finishes a trip, not a salvage job: the last step of
            # work that is not itself a journey needs the work shown done.
            reasons.append("evidence_is_travel")
        if action in {"step_done", "complete"} and quest is not None and not reasons:
            reasons.extend(done_check(evidence, quest, passive=passive))
        if action in {"step_done", "complete"} and quest is not None and not reasons:
            finishing = action == "complete" or _int(quest.get("current_step"), 1) >= _int(quest.get("total_steps"), 1)
            if _PLAYER_NOT_DONE_RE.search(_player_line_text(player_input) or str(player_input or "")):
                # The player's own word that the work is not done stands.
                reasons.append("player_says_not_done")
            elif (
                finishing
                and not _TRAVEL_JOB_RE.search(str(quest.get("title") or "").strip())
                and not _shows_outcome(evidence)
                and not _players_own_act(evidence, player_input)
            ):
                # The last step of work is done by the player's own act or by a
                # quote that shows what it came to, not by someone naming the
                # job's trouble (7B run 30, T15: Dunstan's "The tannery is where
                # the moles are causing trouble" paid "Help with moles" while the
                # traps were still empty).
                reasons.append("evidence_shows_no_outcome")
        if reasons:
            rejected.append({"kind": "update", "item": raw, "reasons": reasons, "checked": evidence[:240]})
            continue
        accepted["updates"].append(
            {"quest_id": quest.get("id"), "code": quest.get("code"), "title": quest.get("title"), "action": action, "evidence": evidence[:300]}
        )
        if len(accepted["updates"]) >= MAX_UPDATES_PER_TURN:
            break
    _one_act_one_quest(accepted, rejected, existing)
    return accepted, rejected


_INTENT_ONLY_RE = re.compile(
    r"\b(?:to\s+(?:look|search|find|hunt|seek|see\s+(?:if|whether)|ask|check|try)|in\s+search\s+of|looking\s+for|"
    r"search(?:es|ing)\s+for|trying\s+to|hoping\s+to|intending\s+to|ready\s+to|about\s+to|on\s+(?:your|the|her|his)\s+way|"
    r"set(?:s|ting)?\s+(?:out|off)|head(?:s|ing)?\s+(?:out|off|down|toward|towards|for))\b",
    re.I,
)
_DONE_WORDS_RE = re.compile(
    r"\b(?:found|find\s+(?:it|them|the)|finds|done|finish\w*|complet\w*|deliver\w*|hand(?:s|ed)?\s+(?:over|it|them)|"
    r"return(?:s|ed)|brought|bring(?:s)?\s+(?:it|them)|sign(?:s|ed)|paid|pays|recover\w*|retriev\w*|haul(?:s|ed)?\s+(?:it|them)\s+(?:up|out|in)|"
    r"rescu\w*|fix\w*|mend\w*|repair\w*|rang|ring(?:s)?\s+(?:it|the)|"
    # The work ran out: "That was the last of the hold" (8B run 54, T6).
    r"(?:was|is|'s)\s+the\s+last\s+(?:of|one))\b",
    re.I,
)


_NOT_YET_BEFORE_RE = re.compile(r"\b(?:to|will|shall|can|could|would|must|might|(?:i|you|we|he|she|they)['’]ll)\s+$", re.I)


def _shows_result(text: str) -> bool:
    """A result word that is not a purpose or a promise: "to find the damaged ship" finds nothing (7B run 29, T5)."""
    text = str(text or "")
    return any(not _NOT_YET_BEFORE_RE.search(text[: m.start()]) for m in _DONE_WORDS_RE.finditer(text))


def _intent_only(evidence: str) -> bool:
    """The quote only sets out to do the work: a purpose or a start, no result."""
    text = str(evidence or "")
    return bool(_INTENT_ONLY_RE.search(text)) and not _shows_result(text)


# Getting there is not the work (7B run 29, T5): "You head down to the docks by
# the old warehouse to find the damaged ship" finished and paid "Salvage a
# damaged ship", whose one step the parser had written as "Go to the harbor".
_TRAVEL_RE = re.compile(
    r"\b(?:head(?:s|ed|ing)?|walk(?:s|ed|ing)?|go(?:es|ing)?|went|make\s+(?:your|my)\s+way|made\s+(?:your|my)\s+way|"
    r"arriv\w*|reach(?:es|ed|ing)?|step(?:s|ped)?\s+(?:in|into|out|onto|inside)|enter(?:s|ed|ing)?|"
    r"climb\w*|descend\w*|cross(?:es|ed|ing)?|set(?:s|ting)?\s+(?:off|out)|travel\w*|approach\w*|stride\w*|strode)\b",
    re.I,
)
# Jobs that are done by getting somewhere: go, visit, meet, deliver, bring.
_TRAVEL_JOB_RE = re.compile(
    r"^(?:go|visit|travel|reach|meet|deliver|bring|take|carry|escort|return|report|head|walk|find|see|speak|talk|ask)\b", re.I
)


# A step that is only getting somewhere: "Go to the tannery", "Head to the docks".
_TRAVEL_STEP_RE = re.compile(
    r"^(?:go|goes|head|travel|walk|visit|reach|return|arrive|journey|sail|ride|get|make\s+(?:your|one['’]s|the)\s+way)\b"
    r"(?:\s+(?:back\s+)?(?:to|toward|towards|into|down|up|over|out|for|at)\b|\s+the\b|$)",
    re.I,
)
# What the work came to, beyond the done words: a catch, a clearing, the giver's
# thanks. Read only for the last step of a work job (7B run 30, T15).
_OUTCOME_RE = re.compile(
    r"\b(?:caught|catch(?:es)?\s+(?:it|them|the|one|two|three|a)|trapped|snared|killed|slain|dead|cleared|clean(?:ed)?\s+out|"
    r"dealt\s+with|took\s+care\s+of|taken\s+care\s+of|salvaged|patched|secured|sealed|emptied|sold|"
    r"thank(?:s|ed)?\s+you|well\s+done|good\s+work|fine\s+work|job\s+well|that['’]s\s+(?:the\s+last|all\s+of\s+them|it\s+done)|"
    r"hands?\s+you|handed\s+you|counts?\s+out|pays?\s+you|paid\s+you|coins?\s+(?:into|in)\s+your|"
    r"hand(?:s|ed)?\s+(?:[\w'’-]+\s+){1,4}?over\s+to)\b",
    re.I,
)
_YOU_ACT_RE = re.compile(r"^\W*(?:then\s+)?you\s+(?:\w+ly\s+)?([a-z]+)", re.I)


def work_done_in_line(quest: dict[str, Any] | None, narration: str, player_input: str) -> bool:
    """The player's own line does this job's work and the prose shows that act done.

    7B run 37, T3: '"I will take the job." I go through to the back and start
    carrying the old planks out to the shed, two at a time, stacking them flat'
    for "Move old planks to the shed"; the prose "You stack the old planks flat
    against the wall" and Delphine paid 5 gold, and the job was logged as paid
    ahead and left open. The line has to share two of the title's words, the
    prose has to show a "You <verb>" the player typed, and the player must not
    say the work is unfinished.
    """
    if not quest:
        return False
    own = _QUOTED_RE.sub(" ", _player_own_line(player_input))
    if not own.strip() or _PLAYER_NOT_DONE_RE.search(own):
        return False
    words = _title_words(str(quest.get("title") or ""))
    own_stems = {_stem(w) for w in re.findall(r"[a-z]{4,}", own.lower())}
    if len({_stem(w) for w in words} & own_stems) < 2:
        return False
    for sentence in re.split(r"(?<=[.!?])\s+", re.sub(r"[\"“][^\"”]*[\"”]", " ", str(narration or ""))):
        if _players_own_act(sentence.strip(), player_input):
            return True
    return False


def _players_own_act(evidence: str, player_input: str) -> bool:
    """The quote is the player's own act this turn: "You set the last polished blade" for "I set ..."."""
    lead = _YOU_ACT_RE.match(str(evidence or ""))
    if not lead:
        return False
    verb = _stem(lead.group(1))
    own = re.sub(r"[\"“][^\"”]*[\"”]", " ", _player_line_text(player_input) or str(player_input or ""))
    return verb in {_stem(w) for w in re.findall(r"[a-z]+", own.lower())}
# The player says the work is not done: "Nothing in either trap yet", "I will
# come back at dusk to check them" (7B run 30, T15 paid the job on that line).
_PLAYER_NOT_DONE_RE = re.compile(
    r"\bnot\s+(?:yet|done|finished)\b|\bnothing\s+(?:\w+\s+){0,4}?yet\b|\bno\s+\w+\s+yet\b|\bstill\s+(?:empty|nothing)\b|"
    r"\b(?:i\s+will|i['’]ll|i\s+shall)\s+come\s+back\b|\bcome\s+back\s+(?:at|later|tomorrow|tonight|in\s+the)\b",
    re.I,
)


def _shows_outcome(text: str) -> bool:
    text = str(text or "")
    return _shows_result(text) or any(
        not _NOT_YET_BEFORE_RE.search(text[: m.start()]) for m in _OUTCOME_RE.finditer(text)
    )


def _travel_only(evidence: str) -> bool:
    # Leave to go is no going: "That was the last of the hold. You're clear to
    # go." held back the finished dock job as travel (8B run 54, T6).
    text = re.sub(r"\b(?:clear|free|good|fit)\s+to\s+go\b|\b(?:you|ye)\s+(?:can|may)\s+go\b", " ",
                  str(evidence or ""), flags=re.I)
    return bool(_TRAVEL_RE.search(text)) and not _shows_result(text)


# Work still owed is not work done (7B run 5 #130, T5: "You will have to clear
# out this hold, piece by piece." completed and paid the hold job).
_STILL_OWED_RE = re.compile(
    r"\b(?:will|shall|going\s+to|have\s+to|has\s+to|need(?:s)?\s+to|must|should|could|would|might|"
    r"(?:you|i|we)'ll)\b",
    re.I,
)
_IN_PROGRESS_RE = re.compile(
    r"\b(?:continu\w*|keep(?:s|ing)?\s+(?:on\s+)?\w+ing|begin\w*|began|begun|start(?:s|ed|ing)?|"
    r"set(?:s|ting)?\s+(?:to\s+work|about)|get(?:s|ting)?\s+to\s+work|got\s+to\s+work|"
    r"work(?:s|ing)?\s+(?:on|through|away\s+at)|halfway|progress\w*|under\s*way|so\s+far)\b",
    re.I,
)
# Words that say nothing about which job a quote is about.
_QUEST_STOP_STEMS = {
    "the", "you", "your", "and", "for", "with", "that", "this", "from", "her", "his", "him", "she", "they",
    "them", "are", "was", "were", "has", "have", "had", "not", "but", "into", "out", "its", "one", "who",
    "what", "there", "their", "then", "than", "some", "just", "back", "still", "about", "over", "will",
}


def _quote_is_question(evidence: str) -> bool:
    text = re.sub(r"[\"'“”‘’\s]+$", "", str(evidence or "")).strip()
    return text.endswith("?")


def _quote_names_the_job(evidence: str, quest: dict[str, Any] | None) -> bool:
    """The quote shares a content word with the job's title or its current step."""
    if not quest:
        return False
    job = _stems(f"{quest.get('title') or ''} {quest.get('current_step_text') or ''}") - _QUEST_STOP_STEMS
    return bool(job & (_stems(evidence) - _QUEST_STOP_STEMS))


def done_check(evidence: str, quest: dict[str, Any] | None, *, passive: bool = False) -> list[str]:
    """Why a quote does not show a step done; empty when it does (7B run 5 #130).

    The parser may cite any sentence, so the engine reads the quote it cites.
    A question, or work still owed with no result word, finishes nothing. On a
    turn where the player acted, the quote must show a result or be about this
    job; on a passive turn (Wait, a plain question, looking around) the player
    did no work, so the quote must show a result *and* be about this job. T58
    paid two jobs on "The rain continues to pour, obscuring the view"; T89 paid
    "A debt of bread" on a Wait because someone handed over a sack.
    """
    text = str(evidence or "")
    result = _shows_result(text)
    if _quote_is_question(text) and not result:
        return ["evidence_is_question"]
    if _STILL_OWED_RE.search(text) and not result:
        return ["evidence_is_owed_work"]
    about = _quote_names_the_job(text, quest)
    if passive:
        if not (result and about):
            return ["passive_turn_not_done"]
        return []
    if not (result or about):
        return ["evidence_not_about_this_job"]
    if _IN_PROGRESS_RE.search(text) and not result:
        # Work under way is not work done (7B run 6, T5 and T7: "You start
        # sorting the goods", "You continue sorting").
        return ["evidence_is_work_in_progress"]
    return []


def _stem(word: str) -> str:
    """A rough stem: "sorting", "sorted" and "sorts" all read "sort" (7B run 6, T7)."""
    w = word.strip("'").lower()
    if w.endswith("'s"):
        w = w[:-2]
    for suffix in ("ings", "ing", "ed", "es", "s", "er"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            w = w[: -len(suffix)]
            if suffix in {"ing", "ings", "ed"} and len(w) >= 4 and w[-1] == w[-2] and w[-1] not in "aeiouls":
                w = w[:-1]  # "running" -> "run", "shipped" -> "ship"
            break
    return w[:5]


def _stems(text: Any) -> set[str]:
    words = re.findall(r"[a-z][a-z']+", str(text or "").lower())
    return {_stem(w) for w in words if len(w) > 2 and w not in _QUEST_STOP_STEMS}


def _one_act_one_quest(accepted: dict[str, Any], rejected: list[dict[str, Any]], existing: list[dict[str, Any]] | None) -> None:
    """One quoted act advances one quest (playtest #98).

    "I set the last polished blade on the rack" was cited for both "Polish
    swords" and "Learn metalworking", and both were completed and paid. When
    two step_done / complete updates rest on the same sentence, the quest
    whose title and current step share the most words with it keeps the
    update; the first listed wins a tie.
    """
    by_id = {int(q.get("id") or 0): q for q in existing or []}
    advancing = [u for u in accepted["updates"] if u["action"] in {"step_done", "complete"} and len(_norm(u["evidence"])) >= 12]
    dropped: set[int] = set()
    for i, upd in enumerate(advancing):
        if id(upd) in dropped:
            continue
        same = [
            other
            for other in advancing[i + 1 :]
            if id(other) not in dropped
            and (_norm(upd["evidence"]) in _norm(other["evidence"]) or _norm(other["evidence"]) in _norm(upd["evidence"]))
        ]
        if not same:
            continue
        group = [upd, *same]
        words = _stems(upd["evidence"])

        def fit(u: dict[str, Any]) -> int:
            quest = by_id.get(int(u.get("quest_id") or 0)) or {}
            return len(words & _stems(f"{quest.get('title') or ''} {quest.get('current_step_text') or ''}"))

        keep = max(group, key=fit)  # max keeps the first of equal scores
        for other in group:
            if other is not keep:
                dropped.add(id(other))
                rejected.append(
                    {
                        "kind": "update",
                        "item": {"quest": other.get("code") or other.get("title"), "action": other["action"]},
                        "reasons": [f"same_act_as:{keep.get('code') or keep.get('title')}"],
                        "checked": other["evidence"][:240],
                    }
                )
    if dropped:
        accepted["updates"] = [u for u in accepted["updates"] if id(u) not in dropped]


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
    the same job is not filed again every time the giver mentions it (TODO n20),
    and jobs finished in that window, so a paid job is not offered and paid
    again (#130). Neither kind can be updated.
    """
    from app.quests import DECLINE_MEMORY_TURNS

    npcs = _rows(conn, "SELECT id, code, name, role FROM npcs ORDER BY id DESC LIMIT 200")
    locations = _rows(conn, "SELECT id, code, name FROM locations ORDER BY id DESC LIMIT 200")
    existing = _rows(
        conn,
        """
        SELECT q.id, q.code, q.title, q.status, q.giver_npc_id, q.current_step, q.total_steps,
               (SELECT s.location_name FROM quest_steps s WHERE s.quest_id = q.id AND s.step_number = 1) AS first_step_location,
               (SELECT s.title || ' ' || COALESCE(s.description, '') FROM quest_steps s
                 WHERE s.quest_id = q.id AND s.step_number = MAX(1, COALESCE(q.current_step, 1))) AS current_step_text
        FROM quests q
        WHERE q.status IN ('active', 'offered')
           OR (q.status = 'declined' AND COALESCE(q.failed_turn, 0) >= ?)
           OR (q.status = 'completed' AND COALESCE(q.completed_turn, 0) >= ?)
        ORDER BY q.id DESC LIMIT 40
        """,
        (int(turn) - DECLINE_MEMORY_TURNS, int(turn) - DECLINE_MEMORY_TURNS),
    )
    return {"npcs": npcs, "locations": locations, "existing": existing}


def apply_quest_changes(
    conn,
    changes: dict[str, Any],
    *,
    narration: str,
    player_input: str = "",
    turn: int = 0,
    settled_ids: set[int] | None = None,
    passive: bool = False,
    shown_unnamed: list[str] | None = None,
) -> dict[str, Any]:
    """Validate against the live DB, create/advance quests, journal + event-log each one. Returns a report for the trace.

    ``settled_ids``: quests the engine already advanced or refused this turn (playtest #85b).
    ``passive``: the player did no work this turn (see validate_quest_changes).
    """
    from app import turn_ledger

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
        from app.quests import accept_offered, complete_quest_step, create_quest, decline_offered, fail_quest

        ctx = load_quest_context(conn, int(turn))
        accepted, rejected = validate_quest_changes(
            changes,
            narration=narration,
            player_input=player_input,
            npcs=ctx["npcs"],
            locations=ctx["locations"],
            existing=ctx["existing"],
            settled_ids=settled_ids,
            passive=passive,
            shown_unnamed=shown_unnamed,
        )
        for r in rejected:
            if r["kind"] == "update" and str(r["item"].get("action") or "") in {"step_done", "complete", "done"}:
                turn_ledger.note(
                    "quest", "payout_refused", quest=str(r["item"].get("quest") or ""), reasons=r["reasons"],
                    quote=str(r.get("checked") or r["item"].get("evidence") or "")[:240], passive=passive,
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
        # The story just offered a job the engine's quest clock had posted:
        # it is now said aloud, no longer a notice nobody has raised (#114).
        for r in rejected:
            for reason in r["reasons"]:
                if reason.startswith("duplicate_of:"):
                    ref = reason.split(":", 1)[1]
                    conn.execute(
                        "UPDATE quests SET notes = notes || '; voiced' WHERE (code = ? OR CAST(id AS TEXT) = ?) "
                        "AND notes LIKE 'clock:%' AND notes NOT LIKE '%voiced%'",
                        (ref, ref),
                    )
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
                status="offered",
                reward_karma=int(item["reward"].get("karma") or 0),
            )
            code = f"Q{quest_id}"
            giver = f" (from {item['giver_name']})" if item["giver_name"] else ""
            _journal(conn, turn, f"New job offered: {item['title']}{giver}")
            if item["status"] == "active":
                # Taken in the player's own words this turn: the one accept path journals it.
                if accept_offered(conn, int(quest_id), turn=int(turn), player_line=player_input) is None:
                    item["status"] = "offered"
                else:
                    turn_ledger.note("quest", "taken_on_offer", quest=code, title=item["title"])
            report["created"].append({"code": code, "title": item["title"], "status": item["status"]})
        for upd in accepted["updates"]:
            qid = int(upd["quest_id"])
            action = upd["action"]
            title = upd["title"] or upd["code"]
            if action == "accept":
                # One path for every accept (TODO n20); it journals.
                if accept_offered(conn, qid, turn=int(turn), player_line=player_input) is None:
                    continue
            elif action == "decline":
                if decline_offered(conn, qid, turn=int(turn)) is None:
                    continue
            elif action in {"step_done", "complete"}:
                # The one step-done path (playtest #85b): it journals, and on
                # completion pays through pay_quest_reward and says what.
                done = complete_quest_step(conn, qid, turn=int(turn), to_end=action == "complete", source="parser")
                if not done.get("ok"):
                    continue
                row = {"code": upd["code"], "action": done["action"]}
                if done.get("paid"):
                    row["paid"] = done["paid"]
                    turn_ledger.note(
                        "quest", "paid", quest=upd["code"], action=action, paid=done["paid"],
                        quote=upd["evidence"][:240], passive=passive,
                    )
                report["updated"].append(row)
                continue
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


def settle_player_answer(conn, player_input: str, turn: int) -> list[dict[str, Any]]:
    """
    The player's own no, or "not yet", to a job (7B run 7, T4-T5).

    "I haven't said yes yet" and "No deal, Oriel. I'll take my chances on the
    flats." left a job the engine had made active on the prose's say-so. Read
    from the player's line, so it needs no parser proposal:

    - a refusal turns down the one open offer (or the one the line names);
    - a job taken in the last turn or this one, with no step done yet, goes
      back to an offer on "not yet", and is turned down on a refusal.

    Only one job can be meant: the one the line names, or the only candidate.
    Returns report rows ({"code", "action"}).
    """
    own = _player_own_line(player_input)
    refuses = bool(_REFUSES_RE.search(own))
    holds_off = bool(_HOLDS_OFF_RE.search(own))
    if not (refuses or holds_off):
        return []
    from app import turn_ledger

    rows = [dict(r) for r in conn.execute(
        "SELECT q.id, q.code, q.title, q.status, q.current_step, n.name AS giver, n.location_id AS giver_at "
        "FROM quests q LEFT JOIN npcs n ON n.id = q.giver_npc_id "
        "WHERE q.status IN ('offered', 'active') ORDER BY q.id"
    ).fetchall()]
    here = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()
    here_id = int(here[0] or 0) if here else 0
    low = own.lower()
    candidates: list[dict[str, Any]] = []
    for row in rows:
        # The answer is to someone in the scene: a "No deal" over a price
        # elsewhere does not turn down a job from a giver who is not here.
        giver_first = str(row.get("giver") or "").split()[:1]
        giver_here = (row.get("giver_at") and int(row["giver_at"]) == here_id) or (
            giver_first and re.search(rf"\b{re.escape(giver_first[0].lower())}\b", low)
        )
        if row.get("giver") and not giver_here:
            continue
        if row["status"] == "offered":
            if refuses:
                candidates.append(row)
            continue
        if int(row.get("current_step") or 1) != 1:
            continue
        taken = conn.execute(
            "SELECT 1 FROM journal WHERE turn >= ? AND content LIKE ? LIMIT 1",
            (int(turn) - 1, f"Quest accepted: {row['title']}%"),
        ).fetchone()
        if taken:
            candidates.append(row)
    if not candidates:
        return []
    words = set(re.findall(r"[a-z]{4,}", own.lower()))
    named = [r for r in candidates if _title_words(str(r.get("title") or "")) & words]
    pool = named or candidates
    if len(pool) != 1:
        turn_ledger.note("quest", "answer_unplaced", refuses=refuses, holds_off=holds_off,
                         candidates=[r["code"] or f"Q{r['id']}" for r in pool])
        return []
    row = pool[0]
    code = str(row.get("code") or f"Q{row['id']}")
    if row["status"] == "active" and not refuses:
        conn.execute("UPDATE quests SET status = 'offered' WHERE id = ? AND status = 'active'", (int(row["id"]),))
        _journal(conn, turn, f"Not taken yet: {row['title']}")
        turn_ledger.note("quest", "accept_undone", quest=code, why="the player has not said yes")
        return [{"code": code, "action": "unaccept"}]
    conn.execute(
        "UPDATE quests SET status = 'declined', failed_turn = ? WHERE id = ? AND status IN ('offered', 'active')",
        (int(turn), int(row["id"])),
    )
    _journal(conn, turn, f"Turned down: {row['title']}")
    turn_ledger.note("quest", "declined_by_player", quest=code, was=row["status"])
    return [{"code": code, "action": "decline"}]


def finishing_quest_ids(
    conn,
    changes: dict[str, Any] | None,
    *,
    narration: str,
    player_input: str = "",
    turn: int = 0,
    settled_ids: set[int] | None = None,
    passive: bool = False,
) -> list[int]:
    """Quests the parser's changes will finish (and pay) this turn; a dry run, nothing is written.

    apply_turn reads this before any gold moves: a job the engine pays this
    turn is the payout, so the model's own gold and XP for the same work go
    (7B run 5 #130, T45: the quest paid +15 gold, +25 XP and the model's GOLD
    and XP ops added +35 and +11 on top). Same rule as playtest #85b's engine
    path.
    """
    if not isinstance(changes, dict) or not changes.get("updates"):
        return []
    try:
        ctx = load_quest_context(conn, int(turn))
        accepted, _rejected = validate_quest_changes(
            changes,
            narration=narration,
            player_input=player_input,
            npcs=ctx["npcs"],
            locations=ctx["locations"],
            existing=ctx["existing"],
            settled_ids=settled_ids,
            passive=passive,
        )
    except Exception:
        return []
    by_id = {int(q.get("id") or 0): q for q in ctx["existing"]}
    out: list[int] = []
    for upd in accepted["updates"]:
        quest = by_id.get(int(upd.get("quest_id") or 0)) or {}
        if upd["action"] == "complete" or (
            upd["action"] == "step_done" and _int(quest.get("current_step"), 1) >= _int(quest.get("total_steps"), 1)
        ):
            out.append(int(upd["quest_id"]))
    return out


# ---------------------------------------------------------------------------
# Terms and pay the story settles itself (7B run 6)
# ---------------------------------------------------------------------------
# T6: "Two gold for the whole pile, sorted by noon. Yes or no?" was agreed in
# the prose ("I suppose we can agree to that ... the gold is yours") while the
# job kept the engine's rolled 11 gold. T9: the giver handed over the two gold
# for the finished pile, the coin reached the purse, and the job stayed open
# with its 11 gold still to pay.

_JOB_AGREE_RE = re.compile(
    r"\b(?:agree\w*|deal|aye|yes|very\s+well|fair\s+enough|done|struck|settled|"
    r"you['’]ve\s+got\s+(?:it|a\s+deal|yourself\s+a\s+deal)|"
    r"(?:the\s+)?(?:gold|coin|coins|money|pay)\s+(?:is|are|will\s+be)\s+yours)\b",
    re.I,
)
_PAY_YOU_RE = None  # built lazily from prose_state's amount pattern


def _pay_you_re() -> re.Pattern[str]:
    global _PAY_YOU_RE
    if _PAY_YOU_RE is None:
        from app.prose_state import _AMOUNT, _COIN

        _PAY_YOU_RE = re.compile(
            r"\b(?:pay|give)\s+you\s+(?:(?:a|an)\s+)?" + _AMOUNT + r"\s+" + _COIN
            + r"|\b" + _AMOUNT.replace("?P<n>", "?P<n2>") + r"\s+" + _COIN + r"\s+(?:for\s+(?:the|this|that|it|your)|a\s+day|when)",
            re.I,
        )
    return _PAY_YOU_RE


def _player_line_text(player_input: str) -> str:
    """The player's own words, without any engine notes appended after them."""
    return re.split(r"\n\s*__\w+__", str(player_input or ""), maxsplit=1)[0].strip()[:300]


_DEAL_QUESTION_RE = re.compile(
    r"\b(?:offer|price|pay|paid|cost|how\s+(?:many|much)|gold|coins?|terms|deal|sum|number|worth|"
    r"what\s+(?:do|have)\s+you\s+(?:got|have)|what\s+can\s+you\s+give)\b",
    re.I,
)


def _agrees(answer: str) -> bool:
    """An agreeing reply that does not go on to question the deal.

    7B run 10, T3: "Very well, then. What do you have to offer?" is a question
    put back to the player, not agreement to her terms. 7B run 18, T7: "Fair
    enough, lass. You're a bit hurt there. What happened?" agrees and then asks
    about something else; that question does not undo the agreement.
    """
    match = _JOB_AGREE_RE.search(answer)
    if not match:
        return False
    rest = answer[match.end():]
    questions = [q for q in re.findall(r"[^.!?]*\?", rest)]
    return not any(_DEAL_QUESTION_RE.search(q) for q in questions)


_PER_DAY_RE = re.compile(r"\s+(?:a|per|each|every)\s+(?:day|shift|tide)\b|\s+daily\b", re.I)


def _per_day(text: str, amount: int) -> bool:
    """The agreed sum is a day's pay: "Three gold a day" (7B run 18, T7)."""
    from app.prose_state import _AMOUNT, _COIN, _match_number

    for found in re.finditer(_AMOUNT + r"\s+" + _COIN, str(text or ""), re.I):
        if _match_number(found) == amount and _PER_DAY_RE.match(str(text)[found.end():found.end() + 16]):
            return True
    return False


def _echoes(span: str, own: str) -> bool:
    words = set(re.findall(r"[a-z']+", span.lower()))
    own_words = set(re.findall(r"[a-z']+", own.lower()))
    return bool(words) and len(words & own_words) * 2 >= len(words)


def agreed_job_price(narration: str, player_input: str = "") -> tuple[int | None, str]:
    """The pay the scene settles for a job: (gold, how) or (None, "").

    The player's own terms ("Two gold for the whole pile") count when the prose
    answers with agreement and nowhere refuses. Else the one sum the other
    side's speech offers ("I'll pay you five gold", "three gold for the haul").
    """
    from app import prose_state

    text = str(narration or "")
    own = str(player_input or "")
    asked = [a for a in prose_state.stated_coin_amounts(own)["priced"] if a > 0]
    if len(set(asked)) == 1:
        if prose_state._REFUSE_RE.search(text):
            return None, ""
        answers = [m.group(1) or m.group(2) or "" for m in _SPEECH_RE.finditer(text)]
        answers = [a for a in answers if not _echoes(a, own)]
        outside = _SPEECH_RE.sub(" ", text)
        if any(_agrees(a) for a in answers) or re.search(
            r"\b(?:deal\s+is\s+(?:struck|made|done)|you\s+(?:shake|shook)\s+(?:on\s+it|hands))\b", outside, re.I
        ):
            return asked[0], "player_terms_agreed"
        return None, ""
    offered: list[int] = []
    for match in _SPEECH_RE.finditer(text):
        span = match.group(1) or match.group(2) or ""
        if _echoes(span, own):
            continue
        for found in _pay_you_re().finditer(span):
            from app.prose_state import _match_number

            value = _match_number(found)
            if value and value not in offered:
                offered.append(value)
    if len(offered) == 1:
        return offered[0], "giver_terms"
    return None, ""


def _named_in(text: str, npc: dict[str, Any] | None) -> bool:
    if not npc:
        return False
    name = str(npc.get("name") or "").strip()
    code = str(npc.get("code") or "").strip()
    first = name.split()[0] if name else ""
    return bool(
        (code and f"[[{code}]]" in text)
        or (name and re.search(rf"\b{re.escape(name)}\b", text))
        or (len(first) >= 3 and re.search(rf"\b{re.escape(first)}\b", text))
    )


def _open_jobs(conn) -> list[dict[str, Any]]:
    return _rows(
        conn,
        """
        SELECT q.id, q.code, q.title, q.status, q.description, q.reward_gold, q.giver_npc_id, q.notes,
               n.name AS giver_name, n.code AS giver_code
        FROM quests q LEFT JOIN npcs n ON n.id = q.giver_npc_id
        WHERE q.status IN ('offered', 'active')
        ORDER BY q.id
        """,
    )


def settle_agreed_price(conn, *, narration: str, player_input: str = "", turn: int = 0,
                        touched_codes: set[str] | None = None) -> dict[str, Any] | None:
    """Make the pay the scene agreed the job's reward; returns what changed, or None.

    The job is the one this turn offered or took, else the one open job whose
    giver the prose names. Two candidates, or none, change nothing.
    """
    from app import turn_ledger

    amount, how = agreed_job_price(narration, player_input)
    if not amount or amount > REWARD_GOLD_CAP:
        return None
    jobs = _open_jobs(conn)
    touched = [q for q in jobs if str(q.get("code") or "") in (touched_codes or set())]
    pool = touched or [
        q for q in jobs if _named_in(narration, {"name": q.get("giver_name"), "code": q.get("giver_code")})
    ]
    if len(pool) != 1:
        if pool:
            turn_ledger.note("quest", "agreed_price_unplaced", amount=amount, how=how, candidates=[q["code"] for q in pool])
        return None
    job = pool[0]
    if advance_paid(job):
        # The pay was handed over up front; the terms do not owe it twice.
        return None
    if int(job.get("reward_gold") or 0) == amount:
        return None
    # A day rate is recorded as the day's pay and said so: the job pays it
    # once the work is done; the rate stays readable for the next day's deal.
    daily = _per_day(player_input, amount) or _per_day(narration, amount)
    promised = f"{amount} gold a day" if daily else f"{amount} gold"
    description = re.sub(r"\s*Promised:.*$", "", str(job.get("description") or "")).strip()
    description = f"{description} Promised: {promised}".strip()
    conn.execute("UPDATE quests SET reward_gold = ?, description = ? WHERE id = ?", (amount, description[:800], int(job["id"])))
    _journal(conn, turn, f"Terms agreed: {job['title']} for {promised}")
    change = {"code": job.get("code"), "from": job.get("reward_gold"), "to": amount, "how": how, "per_day": daily}
    turn_ledger.note("quest", "agreed_price_set", **change)
    return change


_FOR_THE_WORK_RE = re.compile(
    r"\b(?:earned|for\s+(?:the|your|this|that|all\s+the)\s+(?:work|job|help|trouble|efforts?|labou?r|sorting|haul\w*)|"
    r"your\s+(?:pay|wages?|due|cut)|as\s+promised|as\s+agreed|well\s+done)\b",
    re.I,
)


_PAID_AHEAD_NOTE_RE = re.compile(r"paid_in_advance:(\d+)")
# Pay for work not yet done (7B run 29, T3: the reeve handed over the ship
# job's 11 gold - "There's the payment" - before Isk had said yes).
_ADVANCE_RE = re.compile(
    r"\b(?:in\s+advance|up\s*front|upfront|ahead\s+of\s+time|before\s+(?:the\s+work|you\s+(?:start|begin)|it['’]?s\s+done)|"
    r"(?:half|part)\s+now|(?:an|as\s+an|the)\s+advance)\b",
    re.I,
)
_PAYMENT_WORD_RE = re.compile(
    r"\b(?:payment|pay|wages?|fee|your\s+(?:pay|cut|share)|for\s+the\s+(?:job|work|task|errand)|in\s+advance|up\s*front|an\s+advance)\b",
    re.I,
)


def advance_paid(job: dict[str, Any] | None) -> int:
    """Gold already handed over for this job before it was done (its notes say so)."""
    found = _PAID_AHEAD_NOTE_RE.findall(str((job or {}).get("notes") or ""))
    return sum(int(x) for x in found)


def job_for_unsummed_coin(conn, *, narration: str) -> dict[str, Any] | None:
    """The one open job whose giver hands coin over in this scene, when the prose names no sum.

    7B run 30, T5: Dunstan, whose mole job pays 11, "hands you a small pouch.
    'This should cover it.'" and the GM wrote GRANT "11 gold". The pouch is
    that job's pay. Only a job with a pay, not already paid ahead, whose giver
    the scene names; two such jobs are nobody's.
    """
    jobs = [
        q for q in _open_jobs(conn)
        if int(q.get("reward_gold") or 0) > 0 and not advance_paid(q)
        and _named_in(narration, {"name": q.get("giver_name"), "code": q.get("giver_code")})
    ]
    return jobs[0] if len(jobs) == 1 else None


def job_paid_in_advance(conn, *, narration: str, coin_in: int, skip_ids: set[int] | None = None,
                        accepted_now: set[str] | None = None) -> dict[str, Any] | None:
    """The open job the coin handed over this turn pays for ahead of the work, or None.

    An offered job: its giver is in the scene (or it is a board's job the
    prose talks about), and the coin is its whole pay or is called its
    payment. A taken job counts only when the prose says the pay comes up
    front; otherwise coin for a taken job finishes it (``job_paid_in_prose``).
    Among several, the one whose title the scene names most wins; a tie is
    nobody's.
    """
    if coin_in <= 0:
        return None
    skip = {int(i) for i in skip_ids or set()}
    advance_words = bool(_ADVANCE_RE.search(narration))
    payment_words = bool(_PAYMENT_WORD_RE.search(narration))
    narr_stems = _stems(narration) - _QUEST_STOP_STEMS
    scored: list[tuple[int, int, dict[str, Any]]] = []
    for q in _open_jobs(conn):
        if int(q["id"]) in skip or advance_paid(q):
            continue
        status = str(q.get("status") or "")
        # Taken in this very scene, the work is still ahead: coin handed over
        # with the yes is pay up front (7B run 30, T5), as for an offered job.
        if status == "active" and not advance_words and str(q.get("code") or "") not in (accepted_now or set()):
            continue
        named = len((_stems(q.get("title")) - _QUEST_STOP_STEMS) & narr_stems)
        giver_here = _named_in(narration, {"name": q.get("giver_name"), "code": q.get("giver_code")})
        if not (giver_here or (not q.get("giver_npc_id") and named)):
            continue
        exact = int(q.get("reward_gold") or 0) == int(coin_in)
        if not (exact or payment_words or advance_words):
            continue
        scored.append((int(exact), named, q))
    if not scored:
        return None
    best = max((e, n) for e, n, _ in scored)
    top = [q for e, n, q in scored if (e, n) == best]
    return top[0] if len(top) == 1 else None


def record_advance_pay(conn, job: dict[str, Any], *, coin_in: int, turn: int = 0) -> dict[str, Any]:
    """Count coin handed over ahead of the work as the job's pay: what is left to pay drops by it."""
    before = int(job.get("reward_gold") or 0)
    left = max(0, before - int(coin_in))
    notes = f"{str(job.get('notes') or '')}; paid_in_advance:{int(coin_in)}".strip("; ")
    conn.execute("UPDATE quests SET reward_gold = ?, notes = ? WHERE id = ?", (left, notes[:900], int(job["id"])))
    _journal(conn, turn, f"Paid ahead: {job.get('title')} ({int(coin_in)} gold before the work)")
    return {"code": job.get("code"), "action": "paid_in_advance", "gold_in_story": int(coin_in), "reward_gold": {"from": before, "to": left}}


def job_paid_in_prose(conn, *, narration: str, coin_in: int, skip_ids: set[int] | None = None) -> dict[str, Any] | None:
    """The active job the coin handed over this turn pays for, or None.

    The giver has to be in the scene. A job whose agreed pay is exactly the
    sum wins; else, with one such job, the prose has to say the coin is for
    the work ("you've earned this", "for the sorting").
    """
    if coin_in <= 0:
        return None
    skip = {int(i) for i in skip_ids or set()}
    jobs = [
        q for q in _open_jobs(conn)
        if str(q.get("status") or "") == "active" and int(q["id"]) not in skip
        and _named_in(narration, {"name": q.get("giver_name"), "code": q.get("giver_code")})
    ]
    exact = [q for q in jobs if int(q.get("reward_gold") or 0) == int(coin_in)]
    if len(exact) == 1:
        return exact[0]
    if len(jobs) == 1 and (_FOR_THE_WORK_RE.search(narration) or _quote_names_the_job(narration, jobs[0])):
        return jobs[0]
    return None
