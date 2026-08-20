# Dice authority — who decides "how much"

The model narrates. **The server decides every amount.**

```text
model says WHAT and HOW BIG (a band)  ->  app/rng.py says HOW MUCH (a number)
```

## Why

Local 8B models are poor at arithmetic and worse at restraint. Asked for an XP
number they mint 250, then 400 the next turn, and a campaign's economy is gone
by turn thirty. Asking only for a *band* removes the arithmetic from the model's
job entirely — which also makes its required JSON smaller and its failure modes
fewer.

## Bands

Six words, smallest to largest:

```text
none · trivial · small · moderate · large · huge
```

Prefix `-` for a loss: `-moderate` gold is a meaningful expense, `-small`
health is a scratch.

Synonyms are normalized, so `major`, `MAJOR`, `a large reward` and `large` all
land on `large`. Unrecognized text becomes `none` rather than an error.

## Fields

| Turn field | Magnitude kind | Replaces |
| --- | --- | --- |
| `player.xp_band` | `xp` | `xp_delta` |
| `player.gold_band` | `gold` | `gold_delta` |
| `player.health_band` | `damage` | `health_delta` |
| `player.karma_band` | `karma` | `karma_delta` |
| `inventory_changes[].quantity_band` | `item_count` | `quantity_delta` |
| `npcs[].trust_band` | `trust` | `trust_delta` |
| `events[].fame_band` | `fame` | `fame_score` |
| `skill_changes[].delta_band` | `skill_gain` | `delta` |

In the NAR+OPS DSL the same applies: `XP small`, `GOLD -trivial`,
`GRANT "rope" QTY small`, `SKILL "Streetwise" DELTA small`.

## How a band becomes a number

```text
value = roll(dice for that band)
      × level scaling        (none | level | level_soft)
      × difficulty factor    (reward axis down / threat axis up on hard)
      × growth speed         (xp_growth_speed, skill_growth_speed, …)
      clamped to the table's min/max
```

So `xp_band: "moderate"` on a level-1 character on normal difficulty rolls
`2d6+6`; the same band at level 20 on `very_slow` growth produces something
quite different. The model never has to know any of that.

## Raw numbers still work

If a model writes `xp_delta: 250` anyway, it is **not** trusted and **not**
rejected. It is read as an *intent signal* — "they wanted something huge" —
bucketed to the nearest band, and re-rolled properly. Old prompts, cached
browser clients, and third-party agents keep working while the arithmetic still
moves server-side.

Control this with `AI_RPG_BAND_AUTHORITY` or the `band_authority` playthrough
option:

| Mode | Behaviour |
| --- | --- |
| `rolled` *(default)* | Bands rolled; bare numbers re-rolled as band hints. |
| `bands` | Bands rolled; explicit numbers passed through (still clamped). |
| `off` | Legacy behaviour; bands ignored. |

## Determinism

Rolls are seeded from `(campaign seed, turn, tag, sequence)` using blake2b —
not Python's randomized `hash()`. A rewind and regenerate in a fresh process
reproduces the same dice. The campaign seed is created once and stored in
`settings.campaign_rng_seed`, so exporting a world exports its luck.

## Audit trail

Every roll is written to the `dice_rolls` table and summarized into the turn
journal under kind `dice`:

```text
xp (moderate): 2d6+6 [3, 2] +6 = 9 · gold (small): 2d6+3 [4, 4] +3 = 11
```

Read it back with `GET /api/dice/recent?limit=40` or
`GET /api/dice/recent?turn=12`. "Why did I only get 7 gold" has an answer.

## Dice notation

Used in `magnitude_tables` and anywhere else a table declares dice.

| Form | Meaning |
| --- | --- |
| `2d6` | two six-sided dice |
| `2d6+3` | …plus a flat 3 |
| `4d6kh3` | roll four, keep the highest three (`kl` keeps lowest) |
| `12` | a flat amount, no roll |
| `0` or `""` | nothing |

Limits: 1–40 dice, 2–1000 faces. Anything else fails validation loudly rather
than silently rolling something unintended.

## Retuning the tables

Any band's dice can be replaced by a content pack — see
[ContentPacks.md](ContentPacks.md). This is how you make a low-magic,
low-treasure campaign without touching code:

```json
"magnitude_tables": {
  "gold": {"bands": {"moderate": "1d6", "large": "2d6+2", "huge": "3d8+6"}}
}
```

## Kinds

`xp`, `gold`, `damage`, `heal`, `item_count`, `trust`, `karma`, `fame`,
`skill_gain`, `duration_minutes`, `count_people`.

`GET /api/content-packs/authoring-bundle` returns the live list.
