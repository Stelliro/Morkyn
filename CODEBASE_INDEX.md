# CODEBASE INDEX - Mørkyn

> Single source of truth for project structure, conventions, and architecture.
> Last updated: 2026-07-19 (repo layout: root launchers/docs, tests/, benchmarks/, privacy/updates, narration pipeline)

> Use this file before making architecture, schema, API, prompt-contract, launcher, or major UI changes. Update it whenever those facts change.

---

## 1. Project Overview

**Mørkyn** (formerly Mørkyn) - an endless local-browser RPG where a local LLM narrates turns and proposes structured world changes while SQLite remains the source of truth.

- **Type:** Local web app / game prototype
- **Primary Languages:** Python, JavaScript, HTML, CSS
- **Key Frameworks / Libraries:** FastAPI, Pydantic, SQLite, Uvicorn, llama-cpp-python server, Ollama-compatible APIs
- **Target Platforms:** Windows local development, browser UI at localhost or trusted local-network phone/tablet browsers
- **Current Version:** 0.9.0
- **Status:** Active development / prototype
- **Brand assets:** `Media/` (logo + key art)

### Goals
- Keep long-running RPG state consistent through durable SQLite records, stable entity codes, journal entries, summaries, and source indexing.
- Let the player configure character, world, rules, skills, inventory, abilities, model settings, and narrative style before starting play.
- Provide a practical browser UI for turns, entity references, world memory, visual history, rewind points, import/export, and model diagnostics.

### Non-Goals
- Hosted multiplayer, accounts, auth, or cloud persistence.
- A production deployment pipeline or packaged desktop app.
- Fully formalized combat, quest, faction, or item-tag engines; those are future layers.

---

## 2. Repository Structure

```text
Morkyn/
|-- .github/
|   |-- copilot-instructions.md
|   `-- instructions/
|-- app/
|   |-- __init__.py
|   |-- content_packs.py             # JSON packs: skills/powers/items/tables + authoring spec
|   |-- db.py                        # SQLite connection, schema, migrations
|   |-- encounters.py                # Danger model + encounter resolution
|   |-- llm.py                       # Model config, JSON chat, token budget, traces, fallbacks
|   |-- main.py                      # FastAPI routes (turns, slots, diagnostics, model)
|   |-- narration_pipeline.py        # Adaptive paragraph quality pipeline
|   |-- prompts.py                   # System/verifier prompts + agentic CoD steps
|   |-- rng.py                       # Dice, magnitude bands, deterministic seeds, roll audit
|   |-- venues.py                    # Shop/inn kinds, opening hours, settlement commonality
|   |-- turn_dsl.py                  # NAR+OPS draft language
|   |-- updates.py                   # Optional GitHub update/rollback
|   `-- world.py                     # State, planner, memory consolidation, slots, index
|-- content/
|   |-- packs/                       # Built-in packs (auto-loaded, disable-only)
|   `-- pack-examples/               # Templates to copy into data/packs/
|-- static/                          # Browser UI (no build step)
|-- Media/                           # Brand assets (logo, key art, screenshots)
|-- docs/                            # Design notes + docs/README.md index
|-- tools/                           # Smokes, screenshots, timed playtests
|-- tests/                           # behavior_test, narration pipeline unit tests
|-- benchmarks/                      # Dual-role / long-run harnesses (reports/ gitignored)
|-- data/                            # Runtime only (gitignored): world.db, source_index, slots, traces
|-- start.bat / start.sh             # Bootstrappers: clone, update-prompt, launch
|-- Morkyn.bat / Morkyn.ps1          # Primary launcher (root)
|-- start_ai_rpg.bat / .ps1          # Compatibility shims -> Morkyn.*
|-- README.md / CHANGELOG.md / LICENSE.md / PRIVACY_POLICY.md
|-- CODEBASE_INDEX.md
|-- requirements.txt
`-- .env.example
```

### Key Modules

#### FastAPI Surface

- **Files:** `app/main.py`
- **Purpose:** Defines the FastAPI app, request models, static file serving, and all browser-facing endpoints.
- **Key API:** `index()`, `api_state()`, `api_version()`, `api_turn()`, `api_setup()`, `api_export()`, `api_import()`, `api_search()`, `api_bible()`
- **Consumers:** Browser UI in `static/app.js`; launcher starts it through Uvicorn.
- **Dependencies:** `app.db`, `app.world`, `app.llm`, FastAPI, Pydantic.
- **Design Notes:** Pydantic request models enforce string lengths and basic request shape before world logic runs. Setup payloads include current player age/sex and optional previous-life age/sex for reincarnated/transmigrated starts. Setup payloads are normalized before validation so missing/null mobile form values, invalid numeric fields, and stale cached clients fall back to safe setup defaults instead of producing avoidable 422 responses. Domain errors are translated to HTTP 400 or 503 where appropriate.

#### Database Layer

- **Files:** `app/db.py`
- **Purpose:** Opens SQLite connections, enables foreign keys, creates the schema, and performs additive column migrations.
- **Key API:** `connect()`, `init_db()`, `row_to_dict()`, `rows_to_dicts()`
- **Consumers:** `app.main` startup and most of `app.world`.
- **Dependencies:** Python `sqlite3`, `pathlib`, environment variable `AI_RPG_DB`.
- **Design Notes:** `data/world.db` is the default source of truth. Player setup identity columns include `age`, `sex`, `previous_life_age`, and `previous_life_sex` as additive text migrations. The path is resolved by `db_path()` on every `connect()`, never frozen at import, so `AI_RPG_DB` is authoritative regardless of import order; tests must still re-apply their env in `setUpModule()` because the variable itself is process-global. `dice_rolls` stores the audit trail for every server-rolled amount. `content_packs` / `content_pack_entries` register installed content so uninstall is exact. `inventory` carries `stat_links` (canonical attribute keys), `power_codes` (references into `abilities.code`), and `roll_profile` (flat check modifiers applied while equipped); `abilities` carries `read_only`, `roll_profile`, `magnitude_kind`/`magnitude_band`, and `activation` so powers are fixed rules the dice roller consults rather than text the model re-derives.

#### World Engine

- **Files:** `app/world.py`
- **Purpose:** Owns persistent RPG state, playthrough setup, turn application, entity indexing, aliases, search, World Bible data, import/export, and rewind snapshots.
- **Key API:** `get_state()`, `start_playthrough_with_opening()`, `play_turn()`, `play_continue_turn()`, `regenerate_last_turn()`, `get_world_bible()`, `search_world()`, `export_world()`, `import_world()`, `rewind_last_turn()`, `consolidate_memory()`, `search_source_index()`, `list_campaign_slots()`, `save_campaign_slot()`, `load_campaign_slot()`, `get_context_health()`
- **Consumers:** `app.main` routes and indirectly the browser UI.
- **Dependencies:** `app.db`, `app.llm`, SQLite, JSONL summary files, source-index runtime files.
- **Design Notes:** The model proposes changes, but world logic applies them conservatively. Entity references use stable codes: NPCs `A` through `Z` then `AA`, locations `L1`, items `I1`, and events `E1`. `build_prompt_context()` builds a deterministic planner packet with version `V0.1.0` that classifies turn intent, chooses verifier checks, filters context slices, exposes a focused working set, attaches matching `verification_memory` hits for already-cleared checks, and adds `action_context` priority segments such as movement limits, environment pressure, combat opposition, ability constraints, item handling, NPC knowledge, and rest safety. Combat turns also receive a deterministic mechanics packet with version `V0.1.0`: NPC combat health/attack/defense/dodge are derived and persisted from player level, difficulty, NPC rank/stat_profile, and equipment-derived player stats before generation when a combat target is known; direct player attacks get a resolved weapon/equipment source, damage result, and target health delta for the model to narrate rather than recalculate. Inventory items may store `stat_modifiers` and `granted_abilities`; `get_state()` folds those into `equipment_effects`, `player.effective_stats`, and derived `abilities` only while the item has an equipped slot, so unequipping automatically removes those player capabilities from prompt context and UI. The planner passes focused inventory/equipment slices only for item handling, trade, equip/unequip, or hard item references; combat and ability turns use derived stats/abilities rather than raw equipment. Hidden GM events and current-location event lifecycle guidance are included before LLM drafting. New playthroughs persist setup identity including current age/sex and previous-life age/sex, and start with no default player skills; skills are recorded through play, training, discovery, or explicit custom proficiency rules. Location events persist with `persistence`, `disappear_chance`, `respawn_chance`, and `last_seen_turn`; temporary, traveling, and recurring events remain stable while the player stays in the area, may fade after departure, and may reactivate on return when appropriate. Raw journal history is player-visible only and is not passed into turn prompts or source-index retrieval. Export format is `ai-rpg-world-v1`; rewind snapshots use `ai-rpg-delta-v1`. Regeneration restores the latest pre-turn snapshot and replays the saved opening, continue, or player input.

#### LLM Adapter

- **Files:** `app/llm.py`
- **Purpose:** Stores model configuration, tests local model connectivity, calls Ollama or OpenAI-compatible llama.cpp endpoints, repairs malformed JSON, and supplies fallback narration.
- **Key API:** `get_model_config()`, `update_model_config()`, `test_model_connection()`, `generate_setup_randomization()`, `generate_turn()`, `generate_input_suggestions()`, `fallback_turn()`
- **Consumers:** `app.main` model endpoints and `app.world` turn flow.
- **Dependencies:** `app.prompts`, `urllib`, environment variables, local llama.cpp or Ollama-compatible services.
- **Design Notes:** LLM output is JSON-first. Turn generation consumes the focused turn planner packet, runs deterministic handoff cleanup before the draft, performs a draft pass, cleans the draft payload before verification, validates usable narration, scores a selective verification policy, then either skips the model verifier for high-certainty low-risk drafts or runs the verifier focused on remaining checks. The policy treats matching `verification_memory` rows as already-cleared checks when their confidence meets `AI_RPG_VERIFY_MEMORY_CERTAINTY` (default 0.86), so repeated verified facts can make later matching turns draft-only when no risky state changes are present. The policy only skips when the draft has enough narration, valid entity references, a sane scene-plan shape, a passing self-check, no high-risk state changes, and all planner verification checks have been deterministically or previously cleared; `AI_RPG_FAST_VERIFICATION` toggles this path and `AI_RPG_VERIFY_SKIP_CERTAINTY` sets the default 0.88 skip threshold. Verified payloads are cleaned again before world application, and valid turns below the 1000-character narration floor get one depth retry before returning. Normal turn narration targets about 1500 visible characters and stays below 2400 characters / 700 words; deterministic fallback turns follow the same depth expectation. Context-overflow failures trigger compact turn-context retries before deterministic fallback narration. The context window must hold the system contract: `SYSTEM_PROMPT` estimates ~9143 tokens, so `fitting_system_prompts()` selects `COMPACT_SYSTEM_PROMPT` (~3041 tokens) whenever the window cannot also spare `MIN_TURN_HEADROOM_TOKENS` (2048) for the packet and output, and warns once on the server console. `DEFAULT_CONTEXT_TOKENS` is 32768 because the previous 8192 default could not fit the full contract at all and silently forced deterministic fallback on every turn; anything below ~12288 degrades to the compact contract. llama.cpp turn draft/verify timeouts are phase-specific through `AI_RPG_TURN_DRAFT_TIMEOUT` and `AI_RPG_TURN_VERIFY_TIMEOUT`, with longer local defaults for slow first-scene generation; setup randomization and suggestions use `AI_RPG_SETUP_RANDOMIZER_TIMEOUT` and `AI_RPG_SUGGESTION_TIMEOUT`. Input suggestions are clipped near 100 visible characters, with a 120-character maximum. Each turn writes a JSON trace file under `AI_RPG_MODEL_TRACE_DIR` (default `data/model_traces`) containing focused prompt context, deterministic handoff cleanup records, prompts, raw model outputs, parsed JSON, verification-memory hits, verification-policy scores, verifier/self-check data, timing/error records, fallback decisions, and the final turn payload; `AI_RPG_MODEL_TRACE_KEEP` limits retained files and `AI_RPG_TRACE_VALUE_LIMIT` caps individual string values. These traces capture observable model artifacts, not hidden chain-of-thought the model never returned. Model settings default to the llama.cpp-compatible provider unless `AI_RPG_MODEL_PROVIDER=ollama` or the UI explicitly selects Ollama. They store a soft response token target (`response_token_cap`, default 1500) and a hard response token cap (`response_token_hard_cap`, default 2000); repair calls use at least the soft target while all response requests are clamped by the hard cap and remaining context. No machine-specific GGUF path is embedded in defaults; set `AI_RPG_GGUF_MODEL` or use the Model settings UI to choose a local model. `/api/model-status` checks the configured provider and, for llama.cpp with a saved GGUF path, starts a managed `llama_cpp.server` process when the configured `/v1/models` endpoint is refused. Generation requests to llama.cpp also start the managed server and retry once when `/v1/chat/completions` or `/v1/completions` is refused, so setup/opening generation does not depend on pressing Test first. Timeout errors include the failed phase, timeout seconds, approximate prompt tokens, configured soft response target, configured repair cap, and configured hard cap so caps are not mistaken for actual token usage. Refused model-server connections are classified as transport failures, skip generic draft retry, and state that no model response was generated and no token cap was hit. When deterministic fallback is used, any collected model usage rows are still written to `model_logs` for later diagnosis. Turn normalization accepts common narration/segment aliases, hidden `gm_events`, and reuses valid draft narration when the verifier omits it. Malformed JSON repair uses a larger repair token budget so full turn objects are less likely to fall through to deterministic fallback; if draft JSON repair still times out but the raw draft contains readable narration, the adapter recovers narration only, ignores unparseable state changes, and continues through verification instead of immediately using deterministic fallback. Setup randomization includes current age/sex and previous-life age/sex, normalizes `custom_skills` into comma-separated phrases so AI-filled Custom Proficiencies match the setup UI contract, and falls back to deterministic backend values when model output is unavailable or invalid. **Setup randomization.** A group roll ships `field_contracts` for every requested field — kind, `allowed_values`, and the field's own forbidden line — because the group path used to be the one caller sending a bare `return_fields` name list with no shape at all. Asked openly, the model answered `magic_level` with "low", "low-magic" and "Limited to arcane crafters and guilds"; every one falls through `normalize_magic_level()` to its default, so the stored value was "rare" on 12 rolls out of 12 and looked like a model preference rather than a silent default. Idea sparks reach prompts through `idea_bank.prompt_sparks()`, which sends `kind`/`text`/`keywords` only: `id`, `title` and `examples` are all shaped exactly like a setup field value and all three were measured being pasted in verbatim (`world_style: "low_fantasy_mud"`, `world_style: "Low fantasy mud and knives"`, `start_location: "a broken cart axle starts the plot"`). Telling the model not to copy titles was in the rules the whole time and produced 13 verbatim pastes across 12 rolls; removing the field produced 0. `looks_like_card_slug()` and a `start_location` check against `is_plausible_place_name()` are the backstops in `field_contamination_reasons()`, and `_drop_echoed_custom_style()` refuses a `custom_style` that only restates `world_style`.

#### Dice Authority

- **Files:** `app/rng.py`
- **Purpose:** Owns every "how many" and "how much" decision. Dice notation parsing, deterministic seeding, magnitude bands, and the roll audit trail.
- **Key API:** `roll_dice()`, `seed_from()`, `campaign_seed()`, `rng_for()`, `resolve_magnitude()`, `normalize_band()`, `band_from_number()`, `record_roll()`, `recent_rolls()`, `band_contract_block()`, `set_magnitude_overrides()`
- **Consumers:** `app.world` (turn band resolution), `app.encounters`, `app.prompts`, `app.turn_dsl`, `app.main`.
- **Dependencies:** `app.db`, stdlib `hashlib`/`random`.
- **Design Notes:** The model proposes a band (`none, trivial, small, moderate, large, huge`, `-` prefix for losses) and this module rolls the number, scaled by player level, campaign difficulty, and growth-speed settings, then clamped per table. Negative bands clamp the *magnitude* before negating — clamping after negation silently zeroed every loss on floor-0 tables (damage, fame, item_count). Seeds come from blake2b over (campaign seed, turn, tag, salt) rather than Python's randomized `hash()`, so rewind/regenerate reproduce identical dice across processes. `campaign_rng_seed` lives in `settings` and travels with world export. Raw numbers from a model are not trusted and not rejected: they are bucketed via `band_from_number()` and re-rolled, keeping older prompts and third-party agents working. `AI_RPG_BAND_AUTHORITY` (or the `band_authority` playthrough option) selects `rolled` (default), `bands`, or `off`. Every roll is written to `dice_rolls` and summarized into the turn journal under kind `dice`.

#### Content Packs

- **Files:** `app/content_packs.py`, `content/packs/`, `content/pack-examples/`, `data/packs/`
- **Purpose:** Add, retune, or remove skills, powers, items, encounter tables, and magnitude tables from JSON files with no code changes; and emit a self-contained authoring specification for external LLMs.
- **Key API:** `validate_pack()`, `install_pack()`, `remove_pack()`, `set_pack_enabled()`, `list_packs()`, `export_pack()`, `sync_packs_from_disk()`, `apply_active_packs()`, `active_skills()/active_powers()/active_items()/active_encounter_tables()/active_magnitude_tables()`, `skill_triggers()`, `disabled_skill_codes()`, `authoring_bundle()`
- **Consumers:** `app.skill_checks` (skill overlay + triggers), `app.encounters` (terrain/kind tables), `app.rng` (magnitude overrides), `app.world` (item power resolution), `app.main` routes.
- **Dependencies:** `app.db`, `app.rng`.
- **Design Notes:** Format `morkyn-content-pack-v1`. Load order is built-in Python catalog → `content/packs/` (builtin, disable-only) → `data/packs/` (user, removable), with later entries overriding earlier ones by `code`; `"enabled": false` on a built-in code removes that content from play. Every contributed entry is recorded in `content_pack_entries` so uninstall is exact, and live `inventory`/`abilities` rows are *detached* (`pack_id` cleared) rather than deleted so a player never loses gear to an uninstall. `validate_pack()` returns errors as `{path, message, fix}` specifically so the response can be fed back to an authoring model for self-correction; `authoring_bundle()` bundles the schema, field→column mapping, hard rules, a worked example, and in-use codes for a model with zero project context. Packs are loaded at FastAPI startup and never block it on failure.

#### Encounters and Danger

- **Files:** `app/encounters.py`
- **Purpose:** Server-side decision of whether anything happens while moving, waiting, or resting, and what.
- **Key API:** `assess_danger()`, `roll_encounter()`, `player_snapshot()`, `terrain_profile()`, `kind_profile()`, `danger_band()`, `top_factors()`, `danger_context_block()`, `encounter_summary_line()`
- **Consumers:** `app.tile_world.roll_travel_encounter()`, `app.world._local_crowd_danger()` (wait/rest path), `app.main` `/api/danger`.
- **Dependencies:** `app.rng`, `app.content_packs`, `app.db`. Imports no `app.world`/`app.tile_world` at module scope, so both may call in.
- **Design Notes:** Danger is two-stage: environment terms (terrain, weather, clock, road/settlement, difficulty, hidden base) are **additive** and set the level; player terms (awareness stats, field skills, level-vs-terrain, wounds, fatigue, energy, carried load, karma, area reputation, known danger markers) are **multiplicative** and scale it. Additive player bonuses were tried first and were wrong — a few of them cancelled a town's entire base risk and made every skilled character untouchable. The combined player multiplier is damped as `raw ** 0.55` clamped 0.4–2.6, because undamped products saturated the cap for any character with several mild penalties. Exposure compounds as `1 - (1 - danger) ** hours` with a 0.12-hour floor per step. Encounter participant counts and threat come from `rng.resolve_magnitude()` band rolls, never from the model. A passive awareness check against `DC 10 + danger*12` decides `forewarned` vs `surprised`, and a clean read on a non-hostile meeting can avoid it entirely. `player_snapshot()` is a deliberately cheap four-query read rather than `world.get_state()`, which runs on every map step. All failures fall back to the legacy terrain+weather roll so travel never breaks.

#### Local-Model Turn Pipeline Guards

- **Files:** `app/llm.py` (verification policy, circuit breaker, depth retry), `app/skill_checks.py` (`search_skills`, `gm_context_block`)
- **Purpose:** Keep the turn pipeline affordable and reliable on 7B-class local models.
- **Key API:** `verifier_is_disabled()`, `verifier_breaker_status()`, `reset_verifier_breaker()`, `_verified_output_is_useful()`, `_retry_narration_prose()`, `search_skills()`
- **Design Notes:** Measured on Ollama `qwen2.5:7b-instruct`: the JSON verify pass returned an echo of the input `world_state` on 42/42 turns and the JSON depth retry truncated mid-object on 18/18, together consuming 89% of wall-clock while producing nothing. Three guards address this. (1) **Verifier circuit breaker** — `_verified_output_is_useful()` detects regurgitation (reply carries `world_state`/`draft_turn` wrapper keys, or lacks any turn-shaped key) because that failure parses as valid JSON; after `AI_RPG_VERIFY_FAILURE_LIMIT` consecutive failures (default 3, `0` disables) the pass is skipped for the session and resets on any success, so capable models are unaffected. Both the DSL and JSON draft paths are hooked — patching only one is a silent no-op, since the DSL path is the one that runs by default. (2) **Prose depth retry** — `_retry_narration_prose()` asks only for prose and splices it into the existing turn, replacing a retry that requested a whole turn JSON; that form could not fit the response cap and could discard the draft's structured ops. Output is clamped to `MAX_TURN_NARRATION_CHARS` on paragraph boundaries. The JSON retry remains as a fallback. (3) **Verification-skip policy** — short narration is no longer a blocker (the verifier cannot lengthen prose) and `conversations` is no longer high-risk (it records a topic and summary, mints nothing); inventory/skills/events/abilities remain high-risk. Separately, `gm_context_block(query=...)` searches the skill catalog per turn instead of shipping all ~60 entries (~6.4KB/~1,600 tokens); the catalog is no longer persisted into `playthrough_options`, which had been re-sending it inside every prompt. Net effect over 30 turns: median narration 888 → 1993 chars, below-floor turns 60% → 0%, mean turn ~53s → ~19s.

#### Turn Continuity Authority

- **Files:** `app/world.py` (contracts + repairs), `app/naming.py` (naming demands + `name_ledger`), `app/llm.py` (`_ensure_narration_voice`, `_retry_narration_voice`, `_splice_prose_into_turn`), `app/prompts.py` (`PROSE_VOICE` point-of-view block), `app/turn_dsl.py` (travel op rules)
- **Purpose:** Hold the turn-to-turn state a 7B does not reliably maintain on its own — where the player is, who they are addressed as, and whether an NPC actually has a name.
- **Key API:** `movement_contract()`, `resolve_movement()`, `travel_intent()`, `narrative_voice_contract()`, `player_pronouns()`, `check_narrative_voice()`, `is_generic_person_label()`, `name_seed()`
- **Consumers:** `app.world.build_prompt_context` (packet blocks), `app.world.apply_turn` (repairs + telemetry), `app.llm` narration quality ladder, `app.turn_dsl.build_dsl_user_prompt`.
- **Dependencies:** `app.rng` (`seed_from`), `app.db`.
- **Design Notes:** Same pattern as the dice authority: state the server already knows is stated as a contract in the packet, and verified afterwards rather than trusted. Measured on a 30-turn `qwen2.5:7b-instruct` run — **0 `MOVE` and 0 `LOC_NEW` ops across eight travel actions** (the world never grew past one location), 11 of 30 narrations in third person, and an NPC stored under the literal name `"Woman"`.
  **Movement.** `movement_contract()` ships the current location, the required field, and `known_places` — **names, not codes**. Given a code list a 7B reuses the nearest listed code as a stand-in for anywhere new (it narrated a river valley while recording a move back to town, on 8 of 11 moves), and with only `L1` in the world it invents `MOVE L2`, which `_find_location_id()` resolves back to the current location so the move silently no-ops. `move_to_location` already resolves by name against existing places, so codes only enabled those failures; `_match_location_by_name()` matches case- and article-insensitively so "the Redmill Ford" cannot mint a twin. `resolve_movement()` rejects unknown and self-referential codes, then fills a missing `MOVE` from evidence the model produced *this turn*, most-confident first: a place it minted via `LOC_NEW`; a known place the player named verbatim; an `[[L#]]` in the narration's last 900 characters alongside arrival language; or, only after an invented code, a place name extracted from the arrival sentence (`_movement_destination_from_narration`, which requires a destination preposition so scenery cannot become a location). It runs **before** `_save_snapshot()` so a repaired destination is inside the rewind record. Status (`model` / `not_travel` / `repaired` / `unresolved`, plus a `prose_mismatch` flag when the model moves to a place its own prose never names) lands on `state.movement` and the `play_turn` payload; repairs and unresolved travel are journaled. `play_turn` must re-attach this telemetry after any `get_state()` refresh — the injuries path re-reads state and silently dropped it on half of turns.
  **Resolving the action.** The largest cause of travel turns that never travelled was not a missing op: the model narrated deliberation ("Do you approach the figure, or continue to the ruins? The choice is yours.") instead of the journey. A resolve-the-action rule in `PROSE_VOICE` and the DSL prompt took travel turns that moved from 25% to 83%. The residue is trimmed deterministically — `_trim_menu_ending()` and `_trim_option_list()` in `app/llm.py` cut stock closers and trailing bullet menus, since prompting alone did not shift the behaviour and the UI already asks the player what to do. Both are deliberately narrow: perception phrasing ("you could hear the mill wheel") is excluded, a list with prose under it is left alone as something in the world, and nothing is trimmed below `MIN_TURN_NARRATION_CHARS`.
  **Intent.** `_intent_tokens()` stems inflected verbs (`walking` → `walk`, `going` → `go`, plus an irregular table) because keywords are stored as bare verbs and `"keep walking east"` scored zero for travel. `travel_intent()` accepts travel as a *secondary* intent, since ties break in keyword-table order and put travel behind investigation.
  **Voice.** `narrative_voice_contract()` states second person and the player's pronoun set (male/female only when clearly stated, otherwise they/them) per packet; the long-form rule lives in `PROSE_VOICE` inside the system prompt, which the runtime caches, so the packet copy stays short. `check_narrative_voice()` flags only the unambiguous failure — a narration over 200 characters that never says "you" — which triggers one prose-only rewrite through `_retry_narration_voice()` (`AI_RPG_VOICE_REPAIR=0` disables). Pronoun counts are reported on `state.voice_check` but never auto-rewritten: NPCs have genders too, so a regex pass cannot tell a mis-gendered player from a correctly gendered cast.
  **Names.** `is_generic_person_label()` rejects article + modifier + generic-head labels ("Woman", "The Hooded Figure", "Guard") while keeping anything carrying a real proper-noun token ("Old Mara", "Captain Vesk"). Rejected names flow into the existing `invent_person_name()` + prose-rename path, via `unique_person_name()` — the shell pool is only 20x20 and a live run produced two NPCs both called "Saltbin". `name_seed()` replaces `abs(hash(...))` at all three call sites — Python string hashing is randomized per process, so the same save renamed the same NPC differently on every reload. Place names get `humanize_place_name()` at both the upsert and lookup sites, after a run put a location called `east_road` on the player's map.
  **Naming demands.** A 100-turn continuity probe planted "the sealed letter is addressed to Corvin Marrow" on turn 2. Asked to read that name aloud on turn 26 the model answered plainly; asked the identical question on turn 94 it wrote *"the name you read brings a weight to your chest"* and never said it — while volunteering an unrelated debt in the same paragraph. It knew the fact existed and would not commit to it. `app/naming.py` treats this like movement: `name_request_intent()` classifies the player's line as demanding a name, `resolve_name_demand()` answers it from the `name_ledger` first, then from journal history (`player` rows outrank `narration` — what the player asserted is canon, what the narration echoed is derivative), and finally by minting one through `invent_person_name()` + `name_seed()`. Every answer is written to `name_ledger` (`subject` PRIMARY KEY, first writer wins) so the second asking matches the first; **an invented name that is not recorded is just a slower dodge.** `naming_contract()` puts the resolved name in the packet for both the JSON and DSL paths, and `enforce_named_answer()` appends one plain sentence when the prose still fails to state it — including on the deterministic-fallback path, which dodges too. Detection is phrase-level for the same reason venue detection is: `name` is an ordinary English word ("a name for the road", "names carved in the post"), and a bare keyword turned roughly every third turn into a naming demand.
  **Answer acts.** When the player's line commits them to *saying* something ("I explain why...", "I tell them...", "I admit..."), the narration owes that content — the same debt a naming demand creates. `check_answer_act()` flags only a total miss: an explicit answer act whose topic words are all absent from a narration over 200 characters. `_ensure_answer_act()` then runs one prose-only rewrite through `_retry_answer_act()` (`AI_RPG_ANSWER_REPAIR=0` disables), and accepts whatever comes back — the substance is the model's job, so unlike a name there is nothing deterministic to substitute, and inventing the player's own explanation would be worse than a thin one. **A broader "did the narration respond to the action?" detector was built and rejected**: scored against 100 recorded turns, a category-overlap version flagged five of which at least three were plainly responsive ("You ask about..." answering a line about listening for rumours), and a rewrite fired on responsive prose makes the turn worse. The shipped check fires once on those same 100 turns, on the one real failure.
  **Remembered specifics.** An answer act can name its topic and still say nothing. Turn 88 of the 20260823 run answered "who I owe, how much, and when" with *"You answer honestly: who you owe, how much, and when"* and never named the lender or the amount — the run's only recall miss. It was **not** a retrieval failure: the record was in that turn's prompt six times over, so prompt text alone had already failed. `recall_contract()` matches an answer act against the world's own conversation/claim records by stemmed topic overlap (>= 0.5) and pins the **proper nouns and amounts** in the best match; `check_recall_specifics()` passes if *any one* of them reaches the prose, and `_ensure_recall_specifics()` runs one prose-only retry with the record handed back verbatim. Only names and numbers are demanded back: requiring topic words would fire on prose that answered in its own words, and rewriting a good scene is a loss. Scored against all 100 turns of that run it selects exactly one turn — the real failure — at every threshold from 0.3 to 0.5.
  **NPC pronouns.** `npcs.pronouns` is pinned write-once by `bind_npc_pronouns()` after each turn and stated back through `narrative_voice_contract().cast_pronouns`. One 100-turn run referred to the same bargeman as "he" 41 times and "they" 128 times — no gender flip, simply nothing asserting which was right, so the model chose afresh each turn. `infer_npc_pronouns()` reads the sentence naming the character plus the following one when that sentence names nobody else, because prose almost never puts the pronoun in the sentence that introduces the name; a one-sentence window pinned nothing. **Both** sentences must name this character alone — for a while only the lookahead was checked, and the naming sentence was not, so a weaver introduced beside "a young boy, Liora" was pinned masculine off the boy, and "Eldrin ... narrows his eyes ... around Cinderrow bundle" pinned Cinderrow off Eldrin's three "his". Pass the rest of the cast as `others`: the capitalised-token heuristic cannot see a name at the start of a sentence, which is exactly where the second character often sits. Sharing a sentence disqualifies it for *everyone* named in it; a clean sentence usually follows within a turn or two, and declining costs a turn while pinning wrong costs the run. Mixed or absent signal leaves the row unset (defaulting to they/them) — a wrongly pinned NPC is asserted as truth every turn afterwards, so silence beats a guess. Replayed over the recorded run it pins all four recurring NPCs between turns 6 and 17.
  **Opcodes.** `OPCODE_ALIASES` + `normalize_opcode()` in `app/turn_dsl.py` map near-misses onto the closed list, and an unrecognized line is now skipped rather than fatal: a single `MOV` typo used to raise and discard every other op in that turn. A block where *nothing* parses still raises, so genuinely wrong output format still triggers a retry. The same isolation now covers *arity* errors, which bypassed it: `ops_to_turn()` applies each line through `_apply_op()` inside its own try, records the skips in `self_check` and `_dsl.malformed_ops`, and keeps the rest. Three of the four failed self-checks in the 20260823 run were one line — `INDEX npc F "..."` — where the entity type `npc` was read as the `NPC` flag key (`EVENT ... NPC <code>`), swallowing the code, failing INDEX's own arity check, and discarding every MOVE, TALK and JOURNAL in the turn. `_LEADING_POSITIONALS` now marks the leading tokens of `FOCUS` (1) and `INDEX` (2) as positional by definition, so they are never read as flags.

  **World variety.** Prose read well while the *world* kept reinventing the same person and place under new labels. Prose-seeded NPC roles came from a fixed four-item cycle starting "hooded stranger"/"cloaked local", which won 24 of 27 NPCs and fed back on itself — seeded strangers entered the cast, the cast entered the prompt, the model wrote more hooded figures. `_SEED_ROLE_POOLS` now supplies era- and location-aware occupations, never repeats a role standing in that place, and puts appearance in the summary instead of the role column. The **place** axis is chosen by *scored* keyword match, so a town summary mentioning "the road" no longer staffs a gate-town with charcoal burners, and it is era-independent — a docking bay is "where things arrive" for the same reason a wharf is. The **era** axis (`preindustrial` / `industrial` / `modern` / `future`) comes from `resolve_world_era()`. Until it existed the pools were pre-industrial only and genre never entered the function, so a futuristic world was staffed **bargeman, boatwright, salt carrier** at Docking Bay Seven and **scribe, weaver, tanner** on a colony ship's Reactor Deck. That survived four 100-turn playtests because every one of them ran the same world, `world_style: "frontier dark fantasy"` — nothing had ever asked the game for another setting. Identity is world-wide, not per-location: `_person_name_taken()`/`unique_person_name()` guard every name generator (the 20x20 shell pool produced three "Grainwick"s), and `_upsert_npc` matches an existing NPC by name anywhere and moves them, rather than minting a second "Aria the baker" at the next location. For places, `_place_extension_target()` folds "Riverbend Hillcrest Camp" back into "Riverbend Hillcrest" when the addition is only a generic tail noun — bearings and storeys count as generic, so "Hills Beyond Mosswake Gate Eastward" folds too — and `_place_stem_target()` is its mirror for when the model drops the qualifier instead of adding one ("Riverbend" after "Riverbend Camp"), firing only when exactly one existing place matches so an ambiguous stem keeps its own row rather than teleporting the player. `_match_location_by_name()` strips leading descriptors so "Old Ruins by the River" is not a second "Ruins by the River". `is_plausible_place_name()` rejects bare headings after a run recorded `MOVE East` as a location named "East", and bare entity codes after a space-opera run spent three turns at a location literally named `[[L1]]`; it unwraps brackets itself rather than trusting the caller, because the setup form calls it on raw model output.
  **Tech level coherence.** `tech_level` is a Pydantic field with `default="iron age"` (`app/main.py`), so a setup that never touches the tech dropdown records iron age whatever the player wrote elsewhere. A live space-opera run stored `tech_level='iron age'` beside `world_style='far-future interstellar civilisation, faster-than-light travel'`, and the packet asserted **both, every turn** — contradictory world truth handed to the model for the whole run, and a boatwright on the docking bay from the seeder that trusted `tech_level` first. A recorded `"iron age"` cannot be told apart from a deliberate pick at this layer, so `resolve_world_era()` lets the style prose win when the two disagree, while an explicit non-default pick is never overridden. `coherent_tech_level()` states the era's canonical value in the packet instead of the contradicting default.
  **Anti-repetition.** `anti_repetition_block()` was raw word frequency, so a turn spent with Larkcoil at Redmill Ford came back telling the model to avoid "larkcoil", "redmill", "ford" — asking the narrator to stop naming its own world. Entity names are protected at two layers (`_protected_entity_words` from the packet, and every DB name inside `narration_tics`). `narration_tics()` adds run-wide tics because words like "hooded" recur just under once per turn: no single-turn threshold catches them, yet they are what makes twenty-four scenes read alike.

> **Trap:** four separate allowlists silently drop data that is not listed —
> `HANDOFF_BASE_CONTEXT_KEYS` (context blocks), `HANDOFF_PLAYER_FIELDS` (player
> patch fields), the DSL `OPCODES` set, and the `play_turn` return payload
> (telemetry keys such as `movement`, `voice_check`, `naming`). Each has now caused a real bug where
> a feature looked wired up and was nulled out in the packet. When adding a
> context block or a player field, add it to the allowlist in the same commit and
> check the rendered prompt in a trace, not just the code path.

#### Prompt Contracts

- **Files:** `app/prompts.py`
- **Purpose:** Centralizes system prompts, compact prompts, verifier prompts, and the required JSON shape that world application expects.
- **Key API:** Prompt constants imported by `app.llm`.
- **Consumers:** `app.llm`.
- **Dependencies:** None beyond Python string handling.
- **Design Notes:** Keep prompt schema changes synchronized with `app.world` application logic and `static/app.js` rendering expectations. Turn prompts include player identity fields such as current age/sex and previous-life age/sex as descriptive facts, not behavior stereotypes. Turn prompts tell the model to read `world_state.action_context.priority_segments` first and avoid scanning every included player/world field equally after the opening. Verifier prompts may receive `world_state.verification_policy`; when present, they treat `deterministically_verified` checks as already cleared by app logic and focus on `remaining_checks` plus blockers. When `world_state.mechanics_context.combat.status` is `resolved_player_attack`, the model and verifier must treat the listed weapon/equipment, damage, and target health result as authoritative app math while keeping special abilities, tactics, morale, death/capture, witnesses, and prose consequences as narrative work. Equipment bonuses are represented through `player.effective_stats`, `equipment_effects`, and derived `abilities` while equipped; prompts tell the model to inspect raw inventory/equipment only for item handling, trade, loot, equip/unequip, or hard item references. Movement focuses on environment, carry limits, and derived stats/abilities; combat focuses on deterministic mechanics context plus player-vs-target effective stats, skills, abilities, and terrain; ability use focuses on lock state, costs, prerequisites, race/magic rules, target resistance, and environmental limits. Turn prompts ask for a player-visible high-level `scene_plan` with 1-6 focus points, then continuous prose in paragraph-like `narration_segments` rather than visible labeled scene/result blocks; normal playable narration should be at least 1000 visible characters and target about 1500. Event items may include lifecycle fields: `persistence`, `disappear_chance`, and `respawn_chance`; those private lifecycle labels are not shown in the scene-plan UI. Prompt output may also include hidden `gm_events` for future consequences and off-screen reactions.

#### Browser UI

- **Files:** `static/index.html`, `static/app.js`, `static/styles.css`
- **Purpose:** Plain browser interface for setup, turns, indexed entities, inventory, aliases, world memory, search, GM notes, model config, export/import, and rewind.
- **Key API:** Fetches the FastAPI routes listed below; core functions include `loadState()`, `renderShell()`, `requestTurn()`, `startGame()`, `collectSetupSettings()`, `restoreSetupSettings()`, `saveSetupSettings()`, `loadSetupSettings()`, `renderIndex()`, and `displayTurnPayload()`.
- **Consumers:** End users in a browser.
- **Dependencies:** Browser DOM APIs and the FastAPI JSON route contract.
- **Design Notes:** There is no frontend build step. Keep user-provided or model-provided text escaped before inserting into HTML. Setup settings export/import is frontend-only and uses `ai-rpg-setup-settings-v1` JSON for form controls, custom text, gain controls, locks, and ability cards; it is separate from world export/import. Character setup includes current age/sex and conditionally shows previous-life age/sex when backstory or memory settings imply reincarnation, transmigration, rebirth, or former-life memory. Custom Proficiencies are displayed, saved, loaded, randomized, and submitted as comma-separated phrases where each comma separates a proficiency or training-rule phrase. Setup submit sanitizes text and numeric form values before JSON serialization so mobile number-field quirks cannot stringify `NaN` as `null`. Starting a playthrough shows a full-page transition splash with progress lines, a live heartbeat/elapsed timer with rotating reassurance text for long local-model waits, and a slower typewriter reveal of the opening narration. Normal Send, Continue, and Regenerate waits show an elapsed-time reassurance panel in the Output box until the server responds. Current-turn narration is rendered as continuous prose while preserving clickable entity references after the reveal completes. If deterministic fallback is used, the UI shows a warning panel explaining that the visible prose is fallback narration and separates that from the rejected model issue. Every turn also shows the local debug trace JSON path returned by the API. The Player pane shows effective equipment-derived stats/abilities, Inventory item rows show stored stat modifiers and granted abilities, and NPC cards/details show initialized combat HP, attack range, defense, and dodge. Turn responses render a high-contrast reward banner when applied XP or positive inventory gains are present. Model settings include provider selection, llama.cpp/GGUF path and URL fields, Ollama URL/model fields, editable Soft Token Target and Hard Token Cap controls; Test Connection saves the current form before checking status so selected model files are used immediately. The History pane renders raw journal rows as paged, collapsed visual history and remembers user expansion choices; it is not AI prompt context. The visible GM tab was removed; hidden GM notes/events remain backend-only. CSS media queries stack the game panes on tablets/small monitors, make composer and tool buttons touch-friendly on phones, and keep landscape phone layouts compact.

#### Launchers

- **Files:** `Morkyn.ps1`, `Morkyn.bat` (primary); `start.bat`, `start.sh` (standalone bootstrappers, published as release assets); `start_ai_rpg.ps1`, `start_ai_rpg.bat` (compatibility shims)
- **Purpose:** Interactive pre-play menu (simple + Advanced Gatehouse), install missing Python dependencies, optionally start a managed llama.cpp server, and open the browser.
- **Key API:** Environment overrides documented in `README.md`; prefs in `data/launcher_prefs.json`.
- **Consumers:** Windows local users; `start.sh` covers Linux and macOS.
- **Dependencies:** Python, requirements from `requirements.txt`, optional local GGUF model or Ollama/cloud API.
- **Design Notes:** Simple menu is the default (where / engine / pipeline / Play); Advanced (`9`) exposes the full board. Keyboard always works; mouse clicks are best-effort in a normal Windows console. The launcher uses `AI_RPG_GGUF_MODEL` when a managed llama.cpp server should start, and when that env var is absent it reuses a saved `model_config.gguf_model_path` from SQLite on the next launch. Without a configured GGUF path, it still starts the browser app but warns that no managed llama.cpp server will start unless Ollama/cloud is configured. Local-network mode sets `AI_RPG_APP_HOST=0.0.0.0` for phone access; VPN mode prefers overlay adapters. Managed llama.cpp remains loopback by default (`AI_RPG_LLM_HOST=127.0.0.1`). Startup wait: `AI_RPG_LLM_STARTUP_TIMEOUT`. LLM logs: temp files by default, or `AI_RPG_LLM_LOG_MODE=console`. `start.bat` / `start.sh` are the download-and-run entry point: they clone the repo when it is absent, compare `HEAD` against `origin/main` and prompt before fast-forwarding, refuse to touch a checkout with local changes or local commits, and fall through to starting the existing copy when offline. They build a private `.venv` and install `requirements.txt` with `llama-cpp-python` filtered out unless `--full` is passed, because its CUDA wheels are a large download that fails without a matching toolchain and neither Ollama nor the cloud APIs need it. `start.bat` then hands off to `Morkyn.bat` with the venv ahead on `PATH`; `start.sh` runs uvicorn directly, since there is no POSIX Gatehouse.

---

## 3. Technology Stack

| Category | Technology | Version / Source | Notes |
|---|---|---|---|
| Language | Python | 3.x; launcher checks `python`, `py -3`, then local Python 3.12 path | Backend and launch scripts |
| Language | JavaScript | Browser runtime | Plain JS, no bundler |
| Markup / Style | HTML / CSS | Browser runtime | Static files served by FastAPI |
| Web Framework | FastAPI | 0.136.1 | API and static shell |
| ASGI Server | Uvicorn | 0.46.0 | Local development server |
| Validation | Pydantic | 2.13.4 | Request models |
| Database | SQLite | Python standard library | Persistent world state |
| LLM Server | llama-cpp-python[server] | 0.3.22 | Managed local GGUF server path in launcher |
| LLM Alternative | Ollama-compatible API | Configurable | Used when provider is not `llama_cpp` |
| Numeric Library | NumPy | >=1.22,<2.4 | Dependency in requirements |
| Test Runner | Ad hoc Python script | `tests/behavior_test.py` | Memory/token/slots regressions; also `tests/test_narration_pipeline.py` |
| Build Tool | None | N/A | No frontend or backend build step |
| CI/CD | None | N/A | Local prototype |

---

## 4. Coding Conventions

### Naming
- Python modules, functions, and variables use `snake_case`.
- Pydantic request classes use `PascalCase` and usually end in `Request`.
- JavaScript functions and variables use `camelCase`.
- Database tables and columns use `snake_case`.
- API routes use lower-case kebab-case paths such as `/api/model-config`.
- Durable entity references use compact codes: NPCs `A`, `B`, `AA`; locations `L1`; items `I1`; events `E1`.

### File & Module Organization
- Keep API request models and route handlers in `app/main.py`.
- Keep schema creation, connection helpers, and migrations in `app/db.py`.
- Keep world-state reads, writes, indexing, search, import/export, and rewind behavior in `app/world.py`.
- Keep model transport, model config, retries, JSON repair, and fallback generation in `app/llm.py`.
- Keep prompt contracts in `app/prompts.py`; any prompt shape change must be matched by world application logic.
- Keep frontend behavior in `static/app.js` and visual styling in `static/styles.css`; this app intentionally has no frontend framework or build pipeline.

### Error Handling
- Translate user-fixable domain errors to HTTP 400 from route handlers.
- Translate local model failures to HTTP 503 where the browser can report them cleanly.
- Do not silently swallow model JSON failures; either repair, retry, raise `LlmError`, or mark fallback usage in the returned payload.
- Continue clamping player health, XP, gold, level, inventory counts, and related state before persisting model-proposed changes.

### Persistence Rules
- Treat SQLite as authoritative; model narration is never the source of truth by itself.
- Use `connect()` so foreign keys are enabled and the configured `AI_RPG_DB` path is honored.
- Preserve export/import compatibility for `ai-rpg-world-v1` unless making an intentional migration.
- Preserve delta rewind compatibility for `ai-rpg-delta-v1` snapshots unless making an intentional migration.
- Runtime files under `data/` are local state and are ignored by git.
- Local `.env` variants, SQLite world/save files, JSONL runtime logs, trace folders, and GGUF/GGML model files are ignored by git and must stay out of public commits.

### Frontend Rules
- Keep the UI usable as static browser assets served from FastAPI.
- Escape player-provided and model-provided strings before inserting HTML.
- When adding state fields, update both the relevant backend state shape and the render functions that consume it.
- Keep API interactions in `static/app.js` aligned with route names and request models in `app/main.py`.

### Testing
- For isolated tests, set `AI_RPG_DB`, `AI_RPG_SOURCE_INDEX`, and `AI_RPG_HISTORY_SUMMARY` to a temp dir at import **and** re-apply them in `setUpModule()`.
- **Trap:** `unittest discover` imports every test module before running any test, and the paths live in process-global env vars, so whichever module is imported last owns them during everyone's tests. Import-time assignment alone silently sent fixtures into `data/world.db`. Each isolated module asserts its resolved paths sit under its temp dir; keep that guard.
- Runtime paths are functions, not constants (`app.db.db_path()`, `app.world.source_index_dir()`, `model_trace_dir()`, `history_summary_path()`, `consolidated_facts_path()`, `campaign_slots_dir()`, `source_index_manifest()`, `app.idea_bank.user_dir()`, `app.launcher_prefs.prefs_path()`). Do not reintroduce module-level `Path(os.getenv(...))` constants for anything under `data/` — that is what froze the paths.
- Run everything with `python -m unittest discover -s tests -p "test_*.py"` (**354 tests**), plus `python tests/behavior_test.py` (7 checks) which is not collected by that pattern. Files written as bare `assert` functions (no `TestCase`) are invisible to `unittest` on their own and would pass vacuously; `tests/test_bare_assert_files.py` imports them under isolated paths and wraps each `test_*` in a generated `TestCase` so they actually run. Keep that file — deleting it silently drops 127 checks. Convert a file to real `TestCase` classes and the wrapper skips it automatically.
- Patch or mock LLM calls for deterministic tests; do not require a real model for normal automated checks.
- Avoid touching `data/world.db` or `data/history_summaries.jsonl` during tests.
- Prefer `tests/behavior_test.py` and `tests/test_narration_pipeline.py` over ad-hoc root scripts.

### Commit Style
- Prefer Conventional Commits where practical: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.
- Update `CHANGELOG.md` for functional user-facing changes, schema changes, route changes, and significant behavior changes.

---

## 5. Key Design Documents

| Document | Location | Description |
|---|---|---|
| README | `README.md` | User-facing overview, launch instructions, environment overrides |
| Codebase Index | `CODEBASE_INDEX.md` | Project structure, conventions, API surface, data model |
| Changelog | `CHANGELOG.md` | Keep a Changelog history for releases and unreleased changes |
| License | `LICENSE.md` | PolyForm Noncommercial 1.0.0 |
| Privacy | `PRIVACY_POLICY.md` | Local-first privacy (also `/privacy`) |
| Docs index | `docs/README.md` | Links to design notes under `docs/` |
| Environment Example | `.env.example` | Optional local defaults for model, API, and agent settings |
| Copilot Workspace Instructions | `.github/copilot-instructions.md` | Required AI workflow, project boundaries, and agent ID table |
| Documentation Instructions | `.github/instructions/documentation.instructions.md` | Rules for CODEBASE_INDEX, CHANGELOG, README, and instruction docs |
| Agent Routing Instructions | `.github/instructions/agent-routing.instructions.md` | Agent ID selection and changelog attribution examples |
| Feature Pipeline Instructions | `.github/instructions/feature-pipeline.instructions.md` | Checklist for significant features, schema, prompt, UI, and launcher changes |
| Implementation Standards | `.github/instructions/implementation-standards.instructions.md` | Security, compatibility, testing, and performance standards |

---

## 6. Build & Run Instructions

### Prerequisites
- Python available as `python`, `py -3`, or the path resolved by `Morkyn.ps1` / `start_ai_rpg.ps1`.
- Windows PowerShell for the provided launcher.
- Optional local GGUF model for the managed llama.cpp server. Override the default with `AI_RPG_GGUF_MODEL` when needed.

### Setup

```powershell
python -m pip install -r requirements.txt
```

Optional local environment file:

```powershell
Copy-Item .env.example .env
```

### Development

Recommended Windows launcher:

```powershell
.\Morkyn.ps1
```

Batch wrapper:

```text
Morkyn.bat
```

The batch wrapper prompts for local-only or local-network/phone mode. It also accepts quick arguments:

```text
Morkyn.bat local
Morkyn.bat lan
```

Manual FastAPI server, useful when an LLM server is already running:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open the app at:

```text
http://127.0.0.1:8000
```

Common launcher overrides:

```powershell
$env:AI_RPG_GGUF_MODEL="D:\path\to\model.gguf"
$env:AI_RPG_LLAMA_CPP_CONTEXT="32768"   # keep >= 12288: the full system contract is ~9.1k tokens
$env:AI_RPG_LLAMA_CPP_GPU_LAYERS="-1"
$env:AI_RPG_LLAMA_CPP_FLASH_ATTN="True"
$env:AI_RPG_TURN_DRAFT_TIMEOUT="900"
$env:AI_RPG_TURN_VERIFY_TIMEOUT="480"
$env:AI_RPG_SETUP_RANDOMIZER_TIMEOUT="240"
$env:AI_RPG_SUGGESTION_TIMEOUT="240"
$env:AI_RPG_APP_HOST="0.0.0.0"
$env:AI_RPG_APP_PORT="8000"
```

### Tests

No reliable formal test suite is currently established. For future tests, use temporary runtime paths before imports:

```powershell
$env:AI_RPG_DB="$env:TEMP\ai-rpg-test-world.db"
$env:AI_RPG_HISTORY_SUMMARY="$env:TEMP\ai-rpg-history.jsonl"
$env:AI_RPG_SOURCE_INDEX="$env:TEMP\ai-rpg-source-index"
python -m unittest discover
```

Run `python tests/behavior_test.py` for memory/token/slots regressions and `python tests/test_narration_pipeline.py` for pipeline unit checks.

Self-contained `unittest` suites that set up their own temp runtime and run with a
bare `python <file>`:

```powershell
python tests/test_dice_and_packs.py   # dice authority, content packs, danger model (64)
python tests/test_continuity.py       # movement, voice, names, variety, menus (75)
```

Live model probes (need Ollama running; `PLAYTEST_TURNS` and `PLAYTEST_OLLAMA_MODEL` override):

```powershell
python tools/playtest_continuity.py   # movement / voice / names / menus + story health
python tools/playtest_7b_longrun.py   # does output decay as the database fills?
```

The remaining `tests/test_*.py` files are bare `assert` functions with no runner,
so `python <file>` on them exits 0 without executing anything — they need `pytest`
(not currently installed) or `unittest discover` with `PYTHONPATH` set to the repo root.

### Production Build

There is no production build step. This is a local prototype served directly by Uvicorn and static files.

---

## 7. API Routes

| Method | Route | Purpose |
|---|---|---|
| GET | `/` | Serve `static/index.html` |
| GET | `/api/state` | Return current visible world state |
| GET | `/api/version` | Return local app, planner, and mechanics version metadata |
| GET | `/api/model-config` | Return local model configuration |
| POST | `/api/model-config` | Update local model configuration |
| GET | `/api/model-status` | Test local LLM connection |
| POST | `/api/select-model-file` | Open a local file picker for GGUF model selection |
| POST | `/api/randomize-setup` | Ask the model to randomize setup fields |
| POST | `/api/turn` | Apply a player turn; empty text continues the scene |
| POST | `/api/continue` | Continue the current scene without player input |
| POST | `/api/regenerate` | Restore the latest pre-turn snapshot and regenerate that response |
| POST | `/api/suggestions` | Generate three suggested player inputs |
| POST | `/api/setup` | Start a new playthrough and opening scene |
| POST | `/api/alias` | Add a player-created alias for an indexed entity |
| POST | `/api/player-alias` | Create an identity alias for the player |
| POST | `/api/player-alias/state` | Activate, deactivate, or disguise a player alias |
| POST | `/api/rewind` | Restore the latest or selected rewind snapshot |
| GET | `/api/export` | Export world state as `ai-rpg-world-v1` JSON |
| POST | `/api/import` | Import `ai-rpg-world-v1` JSON |
| POST | `/api/search` | Search world memory and generated source index |
| GET | `/api/bible` | Return World Bible summary data |
| POST | `/api/gm-notes` | Save hidden GM notes for backend model context |
| GET | `/api/gm-notes` | Return hidden GM notes for backend tooling; not exposed in the normal UI |
| GET | `/api/content-packs` | List installed content packs with per-section counts |
| GET | `/api/content-packs/authoring-bundle` | Self-contained pack spec for an external LLM (schema, rules, field→column map, example, in-use codes) |
| POST | `/api/content-packs/validate` | Validate a pack; errors carry `{path, message, fix}` for model self-correction |
| POST | `/api/content-packs/install` | Install or replace a pack |
| POST | `/api/content-packs/remove` | Uninstall a user pack and everything it contributed |
| POST | `/api/content-packs/enable` | Enable/disable an installed pack (the only removal path for built-ins) |
| GET | `/api/content-packs/export/{pack_id}` | Return a pack as authored JSON for editing or sharing |
| GET | `/api/dice/recent` | Audit feed of server-rolled amounts (`?limit=`, `?turn=`) |
| GET | `/api/danger` | Current danger assessment for the player's tile with its factor breakdown |

---

## 8. Data Model And Runtime State

### SQLite Tables

The current world export table set is defined in `app/world.py` as `WORLD_TABLES`:

- `locations`
- `player`
- `npcs`
- `relationships`
- `inventory`
- `equipment_slots`
- `inventory_capacity_modifiers`
- `player_skills`
- `abilities`
- `events`
- `conversations`
- `response_drafts`
- `aliases`
- `player_aliases`
- `karma_history`
- `turn_summaries`
- `model_logs`
- `verification_memory`
- `journal`
- `pacing`
- `settings`
- `gm_notes`
- `gm_events`

`turn_snapshots` is used for rewind state but is intentionally not part of the normal `WORLD_TABLES` export list.

`journal` rows are retained for visual history, export/import, audit, and player review. They are intentionally excluded from turn prompts and generated source-index retrieval so raw output prose does not become model memory.

`inventory.stat_modifiers` and `inventory.granted_abilities` store item effects as JSON. These effects are not copied into permanent player tables. `app.world.get_state()` derives active `equipment_effects`, `player.effective_stats`, and equipment-sourced ability rows from equipped inventory only, so unequipping an item removes its stat and ability effects from state, prompt context, and the browser UI.

`gm_events` stores hidden between-turn consequences, off-screen reactions, clocks, and secrets proposed by verified turn JSON. Normal `GET /api/state` responses do not include these rows; turn generation receives a bounded hidden slice only through `get_state(include_hidden=True)`.

The `player` table stores setup identity fields including `public_name`, `title`, `age`, `sex`, `previous_life_age`, `previous_life_sex`, `backstory_mode`, `backstory`, and `memory_policy`. Previous-life fields are intended for reincarnated/transmigrated starts and remain blank for ordinary starts unless explicitly supplied.

The `npcs` table stores durable combat columns `health`, `max_health`, `attack_min`, `attack_max`, `defense`, and `dodge`. These are additive fields initialized lazily for combat-relevant NPCs from player level, playthrough difficulty/scaling, NPC rank/stat_profile, and equipment-derived player stats; deterministic player-attack damage updates NPC health directly in SQLite and writes a `mechanics` journal row.

`verification_memory` stores scoped verifier wins by check name, intent, turn kind, entity codes, confidence, source, and context signature. It is included in export/import and rewind snapshots, cleared on new playthroughs, and used only when the current planner scope matches so cached checks do not make unrelated risky turns skip verification.

### Event Lifecycle Columns

The `events` table includes lifecycle metadata for location happenings:

- `persistence` - `persistent`, `temporary`, `recurring`, `traveling`, or `background`.
- `disappear_chance` - percent chance a temporary/traveling/recurring active event fades when the player leaves its location.
- `respawn_chance` - percent chance a recurring/traveling event reactivates when the player returns.
- `last_seen_turn` - last turn when the event was active, backgrounded, resolved, or refreshed by movement.

These columns are additive migrations. The engine treats the LLM's event metadata as proposals, clamps chances, keeps temporary events stable during the current visit, and applies departure/return lifecycle changes only through SQLite updates.

### Runtime Files

- `data/world.db` - SQLite database created by `init_db()`.
- `data/history_summaries.jsonl` - compact long-term turn summaries.
- `data/source_index/` - generated source index manifest and JSONL files when source search is refreshed.

### Migration Rules

- `init_db()` creates missing tables and seeds default location/player data.
- `_migrate_columns()` handles additive migrations for existing databases.
- Breaking schema changes should include an explicit migration note in this file and a changelog entry.

---

## 9. LLM Turn Flow

1. Browser submits setup, turn text, continue, or suggestion request through `static/app.js`.
2. FastAPI validates the request with Pydantic models in `app/main.py`.
3. `app.world` loads current SQLite state and refreshes or searches source-index context where relevant. Raw journal history stays visual-only; structured summaries, entities, events, conversations, source-index records, hidden GM events, and scoped verification memory provide model/runtime continuity.
4. For combat actions with known targets, `app.world` initializes missing NPC combat profiles and builds `mechanics_context`; direct player attacks include deterministic weapon/equipment, damage, and target-health resolution for the model to narrate instead of recalculate.
5. `app.llm` builds a JSON-only draft prompt from `app.prompts` and the current world context without reducing narration-depth targets.
6. The cleaned draft is scored by the verification policy; deterministic checks and matching `verification_memory` rows can skip or narrow the second verifier pass.
7. The draft response is checked by a second verifier prompt when remaining checks or blockers require it.
8. JSON is parsed, repaired through a JSON-only repair pass if necessary, and normalized.
9. Context-overflow errors are retried with compact prompt context and smaller completion caps before deterministic fallback is used.
10. `app.world.apply_turn` resolves band amounts into rolled numbers and repairs a missing `MOVE` on travel turns (`resolve_movement`) *before* taking the rewind snapshot, so both are inside the record rather than applied on top of it.
11. `app.world` applies allowed state changes, deterministic combat damage, clamps risky values, writes journal entries, summaries, hidden GM events, model logs, verification-memory rows, and rewind snapshots.
12. The API returns updated state plus the turn object to the browser; the UI renders narration as continuous prose even when the model returned compatibility paragraph chunks. Continuity telemetry (`dice_rolls`, `movement`, `voice_check`) rides along at the payload top level.
13. If model generation fails in a recoverable way, fallback narration can be returned and marked in the payload.

---

## 10. Migration Notes

| Date | Change | Migration |
|---|---|---|
| 2026-05-16 | Added `verification_memory` table for scoped verifier-check caching | Additive table/index creation through `init_db()`; old saves start with an empty verifier memory cache |
| 2026-05-16 | Added lazy deterministic NPC combat profile columns and mechanics-context combat resolution | Additive `npcs` columns through `init_db()`; old saves import with default zero values until combat initializes them |
| 2026-05-13 | Added backend-only `gm_events` table and removed raw journal rows from generated source-index context | Additive table creation through `init_db()`; source index is regenerated without `memory/journal.jsonl` |
| 2026-05-13 | Created project-specific `CODEBASE_INDEX.md` and `CHANGELOG.md` from starter documentation | No code or data migration required |

---

## 11. Known Issues & Limitations

| Issue | Severity | Notes |
|---|---|---|
| Long local-LLM turns on 8B | Medium | Expect multi-minute turns; use dual-role benchmarks or cloud/agent provider for faster iteration |
| No formal CI or test runner | Medium | Add focused temp-DB backend tests before large schema or turn-application changes |
| ~~9 pre-existing test failures on `test/morkyn-0.9-wip`~~ — resolved | Resolved | All 9 fixed. Four were real defects: a `known` character rewritten into a transmigrated one by first-hit origin classification; `stitch_arrival_keep_former_life` discarding the player's former life; the backstory gate rejecting arrival phrasing its own generator writes; and `abs(hash(text))` seeding, which made every repaired backstory identical and unreproducible. Five were stale assertions updated to current contracts (entity-code injection, the legacy `special_ability_origin` field, lock-after-creation). Suite is now 297 unittest tests + 7 behavior checks, all passing. |
| Default GGUF model path is machine-specific | Low | Override with `AI_RPG_GGUF_MODEL` or choose a model in the UI |
| Runtime data is local-only | Low | `data/` is ignored by git; export/import JSON is the current portability path |
| Quest, faction, and item-tag systems are still broad | Low | README notes these as likely future schema layers; combat now has a first deterministic health/damage layer but not a full tactical engine |