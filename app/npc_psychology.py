"""
Hidden NPC psychology layer — narrator-only, never exposed to the player.

Three tables track the deep inner life of NPCs:
  - npc_private_feelings  : emotional states (romantic interest, resentment, etc.)
  - npc_agendas           : active hidden goals (revenge, seduction, manipulation…)
  - npc_family_ties       : kinship bonds between existing NPCs

The player sees only the affinity/fear/respect badges from relationships.py.
Everything here is narrator-side: injected into the LLM system prompt, never
into the player-facing state, and never exposed by the turn API.

Public API
----------
init_psychology_tables(conn)          — idempotent CREATE TABLE IF NOT EXISTS
trigger_private_feeling(...)          — create/update a private feeling
get_npc_psychology_context(npc_id)    — compact narrator text block
check_agenda_triggers(npc_id, ...)    — evaluate whether an agenda fires this turn
try_reveal_feeling(npc_id, ...)       — probabilistic disclosure decision
get_scene_psychology_context(conn, npc_ids) — bulk narrator block for a scene
on_npc_killed(conn, npc_id, turn)     — family-tie resentment cascade
auto_seed_feeling_from_affinity(...)  — called by relationships.py on big deltas
seed_demo_psychology(conn)            — three demonstration scenarios
"""
from __future__ import annotations

import json
import random
import sqlite3
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FEELING_TYPES = frozenset({
    "ROMANTIC_INTEREST",
    "RESENTMENT",
    "SUSPICION",
    "ADMIRATION",
    "JEALOUSY",
    "GRIEF",
    "LOYALTY_CONFLICT",
})

AGENDA_TYPES = frozenset({
    "REVENGE",
    "PROTECTION",
    "MANIPULATION",
    "SEDUCTION",
    "SABOTAGE",
    "DEFECTION",
})

AGENDA_STATES = frozenset({"ACTIVE", "COMPLETED", "ABANDONED", "PAUSED"})

FAMILY_TYPES = frozenset({"PARENT", "CHILD", "SIBLING", "SPOUSE", "RIVAL_KIN"})

# Probability that a "warm" NPC reveals a private feeling when the context is right.
_REVEAL_BASE_CHANCE = 0.18
# NPCs with affinity < this are considered "cold/business" — very unlikely to reveal.
_COLD_AFFINITY_THRESHOLD = 20


# ---------------------------------------------------------------------------
# Table creation (idempotent)
# ---------------------------------------------------------------------------

def init_psychology_tables(conn: sqlite3.Connection) -> None:
    """Create the three hidden psychology tables if they do not exist."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS npc_private_feelings (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            npc_id           INTEGER NOT NULL,
            feeling_type     TEXT    NOT NULL,
            intensity        INTEGER NOT NULL DEFAULT 0,
            target_id        INTEGER,          -- player (-1) or another npc.id
            trigger_event    TEXT    NOT NULL DEFAULT '',
            turn_triggered   INTEGER NOT NULL DEFAULT 0,
            is_revealed      INTEGER NOT NULL DEFAULT 0,  -- bool
            updated_at       TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(npc_id, feeling_type, target_id),
            FOREIGN KEY (npc_id) REFERENCES npcs(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_private_feelings_npc
        ON npc_private_feelings(npc_id);

        CREATE TABLE IF NOT EXISTS npc_agendas (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            npc_id       INTEGER NOT NULL,
            agenda_type  TEXT    NOT NULL,
            target_id    INTEGER,              -- player (-1) or another npc.id
            priority     INTEGER NOT NULL DEFAULT 5,  -- 1 (low) to 10 (urgent)
            state        TEXT    NOT NULL DEFAULT 'ACTIVE',
            created_turn INTEGER NOT NULL DEFAULT 0,
            context_json TEXT    NOT NULL DEFAULT '{}',
            updated_at   TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (npc_id) REFERENCES npcs(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_agendas_npc
        ON npc_agendas(npc_id, state);

        CREATE TABLE IF NOT EXISTS npc_family_ties (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            npc_id              INTEGER NOT NULL,
            relative_id         INTEGER NOT NULL,   -- MUST be an existing npcs.id
            relationship_type   TEXT    NOT NULL,
            is_known_to_player  INTEGER NOT NULL DEFAULT 0,  -- bool
            created_at          TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(npc_id, relative_id),
            FOREIGN KEY (npc_id)     REFERENCES npcs(id) ON DELETE CASCADE,
            FOREIGN KEY (relative_id) REFERENCES npcs(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_family_ties_npc
        ON npc_family_ties(npc_id);

        CREATE INDEX IF NOT EXISTS idx_family_ties_relative
        ON npc_family_ties(relative_id);
        """
    )


# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------

def trigger_private_feeling(
    conn: sqlite3.Connection,
    npc_id: int,
    feeling_type: str,
    intensity: int,
    target_id: int | None,
    trigger_event: str,
    turn: int,
) -> dict[str, Any]:
    """
    Create or update a private feeling for an NPC.

    If a feeling of the same type toward the same target already exists,
    the intensity is *combined* (clamped to ±100) and the trigger updated
    only if the new one is stronger.
    """
    feeling_type = feeling_type.upper()
    if feeling_type not in FEELING_TYPES:
        raise ValueError(f"Unknown feeling_type: {feeling_type!r}")
    intensity = max(-100, min(100, int(intensity)))
    target_id = int(target_id) if target_id is not None else None

    existing = conn.execute(
        "SELECT id, intensity, trigger_event FROM npc_private_feelings "
        "WHERE npc_id = ? AND feeling_type = ? AND target_id IS ?",
        (npc_id, feeling_type, target_id),
    ).fetchone()

    if existing:
        combined = max(-100, min(100, int(existing["intensity"]) + intensity))
        # Only update the trigger if the new event is more intense than the old one
        new_trigger = trigger_event if abs(intensity) >= abs(int(existing["intensity"])) else str(existing["trigger_event"])
        conn.execute(
            """
            UPDATE npc_private_feelings
            SET intensity = ?, trigger_event = ?, turn_triggered = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (combined, new_trigger, turn, int(existing["id"])),
        )
        return {"action": "updated", "npc_id": npc_id, "feeling_type": feeling_type, "intensity": combined}
    else:
        conn.execute(
            """
            INSERT INTO npc_private_feelings
                (npc_id, feeling_type, intensity, target_id, trigger_event, turn_triggered)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (npc_id, feeling_type, intensity, target_id, trigger_event[:500], turn),
        )
        return {"action": "created", "npc_id": npc_id, "feeling_type": feeling_type, "intensity": intensity}


def seed_agenda(
    conn: sqlite3.Connection,
    npc_id: int,
    agenda_type: str,
    target_id: int | None,
    priority: int,
    turn: int,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Insert a new agenda row (does not replace — each plot thread is distinct)."""
    agenda_type = agenda_type.upper()
    if agenda_type not in AGENDA_TYPES:
        raise ValueError(f"Unknown agenda_type: {agenda_type!r}")
    priority = max(1, min(10, int(priority)))
    target_id = int(target_id) if target_id is not None else None
    context_json = json.dumps(context or {}, ensure_ascii=True)
    conn.execute(
        """
        INSERT INTO npc_agendas
            (npc_id, agenda_type, target_id, priority, state, created_turn, context_json)
        VALUES (?, ?, ?, ?, 'ACTIVE', ?, ?)
        """,
        (npc_id, agenda_type, target_id, priority, turn, context_json),
    )
    return {"npc_id": npc_id, "agenda_type": agenda_type, "priority": priority}


# ---------------------------------------------------------------------------
# Narrator context assembly
# ---------------------------------------------------------------------------

def get_npc_psychology_context(conn: sqlite3.Connection, npc_id: int) -> str:
    """
    Return a compact plain-text psychology summary FOR THE NARRATOR LLM ONLY.
    Never pass this to the player-facing brain prompt.

    Format example:
        [PRIVATE — narrator only]
        Aldric harbours intense resentment toward the player (triggered turn 4: player killed his brother Doran).
        Active agenda: REVENGE, priority 8 — may act within 5-10 turns.
        Private feeling: ROMANTIC_INTEREST toward player (intensity 35) — conflicted with resentment.
    """
    # Fetch NPC name
    npc_row = conn.execute("SELECT name FROM npcs WHERE id = ?", (npc_id,)).fetchone()
    if not npc_row:
        return ""
    npc_name = str(npc_row["name"])

    lines: list[str] = ["[PRIVATE — narrator only]"]

    # Feelings
    feelings = conn.execute(
        """
        SELECT pf.feeling_type, pf.intensity, pf.target_id, pf.trigger_event,
               pf.turn_triggered, pf.is_revealed,
               CASE WHEN pf.target_id = -1 THEN 'the player'
                    ELSE COALESCE(n.name, 'unknown')
               END AS target_name
        FROM npc_private_feelings pf
        LEFT JOIN npcs n ON n.id = pf.target_id AND pf.target_id != -1
        WHERE pf.npc_id = ?
        ORDER BY ABS(pf.intensity) DESC
        """,
        (npc_id,),
    ).fetchall()

    for row in feelings:
        ftype = str(row["feeling_type"])
        intensity = int(row["intensity"])
        target = str(row["target_name"])
        trigger = str(row["trigger_event"] or "")
        turn_t = int(row["turn_triggered"] or 0)
        revealed = bool(row["is_revealed"])

        strength = _intensity_label(intensity)
        trigger_note = f" (triggered turn {turn_t}: {trigger})" if trigger else ""
        reveal_note = " [already disclosed to player]" if revealed else ""
        lines.append(
            f"{npc_name} harbours {strength} {ftype.lower().replace('_', ' ')} "
            f"toward {target}{trigger_note}.{reveal_note}"
        )

    # Active agendas
    agendas = conn.execute(
        """
        SELECT ag.agenda_type, ag.priority, ag.target_id, ag.created_turn,
               ag.context_json,
               CASE WHEN ag.target_id = -1 THEN 'the player'
                    ELSE COALESCE(n.name, 'unknown')
               END AS target_name
        FROM npc_agendas ag
        LEFT JOIN npcs n ON n.id = ag.target_id AND ag.target_id != -1
        WHERE ag.npc_id = ? AND ag.state = 'ACTIVE'
        ORDER BY ag.priority DESC
        """,
        (npc_id,),
    ).fetchall()

    for row in agendas:
        atype = str(row["agenda_type"])
        priority = int(row["priority"])
        target = str(row["target_name"])
        created = int(row["created_turn"] or 0)
        try:
            ctx = json.loads(str(row["context_json"] or "{}"))
        except Exception:
            ctx = {}
        note = str(ctx.get("note") or "")
        turn_note = f", seeded turn {created}" if created else ""
        note_suffix = f" — {note}" if note else ""
        lines.append(
            f"Active agenda: {atype} against {target}, priority {priority}{turn_note}{note_suffix}."
        )

    # Family ties (narrator sees all; player only sees is_known_to_player=True ones via normal dialogue)
    ties = conn.execute(
        """
        SELECT ft.relationship_type, ft.is_known_to_player,
               n.name AS relative_name
        FROM npc_family_ties ft
        JOIN npcs n ON n.id = ft.relative_id
        WHERE ft.npc_id = ?
        """,
        (npc_id,),
    ).fetchall()

    for row in ties:
        rel_type = str(row["relationship_type"])
        rel_name = str(row["relative_name"])
        known = bool(row["is_known_to_player"])
        known_note = "" if known else " [hidden from player]"
        lines.append(f"Family: {rel_type.lower()} is {rel_name}{known_note}.")

    if len(lines) == 1:
        # Only the header — NPC has no hidden psychology
        return ""

    return "\n".join(lines)


def get_scene_psychology_context(conn: sqlite3.Connection, npc_ids: list[int]) -> str:
    """
    Bulk narrator psychology block for all NPCs currently in a scene.
    Returns empty string if none have any hidden psychology.
    """
    if not npc_ids:
        return ""
    blocks: list[str] = []
    for npc_id in npc_ids:
        try:
            block = get_npc_psychology_context(conn, npc_id)
            if block:
                blocks.append(block)
        except Exception:
            pass
    return "\n\n".join(blocks) if blocks else ""


# ---------------------------------------------------------------------------
# Agenda trigger evaluation
# ---------------------------------------------------------------------------

def check_agenda_triggers(
    conn: sqlite3.Connection,
    npc_id: int,
    world_state: dict[str, Any],
    turn: int,
) -> tuple[bool, str]:
    """
    Decide whether an active agenda fires this turn.

    Returns (should_act, action_description).
    The action_description is a narrator hint — e.g.:
        "Marta (agenda: REVENGE priority 9) finds an opportunity to act against the player."

    Firing probability:
      - priority 1-3 : 5%
      - priority 4-6 : 12%
      - priority 7-8 : 22%
      - priority 9-10: 40%
    Additional +15% if the player is in the same location as the NPC.
    """
    agendas = conn.execute(
        """
        SELECT ag.id, ag.agenda_type, ag.priority, ag.target_id, ag.context_json,
               CASE WHEN ag.target_id = -1 THEN 'the player'
                    ELSE COALESCE(n.name, 'unknown')
               END AS target_name,
               npc.name AS npc_name, npc.location_id
        FROM npc_agendas ag
        JOIN npcs npc ON npc.id = ag.npc_id
        LEFT JOIN npcs n ON n.id = ag.target_id AND ag.target_id != -1
        WHERE ag.npc_id = ? AND ag.state = 'ACTIVE'
        ORDER BY ag.priority DESC
        LIMIT 1
        """,
        (npc_id,),
    ).fetchone()

    if not agendas:
        return False, ""

    npc_name = str(agendas["npc_name"])
    atype = str(agendas["agenda_type"])
    priority = int(agendas["priority"])
    target = str(agendas["target_name"])

    # Base probability from priority
    if priority <= 3:
        base_chance = 0.05
    elif priority <= 6:
        base_chance = 0.12
    elif priority <= 8:
        base_chance = 0.22
    else:
        base_chance = 0.40

    # Proximity bonus: is player in same location as NPC?
    npc_location = int(agendas["location_id"] or 0)
    player_location = int((world_state.get("player") or {}).get("current_location_id") or 0)
    if npc_location and player_location and npc_location == player_location:
        base_chance += 0.15

    should_act = random.random() < base_chance
    if not should_act:
        return False, ""

    try:
        ctx = json.loads(str(agendas["context_json"] or "{}"))
    except Exception:
        ctx = {}

    note = str(ctx.get("note") or "")
    desc = (
        f"{npc_name} (agenda: {atype} against {target}, priority {priority}) "
        f"finds an opportunity to act."
    )
    if note:
        desc += f" Context: {note}"
    return True, desc


# ---------------------------------------------------------------------------
# Feeling revelation
# ---------------------------------------------------------------------------

def try_reveal_feeling(
    conn: sqlite3.Connection,
    npc_id: int,
    feeling_type: str,
    context: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """
    Decide probabilistically whether an NPC reveals a private feeling.

    High-status / purely business NPCs are unlikely to reveal.
    Warm/trusted NPCs are more likely.

    Returns (revealed, what_they_say).
    'what_they_say' is a narrator suggestion only if revealed=True.
    """
    feeling_type = feeling_type.upper()
    context = context or {}

    # Fetch feeling + NPC info together
    row = conn.execute(
        """
        SELECT pf.intensity, pf.target_id, pf.trigger_event, pf.is_revealed,
               n.name AS npc_name, n.personality, n.role,
               COALESCE(r.affinity, 0) AS affinity
        FROM npc_private_feelings pf
        JOIN npcs n ON n.id = pf.npc_id
        LEFT JOIN npc_player_relationships r ON r.npc_id = pf.npc_id
        WHERE pf.npc_id = ? AND pf.feeling_type = ?
        ORDER BY ABS(pf.intensity) DESC
        LIMIT 1
        """,
        (npc_id, feeling_type),
    ).fetchone()

    if not row:
        return False, ""

    if bool(row["is_revealed"]):
        # Already revealed once — can still be mentioned but is not "new"
        return True, f"{row['npc_name']} has already disclosed this feeling."

    intensity = int(row["intensity"])
    affinity = int(row["affinity"])
    personality = str(row["personality"] or "").lower()
    role = str(row["role"] or "").lower()

    # Business/cold NPCs almost never reveal
    cold_role_keywords = {"merchant", "guard", "soldier", "official", "lord", "captain", "clerk"}
    is_cold = any(kw in role for kw in cold_role_keywords) and affinity < _COLD_AFFINITY_THRESHOLD
    if is_cold:
        return False, ""

    # Base chance scaled by |intensity| and warmth
    chance = _REVEAL_BASE_CHANCE
    chance += min(0.30, abs(intensity) / 100 * 0.40)   # up to +30% for extreme intensity
    if affinity > 60:
        chance += 0.20   # trusted relationship
    elif affinity > 20:
        chance += 0.10   # friendly
    if "open" in personality or "warm" in personality or "kind" in personality:
        chance += 0.10
    if "secretive" in personality or "cold" in personality or "stoic" in personality:
        chance -= 0.15

    revealed = random.random() < max(0.0, min(1.0, chance))
    if not revealed:
        return False, ""

    # Mark as revealed
    conn.execute(
        "UPDATE npc_private_feelings SET is_revealed = 1, updated_at = CURRENT_TIMESTAMP "
        "WHERE npc_id = ? AND feeling_type = ?",
        (npc_id, feeling_type),
    )

    npc_name = str(row["npc_name"])
    trigger = str(row["trigger_event"] or "")
    what = _compose_reveal_line(npc_name, feeling_type, intensity, trigger)
    return True, what


# ---------------------------------------------------------------------------
# Family-tie cascade: NPC killed → relatives get RESENTMENT + REVENGE agenda
# ---------------------------------------------------------------------------

def on_npc_killed(conn: sqlite3.Connection, killed_npc_id: int, turn: int) -> list[dict[str, Any]]:
    """
    Called when an NPC is killed by the player.
    Checks npc_family_ties for surviving relatives and:
      - triggers RESENTMENT feeling (intensity −60 to −90) toward the player
      - seeds a REVENGE agenda (priority 7-9)

    Returns a list of side-effect reports for logging.
    """
    reports: list[dict[str, Any]] = []

    killed_row = conn.execute("SELECT name FROM npcs WHERE id = ?", (killed_npc_id,)).fetchone()
    killed_name = str(killed_row["name"]) if killed_row else f"NPC#{killed_npc_id}"

    relatives = conn.execute(
        """
        SELECT ft.npc_id, ft.relationship_type, n.name AS rel_name
        FROM npc_family_ties ft
        JOIN npcs n ON n.id = ft.npc_id
        WHERE ft.relative_id = ?
        """,
        (killed_npc_id,),
    ).fetchall()

    for row in relatives:
        rel_npc_id = int(row["npc_id"])
        rel_name = str(row["rel_name"])
        rel_type = str(row["relationship_type"])

        # Intensity: PARENT/SPOUSE/CHILD get maximum grief; SIBLING/RIVAL_KIN slightly less
        if rel_type in ("PARENT", "CHILD", "SPOUSE"):
            intensity = -(random.randint(75, 90))
            priority = random.randint(8, 10)
        else:
            intensity = -(random.randint(60, 75))
            priority = random.randint(6, 9)

        trigger = f"player killed their {rel_type.lower()} {killed_name}"

        try:
            result = trigger_private_feeling(
                conn, rel_npc_id, "RESENTMENT", intensity,
                target_id=-1,  # -1 = player
                trigger_event=trigger, turn=turn,
            )
            reports.append({"npc": rel_name, "feeling": "RESENTMENT", "intensity": intensity, **result})
        except Exception as exc:
            reports.append({"npc": rel_name, "error": str(exc)})

        try:
            agenda_result = seed_agenda(
                conn, rel_npc_id, "REVENGE", target_id=-1, priority=priority, turn=turn,
                context={"note": f"Seeks revenge for the death of {killed_name}", "trigger_turn": turn},
            )
            reports.append({"npc": rel_name, "agenda": "REVENGE", **agenda_result})
        except Exception as exc:
            reports.append({"npc": rel_name, "agenda_error": str(exc)})

    return reports


# ---------------------------------------------------------------------------
# Auto-seed from relationship affinity swings
# ---------------------------------------------------------------------------

def auto_seed_feeling_from_affinity(
    conn: sqlite3.Connection,
    npc_id: int,
    affinity_delta: int,
    new_affinity: int,
    reason: str,
    turn: int,
) -> dict[str, Any] | None:
    """
    Called by relationships.update_relationship when |delta| > 20.

    Big gain  → may seed ADMIRATION or ROMANTIC_INTEREST (low probability)
    Big loss  → may seed RESENTMENT or SUSPICION
    """
    if abs(affinity_delta) <= 20:
        return None

    if affinity_delta > 0:
        # Positive swing — admiration is more likely than romantic interest
        weights = [("ADMIRATION", 0.20), ("ROMANTIC_INTEREST", 0.08)]
        # Only seed romantic interest if NPC already has some warmth
        if new_affinity < 30:
            weights = [("ADMIRATION", 0.12)]
    else:
        # Negative swing
        if affinity_delta <= -40:
            weights = [("RESENTMENT", 0.35), ("SUSPICION", 0.20)]
        else:
            weights = [("RESENTMENT", 0.15), ("SUSPICION", 0.25)]

    for feeling_type, probability in weights:
        if random.random() < probability:
            intensity = int(affinity_delta * 0.6)  # feeling intensity proportional to swing
            try:
                return trigger_private_feeling(
                    conn, npc_id, feeling_type, intensity,
                    target_id=-1,  # toward player
                    trigger_event=reason[:300], turn=turn,
                )
            except Exception:
                pass

    return None


# ---------------------------------------------------------------------------
# Demo seed data — three illustrative scenarios
# ---------------------------------------------------------------------------

def seed_demo_psychology(conn: sqlite3.Connection) -> dict[str, Any]:
    """
    Seed three demonstration psychology scenarios using EXISTING NPCs.
    Skips gracefully if no NPCs are found.

    Scenario A — Merchant with REVENGE agenda (player wronged them or their kin)
    Scenario B — Guard with ROMANTIC_INTEREST (unrequited, never shown)
    Scenario C — Innkeeper / stable-hand with GRIEF (lost a sibling)

    Returns a report of what was created.
    """
    report: dict[str, Any] = {"seeded": [], "skipped": []}

    # Fetch up to 10 NPCs so we can assign roles
    npcs = conn.execute(
        "SELECT id, name, role, personality FROM npcs ORDER BY id LIMIT 10"
    ).fetchall()

    if not npcs:
        report["skipped"].append("no NPCs exist yet — seed will run on next startup")
        return report

    npc_list = [dict(row) for row in npcs]
    turn_row = conn.execute("SELECT value FROM pacing WHERE key = 'turn'").fetchone()
    current_turn = int(turn_row["value"]) if turn_row else 0

    # --- Scenario A: find a merchant-ish NPC ---------------------------------
    merchant = _find_npc_by_role(npc_list, {"merchant", "trader", "vendor", "shopkeeper"})
    if merchant and not _already_has_agenda(conn, int(merchant["id"]), "REVENGE"):
        npc_id = int(merchant["id"])
        try:
            trigger_private_feeling(
                conn, npc_id, "RESENTMENT", -75,
                target_id=-1, turn=current_turn,
                trigger_event="player cheated them in an old trade deal (or so they believe)",
            )
            seed_agenda(
                conn, npc_id, "REVENGE", target_id=-1, priority=8, turn=current_turn,
                context={
                    "note": "Waits for the right moment to expose the player as a swindler or take payment in blood",
                    "trigger_turn": current_turn,
                },
            )
            report["seeded"].append({
                "npc": merchant["name"], "scenario": "A",
                "feelings": ["RESENTMENT"], "agendas": ["REVENGE"],
            })
        except Exception as exc:
            report["skipped"].append({"npc": merchant["name"], "error": str(exc)})

    # --- Scenario B: find a guard / soldier NPC ------------------------------
    guard = _find_npc_by_role(npc_list, {"guard", "soldier", "watchman", "sentry", "militia"})
    if guard and not _already_has_feeling(conn, int(guard["id"]), "ROMANTIC_INTEREST"):
        npc_id = int(guard["id"])
        try:
            trigger_private_feeling(
                conn, npc_id, "ROMANTIC_INTEREST", 42,
                target_id=-1, turn=current_turn,
                trigger_event="saw the player act with unexpected courage and cannot stop thinking about it",
            )
            report["seeded"].append({
                "npc": guard["name"], "scenario": "B",
                "feelings": ["ROMANTIC_INTEREST"],
            })
        except Exception as exc:
            report["skipped"].append({"npc": guard["name"], "error": str(exc)})

    # --- Scenario C: innkeeper / tavern-keeper with GRIEF + family tie -------
    innkeeper = _find_npc_by_role(npc_list, {"innkeeper", "tavern", "barkeep", "innkeep", "host"})
    if innkeeper:
        npc_id = int(innkeeper["id"])

        # Find a second NPC to be the lost sibling (must already exist)
        sibling_candidates = [n for n in npc_list if n["id"] != npc_id]
        sibling = sibling_candidates[0] if sibling_candidates else None

        if sibling and not _already_has_feeling(conn, npc_id, "GRIEF"):
            sib_id = int(sibling["id"])
            try:
                trigger_private_feeling(
                    conn, npc_id, "GRIEF", -60,
                    target_id=sib_id, turn=current_turn,
                    trigger_event=f"lost their sibling {sibling['name']} to illness last winter — never spoke of it since",
                )
                # Record the family tie (hidden from player)
                try:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO npc_family_ties
                            (npc_id, relative_id, relationship_type, is_known_to_player)
                        VALUES (?, ?, 'SIBLING', 0)
                        """,
                        (npc_id, sib_id),
                    )
                except Exception:
                    pass
                report["seeded"].append({
                    "npc": innkeeper["name"], "scenario": "C",
                    "feelings": ["GRIEF"],
                    "family_tie": f"SIBLING → {sibling['name']} (hidden)",
                })
            except Exception as exc:
                report["skipped"].append({"npc": innkeeper["name"], "error": str(exc)})

    return report


# ---------------------------------------------------------------------------
# Full psychology dump (narrator/debug use only)
# ---------------------------------------------------------------------------

def get_full_psychology_dump(conn: sqlite3.Connection, npc_id: int) -> dict[str, Any]:
    """
    Return the complete psychology record for one NPC.
    [NARRATOR ONLY] — never expose this to the player-facing UI.
    """
    npc_row = conn.execute("SELECT * FROM npcs WHERE id = ?", (npc_id,)).fetchone()
    if not npc_row:
        return {"error": f"NPC {npc_id} not found"}

    feelings = [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM npc_private_feelings WHERE npc_id = ? ORDER BY ABS(intensity) DESC",
            (npc_id,),
        ).fetchall()
    ]
    agendas = [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM npc_agendas WHERE npc_id = ? ORDER BY priority DESC",
            (npc_id,),
        ).fetchall()
    ]
    ties_raw = conn.execute(
        """
        SELECT ft.*, n.name AS relative_name, n.role AS relative_role
        FROM npc_family_ties ft
        JOIN npcs n ON n.id = ft.relative_id
        WHERE ft.npc_id = ?
        """,
        (npc_id,),
    ).fetchall()
    ties = [dict(row) for row in ties_raw]

    narrator_block = get_npc_psychology_context(conn, npc_id)

    return {
        "npc_id": npc_id,
        "npc_name": str(npc_row["name"]),
        "private_feelings": feelings,
        "agendas": agendas,
        "family_ties": ties,
        "narrator_block": narrator_block,
        "_narrator_only": True,
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _intensity_label(intensity: int) -> str:
    abs_val = abs(intensity)
    if abs_val >= 80:
        return "intense"
    if abs_val >= 50:
        return "strong"
    if abs_val >= 25:
        return "moderate"
    return "mild"


def _compose_reveal_line(npc_name: str, feeling_type: str, intensity: int, trigger: str) -> str:
    """Generate a short narrator hint for what the NPC might say when revealing a feeling."""
    ftype = feeling_type.lower().replace("_", " ")
    strength = _intensity_label(intensity)
    trigger_note = f" (originally caused by: {trigger})" if trigger else ""
    return (
        f"{npc_name} reveals {strength} {ftype} toward the player{trigger_note}. "
        f"The narrator may weave this into their next line of dialogue."
    )


def _find_npc_by_role(npc_list: list[dict], role_keywords: set[str]) -> dict | None:
    for npc in npc_list:
        role = str(npc.get("role") or "").lower()
        if any(kw in role for kw in role_keywords):
            return npc
    return None


def _already_has_feeling(conn: sqlite3.Connection, npc_id: int, feeling_type: str) -> bool:
    row = conn.execute(
        "SELECT id FROM npc_private_feelings WHERE npc_id = ? AND feeling_type = ?",
        (npc_id, feeling_type),
    ).fetchone()
    return row is not None


def _already_has_agenda(conn: sqlite3.Connection, npc_id: int, agenda_type: str) -> bool:
    row = conn.execute(
        "SELECT id FROM npc_agendas WHERE npc_id = ? AND agenda_type = ? AND state = 'ACTIVE'",
        (npc_id, agenda_type),
    ).fetchone()
    return row is not None
