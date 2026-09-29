---
applyTo: "**/*.md"
description: "Documentation rules for AI RPG - CODEBASE_INDEX, CHANGELOG, README, and .github instructions."
---

# Documentation Standards

## CODEBASE_INDEX.md

- Update when project structure, conventions, architecture, API routes, schemas, prompt contracts, launcher behavior, testing strategy, or instruction routing changes.
- Keep it as the source of truth for future contributors and AI agents.
- Reference new instruction files from the index when they are created.
- Keep numbered sections stable where possible; add new sections as the project grows.
- Every module/system listed in the index must include purpose, file paths, key API, consumers/dependencies, and design notes.

## Pattern Documentation

- New convention -> create or update an instruction file in `.github/instructions/` and reference it in `CODEBASE_INDEX.md`.
- Modified convention -> update the instruction file and the matching index section in the same change.
- Instruction files should explain what the pattern is, why it exists, examples, and counter-examples when useful.
- Do not leave important persistence, prompt-contract, route, or UI conventions only in code.

## CHANGELOG.md

- Add an `[Unreleased]` entry for every functional change.
- Skip documentation-only and formatting-only edits unless they materially change contributor workflow or release operation.
- Use Keep a Changelog categories:
  - **Added** - new features, systems, files, endpoints, UI screens
  - **Changed** - modified behavior, APIs, schemas, configs
  - **Fixed** - bug fixes, crash fixes, logic corrections
  - **Removed** - deleted features, deprecated code removal, file deletion
- Use one concise line per change and include the affected system/module name.
- Prefix every functional entry with a project agent ID, such as `- [LLM] Fixed verifier fallback handling - turn generation`.
- When a release is tagged, move `[Unreleased]` entries into a new versioned section with the release version and date.

## README.md

- Keep the README focused on the project name, one-sentence description, quick-start, important environment overrides, and links to deeper docs.
- Avoid duplicating long architecture details already covered in `CODEBASE_INDEX.md`.
- Update the README whenever launch steps, dependencies, default model behavior, or project purpose changes.

## .github Instructions

- Keep `.github/copilot-instructions.md` and `.github/instructions/*.instructions.md` project-specific.
- Do not leave fill-in markers, unrelated technology examples, or generic starter language in committed instruction files.
- If an instruction conflicts with `CODEBASE_INDEX.md`, update both or ask for clarification.

## General

- Keep documentation concise and actionable.
- Prefer concrete repo paths and current function names over abstract examples.
- If a section becomes too long, split it into a focused sub-file and link it from `CODEBASE_INDEX.md`.
