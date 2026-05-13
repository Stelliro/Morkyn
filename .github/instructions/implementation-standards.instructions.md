---
description: "AI RPG implementation standards - security, compatibility, code quality, validation, testing, and performance."
---

# Implementation Standards

## Security

- Do not commit secrets, API keys, private tokens, or personal credentials.
- Treat local model paths as configuration. Prefer environment variables or UI configuration over hard-coded machine-specific paths when changing defaults.
- Validate external input at the boundary with Pydantic models, explicit length limits, and type constraints.
- Use parameterized SQLite queries. Do not build SQL from raw user or model text.
- Escape player-provided and model-provided text before inserting it into HTML.
- Do not use `eval()` or dynamic code execution for model responses.
- Normalize and constrain file paths before reading or writing local files.
- If CORS or external hosting is added later, restrict origins explicitly and document the deployment change.

## Backward Compatibility

- Preserve API route names and response shapes unless the change is intentionally breaking.
- Preserve export/import format `ai-rpg-world-v1` or provide a migration path.
- Preserve rewind snapshot format `ai-rpg-delta-v1` or provide a migration path.
- Preserve existing SQLite data with additive migrations whenever possible.
- Never silently change the meaning of a prompt JSON field, setting key, entity code, or saved table column.

## Code Quality

- Keep route handlers in `app/main.py` thin; put domain behavior in `app.world` or model behavior in `app.llm`.
- Keep schema and migration work in `app/db.py`.
- Keep prompt contracts in `app/prompts.py` and synchronize consumers in the same change.
- Keep browser state and rendering in `static/app.js`; keep styling in `static/styles.css`.
- Prefer clear functions and existing helpers over broad abstractions.
- Remove dead code or document why it remains.
- Use names that match `CODEBASE_INDEX.md` conventions.
- Replace repeated magic strings with constants when they represent routes, formats, table lists, or model phases.

## Dependency Management

- Prefer dependencies already in `requirements.txt` and the Python standard library.
- Pin new Python dependencies for reproducible installs.
- Justify any new dependency by maintenance status, license, and the complexity it removes.
- Do not add a frontend build tool or framework without updating launch, docs, and architecture notes.

## Validation

- Trace the happy path and at least two edge cases before declaring work complete.
- Check empty values, missing optional fields, maximum text lengths, invalid entity references, model timeouts, malformed JSON, and import/export mismatches.
- Verify type alignment across Pydantic models, JSON payloads, SQLite rows, and UI renderers.
- Keep retryable or repeatable operations idempotent where practical, especially migrations and launcher checks.
- The codebase must remain runnable after every change.

## Testing

- New features should include focused tests when a reliable harness exists.
- Bug fixes should include regression coverage when practical.
- Tests must set temporary `AI_RPG_DB`, `AI_RPG_HISTORY_SUMMARY`, and `AI_RPG_SOURCE_INDEX` paths before importing `app.db` or `app.world`.
- Mock LLM transport and file pickers in automated tests.
- Do not rely on `behavior_test.py` as authoritative until it is rewritten for the current schema and function names.

## Performance

- Keep prompt context bounded; avoid unbounded history, source-index, or relationship scans in hot turn paths.
- Preserve deterministic LLM handoff cleanup stages between planner context, draft JSON, verifier JSON, and world application; new turn-generation paths should either reuse those cleanup helpers or document why they bypass them.
- Prefer targeted SQLite queries over loading and filtering large tables when data grows.
- Avoid blocking or long-running browser operations on the main interaction path.
- Document performance-sensitive paths in `CODEBASE_INDEX.md` when adding them.
