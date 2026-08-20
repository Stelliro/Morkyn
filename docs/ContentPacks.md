# Content packs

A **content pack** is one JSON file that adds, retunes, or removes game content
without touching code: skills, powers, items, encounter tables, and dice tables.

Packs exist so you can either edit content by hand, or hand the specification to
a capable LLM and ask it to write content for you — including a model that has
never seen this project.

---

## Install and remove

| Action | How |
| --- | --- |
| Install | Save the JSON as `data/packs/<pack_id>.json` and restart, or `POST /api/content-packs/install` |
| Remove | `POST /api/content-packs/remove` with `{"pack_id": "..."}`, or delete the file and restart |
| Disable without removing | `POST /api/content-packs/enable` with `{"pack_id": "...", "enabled": false}` |
| Inspect | `GET /api/content-packs` |
| Get one back for editing | `GET /api/content-packs/export/<pack_id>` |
| Validate before installing | `POST /api/content-packs/validate` |

Removal is exact: every entry a pack contributed is recorded in
`content_pack_entries`, so uninstalling takes back its own content and nothing
else. Items and powers already in a live playthrough are **detached, not
deleted** — a player never loses their sword because you uninstalled a pack.

A working template lives at
[`content/pack-examples/riverlands_kit.json`](../content/pack-examples/riverlands_kit.json).

---

## Load order

```text
built-in Python catalog  ->  content/packs/  ->  data/packs/
```

Later entries override earlier ones **by code**. That means a pack can:

- **add** content by using a new code,
- **retune** a built-in by reusing its code (change `base_dc`, `attribute`, …),
- **remove** a built-in by reusing its code with `"enabled": false`.

---

## Handing this to another LLM

`GET /api/content-packs/authoring-bundle` returns one JSON payload containing
the format, the hard rules, a field-by-field reference including which database
column each field lands in, a worked example, and the codes already in use.

The workflow:

1. Fetch the bundle.
2. Paste it into a chat with: *"Write a Mørkyn content pack that does X,
   following this specification exactly. Return only JSON."*
3. `POST` the result to `/api/content-packs/validate`.
4. If `ok` is false, paste the `errors` array straight back to the model — each
   error carries a JSON `path`, a `message`, and a suggested `fix`.
5. `POST` to `/api/content-packs/install`.

Validation errors are written for that loop. For example:

```json
{
  "path": "skills[0].attribute",
  "message": "missing/unknown attribute 'luck'",
  "fix": "Every skill rolls off one attribute. Use one of: strength, dexterity, constitution, intelligence, wisdom, charisma"
}
```

---

## Pack shape

```json
{
  "format": "morkyn-content-pack-v1",
  "id": "riverlands_kit",
  "label": "Riverlands Kit",
  "version": "1.0.0",
  "author": "",
  "description": "",

  "skills": [],
  "powers": [],
  "items": [],
  "encounter_tables": {"terrain": {}, "kinds": {}},
  "magnitude_tables": {}
}
```

Every section is optional. Unknown top-level keys are dropped silently.

### Skills

```json
{
  "code": "poling",
  "name": "Poling",
  "category": "craft",
  "attribute": "strength",
  "secondary": "dexterity",
  "tags": ["boat", "river"],
  "base_dc": 12,
  "description": "Pushing a flat boat upriver without losing the line.",
  "triggers": ["\\b(pole|punt|push the (boat|barge|raft))\\b"],
  "opposed_by": "",
  "growth": {"band": "small", "on": ["success", "critical_success"]},
  "enabled": true
}
```

| Field | Notes |
| --- | --- |
| `attribute` | Required. One of `strength, dexterity, constitution, intelligence, wisdom, charisma`. Aliases like `str`/`might` are normalized. |
| `base_dc` | 5–30. 10 easy, 12 normal, 14 tricky, 16 hard, 20+ expert only. |
| `triggers` | Lowercase **regex fragments** matched against raw player input. When one matches, the server rolls this skill automatically. Pack triggers are checked *before* built-ins, so you can hijack a phrase. |
| `enabled` | `false` removes the skill from play, including built-ins. |

Keep triggers specific. A greedy pattern will capture unrelated turns.

### Powers

Powers are **read-only rules**. They are defined once, here, and nothing in play
rescales them. Items point at them by code rather than restating them.

```json
{
  "code": "AB_river_read",
  "name": "River Read",
  "description": "Read the current for a heartbeat and know where the channel runs.",
  "activation": "active",
  "read_only": true,
  "resource_cost": {"energy": 2},
  "cooldown_turns": 1,
  "roll_profile": {"poling": 2, "navigation": 1},
  "magnitude": {"kind": "duration_minutes", "band": "small"},
  "prerequisites": "Has poled a river at least once",
  "locked": false
}
```

| Field | Notes |
| --- | --- |
| `activation` | `active` (spent deliberately), `passive` (always on), `triggered` (fires on a condition). |
| `roll_profile` | `skill_code -> flat modifier`, range −12..12. Applied to dice checks while the power is passive or granted by an equipped item. |
| `magnitude` | What the server rolls when the power resolves. See [DiceAuthority.md](DiceAuthority.md). |
| `resource_cost` | Integer cost per use. Keys: `health, energy, mana, fatigue, gold`. |

An `active` power with neither a cost nor a cooldown produces a validation
warning — free unlimited powers trivialize play.

### Items

```json
{
  "code": "IT_river_pole",
  "name": "Ironshod River Pole",
  "item_type": "tool",
  "rarity": "uncommon",
  "weight": 4.0,
  "slot_size": 2,
  "stack_limit": 1,
  "equip_slot": "main_hand",
  "description": "A long ash pole with an iron foot.",
  "stat_links": {"strength": 1},
  "power_codes": ["AB_river_read"],
  "roll_profile": {"poling": 2, "athletics": 1}
}
```

The three fields that matter most:

| Field | Column | What it does |
| --- | --- | --- |
| `stat_links` | `inventory.stat_links` | Canonical attribute bonuses while equipped. Folded into `player.effective_stats`. |
| `power_codes` | `inventory.power_codes` | Powers this item grants while equipped. A **reference**, not a copy. |
| `roll_profile` | `inventory.roll_profile` | Flat check modifiers while equipped. This is how gear affects dice without the narrator doing arithmetic. |

All three are removed automatically when the item is unequipped.

Items created by the narrator during play get these filled in too: free-text
`stat_modifiers` are collapsed onto canonical stat keys, granted abilities are
resolved to power codes where a matching power exists, and a `roll_profile` is
derived from item type and rarity when none was declared. A plain "Iron Sword"
from the model still ends up affecting melee rolls.

### Encounter tables

```json
"encounter_tables": {
  "terrain": {
    "swamp": {
      "base_chance": 0.18,
      "kinds": {"wild_threat": 55, "bandit_ambush": 15, "traveler": 10, "hidden_base": 20}
    }
  },
  "kinds": {
    "wild_threat": {
      "label": "Something in the reeds",
      "hostile": true,
      "avoid_skill": "perception",
      "count_band": "small",
      "threat_band": "moderate"
    }
  }
}
```

`base_chance` is the per-hour chance of *something* happening on that terrain
before any player modifiers. See [Encounters.md](Encounters.md) for how the
final number is reached.

`count_band` and `threat_band` are bands, not amounts — the server rolls how
many showed up and how dangerous they are.

### Magnitude tables

Retune the dice behind any band. See [DiceAuthority.md](DiceAuthority.md).

```json
"magnitude_tables": {
  "gold": {
    "scale": "level_soft",
    "min": -50000,
    "max": 5000,
    "bands": {"small": "3d6+5", "moderate": "5d10+15"}
  }
}
```

Only the bands you list are overridden; the rest keep their defaults.

---

## Hard rules

These are enforced by validation, and repeated in the authoring bundle:

1. Return one JSON object. No markdown fences, no commentary.
2. `format` must be exactly `morkyn-content-pack-v1`.
3. Magnitudes are bands, never amounts: `none, trivial, small, moderate, large, huge`.
4. Powers are read-only. Define a power once; nothing in play may rescale it.
5. Items point at powers by code. Do not copy a power's text into an item.
6. `roll_profile` modifiers stay within −12..12. A +3 sword is already strong on a d20.
7. Stat keys are exactly the six listed above. No custom attributes.
8. Every skill names one attribute, or the dice system cannot resolve it.
9. Reusing a code overrides that entry. Use a new code when you mean to add.
10. Prefer few, well-differentiated entries over many near-duplicates.

---

## Related

- [DiceAuthority.md](DiceAuthority.md) — bands, dice tables, and the audit trail
- [Encounters.md](Encounters.md) — the danger model packs feed into
- [SkillChecks.md](SkillChecks.md) — how a resolved check plays out
