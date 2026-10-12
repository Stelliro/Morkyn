# World database: turn-000

Exported 2026-10-13T00:09:42 from `world.db` (read-only).

## player (1)

| name | level | xp | gold | health | max_health | energy | max_energy | current_location_id |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Isk Tarrow | 1 | 0 | 12 | 20 | 20 | 16 | 16 | 1 |

## locations (1)

| id | code | name | kind |
| --- | --- | --- | --- |
| 1 | L1 | Saltmarrow |  |

## npcs (3)

| code | name | role | location_id | attitude | trust | knows_player_name |
| --- | --- | --- | --- | --- | --- | --- |
| A | Philippa Kemp | chandler | 1 | wary | 0 | 0 |
| B | Hereward Jessop | clerk | 1 | neutral | 0 | 0 |
| C | Wulfstan | weaver | 1 | neutral | 0 | 0 |

## inventory (4)

| name | quantity | item_type | rarity | equipped_slot |
| --- | --- | --- | --- | --- |
| soft-soled boots | 1 | clothing | common | FEET |
| patched tunic | 1 | clothing | common | TORSO |
| wool trousers | 1 | clothing | common | LEGS |
| mother's brass tide-reckoner | 1 | misc | common |  |

## abilities (1)

| name | locked | cost | power_type |
| --- | --- | --- | --- |
| Tidecount | 0 | 1 energy | soft_cap |

## player_skills (2)

| name |
| --- |
| Salvage |
| Tide Reading |

## quests (0)

_none_

## quest_steps (0)

_none_

## npc_player_relationships (0)

_none_

## dice_rolls (0)

_none_

## journal, engine entries (7 of 8)

- T0 `setup` Playthrough started: {"difficulty": "normal", "narration_detail": "balanced", "world_style": "frontier dark fantasy", "custom_style": "A drowned harbour town at the edge of mudflats the sea left behind. Salvage, debt and a tide that keeps the wrong hours.", "leveling_system": true, "game_system": fa
- T0 `system` Initialization phase pending: on the first model turn, establish base play assumptions, respect immutable ability base descriptions, do not seed default player skills beyond any recorded weak skill seed, and set any model-decided ability costs or prerequisites through ability_updates.
- T0 `backstory` known/known: Isk grew up in Saltmarrow, the harbour town the sea abandoned forty years ago. She runs the exposed flats at dry tide, pulling salvage out of the drowned lower district before the water comes back for a few hours each night. Her mother went out on the flats six years ago and never came 
- T1 `opening` Opening scene: the model introduced the initial situation before the player acted.
- T1 `self_check` {"passed": true, "issues_found": ["npcs creates Hereward Jessop but the narration never names him; the clerk at the tide marks appears only as 'a thin man with a slate'."], "corrections_made": ["Verifier replaced narration.", "Deterministic entity name/code repair applied to narration."], "reference
- T1 `rumor` Philippa Kemp's nephew Tam went out on the flats at the last dry tide with a hand cart and has not come back.
- T1 `fact` The guild posted a coin-paid contract for the bell of the old customs house, furthest out on the flats.

## Row counts

| table | rows |
| --- | --- |
| abilities | 1 |
| aliases | 0 |
| content_pack_entries | 0 |
| content_packs | 0 |
| conversations | 0 |
| dice_rolls | 0 |
| entity_titles | 0 |
| equipment_slots | 13 |
| events | 1 |
| gm_events | 0 |
| gm_notes | 1 |
| inventory | 4 |
| inventory_capacity_modifiers | 0 |
| journal | 8 |
| karma_history | 0 |
| locations | 1 |
| model_logs | 2 |
| name_ledger | 3 |
| npc_agendas | 0 |
| npc_family_ties | 0 |
| npc_player_relationships | 0 |
| npc_private_feelings | 0 |
| npcs | 3 |
| pacing | 4 |
| party_members | 0 |
| player | 1 |
| player_aliases | 0 |
| player_name_history | 1 |
| player_proficiencies | 2 |
| player_skills | 2 |
| quest_clocks | 3 |
| quest_steps | 0 |
| quests | 0 |
| relationships | 0 |
| response_drafts | 0 |
| setting_templates | 26 |
| settings | 15 |
| sqlite_sequence | 16 |
| tile_image_run_disable | 0 |
| tile_images | 0 |
| tile_states | 38 |
| titles | 15 |
| town_cells | 0 |
| town_seen | 0 |
| turn_snapshots | 1 |
| turn_summaries | 1 |
| verification_memory | 0 |
| watched_npcs | 0 |
| world_facts | 5 |
| world_maps | 0 |
| world_presets | 8 |
| world_races | 1 |
