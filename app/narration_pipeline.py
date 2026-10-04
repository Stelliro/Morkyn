"""
Adaptive paragraph narration pipeline (design: docs/NarrationPipeline.md).

v1 implements:
  - scene density + model-tier paragraph budget
  - attempt ledger (source of truth for said facts / attempts)
  - surgical edit ops on paragraph text
  - cascade adjacent-check helpers (deterministic overlap/contradiction heuristics)
  - orchestrator skeleton (LLM micro-calls wired later behind AI_RPG_NARRATION_PIPELINE)

Does not replace generate_turn until the feature flag is hooked in llm.py.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable


PIPELINE_VERSION = "V0.2.0"
DEFAULT_MAX_PAIR_EDITS = 2
# Overlap above this → treat as near-duplicate (surgical deletes were shredding prose).
OVERLAP_REJECT = 0.48
OVERLAP_DROP = 0.62

# A sentence is only policed for repetition once it is substantial enough that
# saying it twice reads as a mistake. Short lines -- "She waited.", '"I know."'
# -- echo on purpose, and a model that writes two similar beats is not doing
# the thing this guard exists to stop.
REPEAT_MIN_CHARS = 45
# Verbatim reuse is the common case; this catches the one-word reskin of it.
REPEAT_NEAR_MATCH = 0.85
# Two sentences can share a clause and still measure as different, because one
# of them wraps it in extra words or re-skins the rest. A run of identical
# consecutive words is what a reader actually notices.
#
# Set from measurement, not taste. Two reported turns:
#   "a rusted chain, still attached to a wooden crate"    9 words, jaccard 0.54
#   "thick with the scent of oil and metal"               8 words, jaccard 0.34
# Both read as obvious repeats and both sit far under the near-match bar, so a
# first guess of twelve caught neither. Eight catches both, and the shortest
# innocent collision found while checking -- "leans against the counter and",
# two different people at the same bar -- is five.
REPEAT_SHARED_RUN_WORDS = 8
# The same sentence with its words re-inflected or shuffled (playtest #3):
#   "You follow Aria, and the scent of ink grows stronger with each step."
#   "You follow Aria down the lane, the scent of ink growing stronger with each step."
# Raw tokens put that pair at 0.67, under the near-match bar, and the longest
# shared run is five words. Compared on content stems -- glue words out,
# grows/growing folded together -- it is 8 of 9. Both sentences need enough
# content for the score to mean anything; "Aria nods." is never policed.
REPEAT_STEM_MATCH = 0.7
REPEAT_STEM_MIN = 5
# Spoken lines are compared as whole quotations, across paragraphs only
# (playtest #5: three paragraphs each re-answered one remark, each ending on
# "But then again, isn't everyone..."). A shared five-word run counts only when
# three of the five are content words, so "I don't know what you" -- glue that
# any two people say -- never costs a line.
SPEECH_SHARED_RUN_WORDS = 5
SPEECH_RUN_MIN_CONTENT = 3

# --- env helpers -------------------------------------------------------------


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def pipeline_enabled() -> bool:
    return _env_bool("AI_RPG_NARRATION_PIPELINE", False)


# --- ledger ------------------------------------------------------------------


@dataclass
class AttemptRecord:
    id: str
    kind: str
    para_index: int | None
    input_digest: str
    output_text: str
    status: str
    issues: list[str] = field(default_factory=list)
    edit_ops: list[dict[str, Any]] = field(default_factory=list)
    ts: str = ""


@dataclass
class SaidFact:
    id: str
    text: str
    para: int
    status: str = "accepted"


@dataclass
class NarrationLedger:
    turn: int
    player_input: str
    budget: dict[str, Any]
    said_facts: list[SaidFact] = field(default_factory=list)
    attempts: list[AttemptRecord] = field(default_factory=list)
    final_paragraphs: list[str] = field(default_factory=list)
    final_narration: str = ""
    version: str = PIPELINE_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "turn": self.turn,
            "player_input": self.player_input,
            "budget": self.budget,
            "said_facts": [asdict(f) for f in self.said_facts],
            "attempts": [asdict(a) for a in self.attempts],
            "final_paragraphs": list(self.final_paragraphs),
            "final_narration": self.final_narration,
        }

    def record_attempt(
        self,
        kind: str,
        para_index: int | None,
        input_payload: Any,
        output_text: str,
        status: str,
        issues: list[str] | None = None,
        edit_ops: list[dict[str, Any]] | None = None,
    ) -> AttemptRecord:
        digest = _digest(input_payload)
        attempt = AttemptRecord(
            id=f"a{len(self.attempts) + 1}",
            kind=kind,
            para_index=para_index,
            input_digest=digest,
            output_text=(output_text or "")[:4000],
            status=status,
            issues=list(issues or [])[:12],
            edit_ops=list(edit_ops or [])[:12],
            ts=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )
        self.attempts.append(attempt)
        return attempt

    def add_said_fact(self, text: str, para: int) -> SaidFact:
        clean = _trim(text, 240)
        for existing in self.said_facts:
            if _norm(existing.text) == _norm(clean):
                return existing
        fact = SaidFact(id=f"f{len(self.said_facts) + 1}", text=clean, para=para, status="accepted")
        self.said_facts.append(fact)
        return fact

    def forbidden_repeats(self) -> list[str]:
        return [f.text for f in self.said_facts if f.status == "accepted"]

    def previously_attempted_texts(self, para_index: int | None = None) -> list[str]:
        out: list[str] = []
        for attempt in self.attempts:
            if attempt.status in {"rejected", "superseded"} and attempt.output_text:
                if para_index is None or attempt.para_index == para_index:
                    out.append(attempt.output_text)
        return out[-8:]


def save_ledger(ledger: NarrationLedger, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger.to_dict(), ensure_ascii=True, indent=2), encoding="utf-8")
    return path


def load_ledger(path: Path) -> NarrationLedger:
    raw = json.loads(path.read_text(encoding="utf-8"))
    ledger = NarrationLedger(
        turn=int(raw.get("turn") or 0),
        player_input=str(raw.get("player_input") or ""),
        budget=dict(raw.get("budget") or {}),
        version=str(raw.get("version") or PIPELINE_VERSION),
        final_paragraphs=list(raw.get("final_paragraphs") or []),
        final_narration=str(raw.get("final_narration") or ""),
    )
    for item in raw.get("said_facts") or []:
        if isinstance(item, dict):
            ledger.said_facts.append(
                SaidFact(
                    id=str(item.get("id") or f"f{len(ledger.said_facts) + 1}"),
                    text=str(item.get("text") or ""),
                    para=int(item.get("para") or 0),
                    status=str(item.get("status") or "accepted"),
                )
            )
    for item in raw.get("attempts") or []:
        if isinstance(item, dict):
            ledger.attempts.append(
                AttemptRecord(
                    id=str(item.get("id") or f"a{len(ledger.attempts) + 1}"),
                    kind=str(item.get("kind") or "unknown"),
                    para_index=item.get("para_index"),
                    input_digest=str(item.get("input_digest") or ""),
                    output_text=str(item.get("output_text") or ""),
                    status=str(item.get("status") or "unknown"),
                    issues=list(item.get("issues") or []),
                    edit_ops=list(item.get("edit_ops") or []),
                    ts=str(item.get("ts") or ""),
                )
            )
    return ledger


# --- model tier + budget -----------------------------------------------------


def infer_model_tier(config: dict[str, Any] | None = None) -> str:
    """small / medium / large from context window, response caps, and model name."""
    cfg = config or {}
    name = " ".join(
        str(cfg.get(key) or "")
        for key in ("mle_model", "gguf_model_path", "model", "model_name")
    ).lower()
    try:
        context = int(cfg.get("context_window") or cfg.get("n_ctx") or 0)
    except (TypeError, ValueError):
        context = 0
    try:
        soft = int(cfg.get("response_token_cap") or 0)
    except (TypeError, ValueError):
        soft = 0

    small_name = any(token in name for token in ("3b", "4b", "7b", "8b", "1.5b", "0.5b", "mini", "tiny"))
    large_name = any(token in name for token in ("70b", "72b", "34b", "32b", "27b", "22b", "20b", "14b", "13b"))

    if small_name or (context and context <= 8192) or (soft and soft <= 900):
        return "small"
    if large_name or (context and context >= 32768 and soft >= 1800):
        return "large"
    if (context and context <= 16384) or (soft and soft <= 1500):
        return "medium"
    return "medium"


def _location_match_keys(loc: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    if loc.get("id") is not None:
        keys.add(f"id:{loc.get('id')}")
    code = str(loc.get("code") or loc.get("location_code") or "").strip().upper()
    if code:
        keys.add(f"code:{code}")
    name = str(loc.get("name") or loc.get("location_name") or "").strip().lower()
    if name:
        keys.add(f"name:{name}")
    return keys


def _npc_at_location(npc: dict[str, Any], loc_keys: set[str]) -> bool:
    if not loc_keys:
        return True
    # location_code / location_name / location_id are get_state joins.
    # DSL + JSON schema store the place on `location` (code or name). Never treat
    # npc.code (entity A/B/…) as a place code.
    probe_keys = set()
    if npc.get("location_id") is not None:
        probe_keys.add(f"id:{npc.get('location_id')}")
    if npc.get("location_code"):
        probe_keys.add(f"code:{str(npc.get('location_code')).strip().upper()}")
    if npc.get("location_name"):
        probe_keys.add(f"name:{str(npc.get('location_name')).strip().lower()}")
    loc_field = str(npc.get("location") or "").strip()
    if loc_field:
        probe_keys.add(f"code:{loc_field.upper()}")
        probe_keys.add(f"name:{loc_field.lower()}")
    return bool(probe_keys & loc_keys) if probe_keys else False


def collect_local_npcs(context: dict[str, Any]) -> list[dict[str, Any]]:
    """
    NPCs near the player. get_state() puts current_location WITHOUT nested npcs
    (nested npcs live on locations[] tree entries), so we merge several shapes:
    current_location.npcs, matching locations[].npcs, top-level npcs, action_context.
    """
    loc = context.get("current_location") if isinstance(context.get("current_location"), dict) else {}
    loc_keys = _location_match_keys(loc)
    found: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(npc: Any) -> None:
        if not isinstance(npc, dict):
            return
        key = str(npc.get("code") or npc.get("id") or npc.get("name") or "").strip().lower()
        if not key or key in seen:
            return
        seen.add(key)
        found.append(npc)

    if isinstance(loc.get("npcs"), list):
        for npc in loc["npcs"]:
            _add(npc)

    for place in context.get("locations") or []:
        if not isinstance(place, dict):
            continue
        place_keys = _location_match_keys(place)
        if loc_keys and not (place_keys & loc_keys):
            continue
        for npc in place.get("npcs") or []:
            _add(npc)

    for npc in context.get("npcs") or []:
        if isinstance(npc, dict) and _npc_at_location(npc, loc_keys):
            _add(npc)

    def _add_code(code: Any) -> None:
        token = str(code or "").strip()
        if token:
            _add({"code": token})

    # Prompt-context working sets. world._working_set ships nearby_npc_codes,
    # not a `npcs` list; world._action_context ships local_focus_codes.nearby_npcs.
    # Focused handoff may drop locations[], so these code lists are the local cast.
    for key in ("local_npcs", "nearby_npcs"):
        for npc in context.get(key) or []:
            _add(npc)
    action = context.get("action_context") if isinstance(context.get("action_context"), dict) else {}
    for key in ("local_npcs", "nearby_npcs", "npcs"):
        for npc in action.get(key) or []:
            _add(npc)
    focus = action.get("local_focus_codes") if isinstance(action.get("local_focus_codes"), dict) else {}
    for code in focus.get("nearby_npcs") or []:
        _add_code(code)
    targets = action.get("target_codes") if isinstance(action.get("target_codes"), dict) else {}
    for code in targets.get("npcs") or []:
        _add_code(code)
    working = context.get("working_set") if isinstance(context.get("working_set"), dict) else {}
    for npc in working.get("npcs") or []:
        _add(npc)
    for code in working.get("nearby_npc_codes") or []:
        _add_code(code)

    return found


def collect_relevant_events(context: dict[str, Any]) -> list[dict[str, Any]]:
    """Events from top-level list, location tree, and current location."""
    loc = context.get("current_location") if isinstance(context.get("current_location"), dict) else {}
    loc_keys = _location_match_keys(loc)
    found: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(event: Any) -> None:
        if not isinstance(event, dict):
            return
        key = str(event.get("code") or event.get("id") or event.get("title") or "").strip().lower()
        if not key or key in seen:
            return
        status = str(event.get("status") or "").lower()
        # Prefer active pressure; still count blank/background lightly via caller caps.
        if status in {"resolved", "closed", "ended", "done"}:
            return
        seen.add(key)
        found.append(event)

    for event in context.get("events") or []:
        _add(event)
    if isinstance(loc.get("events"), list):
        for event in loc["events"]:
            _add(event)
    for place in context.get("locations") or []:
        if not isinstance(place, dict):
            continue
        if loc_keys and not (_location_match_keys(place) & loc_keys):
            continue
        for event in place.get("events") or []:
            _add(event)
    return found


def collect_inventory(context: dict[str, Any]) -> list[dict[str, Any]]:
    inv = context.get("inventory") if isinstance(context.get("inventory"), list) else []
    summary = context.get("inventory_summary") if isinstance(context.get("inventory_summary"), dict) else {}
    items = [i for i in inv if isinstance(i, dict)]
    if not items and summary:
        # summary-only contexts still count as carrying gear
        return [{"name": "inventory", "quantity": 1}] if summary else []
    return items


def scene_density(context: dict[str, Any], player_input: str = "") -> dict[str, Any]:
    """Deterministic density score from events, people, locations, items, intent."""
    loc = context.get("current_location") if isinstance(context.get("current_location"), dict) else {}
    npcs = collect_local_npcs(context)
    locations = context.get("locations") if isinstance(context.get("locations"), list) else []
    events = collect_relevant_events(context)
    inventory = collect_inventory(context)
    active_events = [
        e
        for e in events
        if str(e.get("status") or "").lower() in {"", "active", "open", "ongoing", "background", "story"}
    ]
    # If status missing, still count up to a few events as pressure.
    if not active_events and events:
        active_events = events[:3]

    intent = (player_input or "").lower()
    combatish = any(w in intent for w in ("attack", "fight", "strike", "kill", "weapon", "dodge", "block", "flee combat"))
    complex_action = len(intent.split()) >= 18 or intent.count(" and ") >= 2
    social = any(w in intent for w in ("ask", "talk", "tell", "speak", "merchant", "npc", "warn", "rumor"))
    item_focus = any(w in intent for w in ("item", "give", "take", "buy", "sell", "equip", "satchel", "letter", "inventory"))

    # Opening scenes: treat start location as at least moderate density even before NPCs exist.
    kind = str((context.get("turn_kind") or context.get("input_kind") or "")).lower()
    opening_boost = 2 if kind in {"opening", "opening_scene"} or str(player_input).startswith("__opening_scene") else 0

    parts = {
        "npcs": min(4, len(npcs)) + (1 if social and npcs else 0),
        "locations": min(3, max(1, len(locations) if locations else (1 if loc else 0))),
        "items": min(2, (1 if inventory else 0) + (1 if item_focus else 0)),
        "events": min(3, len(active_events) + (1 if events else 0)),
        "combat": 3 if combatish else 0,
        "action_complexity": 2 if complex_action else (1 if len(intent.split()) >= 10 else 0),
        "opening": opening_boost,
    }
    # Cap npc part at 4 for scoring stability
    parts["npcs"] = min(4, int(parts["npcs"]))
    score = int(sum(parts.values()))
    return {
        "score": score,
        "parts": parts,
        "active_npc_count": len(npcs),
        "active_event_count": len(active_events),
        "npc_names": [str(n.get("name") or n.get("code") or "") for n in npcs[:6]],
        "event_titles": [str(e.get("title") or e.get("code") or "") for e in active_events[:6]],
    }


def plan_paragraph_budget(
    context: dict[str, Any],
    player_input: str = "",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    density = scene_density(context, player_input)
    tier = infer_model_tier(config)
    detail = str(((context.get("settings") or {}).get("playthrough_options") or {}).get("narration_detail") or context.get("narration_detail") or "balanced").lower()

    # Base paragraph count by tier, then density.
    # small tier: slightly richer floor so 8B openings are not ~400 chars of air.
    if tier == "small":
        base, lo, hi = 3, 2, 4
        chars = (320, 480)
    elif tier == "large":
        base, lo, hi = 4, 3, 6
        chars = (350, 550)
    else:
        base, lo, hi = 3, 2, 4
        chars = (320, 480)

    score = int(density["score"])
    if score >= 10:
        base += 2
    elif score >= 7:
        base += 1
    elif score <= 3:
        base -= 1

    if "concise" in detail:
        base -= 1
    elif any(token in detail for token in ("rich", "expansive", "detailed")):
        base += 1

    count = max(lo, min(hi, base))
    # Opening / continue scenes get at least tier floor + 1 when dense.
    kind = str((context.get("turn_kind") or context.get("input_kind") or "")).lower()
    if kind in {"opening", "opening_scene"} or str(player_input).startswith("__opening_scene"):
        count = min(hi, max(count, 3 if tier == "small" else count + 1))

    roles = _beat_roles(count)
    max_tokens = max(140, min(420, chars[1] // 3 + 50))
    soft_total = count * ((chars[0] + chars[1]) // 2)
    # Explicit soft floors by tier (comparison run showed ~466 on small was too thin).
    if tier == "small":
        soft_total = max(soft_total, 900)
    elif tier == "medium":
        soft_total = max(soft_total, 1100)
    else:
        soft_total = max(soft_total, 1400)

    return {
        "tier": tier,
        "paragraphs": count,
        "chars_per_paragraph": {"min": chars[0], "max": chars[1]},
        "max_tokens_per_paragraph": max_tokens,
        "density": density,
        "narration_detail": detail,
        "beat_roles": roles,
        "soft_total_chars": soft_total,
        "skip_consolidator": should_skip_consolidator(count, score),
    }


def should_skip_consolidator(paragraph_count: int, density_score: int) -> bool:
    """
    Skip whole-scene consolidator on lean 2-paragraph / low-density turns.
    Saves an LLM call when there is little to reconcile.
    Env AI_RPG_NARRATION_PIPELINE_CONSOLIDATE=0 still disables always.
    """
    if not _env_bool("AI_RPG_NARRATION_PIPELINE_CONSOLIDATE", True):
        return True
    if paragraph_count <= 2 and density_score < 7:
        return True
    return False


def _beat_roles(count: int) -> list[str]:
    # Last beat is pressure, not "choice". PROSE_VOICE / DSL_SYSTEM_PROMPT
    # forbid ending on a restated option menu ("The choice is yours") — that
    # hands the turn back unplayed. End on consequence or new pressure.
    if count <= 1:
        return ["act"]
    if count == 2:
        return ["establish", "pressure"]
    if count == 3:
        return ["establish", "act", "pressure"]
    if count == 4:
        return ["establish", "act", "consequence", "pressure"]
    if count == 5:
        return ["establish", "act", "react", "consequence", "pressure"]
    return ["establish", "act", "react", "consequence", "pressure", "hook"][:count]


# --- surgical edits ----------------------------------------------------------


def looks_truncated(text: str) -> bool:
    """True when prose ends mid-word / mid-clause (common 8B + max_chars cut)."""
    t = _collapse_ws(text)
    if not t or len(t) < 12:
        return True
    if re.search(r'[.!?]["\')\]]?\s*$', t):
        return False
    # ellipsis / dash closeouts can be intentional
    if t.endswith(("…", "...", "—", "–")):
        return False
    last = t[-1]
    if last.isalnum() or last in ",;:":
        return True
    return False


def looks_garbage_fragment(text: str) -> bool:
    """Mid-edit shreds like 'ent faint hum…' or lowercase mid-sentence starts."""
    t = _collapse_ws(text)
    if not t:
        return True
    if looks_truncated(t):
        return True
    # leftover word stump at start ("ent faint", "could be, its")
    if re.match(r"^[a-z]{1,4}\s", t):
        return True
    if t[0].islower() and not re.match(
        r"^(and|but|or|then|so|yet|for|nor|still|now|here|there|inside|outside|above|below)\b",
        t,
        re.I,
    ):
        return True
    # single incomplete clause under ~2 sentences with no period
    if len(t) < 90 and not re.search(r"[.!?]", t):
        return True
    return False


def polish_paragraph(text: str, max_chars: int = 480) -> str:
    """
    Never hard-slice mid-word. Prefer the last complete sentence inside budget.
    Drops a trailing incomplete clause when the model or a char cap cut off.
    """
    t = _collapse_ws(text)
    if not t:
        return ""
    max_chars = max(80, int(max_chars or 480))

    def _last_sentence_cut(window: str) -> str:
        ends = [m.end() for m in re.finditer(r'[.!?]["\')\]]?(?=\s|$)', window)]
        if ends:
            cut = window[: ends[-1]].strip()
            if len(cut) >= 60:
                return cut
        # word boundary fallback (still better than mid-token)
        if " " in window:
            return window.rsplit(" ", 1)[0].rstrip(" ,;:—-")
        return window

    if len(t) > max_chars:
        t = _last_sentence_cut(t[:max_chars])
    elif looks_truncated(t):
        # model stopped mid-sentence without hitting our char cap
        t = _last_sentence_cut(t)
        if looks_truncated(t) and " " in t:
            # drop the incomplete final clause after last punctuation
            m = list(re.finditer(r'[.!?]["\')\]]?\s+', t))
            if m:
                t = t[: m[-1].end()].strip()
            else:
                t = t.rsplit(" ", 1)[0].rstrip(" ,;:—-")
    t = _collapse_ws(t)
    # Capitalize accidental lowercase start from prior edits
    if t and t[0].islower():
        t = t[0].upper() + t[1:]
    return t


def apply_edit_ops(text: str, ops: list[dict[str, Any]]) -> str:
    """Apply surgical edit ops without rewriting the whole paragraph."""
    result = text or ""
    for op in ops or []:
        if not isinstance(op, dict):
            continue
        kind = str(op.get("op") or op.get("type") or "").lower()
        match = str(op.get("match") or "")
        replacement = str(op.get("with") or op.get("replacement") or "")
        if kind in {"rewrite", "drop", "reject"}:
            # Signal full rewrite; caller should not publish empty mid-edits.
            return ""
        if kind in {"replace_span", "replace"} and match:
            if match in result:
                result = result.replace(match, replacement, 1)
            else:
                # soft fallback: case-insensitive single replace
                pattern = re.compile(re.escape(match), re.IGNORECASE)
                result, n = pattern.subn(replacement, result, count=1)
                if n == 0 and replacement:
                    result = result.rstrip() + " " + replacement
        elif kind in {"delete_span", "delete"} and match:
            result = result.replace(match, "", 1)
        elif kind in {"soft_bridge", "append", "bridge"} and replacement:
            if replacement not in result:
                result = (result.rstrip() + " " + replacement.strip()).strip()
        elif kind in {"prepend"} and replacement:
            if not result.startswith(replacement):
                result = (replacement.strip() + " " + result.lstrip()).strip()
        elif kind in {"set"}:
            result = replacement
    cleaned = polish_paragraph(_collapse_ws(result), max_chars=max(len(text or "") + 40, 480))
    if looks_garbage_fragment(cleaned):
        return ""
    return cleaned


# --- adjacent / cascade checks (deterministic core) --------------------------


def token_set(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9']+", (text or "").lower()) if len(t) > 2}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


# House idiom, matching app/world.py and app/setup_composer.py. It deliberately
# under-splits a sentence that ends inside a quotation mark ('He said "go."'),
# which costs a detection now and then and never mangles the prose.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_SENTENCE_NORM_RE = re.compile(r"[^a-z0-9 ]+")
_BLOCK_SPLIT_RE = re.compile(r"\n\s*\n")


def split_sentences(text: str) -> list[str]:
    return [s for s in (part.strip() for part in _SENTENCE_SPLIT_RE.split(text or "")) if s]


def _sentence_key(sentence: str) -> str:
    """Compare on words alone, so punctuation and casing cannot hide a repeat."""
    return " ".join(_SENTENCE_NORM_RE.sub(" ", (sentence or "").lower()).split())


def _shared_runs(sentence_key: str) -> set[str]:
    """Every REPEAT_SHARED_RUN_WORDS-word run in a sentence, for clause reuse."""
    words = sentence_key.split()
    if len(words) < REPEAT_SHARED_RUN_WORDS:
        return set()
    return {
        " ".join(words[i : i + REPEAT_SHARED_RUN_WORDS])
        for i in range(len(words) - REPEAT_SHARED_RUN_WORDS + 1)
    }


# Closed-class words, plus the few verbs that only hold a sentence together.
# A job title is not in this set. Titles are counted and then kept.
_STRUCTURE_WORDS = frozenset({
    "a", "an", "the",
    "and", "but", "or", "nor", "yet", "so",
    "if", "as", "because", "although", "though", "while", "when", "where",
    "whether", "once", "unless", "until",
    "of", "to", "in", "on", "at", "for", "with", "from", "by", "into",
    "over", "under", "about", "after", "before", "between", "through",
    "without", "within", "across", "around", "toward", "towards", "upon",
    "onto", "off", "out", "up", "down", "than", "then",
    "that", "this", "these", "those",
    "it", "its", "is", "are", "was", "were", "be", "been", "being", "am",
    "do", "does", "did", "have", "has", "had",
    "will", "would", "could", "should", "may", "might", "must", "can",
    "not", "no",
    "you", "your", "yours", "we", "our", "ours", "they", "them", "their",
    "he", "she", "him", "her", "his", "hers", "i", "me", "my",
    "who", "whom", "what", "which", "there", "here",
    "said", "says", "asked", "ask", "replied", "told",
})
_CONTENT_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")
# Uses already on the page before a later copy is removed.
WORD_REPEAT_CAP = 3
WORD_COUNT_LOOKBACK = 8


def count_content_words(texts: list[str]) -> dict[str, int]:
    """How many times each content word appears. Glue words are not counted."""
    counts: dict[str, int] = {}
    for text in texts:
        for match in _CONTENT_WORD_RE.finditer(str(text or "")):
            word = match.group(0).lower()
            if len(word) < 2 or word in _STRUCTURE_WORDS:
                continue
            counts[word] = counts.get(word, 0) + 1
    return counts


def narration_keep_words(
    context: dict[str, Any] | None,
    result: dict[str, Any] | None = None,
) -> tuple[set[str], set[str]]:
    """
    Names are never filtered. Job titles are counted elsewhere and also never
    filtered. A title is not a link to one record.

    Names include the names of powers: the player's abilities and skills
    (proficiencies are mirrored into skills), abilities an NPC or an item
    carries, and ones a turn just gained or changed. They used to be left out,
    so a power named in more than WORD_REPEAT_CAP recent scenes had its words
    hidden from the sampler and came out half-written.
    """
    names: set[str] = set()
    titles: set[str] = set()

    def add_name(value: Any) -> None:
        for match in _CONTENT_WORD_RE.finditer(str(value or "")):
            word = match.group(0).lower()
            if len(word) >= 2:
                names.add(word)

    def add_title(value: Any) -> None:
        for match in _CONTENT_WORD_RE.finditer(str(value or "")):
            word = match.group(0).lower()
            if len(word) >= 2 and word not in _STRUCTURE_WORDS:
                titles.add(word)

    packets: list[dict[str, Any]] = []
    if isinstance(context, dict):
        packets.append(context)
    if isinstance(result, dict):
        packets.append(result)
    for packet in packets:
        player = packet.get("player") if isinstance(packet.get("player"), dict) else {}
        for key in ("name", "public_name"):
            add_name(player.get(key))
        add_title(player.get("title"))
        alias = packet.get("active_player_alias")
        if isinstance(alias, dict):
            add_name(alias.get("name"))
        for alias in packet.get("player_aliases") or []:
            if isinstance(alias, dict):
                add_name(alias.get("name"))
        current = packet.get("current_location")
        if isinstance(current, dict):
            add_name(current.get("name"))
        for location in packet.get("locations") or []:
            if not isinstance(location, dict):
                continue
            add_name(location.get("name"))
            for npc in location.get("npcs") or []:
                if isinstance(npc, dict):
                    add_name(npc.get("name"))
                    add_title(npc.get("role"))
        for npc in packet.get("npcs") or []:
            if isinstance(npc, dict):
                add_name(npc.get("name"))
                add_title(npc.get("role"))
                _add_power_names(npc.get("abilities"), add_name)
        for item in packet.get("inventory") or []:
            if isinstance(item, dict):
                add_name(item.get("name"))
                _add_power_names(item.get("granted_abilities"), add_name)
                _add_power_names(item.get("enchantments"), add_name)
        for item in packet.get("inventory_changes") or []:
            if isinstance(item, dict):
                add_name(item.get("name"))
        for key in ("abilities", "skills", "ability_updates", "skill_changes"):
            _add_power_names(packet.get(key), add_name)
    return names, titles


def _add_power_names(entries: Any, add_name: Callable[[Any], None]) -> None:
    """Ability, skill or enchantment names from a list of rows or plain names."""
    if not isinstance(entries, list):
        return
    for entry in entries:
        if isinstance(entry, dict):
            add_name(entry.get("name") or entry.get("skill") or entry.get("ability_name"))
        elif isinstance(entry, str):
            add_name(entry)


def words_past_cap(
    counts: dict[str, int] | None,
    *,
    names: set[str] | None = None,
    titles: set[str] | None = None,
    cap: int = WORD_REPEAT_CAP,
) -> list[str]:
    """
    Content words the middle should hide on the next reply.

    This list is for the sampler, before a word is chosen. It does not edit
    a reply that has already been written. Names and job titles are never
    on the list. A title still counts; it is just never hidden.
    """
    kept_names = {word.lower() for word in (names or set())}
    kept_titles = {word.lower() for word in (titles or set())}
    blocked: list[str] = []
    for word, seen in sorted((counts or {}).items(), key=lambda item: (-item[1], item[0])):
        low = str(word or "").lower()
        if seen <= cap or not low:
            continue
        if low in _STRUCTURE_WORDS or low in kept_names or low in kept_titles:
            continue
        blocked.append(low)
    return blocked


def _is_speech_fragment(sentence: str) -> bool:
    """An unclosed quote opener or a line that trails off: '"Twelve gold...'."""
    text = str(sentence or "").strip()
    quotes = sum(text.count(mark) for mark in ('"', "“", "”"))
    return quotes % 2 == 1 or text.endswith(("...", "…"))


def _stem(word: str) -> str:
    """Fold the common inflections together: grows/growing/grown stay apart, grows/growing meet."""
    w = word.lower().strip("'-")
    if len(w) > 5 and w.endswith("ing"):
        w = w[:-3]
    elif len(w) > 4 and w.endswith("ed"):
        w = w[:-2]
    elif len(w) > 4 and w.endswith("es"):
        w = w[:-2]
    elif len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        w = w[:-1]
    if len(w) > 4 and w.endswith("e"):
        w = w[:-1]
    return w


def content_stems(text: str) -> set[str]:
    """Content words of a sentence, inflection folded, glue words out."""
    out: set[str] = set()
    for match in _CONTENT_WORD_RE.finditer(str(text or "")):
        word = match.group(0).lower()
        if len(word) < 3 or word in _STRUCTURE_WORDS:
            continue
        out.add(_stem(word))
    return out


def is_near_restatement(a: str, b: str) -> bool:
    """Same sentence re-worded: content stems overlap REPEAT_STEM_MATCH or more."""
    sa, sb = content_stems(a), content_stems(b)
    if len(sa) < REPEAT_STEM_MIN or len(sb) < REPEAT_STEM_MIN:
        return False
    return jaccard(sa, sb) >= REPEAT_STEM_MATCH


_QUOTE_SPAN_RE = re.compile(r'"([^"]+)"|\u201c([^\u201d]+)\u201d')


def _quote_marks(text: str) -> int:
    return sum(str(text or "").count(mark) for mark in ('"', "\u201c", "\u201d"))


def quoted_spans(text: str) -> list[str]:
    """Every quoted line in a passage, quotes removed."""
    return [
        (m.group(1) or m.group(2) or "").strip()
        for m in _QUOTE_SPAN_RE.finditer(str(text or ""))
        if (m.group(1) or m.group(2) or "").strip()
    ]


def _speech_key(text: str) -> str:
    """Like _sentence_key, but "isn't" stays one word so contractions do not pad runs."""
    folded = re.sub(r"['\u2019]", "", str(text or "").lower())
    return " ".join(_SENTENCE_NORM_RE.sub(" ", folded).split())


def _speech_runs(text: str) -> set[str]:
    words = _speech_key(text).split()
    runs: set[str] = set()
    for i in range(len(words) - SPEECH_SHARED_RUN_WORDS + 1):
        run = words[i : i + SPEECH_SHARED_RUN_WORDS]
        if sum(1 for w in run if w not in _STRUCTURE_WORDS and len(w) > 2) >= SPEECH_RUN_MIN_CONTENT:
            runs.add(" ".join(run))
    return runs


# Unlike split_sentences, also splits after a closing quote ('...soon." She
# turns'), so a spoken line and the narration after it are separate units.
# A lowercase word after the quote is its attribution ('?" she asks') and stays.
_UNIT_SPLIT_RE = re.compile(r'(?<=[.!?])\s+|(?<=[.!?]["\u201d])\s+(?=[A-Z"\u201c])')


def speech_units(block: str) -> list[str]:
    """Sentences, but a quotation that spans several sentences stays one unit."""
    units: list[str] = []
    pending = ""
    parts = (part.strip() for part in _UNIT_SPLIT_RE.split(str(block or "")))
    for sentence in (part for part in parts if part):
        pending = f"{pending} {sentence}".strip() if pending else sentence
        if _quote_marks(pending) % 2 == 0:
            units.append(pending)
            pending = ""
    if pending:
        units.append(pending)
    return units


def speech_repeats(earlier_speech: list[str], speech: str) -> bool:
    """True when a spoken line restates one already spoken (shared run or re-worded)."""
    runs = _speech_runs(speech)
    for prev in earlier_speech:
        if runs & _speech_runs(prev):
            return True
        if is_near_restatement(prev, speech):
            return True
    return False


def drop_repeated_speech(paragraphs: list[str]) -> tuple[list[str], list[str]]:
    """
    Remove a spoken line that restates a line from an earlier paragraph.

    Works on whole quotations, so a reply that runs over several sentences is
    kept or dropped as one piece and never leaves an unclosed quote behind.
    Lines inside one paragraph are not compared with each other.
    """
    seen: list[str] = []
    kept_paragraphs: list[str] = []
    dropped: list[str] = []
    for para in paragraphs:
        pending: list[str] = []
        kept_blocks: list[str] = []
        for block in _BLOCK_SPLIT_RE.split(str(para or "")):
            kept_units: list[str] = []
            for unit in speech_units(block):
                spans = quoted_spans(unit)
                if not spans or _quote_marks(unit) % 2:
                    kept_units.append(unit)
                    continue
                speech = " ".join(spans)
                if seen and speech_repeats(seen, speech):
                    dropped.append(unit)
                    continue
                pending.append(speech)
                kept_units.append(unit)
            block_text = " ".join(kept_units).strip()
            if block_text:
                kept_blocks.append(block_text)
        seen.extend(pending)
        kept_paragraphs.append("\n\n".join(kept_blocks).strip())
    return kept_paragraphs, dropped


def drop_repeated_sentences(paragraphs: list[str]) -> tuple[list[str], list[str]]:
    """
    Remove any sentence already said earlier in the same turn, however far back.

    The pair walker above only ever compares a paragraph with the one directly
    above it, and it scores whole paragraphs. Both choices miss the shape that
    actually reaches players: a paragraph that repeats one sentence verbatim and
    then adds a fresh one, which dilutes the paragraph-level overlap below the
    reject bar while reading as an obvious stutter.

    Returns (paragraphs, dropped_sentences). The first list is the same length
    as the input, with "" where a paragraph was nothing but repeats, so callers
    holding parallel data (segment labels) stay aligned.
    """
    original = list(paragraphs)
    paragraphs, speech_dropped = drop_repeated_speech(list(paragraphs))
    seen_keys: set[str] = set()
    seen_tokens: list[set[str]] = []
    seen_stems: list[set[str]] = []
    seen_runs: set[str] = set()
    kept_paragraphs: list[str] = []
    dropped: list[str] = list(speech_dropped)

    for para in paragraphs:
        kept_blocks: list[str] = []
        # Paragraph breaks inside a single segment are structure, not noise.
        for block in _BLOCK_SPLIT_RE.split(str(para or "")):
            kept_sentences: list[str] = []
            for sentence in split_sentences(block):
                key = _sentence_key(sentence)
                if len(key) < REPEAT_MIN_CHARS:
                    # Short lines are exempt from the near-match tests, not from
                    # an exact repeat: "Twelve gold..." opened the same reply
                    # three times in one turn because it was 12 characters.
                    # Complete short lines ("I know," he said.) may echo; a
                    # repeated fragment -- an unclosed quote or a trailing
                    # ellipsis -- is the model restarting the same reply.
                    fragment = _is_speech_fragment(sentence)
                    if fragment and len(key.split()) >= 2 and key in seen_keys:
                        dropped.append(sentence)
                        continue
                    if fragment and len(key.split()) >= 2:
                        seen_keys.add(key)
                    kept_sentences.append(sentence)
                    continue
                if key in seen_keys:
                    dropped.append(sentence)
                    continue
                tokens = token_set(sentence)
                if any(jaccard(tokens, prev) >= REPEAT_NEAR_MATCH for prev in seen_tokens):
                    dropped.append(sentence)
                    continue
                runs = _shared_runs(key)
                if runs & seen_runs:
                    dropped.append(sentence)
                    continue
                # Re-worded restatement. Only a sentence with balanced quotes,
                # so dropping it can never leave half a quotation behind.
                stems = content_stems(sentence)
                if (
                    _quote_marks(sentence) % 2 == 0
                    and len(stems) >= REPEAT_STEM_MIN
                    and any(
                        len(prev) >= REPEAT_STEM_MIN and jaccard(stems, prev) >= REPEAT_STEM_MATCH
                        for prev in seen_stems
                    )
                ):
                    dropped.append(sentence)
                    continue
                seen_keys.add(key)
                seen_tokens.append(tokens)
                seen_stems.append(stems)
                seen_runs |= runs
                kept_sentences.append(sentence)
            block_text = " ".join(kept_sentences).strip()
            if block_text:
                kept_blocks.append(block_text)
        kept_paragraphs.append("\n\n".join(kept_blocks).strip())

    # A turn that repeated itself end to end still has to say something.
    if original and not any(p.strip() for p in kept_paragraphs):
        first = str(original[0] or "").strip()
        if first:
            return [first] + [""] * (len(original) - 1), []

    return kept_paragraphs, dropped


def check_adjacent_paragraphs(earlier: str, later: str) -> dict[str, Any]:
    """
    Deterministic pair check. Returns pass/issues/edit_ops.
    LLM consolidator can refine later; this catches doubling and empty drift.
    """
    issues: list[dict[str, str]] = []
    edit_ops: list[dict[str, Any]] = []
    e = (earlier or "").strip()
    l = (later or "").strip()

    if not l:
        return {
            "pass": False,
            "issues": [{"type": "empty", "detail": "Later paragraph is empty."}],
            "edit_ops": [{"target": "later", "op": "set", "with": e[:180] and "The moment continues without repeating itself." or "The scene holds."}],
        }

    # Near-duplicate paragraphs — request full rewrite, never shred mid-sentence.
    if e and (l == e or (len(l) > 40 and l in e) or (len(e) > 40 and e in l)):
        issues.append({"type": "double", "detail": "Later paragraph duplicates earlier text."})
        edit_ops.append({"target": "later", "op": "rewrite", "with": ""})

    overlap = jaccard(token_set(e), token_set(l))
    if e and overlap >= OVERLAP_REJECT:
        issues.append(
            {
                "type": "double",
                "detail": f"High lexical overlap with previous paragraph ({overlap:.0%}).",
            }
        )
        edit_ops.append({"target": "later", "op": "rewrite", "with": ""})

    if looks_truncated(l) or looks_garbage_fragment(l):
        issues.append({"type": "truncated", "detail": "Later paragraph is truncated or a garbage fragment."})
        edit_ops.append({"target": "later", "op": "rewrite", "with": ""})

    # Simple simultaneous dual-intent heuristic
    dual_pairs = [
        ("buy", "flee"),
        ("attack", "rest"),
        ("sleep", "run"),
        ("give", "steal"),
    ]
    l_low = l.lower()
    for a, b in dual_pairs:
        if a in l_low and b in l_low and "then" not in l_low and "before" not in l_low and "after" not in l_low:
            issues.append(
                {
                    "type": "dual_intent",
                    "detail": f"Paragraph tries to do '{a}' and '{b}' without sequencing.",
                }
            )
            edit_ops.append(
                {
                    "target": "later",
                    "op": "soft_bridge",
                    "with": f"First the {a} resolves; only then does the {b} become possible.",
                }
            )
            break

    # Contradiction stubs (presence)
    if e and re.search(r"\b(gone|left|departed|dead)\b", e, re.I) and re.search(r"\b(still here|remains|stands nearby|is present)\b", l, re.I):
        issues.append({"type": "contradiction", "detail": "Earlier text removed someone/something that later text still presents."})
        edit_ops.append({"target": "later", "op": "soft_bridge", "with": "Only traces remain of what was already gone."})

    passed = not issues
    return {"pass": passed, "issues": issues, "edit_ops": edit_ops, "overlap": round(overlap, 3) if e else 0.0}


def cascade_fix_pairs(paragraphs: list[str], max_edits: int = DEFAULT_MAX_PAIR_EDITS) -> tuple[list[str], list[dict[str, Any]]]:
    """
    Walk pairs forward. On hard doubles/truncation, drop the later paragraph
    rather than surgical-delete into fragments.
    Returns (paragraphs, pair_reports).
    """
    texts = [p for p in paragraphs if _collapse_ws(p)]
    reports: list[dict[str, Any]] = []
    if len(texts) < 2:
        return texts, reports

    i = 1
    while i < len(texts):
        edits = 0
        while edits <= max_edits:
            result = check_adjacent_paragraphs(texts[i - 1], texts[i])
            reports.append({"pair": [i - 1, i], "direction": "forward", **result, "edit_round": edits})
            if result.get("pass"):
                break
            issue_types = {
                str(iss.get("type") or "")
                for iss in (result.get("issues") or [])
                if isinstance(iss, dict)
            }
            ops = [op for op in result.get("edit_ops") or [] if str(op.get("target") or "later") == "later"]
            if "double" in issue_types or "truncated" in issue_types or any(
                str(op.get("op") or "").lower() in {"rewrite", "drop", "reject"} for op in ops
            ):
                # Prefer dropping the later duplicate over shredding it.
                reports.append(
                    {
                        "pair": [i - 1, i],
                        "direction": "forward_drop",
                        "pass": False,
                        "issues": result.get("issues") or [],
                        "edit_ops": [{"target": "later", "op": "drop"}],
                        "edit_round": edits,
                    }
                )
                texts.pop(i)
                i -= 1
                break
            if not ops:
                break
            edited = apply_edit_ops(texts[i], ops)
            if not edited or looks_garbage_fragment(edited):
                texts.pop(i)
                i -= 1
                break
            texts[i] = edited
            edits += 1
        i += 1

    return texts, reports


def consolidate_scene_heuristic(paragraphs: list[str], ledger: NarrationLedger) -> list[str]:
    """
    Lightweight whole-stack pass without LLM:
    - polish truncations
    - drop garbage fragments and near-duplicates
    Full LLM consolidator plugs in later as consolidate_fn.
    """
    cleaned: list[str] = []
    for para in paragraphs:
        text = polish_paragraph(para, max_chars=560)
        if not text or looks_garbage_fragment(text):
            ledger.record_attempt(
                "consolidate",
                len(cleaned),
                {"drop_garbage": True},
                str(para)[:200],
                "rejected",
                issues=["garbage_or_truncated"],
            )
            continue
        if cleaned:
            # Against every earlier paragraph, not just the previous one. A
            # paragraph that repeats the opening is no better than one that
            # repeats its neighbour, and the model reaches back more than one
            # step whenever a scene runs long.
            tokens = token_set(text)
            duplicate_of = None
            best_overlap = 0.0
            for earlier in cleaned:
                ov = jaccard(token_set(earlier), tokens)
                contained = (len(text) > 40 and text in earlier) or (len(earlier) > 40 and earlier in text)
                if ov >= OVERLAP_DROP or contained:
                    duplicate_of = earlier
                    best_overlap = max(best_overlap, ov)
                    break
                best_overlap = max(best_overlap, ov)
            if duplicate_of is not None:
                ledger.record_attempt(
                    "consolidate",
                    len(cleaned),
                    {"drop_duplicate_of": duplicate_of[:120], "overlap": round(best_overlap, 3)},
                    text,
                    "rejected",
                    issues=["duplicate_of_earlier"],
                )
                continue
            # Strip leading echo of previous opener (first 8 words)
            prev_open = " ".join(cleaned[-1].split()[:8]).lower()
            this_open = " ".join(text.split()[:8]).lower()
            if prev_open and this_open == prev_open and len(text.split()) > 12:
                rest = " ".join(text.split()[8:]).lstrip(" ,;:—-")
                if rest:
                    text = rest[0].upper() + rest[1:] if rest[0].islower() else rest
        cleaned.append(text)
    if not cleaned and paragraphs:
        seed = polish_paragraph(paragraphs[0], max_chars=560)
        cleaned = [seed if seed and not looks_garbage_fragment(seed) else "The scene holds, waiting for the next clear choice."]
    return cleaned


# --- briefs + orchestrator ---------------------------------------------------


# Reply status for every beat after the one that answers the player (playtest
# #5): each beat used to get the player's line as fresh input and answered it
# again.
REPLY_GIVEN_NOTE = (
    "The reply to the player's line is already given in an earlier paragraph. "
    "Do not answer it again or restate it. Move forward: a consequence, a new "
    "pressure, or something else that happens next."
)
_SPEECH_INTENT_RE = re.compile(
    r"^\s*(?:i\s+)?(?:say|says|said|ask|asks|tell|tells|reply|replies|answer|answers|"
    r"shout|shouts|yell|yells|whisper|whispers|call|calls|mutter|mutters)\b",
    re.IGNORECASE,
)
_DSL_DIRECTIVE_LINE_RE = re.compile(r"^\s*(?:FOCUS|CAST|SCENE)\b.*$", re.MULTILINE)


def player_quotes(player_input: str) -> list[str]:
    """What the player said aloud, as typed. These words belong to the player."""
    text = str(player_input or "")
    if text.startswith("__"):
        return []
    # Engine notes ride on the input after a blank line; only the player's own part counts.
    own = re.split(r"\n\s*\n", text, maxsplit=1)[0]
    return [q for q in quoted_spans(own) if len(q.split()) >= 2]


def player_spoke(player_input: str) -> bool:
    text = str(player_input or "")
    if text.startswith("__"):
        return False
    return bool(player_quotes(text)) or bool(_SPEECH_INTENT_RE.match(text))


_PLAYER_SPEECH_VERB_RE = re.compile(
    r"\byou(?:\s+\w+ly)?\s+(?:say|said|tell|told|ask|asked|reply|replied|answer|answered|"
    r"snap|snapped|growl|growled|mutter|muttered|add|added|continue|continued|warn|warned|"
    r"call|called|shout|shouted|whisper|whispered|speak|spoke|spit|spat|sneer|sneered|"
    r"retort|retorted|declare|declared|state|stated|insist|insisted|repeat|repeated|"
    r"press|pressed|begin|began|start|started|finish|finished|let|bark|barked|hiss|hissed|"
    r"suggest|suggested|offer|offered|explain|explained|murmur|murmured|counter|countered)\b"
    r"|\byour\s+(?:words|voice|question|retort|reply|threat|remark)\b",
    re.IGNORECASE,
)


def _is_player_line(span: str, quotes: list[str]) -> bool:
    """A quoted line that carries the player's own words."""
    if not quotes:
        return False
    key = _speech_key(span)
    for quote in quotes:
        runs = _speech_runs(quote)
        if runs and runs & _speech_runs(span):
            return True
        qkey = _speech_key(quote)
        if not runs and len(qkey.split()) >= 2 and qkey in key:
            return True
    return False


def _slice_has_npc_speech(piece: str, quotes: list[str]) -> bool:
    """Someone other than the player speaks in this part of the draft."""
    for unit in speech_units(piece):
        spans = quoted_spans(unit)
        if not spans or all(_is_player_line(s, quotes) for s in spans):
            continue
        if _PLAYER_SPEECH_VERB_RE.search(unit):
            continue
        return True
    return False


def player_words_misattributed(text: str, quotes: list[str]) -> bool:
    """
    True when a paragraph puts the player's quoted words in a quotation that is
    not given to the player (playtest #6: the player's threat came out of an
    NPC's mouth). The player saying them -- "you say", "you snap" -- is fine.
    """
    if not quotes:
        return False
    units = speech_units(_collapse_ws(str(text or "").replace("\n", " ")))
    for index, unit in enumerate(units):
        for span in quoted_spans(unit):
            if not _is_player_line(span, quotes):
                continue
            around = unit + " " + (units[index - 1] if index else "")
            if not _PLAYER_SPEECH_VERB_RE.search(around):
                return True
    return False


def entity_roster(context: dict[str, Any], draft: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """
    code -> name and kind for every entity the writer may tag.

    A bare code list (playtest #3) let the writer put an item code on a place
    it had just invented; a code it cannot read is a code it will misuse.
    Entries without a name are left out.
    """
    rows: list[dict[str, Any]] = []
    index: dict[str, dict[str, Any]] = {}

    def add(code: Any, name: Any, kind: str, role: Any = "") -> None:
        c = str(code or "").strip()
        n = str(name or "").strip()
        r = str(role or "").strip()
        if not c or not n or n.upper() == c.upper():
            return
        key = c.upper()
        row = index.get(key)
        if row is not None:
            if r and not row.get("role"):
                row["role"] = r
            return
        row = {"code": c, "name": n, "kind": kind}
        if r:
            row["role"] = r
        index[key] = row
        rows.append(row)

    for npc in collect_local_npcs(context):
        add(npc.get("code"), npc.get("name"), "person", npc.get("role"))
    draft = draft if isinstance(draft, dict) else {}
    for npc in draft.get("npcs") or []:
        if isinstance(npc, dict):
            add(npc.get("code"), npc.get("name"), "person", npc.get("role"))
    loc = context.get("current_location") if isinstance(context.get("current_location"), dict) else {}
    add(loc.get("code"), loc.get("name"), "place (where the player is)")
    for place in context.get("locations") or []:
        if isinstance(place, dict):
            add(place.get("code"), place.get("name"), "place")
    for place in draft.get("locations") or []:
        if isinstance(place, dict):
            add(place.get("code"), place.get("name"), "place")
    for item in collect_inventory(context):
        add(item.get("code"), item.get("name"), "item the player carries")
    for event in collect_relevant_events(context):
        add(event.get("code"), event.get("title") or event.get("name"), "event")
    return rows


def draft_narration_text(draft: dict[str, Any] | None) -> str:
    if not isinstance(draft, dict):
        return ""
    text = str(draft.get("narration") or "").strip()
    if not text:
        segments = draft.get("narration_segments") or []
        text = "\n\n".join(
            str(seg.get("text") or "") for seg in segments if isinstance(seg, dict)
        ).strip()
    text = _DSL_DIRECTIVE_LINE_RE.sub("", text)
    return _collapse_ws(text)


def draft_slices(text: str, count: int) -> list[str]:
    """Cut the draft into `count` consecutive slices, one per beat, never inside a quotation."""
    count = max(1, int(count or 1))
    units: list[str] = []
    for block in _BLOCK_SPLIT_RE.split(str(text or "")):
        units.extend(speech_units(block))
    units = [u for u in units if u.strip()]
    if not units:
        return [""] * count
    total = sum(len(u) for u in units)
    slices: list[list[str]] = [[] for _ in range(count)]
    running = 0
    for unit in units:
        # Assign by where the unit starts in the draft, so slices follow its order.
        slot = min(count - 1, int(running * count / max(1, total)))
        slices[slot].append(unit)
        running += len(unit)
    return [" ".join(part).strip() for part in slices]


def scene_facts(
    context: dict[str, Any],
    draft: dict[str, Any] | None,
    player_input: str,
    roster: list[dict[str, Any]],
) -> dict[str, Any]:
    """Who is who, where, and who said what: the draft's facts, for every beat."""
    loc = context.get("current_location") if isinstance(context.get("current_location"), dict) else {}
    facts: dict[str, Any] = {"where": str(loc.get("name") or "")}
    keeper = loc.get("keeper") if isinstance(loc.get("keeper"), dict) else {}
    if loc.get("inside_venue") and keeper.get("name"):
        facts["keeper"] = str(keeper["name"])
    # Whose place is whose (playtest #16): Aria the baker sold the herbs in
    # Elara's shop. The engine's workplace record rides on each cast entry.
    here_id = int(loc.get("id") or 0)
    workplaces = {
        str(npc.get("code") or "").upper(): npc
        for npc in collect_local_npcs(context)
        if isinstance(npc, dict) and npc.get("code")
    }
    cast: list[dict[str, Any]] = []
    seen: set[str] = set()
    low_draft = draft_narration_text(draft).lower()
    for row in roster:
        # With a draft, the cast is who the draft put in the scene; a bystander
        # on the location record is not handed to the writer to stage.
        if row.get("kind") == "person" and (not low_draft or row["name"].lower() in low_draft):
            entry = {"name": row["name"], "code": row["code"]}
            if row.get("role"):
                entry["role"] = row["role"]
            record = workplaces.get(str(row["code"]).upper()) or {}
            workplace_id = int(record.get("workplace_id") or 0)
            if workplace_id and workplace_id == here_id:
                entry["works_here"] = True
            elif record.get("workplace"):
                entry["works_at"] = str(record["workplace"])
            cast.append(entry)
            seen.add(row["name"].lower())
    draft = draft if isinstance(draft, dict) else {}
    for npc in draft.get("npcs") or []:
        if not isinstance(npc, dict):
            continue
        name = str(npc.get("name") or "").strip()
        if name and name.lower() not in seen:
            entry = {"name": name}
            if npc.get("role"):
                entry["role"] = str(npc.get("role"))
            cast.append(entry)
            seen.add(name.lower())
    if cast:
        facts["cast"] = cast[:8]
    draft_player = draft.get("player") if isinstance(draft.get("player"), dict) else {}
    if draft_player.get("move_to_location"):
        facts["player_moves_to"] = str(draft_player["move_to_location"])
    else:
        inside = _draft_goes_inside(context, draft)
        stays = "" if inside else _player_stays_in(context, draft, player_input)
        if inside:
            facts["player_goes_inside"] = inside
        if stays:
            facts["player_stays_in"] = stays
    spoken: list[dict[str, str]] = [
        {"speaker": "player", "words": _trim(q, 300)} for q in player_quotes(player_input)
    ]
    names = {row["code"].upper(): row["name"] for row in roster}
    names.update({row["name"].upper(): row["name"] for row in roster})
    for convo in draft.get("conversations") or []:
        if not isinstance(convo, dict):
            continue
        words = str(convo.get("topic") or convo.get("summary") or "").strip()
        code = str(convo.get("npc_code") or "").strip().upper()
        speaker = names.get(code) or str(convo.get("npc_name") or "").strip()
        if words and speaker:
            spoken.append({"speaker": speaker, "words": _trim(words, 300)})
    if spoken:
        facts["spoken"] = spoken[:8]
    return facts


def _draft_goes_inside(context: dict[str, Any], draft: dict[str, Any]) -> str:
    """
    "the shop" when the draft's prose takes the player into a building with no MOVE, else "".

    Playtest #16: the draft walked the player into a herb shop without a MOVE.
    The engine makes that building a place from the final prose
    (app/world.py _venue_shown_in_prose), so the writer keeps the player going
    inside instead of being told they stay in the street.
    """
    loc = context.get("current_location") if isinstance(context.get("current_location"), dict) else {}
    if loc.get("inside_venue"):
        return ""
    try:
        from app.venues import entry_in_prose

        shown = entry_in_prose(draft_narration_text(draft))
    except Exception:
        return ""
    return f"the {shown['noun']}" if shown else ""


def _player_stays_in(context: dict[str, Any], draft: dict[str, Any], player_input: str) -> str:
    """
    The place the player is still in when this turn ends, or "" when the turn may move them.

    Playtest #20: a travel-shaped line with no MOVE and no place the engine
    could resolve left the player standing in Eldoria's Edge while the prose
    walked them down an alley and into a shop. The engine keeps them here
    unless the draft moves them, the line names a known place, or the line
    walks through a doorway (app/world.py resolve_movement), so the writer
    is told the same.
    """
    loc = context.get("current_location") if isinstance(context.get("current_location"), dict) else {}
    name = str(loc.get("name") or "").strip()
    if not name:
        return ""
    player = draft.get("player") if isinstance(draft.get("player"), dict) else {}
    if player.get("move_to_location") or player.get("move_to_location_code") or draft.get("map_walk"):
        return ""
    if any(isinstance(row, dict) and row.get("name") for row in draft.get("locations") or []):
        return ""
    text = re.split(r"\n\s*\n", str(player_input or ""), maxsplit=1)[0].lower()
    if str(player_input or "").startswith("__"):
        return ""
    try:
        from app.world import venue_move_intent

        if venue_move_intent(text):
            return ""
    except Exception:
        return ""
    contract = context.get("movement_contract") if isinstance(context.get("movement_contract"), dict) else {}
    places = [str(p) for p in contract.get("known_places") or [] if str(p or "").strip()]
    places += [str(v.get("name") or "") for v in contract.get("venues_here") or [] if isinstance(v, dict)]
    if any(len(p) >= 3 and p.lower() in text for p in places):
        return ""
    return name


def build_paragraph_briefs(
    budget: dict[str, Any],
    context: dict[str, Any],
    player_input: str,
    ledger: NarrationLedger,
    ops_summary: str = "",
    draft: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    roles = list(budget.get("beat_roles") or _beat_roles(int(budget.get("paragraphs") or 1)))
    loc = ""
    current = context.get("current_location")
    if isinstance(current, dict):
        loc = str(current.get("name") or current.get("code") or "")
    draft_text = draft_narration_text(draft)
    state_ops = _state_ops_only(ops_summary)
    must_pool = _must_cover_candidates(context, player_input, state_ops, draft_text)
    roster = entity_roster(context, draft)
    may_mention = roster[:14]
    facts = scene_facts(context, draft, player_input, roster)
    slices = draft_slices(draft_text, len(roles)) if draft_text else [""] * len(roles)
    quotes = player_quotes(player_input)
    real_input = bool(player_input) and not str(player_input).startswith("__")
    # The beat that answers the player: the first slice where someone other
    # than the player speaks, else the first beat.
    answer_index = 0
    if real_input:
        npc_lines = [i for i, piece in enumerate(slices) if _slice_has_npc_speech(piece, quotes)]
        player_line = [i for i, piece in enumerate(slices) if any(_is_player_line(s, quotes) for s in quoted_spans(piece))]
        if npc_lines:
            answer_index = npc_lines[0]
        elif player_line:
            # Nobody answers aloud: the beat after the player's line carries the reaction.
            answer_index = min(len(roles) - 1, player_line[0] + 1)
    spoke = player_spoke(player_input)
    # Who the player is talking to, decided by the engine (app/conversation.py).
    from app.conversation import writer_view

    talk = writer_view(context.get("conversation_turn"))
    answerers = ", ".join((talk or {}).get("who_answers") or [])
    # What the player is in the middle of (app/scene_thread.py, playtest #20).
    from app.scene_thread import writer_view as thread_writer_view

    thread = thread_writer_view(context.get("scene_thread"))
    briefs: list[dict[str, Any]] = []
    for index, role in enumerate(roles):
        cover = []
        if real_input and index == answer_index:
            to = f" (the player is talking to {answerers}; {answerers} answers)" if answerers else ""
            cover.append(f"Respond to player intent{to}: {_trim(player_input, 160)}")
        if must_pool:
            cover.append(must_pool[index % len(must_pool)])
        if role in {"pressure", "hook"} and real_input:
            cover.append(
                "End on a consequence, new pressure, or concrete detail. "
                "Do not restate the player's options as a menu, and do not decide anything for the player: "
                "end on the situation as it stands."
            )
        brief: dict[str, Any] = {
            "beat_index": index + 1,
            "beat_count": len(roles),
            "beat_role": role,
            "must_cover": cover,
            "may_mention": may_mention,
            "scene_facts": facts,
            "forbidden_repeat": ledger.forbidden_repeats()[-20:],
            "previous_attempt_texts": ledger.previously_attempted_texts(index)[:4],
            "player_intent": _trim(player_input, 400),
            "location_now": loc,
            "ops_summary": _trim(state_ops, 400),
            "model_limits": {
                "max_tokens": int(budget.get("max_tokens_per_paragraph") or 200),
                "max_chars": int((budget.get("chars_per_paragraph") or {}).get("max") or 420),
                "min_chars": int((budget.get("chars_per_paragraph") or {}).get("min") or 200),
            },
        }
        if draft_text:
            brief["scene_draft"] = _trim(draft_text, 1400)
            brief["draft_slice"] = slices[index]
        if quotes:
            brief["player_speech"] = [{"speaker": "player", "words": _trim(q, 300)} for q in quotes]
        if talk:
            brief["conversation"] = talk
        if thread:
            brief["scene_thread"] = thread
        if spoke and index > answer_index:
            brief["reply_status"] = REPLY_GIVEN_NOTE
            brief["player_intent"] = "Already answered above: " + _trim(player_input, 200)
        briefs.append(brief)
    return briefs


def _state_ops_only(ops_summary: str) -> str:
    """The ops summary minus its turn_summary echo, which is prose and not an op."""
    parts = [p.strip() for p in str(ops_summary or "").split("; ")]
    return "; ".join(p for p in parts if p and not p.startswith("summary:"))


def _must_cover_candidates(
    context: dict[str, Any],
    player_input: str,
    ops_summary: str,
    draft_text: str = "",
) -> list[str]:
    items: list[str] = []
    if ops_summary:
        items.append(f"Honor state ops: {_trim(ops_summary, 160)}")
    loc = context.get("current_location") if isinstance(context.get("current_location"), dict) else {}
    if loc.get("name"):
        items.append(f"Ground the scene in {loc.get('name')}.")
    low_draft = draft_text.lower()
    for npc in collect_local_npcs(context)[:4]:
        name = str(npc.get("name") or "").strip()
        # With a draft, only people the draft put in this scene: a bystander on
        # the location record is not a beat the writer has to stage.
        if name and (not draft_text or name.lower() in low_draft):
            items.append(f"NPC presence: {name}")
    for event in collect_relevant_events(context)[:4]:
        if event.get("title"):
            items.append(f"Event pressure: {event.get('title')}")
    return items


def _entity_codes(context: dict[str, Any]) -> list[str]:
    codes: list[str] = []
    for npc in collect_local_npcs(context):
        if npc.get("code"):
            codes.append(str(npc["code"]))
    for place in context.get("locations") or []:
        if isinstance(place, dict) and place.get("code"):
            codes.append(str(place["code"]))
    loc = context.get("current_location") if isinstance(context.get("current_location"), dict) else {}
    if loc.get("code"):
        codes.append(str(loc["code"]))
    for item in collect_inventory(context):
        if item.get("code"):
            codes.append(str(item["code"]))
    for event in collect_relevant_events(context):
        if event.get("code"):
            codes.append(str(event["code"]))
    # de-dupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for code in codes:
        if code not in seen:
            seen.add(code)
            out.append(code)
    return out


def default_paragraph_writer(brief: dict[str, Any], previous_paragraph: str, ledger: NarrationLedger) -> str:
    """
    Deterministic placeholder writer used when no LLM callback is supplied.
    Real wiring will pass an LLM writer; tests and dual-role benches can use this.
    """
    role = str(brief.get("beat_role") or "act")
    loc = str(brief.get("location_now") or "the area")
    intent = str(brief.get("player_intent") or "").strip()
    cover = "; ".join(str(x) for x in (brief.get("must_cover") or [])[:2])
    forbidden = ledger.forbidden_repeats()
    max_chars = int((brief.get("model_limits") or {}).get("max_chars") or 420)

    templates = {
        "establish": f"At {loc}, the immediate scene settles into usable detail—routes, watchers, and pressure the player can act on.",
        "act": f"Action takes hold in {loc}." + (f" Intent: {intent}." if intent and not intent.startswith("__") else ""),
        "react": f"The place answers: a shift in posture, a sound, or an NPC response that confirms the world noticed.",
        "consequence": f"A concrete consequence lands without undoing prior facts—cost, opportunity, or a new constraint.",
        "pressure": f"Pressure tightens around {loc}: time, witnesses, or a new constraint lands.",
        "hook": f"A concrete detail in {loc} remains unresolved — not a menu of options, a fact the player can act on.",
        "choice": f"A concrete detail in {loc} remains unresolved — not a menu of options, a fact the player can act on.",
    }
    text = templates.get(role, templates["act"])
    if cover:
        text += f" Focus: {cover}."
    if previous_paragraph:
        # avoid starting with same 6 words
        prev_start = " ".join(previous_paragraph.split()[:6]).lower()
        if " ".join(text.split()[:6]).lower() == prev_start:
            text = "Then " + text[0].lower() + text[1:] if text else text
    for fact in forbidden:
        # crude de-dupe: if a full forbidden sentence fragment appears, drop a clause
        frag = fact[:48]
        if frag and frag.lower() in text.lower():
            text = text.replace(frag, "").replace(frag.lower(), "")
    text = _collapse_ws(text)
    return text[:max_chars]


def run_narration_pipeline(
    context: dict[str, Any],
    player_input: str,
    *,
    config: dict[str, Any] | None = None,
    ops_summary: str = "",
    turn_number: int = 0,
    writer: Callable[[dict[str, Any], str, NarrationLedger], str] | None = None,
    consolidator: Callable[[list[str], NarrationLedger], list[str]] | None = None,
    ledger_path: Path | None = None,
    draft: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build narration_segments via adaptive budget + cascade checks + ledger.

    `writer(brief, previous_paragraph, ledger) -> text`
    When writer is None, uses deterministic default_paragraph_writer (no LLM).
    """
    budget = plan_paragraph_budget(context, player_input, config)
    # Prefer caller turn_number; if missing, infer from context history.
    resolved_turn = int(turn_number or 0) or infer_turn_number(context)
    ledger = NarrationLedger(turn=resolved_turn, player_input=player_input, budget=budget)
    briefs = build_paragraph_briefs(budget, context, player_input, ledger, ops_summary, draft=draft)
    quotes = player_quotes(player_input)
    write = writer or default_paragraph_writer
    max_edits = _env_int("AI_RPG_NARRATION_PIPELINE_MAX_EDITS", DEFAULT_MAX_PAIR_EDITS)
    use_consolidator = consolidator is not None and not budget.get("skip_consolidator")
    max_chars = int((budget.get("chars_per_paragraph") or {}).get("max") or 480)

    try:
        from app.generation_progress import set_preview, update as progress_update
    except Exception:  # pragma: no cover
        def progress_update(*_a: Any, **_k: Any) -> None:
            return None

        def set_preview(*_a: Any, **_k: Any) -> None:
            return None

    total_beats = max(1, len(briefs))
    progress_update(
        "narration",
        f"Writing scene in {total_beats} paragraph beat(s)…",
        step=0,
        total_steps=total_beats + 1,
        line=f"Narration pipeline: {total_beats} beats ({budget.get('tier')})",
    )

    paragraphs: list[str] = []
    for brief in briefs:
        index = int(brief["beat_index"]) - 1
        role = str(brief.get("beat_role") or "act")
        previous = paragraphs[-1] if paragraphs else ""
        # refresh forbidden from ledger
        brief["forbidden_repeat"] = ledger.forbidden_repeats()[-20:]
        if paragraphs:
            brief["previous_paragraph_tail"] = previous[-400:]
        progress_update(
            "narration_write",
            f"Drafting paragraph {index + 1}/{total_beats} ({role})…",
            step=index + 1,
            total_steps=total_beats + 1,
            line=f"Writing beat {index + 1}/{total_beats}: {role}",
        )

        text = polish_paragraph(write(brief, previous, ledger), max_chars=max_chars)
        ledger.record_attempt("write", index, brief, text, "proposed")

        # Truncated / garbage first drafts: one rewrite with a stronger finish rule.
        if not text or looks_garbage_fragment(text) or looks_truncated(text):
            rewrite_brief = dict(brief)
            rewrite_brief["rules_extra"] = [
                "Finish every sentence with period/question/exclamation.",
                "Do not cut off mid-word.",
                "Write complete prose only.",
            ]
            retry = polish_paragraph(write(rewrite_brief, previous, ledger), max_chars=max_chars)
            ledger.record_attempt("write_retry_truncated", index, rewrite_brief, retry, "proposed")
            if retry and not looks_garbage_fragment(retry):
                text = retry

        # Speaker and re-answer checks (playtest #5, #6). One rewrite with the
        # problem named; a second failure loses the beat, never the turn.
        problems = _beat_speech_problems(paragraphs, text, quotes)
        if problems and text:
            rewrite_brief = dict(brief)
            rewrite_brief["rules_extra"] = list(brief.get("rules_extra") or []) + problems
            retry = polish_paragraph(write(rewrite_brief, previous, ledger), max_chars=max_chars)
            ledger.record_attempt(
                "write_retry_speech", index, rewrite_brief, retry, "proposed", issues=problems
            )
            if retry and not looks_garbage_fragment(retry) and not _beat_speech_problems(paragraphs, retry, quotes):
                text = retry
            elif quotes and player_words_misattributed(text, quotes):
                ledger.record_attempt(
                    "drop_beat", index, {"role": role}, text, "rejected",
                    issues=["player_words_given_to_another_speaker"],
                )
                continue
            # A re-answer that survives the retry is trimmed by the speech pass
            # below and again on the assembled turn.

        if paragraphs:
            edits = 0
            while edits <= max_edits:
                check = check_adjacent_paragraphs(paragraphs[-1], text)
                ledger.record_attempt(
                    "adjacent_check",
                    index,
                    {"earlier_tail": paragraphs[-1][-200:], "later": text},
                    json.dumps(check.get("issues") or [], ensure_ascii=True),
                    "accepted" if check.get("pass") else "rejected",
                    issues=[i.get("detail", "") for i in check.get("issues") or [] if isinstance(i, dict)],
                    edit_ops=list(check.get("edit_ops") or []),
                )
                if check.get("pass"):
                    break
                issue_types = {
                    str(i.get("type") or "")
                    for i in (check.get("issues") or [])
                    if isinstance(i, dict)
                }
                ops = [op for op in check.get("edit_ops") or [] if str(op.get("target") or "later") == "later"]
                needs_rewrite = "double" in issue_types or "truncated" in issue_types or any(
                    str(op.get("op") or "").lower() in {"rewrite", "drop", "reject"} for op in ops
                )
                if needs_rewrite:
                    # Full rewrite instead of delete_span shredding.
                    rewrite_brief = dict(brief)
                    rewrite_brief["forbidden_repeat"] = (
                        list(ledger.forbidden_repeats())[:20]
                        + [paragraphs[-1][:160], text[:160]]
                    )
                    rewrite_brief["rules_extra"] = [
                        "Do not restate the previous paragraph.",
                        "Advance the scene with new sensory detail or consequence.",
                        "Finish every sentence cleanly.",
                    ]
                    rewritten = polish_paragraph(
                        write(rewrite_brief, paragraphs[-1], ledger),
                        max_chars=max_chars,
                    )
                    ledger.record_attempt(
                        "rewrite",
                        index,
                        {"reason": sorted(issue_types), "ops": ops},
                        rewritten,
                        "proposed",
                        edit_ops=ops,
                    )
                    if rewritten and not looks_garbage_fragment(rewritten):
                        # Accept rewrite only if overlap improved or unique enough
                        ov = jaccard(token_set(paragraphs[-1]), token_set(rewritten))
                        if ov < OVERLAP_DROP and rewritten != text:
                            text = rewritten
                            edits += 1
                            continue
                    # Cannot salvage: skip this beat rather than publish shreds
                    text = ""
                    break
                if not ops:
                    break
                edited = apply_edit_ops(text, ops)
                ledger.record_attempt("edit", index, ops, edited, "proposed", edit_ops=ops)
                if not edited or looks_garbage_fragment(edited):
                    text = ""
                    break
                text = edited
                edits += 1

        text = polish_paragraph(text, max_chars=max_chars)
        if not text or looks_garbage_fragment(text):
            ledger.record_attempt(
                "drop_beat",
                index,
                {"role": role},
                text or "",
                "rejected",
                issues=["unusable_after_checks"],
            )
            progress_update(
                "narration_drop",
                f"Dropped weak beat {index + 1}; continuing…",
                step=index + 1,
                line=f"Dropped unusable beat {index + 1} ({role})",
            )
            continue

        # Final overlap guard before commit
        if paragraphs:
            ov = jaccard(token_set(paragraphs[-1]), token_set(text))
            if ov >= OVERLAP_DROP:
                ledger.record_attempt(
                    "drop_overlap",
                    index,
                    {"overlap": round(ov, 3)},
                    text,
                    "rejected",
                    issues=[f"overlap={ov:.0%}"],
                )
                continue

        if paragraphs:
            trimmed, speech_dropped = drop_repeated_speech(paragraphs + [text])
            if speech_dropped:
                ledger.record_attempt(
                    "drop_repeated_speech", index, {"dropped": speech_dropped[:4]}, trimmed[-1], "accepted",
                    issues=["spoken_line_already_said"],
                )
                text = polish_paragraph(trimmed[-1], max_chars=max_chars)
                if not text or looks_garbage_fragment(text):
                    continue

        paragraphs.append(text)
        first = re.split(r"(?<=[.!?])\s+", text.strip())[0] if text.strip() else ""
        if first and not looks_truncated(first):
            ledger.add_said_fact(first, index)
        # Spoken lines too: with only first sentences on the list, the writer
        # never saw that it had already given the reply (playtest #5).
        for spoken in quoted_spans(text):
            if len(spoken.split()) >= 3:
                ledger.add_said_fact(f'"{spoken}"', index)
        set_preview(text, append_paragraph=True)
        progress_update(
            "narration_accept",
            f"Accepted paragraph {len(paragraphs)} ({role}).",
            step=index + 1,
            line=f"Accepted beat {index + 1}: {_trim(text, 96)}",
        )

        # cascade: re-check pairs; drop garbage after cascade edits
        if len(paragraphs) >= 2:
            paragraphs, pair_reports = cascade_fix_pairs(paragraphs, max_edits=max_edits)
            paragraphs = [
                p
                for p in (polish_paragraph(x, max_chars=max_chars) for x in paragraphs)
                if p and not looks_garbage_fragment(p)
            ]
            for report in pair_reports[-3:]:
                ledger.record_attempt(
                    "cascade",
                    (report.get("pair") or [None, None])[-1],
                    report,
                    "",
                    "accepted" if report.get("pass") else "rejected",
                    issues=[i.get("detail", "") for i in report.get("issues") or [] if isinstance(i, dict)],
                )

    progress_update(
        "narration_consolidate",
        "Polishing scene continuity…",
        step=total_beats + 1,
        total_steps=total_beats + 1,
        line="Consolidating paragraphs…",
    )
    if use_consolidator:
        paragraphs = consolidator(paragraphs, ledger)  # type: ignore[misc]
        ledger.record_attempt("consolidate", None, {"mode": "callback"}, "\n\n".join(paragraphs)[:500], "accepted")
        paragraphs = consolidate_scene_heuristic(paragraphs, ledger)
    elif budget.get("skip_consolidator"):
        ledger.record_attempt(
            "consolidate",
            None,
            {"skipped": True, "reason": "low_density_or_two_para", "paragraphs": len(paragraphs), "density": (budget.get("density") or {}).get("score")},
            "",
            "accepted",
            issues=["consolidator_skipped"],
        )
        paragraphs = consolidate_scene_heuristic(paragraphs, ledger)
    elif _env_bool("AI_RPG_NARRATION_PIPELINE_CONSOLIDATE", True):
        paragraphs = consolidate_scene_heuristic(paragraphs, ledger)

    paragraphs = [
        p
        for p in (polish_paragraph(x, max_chars=max_chars) for x in paragraphs)
        if p and not looks_garbage_fragment(p)
    ]
    if not paragraphs:
        paragraphs = ["The scene holds, waiting for the next clear choice."]

    set_preview("\n\n".join(paragraphs), append_paragraph=False)
    ledger.final_paragraphs = paragraphs
    ledger.final_narration = "\n\n".join(paragraphs)
    for attempt in ledger.attempts:
        if attempt.kind == "write" and attempt.status == "proposed":
            # mark last write per para as accepted if present in final
            if any(_norm(attempt.output_text[:80]) in _norm(p) or _norm(p[:80]) in _norm(attempt.output_text) for p in paragraphs):
                attempt.status = "accepted"
            else:
                attempt.status = "superseded"

    if ledger_path is None:
        trace_dir = Path(os.getenv("AI_RPG_MODEL_TRACE_DIR") or (Path("data") / "model_traces"))
        ledger_path = trace_dir / f"turn-{resolved_turn:06d}-narration-ledger.json"
    save_ledger(ledger, Path(ledger_path))

    segments = [{"label": "paragraph", "text": p} for p in paragraphs]
    return {
        "narration_segments": segments,
        "narration": ledger.final_narration,
        "budget": budget,
        "ledger_path": str(ledger_path),
        "ledger": ledger.to_dict(),
        "pipeline_version": PIPELINE_VERSION,
        "consolidator_skipped": bool(budget.get("skip_consolidator")),
    }


def _beat_speech_problems(paragraphs: list[str], text: str, quotes: list[str]) -> list[str]:
    """Rules to add on a rewrite when a beat misplaces or repeats speech."""
    problems: list[str] = []
    if quotes and player_words_misattributed(text, quotes):
        problems.append(
            "The words in player_speech are the player's own. Only the player (you) says them; "
            "no other character speaks them."
        )
    if paragraphs:
        earlier = [s for p in paragraphs for s in quoted_spans(p)]
        if earlier and any(speech_repeats(earlier, " ".join(quoted_spans(u))) for u in speech_units(text) if quoted_spans(u)):
            problems.append(
                "A spoken line here restates one from an earlier paragraph. "
                "Do not answer the same thing again; move the scene forward."
            )
    return problems


def infer_turn_number(context: dict[str, Any]) -> int:
    """Next turn index for ledger naming: max known turn in context + 1 (min 1)."""
    best = 0
    for key in ("turn", "current_turn"):
        try:
            best = max(best, int(context.get(key)))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            pass
    pacing = context.get("pacing")
    if isinstance(pacing, dict):
        try:
            best = max(best, int(pacing.get("turn") or 0))
        except (TypeError, ValueError):
            pass
    for collection_key in ("turn_summaries", "model_logs", "history", "journal"):
        for row in context.get(collection_key) or []:
            if isinstance(row, dict):
                try:
                    best = max(best, int(row.get("turn") or 0))
                except (TypeError, ValueError):
                    pass
    plan = context.get("turn_plan") if isinstance(context.get("turn_plan"), dict) else {}
    try:
        best = max(best, int(plan.get("turn") or 0))
    except (TypeError, ValueError):
        pass
    return max(1, best + 1)


# --- small utils -------------------------------------------------------------


def _digest(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=True, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _trim(text: str, n: int) -> str:
    text = str(text or "")
    return text if len(text) <= n else text[: max(0, n - 1)].rstrip() + "…"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _collapse_ws(text: str) -> str:
    return re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", text or "")).strip()


def ops_summary_from_turn(turn: dict[str, Any] | None) -> str:
    """Compact non-prose summary of state deltas for paragraph briefs."""
    if not isinstance(turn, dict):
        return ""
    parts: list[str] = []
    player = turn.get("player") if isinstance(turn.get("player"), dict) else {}
    if player.get("move_to_location"):
        parts.append(f"move:{player.get('move_to_location')}")
    for key in ("health_delta", "xp_delta", "gold_delta", "karma_delta"):
        try:
            val = int(player.get(key) or 0)
        except (TypeError, ValueError):
            val = 0
        if val:
            parts.append(f"{key}={val}")
    for item in (turn.get("inventory_changes") or [])[:6]:
        if isinstance(item, dict) and item.get("name"):
            qty = item.get("quantity_delta", item.get("quantity"))
            parts.append(f"item:{item.get('name')}*{qty}")
    for npc in (turn.get("npcs") or [])[:4]:
        if isinstance(npc, dict) and npc.get("name"):
            parts.append(f"npc:{npc.get('name')}")
    for event in (turn.get("events") or [])[:4]:
        if isinstance(event, dict) and event.get("title"):
            parts.append(f"event:{event.get('title')}")
    if turn.get("turn_summary"):
        parts.append(f"summary:{_trim(str(turn.get('turn_summary')), 120)}")
    return "; ".join(parts)[:500]


def parse_consolidated_paragraphs(raw: str, expected: int) -> list[str]:
    """Parse consolidator output: ===P1=== blocks or blank-line paragraphs."""
    text = (raw or "").strip()
    if not text:
        return []
    blocks = re.split(r"\n\s*===P\d+===\s*\n", "\n" + text)
    blocks = [_collapse_ws(b) for b in blocks if _collapse_ws(b)]
    if len(blocks) >= 2:
        return blocks[: max(1, expected + 1)]
    # labeled lines fallback
    labeled = re.findall(r"===P\d+===\s*(.*?)(?=\n===P\d+===|\Z)", text, flags=re.S | re.I)
    labeled = [_collapse_ws(b) for b in labeled if _collapse_ws(b)]
    if labeled:
        return labeled[: max(1, expected + 1)]
    paras = [_collapse_ws(p) for p in re.split(r"\n\s*\n", text) if _collapse_ws(p)]
    return paras[: max(1, expected + 1)] if paras else [text[:800]]
