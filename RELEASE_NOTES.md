# Mørkyn 0.10.0-wip — Release Notes

Notes extended 2026-10-04. Still untagged.

**Status:** WIP release — systems under active development, not stable. Not yet tagged; it ships as `0.10.0`. Builds on the [`0.9.12`](https://github.com/Stelliro/Morkyn/releases/tag/v0.9.12) stable release.

---

## What's new (October 2026)

### Since 2026-10-04

- **Token limits follow the model.** Context window and response caps come from the GGUF header and the GPU, or a tokens-per-billion scale; your own numbers are kept per model; launcher prefs default to `auto` — `app/model_limits.py`.
- **Failsafes.** A model failure opens a dialog that names the problem and what to try, with "Continue anyway"; a context too small for the full contract is announced at boot — `app/failsafe.py`, `static/ui/failsafe.js`.
- **Cheaper turns.** The verifier returns a verdict and a patch, local models share one system prefix per turn, prose repairs carry a prose contract, truncated JSON is closed locally, a dead model costs one call — `app/llm.py`, `app/prompts.py`.
- **The UI is three CSS layers** drawn from the key art, with folds, hover peeks, and right-click menus — `static/ui/`, `docs/UI_RULEBOOK.md`.
- **Rewind covers everything a turn wrote**: quests, offer clocks, the name ledger, social writes, pronoun pins, dice rows. Skill-check dice are seeded and audited. Hidden NPC psychology, server-rolled checks, and the skill search reach the narrator. See `CHANGELOG.md` for the full list.

### MLE (Morkyn LLM Engine)

The local story slot loads a GGUF inside the game process and returns that completion only. `status` is ok only after the file has loaded. If no file is resolved, chat stops and names the path to set.

Lookup order: an existing file path, `data/mle-models/<name>.gguf`, `MLE_GGUF`, then the single `.gguf` in that folder. Weights in `data/` stay off GitHub. Context follows `AI_RPG_CONTEXT_TOKENS` and retries once at 8192 if the larger window will not load.

A call may pass words to hide for that sample only. The mask hits a token when the decoded piece is the whole word. Split pieces, single letters, digits, codes such as `L1`, punctuation, structure words, and keep-words stay choosable. The finished sentence is not edited, and the weight file is not rewritten. Narration drafts send the overused-word list into that call. Names, job titles, and the draft's JSON keys stay choosable.

llama.cpp, Forge, ComfyUI, and cloud APIs stay.

### Wilderness map

The land is a seeded grid, 16,383 cells on a side. A city is a connected clump inside a 9 by 9 neighborhood. Eighty-one cells is the most a metropolis holds, and that same count stretched into a one-cell line is rejected. The center cell is 128 by 128. Outer cells are smaller. The widest fine span is 1,152. Density is the only theme input. The model does not place cities, notices, or coordinates.

The play map can show remembered tiles, heard-about cells, and marks for intel, quests, and NPCs.

### Local intel

Directions, shop stalls, notice boards, and personal-quest clocks are engine data. Heard cells are separate from cells the player has walked. A mark on any other cell is refused. Black-market answers fail closed. A personal offer does not appear on the first day of its 30-day month.

### Encounter board

A fight tracks named people who are the target, who step in, or who are already listed. A crowd is not a combatant list. A move the player has not seen is stored as what was seen, with no effectiveness attached.

### Setup rules

The choice you pick stays short. Before the first scene, the save stores a written rule for that choice: the rank ladder, the economy, how quests appear, and the other setup picks in that catalog. A game can start with no model call. Those prepared sentences are already in the save. When the story provider is a cloud model with a key, it may replace a sentence once, and only if its reply names the choice you made.

A list you type is a preset for each label. `common, uncommon, rare, epic, legendary, unique and unknown` is seven rungs, from ordinary at the bottom to unknown at the top. The word "and" separates the last two. A built-in phrase such as "earned and uncommon" stays one choice. If a model reply drops a label, or treats two neighboring rungs as one, the prepared sentence is the one that is kept.

### World themes

The theme changes the ground, what that ground is made of, and who usually lives there. Deep Caverns is cavern, mushroom, crystal, lava, water, and cliff. Most people there, when a stretch is lived in, are creatures that lurk in the dark, and dwarves. Other themes have their own ground and their own usual people. A stretch can be empty. A kind is a leaning, not a head count. A map that already has its ground stored keeps that ground.

The world-preset card folds. The two map views are labeled. Starting a new game rolls a new map seed. The older small board remains as the legacy map.

---

## What's new (September 2026)

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

A standalone script that plays a full session using the same 8B model through MLE in both narrator and player roles. The player role sees only the narrative text and its character sheet — no world-state JSON, no entity codes, no GM context.

- **Lore Bible:** The agent maintains a running entity tracker built from the narrative it has seen. Named people, places, and objects are accumulated into a "What you know so far:" block injected at the start of each player context.
- **Goal directive:** The agent receives a pursuit goal at session start and works toward it across turns.
- **Debug command blocker:** A filter strips meta-commands and debug strings from player output so the narrator never receives OOC text.

### Save editor (carried from the 0.10.0-wip sprint)

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

Requirements: Python 3.11+. Local story uses MLE. A cloud API is optional. Forge and Comfy stay optional for images.

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

### Files touched in October 2026

| File | Change |
| --- | --- |
| `app/mle.py` | New — in-process GGUF load and sample-time word mask |
| `app/world_scale.py` | New — seeded land grid and city-clump rules |
| `app/local_intel.py` | New — directions, notices, heard cells, quest clocks |
| `app/encounter_board.py` | New — named fight participants and seen moves |
| `app/tile_world.py` | World-scale map preview and city shape |
| `app/llm.py`, `app/launcher_prefs.py`, `Morkyn.ps1` | Local provider is `mle` |
| `static/app.js`, `static/index.html` | MLE in model settings; map marks on the play screen |
| `README.md`, `CHANGELOG.md`, `RELEASE_NOTES.md` | Version stays `0.10.0-wip` until the `0.10.0` release |
| `app/model_limits.py` | New — per-model token limits from the GGUF header, the GPU, or a tokens-per-billion scale |
| `app/failsafe.py`, `static/ui/failsafe.js` | New — model-problem dialog, context notice |
| `static/ui/tokens.css`, `static/ui/skin.css`, `static/ui/interact.js` | New — the three-layer UI |
| `app/llm.py`, `app/prompts.py`, `app/world.py`, `app/mle.py` | Verdict verifier, shared prefix, rewind coverage, dead-model handling, MLE timeout and status |
