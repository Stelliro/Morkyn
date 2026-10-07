# Town grid

Status: **slices A and B built** (generator, storage, read API; the engine: position, walks,
plots made places, the draft's town block; see the build notes at the end). Slice C (UI) is not
built. Builders follow this in three slices (A, B, C, at the end).

The player asked for three things. Entering a town should let them zoom in and see its
sub-grid. Any plot on that grid may be a shop. A road network should run through it for
them to follow. "Expand the sub-grids" means more detail at the same size. The grid stays
128 x 128 fine tiles per city cell (`CITY_CELL_MAX`) and a city still spans up to 9 x 9
world cells. What is new is roads, plots and the shops on them, and the player standing on
a real fine tile instead of the cell's centre.

The player chose how the rest works:

1. **Movement in a town.** The player clicks a plot on the town map, or types "go to the
   bakery". The engine walks the road path, spends in-game minutes, and tells the scene
   where the player is and what is next to them. World travel follows the same rules.
2. **Shops.** Each roadside plot rolls by its district. Market wards are mostly shops,
   residential wards have a few corner shops, and temple and government wards have almost
   none. The rolls use the districts' existing `density` and `shop_count`.
3. **Expand.** Same 128 x 128 grid, with plots (several fine tiles each: buildings, yards,
   alleys) and a real road network.

Rules that hold throughout: the engine decides and the model writes. Generation is
deterministic from the world seed and city, and **lazy per city cell**: nothing ever
builds 81 x 128 x 128 up front. Results are cached in SQLite, carried by saves under the
one-map-per-save rule (#25), and safe to rewind. Names come from `app/example_pools.py`
draws filtered to the world, never from fixed lists.

---

## 1. What exists, and what this builds on

| Piece | Where | What it gives us | Constraint it puts on us |
| --- | --- | --- | --- |
| City clumps | `world_scale._city_from_local` | `city.cells[]`, each with `x, y, local, side (8..128), density, seed, districts[]` | Stored in `world_maps.meta_json["cities"]`. Never re-rolled. |
| Avenues | `world_scale.street_mask(seed, side)` | A cross at `side // 2`, plus one shifted line when `side >= 48`. Empty below 24. | `_flood`, `tiles_in_cell`, `cell_raster`, the #19 view and `local_intel` all rebuild district ownership from this mask. **Changing it moves every district boundary in every existing save**, and a stored anchor that lands on a street then owns nothing. The mask stays exactly as it is. |
| Districts | `world_scale.layout_districts` | `type, name, anchor, density, shop_count, permissions, requires_entry, entrances` | Ownership is the flood. A road drawn on top of a district still belongs to that district. |
| Stalls | `local_intel.stalls_for_district` | `shop_count` positions `(fine_x, fine_y, good)` per district, from a hash | Direction answers have already told players these positions. Plots must agree with them. |
| Notices | `local_intel.roll_notices_for_cell` | `cell["notices"]` with `fine_x, fine_y`, `kind` pinboard/quest_board/guild | Same: already told. |
| Settlement view | `tile_world.settlement_view`, `GET /api/tiles/map/settlement`, `paintSettlementCanvas` | Ward raster per seen cell, outline for unseen cells, places, player | The player marker is the cell centre: "The engine keeps no finer position than the world cell". |
| Venues | `locations` (`parent_id, kind, open/close, settlement_size, keeper_npc_id`), `app/venues.py` | Containment, hours, plausibility, capacity, keeper binding | `kind_capacity` (for example 3 bakeries in a settlement) fits a village, not a 9 x 9 metropolis. |
| Workplaces | `world.plan_npc_workplace`, `ensure_npc_workplace`, `_realize_named_workplaces` | A planned `{kind, name, parent_id}` on the NPC, made a row only when visited or named (#27) | The planned name is `"<NPC>'s <Trade>"`, invented. In a plotted town it should be a plot. |
| Movement | `world.resolve_movement`, `gate_venue_move`, `movement_contract`, `_venue_shown_in_prose`, `_venue_for_named_move` | The #6c/#16/#33/#50 rules | They mint shops whenever the prose or the player names one. That is half of #55. |
| World walk | `tile_world.move_player`, `walk_minutes_for_step` (`city` = 10 min), `apply_map_travel_step` | Minutes, energy, weather, encounters, `travel_ready` gate | One world step into a city cell costs 10 minutes. |
| Rewind | `world._save_snapshot` / `_restore_snapshot_rows` | Delta rows, `SNAPSHOT_SETTING_KEYS`, `AUTOINC_TABLES` max-id cleanup | **`world_maps` is not in the snapshot**, so a rewind does not move the world-map player marker back. This is an existing gap. Town state must not inherit it (section 9). |

---

## 2. Scale

`side` varies from 8 to 128 per cell, and every existing consumer treats a cell's fine grid
as filling the whole world cell. The design keeps that: **a cell's `side x side` tiles
always cover exactly one world cell**. A tile is therefore smaller in the dense centre and
coarser at the edges.

| Constant | Value | Meaning |
| --- | --- | --- |
| `CELL_METRES` | 800 | Width of one world cell. Crossing one costs 10 minutes on foot (`TERRAIN_WALK_MINUTES["city"]`). |
| `CELL_CROSS_MINUTES` | 10 | Read from `TERRAIN_WALK_MINUTES["city"]`, never copied. |
| `tile_metres(side)` | `800 / side` | 6.25 m at 128, 12.5 m at 64, 25 m at 32, 100 m at 8 |
| `tile_minutes(side)` | `10 / side` | 0.078 min (about 5 s) at 128 |
| `TOWN_WALK_BUDGET` | `STEP_BUDGET * CELL_CROSS_MINUTES` = 40 min | The most one turn walks inside a town. This is the same distance a world turn would cover through city cells. |

Plot and block sizes below are given in **metres** and converted per cell with
`tiles = max(1, round(metres / tile_metres(side)))`. The centre cell gets plots of several
tiles each. An 8-wide hamlet cell gets plots of one tile. That is honest: a hamlet of
8 x 8 tiles has only a handful of buildings.

---

## 3. Data model

New module **`app/town_grid.py`**, pure apart from its storage functions. It has no model
calls.

### 3.1 Ports: the joins between cells (city level, cheap, no fine grid)

`city_ports(world, city) -> dict[(cx, cy), list[Port]]` is computed from the city record
alone, so a cell can be generated without its neighbours.

```
Port = {
  "edge": "N"|"E"|"S"|"W",
  "t": float,                # 0..1 along the edge (west to east, north to south)
  "cls": "main"|"street",
  "to": [nx, ny] | None,     # neighbouring city cell, or None for a gate
  "gate": "north"|...|None,  # compass label when this is a way in from outside
}
```

- **Shared edge** (both world cells are in the city): one `main` port at `t = 0.5`, so the
  legacy avenues (`side // 2`) of both cells meet within a tile. Add one `street` port when
  `min(sideA, sideB) >= 48` and another at `>= 96`. Their `t` values are
  `0.15 + 0.7 * mix_hash(world_seed, a_key, b_key, k) / 2**32`, where `a_key`/`b_key` are
  the two cells in sorted order, so both sides compute the same number. Each cell maps `t`
  onto its own side as `floor(t * side)`. When the sides differ, the two tiles sit at the
  same physical point.
- **Gates.** For every `world["roads"]` segment with an end at this city's centre, step
  along the segment (as `_on_road` does) to the last city cell it passes. The edge it
  leaves through gets a `main` port with `gate = compass(edge)` and `t` where the line
  crosses. A city with no road still gets one gate: on the outer edge of the outermost cell
  in the direction of the nearest other city, or a hashed edge when there is none. A city
  with `footprint >= 9` also gets one gate per bbox side, on the outermost cell of the
  centre row or column.
- Ports carry their own `PORT_VERSION`. Changing the port rule would disconnect cells
  already generated in a save from cells generated later, so the rule is frozen once
  shipped (see 3.5).

### 3.2 Roads (per cell)

A road mask of `side * side` bytes, one per tile:

| Code | Class | Source |
| --- | --- | --- |
| 0 | none | |
| 1 | avenue | the legacy `street_mask` tiles, unchanged |
| 2 | main | port-to-network and anchor-to-network connectors |
| 3 | street | side streets that cut blocks |
| 4 | alley | one-tile lanes through deep blocks in dense wards |

Every road is one tile wide. Generation runs in fixed stages, each with its own
`random.Random(mix_hash(world_seed, cell.x, cell.y, STAGE_SALT))`. A change to how names
are drawn can then never move a road.

1. **Avenues.** Copy `street_mask(cell.seed, side)`.
2. **Main roads.** Connect every port tile to the network. When there is no avenue
   (`side < 24`), connect it to a hub, which is the road tile nearest the cell centre. Also
   connect every district anchor's nearest edge tile. Each connector is an L-path with one
   bend whose position is hashed (two bends when the run is over 48 tiles). It stops at the
   first road tile it meets, so connectors merge into a tree, never a grid of parallel
   lines. Paths never cross a world-blocked edge: a city cell is all walkable.
3. **Side streets.** Inside each district's flood region, run lines perpendicular to the
   nearest main road or avenue. Spacing is the district's block length in metres:

   | District | Block length | Plot frontage | Plot depth | Alleys |
   | --- | --- | --- | --- | --- |
   | shopping | 45–65 m | 6–12 m | 12–20 m | if density ≥ 55 |
   | food | 55–75 m | 8–14 m | 14–22 m | if density ≥ 60 |
   | craft | 65–85 m | 10–20 m | 16–26 m | if density ≥ 60 |
   | black_market | 35–55 m | 6–10 m | 10–16 m | always |
   | residential | 75–105 m | 8–16 m | 16–28 m | if density ≥ 70 |
   | temple | 120–160 m | landmark (3.3) | | never |
   | government | 110–150 m | landmark | | never |
   | military | 110–150 m | 20–40 m | 20–40 m | never |

   A side street runs from its road until it meets another road, the cell edge or the
   district boundary, plus one tile so wards join. A segment that does not end on a road
   is either extended to the nearest road with an L-path or dropped, whichever is shorter.
4. **Alleys.** A block deeper than `2 * plot_depth + 1` tiles in a ward that qualifies gets
   a one-tile alley down its long axis. An alley may dead-end. That is the point of an
   alley.
5. **Connectivity check.** BFS from the cell's ports over road tiles. Any road tile not
   reached is joined to the nearest reached one with an L-path. Generation **asserts**
   that afterwards every road tile and every port can be reached. A city's network is
   connected because every shared-edge port lands on a road tile in both cells.

Road **segments** are kept as well as the mask. A segment is a maximal straight run
between junctions, stored as `{id, cls, x0, y0, x1, y1, name_id}`. Segments give the
draft "you are on Wheel Street", bearings along a street, and lines for the UI to draw.
They are not used for pathfinding.

**Street names.** One name per avenue line, per main-road run inside a ward, and per side
street. Alleys are unnamed ("an alley off Wheel Street"). Names come from a new rendered
pool kind, `street_name`, in `example_pools.py`. Its forms are era-tagged, the way
`_VENUE_FORMS` are (`"{noun} Street"`, `"{family} Row"`, `"{adj} Lane"`, `"{noun} Avenue"`
for the newer eras, and so on), and it reuses `_VENUE_NOUN`/`_VENUE_ADJ` and the culture's
family names. Names are unique per city: `draw(..., exclude=used_in_city)`.

### 3.3 Plots

A **block** is a 4-connected component of non-road tiles. Blocks are visited in a stable
order (min y, then min x). Each block is cut into plots:

1. **Landmarks first.** The block holding a temple, government or military district anchor
   becomes one landmark plot when it is no larger than
   `(60 m / tile_metres)^2` tiles. A larger block gets an anchor-centred rectangle of that
   size. Landmark kinds are `temple`, `office` (the hall) and `barracks`.
2. **Frontage cuts.** Walk the block's tiles that touch a road, in perimeter order. Cut
   them into runs of the ward's frontage width, and extend each run inward by the ward's
   depth, or half the block depth when that is less. The result is an axis-aligned
   rectangle `x, y, w, h`. A corner plot (touching two roads) is marked `corner`.
3. **Leftovers.** Tiles not taken by a rectangle form interior plots of kind `yard`
   (courtyards, gardens, middens) with no frontage. A sliver under 2 tiles stays plain
   ground, which is not a plot.

```
Plot = {
  "n": int,                 # index in this cell, stable for a gen_version
  "id": "C3.4.2.117",       # city_id . local_x . local_y . n  (unique within a map)
  "r": [x, y, w, h],        # fine-tile rectangle
  "f": [fx, fy] | None,     # frontage: the road tile in front of the plot's middle
  "seg": int | None,        # segment id of that road tile
  "d": int,                 # index into cell["districts"]
  "k": "shop"|"service"|"house"|"yard"|"temple"|"office"|"barracks"|"warehouse"|"square"|"gate"|"empty",
  "vk": "bakery"|...|"",     # venue kind (venues.VENUE_KINDS) for shop/service/temple
  "name": "...",            # shop/service/temple/office/gate only
  "fl": ["corner","stall","notice","guild","anchor"],   # flags
}
```

The `gate` plot is a 2 x 2 (scaled) square inside the edge at each gate port. It is where
the player enters.

**Notices are collected by destination, not by the list that holds them.** A notice in
cell A's `cell["notices"]` can point at another city cell B (`far: true`, with `x, y` = B
and `home_x, home_y` = A; `local_intel.roll_notices_for_cell`). Generating cell
`(cx, cy)` therefore scans the `notices` of **every** cell of the city (city meta only, no
fine grid) and takes the entries whose `(x, y) == (cx, cy)`. Entries in this cell's own
list that point elsewhere are ignored here. Each collected notice is placed on the road
tile nearest its `fine_x, fine_y` and recorded on the plot whose frontage is nearest, as
flag `notice`. A `guild` notice turns that plot into `service`/`guild_hall`.

### 3.4 Which plots are shops

The rules use the existing numbers and nothing else.

**Stalls are forced, inside their own district.** `local_intel.stalls_for_district`
already gives each district `shop_count` positions with a good. Those positions wrap
modulo `side` and are never clamped to the district's flood region, so the raw nearest
plot can sit in another ward, on a landmark, or across the cell. The rule is therefore:
for each non-filler stall, take the nearest **frontage plot whose `d` is the stall's own
district** and which is not a landmark (`temple`, `office`, `barracks`, `gate`). If an
earlier stall already took that plot, take the next nearest. If the district has no free
frontage plot left, the stall gets no plot (the probe counts these; it should be 0 above
side 24). The stall coordinates themselves stay frozen (section 11); only the plot choice
is constrained. That plot becomes a shop (flag `stall`), with a venue kind chosen from the
good:

| good | venue kinds, era-fitted with `venues.kind_for_era` |
| --- | --- |
| food | bakery, butcher, general_store, diner |
| weapons | smithy, armorer |
| tools | smithy, carpenter, garage |
| cloth | tailor |
| books | scribe, library |
| magic | alchemist, apothecary |
| general, games | general_store |
| black-market goods | general_store, tavern or bar (flag `fence`) |

Directions that `local_intel` already gave ("the food shop is south of you") therefore land
on a real shop.

**Then each remaining frontage plot rolls.**

```
p_shop = base[district.type] * (0.5 + district.density / 100)
         * (3 if corner and type == "residential" else 1)
```

| type | base | otherwise |
| --- | --- | --- |
| shopping | 0.55 | house (rooms over shops) 0.35, warehouse 0.1 |
| food | 0.45 | warehouse 0.3, house 0.25 |
| craft | 0.40 | workshop yard 0.3, house 0.3 (a craft shop is `shop` with vk smithy/carpenter/...) |
| black_market | 0.35 | house 0.4, empty 0.25 |
| residential | 0.04 | house 0.85, yard 0.1, empty by vacancy |
| military | 0.02 | barracks/warehouse/yard |
| government | 0.02 | office 0.6, house 0.4 |
| temple | 0.02 | house (clergy) 0.5, yard 0.5 |

`empty` (vacant lot, ruin) takes a share of `max(0, 0.25 - density / 400)`. Post-collapse
themes double it. **Before caps**, that gives about 0.55 to 0.8 shop rolls per frontage
plot in a dense market ward and about 0.04 to 0.12 per residential plot, mostly on corners.
The share after caps is what the slice A probe measures and reports per district type; the
pre-cap numbers are not a promise. A shop roll picks
**service** instead of shop for kinds that are not retail (inn, tavern, bar, bathhouse,
stable, clinic, shrine, well, guildhall).

**The venue kind** comes from a weighted table by district type, filtered by
`venues.plausible_kinds(size, era)`. `size` is the city's band mapped to venue sizes:
`hamlet`, `village`, `town`, and `city` for city, large_city and metropolis. `era` is
`world._world_era(conn)` at generation time and is stored in the row (3.5). A **kind cap
per district** (not per cell) keeps one ward from holding twenty apothecaries while
leaving a city's several market wards room to be mostly shops:

```
cap(kind, cell, district) = max(VENUE_KINDS[kind]["max"],
                                round(VENUE_KINDS[kind]["max"] * side / 64
                                      * max(district.density, 20) / 50))
```

**Overflow rule.** When the weighted pick lands on a capped kind, that kind is removed
from the district's table and the pick is redrawn from the kinds still under cap. When
every eligible kind is capped, the roll falls through to the ward's "otherwise" row
above (house, warehouse, ...), never to an uncapped kind from another ward's table. The
same rule applies to a stall's kind; a stall whose good maps only to capped kinds keeps
the flag `stall` and takes the least-filled kind of its good's row (stalls were already
told to players, so they are never dropped for a cap).

The weighted tables (food ward: bakery, butcher, tavern, inn, diner, mill, market_hall;
craft ward: smithy, carpenter, tanner, tailor, garage, armorer, jeweller; and so on) live
in `town_grid.py` as **kind weights, not names**. Builders write them from the kinds in
`VENUE_KINDS`, so every new kind added there must get a weight row. A test checks this.

**Names.** `example_pools.draw("venue_name", ctx, 1, rng, exclude=used_in_city)` gains one
context key, `venue_kind`. When it is present:

- `{trade}` is drawn from `venues._KIND_WORDS[kind]` (title-cased, only words that fit the
  era) instead of the era's random `_VENUE_TRADE`. The trade then always matches the plot:
  a bakery is never "Blind Owl Smithy".
- Forms without `{trade}` ("The Crooked Lantern", "The {noun}'s Rest") are allowed only for
  `inn`, `tavern` and `bar`. Classification ignores sign names (Venues.md, possessives), so
  the plot's `vk` is what gives the kind. It is stamped on the location row at realization.
- `{place}` is **not** reused for streets: `_venue_place_word` deliberately reduces a
  place name to its first proper word, so it would give "Wheel Bakery". The context gains
  a second key, `street_name`, and the street forms use a new slot **`{street}`** that is
  the full street name ("{street} {trade}" -> "Wheel Street Bakery"). Forms with
  `{street}` are only drawn when `street_name` is present.

Test: every drawn plot name either has `venues.venue_kind_from_name(name) == vk` or is a
sign form on an inn, tavern or bar. This includes the `{street}` forms: "Wheel Street
Bakery" ends on the trade, not on the place-tail word, so it classifies.

### 3.5 What is stored and what is recomputed

| Data | Stored | Why |
| --- | --- | --- |
| Ports | recomputed (`city_ports`) | Pure, cheap, needed before any cell exists |
| Road mask, segments, street names, plots, plot names | **stored** in `town_cells` the first time a cell is needed | Once a player has read a sign, the name must not change when the pools or the algorithm change. The stored row is the authority for its campaign. |
| District ownership | recomputed (`_flood`) | Unchanged legacy behaviour |
| What the player has seen | stored, append-only (`town_seen`) | Rewind (section 9) |
| Player's town position | `settings.town_position` | Rewind and saves |
| Which plot became which venue row | `locations.plot_id` | Realization rides the existing location snapshot and max-id cleanup |
| NPC's claimed plot | `npcs.workplace_plot` | Same |

```sql
CREATE TABLE IF NOT EXISTS town_cells (
  map_id      TEXT NOT NULL,
  cx          INTEGER NOT NULL,
  cy          INTEGER NOT NULL,
  city_id     TEXT NOT NULL,
  gen_version INTEGER NOT NULL,
  port_version INTEGER NOT NULL,
  side        INTEGER NOT NULL,
  era         TEXT NOT NULL DEFAULT '',
  roads       TEXT NOT NULL,      -- base64(zlib(side*side bytes))
  segments    TEXT NOT NULL,      -- base64(zlib(json))
  streets     TEXT NOT NULL,      -- json list of names, indexed by name_id
  plots       TEXT NOT NULL,      -- base64(zlib(json list of Plot))
  created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (map_id, cx, cy)
);

CREATE TABLE IF NOT EXISTS town_seen (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  map_id  TEXT NOT NULL,
  cx      INTEGER NOT NULL,
  cy      INTEGER NOT NULL,
  roads   TEXT NOT NULL DEFAULT '',   -- base64 bitset over side*side, the tiles newly seen by this event
  plots   TEXT NOT NULL DEFAULT '',   -- base64 bitset over plot n, newly seen
  told    TEXT NOT NULL DEFAULT '',   -- json list of plot n known by being told, not seen
  turn    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS town_seen_cell ON town_seen (map_id, cx, cy);

ALTER TABLE locations ADD COLUMN plot_id TEXT NOT NULL DEFAULT '';
ALTER TABLE locations ADD COLUMN city_id TEXT NOT NULL DEFAULT '';
ALTER TABLE npcs ADD COLUMN workplace_plot TEXT NOT NULL DEFAULT '';
```

Text, not BLOB, because the save export writes rows as JSON (`rows_to_dicts`).
`gen_version` is a module constant. **A stored row is never regenerated** under a newer
version: a cell the campaign has generated keeps its plots. New cells use the current
version. Cells join through ports, which have their own frozen version, so mixing versions
inside one city stays connected.

### 3.6 Budgets

These are estimates to check in slice A with `tools/probe_town_grid.py`. They are not
measured yet.

| Item | Target for a 128 cell | Hard limit (test) |
| --- | --- | --- |
| Generation (all stages, pure Python) | ≤ 150 ms | 1 s |
| Plots | ≈ 900–1,500 | |
| Stored row | ≈ 20–40 KB after zlib | 96 KB |
| `city_ports` for a 9 x 9 city | ≤ 5 ms | 50 ms |
| Load and decode a stored row | ≤ 10 ms | |
| Cells generated by one turn | the cells on the walked path plus at most `TOWN_LOOKUP_CELLS` (2) for a lookup (5.1), never more than 5 | |
| Skeleton (stages 1-2 only, in memory, 3.2) | ≤ 15 ms | 100 ms |
| Skeletons computed by one GET | at most 9 (the `r = 1` view) | |
| Memory | decoded cells kept in an LRU of 9 per process; skeletons in a separate LRU of 27 | |

Full generation (plots, names) runs only inside a turn or a click-walk, and only for the
cells being entered or walked through, plus the bounded lookup in 5.1. **No GET route
ever generates or writes.** A cell that is seen but not generated is drawn from its
**skeleton**: stages 1 and 2 of 3.2 (avenues plus port and anchor connectors) recomputed
in memory, which is pure, cheap, unnamed and identical to what generation will later
store, because each stage has its own RNG salt. Unseen cells are outlines (section 6).

---

## 4. The player inside a town

### 4.1 Position

```json
settings.town_position = {
  "map_id": "...", "city_id": "C3",
  "cx": 8812, "cy": 4410,          // world cell (always equals world_maps.player_x/y)
  "fx": 63, "fy": 70,              // fine tile, always a road tile
  "plot": "C3.4.2.117" | "",       // the plot whose frontage this tile is, if any
  "inside": "C3.4.2.117" | "",     // set while the player is inside a realized plot venue
  "heading": "E"                   // last walk direction, for "ahead of you"
}
```

The key is absent whenever the player is not in a plotted city. It joins
`SNAPSHOT_SETTING_KEYS`. **Invariant:** while it is present, the world-map player cell is
`(cx, cy)`. Every function that writes one writes the other in the same transaction.

### 4.2 Entering and leaving

| Event | Where the player lands |
| --- | --- |
| World step (map arrows, `WALK`, story walk) from outside onto a city cell | The gate plot on the edge they crossed. With no gate on that edge, the road tile nearest that edge's midpoint ("you come in between the yards"). |
| World step from one city cell to a neighbouring one | Walk the road from the current tile to the shared-edge port, then continue in the next cell. This is an ordinary town walk with town minutes, not a flat 10-minute step. |
| Game start or opening placed in a city | The road tile nearest the shopping district's anchor, or the centre cell's hub. |
| World step out of the city | Walk to the nearest gate port on that side (or the edge), then clear `town_position`. |
| Load or rewind with `town_position` set | Reconcile the world marker to `(cx, cy)` (section 9). |

Entering a town makes or adopts the city's **settlement row**: one `locations` row per city
with `city_id` set, `name = city.name`, and `settlement_size` stamped explicitly from the
band. **Adoption comes first, by name:** `locations.name` is UNIQUE, so any existing
top-level row with no venue `kind` whose name equals the city's name (case-folded) is
adopted, whether or not it is the player's current location and whether or not it is
anchored on a city cell. An opening or the story may have made it. Adoption stamps
`city_id` and `settlement_size` on it. A new row is created only when no such row exists.
If a row with that name exists but is a venue (it has a `kind`), it is not adopted, and the
new settlement row takes the name with the city's band word appended ("Ashford town"),
which is a place-tail word and so never classifies as a venue. Plot venues are children of
the settlement row. Outdoor places the story names
inside a city (a square, a lane) stay top-level rows as they are today. Section 5.4 covers
how a typed street or ward name resolves to the grid first.

### 4.3 Pathfinding and minutes

The road graph is hierarchical, so a 9 x 9 city never needs all of its cells loaded.

- **Inside one cell:** BFS over road tiles (4-neighbour, uniform cost). At most 16 k
  tiles.
- **Across cells:** each cell row lazily caches its port-to-port road distances
  (`port_dist`, computed the first time from BFS). The route between cells is a Dijkstra
  over ports, then fine BFS only in the first and last cells. Cells in between are
  generated only when the walk actually crosses them, and those cells are seen anyway.
- **Minutes** = `sum over walked tiles of tile_minutes(side of that tile's cell)`, rounded
  up, minimum 1. Terrain for energy is `"city"`.
- **Spending them on the caller's connection.** `apply_map_travel_step` opens its own
  `connect()`, and a second connection cannot write while the turn's transaction holds
  the lock (the deadlock recorded at `world.py` `settlement_size_for`). Slice B therefore
  splits its time, weather and energy work into `_spend_travel(conn, minutes, terrain,
  context) -> report`, which takes the connection, and `apply_map_travel_step` becomes a
  thin wrapper that opens one and calls it. Every town walk (the turn path in 5.1 and
  `POST /api/town/walk`) runs in this order: **preview** the spend (pure; the existing
  `spend_preview`), then **commit** `town_position` and the world marker, then **advance**
  the clock and weather and spend energy. On a hard block (`insufficient_energy` or any
  other `travel_blocked` reason) nothing is written: `town_position`, the marker,
  `town_seen` and the clock stay as they were, and the report says `blocked` with the
  reasons.
- **Budget:** a walk longer than `TOWN_WALK_BUDGET` stops at the road tile where the budget
  runs out. The report says `"partial": true, "remaining_minutes": N`, and the draft is
  told the player is on the way (5.3). This is the same rule as the world's step budget.
- **Gates still apply.** Confinement (`movement_locked`, `map_blank`) refuses any walk. A
  walk that leaves the current cell needs `travel_ready`, like a long world jump. A walk
  inside the current cell is always allowed, like an adjacent world step.
- **Encounters:** none per tile. The world encounter roll is for terrain. A town's events
  come from the scene, as now.

### 4.4 Plots become venue rows only when visited or named

A plot is just data until one of these happens. Then it becomes a `locations` row with
`plot_id`, `parent_id = settlement row`, `kind = vk`, `default_hours(vk)`, and
`summary = "<kind label> on <street>, <ward>"`:

- the player goes inside it (a resolved enter, 5.1/5.2),
- the player or the shipped prose names it by its plot name and the turn moves there,
- an NPC's workplace is realized (`ensure_npc_workplace`) and that NPC's claimed plot is
  this one.

Realization goes through one function, `realize_plot(conn, chart, plot_id) -> location_id`.
It is idempotent: an existing row with this `plot_id` is returned. On a name clash with an
unrelated row (`locations.name` is UNIQUE), the row is stored as "The Crooked Lantern on
Wheel Street" and the plain plot name is written to `aliases` for it. Because that stored
name ends on a place-tail word, `venue_kind_from_name` returns `""` for it, so **rows with
a `plot_id` are never classified from their name**: every venue rule that reads a row's
kind (containment, keeper, hours, `venue_entry_check`) uses the stamped `kind` column for
them, through one helper `venues.row_kind(row)` (stamped `kind` when set, else the name).
Prose and MOVE matching try the alias as well as the stored name.

**Keepers** use the existing path unchanged. `bind_venue_keeper` and `_trade_keeper_for`
run on entry. Planned workplaces in a plotted town **claim a plot** instead of inventing a
name:

- `plan_npc_workplace`, plotted branch: if the NPC's trade kinds
  (`workplace_kinds_for_role`) have an unclaimed shop or service plot of that kind **in a
  cell of this city that is already generated**, claim the nearest one by road from where
  the NPC stands (the player's tile when they are in the scene). Planning never generates
  a cell. Unclaimed means no `npcs.workplace_plot` points at it and no realized row with
  that `plot_id` has a keeper. The plan becomes
  `{kind, name: plot.name, parent_id: settlement_row, plot_id}`, and `works_at` in the
  prompt now carries a real sign name.
- With no free plot of the kind in a generated cell but a claimed one there, the NPC works
  at that one (a second baker in a bakery).
- With no plot of the kind in any generated cell, the plan stays **unclaimed**:
  `{kind, name: "", parent_id: settlement_row, plot_id: ""}`, and `works_at` reads as the
  kind alone ("works at a bakery"). No name is invented. The claim is retried each time a
  cell of the city is generated (the generation hook calls the claim pass for unclaimed
  plans in that city).
- `ensure_npc_workplace` with a `plot_id` in the plan calls `realize_plot` and binds the
  keeper. `venue_capacity_left` is not consulted for plotted cities, because the plots are
  the capacity.

---

## 5. Movement resolution and the draft (#55)

The rule for #55 in a plotted town: **the engine already has every building. The model
never names a building that is not on the grid, and the engine never makes one that is not
on the grid.**

### 5.1 Typed targets

Town movement is **planned before the prompt and applied after the snapshot**. Two
ordering facts force this. `movement_contract` is built into the prompt before the draft
exists, while `resolve_movement` runs in `apply_turn` after the narration; and
`resolve_movement` runs **before** `_save_snapshot`, which reads `SNAPSHOT_SETTING_KEYS`
and computes `max_ids` itself, so rows it wrote would get ids at or below the snapshot's
max ids and never be removed by a rewind.

1. **Plan** (`plan_town_move(conn, chart, text, position) -> TownPlan | None`) runs in
   `play_turn` before the prompt context is built, whenever `town_position` is set. It
   reads only the player's own words (with speech stripped, as `venue_move_intent` does),
   so the draft is not needed. It writes nothing except `town_cells` cache rows for cells
   it has to generate (a deterministic cache, not rewound, 3.5). It computes the target,
   path, minutes, `partial`, the `spend_preview` (blocked or not) and `enter`. The plan is
   put into `movement_contract.town` (5.3) and carried to `apply_turn` as
   `result["_town_plan"]`.
2. **Resolve** (`resolve_movement`, which keeps its place before the snapshot) only edits the
   `result` dict: for a plan with `enter` it sets `player.move_to_location`, and it
   handles the model's own ops (5.2), which may re-aim a plan only towards a plot already
   in a generated cell. It writes no rows.
3. **Apply** (`apply_town_plan(conn, plan, result)`) runs in `apply_turn` **after**
   `_save_snapshot` and before `_apply_player`, next to where `_apply_story_map_walk`
   already runs late. So `town_position` is snapshotted with its pre-walk value, and the
   `town_seen` and `locations` rows it appends get ids above the snapshot's max ids and are
   removed by an ordinary rewind. `realize_plot` therefore runs before `_apply_player`
   needs the row.

`pre_rows` (`result["_snapshot_rows"]`) is not used for this. Deferring the writes is
simpler than teaching `_save_snapshot` to prefer pre-walk max ids.

The plan reads the player's words in this order:

| # | Shape | Example | Resolves to |
| --- | --- | --- | --- |
| 1 | A plot name the player knows (seen, told or realized) in this city | "back to the Crooked Lantern" | that plot |
| 2 | A trade word (`_KIND_WORDS`, era-fitted) with "the/a/an/nearest/some" | "go to the bakery", "find a smith" | the known plot of that kind nearest by road. When none is known, the nearest of that kind in a **generated** cell (the player walks there asking the way, and it becomes seen). When none is there either, the lookup below. |
| 3 | A street or ward name | "head to Wheel Street", "the market" | that segment's nearest tile, or the plot at the ward's anchor |
| 4 | A doorway with no name | "enter the inn", "go inside" | a plot of that kind (or any shop or service) whose frontage is the player's tile or adjacent to it |
| 5 | "out", "leave the shop" while `inside` | | the frontage tile of the plot they are in |
| 6 | Leaving the town | "leave town", "out the north gate" | the nearest gate (or the named one), then the world rules |

**Lookup, bounded.** Plot kinds exist only after a cell is generated, and a 9 x 9 city
must not be generated whole to answer "find a smith". When rule 2 (or a re-aimed trade
name, 5.2) finds no plot of the kind in any generated cell:

- A city of at most 5 cells is generated whole by the lookup (it is within the per-turn
  budget), so its answer is exact.
- A larger city generates at most `TOWN_LOOKUP_CELLS` (2) more cells, the ungenerated city
  cells nearest the player by port distance, and searches again.
- Still nothing: `town_none` is asserted **only** when every cell of the city is generated.
  Otherwise the report is `rule: "town_unknown", kind: "smithy"`: the player does not move
  and the draft is told none is known nearby and the player can ask around (5.3). Nothing
  is minted either way.

A plan carries `{plot_id | tile, enter: bool, walk_path, minutes, partial, blocked}`.
`apply_town_plan` then does three things itself:

1. Walk the path (4.3) in the preview, commit, advance order and write `town_position`.
   Mark everything seen on the way (6). A blocked plan writes nothing (4.3).
2. When `enter` is set and the plot is reached this turn and is open (`venues.is_open`):
   `realize_plot`, so the row exists when `_apply_player` applies the
   `move_to_location` that step 2 above set, and `gate_venue_move` runs as usual.
   Containment for a row with `plot_id` is **positional**: the player must be on its
   frontage tile, which the walk just ensured. The parent-equality check is skipped for
   these rows. A plot that is closed, or not reached this turn, clears the
   `move_to_location` and leaves the player at the door or on the way, with the existing
   `venue_closed` note when closed. Openness and reach are known at plan time, so the
   contract already said so.
3. Report `rule: "town_walk"` / `"town_enter"`, with `from`, `to`, `minutes`, `partial`
   and `blocked`.

`_mint_venue_from_request` and the `venue_opened` bootstrap are disabled in plotted
cities.

**The world walk stays out of it.** `_apply_story_map_walk` runs after movement and, for a
`model`/`repaired` report, steps the world token toward the destination's anchor, or
`STEP_BUDGET` world steps for a compass word ("walk east to the bakery"). That would move
the world marker off `town_position.cx, cy` and break the 4.1 invariant. `plan_story_walk`
therefore returns `skip` (reason `town`) whenever `town_position` is set and the movement
report's `rule` starts with `town_`, or a town plan was applied this turn. Leaving town
(rule 6) is the one hand-off: the town plan walks to the gate tile, clears
`town_position`, and the world walk then starts from the gate's world cell with its usual
budget, minus the minutes already spent.

### 5.2 What the model's own ops and prose may do

| Model output | In a plotted town |
| --- | --- |
| `MOVE <name>` that matches a plot name in `places_here`, a known plot or a realized plot | Walk and enter as in 5.1 |
| `MOVE <name>` where the name holds a trade word and matches no plot ("Blind Owl Bakery") | Re-aimed at the plot of that kind nearest by road **in a generated cell** (the apply phase walks it within budget; no lookup generation happens after the draft). The report records `renamed: {"from": "Blind Owl Bakery", "to": "<plot name>"}` so the shipped prose can be corrected (below). With no such plot generated, the move is dropped and the turn flagged `prose_mismatch`. |
| `MOVE` to a new outdoor name ("the fountain") | Resolved by 5.1 rule 3 when it names a street or ward. Otherwise it stays where it is and no row is made. |
| `venues.entry_in_prose` shows the player going into a building, with no MOVE | `_venue_shown_in_prose`, plotted branch: match the shown name or kind against `places_here`, then known plots, then the nearest plot of that kind. Never mint. |
| `WALK <dir> STEPS n` inside a town | Ignored. In town, walking is by place. The DSL rule says so (5.3). |

**Prose correction (the hook for #55).** When the engine re-aims a building name, it hands
`{invented, real}` to the reconciliation step that #55 calls for. Until that step exists,
the narrow version runs in place: in the shipped prose, replace the invented name with the
plot name when it occurs verbatim and exactly one invented building name is present. This
mirrors how `corrections_made` already replaces non-person labels. Otherwise the turn is
flagged `prose_mismatch` and nothing is rewritten. This can only fix names. It cannot fix a
scene that walks into a building the town does not have. That case shows up as
`town_none` plus a mismatch, and the #55 reconciliation owns it.

**What should shrink, and how we will know.** In the batch-5 gate's prose/state count, the
two #55 shapes in town scenes were "enters a shop the engine never made" and "the engine
makes a shop the prose never shows". The first becomes a rename or a flagged `town_none`.
The second goes away: workplaces claim plots, which are not rows, and there is no minting.
The measure for slice B: in a plotted town, `locations` rows with a `kind` and no
`plot_id` equal 0, and the gate count of shop-shaped mismatches drops. It is re-run live
on the 8B, not assumed.

### 5.3 The draft context

While `town_position` is set, `movement_contract` gains a `town` block. It **replaces**
`venue_name_options`, `venue_kinds_possible` and the "otherwise give the new building its
own name" sentence. Those three are what invite invention, and the prompt-examples memory
says the fix is to remove an invitation, not to argue against it.

```json
"town": {
  "name": "Ashford",
  "ward": "Copper Market (shopping)",
  "street": "Wheel Street",
  "at": "outside The Crooked Lantern (inn, open)",       // or "on Wheel Street"
  "inside": "The Crooked Lantern (inn)",                  // only while inside
  "places_here": [
    {"name": "The Crooked Lantern", "kind": "inn", "where": "here", "open": true},
    {"name": "Harrow's Bakery", "kind": "bakery", "where": "next door, left", "open": false, "hours": "04:00-12:00"},
    {"name": "Wheel Street Chandlery", "kind": "general store", "where": "across the street", "open": true},
    {"name": "", "kind": "house", "where": "right"},
    {"name": "Copper Market Smithy", "kind": "smithy", "where": "ahead, 2 min east", "open": true}
  ],
  "streets_off": ["Tallow Lane (north)", "an alley (south)"],
  "walking": {"to": "Copper Market Smithy", "minutes_left": 6},   // only after a partial walk
  "rule": "..."
}
```

- `places_here`: the plot the player stands at, the plots whose frontage is within about
  20 m on the same segment, the plots across the street, and the next 2 named shop or
  service plots ahead in `heading`. At most 8 entries. Houses and yards are listed only
  when fewer than 3 named plots qualify, so the street is not described as empty. Each
  entry is shown only if seen, so `places_here` never leaks unseen plots.
- `rule` (one paragraph, no example strings to copy): "The town's buildings are fixed.
  places_here are the ones beside the player. Going to or into one of them is MOVE with
  its name. A trade not listed may stand elsewhere in town; the engine walks there if the
  player asks. A building that is not listed and not asked for does not appear in the
  prose. Closed places cannot be entered."
- These lines come from **this turn's plan** (5.1), which exists before the prompt is
  built, so they describe the turn being written, not the previous one. When the plan
  walks, the contract carries `arrived` (the target's name, where it is, the minutes)
  and `places_here` is computed at the plan's end tile. When the plan is partial,
  `walking` is set and the prose ends on the way. When it is blocked, `blocked` gives the
  reason and the prose keeps the player where they are.
- `town_none` from 5.1 becomes one line: "No <kind> stands in <town>. Say so; do not
  produce one." `town_unknown` becomes: "No <kind> is known nearby. The player can ask
  around; do not produce one."
- `turn_dsl.py`'s movement rules become **conditional** on the town block. Leaving the
  general bullets in place beside a town sentence would keep the invitation to invent.
  When `movement_contract.town` is present, the prompt shows the town versions instead of:
  - "Prefer a name from movement_contract.venues_here; otherwise name the building and it
    is created." The town version: "A building the player goes to or into is MOVE with a
    name from town.places_here, or a street name. Nothing else is created."
  - "Interiors are entered only from the place they stand in ... going in costs the next
    turn. Do not narrate walking across the map and through a shop door in one turn." The
    town version: "The engine walks the player along the road and may take them inside
    within the same turn when town.arrived says so; otherwise the scene ends at the door
    or on the way."
  - "A hike is at most 4 tiles ..." and the WALK grammar: replaced by "In a town do not
    WALK."
  Outside towns and on legacy maps the DSL text is byte-identical to today's (a test
  checks it).
- `map_space` keeps its world block. `places_in_reach` still lists other cities.
- `current_location.people` `works_at` now names real plots, so the draft and the map
  agree on whose shop is whose.

### 5.4 Bearings

Inside a town, `bearings` for known plots and streets come from the road path (direction
of the first long segment, and minutes) instead of the world tile. "Back to the bakery"
then heads the way the engine will walk, as #33 does for world places.

---

## 6. Knowledge and fog

| What | When it becomes known |
| --- | --- |
| Avenues and main roads of a cell | When the world cell is seen (`visited`/`revealed`), matching the #19 rule that a seen cell shows its wards. You can see the big streets. A seen cell that is not generated shows its **skeleton** (3.6), unnamed, over its ward raster; a GET never generates it. |
| Side streets and alleys | Within sight of a walk: every road tile within `max(3, round(40 m / tile_metres))` of a walked tile, plus the straight line of road ahead along the current segment up to 150 m |
| A plot's kind (house, shop, ...) | When its frontage tile is seen |
| A plot's name, hours | When its frontage is within `max(1, round(15 m / tile_metres))` of a walked tile (you can read the sign), or it is realized, or someone told you |
| Told plots | A `local_intel` direction answer that pointed at a stall or a notice records it as `told`. In a generated cell that is the plot (name and kind, not its street). In a cell not yet generated the entry is the stall or notice id (`"stall:<district>:<index>"`, `"notice:<id>"`), which costs no generation; it is folded to its plot when that cell is generated, because the stall-to-plot rule (3.4) is deterministic. Telling never generates a cell. |
| Gates | Always, for a city whose cell you have seen |

Each walk appends **one** `town_seen` row per cell it touched, holding only the newly seen
bits. Knowledge is the OR of a cell's rows. Folding is cheap (a few rows per cell per
turn). Rows older than the 12-snapshot rewind horizon may be compacted into one when a
cell passes 64 rows.

---

## 7. API

All read routes are pure reads: they never generate or write anything, seen or not. A
seen cell that is not generated is returned from its in-memory skeleton (3.6) with
`generated: false`, roads masked to the avenue and main-road classes, and no plots. One
request computes at most 9 skeletons; a larger `r` is refused with 400.

| Route | Purpose |
| --- | --- |
| `GET /api/tiles/map/settlement` (existing) | Unchanged shape, plus `town: {zoomable, player: {cx, cy, fx, fy, plot}}`. The marker uses the real fine position when `town_position` is set. |
| `GET /api/town/view?city_id=&cx=&cy=&r=1` | The street view of cell `(cx, cy)` and its city neighbours within `r` (default: the player's cell). Per **seen** cell: `side`, `roads` (base64 class mask, **masked to seen tiles**), `segments` with names (seen only), `plots` (seen only: `id, r, k, vk, label, name if readable, open, hours, here, realized code`), `gates`, `notices`. Unseen cells in range: `{cx, cy, side, known: false}`. |
| `GET /api/town/plot/{plot_id}` | Peek: name, kind label, street, ward, hours and open-now, keeper if met, whether it is realized. 404 when not known. |
| `POST /api/town/walk` `{plot_id}` or `{cx, cy, fx, fy}` | The click-walk. Same gates as `/api/tiles/map/move` (confinement 409, `travel_ready` for leaving the cell). Walks the road to the plot's frontage, or the nearest road tile to the clicked tile, and **does not enter**. One connection: generates the walked cells, then runs `_spend_travel` in the preview, commit, advance order (4.3); a hard block returns 409 with the reasons and changes nothing. Returns the new view and a `travel` record. When inside a venue, it first leaves it (current location becomes the settlement row). |

**Going in is a turn.** Entering lets the scene happen (a keeper, an event), so the UI never
enters by itself. "Go in" writes "I go into <name>." into the composer and leaves Send to
the player, following UI_RULEBOOK §3.7.

---

## 8. UI: the Settlement view becomes the town view

Follow docs/UI_RULEBOOK.md. Ids and classes live in `app.js`. Layout goes in `styles.css`,
the look in `skin.css`, and colours come from `cssToken`.

- **Zoom.** The existing World / Settlement switch stays. The Settlement view gains a
  second chip pair, **City | Streets** (`.chipBtn`, one cut). City is today's view. Streets
  draws one cell (or the player's cell and its neighbours at a wide viewport) at fine
  resolution, about 4 to 8 CSS px per tile, centred on the player, with drag to pan.
  Clicking a cell on City zooms to Streets on that cell. **Entering a town** switches the
  map to Settlement and Streets once (a toast-free, per-viewer preference in
  `localStorage`, wrapped in try/catch), unless the player chose World since then.
- **Drawing.** Light is a line, so nothing is filled:
  - roads are strokes along segment centrelines: avenue and main in `--thread-dim` at
    1.5 px, street as a `--line-strong` hairline, alley dotted;
  - plots are hairline outlines in `--line-strong`; shop and service plots in `--thread`;
    closed ones dashed; temple and office in `--label`; gated wards (`requires_entry`) in
    `--moon`;
  - a plot's name is drawn only when it fits inside its rectangle without clashing (the
    existing label-placement code), otherwise a 2 px point;
  - unseen ground is void, and an unseen cell is today's dashed outline;
  - the player is the existing ring and needle; the walk path being previewed is a fading
    thread (`--thread-soft` to transparent);
  - hover shows `--thread-soft` on the plot outline only.
- **Interaction.** Click or tap a plot to select it. On desktop the info goes in the peek
  shard. On phone it goes in a card under the canvas (`#townPlotCard`), never floating.
  The card shows name, kind, street, hours and open-now, plus two buttons: **Walk here**
  (POST walk, disabled with the reason when the gate refuses) and **Go in** (writes the
  sentence into the composer). Right-click and long-press on a plot open a menu through
  `interact.js` `MENU_ANCHORS`, following UI_RULEBOOK §3.7: **Go to <name>** writes
  "I walk to <name>." into the composer, **Go in** writes "I go into <name>.", and the one
  immediate item is labelled **Walk here now** and coloured with the red moon, because it
  spends minutes and energy without a turn. Arrow keys in Streets walk to the next
  junction in that direction along the current road (immediate, like the map's arrow
  steps today).
- **Phone, 390 px.** The canvas is full width and square, the chip bars wrap, the card sits
  below, and there is no sideways scroll. Pan is a one-finger drag on the canvas only
  (`touch-action: none` on the canvas, not the page).
- **After a turn or a walk**, the view refreshes the way `refreshSettlementView` does now.

---

## 9. Saves, rewind, new game

- **Export and import.** `town_cells` and `town_seen` join the exported table list as
  ordinary world tables and are **not** added to `_REPLACE_ONLY_WHEN_EXPORTED`. That set
  means "skip the table when the save does not name it", which would keep the previous
  campaign's town rows and leak its seen streets into a loaded old save. As ordinary
  tables they are cleared on every load and refilled from the save, so a save made before
  this loads with them empty. On export both are filtered to `map_id in campaign_map_ids(conn)`, the same rule
  `campaign_map_rows` applies (#25). `prune_world_maps` deletes their rows for dropped
  maps. `town_position` travels in `settings`. The new `locations` and `npcs` columns
  travel with their tables. Old saves get `''` from the migrations.
- **Rewind.** Existing machinery covers it **only because the town writes happen after
  `_save_snapshot`** (5.1, `apply_town_plan`). Had they stayed in `resolve_movement`, which
  runs before the snapshot, every one of the lines below would be false:
  - `town_position` is in `SNAPSHOT_SETTING_KEYS`, read by `_save_snapshot` before the
    walk is applied, so a rewind restores the pre-walk position;
  - `town_seen` joins `AUTOINC_TABLES` and the delete order, so rows a turn appended
    (after the snapshot) are removed by max id. It is append-only, so this is exact, with
    no snapshot rows at all;
  - realized venues are new `locations` rows made after the snapshot, removed by max id;
    `npcs.workplace_plot` rides the `npcs` rows the turn already snapshots;
  - the plan phase writes only `town_cells` (below) before the snapshot;
  - `town_cells` is a deterministic cache and is not rewound. A cell generated in a
    rewound turn stays generated, which is harmless;
  - **reconcile after rewind and load:** when `town_position` is present, put the world
    marker on `(cx, cy)` with `restore_player_position` (no travel cost). This also closes
    the existing gap (section 1) for town walks. The general gap (world walks are not
    rewound) stays open. Snapshotting the world `{x, y}` the same way is a one-line
    follow-up, noted in section 11.
- **Click-walks between turns** are not snapshotted, which is the same as world-map clicks
  today. Rewinding the next turn keeps them. Rewinding further back undoes them with that
  turn's settings.

---

## 10. Build order

Each slice ends green on the full suite
(`.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"`;
`test_fallback_abilities_pass_gate` is known flaky). Each slice is committed separately.
Probes isolate every data path (`isolated_data_env` plus `AI_RPG_IDEA_BANK`,
`AI_RPG_LAUNCHER_PREFS`, `AI_RPG_SKILL_LIBRARY` and `AI_RPG_PACK_DIR`) and never write under
`data\`.

### Slice A: generator, storage, read API

1. `app/town_grid.py`: `city_ports`, `generate_cell(world, city, cell, era) -> TownCell`
   (pure), `encode/decode`, `get_cell(conn, chart, cx, cy, *, create)` (cache, LRU),
   `GEN_VERSION`, `PORT_VERSION`, kind weight tables, `town_seen` folding helpers.
2. `example_pools.py`: `venue_kind` context for `venue_name`; new `street_name` rendered
   kind.
3. `db.py`: the two tables and three columns (migration). Export, import and prune wiring.
4. `GET /api/town/view` and `GET /api/town/plot/{id}` (read-only), and the `town` block on
   the settlement route.
5. `tools/probe_town_grid.py`: builds an isolated world and generates a sample of cells
   (the centre 128 cell, an outer cell, a hamlet). Prints timings, row sizes, plot and
   shop counts per district type, and an ASCII render of a cell to read by eye.

Tests (`tests/test_town_grid.py`):
- determinism: same inputs give byte-identical rows; generating cell A first or B first
  gives identical rows;
- laziness: `get_cell` for one cell creates exactly one row; `city_ports` reads no fine grid;
- legacy compatibility: every `street_mask` tile is a road; `cell_raster` and
  `tiles_in_cell` are unchanged for the same cell;
- connectivity: every road tile and every port reachable in a cell; in a full sample
  9 x 9 city (test-only), the whole network is connected through the ports, and both sides
  of every shared-edge port are road;
- plots: no overlap, no plot on a road tile, every non-yard plot's frontage is a road tile
  orthogonally next to it, landmarks at temple and government anchors;
- shops: every stall maps to a shop plot **in its own district** with a fitting kind,
  never a landmark, including a seed where the stall position wraps across the cell; shop
  share (after caps) ordered shopping > food/craft > residential > temple/government over
  a fixed set of seeds; per-district kind caps hold and a capped roll falls through to the
  ward's "otherwise" row; every `VENUE_KINDS` key has a weight row;
- notices: a far notice stored in cell A's list appears in cell B's plots and not A's;
  generating A then B and B then A gives identical rows;
- skeleton: stages 1-2 recomputed in memory equal the same stages of the stored row;
- era: a modern world has no smithy or alchemist plots, and a preindustrial one has no
  garage;
- names: unique per city; each one classifies to its `vk` or is a sign form on an inn,
  tavern or bar, including `{street}` forms ("Wheel Street Bakery"); no name ends on a
  closed word;
- budget: a 128 cell generates in under 1 s and encodes to under 96 KB;
- storage: a cached row is returned without regenerating, and a row with an older
  `gen_version` is kept as is;
- read API: only seen plots and roads come back; a seen ungenerated cell returns its
  skeleton and the request creates no `town_cells` row (row count unchanged); `r > 1` is
  refused; a non-world or legacy map reports `available: false`; a hamlet works;
- saves: export filtered by map, prune, and an old-format save without the tables loaded
  **after a game that walked a town** leaves `town_seen` and `town_cells` empty.

### Slice B: engine integration

1. `town_position` and the world-marker invariant; entering, leaving and crossing cells
   (4.2); start-in-city.
2. Pathfinding with `port_dist`, minutes and budget; `_spend_travel(conn, ...)` split out
   of `apply_map_travel_step`; `POST /api/town/walk`.
3. Settlement-row adoption, `realize_plot`, positional containment in
   `venue_entry_check`/`gate_venue_move` for `plot_id` rows.
4. `plan_town_move` before the prompt, `apply_town_plan` after `_save_snapshot`, the
   bounded lookup, and the `plan_story_walk` town skip; in `resolve_movement` the plotted
   branches of `_venue_shown_in_prose`,
   `_venue_for_named_move` and `_mint_venue_from_request` (disabled there); the rename
   report and the narrow prose rename.
5. Workplaces claim plots (`plan_npc_workplace`, `ensure_npc_workplace`,
   `_realize_named_workplaces`).
6. The `movement_contract.town` block; removal of `venue_name_options` and
   `venue_kinds_possible` in town; the conditional town DSL bullets; road bearings.
7. Knowledge (`town_seen` appends on every walk, told plots from `local_intel`).
8. Rewind and load reconcile.

Tests (`tests/test_town_movement.py`, writer-off fixtures, no model):
- enter from the world at a gate and at a gateless edge; cross a shared edge; leave by a
  gate;
- walk minutes equal the path sum for both side 128 and side 64; a 60-minute walk stops at
  40 with `partial`;
- typed targets: plot name, "go to the bakery" (nearest known, else nearest generated,
  else the bounded lookup), "enter the inn" at the door, street name, "leave the shop", a
  trade a fully generated small city lacks (no move, `town_none`, no row made), a trade
  missing from a 9 x 9 city's generated cells (`town_unknown`, at most 2 cells generated,
  no row made);
- plan before prompt: the prompt context of the walking turn carries `arrived`/`walking`
  from the plan, and `apply_turn` applies the same path;
- spend: an in-turn walk and `POST /api/town/walk` advance the clock on the caller's
  connection (no second connection); an energy-blocked walk leaves `town_position`, the
  marker, `town_seen` and the clock unchanged;
- story walk: "walk east to the bakery" in town leaves `world_maps.player` equal to
  `(cx, cy)`; "out the north gate" hands off to the world walk from the gate cell;
- settlement row: an existing unanchored top-level row named like the city is adopted, not
  duplicated (no UNIQUE error);
- realization: a row with `plot_id`, parent settlement row, kind, hours; idempotent; name
  clash stores "<name> on <street>" plus an alias, and `row_kind` still gives the plot's
  kind; closed shop leaves the player at the door;
- MOVE "Blind Owl Bakery" re-aimed at the real bakery and the prose name replaced; an
  unshown move still dropped (#6c rule unchanged);
- prose entering a listed plot with no MOVE enters it; prose entering an unlisted kind
  mints nothing;
- workplaces: a baker NPC claims a bakery plot in a generated cell, `works_at` carries
  the plot name, no row is made until visited, two bakers never claim one plot; with no
  bakery generated the plan stays unclaimed with no name, and is claimed when a cell with
  one is generated; planning generates no cell;
- contract: `places_here` lists only seen plots, at most 8; no `venue_name_options` in
  town; the town DSL bullets replace the general invent/next-turn/hike bullets; the legacy
  contract and DSL text are unchanged outside towns and on legacy maps;
- rewind: rewinding a turn that walked, entered a plot and saw new tiles restores the
  pre-walk `town_position`, deletes that turn's `town_seen` rows and the realized
  `locations` row, and reconciles the world marker;
- the existing venue, movement and #33/#50 tests still pass unchanged.

A **live check** on the 8B uses the staged-playtest or setup-preset harness against an
isolated database: a town walk, entering a named shop, asking for a missing trade. The
#55 count from the transcript is reported, whatever it shows.

### Slice C: UI

1. The City | Streets chips, the Streets canvas painter (generated cells and skeletons),
   pan, plot hit-testing, peek, card and menu (Go to, Go in, moon-coloured Walk here now),
   Walk here and Go in on the card, arrow walking, auto-zoom on entering.
2. Layout in `styles.css` and the look in `skin.css`, with no colour in `styles.css`.
3. Verify with headless Playwright (system python) on an isolated scratch uvicorn
   (`AI_RPG_MODEL_PROVIDER=mle`, a nonexistent `MLE_MODEL`, a free port). Use a debug save
   that stands in a plotted city. At 1440 px and 390 px: open the map, switch to Streets,
   click a shop, Walk here, check that the marker moved and the clock advanced, check that
   Go in and the menu's Go to write their sentences and that Walk here now carries the moon
   class, and check no page errors and no sideways scroll. Take
   screenshots of both widths. Kill the server afterwards.

---

## 11. Open points, decided defaults, and risks

- **Tile scale varies by cell** (6 m at the centre, up to 100 m in a hamlet cell). This
  keeps every existing consumer valid. The cost is that outer-cell buildings are drawn
  coarser. The alternative was a fixed tile size with fabric centred in the cell, which
  needs outskirt geometry and a new raster. It was rejected for v1.
- **The world-map marker is not rewound** today (section 1). Town position reconciles the
  marker; plain world walks still do not. Follow-up: snapshot the world `{x, y}` in a
  settings key and reconcile after rewind.
- **Fixed district names** (`world_scale._DISTRICT_NAMES`) and city names
  (`_NAME_LEFT/_NAME_RIGHT`) are still fixed lists, which goes against the pools rule.
  Changing them would rename districts in existing saves, so it is out of scope here and
  noted for 1.0.
- **Stalls versus plots.** `local_intel` answers far questions from stalls without
  generating cells, and plots honour stalls. If a future change to `stalls_for_district`
  moves stalls, cells already stored keep their old shops. Treat the stall function as
  frozen, like `PORT_VERSION`.
- **NPCs on the street** (who stands outside which plot) are not part of this design. The
  scene's people stay attached to the location row, as now.
- **Budgets in 3.6 are estimates** until the slice A probe measures them.
- **Lookup trade-off.** Bounding lookups (5.1) means a large city can answer "no smithy
  known nearby" while one exists in a far ward. That is honest (the player has not been
  there) and the player can ask around or walk; a cheap per-city kind census was
  considered and rejected for v1 because generation would then have to honour it, which
  couples the plot rolls to a second, earlier set of rolls.

---

## 12. Review notes

Critic review of the first draft, with each finding checked against the code before it
was decided. All 14 were confirmed and accepted; none was rejected.

| # | Finding | Decision | Where |
| --- | --- | --- | --- |
| R1 | The in-turn walk in `resolve_movement` runs before `_save_snapshot` (`world.py` around 14971-14985), so its `town_seen`/`locations` rows sit at or below `max_ids` and `town_position` is captured after the walk; rewind would not undo it. | **Accepted.** Chose the deferral option: town writes move to `apply_town_plan`, after `_save_snapshot` and before `_apply_player`. Rejected the `pre_rows` option because `_save_snapshot` computes `max_ids` itself and would need a new override path. Rewind test added. | 5.1, 9, slice B tests |
| R2 | `movement_contract` is built before the draft; `resolve_movement` runs after it, so `arrived`, `walking` and `town_none` could not reach this turn's prose. | **Accepted.** Split into a pure `plan_town_move` before the prompt and an apply after the snapshot; the contract reads the plan. | 5.1, 5.3 |
| R3 | Typed lookups, `town_none`, workplace claims and `told` needed every cell generated, breaking laziness. | **Accepted, option (b) with a bound.** Search generated cells; small cities (≤ 5 cells) generate whole; larger ones generate at most 2 more cells; `town_none` only when the city is fully generated, else `town_unknown`. Claims only in generated cells, else an unclaimed nameless plan retried on generation. `told` stores stall/notice ids for ungenerated cells. Option (a), a kind census, rejected (section 11). | 3.6, 4.4, 5.1, 5.2, 5.3, 6 |
| R4 | `_REPLACE_ONLY_WHEN_EXPORTED` keeps the previous campaign's rows when an old save lacks the key: a fog leak, the opposite of what the draft said. | **Accepted.** Both tables are ordinary world tables, cleared on every load. Test loads an old save after a town walk. | 9, slice A tests |
| R5 | `apply_map_travel_step` opens its own connection (deadlock risk inside the turn) and can hard-block on energy after the draft had written the position. | **Accepted.** `_spend_travel(conn, ...)` split out; preview, commit, advance order; a block writes nothing. Same for `POST /api/town/walk`. | 4.3, 5.1, 7 |
| R6 | `_apply_story_map_walk`/`plan_story_walk` would step the world marker off `town_position` (up to `STEP_BUDGET` steps on a compass word). | **Accepted.** `plan_story_walk` skips with reason `town`; leaving town hands off from the gate cell. Test checks the marker stays on `(cx, cy)`. | 5.1, slice B tests |
| R7 | `{place}` reduces to one word ("Wheel Bakery"), and the "on Wheel Street" clash suffix makes `venue_kind_from_name` return `""`. | **Accepted.** New `{street}` slot with the full street name; plot rows classified by stamped `kind` via `venues.row_kind`, with the plain name kept as an alias. | 3.4, 4.4, tests |
| R8 | Stall positions wrap modulo `side`, so "nearest frontage plot" can land in another ward or on a landmark. | **Accepted.** Nearest frontage plot within the stall's own district, never a landmark, next nearest on a collision; wrap case tested. | 3.4, slice A tests |
| R9 | Far notices live in the origin cell's list but point at another cell. | **Accepted.** A cell collects notices whose `(x, y)` is itself from every cell's list; A-then-B and B-then-A test with a far notice. | 3.3, slice A tests |
| R10 | Per-cell caps (about 96-184 venues at side 128) cannot coexist with the stated shop rates over 900-1,500 plots, and the capped case was undefined. | **Accepted, both halves.** Caps are per district, the overflow rule is written (redraw among uncapped kinds, then the ward's "otherwise" row), and the stated rates are labelled pre-cap with the post-cap share measured by the probe. | 3.4 |
| R11 | The existing DSL bullets still say "otherwise name the building and it is created" and "going in costs the next turn", contradicting walk-and-enter. | **Accepted.** Those bullets and the hike bullet are swapped for town versions while the town block is present; legacy text unchanged elsewhere (tested). | 5.3, slice B tests |
| R12 | Creating the settlement row can hit `locations.name UNIQUE` when an unanchored row with the city's name exists. | **Accepted.** Adopt any kindless top-level row with the city's name first; create only when none exists; a venue row with that name forces the band-word form. | 4.2, slice B tests |
| R13 | "Seen" covers vision and revealed maps, far more than walked cells, so the Streets view would generate inside a GET. | **Accepted.** GETs never generate or write; seen ungenerated cells show an in-memory skeleton (stages 1-2), at most 9 per request. | 3.6, 6, 7, slice A tests |
| R14 | UI_RULEBOOK §3.7: immediate menu actions must say so and use the red moon. | **Accepted.** The menu's immediate item is "Walk here now" in moon colour; "Go to" and "Go in" write sentences. | 8, slice C |

---

## 13. Slice A build notes

Built in `app/town_grid.py`, tested in `tests/test_town_grid.py` (37 tests), measured with
`tools/probe_town_grid.py` (seed 20261007, `forest_march`, density 60, warm imports).

### Measured (replaces the estimates in 3.6)

| Item | Target | Measured |
| --- | --- | --- |
| Generate + store the 128 centre cell | ≤ 150 ms (limit 1 s) | **~200 ms** (over target, under the limit). About 90 ms is roads and plots, the rest names. |
| Outer cell (side 44) / hamlet (side 28) | | 83 ms / 9 ms |
| Plots in the 128 cell | 900–1,500 | 1,906 |
| Stored row, 128 cell | 20–40 KB (limit 96 KB) | 38.5 KiB; largest seen 41.2 KiB |
| `city_ports`, 25-cell city | ≤ 5 ms | 0.3 ms |
| Load and decode a row | ≤ 10 ms | 3–5 ms |
| Skeleton, 128 cell | ≤ 15 ms | 5 ms |
| Memory | | 2.0 MiB peak to generate a 128 cell; the 9-cell LRU of decoded rows holds about 8.5 MiB |
| Whole largest real city (25 cells) | | 3.1 s, per cell median 127 ms, max 227 ms, 712 KiB stored |
| Synthetic 9 x 9 box (47 cells, sides 46–128), in memory | | 8.4 s, per cell median 171 ms, max 291 ms, 1.3 MiB encoded |
| Stalls placed on plots | 0 unplaced above side 24 | 277 of 277 |

Shop share after caps (shop + service per frontage plot, landmarks and gates excluded), 25-cell
city: shopping 0.52, food 0.37, craft 0.32, black market 0.17, residential 0.04, temple 0.02,
government 0.02, military 0.01.

### Deviations from this design

1. **Kind caps scale with the ward, not the cell.** 3.4's `max * side / 64 * density / 50`
   measured market wards at 0.19 shops per frontage plot, below craft wards (0.21): a market
   ward has hundreds of frontage plots and the per-kind caps ran out long before the rolls.
   `kind_cap` now uses `max * frontage_plots_in_district / 32 * max(density, 20) / 50`. The
   overflow rule is unchanged. A big market ward can now hold a couple of dozen bakeries.
2. **Names are owned by one cell, not excluded by what is stored.** `draw(..., exclude=used_in_city)`
   contradicts the slice A test "A first or B first gives identical rows": with a few hundred
   street names per city, two cells drew the same name in the first seed tried. Each name now
   hashes to one owning cell of its city (`NameOwners`, streets weighted by side, buildings by
   side squared) and a cell draws until it renders a name it owns (`example_pools.draw` gained
   `accept` and `max_attempts`). A building with no owned name after 40 renders takes a
   `{street} {trade}` name on a street of its own cell, which is unique because the street is.
   Large cities therefore have more street-form names in their outer wards. Stored names of
   rows from another `GEN_VERSION` are still excluded.
3. **Side streets run on across ward boundaries** until they meet a road. Stopping one tile past
   the boundary left most lines dangling and dropped, and the cells were mostly yards.
   `SIDE_STREET_PASSES = 4` passes of cross streets fill the grid outwards. Cells below side 16
   get no side streets (connectors only).
4. **Stored extras:** plots carry `st` (`"<district id>:<stall index>"`, to fold `told` stall ids),
   `nt` (notice ids) and `gate` (compass word). The plot `id` is not stored; it is rebuilt on
   decode. `town_seen` bitsets are zlib-compressed before base64. Gate names are city-unique
   labels from `city_ports` ("North Gate", "South Gate 2"). Landmark offices and barracks take
   their district's existing name.
5. **Read API fog.** A plot's kind shows once its frontage tile is in a `town_seen` road bitset;
   its name once its bit is in a `town_seen` plots bitset, it is told, or it is realized. Avenues
   and main roads of a seen cell are always drawn, but a segment's name only once one of its
   tiles was seen. Nothing writes `town_seen` yet (slice B).
6. **New playthrough** clears `town_cells` and `town_seen` (the era may differ).

### Known limits

- District names (offices, barracks) can repeat between cells of one city; they come from the
  fixed `_DISTRICT_NAMES` (section 11).
- Big blocks keep large interior yards: plot depth follows 3.2, so a residential block of
  75–105 m keeps back gardens.

## 14. Slice B build notes

Built in `app/town_moves.py`, wired into `app/world.py` (play_turn, resolve_movement, apply_turn,
the story walk, workplaces, rewind, load), `app/main.py` (`POST /api/town/walk`, map steps),
`app/turn_dsl.py`, `app/prompts.py`, `app/llm.py`, `app/local_intel.py`, `app/player_resources.py`
and `app/venues.py`. Tested in `tests/test_town_movement.py` (42 tests, writer-off, no model).

### What a turn does

1. `plan_turn` (play_turn, before the prompt): places the player when they stand on a city cell
   with no `town_position` (game start, an old save; the shopping ward's road, else the hub),
   reads the player's own words and returns the plan and the `movement_contract.town` block. It
   writes only `town_cells`.
2. `resolve_town_movement` (first thing in `resolve_movement`, before the snapshot): engine plans
   win over the draft's MOVE; a MOVE naming a plot, a realized plot row, a street or a ward is
   re-planned with no generation; a MOVE whose name holds a trade word is re-aimed at the nearest
   generated plot of that trade (`renamed`, and the narrow prose rename when the name occurs
   verbatim and no other invented building does), else dropped with `prose_mismatch`. The #6c
   unshown-move rule runs first, unchanged. With no MOVE, an entry the prose shows goes into the
   plot at or beside the player's door that matches it; nothing is minted. LOC_NEW rows whose name
   is a building the grid does not have are not stored. A MOVE to a known place outside the grid
   (no kind, no parent) returns to the legacy rules, which is how world travel out of town works.
3. `apply_town_turn` (apply_turn, right after the snapshot): preview the spend on the caller's
   connection, commit `town_position` and the marker, record `town_seen`, then `_spend_travel`;
   realize the plot when the plan enters and it is open, and set the move to its row (or to the
   settlement row when a walk leaves a building).

### Measured (tests and a scratch probe, seed 20261007, `forest_march`)

- `plan_turn` with a typed target in a generated 128 cell: 15-40 ms; first placement including
  the cell's generation about 0.12 s; a full fake-draft `play_turn` in town about 0.2-0.45 s.
- A walk to the nearest bakery from the shopping ward's road: 2-3 minutes; the nearest gate of a
  three-cell city: 25 minutes.

### Deviations from this design

1. **No `port_dist` cache.** A route is the fewest-cells path over the city's cells (BFS), then a
   fine BFS in each cell from the entry port to the exit port. That is not a Dijkstra over port
   distances, so a cross-city walk can be longer by road than the best one. Cells are generated as
   the walk reaches them, at most 5 per turn (`MAX_CELLS_PER_TURN`); a walk stops where the cells
   or the 40 minutes run out (`partial`, with an estimate of the minutes left).
2. **Map arrow steps between cells of one city** keep the flat 10-minute world step and put the
   player on the shared port of the new cell, instead of a town walk with town minutes.
3. **Leaving through a gate** puts the world marker one cell outside the gate edge, so the next
   turn does not place the player back in town. The world walk after it keeps its full budget
   (the town minutes are not subtracted).
4. **Entering by a map step** moves the current location to the settlement row (unless it already
   is one of this city's rows). A story walk into a city does not: the turn's MOVE decides.
5. **Bearings (5.4)** are not a separate block. `places_here` entries carry minutes and a compass
   word for what is ahead, and `arrived` / `walking` name the target.
6. **`travel_ready`** gates only the click-walk (leaving the cell). An in-turn walk is the player's
   own action; confinement (`movement_locked`, `map_blank`) refuses both.
7. **A slice A gap fixed here:** `town_seen` was in `AUTOINC_TABLES` but not in the rewind delete,
   so a rewound turn kept its seen rows. It is now deleted by max id, like the quest tables.
8. `town_seen` compaction past 64 rows a cell is not built.

### Not done in slice B

- **The live check on the 8B** (a town walk, entering a named shop, asking for a missing trade,
  and the #55 count from the transcript) was not run: the GPU was in use by the user's own
  application when this slice was built. It is the first thing to run before slice C.
- The UI (slice C): the click-walk route exists, nothing calls it yet.

## 15. Slice C build notes

Built in `static/app.js` (the "Town streets" block), `static/index.html`, `static/styles.css`,
`static/ui/skin.css` and `static/ui/interact.js`. Tested in `tests/test_town_ui.py` (14 tests: the JS
functions run in node with stubs, plus the markup and file-split contract) and checked headless with
Playwright at 1440 x 960 and 390 x 844 on an isolated scratch server (seed 20261007, `forest_march`, the
player in Moorford, a three-cell city): auto-zoom on entry, click a shop, Go in writes its sentence, Walk
here moves the marker to the plot's door and advances the clock, the menu's Go to writes its sentence and
Walk here now carries the moon class, an arrow key walks to the next junction, drag pans, + zooms, a click
on a City cell zooms to its streets, World goes back and sets the flag; no page errors, no sideways scroll.

### Deviations from this design

1. **The card is used at every width.** Section 8 put a desktop plot in the peek shard; the peek system is
   for entities with a code, and a plot has none until it is realized. The card sits under the canvas on
   desktop and phone alike; desktop also gets the map's hover tip with name, kind and open or closed.
2. **Road strokes are heavier.** Streets as a `--line-strong` hairline were not visible beside the plot
   outlines in the screenshots. Avenues and main roads are `--thread-dim` at 3 px, streets `--thread-dim` at
   1.5 px, alleys `--line-strong` dotted.
3. **Zoom.** − / + chips and the mouse wheel scale the view (0.5x to 3x, about 6 px a tile by default);
   pinch is not handled. Every world cell is drawn the same size, so a cell with a smaller side has bigger
   tiles.
4. **Gated wards are not drawn in the moon colour.** The view's plots carry no ward, so `requires_entry`
   cannot reach the painter; the City zoom still marks gated wards.
5. **The preview thread** is drawn only inside the player's own cell, over the roads the player knows,
   in `--thread` fading out (`--thread-soft` was too faint to read).
6. **Arrow keys and the pad** walk to the next junction in the player's cell; at the cell's edge they walk
   into the neighbouring cell at the matching tile (needs `travelReady`).
7. **Long-press** is a 550 ms pointer timer on the canvas that opens the same interact.js menu
   (`MorkynInteract.openMenu`), because iOS sends no `contextmenu` for a touch.

### Known limits

- At 390 px the game's existing two-column phone layout leaves the map column about 200 px wide, so the
  Streets square is small there; + and drag make it usable. The layout itself is not part of this slice.
- Clicking a road tile walks to the nearest road; there is no way to click an unseen tile, because unseen
  roads are not drawn.
