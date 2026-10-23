"""Scene drift: the story is told where the player is.

Stell (2026-10-24): "the story should be told where the player is, fix the drift". On recorded drift
turns (drift eval, combined live replay T4 "i search the dead ghoul" in the subway tunnel came back "In
the dim glow of the clinic's emergency lanterns ... The clinic's medic ... watches you") a fact in the
draft's packet alone moved clear drift only 7/36 -> 4/36.

Engine first: app/where_ended.py already asks, on every player turn, where the prose leaves the player,
and checks the answer with "are you still in <here>?" (live: 0 wrong moves in 72). When that checked
answer is somewhere other than the player's place AND the player's line is clearly a staying act (the
turn's own intent reading is combat, trade, conversation, investigation or an item in hand, with no
movement read at all: world.line_stays_here), the scene drifted: an unasked move is offered, not made
(#46, #76). Any other line (a way of going the keywords miss, rest, anything unread) is left alone: a
missed re-draft only keeps the draft, a wrong one would take the player's move away. The engine then sends ONE re-draft of the turn through the same draft pipeline with one
short correction passed on as instruction, and asks where_ended again:

* the re-draft stays here (checked): it is kept;
* it still drifts, or its answer is unclear: the first draft is kept, and the ledger says so.

The narrator's normal prompt is unchanged; the correction rides only on the re-draft. One re-draft per
turn at most. Every ask goes through the turn's usage and trace (phases ``where_ended`` and the draft's
own), the decision is a ``scene_drift`` trace record and a ledger note, and the re-draft is marked in
model_usage (phase ``scene_drift_redraft``). Nothing here writes the save.
AI_RPG_SCENE_DRIFT=0|off turns the re-draft off (where_ended still asks).
"""
from __future__ import annotations

import os
from typing import Any, Callable

from app import turn_ledger

PHASE = "scene_drift"


def enabled() -> bool:
    raw = str(os.environ.get("AI_RPG_SCENE_DRIFT", "") or "").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def correction(here_name: str) -> str:
    """The one line the re-draft carries."""
    return f"The player is still in {here_name}; the scene stays there."


def _choice(record: Any) -> dict[str, Any]:
    return record.get("choice") if isinstance(record, dict) and isinstance(record.get("choice"), dict) else {}


def stays(record: Any) -> bool:
    """where_ended's checked answer is the place the player is in."""
    return isinstance(record, dict) and record.get("confirmed") is True and _choice(record).get("kind") == "here"


def ends_elsewhere(record: Any) -> bool:
    """where_ended's checked answer is somewhere other than the place the player is in."""
    return isinstance(record, dict) and record.get("confirmed") is True and _choice(record).get("kind") not in {None, "here"}


def _narration_of(turn: Any) -> str:
    """The prose the way play_turn reads it, so its reuse of the answer compares like with like."""
    if not isinstance(turn, dict):
        return ""
    from app.world import _narration_text_of

    return _narration_text_of(turn)


def _ask(turn: dict[str, Any], player_input: str) -> dict[str, Any] | None:
    from app import where_ended
    from app.db import connect

    text = _narration_of(turn)
    with connect().closing() as conn:
        record = where_ended.ask_where(conn, turn, player_input, text)
    if isinstance(record, dict):
        # play_turn reuses the answer when the prose it acts on is this one.
        record["text"] = text
    return record


def _stays_here(player_input: str) -> bool:
    from app.db import connect
    from app.world import line_stays_here

    with connect().closing() as conn:
        return line_stays_here(conn, player_input)


def check(
    turn: Any,
    player_input: str,
    redraft: Callable[[str], Any],
    *,
    usage: list[dict[str, Any]] | None = None,
    trace: list[dict[str, Any]] | None = None,
) -> Any:
    """Ask where the draft ends; on drift, re-draft once with the correction and keep the better draft."""
    if not isinstance(turn, dict) or not enabled():
        return turn
    from app.turn_dsl import player_line_of

    # The player's own line, without the engine's notes after it (forced
    # events, ability blocks): those are not the player asking to go.
    player_input = player_line_of(player_input)
    if not player_input:
        return turn
    try:
        first = _ask(turn, player_input)
    except Exception as exc:
        turn_ledger.note("movement", "scene_drift_check_failed", error=f"{type(exc).__name__}: {exc}"[:200])
        return turn
    if not ends_elsewhere(first):
        return turn
    answer = str(_choice(first).get("label") or "")
    try:
        staying = _stays_here(player_input)
    except Exception:
        staying = False  # unsure: the move rules decide, as before
    if not staying:
        return turn
    options = first.get("options") or []
    here_name = str((options[0] if options else {}).get("name") or "").strip()
    if not here_name:
        return turn
    note = correction(here_name)
    record: dict[str, Any] = {"phase": PHASE, "event": "redraft", "correction": note, "first_answer": answer,
                              "here": here_name}
    if isinstance(usage, list):
        usage.append({"phase": "scene_drift_redraft", "chars": len(note), "estimated_tokens": max(1, len(note) // 4)})
    try:
        second = redraft(note)
    except Exception as exc:
        record.update(event="redraft_failed", error=f"{type(exc).__name__}: {exc}"[:300], kept="first")
        _trace(trace, record)
        turn_ledger.note("movement", "scene_drift_redraft_failed", answer=answer, error=record["error"])
        return turn
    second_record = None
    if isinstance(second, dict):
        try:
            second_record = _ask(second, player_input)
        except Exception as exc:
            record["second_error"] = f"{type(exc).__name__}: {exc}"[:200]
    record["second_answer"] = str(_choice(second_record).get("label") or "unclear")
    record["second_confirmed"] = (second_record or {}).get("confirmed") if isinstance(second_record, dict) else None
    if isinstance(second, dict) and stays(second_record):
        record["kept"] = "redraft"
        _trace(trace, record)
        turn_ledger.note("movement", "scene_drift_redrafted", answer=answer, here=here_name, kept="redraft")
        return second
    record["kept"] = "first"
    _trace(trace, record)
    turn_ledger.note("movement", "scene_drift_kept_first", answer=answer, here=here_name,
                     second=record["second_answer"], why="the re-draft did not stay here either")
    return turn


def _trace(trace: list[dict[str, Any]] | None, record: dict[str, Any]) -> None:
    if isinstance(trace, list):
        try:
            from app.llm import _append_trace

            _append_trace(trace, record)
        except Exception:
            trace.append(record)
