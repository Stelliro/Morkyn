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
        for key in ("ollama_model", "gguf_model_path", "model", "model_name")
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
    probe = {
        "id": npc.get("location_id"),
        "code": npc.get("location_code") or npc.get("code"),
        "name": npc.get("location_name"),
    }
    # location_code on npc is the place code; code on npc is entity code — prefer location_* fields.
    probe_keys = set()
    if npc.get("location_id") is not None:
        probe_keys.add(f"id:{npc.get('location_id')}")
    if npc.get("location_code"):
        probe_keys.add(f"code:{str(npc.get('location_code')).strip().upper()}")
    if npc.get("location_name"):
        probe_keys.add(f"name:{str(npc.get('location_name')).strip().lower()}")
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

    # Prompt-context working sets
    for key in ("local_npcs", "nearby_npcs"):
        for npc in context.get(key) or []:
            _add(npc)
    action = context.get("action_context") if isinstance(context.get("action_context"), dict) else {}
    for key in ("local_npcs", "nearby_npcs", "npcs"):
        for npc in action.get(key) or []:
            _add(npc)
    working = context.get("working_set") if isinstance(context.get("working_set"), dict) else {}
    for npc in working.get("npcs") or []:
        _add(npc)

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
    if count <= 1:
        return ["act"]
    if count == 2:
        return ["establish", "choice"]
    if count == 3:
        return ["establish", "act", "choice"]
    if count == 4:
        return ["establish", "act", "consequence", "choice"]
    if count == 5:
        return ["establish", "act", "react", "consequence", "choice"]
    return ["establish", "act", "react", "consequence", "pressure", "choice"][:count]


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
            ov = jaccard(token_set(cleaned[-1]), token_set(text))
            if ov >= OVERLAP_DROP or (len(text) > 40 and text in cleaned[-1]) or (len(cleaned[-1]) > 40 and cleaned[-1] in text):
                ledger.record_attempt(
                    "consolidate",
                    len(cleaned),
                    {"drop_duplicate_of": cleaned[-1][:120], "overlap": round(ov, 3)},
                    text,
                    "rejected",
                    issues=["duplicate_of_previous"],
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


def build_paragraph_briefs(
    budget: dict[str, Any],
    context: dict[str, Any],
    player_input: str,
    ledger: NarrationLedger,
    ops_summary: str = "",
) -> list[dict[str, Any]]:
    roles = list(budget.get("beat_roles") or _beat_roles(int(budget.get("paragraphs") or 1)))
    loc = ""
    current = context.get("current_location")
    if isinstance(current, dict):
        loc = str(current.get("name") or current.get("code") or "")
    must_pool = _must_cover_candidates(context, player_input, ops_summary)
    briefs: list[dict[str, Any]] = []
    for index, role in enumerate(roles):
        cover = []
        if must_pool:
            cover.append(must_pool[index % len(must_pool)])
        if role == "choice" and player_input:
            cover.append("Leave at least one concrete next choice open.")
        briefs.append(
            {
                "beat_index": index + 1,
                "beat_count": len(roles),
                "beat_role": role,
                "must_cover": cover,
                "may_mention": _entity_codes(context)[:12],
                "forbidden_repeat": ledger.forbidden_repeats()[:20],
                "previous_attempt_texts": ledger.previously_attempted_texts(index)[:4],
                "player_intent": _trim(player_input, 400),
                "location_now": loc,
                "ops_summary": _trim(ops_summary, 400),
                "model_limits": {
                    "max_tokens": int(budget.get("max_tokens_per_paragraph") or 200),
                    "max_chars": int((budget.get("chars_per_paragraph") or {}).get("max") or 420),
                    "min_chars": int((budget.get("chars_per_paragraph") or {}).get("min") or 200),
                },
            }
        )
    return briefs


def _must_cover_candidates(context: dict[str, Any], player_input: str, ops_summary: str) -> list[str]:
    items: list[str] = []
    if player_input and not player_input.startswith("__"):
        items.append(f"Respond to player intent: {_trim(player_input, 160)}")
    if ops_summary:
        items.append(f"Honor state ops: {_trim(ops_summary, 160)}")
    loc = context.get("current_location") if isinstance(context.get("current_location"), dict) else {}
    if loc.get("name"):
        items.append(f"Ground the scene in {loc.get('name')}.")
    for npc in collect_local_npcs(context)[:4]:
        if npc.get("name"):
            items.append(f"NPC presence: {npc.get('name')}")
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
        "pressure": f"Pressure tightens around {loc}: time, witnesses, or competing needs force a sharper choice.",
        "choice": f"The moment leaves clear next moves: press, wait, speak, withdraw, or reassess with what is now known.",
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
    briefs = build_paragraph_briefs(budget, context, player_input, ledger, ops_summary)
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
        brief["forbidden_repeat"] = ledger.forbidden_repeats()[:20]
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

        paragraphs.append(text)
        first = re.split(r"(?<=[.!?])\s+", text.strip())[0] if text.strip() else ""
        if first and not looks_truncated(first):
            ledger.add_said_fact(first, index)
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
