# World map & tile systems

Status: **v1 live** — presets, flat generation, tile-state model, image archive API + setup UI.

## Core model

The map is a **flat grid**. Each cell has:

| Field | Meaning |
| --- | --- |
| `state` | Abstract type: `city`, `waterfall`, `mountain`, `void`, … |
| `elevation` | Only **0 or 1** (ground vs raised). Mountains/cliffs/hills use 1. |
| `walkable` | From the state catalog (water/void/mountain peak = blocked by default). |
| `image_*` | Optional art pulled from the **tile image archive** after generation. |

Mountains are not 3D: a **mountain blob** paints several neighboring tiles as `mountain` (elevation 1), often with `hill` / `cliff` around the rim.

Space ages use the same flat board with states like `void`, `station`, `gate`, `asteroid`.

## Presets (ages & environments)

Seeded in SQLite `world_presets` (idempotent):

| Id | Age | Environment |
| --- | --- | --- |
| `frontier_any` | mixed | multi |
| `forest_march` | medieval | terrestrial |
| `coastal_scrap` | industrial | coastal |
| `ash_plain` | post_collapse | volcanic |
| `mountain_pass` | ancient | alpine |
| `deep_caverns` | timeless | subterranean |
| `orbital_belt` | far_future | orbital |
| `star_lane` | space_opera | deep_space |

Each preset has **weights** per state and **features** (`mountain_blob_*`, `water_bodies`, `landmark_count`, `space`).

## Play UI map (v2)

| Piece | Behavior |
| --- | --- |
| **Nearby mini-map** | Player + few tiles around them (radius ~4) |
| **Map overlay** | Opens over the scene/chat; close with **×** |
| **Fog / visited** | Unvisited tiles dimmed; settlements highlighted |
| **Hover / click** | Settlement hover tip; click for detail panel |
| **Walk** | When `travel_ready`, click tile or **Walk here** |
| **Travel lock** | After walking (or during active scene), travel locks until the turn pipeline sets `travel_ready` again |

### Travel signal

Hard problem: the GM/model should set when an event is “done.” Supported paths:

1. Turn payload `travel.ready` / `travel_ready` (preferred when model cooperates)  
2. Heuristic: combat active → lock; opening → lock; scene goal mentions leave/travel → open  
3. UI reads `GET /api/travel-status` and banners

### APIs

- `GET /api/tiles/map/local?radius=4`  
- `GET /api/tiles/map/full`  
- `POST /api/tiles/map/move` `{x,y}`  
- `GET /api/tiles/map/settlements`  
- `GET /api/travel-status`

## Generation pipeline

1. Value-noise fields bias weights (coherent regions).  
2. Weighted pick → base state per cell.  
3. Optional water bodies / mountain multi-tile blobs.  
4. Landmark stamps (settlements, monoliths, gates…).  
5. Cliff edges at elevation transitions.  
6. Pick walkable start (prefer town/road/station).  
7. **Art pass**: for each cell state, random image from archive (respecting disable flags).

## Image archive

Table `tile_images`:

- Tied to `state_id`  
- `path` / `data_url`, `source` (`user` / `generated`), `prompt`, `tags`, `quality`  
- `disabled_forever`  
- Per-run hide: `tile_image_run_disable(image_id, run_id)`

Bulk actions in UI / API:

- Disable forever  
- Disable for this map run  
- Re-enable  
- Delete  

Users can **Generate** via Forge/Comfy (Image backend) into the archive, or later upload.

## API

```text
GET  /api/tiles/states
GET  /api/tiles/presets
POST /api/tiles/generate     { preset_id, seed?, width?, height? }
GET  /api/tiles/map
GET  /api/tiles/maps
POST /api/tiles/images/search
POST /api/tiles/images
POST /api/tiles/images/generate
POST /api/tiles/images/disable-forever
POST /api/tiles/images/disable-run
POST /api/tiles/images/delete
```

## Setup UI

World tab → **World map** card:

- Preset + optional seed → **Generate** (ASCII preview)  
- **Tile library** → search, select many, bulk disable/delete, generate art for a state  

## Next steps

- Play mini-map + move API + enter-POI hooks for the agent  
- Upload file picker for user tile art  
- More states / preset editor in UI  
- Seamless tile packing / autotile rules  
