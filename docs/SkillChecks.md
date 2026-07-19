# Dice rolls & skill checks

Optional system for contested or uncertain actions: inspecting symbols, forcing doors, speech contests, random events, and encounters.

## Toggle

Setup → **5 Checks** → **Dice checks: On**.

When **Off**, play stays pure narrative (default).

## How resolution works

```text
roll = dN + attribute_mod + skill_rank
compare to DC (skill base_dc + difficulty shift)
```

| Outcome | Meaning |
| --- | --- |
| critical success | Clean win + extra useful detail / advantage |
| success | Requested info or effect |
| partial | Incomplete: skill salvage or near-miss |
| failure | Miss; setbacks if **negative outcomes** are on |
| critical failure | Complication, wrong reading, alarm, injury risk… |

### Specialized skill salvage

Example: Intelligence is low, but **Symbol Lore** rank ≥ threshold:

- Attribute alone would fail
- Specialized skill can still produce a **partial** result (fragment, risky reading, costly insight)

Controlled by:

- `partial_on_specialized_skill`
- `attribute_floor_for_partial` (default 6)
- `specialized_skill_partial_threshold` (default skill rank 2)

## Categories

Physical · Mental · Social/Speech · Craft/Tech · Combat · Events · Encounters · General

Built-ins include strength, speech/persuasion, symbol lore, hacking, ambush sense, random encounter, hazard, discovery, and more.

## Durable skill library

Stored at `data/skill_library.json` (gitignored runtime file).

- New skills from the UI or play are **compared** to similar catalog entries
- Base DC is averaged toward peers; related codes are linked
- Skills persist across playthroughs; enable/disable per skill

## APIs

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/skill-checks/catalog` | Categories + skills + defaults |
| POST | `/api/skill-checks/resolve` | Roll a check |
| POST | `/api/skill-checks/register` | Add/adjust skill in library |
| POST | `/api/skill-checks/enable` | Toggle skill for future use |

## GM / model context

When enabled, `skill_check_context` is injected into the prompt packet with active skills and rules:

- Call checks by **code** when uncertainty matters
- Prefer partial over blank when specialized skill exists
- Apply concrete setbacks on failure when negative outcomes are on
- Register novel skills for balance against the catalog

## Play UI (next)

Showing roll banners when `show_rolls_in_ui` is on will use the resolve payload / turn `skill_checks` list. v1 ships setup + library + resolve API + context wiring.
