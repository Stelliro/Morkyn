"""Scene cast with placeholder slots: who a draft may name, how slots bind, what the verifier rejects.

Status: built, not wired (TODO n14).

The draft flow trusts free-text names and gets `travel-stained coat's rebels` and `L1's allies`: gear and
places used as people, while the npcs table stays empty. This module turns the cast into a fill-in map.
Before the draft, build_involved() lists the people, items and places this beat may use as slots
(NPC_1, ITEM_1, PLACE_1), reusing known codes and offering at most one new face. The draft writes
{NPC_1} in prose and in ops; bind() maps every slot to `Name [[CODE]]` (people), `Name [[L#]]` (places)
or object phrasing (`your coat [[I#]]`) and proposes the NPC_NEW rows for new faces with their drawn
names. verify() runs gates (unbound placeholder, slot bound to gear, item or place as agent, clothing
name, cast overflow, speaker outside the cast) and propose_repairs() answers with a deterministic refill
or cut, or flags that one prose re-ask is needed. Reports ride on turn["_dsl"]["scene_cast"], the one
turn carrier the handoff cleanup keeps. Nothing here touches the database, the prompts, or the DSL
opcode table, and the live game does not call this module.

Wiring (not done):
  app/llm.py:_try_dsl_draft() just before build_dsl_user_prompt(active_context, player_input) -> inv = scene_cast.build_involved(active_context, player_input, turn=...); active_context["involved"] = inv["involved"] (and app/turn_dsl.py:build_dsl_user_prompt() copies context["involved"] into the packet beside cast_options)
  app/turn_dsl.py:ops_to_turn() after the turn dict is built -> turn["_dsl"]["placeholders"] = scene_cast.find_placeholders(narration); scene_cast.slot_refs_in_ops(ops) for NPC_NEW / CAST / TALK lines that name a slot
  app/llm.py:_normalize_turn() just before _repair_entity_names_in_turn(result, context) -> b = scene_cast.bind(result, context.get("involved"), scene_cast.entity_map_from_context(context, result), seed=...); result = b["turn"]; scene_cast.attach_report(result, {"binding": b["binding"]})
  app/llm.py:_verification_policy() beside the unresolved_entity_references blocker -> v = scene_cast.verify(draft, involved, binding, entity_map); blockers += v["policy_blockers"]
  app/llm.py:generate_turn() at the _run_quest_parser seat (final prose) -> v2 = scene_cast.verify(...); r = scene_cast.propose_repairs(result, v2, binding, entity_map, seed=...); r["mode"] in ("refill", "cut") -> result = scene_cast.apply_repairs(result, r); r["needs_model_call"] -> one _retry_narration_prose-style call built by llm.py from r["reask_slots"] (that prompt text lives in llm.py)
  app/world.py:apply_turn() between the name repair and _collect_npcs_from_turn_result -> scene_cast.npc_rows_for_apply(result) gives the NPC_NEW-shaped rows for new slots so _npcs_shown_in_prose keeps them (a bound slot is shown by construction)
  app/world.py:apply_turn() at _apply_scene_cast(conn, result.get("scene_cast")) -> result["scene_cast"] = scene_cast.resolve_pending_cast(result, code_by_name) appends the codes _upsert_npc minted this turn to scene_cast.present / interacting
  app/llm.py:_clean_turn_for_handoff() -> nothing: reports live under _dsl, which is already preserved
  app/turn_dsl.py:DSL_SYSTEM_PROMPT and app/prompts.py:SYSTEM_PROMPT / VERIFY_PROMPT -> the placeholder rule and the slot legend (prompt text, written there, not here)

Turn on:
  [ ] playthrough_options.scene_cast_enabled (default off), read by llm.py at the three seats
  [ ] packet: context["involved"] (HANDOFF_BASE_CONTEXT_KEYS gains "involved"; build_dsl_user_prompt copies it)
  [ ] draft: placeholder rule in DSL_SYSTEM_PROMPT; NPC_NEW / CAST / TALK accept a slot token
  [ ] bind at _normalize_turn; gates at _verification_policy; final-prose gate + repairs at the quest-parser seat
  [ ] apply: npc_rows_for_apply before _collect_npcs_from_turn_result; resolve_pending_cast before _apply_scene_cast
  [ ] no schema, no settings row, no route, no UI; trace shows _dsl.scene_cast in the turn file

Tests: tests/test_scene_cast.py
"""
from __future__ import annotations

import copy
import re
from typing import Any

VERSION = 1

# ---------------------------------------------------------------------------
# Rules tables (data)
# ---------------------------------------------------------------------------

PLACEHOLDER_RE = re.compile(
    r"\{(NPC|ITEM|PLACE)_(\d{1,2})(?:\|(name|first|they|them|their|theirs|he|she|his|her|it|its))?\}"
)
# Near-miss forms normalised before parsing (fixes recorded):
# {npc_1} {Npc_1} {NPC1} {NPC-1} {{NPC_1}} [NPC_1] <NPC_1> {NPC 1}
LOOSE_PLACEHOLDER_RE = re.compile(
    r"[\{\[<]{1,2}\s*(npc|item|place)\s*[_\- ]?\s*(\d{1,2})\s*(?:\|\s*(\w+))?\s*[\}\]>]{1,2}", re.I
)
POSSESSIVE_RE = re.compile(r"(?:'s|’s)\b")  # right after a placeholder: {NPC_1}'s
PLACEHOLDER_FORMS = ("name", "first", "they", "them", "their", "theirs", "he", "she", "his", "her", "it", "its")
FAMILIES = ("NPC", "ITEM", "PLACE")

LIMITS = {"npcs": 4, "new_npcs": 1, "items": 4, "places": 3}
LIMITS_OPENING = {"npcs": 5, "new_npcs": 2, "items": 4, "places": 3}  # input_kind opening (turn 0) may introduce two faces
PRESENCE_RANK = {"full": 0, "event_worthy": 1, "background": 2, "nameless": 3}  # lower first when filling "here" slots

# Fill order for NPC slots (first match wins per person; people are added until LIMITS["npcs"]):
NPC_SOURCE_ORDER = ("addressed", "companion", "keeper", "interacting", "present", "here")
# A new-face slot is added (status "new") when any holds, and never more than LIMITS["new_npcs"]:
NEW_FACE_TRIGGERS = (
    "no_people_here",  # the place has no people and the input is conversation / trade / claim_check
    "input_names_stranger",  # the player's line has one of NEW_FACE_WORDS
    "opening_turn",  # turn == 0 (two slots)
    "turn_plan_asks",  # context.turn_plan.explicit_references.all has a role word not matching anyone here
)
NEW_FACE_WORDS = (
    "someone", "stranger", "a man", "a woman", "a figure", "guard", "guards", "clerk", "merchant", "keeper",
    "passerby", "beggar", "child", "rider", "watchman", "priest", "broker", "anyone",
)
# The NEW_FACE_WORDS that are jobs: the player's line "I ask the clerk" gives the new face that role.
NEW_FACE_ROLE_WORDS = ("guard", "clerk", "merchant", "keeper", "beggar", "rider", "watchman", "priest", "broker")
# Intents (turn_plan.primary_intent, the world._turn_intent words) for which an empty room still offers a face.
SOCIAL_INTENTS = ("conversation", "trade", "claim_check")

# Items: worn first, then carried, only those "in play" (named in the player's line, in turn_plan references, or the two
# most recently granted); places: current location first, then its parent, then places named in the input.
ITEM_IN_PLAY_MAX_RECENT = 2

# Rendering
RENDER = {
    "person_first": "{name} [[{code}]]", "person_later": "{name}",
    "person_new": "{name}",  # no code until upsert; the second name repair adds it
    "place_first": "{name} [[{code}]]", "place_later": "{name}",
    "item_first": "{article}{name} [[{code}]]", "item_later": "{article}{name}",  # article "your " for worn/carried, "the " for new
}
POSSESSIVE_FORM = "{render}'s"  # {NPC_1}'s -> "Mara [[A]]'s" on first mention, "Mara's" after
PRONOUNS = {
    "she": {"they": "she", "them": "her", "their": "her", "theirs": "hers"},
    "he": {"they": "he", "them": "him", "their": "his", "theirs": "his"},
    "they": {"they": "they", "them": "them", "their": "their", "theirs": "theirs"},
}
ITEM_PRONOUNS = {"they": "it", "them": "it", "their": "its", "theirs": "its", "it": "it", "its": "its"}
PLACE_PRONOUNS = ITEM_PRONOUNS
# Gendered forms a draft may write are read as the person's own pronoun set.
_FORM_TO_CASE = {"he": "they", "she": "they", "it": "they", "his": "their", "her": "their", "its": "their"}
_ARTICLE_WORDS = ("your", "the", "a", "an", "my", "his", "her", "their", "its", "this", "that")

# Name drawing for new faces: cast_options.names (unused names drawn for this turn) by index, else world.invent_person_name
# with name_seed("scene_cast", turn, location_code, slot, attempt). A drawn name is rejected and redrawn (up to NAME_ATTEMPTS)
# when it is in names_lower of the entity map, fails world.is_plausible_person_name, or matches GEAR_HEADS / world.is_generic_person_label.
NAME_ATTEMPTS = 6
ROLE_FOR_NEW_FACE_ORDER = ("input_role_word", "cast_options.jobs[i]", "local")  # the job word in the player's line wins, then the drawn job, then "local"

# Gates: (check, severity). Weight is always 0.0 here.
GATES = (
    ("placeholder_unbound", "block"),  # a {SLOT} remains in narration / turn_summary / scene_plan after bind
    ("npc_slot_not_person", "block"),  # an NPC slot bound to an item/place code, or to a name that is_generic_person_label / not is_plausible_person_name
    ("slot_name_is_clothing", "block"),  # a new-face name (bound or in npcs rows) matches GEAR_HEADS or SCENERY_WORDS
    ("item_as_agent", "block"),  # inventory name or [[I#]] heads a GROUP_NOUNS possessive or precedes AGENT_VERBS
    ("place_as_agent", "block"),  # place name or [[L#]] heads a GROUP_NOUNS possessive or precedes AGENT_VERBS
    ("cast_overflow", "block"),  # distinct new person names (npcs rows with code None, plus world._figure_hints in the prose) exceed limits["new_npcs"]
    ("unlisted_new_npc", "warn"),  # an npcs row with code None whose name the prose never shows and that is no slot
    ("speaker_outside_cast", "warn"),  # conversation.spoken_lines attributes a quote to a code not in involved.npcs
    ("must_speak_silent", "warn"),  # the addressed person (must_speak) has no quote and no agent sentence
    ("slot_reused_for_two", "block"),  # the same slot bound to two different names inside one turn (NPC_NEW name differs from prose fill)
)
GEAR_HEADS = (
    "coat", "cloak", "cloaks", "jacket", "jackets", "robe", "robes", "tunic", "tunics", "vest", "vests", "shirt", "shirts",
    "boot", "boots", "shoe", "shoes", "glove", "gloves", "hat", "hats", "hood", "hoods", "satchel", "satchels", "bag", "bags",
    "pack", "packs", "pouch", "pouches", "belt", "belts", "scabbard", "sheath", "sword", "swords", "dagger", "daggers",
    "blade", "blades", "bow", "bows", "crossbow", "armor", "armour", "helm", "helmet", "shield", "staff", "staves",
    "wand", "tankard", "mug", "scroll", "map", "knife", "lantern", "rope", "cup",
)
GROUP_NOUNS = (
    "allies", "rebels", "men", "women", "crew", "gang", "forces", "soldiers", "band", "faction", "enemies", "friends",
    "followers", "people", "side", "sides", "camp", "company", "party", "guards", "riders", "agents",
)
AGENT_VERBS = (
    "says", "said", "asks", "asked", "whispers", "shouts", "nods", "smirks", "grunts", "laughs", "watches", "glances",
    "stands", "leans", "steps", "turns", "replies", "answers", "mutters", "grins", "frowns", "waves", "beckons", "demands",
)
SCENERY_WORDS = (
    "window", "door", "street", "alley", "inn", "tavern", "market", "square", "wall", "gate", "bridge", "road", "river",
    "fire", "hearth",
)

# Repairs
MAX_SENTENCE_CUTS = 2  # more than this many cuts -> mode "rewrite"
MIN_PROSE_AFTER_CUT = 240  # characters; below it -> "rewrite" (turn_dsl.narration_depth_floor is the live floor, read when wired)
ONE_REPAIR_CALL = 1  # the ceiling the llm.py seat enforces; the module only flags needs_model_call
REPAIR_ORDER = ("refill_unbound", "fix_agent_heads", "rename_clothing_slot", "cut_unfixable", "rewrite")
AGENT_HEAD_REWRITE = {"group": "the {group}", "voice": "its voice", "hand": "its strap", "eyes": "its clasp"}  # item possessive repairs

# ---------------------------------------------------------------------------
# Compiled helpers over the tables
# ---------------------------------------------------------------------------

_GEAR_ALT = "|".join(re.escape(w) for w in GEAR_HEADS)
_GROUP_ALT = "|".join(re.escape(w) for w in GROUP_NOUNS)
_VERB_ALT = "|".join(re.escape(w) for w in AGENT_VERBS)
_POSS = r"(?:'s|’s)"
_GEAR_GROUP_RE = re.compile(
    rf"\b(?:the\s+|a\s+|an\s+)?(?:[\w\-]+[\s\-]+){{0,3}}(?:{_GEAR_ALT}){_POSS}\s+({_GROUP_ALT})\b", re.I
)
_ITEM_CODE_AGENT_RE = re.compile(
    rf"\[\[I\d+\]\](?:{_POSS}\s+(?:{_GROUP_ALT}|voice|hand|eyes?|gaze)|\s+(?:{_VERB_ALT}))\b", re.I
)
_PLACE_CODE_AGENT_RE = re.compile(
    rf"(?:\[\[L\d+\]\]|\bL\d+)(?:{_POSS}\s+(?:{_GROUP_ALT})|\s+(?:{_VERB_ALT}))\b", re.I
)
_GEAR_WORD_RE = re.compile(rf"\b(?:{_GEAR_ALT})\b", re.I)
_SCENERY_WORD_RE = re.compile(r"\b(?:" + "|".join(re.escape(w) for w in SCENERY_WORDS) + r")\b", re.I)
_SENTENCE_SPLIT_RE = re.compile(r"(?:(?<=[.!?…])|(?<=[.!?…][\"'”’)\]]))\s+")
_CODE_TAG_RE = re.compile(r"\s*\[\[[A-Za-z]{1,3}\d{0,4}\]\]")
_SLOT_TOKEN_RE = re.compile(r"^(?:\{\{?|\[\[?|<)?\s*(NPC|ITEM|PLACE)[_\- ]?(\d{1,2})(?:\|(\w+))?\s*(?:\}\}?|\]\]?|>)?$", re.I)
_WORD_RE = re.compile(r"[a-z0-9][a-z0-9'’-]*")
_PLACE_IN_INPUT_RE = re.compile(
    r"\b(?:to|at|in|into|toward|towards|near|inside|through|past)\s+(?:the\s+)?"
    r"((?:[A-Z][\w'’-]+)(?:\s+(?:of|the|[A-Z][\w'’-]+)){0,3})"
)
_TEXT_LIMIT = 240


def _s(value: Any) -> str:
    return str(value or "").strip()


def _lower_words(text: str) -> set[str]:
    return set(_WORD_RE.findall(str(text or "").lower()))


def _evidence(check: str, ok: bool, evidence: str, severity: str) -> dict[str, Any]:
    return {"check": check, "ok": bool(ok), "evidence": _s(evidence)[:_TEXT_LIMIT], "severity": severity, "weight": 0.0}


def _sentences(text: str) -> list[str]:
    """The sentences of a text as exact substrings, so a cut can remove one by replacement."""
    return [part for part in _SENTENCE_SPLIT_RE.split(str(text or "")) if part.strip()]


def _sentence_holding(text: str, pos: int) -> str:
    running = 0
    for sentence in _sentences(text):
        start = str(text).find(sentence, running)
        if start < 0:
            continue
        end = start + len(sentence)
        if start <= pos < end:
            return sentence
        running = end
    return ""


def _entity_ref(code: Any, name: Any, kind: str, role: Any = "") -> dict[str, Any]:
    return {"code": _s(code).upper(), "name": _s(name), "kind": kind, "role": _s(role) if kind == "person" else ""}


# ---------------------------------------------------------------------------
# Schema (none)
# ---------------------------------------------------------------------------


def ensure_schema(conn) -> None:
    """No table and no settings row: a documented no-op so one wiring loop can call every module."""
    return None


# ---------------------------------------------------------------------------
# Entity map
# ---------------------------------------------------------------------------


def _pronoun_word(value: Any) -> str:
    word = _s(value).lower()
    if word.startswith("she"):
        return "she"
    if word.startswith("he"):
        return "he"
    return "they"


def _location_keys(location: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    if location.get("id") is not None and _s(location.get("id")):
        keys.add("id:" + _s(location.get("id")))
    if _s(location.get("code")):
        keys.add("code:" + _s(location.get("code")).upper())
    return keys


def _people_rows_from_context(context: dict[str, Any], draft: dict[str, Any] | None) -> list[dict[str, Any]]:
    current = context.get("current_location") if isinstance(context.get("current_location"), dict) else {}
    here_keys = _location_keys(current)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(npc: Any, here: bool) -> None:
        if not isinstance(npc, dict):
            return
        code = _s(npc.get("code")).upper()
        name = _s(npc.get("name"))
        if not name:
            return
        key = code or ("name:" + name.lower())
        if key in seen:
            return
        seen.add(key)
        rows.append(
            {
                "code": code,
                "name": name,
                "role": _s(npc.get("role")),
                "here": bool(here),
                "presence": _s(npc.get("presence")) or "full",
                "pronouns": _pronoun_word(npc.get("pronouns")),
            }
        )

    for npc in current.get("npcs") or []:
        add(npc, True)
    for location in context.get("locations") or []:
        if not isinstance(location, dict):
            continue
        here = bool(here_keys & _location_keys(location))
        for npc in location.get("npcs") or []:
            add(npc, here)
    for npc in context.get("npcs") or []:
        if isinstance(npc, dict):
            here = ("id:" + _s(npc.get("location_id"))) in here_keys if _s(npc.get("location_id")) else False
            add(npc, here)
    for npc in (draft or {}).get("npcs") or []:
        add(npc, True)
    return rows


def _place_rows_from_context(context: dict[str, Any], draft: dict[str, Any] | None) -> list[dict[str, Any]]:
    current = context.get("current_location") if isinstance(context.get("current_location"), dict) else {}
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(place: Any, here: bool) -> None:
        if not isinstance(place, dict):
            return
        code = _s(place.get("code")).upper()
        name = _s(place.get("name"))
        if not name:
            return
        key = code or ("name:" + name.lower())
        if key in seen:
            return
        seen.add(key)
        rows.append({"code": code, "name": name, "here": bool(here)})

    add(current, True)
    for place in context.get("locations") or []:
        add(place, isinstance(place, dict) and bool(_location_keys(current) & _location_keys(place)))
    for place in (draft or {}).get("locations") or []:
        add(place, False)
    return rows


def _item_rows_from_context(context: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in context.get("inventory") if isinstance(context.get("inventory"), list) else []:
        if not isinstance(item, dict) or not _s(item.get("name")):
            continue
        rows.append(
            {
                "id": item.get("id"),
                "code": _s(item.get("code")).upper(),
                "name": _s(item.get("name")),
                "worn": bool(_s(item.get("equipped_slot"))),
            }
        )
    return rows


def _event_rows_from_context(context: dict[str, Any], draft: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in list(context.get("events") or []) + list((draft or {}).get("events") or []):
        if isinstance(event, dict) and _s(event.get("title") or event.get("name")):
            rows.append({"code": _s(event.get("code")).upper(), "name": _s(event.get("title") or event.get("name"))})
    return rows


def entity_map_from_rows(
    people: list[dict[str, Any]],
    places: list[dict[str, Any]],
    items: list[dict[str, Any]],
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """The entity map from rows (npcs / locations / inventory / events table rows, or the context's).

    Each row needs `name`; `code` may be empty for a thing with no code yet. People rows may carry
    `role`, `presence`, `pronouns` and `here` (default True: rows handed in at the apply seat are the
    live cast at the player's location); place rows `here` (default False); item rows `worn` or
    `equipped_slot`.
    """
    out: dict[str, Any] = {"people": [], "places": [], "items": [], "events": [], "by_code": {}, "names_lower": {}}

    def register(ref: dict[str, Any]) -> None:
        if ref["code"] and ref["code"] not in out["by_code"]:
            out["by_code"][ref["code"]] = ref
        key = ref["name"].lower()
        if key and key not in out["names_lower"]:
            out["names_lower"][key] = ref

    seen: set[str] = set()
    for row in people or []:
        if not isinstance(row, dict) or not _s(row.get("name")):
            continue
        ref = _entity_ref(row.get("code"), row.get("name"), "person", row.get("role"))
        key = ref["code"] or ("name:" + ref["name"].lower())
        if key in seen:
            continue
        seen.add(key)
        ref["here"] = bool(row.get("here", True))
        ref["presence"] = _s(row.get("presence")) or "full"
        ref["pronouns"] = _pronoun_word(row.get("pronouns"))
        out["people"].append(ref)
        register(ref)
    for row in places or []:
        if not isinstance(row, dict) or not _s(row.get("name")):
            continue
        ref = _entity_ref(row.get("code"), row.get("name"), "place")
        key = ref["code"] or ("name:" + ref["name"].lower())
        if key in seen:
            continue
        seen.add(key)
        ref["here"] = bool(row.get("here", False))
        out["places"].append(ref)
        register(ref)
    for row in items or []:
        if not isinstance(row, dict) or not _s(row.get("name")):
            continue
        ref = _entity_ref(row.get("code"), row.get("name"), "item")
        key = ref["code"] or ("name:" + ref["name"].lower())
        if key in seen:
            continue
        seen.add(key)
        ref["worn"] = bool(row.get("worn")) or bool(_s(row.get("equipped_slot")))
        if row.get("id") is not None:
            ref["id"] = row.get("id")
        out["items"].append(ref)
        register(ref)
    for row in events or []:
        if not isinstance(row, dict) or not _s(row.get("name") or row.get("title")):
            continue
        ref = _entity_ref(row.get("code"), row.get("name") or row.get("title"), "event")
        key = ref["code"] or ("name:" + ref["name"].lower())
        if key in seen:
            continue
        seen.add(key)
        out["events"].append(ref)
        register(ref)
    return out


def entity_map_from_context(context: dict[str, Any], draft: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the entity map from the handed-off context (and the draft's own creates).

    narration_pipeline.entity_roster gives the code -> name -> kind rows the beat writer already trusts;
    the context rows add the flags it drops (here, presence, pronouns, worn) and the items it holds back
    when nothing names them. Kind words are normalised: "person"; "place (where the player is)" and
    "place"; "worn by the player (you)" / "carried by the player (you)"; "event".
    """
    context = context if isinstance(context, dict) else {}
    draft = draft if isinstance(draft, dict) else None
    people = _people_rows_from_context(context, draft)
    places = _place_rows_from_context(context, draft)
    items = _item_rows_from_context(context)
    events = _event_rows_from_context(context, draft)
    try:
        from app.narration_pipeline import entity_roster

        roster_rows = entity_roster(context, draft)
    except Exception:
        roster_rows = []
    known = {(_s(r.get("code")).upper()) for r in people + places + items + events if _s(r.get("code"))}
    for row in roster_rows:
        code = _s(row.get("code")).upper()
        if not code or code in known:
            continue
        kind = _s(row.get("kind")).lower()
        if kind == "person":
            people.append({"code": code, "name": row.get("name"), "role": row.get("role"), "here": True, "presence": "full", "pronouns": "they"})
        elif kind.startswith("place"):
            places.append({"code": code, "name": row.get("name"), "here": "where the player is" in kind})
        elif kind.startswith("worn") or kind.startswith("carried"):
            items.append({"code": code, "name": row.get("name"), "worn": kind.startswith("worn")})
        elif kind == "event":
            events.append({"code": code, "name": row.get("name")})
        known.add(code)
    return entity_map_from_rows(people, places, items, events)


# ---------------------------------------------------------------------------
# Involved
# ---------------------------------------------------------------------------


def _player_line(player_input: str) -> str:
    text = str(player_input or "")
    if not text.strip() or text.startswith("__"):
        return ""
    return re.split(r"\n\s*\n", text, maxsplit=1)[0].strip()


def _primary_intent(context: dict[str, Any], player_input: str) -> str:
    plan = context.get("turn_plan") if isinstance(context.get("turn_plan"), dict) else {}
    intent = _s(plan.get("primary_intent"))
    if intent:
        return intent
    try:
        from app.world import _turn_intent

        return _s(_turn_intent(str(player_input or ""))[0])
    except Exception:
        return ""


def _explicit_refs(context: dict[str, Any]) -> list[str]:
    plan = context.get("turn_plan") if isinstance(context.get("turn_plan"), dict) else {}
    refs = plan.get("explicit_references") if isinstance(plan.get("explicit_references"), dict) else {}
    return [_s(r) for r in (refs.get("all") or []) if _s(r)]


def _name_is_usable(name: str, entity_map: dict[str, Any]) -> bool:
    """A drawn new-face name the draft may use: plausible, no gear or scenery word, not a label, unused."""
    n = _s(name)
    if not n or n.lower() in entity_map.get("names_lower", {}):
        return False
    if _GEAR_WORD_RE.search(n) or _SCENERY_WORD_RE.search(n):
        return False
    try:
        from app.world import is_generic_person_label, is_plausible_person_name

        if is_generic_person_label(n) or not is_plausible_person_name(n):
            return False
    except Exception:
        if len(n) < 2 or len(n) > 48:
            return False
    return True


def _draw_new_name(entity_map: dict[str, Any], pool: list[str], taken: set[str], *, turn: int, location_code: str, slot: str) -> str:
    """cast_options.names in order, then invent_person_name with a stable seed; rejected names are skipped."""
    for candidate in pool:
        c = _s(candidate)
        if c and c.lower() not in taken and _name_is_usable(c, entity_map):
            taken.add(c.lower())
            return c
    try:
        from app.world import invent_person_name, name_seed
    except Exception:
        return ""
    last = ""
    for attempt in range(NAME_ATTEMPTS):
        candidate = _s(invent_person_name(seed=name_seed("scene_cast", turn, location_code, slot, attempt)))
        last = candidate
        if candidate and candidate.lower() not in taken and _name_is_usable(candidate, entity_map):
            taken.add(candidate.lower())
            return candidate
    taken.add(last.lower())
    return last


def _input_role_word(line: str) -> str:
    words = _lower_words(line)
    for word in NEW_FACE_ROLE_WORDS:
        if word in words:
            return word
    return ""


def _input_names_stranger(line: str) -> bool:
    low = " " + re.sub(r"\s+", " ", str(line or "").lower()) + " "
    for phrase in NEW_FACE_WORDS:
        if re.search(r"(?<![\w])" + re.escape(phrase) + r"(?![\w])", low):
            return True
    return False


def _turn_plan_asks(context: dict[str, Any], people_here: list[dict[str, Any]], entity_map: dict[str, Any]) -> str:
    """A role word in the plan's references that fits nobody here ("the clerk" with no clerk)."""
    roles_here = " ".join(_s(p.get("role")).lower() for p in people_here)
    names_here = {p["name"].lower() for p in people_here}
    for ref in _explicit_refs(context):
        low = ref.lower()
        if low in entity_map.get("names_lower", {}) or low.upper() in entity_map.get("by_code", {}):
            continue
        words = _lower_words(low)
        if not words or words & names_here:
            continue
        hit = [w for w in words if w in NEW_FACE_ROLE_WORDS]
        if hit and not any(w in roles_here for w in hit):
            return ref
    return ""


def _new_face_triggers(
    context: dict[str, Any],
    player_input: str,
    *,
    turn: int,
    input_kind: str,
    people_here: list[dict[str, Any]],
    entity_map: dict[str, Any],
) -> list[tuple[str, str]]:
    line = _player_line(player_input)
    fired: list[tuple[str, str]] = []
    if turn == 0 or input_kind == "opening":
        fired.append(("opening_turn", "turn 0"))
    if not people_here:
        intent = _primary_intent(context, player_input)
        speech = bool((context.get("conversation_turn") or {}).get("speech")) if isinstance(context.get("conversation_turn"), dict) else False
        if intent in SOCIAL_INTENTS or speech:
            fired.append(("no_people_here", intent or "speech"))
    if line and _input_names_stranger(line):
        fired.append(("input_names_stranger", "input names a stranger"))
    asks = _turn_plan_asks(context, people_here, entity_map)
    if asks:
        fired.append(("turn_plan_asks", asks))
    return fired


def _keeper_codes(context: dict[str, Any]) -> list[str]:
    codes: list[str] = []
    current = context.get("current_location") if isinstance(context.get("current_location"), dict) else {}
    keeper = current.get("keeper") if isinstance(current.get("keeper"), dict) else {}
    if _s(keeper.get("code")):
        codes.append(_s(keeper.get("code")).upper())
    try:
        from app.conversation import roster

        for row in roster(context):
            if row.get("keeper") and _s(row.get("code")).upper() not in codes:
                codes.append(_s(row.get("code")).upper())
    except Exception:
        pass
    return codes


def _active_scene_codes(context: dict[str, Any], bucket: str) -> list[str]:
    settings = context.get("settings") if isinstance(context.get("settings"), dict) else {}
    scene = settings.get("active_scene") if isinstance(settings.get("active_scene"), dict) else {}
    return [_s(c).upper() for c in scene.get(bucket) or [] if _s(c)]


def _source_candidates(context: dict[str, Any], entity_map: dict[str, Any], people_here: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """(source, code) in NPC_SOURCE_ORDER; a code appears once, at its first source."""
    by_code = entity_map.get("by_code", {})
    here_codes = [p["code"] for p in people_here if p["code"]]
    ordered: list[tuple[str, str]] = []
    seen: set[str] = set()

    def take(source: str, codes: list[str]) -> None:
        for code in codes:
            c = _s(code).upper()
            ref = by_code.get(c)
            if not c or c in seen or ref is None or ref.get("kind") != "person":
                continue
            seen.add(c)
            ordered.append((source, c))

    conv = context.get("conversation_turn") if isinstance(context.get("conversation_turn"), dict) else {}
    take("addressed", [c for c in conv.get("addressed") or []])
    thread = context.get("scene_thread") if isinstance(context.get("scene_thread"), dict) else {}
    companions: list[str] = []
    for row in thread.get("with") or []:
        if isinstance(row, dict):
            code = _s(row.get("code")).upper()
            if not code and _s(row.get("name")):
                ref = entity_map.get("names_lower", {}).get(_s(row.get("name")).lower())
                code = ref["code"] if ref else ""
            companions.append(code)
        else:
            companions.append(_s(row).upper())
    take("companion", companions)
    take("keeper", _keeper_codes(context))
    take("interacting", [c for c in _active_scene_codes(context, "interacting") if c in here_codes])
    take("present", [c for c in _active_scene_codes(context, "present") if c in here_codes])
    rest = sorted(
        (p for p in people_here if p["code"] and p["code"] not in seen),
        key=lambda p: (PRESENCE_RANK.get(_s(p.get("presence")).lower(), 9), p["name"].lower()),
    )
    take("here", [p["code"] for p in rest])
    return ordered


def _items_in_play(context: dict[str, Any], entity_map: dict[str, Any], player_input: str) -> list[dict[str, Any]]:
    words = _lower_words(_player_line(player_input)) | _lower_words(" ".join(_explicit_refs(context)))
    codes = {r.upper() for r in _explicit_refs(context)}
    items = list(entity_map.get("items") or [])
    with_ids = [i for i in items if isinstance(i.get("id"), int)]
    recent = {i["code"] or i["name"].lower() for i in sorted(with_ids, key=lambda i: int(i["id"]), reverse=True)[:ITEM_IN_PLAY_MAX_RECENT]}
    if not with_ids:
        recent = {i["code"] or i["name"].lower() for i in items[-ITEM_IN_PLAY_MAX_RECENT:]} if items else set()
    chosen: list[dict[str, Any]] = []
    for item in items:
        head = _lower_words(item["name"])
        if (item["code"] and item["code"] in codes) or (head and head & words) or ((item["code"] or item["name"].lower()) in recent):
            chosen.append(item)
    chosen.sort(key=lambda i: (0 if i.get("worn") else 1))
    return chosen


def _unknown_place_in_input(line: str, entity_map: dict[str, Any]) -> str:
    names = entity_map.get("names_lower", {})
    for match in _PLACE_IN_INPUT_RE.finditer(str(line or "")):
        phrase = _s(match.group(1))
        if not phrase or phrase.lower() in names:
            continue
        if any(phrase.lower() in n or n in phrase.lower() for n in names):
            continue
        if phrase.lower() in {"i", "you", "we"}:
            continue
        return phrase
    return ""


def build_involved(
    context: dict[str, Any],
    player_input: str,
    *,
    turn: int = 0,
    input_kind: str = "player",
    entity_map: dict[str, Any] | None = None,
    limits: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The slots this beat may use, from the packet: {"involved": Involved, "notes": [str]}.

    People follow NPC_SOURCE_ORDER up to the people limit minus the new-face slots NEW_FACE_TRIGGERS
    reserve first; new faces get a drawn name (cast_options.names, then invent_person_name by a stable
    seed) and a role per ROLE_FOR_NEW_FACE_ORDER; items worn first then carried, only those in play;
    places the current location, its parent, then places the input names. Pure.
    """
    context = context if isinstance(context, dict) else {}
    em = entity_map if isinstance(entity_map, dict) else entity_map_from_context(context)
    opening = input_kind == "opening" or int(turn or 0) == 0
    lim = dict(LIMITS_OPENING if opening else LIMITS)
    if isinstance(limits, dict):
        lim.update({k: int(v) for k, v in limits.items() if k in lim})
    current = context.get("current_location") if isinstance(context.get("current_location"), dict) else {}
    location_code = _s(current.get("code")).upper()
    notes: list[str] = []
    people_here = [p for p in em.get("people", []) if p.get("here") and p.get("code")]
    line = _player_line(player_input)

    triggers = _new_face_triggers(context, player_input, turn=int(turn or 0), input_kind=input_kind, people_here=people_here, entity_map=em)
    new_count = 0
    if triggers:
        new_count = lim["new_npcs"] if any(t == "opening_turn" for t, _r in triggers) else 1
        new_count = min(new_count, lim["new_npcs"])
    people_cap = max(0, lim["npcs"] - new_count)

    npcs: list[dict[str, Any]] = []
    by_code = em.get("by_code", {})
    addressed = {_s(c).upper() for c in ((context.get("conversation_turn") or {}).get("addressed") or [])} if isinstance(context.get("conversation_turn"), dict) else set()
    for source, code in _source_candidates(context, em, people_here):
        if len(npcs) >= people_cap:
            ref = by_code[code]
            notes.append(f"left out: {ref['name']} ({source}; people limit {people_cap})")
            continue
        ref = by_code[code]
        slot = f"NPC_{len(npcs) + 1}"
        npcs.append(
            {
                "slot": slot,
                "code": code,
                "name": ref["name"],
                "role_hint": _s(ref.get("role")),
                "status": "known",
                "source": source,
                "must_speak": code in addressed,
                "pronouns": _s(ref.get("pronouns")) or "they",
            }
        )
        notes.append(f"{slot}: {source}")

    cast_options = context.get("cast_options") if isinstance(context.get("cast_options"), dict) else {}
    pool = [_s(n) for n in (cast_options.get("names") or []) if _s(n)]
    jobs = [_s(j) for j in (cast_options.get("jobs") or []) if _s(j)]
    taken: set[str] = set()
    role_word = _input_role_word(line)
    for i in range(new_count):
        slot = f"NPC_{len(npcs) + 1}"
        name = _draw_new_name(em, pool, taken, turn=int(turn or 0), location_code=location_code, slot=slot)
        role = role_word if (i == 0 and role_word) else (jobs[i] if i < len(jobs) else "local")
        npcs.append(
            {
                "slot": slot,
                "code": None,
                "name": name or None,
                "role_hint": role,
                "status": "new",
                "source": "new_face",
                "must_speak": False,
                "pronouns": "they",
            }
        )
        reason = triggers[min(i, len(triggers) - 1)][0].replace("_", " ") if triggers else "new face"
        notes.append(f"{slot}: new face ({reason})")

    items: list[dict[str, Any]] = []
    for item in _items_in_play(context, em, player_input)[: lim["items"]]:
        items.append({"slot": f"ITEM_{len(items) + 1}", "ref": item["code"] or None, "name": item["name"], "kind": "worn" if item.get("worn") else "carried"})

    places: list[dict[str, Any]] = []
    place_codes: set[str] = set()

    def add_place(ref: dict[str, Any] | None, kind: str, name: str = "") -> None:
        if len(places) >= lim["places"]:
            return
        if ref is not None:
            key = ref["code"] or ref["name"].lower()
            if key in place_codes:
                return
            place_codes.add(key)
            places.append({"slot": f"PLACE_{len(places) + 1}", "code": ref["code"] or None, "name": ref["name"], "kind": kind})
        elif name:
            places.append({"slot": f"PLACE_{len(places) + 1}", "code": None, "name": name, "kind": kind})

    here_place = next((p for p in em.get("places", []) if p.get("here")), None)
    if here_place is None and location_code and location_code in by_code:
        here_place = by_code[location_code]
    if here_place is not None:
        add_place(here_place, "here")
    parent_code = _s(current.get("parent_code")).upper()
    parent = by_code.get(parent_code) if parent_code else None
    if parent is None and _s(current.get("exit_to")):
        parent = em.get("names_lower", {}).get(_s(current.get("exit_to")).lower())
    if parent is not None and parent.get("kind") == "place":
        add_place(parent, "nearby")
    low_line = line.lower()
    for place in em.get("places", []):
        if place.get("name") and place["name"].lower() in low_line:
            add_place(place, "nearby")
    unknown = _unknown_place_in_input(line, em) if line else ""
    if unknown and not any(p["name"].lower() == unknown.lower() for p in places):
        add_place(None, "new", unknown)
        notes.append(f"PLACE_{len(places)}: new place named in the input")

    involved = {
        "version": VERSION,
        "turn": int(turn or 0),
        "location_code": location_code,
        "npcs": npcs,
        "items": items,
        "places": places,
        "limits": {"npcs": lim["npcs"], "new_npcs": lim["new_npcs"], "items": lim["items"], "places": lim["places"]},
        "legend": [],
    }
    involved["legend"] = involved_legend(involved)
    normalized = normalize_involved(involved)
    return {"involved": normalized if normalized is not None else involved, "notes": notes}


def involved_legend(involved: dict[str, Any]) -> list[str]:
    """Machine legend lines, one per slot: "NPC_1=A:Mara (innkeeper)", "NPC_2=new:Tamsin (broker)",
    "ITEM_1=I3:travel-stained coat", "PLACE_1=L1:Second Shadow Inn". Data, not prose."""
    lines: list[str] = []
    for entry in (involved or {}).get("npcs") or []:
        code = _s(entry.get("code")) or "new"
        role = _s(entry.get("role_hint"))
        lines.append(f"{entry['slot']}={code}:{_s(entry.get('name'))}" + (f" ({role})" if role else ""))
    for entry in (involved or {}).get("items") or []:
        lines.append(f"{entry['slot']}={_s(entry.get('ref')) or 'new'}:{_s(entry.get('name'))}")
    for entry in (involved or {}).get("places") or []:
        lines.append(f"{entry['slot']}={_s(entry.get('code')) or 'new'}:{_s(entry.get('name'))}")
    return lines


def normalize_involved(raw: Any) -> dict[str, Any] | None:
    """Pure validation of an Involved that came back through the packet or a patch; None when unusable."""
    if not isinstance(raw, dict) or not isinstance(raw.get("npcs"), list):
        return None
    try:
        out: dict[str, Any] = {
            "version": VERSION,
            "turn": int(raw.get("turn") or 0),
            "location_code": _s(raw.get("location_code")).upper(),
            "npcs": [],
            "items": [],
            "places": [],
            "limits": {},
            "legend": [],
        }
        for i, entry in enumerate(raw.get("npcs") or []):
            if not isinstance(entry, dict):
                return None
            slot = f"NPC_{i + 1}"
            if _s(entry.get("slot")).upper() != slot:
                return None
            code = _s(entry.get("code")).upper() or None
            status = "known" if code else "new"
            if _s(entry.get("status")) and _s(entry.get("status")) not in ("known", "new"):
                return None
            pron = _s(entry.get("pronouns")).lower()
            out["npcs"].append(
                {
                    "slot": slot,
                    "code": code,
                    "name": _s(entry.get("name")) or None,
                    "role_hint": _s(entry.get("role_hint")),
                    "status": status,
                    "source": _s(entry.get("source")) or ("new_face" if status == "new" else "here"),
                    "must_speak": bool(entry.get("must_speak")),
                    "pronouns": pron if pron in PRONOUNS else "they",
                }
            )
        for i, entry in enumerate(raw.get("items") or []):
            if not isinstance(entry, dict) or _s(entry.get("slot")).upper() != f"ITEM_{i + 1}" or not _s(entry.get("name")):
                return None
            kind = _s(entry.get("kind"))
            out["items"].append({"slot": f"ITEM_{i + 1}", "ref": _s(entry.get("ref")).upper() or None, "name": _s(entry.get("name")), "kind": kind if kind in ("worn", "carried", "new") else "carried"})
        for i, entry in enumerate(raw.get("places") or []):
            if not isinstance(entry, dict) or _s(entry.get("slot")).upper() != f"PLACE_{i + 1}" or not _s(entry.get("name")):
                return None
            kind = _s(entry.get("kind"))
            out["places"].append({"slot": f"PLACE_{i + 1}", "code": _s(entry.get("code")).upper() or None, "name": _s(entry.get("name")), "kind": kind if kind in ("here", "nearby", "new") else "nearby"})
        limits = raw.get("limits") if isinstance(raw.get("limits"), dict) else {}
        out["limits"] = {k: int(limits.get(k, LIMITS[k])) for k in ("npcs", "new_npcs", "items", "places")}
        out["legend"] = involved_legend(out)
    except (TypeError, ValueError):
        return None
    return out


# ---------------------------------------------------------------------------
# Placeholders
# ---------------------------------------------------------------------------


def _canonical(family: str, index: Any, form: str = "") -> str:
    fam = _s(family).upper()
    try:
        n = int(index)
    except (TypeError, ValueError):
        n = 0
    f = _s(form).lower()
    return f"{{{fam}_{n}|{f}}}" if f in PLACEHOLDER_FORMS else f"{{{fam}_{n}}}"


def normalize_placeholder_text(text: str) -> tuple[str, list[str]]:
    """Near-miss placeholder forms to the canonical one; returns (text, fixes)."""
    fixes: list[str] = []
    source = str(text or "")

    def fix(match: re.Match[str]) -> str:
        canonical = _canonical(match.group(1), match.group(2), match.group(3) or "")
        if match.group(0) != canonical:
            fixes.append(f"{match.group(0)} -> {canonical}")
        return canonical

    return LOOSE_PLACEHOLDER_RE.sub(fix, source), fixes


def find_placeholders(text: str, *, where: str = "narration") -> list[dict[str, Any]]:
    """Every canonical placeholder in a text, with its span, form and whether a possessive follows."""
    out: list[dict[str, Any]] = []
    source = str(text or "")
    for match in PLACEHOLDER_RE.finditer(source):
        family = match.group(1).upper()
        index = int(match.group(2))
        form = _s(match.group(3)).lower()
        out.append(
            {
                "raw": match.group(0),
                "family": family,
                "index": index,
                "slot": f"{family}_{index}",
                "form": form,
                "start": match.start(),
                "end": match.end(),
                "possessive": bool(POSSESSIVE_RE.match(source, match.end())),
                "where": where,
            }
        )
    return out


def _scene_plan_strings(plan: Any) -> list[tuple[list[Any], Any, str]]:
    """(container, key, text) for every string a scene_plan carries, so each can be rewritten in place."""
    found: list[tuple[Any, Any, str]] = []
    if not isinstance(plan, dict):
        return found
    if isinstance(plan.get("goal"), str):
        found.append((plan, "goal", plan["goal"]))
    for point in plan.get("focus_points") or []:
        if isinstance(point, dict):
            for key in ("summary", "label", "text"):
                if isinstance(point.get(key), str):
                    found.append((point, key, point[key]))
        elif isinstance(point, str):
            found.append((plan["focus_points"], plan["focus_points"].index(point), point))
    return found


def _turn_texts(turn: dict[str, Any]) -> list[tuple[str, str]]:
    """(where, text) in the order bind reads them."""
    out: list[tuple[str, str]] = []
    segments = turn.get("narration_segments") if isinstance(turn.get("narration_segments"), list) else []
    seg_texts = [str(seg.get("text") or "") for seg in segments if isinstance(seg, dict)]
    if any(t.strip() for t in seg_texts):
        for t in seg_texts:
            out.append(("narration", t))
    else:
        out.append(("narration", str(turn.get("narration") or "")))
    out.append(("turn_summary", str(turn.get("turn_summary") or "")))
    for _container, _key, text in _scene_plan_strings(turn.get("scene_plan")):
        out.append(("scene_plan", text))
    return out


def placeholders_in_turn(turn: dict[str, Any]) -> list[dict[str, Any]]:
    """Placeholders in narration (segment by segment), turn_summary, scene_plan strings and the ops echo (_dsl.draft_narration)."""
    turn = turn if isinstance(turn, dict) else {}
    found: list[dict[str, Any]] = []
    for where, text in _turn_texts(turn):
        found.extend(find_placeholders(text, where=where))
    dsl = turn.get("_dsl") if isinstance(turn.get("_dsl"), dict) else {}
    if isinstance(dsl.get("draft_narration"), str):
        found.extend(find_placeholders(dsl["draft_narration"], where="ops"))
    return found


def slot_of(value: Any) -> str:
    """The canonical slot ("NPC_1") a token names: "NPC_1", "{NPC_1}", "[[NPC_1]]", "{npc_1|their}"; "" otherwise."""
    match = _SLOT_TOKEN_RE.match(_s(value).strip("\"'“”"))
    if not match:
        return ""
    return f"{match.group(1).upper()}_{int(match.group(2))}"


def is_slot_token(value: Any) -> bool:
    """True for "NPC_1" / "{NPC_1}" / "[[NPC_1]]" in any case (not turn_dsl.is_slot_token, which rejects legend words)."""
    return bool(slot_of(value))


def slot_refs_in_ops(ops: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """[{"op", "slot", "line", "field"}] for every NPC_NEW / CAST / TALK / REL / NPC_NOTE arg or flag that is a slot token."""
    out: list[dict[str, Any]] = []
    for entry in ops or []:
        if not isinstance(entry, dict):
            continue
        op = _s(entry.get("op")).upper()
        args = [str(a) for a in (entry.get("args") or [])]
        flags = entry.get("flags") if isinstance(entry.get("flags"), dict) else {}
        line = int(entry.get("line") or 0)
        if op == "NPC_NEW":
            name = flags.get("NAME") or (args[0] if args else "")
            if is_slot_token(name):
                out.append({"op": op, "slot": slot_of(name), "line": line, "field": "name"})
        elif op == "CAST":
            if len(args) > 1 and is_slot_token(args[1]):
                out.append({"op": op, "slot": slot_of(args[1]), "line": line, "field": "code"})
        elif op in ("TALK", "NPC_NOTE"):
            if args and is_slot_token(args[0]):
                out.append({"op": op, "slot": slot_of(args[0]), "line": line, "field": "code"})
        elif op == "REL":
            for arg in args[:2]:
                if is_slot_token(arg):
                    out.append({"op": op, "slot": slot_of(arg), "line": line, "field": "code"})
    return out


# ---------------------------------------------------------------------------
# Bind
# ---------------------------------------------------------------------------


def _slot_entries(involved: dict[str, Any] | None, entity_map: dict[str, Any], *, seed: int) -> dict[str, dict[str, Any]]:
    """Binding.slots from an Involved: one entry per slot with its EntityRef and render forms."""
    slots: dict[str, dict[str, Any]] = {}
    if not isinstance(involved, dict):
        return slots
    by_code = entity_map.get("by_code", {}) if isinstance(entity_map, dict) else {}
    for entry in involved.get("npcs") or []:
        code = _s(entry.get("code")).upper()
        name = _s(entry.get("name"))
        known = bool(code)
        if known:
            ref = by_code.get(code)
            if ref is not None and not name:
                name = ref["name"]
            ref = dict(ref) if ref is not None else _entity_ref(code, name, "person", entry.get("role_hint"))
        else:
            if not name:
                try:
                    from app.world import invent_person_name, name_seed

                    name = invent_person_name(seed=name_seed("scene_cast", "fallback", int(seed or 0), entry.get("slot")))
                except Exception:
                    name = "Someone"
            ref = _entity_ref("", name, "person", entry.get("role_hint"))
        ref["name"] = ref.get("name") or name
        slots[_s(entry.get("slot")).upper()] = {
            "ref": ref,
            "status": "known" if known else "new",
            "render": RENDER["person_first"].format(name=ref["name"], code=code) if known else RENDER["person_new"].format(name=ref["name"]),
            "render_bare": RENDER["person_later"].format(name=ref["name"]),
            "pronouns": _s(entry.get("pronouns")).lower() if _s(entry.get("pronouns")).lower() in PRONOUNS else "they",
            "first_mention_done": False,
        }
    for entry in involved.get("items") or []:
        code = _s(entry.get("ref")).upper()
        name = _s(entry.get("name"))
        ref = dict(by_code.get(code) or _entity_ref(code, name, "item"))
        article = "the " if _s(entry.get("kind")) == "new" else "your "
        first = RENDER["item_first"].format(article=article, name=ref["name"], code=code) if code else RENDER["item_later"].format(article=article, name=ref["name"])
        slots[_s(entry.get("slot")).upper()] = {
            "ref": ref,
            "status": "known" if code else "new",
            "render": first,
            "render_bare": RENDER["item_later"].format(article=article, name=ref["name"]),
            "pronouns": "it",
            "first_mention_done": False,
        }
    for entry in involved.get("places") or []:
        code = _s(entry.get("code")).upper()
        name = _s(entry.get("name"))
        ref = dict(by_code.get(code) or _entity_ref(code, name, "place"))
        slots[_s(entry.get("slot")).upper()] = {
            "ref": ref,
            "status": "known" if code else "new",
            "render": RENDER["place_first"].format(name=ref["name"], code=code) if code else RENDER["place_later"].format(name=ref["name"]),
            "render_bare": RENDER["place_later"].format(name=ref["name"]),
            "pronouns": "it",
            "first_mention_done": False,
        }
    return slots


def render_slot(entry: dict[str, Any], *, form: str = "", first: bool, possessive: bool = False) -> str:
    """One placeholder's text for a slot entry (Binding.slots value) per RENDER / PRONOUNS.

    `possessive` appends POSSESSIVE_FORM's "'s"; bind() itself leaves the apostrophe that already
    follows the placeholder in the text, so it calls this with possessive False.
    """
    form = _s(form).lower()
    kind = _s((entry.get("ref") or {}).get("kind")) or "person"
    name = _s((entry.get("ref") or {}).get("name"))
    if form in ("they", "them", "their", "theirs", "he", "she", "his", "her", "it", "its"):
        case = _FORM_TO_CASE.get(form, form)
        if kind == "person":
            text = PRONOUNS.get(_s(entry.get("pronouns")).lower() or "they", PRONOUNS["they"]).get(case, "they")
        else:
            text = ITEM_PRONOUNS.get(case, "it")
    elif form == "first":
        text = name.split()[0] if name.split() else name
    elif form == "name":
        text = name
    else:
        text = _s(entry.get("render")) if first else _s(entry.get("render_bare"))
    if possessive:
        text = POSSESSIVE_FORM.format(render=text)
    return text


def _at_sentence_start(text: str, pos: int) -> bool:
    before = text[:pos].rstrip(" \t\"'“‘(")
    return not before or before.endswith(("\n", ".", "!", "?", "…"))


def _preceded_by_article(text: str, pos: int) -> bool:
    before = text[:pos].rstrip()
    words = before.lower().split()
    return bool(words) and words[-1].strip("\"'“‘(") in _ARTICLE_WORDS


def _fill_text(
    text: str,
    where: str,
    slots: dict[str, dict[str, Any]],
    mentioned: set[str],
    unbound: list[str],
    replacements: list[dict[str, str]],
    used: set[str],
) -> str:
    """Replace every placeholder in one text; first-mention bookkeeping in `mentioned` (per scope)."""
    source = str(text or "")
    out: list[str] = []
    cursor = 0
    for ph in find_placeholders(source, where=where):
        out.append(source[cursor : ph["start"]])
        entry = slots.get(ph["slot"])
        if entry is None:
            if ph["slot"] not in unbound:
                unbound.append(ph["slot"])
            out.append(ph["raw"])
            cursor = ph["end"]
            continue
        used.add(ph["slot"])
        first = ph["slot"] not in mentioned and not ph["form"]
        rendered = render_slot(entry, form=ph["form"], first=first)
        prefix = "".join(out)
        if entry["ref"].get("kind") == "item" and not ph["form"] and _preceded_by_article(prefix, len(prefix)):
            rendered = re.sub(r"^(?:your|the)\s+", "", rendered)
        if _at_sentence_start(source, ph["start"]) and rendered[:1].islower():
            rendered = rendered[:1].upper() + rendered[1:]
        if not ph["form"] or ph["form"] in ("name", "first"):
            mentioned.add(ph["slot"])
            entry["first_mention_done"] = True
        replacements.append({"from": ph["raw"], "to": rendered, "where": where})
        out.append(rendered)
        cursor = ph["end"]
    out.append(source[cursor:])
    return "".join(out)


def _npc_row_proposal(entry: dict[str, Any], slot: str, location_code: str) -> dict[str, Any]:
    return {
        "code": None,
        "name": _s(entry["ref"].get("name"))[:120],
        "race": "human",
        "location": location_code,
        "role": (_s(entry["ref"].get("role")) or "local")[:80],
        "summary": "",
        "attitude": "neutral",
        "personality": "",
        "likes": "",
        "principles": "",
        "dislikes": "",
        "rank": "",
        "stat_profile": {},
        "skill_profile": {},
        "trust_delta": 0,
        "known_fact": "",
        "mentioned_by": None,
        "presence": "event_worthy",
        "_slot": slot,
    }


def _bind_code_or_name(value: Any, slots: dict[str, dict[str, Any]], used: set[str]) -> Any:
    slot = slot_of(value)
    if not slot or slot not in slots:
        return value
    entry = slots[slot]
    used.add(slot)
    return entry["ref"]["code"] if entry["status"] == "known" else entry["ref"]["name"]


def bind(turn: dict[str, Any], involved: dict[str, Any] | None, entity_map: dict[str, Any], *, seed: int = 0) -> dict[str, Any]:
    """Map every placeholder to text and every slot token in the ops to a code or drawn name.

    Returns {"turn": new dict, "binding": Binding, "text_changed": bool}. Never allocates a code; new
    faces are proposed as NpcRowProposal rows in binding["new_npcs"] for the apply seat.
    """
    source = turn if isinstance(turn, dict) else {}
    new_turn = copy.deepcopy(source)
    slots = _slot_entries(involved, entity_map, seed=int(seed or 0))
    location_code = _s((involved or {}).get("location_code")).upper() if isinstance(involved, dict) else ""
    fixes: list[str] = []
    unbound: list[str] = []
    replacements: list[dict[str, str]] = []
    used: set[str] = set()

    def normalise(text: str) -> str:
        fixed, found = normalize_placeholder_text(text)
        fixes.extend(f for f in found if f not in fixes)
        return fixed

    # (1) + (2) + (3): prose, segment by segment, then summary and scene_plan, each its own first-mention scope.
    mentioned: set[str] = set()
    segments = new_turn.get("narration_segments") if isinstance(new_turn.get("narration_segments"), list) else []
    seg_rows = [seg for seg in segments if isinstance(seg, dict)]
    if any(_s(seg.get("text")) for seg in seg_rows):
        for seg in seg_rows:
            seg["text"] = _fill_text(normalise(str(seg.get("text") or "")), "narration", slots, mentioned, unbound, replacements, used)
        new_turn["narration"] = "\n\n".join(str(seg.get("text") or "") for seg in seg_rows).strip()
    elif isinstance(new_turn.get("narration"), str):
        new_turn["narration"] = _fill_text(normalise(new_turn["narration"]), "narration", slots, mentioned, unbound, replacements, used)
    if isinstance(new_turn.get("turn_summary"), str):
        new_turn["turn_summary"] = _fill_text(normalise(new_turn["turn_summary"]), "turn_summary", slots, set(), unbound, replacements, used)
    plan_scope: set[str] = set()
    for container, key, text in _scene_plan_strings(new_turn.get("scene_plan")):
        container[key] = _fill_text(normalise(text), "scene_plan", slots, plan_scope, unbound, replacements, used)

    # (4) ops: npcs rows, scene_cast buckets, conversations, relationships.
    new_name_to_slot = {e["ref"]["name"].lower(): s for s, e in slots.items() if s.startswith("NPC_") and e["status"] == "new"}
    covered: set[str] = set()
    for row in new_turn.get("npcs") or []:
        if not isinstance(row, dict):
            continue
        name = _s(row.get("name"))
        slot = slot_of(name) or new_name_to_slot.get(name.lower(), "")
        if slot and slot in slots and slot.startswith("NPC_"):
            entry = slots[slot]
            used.add(slot)
            row["name"] = entry["ref"]["name"]
            row["_slot"] = slot
            if entry["status"] == "known" and not _s(row.get("code")):
                row["code"] = entry["ref"]["code"]
            if entry["status"] == "new":
                if not _s(row.get("role")) or _s(row.get("role")).lower() == "local":
                    row["role"] = _s(entry["ref"].get("role")) or _s(row.get("role")) or "local"
                row.setdefault("presence", "event_worthy")
                covered.add(slot)
    pending_cast: list[dict[str, str]] = []
    cast = new_turn.get("scene_cast") if isinstance(new_turn.get("scene_cast"), dict) else None
    if cast is not None:
        for bucket in ("present", "interacting", "off"):
            kept: list[str] = []
            for code in cast.get(bucket) or []:
                slot = slot_of(code)
                if slot and slot in slots:
                    entry = slots[slot]
                    used.add(slot)
                    if entry["status"] == "known":
                        if entry["ref"]["code"] not in kept:
                            kept.append(entry["ref"]["code"])
                    else:
                        pending_cast.append({"slot": slot, "name": entry["ref"]["name"], "bucket": bucket})
                    continue
                if slot:
                    if slot not in unbound:
                        unbound.append(slot)
                    continue
                kept.append(code)
            if bucket in cast:
                cast[bucket] = kept
    for row in new_turn.get("conversations") or []:
        if isinstance(row, dict) and "npc_code" in row:
            row["npc_code"] = _bind_code_or_name(row.get("npc_code"), slots, used)
    for row in new_turn.get("relationships") or []:
        if isinstance(row, dict):
            for key in ("source_code", "target_code"):
                if key in row:
                    row[key] = _bind_code_or_name(row.get(key), slots, used)

    # (5) proposals for new slots the text used and no npcs row covers.
    new_npcs = [
        _npc_row_proposal(slots[slot], slot, location_code)
        for slot in sorted(used, key=lambda s: (s.split("_")[0], int(s.split("_")[1])))
        if slot.startswith("NPC_") and slots[slot]["status"] == "new" and slot not in covered
    ]
    binding = {
        "slots": slots,
        "unbound": unbound,
        "new_npcs": new_npcs,
        "pending_cast": pending_cast,
        "replacements": replacements,
        "fixes": fixes,
        "seed": int(seed or 0),
    }
    return {"turn": new_turn, "binding": binding, "text_changed": bool(replacements)}


def npc_rows_for_apply(turn: dict[str, Any]) -> list[dict[str, Any]]:
    """binding.new_npcs from turn["_dsl"]["scene_cast"] (deep copies); [] when absent."""
    report = report_of(turn)
    binding = report.get("binding") if isinstance(report, dict) else None
    rows = binding.get("new_npcs") if isinstance(binding, dict) else None
    return [copy.deepcopy(r) for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def resolve_pending_cast(turn: dict[str, Any], code_by_name: dict[str, str]) -> dict[str, Any]:
    """The scene_cast dict with pending new faces' codes appended (does not mutate the turn)."""
    source = turn.get("scene_cast") if isinstance(turn, dict) and isinstance(turn.get("scene_cast"), dict) else {}
    cast = {
        "present": list(source.get("present") or []),
        "interacting": list(source.get("interacting") or []),
        "off": list(source.get("off") or []),
        "keywords": list(source.get("keywords") or []),
    }
    lookup = {_s(k).lower(): _s(v).upper() for k, v in (code_by_name or {}).items() if _s(k) and _s(v)}
    report = report_of(turn)
    binding = report.get("binding") if isinstance(report, dict) else None
    for pending in (binding or {}).get("pending_cast") or []:
        if not isinstance(pending, dict):
            continue
        code = lookup.get(_s(pending.get("name")).lower())
        bucket = _s(pending.get("bucket"))
        if code and bucket in ("present", "interacting", "off") and code not in cast[bucket]:
            cast[bucket].append(code)
    return cast


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------


def _prose_of(turn: dict[str, Any]) -> str:
    segments = turn.get("narration_segments") if isinstance(turn.get("narration_segments"), list) else []
    joined = "\n\n".join(str(seg.get("text") or "") for seg in segments if isinstance(seg, dict)).strip()
    return joined or str(turn.get("narration") or "")


def _distinct_spans(hits: list[tuple[int, int, str]]) -> list[str]:
    """Evidence strings of hits whose spans do not overlap an earlier (longer-first) hit, in text order."""
    kept: list[tuple[int, int, str]] = []
    for start, end, evidence in sorted(hits, key=lambda h: (h[0], -(h[1] - h[0]))):
        if any(s < end and start < e for s, e, _t in kept):
            continue
        kept.append((start, end, evidence))
    return [evidence for _s0, _e0, evidence in kept]


def gate_item_as_agent(text: str, item_names: list[str]) -> list[dict[str, Any]]:
    """Evidence rows (ok False) for every inventory name, gear head or [[I#]] used as a person or faction."""
    source = str(text or "")
    hits: list[tuple[int, int, str]] = []
    for match in _GEAR_GROUP_RE.finditer(source):
        hits.append((match.start(), match.end(), match.group(0)))
    for match in _ITEM_CODE_AGENT_RE.finditer(source):
        hits.append((match.start(), match.end(), _sentence_holding(source, match.start()) or match.group(0)))
    for name in sorted({_s(n) for n in item_names or [] if _s(n)}, key=len, reverse=True):
        if len(name) < 4:
            continue
        pattern = re.compile(
            rf"(?<![\w]){re.escape(name)}(?:\s*\[\[I\d+\]\])?(?:{_POSS}\s+(?:{_GROUP_ALT}|voice|hand|eyes?|gaze)|\s+(?:{_VERB_ALT}))\b",
            re.I,
        )
        for match in pattern.finditer(source):
            hits.append((match.start(), match.end(), match.group(0)))
    return [_evidence("item_as_agent", False, evidence, "block") for evidence in _distinct_spans(hits)]


def gate_place_as_agent(text: str, place_names: list[str]) -> list[dict[str, Any]]:
    """Evidence rows (ok False) for every place name, place head or [[L#]] used as a person or faction."""
    source = str(text or "")
    hits: list[tuple[int, int, str]] = []
    for match in _PLACE_CODE_AGENT_RE.finditer(source):
        hits.append((match.start(), match.end(), match.group(0)))
    forms: set[str] = set()
    for name in place_names or []:
        n = _s(name)
        if not n:
            continue
        forms.add(n)
        head = n.split()[-1].lower() if n.split() else ""
        if head in SCENERY_WORDS:
            forms.add(head)
    for form in sorted(forms, key=len, reverse=True):
        pattern = re.compile(
            rf"(?<![\w]){re.escape(form)}(?:\s*\[\[L\d+\]\])?(?:{_POSS}\s+(?:{_GROUP_ALT})|\s+(?:{_VERB_ALT}))\b",
            re.I,
        )
        for match in pattern.finditer(source):
            hits.append((match.start(), match.end(), match.group(0)))
    return [_evidence("place_as_agent", False, evidence, "block") for evidence in _distinct_spans(hits)]


def _new_npc_names(turn: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for row in turn.get("npcs") or []:
        if isinstance(row, dict) and not _s(row.get("code")) and _s(row.get("name")):
            if _s(row.get("name")).lower() not in {n.lower() for n in names}:
                names.append(_s(row.get("name")))
    return names


def gate_cast_overflow(turn: dict[str, Any], limit: int, known_names: list[str]) -> dict[str, Any]:
    """One Evidence row: distinct code-less npc names plus described figures in the prose against the limit."""
    turn = turn if isinstance(turn, dict) else {}
    prose = _prose_of(turn)
    new_names = _new_npc_names(turn)
    known = [_s(n) for n in known_names or [] if _s(n)] + new_names
    try:
        from app.world import _figure_hints

        hints = _figure_hints(prose, known)
    except Exception:
        hints = []
    kept_hints: list[str] = []
    for hint in hints:
        pos = prose.find(hint)
        sentence = _sentence_holding(prose, pos) if pos >= 0 else ""
        if any(n and n.lower() in sentence.lower() for n in new_names):
            continue  # the figure is a bound new face described in the same sentence
        kept_hints.append(hint)
    count = len(new_names) + len(kept_hints)
    fired = count > int(limit)
    listed = ", ".join(new_names + kept_hints)
    return _evidence("cast_overflow", not fired, f"{count} new faces (limit {int(limit)}): {listed}" if fired else listed, "block")


def _spoken(prose: str, entity_map: dict[str, Any], player_input: str) -> list[dict[str, str]]:
    rows = [{"code": p["code"], "name": p["name"], "aliases": []} for p in entity_map.get("people", []) if p.get("code")]
    try:
        from app.conversation import spoken_lines

        return spoken_lines(prose, rows, player_input)
    except Exception:
        return []


def _acts_in_prose(prose: str, name: str, pronouns: str) -> bool:
    """True when the person does something: their name, or their subject pronoun opening the sentence
    after one that named them, precedes an AGENT_VERBS word within three words."""
    if not name:
        return False
    if re.search(rf"(?<![\w]){re.escape(name)}(?:\s*\[\[[A-Z]{{1,3}}\]\])?\s+(?:[\w,'’-]+\s+){{0,3}}(?:{_VERB_ALT})\b", prose, re.I):
        return True
    subject = PRONOUNS.get(pronouns, PRONOUNS["they"])["they"]
    named_before = False
    for sentence in _sentences(prose):
        lead = sentence.lstrip(" \"'\u201c\u2018(")
        if named_before and re.match(rf"{subject}\s+(?:[\w,'’-]+\s+){{0,3}}(?:{_VERB_ALT})\b", lead, re.I):
            return True
        named_before = bool(re.search(rf"(?<![\w]){re.escape(name)}(?![\w])", sentence))
    return False


def verify(
    turn: dict[str, Any],
    involved: dict[str, Any] | None,
    binding: dict[str, Any] | None,
    entity_map: dict[str, Any],
    *,
    player_input: str = "",
) -> dict[str, Any]:
    """Run every GATES row on the current prose, summary and scene_plan; a block row that fired is a policy blocker."""
    turn = turn if isinstance(turn, dict) else {}
    entity_map = entity_map if isinstance(entity_map, dict) else entity_map_from_rows([], [], [])
    involved = involved if isinstance(involved, dict) else None
    binding = binding if isinstance(binding, dict) else None
    prose = _prose_of(turn)
    texts = [(w, t) for w, t in _turn_texts(turn)]
    by_code = entity_map.get("by_code", {})
    gates: list[dict[str, Any]] = []
    warnings: list[str] = []
    counts = {"placeholders": 0, "unbound": 0, "new_names": 0, "agent_items": 0, "agent_places": 0}

    # placeholder_unbound
    leftover: list[dict[str, Any]] = []
    for where, text in texts:
        normalised, _fixes = normalize_placeholder_text(text)
        leftover.extend(find_placeholders(normalised, where=where) if normalised != text else find_placeholders(text, where=where))
    counts["placeholders"] = len(leftover)
    counts["unbound"] = len({p["slot"] for p in leftover})
    if leftover:
        first = leftover[0]
        where_text = next((t for w, t in texts if w == first["where"] and first["raw"] in t), "")
        gates.append(_evidence("placeholder_unbound", False, f"{first['where']}: {_sentence_holding(where_text, where_text.find(first['raw'])) or first['raw']}", "block"))
    else:
        gates.append(_evidence("placeholder_unbound", True, "", "block"))

    # npc_slot_not_person
    bad = ""
    try:
        from app.world import _is_place_or_item_code, is_generic_person_label, is_plausible_person_name
    except Exception:  # pragma: no cover - the world module is always importable in this repo
        _is_place_or_item_code = lambda v: bool(re.fullmatch(r"[LIElie]\d+", _s(v)))  # noqa: E731
        is_generic_person_label = lambda n: False  # noqa: E731
        is_plausible_person_name = lambda n: bool(_s(n))  # noqa: E731
    npc_entries = list((involved or {}).get("npcs") or [])
    for entry in npc_entries:
        code = _s(entry.get("code")).upper()
        name = _s(entry.get("name"))
        if code and (_is_place_or_item_code(code) or (code in by_code and by_code[code].get("kind") != "person")):
            bad = f"{entry.get('slot')} bound to {code} ({name or 'no name'})"
            break
        if not code and name and (is_generic_person_label(name) or not is_plausible_person_name(name)):
            bad = f"{entry.get('slot')} named {name!r}"
            break
    if not bad:
        for slot, entry in ((binding or {}).get("slots") or {}).items():
            ref = entry.get("ref") if isinstance(entry, dict) else None
            if _s(slot).startswith("NPC_") and isinstance(ref, dict) and ref.get("kind") != "person":
                bad = f"{slot} bound to {ref.get('code') or ref.get('name')} ({ref.get('kind')})"
                break
    gates.append(_evidence("npc_slot_not_person", not bad, bad, "block"))

    # slot_name_is_clothing
    new_face_names: list[str] = []
    for entry in npc_entries:
        if not _s(entry.get("code")) and _s(entry.get("name")):
            new_face_names.append(_s(entry.get("name")))
    for row in ((binding or {}).get("new_npcs") or []):
        if isinstance(row, dict) and _s(row.get("name")):
            new_face_names.append(_s(row.get("name")))
    new_face_names.extend(_new_npc_names(turn))
    clothing = next((n for n in new_face_names if _GEAR_WORD_RE.search(n) or _SCENERY_WORD_RE.search(n)), "")
    gates.append(_evidence("slot_name_is_clothing", not clothing, clothing, "block"))

    # item_as_agent / place_as_agent
    item_names = [i["name"] for i in entity_map.get("items", [])] + [
        _s(c.get("name")) for c in turn.get("inventory_changes") or [] if isinstance(c, dict) and _s(c.get("name"))
    ]
    item_rows = gate_item_as_agent(prose, item_names)
    counts["agent_items"] = len(item_rows)
    gates.append(item_rows[0] if item_rows else _evidence("item_as_agent", True, "", "block"))
    place_names = [p["name"] for p in entity_map.get("places", [])] + [
        _s(l.get("name")) for l in turn.get("locations") or [] if isinstance(l, dict) and _s(l.get("name"))
    ]
    place_rows = gate_place_as_agent(prose, place_names)
    counts["agent_places"] = len(place_rows)
    gates.append(place_rows[0] if place_rows else _evidence("place_as_agent", True, "", "block"))

    # cast_overflow
    limit = int(((involved or {}).get("limits") or {}).get("new_npcs", LIMITS["new_npcs"]))
    known_names = [p["name"] for p in entity_map.get("people", []) if p.get("code")]
    for entry in npc_entries:
        if _s(entry.get("name")):
            known_names.append(_s(entry.get("name")))
    counts["new_names"] = len(_new_npc_names(turn))
    gates.append(gate_cast_overflow(turn, limit, known_names))

    # unlisted_new_npc (warn)
    low_prose = prose.lower()
    unlisted = ""
    for row in turn.get("npcs") or []:
        if not isinstance(row, dict) or _s(row.get("code")) or row.get("_slot"):
            continue
        name = _s(row.get("name"))
        parts = [p for p in name.lower().split() if len(p) >= 3]
        if name and not (name.lower() in low_prose or any(p in low_prose for p in parts)):
            unlisted = name
            break
    gates.append(_evidence("unlisted_new_npc", not unlisted, unlisted, "warn"))

    # speaker_outside_cast (warn)
    spoken = _spoken(prose, entity_map, player_input)
    cast_codes = {_s(e.get("code")).upper() for e in npc_entries if _s(e.get("code"))}
    outside = ""
    if involved is not None:
        for line in spoken:
            code = _s(line.get("code")).upper()
            if code and code not in cast_codes:
                outside = f"{code}: {line.get('line')}"
                break
    gates.append(_evidence("speaker_outside_cast", not outside, outside, "warn"))

    # must_speak_silent (warn)
    silent = ""
    spoken_codes = {_s(line.get("code")).upper() for line in spoken}
    for entry in npc_entries:
        if not entry.get("must_speak"):
            continue
        code = _s(entry.get("code")).upper()
        name = _s(entry.get("name"))
        if code in spoken_codes:
            continue
        acts = _acts_in_prose(prose, name, _s(entry.get("pronouns")) or "they")
        if not acts:
            silent = f"{entry.get('slot')} {name or code} has no line and no act"
            break
    gates.append(_evidence("must_speak_silent", not silent, silent, "warn"))

    # slot_reused_for_two
    reused = ""
    names_by_slot: dict[str, set[str]] = {}
    for row in turn.get("npcs") or []:
        if isinstance(row, dict) and _s(row.get("_slot")) and _s(row.get("name")):
            names_by_slot.setdefault(_s(row.get("_slot")).upper(), set()).add(_s(row.get("name")).lower())
    for slot, entry in ((binding or {}).get("slots") or {}).items():
        if isinstance(entry, dict) and _s(slot).upper() in names_by_slot:
            names_by_slot[_s(slot).upper()].add(_s(entry.get("render_bare")).lower())
    for slot, names in names_by_slot.items():
        if len(names) > 1:
            reused = f"{slot}: {', '.join(sorted(names))}"
            break
    gates.append(_evidence("slot_reused_for_two", not reused, reused, "block"))

    order = {check: i for i, (check, _sev) in enumerate(GATES)}
    gates.sort(key=lambda g: order.get(g["check"], 99))
    blockers = [g["check"] for g in gates if g["severity"] == "block" and not g["ok"]]
    warnings = [f"{g['check']}: {g['evidence']}" for g in gates if g["severity"] == "warn" and not g["ok"]]
    return {"ok": not blockers, "gates": gates, "policy_blockers": blockers, "warnings": warnings, "counts": counts}


# ---------------------------------------------------------------------------
# Repair
# ---------------------------------------------------------------------------


def _apply_text_plan(text: str, replacements: list[dict[str, str]], cuts: list[str]) -> str:
    out = str(text or "")
    for rep in replacements:
        if rep.get("from"):
            out = out.replace(rep["from"], rep.get("to", ""))
    for sentence in cuts:
        if sentence and sentence in out:
            out = out.replace(sentence, "", 1)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def propose_repairs(
    turn: dict[str, Any],
    verify_result: dict[str, Any],
    binding: dict[str, Any] | None,
    entity_map: dict[str, Any],
    *,
    seed: int = 0,
) -> dict[str, Any]:
    """A deterministic repair plan for the gates that fired, in REPAIR_ORDER; "rewrite" asks for one model call."""
    turn = turn if isinstance(turn, dict) else {}
    verify_result = verify_result if isinstance(verify_result, dict) else {}
    binding = binding if isinstance(binding, dict) else {}
    entity_map = entity_map if isinstance(entity_map, dict) else entity_map_from_rows([], [], [])
    slots = binding.get("slots") if isinstance(binding.get("slots"), dict) else {}
    fired = {g["check"]: g for g in verify_result.get("gates") or [] if isinstance(g, dict) and not g.get("ok")}
    plan: dict[str, Any] = {
        "mode": "none",
        "needs_model_call": False,
        "replacements": [],
        "cut_sentences": [],
        "reask_slots": [],
        "renamed": [],
        "npcs_dropped": [],
        "text": "",
        "reasons": [],
    }
    actionable = {"placeholder_unbound", "item_as_agent", "place_as_agent", "slot_name_is_clothing", "cast_overflow", "npc_slot_not_person", "slot_reused_for_two"}
    if not (set(fired) & actionable):
        return plan
    prose = _prose_of(turn)
    prose, _fixes = normalize_placeholder_text(prose)

    def add_reason(check: str) -> None:
        if check in fired and check not in plan["reasons"]:
            plan["reasons"].append(check)

    def add_cut(sentence: str, slot: str = "") -> None:
        if sentence and sentence not in plan["cut_sentences"]:
            plan["cut_sentences"].append(sentence)
        if slot and slot not in plan["reask_slots"]:
            plan["reask_slots"].append(slot)

    # refill_unbound / cut_unfixable for placeholders left in the text
    if "placeholder_unbound" in fired:
        add_reason("placeholder_unbound")
        mentioned = {s for s, e in slots.items() if e.get("render_bare") and _s(e.get("render_bare")).lower() in prose.lower()}
        for ph in find_placeholders(prose):
            entry = slots.get(ph["slot"])
            if entry is not None:
                first = ph["slot"] not in mentioned and not ph["form"]
                rendered = render_slot(entry, form=ph["form"], first=first)
                if _at_sentence_start(prose, ph["start"]) and rendered[:1].islower():
                    rendered = rendered[:1].upper() + rendered[1:]
                if not ph["form"]:
                    mentioned.add(ph["slot"])
                plan["replacements"].append({"from": ph["raw"], "to": rendered, "why": "refill_unbound"})
            else:
                add_cut(_sentence_holding(prose, ph["start"]), ph["slot"])

    # fix_agent_heads
    if "item_as_agent" in fired or "place_as_agent" in fired:
        add_reason("item_as_agent")
        add_reason("place_as_agent")
        for match in _GEAR_GROUP_RE.finditer(prose):
            plan["replacements"].append({"from": match.group(0), "to": AGENT_HEAD_REWRITE["group"].format(group=match.group(1).lower()), "why": "fix_agent_heads"})
        item_names = [i["name"] for i in entity_map.get("items", [])]
        for name in sorted({_s(n) for n in item_names if len(_s(n)) >= 4}, key=len, reverse=True):
            poss = re.compile(rf"(?<![\w]){re.escape(name)}(?:\s*\[\[I\d+\]\])?{_POSS}\s+({_GROUP_ALT}|voice|hand|eyes?|gaze)\b", re.I)
            for match in poss.finditer(prose):
                head = match.group(1).lower()
                if re.fullmatch(_GROUP_ALT, head, re.I):
                    to = AGENT_HEAD_REWRITE["group"].format(group=head)
                else:
                    to = AGENT_HEAD_REWRITE.get("eyes" if head.startswith("eye") or head == "gaze" else head, f"its {head}")
                plan["replacements"].append({"from": match.group(0), "to": to, "why": "fix_agent_heads"})
            verb = re.compile(rf"(?<![\w]){re.escape(name)}(?:\s*\[\[I\d+\]\])?\s+(?:{_VERB_ALT})\b", re.I)
            for match in verb.finditer(prose):
                add_cut(_sentence_holding(prose, match.start()))
        for match in _ITEM_CODE_AGENT_RE.finditer(prose):
            add_cut(_sentence_holding(prose, match.start()))
        for match in _PLACE_CODE_AGENT_RE.finditer(prose):
            if re.search(_POSS, match.group(0)):
                group = match.group(0).split()[-1].lower()
                plan["replacements"].append({"from": match.group(0), "to": AGENT_HEAD_REWRITE["group"].format(group=group), "why": "fix_agent_heads"})
            else:
                add_cut(_sentence_holding(prose, match.start()))
        place_forms: set[str] = set()
        for p in entity_map.get("places", []):
            place_forms.add(p["name"])
            head = p["name"].split()[-1].lower() if p["name"].split() else ""
            if head in SCENERY_WORDS:
                place_forms.add(head)
        for form in sorted(place_forms, key=len, reverse=True):
            poss = re.compile(rf"(?<![\w]){re.escape(form)}(?:\s*\[\[L\d+\]\])?{_POSS}\s+({_GROUP_ALT})\b", re.I)
            for match in poss.finditer(prose):
                plan["replacements"].append({"from": match.group(0), "to": AGENT_HEAD_REWRITE["group"].format(group=match.group(1).lower()), "why": "fix_agent_heads"})
            verb = re.compile(rf"(?<![\w]){re.escape(form)}(?:\s*\[\[L\d+\]\])?\s+(?:{_VERB_ALT})\b", re.I)
            for match in verb.finditer(prose):
                add_cut(_sentence_holding(prose, match.start()))

    # rename_clothing_slot
    if "slot_name_is_clothing" in fired:
        add_reason("slot_name_is_clothing")
        taken = set(entity_map.get("names_lower", {}).keys())
        candidates: list[tuple[str, str]] = []
        for slot, entry in slots.items():
            if slot.startswith("NPC_") and entry.get("status") == "new":
                candidates.append((slot, _s((entry.get("ref") or {}).get("name"))))
        for row in turn.get("npcs") or []:
            if isinstance(row, dict) and not _s(row.get("code")) and _s(row.get("name")):
                candidates.append((_s(row.get("_slot")), _s(row.get("name"))))
        for slot, old in candidates:
            if not old or not (_GEAR_WORD_RE.search(old) or _SCENERY_WORD_RE.search(old)):
                continue
            if any(r["old"] == old for r in plan["renamed"]):
                continue
            new = ""
            try:
                from app.world import invent_person_name, name_seed

                for attempt in range(NAME_ATTEMPTS):
                    candidate = invent_person_name(seed=name_seed("scene_cast", "rename", int(seed or 0), old, attempt))
                    if candidate.lower() not in taken and _name_is_usable(candidate, entity_map):
                        new = candidate
                        break
            except Exception:
                new = ""
            if not new:
                add_cut(_sentence_holding(prose, prose.find(old)) if old in prose else "", slot)
                if slot and slot not in plan["reask_slots"]:
                    plan["reask_slots"].append(slot)
                continue
            taken.add(new.lower())
            plan["renamed"].append({"slot": slot, "old": old, "new": new})
            plan["replacements"].append({"from": old, "to": new, "why": "rename_clothing_slot"})

    # npc_slot_not_person / slot_reused_for_two: the row cannot be trusted; drop it and ask for the slot again.
    for check in ("npc_slot_not_person", "slot_reused_for_two"):
        if check in fired:
            add_reason(check)
            for row in turn.get("npcs") or []:
                if isinstance(row, dict) and not _s(row.get("code")) and _s(row.get("name")) and _s(row.get("_slot")):
                    if _s(row.get("_slot")) in slots and _s(slots[_s(row.get("_slot"))].get("render_bare")).lower() != _s(row.get("name")).lower():
                        if _s(row.get("name")) not in plan["npcs_dropped"]:
                            plan["npcs_dropped"].append(_s(row.get("name")))
                        if _s(row.get("_slot")) not in plan["reask_slots"]:
                            plan["reask_slots"].append(_s(row.get("_slot")))

    repaired = _apply_text_plan(prose, plan["replacements"], plan["cut_sentences"])
    overflow = "cast_overflow" in fired
    if overflow:
        add_reason("cast_overflow")
    too_many = len(plan["cut_sentences"]) > MAX_SENTENCE_CUTS
    too_short = bool(plan["cut_sentences"]) and len(repaired) < MIN_PROSE_AFTER_CUT
    if overflow or too_many or too_short:
        plan["mode"] = "rewrite"
        plan["needs_model_call"] = True
        for slot in [s for s in binding.get("unbound") or [] if _s(s)] + [r["slot"] for r in plan["renamed"] if r.get("slot")]:
            if slot not in plan["reask_slots"]:
                plan["reask_slots"].append(slot)
        plan["text"] = ""
        return plan
    if plan["cut_sentences"]:
        plan["mode"] = "cut"
    elif plan["replacements"] or plan["npcs_dropped"]:
        plan["mode"] = "refill"
    else:
        plan["mode"] = "none"
        return plan
    plan["text"] = repaired
    return plan


def apply_repairs(turn: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    """A new turn dict with the plan applied: prose spliced segment by segment, summary replacements,
    npcs rows renamed or dropped, _dsl.scene_cast.repairs set; every other key untouched."""
    new_turn = copy.deepcopy(turn if isinstance(turn, dict) else {})
    plan = plan if isinstance(plan, dict) else {}
    attach_report(new_turn, {"repairs": copy.deepcopy(plan)})
    if _s(plan.get("mode")) not in ("refill", "cut"):
        return new_turn
    replacements = [r for r in plan.get("replacements") or [] if isinstance(r, dict)]
    cuts = [c for c in plan.get("cut_sentences") or [] if _s(c)]
    segments = new_turn.get("narration_segments") if isinstance(new_turn.get("narration_segments"), list) else []
    seg_rows = [seg for seg in segments if isinstance(seg, dict)]
    if any(_s(seg.get("text")) for seg in seg_rows):
        kept: list[dict[str, Any]] = []
        for seg in seg_rows:
            fixed, _f = normalize_placeholder_text(str(seg.get("text") or ""))
            seg["text"] = _apply_text_plan(fixed, replacements, cuts)
            if seg["text"]:
                kept.append(seg)
        new_turn["narration_segments"] = kept
        new_turn["narration"] = "\n\n".join(seg["text"] for seg in kept).strip()
    elif isinstance(new_turn.get("narration"), str):
        fixed, _f = normalize_placeholder_text(new_turn["narration"])
        new_turn["narration"] = _apply_text_plan(fixed, replacements, cuts)
    if isinstance(new_turn.get("turn_summary"), str):
        fixed, _f = normalize_placeholder_text(new_turn["turn_summary"])
        new_turn["turn_summary"] = _apply_text_plan(fixed, replacements, [])
    renamed = {r["old"]: r["new"] for r in plan.get("renamed") or [] if isinstance(r, dict) and _s(r.get("old"))}
    dropped = {_s(n).lower() for n in plan.get("npcs_dropped") or []}
    rows: list[Any] = []
    for row in new_turn.get("npcs") or []:
        if isinstance(row, dict):
            name = _s(row.get("name"))
            if name.lower() in dropped:
                continue
            if name in renamed:
                row["name"] = renamed[name]
        rows.append(row)
    if isinstance(new_turn.get("npcs"), list):
        new_turn["npcs"] = rows
    return new_turn


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _empty_report() -> dict[str, Any]:
    return {"involved": None, "binding": None, "gates": [], "repairs": None, "version": VERSION}


def attach_report(turn: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    """Merge `part` into turn["_dsl"]["scene_cast"] (the one carrier the handoff keeps); returns the turn."""
    if not isinstance(turn, dict):
        return turn
    dsl = turn.setdefault("_dsl", {})
    if not isinstance(dsl, dict):
        dsl = {}
        turn["_dsl"] = dsl
    report = dsl.setdefault("scene_cast", _empty_report())
    if not isinstance(report, dict):
        report = _empty_report()
        dsl["scene_cast"] = report
    for key in ("involved", "binding", "gates", "repairs", "version"):
        report.setdefault(key, _empty_report()[key])
    for key, value in (part or {}).items():
        if key == "binding" and isinstance(value, dict) and isinstance(value.get("binding"), dict) and "turn" in value:
            value = value["binding"]  # a whole BindResult was handed in
        if key == "gates" and isinstance(value, dict) and isinstance(value.get("gates"), list):
            value = value["gates"]  # a whole VerifyResult was handed in
        report[key] = value
    report["version"] = VERSION
    return turn


def report_of(turn: dict[str, Any]) -> dict[str, Any] | None:
    """The scene_cast report under turn["_dsl"], or None."""
    if not isinstance(turn, dict):
        return None
    dsl = turn.get("_dsl")
    if not isinstance(dsl, dict):
        return None
    report = dsl.get("scene_cast")
    return report if isinstance(report, dict) else None
