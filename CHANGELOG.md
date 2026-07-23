# Changelog

All notable changes to **Mørkyn** (formerly Mørkyn) are documented here.

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

### Version Number Guide
- **MAJOR** (`x.0.0`) - Breaking changes to public APIs or saved data formats
- **MINOR** (`0.x.0`) - New features, backward-compatible
- **PATCH** (`0.0.x`) - Bug fixes, backward-compatible

### Entry Format

```text
- [AGENT_ID] Description of change - module/system name included
```

---

## [Unreleased]

> Future changes after `0.8.0` live here.

### Added
- [FE] Per-turn collapsed **Debug** panel (expand, copy summary/JSON/path, view full trace file via `GET /api/debug-trace`)
- [BE] Always write model traces under `data/model_traces/`; each turn response includes compact `debug` bundle + `debug_trace_path`
- [RULES] Optional **dice / skill checks** system: setup tab **5 Checks**, d6–d100, events/encounters, specialized-skill partial salvage, negative outcomes
- [RULES] Durable skill library (`data/skill_library.json`) with similarity adjust on new skills; catalog enable/disable
- [API] `/api/skill-checks/catalog|resolve|register|enable` + GM `skill_check_context` in prompt packet
- [DOCS] `docs/SkillChecks.md`
- [RULES] Contested DCs from enemy/object power + power RNG; degree flavor (“just barely”, “as if you did nothing”); unskilled weapon mishaps with lasting injuries
- [FE] Roll banners under narration; color map canvas + auto-generate; play-side mini-map
- [MAP] Fix empty ASCII preview when grid omitted from stored tiles

---

## [0.8.0] - 2026-07-19

### Added
- [FE] Calmer setup UI remodel — softer surfaces, pill controls, dim secondary buttons, corner decals, ambient background; playstyle themes (Dusk / Ember / Tide / Bloom / Ash)
- [FE] Responsive layouts: phone / tablet / desktop / wide (≥1500px step rail + side-by-side play)
- [MAP] Flat tile world v1: multi-age presets, elev 0/1 mountains, tile image archive + Forge/Comfy generate
- [IMG] Optional Forge/A1111 + ComfyUI image backends; portrait preview API
- [BILD] `Morkyn.bat` / `Morkyn.ps1` launcher (simple menu + Advanced Gatehouse); console mouse/keyboard polish
- [LLM] Cloud/agent OpenAI-compatible provider; agent bridge routes; narration pipeline quality hardens (no mid-word shreds)
- [BE] Live `GET /api/generation-progress` for splash/turn wait (phase lines + partial narration)
- [PRIV] Local-only privacy policy + optional GitHub-only updates/rollback
- [DOCS] Showcase: dual-role **100-turn** Mosswake lore teaser (`docs/showcase/`)
- [TOOLS] `benchmarks/run_dual_role_playtest.py` regenerates showcase metrics/markdown
- [FE] Release UI hides self-check / debug-trace panels (opt-in `?debug=1` or `AI_RPG_DEBUG=1`)

### Changed
- [BE] Model trace files and `debug_trace_path` are **off** unless `AI_RPG_DEBUG=1`
- [REPO] Housekeeping: root launchers/docs, `tests/`, `benchmarks/`, expanded `.gitignore`
- [VER] App version **0.8.0**

### Fixed
- [LLM] Narration pipeline no longer accepts truncated mid-word paragraphs or delete-span garbage fragments
- [BILD] Advanced menu click coordinate / jitter issues (raw INPUT_RECORD + no-scroll window size)

---

## Earlier (0.7.x summary)

Notes from the 0.7 line retained for history:

- [LLM] NAR+OPS draft DSL, adaptive narration pipeline design, Ollama `think: false`
- [DOCS] Turn metrics, ConnectAPIs, pipeline docs

### Changed
- [LLM] `generate_turn` prefers DSL draft then optional verify; depth retries only when narration is short
- [DOCS] Repository layout housekeeping: start scripts and project docs stay at root; tests → `tests/`; harnesses → `benchmarks/`; LICENSE copyright updated to Mørkyn / Stelliro
- [BILD] Launcher interactive input hardened so keyboard always works; mouse click path is best-effort without killing the menu

### Removed
- [DOCS] Transient local diagnostics (`temp_*`, empty `*_check.txt`, one-off `tools/write_readme.py` / branding fix scripts)
- [TOOLS] Renamed/removed `GROK BENCHMARK/` space-named folder in favor of `benchmarks/`

---

## [0.7.0] - 2026-07-17

> Rebrand to **Mørkyn**, long-play memory/token tools, campaign slots, combat handoff, verification memory, and UI polish.

### Added
- [BRAND] Rebranded product name, UI titles, API metadata, launchers, and documentation to **Mørkyn**
- [DOCS] Added `Media/` brand gallery (logo + key art) referenced from README
- [MEM] Hierarchical memory consolidation (`consolidate_memory`) into durable source-index facts
- [LLM] Pre-call `enforce_token_budget()` estimation and pruning
- [LLM] SQLite-backed verification memory and certainty-based selective verifier skipping
- [GPLAY] Deterministic NPC combat profiles and player-attack damage handoff before narration
- [GM] Lightweight deterministic off-screen GM event ticks (no extra LLM call)
- [BE] Named campaign save slots under `data/campaign_slots/` with list/save/load/delete APIs
- [FE] Context-health card, consolidate control, compact mode, campaign slot buttons
- [LLM] Managed llama.cpp startup from Model Settings test flow; per-turn model trace exports
- [FE] Startup heartbeat and turn wait timers for long local-model operations
- [TEST] Runnable `behavior_test.py` regression suite

### Changed
- [BE] App version metadata `V0.7.0`
- [LLM] Source-index scoring: keyword fit + recency + importance
- [LLM] Explicit agentic Observe ΓåÆ Plan GM events ΓåÆ Scene plan ΓåÆ Narrate ΓåÆ Self-check chain
- [FE] Model Settings exposes provider/URL fields; Soft Token Target naming
- [LLM] Handoff cleanup between planner, draft, verifier, and world application
- [SEC] Ignore rules exclude local saves, DB sidecars, traces, env variants, model binaries

### Fixed
- [LLM] Draft repair timeouts salvage narration instead of immediate fallback
- [FE] Fallback notices no longer claim missing narration when fallback prose exists
- [LLM] Refused model-server connections reported accurately
- [BILD] Launcher reuses saved GGUF paths on next launch
- [LLM] Default provider alignment and managed llama.cpp startup/status initialization
- [LLM] Setup/turn auto-start + retry when llama.cpp is not yet listening

---

## [0.6.0] - 2026-05-13

> Public pre-1.0 release. This is a featureful local prototype with durable state, focused LLM context, LAN/VPN launch options, regeneration, hidden GM context, setup persistence, and equipment-derived capabilities.

### Added
- [DOCS] Added a strict non-commercial license reference allowing non-commercial forks and modified uploads - licensing
- [GPLAY] Added equipped-item stat modifiers and item-granted abilities that derive into player stats and abilities only while equipped - equipment effects
- [LLM] Added action-specific context segments and focused player capability slices for movement, combat, abilities, and other turn intents - turn generation
- [FE] Added high-visibility turn reward banners for applied XP and item gains - browser UI
- [BILD] Added a VPN/private-overlay launch mode with port selection and VPN URL detection - startup
- [GPLAY] Added current and previous-life age/sex fields to character creation - setup identity
- [BILD] Added local-only and local-network launch modes for phone access - startup
- [FE] Added responsive phone, landscape mobile, and small-monitor layout rules - browser UI
- [GM] Added backend-only hidden GM events for between-turn consequences and off-screen reactions - hidden world context
- [FE] Added paged, collapsed visual history with persisted expansion choices - browser UI
- [UI] Added full-page start splash with progress lines and animated opening narration reveal - setup flow
- [FE] Added compact scene plan readout for high-level model focus points after generated turns - browser UI
- [GPLAY] Added event lifecycle metadata for temporary, recurring, traveling, background, and persistent location events - world events
- [LLM] Added deterministic turn context planning to focus prompts by intent, working set, and verifier risk checks - turn generation
- [FE] Added setup settings save/load with comma-separated Custom Proficiencies guidance and normalization - setup UI
- [GPLAY] Added latest-response regeneration for opening, continue, and player turns - turn tools

### Changed
- [BE] Changed app version metadata to `V0.6.0` for the public pre-1.0 release - API surface
- [BILD] Changed launcher and model defaults to avoid machine-specific GGUF paths and rely on `AI_RPG_GGUF_MODEL` or UI model selection - startup
- [DOCS] Reworked README for public release clarity while keeping setup, model, LAN/VPN, data, and license notes concise - documentation
- [LLM] Split response cap and hard cap token settings with editable model controls and larger repair defaults - model settings
- [LLM] Changed turn prompts and source-index generation so raw journal history stays visual-only and model memory uses structured records - prompt context
- [FE] Changed opening narration reveal timing to stay visible longer after setup generation completes - setup flow
- [LLM] Changed turn prompts to request a 1-6 focus point scene plan and continuous prose narration - prompt contract
- [FE] Changed current turn rendering to join model narration chunks into one continuous prose flow - browser UI
- [BILD] Changed managed llama.cpp launcher logs to quiet temp files by default with `AI_RPG_LLM_LOG_MODE=console` opt-in - startup
- [GPLAY] Changed new playthrough setup to stop seeding default player skills and let skills emerge through play or explicit custom rules - setup system
- [DOCS] Made `.github` Copilot instructions project-specific and referenced instruction files in the codebase index - AI workflow

### Fixed
- [BE] Fixed setup 422 responses from null or invalid mobile form values by normalizing setup payloads before validation - setup API
- [BILD] Fixed local-network launcher URL selection to prefer Wi-Fi/Ethernet over VPN or virtual adapter addresses - startup
- [LLM] Fixed local llama.cpp turn fallbacks from slow drafts by raising phase-specific timeouts and logging prompt diagnostics - model adapter
- [LLM] Fixed malformed turn JSON repair using too small a repair token budget before fallback - model adapter
- [LLM] Fixed setup randomizer 503s by returning deterministic backend fallback fields when model setup JSON is invalid or unavailable - setup randomization
- [BILD] Fixed launcher startup race by waiting for llama.cpp readiness before opening the app - startup
- [BE] Fixed `/api/version` health checks by returning local app and planner version metadata - API surface
- [LLM] Fixed the turn planner packet version string to use `V0.1.0` - turn generation
- [LLM] Fixed deterministic fallback when turn JSON contains salvageable or verifier-omitted narration - turn generation
- [LLM] Fixed context-length fallback by raising the managed llama.cpp default context and adding compact turn retries - model adapter

### Removed
- [GM] Removed the visible GM tab while keeping hidden GM context backend-only - browser UI

---

## [0.1.0] - 2026-05-13

> First tracked release. Establishes the current local AI RPG prototype baseline.

### Added
- [ARCH] Established FastAPI backend with plain browser UI served from `/` - app shell
- [DATA] Added SQLite world database with persistent locations, player, NPCs, relationships, inventory, skills, abilities, events, conversations, aliases, karma history, summaries, model logs, journal, settings, and GM notes - world state
- [LLM] Added local LLM integration for Ollama-compatible and llama.cpp-compatible JSON generation - model adapter
- [LLM] Added draft plus verifier turn flow with JSON repair and fallback narration - turn generation
- [GPLAY] Added configurable playthrough setup for character identity, backstory, world style, rules, abilities, economy, magic, tech, quests, NPC density, factions, skills, and progression - setup system
- [GPLAY] Added structured turn application for player stats, karma, skills, inventory, equipment, capacity modifiers, locations, NPCs, relationships, events, conversations, claim checks, and journal entries - world engine
- [DATA] Added stable entity references for NPCs, locations, items, and events with clickable UI references - indexing
- [DATA] Added compact turn summaries, source-index search, active-location relevance, and World Bible summary views - memory retrieval
- [GPLAY] Added player-created entity aliases and player identity aliases with activation and disguise state - alias system
- [GPLAY] Added one-turn rewind using delta snapshots plus export/import through `ai-rpg-world-v1` JSON - persistence tools
- [GM] Added hidden GM notes for model context and a GM tab for playtesting - GM tooling
- [FE] Added setup wizard, current turn view, history and index panes, inventory display, model settings, search, suggestions, rewind controls, import, and export - browser UI
- [BILD] Added Windows launch scripts that install missing dependencies, start a managed llama.cpp server when configured, start Uvicorn, and open the browser - local launcher
- [DOCS] Added README, CODEBASE_INDEX.md, CHANGELOG.md, and environment example documentation - project documentation

---

<!--
  HOW TO USE THIS FILE
  ====================

  1. Every functional code change gets one line under [Unreleased].
  2. Prefix each entry with the responsible agent ID in brackets, such as [ARCH], [FE], [BE], [DATA], [LLM], [GPLAY], [GM], [BILD], [DOCS], or [TEST].
  3. Use the correct category:
       Added   - new feature, system, file, endpoint, screen
       Changed - modified behavior, API, schema, config
       Fixed   - bug fix, crash fix, logic correction
       Removed - deletion, deprecation cleanup
  4. Skip formatting-only churn. Include docs when they change contributor workflow or project operation.
  5. When releasing: rename [Unreleased] to the new version and release date, then add a fresh [Unreleased] above it.
-->
