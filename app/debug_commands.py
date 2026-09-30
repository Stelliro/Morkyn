"""Slash commands. /help is local. The rest can edit the world.

A command is not a story turn. It does not advance time.
After the command and any @ link, the rest of the line is an instruction
the model follows. Edit COMMAND_SYSTEM if you want that looser or stricter.

Examples:
  /item @Inon_slip_shoes make the soles louder but keep them black
  /npc @Cmarta make her wary, still the one talking
  /teleport @Llow_gate
  /godmode on
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.db import connect
from app.llm import LlmError, _chat_json
from app.world import (
    _active_scene,
    _mention_catalog,
    _pick_mention,
    _set_setting,
    _settings,
    get_state,
)

HELP_TEXT = """Linking
Type @ and a letter, then search. Or type a bare name if it is unambiguous.
@C character   @I item   @L place   @S skill   @A ability   @E event
Drag a highlighted name from the narration into this box.
Ask, no turn is in Optional, next to Help. Type a question in the box first. It looks something up and does not take a turn. An empty box says to type a question first. The answer under the scene is marked Ask, no turn.

Commands
These change the character, another character, or the place. They do not play a scene.
Put a link or a name first, then a statement for the model:
  /item @Inon_slip_shoes make the soles louder but keep them black
  /npc @Cmarta_venn make her wary and leave her as the one talking
  /teleport @Llow_gate put me just inside the arch

/help                         this list
/godmode [on|off]             damage does not stick when on
/teleport <place or @L>       move there now
/stat <health|max_health|gold|xp|level> <number>
/item <@I or name> <what to change>
/npc <@C or name> <what to change>
/cast interacting|present|off <@C or name>
/give <item name> [quantity]
/reveal x y [radius] [label]   open cells the player has not walked
/mark x y <label>               pin a walked or heard-about cell
/mark here <label>              pin the cell you are standing on
""".strip()

COMMAND_SYSTEM = """You apply one debug command in an RPG. You do not narrate a scene and you do not advance time.

You receive the command, the matched records, and the player's instruction.
Change only what the instruction asks. Keep unrelated fields empty.
Return only JSON:
{
  "note": "one short sentence confirming the change",
  "godmode": null,
  "player": {"health": null, "max_health": null, "gold": null, "xp": null, "level": null},
  "move_to_code": "",
  "item": {"code": "", "name": "", "description": ""},
  "npc": {"code": "", "summary": "", "attitude": "", "personality": ""},
  "give": {"name": "", "quantity": 0, "description": ""},
  "cast": {"present": [], "interacting": [], "off": []}
}
Use null or "" or [] when you are not changing that part.
godmode is true, false, or null.
Do not invent a new plot. A request to edit an item may change its description, name, or obvious physical traits.
"""

_STAT_FIELDS = {"health", "max_health", "gold", "xp", "level"}


def is_command(text: str) -> bool:
    return str(text or "").lstrip().startswith("/")


def _split(text: str) -> tuple[str, str]:
    body = str(text or "").strip()
    if body.startswith("/"):
        body = body[1:]
    head, _, rest = body.partition(" ")
    return head.strip().lower(), rest.strip()


def _subject(context: dict[str, Any], text: str, kinds: str) -> dict[str, str] | None:
    rows = _mention_catalog(context)
    match = re.search(rf"@([{kinds}])([a-z0-9_]+)", text or "", re.IGNORECASE)
    if match:
        return _pick_mention(rows, match.group(1), match.group(2))
    lowered = str(text or "").lower()
    hits = []
    for row in rows:
        if row.get("kind") not in set(kinds):
            continue
        name = str(row.get("name") or "")
        if name and name.lower() in lowered:
            hits.append(row)
    if len(hits) == 1:
        return hits[0]
    return None


def _note(text: str, *, refresh: bool = False, command: str = "") -> dict[str, Any]:
    return {
        "ok": True,
        "command": command,
        "answer": text,
        "refresh": refresh,
        "advanced_turn": False,
    }


def _journal(command: str, answer: str) -> None:
    with connect() as conn:
        row = conn.execute("SELECT value FROM pacing WHERE key = 'turn'").fetchone()
        turn = int(row["value"]) if row else 0
        conn.execute(
            "INSERT INTO journal (turn, kind, content) VALUES (?, ?, ?)",
            (turn, "debug", f"{command[:240]}\n{answer[:800]}"),
        )


def _set_godmode(on: bool) -> None:
    with connect() as conn:
        _set_setting(conn, "debug_godmode", bool(on))


def _godmode_on() -> bool:
    with connect() as conn:
        return _settings(conn).get("debug_godmode") in (True, "true", "1", 1)


def _set_player_fields(fields: dict[str, int]) -> None:
    if not fields:
        return
    with connect() as conn:
        player = conn.execute("SELECT * FROM player WHERE id = 1").fetchone()
        if not player:
            return
        health = int(fields.get("health", player["health"]))
        max_health = int(fields.get("max_health", player["max_health"]))
        max_health = max(1, min(999, max_health))
        health = max(0, min(max_health, health))
        level = max(1, min(100, int(fields.get("level", player["level"]))))
        xp = max(0, min(1_000_000, int(fields.get("xp", player["xp"]))))
        gold = max(0, min(1_000_000, int(fields.get("gold", player["gold"]))))
        conn.execute(
            "UPDATE player SET health = ?, max_health = ?, level = ?, xp = ?, gold = ? WHERE id = 1",
            (health, max_health, level, xp, gold),
        )


def _teleport_to(name_or_code: str) -> str | None:
    target = str(name_or_code or "").strip()
    if not target:
        return None
    with connect() as conn:
        code = target.upper()
        row = conn.execute("SELECT id, name FROM locations WHERE code = ?", (code,)).fetchone()
        if not row:
            row = conn.execute("SELECT id, name FROM locations WHERE name = ? COLLATE NOCASE", (target,)).fetchone()
        if not row:
            return None
        conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (int(row["id"]),))
        return str(row["name"])


def _apply_patch(patch: dict[str, Any]) -> list[str]:
    done: list[str] = []
    if patch.get("godmode") is True:
        _set_godmode(True)
        done.append("godmode on")
    elif patch.get("godmode") is False:
        _set_godmode(False)
        done.append("godmode off")
    player = patch.get("player") if isinstance(patch.get("player"), dict) else {}
    numeric = {}
    for key in _STAT_FIELDS:
        if player.get(key) is None or player.get(key) == "":
            continue
        try:
            numeric[key] = int(player[key])
        except (TypeError, ValueError):
            continue
    if numeric:
        _set_player_fields(numeric)
        done.append("stats " + ", ".join(f"{key}={value}" for key, value in numeric.items()))
    move_code = str(patch.get("move_to_code") or "").strip()
    if move_code:
        moved = _teleport_to(move_code)
        done.append(f"moved to {moved}" if moved else f"no place matched {move_code}")
    item = patch.get("item") if isinstance(patch.get("item"), dict) else {}
    if item.get("code") and (item.get("description") or item.get("name")):
        with connect() as conn:
            if item.get("description"):
                conn.execute(
                    "UPDATE inventory SET description = ? WHERE code = ?",
                    (str(item["description"])[:900], str(item["code"]).upper()),
                )
            if item.get("name"):
                conn.execute(
                    "UPDATE inventory SET name = ? WHERE code = ?",
                    (str(item["name"])[:120], str(item["code"]).upper()),
                )
        done.append(f"item {item.get('code')}")
    npc = patch.get("npc") if isinstance(patch.get("npc"), dict) else {}
    if npc.get("code"):
        with connect() as conn:
            row = conn.execute("SELECT summary, attitude, personality FROM npcs WHERE code = ?", (str(npc["code"]).upper(),)).fetchone()
            if row:
                conn.execute(
                    "UPDATE npcs SET summary = ?, attitude = ?, personality = ? WHERE code = ?",
                    (
                        str(npc.get("summary") or row["summary"] or "")[:1400],
                        str(npc.get("attitude") or row["attitude"] or "")[:40],
                        str(npc.get("personality") or row["personality"] or "")[:700],
                        str(npc["code"]).upper(),
                    ),
                )
                done.append(f"npc {npc.get('code')}")
    give = patch.get("give") if isinstance(patch.get("give"), dict) else {}
    if str(give.get("name") or "").strip():
        qty = max(1, min(99, int(give.get("quantity") or 1)))
        with connect() as conn:
            existing = conn.execute(
                "SELECT id, quantity FROM inventory WHERE name = ? COLLATE NOCASE",
                (str(give["name"]).strip(),),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE inventory SET quantity = ? WHERE id = ?",
                    (int(existing["quantity"]) + qty, existing["id"]),
                )
            else:
                conn.execute(
                    "INSERT INTO inventory (name, description, quantity) VALUES (?, ?, ?)",
                    (str(give["name"]).strip()[:120], str(give.get("description") or "")[:900], qty),
                )
        done.append(f"gave {qty} {give.get('name')}")
    cast = patch.get("cast") if isinstance(patch.get("cast"), dict) else {}
    if any(cast.get(slot) for slot in ("present", "interacting", "off")):
        from app.world import _apply_scene_cast

        with connect() as conn:
            _apply_scene_cast(conn, cast)
        done.append("scene cast")
    return done


def _llm_patch(command: str, instruction: str, context: dict[str, Any], subject: dict[str, str] | None) -> dict[str, Any]:
    player = context.get("player") or {}
    location = context.get("current_location") or {}
    packet = {
        "command": command,
        "instruction": instruction,
        "subject": subject,
        "player": {
            "name": player.get("name"),
            "health": player.get("health"),
            "max_health": player.get("max_health"),
            "gold": player.get("gold"),
            "xp": player.get("xp"),
            "level": player.get("level"),
        },
        "here": {"name": location.get("name"), "code": location.get("code")},
        "scene": _active_scene(context),
    }
    return _chat_json(COMMAND_SYSTEM, json.dumps(packet, ensure_ascii=True), timeout=45, phase="debug_command", max_tokens=400)


def handle_command(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    name, rest = _split(raw)
    if not name:
        return {"ok": False, "error": "Empty command. Type /help.", "advanced_turn": False}
    if name in {"help", "?"} or raw.strip() == "/help":
        return _note(HELP_TEXT, command="/help")
    if name in {"mark", "reveal"}:
        from app.local_intel import run_map_command

        return run_map_command(name, rest)

    context = get_state(include_hidden=True)
    if name == "godmode" and rest.lower() in {"", "on", "off", "toggle"}:
        turn_on = rest.lower() != "off"
        if rest.lower() == "toggle":
            turn_on = not _godmode_on()
        elif rest.lower() == "":
            turn_on = not _godmode_on()
        _set_godmode(turn_on)
        answer = "Godmode is on. Damage will not stick." if turn_on else "Godmode is off."
        _journal(raw, answer)
        return _note(answer, refresh=True, command=raw)

    if name == "stat":
        parts = rest.split()
        if len(parts) >= 2 and parts[0].lower() in _STAT_FIELDS and re.fullmatch(r"-?\d+", parts[1]):
            _set_player_fields({parts[0].lower(): int(parts[1])})
            answer = f"{parts[0].lower()} set to {int(parts[1])}."
            _journal(raw, answer)
            return _note(answer, refresh=True, command=raw)

    if name == "teleport" and rest and not re.search(r"\b(and|then|but|so|make|put|leave)\b", rest, re.I):
        target = re.sub(r"^@L", "", rest, flags=re.I).replace("_", " ").strip()
        subject = _subject(context, rest, "L")
        if subject and subject.get("name"):
            target = subject["name"]
        moved = _teleport_to(target)
        if moved:
            answer = f"You are at {moved}."
            _journal(raw, answer)
            return _note(answer, refresh=True, command=raw)

    subject = None
    if name == "item":
        subject = _subject(context, rest, "I")
    elif name in {"npc", "cast"}:
        subject = _subject(context, rest, "C")
    elif name == "teleport":
        subject = _subject(context, rest, "L")
    try:
        patch = _llm_patch(name, rest or raw, context, subject)
    except LlmError as exc:
        return {"ok": False, "error": str(exc), "advanced_turn": False}
    if not isinstance(patch, dict):
        return {"ok": False, "error": "The command did not return a change.", "advanced_turn": False}
    done = _apply_patch(patch)
    answer = str(patch.get("note") or "").strip() or ("; ".join(done) if done else "Nothing changed.")
    _journal(raw, answer)
    return _note(answer, refresh=bool(done), command=raw)
