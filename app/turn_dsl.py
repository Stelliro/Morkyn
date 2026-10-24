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
    # Someone asks the player along or offers to take them somewhere (TODO
    # n21). An offer, not a move: the engine turns it into Go with / Stay.
    "LEAD",
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
One op per line: the op word, a space, then its parts. Prefer entity codes from world_state.
Put free text in double quotes. Parts are separated by spaces only, never by commas.

Allowed opcodes. Each line below names an op and says in words what follows it on the line;
write the real thing from this scene, never the description. Words in capitals (NAME, ROLE,
LOC, QTY, STEPS and the like) are written as shown. "May add" parts can be left out.
SUMMARY: in quotes, what this turn changed, in under 55 words, for memory.
SCENE: one of action, conversation, travel, survival, filler, lore, system.
GOAL: in quotes, one sentence on what the scene is about now.
FOCUS: one of event, location, npc, risk, resource, choice, sensory, then in quotes a few words on what it is.
NPC_NEW: the word NAME followed by the person's name in quotes, the word ROLE followed by their job, the word LOC followed by a known place's code or a place name in quotes. May add ATTITUDE, RACE and RANK, each followed by one word.
NPC_NOTE: a person's code, then in quotes one fact about them that will stay true.
TALK: the code of the person the player spoke with, then in quotes what the two of them talked about.
GRANT: the item's name in quotes, then QTY and a band. May add TYPE with a kind of item, DESC with a description in quotes, RARITY with one word.
TAKE: an item the player loses, uses up or hands over: its name in quotes, then QTY and a band (what they get is GRANT).
GOLD: the number of coins ===NAR=== names as paid or handed over, or a band when no number is said. A minus sign makes it a loss.
XP, HP: a band. A minus sign written right before the band makes it a loss.
KARMA: a band, minus for a loss. May add VIS with one of private, local, faction, public, and REASON with the reason in quotes.
MOVE: the name of the place the scene ends in (the movement rules below say which names).
WALK: a compass direction. May add STEPS and a number from 1 to 4.
LOC_NEW: the new place's name in quotes, then a description of it in quotes.
EVENT: a title in quotes. May add LOC with a place code, NPC with a person's code, SUMMARY with text in quotes.
GM: in quotes what would trigger it, then in quotes a private note for later.
REL: the code of the one who knows, the code of the one known, then in quotes what the first knows or thinks of the second. Write PLAYER for the player: a person's tie to the player (family, debt, an old promise) is REL with that person's code and PLAYER.
SKILL: the skill's name in quotes, then DELTA and a band. May add NOTES with the reason in quotes.
CLAIM: the claim in quotes, then VERDICT and one of true, false, unverified. May add SKILL with a skill's name and NOTES with the reason in quotes.
JOURNAL: one of fact, quest, rumor, event, system, then the entry in quotes.
INDEX: one of npc, location, item, event, then that one's code, then in quotes what to add to its summary.
NOTE: in quotes, one fact worth keeping in the journal.
CAST: one of present, interacting, off, then a person's code (or, for someone NPC_NEW makes this turn, their name in quotes); or keyword, then one word for the scene.
QUEST: the job's title in quotes, GIVER and the giver's code or name in quotes, STEP and the first thing to do in quotes. May add AT with a place code or name in quotes, REWARD with what was promised in quotes.
QUEST_DONE: the quest's code or title in quotes, then one of accept, step_done, complete, fail, abandon.
LEAD: the code of the person who asks the player to come along or offers to take them somewhere. May add TO with the place they named, in quotes.

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
LEAD marks an offer to take the player along. The player has not gone: ===NAR=== ends on the offer with
the player still where they are, and the player answers with their own words or the Go with and Stay buttons.
- Database/world_state is source of truth. Only propose justified changes.
- playthrough_options.choices are this playthrough's labels. For RANK, use only the rungs named in choices.rank_scale. playthrough_options.setting_templates, when present, is the one written rule this action named. Follow that included rule. Do not replace its labels.
- Amounts are bands, never numbers: none, trivial, small, moderate, large, huge.
  Band words belong on op lines only; ===NAR=== never uses one as an amount of anything.
  GRANT takes the item's name in quotes, then QTY and a band.
  A leading "-" means a loss. The app rolls the actual amount; a bare number on
  XP, HP, KARMA or SKILL is read as a band hint and re-rolled, so bands are
  shorter and more reliable.
- GOLD is the one exception. When someone in ===NAR=== names a price, a payment
  or a sum handed over, GOLD takes that same number (with "-" when the player
  pays), and the app takes exactly that. Use a band only when no number is said.
  A price only offered is not paid: no GOLD until the player agrees to it.
- GRANT and TAKE QTY counts objects: trivial or small is one, moderate two,
  large three, huge five. A real stack may be a plain number. GRANT only what
  someone in ===NAR=== gives, sells or awards the player, or what player_line itself
  takes, buys or loots. Something only found, looked at, touched, tasted or handed
  back is not granted; the player can take it next turn.
- NPC_NEW NAME is the person's own given name, the one people call them by, made for this
  world and this person. How they look or what they do is not a name; the app overwrites
  description-only names. Never give a name already used by someone else in world_state.
  cast_options.names are unused names drawn for this turn: take one or make one like them.
  NPC_NEW records someone ===NAR=== shows, and ===NAR=== calls them by that same name; a
  person the prose does not show gets no NPC_NEW.
- world_state.current_location.people: works_here marks someone who works in this place;
  works_at is that person's own workplace somewhere else, so here they are a visitor and do not
  sell, keep or own what is here. current_location.keeper keeps the place the player is inside.
  Everyone listed under people is here, in this scene. working says whether that person is
  at their job right now (the app reads it from the clock): working false means they are
  here as themselves, not at their job, and the story may still call them in. Show it in
  what they do; it is not a label to state.
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
- The scene ends when the player's action is done or someone puts something to them. After that the
  player does nothing more: no walking on, boarding, entering, taking, searching, resting, thanking or
  turning back, and no further words. The world may still move; the player's next step is theirs.
- When act_outcome is present, the engine's dice already decided how player_act turns out: write
  exactly that outcome, success or failure, and never a different one. A quest task is finished only
  when act_outcome.quest.result says done.
- world_state.mechanics_context.health_state is the player's body as the engine has it (health, band,
  conditions). Keep to it: a critical player moves and speaks like one. When health_state.downed is
  true the player goes down at the end of this action: the action does not finish, the scene ends
  with them losing consciousness, and "you" does nothing after that.
- When world_state.mechanics_context.recovery is present, the player collapsed last turn and this
  turn is the coming round, as recovery.what_happens says. The action in player_line did not happen.
  Narrate the waking, who or what is there, and the rule's mark. No HEALTH or XP line for it: the
  engine already set the player's health.
- When world_state.mechanics_context.death is present, this turn is the player's death and the last
  turn of the story: narrate it from inside the scene (death.cause is what did it), who or what is
  there, and let the scene close on it. No rescue, no waking, no next step offered, no HEALTH line.
- player_line is the player's own input and the whole of the player's turn. "you" does only what
  player_line says: no further actions, words, replies, gestures, thoughts, feelings, memories,
  conclusions or decisions. Narrate that action, then what the world and the people in it do in
  response. When someone speaks to the player, end the exchange on that line; the player answers
  next turn.
- Opening/continue: establish or advance scene; do not invent player commands.
- Keep rewards small. Empty ===OPS=== is allowed when nothing structured changes.
- Never put private GM text in ===NAR===.
- ===NAR=== must be easy to follow: direct sentences, varied but plain vocabulary, no inverted poetic templates.
"""


# In a plotted town (docs/TownGrid.md 5.3) three of the general movement
# bullets invite the draft to invent a building ("otherwise name the building
# and it is created"), say going in costs the next turn while the engine may
# walk and enter in one, and ask for WALK. While movement_contract.town is
# present they are swapped for town versions; everywhere else the system
# prompt is DSL_SYSTEM_PROMPT, byte for byte.
_GENERAL_MOVE_BULLETS = (
    (
        "- Going indoors is a MOVE. A shop, inn, forge or temple the player steps into is a place, not\n"
        "  scenery: write MOVE with that building's name. Prefer a name from movement_contract.venues_here;\n"
        "  otherwise name the building and it is created. Stepping back outside is another MOVE, to\n"
        "  movement_contract.current_location's parent. A scene that walks the player into a shop with no\n"
        "  MOVE line leaves them standing in the street, and the shop stops existing the moment it scrolls\n"
        "  out of context.\n",
        "- Going indoors is a MOVE. A building the player goes to or into is MOVE with a name from\n"
        "  world_state.town.places_here, or a street name. Nothing else is created. Stepping back outside\n"
        "  is another MOVE, to movement_contract.current_location's parent.\n",
    ),
    (
        "- A hike is at most 4 tiles. One step does not cross inside a city. When map_space.step_budget\n"
        "  is present, that is this turn's limit. A hike across country is WALK with a direction and STEPS 1-4\n"
        "  (north, south, east, west, or a compound such as northeast) plus a MOVE naming the place\n"
        "  where the walk stops. Do not invent a road, town, or wilderness farther than that walk.\n"
        "  A door into a shop or room is MOVE only — do not WALK the grid for a room.\n",
        "- In a town do not WALK. The engine walks the player along the roads to the place they asked for.\n",
    ),
    (
        "- Interiors are entered only from the place they stand in. A player two locations away cannot\n"
        "  MOVE straight into a shop — that move lands them outside it instead, and going in costs the next\n"
        "  turn. Do not narrate walking across the map and through a shop door in one turn.\n",
        "- The engine walks the player along the road and may take them inside within the same turn when\n"
        "  world_state.town.arrived says so; otherwise the scene ends at the door or on the way.\n",
    ),
)


def _town_system_prompt() -> str:
    text = DSL_SYSTEM_PROMPT
    for general, town in _GENERAL_MOVE_BULLETS:
        if text.count(general) != 1:
            raise RuntimeError("turn_dsl: a general movement bullet changed; update _GENERAL_MOVE_BULLETS")
        text = text.replace(general, town)
    return text


DSL_SYSTEM_PROMPT_TOWN = _town_system_prompt()


def in_town(context: Any) -> bool:
    """Does this turn's movement contract carry a plotted town block?"""
    contract = context.get("movement_contract") if isinstance(context, dict) else None
    return isinstance(contract, dict) and isinstance(contract.get("town"), dict)


def dsl_system_prompt_for(context: Any) -> str:
    """The DSL system prompt for this turn: the town bullets while the player is in a plotted town."""
    return DSL_SYSTEM_PROMPT_TOWN if in_town(context) else DSL_SYSTEM_PROMPT


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
_OPCODE_FLAG_KEYS: dict[str, set[str]] = {"QUEST": {"GIVER", "STEP", "AT", "REWARD"}, "LEAD": {"TO"}}
# Flags whose unquoted value may be several words ("ROLE net mender").
# Playtest #34 (live): "NAME Umar Mendes" kept only "Umar", and the roster
# lookup then minted a second person. A name runs to the next flag too.
_MULTIWORD_FLAGS = {"ROLE", "LOC", "NAME", "TO"}
# Longest unquoted run each multi-word flag may take.
_MULTIWORD_LIMIT = {"ROLE": 4, "LOC": 6, "NAME": 4, "TO": 6}
# A <slot> the model copied from a placeholder: "LOC <The Wasteland's Edge>"
# (live Qwen3 8B, playtest #28). The wrapper is syntax, not text; the span is
# read as one quoted argument. Only a bracket at a token edge counts, so
# "[[L1]]" and arrows inside quoted text are left alone.
_ANGLE_SPAN_RE = re.compile(r"(?<!\S)<\s*([^<>\n]*?)\s*>(?!\S)")
_SINGLE_QUOTED_SPAN_RE = re.compile(r"(?<!\S)'([^'\n]+?)'(?=[\s,;]|$)")
# Field words read as flags on any op line.
_FLAG_KEYS = frozenset({
    "NAME", "ROLE", "LOC", "ATTITUDE", "RACE", "RANK", "QTY", "TYPE", "DESC", "RARITY", "VIS", "REASON",
    "NPC", "SUMMARY", "DELTA", "NOTES", "VERDICT", "SKILL",
})


def _op_fields_from_op_list(text: str) -> tuple[dict[str, frozenset[str]], frozenset[str]]:
    """Each op's own field words, read from the op list the model is given
    (DSL_SYSTEM_PROMPT), so the table cannot drift from it; and the ops whose
    first part is a name in quotes (GRANT, TAKE, LOC_NEW, SKILL)."""
    fields: dict[str, frozenset[str]] = {}
    name_first: set[str] = set()
    known = set(_FLAG_KEYS) | {k for keys in _OPCODE_FLAG_KEYS.values() for k in keys}
    for m in re.finditer(r"^([A-Z_]+): (.+)$", text, re.M):
        op, body = m.group(1), m.group(2)
        if op not in OPCODES:
            continue
        words = set(re.findall(r"\b[A-Z]{2,}\b", body)) & known
        if words:
            fields[op] = frozenset(words)
        if "NAME" not in words and re.match(r"(?:the [\w' ]+?'s|[^:]*: its) name in quotes", body):
            name_first.add(op)
    return fields, frozenset(name_first)


# Playtest #28: an op's field label inside a value ("NAME: Beth", "NAME Marisol
# Carter ROLE doctor LOC clinic"). Only an op's own field words are labels, so
# "Name: the doctor is Beth" on JOURNAL and "npc: the guard" on FOCUS stay text.
_OP_FIELDS, _NAME_FIRST_OPS = _op_fields_from_op_list(DSL_SYSTEM_PROMPT)
# Ops whose first part is a person ("the code of the person ..."): TALK, REL,
# LEAD. Read from the op list like the table above.
_PERSON_FIRST_OPS = frozenset(
    m.group(1) for m in re.finditer(r"^([A-Z_]+): the code of the (?:one|person)\b", DSL_SYSTEM_PROMPT, re.M)
    if m.group(1) in OPCODES
)
# #163 (Hermes 3 8B): the NAME label left at the front of a person's name in
# a part that is not NAME's own ('LEAD: "NAME Yosef Rahman"', 'QUEST ...
# "GIVER NAME Theo"'), and a name wrapped in single quotes inside the double
# ones ('NPC_NEW: "NAME: \'Mohan Wong\'"'). Both are the op form, not the name.
_NAME_LABEL_PREFIX_RE = re.compile(r"(?:(?i:name)\s*:\s*|NAME\s+)(?=\S)")
_WRAPPED_SINGLE_RE = re.compile(r"'([^'\n]+)'")


def _bare_value(text: str, *, name_label: bool = False) -> str:
    """A part's text without the op form around it: wrapping single quotes and,
    for a name or a person, a leading NAME label."""
    value = str(text or "").strip()
    if name_label:
        label = _NAME_LABEL_PREFIX_RE.match(value)
        if label:
            value = value[label.end():].strip()
    wrapped = _WRAPPED_SINGLE_RE.fullmatch(value)
    return wrapped.group(1).strip() if wrapped else value


# #163 (Hermes 3 8B, live/integ-r3 T1): every op on the list written, the ones
# the scene did not need filled with a placeholder ("MOVE: None", "LOC_NEW:
# None", "EVENT: None"), minted a place and an event called None. An op whose
# only value is one of these is no op. GOLD, XP, HP and KARMA take "none" as a
# band (the op list's amounts), which already changes nothing, so they keep it.
# Final live replay 2026-10-24: "LOC_NEW: not present" minted a place called "Not".
# A closed set of empty values (orthographic no-ops, rule 3), not a list for meaning.
_PLACEHOLDER_VALUES = frozenset({
    "", "none", "null", "n/a", "na", "-", "--", "nothing", "not present", "not applicable",
    "no change", "none needed", "empty",
})
_BAND_OPS = frozenset({"GOLD", "XP", "HP", "KARMA"})
# The item ops: a name in quotes, then QTY and a band (F194: the band's own
# label, BAND, written out is a field of these two).
_ITEM_OPS = frozenset({"GRANT", "TAKE"})


def _is_placeholder_op(op: str, positionals: list[str], flags: dict[str, str]) -> bool:
    if op in _BAND_OPS or flags:
        return False
    text = " ".join(str(p) for p in positionals).strip().strip("\"'.,;:").strip().lower()
    return text in _PLACEHOLDER_VALUES


def _labelled_parts(value: str, fields: frozenset[str] | set[str]) -> list[tuple[str, str]] | None:
    """A quoted value that opens on one of the op's own field labels, split at
    each of them: "NAME: Beth, ROLE: doctor" -> [(NAME, Beth), (ROLE, doctor)].
    A label is the field word with a colon (any case), or the word in capitals
    alone ("NAME Jonah Park"). None when the value does not open on a label."""
    if not fields:
        return None
    words = "|".join(sorted(fields, key=len, reverse=True))
    label_re = re.compile(rf"(?:^|(?<=[\s,;]))(?:(?i:({words}))\s*:|({words})(?=\s))")
    marks = [m for m in label_re.finditer(value)]
    if not marks or marks[0].start() != len(value) - len(value.lstrip()):
        return None
    parts: list[tuple[str, str]] = []
    for at, m in enumerate(marks):
        end = marks[at + 1].start() if at + 1 < len(marks) else len(value)
        text = value[m.end():end].strip().strip(",;").strip()
        if not text:
            return None
        parts.append(((m.group(1) or m.group(2)).upper(), text))
    return parts


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

    def _pull_single(match: re.Match[str]) -> str:
        body = match.group(1).strip()
        if not body or "__STR" in body:
            return match.group(0)
        strings.append(_decode_arg_escapes(body))
        return f" __STR{len(strings) - 1}__ "

    # #163 (Hermes 3 8B, cc87dd29): "QUEST: 'Seek medical treatment' GIVER B"
    # filed a job called "'Seek". Single quotes around a whole part are quotes:
    # only a quote at a part's edge counts, so "Beth's" is left alone.
    working = _SINGLE_QUOTED_SPAN_RE.sub(_pull_single, working)
    # Playtest #74 (live): `NPC_NEW: "Fenella Goodwin", "woodward", "L1"` stored
    # the role ", woodward ,"; `TALK A, "..."` stored the code "A,". Commas and
    # semicolons between parts are list punctuation, never part of a value.
    strings[:] = [s.strip().strip(",;").strip() for s in strings]
    # An unbalanced edge left over ("LOC <The"): drop the stray bracket.
    parts = [p.strip("<>").strip(",;") for p in working.split()]
    parts = [p for p in parts if p]
    if not parts:
        return "", [], {}
    opcode = parts[0].upper()
    positionals: list[str] = []
    flags: dict[str, str] = {}
    flag_keys = set(_FLAG_KEYS)
    # Flag words that only mean something on one op. "AT" and "STEP" are
    # ordinary words elsewhere, so they are flags on QUEST lines alone.
    flag_keys = flag_keys | _OPCODE_FLAG_KEYS.get(normalize_opcode(opcode), set())
    force_positional_remaining = _LEADING_POSITIONALS.get(opcode, 0)
    own_op = normalize_opcode(opcode)
    own_fields = _OP_FIELDS.get(own_op, frozenset())
    # F194 (sonnet100 T13): 'TAKE: "BAND: small"' on a line of its own filed an
    # item called "BAND: small". The op list says "QTY and a band"; the band's
    # label written out is this field of GRANT and TAKE, never the name.
    if own_op in _ITEM_OPS:
        own_fields = own_fields | {"BAND"}
        flag_keys = flag_keys | {"BAND"}

    def _is_label(tok: str) -> bool:
        return (tok.endswith(":") and tok[:-1].upper() in own_fields) or tok in own_fields

    if own_fields and not force_positional_remaining:
        # #163 (Hermes 3 8B, live/integ-r3 opening): each field label quoted as
        # its own part, 'NPC_NEW: "NAME" "Theo" "ROLE" "drifter" "LOC" "L1"',
        # minted a person called "NAME Theo ROLE"; 'QUEST ... "giver": "Hiro
        # Morgan", "STEP": "..."' filed the step "giver". A quoted part that is
        # exactly one of this op's own field labels is that label.
        relabelled: list[str] = []
        for tok in parts[1:]:
            if tok == ":" and relabelled and relabelled[-1].endswith(":"):
                continue
            quoted = re.fullmatch(r"__STR(\d+)__", tok)
            label = strings[int(quoted.group(1))].strip().rstrip(":").strip().upper() if quoted else ""
            relabelled.append(f"{label}:" if label in own_fields else tok)
        parts = parts[:1] + relabelled

    i = 1
    while i < len(parts):
        token = parts[i]
        # 'SKILL: name: "perception", DELTA: ...' (#163) filed a skill called
        # "name:": the label of the name these ops open on, written bare.
        if own_op in _NAME_FIRST_OPS and not positionals and token.lower() == "name:":
            i += 1
            continue
        # Playtest #28: "NAME: Beth ROLE: doctor", "REASON: starting conflict".
        # One of this op's own field words with a colon is that field, and its
        # unquoted value runs to the op's next field label. Any other word with
        # a colon is text ("JOURNAL: fact, Name: the doctor is Beth").
        if token.endswith(":") and token[:-1].upper() in own_fields and not force_positional_remaining:
            key_u = token[:-1].upper()
            i += 1
            if i < len(parts) and re.fullmatch(r"__STR(\d+)__", parts[i]):
                flags.setdefault(key_u, _bare_value(strings[int(parts[i][5:-2])], name_label=key_u == "GIVER"))
                i += 1
                continue
            words: list[str] = []
            while i < len(parts) and not _is_label(parts[i]) and not re.fullmatch(r"__STR\d+__", parts[i]):
                words.append(_decode_arg_escapes(parts[i]))
                i += 1
            if words:
                flags.setdefault(key_u, " ".join(words))
            continue
        # F194 (sonnet100 T14): "QTY:1", "BAND:small"; one of this op's own
        # field labels glued to its value by the colon is that field, not a
        # word of the item's name.
        glued = re.fullmatch(r"([A-Za-z]+):(\S+)", token) if not force_positional_remaining else None
        if glued and glued.group(1).upper() in own_fields:
            glued_value = glued.group(2)
            glued_str = re.fullmatch(r"__STR(\d+)__", glued_value)
            flags.setdefault(glued.group(1).upper(), strings[int(glued_str.group(1))] if glued_str else _decode_arg_escapes(glued_value))
            i += 1
            continue
        upper = token.upper()
        str_match = re.fullmatch(r"__STR(\d+)__", token)
        if str_match:
            value = strings[int(str_match.group(1))]
            # Playtest #28 (Hermes 3 8B, cc87dd29 T10): NPC_NEW: "NAME: Beth"
            # minted a second person called "NAME: Beth" beside Beth [[B]], and
            # QUEST "AT: New Vegas" lost its place (T2). The op's own field
            # labels opening a quoted part label it; they are not its text
            # ("NAME Marisol Carter ROLE doctor LOC clinic", T14).
            labelled = _labelled_parts(value, own_fields) if not force_positional_remaining else None
            if labelled:
                for key_u, text in labelled:
                    flags.setdefault(key_u, _bare_value(text, name_label=key_u == "GIVER"))
                i += 1
                continue
            # LOC_NEW "NAME: The Rusty Bar": the name these ops open on, labelled.
            if own_op in _NAME_FIRST_OPS and not positionals:
                named = re.match(r"(?i)\s*name\s*:\s*(\S.*)$", value, re.S)
                if named:
                    value = _bare_value(named.group(1))
                # #163: 'GRANT: "Ripped Doctor Parts; QTY: 2; BAND: small"'
                # stored all of it as the item's name. The name ends where one
                # of the op's own labels starts.
                tail = re.search(
                    r"\s*[;,]\s*(?=(?i:%s)\s*:)" % "|".join(sorted(own_fields, key=len, reverse=True)), value
                ) if own_fields else None
                if tail and tail.start() > 0:
                    for seg in re.split(r"\s*;\s*", value[tail.end():]):
                        seg_label = re.match(r"(?i)\s*(\w+)\s*:\s*(\S.*)$", seg)
                        if seg_label and seg_label.group(1).upper() in own_fields:
                            flags.setdefault(seg_label.group(1).upper(), seg_label.group(2).strip())
                    value = value[:tail.start()].strip()
            elif own_op in _PERSON_FIRST_OPS and not positionals:
                value = _bare_value(value, name_label=True)
            positionals.append(value)
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
    "FOLLOW_ME": "LEAD",
    "INVITE": "LEAD",
    "ESCORT": "LEAD",
    "GUIDE": "LEAD",
    "LEAD_TO": "LEAD",
}


def normalize_opcode(opcode: str) -> str:
    """Map a near-miss opcode onto the closed list, or return '' if unrecognized."""
    # "TALK:" -- the op legend describes each op after a colon (playtest #39).
    token = str(opcode or "").strip().rstrip(":").upper().replace("-", "_")
    if token in OPCODES:
        return token
    return OPCODE_ALIASES.get(token, "")


def parse_ops(ops_block: str) -> list[dict[str, Any]]:
    return parse_ops_detailed(ops_block)[0]


def parse_ops_detailed(
    ops_block: str, placeholders: list[str] | None = None
) -> tuple[list[dict[str, Any]], list[str]]:
    """Ops plus the lines whose opcode is not on the list (they used to vanish untraced).

    An op whose only value is a placeholder ("MOVE: None") is no op: it is left
    out, and its line goes to ``placeholders`` when a list is given (#163)."""
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
        canonical = normalize_opcode(opcode)
        if positionals and positionals[0] == ":":
            positionals = positionals[1:]
        # An empty op counts only in the shape Hermes writes it ("EVENT: "); a
        # bare op word with nothing after it stays a malformed line.
        if canonical and (positionals or stripped.endswith(":")) and _is_placeholder_op(canonical, positionals, flags):
            if placeholders is not None:
                placeholders.append(stripped[:80])
            continue
        seen_lines += 1
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


_KARMA_VISIBILITY = frozenset({"private", "local", "faction", "public"})


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


# A copied slot word (playtest #39): one all-lowercase identifier such as
# "choose_direction" or "topic_of_the_exchange". No sentence, topic or summary
# has that shape, so it is a malformed line, not a value. Structural only.
_SLOT_TOKEN_RE = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+")
# Old op-list slot names that could come back as a destination.
_PLACE_SLOT_WORDS = frozenset({
    "place_name", "location_code", "location_code_or_place_name", "place_code", "place_code_or_name",
})


def is_slot_token(value: Any) -> bool:
    """True when ``value`` is a lone snake_case identifier, not prose."""
    text = str(value or "").strip().strip("\"'\u201c\u201d").strip()
    return bool(text) and bool(_SLOT_TOKEN_RE.fullmatch(text))


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
        if is_slot_token(" ".join(args)):
            raise TurnDslError(f"SUMMARY holds a slot word, not a summary, on line {entry['line']}")
        turn["turn_summary"] = " ".join(args)[:700] or turn["turn_summary"]
    elif op == "SCENE":
        turn["scene_focus"] = (args[0] if args else "action")[:40]
    elif op == "GOAL":
        if is_slot_token(" ".join(args)):
            raise TurnDslError(f"GOAL holds a slot word, not a goal, on line {entry['line']}")
        turn["scene_plan"]["goal"] = " ".join(args)[:400]
    elif op == "FOCUS":
        kind = (args[0] if args else "event")[:40]
        summary = " ".join(args[1:]) if len(args) > 1 else flags.get("SUMMARY", "beat")
        if is_slot_token(summary):
            raise TurnDslError(f"FOCUS holds a slot word, not a summary, on line {entry['line']}")
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
        name = _strip_name_codes(name)
        note = ""
        role_arg = flags.get("ROLE") or positional["role"]
        if _role_is_note(role_arg):
            # Kept as what is known about them; the job comes from the prose
            # that introduces them (world._roles_stated_in_prose) or stays open.
            note = re.sub(r"^\s*works?_at\b", "works at", str(role_arg).strip(), flags=re.I)
            if flags.get("ROLE"):
                flags["ROLE"] = ""
            positional["role"] = ""
        else:
            # "grocer Quarrel and Sons": the job, then the shop's name glued on
            # (7B run 16, T0). The job stays; the shop is what is known.
            glued = re.match(r"^(?P<job>[a-z][a-z' -]*?)\s+(?P<place>[A-Z][\w'’-]*(?:\s+(?:and|of|the|&)?\s*[A-Z][\w'’-]*)*)$",
                             str(role_arg or "").strip())
            if glued:
                note = f"works at {glued.group('place')}"
                if flags.get("ROLE"):
                    flags["ROLE"] = glued.group("job")
                else:
                    positional["role"] = glued.group("job")
        npc = {
            "code": None,
            "name": name[:120],
            "race": flags.get("RACE", "human")[:80],
            "location": flags.get("LOC") or positional["location"],
            "role": (flags.get("ROLE") or positional["role"] or "local")[:80],
            # Nothing known yet stays empty (playtest #24). A placeholder here
            # was stored as the summary and the first NPC_NOTE glued onto it:
            # "Introduced this turn: Aria Aria is a baker ...".
            "summary": (flags.get("DESC") or note or "")[:400],
            "attitude": (flags.get("ATTITUDE") or positional["attitude"] or "neutral")[:40],
            "personality": "",
            "likes": "",
            "principles": "",
            "dislikes": "",
            "rank": flags.get("RANK", "")[:8],
            "stat_profile": {},
            "skill_profile": {},
            "trust_delta": 0,
            "known_fact": note[:400],
            "mentioned_by": None,
        }
        if note:
            from app import turn_ledger

            turn_ledger.note("npc", "role_was_a_note", name=name, note=note)
        if positional.get("places") and not flags.get("ROLE"):
            npc["_place_candidates"] = list(positional["places"])
        turn["npcs"].append(npc)
    elif op == "NPC_NOTE":
        if args:
            args[0] = _strip_name_codes(args[0])
        code = (args[0] if args else "").upper()
        # Join every token after the code. A quoted fact is one arg; an unquoted
        # fact is many. Taking only args[1] stored "the" and dropped the rest.
        fact = " ".join(args[1:]).strip()
        name = ""
        if len(args) == 1 and "," in args[0]:
            # One quoted arg holding the person and the fact (7B run 6, T9):
            # NPC_NOTE "Oldfield B, village reeve, stern but fair".
            head, _, fact = args[0].partition(",")
            fact = fact.strip()
            words = head.replace("[", " ").replace("]", " ").split()
            if words and re.fullmatch(r"[A-Z][A-Z0-9]{0,2}", words[-1]):
                code = words[-1]
                name = " ".join(words[:-1])
            else:
                code = ""
                name = " ".join(words)
        elif args and " " in args[0].strip():
            # A full name in the code slot ("Linnet Eastlake"): matched by name.
            name = args[0].strip()
        if not (code or name) or not fact:
            raise TurnDslError(f"NPC_NOTE requires code and fact on line {entry['line']}")
        update = {"entity_type": "npc", "code": code or name, "summary_append": fact[:400], "known_fact": fact[:400]}
        if name:
            update["name"] = name
        turn["index_updates"].append(update)
    elif op == "TALK":
        # A code is upper-cased; a name stays as written. Upper-cased, "Linnet
        # Eastlake" became the code "LINNET EASTLAKE" and the prose was tagged
        # "Linnet Eastlake [[LINNET EASTLAKE]]" (7B run 8, T0).
        ref = _strip_name_codes(args[0] if args else "")
        code = ref.upper() if " " not in ref else ref
        topic = " ".join(args[1:]).strip() if len(args) > 1 else "conversation"
        if not code:
            raise TurnDslError(f"TALK requires npc code on line {entry['line']}")
        if is_slot_token(topic):
            raise TurnDslError(f"TALK holds a slot word, not a topic, on line {entry['line']}")
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
        if qty_token in (None, ""):
            qty_token = flags.get("BAND")
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
        if qty_token in (None, ""):
            qty_token = flags.get("BAND")
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
        # The visibility written where the band goes (7B runs 5-9: KARMA "public"
        # "large", KARMA "moderate" "private") is the VIS flag; the band is the
        # other argument.
        args = list(args)
        visibility = flags.get("VIS")
        for index, arg in enumerate(args[:2]):
            if str(arg).strip().lower() in _KARMA_VISIBILITY:
                visibility = visibility or str(arg).strip().lower()
                args.pop(index)
                break
        _apply_amount(turn["player"], band_key="karma_band", number_key="karma_delta", token=args[0] if args else None)
        turn["player"]["karma_visibility"] = (visibility or "private")[:40]
        turn["player"]["karma_reason"] = flags.get("REASON") or (" ".join(args[1:]) if len(args) > 1 else "")
    elif op == "MOVE":
        dest = " ".join(args).strip()
        if not dest:
            raise TurnDslError(f"MOVE requires destination on line {entry['line']}")
        if dest.strip("\"'").lower() in _PLACE_SLOT_WORDS:
            raise TurnDslError(f"MOVE holds a slot word, not a place, on line {entry['line']}")
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
                "source_code": _person_ref(args[0]),
                "target_code": _person_ref(args[1]),
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
        if head.lower() in known_kinds and len(args) == 1:
            # 'JOURNAL: "fact"' (Hermes 3 8B, #163): the kind with no entry
            # stored a journal line reading "fact".
            raise TurnDslError(f"JOURNAL has a kind and no entry on line {entry['line']}")
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
    elif op == "LEAD":
        # Kept on _dsl, which the trace keeps and the verifier never sees: an
        # offer is checked by the engine (app/turn_prompts.py), not rewritten.
        who = re.sub(r"^\[\[|\]\]$", "", str(args[0] if args else flags.get("NPC", "")).strip()).strip("[]")
        if not who:
            raise TurnDslError(f"LEAD requires the person's code on line {entry['line']}")
        to = str(flags.get("TO") or (" ".join(args[1:]) if len(args) > 1 else "")).strip()
        if re.fullmatch(r"to", to.split(" ")[0] if to else "", re.I):
            to = to.split(" ", 1)[1] if " " in to else ""
        turn["_dsl"].setdefault("leads", []).append({"npc": who[:40], "to": to[:120]})
    elif op == "CAST":
        if _cast_slot_chain(turn, args):
            return
        slot = str(args[0] if args else "").strip().lower()
        value = " ".join(args[1:]).strip() if len(args) > 1 else ""
        # "CAST interacting [[H]] Tam" leads with the person's code on purpose;
        # a place or item code before a name ("L1 Linnet Eastlake") is not a
        # person (7B run 8, T0: the place L1 was cast).
        words = value.split()
        if len(words) > 1 and re.fullmatch(r"\[?\[?[LIE]\d+\]?\]?", words[0]):
            value = " ".join(words[1:])
        cast = turn.setdefault("scene_cast", {"present": [], "interacting": [], "off": [], "keywords": []})
        if slot in {"present", "interacting", "off"} and value:
            # "CAST interacting [[B]]": the prose tag is not the code (playtest
            # #46). A quoted name stays a name, so a person made by NPC_NEW this
            # turn can be cast before their code exists (Saltmarrow #106).
            first = value.split()[0]
            bare = first.strip("[]")
            is_code = first.startswith("[[") or bool(re.fullmatch(r"[A-Z]{1,3}\d{0,3}", bare))
            code = _person_ref(first if is_code or len(value.split()) == 1 else value)[:60]
            if code and code not in cast[slot]:
                cast[slot].append(code)
        elif slot == "keyword" and value:
            word = re.sub(r"[^A-Za-z0-9'-]+", "", value.split()[0]).lower()[:40]
            if len(word) >= 3 and word not in cast["keywords"]:
                cast["keywords"].append(word)


_CAST_SLOTS = ("present", "interacting", "off")


def _cast_slot_chain(turn: dict[str, Any], args: list[Any]) -> bool:
    """Hermes 3 8B's CAST shape: slots chained before the code ("CAST: present, interacting, A",
    'CAST:"present interacting A"'), read as the person "interacting A" (live replays 2026-10-24:
    every recorded run; the cast was empty, so a person on record elsewhere was never brought to
    the player). A narrow repair of that one shape (CLAUDE.md rule 3): when every word is a slot
    name or a person code, each code goes into every slot named before it. Anything with a name
    in it keeps the ordinary path.
    """
    words = [w for w in re.split(r"[\s,;]+", " ".join(str(a) for a in args).replace('"', " ").strip()) if w]
    if len(words) < 3 or words[0].lower() not in _CAST_SLOTS:
        return False
    if not all(w.lower() in _CAST_SLOTS or re.fullmatch(r"\[?\[?[A-Z]{1,3}\d{0,3}\]?\]?", w) for w in words):
        return False
    if sum(1 for w in words if w.lower() in _CAST_SLOTS) < 2:
        return False
    cast = turn.setdefault("scene_cast", {"present": [], "interacting": [], "off": [], "keywords": []})
    slots: list[str] = []
    last_was_code = False
    for word in words:
        if word.lower() in _CAST_SLOTS:
            if last_was_code:
                slots = []
            slots.append(word.lower())
            last_was_code = False
            continue
        code = word.strip("[]").upper()
        for slot in slots or ["present"]:
            if code not in cast[slot]:
                cast[slot].append(code)
        last_was_code = True
    return True


PLAYER_REF = "PLAYER"
_PLAYER_WORDS = frozenset({"you", "player", "the player", "me", "i", "pc", "self", "yourself", "@player", "@you"})


def _person_ref(token: Any) -> str:
    """A person in REL / CAST: "PLAYER" for the player, a code upper-cased, a name as written.

    Saltmarrow #106: "REL K YOU ..." became the code YOU, which no row holds,
    and "REL Mara Tarrow ..." was upper-cased so the name lookup missed.
    """
    text = re.sub(r"^\[\[|\]\]$", "", str(token or "").strip()).strip("[]").strip()
    if text.lower() in _PLAYER_WORDS:
        return PLAYER_REF
    if re.fullmatch(r"[A-Za-z]{1,3}\d{0,3}", text) and (text.isupper() or len(text) <= 2):
        return text.upper()
    return text


_NPC_ATTITUDES = frozenset({
    "friendly", "neutral", "hostile", "wary", "suspicious", "curious", "helpful", "cold", "warm",
    "afraid", "fearful", "nervous", "angry", "calm", "indifferent", "guarded", "kind", "rude",
})
_LOCATION_CODE_RE = re.compile(r"^\[?\[?L\d+\]?\]?$", re.I)
_SHORT_CODE_RE = re.compile(r"^\[?\[?[A-Z]{1,2}\d{0,3}\]?\]?$")
# An entity code at the edge of a name slot (7B run 8, T0): NPC_NEW / TALK /
# NPC_NOTE / CAST "L1 Linnet Eastlake" made a person called "L1 Linnet
# Eastlake", cast the place L1, and the prose later read "Saltmarrow [[L1]]
# Linnet Eastlake". A bracketed tag or a letter-and-number code is never part
# of a name; a bare single trailing capital ("Oldfield B") is a person code,
# except the roman numerals a name can end with.
_EDGE_CODE_RE = re.compile(r"\[\[[A-Z0-9]{1,4}\]\]|[A-Z]{1,2}\d{1,3}")
_TRAILING_LETTER_CODE_RE = re.compile(r"[A-HJ-UWYZ]")


def _strip_name_codes(text: Any) -> str:
    """Take entity codes off the ends of a multi-word name; a lone code is left alone."""
    raw = str(text or "").strip()
    words = raw.split()
    if len(words) < 2:
        return raw
    while len(words) > 1 and _EDGE_CODE_RE.fullmatch(words[0]) and words[1][:1].isupper():
        words.pop(0)
    while len(words) > 1 and (
        _EDGE_CODE_RE.fullmatch(words[-1]) or _TRAILING_LETTER_CODE_RE.fullmatch(words[-1])
    ) and words[-2][:1].isupper():
        words.pop()
    return " ".join(words)


# A role argument that is a note, not a job (7B run 8, T0): NPC_NEW "Linnet"
# "works_at the Wren's Rest, reliable and concerned for your safety" stored all
# of that as her job. Shape only: a comma, a works_at slot word, or a sentence.
_NOTE_ROLE_RE = re.compile(r"^\s*works?[_ ]at\b|,", re.I)


def _role_is_note(role: str) -> bool:
    text = str(role or "").strip()
    return bool(text) and (bool(_NOTE_ROLE_RE.search(text)) or len(text.split()) > 6)


def _classify_npc_args(args: list[str]) -> dict[str, str]:
    """
    Read NPC_NEW's bare arguments by what they are, not where they sit.

    The model wrote `NPC_NEW Dockwick "Dockwick" carter L1 friendly`. Read by
    position, the second "Dockwick" became the location, and the engine minted
    a place called Dockwick and moved the carter there. A location now comes
    only from a location code (L1, [[L1]]) or the LOC flag, never a bare word.
    """
    out: dict[str, Any] = {"name": "", "location": "", "role": "", "attitude": ""}
    words: list[str] = []
    for raw in args:
        token = _strip_name_codes(raw)
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
    # 7B run 4 (T1): NPC_NEW A "tinker" "Helewise Eastlake" "off" made a person named
    # "tinker" whose job was "Helewise Eastlake off", and every later mention of
    # Helewise was relabelled through it. A lower-case job word in the name slot
    # with a capitalised name after it is the job; the name is the name.
    if words and not any(ch.isupper() for ch in words[0]):
        for index in range(1, min(len(words), 4)):
            candidate = words[index]
            parts = candidate.split()
            if (
                1 <= len(parts) <= 3
                and all(p[:1].isupper() and re.fullmatch(r"[A-Za-z'\-]+", p) for p in parts)
                and parts[0].lower() not in {"the", "a", "an", "old", "north", "south", "east", "west"}
            ):
                words = [candidate, words[0]] + [w for i, w in enumerate(words[1:], 1) if i != index]
                out["name"] = candidate
                break
    # A scene-cast keyword is not part of anyone's job.
    words = [w for i, w in enumerate(words) if i == 0 or w.lower() not in {"off", "present", "interacting"}]
    if len(words) > rest_start:
        # "Dockwick" "Dockwick": a repeated name is not a role.
        rest = [w for w in words[rest_start:] if w.lower() != out["name"].lower() and w.lower() != words[0].lower()]
        out["role"] = " ".join(rest[:4]) if rest else ""
        # A quoted capitalised phrase after the job may be a place (live gate N1:
        # NPC_NEW "Mira Kettle" "shopkeeper" "The Kettle at The"). ops_to_turn
        # reads it as the place only when this turn's MOVE or LOC_NEW names it.
        places = [w for w in rest[:4] if " " in w and w[:1].isupper()]
        if places:
            out["places"] = places
    return out


def _settle_npc_place_candidates(turn: dict[str, Any]) -> None:
    """A positional NPC_NEW phrase that this turn's MOVE or LOC_NEW names is the
    person's place, not part of their job; anything else stays in the role."""
    named = {
        str(loc.get("name") or "").strip().lower()
        for loc in turn.get("locations") or []
        if isinstance(loc, dict) and str(loc.get("name") or "").strip()
    }
    move = str((turn.get("player") or {}).get("move_to_location") or "").strip().lower()
    if move:
        named.add(move)
    for npc in turn.get("npcs") or []:
        candidates = npc.pop("_place_candidates", None) if isinstance(npc, dict) else None
        for phrase in candidates or []:
            if phrase.strip().lower() not in named:
                continue
            role = re.sub(r"\s+", " ", str(npc.get("role") or "").replace(phrase, " ")).strip()
            npc["role"] = role or "local"
            if not str(npc.get("location") or "").strip():
                npc["location"] = phrase
            break


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
    _settle_npc_place_candidates(turn)
    # What this draft granted. A later patch can empty inventory_changes; a GOLD
    # loss that paid for these is void when none of them arrive (playtest #41).
    grants = [
        str(change.get("name") or "")[:120]
        for change in turn["inventory_changes"]
        if isinstance(change, dict)
        and str(change.get("name") or "").strip()
        and not str(change.get("quantity_band") or "").strip().startswith("-")
        and int(change.get("quantity_delta") or 0) >= 0
    ]
    if grants:
        turn["_dsl"]["grants"] = grants[:12]
    if malformed_ops:
        # The engine already skipped these lines; they are not draft issues.
        # In self_check.issues_found the verifier echoed them back ("INDEX
        # requires type code summary on line 7") and rewrote the narration
        # to answer them, 27-36 s a turn that fixed no fact (playtest #43).
        # They stay in _dsl, which the trace keeps and the verifier never sees.
        turn["_dsl"]["malformed_op_notes"] = malformed_ops[:6]
        # A dropped line is a refusal: on the ledger too (F194, sonnet100 T13:
        # 'TAKE: "BAND: small"' is the band field alone, no item name).
        try:
            from app import turn_ledger

            turn_ledger.note("ops", "malformed_op_dropped", errors=malformed_ops[:6])
        except Exception:
            pass
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


_GLUED_THE_RE = re.compile(r"\b([Tt])he([a-z]{4,})\b")


def unglue_the(text: str, also: str = "") -> str:
    """Split "the" glued to the next word when that word also stands alone in the text.

    7B run 32 wrote "theflats" from T1 on; the engine stored a place "Theflats"
    and a fact about it, and both came back in every prompt. "Theobald" stays:
    "obald" never stands alone.
    """
    source = str(text or "")
    if not _GLUED_THE_RE.search(source):
        return source
    alone = {w.lower() for w in re.findall(r"\b[a-z]{4,}\b", f"{source} {also}", re.I)}

    def _split(match: re.Match[str]) -> str:
        rest = match.group(2)
        return f"{match.group(1)}he {rest}" if rest in alone else match.group(0)

    return _GLUED_THE_RE.sub(_split, source)


# A spoken line in straight single quotes: opens after a line start, a space or
# a dash, starts with a capital, and closes on its own punctuation before the
# quote. An apostrophe inside it is one before a letter ("I'm", "flat-runner's").
_SINGLE_QUOTED_LINE_RE = re.compile(
    r"(?:(?<=^)|(?<=[\s(—–-]))'(?P<body>[A-Z](?:[^'\n]|'(?=[A-Za-z]))*?[.,!?…])'(?=\s|$|[)—–-])",
    re.M,
)


def double_single_quoted_speech(narration: str) -> str:
    """Write a paragraph's single-quoted dialogue in double quotes.

    7B run 35, T1 wrote every line in single quotes, and every speech pass reads
    double ones, so "You show him the tools and explain, 'I'm going to patch up
    this plank.'" kept a line the player never said. Only a paragraph with no
    double quotes is touched, so a quote inside a quote stays as it is.
    """
    paragraphs = re.split(r"(\n\s*\n)", str(narration or ""))
    for index in range(0, len(paragraphs), 2):
        para = paragraphs[index]
        if re.search(r"[\"“”]", para) or "'" not in para:
            continue
        paragraphs[index] = _SINGLE_QUOTED_LINE_RE.sub(lambda m: f"\"{m.group('body')}\"", para)
    return "".join(paragraphs)


def parse_dsl_turn(text: str, player_input: str = "") -> dict[str, Any]:
    text = unglue_the(text, player_input)
    narration, ops_block = split_nar_ops(text)
    narration = double_single_quoted_speech(narration)
    placeholders: list[str] = []
    ops, skipped = parse_ops_detailed(ops_block, placeholders)
    turn = ops_to_turn(narration, ops, player_input=player_input)
    if skipped:
        turn["_dsl"]["unknown_ops"] = skipped[:8]
    if placeholders:
        turn["_dsl"]["placeholder_ops"] = placeholders[:24]
        from app import turn_ledger

        turn_ledger.note("ops", "placeholder_op_dropped", lines=placeholders[:24])
    return turn


ACT_OUTCOME_RULE = (
    "act_outcome was decided by the dice before you write: player_act turns out exactly as act_outcome.means "
    "(outcome and degree say how well). Failure: it goes wrong or falls short, and the people watching react "
    "to that. Success: it works. Do not soften it, upgrade it or leave it undecided. When act_outcome.injury "
    "is present, that hurt happens in the scene."
)
# The act was the work of an open quest (playtest #85b, T7: the job was done in
# the prose and never in the game). The engine has decided the step already.
ACT_QUEST_RULE = (
    "act_outcome.quest says what this act did for the player's quest, decided by the engine: write "
    "act_outcome.quest.result as it says. Done: the job or step is finished and whoever gave it sees that, and pays "
    "exactly what result names. Not done: the job is still open. Never call a quest task finished, or pay for it, "
    "unless result says done."
)
PREVIOUS_ACT_RULE = (
    "previous_act is how the player's last attempt turned out (outcome). Keep to it: work that failed is still "
    "not done, work that succeeded stays done, and nobody remembers it differently. When act_outcome is also "
    "present, it is a new attempt this turn and its outcome is the one that stands now."
)


def _mechanics_of(context: Any) -> dict[str, Any]:
    mech = context.get("mechanics_context") if isinstance(context, dict) else None
    return mech if isinstance(mech, dict) else {}


def act_outcome_of(context: Any) -> dict[str, Any] | None:
    """The engine's outcome for this turn's declared act (playtest #85a), or None."""
    note = _mechanics_of(context).get("act_outcome")
    return note if isinstance(note, dict) and note.get("outcome") else None


def previous_act_of(context: Any) -> dict[str, Any] | None:
    """How the last rolled act turned out (playtest #85a), or None."""
    note = _mechanics_of(context).get("previous_act")
    return note if isinstance(note, dict) and note.get("outcome") else None


def player_line_of(player_input: str) -> str:
    """The player's own input without the engine notes after it; "" for engine requests."""
    text = str(player_input or "")
    if not text.strip() or text.startswith("__"):
        return ""
    return re.split(r"\n\s*\n", text, maxsplit=1)[0].strip()


NARRATION_DEPTH_FLOOR_DEFAULT = 600
NARRATION_DEPTH_FLOOR_RANGE = (300, 1500)


def narration_depth_floor() -> int:
    """
    The prose depth floor with the paragraph writer off (playtest #52):
    AI_RPG_MIN_NARRATION_CHARS, clamped, default 600. The draft is the prose
    now, and a hard-coded 1000 sent about half of all live turns (700-860
    characters, already whole scenes) through a second generation.
    """
    import os

    raw = str(os.getenv("AI_RPG_MIN_NARRATION_CHARS", "") or "").strip()
    try:
        value = int(float(raw)) if raw else NARRATION_DEPTH_FLOOR_DEFAULT
    except ValueError:
        value = NARRATION_DEPTH_FLOOR_DEFAULT
    low, high = NARRATION_DEPTH_FLOOR_RANGE
    return max(low, min(high, value))


def _writer_enabled() -> bool:
    from app.narration_pipeline import pipeline_enabled

    return pipeline_enabled()


def narration_length_target(player_input: str) -> str:
    """
    ===NAR=== length for this action, kept in step with the depth floor so the
    ask and the retry agree. A one-line action gets a short scene (playtest
    #30): a fixed 1000-character demand was filled by playing the player's
    side, following, nodding, wondering and deciding for them.

    With the paragraph writer on, the writer sets the length, and the draft
    keeps its old 1000-character ask.
    """
    own = player_line_of(player_input)
    words = len(own.split())
    if _writer_enabled():
        if not own or words > 30:
            return "about 1000-1800 characters"
        if words <= 12:
            return "about 1000-1200 characters"
        return "about 1000-1500 characters"
    floor = narration_depth_floor()
    if not own or words > 30:
        low, high = floor + 400, floor + 1200
    elif words <= 12:
        low, high = floor + 100, floor + 350
    else:
        low, high = floor + 300, floor + 800
    return f"about {low}-{high} characters"


def facts_to_keep(context: Any, limit: int = 6) -> list[str]:
    """The hour, who is dead (#154) and which nearby places are open, as sentences the prose must keep (playtest #59)."""
    if not isinstance(context, dict):
        return []
    facts: list[str] = []
    # Where the player is, first (Stell, 2026-10-24: "the story should be told where the player is,
    # fix the drift"). The player_is_in field in the place view was there and ignored: the combined
    # live replay's T4 'i search the dead ghoul' in the subway tunnel was written in "the clinic's
    # emergency lanterns" with the clinic's medic. A fact here is held like the hour.
    here = context.get("current_location") if isinstance(context.get("current_location"), dict) else {}
    here_name = str(here.get("name") or "").strip()
    if here_name:
        from app.prompts import _player_is_in

        where = _player_is_in(context, here_name, str(here.get("code") or "").strip())
        if where:
            facts.append(f"You are in {where}")
    clock = context.get("world_time")
    if isinstance(clock, dict) and clock.get("hour") is not None:
        try:
            hour = int(clock.get("hour") or 0)
            minute = int(clock.get("minute_of_hour") or 0)
        except (TypeError, ValueError):
            hour = minute = -1
        if hour >= 0:
            part = str(clock.get("part_of_day") or "").strip()
            if not part:
                from app.world import part_of_day

                part = part_of_day(hour)
            facts.append(f"It is {part}, {hour:02d}:{minute:02d}.")
    # Who the interpreter recorded dead and what destroyed (#154): facts like
    # the hour, so the scene is held to them; they do not crowd out the hours.
    try:
        from app.interpreter import facts as recorded_facts

        held = recorded_facts(context)
    except Exception:
        held = []
    facts.extend(held)
    limit += len(held)
    contract = context.get("movement_contract")
    town = contract.get("town") if isinstance(contract, dict) else None
    places = town.get("places_here") if isinstance(town, dict) else None
    for place in places or []:
        if len(facts) >= limit:
            break
        if not isinstance(place, dict) or "open" not in place:
            continue
        name = str(place.get("name") or "").strip() or f"the {str(place.get('kind') or 'place').strip()}"
        where = str(place.get("where") or "").strip()
        label = f"{name} ({where})" if where else name
        if place.get("open"):
            facts.append(f"{label[0].upper()}{label[1:]} is open.")
        else:
            hours = str(place.get("hours") or "").strip()
            facts.append(f"{label[0].upper()}{label[1:]} is closed" + (f"; its hours are {hours}." if hours else "."))
    return facts


def drop_fact_echo_opening(narration: str, facts: list[str]) -> tuple[str, list[str]]:
    """The prose without the opening sentences that copy a facts_to_keep entry word for word.

    A narrow repair of one shape (drift eval: 'You are in Radiation Fenced Sanctuary [[L1]]. It is
    morning, 08:12. ...' opened a narration): the packet's own fact read back as prose. Only the
    leading sentences, only an exact copy (with or without its [[code]]), and never the whole scene.
    Returns (text, dropped sentences).
    """
    from app.narration_pipeline import _sentence_key, split_sentences

    text = str(narration or "")

    def key(sentence: str) -> str:
        return _sentence_key(re.sub(r"\s*\[\[[^\]]*\]\]", "", str(sentence or "")))

    wanted = {key(f) for f in facts or [] if key(f)}
    if not wanted or not text.strip():
        return text, []
    first_para, sep, rest = text.lstrip().partition("\n\n")
    dropped: list[str] = []
    for sentence in split_sentences(first_para):
        if key(sentence) not in wanted:
            break
        dropped.append(sentence)
    if not dropped:
        return text, []
    head = first_para
    for sentence in dropped:
        head = head[head.find(sentence) + len(sentence):] if sentence in head else head
    remaining = (head.strip() + ("\n\n" + rest if sep else "")).strip()
    if not remaining:
        return text, []
    return remaining, dropped


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
            "player_line is the player's whole turn. Narrate only that action and how the world and its people respond; "
            "the player's further actions, words, thoughts, feelings and decisions are theirs to write, not yours."
        )
        # The player's words, as their own field (7B run 5, #123: the quote was
        # dropped, reworded or given to the clerk in a third of the speaking
        # turns while player_line held it). They are the player's own text.
        from app.narration_pipeline import player_quotes

        says = player_quotes(player_input)
        if says:
            packet["player_says"] = says
            instructions.append(
                "player_says is what the player (you) says aloud this turn. ===NAR=== has you say each line in "
                "quotation marks, word for word as written, then shows how the others answer. Nobody else says these "
                "words, and you say nothing beyond them."
            )
            # A question the scene never answered (7B run 10, T1-T3: "what does
            # it pay?" three times, met with "What do you have to offer?").
            asks = [line for line in says if "?" in line]
            if asks:
                packet["player_asks"] = asks
                instructions.append(
                    "player_asks holds the questions the player puts to someone this turn. The one asked answers "
                    "each in ===NAR=== plainly and concretely (a number, a name, a place, a yes or a no), or says "
                    "outright why they will not; they do not answer a question with the same question."
                )
        from app.prose_state import declared_act, player_trade_offer

        # Who does the act (playtest #77, T13: "fix a rusty sword" was done by
        # the smith). The phrase is the player's own words, not an example.
        act = declared_act(own)
        if act:
            packet["player_act"] = act["phrase"]
            instructions.append(
                "player_act is done by the player (you) in ===NAR===; others may help, watch or react, "
                "but nobody does it for them."
            )
        # The dice already decided how the act turns out (playtest #85a, T7:
        # "Not bad, not bad at all" with no roll behind it). The prose follows.
        outcome = act_outcome_of(context)
        if outcome:
            packet["act_outcome"] = outcome
            instructions.append(ACT_OUTCOME_RULE)
            if isinstance(outcome.get("quest"), dict):
                instructions.append(ACT_QUEST_RULE)
        # The player's own offer (playtest #75, T7: the last 3 gold offered for
        # directions was never paid). The engine takes the sum when it is accepted.
        offer = player_trade_offer(own)
        if offer:
            packet["trade_offer"] = {"gold": offer}
            instructions.append(
                f"trade_offer: the player offers {offer} gold. If the other side accepts, ===OPS=== has GOLD -{offer} "
                "and ===NAR=== shows the coin handed over; if they refuse, there is no GOLD line and ===NAR=== says so."
            )
    # How the player's last act turned out, so this scene does not redo or
    # undo it from memory (playtest #85a, T8: "swords already polished").
    # After the #75 offer, which belongs to every player line, not only to
    # turns after a rolled act (#85 review). The engine leaves it out when
    # this turn retries the same work (world.play_turn).
    previous = previous_act_of(context)
    if previous:
        packet["previous_act"] = previous
        instructions.append(PREVIOUS_ACT_RULE)
    packet["narration_length"] = narration_length_target(player_input)
    # The clock and the shops' hours, as plain sentences (playtest #59: open
    # shops written as shuttered and 'afternoon' at 08:35, with both in the
    # packet as fields the prose did not read as facts).
    facts = facts_to_keep(context)
    if facts:
        packet["facts_to_keep"] = facts
        instructions.append(
            "facts_to_keep are true at this moment. ===NAR=== may add anything else to the scene, "
            "but does not contradict them: the time of day is that time, an open place is open, a closed one is closed."
        )
        # Death is a 0/1 state told only when it is 1 (#154): Stell's one line, with a flag only.
        from app.interpreter import DEAD_RULE, shows_dead

        if shows_dead(facts):
            instructions.append(DEAD_RULE)
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
    town_turn = in_town(context)
    if not (isinstance(here_loc, dict) and here_loc.get("inside_venue")):
        if town_turn:
            instructions.append(
                "If ===NAR=== takes the player through a door, it is a building in world_state.town.places_here "
                "and ===OPS=== MUST contain MOVE with that name. No other building appears."
            )
        else:
            instructions.append(
                "If ===NAR=== takes the player through a door into a shop, inn, forge, temple or other building, "
                "===OPS=== MUST contain MOVE with that building's name."
            )
    space = context.get("map_space") if isinstance(context, dict) else None
    if town_turn:
        instructions.append(
            "In a town do not WALK. Where the walk ends is world_state.town.arrived (or town.walking when it is "
            "still on the way); the prose ends there."
        )
    elif isinstance(space, dict) and space.get("width") and space.get("height"):
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
            "open_offers were already offered; pays is what the job pays, and the giver says that sum "
            "when the player asks. waiting_for_answer: do not offer it again or "
            "write the player taking it. player_takes_it_now: the player's line takes it and the app has "
            "accepted it; write the giver's answer, and do not offer it again. "
            "turned_down: the player refused it; do not offer it again. "
            "not_raised_yet: work the giver has or a notice posted on its board; the player has not heard of it, "
            "so nobody treats it as already asked. "
            "The story may offer other work that fits this scene and quest_style, but not a pile of offers at once."
        )
    # The player asks what a job pays (7B run 30, T5): the answer is the job's sum.
    try:
        from app.prompts import asked_job_pay

        pay = asked_job_pay(context, player_input) if isinstance(context, dict) else None
    except Exception:
        pay = None
    if pay:
        instructions.append(
            "pay_asked: the player asks what that job pays. pay_asked.giver answers with the sum in pay_asked.pays, "
            "in their own words, not a vaguer phrase."
        )
    leads = context.get("open_leads") if isinstance(context, dict) else None
    if isinstance(leads, list) and leads:
        instructions.append(
            "open_leads were already offered. waiting_for_answer: the player has not gone with them; do not write the "
            "player going, and do not offer it again. player_going_now: the player's line goes with them; the walk "
            "is world_state.town. player_stayed: the player chose to stay; do not ask again."
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
