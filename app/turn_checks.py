"""The turn checks that replace the broad verifier: the engine's own, no model ask.

Playtest #157 (b) and #77 (2026-10-23, Hermes 3 8B, cc87dd29). The verifier
got the whole world state and the draft and was asked for one broad verdict,
a list of issues and a patch of any turn key. The 8B filled the verdict with
rules that do not exist (T5: 'no killing', 'no magic' ... and passed), flagged
a laser rifle the player's own line names (T8/T9) and in T9 patched the
player's shot into a punch. Its other patches in the baseline replay
(974c9d69 T1-T6: narration, player, quest_marks, scene_cast, scene_plan, npcs)
followed the same invented rules ('killing takes 1-3 turns', 'no such NPC is
listed'). The broad verdict is off by default (llm._broad_verifier_enabled).

Round 2 put one model question in its place ('Does the scene show the player
trying what they wrote?') with a sentence pick and a rewrite. Measured live on
Hermes 3 8B it said yes to almost anything (27/36 false yes; no other wording
did better), the pick was right half the time and the rewrite leaked engine
text and wrote the player's claimed outcome into the scene. All three asks are
gone. The facts only a model can judge belong to the classes whose asks were
measured: a dead person acting (the interpreter's died and hold asks) and
words or choices put in the player's mouth (the agency asks).

What the verifier pass still owes the game, and who gives it now:

  * self_check, which the save, the turn payload and the page's ok/review flag
    read: written here. ``passed`` means the engine's checks found nothing
    they could not act on. The checks that ran before this point (the
    verification policy's: codes, scene plan, state deltas) and the prose
    gates in ensure_quality act on what they find (repair, cut, refuse); what
    is left that nothing acts on is an empty scene.
  * state-key patches: none. State changes are decided by the engine's own
    gates when the turn is applied (items, gold, moves, deaths, new places),
    each refusal a turn_ledger note.
  * an [[code]] naming no record is not judged here: places and people the
    prose brings in get their codes when the turn is applied (cc87dd29 T3's
    clinic [[L3]] is in no record yet at this point).
  * verification_memory: written and read only when the broad verifier runs
    (llm._verification_memory_covered_checks, world._write_verification_memory).
    These checks would only certify themselves, and rows an old broad verdict
    wrote must not clear checks nothing re-asks.
"""
from __future__ import annotations

from typing import Any

from app import turn_ledger


def _narration(turn: dict[str, Any]) -> str:
    text = str(turn.get("narration") or "").strip()
    if text:
        return text
    segments = turn.get("narration_segments") or []
    if isinstance(segments, list):
        return "\n\n".join(
            str(seg.get("text") or "").strip()
            for seg in segments
            if isinstance(seg, dict) and str(seg.get("text") or "").strip()
        )
    return ""


def check_turn(turn: dict[str, Any], policy: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Write ``turn``'s self_check from the engine's checks. The scene is never changed.

    ``policy`` is the turn's verification policy (llm._verification_policy):
    its cleared checks are named in reference_check. Returns (turn, report)
    for the trace.
    """
    result = dict(turn)
    policy = policy if isinstance(policy, dict) else {}
    cleared = [str(c) for c in policy.get("deterministically_verified") or [] if str(c).strip()]
    issues: list[str] = []
    empty = not _narration(result)
    if empty:
        issues.append("The scene is empty.")
        turn_ledger.note("verify", "scene_empty")
    previous = result.get("self_check") if isinstance(result.get("self_check"), dict) else {}
    # The draft's own corrections (the transcoder's, a skipped op line) stay;
    # its issues do not: a model-written draft's issues are the same free-form
    # verdict the broad verifier wrote (T5's invented rules).
    earlier = [str(c) for c in previous.get("corrections_made") or [] if str(c).strip()]
    passed = not issues
    result["self_check"] = {
        "passed": passed,
        "issues_found": issues,
        "corrections_made": earlier[:8],
        "reference_check": "Engine checks: " + (", ".join(cleared[:12]) if cleared else "prose gates only") + ".",
        "consistency_check": "No model verdict; the engine checks each state change when the turn is applied.",
    }
    report = {
        "passed": passed,
        "empty": empty,
        "cleared": cleared[:12],
        # What the broad verifier would have been sent for; the apply gates own it now.
        "left_to_apply_gates": [str(b) for b in policy.get("blockers") or []][:12],
    }
    return result, report
