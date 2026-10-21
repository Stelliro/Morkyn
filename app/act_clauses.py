"""Which parts of the player's own line are things the player does now.

One reading, by grammar, for every engine reader that turns the player's line
into an act: the dice (skill_checks), the body's cost (player_resources), the
clock and the act families (prose_state.declared_act), and whether the line
asks to go somewhere (world._unasked_unshown_move).

The line is split into clauses and each clause is judged by its form, not by
its verb (fault log F153, F171, F179):

- speech: words inside the player's quotes are said, not done;
- condition: a clause led by if / unless / once / whether / when / before /
  until is a case or a goal, not the act ("when the reef comes in sight",
  "until I find him", "before I agree to anything");
- plan: a modal or a wish ("I could", "I should", "I want to", "I plan to"),
  or a future with a later time ("I'll polish them after lunch");
- reported: what follows tell / ask / order / promise / let ... to / that /
  I'll is someone else's act or a message ("tell Nell I'll take the matter to
  the reeve", "ask Rafe to hold the skiff");
- question: a narrated question ("is this the reeve's office?");
- mental: an act whose object is placed in the mind ("fix it in my memory",
  "commit the name to memory");
- denied: a clause the player negates ("I don't draw my knife").

A bare future with no later time ("I'll take the crate up") is how many
players write what they do now; it counts as now unless another clause of the
same line is plainly done now, in which case it is the plan after the act.
Where that stays undecided, an optional injected ask (one yes/no question)
can settle it; it is off by default and tests use a fake.

Blanked clauses are replaced with spaces, so offsets into the line still hold.
"""
from __future__ import annotations

import re
from typing import Any, Callable

_AP = "['’]"

# Quoted speech: straight or curly, never across a blank line.
_QUOTE_RE = re.compile(r'"[^"\n]*(?:"|$)|“[^”\n]*(?:”|$)', re.M)
_MASK = "\x01"

# Clause boundaries inside a sentence.
_HARD_STOP_RE = re.compile(r"[.!?;\n]+|:\s|\s[-–—]+\s|—")
_COMMA_RE = re.compile(r",")
_SUBORDINATOR = (
    r"if|unless|once(?!\s+(?:more|again|over))|whether|when|whenever|before|until|till|"
    r"as\s+soon\s+as|in\s+case|so\s+that"
)
_COORDINATOR = r"and\s+then|and|then|but|or|so|while"
_LEAD_RE = re.compile(rf"^\s*(?:(?P<sub>{_SUBORDINATOR})|(?P<co>{_COORDINATOR}))\b", re.I)
# A connector inside a stretch starts a new clause.
_CONNECTOR_RE = re.compile(rf"\s(?=(?:{_SUBORDINATOR}|{_COORDINATOR})\b)", re.I)
_PLAYER_SUBJECT_RE = re.compile(r"\b(?:i|we)\b(?!" + _AP + r"(?:d|ve)\b)", re.I)
_ANY_SUBJECT_START_RE = re.compile(
    r"^\s*(?:i|we|you|he|she|they|it|there|the|a|an|this|that|[A-Z][\w'’-]*)\b"
)

# Moods.
_MODAL_RE = re.compile(
    r"^\s*(?:i|we)\s+(?:would|could|should|might|may|must|can|ought\s+to)\b"
    r"|^\s*(?:i|we)" + _AP + r"d\b(?!\s+(?:better|rather)\b)",
    re.I,
)
_WISH_RE = re.compile(
    r"^\s*(?:i|we)\s+(?:(?:really|still|just)\s+)?(?:plan|planned|intend|intended|mean|meant|hope|hoped|want|wanted|"
    r"wish|wished|would\s+like|" r"am\s+planning|am\s+hoping|am\s+meaning|'m\s+planning|'m\s+hoping)\s+to\b",
    re.I,
)
_FUTURE_RE = re.compile(
    r"^\s*(?:i|we)(?:" + _AP + r"ll|\s+will|\s+shall|\s+am\s+going\s+to|" + _AP + r"m\s+going\s+to|"
    r"\s+are\s+going\s+to|" + _AP + r"re\s+going\s+to|\s+am\s+gonna|" + _AP + r"m\s+gonna)\b",
    re.I,
)
_LATER_RE = re.compile(
    r"\b(?:later|tomorrow|tonight|soon|someday|one\s+day|next\s+\w+|after\s+(?:lunch|dinner|supper|breakfast|dark|dusk|"
    r"this|that|the\s+\w+)|in\s+the\s+morning|at\s+(?:first\s+light|dawn|dusk|sundown|sunset|noon|midnight|low\s+tide|"
    r"high\s+tide)|by\s+(?:dusk|nightfall|morning|tomorrow))\b",
    re.I,
)
_NOW_WORD_RE = re.compile(r"\b(?:now|right\s+away|at\s+once|immediately|straight\s+away|here\s+and\s+now)\b", re.I)
_SUBORDINATE_IN_RE = re.compile(r"\b(?:if|unless|once(?!\s+(?:more|again|over))|whether|in\s+case)\b", re.I)
_QUESTION_LEAD_RE = re.compile(
    r"^\s*(?:is|are|was|were|am|do|does|did|can|could|will|would|should|shall|may|might|have|has|had|"
    r"who|whom|whose|what|where|when|why|how|which)\b",
    re.I,
)
# What follows a word of telling, asking or allowing is the message or the
# other's act: "tell Nell I'll take the matter to the reeve", "ask Rafe to
# hold the skiff", "let me know when it's done".
_REPORTED_RE = re.compile(
    r"\b(?:tell|tells|told|telling|ask|asks|asked|asking|order|orders|ordered|beg|begs|begged|urge|urges|urged|"
    r"remind|reminds|reminded|warn|warns|warned|promise|promises|promised|instruct\w*|"
    r"let|lets|say|says|said|swear|swore|agree|agrees|agreed|offer|offers|offered)\b"
    r"(?:\s+(?!(?:to|that|if|whether|i|we|and|then|but|or|while)\b)[\w'’-]+){0,4}?"
    r"\s+(?=(?:to|that|if|whether|what|where|when|why|how|i|we|i" + _AP + r"ll|we" + _AP + r"ll)\b)",
    re.I,
)
_LET_ME_KNOW_RE = re.compile(r"\blet\s+(?:me|us)\s+(?:know|hear)\b", re.I)
# An act whose object is put in the mind: "fix it in my memory", "commit the name to memory".
_MENTAL_RE = re.compile(
    r"\b(?:fix|set|hold|keep|lock|burn|etch|sear|commit|file|store|carve|press|stamp|engrave|lodge|tuck)\w*"
    r"(?:\s+[\w'’-]+){0,4}?\s+(?:in|into|to|on)\s+(?:(?:my|our|his|her|their|your)\s+)?(?:own\s+)?"
    r"(?:memory|memories|mind|head|heart|thoughts)\b",
    re.I,
)

# A gerund that describes a thing or a time is no act now: "search the hold for
# anything worth hauling back" rolled athletics for "hauling back" (8B run 152e,
# T8). Not "for": "I head out for fishing" is the act.
_GERUND_COMPLEMENT_RE = re.compile(
    r"\b(?:worth|without|instead\s+of|besides|before|after)\s+[\w'’-]+ing\b"
    r"(?:\s+(?:back|up|out|down|off|away|over|in|on|home))?",
    re.I,
)

NOW = "now"
SOFT_FUTURE = "soft_future"

NowAsk = Callable[[str, str], "bool | None"]
_now_ask: NowAsk | None = None


def set_now_ask(fn: NowAsk | None) -> None:
    """Install (or remove) the one-question ask for an undecided future.

    fn(line, clause) -> True (doing it now), False (not now) or None (no answer).
    Off by default; the question is NOW_QUESTION.
    """
    global _now_ask
    _now_ask = fn


NOW_QUESTION = "Is the player doing this now? Answer yes or no."


def _negated_spans(masked: str) -> list[tuple[int, int]]:
    try:
        from app.prose_state import _NEGATED_CLAUSE_RE
    except Exception:
        return []
    return [(m.start(), m.end()) for m in _NEGATED_CLAUSE_RE.finditer(masked)]


def _mask_speech(text: str) -> str:
    return _QUOTE_RE.sub(lambda m: _MASK * len(m.group(0)), text)


def _stretches(masked: str) -> list[tuple[int, int, bool]]:
    """(start, end, is_question) for each stretch between hard stops and commas."""
    out: list[tuple[int, int, bool]] = []
    pos = 0
    for stop in list(_HARD_STOP_RE.finditer(masked)) + [None]:
        end = stop.start() if stop else len(masked)
        sentence_q = bool(stop and "?" in stop.group(0))
        seg_start = pos
        for comma in list(_COMMA_RE.finditer(masked, pos, end)) + [None]:
            seg_end = comma.start() if comma else end
            out.append((seg_start, seg_end, sentence_q))
            seg_start = (comma.end() if comma else end)
        pos = stop.end() if stop else len(masked)
    return out


def _sentence_around(masked: str, start: int, end: int) -> str:
    """The whole sentence a comma-stretch sits in (stops, not commas)."""
    left = max(masked.rfind(ch, 0, start) for ch in ".!?;\n")
    stops = [i for i in (masked.find(ch, end) for ch in ".!?;\n") if i >= 0]
    return masked[left + 1: min(stops) if stops else len(masked)]


def _split_connectors(masked: str, start: int, end: int) -> list[tuple[int, int]]:
    cuts = [start]
    for m in _CONNECTOR_RE.finditer(masked, start, end):
        if m.end() > start + 1:
            cuts.append(m.end())
    cuts.append(end)
    return [(a, b) for a, b in zip(cuts, cuts[1:]) if b > a]


def _split_subordinate(masked: str, start: int, end: int) -> list[tuple[int, int]]:
    """A clause led by when/if/until runs to the main clause's own "I":
    "When the reef comes in sight I ask Rafe" is two clauses."""
    piece = masked[start:end]
    lead = _LEAD_RE.match(piece)
    if not lead or not lead.group("sub"):
        return [(start, end)]
    rest_at = lead.end()
    subjects = list(_PLAYER_SUBJECT_RE.finditer(piece, rest_at))
    if subjects and not piece[rest_at: subjects[0].start()].strip():
        subjects = subjects[1:]  # "until I find him": the clause's own subject
    if not subjects:
        return [(start, end)]
    cut = start + subjects[0].start()
    return [(start, cut), (cut, end)]


def read_clauses(line: str) -> list[dict[str, Any]]:
    """Each clause of the player's own line with its mood.

    [{"start", "end", "text", "mood"}], mood one of now, soft_future, plan,
    condition, reported, question, mental, denied, speech.
    """
    text = str(line or "")
    masked = _mask_speech(text)
    clauses: list[dict[str, Any]] = []
    for s_start, s_end, is_q in _stretches(masked):
        main_mood = NOW
        for c_start, c_end in _split_connectors(masked, s_start, s_end):
            for a, b in _split_subordinate(masked, c_start, c_end):
                body = masked[a:b]
                if not body.strip(" \t" + _MASK):
                    if _MASK in body:
                        clauses.append({"start": a, "end": b, "text": text[a:b], "mood": "speech"})
                    continue
                lead = _LEAD_RE.match(body)
                core = body[lead.end():] if lead else body
                fresh_subject = bool(_ANY_SUBJECT_START_RE.match(core.replace(_MASK, " ").lstrip()))
                if lead and lead.group("sub"):
                    mood = "condition"
                elif is_q and _QUESTION_LEAD_RE.match(core.replace(_MASK, " ")):
                    mood = "question"
                elif _MODAL_RE.match(core) or _WISH_RE.match(core):
                    mood = "plan"
                elif _FUTURE_RE.match(core):
                    sentence = _sentence_around(masked, s_start, s_end)
                    if _NOW_WORD_RE.search(core):
                        mood = NOW  # "I'll pay the three gold now"
                    elif _LATER_RE.search(sentence) or _SUBORDINATE_IN_RE.search(sentence):
                        # A later time, or a case it waits on ("If the guard sees me I'll run").
                        mood = "plan"
                    else:
                        mood = SOFT_FUTURE
                elif lead and lead.group("co") and not fresh_subject:
                    mood = main_mood  # "I'll go down and ask him": the ask shares the future
                else:
                    mood = NOW
                if mood != "condition":
                    main_mood = mood
                clauses.append({"start": a, "end": b, "text": text[a:b], "mood": mood})
    return clauses


def _blank(chars: list[str], start: int, end: int, keep_speech: bool, masked: str) -> None:
    for i in range(max(0, start), min(len(chars), end)):
        if keep_speech and masked[i] == _MASK:
            continue
        if chars[i] != "\n":
            chars[i] = " "


def acts_now(
    line: str,
    *,
    keep_speech: bool = False,
    keep_questions: bool = False,
    ask: NowAsk | None = None,
) -> str:
    """The player's line with every clause that is not done now blanked out.

    keep_speech=True keeps the quoted words (for readers that judge talk);
    otherwise speech is blanked too. keep_questions=True keeps a narrated
    question (the dice: "what is the ring worth?" is an appraisal asked).
    Offsets into the line are preserved.
    """
    text = str(line or "")
    if not text.strip():
        return text
    masked = _mask_speech(text)
    chars = list(text)
    clauses = read_clauses(text)
    any_now = any(c["mood"] == NOW and re.search(r"[a-z]{2,}", c["text"], re.I) for c in clauses)
    asker = ask if ask is not None else _now_ask
    for clause in clauses:
        mood = clause["mood"]
        if mood == "speech":
            if not keep_speech:
                _blank(chars, clause["start"], clause["end"], False, masked)
            continue
        if mood == SOFT_FUTURE:
            if any_now:
                mood = "plan"
            elif asker is not None:
                try:
                    answer = asker(text, clause["text"])
                except Exception:
                    answer = None
                if answer is False:
                    mood = "plan"
        if mood == "question" and keep_questions:
            continue
        if mood not in {NOW, SOFT_FUTURE}:
            _blank(chars, clause["start"], clause["end"], keep_speech, masked)
    out = "".join(chars)
    masked_out = "".join(_MASK if masked[i] == _MASK else ch for i, ch in enumerate(out))
    # Inside the kept clauses: the reported tail, "let me know", the mental act, the denied clause.
    spans: list[tuple[int, int]] = []
    for m in _REPORTED_RE.finditer(masked_out):
        tail_end = _clause_end(masked_out, m.end())
        spans.append((m.end(), tail_end))
    for m in _LET_ME_KNOW_RE.finditer(masked_out):
        spans.append((m.start(), _clause_end(masked_out, m.start())))
    for m in _MENTAL_RE.finditer(masked_out):
        spans.append((m.start(), m.end()))
    for m in _GERUND_COMPLEMENT_RE.finditer(masked_out):
        spans.append((m.start(), m.end()))
    spans.extend(_negated_spans(masked_out))
    chars = list(out)
    for start, end in spans:
        _blank(chars, start, end, keep_speech, masked)
    if not keep_speech:
        # Speech inside a clause that is also narrated is still said, not done.
        for i, ch in enumerate(masked):
            if ch == _MASK and chars[i] != "\n":
                chars[i] = " "
    return "".join(chars)


def _clause_end(masked: str, at: int) -> int:
    """Where the clause that starts at `at` ends: a stop, a comma, or a fresh
    "and I" / "then I" that takes the act back."""
    stop = re.compile(r"[.!?;,\n]|\s(?:and|then|but)\s+(?:then\s+)?(?:i|we)\b(?!" + _AP + r"ll)", re.I).search(masked, at)
    return stop.start() if stop else len(masked)


def is_all_speech(line: str) -> bool:
    """True when the line has quoted words and nothing narrated outside them."""
    text = str(line or "")
    return bool(_QUOTE_RE.search(text)) and not re.search(r"[a-z]{2,}", _mask_speech(text).replace(_MASK, " "), re.I)
