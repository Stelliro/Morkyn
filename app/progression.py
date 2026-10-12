"""Levels come from XP, by the engine (playtest #121).

The model proposes XP as a band and the engine rolls it; it never decides a
level. Reaching level n takes 50 * n * (n - 1) XP in total: 100 for level 2,
300 for level 3, 600 for level 4, 1000 for level 5. A level is never taken
away, so a save whose level was set by hand keeps it.
"""
from __future__ import annotations

from typing import Any

MAX_LEVEL = 100


def xp_for_level(level: int) -> int:
    """Total XP needed to reach ``level``."""
    n = max(1, int(level))
    return 50 * n * (n - 1)


def level_for_xp(xp: int) -> int:
    level = 1
    while level < MAX_LEVEL and int(xp) >= xp_for_level(level + 1):
        level += 1
    return level


def level_progress(xp: int, level: int) -> dict[str, int]:
    """Where the player stands inside the current level, for the XP bar (TODO n29)."""
    level = max(1, min(MAX_LEVEL, int(level)))
    floor = xp_for_level(level)
    ceiling = xp_for_level(level + 1) if level < MAX_LEVEL else floor
    return {
        "level": level,
        "xp": int(xp),
        "into_level": max(0, int(xp) - floor),
        "needed": max(0, ceiling - floor),
        "next_level_at": ceiling,
    }


def leveling_enabled(conn: Any) -> bool:
    """The playthrough's leveling_system choice (on unless the setup turned it off)."""
    import json

    row = conn.execute("SELECT value FROM settings WHERE key = 'playthrough_options'").fetchone()
    try:
        options = json.loads(row["value"]) if row and row["value"] else {}
    except (TypeError, ValueError):
        options = {}
    value = options.get("leveling_system", True) if isinstance(options, dict) else True
    return str(value).strip().lower() not in {"false", "0", "off", "no", "none"}


def sync_level(conn: Any, turn: int = 0, *, enabled: bool | None = None) -> int | None:
    """Raise the stored level to what the stored XP has earned; journal each level gained.

    Returns the new level when it rose, else None.
    """
    if enabled is None:
        enabled = leveling_enabled(conn)
    if not enabled:
        return None
    row = conn.execute("SELECT level, xp FROM player WHERE id = 1").fetchone()
    if not row:
        return None
    current = int(row["level"] or 1)
    earned = level_for_xp(int(row["xp"] or 0))
    if earned <= current:
        return None
    conn.execute("UPDATE player SET level = ? WHERE id = 1", (earned,))
    for gained in range(current + 1, earned + 1):
        conn.execute(
            "INSERT INTO journal (turn, kind, content) VALUES (?, ?, ?)",
            (int(turn), "level_up", f"Level {gained} reached ({xp_for_level(gained)} XP)."),
        )
    return earned
