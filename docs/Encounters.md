# Encounters and the danger model

Whether something happens while you move, wait, or rest is decided entirely by
the server in [`app/encounters.py`](../app/encounters.py). The model narrates
the result; it never decides whether an ambush occurs, how many bandits there
are, or how dangerous they were.

## Two stages

Danger is **not** a single additive score. Environment sets the level; the
player scales it.

```text
danger = environment(additive) × player_multiplier(multiplicative, damped)
```

**Environment terms are additive** — terrain baseline, weather, hour of day,
roads and settlements, campaign difficulty, standing on an undiscovered camp.
These are properties of the world.

**Player terms are multiplicative** — awareness stats, field skills, level vs.
terrain, wounds, fatigue, low energy, carried load, notoriety, local standing,
and danger markers the player already knows about.

The first version made player bonuses additive, and it was wrong: a handful of
them cancelled a town's entire base risk and every skilled character became
untouchable. Multiplying means a great scout in a dungeon is still in a
dungeon — meaningfully better off than a novice there, but not safe.

The combined player multiplier is damped in log space
(`raw ** 0.55`, clamped 0.4–2.6). Without damping, six mild penalties compounded
to ~6.5× and pinned every unlucky character to the cap, erasing the difference
between "having a bad day" and "about to die".

## What actually moves the number

| Factor | Direction | Source |
| --- | --- | --- |
| Terrain baseline | sets the level | tile state, pack-overridable |
| Weather kind × strength | raises | server weather sim |
| Night / dawn / full daylight | raises / lowers | world clock |
| Road, bridge, settlement | lowers | tile state |
| Undiscovered hidden base on tile | raises sharply | map meta |
| Campaign difficulty | raises / lowers | playthrough options |
| Wisdom, dexterity | scales down | `player.effective_stats` |
| Perception, ambush sense, survival, navigation, stealth, streetwise | scales down | player skills |
| Low level in high-risk terrain | scales up | player level |
| Low energy, high fatigue, wounds | scales up | player resources |
| Carrying over 75% of capacity | scales up | inventory summary |
| Deep negative karma | scales up | notoriety attracts trouble |
| Area reputation | scales up / down | local standing |
| Known danger markers nearby | scales down | you route around them |

Bands: `calm` < 0.10, `uneasy` < 0.22, `dangerous` < 0.40, `deadly` above.

## Example

Identical tile, identical weather, identical hour — different characters:

```text
expert  / forest / noon        env=0.130 ×0.74 = 0.097 calm
average / forest / noon        env=0.130 ×0.93 = 0.121 uneasy
novice  / forest / noon        env=0.130 ×2.60 = 0.338 dangerous
novice  / forest / night storm env=0.373 ×2.60 = 0.950 deadly
```

## From danger to an event

Exposure compounds with time:

```text
chance = 1 - (1 - danger) ** hours      (floor of 0.12 hours per step)
```

A five-minute step through a deadly swamp is survivable; four hours of it is
not.

When something fires:

1. **Kind** is picked from the terrain's weighted table (bandit ambush, wild
   threat, hidden base, traveler, or anything a pack defines).
2. **How many** is rolled from the kind's `count_band` via the dice authority —
   never asked of the model.
3. **How dangerous** is rolled from its `threat_band`.
4. **Awareness**: the player passively rolls the kind's `avoid_skill` against
   `DC 10 + danger × 12`. Passing means `forewarned` instead of `surprised` —
   the difference between an ambush and a standoff. A clean read on a
   non-hostile meeting can avoid the encounter entirely.

## Inspecting it

`GET /api/danger` returns the current assessment for the player's tile with its
full factor breakdown:

```json
{
  "danger": 0.338,
  "band": "dangerous",
  "environment": 0.13,
  "player_multiplier": 2.6,
  "factors": [
    {"name": "terrain", "delta": 0.16, "detail": "forest baseline (builtin)"},
    {"name": "fatigue", "mult": 1.495, "detail": "fatigue 85%"}
  ]
}
```

Factors carry `delta` when additive and `mult` when multiplicative.

Travel results include the same keys on `travel.encounter`, and the journal
records a `travel` line per step.

## What the narrator is told

Only the *feel*, never the arithmetic:

```json
{
  "band": "deadly",
  "reasons": ["swamp baseline", "Heavy storm (strength 0.90)", "fatigue 85%"],
  "reliefs": [],
  "note": "Danger is server-simulated. Convey it as atmosphere; never quote numbers or odds to the player."
}
```

## Retuning

Terrain chances and encounter kinds are content-pack data — see
[ContentPacks.md](ContentPacks.md):

```json
"encounter_tables": {
  "terrain": {"forest": {"base_chance": 0.05, "kinds": {"traveler": 100}}}
}
```

## Fallback

If the danger model raises for any reason, travel falls back to the legacy
terrain-plus-weather roll. Walking never breaks because a new subsystem
misbehaved.
