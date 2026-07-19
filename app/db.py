from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any


DB_PATH = Path(os.getenv("AI_RPG_DB", "data/world.db"))


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [row_to_dict(row) or {} for row in rows]


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS locations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE DEFAULT '',
                name TEXT NOT NULL UNIQUE,
                summary TEXT NOT NULL DEFAULT '',
                discovered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                visit_count INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS player (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                name TEXT NOT NULL,
                health INTEGER NOT NULL,
                max_health INTEGER NOT NULL,
                level INTEGER NOT NULL,
                xp INTEGER NOT NULL,
                gold INTEGER NOT NULL,
                karma INTEGER NOT NULL DEFAULT 0,
                public_name TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                age TEXT NOT NULL DEFAULT '',
                sex TEXT NOT NULL DEFAULT '',
                previous_life_age TEXT NOT NULL DEFAULT '',
                previous_life_sex TEXT NOT NULL DEFAULT '',
                backstory_mode TEXT NOT NULL DEFAULT 'known',
                backstory TEXT NOT NULL DEFAULT '',
                memory_policy TEXT NOT NULL DEFAULT 'known',
                current_location_id INTEGER,
                FOREIGN KEY (current_location_id) REFERENCES locations(id)
            );

            CREATE TABLE IF NOT EXISTS npcs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE DEFAULT '',
                location_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                race TEXT NOT NULL DEFAULT 'human',
                role TEXT NOT NULL DEFAULT 'local',
                summary TEXT NOT NULL DEFAULT '',
                attitude TEXT NOT NULL DEFAULT 'neutral',
                personality TEXT NOT NULL DEFAULT '',
                likes TEXT NOT NULL DEFAULT '',
                principles TEXT NOT NULL DEFAULT '',
                dislikes TEXT NOT NULL DEFAULT '',
                trust INTEGER NOT NULL DEFAULT 0,
                known_facts TEXT NOT NULL DEFAULT '[]',
                rank TEXT NOT NULL DEFAULT 'F',
                stat_profile TEXT NOT NULL DEFAULT '{}',
                skill_profile TEXT NOT NULL DEFAULT '{}',
                health INTEGER NOT NULL DEFAULT 0,
                max_health INTEGER NOT NULL DEFAULT 0,
                attack_min INTEGER NOT NULL DEFAULT 0,
                attack_max INTEGER NOT NULL DEFAULT 0,
                defense INTEGER NOT NULL DEFAULT 0,
                dodge INTEGER NOT NULL DEFAULT 0,
                mentioned_by TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(location_id, name),
                FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_npc_id INTEGER NOT NULL,
                target_npc_id INTEGER NOT NULL,
                summary TEXT NOT NULL,
                weight INTEGER NOT NULL DEFAULT 1,
                UNIQUE(source_npc_id, target_npc_id),
                FOREIGN KEY (source_npc_id) REFERENCES npcs(id) ON DELETE CASCADE,
                FOREIGN KEY (target_npc_id) REFERENCES npcs(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE DEFAULT '',
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                quantity INTEGER NOT NULL DEFAULT 0,
                weight REAL NOT NULL DEFAULT 1.0,
                slot_size INTEGER NOT NULL DEFAULT 1,
                item_type TEXT NOT NULL DEFAULT 'misc',
                rarity TEXT NOT NULL DEFAULT 'common',
                enchantments TEXT NOT NULL DEFAULT '[]',
                stat_modifiers TEXT NOT NULL DEFAULT '{}',
                granted_abilities TEXT NOT NULL DEFAULT '[]',
                stack_limit INTEGER NOT NULL DEFAULT 20,
                carry_modifier REAL NOT NULL DEFAULT 1.0,
                container_bonus_weight REAL NOT NULL DEFAULT 0,
                container_bonus_slots INTEGER NOT NULL DEFAULT 0,
                dimensional_space INTEGER NOT NULL DEFAULT 0,
                equipped_slot TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS equipment_slots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'gear',
                capacity INTEGER NOT NULL DEFAULT 1,
                accepts TEXT NOT NULL DEFAULT '[]',
                source_item_code TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS inventory_capacity_modifiers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL,
                weight_bonus REAL NOT NULL DEFAULT 0,
                slot_bonus INTEGER NOT NULL DEFAULT 0,
                carry_modifier REAL NOT NULL DEFAULT 1.0,
                dimensional_space INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS player_skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                value INTEGER NOT NULL DEFAULT 0,
                notes TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS abilities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                locked INTEGER NOT NULL DEFAULT 0,
                base_description TEXT NOT NULL DEFAULT '',
                cost TEXT NOT NULL DEFAULT '',
                prerequisites TEXT NOT NULL DEFAULT '',
                additions TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'setup'
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE DEFAULT '',
                location_id INTEGER,
                npc_id INTEGER,
                title TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                fame_score INTEGER NOT NULL DEFAULT 0,
                fame_scope TEXT NOT NULL DEFAULT 'local',
                rumor_summary TEXT NOT NULL DEFAULT '',
                persistence TEXT NOT NULL DEFAULT 'persistent',
                disappear_chance INTEGER NOT NULL DEFAULT 0,
                respawn_chance INTEGER NOT NULL DEFAULT 0,
                last_seen_turn INTEGER NOT NULL DEFAULT 0,
                turn INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE SET NULL,
                FOREIGN KEY (npc_id) REFERENCES npcs(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                turn INTEGER NOT NULL,
                npc_id INTEGER,
                topic TEXT NOT NULL DEFAULT '',
                summary TEXT NOT NULL,
                player_claims TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (npc_id) REFERENCES npcs(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS response_drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                turn INTEGER NOT NULL,
                claim TEXT NOT NULL,
                verdict TEXT NOT NULL,
                skill TEXT NOT NULL DEFAULT '',
                difficulty_class INTEGER NOT NULL DEFAULT 10,
                result TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alias TEXT NOT NULL UNIQUE,
                entity_type TEXT NOT NULL,
                entity_code TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS karma_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                turn INTEGER NOT NULL,
                delta INTEGER NOT NULL,
                total INTEGER NOT NULL,
                reason TEXT NOT NULL,
                visibility TEXT NOT NULL DEFAULT 'local',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS player_aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alias TEXT NOT NULL UNIQUE,
                reputation INTEGER NOT NULL DEFAULT 0,
                notes TEXT NOT NULL DEFAULT '',
                active INTEGER NOT NULL DEFAULT 0,
                disguised INTEGER NOT NULL DEFAULT 0,
                disguise_description TEXT NOT NULL DEFAULT '',
                created_turn INTEGER NOT NULL DEFAULT 0,
                last_used_turn INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS turn_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                turn INTEGER NOT NULL,
                summary TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS gm_notes (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                content TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS gm_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                turn INTEGER NOT NULL DEFAULT 0,
                trigger TEXT NOT NULL DEFAULT '',
                summary TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                priority INTEGER NOT NULL DEFAULT 3,
                location_id INTEGER,
                npc_id INTEGER,
                event_id INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE SET NULL,
                FOREIGN KEY (npc_id) REFERENCES npcs(id) ON DELETE SET NULL,
                FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS turn_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                turn INTEGER NOT NULL,
                snapshot TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS model_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                turn INTEGER NOT NULL,
                phase TEXT NOT NULL,
                chars INTEGER NOT NULL,
                estimated_tokens INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS verification_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope_key TEXT NOT NULL,
                check_name TEXT NOT NULL,
                intent TEXT NOT NULL DEFAULT '',
                turn_kind TEXT NOT NULL DEFAULT '',
                entity_codes TEXT NOT NULL DEFAULT '[]',
                confidence REAL NOT NULL DEFAULT 0,
                source TEXT NOT NULL DEFAULT '',
                last_verified_turn INTEGER NOT NULL DEFAULT 0,
                hit_count INTEGER NOT NULL DEFAULT 1,
                evidence TEXT NOT NULL DEFAULT '',
                context_signature TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(scope_key, check_name)
            );

            CREATE INDEX IF NOT EXISTS idx_verification_memory_scope
            ON verification_memory(scope_key, check_name);

            CREATE TABLE IF NOT EXISTS journal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                turn INTEGER NOT NULL,
                kind TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS pacing (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            -- Tile catalog: abstract state tags like city / waterfall / mountain
            CREATE TABLE IF NOT EXISTS tile_states (
                id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'terrain',
                elevation INTEGER NOT NULL DEFAULT 0,
                walkable INTEGER NOT NULL DEFAULT 1,
                space_ok INTEGER NOT NULL DEFAULT 0,
                tags TEXT NOT NULL DEFAULT '[]',
                description TEXT NOT NULL DEFAULT ''
            );

            -- World presets: ages, environments, weighted state mixes
            CREATE TABLE IF NOT EXISTS world_presets (
                id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                age TEXT NOT NULL DEFAULT 'medieval',
                environment TEXT NOT NULL DEFAULT 'terrestrial',
                width INTEGER NOT NULL DEFAULT 32,
                height INTEGER NOT NULL DEFAULT 32,
                weights_json TEXT NOT NULL DEFAULT '{}',
                features_json TEXT NOT NULL DEFAULT '{}',
                description TEXT NOT NULL DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 0
            );

            -- Image archive for tile art (user-made, generated, imported)
            CREATE TABLE IF NOT EXISTS tile_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                state_id TEXT NOT NULL,
                path TEXT NOT NULL DEFAULT '',
                data_url TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'user',
                prompt TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '',
                quality TEXT NOT NULL DEFAULT '8bit',
                disabled_forever INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (state_id) REFERENCES tile_states(id)
            );

            CREATE INDEX IF NOT EXISTS idx_tile_images_state ON tile_images(state_id);
            CREATE INDEX IF NOT EXISTS idx_tile_images_disabled ON tile_images(disabled_forever);

            -- Per-run suppress list (hide image for one campaign/map seed without deleting)
            CREATE TABLE IF NOT EXISTS tile_image_run_disable (
                image_id INTEGER NOT NULL,
                run_id TEXT NOT NULL,
                PRIMARY KEY (image_id, run_id),
                FOREIGN KEY (image_id) REFERENCES tile_images(id) ON DELETE CASCADE
            );

            -- Generated / active maps
            CREATE TABLE IF NOT EXISTS world_maps (
                id TEXT PRIMARY KEY,
                preset_id TEXT NOT NULL DEFAULT '',
                seed INTEGER NOT NULL DEFAULT 0,
                width INTEGER NOT NULL DEFAULT 32,
                height INTEGER NOT NULL DEFAULT 32,
                age TEXT NOT NULL DEFAULT '',
                environment TEXT NOT NULL DEFAULT '',
                tiles_json TEXT NOT NULL DEFAULT '[]',
                player_x INTEGER NOT NULL DEFAULT 0,
                player_y INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                meta_json TEXT NOT NULL DEFAULT '{}'
            );
            """
        )

        _migrate_columns(conn)
        _seed_tile_catalog(conn)

        start = conn.execute("SELECT id FROM locations WHERE name = ?", ("Mosswake Gate",)).fetchone()
        if start is None:
            start = conn.execute("SELECT id FROM locations WHERE code = ?", ("L1",)).fetchone()
        if start is None:
            cursor = conn.execute(
                "INSERT INTO locations (code, name, summary, visit_count) VALUES (?, ?, ?, ?)",
                (
                    "L1",
                    "Mosswake Gate",
                    "A damp frontier gate-town where caravans wait out the mist before entering the old roads.",
                    1,
                ),
            )
            start_id = int(cursor.lastrowid)
        else:
            start_id = int(start["id"])

        player = conn.execute("SELECT id FROM player WHERE id = 1").fetchone()
        if player is None:
            conn.execute(
                """
                INSERT INTO player (id, name, health, max_health, level, xp, gold, karma, current_location_id)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("Wanderer", 20, 20, 1, 0, 12, 0, start_id),
            )

        conn.execute("INSERT OR IGNORE INTO pacing (key, value) VALUES ('turn', '0')")
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('setup_complete', 'false')")
        conn.execute("INSERT OR IGNORE INTO gm_notes (id, content) VALUES (1, '')")


def _migrate_columns(conn: sqlite3.Connection) -> None:
    table_columns = {
        table: {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for table in ("locations", "npcs", "inventory", "events", "player", "abilities")
    }
    if "code" not in table_columns["locations"]:
        conn.execute("ALTER TABLE locations ADD COLUMN code TEXT NOT NULL DEFAULT ''")
    if "code" not in table_columns["npcs"]:
        conn.execute("ALTER TABLE npcs ADD COLUMN code TEXT NOT NULL DEFAULT ''")
    if "code" not in table_columns["inventory"]:
        conn.execute("ALTER TABLE inventory ADD COLUMN code TEXT NOT NULL DEFAULT ''")
    if "code" not in table_columns["events"]:
        conn.execute("ALTER TABLE events ADD COLUMN code TEXT NOT NULL DEFAULT ''")

    npc_columns = table_columns["npcs"]
    for column, default in (
        ("personality", "''"),
        ("race", "'human'"),
        ("likes", "''"),
        ("principles", "''"),
        ("dislikes", "''"),
        ("rank", "'F'"),
        ("stat_profile", "'{}'"),
        ("skill_profile", "'{}'"),
        ("trust", "0"),
    ):
        if column not in npc_columns:
            conn.execute(f"ALTER TABLE npcs ADD COLUMN {column} TEXT NOT NULL DEFAULT {default}" if column != "trust" else "ALTER TABLE npcs ADD COLUMN trust INTEGER NOT NULL DEFAULT 0")

    for column, definition in (
        ("health", "INTEGER NOT NULL DEFAULT 0"),
        ("max_health", "INTEGER NOT NULL DEFAULT 0"),
        ("attack_min", "INTEGER NOT NULL DEFAULT 0"),
        ("attack_max", "INTEGER NOT NULL DEFAULT 0"),
        ("defense", "INTEGER NOT NULL DEFAULT 0"),
        ("dodge", "INTEGER NOT NULL DEFAULT 0"),
    ):
        if column not in npc_columns:
            conn.execute(f"ALTER TABLE npcs ADD COLUMN {column} {definition}")

    player_columns = table_columns["player"]
    if "karma" not in player_columns:
        conn.execute("ALTER TABLE player ADD COLUMN karma INTEGER NOT NULL DEFAULT 0")
    for column, default in (
        ("public_name", "''"),
        ("title", "''"),
        ("age", "''"),
        ("sex", "''"),
        ("previous_life_age", "''"),
        ("previous_life_sex", "''"),
        ("backstory_mode", "'known'"),
        ("backstory", "''"),
        ("memory_policy", "'known'"),
    ):
        if column not in player_columns:
            conn.execute(f"ALTER TABLE player ADD COLUMN {column} TEXT NOT NULL DEFAULT {default}")

    event_columns = table_columns["events"]
    for column, definition in (
        ("fame_score", "INTEGER NOT NULL DEFAULT 0"),
        ("fame_scope", "TEXT NOT NULL DEFAULT 'local'"),
        ("rumor_summary", "TEXT NOT NULL DEFAULT ''"),
        ("persistence", "TEXT NOT NULL DEFAULT 'persistent'"),
        ("disappear_chance", "INTEGER NOT NULL DEFAULT 0"),
        ("respawn_chance", "INTEGER NOT NULL DEFAULT 0"),
        ("last_seen_turn", "INTEGER NOT NULL DEFAULT 0"),
    ):
        if column not in event_columns:
            conn.execute(f"ALTER TABLE events ADD COLUMN {column} {definition}")

    ability_columns = table_columns["abilities"]
    for column in ("base_description", "cost", "prerequisites", "additions"):
        if column not in ability_columns:
            conn.execute(f"ALTER TABLE abilities ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")

    inventory_columns = table_columns["inventory"]
    for column, definition in (
        ("weight", "REAL NOT NULL DEFAULT 1.0"),
        ("slot_size", "INTEGER NOT NULL DEFAULT 1"),
        ("item_type", "TEXT NOT NULL DEFAULT 'misc'"),
        ("rarity", "TEXT NOT NULL DEFAULT 'common'"),
        ("enchantments", "TEXT NOT NULL DEFAULT '[]'"),
        ("stat_modifiers", "TEXT NOT NULL DEFAULT '{}'"),
        ("granted_abilities", "TEXT NOT NULL DEFAULT '[]'"),
        ("stack_limit", "INTEGER NOT NULL DEFAULT 20"),
        ("carry_modifier", "REAL NOT NULL DEFAULT 1.0"),
        ("container_bonus_weight", "REAL NOT NULL DEFAULT 0"),
        ("container_bonus_slots", "INTEGER NOT NULL DEFAULT 0"),
        ("dimensional_space", "INTEGER NOT NULL DEFAULT 0"),
        ("equipped_slot", "TEXT NOT NULL DEFAULT ''"),
    ):
        if column not in inventory_columns:
            conn.execute(f"ALTER TABLE inventory ADD COLUMN {column} {definition}")

    for table, prefix in (("locations", "L"), ("inventory", "I"), ("events", "E")):
        rows = conn.execute(f"SELECT id FROM {table} WHERE code = '' OR code IS NULL ORDER BY id").fetchall()
        for row in rows:
            conn.execute(f"UPDATE {table} SET code = ? WHERE id = ?", (f"{prefix}{row['id']}", row["id"]))

    rows = conn.execute("SELECT id FROM npcs WHERE code = '' OR code IS NULL ORDER BY id").fetchall()
    for row in rows:
        conn.execute("UPDATE npcs SET code = ? WHERE id = ?", (_alpha_code(row["id"]), row["id"]))


def _alpha_code(number: int) -> str:
    result = ""
    n = max(1, number)
    while n:
        n -= 1
        result = chr(65 + (n % 26)) + result
        n //= 26
    return result


def _seed_tile_catalog(conn: sqlite3.Connection) -> None:
    """Idempotent catalog of tile states + world presets for generation weights."""
    import json

    states = [
        # elevation 0 base
        ("plains", "Plains", "terrain", 0, 1, 0, ["open", "land"], "Open ground."),
        ("forest", "Forest", "terrain", 0, 1, 0, ["wood", "land"], "Wooded land."),
        ("desert", "Desert", "terrain", 0, 1, 0, ["arid", "land"], "Dry open sand or scrub."),
        ("swamp", "Swamp", "terrain", 0, 1, 0, ["wet", "land"], "Marsh and slow water."),
        ("tundra", "Tundra", "terrain", 0, 1, 0, ["cold", "land"], "Frozen plain."),
        ("ash", "Ash plain", "terrain", 0, 1, 0, ["waste", "land"], "Burned or volcanic ash."),
        ("beach", "Beach", "terrain", 0, 1, 0, ["coast", "land"], "Shore between land and sea."),
        ("water", "Water", "terrain", 0, 0, 0, ["sea", "lake"], "Open water; not walkable."),
        ("ice", "Ice", "terrain", 0, 1, 0, ["cold"], "Frozen water surface."),
        ("road", "Road", "structure", 0, 1, 0, ["path"], "Travel route."),
        ("ruins", "Ruins", "landmark", 0, 1, 0, ["old"], "Collapsed works."),
        ("city", "City", "settlement", 0, 1, 0, ["town", "urban"], "Dense settlement."),
        ("town", "Town", "settlement", 0, 1, 0, ["settlement"], "Small settlement."),
        ("village", "Village", "settlement", 0, 1, 0, ["settlement"], "Hamlet."),
        ("farm", "Farm", "settlement", 0, 1, 0, ["rural"], "Cultivated land."),
        ("waterfall", "Waterfall", "landmark", 0, 1, 0, ["water", "feature"], "Falling water feature."),
        ("monolith", "Monolith", "landmark", 0, 1, 0, ["mystic"], "Standing stone or artifact."),
        ("dungeon", "Dungeon", "landmark", 0, 1, 0, ["danger"], "Entrance to depths."),
        ("bridge", "Bridge", "structure", 0, 1, 0, ["path"], "Crossing."),
        ("harbor", "Harbor", "settlement", 0, 1, 0, ["coast"], "Docks and ships."),
        # elevation 1 raised / mountain band
        ("hill", "Hill", "terrain", 1, 1, 0, ["high"], "Raised land, still walkable."),
        ("mountain", "Mountain", "terrain", 1, 0, 0, ["high", "peak"], "Peak mass; elevation 1, multi-tile blobs."),
        ("cliff", "Cliff", "terrain", 1, 0, 0, ["edge", "high"], "Sheer face between elevations."),
        ("volcano", "Volcano", "landmark", 1, 0, 0, ["fire", "high"], "Active or dormant vent."),
        ("mesa", "Mesa", "terrain", 1, 1, 0, ["high", "arid"], "Flat-topped high land."),
        # space / far future
        ("void", "Void", "space", 0, 0, 1, ["space"], "Empty vacuum."),
        ("nebula", "Nebula", "space", 0, 0, 1, ["space"], "Clouded space."),
        ("asteroid", "Asteroid", "space", 0, 1, 1, ["space", "rock"], "Rock body."),
        ("station", "Station", "settlement", 0, 1, 1, ["space", "urban"], "Orbital habitat."),
        ("shipyard", "Shipyard", "settlement", 0, 1, 1, ["space"], "Construction docks."),
        ("gate", "Jump gate", "landmark", 0, 1, 1, ["space", "travel"], "FTL / portal structure."),
        ("colony", "Colony dome", "settlement", 0, 1, 1, ["space", "settlement"], "Sealed colony."),
        ("wreck", "Wreck", "landmark", 0, 1, 1, ["space", "danger"], "Derelict hulk."),
        ("anomaly", "Anomaly", "landmark", 0, 0, 1, ["space", "mystic"], "Spatial distortion."),
        # subterranean
        ("cavern", "Cavern", "terrain", 0, 1, 0, ["under"], "Open cave floor."),
        ("mushroom", "Mushroom grove", "terrain", 0, 1, 0, ["under"], "Fungal forest."),
        ("lava", "Lava", "terrain", 0, 0, 0, ["fire", "under"], "Molten rock."),
        ("crystal", "Crystal field", "landmark", 0, 1, 0, ["under", "mystic"], "Crystal growths."),
    ]
    for row in states:
        sid, label, cat, elev, walk, space, tags, desc = row
        conn.execute(
            """
            INSERT OR IGNORE INTO tile_states
              (id, label, category, elevation, walkable, space_ok, tags, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (sid, label, cat, elev, walk, space, json.dumps(tags), desc),
        )

    presets = [
        {
            "id": "forest_march",
            "label": "Forest March",
            "age": "medieval",
            "environment": "terrestrial",
            "width": 32,
            "height": 32,
            "weights": {
                "plains": 28, "forest": 34, "water": 10, "hill": 8, "mountain": 6,
                "road": 4, "village": 3, "town": 2, "ruins": 2, "waterfall": 1, "monolith": 1, "dungeon": 1,
            },
            "features": {"mountain_blob_min": 2, "mountain_blob_max": 5, "water_bodies": 2, "landmark_count": 4},
            "description": "Misty wood roads, small towns, low peaks.",
            "sort_order": 10,
        },
        {
            "id": "coastal_scrap",
            "label": "Coastal Scrap",
            "age": "industrial",
            "environment": "coastal",
            "width": 32,
            "height": 32,
            "weights": {
                "water": 28, "beach": 14, "plains": 18, "city": 4, "harbor": 4,
                "road": 6, "ruins": 5, "farm": 4, "cliff": 5, "mountain": 3, "wreck": 2, "monolith": 1,
            },
            "features": {"mountain_blob_min": 2, "mountain_blob_max": 4, "water_bodies": 1, "landmark_count": 5},
            "description": "Shipyards, beaches, scrap cliffs.",
            "sort_order": 20,
        },
        {
            "id": "ash_plain",
            "label": "Ash Plain",
            "age": "post_collapse",
            "environment": "volcanic",
            "width": 32,
            "height": 32,
            "weights": {
                "ash": 40, "plains": 12, "lava": 8, "volcano": 2, "mountain": 10,
                "ruins": 10, "road": 4, "dungeon": 3, "monolith": 3, "water": 4, "cliff": 4,
            },
            "features": {"mountain_blob_min": 3, "mountain_blob_max": 7, "water_bodies": 1, "landmark_count": 5},
            "description": "Burned waste, volcanoes, dead cities.",
            "sort_order": 30,
        },
        {
            "id": "mountain_pass",
            "label": "Mountain Pass",
            "age": "ancient",
            "environment": "alpine",
            "width": 28,
            "height": 28,
            "weights": {
                "mountain": 28, "hill": 18, "cliff": 10, "plains": 12, "forest": 10,
                "ice": 6, "water": 4, "road": 5, "village": 2, "monolith": 2, "dungeon": 2, "waterfall": 1,
            },
            "features": {"mountain_blob_min": 4, "mountain_blob_max": 10, "water_bodies": 1, "landmark_count": 3},
            "description": "High roads, cliffs, sparse villages.",
            "sort_order": 40,
        },
        {
            "id": "deep_caverns",
            "label": "Deep Caverns",
            "age": "timeless",
            "environment": "subterranean",
            "width": 28,
            "height": 28,
            "weights": {
                "cavern": 40, "mushroom": 14, "crystal": 6, "lava": 8, "water": 8,
                "ruins": 6, "dungeon": 5, "monolith": 3, "road": 4, "town": 2, "cliff": 4,
            },
            "features": {"mountain_blob_min": 0, "mountain_blob_max": 0, "water_bodies": 2, "landmark_count": 6},
            "description": "Underworld halls, fungus, crystal.",
            "sort_order": 50,
        },
        {
            "id": "orbital_belt",
            "label": "Orbital Belt",
            "age": "far_future",
            "environment": "orbital",
            "width": 32,
            "height": 32,
            "weights": {
                "void": 42, "asteroid": 18, "nebula": 10, "station": 6, "colony": 4,
                "shipyard": 3, "gate": 2, "wreck": 6, "anomaly": 3, "road": 2, "monolith": 1, "city": 1,
            },
            "features": {"mountain_blob_min": 0, "mountain_blob_max": 0, "water_bodies": 0, "landmark_count": 8, "space": True},
            "description": "Stations, gates, wrecks in vacuum.",
            "sort_order": 60,
        },
        {
            "id": "star_lane",
            "label": "Star Lane",
            "age": "space_opera",
            "environment": "deep_space",
            "width": 36,
            "height": 24,
            "weights": {
                "void": 50, "nebula": 16, "gate": 5, "station": 5, "wreck": 8,
                "anomaly": 6, "asteroid": 6, "shipyard": 2, "colony": 2,
            },
            "features": {"mountain_blob_min": 0, "mountain_blob_max": 0, "water_bodies": 0, "landmark_count": 6, "space": True},
            "description": "Deep-space travel board; sparse nodes.",
            "sort_order": 70,
        },
        {
            "id": "frontier_any",
            "label": "Anything Frontier",
            "age": "mixed",
            "environment": "multi",
            "width": 36,
            "height": 36,
            "weights": {
                "plains": 16, "forest": 12, "water": 10, "desert": 8, "mountain": 7,
                "city": 3, "ruins": 5, "road": 5, "monolith": 2, "waterfall": 1,
                "station": 2, "void": 6, "asteroid": 3, "gate": 1, "ash": 4, "harbor": 2, "dungeon": 2, "cliff": 3, "hill": 6, "town": 2,
            },
            "features": {"mountain_blob_min": 2, "mountain_blob_max": 6, "water_bodies": 2, "landmark_count": 7, "space": True},
            "description": "Kitchen-sink board for mixed-age campaigns.",
            "sort_order": 5,
        },
    ]
    for p in presets:
        conn.execute(
            """
            INSERT OR IGNORE INTO world_presets
              (id, label, age, environment, width, height, weights_json, features_json, description, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                p["id"], p["label"], p["age"], p["environment"], p["width"], p["height"],
                json.dumps(p["weights"]), json.dumps(p["features"]), p["description"], p["sort_order"],
            ),
        )
