"""On and off duty, derived from a person's job and the world clock (playtest #83).

"Off-duty guard" was a role in the seed pools, so the model wrote her saying
"Off-duty guard isn't a career". The role is the job; whether someone is at it
right now is a state that follows the clock, the way a venue's opening hours do.

Nothing here is stored per person. Each kind of job has a shift template (one
or more windows of the day); a person's own window comes from that template and
the campaign seed, so it is stable for them and varies across a town. A story
event can set a short override ("called in early", "covering a shift") that
expires on its own.
"""
from __future__ import annotations

import json
import re
from typing import Any

from app import venues

MINUTES_PER_DAY = 24 * 60

# Words that are a state, not a job. "Off-duty guard" is a guard.
_STATE_PREFIX = re.compile(r"^\s*(?:off|on)[\s-]+(?:duty|shift)\s+", re.I)

# (job words, shift windows as (start, end) minutes of the day, where off duty usually finds them)
_TEMPLATES: tuple[tuple[tuple[str, ...], tuple[tuple[int, int], ...], str], ...] = (
    (
        ("guard", "watchman", "watchwoman", "warden", "marshal", "deputy", "officer", "police officer",
         "constable", "sentry", "security guard", "road warden", "harbour watchman", "port inspector",
         "dock inspector", "toll keeper", "gatekeeper",
         # Hired fighters keep a guard's watches.
         "mercenary", "merc", "hired gun", "hired blade", "hired sword", "sellsword", "bodyguard", "enforcer",
         "hired muscle"),
        ((6 * 60, 14 * 60), (14 * 60, 22 * 60), (22 * 60, 6 * 60)),
        "at home asleep, or in a tavern",
    ),
    (
        ("baker", "fisher", "fisherman", "fisherwoman", "eel fisher", "net mender", "bargeman", "ferryman",
         "goatherd", "drover", "stablehand", "stable hand", "farrier", "mudlark", "milkmaid", "salt carrier"),
        ((4 * 60, 13 * 60),),
        "at home, or at the market",
    ),
    (
        ("barkeep", "bartender", "server", "musician", "piano player", "night clerk", "night-cycle clerk",
         "innkeeper", "tavern keeper", "waiter", "waitress"),
        ((16 * 60, 2 * 60),),
        "asleep at home",
    ),
    (
        ("cook", "line cook", "kitchen hand", "galley hand", "mess server", "chef", "barista"),
        ((6 * 60, 15 * 60), (11 * 60, 22 * 60)),
        "at home, or at the market",
    ),
    (
        ("nurse", "medic", "medtech", "paramedic", "doctor", "surgeon", "crew", "deck crew", "deckhand",
         "dock hand", "dock worker", "stevedore", "rail hand", "brakeman", "crane hand", "crane operator",
         "gantry hand", "cargo loader", "tug pilot", "coal heaver", "hull welder", "dispatcher", "cab driver",
         "trucker", "teamster", "courier", "delivery driver", "riverboat hand"),
        ((7 * 60, 19 * 60), (19 * 60, 7 * 60)),
        "at home resting, or in a bar",
    ),
)
_DAY_SHIFT = ((8 * 60, 18 * 60),)
_DAY_OFF = "at home"

# Roles that say why someone is here, not what work they do: no shift.
_NOT_JOBS = frozenset({
    "", "local", "patron", "customer", "regular", "lodger", "boarder", "bunkmate", "card player", "pilgrim",
    "drifter", "hermit", "deserter", "traveller", "traveler", "stranger", "visitor", "guest", "wanderer",
    "refugee", "beggar", "child", "elder", "companion", "landlord's son", "homesteader",
})


def job_of(role: Any) -> str:
    """The job in a role: "off-duty guard" -> "guard"."""
    text = re.sub(r"\s+", " ", str(role or "")).strip()
    return _STATE_PREFIX.sub("", text).strip()


def _template(job: str) -> tuple[tuple[tuple[int, int], ...], str] | None:
    text = re.sub(r"[^a-z' -]+", " ", job.lower()).replace("-", " ")
    text = re.sub(r"\s+", " ", text).strip()
    if text in _NOT_JOBS:
        return None
    best: tuple[tuple[tuple[int, int], ...], str] | None = None
    best_len = 0
    for words, windows, off in _TEMPLATES:
        for word in words:
            folded = word.replace("-", " ")
            if len(folded) > best_len and re.search(rf"(?:^|\s){re.escape(folded)}(?:\s|$)", text):
                best, best_len = (windows, off), len(folded)
    if best:
        return best
    kind = venues.workplace_kind_for_role(text)
    if kind:
        start, end = venues.default_hours(kind)
        if start >= 0 and end >= 0 and start != end:
            return ((start, end),), _DAY_OFF
    return _DAY_SHIFT, _DAY_OFF


def job_words(role: Any) -> tuple[str, ...]:
    """The names of the job family this role belongs to ("kitchen hand" -> cook, line cook, kitchen hand, ...); () when none.

    The templates group the jobs that are one job under different names, so a
    reader that asks whether "the cook" may mean the kitchen hand has the
    engine's own answer.
    """
    text = re.sub(r"[^a-z' -]+", " ", job_of(role).lower()).replace("-", " ")
    text = re.sub(r"\s+", " ", text).strip()
    if not text or text in _NOT_JOBS:
        return ()
    best: tuple[str, ...] = ()
    best_len = 0
    for words, _windows, _off in _TEMPLATES:
        for word in words:
            folded = word.replace("-", " ")
            if len(folded) > best_len and re.search(rf"(?:^|\s){re.escape(folded)}(?:\s|$)", text):
                best, best_len = words, len(folded)
    return best


def shift_for(role: Any, code: str, seed: int) -> tuple[int, int, str] | None:
    """This person's own shift (start, end, off-duty place), or None for a role that is not a job."""
    from app.rng import seed_from

    found = _template(job_of(role))
    if found is None:
        return None
    windows, off = found
    draw = seed_from(seed, "shift", str(code or "").upper())
    start, end = windows[draw % len(windows)]
    # Half an hour either way, so one town's guards do not all change at once.
    shift = ((draw >> 8) % 3 - 1) * 30
    return (start + shift) % MINUTES_PER_DAY, (end + shift) % MINUTES_PER_DAY, off


def duty_for(
    role: Any,
    code: str,
    seed: int,
    abs_minute: int,
    override: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """{"on_duty", "shift", "off_duty_likely"?, "reason"?} for this person now, or None for no job."""
    shift = shift_for(role, code, seed)
    if shift is None:
        return None
    start, end, off = shift
    window = venues.describe_hours(start, end)
    on = venues.is_open(start, end, int(abs_minute) % MINUTES_PER_DAY)
    out: dict[str, Any] = {"shift": window}
    if override and int(override.get("until") or 0) > int(abs_minute):
        on = bool(override.get("on_duty"))
        if override.get("reason"):
            out["reason"] = str(override["reason"])[:80]
    out["on_duty"] = on
    if not on:
        out["off_duty_likely"] = off
    return out


def working_fields(duty: dict[str, Any] | None) -> dict[str, Any]:
    """What a prompt says about someone in the scene: {"working": bool} and an override's reason.

    The prompt used to carry duty_note's sentence, and the 7B pasted it as
    written ("Abel Hollis (D) - woodcutter (on duty (shift 08:00-18:00))") or
    staged both halves of "off duty; likely asleep at home" for a woman behind
    her own counter (7B run 5, #83). Everyone a prompt lists is in the scene, so
    where they would be off duty is not said, and the shift hours are the
    engine's: a flag leaves nothing to paste.
    """
    if not duty:
        return {}
    out: dict[str, Any] = {"working": bool(duty.get("on_duty"))}
    if duty.get("reason"):
        out["working_because"] = str(duty["reason"])[:80]
    return out


def duty_note(duty: dict[str, Any] | None) -> str:
    """One line for logs and tools: "on duty (shift 06:00-14:00)" / "off duty (shift ...); likely at home".

    Not for prompts: see working_fields.
    """
    if not duty:
        return ""
    if duty.get("on_duty"):
        note = f"on duty (shift {duty.get('shift')})"
    else:
        note = f"off duty (shift {duty.get('shift')}); likely {duty.get('off_duty_likely') or _DAY_OFF}"
    if duty.get("reason"):
        note += f"; {duty['reason']}"
    return note


# ---------------------------------------------------------------------------
# Short-lived story overrides
# ---------------------------------------------------------------------------

_OVERRIDE_KEY = "duty_overrides"


def abs_minute(conn) -> int:
    from app.world import get_world_time

    clock = get_world_time(conn)
    day = max(1, int(clock.get("day") or 1))
    minute = int(clock.get("minute") or 0)
    return (day - 1) * MINUTES_PER_DAY + minute


def _load_overrides(conn) -> dict[str, dict[str, Any]]:
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (_OVERRIDE_KEY,)).fetchone()
        data = json.loads(str(row["value"] or "{}")) if row else {}
    except Exception:
        data = {}
    return data if isinstance(data, dict) else {}


def overrides(conn, now: int | None = None) -> dict[str, dict[str, Any]]:
    """Live overrides by NPC code; expired ones are dropped as they are read."""
    now = abs_minute(conn) if now is None else int(now)
    return {
        code: entry
        for code, entry in _load_overrides(conn).items()
        if isinstance(entry, dict) and int(entry.get("until") or 0) > now
    }


def set_override(conn, code: str, on_duty: bool, *, minutes: int = 240, reason: str = "", now: int | None = None) -> None:
    """A story event puts someone on or off duty for a while (default four hours)."""
    now = abs_minute(conn) if now is None else int(now)
    live = overrides(conn, now)
    live[str(code or "").upper()] = {
        "on_duty": bool(on_duty),
        "until": now + max(1, int(minutes)),
        "reason": str(reason or "")[:80],
    }
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (_OVERRIDE_KEY, json.dumps(live, ensure_ascii=True)),
    )


def _read_seed(conn) -> int:
    """The campaign seed, read only.

    rng.campaign_seed writes the seed when it is missing; from get_state that
    write held the database and the next connection hit "database is locked".
    """
    from app.db import db_path
    from app.rng import _SEED_CACHE, seed_from

    key = str(db_path())
    if key in _SEED_CACHE:
        return _SEED_CACHE[key]
    row = conn.execute("SELECT value FROM settings WHERE key = 'campaign_rng_seed'").fetchone()
    if row:
        try:
            return int(json.loads(row["value"]))
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    return seed_from("duty", key)


def stamp_duty(conn, npcs: list[dict[str, Any]]) -> None:
    """Add "duty" to each person dict that has a job (the prompt reads it)."""
    if not npcs:
        return
    try:
        seed = _read_seed(conn)
        now = abs_minute(conn)
        live = overrides(conn, now)
    except Exception:
        return
    for npc in npcs:
        if not isinstance(npc, dict):
            continue
        code = str(npc.get("code") or "").upper()
        duty = duty_for(npc.get("role"), code, seed, now, live.get(code))
        if duty:
            npc["duty"] = duty
