# Dice rolls & skill checks

Optional system for contested or uncertain actions: inspecting symbols, forcing doors, speech contests, random events, and encounters.

## Toggle

Setup → **5 Checks** → **Dice checks: On**.

When **Off**, play stays pure narrative (default).

## How resolution works

```text
natural = dN
total   = natural + attribute_mod + skill_rank
DC      = skill base + difficulty + contested opposition power (± power RNG)
```

Play UI shows a **roll banner** under the narration:

```text
You rolled 13 with your base of 9 (strength) and a modifier of -1.
Total: 12  ·  Base success (DC): 25  ·  vs Guard power 17
Result: critical failure (unskilled mishap)
You are unskilled at wielding sword — you injure your own leg…
```

| Degree | Feel |
| --- | --- |
| critical success | Effortless / beyond intent |
| success | Clean win |
| barely | Just scraped through |
| partial | Incomplete info / costly glimpse |
| failure | Nothing useful |
| bad nothing | Almost as if you did nothing at all |
| unskilled mishap | Tool/weapon hurts *you* |
| critical failure | Disaster + setbacks |

### Contested power

DC is **not** a fixed 20. With **contested checks** on, enemy/object stats, rank, defense, and a small **power RNG** set how hard the thing is.

### Specialized skill salvage

Low Intelligence + **Symbol Lore** rank ≥ threshold can still yield a **partial** reading instead of a blank.

### Lasting injuries

Severe unskilled fails can:

- apply `health_delta`
- store `player_conditions` (limb injuries with combat penalties)
- surface an **Injury** line on the roll banner

## Settings (setup tab 5)

| Setting | Default |
| --- | --- |
| Dice checks | Off |
| Dice | d20 |
| Contested vs enemy/object | On |
| Power RNG + variance | On / 3 |
| Unskilled mishaps | On |
| Severe mishap on crit fail | On |
| Auto-check risky actions | On |
| Degree flavor lines | On |
| Show rolls in UI | On |

## Pipeline fit

Checks run **after** the model turn, **before** `apply_turn`:

1. Model drafts narration / ops as usual  
2. Server resolves real dice (model cannot fake the roll)  
3. Injuries merge into player patch + journal  
4. Response includes `skill_checks[]` for the UI banner  

Auto-check uses player input keywords (`attack`, `inspect symbols`, `sneak`…) plus combat target stats when present.

## Durable skill library

`data/skill_library.json` — new skills compared to peers for DC balance; enable/disable per skill.

## APIs

| Method | Path |
| --- | --- |
| GET | `/api/skill-checks/catalog` |
| POST | `/api/skill-checks/resolve` (supports `opposition`, `weapon_or_tool`) |
| POST | `/api/skill-checks/register` |
| POST | `/api/skill-checks/enable` |
