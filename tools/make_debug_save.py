"""
Build a rich debug world and write it out as an importable `ai-rpg-world-v1` save.

Hand-testing kept needing a world that already had things in it -- gold to spend,
a locked power with a prerequisite, a half-empty mana bar, a shop with a keeper
behind the counter, somewhere far away to walk back from. Starting a fresh
playthrough gives none of that, and each setup costs a model call.

This writes the world into a temp database and exports it, so it never touches
`data/world.db`. Load it from the UI's Import, or POST the file to /api/import.

    python tools/make_debug_save.py                    # -> data/debug-save.json
    python tools/make_debug_save.py path/to/save.json

What it contains, and why each piece is there:

  * Brimmer Square plus three venues on it (apothecary, smithy, inn) and two
    places out of town -- so "re-enter the shop from the square" and "walk back
    to the shop from the forest" are both testable without a model call.
  * A keeper NPC in each venue, plus travellers, so shop interactions have
    somebody to talk to.
  * Inventory covering every case that behaves differently: equipped weapon and
    armour, a stacking consumable, a container, a quest item, a heavy thing that
    strains capacity, and an item that grants an ability.
  * Four abilities: one plain, one costing mana, one costing energy plus fatigue,
    and one locked behind a prerequisite.
  * Resources deliberately part-spent (health, mana, energy, fatigue) so regen,
    costs, and collapse thresholds are all reachable from the first turn.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


# (name, summary, visits, parent, kind) -- parent "" means an open-world place.
# The three venues are children of the square, so entering one is a real move,
# they can only be entered from the square, and they keep their own opening hours.
LOCATIONS: list[tuple[str, str, int, str, str]] = [
    ("Brimmer Square", "A cobbled market square ringed by shopfronts. Carts crowd the middle by noon.", 6, "", ""),
    ("Brimmer Apothecary", "A narrow shop off the square. Shelves of jars, a counter worn smooth, a back room behind a curtain.", 3, "Brimmer Square", "apothecary"),
    ("Brimmer Smithy", "An open-fronted forge on the square's north side. Heat, hammer noise, and a rack of finished work.", 2, "Brimmer Square", "smithy"),
    ("The Kettle and Crow", "An inn on the square's east corner. Common room downstairs, four let rooms above.", 4, "Brimmer Square", "inn"),
    ("East Road", "The rutted road out of town, running between hedgerows toward the hills.", 2, "", ""),
    ("Thistle Woods", "Close-grown woodland an hour east of town. Little light reaches the floor.", 1, "", ""),
]

# (code, name, location, role, attitude, summary)
NPCS: list[tuple[str, str, str, str, str, str]] = [
    ("A", "Aria Fenn", "Brimmer Apothecary", "apothecary", "friendly",
     "Keeps the apothecary. Sharp about prices, softer about people who are actually ill."),
    ("B", "Gedra Holt", "Brimmer Smithy", "blacksmith", "neutral",
     "Runs the forge alone since her brother left. Will not be hurried."),
    ("C", "Tam Willowes", "The Kettle and Crow", "innkeeper", "friendly",
     "Pours, listens, and remembers. Knows who owes what to whom."),
    ("D", "Ost Rell", "Brimmer Square", "carter", "neutral",
     "Hauls grain between the square and the river landings. Always half-late."),
    ("E", "Sella Marsh", "Brimmer Square", "grain factor", "wary",
     "Buys and resells the season's grain. Watches the gate for competitors."),
    ("F", "Kip Danner", "East Road", "road warden", "wary",
     "Walks the road between town and the woods. Suspicious of couriers."),
]

# (code, name, description, qty, weight, type, rarity, equipped_slot, extras)
ITEMS: list[dict] = [
    {"code": "I1", "name": "Worn Short Sword", "description": "A serviceable blade, edge rolled in two places.",
     "quantity": 1, "weight": 3.0, "item_type": "weapon", "rarity": "common", "equipped_slot": "main_hand",
     "stat_modifiers": json.dumps({"attack": 2})},
    {"code": "I2", "name": "Boiled Leather Jerkin", "description": "Cheap armour that has already saved somebody once.",
     "quantity": 1, "weight": 6.0, "item_type": "armor", "rarity": "common", "equipped_slot": "torso",
     "stat_modifiers": json.dumps({"defense": 2})},
    {"code": "I3", "name": "Bitterroot Draught", "description": "Foul-tasting. Closes small wounds within the hour.",
     "quantity": 4, "weight": 0.3, "item_type": "consumable", "rarity": "common", "equipped_slot": "",
     "stack_limit": 10},
    {"code": "I4", "name": "Courier's Satchel", "description": "Oiled canvas. Carries more than it looks like it should.",
     "quantity": 1, "weight": 1.5, "item_type": "container", "rarity": "uncommon", "equipped_slot": "back",
     "container_bonus_weight": 8.0, "container_bonus_slots": 4},
    {"code": "I5", "name": "Sealed Letter", "description": "Wax seal unbroken. The address is a name, not a place.",
     "quantity": 1, "weight": 0.1, "item_type": "quest", "rarity": "unique", "equipped_slot": ""},
    {"code": "I6", "name": "Iron Anvil Weight", "description": "Absurdly heavy. Here so carry-capacity limits are reachable.",
     "quantity": 1, "weight": 40.0, "item_type": "misc", "rarity": "common", "equipped_slot": ""},
    {"code": "I7", "name": "Emberglass Lens", "description": "Warm to the touch. Focuses more than light.",
     "quantity": 1, "weight": 0.4, "item_type": "focus", "rarity": "rare", "equipped_slot": "off_hand",
     "power_codes": "P2"},
    {"code": "I8", "name": "Copper Bits", "description": "Loose local coin, below the value of a gold mark.",
     "quantity": 37, "weight": 0.01, "item_type": "currency", "rarity": "common", "equipped_slot": "",
     "stack_limit": 200},
]

# (code, name, description, locked, power_type, cost, prerequisites, resource_cost)
ABILITIES: list[dict] = [
    {"code": "P1", "name": "Steady Hand", "description": "Your grip does not shake, however long the wait.",
     "locked": 0, "power_type": "passive", "cost": "no cost", "prerequisites": "", "resource_cost": ""},
    {"code": "P2", "name": "Emberglass Focus", "description": "Draw heat through the lens and hold it as a working flame.",
     "locked": 0, "power_type": "linear", "cost": "3 mana", "prerequisites": "", "resource_cost": "mana:3"},
    {"code": "P3", "name": "Courier's Sprint", "description": "A burst of road speed you pay for afterwards.",
     "locked": 0, "power_type": "flat", "cost": "6 energy, 4 fatigue", "prerequisites": "", "resource_cost": "energy:6,fatigue:4"},
    {"code": "P4", "name": "Ash Reading", "description": "Read what burned here, and roughly when.",
     "locked": 1, "power_type": "compounding", "cost": "5 mana", "prerequisites": "Spend a night at a fire that burned something worth reading.",
     "resource_cost": "mana:5"},
]

SKILLS: list[tuple[str, int, str]] = [
    ("Road Lore", 4, "Reads tracks, weather, and how far a cart got before dark."),
    ("Bargaining", 3, "Knows what a thing is worth in two towns, not just this one."),
    ("Short Blades", 2, "Trained enough not to embarrass themselves."),
    ("Herb Craft", 1, "Can name a plant. Cannot reliably use one."),
    ("Letters", 5, "Reads and writes cleanly, which is rarer here than it sounds."),
]

JOURNAL: list[tuple[int, str, str]] = [
    (1, "narration", "Ash reached Brimmer Square with the seal still unbroken."),
    (2, "event", "Aria Fenn agreed to hold a draught back for them, on credit."),
    (3, "dice", "Bargaining check vs Sella Marsh: rolled 14 + 3 = 17 against 15. Success."),
    (4, "narration", "The road warden asked twice who the letter was for."),
]

EVENTS: list[dict] = [
    {"code": "E1", "title": "The unbroken seal", "location": "Brimmer Square",
     "summary": "A courier is carrying a letter addressed to a person, not a place. Several people have noticed.",
     "status": "open", "persistence": "persistent", "fame_score": 12, "fame_scope": "local"},
    {"code": "E2", "title": "Short season at the forge", "location": "Brimmer Smithy",
     "summary": "Gedra Holt is behind on commissions and will trade work for materials.",
     "status": "open", "persistence": "recurring", "fame_score": 4, "fame_scope": "local"},
]


def build(destination: Path) -> Path:
    temp = Path(tempfile.mkdtemp(prefix="morkyn_debug_save_"))
    for key, val in {
        "AI_RPG_DB": str(temp / "world.db"),
        "AI_RPG_SOURCE_INDEX": str(temp / "source_index"),
        "AI_RPG_HISTORY_SUMMARY": str(temp / "history.jsonl"),
        "AI_RPG_CONSOLIDATED_FACTS": str(temp / "facts.jsonl"),
        "AI_RPG_CAMPAIGN_SLOTS": str(temp / "slots"),
        "AI_RPG_MODEL_TRACE_DIR": str(temp / "traces"),
        "AI_RPG_PACK_DIR": str(temp / "packs"),
        "AI_RPG_SKILL_LIBRARY": str(temp / "skill_library.json"),
    }.items():
        os.environ[key] = val
    sys.path.insert(0, str(ROOT))

    from app import venues
    from app.db import connect, db_path, init_db
    from app.world import export_world

    if not str(db_path()).startswith(str(temp)):
        raise SystemExit(f"refusing to build: AI_RPG_DB resolved to {db_path()!r}, outside {temp}")

    init_db()
    with connect() as conn:
        # init_db seeds a default L1 "Mosswake Gate" and a blank player row; this
        # world replaces both rather than sitting alongside them.
        # Player first: player.current_location_id has a foreign key onto locations.
        conn.execute("DELETE FROM player")
        conn.execute("DELETE FROM npcs")
        conn.execute("DELETE FROM locations")
        loc_ids: dict[str, int] = {}
        for index, (name, summary, visits, parent, kind) in enumerate(LOCATIONS, start=1):
            open_minute, close_minute = venues.default_hours(kind) if kind else (-1, -1)
            conn.execute(
                """
                INSERT INTO locations
                    (code, name, summary, visit_count, parent_id, kind,
                     open_minute, close_minute, settlement_size)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (f"L{index}", name, summary, visits, loc_ids.get(parent, 0), kind,
                 open_minute, close_minute, "town" if not parent else ""),
            )
            loc_ids[name] = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

        # Pin each venue's keeper once the NPCs exist (done below, after inserts).

        conn.execute(
            """
            INSERT INTO player (
                id, name, health, max_health, level, xp, gold, karma,
                energy, max_energy, mana, max_mana, fatigue, max_fatigue,
                public_name, title, age, sex, backstory_mode, backstory,
                memory_policy, current_location_id
            ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "Ash", 34, 48, 5, 1250, 86, 3,
                # part-spent on purpose: regen, costs and collapse are all reachable
                22, 40, 9, 24, 17, 50,
                "Ash", "Courier", 27, "unspecified", "known",
                "A road courier carrying a sealed letter and older debts. Grew up two towns west.",
                "known", loc_ids["Brimmer Square"],
            ),
        )

        for code, name, location, role, attitude, summary in NPCS:
            conn.execute(
                """
                INSERT INTO npcs (code, location_id, name, race, role, summary, attitude, trust, presence, shell)
                VALUES (?, ?, ?, 'human', ?, ?, ?, ?, 'present', 0)
                """,
                (code, loc_ids[location], name, role, summary, attitude, 40 if attitude == "friendly" else 20),
            )

        # Bind the keeper of each venue so the shop has the same person behind the
        # counter on every visit rather than a freshly invented stranger.
        for venue_name in ("Brimmer Apothecary", "Brimmer Smithy", "The Kettle and Crow"):
            keeper = conn.execute(
                "SELECT id FROM npcs WHERE location_id = ? ORDER BY id LIMIT 1", (loc_ids[venue_name],)
            ).fetchone()
            if keeper:
                conn.execute(
                    "UPDATE locations SET keeper_npc_id = ? WHERE id = ?",
                    (int(keeper["id"]), loc_ids[venue_name]),
                )

        for item in ITEMS:
            columns = ["code", "name", "description", "quantity", "weight", "item_type", "rarity", "equipped_slot"]
            values = [item[c] for c in columns]
            for extra in ("stat_modifiers", "stack_limit", "container_bonus_weight",
                          "container_bonus_slots", "power_codes"):
                if extra in item:
                    columns.append(extra)
                    values.append(item[extra])
            conn.execute(
                f"INSERT INTO inventory ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
                values,
            )

        for ability in ABILITIES:
            conn.execute(
                """
                INSERT INTO abilities (code, name, description, locked, power_type, cost, prerequisites, resource_cost, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'debug_save')
                """,
                (ability["code"], ability["name"], ability["description"], ability["locked"],
                 ability["power_type"], ability["cost"], ability["prerequisites"], ability["resource_cost"]),
            )

        for name, value, notes in SKILLS:
            conn.execute("INSERT INTO player_skills (name, value, notes) VALUES (?, ?, ?)", (name, value, notes))

        for turn, kind, content in JOURNAL:
            conn.execute("INSERT INTO journal (turn, kind, content) VALUES (?, ?, ?)", (turn, kind, content))

        for event in EVENTS:
            conn.execute(
                """
                INSERT INTO events (code, location_id, title, summary, status, persistence, fame_score, fame_scope, turn)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 4)
                """,
                (event["code"], loc_ids[event["location"]], event["title"], event["summary"],
                 event["status"], event["persistence"], event["fame_score"], event["fame_scope"]),
            )

        # Playthrough options gate real mechanics: with no magic_level the whole
        # mana pool is forced to 0/0, so a debug save without these cannot test
        # mana costs at all.
        options = {
            "world_style": "frontier dark fantasy",
            "tech_level": "medieval",
            "magic_level": "rare",
            "difficulty": "normal",
            "narration_detail": "balanced",
            "leveling_system": True,
            "game_system": False,
            "skill_style": "standard",
            "skill_levels_enabled": True,
            "proficiency_system": True,
            "proficiency_access": "learned",
            "skill_growth_speed": "normal",
            "xp_growth_speed": "normal",
            "dice_checks_enabled": True,
            "start_location": "Brimmer Square",
        }
        for key, value in (
            ("setup_complete", "true"),
            ("playthrough_options", json.dumps(options)),
        ):
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

        for key, value in (("turn", "4"), ("world_day", "3"), ("world_minute", "560"),
                           ("world_epoch_label", "frontier dark fantasy")):
            conn.execute(
                "INSERT INTO pacing (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    payload = export_world()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return destination


def main(argv: list[str]) -> int:
    destination = Path(argv[1]) if len(argv) > 1 else (ROOT / "data" / "debug-save.json")
    written = build(destination)
    size_kb = written.stat().st_size / 1024
    print(f"wrote {written}  ({size_kb:.0f} KB)")
    print()
    print("Load it with the UI's Import button, or:")
    print(f'  curl -X POST http://127.0.0.1:8000/api/import -H "Content-Type: application/json" -d @"{written}"')
    print()
    print("Importing REPLACES the current world. Export your real save first if you want it back.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
