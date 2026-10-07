"""Directions, map marks, notice boards, and the in-game quest clock.

The engine owns coordinates. A model may repeat the wording this module
supplies; it does not pick the cell. Heard-about cells live in ``revealed``,
separate from cells the player has walked. A mark is refused on any cell that
is in neither set.

Shop stalls are derived from a district's seed. They are not stored as tiles.
"Closest" is the nearest matching stall. A district question uses that ward's
middle. A far answer is pulled back toward the player, and only that told
patch is opened.

Black-market answers fail closed. A shady person, a bribe, or a rare slip from
someone who already trusts the player can still give one, in indirect wording.
Forbidden magic counts as that trade except in far-future and space-opera
settings. Songs are only a contraband category.

Personal quests are rolled when a person is met. The chance is not the same
for everyone. An offer does not appear on the day its month starts. Each later
day of a 30-day month can post it. Once posted, each day can take it down
again, and that lapse does nothing to a quest the player already accepted.
Guild halls and boards are a separate percent, placed only on settlement cells.
"""
from __future__ import annotations

import json
import random
import re
from typing import Any

from app.world_scale import clamp_int, mix_hash, normalize_density, theme_allows_slavery

QUEST_MONTH = 30
BRIBE_GOLD = 2
REVEAL_RADIUS = 1
_ALWAYS_FORBIDDEN = frozenset({"drugs", "slavery", "songs"})
_SHADY_RE = re.compile(
    r"\b(thief|smuggler|fence|criminal|cult|cultist|beggar|spy|rogue|bandit|fixer|night)\b"
    r"|black[- ]market",
    re.IGNORECASE,
)
_HOSTILE = frozenset({
    "hostile", "unfriendly", "wary", "suspicious", "angry", "cold", "hateful", "enemy",
})
_BRIBE_RE = re.compile(
    r"\b(bribe|slip\s+(?:him|her|them)|pay for the information|offer(?:s|ed|ing)? coin|hand(?:s|ed|ing)? over coin)\b",
    re.IGNORECASE,
)
_ACCEPT_RE = re.compile(
    r"\b(?:i(?:'ll| will) (?:take|do)|i accept|take|accept)\b(?:\s+\w+){0,4}\s+\b(?:quest|job|notice|errand|contract|work)\b",
    re.IGNORECASE,
)
_GOOD_PATTERNS = (
    ("slavery", r"\b(slave|slavery|thralls?)\b"),
    ("drugs", r"\b(drugs?|narcotics?)\b"),
    ("songs", r"\b(songs?|sheet music)\b"),
    ("magic", r"\b(magic|enchant\w*|spell\w*|arcane)\b"),
    ("food", r"\b(food|bread|grain|meals?|rations?|grocer\w*)\b"),
    ("weapons", r"\b(weapons?|swords?|arms|armou?r)\b"),
    ("tools", r"\b(tools?|smith\w*|forges?)\b"),
    ("books", r"\b(books?|tomes?|scrolls?)\b"),
    ("games", r"\b(games?|dice|cards)\b"),
    ("cloth", r"\b(cloth|clothes|clothing|tailor)\b"),
    ("guild", r"\bguilds?\b"),
    ("notice", r"\b(?:pinboards?|notice boards?|quest boards?|job boards?|poster boards?|bulletin)\b"),
    ("black_market", r"\bblack markets?\b"),
)
_NOTICE_BANDS = {
    "post_collapse": (4, 12),
    "medieval": (20, 45),
    "industrial": (24, 50),
    "far_future": (15, 40),
    "space_opera": (8, 24),
    "ancient": (12, 30),
    "mixed": (15, 35),
    "timeless": (6, 16),
}
_NOTICE_LABELS = {
    "guild": "Guild hall",
    "pinboard": "Notice board",
    "quest_board": "Quest board",
}
_OFFERS = (
    ("A parcel to carry", "Carry a sealed parcel to someone in this town and bring back their word."),
    ("Word of a missing crate", "A stall is one crate short. Find it and bring it back."),
    ("A name to ask after", "Ask after a person who left at dawn. Bring back what you hear."),
    ("The watch's errand", "Take a message to a gate and bring the answer back."),
    ("A debt of bread", "Someone is owed a sack of food. See that it reaches them."),
)
_QUEST_CLOCKS_SQL = """
CREATE TABLE IF NOT EXISTS quest_clocks (
    subject_key TEXT PRIMARY KEY,
    offers INTEGER NOT NULL,
    chance INTEGER NOT NULL,
    phase TEXT NOT NULL,
    phase_day INTEGER NOT NULL,
    quest_id INTEGER NOT NULL DEFAULT 0,
    last_day INTEGER NOT NULL DEFAULT 0
)
"""


def _text_salt(text: str) -> int:
    value = 0
    for ch in str(text or ""):
        value = (value * 33 + ord(ch)) & 0xFFFFFFFF
    return value or 1


def _norm_question(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").lower()).strip()


def magic_is_contraband(theme: str) -> bool:
    """Far-future and space-opera settings sell magic like any other craft."""
    return str(theme or "") not in {"far_future", "space_opera"}


def contraband_goods(theme: str, slavery: bool) -> tuple[str, ...]:
    goods = ["books", "food", "weapons", "games", "songs", "drugs"]
    if magic_is_contraband(theme):
        goods.append("magic")
    if slavery:
        goods.append("slavery")
    return tuple(goods)


def parse_direction_question(text: str) -> dict[str, Any] | None:
    """Return the ask, or None when the line is not a where-question."""
    low = _norm_question(text)
    if not low or not re.search(r"\b(where|closest|nearest|buy|sell|district)\b", low):
        return None
    good = "general"
    found = False
    for name, pattern in _GOOD_PATTERNS:
        if re.search(pattern, low):
            good = name
            found = True
            break
    if not found and not re.search(r"\b(shop|stall|market|district|store|buy|sell|board)\b", low):
        return None
    specificity = "closest" if re.search(r"\b(closest|nearest)\b", low) else "area"
    asks_forbidden = bool(re.search(
        r"\b(black markets?|under the table|illegal|illicit|contraband|slaves?|slavery)\b",
        low,
    ))
    return {
        "specificity": specificity,
        "good": good,
        "asks_forbidden": asks_forbidden,
        "bribe": bool(_BRIBE_RE.search(low)),
        "text": low,
    }


def _player_cell(world: dict[str, Any], player_xy: tuple[int, int] | None) -> tuple[int, int]:
    if player_xy is not None:
        return int(player_xy[0]), int(player_xy[1])
    player = world.get("player") or {}
    return int(player.get("x") or 0), int(player.get("y") or 0)


def _indexed_cell(world: dict[str, Any], x: int, y: int) -> dict[str, Any] | None:
    index = world.get("cell_index")
    if not isinstance(index, dict):
        from app.world_scale import index_cities

        index = index_cities(world.get("cities") or [])
        world["cell_index"] = index
    found = index.get(f"{int(x)},{int(y)}")
    if not isinstance(found, dict):
        return None
    cell = found.get("cell")
    return cell if isinstance(cell, dict) else None


def _player_fine(world: dict[str, Any], px: int, py: int) -> tuple[int, int]:
    cell = _indexed_cell(world, px, py)
    if not cell:
        return 0, 0
    side = max(1, int(cell.get("side") or 1))
    return side // 2, side // 2


def point_distance(
    px: int, py: int, pfx: int, pfy: int, tx: int, ty: int, tfx: int, tfy: int,
) -> tuple[int, int]:
    """World Chebyshev, then fine Chebyshev when both points share a world cell."""
    world = max(abs(int(tx) - int(px)), abs(int(ty) - int(py)))
    if world == 0:
        return world, max(abs(int(tfx) - int(pfx)), abs(int(tfy) - int(pfy)))
    return world, 0


def compass_word(dx: int, dy: int) -> str:
    """Positive y is south, matching the walker."""
    ns = "north" if dy < 0 else ("south" if dy > 0 else "")
    ew = "east" if dx > 0 else ("west" if dx < 0 else "")
    if ns and ew:
        return ns + ew
    return ns or ew or "here"


def blur_cell(px: int, py: int, tx: int, ty: int) -> tuple[int, int, bool]:
    """A near place is named exactly. A far place stops short of the true cell."""
    dx, dy = int(tx) - int(px), int(ty) - int(py)
    dist = max(abs(dx), abs(dy))
    if dist <= 4:
        return int(tx), int(ty), True
    pull = min(dist // 2, dist - 1)
    remain = dist - pull
    told_x = int(px) + int(round(dx * remain / dist))
    told_y = int(py) + int(round(dy * remain / dist))
    return told_x, told_y, False


def _public_pool(district: dict[str, Any], theme: str) -> list[str]:
    kind = str(district.get("type") or "")
    perms = set(district.get("permissions") or [])
    pool: list[str] = []
    if kind == "food" or "food" in perms:
        pool.append("food")
    if "weapons" in perms or kind == "craft":
        pool.append("weapons")
    if "tools" in perms or "workshops" in perms or kind == "craft":
        pool.append("tools")
    if "cloth" in perms:
        pool.append("cloth")
    if kind == "shopping":
        pool.extend(("books", "games", "general"))
    if not magic_is_contraband(theme) and kind in {"shopping", "craft"}:
        pool.append("magic")
    if not pool:
        pool.append("general")
    return list(dict.fromkeys(pool))


def stalls_for_district(
    cell: dict[str, Any],
    district: dict[str, Any],
    *,
    theme: str,
    slavery: bool,
) -> list[dict[str, Any]]:
    """Reproducible stalls. When there are at least three, about a third are filler."""
    count = int(district.get("shop_count") or 0)
    if count <= 0:
        return []
    side = max(1, int(cell.get("side") or 1))
    seed = int(cell.get("seed") or 1)
    anchor = district.get("anchor") or [0, 0]
    ax, ay = int(anchor[0]), int(anchor[1])
    kind = str(district.get("type") or "")
    salt = _text_salt(str(district.get("id") or kind))
    perms = set(district.get("permissions") or [])
    shady = kind == "black_market" or "black_market" in perms
    if shady:
        pool = list(contraband_goods(theme, slavery or "slavery" in perms))
    else:
        pool = _public_pool(district, theme)
    stalls = []
    for index in range(count):
        filler = count >= 3 and index % 3 == 2
        h = mix_hash(seed, index, salt)
        fine_x = (ax + 2 + index * 3 + (h % 5)) % side
        fine_y = (ay + 1 + index * 5 + ((h >> 8) % 7)) % side
        good = "general" if filler else pool[index % len(pool)]
        stalls.append(
            {
                "x": int(cell.get("x") or 0),
                "y": int(cell.get("y") or 0),
                "fine_x": fine_x,
                "fine_y": fine_y,
                "good": good,
                "filler": filler,
                "district_id": str(district.get("id") or ""),
                "district_type": kind,
                "district_name": str(district.get("name") or ""),
                "label": str(district.get("label") or kind),
                "anchor_x": ax,
                "anchor_y": ay,
            }
        )
    return stalls


def _district_serves(district: dict[str, Any], good: str, forbidden: bool) -> bool:
    kind = str(district.get("type") or "")
    perms = set(district.get("permissions") or [])
    shady = kind == "black_market" or "black_market" in perms
    if forbidden:
        return shady
    if shady or kind in {"street", "government", "military", "temple", "residential"}:
        return False
    if good == "general":
        return kind in {"shopping", "food", "craft"}
    if good == "food":
        return kind in {"food", "shopping", "craft"}
    if good == "magic":
        return kind in {"shopping", "craft"}
    if good == "weapons":
        return kind in {"shopping", "craft"}
    if good == "tools":
        return kind in {"craft", "shopping"}
    if good in {"books", "games", "cloth"}:
        return kind == "shopping"
    return kind in {"shopping", "food", "craft"}


def _type_rank(kind: str, good: str) -> int:
    order = {
        "food": {"food": 0, "shopping": 1, "craft": 2},
        "magic": {"shopping": 0, "craft": 1},
        "weapons": {"craft": 0, "shopping": 1},
        "tools": {"craft": 0, "shopping": 1},
    }.get(good)
    if not order:
        return 0 if kind == "shopping" else 1
    return order.get(kind, 5)


def _iter_city_cells(world: dict[str, Any]):
    for city in world.get("cities") or []:
        if not isinstance(city, dict):
            continue
        for cell in city.get("cells") or []:
            if isinstance(cell, dict):
                yield city, cell


def _anchor_target(cell: dict[str, Any], district: dict[str, Any]) -> dict[str, Any]:
    anchor = district.get("anchor") or [0, 0]
    return {
        "x": int(cell.get("x") or 0),
        "y": int(cell.get("y") or 0),
        "fine_x": int(anchor[0]),
        "fine_y": int(anchor[1]),
        "good": "",
        "filler": False,
        "district_id": str(district.get("id") or ""),
        "district_type": str(district.get("type") or ""),
        "district_name": str(district.get("name") or ""),
        "label": str(district.get("label") or district.get("type") or "place"),
        "kind": "district",
    }


def _stall_target(stall: dict[str, Any]) -> dict[str, Any]:
    target = dict(stall)
    target["kind"] = "stall"
    return target


def _notice_targets(world: dict[str, Any], good: str) -> list[dict[str, Any]]:
    wanted = {"guild"} if good == "guild" else {"pinboard", "quest_board"}
    found = []
    for _city, cell in _iter_city_cells(world):
        for notice in cell.get("notices") or []:
            if not isinstance(notice, dict):
                continue
            if str(notice.get("kind") or "") not in wanted:
                continue
            found.append(
                {
                    "x": int(notice.get("x") or cell.get("x") or 0),
                    "y": int(notice.get("y") or cell.get("y") or 0),
                    "fine_x": int(notice.get("fine_x") or 0),
                    "fine_y": int(notice.get("fine_y") or 0),
                    "good": good,
                    "filler": False,
                    "district_id": str(notice.get("id") or ""),
                    "district_type": str(notice.get("kind") or ""),
                    "district_name": str(notice.get("label") or ""),
                    "label": str(notice.get("label") or good),
                    "kind": "notice",
                    "far": bool(notice.get("far")),
                }
            )
    return found


def _shop_targets(world: dict[str, Any], good: str, forbidden: bool, specificity: str) -> list[dict[str, Any]]:
    theme = str(world.get("theme") or "")
    slavery = bool(world.get("allows_slavery")) or theme_allows_slavery(theme)
    targets: list[dict[str, Any]] = []
    for _city, cell in _iter_city_cells(world):
        for district in cell.get("districts") or []:
            if not isinstance(district, dict) or not _district_serves(district, good, forbidden):
                continue
            if specificity == "area" or int(district.get("shop_count") or 0) <= 0:
                target = _anchor_target(cell, district)
                target["rank"] = _type_rank(str(district.get("type") or ""), good)
                targets.append(target)
                if specificity == "area":
                    continue
            stalls = stalls_for_district(cell, district, theme=theme, slavery=slavery)
            matched = [
                stall for stall in stalls
                if not stall["filler"] and (good == "general" or good == "black_market" or stall["good"] == good)
            ]
            if not matched:
                fallback = _anchor_target(cell, district)
                fallback["rank"] = _type_rank(str(district.get("type") or ""), good)
                targets.append(fallback)
                continue
            for stall in matched:
                target = _stall_target(stall)
                target["rank"] = _type_rank(str(district.get("type") or ""), good)
                targets.append(target)
    return targets


def _good_phrase(good: str) -> str:
    return {
        "food": "food shop",
        "magic": "magic shop",
        "weapons": "weapon shop",
        "tools": "tool shop",
        "books": "book shop",
        "games": "game shop",
        "cloth": "cloth shop",
        "songs": "song seller",
        "drugs": "quiet seller",
        "slavery": "quiet trade",
        "general": "shop",
        "guild": "guild hall",
        "notice": "notice board",
        "black_market": "night market",
    }.get(good, "shop")


def _wording(
    *,
    told: bool,
    forbidden: bool,
    specificity: str,
    precise: bool,
    good: str,
    label: str,
    name: str,
    compass: str,
) -> str:
    if not told:
        return ""
    if forbidden:
        if compass == "here":
            return "A quiet stall in this part of town deals in that. It does not keep a sign."
        return f"A quiet stall {compass} of here deals in that. It does not keep a sign."
    place = str(name or label or "that ward")
    if specificity == "area" or good in {"guild", "notice", "black_market"}:
        if good == "guild":
            noun = "guild hall"
        elif good == "notice":
            noun = "notice board"
        elif good == "black_market":
            noun = "night market"
        else:
            noun = f"{label or good} district".replace(" district district", " district")
        if compass == "here":
            return f"The {noun} is around the middle of {place}, in this part of town."
        return f"The {noun} is {compass} of here, around the middle of {place}."
    phrase = _good_phrase(good)
    if precise:
        if compass == "here":
            return f"The closest {phrase} is here, at {place}."
        return f"The closest {phrase} is {compass} of here, at {place}."
    if compass == "here":
        return f"There is a {phrase} in this part of town. I would start around {place}."
    return f"There is a {phrase} {compass} of here. I would start around {place}, not on the doorstep."


def is_shady(role: str) -> bool:
    return bool(_SHADY_RE.search(str(role or "")))


def will_tell(
    npc: dict[str, Any] | None,
    *,
    forbidden: bool,
    roll: int,
    check_success: bool,
    bribe: bool,
) -> tuple[bool, str]:
    """Public news is given freely by a willing person. Forbidden news is not."""
    if not npc:
        return False, "nobody"
    role = str(npc.get("role") or "")
    attitude = str(npc.get("attitude") or "neutral").strip().lower()
    trust = int(npc.get("trust") or 0)
    roll = int(roll) % 100
    if not forbidden:
        if attitude not in _HOSTILE:
            return True, "willing"
        if check_success:
            return True, "check"
        if bribe:
            return True, "bribe"
        if roll < 25:
            return True, "willing"
        return False, "refused"
    shady = is_shady(role)
    if shady and (roll < 70 or bribe or trust >= 40):
        if bribe and roll >= 70 and trust < 40:
            return True, "bribe"
        return True, "shady"
    if bribe and roll < 35:
        return True, "bribe"
    if trust >= 50 and roll < 8:
        return True, "slip"
    return False, "refused"


def stand_in_check(npc_id: int, day: int, question: str, trust: int) -> bool:
    """A local d20, so the prompt and the saved reveal use the same success."""
    roll = mix_hash(int(day), int(npc_id), _text_salt(question), 3) % 20 + 1
    bonus = max(-2, min(6, int(trust) // 10))
    return roll + bonus >= 12


def direction_roll(day: int, npc_id: int, question: str) -> int:
    return mix_hash(int(day), int(npc_id), _text_salt(question), 9) % 100


def resolve_direction(
    world: dict[str, Any],
    question: str,
    npc: dict[str, Any] | None,
    *,
    day: int = 1,
    gold: int = 0,
    player_xy: tuple[int, int] | None = None,
    roll: int | None = None,
    check_success: bool | None = None,
) -> dict[str, Any] | None:
    """The hint for this ask. Nothing here writes the map."""
    spec = parse_direction_question(question)
    if spec is None or str(world.get("scale") or "") != "world":
        return None
    theme = str(world.get("theme") or "")
    good = str(spec["good"])
    forbidden = bool(spec["asks_forbidden"]) or good in _ALWAYS_FORBIDDEN or good == "black_market"
    if good == "magic" and magic_is_contraband(theme):
        forbidden = True
    px, py = _player_cell(world, player_xy)
    pfx, pfy = _player_fine(world, px, py)
    npc_id = int((npc or {}).get("id") or 0)
    if npc and not npc_id:
        npc_id = _text_salt(str(npc.get("name") or "someone"))
    question_key = spec["text"]
    used_roll = direction_roll(day, npc_id, question_key) if roll is None else int(roll) % 100
    if check_success is None:
        check_success = stand_in_check(npc_id, day, question_key, int((npc or {}).get("trust") or 0))
    bribe = bool(spec["bribe"]) and int(gold) >= BRIBE_GOLD
    told, reason = will_tell(
        npc, forbidden=forbidden, roll=used_roll, check_success=bool(check_success), bribe=bribe,
    )
    if good in {"guild", "notice"}:
        candidates = _notice_targets(world, good)
        for item in candidates:
            item["rank"] = 0
    else:
        candidates = _shop_targets(world, good, forbidden, str(spec["specificity"]))
    chosen = None
    if candidates:
        ranked = []
        for item in candidates:
            dist = point_distance(px, py, pfx, pfy, item["x"], item["y"], item["fine_x"], item["fine_y"])
            rank = int(item.get("rank") or 0) if spec["specificity"] == "area" else 0
            ranked.append((rank, dist, item["x"], item["y"], item["fine_x"], item))
        ranked.sort(key=lambda row: row[:5])
        chosen = ranked[0][5]
    if chosen is None:
        told = False
        reason = "nobody" if reason == "nobody" else "unknown"
    true_x = int(chosen["x"]) if chosen else px
    true_y = int(chosen["y"]) if chosen else py
    told_x, told_y, near = blur_cell(px, py, true_x, true_y) if chosen else (px, py, False)
    told_ok = bool(told and chosen is not None)
    precise = bool(told_ok and spec["specificity"] == "closest" and near and not forbidden)
    label = str((chosen or {}).get("label") or good)
    name = str((chosen or {}).get("district_name") or label)
    compass = compass_word(told_x - px, told_y - py) if chosen else ""
    hint = {
        "told": told_ok,
        "specificity": spec["specificity"],
        "good": good,
        "label": label,
        "name": name,
        "distance": max(abs(told_x - px), abs(told_y - py)) if told_ok else None,
        "exact": bool(told_ok and near),
        "compass": compass,
        "forbidden": forbidden,
        "reason": reason if chosen is not None or reason == "nobody" else reason,
        "wording": "",
        "place": chosen,
    }
    if not hint["told"]:
        hint["wording"] = ""
        hint["x"] = None
        hint["y"] = None
        hint["distance"] = None
        hint["place"] = None
        return hint
    hint["x"] = told_x
    hint["y"] = told_y
    hint["wording"] = _wording(
        told=True,
        forbidden=forbidden,
        specificity=str(spec["specificity"]),
        precise=precise,
        good=good,
        label=label,
        name=name,
        compass=compass,
    )
    return hint


def prompt_direction_hint(hint: dict[str, Any] | None) -> dict[str, Any] | None:
    """Drop the true stall so the packet cannot name a cell we did not open."""
    if not isinstance(hint, dict):
        return None
    shown = {
        "told": bool(hint.get("told")),
        "specificity": hint.get("specificity") or "",
        "good": hint.get("good") or "",
        "label": hint.get("label") or "",
        "wording": hint.get("wording") or "",
        "compass": hint.get("compass") or "",
        "forbidden": bool(hint.get("forbidden")),
        "reason": hint.get("reason") or "",
        "exact": bool(hint.get("exact")),
    }
    if hint.get("told"):
        shown["x"] = hint.get("x")
        shown["y"] = hint.get("y")
        shown["distance"] = hint.get("distance")
    return shown


def _known(map_data: dict[str, Any], x: int, y: int) -> bool:
    key = f"{int(x)},{int(y)}"
    if key in {str(item) for item in (map_data.get("visited") or [])}:
        return True
    if key in {str(item) for item in (map_data.get("revealed") or [])}:
        return True
    player = map_data.get("player") or {}
    return int(player.get("x") or 0) == int(x) and int(player.get("y") or 0) == int(y)


def reveal_cells(map_data: dict[str, Any], x: int, y: int, radius: int = REVEAL_RADIUS) -> list[str]:
    """Open a small patch. Walked cells stay walked; these are only heard-about."""
    width = int(map_data.get("width") or 0)
    height = int(map_data.get("height") or 0)
    radius = max(0, min(4, int(radius)))
    revealed = {str(item) for item in (map_data.get("revealed") or [])}
    added: list[str] = []
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            nx, ny = int(x) + dx, int(y) + dy
            if width and not (0 <= nx < width and 0 <= ny < height):
                continue
            key = f"{nx},{ny}"
            if key in revealed:
                continue
            revealed.add(key)
            added.append(key)
    map_data["revealed"] = sorted(revealed)
    return added


def place_marker(
    map_data: dict[str, Any],
    x: int,
    y: int,
    label: str,
    *,
    source: str = "player",
    save: bool = False,
) -> dict[str, Any]:
    """A mark may sit on a walked or heard-about cell, never on a blank one."""
    if not _known(map_data, x, y):
        return {"ok": False, "error": "That grid is still blank."}
    from app.tile_world import grant_map_knowledge

    text = str(label or "mark").strip()[:80] or "mark"
    grant_map_knowledge(
        map_data,
        notes=[{
            "id": f"m{int(x)}_{int(y)}_{_text_salt(text) % 10000}",
            "x": int(x),
            "y": int(y),
            "label": text,
            "kind": "marker",
            "source": source,
            "summary": text,
        }],
        source=source,
        save=save,
    )
    return {"ok": True, "x": int(x), "y": int(y), "label": text}


def apply_hint_to_map(map_data: dict[str, Any], hint: dict[str, Any] | None, *, save: bool = False) -> dict[str, Any]:
    if not hint or not hint.get("told") or hint.get("x") is None:
        return {"told": False, "reason": (hint or {}).get("reason") or ""}
    added = reveal_cells(map_data, int(hint["x"]), int(hint["y"]), REVEAL_RADIUS)
    marker = place_marker(
        map_data,
        int(hint["x"]),
        int(hint["y"]),
        str(hint.get("label") or hint.get("name") or "heard"),
        source="direction",
        save=False,
    )
    if save:
        from app.tile_world import _save_map_payload

        _save_map_payload(map_data)
    return {"told": True, "revealed": added, "marker": marker}


def advise_notice_percent(theme: str, rng: random.Random) -> int:
    """A percent, not a layout. A model may replace this number later."""
    lo, hi = _NOTICE_BANDS.get(str(theme or ""), (15, 35))
    return rng.randint(lo, hi)


def notice_capacity(side: int) -> int:
    """A 128-wide cell can hold 8 sites. An 8-wide town can hold one."""
    side = int(side)
    if side < 8:
        return 0
    if side < 16:
        return 1
    return max(1, min(8, int(round(8 * side / 128))))


def site_chance(percent: int, density: int) -> float:
    rank = max(0, min(100, int(percent))) / 100
    dense = max(0, min(100, int(density))) / 100
    return rank * (0.45 + 0.55 * dense)


def _spread_points(rng: random.Random, side: int, count: int) -> list[tuple[int, int]]:
    gap = max(2, int(side) // 8)
    points: list[tuple[int, int]] = []
    for _ in range(max(1, count) * 20):
        if len(points) >= count:
            break
        x = rng.randrange(max(1, side))
        y = rng.randrange(max(1, side))
        if all(max(abs(x - px), abs(y - py)) >= gap for px, py in points):
            points.append((x, y))
    while len(points) < count:
        points.append((rng.randrange(max(1, side)), rng.randrange(max(1, side))))
    return points


def roll_notices_for_cell(
    cell: dict[str, Any],
    percent: int,
    rng: random.Random,
    *,
    city_id: str = "",
    other_cells: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Sites for one cell. Guilds are a minority and only on a large cell."""
    side = int(cell.get("side") or 0)
    cap = notice_capacity(side)
    if cap <= 0 or int(percent) <= 0:
        return []
    chance = site_chance(percent, int(cell.get("density") or 0))
    count = sum(1 for _ in range(cap) if rng.random() < chance)
    if count <= 0:
        return []
    guild_cap = 0 if side < 64 or count < 2 else max(1, count // 6)
    kinds: list[str] = []
    guilds = 0
    for _ in range(count):
        if guilds < guild_cap and rng.random() < 0.18:
            kinds.append("guild")
            guilds += 1
        elif side < 16 or rng.random() < 0.65:
            kinds.append("pinboard")
        else:
            kinds.append("quest_board")
    points = _spread_points(rng, side, count)
    others = [item for item in (other_cells or []) if item is not cell]
    notices = []
    cx, cy = int(cell.get("x") or 0), int(cell.get("y") or 0)
    for index, kind in enumerate(kinds):
        home = True
        dest = cell
        fine_x, fine_y = points[index]
        if len(kinds) > 1 and others and index > 0 and rng.random() < 0.20:
            if kind == "guild":
                destinations = [item for item in others if int(item.get("side") or 0) >= 64]
            else:
                destinations = others
            if destinations:
                dest = destinations[rng.randrange(len(destinations))]
                home = False
                dest_side = max(1, int(dest.get("side") or 1))
                fine_x = rng.randrange(dest_side)
                fine_y = rng.randrange(dest_side)
        dx, dy = int(dest.get("x") or cx), int(dest.get("y") or cy)
        notices.append(
            {
                "id": f"{city_id}:{cx}:{cy}:{index}",
                "kind": kind,
                "label": _NOTICE_LABELS.get(kind, "Notice board"),
                "x": dx,
                "y": dy,
                "fine_x": int(fine_x),
                "fine_y": int(fine_y),
                "far": not home,
                "home_x": cx,
                "home_y": cy,
            }
        )
    return notices


def stamp_city_notices(city: dict[str, Any], percent: int, rng: random.Random) -> None:
    cells = [item for item in (city.get("cells") or []) if isinstance(item, dict)]
    for cell in cells:
        cell["notices"] = []
    city_id = str(city.get("id") or "C")
    for cell in cells:
        notices = roll_notices_for_cell(
            cell, percent, rng, city_id=city_id, other_cells=cells,
        )
        for notice in notices:
            dest = next(
                (
                    item for item in cells
                    if int(item.get("x") or 0) == int(notice["x"]) and int(item.get("y") or 0) == int(notice["y"])
                ),
                cell,
            )
            dest.setdefault("notices", []).append(notice)


def apply_notice_plan(
    cities: list[dict[str, Any]],
    theme: str,
    rng: random.Random,
    notice_percent: int | None,
) -> tuple[int, str]:
    if notice_percent is None:
        percent = advise_notice_percent(theme, rng)
        source = "theme"
    else:
        percent = normalize_density(notice_percent)
        source = "given"
    for city in cities:
        if isinstance(city, dict):
            stamp_city_notices(city, percent, rng)
    return percent, source


def roll_quest_propensity(rng: random.Random, *, shell: bool = False, role: str = "") -> tuple[bool, int]:
    """Whether this person offers work, and their daily percent. Five is typical, not fixed."""
    role_l = str(role or "").lower()
    if any(word in role_l for word in ("guild", "herald", "fixer", "patron")):
        offer_p = 0.80
    elif shell or not role_l.strip():
        offer_p = 0.15
    else:
        offer_p = 0.45
    if rng.random() >= offer_p:
        return False, 0
    table = (2, 3, 4, 4, 5, 5, 5, 5, 6, 6, 7, 8, 9, 10, 12)
    return True, int(table[rng.randrange(len(table))])


def advance_clock(
    state: dict[str, Any],
    from_day: int,
    to_day: int,
    rng: random.Random,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Roll each day after the day a month started. A taken quest is left alone."""
    state = dict(state)
    events: list[dict[str, Any]] = []
    if int(state.get("offers") or 0) <= 0 or int(state.get("chance") or 0) <= 0:
        state["last_day"] = int(to_day)
        return state, events
    chance = int(state["chance"]) / 100.0
    day = int(from_day)
    while day < int(to_day):
        day += 1
        phase_day = int(state.get("phase_day") or from_day)
        elapsed = day - phase_day
        if elapsed <= 0:
            continue
        if elapsed > QUEST_MONTH:
            state["phase_day"] = day
            continue
        phase = str(state.get("phase") or "waiting")
        taken = bool(state.get("taken"))
        if phase == "offered" and taken:
            continue
        roll = rng.random()
        if phase == "waiting" and roll < chance:
            state["phase"] = "offered"
            state["phase_day"] = day
            events.append({"day": day, "event": "offer"})
        elif phase == "offered" and not taken and roll < chance:
            state["phase"] = "waiting"
            state["phase_day"] = day
            events.append({"day": day, "event": "expire"})
    state["last_day"] = int(to_day)
    return state, events


def ensure_quest_clock_table(conn) -> None:
    conn.execute(_QUEST_CLOCKS_SQL)


def _world_day(conn) -> int:
    row = conn.execute("SELECT value FROM pacing WHERE key = 'world_day'").fetchone()
    if not row:
        return 1
    try:
        return max(1, int(row["value"]))
    except (TypeError, ValueError):
        return 1


def ensure_npc_clock(conn, npc_id: int, *, role: str = "", shell: bool = False, day: int | None = None) -> None:
    ensure_quest_clock_table(conn)
    key = f"npc:{int(npc_id)}"
    found = conn.execute("SELECT subject_key FROM quest_clocks WHERE subject_key = ?", (key,)).fetchone()
    if found:
        return
    rng = random.Random(mix_hash(int(npc_id), 91, 3))
    offers, chance = roll_quest_propensity(rng, shell=bool(shell), role=role)
    met = int(day if day is not None else _world_day(conn))
    conn.execute(
        """
        INSERT INTO quest_clocks (subject_key, offers, chance, phase, phase_day, quest_id, last_day)
        VALUES (?, ?, ?, 'waiting', ?, 0, ?)
        """,
        (key, 1 if offers else 0, int(chance), met, met),
    )


def _quest_is_taken(conn, quest_id: int) -> bool:
    if not quest_id:
        return False
    row = conn.execute("SELECT status FROM quests WHERE id = ?", (int(quest_id),)).fetchone()
    return bool(row) and str(row["status"]) == "active"


def expire_offered_quest(conn, quest_id: int) -> None:
    """Only an untaken offer lapses. An accepted quest stays active."""
    conn.execute(
        "UPDATE quests SET status = 'expired' WHERE id = ? AND status = 'offered'",
        (int(quest_id),),
    )


def _post_offer(conn, key: str, *, day: int, npc_id: int | None, place: str, x: int | None, y: int | None) -> int:
    from app.quests import create_quest

    title, description = _OFFERS[mix_hash(_text_salt(key), int(day), 4) % len(_OFFERS)]
    step: dict[str, Any] = {"title": title, "description": description, "location_name": place or ""}
    if x is not None and y is not None:
        step["location_coords"] = {"x": int(x), "y": int(y)}
    return create_quest(
        conn,
        title=title,
        description=description,
        steps=[step],
        difficulty="easy",
        giver_npc_id=npc_id,
        created_turn=0,
        notes=f"clock:{key}",
        status="offered",
    )


def _clock_row(row) -> dict[str, Any]:
    return {
        "subject_key": str(row["subject_key"]),
        "offers": int(row["offers"] or 0),
        "chance": int(row["chance"] or 0),
        "phase": str(row["phase"] or "waiting"),
        "phase_day": int(row["phase_day"] or 0),
        "quest_id": int(row["quest_id"] or 0),
        "last_day": int(row["last_day"] or 0),
    }


def _save_clock(conn, state: dict[str, Any]) -> None:
    conn.execute(
        """
        UPDATE quest_clocks
        SET offers = ?, chance = ?, phase = ?, phase_day = ?, quest_id = ?, last_day = ?
        WHERE subject_key = ?
        """,
        (
            int(state.get("offers") or 0),
            int(state.get("chance") or 0),
            str(state.get("phase") or "waiting"),
            int(state.get("phase_day") or 0),
            int(state.get("quest_id") or 0),
            int(state.get("last_day") or 0),
            str(state.get("subject_key") or ""),
        ),
    )


def _ensure_notice_clocks(conn, chart: dict[str, Any] | None, from_day: int) -> None:
    if not chart:
        return
    existing = {
        str(row["subject_key"])
        for row in conn.execute("SELECT subject_key FROM quest_clocks").fetchall()
    }
    for city, cell in _iter_city_cells(chart):
        for notice in cell.get("notices") or []:
            if not isinstance(notice, dict):
                continue
            key = f"notice:{notice.get('id')}"
            if key in existing:
                continue
            rng = random.Random(mix_hash(_text_salt(key), 5, 1))
            chance = rng.randint(3, 8)
            conn.execute(
                """
                INSERT INTO quest_clocks (subject_key, offers, chance, phase, phase_day, quest_id, last_day)
                VALUES (?, 1, ?, 'waiting', ?, 0, ?)
                """,
                (key, chance, int(from_day), int(from_day)),
            )
            existing.add(key)


def _ensure_met_npcs(conn, met_day: int) -> None:
    loc = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()
    loc_id = int(loc["current_location_id"] or 0) if loc and loc["current_location_id"] else 0
    if not loc_id:
        return
    rows = conn.execute(
        "SELECT id, role, shell FROM npcs WHERE location_id = ?",
        (loc_id,),
    ).fetchall()
    for row in rows:
        ensure_npc_clock(
            conn,
            int(row["id"]),
            role=str(row["role"] or ""),
            shell=bool(row["shell"]),
            day=met_day,
        )


def _notice_lookup(chart: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    if not chart:
        return found
    for city, cell in _iter_city_cells(chart):
        for notice in cell.get("notices") or []:
            if isinstance(notice, dict):
                item = dict(notice)
                item["city_name"] = str(city.get("name") or "")
                found[f"notice:{notice.get('id')}"] = item
    return found


def tick_quest_clocks(conn, *, from_day: int, to_day: int) -> list[int]:
    """Advance personal and board offers across real in-game days."""
    ensure_quest_clock_table(conn)
    if int(to_day) <= int(from_day):
        return []
    chart = None
    try:
        from app.tile_world import get_map

        chart = get_map(None, conn=conn)
    except Exception:
        chart = None
    _ensure_notice_clocks(conn, chart, int(from_day))
    _ensure_met_npcs(conn, int(to_day))
    notices = _notice_lookup(chart)
    posted: list[int] = []
    notes = 0
    rows = conn.execute("SELECT * FROM quest_clocks").fetchall()
    for row in rows:
        try:
            state = _clock_row(row)
            start = int(state["last_day"] or from_day)
            if int(to_day) <= start:
                continue
            state["taken"] = _quest_is_taken(conn, int(state["quest_id"]))
            rng = random.Random(mix_hash(_text_salt(state["subject_key"]), start, int(to_day)))
            state, events = advance_clock(state, start, int(to_day), rng)
            offered_now = False
            for event in events:
                if event["event"] == "expire" and int(state.get("quest_id") or 0):
                    expire_offered_quest(conn, int(state["quest_id"]))
                    state["quest_id"] = 0
                    offered_now = False
                elif event["event"] == "offer" and not state.get("taken"):
                    key = state["subject_key"]
                    notice = notices.get(key) or {}
                    npc_id = None
                    if key.startswith("npc:"):
                        try:
                            npc_id = int(key.split(":", 1)[1])
                        except ValueError:
                            npc_id = None
                    quest_id = _post_offer(
                        conn,
                        key,
                        day=int(event["day"]),
                        npc_id=npc_id,
                        place=str(notice.get("city_name") or ""),
                        x=notice.get("x") if notice else None,
                        y=notice.get("y") if notice else None,
                    )
                    state["quest_id"] = quest_id
                    posted.append(quest_id)
                    offered_now = True
            if offered_now and notes < 6 and str(state.get("phase") or "") == "offered":
                title = conn.execute(
                    "SELECT title FROM quests WHERE id = ?",
                    (int(state.get("quest_id") or 0),),
                ).fetchone()
                label = str(title["title"]) if title else "An offer"
                turn_row = conn.execute("SELECT value FROM pacing WHERE key = 'turn'").fetchone()
                turn = int(turn_row["value"]) if turn_row else 0
                conn.execute(
                    "INSERT INTO journal (turn, kind, content) VALUES (?, ?, ?)",
                    (turn, "system", f"A notice is up: {label}."[:400]),
                )
                notes += 1
            state.pop("taken", None)
            _save_clock(conn, state)
        except Exception:
            continue
    return posted


def accept_offered_quest(conn, text: str, turn: int | None = None) -> dict[str, Any] | None:
    if not re.search(r"\b(quest|job|notice|errand|contract|work|take|accept)\b", text or "", re.I):
        return None
    try:
        rows = conn.execute(
            "SELECT id, title FROM quests WHERE status = 'offered' ORDER BY id DESC"
        ).fetchall()
    except Exception:
        return None
    if not rows:
        return None
    low = str(text or "").lower()
    chosen = None
    for row in rows:
        title = str(row["title"] or "")
        if title and title.lower() in low:
            chosen = row
            break
    # A typed "I'll take the job" stands for the Accept button only when it can
    # mean one offer (TODO n20). It used to take the newest of several.
    if chosen is None and len(rows) == 1 and _ACCEPT_RE.search(text or ""):
        chosen = rows[0]
    if chosen is None:
        return None
    from app.quests import accept_offered

    if turn is None:
        try:
            row = conn.execute("SELECT value FROM pacing WHERE key = 'turn'").fetchone()
            turn = int(row["value"]) if row else 0
        except Exception:
            turn = 0
    if accept_offered(conn, int(chosen["id"]), turn=turn) is None:
        return None
    return {"id": int(chosen["id"]), "title": str(chosen["title"] or "the offer")}


def list_open_offers(limit: int = 8) -> list[dict[str, Any]]:
    from app.db import connect

    from app.quests import DECLINE_MEMORY_TURNS

    conn = connect()
    try:
        turn_row = conn.execute("SELECT value FROM pacing WHERE key = 'turn'").fetchone()
        turn = int(turn_row["value"]) if turn_row else 0
        # Offers the player turned down lately ride along as "declined", so the
        # narrator and the quest parser are told not to offer them again (TODO n20).
        rows = conn.execute(
            """
            SELECT q.id, q.title, q.notes, q.giver_npc_id, q.status, n.name AS giver_name
            FROM quests q LEFT JOIN npcs n ON n.id = q.giver_npc_id
            WHERE q.status = 'offered'
               OR (q.status = 'declined' AND COALESCE(q.failed_turn, 0) >= ?)
            ORDER BY (q.status = 'offered') DESC, q.id DESC LIMIT ?
            """,
            (turn - DECLINE_MEMORY_TURNS, max(1, min(12, int(limit) + 4))),
        ).fetchall()
    except Exception:
        return []
    finally:
        conn.close()
    found = []
    for row in rows:
        notes = str(row["notes"] or "")
        if notes.startswith("clock:notice:"):
            source = "notice"
        elif notes.startswith("clock:npc:"):
            source = "person"
        else:
            source = ""
        found.append(
            {
                "id": int(row["id"]),
                "title": str(row["title"] or ""),
                "source": source,
                "giver": str(row["giver_name"] or ""),
                "status": str(row["status"] or "offered"),
            }
        )
    return found


def _player_gold(conn) -> int:
    row = conn.execute("SELECT gold FROM player WHERE id = 1").fetchone()
    if not row:
        return 0
    try:
        return int(row["gold"] or 0)
    except (TypeError, ValueError):
        return 0


def _scene_codes(conn) -> list[str]:
    row = conn.execute("SELECT value FROM settings WHERE key = 'active_scene'").fetchone()
    if not row:
        return []
    try:
        scene = json.loads(row["value"])
    except (TypeError, ValueError):
        return []
    if not isinstance(scene, dict):
        return []
    return [str(code).upper() for code in (scene.get("interacting") or []) if str(code).strip()]


def pick_speaker(rows: list[dict[str, Any]], text: str, interacting: list[str]) -> dict[str, Any] | None:
    low = str(text or "").lower()
    for row in rows:
        name = str(row.get("name") or "").strip()
        if len(name) >= 3 and name.lower() in low:
            return row
    codes = {str(code).upper() for code in interacting}
    for row in rows:
        if str(row.get("code") or "").upper() in codes:
            return row
    return rows[0] if rows else None


def _hydrate_speaker(conn, speaker: dict[str, Any]) -> dict[str, Any]:
    npc_id = speaker.get("id")
    code = str(speaker.get("code") or "").strip()
    row = None
    if npc_id:
        row = conn.execute(
            "SELECT id, code, name, role, attitude, trust, shell FROM npcs WHERE id = ?",
            (int(npc_id),),
        ).fetchone()
    elif code:
        row = conn.execute(
            "SELECT id, code, name, role, attitude, trust, shell FROM npcs WHERE code = ?",
            (code,),
        ).fetchone()
    if not row:
        return {
            "id": int(npc_id or 0),
            "code": code,
            "name": speaker.get("name") or "",
            "role": speaker.get("role") or "",
            "attitude": speaker.get("attitude") or "neutral",
            "trust": int(speaker.get("trust") or 0),
            "shell": speaker.get("shell") or 0,
        }
    return dict(row)


def direction_hint_for_prompt(state: dict[str, Any], player_input: str) -> dict[str, Any] | None:
    if parse_direction_question(player_input) is None:
        return None
    from app.db import connect
    from app.tile_world import get_map

    conn = connect()
    try:
        chart = get_map(None, conn=conn)
        if not chart or str(chart.get("scale") or "") != "world":
            return None
        current = state.get("current_location") if isinstance(state.get("current_location"), dict) else {}
        code = str(current.get("code") or "")
        rows: list[dict[str, Any]] = []
        for loc in state.get("locations") or []:
            if not isinstance(loc, dict):
                continue
            if code and str(loc.get("code") or "") != code:
                continue
            for npc in loc.get("npcs") or []:
                if isinstance(npc, dict):
                    rows.append(npc)
        if not rows and current.get("id"):
            found = conn.execute(
                "SELECT id, code, name, role, attitude, trust, shell FROM npcs WHERE location_id = ?",
                (int(current["id"]),),
            ).fetchall()
            rows = [dict(item) for item in found]
        settings = state.get("settings") if isinstance(state.get("settings"), dict) else {}
        scene = settings.get("active_scene") if isinstance(settings.get("active_scene"), dict) else {}
        interacting = [str(item).upper() for item in (scene.get("interacting") or [])]
        speaker = pick_speaker(rows, player_input, interacting)
        if speaker:
            speaker = _hydrate_speaker(conn, speaker)
        day = int(((state.get("world_time") or {}) if isinstance(state.get("world_time"), dict) else {}).get("day") or _world_day(conn))
        hint = resolve_direction(chart, player_input, speaker, day=day, gold=_player_gold(conn))
        return prompt_direction_hint(hint)
    finally:
        conn.close()


def _play_flag_on(conn, key: str) -> bool:
    """Missing setup flags stay on, matching current play."""
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = 'playthrough_options'"
        ).fetchone()
        opts = json.loads(row["value"]) if row and row["value"] else {}
    except Exception:
        return True
    if not isinstance(opts, dict) or key not in opts:
        return True
    value = opts.get(key)
    if value is None or value == "":
        return True
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
        return True
    return bool(value)


def apply_turn_intel(conn, player_input: str, turn: int) -> str:
    """Save a heard-about patch, charge a bribe, or accept a posted offer."""
    notes: list[str] = []
    asked = parse_direction_question(player_input)
    faction_held = bool(asked and asked.get("good") == "guild" and not _play_flag_on(conn, "factions_enabled"))
    if asked is not None and not faction_held:
        from app.tile_world import _save_map_payload, get_map

        chart = get_map(None, conn=conn)
        if chart and str(chart.get("scale") or "") == "world":
            loc = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()
            loc_id = int(loc["current_location_id"] or 0) if loc and loc["current_location_id"] else 0
            rows = []
            if loc_id:
                found = conn.execute(
                    "SELECT id, code, name, role, attitude, trust, shell FROM npcs WHERE location_id = ?",
                    (loc_id,),
                ).fetchall()
                rows = [dict(item) for item in found]
            speaker = pick_speaker(rows, player_input, _scene_codes(conn))
            gold = _player_gold(conn)
            hint = resolve_direction(
                chart,
                player_input,
                speaker,
                day=_world_day(conn),
                gold=gold,
            )
            if hint and hint.get("reason") == "bribe" and gold < BRIBE_GOLD:
                hint = resolve_direction(
                    chart,
                    player_input,
                    speaker,
                    day=_world_day(conn),
                    gold=0,
                )
            applied = apply_hint_to_map(chart, hint, save=False)
            if applied.get("told") and hint:
                _save_map_payload(chart, conn=conn)
                # The stall or notice it pointed at is now told (docs/TownGrid.md 6):
                # its plot's name shows once that cell is generated. Generates nothing.
                try:
                    from app.town_moves import record_told

                    record_told(conn, chart, hint.get("place"), turn)
                except Exception:
                    pass
                distance = max(
                    abs(int(hint["x"]) - int((chart.get("player") or {}).get("x") or 0)),
                    abs(int(hint["y"]) - int((chart.get("player") or {}).get("y") or 0)),
                )
                where = "in this cell" if distance <= 0 else f"about {distance} cells {hint.get('compass') or 'away'}"
                notes.append(
                    f"Heard about {hint.get('label') or 'a place'}, {where}. "
                    f"The map marks ({hint.get('x')}, {hint.get('y')})."
                )
                if hint.get("reason") == "bribe" and _play_flag_on(conn, "economy_enabled"):
                    gold = _player_gold(conn)
                    if gold >= BRIBE_GOLD:
                        conn.execute(
                            "UPDATE player SET gold = ? WHERE id = 1",
                            (gold - BRIBE_GOLD,),
                        )
                        notes.append(f"You paid {BRIBE_GOLD} coin for the direction.")
    # quests.accept_offered journals the acceptance itself, so no second note here.
    if _play_flag_on(conn, "quests_enabled"):
        accept_offered_quest(conn, player_input, turn)
    return " ".join(notes)[:1400]


def _journal_map(conn, text: str) -> None:
    try:
        row = conn.execute("SELECT value FROM pacing WHERE key = 'turn'").fetchone()
        turn = int(row["value"]) if row else 0
        conn.execute(
            "INSERT INTO journal (turn, kind, content) VALUES (?, ?, ?)",
            (turn, "system", str(text)[:400]),
        )
    except Exception:
        return


def run_map_command(name: str, rest: str) -> dict[str, Any]:
    """Slash /reveal and /mark. They do not call the model."""
    from app.db import connect
    from app.tile_world import _save_map_payload, get_map

    tokens = str(rest or "").split()
    if name == "mark" and tokens and tokens[0].lower() == "here":
        label = " ".join(tokens[1:]).strip() or "mark"
        here = True
        x = y = 0
        radius = 0
    elif len(tokens) >= 2 and re.fullmatch(r"-?\d+", tokens[0]) and re.fullmatch(r"-?\d+", tokens[1]):
        here = False
        x, y = int(tokens[0]), int(tokens[1])
        radius = 1
        label_at = 2
        if name == "reveal" and len(tokens) >= 3 and re.fullmatch(r"\d+", tokens[2]):
            radius = int(tokens[2])
            label_at = 3
        label = " ".join(tokens[label_at:]).strip()
    else:
        if name == "mark":
            return {"ok": False, "error": "Use /mark x y label, or /mark here label.", "advanced_turn": False}
        return {"ok": False, "error": "Use /reveal x y [radius] [label].", "advanced_turn": False}
    conn = connect()
    try:
        chart = get_map(None, conn=conn)
        if not chart:
            return {"ok": False, "error": "There is no map yet.", "advanced_turn": False}
        if here:
            player = chart.get("player") or {}
            x, y = int(player.get("x") or 0), int(player.get("y") or 0)
        width = int(chart.get("width") or 0)
        height = int(chart.get("height") or 0)
        if width and not (0 <= x < width and 0 <= y < height):
            return {"ok": False, "error": "That cell is off the map.", "advanced_turn": False}
        if name == "reveal":
            added = reveal_cells(chart, x, y, radius)
            text = label or "revealed"
            marker = place_marker(chart, x, y, text, source="gm", save=False)
            answer = f"Revealed {len(added)} cells around ({x}, {y})."
            if marker.get("ok"):
                answer += f" Marked {marker.get('label')}."
            _journal_map(conn, answer)
            _save_map_payload(chart, conn=conn)
            conn.commit()
            return {"ok": True, "command": f"/{name}", "answer": answer, "refresh": True, "advanced_turn": False}
        marker = place_marker(chart, x, y, label or "mark", source="player", save=False)
        if not marker.get("ok"):
            return {"ok": False, "error": marker.get("error") or "That grid is still blank.", "advanced_turn": False}
        answer = f"Marked {marker['label']} at ({marker['x']}, {marker['y']})."
        _journal_map(conn, answer)
        _save_map_payload(chart, conn=conn)
        conn.commit()
        return {
            "ok": True,
            "command": "/mark",
            "answer": answer,
            "refresh": True,
            "advanced_turn": False,
        }
    finally:
        conn.close()
