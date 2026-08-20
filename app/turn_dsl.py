"""
NAR+OPS turn draft language.

The model fills a fixed text form (narration + opcode lines). A deterministic
transcoder maps ops into the turn JSON shape expected by apply_turn.

String escaping for durable storage uses percent-encoding applied only by this
module — never by the model.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote, unquote

from app.prompts import PROSE_VOICE

# Closed opcode set (case-insensitive). Unknown ops fail loud.
OPCODES = {
    "SUMMARY",
    "SCENE",
    "GOAL",
    "FOCUS",
    "NPC_NEW",
    "NPC_NOTE",
    "TALK",
    "GRANT",
    "TAKE",
    "GOLD",
    "XP",
    "HP",
    "KARMA",
    "MOVE",
    "LOC_NEW",
    "EVENT",
    "GM",
    "REL",
    "SKILL",
    "CLAIM",
    "JOURNAL",
    "INDEX",
    "NOTE",
}

NAR_MARKERS = ("===NAR===", "===NARRATION===", "@NAR")
OPS_MARKERS = ("===OPS===", "@OPS")

DSL_SYSTEM_PROMPT = """You are the local narrative engine for an endless RPG.

Return ONLY the fixed form below. Do not return JSON. Do not invent new section headers.
Do not percent-encode or HTML-escape text. Write normal readable characters; the app encodes storage later.

""" + PROSE_VOICE + """

Form:
===NAR===
<continuous playable prose, about 1000-1800 characters, natural paragraphs in clear English>
Use [[CODE]] after entity names when known (name [[A]], place [[L1]]).

===OPS===
<zero or more opcode lines from the closed list below>
One op per line. Prefer entity codes from world_state. Use quoted strings for free text.

Allowed opcodes:
SUMMARY <compact memory line under 55 words, entity codes OK>
SCENE <action|conversation|travel|survival|filler|lore|system>
GOAL <one sentence scene goal>
FOCUS <event|location|npc|risk|resource|choice|sensory> <short summary>
NPC_NEW NAME "<real name, not a description>" ROLE <role> LOC <location code or name> [ATTITUDE <word>] [RACE <word>] [RANK <letter>]
NPC_NOTE <code> "<durable fact>"
TALK <npc_code> "<topic/summary of exchange>"
GRANT "<item name>" QTY <band> [TYPE <type>] [DESC "<description>"] [RARITY <word>]
TAKE "<item name>" QTY <band>
GOLD <band>
XP <band>
HP <band>
KARMA <band> [VIS <private|local|faction|public>] [REASON "<why>"]
MOVE <place name — an existing one from movement_contract.known_places, or a new one you name>
LOC_NEW "<name>" "<summary>"
EVENT "<title>" [LOC <code>] [NPC <code>] [SUMMARY "<text>"]
GM "<trigger>" "<private future note>"
REL <source_code> <target_code> "<what source knows/thinks>"
SKILL "<name>" DELTA <band> [NOTES "<why>"]
CLAIM "<claim text>" VERDICT <true|false|unverified> [SKILL <skill>] [NOTES "<why>"]
JOURNAL <fact|quest|rumor|event|system> "<content>"
INDEX <npc|location|item|event> <code> "<summary_append>"
NOTE "<short durable journal-style fact>"

Rules:
- Database/world_state is source of truth. Only propose justified changes.
- Amounts are bands, never numbers: none, trivial, small, moderate, large, huge.
  Write "XP small", "GOLD -moderate", "HP -small", "GRANT \"rope\" QTY small".
  A leading "-" means a loss. The app rolls the actual amount; a bare number is
  read as a band hint and re-rolled, so bands are shorter and more reliable.
- NPC_NEW NAME must be a name ("Aria", "Thornrow", "Captain Vesk"), never a description
  ("Woman", "Old Man", "Hooded Figure", "Guard"). The app overwrites description-only names.
- NPC_NEW ROLE is an occupation — carter, net mender, baker, off-duty guard, ferryman.
  It is not an appearance: "hooded stranger" and "cloaked local" are not jobs. Describe the
  hood in ===NAR=== if it matters. At most one genuinely mysterious watcher on screen.
- Movement is an op, not a description. If the prose ends with the player anywhere other than
  world_state.movement_contract.current_location, ===OPS=== MUST contain a MOVE line.
  Writing "you leave for the coast road" with no MOVE line leaves the player standing where they were,
  and the next turn will contradict your prose.
- MOVE takes a place NAME: MOVE Redmill Ford. A name already in movement_contract.known_places
  goes back there; any other name creates that place. Name what the prose actually describes —
  if the scene ends at a river camp, write MOVE Riverbend Camp, do not substitute a known town.
  Never guess a location code: "MOVE L2" is discarded and the player does not move.
- Going indoors is a MOVE. A shop, inn, forge or temple the player steps into is a place, not
  scenery: write MOVE <that building's name>. Prefer a name from movement_contract.venues_here;
  otherwise name the building and it is created. Stepping back outside is another MOVE, to
  movement_contract.current_location's parent. A scene that walks the player into a shop with no
  MOVE line leaves them standing in the street, and the shop stops existing the moment it scrolls
  out of context.
- Interiors are entered only from the place they stand in. A player two locations away cannot
  MOVE straight into a shop — that move lands them outside it instead, and going in costs the next
  turn. Do not narrate walking across the map and through a shop door in one turn.
- A new place gets its own name, not a known one with a word added. If known_places has
  "Riverbend Camp", do not invent "Riverbend Hillcrest Camp" — it is either the place you already
  have, or it has a different name. The app folds those extensions back into the original.
- Narrate in second person ("you"), and use world_state.narrative_voice.player_pronouns for the player.
  Never switch to third person or the player's name as narration subject.
- Resolve the player's action. They already chose; show what happens. Never end ===NAR=== with the
  choice restated ("Do you approach X, or continue to Y?", "The choice is yours.") — that hands the
  turn back unplayed. End on a consequence, a new pressure, or a concrete detail, then stop.
- Opening/continue: establish or advance scene; do not invent player commands.
- Keep rewards small. Empty ===OPS=== is allowed when nothing structured changes.
- Never put private GM text in ===NAR===.
- ===NAR=== must be easy to follow: direct sentences, varied but plain vocabulary, no inverted poetic templates.
"""


class TurnDslError(ValueError):
    """Raised when DSL text cannot be parsed into a usable turn."""


def draft_mode_enabled() -> bool:
    mode = (os_getenv_draft_mode() or "dsl").strip().lower()
    return mode in {"dsl", "ops", "nar_ops", "1", "true", "yes", "on"}


def os_getenv_draft_mode() -> str:
    import os

    return os.getenv("AI_RPG_DRAFT_MODE", "dsl")


def encode_storage_text(value: str) -> str:
    """Percent-encode reserved characters for durable structured storage."""
    text = str(value or "")
    # Encode everything except unreserved + spaces we keep as %20 for stability.
    return quote(text, safe="")


def decode_storage_text(value: str) -> str:
    return unquote(str(value or ""))


def _decode_arg_escapes(text: str) -> str:
    """Decode %XX sequences the transcoder may have stored; models should not emit these."""
    if not text or "%" not in text:
        return text
    try:
        return unquote(text)
    except Exception:
        return text


def _tokenize_line(line: str) -> tuple[str, list[str], dict[str, str]]:
    """
    Tokenize an opcode line into:
      opcode, positional bare tokens, key=value or KEY value pairs, and quoted strings in order.
    Simpler approach: extract quoted strings first, then split remainder.
    """
    raw = line.strip()
    if not raw or raw.startswith("#"):
        return "", [], {}

    strings: list[str] = []

    def _pull_quoted(match: re.Match[str]) -> str:
        body = match.group(1)
        body = body.replace('\\"', '"').replace("\\n", "\n")
        strings.append(_decode_arg_escapes(body))
        return f" __STR{len(strings) - 1}__ "

    working = re.sub(r'"((?:\\.|[^"\\])*)"', _pull_quoted, raw)
    parts = [p for p in working.split() if p]
    if not parts:
        return "", [], {}
    opcode = parts[0].upper()
    positionals: list[str] = []
    flags: dict[str, str] = {}
    flag_keys = {
        "NAME",
        "ROLE",
        "LOC",
        "ATTITUDE",
        "RACE",
        "RANK",
        "QTY",
        "TYPE",
        "DESC",
        "RARITY",
        "VIS",
        "REASON",
        "NPC",
        "SUMMARY",
        "DELTA",
        "NOTES",
        "VERDICT",
        "SKILL",
    }
    # First free token after FOCUS is always the kind (event/npc/risk/...), never a flag key.
    force_positional_remaining = 1 if opcode == "FOCUS" else 0
    i = 1
    while i < len(parts):
        token = parts[i]
        upper = token.upper()
        str_match = re.fullmatch(r"__STR(\d+)__", token)
        if str_match:
            positionals.append(strings[int(str_match.group(1))])
            if force_positional_remaining:
                force_positional_remaining -= 1
            i += 1
            continue
        # KEY=value form (preferred; never collides with FOCUS kinds like "npc")
        if "=" in token and not token.startswith("="):
            key, _, value = token.partition("=")
            key_u = key.upper()
            if key_u in flag_keys and value:
                sm = re.fullmatch(r"__STR(\d+)__", value)
                flags[key_u] = strings[int(sm.group(1))] if sm else _decode_arg_escapes(value)
                i += 1
                continue
        # KEY value form — skip while forcing positionals (FOCUS kind)
        if force_positional_remaining:
            positionals.append(_decode_arg_escapes(token))
            force_positional_remaining -= 1
            i += 1
            continue
        if upper in flag_keys and i + 1 < len(parts):
            nxt = parts[i + 1]
            sm = re.fullmatch(r"__STR(\d+)__", nxt)
            flags[upper] = strings[int(sm.group(1))] if sm else _decode_arg_escapes(nxt)
            i += 2
            continue
        positionals.append(_decode_arg_escapes(token))
        i += 1
    return opcode, positionals, flags


def split_nar_ops(text: str) -> tuple[str, str]:
    content = str(text or "").replace("\r\n", "\n").strip()
    if not content:
        return "", ""

    upper = content.upper()
    nar_idx = -1
    nar_len = 0
    for marker in NAR_MARKERS:
        idx = upper.find(marker)
        if idx >= 0 and (nar_idx < 0 or idx < nar_idx):
            nar_idx = idx
            nar_len = len(marker)

    ops_idx = -1
    ops_len = 0
    for marker in OPS_MARKERS:
        idx = upper.find(marker)
        if idx >= 0 and (ops_idx < 0 or idx < ops_idx):
            ops_idx = idx
            ops_len = len(marker)

    if nar_idx >= 0 and ops_idx >= 0:
        if nar_idx < ops_idx:
            narration = content[nar_idx + nar_len : ops_idx].strip()
            ops_block = content[ops_idx + ops_len :].strip()
        else:
            ops_block = content[ops_idx + ops_len : nar_idx].strip()
            narration = content[nar_idx + nar_len :].strip()
        return narration, ops_block

    if nar_idx >= 0:
        return content[nar_idx + nar_len :].strip(), ""

    if ops_idx >= 0:
        return "", content[ops_idx + ops_len :].strip()

    # No markers: treat whole body as narration if it looks like prose.
    if content.lstrip().startswith("{") and '"narration"' in content:
        raise TurnDslError("Response looks like JSON, not NAR+OPS form.")
    return content, ""


# Near-misses seen from local models. A 7B wrote `MOV` once, and because an
# unknown opcode raised, that single typo threw away every other op in the turn.
OPCODE_ALIASES = {
    "MOV": "MOVE",
    "MOVETO": "MOVE",
    "GOTO": "MOVE",
    "TRAVEL": "MOVE",
    "LOCNEW": "LOC_NEW",
    "NEWLOC": "LOC_NEW",
    "NEW_LOCATION": "LOC_NEW",
    "LOCATION_NEW": "LOC_NEW",
    "NPCNEW": "NPC_NEW",
    "NEWNPC": "NPC_NEW",
    "NPCNOTE": "NPC_NOTE",
    "SUMM": "SUMMARY",
    "SUM": "SUMMARY",
    "GIVE": "GRANT",
    "ITEM": "GRANT",
    "REMOVE": "TAKE",
    "DROP": "TAKE",
    "HEALTH": "HP",
    "GOLDS": "GOLD",
    "COIN": "GOLD",
    "MONEY": "GOLD",
    "EXP": "XP",
    "RELATION": "REL",
    "RELATIONSHIP": "REL",
}


def normalize_opcode(opcode: str) -> str:
    """Map a near-miss opcode onto the closed list, or return '' if unrecognized."""
    token = str(opcode or "").strip().upper().replace("-", "_")
    if token in OPCODES:
        return token
    return OPCODE_ALIASES.get(token, "")


def parse_ops(ops_block: str) -> list[dict[str, Any]]:
    ops: list[dict[str, Any]] = []
    seen_lines = 0
    skipped: list[str] = []
    for line_no, line in enumerate(str(ops_block or "").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        opcode, positionals, flags = _tokenize_line(stripped)
        if not opcode:
            continue
        seen_lines += 1
        canonical = normalize_opcode(opcode)
        if not canonical:
            # Drop the bad line, keep the turn. Losing one op the model fumbled
            # beats losing the scene's whole state because of a typo.
            skipped.append(stripped[:80])
            continue
        ops.append({"op": canonical, "args": positionals, "flags": flags, "line": line_no, "raw": stripped})
    if seen_lines and not ops:
        # Nothing at all parsed: this is not a typo, it is the wrong format.
        raise TurnDslError(f"No recognizable opcodes in ops block: {'; '.join(skipped[:3])}")
    return ops


def _paragraphs(narration: str) -> list[dict[str, str]]:
    chunks = [p.strip() for p in re.split(r"\n\s*\n", narration.strip()) if p.strip()]
    if not chunks and narration.strip():
        chunks = [narration.strip()]
    return [{"label": "paragraph", "text": chunk[:2000]} for chunk in chunks[:12]]


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _amount(value: Any) -> tuple[str | None, int | None]:
    """
    Classify an amount token as either a band or a bare number.

    Returns ``(band, number)`` with exactly one side set (or both None when
    the token is empty). Bands are the documented form; bare integers stay
    supported for hand-written ops and older prompts, and the world layer
    re-rolls them as band hints. Nothing here decides an amount.
    """
    from app.rng import BAND_ALIASES, BAND_INDEX

    text = str(value if value is not None else "").strip()
    if not text:
        return None, None
    negative = text.startswith("-")
    body = text.lstrip("+-").strip().lower()
    try:
        number = int(float(body))
    except (TypeError, ValueError):
        if body not in BAND_INDEX and body not in BAND_ALIASES:
            return None, None
        return (("-" if negative else "") + body), None
    return None, (-number if negative else number)


def _apply_amount(
    target: dict[str, Any],
    *,
    band_key: str,
    number_key: str,
    token: Any,
    negate: bool = False,
) -> None:
    """Write an amount token onto a turn dict in whichever form it arrived."""
    band, number = _amount(token)
    if band is not None:
        if negate and not band.startswith("-"):
            band = f"-{band}"
        target[band_key] = band
    elif number is not None:
        target[number_key] = -abs(number) if negate else number


def ops_to_turn(narration: str, ops: list[dict[str, Any]], player_input: str = "") -> dict[str, Any]:
    """Deterministic transcoder: NAR+OPS → apply_turn-compatible dict."""
    narration = str(narration or "").strip()
    if not narration:
        raise TurnDslError("DSL draft missing narration in ===NAR=== section.")

    turn: dict[str, Any] = {
        "scene_plan": {"goal": "", "focus_points": []},
        "narration_segments": _paragraphs(narration),
        "narration": narration[:5600],
        "player": {
            "health_delta": 0,
            "max_health_delta": 0,
            "xp_delta": 0,
            "gold_delta": 0,
            "level_delta": 0,
            "move_to_location": None,
            "move_to_location_code": None,
            "karma_delta": 0,
            "karma_reason": "",
            "karma_visibility": "private",
        },
        "skill_changes": [],
        "inventory_changes": [],
        "equipment_slots": [],
        "equipment_changes": [],
        "inventory_capacity_modifiers": [],
        "locations": [],
        "npcs": [],
        "relationships": [],
        "events": [],
        "gm_events": [],
        "conversations": [],
        "response_drafts": [],
        "index_updates": [],
        "ability_updates": [],
        "self_check": {
            "passed": True,
            "issues_found": [],
            "corrections_made": ["deterministic_turn_dsl_transcoder"],
            "reference_check": "ops validated against closed opcode table",
            "consistency_check": "structured fields produced by formula, not freeform model JSON",
        },
        "turn_summary": "",
        "journal": [],
        "scene_focus": "action",
        "_dsl": {"ops_count": len(ops), "source": "nar_ops"},
    }

    for entry in ops:
        op = entry["op"]
        args: list[str] = list(entry.get("args") or [])
        flags: dict[str, str] = dict(entry.get("flags") or {})

        if op == "SUMMARY":
            turn["turn_summary"] = " ".join(args)[:700] or turn["turn_summary"]
        elif op == "SCENE":
            turn["scene_focus"] = (args[0] if args else "action")[:40]
        elif op == "GOAL":
            turn["scene_plan"]["goal"] = " ".join(args)[:400]
        elif op == "FOCUS":
            kind = (args[0] if args else "event")[:40]
            summary = " ".join(args[1:]) if len(args) > 1 else flags.get("SUMMARY", "beat")
            turn["scene_plan"]["focus_points"].append(
                {
                    "kind": kind,
                    "summary": summary[:300],
                    "event_worthy": kind in {"event", "risk", "npc"},
                    "persistence": "temporary",
                }
            )
        elif op == "NPC_NEW":
            name = flags.get("NAME") or (args[0] if args else "")
            if not name:
                raise TurnDslError(f"NPC_NEW requires NAME on line {entry['line']}")
            npc = {
                "code": None,
                "name": name[:120],
                "race": flags.get("RACE", "human")[:80],
                "location": flags.get("LOC") or (args[1] if len(args) > 1 else ""),
                "role": flags.get("ROLE") or (args[2] if len(args) > 2 else "local")[:80],
                "summary": flags.get("DESC") or f"Introduced this turn: {name}"[:400],
                "attitude": flags.get("ATTITUDE", "neutral")[:40],
                "personality": "",
                "likes": "",
                "principles": "",
                "dislikes": "",
                "rank": flags.get("RANK", "")[:8],
                "stat_profile": {},
                "skill_profile": {},
                "trust_delta": 0,
                "known_fact": "",
                "mentioned_by": None,
            }
            turn["npcs"].append(npc)
        elif op == "NPC_NOTE":
            code = (args[0] if args else "").upper()
            fact = args[1] if len(args) > 1 else " ".join(args[1:])
            if not code or not fact:
                raise TurnDslError(f"NPC_NOTE requires code and fact on line {entry['line']}")
            turn["index_updates"].append(
                {"entity_type": "npc", "code": code, "summary_append": fact[:400], "known_fact": fact[:400]}
            )
        elif op == "TALK":
            code = (args[0] if args else "").upper()
            topic = args[1] if len(args) > 1 else "conversation"
            if not code:
                raise TurnDslError(f"TALK requires npc code on line {entry['line']}")
            turn["conversations"].append(
                {
                    "npc_code": code,
                    "topic": topic[:120],
                    "summary": topic[:500],
                    "player_claims": [],
                }
            )
        elif op == "GRANT":
            name = args[0] if args else flags.get("NAME", "")
            if not name:
                raise TurnDslError(f"GRANT requires item name on line {entry['line']}")
            qty_token = flags.get("QTY")
            if qty_token in (None, "") and len(args) > 1:
                qty_token = args[1]
            amount: dict[str, Any] = {}
            _apply_amount(amount, band_key="quantity_band", number_key="quantity_delta", token=qty_token)
            if not amount:
                amount = {"quantity_band": "trivial"}
            elif "quantity_delta" in amount:
                amount["quantity_delta"] = abs(amount["quantity_delta"]) or 1
            turn["inventory_changes"].append(
                {
                    "name": name[:120],
                    "description": flags.get("DESC", "")[:400],
                    **amount,
                    "weight": 1.0,
                    "slot_size": 1,
                    "item_type": flags.get("TYPE", "misc")[:80],
                    "rarity": flags.get("RARITY", "common")[:40],
                    "enchantments": [],
                    "stat_modifiers": {},
                    "granted_abilities": [],
                    "stack_limit": 20,
                    "carry_modifier": 1.0,
                    "container_bonus_weight": 0,
                    "container_bonus_slots": 0,
                    "dimensional_space": False,
                }
            )
        elif op == "TAKE":
            name = args[0] if args else ""
            if not name:
                raise TurnDslError(f"TAKE requires item name on line {entry['line']}")
            qty_token = flags.get("QTY")
            if qty_token in (None, "") and len(args) > 1:
                qty_token = args[1]
            amount = {}
            _apply_amount(amount, band_key="quantity_band", number_key="quantity_delta", token=qty_token, negate=True)
            if not amount:
                amount = {"quantity_band": "-trivial"}
            turn["inventory_changes"].append(
                {
                    "name": name[:120],
                    "description": "",
                    **amount,
                    "weight": 1.0,
                    "slot_size": 1,
                    "item_type": "misc",
                    "rarity": "common",
                    "enchantments": [],
                    "stat_modifiers": {},
                    "granted_abilities": [],
                    "stack_limit": 20,
                    "carry_modifier": 1.0,
                    "container_bonus_weight": 0,
                    "container_bonus_slots": 0,
                    "dimensional_space": False,
                }
            )
        elif op == "GOLD":
            _apply_amount(turn["player"], band_key="gold_band", number_key="gold_delta", token=args[0] if args else None)
        elif op == "XP":
            _apply_amount(turn["player"], band_key="xp_band", number_key="xp_delta", token=args[0] if args else None)
        elif op == "HP":
            _apply_amount(turn["player"], band_key="health_band", number_key="health_delta", token=args[0] if args else None)
        elif op == "KARMA":
            _apply_amount(turn["player"], band_key="karma_band", number_key="karma_delta", token=args[0] if args else None)
            turn["player"]["karma_visibility"] = (flags.get("VIS") or "private")[:40]
            turn["player"]["karma_reason"] = flags.get("REASON") or (" ".join(args[1:]) if len(args) > 1 else "")
        elif op == "MOVE":
            dest = " ".join(args).strip()
            if not dest:
                raise TurnDslError(f"MOVE requires destination on line {entry['line']}")
            if re.fullmatch(r"L\d+", dest, re.I):
                turn["player"]["move_to_location_code"] = dest.upper()
            else:
                turn["player"]["move_to_location"] = dest[:120]
        elif op == "LOC_NEW":
            name = args[0] if args else ""
            summary = args[1] if len(args) > 1 else f"Discovered location: {name}"
            if not name:
                raise TurnDslError(f"LOC_NEW requires name on line {entry['line']}")
            turn["locations"].append({"name": name[:120], "summary": summary[:500]})
        elif op == "EVENT":
            title = args[0] if args else "Event"
            turn["events"].append(
                {
                    "code": None,
                    "title": title[:120],
                    "location_code": flags.get("LOC", ""),
                    "npc_code": flags.get("NPC", ""),
                    "summary": flags.get("SUMMARY") or title,
                    "status": "active",
                    "persistence": "temporary",
                    "disappear_chance": 70,
                    "respawn_chance": 0,
                    "fame_score": 0,
                    "fame_scope": "local",
                    "rumor_summary": "",
                }
            )
        elif op == "GM":
            trigger = args[0] if args else "offscreen"
            summary = args[1] if len(args) > 1 else trigger
            turn["gm_events"].append(
                {
                    "trigger": trigger[:240],
                    "summary": summary[:500],
                    "status": "pending",
                    "priority": 3,
                    "location_code": flags.get("LOC", ""),
                    "npc_code": flags.get("NPC", ""),
                    "event_code": "",
                }
            )
        elif op == "REL":
            if len(args) < 3:
                raise TurnDslError(f"REL requires source target summary on line {entry['line']}")
            turn["relationships"].append(
                {
                    "source_code": args[0].upper(),
                    "target_code": args[1].upper(),
                    "location": flags.get("LOC", ""),
                    "summary": " ".join(args[2:])[:400],
                    "weight_delta": 1,
                }
            )
        elif op == "SKILL":
            name = args[0] if args else flags.get("NAME", "")
            if not name:
                raise TurnDslError(f"SKILL requires name on line {entry['line']}")
            delta_token = flags.get("DELTA")
            if delta_token in (None, "") and len(args) > 1:
                delta_token = args[1]
            amount = {}
            _apply_amount(amount, band_key="delta_band", number_key="delta", token=delta_token)
            if not amount:
                amount = {"delta_band": "small"}
            turn["skill_changes"].append(
                {"name": name[:80], **amount, "notes": flags.get("NOTES", "")[:240]}
            )
        elif op == "CLAIM":
            claim = args[0] if args else ""
            verdict = (flags.get("VERDICT") or (args[1] if len(args) > 1 else "unverified")).lower()
            turn["response_drafts"].append(
                {
                    "claim": claim[:240],
                    "verdict": verdict[:40],
                    "skill": flags.get("SKILL", "")[:40],
                    "difficulty_class": 12,
                    "result": "not_checked",
                    "notes": flags.get("NOTES", "")[:240],
                }
            )
        elif op == "JOURNAL":
            kind = (args[0] if args else "fact")[:40]
            content = args[1] if len(args) > 1 else " ".join(args[1:])
            turn["journal"].append({"kind": kind, "content": content[:1400]})
        elif op == "INDEX":
            if len(args) < 3:
                raise TurnDslError(f"INDEX requires type code summary on line {entry['line']}")
            turn["index_updates"].append(
                {
                    "entity_type": args[0].lower()[:40],
                    "code": args[1].upper()[:20],
                    "summary_append": " ".join(args[2:])[:400],
                }
            )
        elif op == "NOTE":
            content = " ".join(args) if args else ""
            if content:
                turn["journal"].append({"kind": "fact", "content": content[:1400]})

    if not turn["turn_summary"]:
        intent = str(player_input or "").strip()[:80]
        turn["turn_summary"] = f"player: {intent or 'acted'}. response: scene advanced with DSL ops."[:700]
    if not turn["scene_plan"]["goal"]:
        turn["scene_plan"]["goal"] = "Advance the immediate scene with justified local consequences."
    if not turn["scene_plan"]["focus_points"]:
        turn["scene_plan"]["focus_points"] = [
            {
                "kind": "choice",
                "summary": "Immediate reaction options after the latest beat",
                "event_worthy": False,
                "persistence": "temporary",
            }
        ]
    return turn


def parse_dsl_turn(text: str, player_input: str = "") -> dict[str, Any]:
    narration, ops_block = split_nar_ops(text)
    ops = parse_ops(ops_block)
    turn = ops_to_turn(narration, ops, player_input=player_input)
    return turn


def build_dsl_user_prompt(context: dict[str, Any], player_input: str) -> str:
    """Slim prompt: reuse world packet but demand NAR+OPS output."""
    from app.prompts import build_user_prompt

    base = build_user_prompt(context, player_input)
    try:
        packet = __import__("json").loads(base)
    except Exception:
        packet = {"world_state": context, "player_input": player_input}
    packet["output_contract"] = {
        "format": "nar_ops_v0",
        "required_sections": ["===NAR===", "===OPS==="],
        "forbidden": ["json object root", "markdown code fences"],
        "opcode_list": sorted(OPCODES),
        "escape_policy": "Write raw Unicode in quotes. Do not percent-encode; the app encodes storage.",
    }
    instructions = [
        "Fill ===NAR=== with continuous playable prose.",
        "Fill ===OPS=== with zero or more closed opcodes only.",
        "Do not return JSON.",
    ]
    # Required-op hint, next to the opcode list where the model looks for them.
    # Only on travel turns, so ordinary turns do not pay for it.
    contract = context.get("movement_contract") if isinstance(context, dict) else None
    if isinstance(contract, dict) and contract.get("travel_intent"):
        here = (contract.get("current_location") or {}).get("code") or "the current location"
        instructions.append(
            f"Travel turn: if the prose ends anywhere but {here}, ===OPS=== MUST contain a MOVE line."
        )
    packet["instructions"] = instructions
    return __import__("json").dumps(packet, ensure_ascii=True, separators=(",", ":"))
