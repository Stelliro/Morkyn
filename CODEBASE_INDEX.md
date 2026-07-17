# CODEBASE INDEX - Mørkyn

> Single source of truth for project structure, conventions, and architecture.
> Last updated: 2026-07-17 (Mørkyn rebrand, hierarchical memory consolidation, token budget guard, campaign slots, context-health UI, Media/ brand assets, 0.7.0)

> Use this file before making architecture, schema, API, prompt-contract, launcher, or major UI changes. Update it whenever those facts change.

---

## 1. Project Overview

**Mørkyn** (formerly AI RPG Consistency Prototype) - an endless local-browser RPG where a local LLM narrates turns and proposes structured world changes while SQLite remains the source of truth.

- **Type:** Local web app / game prototype
- **Primary Languages:** Python, JavaScript, HTML, CSS
- **Key Frameworks / Libraries:** FastAPI, Pydantic, SQLite, Uvicorn, llama-cpp-python server, Ollama-compatible APIs
- **Target Platforms:** Windows local development, browser UI at localhost or trusted local-network phone/tablet browsers
- **Current Version:** 0.7.0
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
Mørkyn/  (repo folder may still be named "AI RPG" locally)
|-- .github/
|   |-- copilot-instructions.md
|   `-- instructions/
|-- app/
|   |-- __init__.py
|   |-- db.py                        # SQLite connection, schema, migrations
|   |-- llm.py                       # Model config, JSON chat, token budget, traces, fallbacks
|   |-- main.py                      # FastAPI routes (turns, slots, diagnostics, model)
|   |-- prompts.py                   # System/verifier prompts + agentic CoD steps
|   `-- world.py                     # State, planner, memory consolidation, slots, index
|-- data/                            # Runtime only (gitignored): world.db, source_index, slots, traces
|-- Media/                           # Brand assets (logo, key art)
|-- static/
|   |-- app.js
|   |-- index.html
|   `-- styles.css
|-- tools/
|-- behavior_test.py                 # Regression suite for memory/token/slots scoring
|-- README.md
|-- LICENSE.md
|-- requirements.txt
|-- start_ai_rpg.bat
|-- start_ai_rpg.ps1
|-- CODEBASE_INDEX.md
`-- CHANGELOG.md
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
- **Design Notes:** `data/world.db` is the default source of truth. Player setup identity columns include `age`, `sex`, `previous_life_age`, and `previous_life_sex` as additive text migrations. Tests should set `AI_RPG_DB` before importing `app.db` or `app.world` to avoid touching real play data.

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
- **Design Notes:** LLM output is JSON-first. Turn generation consumes the focused turn planner packet, runs deterministic handoff cleanup before the draft, performs a draft pass, cleans the draft payload before verification, validates usable narration, scores a selective verification policy, then either skips the model verifier for high-certainty low-risk drafts or runs the verifier focused on remaining checks. The policy treats matching `verification_memory` rows as already-cleared checks when their confidence meets `AI_RPG_VERIFY_MEMORY_CERTAINTY` (default 0.86), so repeated verified facts can make later matching turns draft-only when no risky state changes are present. The policy only skips when the draft has enough narration, valid entity references, a sane scene-plan shape, a passing self-check, no high-risk state changes, and all planner verification checks have been deterministically or previously cleared; `AI_RPG_FAST_VERIFICATION` toggles this path and `AI_RPG_VERIFY_SKIP_CERTAINTY` sets the default 0.88 skip threshold. Verified payloads are cleaned again before world application, and valid turns below the 1000-character narration floor get one depth retry before returning. Normal turn narration targets about 1500 visible characters and stays below 2400 characters / 700 words; deterministic fallback turns follow the same depth expectation. Context-overflow failures trigger compact turn-context retries before deterministic fallback narration. llama.cpp turn draft/verify timeouts are phase-specific through `AI_RPG_TURN_DRAFT_TIMEOUT` and `AI_RPG_TURN_VERIFY_TIMEOUT`, with longer local defaults for slow first-scene generation; setup randomization and suggestions use `AI_RPG_SETUP_RANDOMIZER_TIMEOUT` and `AI_RPG_SUGGESTION_TIMEOUT`. Input suggestions are clipped near 100 visible characters, with a 120-character maximum. Each turn writes a JSON trace file under `AI_RPG_MODEL_TRACE_DIR` (default `data/model_traces`) containing focused prompt context, deterministic handoff cleanup records, prompts, raw model outputs, parsed JSON, verification-memory hits, verification-policy scores, verifier/self-check data, timing/error records, fallback decisions, and the final turn payload; `AI_RPG_MODEL_TRACE_KEEP` limits retained files and `AI_RPG_TRACE_VALUE_LIMIT` caps individual string values. These traces capture observable model artifacts, not hidden chain-of-thought the model never returned. Model settings default to the llama.cpp-compatible provider unless `AI_RPG_MODEL_PROVIDER=ollama` or the UI explicitly selects Ollama. They store a soft response token target (`response_token_cap`, default 1500) and a hard response token cap (`response_token_hard_cap`, default 2000); repair calls use at least the soft target while all response requests are clamped by the hard cap and remaining context. No machine-specific GGUF path is embedded in defaults; set `AI_RPG_GGUF_MODEL` or use the Model settings UI to choose a local model. `/api/model-status` checks the configured provider and, for llama.cpp with a saved GGUF path, starts a managed `llama_cpp.server` process when the configured `/v1/models` endpoint is refused. Generation requests to llama.cpp also start the managed server and retry once when `/v1/chat/completions` or `/v1/completions` is refused, so setup/opening generation does not depend on pressing Test first. Timeout errors include the failed phase, timeout seconds, approximate prompt tokens, configured soft response target, configured repair cap, and configured hard cap so caps are not mistaken for actual token usage. Refused model-server connections are classified as transport failures, skip generic draft retry, and state that no model response was generated and no token cap was hit. When deterministic fallback is used, any collected model usage rows are still written to `model_logs` for later diagnosis. Turn normalization accepts common narration/segment aliases, hidden `gm_events`, and reuses valid draft narration when the verifier omits it. Malformed JSON repair uses a larger repair token budget so full turn objects are less likely to fall through to deterministic fallback; if draft JSON repair still times out but the raw draft contains readable narration, the adapter recovers narration only, ignores unparseable state changes, and continues through verification instead of immediately using deterministic fallback. Setup randomization includes current age/sex and previous-life age/sex, normalizes `custom_skills` into comma-separated phrases so AI-filled Custom Proficiencies match the setup UI contract, and falls back to deterministic backend values when model output is unavailable or invalid.

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

- **Files:** `start_ai_rpg.ps1`, `start_ai_rpg.bat`
- **Purpose:** Start the local app, install missing Python dependencies, optionally start a managed llama.cpp server, and open the browser.
- **Key API:** Environment overrides documented in `README.md`.
- **Consumers:** Windows local users.
- **Dependencies:** Python, requirements from `requirements.txt`, optional local GGUF model.
- **Design Notes:** The launcher uses `AI_RPG_GGUF_MODEL` when a managed llama.cpp server should start, and when that env var is absent it reuses a saved `model_config.gguf_model_path` from SQLite on the next launch. Without a configured GGUF path, it still starts the browser app but warns that no managed llama.cpp server will start; the user must start Ollama/llama.cpp separately or generation will use deterministic fallback. The batch launcher prompts for this-machine-only mode, local-network/phone mode, or VPN/private-overlay mode. The PowerShell launcher binds FastAPI to `AI_RPG_APP_HOST`/`AI_RPG_APP_PORT`, defaulting to `127.0.0.1:8000`; local-network mode sets `AI_RPG_APP_HOST=0.0.0.0`, prints the local PC URL, prefers a Wi-Fi/Ethernet RFC1918 IPv4 URL for phones, and lists other detected local URLs when VPN or virtual adapters are present. VPN mode also binds FastAPI to `0.0.0.0`, prompts for an app port from the batch launcher when one is not set, and prefers adapter URLs whose interface names look like Tailscale, WireGuard, ZeroTier, ProtonVPN, OpenVPN, TAP/TUN, Hamachi, or Radmin. The managed llama.cpp server remains loopback by default through `AI_RPG_LLM_HOST=127.0.0.1`. The PowerShell launcher waits for the configured llama.cpp server to answer `/v1/models` before starting the browser app; `AI_RPG_LLM_STARTUP_TIMEOUT` controls the wait limit. Managed llama.cpp stdout/stderr are written to temp log files by default so compatibility probes such as `/api/version` do not clutter the app terminal; set `AI_RPG_LLM_LOG_MODE=console` to show raw llama.cpp logs.

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
| Test Runner | Ad hoc Python script | `behavior_test.py` | Currently stale/experimental; prefer focused temp-DB tests |
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
- For isolated tests, set `AI_RPG_DB`, `AI_RPG_SOURCE_INDEX`, and `AI_RPG_HISTORY_SUMMARY` before importing `app.db` or `app.world`.
- Patch or mock LLM calls for deterministic tests; do not require a real model for normal automated checks.
- Avoid touching `data/world.db` or `data/history_summaries.jsonl` during tests.
- `behavior_test.py` appears to reference older names such as `gameState`, `call_llm_structured`, and `apply_karma_change`; update or replace it before relying on it as a regression suite.

### Commit Style
- Prefer Conventional Commits where practical: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.
- Update `CHANGELOG.md` for functional user-facing changes, schema changes, route changes, and significant behavior changes.

---

## 5. Key Design Documents

| Document | Location | Description |
|---|---|---|
| README | `README.md` | User-facing overview, launch instructions, environment overrides, and design notes |
| Codebase Index | `CODEBASE_INDEX.md` | Project structure, conventions, API surface, data model, and known limitations |
| Changelog | `CHANGELOG.md` | Keep a Changelog history for releases and unreleased changes |
| Environment Example | `.env.example` | Optional local defaults for model and database settings |
| Copilot Workspace Instructions | `.github/copilot-instructions.md` | Required AI workflow, project boundaries, and agent ID table |
| Documentation Instructions | `.github/instructions/documentation.instructions.md` | Rules for CODEBASE_INDEX, CHANGELOG, README, and instruction docs |
| Agent Routing Instructions | `.github/instructions/agent-routing.instructions.md` | Agent ID selection and changelog attribution examples |
| Feature Pipeline Instructions | `.github/instructions/feature-pipeline.instructions.md` | Checklist for significant features, schema, prompt, UI, and launcher changes |
| Implementation Standards | `.github/instructions/implementation-standards.instructions.md` | Security, compatibility, testing, and performance standards |

---

## 6. Build & Run Instructions

### Prerequisites
- Python available as `python`, `py -3`, or the local Python 3.12 path checked by `start_ai_rpg.ps1`.
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
.\start_ai_rpg.ps1
```

Batch wrapper:

```text
start_ai_rpg.bat
```

The batch wrapper prompts for local-only or local-network/phone mode. It also accepts quick arguments:

```text
start_ai_rpg.bat local
start_ai_rpg.bat lan
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
$env:AI_RPG_LLAMA_CPP_CONTEXT="8192"
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

`behavior_test.py` exists, but it should be treated as legacy until updated against the current schema and function names.

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
10. `app.world` applies allowed state changes, deterministic combat damage, clamps risky values, writes journal entries, summaries, hidden GM events, model logs, verification-memory rows, and rewind snapshots.
11. The API returns updated state plus the turn object to the browser; the UI renders narration as continuous prose even when the model returned compatibility paragraph chunks.
12. If model generation fails in a recoverable way, fallback narration can be returned and marked in the payload.

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
| `behavior_test.py` appears stale | Medium | It references older schema/function names and should be rewritten before relying on automated behavior coverage |
| No formal CI or test runner | Medium | Add focused temp-DB backend tests before large schema or turn-application changes |
| Default GGUF model path is machine-specific | Low | Override with `AI_RPG_GGUF_MODEL` or choose a model in the UI |
| Runtime data is local-only | Low | `data/` is ignored by git; export/import JSON is the current portability path |
| Quest, faction, and item-tag systems are still broad | Low | README notes these as likely future schema layers; combat now has a first deterministic health/damage layer but not a full tactical engine |