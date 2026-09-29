# Mørkyn 0.10.0-wip — Release Notes

**Status:** WIP release — systems under active development, not stable. Not yet tagged. Builds on the [`0.9.12`](https://github.com/Stelliro/Morkyn/releases/tag/v0.9.12) stable release.

---

## What's new in 0.10.0-wip

### Fight / combat state

NPCs can be initiated into combat from the UI or via `initiate_fight`. Ambient `fight_nearby` events fire as full combat turns during Wait and Rest. Fight state persists in the world database and is cleared on resolution.

### Quest / Objectives system

Active quests are first-class database objects (`quests` + `quest_steps` tables). Each quest has:

- Up to 6 ordered steps, each with a title, description, and optional location code
- Optional timer (quests auto-fail when `turns_remaining` reaches zero, wired into `apply_turn`)
- Hidden steps that reveal only when the player reaches a specified earlier step
- Rewards: gold, XP, and an optional item list (paid out automatically on completion)
- Difficulty multiplier that scales gold and XP rewards (`trivial` × 0.5 → `deadly` × 2.5)

**UI:** The Quests tab shows the active quest log above the GM tools. Each quest shows a progress bar, per-step objectives (done/active/pending styling), the reward, and an Advance Step button. A **Seed starter quests** button adds three starter quests to an empty world.

**Quest creation form:** A new in-browser form lets you author quests directly in the UI — title, description, difficulty, rewards, and up to six steps with optional location and hidden-until-step flags. No API call needed.

**API:** `GET /api/quests`, `POST /api/quests/{id}/advance`, `POST /api/quests/seed`

**LLM context:** Active quests are injected into every turn's prompt so the narrator knows what the player is trying to accomplish.

### NPC relationship system

Each NPC tracks three relationship axes toward the player:

| Axis | Range | Bands |
| --- | --- | --- |
| Affinity | −100 → +100 | Hostile · Unfriendly · Neutral · Friendly · Trusted · Devoted |
| Fear | 0 → 100 | None · Wary · Afraid · Terrified |
| Respect | 0 → 100 | Ignored · Acknowledged · Respected · Revered |

Twelve preset event deltas cover common outcomes: `helped_npc`, `attacked_npc`, `saved_npc_life`, `quest_complete_for_npc`, `quest_failed_for_npc`, `intimidated_npc`, `bribed_npc`, `lied_to_npc_caught`, `killed_npc_friend`, and more.

NPCs with any non-default relationship appear in the LLM context each turn with their current bands so the narrator can write dialogue and behaviour consistent with the player's history.

**Relationship badges:** NPC entity cards in the People tab now show coloured band badges for affinity, fear, and respect inline — visible at a glance without opening the API.

**API:** `GET /api/relationships`, `GET /api/relationships/{npc_id}`, `POST /api/relationships/{npc_id}/update`

### LLM context enrichment (`app/world_context.py`)

Three new blocks injected into every turn's LLM prompt:

- **Naming guide** — cultural naming patterns for five registers (Nordic, Eastern, medieval English, Arabic, Slavic) with sample names so the model picks names consistent with the world's cultural register.
- **Loot reference** — 28 named items across four rarities (common / uncommon / rare / legendary), each with a one-sentence flavour description. Encourages consistent named loot rather than invented disposable items.
- **Ability registry** — 20 abilities across 8 domains (combat, social, stealth, craft, medicine, survival, arcane, summon, necromancy) with type and descriptions, so granted abilities stay consistent with existing vocabulary.

### Autonomous player agent (`player_agent.py`)

A standalone script that plays a full session using the same 8B Ollama model in both narrator and player roles. The player role sees only the narrative text and its character sheet — no world-state JSON, no entity codes, no GM context.

- **Lore Bible:** The agent maintains a running entity tracker built from the narrative it has seen. Named people, places, and objects are accumulated into a "What you know so far:" block injected at the start of each player context.
- **Goal directive:** The agent receives a pursuit goal at session start and works toward it across turns.
- **Debug command blocker:** A filter strips meta-commands and debug strings from player output so the narrator never receives OOC text.

### Save editor (carried from 0.9.13-dev sprint)

World save files can be viewed and edited cell-by-cell in the browser. Any table except `world_maps` and `settings` is editable. Changes are all-or-nothing; a backup is written before any file is touched. `dry_run` mode reports what would change before committing — `app/save_editor.py`.

---

## In Progress

> These systems have schemas and partial APIs in place but are not yet complete. Saves created now will carry the schema. UI, auto-wiring, and balance tuning are follow-on work.

- **Titles system** — Earnable titles with stat bonuses. Schema and seeding in place; award logic and UI integration incomplete.
- **Party system** — Invite / remove NPCs, morale tracking, combat bonuses. Schema and invite/remove API in place; morale propagation to combat and narrator context incomplete.
- **Hidden NPC psychology** — Private feelings, agendas, and family ties stored as narrator-only context. Schema in place; injection into narrator context and authoring UI incomplete.

---

## How to run

```powershell
# Windows (in-repo)
Morkyn.bat

# Skip menu
Morkyn.bat local

# Direct
python -m uvicorn app.main:app --port 8000
```

Requirements: Python 3.11+, Ollama running locally (or configured cloud API).

See [README.md](README.md) for full setup.

---

## Files changed in this release

| File | Change |
| --- | --- |
| `app/world.py` | Fight/combat state, `initiate_fight`, ambient fight events during Wait/Rest; hidden NPC psychology schema wiring |
| `app/quests.py` | New — quest CRUD, step advancement, timers, seeding, LLM context injection |
| `app/relationships.py` | New — NPC-player relationship tracking on three axes |
| `app/world_context.py` | New — static naming / loot / ability context blocks for LLM injection |
| `app/save_editor.py` | New — save-file editor API (all-or-nothing edits, dry run, backup) |
| `app/titles.py` | New *(IN PROGRESS)* — titles schema, seeding, stat bonus model |
| `app/party.py` | New *(IN PROGRESS)* — party invite/remove, morale tracking |
| `app/db.py` | Added `quests`, `quest_steps`, `npc_player_relationships`, titles, party tables |
| `app/prompts.py` | Inject world context blocks and quest/relationship state into `build_user_prompt()` |
| `app/main.py` | Quest and relationship endpoints; save-editor endpoints; party invite/remove endpoints |
| `static/app.js` | Quest log, quest creation form, relationship badges on NPC cards, fight-initiate UI, save-editor UI |
| `static/styles.css` | Quest card styles, relationship badge chips, fight-state indicators, save-editor layout |
| `player_agent.py` | New — autonomous player agent with Lore Bible, goal directive, debug command blocker |
| `README.md` | Bumped version to 0.10.0-wip, updated feature highlights |
| `CHANGELOG.md` | [Unreleased] promoted to [0.10.0-wip], new entries added |
| `RELEASE_NOTES.md` | This file |
