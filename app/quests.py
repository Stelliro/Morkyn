"""
Quest / Objectives system for Morkyn.

Quests are chains of up to 6 location steps. Each quest has:
- title, description, reward (gold/XP/items)
- optional timer
- optional hidden sub-tasks revealed on arrival
- status: active | offered | declined | completed | failed | abandoned | expired

Reward scales with length (steps) and difficulty.
"""
from __future__ import annotations

import json
import re
from typing import Any

from app.db import connect


def _snap_to_settlement(location_name: str) -> dict[str, float] | None:
    """
    Return grid coords {"x": float, "y": float} if a settlement with a
    name matching *location_name* (case-insensitive) exists on the active map.
    Returns None if no map is loaded or no matching settlement is found.
    """
    if not location_name:
        return None
    try:
        from app.tile_world import get_map, list_settlements

        map_data = get_map()
        if not map_data:
            return None
        name_lower = location_name.strip().lower()
        for s in list_settlements(map_data):
            if str(s.get("name") or "").strip().lower() == name_lower:
                x = s.get("x")
                y = s.get("y")
                if x is not None and y is not None:
                    return {"x": float(x), "y": float(y)}
    except Exception:
        pass
    return None

DIFFICULTY_MULTIPLIERS = {
    "trivial": 0.5,
    "easy": 0.75,
    "normal": 1.0,
    "hard": 1.5,
    "deadly": 2.5,
}

BASE_REWARDS = {
    "gold_per_step": 15,
    "xp_per_step": 25,
}


def _quest_code(conn, quest_id: int) -> str:
    return f"Q{quest_id}"


def create_quest(
    conn,
    *,
    title: str,
    description: str = "",
    steps: list[dict[str, Any]],
    reward_gold: int | None = None,
    reward_xp: int | None = None,
    reward_items: list[str] | None = None,
    difficulty: str = "normal",
    timer_turns: int = 0,
    giver_npc_id: int | None = None,
    target_location_id: int | None = None,
    created_turn: int = 0,
    notes: str = "",
    status: str = "active",
    reward_karma: int = 0,
) -> int:
    """Create a quest with its steps. Returns the quest id.

    ``offered`` is posted and not yet taken. Every older caller stays ``active``.
    ``reward_karma`` is paid with the rest by pay_quest_reward (playtest #85b).
    """
    if not steps:
        raise ValueError("Quest must have at least one step")
    if len(steps) > 6:
        raise ValueError("Quest may have at most 6 steps")
    status = str(status or "active").strip().lower()
    if status not in {"active", "offered"}:
        status = "active"

    mult = DIFFICULTY_MULTIPLIERS.get(difficulty, 1.0)
    n_steps = len(steps)
    if reward_gold is None:
        reward_gold = int(BASE_REWARDS["gold_per_step"] * n_steps * mult)
    if reward_xp is None:
        reward_xp = int(BASE_REWARDS["xp_per_step"] * n_steps * mult)
    if reward_items is None:
        reward_items = []

    cur = conn.execute(
        """
        INSERT INTO quests
          (title, description, status, current_step, total_steps,
           reward_gold, reward_xp, reward_items, difficulty,
           timer_turns, turns_remaining, giver_npc_id, target_location_id,
           created_turn, notes)
        VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(title),
            str(description),
            status,
            int(n_steps),
            int(reward_gold),
            int(reward_xp),
            json.dumps(reward_items),
            str(difficulty),
            int(timer_turns),
            int(timer_turns),  # turns_remaining starts equal to timer
            giver_npc_id,
            target_location_id,
            int(created_turn),
            str(notes),
        ),
    )
    quest_id = int(cur.lastrowid)
    code = _quest_code(conn, quest_id)
    conn.execute("UPDATE quests SET code = ? WHERE id = ?", (code, quest_id))
    if reward_karma:
        # Written only when there is some, so a database the column has not
        # reached yet still creates quests (db._migrate_columns adds it).
        conn.execute("UPDATE quests SET reward_karma = ? WHERE id = ?", (max(-25, min(25, int(reward_karma))), quest_id))

    for i, step in enumerate(steps, 1):
        loc_name = str(step.get("location_name", "") or "")
        # Town snapping: if location_name matches a known settlement, use its coords
        loc_coords_raw = step.get("location_coords")
        if loc_name and loc_coords_raw is None:
            snapped = _snap_to_settlement(loc_name)
            if snapped is not None:
                loc_coords_raw = snapped
        loc_coords_str = json.dumps(loc_coords_raw) if loc_coords_raw else ""
        conn.execute(
            """
            INSERT INTO quest_steps
              (quest_id, step_number, title, description, location_code,
               location_name, location_coords,
               status, hidden, revealed_at_step, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                quest_id,
                i,
                str(step.get("title", f"Step {i}")),
                str(step.get("description", "")),
                str(step.get("location_code", "")),
                loc_name,
                loc_coords_str,
                "active" if i == 1 else "pending",
                1 if step.get("hidden", False) and i > 1 else 0,
                int(step.get("revealed_at_step", 0)),
                str(step.get("notes", "")),
            ),
        )
    return quest_id


def get_active_quests(conn) -> list[dict[str, Any]]:
    """Return all active quests with their steps."""
    return _quests_with_status(conn, "active")


def get_offered_quests(conn) -> list[dict[str, Any]]:
    """Offered (posted, not yet taken) quests with their steps and giver name."""
    quests = _quests_with_status(conn, "offered")
    for quest in quests:
        quest["giver_name"] = ""
        quest["giver_code"] = ""
        if quest.get("giver_npc_id"):
            row = conn.execute("SELECT name, code FROM npcs WHERE id = ?", (quest["giver_npc_id"],)).fetchone()
            quest["giver_name"] = str(row["name"] or "") if row else ""
            quest["giver_code"] = str(row["code"] or "") if row else ""
    return quests


def get_declined_offers(conn, *, since_turn: int = 0, limit: int = 8) -> list[dict[str, Any]]:
    """Offers the player turned down at or after ``since_turn``: id, code, title, giver_npc_id, failed_turn."""
    try:
        rows = conn.execute(
            "SELECT id, code, title, giver_npc_id, failed_turn FROM quests "
            "WHERE status = 'declined' AND COALESCE(failed_turn, 0) >= ? ORDER BY id DESC LIMIT ?",
            (int(since_turn), max(1, int(limit))),
        ).fetchall()
    except Exception:
        return []
    return [dict(r) for r in rows]


# How long a refusal holds before the same job may be offered again.
DECLINE_MEMORY_TURNS = 30


def _offer_journal(conn, turn: int, content: str) -> None:
    conn.execute("INSERT INTO journal (turn, kind, content) VALUES (?, ?, ?)", (int(turn), "quest", str(content)[:1400]))


def _giver_suffix(conn, quest: dict[str, Any]) -> str:
    if not quest.get("giver_npc_id"):
        return ""
    row = conn.execute("SELECT name FROM npcs WHERE id = ?", (quest["giver_npc_id"],)).fetchone()
    name = str(row["name"] or "") if row else ""
    return f" (from {name})" if name else ""


def accept_offered(conn, quest_id: int, *, turn: int = 0) -> dict[str, Any] | None:
    """
    The one place an offer becomes the player's quest (TODO n20).

    The Accept button, the parser's ``accept`` update and a typed "I'll take
    the job" all come here, so an offer cannot be taken twice or by a path that
    skips the journal. A timer starts now, not when the job was offered.
    Returns the quest, or None when it was not an open offer.
    """
    quest = get_quest(conn, int(quest_id))
    if not quest or str(quest.get("status") or "") != "offered":
        return None
    conn.execute(
        "UPDATE quests SET status = 'active', turns_remaining = timer_turns WHERE id = ? AND status = 'offered'",
        (int(quest_id),),
    )
    _offer_journal(conn, turn, f"Quest accepted: {quest['title']}{_giver_suffix(conn, quest)}")
    quest["status"] = "active"
    return quest


def decline_offered(conn, quest_id: int, *, turn: int = 0) -> dict[str, Any] | None:
    """
    Record that the player turned an offer down (TODO n20).

    ``declined`` keeps the row so the quest parser can refuse the same job when
    the giver brings it up again (see quest_parser._is_duplicate). failed_turn
    holds the turn of the refusal. Returns the quest, or None when it was not an
    open offer.
    """
    quest = get_quest(conn, int(quest_id))
    if not quest or str(quest.get("status") or "") != "offered":
        return None
    conn.execute(
        "UPDATE quests SET status = 'declined', failed_turn = ? WHERE id = ? AND status = 'offered'",
        (int(turn), int(quest_id)),
    )
    _offer_journal(conn, turn, f"Turned down: {quest['title']}{_giver_suffix(conn, quest)}")
    quest["status"] = "declined"
    return quest


def quest_reward_amounts(conn, quest: dict[str, Any], *, units: int = 1) -> dict[str, Any]:
    """What completing ``quest`` pays now, after the game's own rules (playtest #85b).

    The same gates the turn's own rewards pass (world._apply_player): no gold
    when the economy is off, no XP when leveling is off, XP scaled by the
    growth speed. Read by the narrator's note before the prose and by the
    payout after it, so the prose names the sum that is paid.
    ``units`` is how many times a repeatable task was done (TODO n27).
    """
    from app.world import _play_system_enabled, _scaled_delta, _settings

    units = max(1, int(units or 1))
    options = _settings(conn).get("playthrough_options") or {}
    options = options if isinstance(options, dict) else {}
    gold = max(0, int(quest.get("reward_gold") or 0)) * units
    if not _play_system_enabled(conn, "economy_enabled", True):
        gold = 0
    xp = max(0, int(quest.get("reward_xp") or 0)) * units
    if not options.get("leveling_system", True):
        xp = 0
    elif xp:
        multiplier = options.get("xp_growth_multiplier")
        xp = _scaled_delta(
            xp,
            str(options.get("xp_growth_speed") or "normal"),
            float(multiplier) if multiplier else None,
        )
    karma = max(-25, min(25, int(quest.get("reward_karma") or 0))) * units
    items = quest.get("reward_items")
    if isinstance(items, str):
        try:
            items = json.loads(items or "[]")
        except ValueError:
            items = []
    items = [str(i).strip()[:80] for i in (items or []) if str(i or "").strip()]
    if not _play_system_enabled(conn, "items_enabled", True):
        items = []
    return {"gold": gold, "xp": xp, "karma": karma, "items": items, "units": units}


def reward_text(paid: dict[str, Any] | None) -> str:
    """'+11 gold, +18 XP' for the journal, the toast and the narrator's note."""
    if not isinstance(paid, dict):
        return ""
    bits = []
    if paid.get("gold"):
        bits.append(f"+{int(paid['gold'])} gold")
    if paid.get("xp"):
        bits.append(f"+{int(paid['xp'])} XP")
    if paid.get("karma"):
        bits.append(f"{int(paid['karma']):+d} karma")
    units = max(1, int(paid.get("units") or 1))
    for name in paid.get("items") or []:
        bits.append(f"{name} x{units}" if units > 1 else str(name))
    return ", ".join(bits)


def pay_quest_reward(conn, quest_id: int, *, turn: int = 0, units: int = 1, source: str = "") -> dict[str, Any]:
    """
    The one quest payout (playtest #85b). Every completion path comes here:
    the engine's step matcher, the quest parser and the Advance step button.

    The old payout added gold and XP by raw SQL past the economy and leveling
    rules, dropped the reward items it was handed, had no karma, journaled
    nothing and swallowed every error, so nobody could show what was paid.
    This pays gold, XP, karma and items through the game's own gates, credits
    the giver, writes one journal line naming the amounts and returns them:
    {"gold", "xp", "karma", "items", "units", "text", "errors"?}.
    """
    quest = get_quest(conn, int(quest_id))
    paid: dict[str, Any] = {"gold": 0, "xp": 0, "karma": 0, "items": [], "units": max(1, int(units or 1)), "text": ""}
    if not quest:
        paid["errors"] = ["quest_not_found"]
        return paid
    errors: list[str] = []
    try:
        paid.update(quest_reward_amounts(conn, quest, units=units))
    except Exception as exc:
        errors.append(f"amounts: {type(exc).__name__}: {exc}"[:200])
    try:
        if paid["gold"] or paid["xp"] or paid["karma"]:
            row = conn.execute("SELECT gold, xp, karma FROM player WHERE id = 1").fetchone()
            if row:
                gold = max(0, min(1_000_000, int(row["gold"] or 0) + int(paid["gold"])))
                xp = max(0, min(1_000_000, int(row["xp"] or 0) + int(paid["xp"])))
                karma = max(-1000, min(1000, int(row["karma"] or 0) + int(paid["karma"])))
                conn.execute("UPDATE player SET gold = ?, xp = ?, karma = ? WHERE id = 1", (gold, xp, karma))
                if paid["karma"]:
                    conn.execute(
                        "INSERT INTO karma_history (turn, delta, total, reason, visibility) VALUES (?, ?, ?, ?, ?)",
                        (int(turn), int(paid["karma"]), karma, f"Quest complete: {quest['title']}"[:900], "local"),
                    )
    except Exception as exc:
        errors.append(f"player: {type(exc).__name__}: {exc}"[:200])
    if paid["items"]:
        try:
            from app.world import _apply_inventory

            # Reward items used to ride back in advance_quest_step's result and
            # nothing read them.
            _apply_inventory(
                conn,
                [
                    {"name": name, "quantity_delta": paid["units"], "description": f"Reward for {quest['title']}."[:700]}
                    for name in paid["items"]
                ],
            )
        except Exception as exc:
            errors.append(f"items: {type(exc).__name__}: {exc}"[:200])
    try:
        giver_npc_id = int(quest["giver_npc_id"]) if quest.get("giver_npc_id") else None
        if giver_npc_id:
            from app.relationships import RELATIONSHIP_EVENTS, update_relationship

            update_relationship(
                conn,
                giver_npc_id,
                reason=f"Player completed quest {quest_id}",
                **RELATIONSHIP_EVENTS["quest_complete_for_npc"],
            )
    except Exception as exc:
        errors.append(f"giver: {type(exc).__name__}: {exc}"[:200])
    paid["text"] = reward_text(paid)
    line = f"Quest complete: {quest['title']}{_giver_suffix(conn, quest)}"
    _offer_journal(conn, turn, f"{line}: {paid['text']}" if paid["text"] else line)
    if source:
        paid["source"] = str(source)[:40]
    if errors:
        paid["errors"] = errors
    return paid


def pay_quest_completion(conn, quest_id: int, result: dict[str, Any], *, turn: int = 0, source: str = "") -> dict[str, Any] | None:
    """Pay when ``result`` (from advance_quest_step) completed the quest; the paid amounts, else None."""
    if not result.get("completed"):
        return None
    return pay_quest_reward(conn, int(quest_id), turn=int(turn), source=source)


def complete_quest_step(conn, quest_id: int, *, turn: int = 0, to_end: bool = False, source: str = "") -> dict[str, Any]:
    """
    Finish the quest's current step (or every step, ``to_end``) and pay on
    completion (playtest #85b). The one state change for a step done, so the
    engine's matcher, the parser and the Advance step button cannot each
    journal and pay their own way. Returns
    {"ok", "code", "title", "action": "step_done"|"complete", "completed", "paid"?, "next_step"?, "error"?}.
    """
    quest = get_quest(conn, int(quest_id))
    if not quest:
        return {"ok": False, "error": "Quest not found"}
    out: dict[str, Any] = {"ok": False, "quest_id": int(quest_id), "code": quest.get("code") or _quest_code(conn, int(quest_id)), "title": quest.get("title") or ""}
    step_title = ""
    for step in quest.get("steps") or []:
        if int(step.get("step_number") or 0) == int(quest.get("current_step") or 0):
            step_title = str(step.get("title") or "")
    res: dict[str, Any] = {}
    for _ in range(MAX_QUEST_STEPS if to_end else 1):
        res = advance_quest_step(conn, int(quest_id), turn=int(turn))
        if not res.get("ok") or res.get("completed"):
            break
    out["ok"] = bool(res.get("ok"))
    if not out["ok"]:
        out["error"] = res.get("error") or "not advanced"
        return out
    out["completed"] = bool(res.get("completed"))
    out["action"] = "complete" if out["completed"] else "step_done"
    if out["completed"]:
        out["paid"] = pay_quest_reward(conn, int(quest_id), turn=int(turn), source=source)
    else:
        out["next_step"] = res.get("next_step")
        _offer_journal(conn, turn, f"Step done: {quest['title']}" + (f" ({step_title})" if step_title and step_title != quest["title"] else ""))
    return out


MAX_QUEST_STEPS = 6


# ---------------------------------------------------------------------------
# A quest task done in play (playtest #85b)
# ---------------------------------------------------------------------------
# "i polish the blades the best i can" at the armory, with "Polish swords"
# active there, advanced nothing: only the quest parser could move a step,
# and its model returned no update. The engine now reads the player's own
# declared act against each open step before the prose is written.

# The checks' own reading of a quest's difficulty (quests say "deadly").
QUEST_CHECK_DIFFICULTY = {"trivial": "trivial", "easy": "easy", "normal": "normal", "hard": "hard", "deadly": "brutal"}
# A step is done only on these; a partial job is visibly not finished.
STEP_DONE_OUTCOMES = frozenset({"success", "critical_success"})

_STEP_STOP_WORDS = frozenset({
    "the", "and", "for", "with", "this", "that", "these", "those", "some", "any", "all", "you", "your", "his", "her",
    "their", "them", "they", "him", "she", "its", "our", "from", "into", "onto", "then", "than", "can", "best",
    "try", "tries", "trying", "start", "starting", "starts", "help", "helping", "helps", "more", "about", "again",
    "just", "will", "would", "could", "should", "here", "there", "what", "who", "how", "where", "when", "why",
    "learn", "learning", "work", "job", "task", "finish", "carefully", "quickly", "well", "good", "very", "few",
    "one", "two", "each", "every", "other", "own", "out", "off", "over", "under", "around", "back", "now",
})
# Words the prose and the quest text use for one thing (TODO: grow with play).
_STEP_SYNONYMS = {
    "blade": "sword", "sabre": "sword", "saber": "sword",
    "shine": "polish", "buff": "polish", "burnish": "polish",
    "hone": "sharpen", "whet": "sharpen",
    "mend": "repair", "fix": "repair",
    "scrub": "clean", "wash": "clean",
    "carry": "haul", "lug": "haul",
}
_STEP_WORD_RE = re.compile(r"[a-z]+")
_QUESTION_RE = re.compile(r"^\s*(?:who|what|where|when|why|how|which|is|are|do|does|can|could|would|will|should)\b|\?\s*$", re.I)


def _word_forms(word: str) -> set[str]:
    from app.skill_checks import _word_stems

    forms = {word, *_word_stems(word)}
    return forms | {_STEP_SYNONYMS[f] for f in forms if f in _STEP_SYNONYMS}


def _content_words(text: str, *, drop: set[str] | None = None) -> list[set[str]]:
    out = []
    for word in _STEP_WORD_RE.findall(str(text or "").lower()):
        if len(word) < 3 or word in _STEP_STOP_WORDS or (drop and word in drop):
            continue
        out.append(_word_forms(word))
    return out


def _overlap(player_words: list[set[str]], forms: set[str]) -> list[str]:
    return [sorted(w)[0] for w in player_words if w & forms]


def match_quest_step(
    own_line: str,
    quests: list[dict[str, Any]],
    *,
    location_code: str = "",
    present_npc_ids: set[int] | None = None,
) -> dict[str, Any] | None:
    """
    The one open quest step the player's own line is doing, or None (playtest #85b).

    Pure. The line must declare a hands-on act (prose_state.act_rules, the
    reading the dice use). A step counts when the act's verb, or a verb of the
    same family, is in the step's or quest's text together with a word of the
    line that is not the verb (what it is done to), or two such words are;
    when the step names a place, the player is there; when it names the giver,
    or is at the giver's own place, the giver is here. At most one quest is
    returned, so one "polish" cannot finish two quests that both mention
    polishing: the most words, then the most in the quest's title, then the
    oldest. ``candidate_ids`` lists every quest the act matched, the pick
    included, so the parser cannot finish a sibling for the same act.
    Each quest needs "id", "code", "title", "current_step", "total_steps",
    "steps" and optionally "giver_npc_id", "giver_name", "giver_location_code",
    "difficulty".
    """
    own = str(own_line or "").strip()
    if not own or own.startswith("__") or _QUESTION_RE.search(own):
        return None
    try:
        from app.prose_state import _ACT_FAMILIES, act_rules

        act = act_rules(own)
    except Exception:
        return None
    if not act:
        return None
    family_verbs = set(dict(_ACT_FAMILIES).get(act["family"]) or ())
    verb_forms = _word_forms(act["verb"])
    # Every form of the act's own verbs: a line's verb is not also its object
    # (#85 review: "i polish my boots" finished "Polish swords" on "polish" alone).
    all_verb_forms = set(verb_forms)
    for verb in family_verbs:
        all_verb_forms |= _word_forms(verb)
    present = set(present_npc_ids or set())
    here = str(location_code or "").strip().upper()
    best: tuple[tuple[int, int, int], dict[str, Any]] | None = None
    # Every quest this act would do, so the turn can close all of them to the
    # parser, not only the one the engine picked (#85 review: Q2 beside Q1).
    candidates: list[int] = []
    for quest in quests or []:
        if str(quest.get("status") or "active") != "active":
            continue
        current = int(quest.get("current_step") or 0)
        step = next((s for s in quest.get("steps") or [] if int(s.get("step_number") or 0) == current), None)
        if not step:
            continue
        step_place = str(step.get("location_code") or "").strip().upper()
        if step_place and here and step_place != here:
            continue  # the work is somewhere else
        giver_name = str(quest.get("giver_name") or "").strip()
        step_text = f"{step.get('title') or ''} {step.get('description') or ''}"
        giver_first = giver_name.split()[0].lower() if giver_name else ""
        giver_away = bool(quest.get("giver_npc_id")) and int(quest["giver_npc_id"]) not in present
        giver_place = str(quest.get("giver_location_code") or "").strip().upper()
        if giver_away and (
            (giver_first and giver_first in step_text.lower()) or (step_place and giver_place and step_place == giver_place)
        ):
            # "helping Finnian polish" needs Finnian here, and so does work at
            # the giver's own place whether the step names them or not (#85
            # review: with Finnian out, the same polish finished Q2 instead).
            continue
        drop = {giver_first} if giver_first else set()
        words = _content_words(own, drop=drop)
        text_forms: set[str] = set()
        for forms in _content_words(f"{step_text} {quest.get('title') or ''}", drop=drop):
            text_forms |= forms
        title_forms: set[str] = set()
        for forms in _content_words(str(quest.get("title") or ""), drop=drop):
            title_forms |= forms
        hits = _overlap(words, text_forms)
        object_hits = _overlap([w for w in words if not (w & all_verb_forms)], text_forms)
        verb_hit = bool(verb_forms & text_forms) or bool(family_verbs & text_forms)
        # The verb plus something it is done to, or two such words.
        if not ((verb_hit and object_hits) or len(set(object_hits)) >= 2):
            continue
        candidates.append(int(quest.get("id") or 0))
        score = (len(set(hits)) + (1 if verb_hit else 0), len(set(_overlap(words, title_forms))), -int(quest.get("id") or 0))
        if best is None or score > best[0]:
            best = (
                score,
                {
                    "quest_id": int(quest.get("id") or 0),
                    "code": str(quest.get("code") or f"Q{quest.get('id')}"),
                    "title": str(quest.get("title") or ""),
                    "step_number": current,
                    "step": str(step.get("title") or "")[:120],
                    "objective": str(step.get("description") or "")[:240],
                    "total_steps": int(quest.get("total_steps") or 1),
                    "completes_quest": current >= int(quest.get("total_steps") or 1),
                    "difficulty": str(quest.get("difficulty") or "normal"),
                    "giver_npc_id": quest.get("giver_npc_id"),
                    "giver_name": giver_name,
                    "giver_present": not giver_away,
                    "matched": sorted(set(hits))[:6],
                    "act": act,
                },
            )
    if not best:
        return None
    return {**best[1], "candidate_ids": candidates}


def _quests_with_status(conn, status: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM quests WHERE status = ? ORDER BY created_turn DESC, id DESC", (status,)
    ).fetchall()
    result = []
    for row in rows:
        quest = dict(row)
        quest["reward_items"] = json.loads(quest.get("reward_items") or "[]")
        steps = conn.execute(
            "SELECT * FROM quest_steps WHERE quest_id = ? ORDER BY step_number",
            (quest["id"],),
        ).fetchall()
        visible_steps = []
        current = quest["current_step"]
        for s in steps:
            sd = dict(s)
            # Hide steps that are hidden and not yet revealed
            if sd["hidden"] and sd["step_number"] > current:
                rev_at = sd["revealed_at_step"]
                if rev_at == 0 or current < rev_at:
                    sd["description"] = "[Hidden — reveals on arrival]"
            visible_steps.append(sd)
        quest["steps"] = visible_steps
        result.append(quest)
    return result


def get_quest(conn, quest_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM quests WHERE id = ?", (quest_id,)).fetchone()
    if not row:
        return None
    quest = dict(row)
    quest["reward_items"] = json.loads(quest.get("reward_items") or "[]")
    steps = conn.execute(
        "SELECT * FROM quest_steps WHERE quest_id = ? ORDER BY step_number",
        (quest_id,),
    ).fetchall()
    quest["steps"] = [dict(s) for s in steps]
    return quest


def advance_quest_step(conn, quest_id: int, *, turn: int = 0) -> dict[str, Any]:
    """Mark current step complete and advance to next. Returns result dict."""
    quest = get_quest(conn, quest_id)
    if not quest:
        return {"ok": False, "error": "Quest not found"}
    if quest["status"] != "active":
        return {"ok": False, "error": f"Quest is {quest['status']}"}

    current = quest["current_step"]
    total = quest["total_steps"]

    # Mark current step done
    conn.execute(
        "UPDATE quest_steps SET status = 'completed', completed_turn = ? WHERE quest_id = ? AND step_number = ?",
        (int(turn), quest_id, current),
    )

    if current >= total:
        # Quest complete
        conn.execute(
            "UPDATE quests SET status = 'completed', completed_turn = ?, current_step = ? WHERE id = ?",
            (int(turn), total, quest_id),
        )
        return {
            "ok": True,
            "completed": True,
            "quest_id": quest_id,
            "reward_gold": quest["reward_gold"],
            "reward_xp": quest["reward_xp"],
            "reward_items": quest["reward_items"],
        }
    else:
        next_step = current + 1
        conn.execute(
            "UPDATE quests SET current_step = ? WHERE id = ?",
            (next_step, quest_id),
        )
        # Activate next step
        conn.execute(
            "UPDATE quest_steps SET status = 'active' WHERE quest_id = ? AND step_number = ?",
            (quest_id, next_step),
        )
        # Reveal any hidden steps that unlock at this step
        conn.execute(
            "UPDATE quest_steps SET hidden = 0 WHERE quest_id = ? AND revealed_at_step = ?",
            (quest_id, next_step),
        )
        return {"ok": True, "completed": False, "quest_id": quest_id, "next_step": next_step}


def fail_quest(conn, quest_id: int, *, turn: int = 0, reason: str = "") -> None:
    conn.execute(
        "UPDATE quests SET status = 'failed', failed_turn = ?, notes = ? WHERE id = ?",
        (int(turn), str(reason), quest_id),
    )


def tick_quest_timers(conn, *, turn: int = 0) -> list[int]:
    """Decrement timer for all timed active quests. Returns list of failed quest ids."""
    rows = conn.execute(
        "SELECT id, turns_remaining FROM quests WHERE status = 'active' AND timer_turns > 0"
    ).fetchall()
    failed = []
    for row in rows:
        remaining = int(row["turns_remaining"]) - 1
        if remaining <= 0:
            fail_quest(conn, int(row["id"]), turn=turn, reason="Time expired")
            failed.append(int(row["id"]))
        else:
            conn.execute(
                "UPDATE quests SET turns_remaining = ? WHERE id = ?",
                (remaining, int(row["id"])),
            )
    return failed


def seed_starter_quests(conn, *, turn: int = 0) -> None:
    """Add a few starter quests to seed the world. Idempotent."""
    try:
        from app.local_intel import _play_flag_on

        if not _play_flag_on(conn, "quests_enabled"):
            return
    except Exception:
        pass
    existing = conn.execute("SELECT COUNT(*) FROM quests").fetchone()[0]
    if existing > 0:
        return

    # Discover what towns actually exist on the map (if any) for snapping
    _town_names: list[str] = []
    try:
        from app.tile_world import get_map, list_settlements
        _md = get_map()
        if _md:
            _town_names = [
                str(s.get("name") or "")
                for s in list_settlements(_md)
                if s.get("name") and s.get("x") is not None and s.get("y") is not None
            ]
    except Exception:
        pass
    # Pick up to two town names for seeded quest destinations (falls back to
    # generic empty location_name when no map exists yet)
    _dest1 = _town_names[0] if len(_town_names) > 0 else ""
    _dest2 = _town_names[1] if len(_town_names) > 1 else _dest1

    # Quest 1: Simple delivery
    create_quest(
        conn,
        title="The Sealed Letter",
        description="A dying courier pressed a sealed letter into your hands. Find out who it is addressed to and deliver it.",
        steps=[
            {"title": "Read the letter", "description": "Examine the sealed letter to find the recipient's name.", "location_code": ""},
            {"title": "Find the recipient", "description": "Locate the person named on the letter.", "location_code": "", "location_name": _dest1},
            {"title": "Deliver the letter", "description": "Hand it over — and decide whether you mention the courier's fate.", "location_code": "", "location_name": _dest1},
        ],
        reward_gold=30,
        reward_xp=60,
        difficulty="easy",
        created_turn=turn,
    )

    # Quest 2: Investigation chain
    create_quest(
        conn,
        title="The Missing Grain",
        description="Half a shipment of grain has gone missing between the mill and the market. The miller blames the carter. The carter blames the miller.",
        steps=[
            {"title": "Talk to the miller", "description": "Get the miller's side of the story.", "location_code": "", "location_name": _dest1},
            {"title": "Talk to the carter", "description": "Get the carter's account. Note any contradictions.", "location_code": "", "location_name": _dest2},
            {"title": "Find the grain", "description": "Investigate what actually happened.", "location_code": "", "hidden": True, "revealed_at_step": 2},
            {"title": "Settle the dispute", "description": "Bring what you found back to the parties.", "location_code": "", "location_name": _dest1, "hidden": True, "revealed_at_step": 3},
        ],
        reward_gold=50,
        reward_xp=80,
        difficulty="normal",
        created_turn=turn,
    )

    # Quest 3: Timed urgent quest
    create_quest(
        conn,
        title="Before the Gate Closes",
        description="A traveller needs a specific herb from the market before the east gate closes at dusk. They cannot walk that far.",
        steps=[
            {"title": "Buy the herb", "description": "Find it at the apothecary or the market stalls.", "location_code": "", "location_name": _dest2},
            {"title": "Return before dusk", "description": "Deliver the herb before the gate closes.", "location_code": "", "location_name": _dest1},
        ],
        reward_gold=20,
        reward_xp=35,
        difficulty="easy",
        timer_turns=8,
        created_turn=turn,
    )


def quest_context_for_llm(conn) -> list[dict[str, Any]]:
    """Compact quest state for LLM injection."""
    try:
        quests = get_active_quests(conn)
    except Exception:
        return []
    out = []
    for q in quests:
        current_step = next((s for s in q["steps"] if s["step_number"] == q["current_step"]), None)
        entry: dict[str, Any] = {
            "code": q["code"],
            "title": q["title"],
            "status": q["status"],
            "current_step": q["current_step"],
            "total_steps": q["total_steps"],
            "reward": f"{q['reward_gold']}g / {q['reward_xp']}xp",
            "current_objective": current_step["description"] if current_step else "",
        }
        if q.get("turns_remaining", 0) > 0:
            entry["turns_remaining"] = q["turns_remaining"]
        out.append(entry)
    return out
