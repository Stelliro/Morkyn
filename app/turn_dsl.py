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
    "WALK",
    "LOC_NEW",
    "EVENT",
    "GM",
    "REL",
    "SKILL",
    "CLAIM",
    "JOURNAL",
    "INDEX",
    "NOTE",
    "CAST",
    # Quest marks. Optional: the engine's quest parser also reads the prose.
    "QUEST",
    "QUEST_DONE",
}

QUEST_DONE_ACTIONS = ("accept", "step_done", "complete", "fail", "abandon")

NAR_MARKERS = ("===NAR===", "===NARRATION===", "@NAR")
OPS_MARKERS = ("===OPS===", "@OPS")

DSL_SYSTEM_PROMPT = """You are the local narrative engine for an endless RPG.

Return ONLY the fixed form below. Do not return JSON. Do not invent new section headers.
Do not percent-encode or HTML-escape text. Write normal readable characters; the app encodes storage later.

""" + PROSE_VOICE + """

Form:
===NAR===
the scene as continuous playable prose, as long as narration_length asks, natural paragraphs in clear English
Use [[CODE]] after entity names when known (name [[A]], place [[L1]]).

===OPS===
zero or more opcode lines from the closed list below
One op per line. Prefer entity codes from world_state. Use quoted strings for free text.

Allowed opcodes. UPPER-CASE words are written as shown. A lower_case_word is a slot: write
your value in its place, and the slot word itself never appears in the line. a|b|c means
write one of them. Parts after "optional:" may be left out.
SUMMARY compact_memory_line_under_55_words
SCENE action|conversation|travel|survival|filler|lore|system
GOAL one_sentence_scene_goal
FOCUS event|location|npc|risk|resource|choice|sensory short_summary
NPC_NEW NAME "real_name" ROLE job_words LOC location_code_or_"place name" optional: ATTITUDE word RACE word RANK letter
NPC_NOTE npc_code "durable_fact"
TALK npc_code "topic_of_the_exchange"
GRANT "item_name" QTY band optional: TYPE type DESC "description" RARITY word
TAKE "item_name" QTY band
GOLD band
XP band
HP band
KARMA band optional: VIS private|local|faction|public REASON "why"
MOVE place_name (one from movement_contract.known_places, or a new one you name)
WALK direction optional: STEPS 1-4
LOC_NEW "place_name" "summary"
EVENT "title" optional: LOC location_code NPC npc_code SUMMARY "text"
GM "trigger" "private_future_note"
REL source_code target_code "what_source_knows_or_thinks"
SKILL "skill_name" DELTA band optional: NOTES "why"
CLAIM "claim_text" VERDICT true|false|unverified optional: SKILL skill_name NOTES "why"
JOURNAL fact|quest|rumor|event|system "content"
INDEX npc|location|item|event code "summary_append"
NOTE "short_durable_journal_style_fact"
CAST present npc_code
CAST interacting npc_code
CAST off npc_code
CAST keyword one_scene_word
QUEST "title" GIVER npc_code_or_"name" STEP "first_thing_to_do" optional: AT place_code_or_"name" REWARD "as_promised"
QUEST_DONE quest_code_or_"title" accept|step_done|complete|fail|abandon

Rules:
CAST is the only way to change who is in the active scene.
interacting = the character who replies to the player. present = nearby and relevant, but not the one who answers.
If nobody is interacting, do not invent a speaker. If you want someone to address the player, CAST interacting that code.
A later "how was your day?" is for the interacting character, not everyone marked present.
Leave CAST out when the scene cast does not change.
QUEST marks work the story just offered or the player just took on. Marking is optional: the
engine also reads the prose for offered work, so write the offer in ===NAR=== either way. At most
one QUEST per turn, and only for real work with a giver and a first step, not idle talk.
QUEST_DONE marks a step or a job the prose just finished, accepted, failed or dropped.
- Database/world_state is source of truth. Only propose justified changes.
- playthrough_options.choices are this playthrough's labels. For RANK, use only the rungs named in choices.rank_scale. playthrough_options.setting_templates, when present, is the one written rule this action named. Follow that included rule. Do not replace its labels.
- Amounts are bands, never numbers: none, trivial, small, moderate, large, huge.
  Write "XP small", "GOLD -moderate", "HP -small"; GRANT takes the item's name in quotes,
  then QTY and a band.
  A leading "-" means a loss. The app rolls the actual amount; a bare number on
  XP, GOLD, HP, KARMA or SKILL is read as a band hint and re-rolled, so bands are
  shorter and more reliable.
- GRANT and TAKE QTY counts objects: trivial or small is one, moderate two,
  large three, huge five. A real stack may be a plain number. GRANT only what
  ===NAR=== puts in the player's hands (given, bought, picked up, looted,
  crafted); something looked at, touched, tasted or handed back is not granted.
- NPC_NEW NAME is the person's own given name, the one people call them by, made for this
  world and this person. How they look or what they do is not a name; the app overwrites
  description-only names. Never give a name already used by someone else in world_state.
  cast_options.names are unused names drawn for this turn: take one or make one like them.
- world_state.current_location.people: works_here marks someone who works in this place;
  works_at is that person's own workplace somewhere else, so here they are a visitor and do not
  sell, keep or own what is here. current_location.keeper keeps the place the player is inside.
- NPC_NEW ROLE is the person's occupation, a job word or two that fits this place and this
  world; cast_options.jobs were drawn for this place. It is not an appearance: what they wear
  or how they look belongs in ===NAR===.
  At most one genuinely mysterious watcher on screen.
- Movement is an op, not a description. If the prose ends with the player anywhere other than
  world_state.movement_contract.current_location, ===OPS=== MUST contain a MOVE line.
  Writing "you leave for the coast road" with no MOVE line leaves the player standing where they were,
  and the next turn will contradict your prose.
- MOVE takes a place NAME, spelled the way the prose just spelled it. A name already in
  movement_contract.known_places goes back there; any other name creates that place. Name what
  the prose actually describes — if the scene ends at a river camp, MOVE to that camp under the
  name you gave it, do not substitute a known town that is merely nearby.
  Never guess a location code: "MOVE L2" is discarded and the player does not move.
- Going indoors is a MOVE. A shop, inn, forge or temple the player steps into is a place, not
  scenery: write MOVE with that building's name. Prefer a name from movement_contract.venues_here;
  otherwise name the building and it is created. Stepping back outside is another MOVE, to
  movement_contract.current_location's parent. A scene that walks the player into a shop with no
  MOVE line leaves them standing in the street, and the shop stops existing the moment it scrolls
  out of context.
- A hike is at most 4 tiles. One step does not cross inside a city. When map_space.step_budget
  is present, that is this turn's limit. A hike across country is WALK with a direction and STEPS 1-4
  (north, south, east, west, or a compound such as northeast) plus a MOVE naming the place
  where the walk stops. Do not invent a road, town, or wilderness farther than that walk.
  A door into a shop or room is MOVE only — do not WALK the grid for a room.
- Interiors are entered only from the place they stand in. A player two locations away cannot
  MOVE straight into a shop — that move lands them outside it instead, and going in costs the next
  turn. Do not narrate walking across the map and through a shop door in one turn.
- A new place gets its own name, not a known one with a word added, and not a known one with a
  word removed. Whatever movement_contract.known_places holds, the next place is neither that name
  plus a bearing or a storey, nor that name with its qualifier stripped off — it is either the
  place you already have, or it has a genuinely different name. The app folds both back into the
  original.
- Narrate in second person ("you"), and use world_state.narrative_voice.player_pronouns for the player.
- If world_state.naming_contract is present, the player asked for a name. Write
  naming_contract.name into the prose as plain text. Describing a name without
  stating it ("the name weighs on you") does not count and will be corrected.
  Never switch to third person or the player's name as narration subject.
- If world_state.recall_contract is present, the player is answering a question this
  world already has an answer to. Write recall_contract.specifics into the prose as
  plain text. Echoing the question back ("you answer honestly: who you owe, how much,
  and when") is not an answer and will be corrected.
- Resolve the player's action. They already chose; show what happens. Never end ===NAR=== with the
  choice restated ("Do you approach X, or continue to Y?", "The choice is yours.") — that hands the
  turn back unplayed. End on a consequence, a new pressure, or a concrete detail, then stop.
- player_line is the player's own input: the only words, reply, gesture, feeling or memory "you" have
  this turn. Narrate its action and what the world does back. When someone speaks to the player, end
  the exchange on that line; the player answers next turn.
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


# Opcodes whose leading free tokens are positional by definition, so they are
# never read as flag keys. Both entries here are real collisions, not caution:
# FOCUS takes a kind ("npc", "event"), and INDEX takes an entity type followed
# by a code -- and "NPC" is also a flag key (EVENT ... NPC <code>). Without this,
# "INDEX npc F \"...\"" parsed as flags={NPC: F} with one positional left, failed
# INDEX's own arity check, and cost the turn every op on every other line.
_LEADING_POSITIONALS = {"FOCUS": 1, "INDEX": 2}
_OPCODE_FLAG_KEYS: dict[str, set[str]] = {"QUEST": {"GIVER", "STEP", "AT", "REWARD"}}
# Flags whose unquoted value may be several words ("ROLE net mender").
# Playtest #34 (live): "NAME Umar Mendes" kept only "Umar", and the roster
# lookup then minted a second person. A name runs to the next flag too.
_MULTIWORD_FLAGS = {"ROLE", "LOC", "NAME"}
# Longest unquoted run each multi-word flag may take.
_MULTIWORD_LIMIT = {"ROLE": 4, "LOC": 6, "NAME": 4}
# A <slot> the model copied from a placeholder: "LOC <The Wasteland's Edge>"
# (live Qwen3 8B, playtest #28). The wrapper is syntax, not text; the span is
# read as one quoted argument. Only a bracket at a token edge counts, so
# "[[L1]]" and arrows inside quoted text are left alone.
_ANGLE_SPAN_RE = re.compile(r"(?<!\S)<\s*([^<>\n]*?)\s*>(?!\S)")


def _ends_multiword(token: str, flag_keys: set[str]) -> bool:
    """A token that is not part of an unquoted multi-word value: a flag, a quoted
    string, a location code or an attitude word."""
    if token.upper() in flag_keys or re.fullmatch(r"__STR\d+__", token):
        return True
    key, sep, _ = token.partition("=")
    if sep and key.upper() in flag_keys:
        return True
    return bool(_LOCATION_CODE_RE.match(token)) or token.lower() in _NPC_ATTITUDES


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

    def _pull_angle(match: re.Match[str]) -> str:
        body = match.group(1).strip()
        if not body:
            return " "
        if "__STR" in body:
            return f" {body} "
        strings.append(_decode_arg_escapes(body))
        return f" __STR{len(strings) - 1}__ "

    working = _ANGLE_SPAN_RE.sub(_pull_angle, working)
    # An unbalanced edge left over ("LOC <The"): drop the stray bracket.
    parts = [p.strip("<>") for p in working.split()]
    parts = [p for p in parts if p]
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
    # Flag words that only mean something on one op. "AT" and "STEP" are
    # ordinary words elsewhere, so they are flags on QUEST lines alone.
    flag_keys = flag_keys | _OPCODE_FLAG_KEYS.get(normalize_opcode(opcode), set())
    force_positional_remaining = _LEADING_POSITIONALS.get(opcode, 0)
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
            if upper in _MULTIWORD_FLAGS and not sm and not (upper == "LOC" and _LOCATION_CODE_RE.match(nxt)):
                # Playtest #16: "ROLE message runner LOC L1" stored Elara as a
                # "message". An unquoted occupation runs to the next flag.
                # Playtest #28: "LOC The Frostbound Crossroads ATTITUDE wary"
                # stored three NPCs at a new place called "The". A place name
                # runs to the next flag too; a location code stands alone.
                words = [flags[upper]]
                limit = _MULTIWORD_LIMIT.get(upper, 4)
                while i < len(parts) and len(words) < limit and not _ends_multiword(parts[i], flag_keys):
                    # A capitalised word after a lower-case job is a name:
                    # "ROLE baker Bo L1" keeps Bo as the NPC's name. Place
                    # names are capitalised all the way through, so not LOC.
                    if upper == "ROLE" and words[0][:1].islower() and parts[i][:1].isupper():
                        break
                    # A lower-case word after a capitalised name is a job:
                    # "NAME Bo baker L1" keeps "baker" out of the name.
                    if upper == "NAME" and words[0][:1].isupper() and not parts[i][:1].isupper():
                        break
                    words.append(_decode_arg_escapes(parts[i]))
                    i += 1
                flags[upper] = " ".join(words)
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
    "STEP": "WALK",
    "STEPS": "WALK",
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
    "OFFER": "QUEST",
    "JOB": "QUEST",
    "TASK": "QUEST",
    "QUEST_NEW": "QUEST",
    "NEWQUEST": "QUEST",
    "QUEST_UPDATE": "QUEST_DONE",
    "QUESTDONE": "QUEST_DONE",
    "QUEST_STEP": "QUEST_DONE",
}


def normalize_opcode(opcode: str) -> str:
    """Map a near-miss opcode onto the closed list, or return '' if unrecognized."""
    token = str(opcode or "").strip().upper().replace("-", "_")
    if token in OPCODES:
        return token
    return OPCODE_ALIASES.get(token, "")


def parse_ops(ops_block: str) -> list[dict[str, Any]]:
    return parse_ops_detailed(ops_block)[0]


def parse_ops_detailed(ops_block: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Ops plus the lines whose opcode is not on the list (they used to vanish untraced)."""
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
    return ops, skipped


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


def _walk_direction_and_steps(args: list[str], flags: dict[str, str]) -> tuple[str, int]:
    """WALK east / WALK east STEPS 2 / WALK northeast. Steps clamp to the map budget."""
    from app.tile_world import STEP_BUDGET, canonical_direction, clamp_steps

    tokens = [str(token) for token in args]
    step_token = flags.get("STEPS")
    direction = ""
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.upper() == "STEPS" and index + 1 < len(tokens):
            step_token = tokens[index + 1]
            index += 2
            continue
        if not direction:
            one = canonical_direction(token)
            pair = ""
            if index + 1 < len(tokens):
                pair = canonical_direction(f"{token} {tokens[index + 1]}")
            if pair and not one:
                direction = pair
                index += 2
                continue
            if one:
                direction = one
                index += 1
                continue
            if token.isdigit() and step_token is None:
                step_token = token
                index += 1
                continue
        index += 1
    if not direction:
        return "", 0
    return direction, clamp_steps(step_token if step_token is not None else STEP_BUDGET)


def _apply_op(turn: dict[str, Any], entry: dict[str, Any]) -> None:
    """
    Apply one opcode to the turn under construction.

    Raises TurnDslError for a malformed line. The caller isolates that to the
    single line: dropping one op the model fumbled beats dropping the whole
    scene's state, which is what happened before ops_to_turn caught nothing.
    """
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
        positional = _classify_npc_args(args)
        name = flags.get("NAME") or positional["name"]
        if flags.get("NAME") and not positional["role"] and positional["name"][:1].islower():
            # "NAME Bo baker LOC L1": the bare words after the name are the job.
            positional["role"] = positional["name"]
        if not name:
            raise TurnDslError(f"NPC_NEW requires NAME on line {entry['line']}")
        npc = {
            "code": None,
            "name": name[:120],
            "race": flags.get("RACE", "human")[:80],
            "location": flags.get("LOC") or positional["location"],
            "role": (flags.get("ROLE") or positional["role"] or "local")[:80],
            # Nothing known yet stays empty (playtest #24). A placeholder here
            # was stored as the summary and the first NPC_NOTE glued onto it:
            # "Introduced this turn: Aria Aria is a baker ...".
            "summary": (flags.get("DESC") or "")[:400],
            "attitude": (flags.get("ATTITUDE") or positional["attitude"] or "neutral")[:40],
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
        # Join every token after the code. A quoted fact is one arg; an unquoted
        # fact is many. Taking only args[1] stored "the" and dropped the rest.
        fact = " ".join(args[1:]).strip()
        if not code or not fact:
            raise TurnDslError(f"NPC_NOTE requires code and fact on line {entry['line']}")
        turn["index_updates"].append(
            {"entity_type": "npc", "code": code, "summary_append": fact[:400], "known_fact": fact[:400]}
        )
    elif op == "TALK":
        code = (args[0] if args else "").upper()
        topic = " ".join(args[1:]).strip() if len(args) > 1 else "conversation"
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
    elif op == "WALK":
        direction, steps = _walk_direction_and_steps(args, flags)
        if not direction:
            raise TurnDslError(f"WALK requires a direction on line {entry['line']}")
        turn["map_walk"] = {"direction": direction, "steps": steps}
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
        summary = " ".join(args[1:]).strip() if len(args) > 1 else trigger
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
        # Kind is only the closed token. A bare quote, or an unquoted sentence
        # after the kind, used to keep one word (or park the whole fact in kind
        # with empty content) and the journal row lost the memory.
        known_kinds = {"fact", "quest", "rumor", "event", "system"}
        head = str(args[0] if args else "").strip()
        if head.lower() in known_kinds and len(args) > 1:
            kind = head.lower()[:40]
            content = " ".join(args[1:]).strip()
        else:
            kind = "fact"
            content = " ".join(args).strip() if args else ""
        if content:
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
    elif op == "QUEST":
        title = str(args[0] if args else flags.get("NAME", "")).strip()
        if not title:
            raise TurnDslError(f"QUEST requires a title on line {entry['line']}")
        step = flags.get("STEP") or (args[1] if len(args) > 1 else "")
        turn.setdefault("quest_marks", []).append(
            {
                "op": "QUEST",
                "title": title[:80],
                "giver": str(flags.get("GIVER") or "").strip()[:80],
                "step": str(step).strip()[:240],
                "location": str(flags.get("AT") or flags.get("LOC") or "").strip()[:80],
                "reward": str(flags.get("REWARD") or "").strip()[:160],
                "evidence": "",
            }
        )
    elif op == "QUEST_DONE":
        quest = str(args[0] if args else "").strip()
        action = str(args[1] if len(args) > 1 else "step_done").strip().lower().replace("-", "_")
        if action == "done":
            action = "step_done"
        if not quest or action not in QUEST_DONE_ACTIONS:
            raise TurnDslError(f"QUEST_DONE requires a quest and one of {', '.join(QUEST_DONE_ACTIONS)} on line {entry['line']}")
        turn.setdefault("quest_marks", []).append({"op": "QUEST_DONE", "quest": quest[:80], "action": action})
    elif op == "CAST":
        slot = str(args[0] if args else "").strip().lower()
        value = " ".join(args[1:]).strip() if len(args) > 1 else ""
        cast = turn.setdefault("scene_cast", {"present": [], "interacting": [], "off": [], "keywords": []})
        if slot in {"present", "interacting", "off"} and value:
            code = value.split()[0].upper()[:20]
            if code and code not in cast[slot]:
                cast[slot].append(code)
        elif slot == "keyword" and value:
            word = re.sub(r"[^A-Za-z0-9'-]+", "", value.split()[0]).lower()[:40]
            if len(word) >= 3 and word not in cast["keywords"]:
                cast["keywords"].append(word)


_NPC_ATTITUDES = frozenset({
    "friendly", "neutral", "hostile", "wary", "suspicious", "curious", "helpful", "cold", "warm",
    "afraid", "fearful", "nervous", "angry", "calm", "indifferent", "guarded", "kind", "rude",
})
_LOCATION_CODE_RE = re.compile(r"^\[?\[?L\d+\]?\]?$", re.I)
_SHORT_CODE_RE = re.compile(r"^\[?\[?[A-Z]{1,2}\d{0,3}\]?\]?$")


def _classify_npc_args(args: list[str]) -> dict[str, str]:
    """
    Read NPC_NEW's bare arguments by what they are, not where they sit.

    The model wrote `NPC_NEW Dockwick "Dockwick" carter L1 friendly`. Read by
    position, the second "Dockwick" became the location, and the engine minted
    a place called Dockwick and moved the carter there. A location now comes
    only from a location code (L1, [[L1]]) or the LOC flag, never a bare word.
    """
    out = {"name": "", "location": "", "role": "", "attitude": ""}
    words: list[str] = []
    for raw in args:
        token = str(raw or "").strip()
        if not token:
            continue
        if _LOCATION_CODE_RE.match(token):
            out["location"] = out["location"] or token.strip("[]").upper()
        elif token.lower() in _NPC_ATTITUDES:
            out["attitude"] = out["attitude"] or token.lower()
        elif _SHORT_CODE_RE.match(token) and not out["name"]:
            continue  # an entity code like A1, not a name
        elif not words or token.lower() != words[-1].lower():
            words.append(token)
    if words:
        out["name"] = words[0]
    rest_start = 1
    # Playtest #34 (live): "NPC_NEW Umar Mendes LOC L1" stored "Umar" with the
    # role "Mendes". Capitalised bare words after a capitalised first word are
    # the rest of the name; the job is the lower-case words after it.
    if words and words[0][:1].isupper() and " " not in words[0]:
        while (
            rest_start < len(words)
            and rest_start < 4
            and words[rest_start][:1].isupper()
            and " " not in words[rest_start]
            and words[rest_start].lower() != words[0].lower()
        ):
            out["name"] += " " + words[rest_start]
            rest_start += 1
    if len(words) > rest_start:
        # "Dockwick" "Dockwick": a repeated name is not a role.
        rest = [w for w in words[rest_start:] if w.lower() != out["name"].lower() and w.lower() != words[0].lower()]
        out["role"] = " ".join(rest[:4]) if rest else ""
    return out


def _first_sentences(text: str, limit: int) -> str:
    """Whole sentences from the start of the prose, up to ``limit`` characters, code markers removed."""
    flat = re.sub(r"\s*\[\[[A-Z0-9]+\]\]", "", str(text or ""))
    flat = re.sub(r"\s+", " ", flat).strip()
    out = ""
    for sentence in re.split(r"(?<=[.!?])\s+", flat):
        if not sentence:
            continue
        if out and len(out) + 1 + len(sentence) > limit:
            break
        out = f"{out} {sentence}".strip()
    return out[:limit]


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
        "scene_cast": {"present": [], "interacting": [], "off": [], "keywords": []},
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
        # The prose the ops were written against. The narration pipeline and
        # the depth retry rewrite the narration afterwards and can invent
        # things (a turn granted "prayer beads" the draft never mentioned,
        # then the rewrite put "beads clasped in your hands" in the final
        # text); grounding a gain must not trust text written after the grant.
        "_dsl": {"ops_count": len(ops), "source": "nar_ops", "draft_narration": narration[:5600]},
    }

    malformed_ops: list[str] = []
    for entry in ops:
        try:
            _apply_op(turn, entry)
        except TurnDslError as exc:
            # One bad line must not cost the turn every other op it got right.
            malformed_ops.append(str(exc))
    if malformed_ops:
        turn["self_check"]["issues_found"].extend(malformed_ops[:6])
        turn["self_check"]["corrections_made"].append(
            f"Skipped {len(malformed_ops)} malformed op line(s); kept the rest."
        )
        turn["_dsl"]["malformed_ops"] = len(malformed_ops)

    if not turn["turn_summary"]:
        # This summary is not scratch text: it becomes the turn_summary row and
        # from there the consolidated fact, which IS the long-term memory of what
        # the player said. Truncating it destroys the fact at write time, where no
        # retrieval can ever get it back.
        #
        # At 80 characters a 100-turn probe stored
        #     "player: I tie a red ribbon around my left wrist and explain that
        #      it is a keepsake from m"
        # cutting off "y sister Neve" -- and 64 turns later the game could not say
        # who the ribbon came from. A planted debt lost "comes due at the next full
        # moon" the same way; the lender's name survived only by sitting at
        # character 70. The field is capped at 700 downstream, so the 80 bought
        # nothing.
        intent = str(player_input or "").strip()[:400]
        # "response: scene advanced with DSL ops." told every later turn nothing
        # about what happened; the history of the Miriam Shaw save read that way
        # for two of its three turns. The scene's own first sentences do.
        happened = _first_sentences(narration, 260)
        if intent.startswith("__opening_scene_request__"):
            turn["turn_summary"] = f"opening: {happened or 'the scene opened'}"[:700]
        else:
            turn["turn_summary"] = f"player: {intent or 'acted'}. response: {happened or 'the scene moved on'}"[:700]
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
    ops, skipped = parse_ops_detailed(ops_block)
    turn = ops_to_turn(narration, ops, player_input=player_input)
    if skipped:
        turn["_dsl"]["unknown_ops"] = skipped[:8]
    return turn


def player_line_of(player_input: str) -> str:
    """The player's own input without the engine notes after it; "" for engine requests."""
    text = str(player_input or "")
    if not text.strip() or text.startswith("__"):
        return ""
    return re.split(r"\n\s*\n", text, maxsplit=1)[0].strip()


def narration_length_target(player_input: str) -> str:
    """
    ===NAR=== length for this action. The floor stays at the engine's
    1000-character depth minimum (MIN_TURN_NARRATION_CHARS), so a short turn
    does not set off a depth retry; the ceiling shrinks with a short action.
    """
    own = player_line_of(player_input)
    words = len(own.split())
    if not own or words > 30:
        return "about 1000-1800 characters"
    if words <= 12:
        return "about 1000-1200 characters"
    return "about 1000-1500 characters"


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
    # What the player said and did, as its own field, and a length that fits
    # it (playtest #30): a one-line action asked for up to 1800 characters, and
    # the model filled them by playing the player's side of the talk.
    own = player_line_of(player_input)
    if own:
        packet["player_line"] = own
        instructions.append(
            "player_line is everything you (the player) say and do this turn; write no other words or replies for the player."
        )
    packet["narration_length"] = narration_length_target(player_input)
    # Fresh per turn (app/example_pools.py): options, not people who exist.
    cast = context.get("cast_options") if isinstance(context, dict) else None
    if isinstance(cast, dict) and (cast.get("names") or cast.get("jobs")):
        packet["cast_options"] = {key: cast[key] for key in ("names", "jobs", "venue_names") if cast.get(key)}
        instructions.append(str(cast.get("rule") or ""))
    # Required-op hint, next to the opcode list where the model looks for them.
    # Only on travel turns, so ordinary turns do not pay for it.
    contract = context.get("movement_contract") if isinstance(context, dict) else None
    if isinstance(contract, dict) and contract.get("travel_intent"):
        here = (contract.get("current_location") or {}).get("code") or "the current location"
        here_name = (contract.get("current_location") or {}).get("name") or here
        instructions.append(
            f"Travel turn: if the prose ends anywhere but {here}, ===OPS=== MUST contain a MOVE line. "
            f"Without a MOVE the player is still in {here_name} when the turn ends, and the prose says so."
        )
        # The engine's heading for this walk (playtest #33): the prose follows the map.
        plan = contract.get("walk_plan") if isinstance(contract.get("walk_plan"), dict) else {}
        if plan.get("direction"):
            toward = f" toward {plan['toward']}" if plan.get("toward") else ""
            instructions.append(
                f"If the player walks, the way runs {plan['direction']}{toward}: the prose heads "
                f"{plan['direction']} and WALK says {plan['direction']}."
            )
        # Going after someone with no destination named (playtest #20).
        from app.scene_thread import follow_target

        followed = follow_target(player_input)
        if followed:
            instructions.append(
                f"The player goes after {followed}. If they lead into another place, MOVE names that place; "
                f"otherwise the pursuit stays inside {here_name}."
            )
    # Going indoors is a move on any turn, not only a travel turn (playtest #16:
    # a talk turn ended inside a herb shop with no MOVE, and the shop never existed).
    here_loc = context.get("current_location") if isinstance(context, dict) else None
    if not (isinstance(here_loc, dict) and here_loc.get("inside_venue")):
        instructions.append(
            "If ===NAR=== takes the player through a door into a shop, inn, forge, temple or other building, "
            "===OPS=== MUST contain MOVE with that building's name."
        )
    space = context.get("map_space") if isinstance(context, dict) else None
    if isinstance(space, dict) and space.get("width") and space.get("height"):
        budget = int(space.get("step_budget") or 4)
        city_clause = " One step does not cross inside a city." if space.get("scale") == "world" else ""
        instructions.append(
            f"This turn walks at most {budget} tiles. If the prose crosses country, ===OPS=== MUST contain "
            "WALK with a direction and STEPS, and a MOVE naming where the scene stops. "
            "Do not name a place beyond that walk. A door into a room is MOVE only."
            + city_clause
        )
    hint = context.get("direction_hint") if isinstance(context, dict) else None
    if isinstance(hint, dict):
        if hint.get("told"):
            instructions.append("Say direction_hint.wording. Do not add another place or a coordinate.")
        else:
            instructions.append("This question was not answered. Do not name a location for it.")
    offers = context.get("open_offers") if isinstance(context, dict) else None
    if isinstance(offers, list) and offers:
        instructions.append(
            "open_offers are posted and not yet taken. They can be accepted. The story may offer other work "
            "that fits this scene and quest_style, but not a pile of offers at once."
        )
    options = {}
    if isinstance(context, dict):
        options = ((context.get("settings") or {}).get("playthrough_options") or {})
    templates = options.get("setting_templates") if isinstance(options, dict) else None
    if isinstance(templates, dict) and templates:
        instructions.append(
            "playthrough_options.choices are this playthrough's labels. "
            "For rank_scale, use only the rungs named there."
        )
    included = ((packet.get("world_state") or {}).get("settings") or {}).get("playthrough_options") or {}
    included_rules = included.get("setting_templates") if isinstance(included, dict) else None
    if isinstance(included_rules, dict) and included_rules:
        instructions.append(
            "Follow the setting_templates rule included for this action. Do not replace its labels."
        )
    packet["instructions"] = instructions
    return __import__("json").dumps(packet, ensure_ascii=True, separators=(",", ":"))
