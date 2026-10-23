"""The turn checker: the engine's own questions about a finished scene, one at a time.

Playtest #157 (b) and #77 (2026-10-23, Hermes 3 8B, cc87dd29). The verifier
used to get the whole world state and the draft and was asked for one broad
verdict, a list of issues and a patch of any turn key. The 8B filled the
verdict with rules that do not exist (T5: 'no killing', 'no magic', 'no new
people' ... and passed), flagged a laser rifle the player's own line names
(T8/T9) and, in T9, patched the scene so the player's shot became a punch,
saying so in its own issues and passing anyway. CLAUDE.md (2026-10-17): a task
the model keeps failing is too hard, so make it simpler.

What the verifier was still needed for, once the engine's own gates are
counted (codes and names, scene plan, state deltas, item grants, moves, money
and dice are all decided by engine code before or after it):

  * whether the scene shows the player doing what their line says. Nothing
    else in the engine can decide that; prose_state.act_handed_off only
    measures one shape of it.

So that is the one question asked today. It is a fixed question with its fact
in it (the player's line), answered yes or no. Every other question the broad
verdict touched is either the engine's (and an engine gate decides it) or has
no fact the engine can hand over, and is not asked. A new question joins
QUESTIONS only with the record it is about, and the engine acts on its answer.

The answer is acted on, not listed:
  * yes: nothing changes.
  * no: one small ask picks the sentence that should show the act (a number
    from a numbered list), and one small ask rewrites only that sentence so the
    player does what they wrote. The rest of the scene stays as written. The
    checker can never write the player's act into something else: the only
    prose it changes is toward the player's own line.

``passed`` is true only when every question asked got a usable answer and
every "no" was repaired. Nothing here writes a rule, a verdict in the model's
words, or a patch of any state key.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from app import turn_ledger

# ask(system_prompt, user_prompt, phase, max_tokens) -> raw reply text.
# The caller (app/llm.py) routes it through _chat_text, so the prompt, the raw
# reply and the seconds land in the turn's trace and model_usage.
Ask = Callable[[str, str, str, int], str]

ASK_SYSTEM = "Reply with the answer only."

# The phases the asks are recorded under (model_usage, trace, timings).
PHASE_ACT = "check_act"
PHASE_PICK = "check_act_pick"
PHASE_REWRITE = "check_act_rewrite"

QUESTIONS = ("player_act",)

_CODE_RE = re.compile(r"\s*\[\[[A-Za-z0-9_]{1,12}\]\]")
# "Beth [[B]]" / "Doc Beth [[B]]": the name a code tag follows, for putting
# the tag back after a rewrite that was asked without codes.
_NAMED_CODE_RE = re.compile(r"((?:[A-Z][\w'’-]*)(?:\s+[A-Z][\w'’-]*){0,3})\s*(\[\[[A-Za-z0-9_]{1,12}\]\])")
_MAX_SENTENCES = 40


def plain(text: Any) -> str:
    """Text without [[CODE]] tags, for a question the model reads."""
    return re.sub(r"[ \t]{2,}", " ", _CODE_RE.sub("", str(text or ""))).strip()


def act_question(line: str, scene: str) -> str:
    return (
        f'The player wrote: "{line}"\n\n'
        f'Scene (it calls the player "you"):\n{scene}\n\n'
        "Does the scene show the player trying what they wrote? Answer yes or no."
    )


def pick_question(line: str, sentences: list[str]) -> str:
    numbered = "\n".join(f"{index}. {sentence}" for index, sentence in enumerate(sentences, 1))
    return (
        f'The player wrote: "{line}"\n\n'
        f"Sentences:\n{numbered}\n\n"
        "Which sentence should show the player doing what they wrote? Answer with its number."
    )


def rewrite_question(line: str, sentence: str) -> str:
    return (
        f'The player wrote: "{line}"\n\n'
        f"Sentence: {sentence}\n\n"
        "Rewrite this sentence so the player does what they wrote. Change as little as you can. "
        "Reply with the sentence only."
    )


def yes_no(reply: Any) -> str:
    """'yes', 'no' or '' from a reply's first word."""
    match = re.match(r"\W*(yes|no)\b", str(reply or ""), re.I)
    return match.group(1).lower() if match else ""


def sentence_number(reply: Any, count: int) -> int:
    """The 1-based number the reply names, or 0 when it names none in range."""
    match = re.search(r"\d+", str(reply or ""))
    if not match:
        return 0
    number = int(match.group(0))
    return number if 1 <= number <= count else 0


def clean_rewrite(reply: Any, original: str) -> str:
    """The rewritten sentence, or '' when the reply is not one usable sentence."""
    text = str(reply or "").strip()
    text = re.sub(r"^(?:sentence|rewritten(?: sentence)?|new sentence)\s*:\s*", "", text, flags=re.I)
    text = text.split("\n\n", 1)[0].strip()
    if len(text) >= 2 and text[0] in "\"“" and text[-1] in "\"”" and text.count('"') + text.count("“") + text.count("”") == 2:
        text = text[1:-1].strip()
    if not text or "\n" in text:
        return ""
    base = plain(original)
    if len(text) > max(2 * len(base), len(base) + 160):
        return ""
    if text == base:
        return ""
    return text


def retag(rewrite: str, original: str) -> str:
    """Put back each 'Name [[X]]' tag the original sentence had, after the name's first use."""
    out = rewrite
    for match in _NAMED_CODE_RE.finditer(original):
        name, tag = match.group(1).strip(), match.group(2)
        if tag in out:
            continue
        found = re.search(rf"\b{re.escape(name)}\b(?!\s*\[\[)", out)
        if found:
            out = out[: found.end()] + f" {tag}" + out[found.end():]
    return out


def _narration(turn: dict[str, Any]) -> str:
    text = str(turn.get("narration") or "").strip()
    if text:
        return text
    segments = turn.get("narration_segments") or []
    if isinstance(segments, list):
        return "\n\n".join(str(seg.get("text") or "").strip() for seg in segments if isinstance(seg, dict) and str(seg.get("text") or "").strip())
    return ""


_SHORT_TITLE_END_RE = re.compile(r"(?:^|\s)[A-Z][a-z]{0,2}\.$")


def _sentences(text: str) -> list[tuple[int, int, str]]:
    """prose_state.sentence_spans, with a split after a short title ("Dr. Beth", T13) joined back."""
    from app.prose_state import sentence_spans

    out: list[tuple[int, int, str]] = []
    for start, end, sentence in sentence_spans(text):
        if out and _SHORT_TITLE_END_RE.search(out[-1][2]) and text[out[-1][1]:start].strip() == "":
            prev_start = out[-1][0]
            out[-1] = (prev_start, end, text[prev_start:end])
            continue
        out.append((start, end, sentence))
    return out


def _set_narration(turn: dict[str, Any], text: str) -> None:
    turn["narration"] = text
    paragraphs = [para.strip() for para in re.split(r"\n\s*\n", text) if para.strip()]
    turn["narration_segments"] = [{"label": "paragraph", "text": para} for para in paragraphs]


def _ask(ask: Ask, user: str, phase: str, max_tokens: int, record: dict[str, Any]) -> str | None:
    try:
        return str(ask(ASK_SYSTEM, user, phase, max_tokens) or "")
    except Exception as exc:  # a failed ask is "not checked", never a lost turn
        record.setdefault("errors", []).append(f"{phase}: {type(exc).__name__}: {exc}"[:240])
        turn_ledger.note("verify", "check_ask_failed", phase=phase, error=f"{type(exc).__name__}: {exc}"[:200])
        return None


def _repair_act(turn: dict[str, Any], line: str, ask: Ask, record: dict[str, Any]) -> bool:
    """One sentence rewritten toward the player's line. True when the scene was changed."""
    narration = _narration(turn)
    spans = _sentences(narration)[:_MAX_SENTENCES]
    if not spans:
        record["repair"] = "no_sentences"
        return False
    reply = _ask(ask, pick_question(line, [plain(s) for _a, _b, s in spans]), PHASE_PICK, 8, record)
    if reply is None:
        record["repair"] = "pick_failed"
        return False
    record["pick_reply"] = reply[:80]
    number = sentence_number(reply, len(spans))
    if not number:
        record["repair"] = "pick_unreadable"
        return False
    start, end, sentence = spans[number - 1]
    reply = _ask(ask, rewrite_question(line, plain(sentence)), PHASE_REWRITE, 200, record)
    if reply is None:
        record["repair"] = "rewrite_failed"
        return False
    rewrite = clean_rewrite(reply, sentence)
    if not rewrite:
        record["repair"] = "rewrite_unusable"
        record["rewrite_reply"] = reply[:300]
        return False
    rewrite = retag(rewrite, sentence)
    _set_narration(turn, narration[:start] + rewrite + narration[end:])
    record.update(repair="rewrote_sentence", sentence_number=number, before=sentence[:400], after=rewrite[:400])
    turn_ledger.note("verify", "player_act_sentence_rewritten", before=sentence[:200], after=rewrite[:200], line=line[:160])
    return True


def check_turn(
    turn: dict[str, Any],
    player_line: str,
    ask: Ask,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Ask the fixed questions about ``turn``, act on the answers, write self_check.

    Returns (turn, report). report["usable"] is False when an ask was made and
    no usable answer came back (the caller counts that toward the verifier
    breaker); report["checks"] holds one record per question asked.
    """
    result = dict(turn)
    line = plain(player_line)
    checks: list[dict[str, Any]] = []
    corrections: list[str] = []
    issues: list[str] = []
    narration = _narration(result)
    if line and narration:
        record: dict[str, Any] = {"question": "player_act", "line": line[:300]}
        reply = _ask(ask, act_question(line, plain(narration)), PHASE_ACT, 8, record)
        answer = yes_no(reply) if reply is not None else ""
        record["answer"] = answer or ("error" if reply is None else "unreadable")
        if reply is not None:
            record["reply"] = reply[:80]
        if answer == "yes":
            record["ok"] = True
        elif answer == "no":
            record["ok"] = _repair_act(result, line, ask, record)
            if record["ok"]:
                corrections.append(f"Rewrote sentence {record['sentence_number']} so the player does what their line says.")
            else:
                issues.append(f'The scene does not show the player\'s act as written: "{line[:160]}".')
                turn_ledger.note("verify", "player_act_not_shown", line=line[:160], repair=record.get("repair"))
        else:
            record["ok"] = False
            issues.append("Not checked: the question about the player's act got no usable answer.")
        checks.append(record)
    asked = [c["question"] for c in checks]
    passed = all(c.get("ok") for c in checks)
    usable = all(c.get("answer") in {"yes", "no"} for c in checks)
    previous = result.get("self_check") if isinstance(result.get("self_check"), dict) else {}
    earlier = [str(c) for c in previous.get("corrections_made") or [] if str(c).strip()]
    answers = ", ".join(f"{c['question']}={c['answer']}" for c in checks)
    result["self_check"] = {
        "passed": passed,
        "issues_found": issues[:8],
        "corrections_made": [*earlier, *corrections][:8],
        "reference_check": f"Engine questions: {answers}." if checks else "No engine question applied to this turn.",
        "consistency_check": (
            "Every question answered and acted on." if passed else "A question was not answered, or its answer could not be acted on."
        ),
    }
    return result, {"checks": checks, "asked": asked, "passed": passed, "usable": usable}
