---
description: "AI RPG feature pipeline - use for new game systems, API routes, prompt contracts, UI features, schema changes, and launch tooling."
---

# Feature Pipeline

Use this pipeline for new features, significant behavior changes, schema changes, prompt-contract changes, and cross-module refactors. Small one-file fixes can be concise, but the same checks still apply.

## 1. Context Loaded

- Read `CODEBASE_INDEX.md` first.
- Read applicable instructions from `.github/instructions/`.
- Read the affected source files before planning changes.

Example: `CODEBASE_INDEX.md` sections 2, 4, 7, 8, and 9 plus `app/main.py`, `app/world.py`, `app/prompts.py`, and `static/app.js` for a new turn action contract.

## 2. Architecture Impact

- List affected layers: FastAPI route, Pydantic request model, SQLite schema, world application logic, LLM prompt contract, static UI renderer, launcher, tests, docs.
- Identify whether the change affects export/import format `ai-rpg-world-v1` or rewind snapshot format `ai-rpg-delta-v1`.

## 3. Pattern Match

- Reuse the closest existing flow.
- For routes, mirror existing handlers in `app/main.py`.
- For state changes, mirror existing apply/upsert helpers in `app/world.py`.
- For LLM output, mirror the JSON contract in `app/prompts.py` and normalization in `app/llm.py`.
- For UI, mirror existing render functions and fetch helpers in `static/app.js`.

## 4. Files To Change

- List exact files to create, modify, or delete.
- Include docs and tests when applicable.

Example:

```text
Modify: app/main.py
Modify: app/world.py
Modify: app/prompts.py
Modify: static/app.js
Modify: static/styles.css
Modify: CODEBASE_INDEX.md
Modify: CHANGELOG.md
Create: tests/test_quests.py
Delete: none
```

## 5. Detailed Plan

- Describe the data flow from browser input to FastAPI, world logic, model prompt, SQLite persistence, and returned state.
- Name new request models, functions, table columns, JSON fields, constants, and render functions.
- Call out compatibility decisions and migration needs.

## 6. Implementation

- Keep changes focused and consistent with existing patterns.
- Preserve existing runtime data unless the user explicitly requests a reset or migration.
- Update all consumers of changed state shapes in the same pass.

## 7. Documentation Update

- Update `CODEBASE_INDEX.md` for structure, architecture, route, schema, prompt-contract, launcher, testing, or instruction changes.
- Update `CHANGELOG.md` under `[Unreleased]` for functional changes only.
- Update `README.md` when quick-start, dependency, or user-facing behavior changes.

## 8. Self-Review Checklist

- [ ] Follows documented architecture and module boundaries.
- [ ] Uses parameterized SQL and `app.db.connect()` for database work.
- [ ] Validates input at the FastAPI/Pydantic boundary.
- [ ] Escapes player-provided and model-provided text before HTML insertion.
- [ ] Keeps prompt JSON contracts synchronized across prompts, LLM normalization, world application, and UI rendering.
- [ ] Preserves export/import and rewind compatibility or documents a migration.
- [ ] Avoids touching runtime `data/` files unless explicitly required.
- [ ] Tests use temporary DB/history/source-index paths and mock LLM transport.
- [ ] Docs and changelog rules were followed.

## 9. Validation

- Run the narrowest meaningful automated check when available.
- If no reliable test exists, do a mental dry-run of the happy path and at least two edge cases.
- For UI changes, verify loading, empty, error, and populated states.
- For model changes, verify malformed JSON, timeout/fallback, and verifier-failure paths.

---

## Sub-Pipelines

### New FastAPI Route

- Add or update a Pydantic request model in `app/main.py`.
- Add the route with explicit error handling.
- Delegate domain behavior to `app.world` or `app.llm`; keep route handlers thin.
- Update `static/app.js` fetch logic if the browser consumes it.
- Update the API route table in `CODEBASE_INDEX.md`.

### New World Or Gameplay System

- Add persistence through SQLite if the state must survive turns.
- Add setup defaults, turn application rules, export/import handling, rewind snapshot behavior, and UI rendering where needed.
- Clamp or validate model-proposed values before persistence.
- Add a temp-DB test or document why a test is not currently possible.

### LLM Prompt Contract Change

- Update `app/prompts.py` JSON shape and rules.
- Update `app/llm.py` normalization or fallback behavior if needed.
- Update `app/world.py` application logic and validation.
- Update `static/app.js` renderers for any returned state or narration changes.
- Test malformed JSON and missing-field behavior mentally or with mocks.

### SQLite Schema Change

- Add table/column creation in `app/db.py`.
- Add additive migration logic for existing databases.
- Update `WORLD_TABLES`, export/import, rewind snapshots, and state queries when applicable.
- Update `CODEBASE_INDEX.md` data model notes.

### Static UI Feature

- Keep it framework-free and served from `static/`.
- Use existing render helpers, escaping helpers, and fetch patterns.
- Handle loading, empty, error, and populated states.
- Keep CSS responsive and avoid layout shifts in repeated controls.

### Launcher Or Tooling Change

- Keep Windows launcher behavior explicit and reversible.
- Prefer environment overrides over hard-coded local assumptions.
- Update `README.md` and `CODEBASE_INDEX.md` when commands or defaults change.
