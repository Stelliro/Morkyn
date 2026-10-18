"""
Quest offers, engine first: the engine finds the line, one small ask fills the
card, a second small ask checks it, and the engine decides the rest.

Why this exists (2026-10-18)
----------------------------
The one-shot quest parser read a whole turn and had to decide, in one JSON
reply, whether work was offered, by whom, what the task was, its steps, its pay,
whether the player took it, and whether it duplicated an open job. Over 141 8B
runs it proposed a job in 355 of 360 calls; 112 were created and a rule was
added after it almost every run (docs/showcase/saltmarrow-8b-findings.md). That
is the shape of a task too hard for the model (CLAUDE.md: simplify the failing
task; engine first, checkers not narrator prompt lines).

The split
---------
1. ``find_offer_candidates``: the engine, with no model, finds the spoken lines
   that could offer work: someone other than the player speaks them
   (``conversation.spoken_lines``), they carry job language (the parser's own
   ``_JOB_RE`` / ``_GIVER_OFFERS_JOB_RE`` vocabulary), they are not a refusal,
   and the known hard shapes (a question back about what work is wanted, a
   bare demand to prove oneself) are dropped here. The speaker is the giver.
2. ``build_fill_prompt``: one small ask per candidate line fills the card from
   *that line alone*: does it offer work, what is the task, a title, steps,
   the place and pay the line names. It never sees the roster, the open quests
   or the player's acceptance; those are the engine's.
3. ``build_check_prompt``: a second small ask answers three yes/no questions
   against the paragraph: is this task offered to the player by the giver, is
   it a specific piece of work, is it in the text. Any "no" drops the card.
4. The surviving cards go to ``quest_parser.validate_quest_changes`` in the
   legacy proposal shape with ``_checked`` set: grounding, giver resolution,
   duplicates, retold offers, reward caps and the player's own acceptance stay
   where they were.

``run_offer_pass`` and ``run_progress_pass`` take an ``ask(system, user,
max_tokens, phase)`` callable so this module never talks to the model itself;
app/llm.py supplies ``_chat_json``.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from app import quest_parser as qp

FILL_PHASE = "quest_fill"
CHECK_PHASE = "quest_check"
PROGRESS_PHASE = "quest_progress_check"
FILL_MAX_TOKENS = 260
CHECK_MAX_TOKENS = 90
CANDIDATE_CAP = 3
PROGRESS_CAP = 2

Ask = Callable[..., Any]

# The giver setting the task for one who asked: "You'll need to clear a full
# load" (8B run 47, T2). Working off one's own debt, paying, waiting and proving
# oneself set no task (runs 74, 132).
_SETS_TASK_RE = re.compile(
    r"\byou['’]ll\s+(?:need|have)\s+to\s+(?!work\s+(?:it|that|this|the\s+debt|your\s+debt)\s+off)"
    r"(?!pay\b|wait\b|be\s+careful|prove|show|choose|pick|select|decide)[a-z]+",
    re.I,
)
# A list to choose from is not a task yet: "The guild has a list of tasks.
# You'll need to choose one that fits your skills" filed "Choose a Task" with
# the steps "Choose dockside salvage", "Choose warehouse inventory" (8B run
# 143, T2). The job is the one the player picks, offered when the giver names it.
_CHOOSE_ONE_RE = re.compile(
    r"\b(?:choose|pick|select|decide\s+on|take\s+your\s+pick)\s+(?:one|which|whichever|the\s+one|a\s+task|a\s+job|"
    r"from|between|among|what\s+suits|one\s+that)\b",
    re.I,
)
# A bare demand to prove oneself names no task (8B run 132, T2).
_PROVE_ONLY_RE = re.compile(
    r"\byou(?:['’]ll|\s+will|['’]d|\s+would)?\s+(?:have|need|got)\s+to\s+(?:prove|show)\s+"
    r"(?:yourself|your\s+worth|your\s+mettle|you(?:['’]re|\s+are)\s+worth\s+it)\b",
    re.I,
)
_YES_RE = re.compile(r"^\s*(?:y|yes|true|1)\b", re.I)


def _yes(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value >= 1
    return bool(_YES_RE.match(str(value or "")))


def _paragraph_of(narration: str, line: str) -> str:
    """The paragraph that holds the spoken line; the whole text when none does."""
    probe = qp._ws(line)[:40]
    for paragraph in re.split(r"\n\s*\n", str(narration or "")):
        if probe and probe in qp._ws(paragraph):
            return re.sub(r"\s+", " ", paragraph).strip()
    return re.sub(r"\s+", " ", str(narration or "")).strip()


def _npc_label(npc: dict[str, Any] | None, stranger: str = "", kind: str = "spoken") -> str:
    if kind == "posted":
        return "a posted notice"
    if npc:
        name = str(npc.get("name") or "").strip()
        role = str(npc.get("role") or "").strip()
        return f"{name} ({role})" if role else name or "someone"
    return stranger or "someone the engine does not know yet"


# "You'll find her where the wreckage still floats", "You'll find them at the
# docks": directions to a person or thing, not work (8B runs 111, 48, 55, 99).
_FIND_POINTER_RE = re.compile(
    r"\byou(?:['’]ll|\s+will|\s+might|\s+may|\s+can|\s+should)\s+find\s+(?:him|her|them|it)\b", re.I
)


def _code_veto(line: str, *, asked_for_work: bool) -> str:
    """Why a job-worded line still offers nothing, decided in code; "" when it may."""
    cleaned = qp._offer_text(line)
    if qp._NO_WORK_RE.search(line):
        return "refusal"
    if qp._ASKS_WHICH_WORK_RE.search(line) and not qp._GIVER_OFFERS_JOB_RE.search(line):
        return "asks_what_work"
    if _PROVE_ONLY_RE.search(line) and not qp._GIVER_OFFERS_JOB_RE.search(line) and not qp._JOB_RE.search(cleaned):
        return "prove_only"
    if _CHOOSE_ONE_RE.search(line) and not qp._GIVER_OFFERS_JOB_RE.search(cleaned):
        return "asks_to_choose"
    # The player paying for a service is no job for them (8B run 106, T7:
    # "you're paying for the risk"; runs 82, 96: "if you're willing to pay").
    if qp._PLAYER_PAYS_RE.search(line) and not qp._PAYS_THE_PLAYER_RE.search(line) and not qp._GIVER_OFFERS_JOB_RE.search(cleaned):
        return "player_pays"
    without_pointer = _FIND_POINTER_RE.sub(" ", cleaned)
    if _FIND_POINTER_RE.search(cleaned) and not qp._JOB_RE.search(without_pointer) and not qp._GIVER_OFFERS_JOB_RE.search(cleaned):
        return "pointer_to_someone"
    # A suggestion is no assignment: "Now, let's see if there's anything else
    # worth salvaging ... You might find the name board in there" from the
    # ferryman filed a second wreck job (8B run 147, T29). Nobody who says
    # "let's" or "you might" is handing out work unless they also name pay.
    if _SUGGESTION_RE.search(cleaned) and not qp._GIVER_OFFERS_JOB_RE.search(cleaned) and not _names_pay(cleaned):
        return "suggestion_not_task"
    # A debt read out of a ledger is a fact, not a task: "The guild owes the
    # reeve a sum of thirty gold for the work done on the wreck" filed "Record
    # the Guild's Debt" with invented steps (8B run 148, T75). Only an errand
    # on that debt (collect it, bring it, deliver it) is work.
    if _DEBT_STATEMENT_RE.search(cleaned) and not qp._GIVER_OFFERS_JOB_RE.search(cleaned) and not _ERRAND_VERB_RE.search(cleaned):
        return "debt_statement"
    # A word on work under way is no new job: "You're doing good work,
    # Flat-runner. The guild needs more hands, and you're helping out" from a
    # passing hand filed "Helping Out at the Guild" while the crates were being
    # loaded (8B run 150, T46).
    if _PRAISE_OF_WORK_RE.search(cleaned) and not qp._GIVER_OFFERS_JOB_RE.search(cleaned) and not _names_pay(cleaned):
        return "praise_of_work"
    return ""


_DEBT_STATEMENT_RE = re.compile(
    r"\b(?:owes?|owed|is\s+owed|are\s+owed|in\s+debt\s+to|the\s+debt\s+(?:stands|is|comes)\s+(?:at|to))\b", re.I
)
_PRAISE_OF_WORK_RE = re.compile(
    r"\b(?:good\s+work|well\s+done|keep\s+(?:it|that)\s+up|nice\s+work|fine\s+work|"
    r"you(?:['’]re|\s+are)\s+(?:doing|helping|working|pulling|earning)\b)",
    re.I,
)
_ERRAND_VERB_RE = re.compile(
    r"\b(?:bring|fetch|collect|deliver|find|take|carry|haul|go|get|recover|settle|pay\s+(?:it|him|her|them)|"
    r"call\s+(?:it|the\s+debt)\s+in|see\s+(?:it|that)\s+(?:paid|settled))\b",
    re.I,
)


def _names_pay(text: str) -> bool:
    """The line pays the player or names a sum of coin."""
    if qp._PAYS_THE_PLAYER_RE.search(text):
        return True
    from app import prose_state

    return bool(prose_state.coin_mentions(text))


_SUGGESTION_RE = re.compile(
    r"\b(?:let['’]s|let\s+us|we\s+could|we\s+might|you\s+might|you\s+could|maybe|perhaps|why\s+don['’]t\s+(?:we|you)|"
    r"shall\s+we|how\s+about|"
    # "You should speak to the guildmaster. He'll know the details" filed a
    # job "Clear Credit with Guild" on the player's own question (8B run 148,
    # T59): advice on whom to see is no assignment.
    r"you\s+should|you['’]d\s+(?:best|better|do\s+well\s+to)|you\s+ought\s+to|your\s+best\s+bet)\b",
    re.I,
)


def _carries_offer(line: str, *, asked_for_work: bool) -> str:
    """The job language the line carries, as the reason it is a candidate; "" when none."""
    cleaned = qp._offer_text(line)
    if qp._GIVER_OFFERS_JOB_RE.search(cleaned):
        return "giver_offers_job"
    if qp._JOB_RE.search(cleaned):
        return "job_words"
    if asked_for_work:
        if qp._AGREES_RE.search(line):
            return "agrees_to_ask"
        if _SETS_TASK_RE.search(cleaned):
            return "sets_the_task"
    return ""


def find_offer_candidates(
    narration: str,
    player_input: str = "",
    *,
    npcs: list[dict[str, Any]] | None = None,
    locations: list[dict[str, Any]] | None = None,
    marks: list[dict[str, Any]] | None = None,
    asked_for_work: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    (candidates, dropped). Each candidate: {"line", "speaker", "stranger", "kind",
    "paragraph", "why"}; each dropped row: {"line", "why"}. No model.

    A candidate is one speaker's quoted speech in one unit of the prose; the
    unit keeps a quotation spanning several sentences together, so "There's a
    job at the docks. A shipment of salted fish needs unloading." is one line.
    """
    text = str(narration or "")
    rows = [n for n in npcs or [] if isinstance(n, dict) and str(n.get("code") or "").strip()]
    by_code = {str(n.get("code") or "").strip(): n for n in rows}
    place_names = [str(p.get("name") or "") for p in locations or [] if isinstance(p, dict)]
    candidates: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(line: str, *, code: str, kind: str, why: str, quote: str = "") -> None:
        flat = re.sub(r"\s+", " ", str(line or "")).strip()
        quote = re.sub(r"\s+", " ", str(quote or flat)).strip()
        key = qp._norm(flat)[:80]
        if not flat or key in seen:
            return
        veto = _code_veto(flat, asked_for_work=asked_for_work)
        if veto:
            seen.add(key)
            dropped.append({"line": flat[:240], "why": veto})
            return
        speaker = by_code.get(code) if code else None
        stranger = ""
        if speaker is None and kind != "posted":
            stranger = qp._unknown_offer_speaker(text, quote, rows, place_names)
        seen.add(key)
        candidates.append(
            {
                "line": flat,
                "quote": quote,
                "speaker": speaker,
                "stranger": stranger,
                "kind": kind,
                "paragraph": _paragraph_of(text, quote),
                "why": why,
            }
        )

    try:
        from app.conversation import spoken_lines

        spoken = spoken_lines(text, rows, player_input)
    except Exception:
        spoken = []
    # One speaker's lines in one paragraph are one offer: Garrick's '"A job,"
    # ... "You'll be fetching salvage from the docks ..."' is read together, and
    # the longest piece is the quote the engine grounds (8B run 103, T4).
    # A known speaker's lines across the whole turn are one candidate too: the
    # tallyman's "You'll need to work it off ..." and, a paragraph on, "There's
    # the salvage contracts ..." cost two fills and two checks (8B run 146, T2).
    # Lines with no known speaker stay per paragraph, since two strangers may speak.
    groups: list[dict[str, Any]] = []
    for entry in spoken:
        line = str(entry.get("line") or "")
        code = str(entry.get("code") or "")
        paragraph = _paragraph_of(text, line)
        same = next(
            (g for g in groups if g["code"] == code and (code or g["paragraph"] == paragraph)), None
        ) if code else (groups[-1] if groups and groups[-1]["code"] == code and groups[-1]["paragraph"] == paragraph else None)
        if same is not None:
            same["lines"].append(line)
            if paragraph not in same["paragraph"]:
                same["paragraph"] = f"{same['paragraph']}\n\n{paragraph}"
        else:
            groups.append({"code": code, "paragraph": paragraph, "lines": [line]})
    for group in groups:
        joined = " ".join(group["lines"])
        why = _carries_offer(joined, asked_for_work=asked_for_work)
        if why:
            _add(joined, code=group["code"], kind="spoken", why=why, quote=max(group["lines"], key=len))
    # A posting read aloud: "You read the details aloud: 'Lifting supplies ...'"
    for sentence in qp._SENTENCE_SPLIT.split(text):
        if qp._READ_POSTING_RE.search(sentence) and qp._JOB_RE.search(qp._offer_text(sentence)):
            _add(sentence, code="", kind="posted", why="posting_read")
    # The narrator's own QUEST marks are hints to look at a line, never a card
    # on their own (they carry no quote: 0 of 95 in the 8B runs). The mark's
    # giver's spoken lines, when no candidate is theirs yet, go through the
    # same fill and check as any other line; a mark with no spoken line behind
    # it is dropped, which is where "Salvage Contract" from "You're late,
    # Flat-runner" came from (8B run 44, T1).
    for mark in marks or []:
        if not isinstance(mark, dict) or str(mark.get("op") or "").upper() != "QUEST":
            continue
        giver = qp._resolve_npc(str(mark.get("giver") or ""), rows)
        code = str((giver or {}).get("code") or "")
        if code and any((c.get("speaker") or {}).get("code") == code for c in candidates):
            continue
        if not code and candidates:
            # A giver met this turn is not in the roster yet; their spoken
            # offer is already a candidate under an unknown speaker.
            continue
        theirs = [g for g in groups if code and g["code"] == code]
        if not theirs:
            dropped.append({"line": str(mark.get("title") or "")[:80], "why": "mark_without_a_spoken_line"})
            continue
        group = max(theirs, key=lambda g: len(" ".join(g["lines"])))
        _add(" ".join(group["lines"]), code=code, kind="mark", why="narrator_mark", quote=max(group["lines"], key=len))
    return candidates[:CANDIDATE_CAP], dropped


_FILL_SYSTEM = (
    "You fill in one job card for a role-playing game engine from one spoken line. "
    "Return JSON only, one object. Copy words from the line; never add work the line does not name."
)
_CHECK_SYSTEM = (
    "You check one job card against a passage of story for a game engine. "
    "Answer each question yes or no from the passage alone. Return JSON only, one object."
)
_PROGRESS_SYSTEM = (
    "You check whether a passage of story shows a piece of work finished, for a game engine. "
    "Answer yes or no from the passage alone. Return JSON only, one object."
)

FILL_SHAPE: dict[str, Any] = {
    "offers_work": "true only when the speaker asks the player to do a specific piece of work, or agrees to the player doing one",
    "task": "the work itself, in the speaker's own words",
    "title": "three to eight words naming the work",
    "steps": ["one to four concrete actions, in order"],
    "place": "where the work is, when the line says; else empty",
    "pay": "what is promised for it, in the line's words; else empty",
    "gold": "a number only when the line names an amount of coin, else 0",
}


_FILL_PLACEHOLDERS = qp._shape_strings(FILL_SHAPE)


def _drop_fill_placeholders(node: Any) -> Any:
    """A field filled with the shape's own wording is empty (the 8B pastes shapes back; 8B run 92, T2)."""
    if isinstance(node, dict):
        return {k: _drop_fill_placeholders(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_drop_fill_placeholders(v) for v in node]
    if isinstance(node, str) and node.strip().lower() in _FILL_PLACEHOLDERS:
        return ""
    return node


def build_fill_prompt(
    candidate: dict[str, Any], player_input: str = "", *, locations: list[dict[str, Any]] | None = None
) -> tuple[str, str]:
    """(system, user) for the fill ask: one line, one card."""
    import json

    speaker = _npc_label(candidate.get("speaker"), candidate.get("stranger") or "", candidate.get("kind") or "spoken")
    places = [str(p.get("name") or "") for p in locations or [] if isinstance(p, dict) and p.get("name")][:8]
    payload = {
        "speaker": speaker,
        "line": str(candidate.get("line") or "")[:600],
        "around": str(candidate.get("paragraph") or "")[:700],
        "player_said": qp._player_own_line(str(player_input or ""))[:300],
        "known_places": places,
        "return": FILL_SHAPE,
        "rules": [
            "offers_work is false for a question about what work the player wants, a demand to prove oneself, "
            "talk about the player's debt, and the player's own plans or wishes.",
            "Read only the line and what is around it.",
        ],
    }
    return _FILL_SYSTEM, json.dumps(payload, ensure_ascii=True)


def parse_fill(raw: Any) -> dict[str, Any] | None:
    """The filled card, or None when the line offers no work or the reply is unusable."""
    data = raw if isinstance(raw, dict) else None
    if data is None:
        try:
            data = qp._loads_loose(str(raw or ""))
        except Exception:
            data = None
    if not isinstance(data, dict):
        return None
    data = _drop_fill_placeholders(qp._drop_placeholders(data))
    # Only an explicit no ends the card. A reply that filled every field and
    # left the flag out lost a real job (the Reeve's chest for forty-five gold,
    # 8B run 147, T36); the check ask still has to say yes to it.
    flag = data.get("offers_work")
    if flag is not None and str(flag).strip() != "" and not _yes(flag):
        return None
    task = re.sub(r"\s+", " ", str(data.get("task") or "")).strip()
    title = re.sub(r"\s+", " ", str(data.get("title") or "")).strip(" .\"'")
    if not task and not title:
        return None
    steps = data.get("steps")
    if isinstance(steps, str):
        steps = [steps]
    step_titles = []
    for step in steps or []:
        if isinstance(step, dict):
            step = step.get("title") or step.get("description") or ""
        step = re.sub(r"\s+", " ", str(step or "")).strip()
        if step:
            step_titles.append(step[:120])
    gold = qp._int(data.get("gold"), 0)
    return {
        "task": task[:400],
        "title": (title or task)[:80],
        "steps": step_titles[:4] or [(task or title)[:120]],
        "place": re.sub(r"\s+", " ", str(data.get("place") or "")).strip()[:100],
        "pay": re.sub(r"\s+", " ", str(data.get("pay") or "")).strip()[:200],
        "gold": max(0, gold),
    }


def build_check_prompt(
    candidate: dict[str, Any], card: dict[str, Any], player_input: str = "",
    open_jobs: list[dict[str, Any]] | None = None,
) -> tuple[str, str]:
    """(system, user) for the check ask: three yes/no questions against the paragraph.

    With ``open_jobs`` (the jobs already offered or taken, by code), a fourth
    question asks which of them, if any, this line tells again: a job retold
    under another name binds by its reference, not by title similarity
    (Stell, 2026-10-18).
    """
    import json

    giver = _npc_label(candidate.get("speaker"), candidate.get("stranger") or "", candidate.get("kind") or "spoken")
    passage = str(candidate.get("paragraph") or candidate.get("line") or "")[:900]
    own = qp._player_own_line(str(player_input or ""))[:300]
    payload: dict[str, Any] = {
        "passage": passage,
        "player_said": own,
        "card": {"giver": giver, "title": card.get("title"), "task": card.get("task")},
        "questions": {
            "offered": f"Does {giver}, not the player, offer or assign this task to the player in the passage?",
            "specific": "Is the task a specific piece of work the player could go and do, rather than a demand to prove "
                        "oneself, a question about what work the player wants, or talk about the player's debt?",
            "in_text": "Is this task stated in the passage, not added to it?",
        },
        "return": {"offered": "yes or no", "specific": "yes or no", "in_text": "yes or no", "why": "one short sentence"},
    }
    jobs = [
        {"code": str(j.get("code") or ""), "title": str(j.get("title") or "")[:80], "giver": str(j.get("giver") or "")[:60]}
        for j in open_jobs or [] if isinstance(j, dict) and j.get("code") and j.get("title")
    ][:8]
    if jobs:
        payload["open_jobs"] = jobs
        payload["questions"]["same_job"] = (
            "Is this task one of open_jobs told again, in other words or more detail? If so, which code; if it is new work, none."
        )
        payload["return"]["same_job"] = "a code from open_jobs, or none"
    return _CHECK_SYSTEM, json.dumps(payload, ensure_ascii=True)


def parse_check(raw: Any) -> dict[str, Any]:
    """{"ok": bool, "offered", "specific", "in_text", "why"}; an unusable reply is not ok."""
    data = raw if isinstance(raw, dict) else None
    if data is None:
        try:
            data = qp._loads_loose(str(raw or ""))
        except Exception:
            data = None
    if not isinstance(data, dict):
        return {"ok": False, "offered": False, "specific": False, "in_text": False, "why": "unusable reply", "same_job": ""}
    verdict = {key: _yes(data.get(key)) for key in ("offered", "specific", "in_text")}
    same = re.search(r"\bQ\d+\b", str(data.get("same_job") or ""), re.I)
    return {"ok": all(verdict.values()), **verdict, "why": str(data.get("why") or "")[:200],
            "same_job": same.group(0).upper() if same else ""}


def _verified_retell(code: str, open_jobs: list[dict[str, Any]] | None, candidate: dict[str, Any]) -> str:
    """The open job's code the check named, when it is listed and its giver fits this line's speaker; else ""."""
    code = str(code or "").strip().upper()
    if not code:
        return ""
    job = next((j for j in open_jobs or [] if isinstance(j, dict) and str(j.get("code") or "").upper() == code), None)
    if job is None:
        return ""
    speaker = candidate.get("speaker") if isinstance(candidate.get("speaker"), dict) else None
    giver = str(job.get("giver") or "").strip().lower()
    if speaker and giver:
        who = {str(speaker.get("name") or "").lower(), str(speaker.get("code") or "").lower()}
        first = str(speaker.get("name") or "").split()[0].lower() if str(speaker.get("name") or "").split() else ""
        if giver not in who and (not first or not giver.startswith(first)):
            return ""
    return code


def card_to_proposal(candidate: dict[str, Any], card: dict[str, Any], check: dict[str, Any]) -> dict[str, Any]:
    """The legacy proposal shape validate_quest_changes reads, marked as checked."""
    speaker = candidate.get("speaker") if isinstance(candidate.get("speaker"), dict) else None
    if candidate.get("kind") == "posted":
        giver = "the notice board"
    elif speaker:
        giver = str(speaker.get("code") or speaker.get("name") or "")
    else:
        giver = str(candidate.get("stranger") or "")
    quote = str(candidate.get("quote") or candidate.get("line") or "")
    return {
        "title": card["title"],
        "summary": card["task"] or card["title"],
        "giver": giver,
        "status": "offered",
        "steps": [{"title": s, "description": s, "location": card.get("place") or ""} for s in card["steps"]],
        "reward": {"gold": card.get("gold") or 0, "xp": 0, "items": [], "text": card.get("pay") or ""},
        "difficulty": "normal",
        "timer_turns": 0,
        "offer_line": quote[:300],
        "evidence": quote[:300],
        "_checked": {"why": check.get("why") or "", "found_by": candidate.get("why") or "", "kind": candidate.get("kind")},
    }


def run_offer_pass(
    narration: str,
    player_input: str = "",
    *,
    npcs: list[dict[str, Any]] | None = None,
    locations: list[dict[str, Any]] | None = None,
    marks: list[dict[str, Any]] | None = None,
    asked_for_work: bool = False,
    ask: Ask | None = None,
    open_jobs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Find, fill, check. Returns {"new": [proposals], "candidates", "dropped", "fills", "checks"}.

    ``open_jobs`` (code, title, giver) are the jobs already offered or taken;
    the check names the one a line tells again, and the proposal carries it as
    ``retells`` so the parser binds by reference.

    ``ask(system, user, max_tokens=..., phase=...)`` returns the model's JSON
    (a dict) or raises. With no ``ask`` nothing is proposed: the engine never
    guesses a card from keywords alone.
    """
    candidates, dropped = find_offer_candidates(
        narration, player_input, npcs=npcs, locations=locations, marks=marks, asked_for_work=asked_for_work
    )
    report: dict[str, Any] = {
        "new": [],
        "candidates": [
            {"line": c["line"][:240], "speaker": str((c.get("speaker") or {}).get("name") or c.get("stranger") or ""),
             "kind": c["kind"], "why": c["why"]}
            for c in candidates
        ],
        "dropped": dropped,
        "fills": [],
        "checks": [],
    }
    if not candidates or ask is None:
        return report
    for candidate in candidates:
        system, user = build_fill_prompt(candidate, player_input, locations=locations)
        try:
            raw = ask(system, user, max_tokens=FILL_MAX_TOKENS, phase=FILL_PHASE)
        except Exception as exc:
            report["fills"].append({"line": candidate["line"][:120], "error": f"{exc.__class__.__name__}: {exc}"[:200]})
            continue
        card = parse_fill(raw)
        report["fills"].append({"line": candidate["line"][:120], "card": card})
        if card is None:
            continue
        # The task has to be the giver's, not the player's own words said back:
        # Hamon's "Most of them would've asked for a cut" filled a card whose
        # task was the player's "Take me out to the wreck and show me what is
        # buried" (8B run 146, T34).
        own = qp._player_own_line(str(player_input or ""))
        # Unless the giver's own line names the pay: the player asking "whether
        # the guild wants that bread debt collected from Dunmore, and what it
        # pays" and Mira answering "a silver for every coin you bring in, plus
        # a bonus" is a real offer in the player's words (8B run 147, T89).
        if (
            (card.get("task") and qp.evidence_found(card["task"], own))
            or (card.get("title") and len(card["title"]) >= 12 and qp.evidence_found(card["title"], own))
        ) and not _names_pay(str(candidate.get("line") or "")):
            report["fills"][-1]["dropped"] = "task_is_the_players_words"
            continue
        # The steps are the giver's words too: Nell's "You'll be paid well for
        # this" filled "Load the Hesperian's crates for Rafe" and "Pay Mabel's
        # three gold" out of the player's own line (8B run 150, T72). A step
        # found in the player's line and not in the giver's goes; a card left
        # with none is no offer.
        giver_line = str(candidate.get("line") or "")
        kept_steps = [s for s in card["steps"] if not (qp.evidence_found(s, own) and not qp.evidence_found(s, giver_line))]
        if not kept_steps:
            report["fills"][-1]["dropped"] = "steps_are_the_players_words"
            continue
        card["steps"] = kept_steps
        system, user = build_check_prompt(candidate, card, player_input, open_jobs=open_jobs)
        try:
            raw = ask(system, user, max_tokens=CHECK_MAX_TOKENS, phase=CHECK_PHASE)
        except Exception as exc:
            report["checks"].append({"title": card["title"], "error": f"{exc.__class__.__name__}: {exc}"[:200]})
            continue
        check = parse_check(raw)
        # The engine checks the reference: the code has to be a listed open job,
        # and its giver this line's speaker when both are known.
        retells = _verified_retell(check.get("same_job") or "", open_jobs, candidate)
        check["same_job"] = retells
        report["checks"].append({"title": card["title"], **check})
        if not check["ok"] and not (retells and check.get("in_text")):
            continue
        proposal = card_to_proposal(candidate, card, check)
        if retells:
            proposal["retells"] = retells
        report["new"].append(proposal)
        if len(report["new"]) >= qp.MAX_NEW_PER_TURN:
            break
    return report


def typed_accepts(player_input: str, open_offers: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """
    The player's own typed yes to the one offer it can mean, as an update for
    validate_quest_changes (which still checks player_takes_job).

    In legacy mode the one-shot parser proposed these; the checked flow
    proposes no updates of its own, so '"The captain's ledger, then. I'll find
    it."' left the offer standing (8B run 146, T14). A refusal is the engine's
    already (quest_parser.settle_player_answer).
    """
    line = qp._player_own_line(str(player_input or ""))
    offers = [o for o in open_offers or [] if isinstance(o, dict) and str(o.get("status") or "offered") == "offered"]
    if not offers or not qp.player_accepts(line) or qp.player_refuses(line):
        return []
    picked = None
    if len(offers) == 1:
        picked = offers[0]
    else:
        named = [o for o in offers if qp._means_this_offer(o, offers, line)]
        picked = named[0] if len(named) == 1 else None
    if picked is None:
        return []
    code = str(picked.get("code") or (f"Q{picked['id']}" if picked.get("id") else picked.get("title") or ""))
    return [{"quest": code, "action": "accept", "evidence": line[:300], "_typed": True}]


def marks_to_merge(marks: list[dict[str, Any]] | None, mode: str) -> list[dict[str, Any]]:
    """
    The narrator marks the engine may still fold in after the offer pass.

    In checked mode a QUEST mark was already read as a hint to a spoken line
    (find_offer_candidates) and never becomes a card on its own, so only the
    QUEST_DONE / QUEST_UPDATE marks remain to merge, and validate_quest_changes
    holds those to the same evidence as any other update. The 8B run 142 T2
    showed the apply step merging a bare "Salvage Contract" mark after the
    offer pass had already decided; both merge points use this one rule.
    """
    rows = [m for m in marks or [] if isinstance(m, dict)]
    if str(mode or "") != "checked":
        return rows
    return [m for m in rows if str(m.get("op") or "").upper() != "QUEST"]


# ---------------------------------------------------------------------------
# Progress: a step of an active job shown finished in the prose
# ---------------------------------------------------------------------------
# A step whose result is another's agreement.
_CONSENT_STEP_RE = re.compile(
    r"\b(?:convinc\w*|persuad\w*|talk\s+(?:\w+\s+){0,3}?into|get\s+(?:\w+\s+){0,3}?to\s+(?:agree|let|allow|give|hand|part)|"
    r"win\s+(?:\w+\s+){0,2}?over|bargain\w*|negotiat\w*|make\s+(?:\w+\s+){0,3}?agree|secure\s+(?:\w+\s+){0,2}?(?:agreement|consent|blessing|leave))\b",
    re.I,
)
# Someone other than the player saying yes, in speech or in the narration.
_CONSENT_SHOWN_RE = re.compile(
    r"\b(?:agree[sd]?|agreed|very\s+well|all\s+right|alright|so\s+be\s+it|you\s+may|you\s+can\s+(?:have|take)|"
    r"take\s+it(?:,|\.|\s+then)|it['’]s\s+yours|(?:we|you)\s+have\s+a\s+deal|deal\b|done\b|"
    r"i['’]ll\s+(?:allow|let|permit)|(?:nods|nodding)\s+(?:once|slowly|his|her|their)?\s*(?:assent|agreement|yes)?|"
    r"relent\w*|gives?\s+(?:in|way)|consent\w*|yes\b)",
    re.I,
)


def _others_consent(narration: str, player_input: str = "") -> bool:
    """Does anyone but the player say or show yes in this passage?"""
    text = str(narration or "")
    own = [re.sub(r"\s+", " ", (a or b)).strip().lower()
           for a, b in re.findall(r"\"([^\"]+)\"|“([^”]+)”", qp._player_own_line(str(player_input or "")))]
    for match in re.finditer(r"\"([^\"]+)\"|“([^”]+)”", text):
        quote = (match.group(1) or match.group(2) or "").strip()
        if any(q[:40] in quote.lower() for q in own):
            continue
        tail = text[match.end(): match.end() + 60]
        if re.match(r"\s*,?\s*you\s+(?:say|said|ask|reply|add|answer|offer|tell)\b", tail, re.I):
            continue
        if _CONSENT_SHOWN_RE.search(quote):
            return True
    unspoken = re.sub(r"\"[^\"]*\"|“[^”]*”", " ", text)
    for sentence in qp._SENTENCE_SPLIT.split(unspoken):
        if re.search(r"\byou\b", sentence, re.I) and not re.search(r"\b(?:he|she|they)\b", sentence, re.I):
            continue
        if re.search(r"\b(?:agrees?|agreed|relents?|relented|consents?|consented|nods\s+(?:his|her|their)\s+assent|gives\s+(?:in|way)|hands\s+(?:it|them)\s+over)\b", sentence, re.I):
            return True
    return False


def find_progress_candidates(
    narration: str, player_input: str = "", *, active: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """
    Sentences that may show a step of an active job done: a result word that is
    not a purpose or a promise (quest_parser._shows_result) in a sentence that
    shares a word with the job's title or its current step. No model.
    """
    out: list[dict[str, Any]] = []
    text = str(narration or "")
    # The player's own words said back by the prose are no result: '"Forty-five
    # gold for the deep dive ... Done," you say' finished "Join a team for a
    # deep dive" (8B run 145, T38). Only what the world shows counts.
    own_quotes = [
        re.sub(r"\s+", " ", (a or b)).strip().lower()
        for a, b in re.findall(r"\"([^\"]+)\"|“([^”]+)”", qp._player_own_line(str(player_input or "")))
        if len((a or b).strip()) >= 12
    ]
    for quest in active or []:
        if not isinstance(quest, dict) or str(quest.get("status") or "active") != "active":
            continue
        title = str(quest.get("title") or "")
        step = str(quest.get("current_objective") or quest.get("current_step_title") or "")
        words = qp._title_words(title) | {w for w in qp._stems(step) if len(w) >= 4}
        if not words:
            continue
        for sentence in qp._SENTENCE_SPLIT.split(text):
            flat = re.sub(r"\s+", " ", sentence).strip()
            if not flat or flat.endswith("?"):
                continue
            if any(q[:40] in flat.lower() for q in own_quotes):
                continue
            # A sentence tagged as the player's speech is theirs however it was split.
            if re.search(r"\byou\s+(?:say|said|ask|asked|reply|replied|add|added|mutter|muttered|call|called|tell|told)\b", flat, re.I):
                continue
            # A result word that is not a purpose ("to find the ship" finds
            # nothing), or the parser's own progress vocabulary ("counts out",
            # "handed over", "pays you").
            if not (qp._shows_result(flat) or qp._PROGRESS_RE.search(flat)):
                continue
            stems = qp._stems(flat) | set(re.findall(r"[a-z]{4,}", flat.lower()))
            if not (words & stems) and not any(w in flat.lower() for w in words if len(w) >= 5):
                continue
            # A step that needs someone's yes is done only when they give it:
            # "Convince the Drowned Hand to let you take it" was finished on
            # "You hand the journal over to Rolf" while Veyra had said "Not
            # without a price" (8B run 146, T70). The check is not asked.
            if _CONSENT_STEP_RE.search(step or title) and not _others_consent(text, player_input):
                from app import turn_ledger

                turn_ledger.note("quest", "consent_step_without_a_yes", title=title, step=step)
                break
            out.append({"quest": quest, "sentence": flat[:400], "step": step, "title": title})
            break
        if len(out) >= PROGRESS_CAP:
            break
    return out


def build_progress_prompt(candidate: dict[str, Any], narration: str, player_input: str = "") -> tuple[str, str]:
    import json

    payload = {
        "passage": _paragraph_of(narration, candidate["sentence"])[:900],
        "player_did": qp._player_own_line(str(player_input or ""))[:300],
        "job": {"title": candidate["title"], "current_step": candidate["step"] or candidate["title"]},
        "question": "Does the passage show this step finished, with its result, by the player? "
                    "Setting out, planning, being told about the work, or work still going on is no.",
        "return": {"finished": "yes or no", "why": "one short sentence"},
    }
    return _PROGRESS_SYSTEM, json.dumps(payload, ensure_ascii=True)


def run_progress_pass(
    narration: str,
    player_input: str = "",
    *,
    active: list[dict[str, Any]] | None = None,
    ask: Ask | None = None,
) -> dict[str, Any]:
    """Find, check. Returns {"updates": [{"quest", "action": "step_done", "evidence"}], "candidates", "checks"}."""
    candidates = find_progress_candidates(narration, player_input, active=active)
    report: dict[str, Any] = {
        "updates": [],
        "candidates": [{"title": c["title"], "sentence": c["sentence"][:240]} for c in candidates],
        "checks": [],
    }
    if not candidates or ask is None:
        return report
    for candidate in candidates:
        system, user = build_progress_prompt(candidate, narration, player_input)
        try:
            raw = ask(system, user, max_tokens=CHECK_MAX_TOKENS, phase=PROGRESS_PHASE)
        except Exception as exc:
            report["checks"].append({"title": candidate["title"], "error": f"{exc.__class__.__name__}: {exc}"[:200]})
            continue
        data = raw if isinstance(raw, dict) else None
        if data is None:
            try:
                data = qp._loads_loose(str(raw or ""))
            except Exception:
                data = None
        finished = isinstance(data, dict) and _yes(data.get("finished"))
        why = str((data or {}).get("why") or "")[:200] if isinstance(data, dict) else "unusable reply"
        report["checks"].append({"title": candidate["title"], "finished": bool(finished), "why": why})
        if not finished:
            continue
        quest = candidate["quest"]
        report["updates"].append(
            {
                "quest": str(quest.get("code") or (f"Q{quest['id']}" if quest.get("id") else candidate["title"])),
                "action": "step_done",
                "evidence": candidate["sentence"][:300],
                "_checked": {"why": why},
            }
        )
    return report
