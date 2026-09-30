"""Who is actually in the current fight, and what the player has seen them do.

A crowd is not a combatant list. Only a named target, someone who steps into
the fight, or someone already on the board is tracked. Health is copied from
the sheet when the sheet has it. A move the player does not know is stored as
what was seen, with no effectiveness attached.
"""
from __future__ import annotations

import json
import re
from typing import Any

SETTING_KEY = "active_encounter"

_JOIN_RE = re.compile(
    r"\b(joins the fight|steps into the fight|rushes in|draws on you|attacks you|turns on you)\b",
    re.IGNORECASE,
)
_MOVE_RE = re.compile(
    r"\b(?:uses|casts|unleashes|invokes|channels)\s+(?:the\s+)?([A-Za-z][^.,;\n]{2,48})",
    re.IGNORECASE,
)
_CROWD_RE = re.compile(r"\b(everyone|the crowd|the army|all of them|the mob)\b", re.IGNORECASE)


def empty_board() -> dict[str, Any]:
    return {
        "active": False,
        "updated_turn": 0,
        "closed_turn": 0,
        "outcome": "",
        "scale_note": "",
        "allies": [],
        "foes": [],
        "seen_moves": [],
    }


def _clean_name(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())[:80]


def _health_pair(row: dict[str, Any] | None) -> tuple[int | None, int | None, bool]:
    if not isinstance(row, dict):
        return None, None, False
    try:
        maximum = int(row.get("max_health") or 0)
    except (TypeError, ValueError):
        maximum = 0
    if maximum <= 0:
        return None, None, False
    try:
        current = int(row.get("health") if row.get("health") is not None else maximum)
    except (TypeError, ValueError):
        current = maximum
    return max(0, current), maximum, True


def _person(row: dict[str, Any], *, side: str) -> dict[str, Any]:
    health, maximum, known = _health_pair(row)
    person = {
        "code": str(row.get("code") or ""),
        "name": _clean_name(row.get("name") or "Unknown"),
        "side": side,
        "health": health,
        "max_health": maximum,
        "health_known": known,
        "role": "",
        "attitude": "",
        "detail": "",
        "notes": [],
        "abilities": [],
    }
    _apply_profile(person, row)
    return person


def _apply_profile(person: dict[str, Any], row: dict[str, Any] | None) -> None:
    if not isinstance(row, dict):
        return
    role = _clean_name(row.get("role"))
    attitude = _clean_name(row.get("attitude"))
    detail = _clean_name(row.get("summary") or row.get("detail") or "")[:200]
    if role:
        person["role"] = role
    if attitude:
        person["attitude"] = attitude
    if detail:
        person["detail"] = detail


def _find(people: list[dict[str, Any]], code: str, name: str) -> dict[str, Any] | None:
    code_key = str(code or "").strip().upper()
    name_key = _clean_name(name).lower()
    for person in people:
        if code_key and str(person.get("code") or "").upper() == code_key:
            return person
        if name_key and _clean_name(person.get("name")).lower() == name_key:
            return person
    return None


def _add_note(person: dict[str, Any], note: str) -> None:
    text = _clean_name(note)
    if not text:
        return
    notes = person.setdefault("notes", [])
    if any(str(item) == text for item in notes):
        return
    notes.append(text)
    if len(notes) > 6:
        del notes[:-6]


def _refresh_health(person: dict[str, Any], row: dict[str, Any] | None) -> None:
    health, maximum, known = _health_pair(row)
    person["health"] = health
    person["max_health"] = maximum
    person["health_known"] = known


def _named_in(text: str, name: str) -> bool:
    folded = _clean_name(name)
    if len(folded) < 3:
        return False
    return re.search(rf"\b{re.escape(folded)}\b", text, re.IGNORECASE) is not None


def _joined(text: str, name: str) -> bool:
    """True when this person's name sits next to a phrase that puts them in the fight."""
    folded = _clean_name(name)
    if len(folded) < 3 or not text.strip():
        return False
    for match in re.finditer(rf"\b{re.escape(folded)}\b", text, re.IGNORECASE):
        start = max(0, match.start() - 48)
        end = min(len(text), match.end() + 48)
        if _JOIN_RE.search(text[start:end]):
            return True
    return False


def _move_label(raw: str) -> str:
    label = _clean_name(raw)
    label = re.split(
        r"\s+(?:at|on|toward|towards|against|into|upon|and)\b",
        label,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return _clean_name(label)


def _match_known(label: str, catalog: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    key = _clean_name(label).lower()
    if not key:
        return None
    direct = catalog.get(key)
    if direct:
        return direct
    for name, item in catalog.items():
        if key.startswith(name + " "):
            return item
    return None


def _observe_moves(
    board: dict[str, Any],
    narration: str,
    known_abilities: list[dict[str, Any]],
) -> None:
    if not narration.strip():
        return
    catalog = {
        _clean_name(item.get("name")).lower(): item
        for item in known_abilities
        if _clean_name(item.get("name"))
    }
    people = list(board.get("allies") or []) + list(board.get("foes") or [])
    for sentence in re.split(r"(?<=[.!?])\s+", narration):
        match = _MOVE_RE.search(sentence)
        if not match:
            continue
        label = _move_label(match.group(1))
        if len(label) < 3:
            continue
        known = _match_known(label, catalog)
        if known:
            entry = {
                "name": _clean_name(known.get("name") or label),
                "known": True,
                "detail": _clean_name(known.get("description") or known.get("detail") or "")[:240],
                "effectiveness": _clean_name(known.get("effectiveness") or "Known ability. The sheet has the effect."),
            }
        else:
            entry = {
                "name": label,
                "known": False,
                "seen": _clean_name(sentence)[:240],
                "effectiveness": None,
            }
        owner = None
        for person in people:
            if _named_in(sentence, str(person.get("name") or "")):
                owner = person
                break
        if owner is None:
            seen = board.setdefault("seen_moves", [])
            prior = next((item for item in seen if str(item.get("name") or "").lower() == entry["name"].lower()), None)
            if prior is not None:
                if not entry["known"]:
                    prior["seen"] = entry.get("seen")
                continue
            seen.append(entry)
            if len(seen) > 8:
                del seen[:-8]
            continue
        abilities = owner.setdefault("abilities", [])
        prior = next(
            (
                item
                for item in abilities
                if str(item.get("name") or "").lower() == entry["name"].lower() and bool(item.get("known")) == bool(entry["known"])
            ),
            None,
        )
        if prior is not None:
            if not entry["known"]:
                prior["seen"] = entry.get("seen")
            continue
        abilities.append(entry)
        if len(abilities) > 8:
            del abilities[:-8]


def _learn_from_narration(board: dict[str, Any], narration: str) -> None:
    """Keep one new line of what was seen. Move sentences stay on the ability list."""
    if not narration.strip():
        return
    people = list(board.get("allies") or []) + list(board.get("foes") or [])
    seen: set[int] = set()
    for sentence in re.split(r"(?<=[.!?])\s+", narration):
        if _MOVE_RE.search(sentence):
            continue
        cleaned = _clean_name(sentence)[:180]
        if len(cleaned) < 8:
            continue
        for index, person in enumerate(people):
            if index in seen:
                continue
            if _named_in(sentence, str(person.get("name") or "")):
                _add_note(person, cleaned)
                seen.add(index)
                break


def merge_encounter(board: dict[str, Any] | None, packet: dict[str, Any]) -> dict[str, Any]:
    """Fold one turn into the fight list. Does not invent combatants."""
    current = empty_board()
    if isinstance(board, dict):
        current.update({key: board.get(key) for key in current})
        current["allies"] = [dict(item) for item in board.get("allies") or [] if isinstance(item, dict)]
        current["foes"] = [dict(item) for item in board.get("foes") or [] if isinstance(item, dict)]
        current["seen_moves"] = [dict(item) for item in board.get("seen_moves") or [] if isinstance(item, dict)]
        for person in current["allies"] + current["foes"]:
            person["notes"] = list(person.get("notes") or [])
            person["abilities"] = [dict(item) for item in person.get("abilities") or [] if isinstance(item, dict)]

    turn = int(packet.get("turn") or 0)
    combat = packet.get("combat") if isinstance(packet.get("combat"), dict) else {}
    status = str(combat.get("status") or "")
    fighting = status not in {"", "not_combat"}
    moved = bool(packet.get("moved"))
    narration = str(packet.get("narration") or "")
    player_input = str(packet.get("player_input") or "")
    text = f"{player_input}\n{narration}"

    if moved and current.get("active"):
        current["active"] = False
        current["closed_turn"] = turn
        current["outcome"] = "You left the place where the fight was."
        current["updated_turn"] = turn
        return current

    player = packet.get("player") if isinstance(packet.get("player"), dict) else {}
    if player.get("name"):
        ally = _find(current["allies"], "player", str(player.get("name") or ""))
        if ally is None:
            ally = _person({**player, "code": "player"}, side="ours")
            current["allies"].insert(0, ally)
        else:
            _refresh_health(ally, player)
            ally["name"] = _clean_name(player.get("name") or ally.get("name"))
            ally["code"] = "player"

    for member in packet.get("party") or []:
        if not isinstance(member, dict) or not member.get("name"):
            continue
        ally = _find(current["allies"], str(member.get("code") or ""), str(member.get("name") or ""))
        if ally is None:
            ally = _person(member, side="ours")
            current["allies"].append(ally)
        else:
            _refresh_health(ally, member)
            _apply_profile(ally, member)

    named: list[dict[str, Any]] = []
    target = packet.get("target") if isinstance(packet.get("target"), dict) else None
    if target and (target.get("code") or target.get("name")):
        named.append(target)
    for row in packet.get("named_foes") or []:
        if isinstance(row, dict) and (row.get("code") or row.get("name")):
            named.append(row)

    if fighting or current.get("active"):
        for row in named:
            if _find(current["allies"], str(row.get("code") or ""), str(row.get("name") or "")):
                continue
            foe = _find(current["foes"], str(row.get("code") or ""), str(row.get("name") or ""))
            if foe is None:
                foe = _person(row, side="theirs")
                current["foes"].append(foe)
            else:
                _refresh_health(foe, row)
                _apply_profile(foe, row)

        for row in packet.get("present") or []:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "")
            if not _joined(text, name):
                continue
            if _find(current["allies"], str(row.get("code") or ""), name):
                continue
            foe = _find(current["foes"], str(row.get("code") or ""), name)
            if foe is None:
                foe = _person(row, side="theirs")
                _add_note(foe, "Stepped into the fight.")
                current["foes"].append(foe)
            else:
                _refresh_health(foe, row)
                _apply_profile(foe, row)

    ally_codes = {str(person.get("code") or "").upper() for person in current["allies"] if person.get("code")}
    ally_names = {_clean_name(person.get("name")).lower() for person in current["allies"] if person.get("name")}
    current["foes"] = [
        foe
        for foe in current["foes"]
        if str(foe.get("code") or "").upper() not in ally_codes
        and _clean_name(foe.get("name")).lower() not in ally_names
    ]

    if fighting and (current["foes"] or status == "needs_target"):
        current["active"] = True
        current["outcome"] = ""
        current["closed_turn"] = 0

    resolution = combat.get("resolution") if isinstance(combat.get("resolution"), dict) else {}
    target_code = str((target or {}).get("code") or "")
    target_name = str((target or {}).get("name") or "")
    foe = _find(current["foes"], target_code, target_name) if (target_code or target_name) else None
    if foe is not None and resolution:
        outcome = str(resolution.get("outcome") or "")
        damage = resolution.get("damage")
        after = resolution.get("target_health_after")
        if outcome:
            detail = outcome.replace("_", " ")
            if damage is not None:
                detail += f", {damage} damage"
            if after is not None and foe.get("health_known"):
                detail += f", health now {after}"
            _add_note(foe, detail[:160])
        if foe.get("health_known") and after is not None:
            try:
                foe["health"] = max(0, int(after))
            except (TypeError, ValueError):
                pass

    for row in packet.get("sheet") or []:
        if not isinstance(row, dict):
            continue
        person = _find(current["allies"], str(row.get("code") or ""), str(row.get("name") or ""))
        if person is None:
            person = _find(current["foes"], str(row.get("code") or ""), str(row.get("name") or ""))
        if person is not None:
            _refresh_health(person, row)
            _apply_profile(person, row)

    if current.get("active"):
        _learn_from_narration(current, narration)
        _observe_moves(current, narration, list(packet.get("known_abilities") or []))
        if _CROWD_RE.search(player_input) or _CROWD_RE.search(narration):
            current["scale_note"] = "Only people you are actually fighting are listed. The rest of the crowd stays off this board."
        else:
            current["scale_note"] = ""
        if status == "needs_target" and not current["foes"]:
            current["outcome"] = "You swung, and no one person is locked as the target yet."
        elif all(person.get("health_known") and int(person.get("health") or 0) <= 0 for person in current["foes"]) and current["foes"]:
            current["active"] = False
            current["closed_turn"] = turn
            current["outcome"] = "The other side cannot keep fighting."

    current["updated_turn"] = turn
    if not current.get("active") and not current.get("closed_turn"):
        return empty_board() | {"updated_turn": turn}
    return current


def load_encounter(conn) -> dict[str, Any]:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (SETTING_KEY,)).fetchone()
    if row is None:
        return empty_board()
    try:
        parsed = json.loads(row["value"])
    except (TypeError, json.JSONDecodeError):
        return empty_board()
    return parsed if isinstance(parsed, dict) else empty_board()


def save_encounter(conn, board: dict[str, Any]) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (SETTING_KEY, json.dumps(board, ensure_ascii=True)),
    )


def record_encounter_turn(
    conn,
    *,
    turn: int,
    player_input: str,
    narration: str,
    combat: dict[str, Any] | None,
    moved: bool,
) -> dict[str, Any]:
    """Read the sheet, fold this turn in, and store the board."""
    player_row = conn.execute("SELECT name, health, max_health FROM player WHERE id = 1").fetchone()
    player = dict(player_row) if player_row is not None else {}
    present = [
        dict(row)
        for row in conn.execute(
            """
            SELECT n.code, n.name, n.health, n.max_health, n.role, n.attitude, n.summary
            FROM npcs n
            JOIN player p ON p.current_location_id = n.location_id
            WHERE p.id = 1
            """
        ).fetchall()
    ]
    party: list[dict[str, Any]] = []
    try:
        party = [
            dict(row)
            for row in conn.execute(
                """
                SELECT n.code, n.name, n.health, n.max_health, n.role, n.attitude, n.summary
                FROM party_members m
                JOIN npcs n ON n.id = m.npc_id
                """
            ).fetchall()
        ]
    except Exception:
        party = []
    abilities = []
    try:
        abilities = [
            {"name": row["name"], "description": row["description"]}
            for row in conn.execute("SELECT name, description FROM abilities").fetchall()
        ]
    except Exception:
        abilities = []

    combat = combat if isinstance(combat, dict) else {}
    target = combat.get("target") if isinstance(combat.get("target"), dict) else None
    target_row = None
    if target:
        code = str(target.get("code") or "").strip()
        name = _clean_name(target.get("name"))
        for row in present:
            if code and str(row.get("code") or "").upper() == code.upper():
                target_row = row
                break
            if name and _clean_name(row.get("name")).lower() == name.lower():
                target_row = row
                break
        if target_row is None and (code or name):
            target_row = {"code": code, "name": name or code, "health": None, "max_health": 0}

    # A name in the sentence is not a combatant. Joiners are detected from the
    # wording. named_foes stays empty so a bystander who is only mentioned is
    # left off the board.
    sheet = [player] + present + party
    board = merge_encounter(
        load_encounter(conn),
        {
            "turn": turn,
            "combat": combat,
            "moved": moved,
            "player": player,
            "party": party,
            "present": present,
            "target": target_row,
            "named_foes": [],
            "known_abilities": abilities,
            "narration": narration,
            "player_input": player_input,
            "sheet": sheet,
        },
    )
    save_encounter(conn, board)
    return board
