---
description: "Agent routing rules for AI RPG - assign specialist IDs and write changelog attribution."
---

# Agent Routing

## Purpose

Agent IDs keep implementation focus clear and make `CHANGELOG.md` entries easy to scan. Pick the ID that matches the primary domain of the change.

## How To Route

1. Identify the primary module or behavior being changed.
2. Use the project agent table in `.github/copilot-instructions.md`.
3. If the task spans multiple modules, use the ID for the highest-risk or most central change.
4. Add a changelog entry only for functional changes; skip documentation-only and formatting-only edits.

## Agent ID Rules

- IDs are 2-5 uppercase letters.
- IDs are unique and stable once used in `CHANGELOG.md`.
- Add new IDs only when the existing table cannot describe the work.
- When adding an ID, update `.github/copilot-instructions.md`, this file, `CODEBASE_INDEX.md`, and any affected changelog examples.

## Project Agent Table

| Agent | ID | Use When |
|---|---|---|
| **CoreArchitect** | `ARCH` | App wiring, lifecycle, cross-module architecture, route/system integration |
| **BackendDev** | `BE` | FastAPI routes, Pydantic request models, server-side behavior |
| **FrontendDev** | `FE` | `static/` UI behavior, rendering, layout, browser interactions |
| **DataLayer** | `DATA` | SQLite schema, migrations, queries, export/import, source index data |
| **GameplaySystems** | `GPLAY` | Turn rules, RPG mechanics, inventory, skills, abilities, karma, aliases, rewind |
| **LLMIntegrator** | `LLM` | Model config, prompt contracts, JSON repair, verifier flow, fallback generation |
| **GameMasterTools** | `GM` | Hidden GM notes, playtest tools, referee-facing diagnostics |
| **UINavigator** | `UI` | Navigation, setup flow, tabs, forms, modals, accessibility polish |
| **BuildEngineer** | `BILD` | Requirements, launch scripts, local server setup, environment defaults |
| **SecurityAudit** | `SEC` | Input validation, file paths, HTML escaping, secrets, injection risks |
| **DocKeeper** | `DOCS` | CODEBASE_INDEX, CHANGELOG, README, `.github` instructions |
| **TestEngineer** | `TEST` | Test harnesses, mocks, temp runtime paths, regression coverage |
| **FastRefactor** | `RFCT` | Renaming, extracting, moving code, dead-code cleanup |
| **ToolSmith** | `TOOL` | Developer utilities, diagnostics, scripts under `tools/` |
| **LowTokenMode** | `LO` | Small, urgent, low-context changes |

## Changelog Examples

```text
### Added
- [BE] Added POST /api/quests endpoint with Pydantic validation - quest API
- [GPLAY] Added quest state application from verified turn JSON - world engine
- [FE] Added quest cards to the World Bible tab - browser UI

### Fixed
- [DATA] Fixed rewind snapshot restoration for equipped inventory rows - persistence
- [LLM] Fixed malformed JSON repair token cap for expansive narration - model adapter

### Changed
- [BILD] Changed launcher context window default to match local GGUF model settings - startup

### Removed
- [RFCT] Removed obsolete source-index helper after replacement by `search_source_index()` - world search
```
