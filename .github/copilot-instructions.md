# Copilot Workspace Instructions - AI RPG Consistency Prototype

> Mandatory. Execute in order. These instructions apply to this FastAPI + SQLite + plain browser UI RPG prototype.
> Domain-specific rules live in `.github/instructions/` and should be loaded when relevant to the files being changed.

---

## Step 1: Read Priority Context First

1. Read `CODEBASE_INDEX.md` at the workspace root before any work.
2. Read relevant instruction files from `.github/instructions/` for the affected modules.
3. Treat `CODEBASE_INDEX.md` as the source of truth for structure, conventions, architecture, route surface, data formats, and known limitations.
4. Verify against the code before changing behavior.

## Step 2: Understand The Request

1. Read the entire prompt and identify affected files, modules, routes, schemas, prompts, UI surfaces, and runtime data.
2. Cross-reference against `CODEBASE_INDEX.md` and the applicable instruction file.
3. Ask before proceeding only when the request is ambiguous, risky, or conflicts with documented conventions.

## Step 3: Plan Before Coding

1. Outline files to create, modify, or delete.
2. Identify side effects for SQLite state, API contracts, prompt JSON contracts, static UI rendering, launch scripts, and tests.
3. For large or risky changes, propose incremental steps and get confirmation.

## Step 4: After Every Change

1. Update `CODEBASE_INDEX.md` when structure, conventions, architecture, API routes, schemas, prompt contracts, launcher behavior, or instruction routing changes.
2. Update `CHANGELOG.md` under `[Unreleased]` for every functional change. Skip documentation-only and formatting-only edits.
3. Update related consumers, tests, docs, configs, and static UI files in the same change.
4. New convention? Add or update an instruction file in `.github/instructions/` and reference it from `CODEBASE_INDEX.md`.

## Step 5: Validate And Self-Review

- Mentally dry-run the happy path and edge cases.
- Check API/request type alignment, SQLite writes, JSON serialization, frontend rendering, and model fallback paths.
- Confirm errors are explicit, no secrets are introduced, and runtime data in `data/` is not accidentally treated as source.
- Leave the codebase valid, runnable, and internally consistent.

---

## Project Boundaries

- SQLite is the source of truth. LLM narration alone must not define persisted state.
- Keep model output JSON-first and synchronized across `app/prompts.py`, `app/llm.py`, `app/world.py`, and `static/app.js`.
- Use parameterized SQL and `app.db.connect()` for database access.
- Escape player-provided and model-provided text before inserting HTML in `static/app.js`.
- Tests must set temporary `AI_RPG_*` paths **and** re-apply them in `setUpModule()`. Setting them at import time alone is not enough: `unittest` imports every test module before running any test, so the module imported last owns the environment while everyone else's tests run.
- Do not require a real local model for automated tests; patch or mock LLM transport.
- Keep the frontend framework-free unless the project intentionally adopts a build pipeline.

---

## Agent Routing

Specialist agents are identified by short IDs for changelog attribution. Use the primary domain of the change.

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

### Changelog Attribution

Every functional `CHANGELOG.md` entry under `[Unreleased]` must start with one of the IDs above.

```text
- [LLM] Fixed verifier fallback handling when llama.cpp returns malformed JSON - turn generation
- [DATA] Added migration for inventory capacity modifiers - world schema
- [FE] Fixed entity reference insertion in the turn composer - browser UI
```

For multi-domain work, use the primary agent ID and mention the affected areas in one concise line.
