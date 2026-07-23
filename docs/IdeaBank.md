# Idea bank (cold storage)

Keyword-searchable **idea sparks** for wider wording in setup randomize / compose.

This is **not**:

- model training data  
- embeddings / vector RAG  
- weighted ranking learned from play  

It **is**:

- JSONL cards on disk  
- pure keyword match  
- injected into LLM prompts as `idea_sparks` with explicit “inspiration only” rules  

## Layout

| Path | Role |
| --- | --- |
| `config/idea_bank/*.jsonl` | Shipped seeds (**~290 unique cards**, multi-theme) |
| `data/idea_bank/*.jsonl` | Your local cold storage (optional; wins on same `id`) |

Env override for the user folder: `AI_RPG_IDEA_BANK`.

### Shipped packs (wide RPG range)

| File | Themes |
| --- | --- |
| `abilities.jsonl` / `places_factions.jsonl` / `tone_style_system.jsonl` | Original core seeds |
| `expand_fantasy.jsonl` | High/low fantasy, fey, dungeon ecology, courts |
| `expand_dark_horror.jsonl` | Grimdark, gothic, cosmic, folk, war |
| `expand_scifi_system.jsonl` | Cyber, space salvage, system-apoc, mecha, colony |
| `expand_historical.jsonl` | Wuxia, samurai, pirate, western, regency, saga |
| `expand_social_heist.jsonl` | Cozy mystery, heist, intrigue, slice-of-life |
| `expand_travel_survival.jsonl` | Trek, arctic, jungle, desert, sea |
| `expand_systems_growth.jsonl` | Ability seeds + XP/rank wording variety |
| `expand_meta_openings.jsonl` | Death, loot, NPCs, openings, isekai/urban/cape |

Regenerate expand packs only: `python tools/seed_idea_bank_expand.py`

## Card shape

```json
{
  "id": "ability.ropework.seed",
  "kind": "ability",
  "title": "Load-bearing rope habit",
  "text": "Near-useless knot habit that only compounds when the line is load-bearing…",
  "keywords": ["rope", "knot", "seed", "weak", "compounding"],
  "tags": ["isekai", "craft"],
  "examples": ["false hitch under panic"]
}
```

**Kinds:** `ability`, `skill`, `growth`, `place`, `tone`, `faction`, `system`, `death`, `loot`, `npc`, `style`, `opening`.

## Runtime

- `app/idea_bank.py` — load, search, `idea_sparks_for_prompt()`
- Setup randomize + compose-intent attach `idea_sparks` automatically
- Model is told: borrow wording, do not paste titles, not weights

## API

| Method | Path | Use |
| --- | --- | --- |
| GET | `/api/idea-bank` | Stats + file list |
| GET | `/api/idea-bank/search?q=harbor&kind=place` | Quick search |
| POST | `/api/idea-bank/search` | Search or build sparks from setup fields |
| POST | `/api/idea-bank/add` | Append a user card to `data/idea_bank/` |
| GET | `/api/idea-bank/cards` | Browse cards |

### Add a personal idea

```http
POST /api/idea-bank/add
{
  "kind": "ability",
  "title": "Salt-crust map itch",
  "text": "When lost near the sea, an itch points slightly less wrong after each bad turn.",
  "keywords": ["map", "salt", "travel", "seed"]
}
```

## Growing the bank

1. Drop more `.jsonl` lines under `config/idea_bank/` (ship) or `data/idea_bank/` (local).  
2. Use concrete, playable wording — not slogans.  
3. Prefer **many short cards** over long essays.  
4. Keywords should match how players type ideas (`harbor`, `wuxia`, `system`, `seed`).  

No restart required for new files in most cases (cache invalidates on mtime).
