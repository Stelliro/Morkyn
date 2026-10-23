"""Small yes/no asks that settle whose words and choices the prose shows (#30, #29).

The engine finds each candidate by structure (a quote with "you" right beside
it, a "You:" script line, a narrator question with an "or" in it followed by
a "you" sentence, a paragraph that shares much of an earlier one, a dropped
player act with an answer after it). One plain question per candidate goes to
the model; the engine acts on the answer. No word list decides what a
sentence means.

Every ask goes through app.llm._chat_text (the caller injects it), so its
prompt, raw reply and time are in the turn trace and model_usage like any
other call. An unclear or failed reply is None, and the caller then keeps the
old behaviour.
"""
from __future__ import annotations

import re
from typing import Any, Callable

ASK_SYSTEM = "You answer one question about a short piece of a story. Reply with one word: yes or no."
ASK_MAX_TOKENS = 8
PHASE_PREFIX = "agency_ask"

Chat = Callable[[str, str, str], str]

_CODE_RE = re.compile(r"\s*\[\[[A-Za-z0-9]{1,4}\]\]")
_YES_RE = re.compile(r"^\W*(yes|no)\b", re.I)


def plain(text: str, limit: int = 600) -> str:
    """Engine codes out, spaces folded, cut at a word."""
    out = " ".join(_CODE_RE.sub("", str(text or "")).split())
    if len(out) > limit:
        out = out[:limit].rsplit(" ", 1)[0] + " ..."
    return out


def parse_yes_no(raw: Any) -> bool | None:
    match = _YES_RE.match(str(raw or ""))
    if not match:
        return None
    return match.group(1).lower() == "yes"


# The questions. One question each, the fewest plain words.
def speaks_question(sentence: str) -> str:
    return (
        'In this story, "you" is the player.\n'
        f"Sentence: {plain(sentence)}\n"
        "Does the player say the words in quotes? Answer yes or no."
    )


def voices_question(chosen: str, line: str) -> str:
    return (
        f"The player chose to: {plain(chosen, 300)}\n"
        f'The story has the player say: "{plain(line, 300)}"\n'
        "Is that what the player chose to say? Answer yes or no."
    )


def choice_question(question: str, sentence: str) -> str:
    return (
        f"The story asks the player: {plain(question, 300)}\n"
        f"Then it says: {plain(sentence, 300)}\n"
        "Does that sentence make the choice for the player? Answer yes or no."
    )


def retell_question(earlier: str, later: str) -> str:
    return (
        f"Passage 1: {plain(earlier)}\n"
        f"Passage 2: {plain(later)}\n"
        "Does passage 2 tell the same events as passage 1 again? Answer yes or no."
    )


def reply_question(act: str, after: str) -> str:
    return (
        f"The player did not do this: {plain(act, 300)}\n"
        f"Next in the story: {plain(after, 400)}\n"
        "Is the next part a reply to what the player did not do? Answer yes or no."
    )


class AgencyAsks:
    """The turn's yes/no asks, each asked once per text (a memo per turn)."""

    def __init__(self, chat: Chat | None):
        self.chat = chat
        self.memo: dict[tuple[str, str], bool | None] = {}
        self.log: list[dict[str, Any]] = []

    def ask(self, kind: str, user: str) -> bool | None:
        key = (kind, user)
        if key in self.memo:
            return self.memo[key]
        answer: bool | None = None
        raw = ""
        error = ""
        if self.chat is not None:
            try:
                raw = str(self.chat(ASK_SYSTEM, user, f"{PHASE_PREFIX}_{kind}") or "")
                answer = parse_yes_no(raw)
            except Exception as exc:  # model down or timed out: the old rule stands
                error = f"{exc.__class__.__name__}: {exc}"[:200]
        self.memo[key] = answer
        entry = {"kind": kind, "answer": answer, "reply": raw[:80]}
        if error:
            entry["error"] = error
        self.log.append(entry)
        try:
            from app import turn_ledger

            turn_ledger.note("player_words", "agency_ask", kind=kind, answer=answer, reply=raw[:40], error=error)
        except Exception:
            pass
        return answer

    def speaks(self, sentence: str) -> bool | None:
        return self.ask("speaks", speaks_question(sentence))

    def voices(self, chosen: str, line: str) -> bool | None:
        return self.ask("voices", voices_question(chosen, line))

    def makes_choice(self, question: str, sentence: str) -> bool | None:
        return self.ask("choice", choice_question(question, sentence))

    def retells(self, earlier: str, later: str) -> bool | None:
        return self.ask("retell", retell_question(earlier, later))

    def replies_to(self, act: str, after: str) -> bool | None:
        return self.ask("reply", reply_question(act, after))


# --- Structure: where a candidate is -----------------------------------------

# "you" right beside a quotation, as the subject of the clause that carries it:
# '"You're not the enemy," you confirm' and 'You lean in, "..."'. Any verb: the
# ask decides whether the player is the one speaking.
_YOU_AFTER_QUOTE_RE = re.compile(r"[\"”]\s*,?\s*you\s+(?:[a-z]+ly\s+)?[a-z]+\b")
_YOU_BEFORE_QUOTE_RE = re.compile(r"(?:^|[.!?]\s+|,\s+)you\s+(?:[\w'’]+\s+){0,4}?[\w'’]+\s*[,:]\s*[\"“]", re.I)


def you_beside_quote(unit: str) -> bool:
    return bool(_YOU_AFTER_QUOTE_RE.search(unit) or _YOU_BEFORE_QUOTE_RE.search(unit))


# A script line: 'You: i shoot Marisol [[A]]' (baseline replay T2).
def script_label_re(names: list[str] | tuple[str, ...] = ()) -> re.Pattern[str]:
    forms = ["You", "Player", *[re.escape(str(n)) for n in names if len(str(n or "").strip()) >= 2]]
    return re.compile(r"^[ \t]*(?:" + "|".join(forms) + r")[ \t]*:[ \t]*(?P<line>\S[^\n]*)$", re.M)


_QUOTED_RE = re.compile(r'"[^"\n]*"|“[^”\n]*”')
# Sentence ends: . ! ? (and closing quotes), never after a title like "Dr."
# (see narration_pipeline.NOT_AFTER_TITLE).


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    from app.narration_pipeline import UNIT_SPLIT_RE

    spans: list[tuple[int, int]] = []
    pos = 0
    pending_start = None
    for m in list(UNIT_SPLIT_RE.finditer(text)) + [None]:
        end = m.start() if m else len(text)
        start = pos if pending_start is None else pending_start
        piece = text[start:end]
        if piece.strip():
            marks = sum(piece.count(q) for q in ('"', "“", "”"))
            if marks % 2 and m is not None:
                pending_start = start  # a quotation runs on over sentences
                pos = m.end()
                continue
            spans.append((start, end))
        pending_start = None
        pos = m.end() if m else len(text)
    return spans


def choice_taken_cut(text: str, asks: AgencyAsks, *, floor: int = 200, look_ahead: int = 3) -> dict[str, Any] | None:
    """Where the prose goes on to make a choice it put to the player.

    Candidate: a narrator question outside quotes with an "or" in it, then one
    of the next sentences with "you" in it outside quotes. The ask says
    whether that sentence makes the choice; on yes the scene ends before it.
    """
    spans = _sentence_spans(text)
    for index, (start, end) in enumerate(spans):
        sentence = text[start:end].strip()
        outside = _QUOTED_RE.sub(" ", sentence)
        if '"' in sentence or "“" in sentence or not outside.rstrip().endswith("?"):
            continue
        if not re.search(r"\bor\b", outside, re.I):
            continue
        for later_start, later_end in spans[index + 1 : index + 1 + look_ahead]:
            later = text[later_start:later_end].strip()
            later_outside = _QUOTED_RE.sub(" ", later)
            if not re.search(r"\byou\b", later_outside, re.I) or later_outside.rstrip().endswith("?"):
                continue
            if later_start < floor:
                break
            if asks.makes_choice(sentence, later):
                return {"cut": later_start, "question": sentence, "sentence": later}
        # Only the first choice put to the player is judged.
        return None
    return None


def reply_to_dropped_act_cut(
    before: str, after: str, dropped: list[str], asks: AgencyAsks, *, floor: int = 200
) -> dict[str, Any] | None:
    """Where the kept prose answers a player act the engine dropped as invented.

    Candidate: the first dropped act with a quoted line in what followed it.
    The ask says whether what followed is a reply to it; on yes the scene ends
    where the act stood (the kept text up to the sentence that came after it).
    """
    for act in dropped:
        act = str(act or "").strip()
        at = before.find(act) if act else -1
        if at < 0:
            continue
        rest = before[at + len(act):]
        # The first kept sentence after the act, found in the kept text.
        following = [s for s in (rest[a:b].strip() for a, b in _sentence_spans(rest)) if s and s not in dropped]
        if not following:
            continue
        nxt = following[0]
        where = after.find(nxt)
        if where < 0:
            continue
        window = " ".join(following[:3])
        if not _QUOTED_RE.search(window):
            continue
        if len(after[:where].strip()) < floor:
            return None
        if asks.replies_to(act, window):
            return {"cut": where, "act": act, "reply": window}
        return None
    return None


RETELL_MIN_SHARED = 5
RETELL_MIN_SHARE = 0.35
RETELL_SENTENCE_SHARE = 0.4


def drop_retold_paragraphs(paragraphs: list[str], asks: AgencyAsks) -> tuple[list[str], list[str]]:
    """A paragraph that tells an earlier paragraph's events again (#29, cc87dd29 T2).

    Candidate: a later paragraph whose content words are much of an earlier
    one's. The ask says whether it retells it; on yes the sentences of the
    later paragraph that are mostly the earlier one's go, and any sentence with
    something new stays. Returns (paragraphs, dropped) with the input's length.
    """
    from app.narration_pipeline import content_stems, speech_units

    out = [str(p or "") for p in paragraphs]
    stems = [content_stems(p) for p in out]
    dropped: list[str] = []
    for j in range(1, len(out)):
        later = stems[j]
        if not later:
            continue
        for i in range(j):
            earlier = stems[i]
            shared = later & earlier
            if len(shared) < RETELL_MIN_SHARED or len(shared) < RETELL_MIN_SHARE * len(later):
                continue
            if not asks.retells(out[i], out[j]):
                continue
            kept: list[str] = []
            gone: list[str] = []
            for unit in speech_units(out[j]):
                unit_stems = content_stems(unit)
                if unit_stems and len(unit_stems & earlier) >= RETELL_SENTENCE_SHARE * len(unit_stems):
                    gone.append(unit)
                else:
                    kept.append(unit)
            if gone:
                dropped.extend(gone)
                out[j] = " ".join(kept).strip()
                stems[j] = content_stems(out[j])
            break
    if dropped and not any(p.strip() for p in out):
        return list(paragraphs), []
    return out, dropped


# --- An opening quote with no close in its paragraph (#29, cc87dd29 T14) -----

def close_open_quotes(paragraph: str) -> tuple[str, int]:
    """Give an unclosed straight quotation its closing mark.

    The marks are read in pairs from the start. Where a line stops and the
    narration starts is read from the text: a ! ? or . inside a quotation with
    a lower-case word after it ('"Hey! calls out a woman') is the end of the
    line, and its tag starts there; a pair that swallows a tag that way is the
    fault even when the paragraph's count is even. A last opener with no such
    point closes at the paragraph's end. Only straight quotes.
    """
    text = str(paragraph or "")
    fixes = 0
    for _ in range(4):
        marks = [m.start() for m in re.finditer('"', text)]
        changed = False
        for k in range(0, len(marks), 2):
            opener = marks[k]
            closer = marks[k + 1] if k + 1 < len(marks) else None
            inside = text[opener + 1 : closer if closer is not None else len(text)]
            stop = _LINE_STOP_RE.search(inside)
            if stop:
                at = opener + 1 + stop.end()
                text = text[:at] + '"' + text[at:]
                changed = True
                break
            if closer is None:
                # A lone mark at the very end is a closer whose opener is lost;
                # where the line began cannot be read, so it is left alone.
                if inside.strip():
                    text = text.rstrip() + '"'
                    changed = True
                break
        if not changed:
            break
        fixes += 1
    return text, fixes


# A stop that ends a spoken line: one ! ? or . (never an ellipsis) and then a
# lower-case word, which no line of speech goes on with.
_LINE_STOP_RE = re.compile(r"(?<![.!?])[!?.](?![.!?])(?=\s+[a-z])")
