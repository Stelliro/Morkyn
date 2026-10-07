from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any


def db_path() -> Path:
    """Resolve the world database path, re-reading the environment every call.

    Deliberately not a module-level constant. Tests set ``AI_RPG_DB`` to a temp
    path at import time, but a constant is frozen by whichever module imports
    ``app.db`` first -- under ``unittest discover`` that is an alphabetically
    earlier test file, and every later test then wrote into the player's real
    ``data/world.db``. Resolving per call makes the env var authoritative
    regardless of import order.
    """
    return Path(os.getenv("AI_RPG_DB", "data/world.db"))


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
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
    conn = connect()
    try:
        with conn:
            conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS locations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE DEFAULT '',
                name TEXT NOT NULL UNIQUE,
                summary TEXT NOT NULL DEFAULT '',
                discovered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                visit_count INTEGER NOT NULL DEFAULT 0,
                -- Containment. 0 = a place in the open world; otherwise the id of
                -- the place you must be standing in to enter this one. A shop on a
                -- square is the square's child, so entering it is an ordinary move
                -- and it can never be reached from two towns away.
                parent_id INTEGER NOT NULL DEFAULT 0,
                -- '' for open places; otherwise a venue kind (apothecary, smithy...)
                kind TEXT NOT NULL DEFAULT '',
                -- Minutes past midnight. -1/-1 means always open.
                open_minute INTEGER NOT NULL DEFAULT -1,
                close_minute INTEGER NOT NULL DEFAULT -1,
                -- hamlet | village | town | city, on settlements. Decides which
                -- venue kinds can plausibly exist here.
                settlement_size TEXT NOT NULL DEFAULT '',
                -- The one NPC who is always behind this counter.
                keeper_npc_id INTEGER NOT NULL DEFAULT 0
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
                energy INTEGER NOT NULL DEFAULT 20,
                max_energy INTEGER NOT NULL DEFAULT 20,
                mana INTEGER NOT NULL DEFAULT 0,
                max_mana INTEGER NOT NULL DEFAULT 0,
                fatigue INTEGER NOT NULL DEFAULT 0,
                max_fatigue INTEGER NOT NULL DEFAULT 20,
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
                -- Pinned once from prose, then never re-inferred: the same NPC
                -- was 'he' 41 times and 'they' 128 times across one 100-turn run.
                pronouns TEXT NOT NULL DEFAULT '',
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
                equipped_slot TEXT NOT NULL DEFAULT '',
                item_stats TEXT NOT NULL DEFAULT '{}'
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
                code TEXT NOT NULL DEFAULT '',
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                locked INTEGER NOT NULL DEFAULT 0,
                power_type TEXT NOT NULL DEFAULT 'linear',
                base_description TEXT NOT NULL DEFAULT '',
                cost TEXT NOT NULL DEFAULT '',
                prerequisites TEXT NOT NULL DEFAULT '',
                growth_math TEXT NOT NULL DEFAULT '',
                additions TEXT NOT NULL DEFAULT '',
                resource_cost TEXT NOT NULL DEFAULT '{}',
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

            -- Every "how much" decision the server rolled, for player audit.
            CREATE TABLE IF NOT EXISTS dice_rolls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                turn INTEGER NOT NULL DEFAULT 0,
                tag TEXT NOT NULL DEFAULT '',
                kind TEXT NOT NULL DEFAULT '',
                notation TEXT NOT NULL DEFAULT '',
                rolls TEXT NOT NULL DEFAULT '[]',
                modifier INTEGER NOT NULL DEFAULT 0,
                raw_total INTEGER NOT NULL DEFAULT 0,
                value INTEGER NOT NULL DEFAULT 0,
                band TEXT NOT NULL DEFAULT '',
                seed INTEGER NOT NULL DEFAULT 0,
                inputs TEXT NOT NULL DEFAULT '{}',
                source TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_dice_rolls_turn ON dice_rolls(turn);

            -- Names the world has committed to, keyed by what they name.
            -- A name given once must be the same name next time it is asked
            -- for; an invented name that is not written down is just a
            -- different kind of dodge. First writer wins.
            CREATE TABLE IF NOT EXISTS name_ledger (
                subject TEXT PRIMARY KEY,
                name TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT '',
                turn INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            -- Installed content packs (skills / powers / items / tables).
            CREATE TABLE IF NOT EXISTS content_packs (
                id TEXT PRIMARY KEY,
                label TEXT NOT NULL DEFAULT '',
                version TEXT NOT NULL DEFAULT '1',
                author TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'user',
                enabled INTEGER NOT NULL DEFAULT 1,
                builtin INTEGER NOT NULL DEFAULT 0,
                checksum TEXT NOT NULL DEFAULT '',
                payload TEXT NOT NULL DEFAULT '{}',
                installed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            -- One row per thing a pack contributed, so removal is exact.
            CREATE TABLE IF NOT EXISTS content_pack_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pack_id TEXT NOT NULL,
                section TEXT NOT NULL,
                entry_code TEXT NOT NULL,
                entry_name TEXT NOT NULL DEFAULT '',
                payload TEXT NOT NULL DEFAULT '{}',
                UNIQUE(pack_id, section, entry_code),
                FOREIGN KEY (pack_id) REFERENCES content_packs(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_pack_entries_section
            ON content_pack_entries(section, entry_code);

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

            CREATE TABLE IF NOT EXISTS quests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE DEFAULT '',
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                current_step INTEGER NOT NULL DEFAULT 1,
                total_steps INTEGER NOT NULL DEFAULT 1,
                reward_gold INTEGER NOT NULL DEFAULT 0,
                reward_xp INTEGER NOT NULL DEFAULT 0,
                reward_items TEXT NOT NULL DEFAULT '[]',
                difficulty TEXT NOT NULL DEFAULT 'normal',
                timer_turns INTEGER NOT NULL DEFAULT 0,
                turns_remaining INTEGER NOT NULL DEFAULT 0,
                giver_npc_id INTEGER,
                target_location_id INTEGER,
                created_turn INTEGER NOT NULL DEFAULT 0,
                completed_turn INTEGER NOT NULL DEFAULT 0,
                failed_turn INTEGER NOT NULL DEFAULT 0,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS quest_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                quest_id INTEGER NOT NULL,
                step_number INTEGER NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                location_code TEXT NOT NULL DEFAULT '',
                location_name TEXT NOT NULL DEFAULT '',
                location_coords TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                hidden INTEGER NOT NULL DEFAULT 0,
                revealed_at_step INTEGER NOT NULL DEFAULT 0,
                completed_turn INTEGER NOT NULL DEFAULT 0,
                notes TEXT NOT NULL DEFAULT '',
                UNIQUE(quest_id, step_number),
                FOREIGN KEY (quest_id) REFERENCES quests(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS npc_player_relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                npc_id INTEGER NOT NULL UNIQUE,
                affinity INTEGER NOT NULL DEFAULT 0,
                fear INTEGER NOT NULL DEFAULT 0,
                respect INTEGER NOT NULL DEFAULT 0,
                last_interaction TEXT NOT NULL DEFAULT '',
                interaction_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (npc_id) REFERENCES npcs(id) ON DELETE CASCADE
            );

            -- Hidden NPC psychology layer (narrator-only; never player-facing).
            -- Three tables hold the deep inner life of NPCs: private emotional states,
            -- hidden agendas, and family bonds between existing NPCs.

            CREATE TABLE IF NOT EXISTS npc_private_feelings (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                npc_id           INTEGER NOT NULL,
                feeling_type     TEXT    NOT NULL,
                intensity        INTEGER NOT NULL DEFAULT 0,
                target_id        INTEGER,          -- -1 = player; else another npcs.id
                trigger_event    TEXT    NOT NULL DEFAULT '',
                turn_triggered   INTEGER NOT NULL DEFAULT 0,
                is_revealed      INTEGER NOT NULL DEFAULT 0,
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
                target_id    INTEGER,              -- -1 = player; else another npcs.id
                priority     INTEGER NOT NULL DEFAULT 5,
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
                relative_id         INTEGER NOT NULL,
                relationship_type   TEXT    NOT NULL,
                is_known_to_player  INTEGER NOT NULL DEFAULT 0,
                created_at          TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(npc_id, relative_id),
                FOREIGN KEY (npc_id)      REFERENCES npcs(id) ON DELETE CASCADE,
                FOREIGN KEY (relative_id) REFERENCES npcs(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_family_ties_npc
            ON npc_family_ties(npc_id);

            CREATE INDEX IF NOT EXISTS idx_family_ties_relative
            ON npc_family_ties(relative_id);

            -- Town grid (docs/TownGrid.md 3.5): one generated city cell per row,
            -- made the first time a turn needs it and never regenerated.
            CREATE TABLE IF NOT EXISTS town_cells (
                map_id       TEXT    NOT NULL,
                cx           INTEGER NOT NULL,
                cy           INTEGER NOT NULL,
                city_id      TEXT    NOT NULL,
                gen_version  INTEGER NOT NULL,
                port_version INTEGER NOT NULL,
                side         INTEGER NOT NULL,
                era          TEXT    NOT NULL DEFAULT '',
                roads        TEXT    NOT NULL,
                segments     TEXT    NOT NULL,
                streets      TEXT    NOT NULL,
                plots        TEXT    NOT NULL,
                created_at   TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (map_id, cx, cy)
            );

            -- What the player has seen of a town cell: append-only, newly seen bits per row.
            CREATE TABLE IF NOT EXISTS town_seen (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                map_id  TEXT    NOT NULL,
                cx      INTEGER NOT NULL,
                cy      INTEGER NOT NULL,
                roads   TEXT    NOT NULL DEFAULT '',
                plots   TEXT    NOT NULL DEFAULT '',
                told    TEXT    NOT NULL DEFAULT '',
                turn    INTEGER NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS town_seen_cell ON town_seen (map_id, cx, cy);
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
        conn.commit()
    finally:
        conn.close()


def _migrate_columns(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
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
    )
    table_columns = {
        table: {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for table in ("locations", "npcs", "inventory", "events", "player", "abilities")
    }
    if "code" not in table_columns["locations"]:
        conn.execute("ALTER TABLE locations ADD COLUMN code TEXT NOT NULL DEFAULT ''")
    location_columns = table_columns["locations"]
    for column, definition in (
        ("parent_id", "INTEGER NOT NULL DEFAULT 0"),
        ("kind", "TEXT NOT NULL DEFAULT ''"),
        ("open_minute", "INTEGER NOT NULL DEFAULT -1"),
        ("close_minute", "INTEGER NOT NULL DEFAULT -1"),
        ("settlement_size", "TEXT NOT NULL DEFAULT ''"),
        ("keeper_npc_id", "INTEGER NOT NULL DEFAULT 0"),
        # Town grid: the plot a venue row was realized from, and the city a
        # settlement row stands for (docs/TownGrid.md 3.5, 4.4).
        ("plot_id", "TEXT NOT NULL DEFAULT ''"),
        ("city_id", "TEXT NOT NULL DEFAULT ''"),
    ):
        if column not in location_columns:
            conn.execute(f"ALTER TABLE locations ADD COLUMN {column} {definition}")
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
        ("pronouns", "''"),
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
        # full | event_worthy | nameless | background
        ("presence", "TEXT NOT NULL DEFAULT 'full'"),
        # 0–100 social/military power in a place (higher = more power)
        ("power_rank", "INTEGER NOT NULL DEFAULT 10"),
        ("portrait_eligible", "INTEGER NOT NULL DEFAULT 1"),
        ("shell", "INTEGER NOT NULL DEFAULT 0"),
        # Map position for NPC markers (-1 = not yet placed on map)
        ("map_x", "REAL NOT NULL DEFAULT -1"),
        ("map_y", "REAL NOT NULL DEFAULT -1"),
        # 1 = wandering/moving NPC whose position updates each turn
        ("is_moving", "INTEGER NOT NULL DEFAULT 0"),
        # Turn on which position was last updated (for throttling movement)
        ("last_moved_turn", "INTEGER NOT NULL DEFAULT 0"),
        # The venue this NPC works in (locations.id, 0 = none yet); set by
        # world.ensure_npc_workplace the first time it is needed (playtest #16)
        ("workplace_id", "INTEGER NOT NULL DEFAULT 0"),
        # The workplace before it is a place (playtest #27): JSON {kind, name,
        # parent_id}. world.plan_npc_workplace writes it; the location row is
        # only made when the player goes there, asks for it, or the story names it.
        ("workplace_plan", "TEXT NOT NULL DEFAULT ''"),
        # Town grid: the plot this NPC's planned workplace claims (TownGrid.md 4.4).
        ("workplace_plot", "TEXT NOT NULL DEFAULT ''"),
    ):
        if column not in npc_columns:
            conn.execute(f"ALTER TABLE npcs ADD COLUMN {column} {definition}")

    player_columns = table_columns["player"]
    if "karma" not in player_columns:
        conn.execute("ALTER TABLE player ADD COLUMN karma INTEGER NOT NULL DEFAULT 0")
    for column, definition in (
        ("energy", "INTEGER NOT NULL DEFAULT 20"),
        ("max_energy", "INTEGER NOT NULL DEFAULT 20"),
        ("mana", "INTEGER NOT NULL DEFAULT 0"),
        ("max_mana", "INTEGER NOT NULL DEFAULT 0"),
        ("fatigue", "INTEGER NOT NULL DEFAULT 0"),
        ("max_fatigue", "INTEGER NOT NULL DEFAULT 20"),
    ):
        if column not in player_columns:
            conn.execute(f"ALTER TABLE player ADD COLUMN {column} {definition}")
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
        # The player's people, one of world_races (playtest #23); set at start
        # by app/world_facts.py from setup, a backstory, or human.
        ("race", "''"),
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

    # World-event bus columns (walk ambushes, quest stages, forced portals, etc.)
    gm_cols = {row["name"] for row in conn.execute("PRAGMA table_info(gm_events)").fetchall()}
    for column, definition in (
        ("kind", "TEXT NOT NULL DEFAULT ''"),
        ("due_turn", "INTEGER NOT NULL DEFAULT 0"),
        ("force", "INTEGER NOT NULL DEFAULT 0"),
        ("payload", "TEXT NOT NULL DEFAULT '{}'"),
    ):
        if column not in gm_cols:
            conn.execute(f"ALTER TABLE gm_events ADD COLUMN {column} {definition}")

    ability_columns = table_columns["abilities"]
    for column in ("base_description", "cost", "prerequisites", "growth_math", "additions"):
        if column not in ability_columns:
            conn.execute(f"ALTER TABLE abilities ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
    if "resource_cost" not in ability_columns:
        conn.execute("ALTER TABLE abilities ADD COLUMN resource_cost TEXT NOT NULL DEFAULT '{}'")
    if "power_type" not in ability_columns:
        conn.execute("ALTER TABLE abilities ADD COLUMN power_type TEXT NOT NULL DEFAULT 'linear'")
    if "code" not in ability_columns:
        conn.execute("ALTER TABLE abilities ADD COLUMN code TEXT NOT NULL DEFAULT ''")
    # Powers are read-only rules the dice roller consults; they are never
    # re-derived by the model mid-play. roll_profile says which checks the
    # power modifies; magnitude_band is its default "how much" band.
    for column, definition in (
        ("read_only", "INTEGER NOT NULL DEFAULT 1"),
        ("roll_profile", "TEXT NOT NULL DEFAULT '{}'"),
        ("magnitude_band", "TEXT NOT NULL DEFAULT ''"),
        ("magnitude_kind", "TEXT NOT NULL DEFAULT ''"),
        ("activation", "TEXT NOT NULL DEFAULT 'active'"),
        ("pack_id", "TEXT NOT NULL DEFAULT ''"),
    ):
        if column not in ability_columns:
            conn.execute(f"ALTER TABLE abilities ADD COLUMN {column} {definition}")
    # Backfill ability codes (AB1, AB2…) when missing
    try:
        bare = conn.execute(
            "SELECT id FROM abilities WHERE code = '' OR code IS NULL ORDER BY id"
        ).fetchall()
        for row in bare:
            conn.execute(
                "UPDATE abilities SET code = ? WHERE id = ?",
                (f"AB{int(row['id'])}", int(row["id"])),
            )
    except Exception:
        pass

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
        # --- item -> stats / powers wiring -------------------------------
        # stat_links: canonical stat keys only ({"strength": 2}), normalized
        #   from the free-text stat_modifiers the model may write.
        # power_codes: JSON array of abilities.code (AB1, AB2...) this item
        #   grants while equipped. Powers stay read-only; the item points at
        #   them rather than restating them.
        # roll_profile: which skill checks this item shifts, e.g.
        #   {"melee": 2, "stealth": -1}. The dice roller applies these
        #   automatically so the model never has to reason about modifiers.
        ("stat_links", "TEXT NOT NULL DEFAULT '{}'"),
        ("power_codes", "TEXT NOT NULL DEFAULT '[]'"),
        ("roll_profile", "TEXT NOT NULL DEFAULT '{}'"),
        ("pack_id", "TEXT NOT NULL DEFAULT ''"),
        # item_stats: the item's own numbers from setup gear (weight is also
        #   the weight column; durability, protection, value and rarity ride
        #   here as JSON so the card and the DM read the same figures).
        ("item_stats", "TEXT NOT NULL DEFAULT '{}'"),
    ):
        if column not in inventory_columns:
            conn.execute(f"ALTER TABLE inventory ADD COLUMN {column} {definition}")

    # Blank codes used to be filled from the row id (L2, or alpha B for id 2).
    # That collides when the id-derived code is already taken, and init_db
    # then dies on UNIQUE. Probe for a free code instead.
    for table, prefix in (("locations", "L"), ("inventory", "I"), ("events", "E")):
        _fill_blank_prefixed_codes(conn, table, prefix)
    _fill_blank_alpha_codes(conn, "npcs")

    # Quest tables (added in 0.10.0-wip)
    _existing_tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if "quests" not in _existing_tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS quests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE DEFAULT '',
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                current_step INTEGER NOT NULL DEFAULT 1,
                total_steps INTEGER NOT NULL DEFAULT 1,
                reward_gold INTEGER NOT NULL DEFAULT 0,
                reward_xp INTEGER NOT NULL DEFAULT 0,
                reward_items TEXT NOT NULL DEFAULT '[]',
                difficulty TEXT NOT NULL DEFAULT 'normal',
                timer_turns INTEGER NOT NULL DEFAULT 0,
                turns_remaining INTEGER NOT NULL DEFAULT 0,
                giver_npc_id INTEGER,
                target_location_id INTEGER,
                created_turn INTEGER NOT NULL DEFAULT 0,
                completed_turn INTEGER NOT NULL DEFAULT 0,
                failed_turn INTEGER NOT NULL DEFAULT 0,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS quest_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                quest_id INTEGER NOT NULL,
                step_number INTEGER NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                location_code TEXT NOT NULL DEFAULT '',
                location_name TEXT NOT NULL DEFAULT '',
                location_coords TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                hidden INTEGER NOT NULL DEFAULT 0,
                revealed_at_step INTEGER NOT NULL DEFAULT 0,
                completed_turn INTEGER NOT NULL DEFAULT 0,
                notes TEXT NOT NULL DEFAULT '',
                UNIQUE(quest_id, step_number),
                FOREIGN KEY (quest_id) REFERENCES quests(id) ON DELETE CASCADE
            );
        """)
    if "npc_player_relationships" not in _existing_tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS npc_player_relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                npc_id INTEGER NOT NULL UNIQUE,
                affinity INTEGER NOT NULL DEFAULT 0,
                fear INTEGER NOT NULL DEFAULT 0,
                respect INTEGER NOT NULL DEFAULT 0,
                last_interaction TEXT NOT NULL DEFAULT '',
                interaction_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (npc_id) REFERENCES npcs(id) ON DELETE CASCADE
            );
        """)

    if "watched_npcs" not in _existing_tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS watched_npcs (
                npc_id INTEGER PRIMARY KEY,
                added_turn INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (npc_id) REFERENCES npcs(id) ON DELETE CASCADE
            );
        """)

    # quest_steps location columns (added in 0.10.0-wip)
    qs_cols = {row["name"] for row in conn.execute("PRAGMA table_info(quest_steps)").fetchall()}
    if "location_name" not in qs_cols:
        try:
            conn.execute("ALTER TABLE quest_steps ADD COLUMN location_name TEXT NOT NULL DEFAULT ''")
        except Exception:
            pass
    if "location_coords" not in qs_cols:
        try:
            conn.execute("ALTER TABLE quest_steps ADD COLUMN location_coords TEXT NOT NULL DEFAULT ''")
        except Exception:
            pass

    repair_npc_default_summaries(conn)

    # Written rules for short setup choices (rank ladder and the other selections).
    try:
        from app.setting_templates import ensure_setting_template_table

        ensure_setting_template_table(conn)
    except Exception:
        pass

    # Per-world race and lore rows (playtest #8).
    try:
        from app.world_facts import ensure_world_fact_tables

        ensure_world_fact_tables(conn)
    except Exception:
        pass

    # Settled custom proficiencies (playtest #1).
    try:
        from app.proficiencies import ensure_proficiency_table

        ensure_proficiency_table(conn)
    except Exception:
        pass

    # Titles system (added in 0.10.0-wip)
    try:
        from app.titles import init_titles
        init_titles(conn)
    except Exception:
        pass

    # Party system (added in 0.10.0-wip)
    try:
        from app.party import init_party
        init_party(conn)
    except Exception:
        pass


# The placeholder NPC_NEW used to store as a summary (playtest #24). Saves from
# before the fix carry it, often with a note glued on: "Introduced this turn:
# Aria Aria is a baker with a steady hand and a sharp mind."
_INTRODUCED_PREFIX = "Introduced this turn:"


def strip_introduced_prefix(summary: str, name: str = "") -> str:
    """The summary without the old 'Introduced this turn: <Name>' placeholder."""
    text = str(summary or "").strip()
    if not text.lower().startswith(_INTRODUCED_PREFIX.lower()):
        return text
    rest = text[len(_INTRODUCED_PREFIX):].lstrip()
    name = str(name or "").strip()
    if name and rest.lower().startswith(name.lower()):
        rest = rest[len(name):]
    return rest.lstrip(" .,;:-").strip()


def repair_npc_default_summaries(conn: sqlite3.Connection) -> int:
    """Strip the placeholder from stored NPC summaries; returns rows changed."""
    try:
        rows = conn.execute(
            "SELECT id, name, summary FROM npcs WHERE summary LIKE ?", (f"{_INTRODUCED_PREFIX}%",)
        ).fetchall()
    except sqlite3.Error:
        return 0
    for row in rows:
        conn.execute(
            "UPDATE npcs SET summary = ? WHERE id = ?",
            (strip_introduced_prefix(row["summary"], row["name"]), int(row["id"])),
        )
    return len(rows)


def _alpha_code(number: int) -> str:
    result = ""
    n = max(1, number)
    while n:
        n -= 1
        result = chr(65 + (n % 26)) + result
        n //= 26
    return result


def _used_codes(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(
        f"SELECT code FROM {table} WHERE code IS NOT NULL AND TRIM(code) != ''"
    ).fetchall()
    return {str(row["code"]) for row in rows}


def _fill_blank_prefixed_codes(conn: sqlite3.Connection, table: str, prefix: str) -> None:
    rows = conn.execute(
        f"SELECT id FROM {table} WHERE code IS NULL OR TRIM(code) = '' ORDER BY id"
    ).fetchall()
    if not rows:
        return
    used = _used_codes(conn, table)
    n = 1
    for row in rows:
        while f"{prefix}{n}" in used:
            n += 1
        code = f"{prefix}{n}"
        used.add(code)
        n += 1
        conn.execute(f"UPDATE {table} SET code = ? WHERE id = ?", (code, int(row["id"])))


def _fill_blank_alpha_codes(conn: sqlite3.Connection, table: str) -> None:
    rows = conn.execute(
        f"SELECT id FROM {table} WHERE code IS NULL OR TRIM(code) = '' ORDER BY id"
    ).fetchall()
    if not rows:
        return
    used = _used_codes(conn, table)
    n = 1
    for row in rows:
        while _alpha_code(n) in used:
            n += 1
        code = _alpha_code(n)
        used.add(code)
        n += 1
        conn.execute(f"UPDATE {table} SET code = ? WHERE id = ?", (code, int(row["id"])))


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
