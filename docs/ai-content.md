# Mørkyn for language models

A fast, accurate picture of the project for an LLM (a coding agent, a reviewer, a chat
assistant) before it reads the code. It is a map, not the rules: the standing decisions are in
[CLAUDE.md](../CLAUDE.md) and win over anything here. Kept current with
[CHANGELOG.md](../CHANGELOG.md): the condensed changelog at the end is updated in the same commit
as every changelog entry.

## What Mørkyn is

A local, single-player text RPG. A language model narrates; the game engine decides what is true.
The player types what they do, the model writes the scene, and the engine keeps the facts
(places, people, items, money, dice, quests, health, time) in a SQLite save. It runs on the
player's own computer: a FastAPI server on `127.0.0.1` and a browser page or Mørkyn's own window.
The model is local (a GGUF run in-process through llama-cpp-python, "MLE"), a llama.cpp server, or
a cloud API the player sets up (xAI, OpenAI, OpenAI-compatible). Licence: PolyForm Noncommercial.

Target model today: **Hermes 3 (Llama 3.1 8B, Q4_K_M)**; earlier long runs used Qwen3 8B and
Qwen2.5 7B. Small models are the design constraint: every ask is short and plain, and the engine
does the work a small model gets wrong.

## The one idea to keep in mind

**Narrator, interpreter, engine.** The narrator only describes; it cannot make anything happen.
The interpreter reads the player's line (what was tried) and the finished scene (what happened)
and states the outcome as plain events. The engine checks each event against its records,
applies or refuses it, and owns all math (dice, costs, counts, growth). Prose and state must
agree; when they do not, the fix is, in order: better context for the model, reconcile the state
to reasonable prose, a narrow repair, and only last a gate. Fix by fault class, never by phrasing,
and never by shrinking what the model may write. See CLAUDE.md, "The guiding rule for fixes".

## How a turn runs

1. `static/app.js` posts the player's line to `POST /api/turn` (`app/main.py` `api_turn`).
2. `app/world.py` `play_turn` builds the context (state, the place first, the people here, dead
   people as `dead = 1`, money as `$<units>`), settles what the player's line commits to before the
   draft (attack rolls, payments, hand-overs), and asks for the draft.
3. `app/llm.py` `generate_turn` calls the model. The draft is the NAR+OPS text form
   (`app/turn_dsl.py`): narration plus opcode lines, transcoded to the turn JSON.
4. `app/world.py` `apply_turn` applies the ops, then the readers and checkers reconcile prose and
   state: `app/interpreter.py` (events), `app/prose_state.py` (facts the narration states),
   `app/quest_parser.py` (jobs as offered), `app/unnamed.py` (numbered unnamed people and
   creatures), `app/attack_intent.py` and `app/attack_line.py` (who is attacked; the engine writes
   the result line), `app/skill_checks.py` (dice and checks), `app/narration_pipeline.py`.
5. Everything the engine wrote, refused or swallowed is recorded per turn by `app/turn_ledger.py`
   into `data/model_traces/turn-*.json` (`engine.ledger`), with `timings.jsonl` and
   `requests.jsonl` beside them. Read a turn's trace before reading code when debugging.

## Where things are

| Path | What it is |
| --- | --- |
| `app/main.py` | FastAPI app, every `/api/*` route, `APP_VERSION` |
| `app/world.py` | The engine: state, saves, `play_turn`, `apply_turn`, money, people, places (the largest file; read by section) |
| `app/llm.py` | Model calls, prompts in use, MLE / llama.cpp / cloud adapters, context budgeting |
| `app/prompts.py` | Prompt text |
| `app/setup_composer.py`, `app/starter_logic.py` | New-game setup: the Randomize dependency tree, starting gear |
| `app/tile_world.py`, `app/world_scale.py`, `app/town_grid.py`, `app/town_moves.py` | World map, towns, streets, movement |
| `app/runtime_packs.py`, `app/versions.py`, `app/updates.py`, `app/paths.py` | Packaging: runtime packs (llama-cpp per accelerator), the version picker, update checks, the data/runtime roots |
| `app/user_store.py` | Per-user settings and API keys, outside saves |
| `app/model_catalog.py` | One-click local models |
| `static/index.html`, `static/app.js`, `static/styles.css` | The whole UI (app.js is large; read by section) |
| `static/ui/*.js` | UI modules: interact (folds, peeks, menus), failsafe (model failures), death, frame (window title bar), game_tour, game_bookmarks |
| `static/ui/tokens.css`, `static/ui/skin.css` | Theme tokens and the skin; rules in docs/UI_RULEBOOK.md |
| `morkyn_app.py`, `start.sh`, `Morkyn.bat`, `packaging/` | Launchers and the packaged builds (.exe, .deb, .rpm, AppImage, AUR) |
| `tools/` | Harnesses and probes: `run_suite.py`, `api_bridge_playtest.py`, `harness_with_packs.py`, `playtest_setup_presets.py`, `make_debug_save.py`, `timing_report.py` |
| `tests/` | ~5000 unittest tests; no `__init__.py` |
| `docs/` | Design docs (NarrationPipeline, TurnDsl, SkillChecks, Packaging, UI_RULEBOOK, ...), the playtest issue log, run findings in `docs/showcase/` |
| `data/` | The live save and traces. Never touched by tests, probes or servers started for testing |

## Working on it

- **Run:** `./start.sh --no-update` (Linux) serves on port 8000 and opens the browser.
- **Test:** `.venv/bin/python tools/run_suite.py --tmp <scratch folder> --out <file>`. There are
  known failures (14 on Linux); the list is kept on the maintainer's machine (a local Claude Code
  skill, not in the repo). Anything else is new.
- **Isolated data:** a server started for a test uses
  `tools/playtest_setup_presets.isolated_data_env(dir)`, never the live `data/`.
- **Line endings are mixed** (some files CRLF, some LF; list in CLAUDE.md). Edit in a way that keeps
  each file's own endings.
- **Database blocks** are `with connect().closing() as conn:`; a bare `with connect()` leaks.
- **Prompts:** prefer no new prompt text; keep every ask short, one question, no fixed examples
  (small models copy them). A fault the model keeps making means the task is too hard: make it
  simpler or move it to the engine.
- **Versions:** the current line is 0.11.x; entries go under `## [Unreleased]` in CHANGELOG.md.
  Push, tag and release only on the owner's explicit ask.
- **Privacy:** no analytics or telemetry. The only automatic outside calls are updates from
  GitHub (version checks and downloads, a packaged build's first engine pack, `start.sh`'s launch
  check). Downloads and cloud services happen only when the player sets them up. Keep it so.

## Condensed changelog

Newest first. One line per release; the full record is CHANGELOG.md.

**Unreleased (next: 0.11.4)**
- New-game settings are tabs (Primary, Identity, Powers, World, People, Rules, Checks & Dice,
  Character art) with Back/Next, and a settings search (labels, field values, dropdown options;
  live after three characters or on Enter, at most every 0.5 s; results editable in place; a
  "Localized tab search" toggle).
- Presets are a window left of the settings window, opened from a bookmark on its edge; locked
  settings are listed and editable under the preset; narrow windows use » / « edge handles and
  return to the same spot.
- Text boxes grow to fill a tab's empty space; the preset Idea box is five lines and grows with
  its text.
- A short in-game tour; play-screen bookmarks (slide a handle out for the Character window) on
  narrow and touch screens; tours show the steps the device has.
- A "JavaScript is required" screen that states the privacy facts and lists every script.
- Fixes: setup boxes no longer lose spaces or letters while typing; a large character image no
  longer stops setup; section help text keeps a readable width.

**0.11.3 (2026-10-28)** The Windows NVIDIA (CUDA) pack carries the CUDA runtime and cuBLAS and
loads them first, so it works on a PC with only the graphics driver.

**0.11.2 (2026-10-27)** Money is a currency set per world (copper/silver/gold by default) held as
one number the engine owns, moved only by sums the scene states. Jobs filed as said, creatures
shown in prose are filed and take the blow, and the holes an adversarial "cheat" run found are
closed in the engine (declared moves, one-sided trades, declared blows, claimed powers and kills,
codes as items, code travel). Context budgeting follows the model really loaded.

**0.11.1 (2026-10-24)** First 0.11 build on GitHub. Unnamed people and creatures numbered per kind
(Ghoul 1, Ghoul 2), plural groups rolled to a count, the dead as a 0/1 state leaving a body, the
narrator told the player's place first, one roll decides an attack, rewind fixes, Linux window and
terminal fixes.

**0.11.0 (2026-10-23)** People pencilled in until a later turn brings them back, places with
insides, jobs filed as said with an engine pay ledger, acts read from grammar; per-user encrypted
settings; Linux packages and the game's own Linux window.

**0.10.0-dev.15 (2026-10-22)** First packaged build: a small exe, llama-cpp-python split into
runtime packs per accelerator, a version picker; persuasion difficulty follows what is asked.

**0.10.0-dev.12 to dev.14 (2026-10-13 to 10-18)** The Saltmarrow test world replayed on local
models (Qwen2.5 7B, Qwen3 8B), close to 200 runs, each fault fixed by class (540 fixes):
places, people, jobs by reference (`@Q1`), gold and items only on evidence, the player's words kept
theirs, a database connection leak closed.

**0.10.0-dev.1 to dev.11 (2026-08-29 to 10-13)** MLE in-process model, wilderness grid, encounters,
quests, party, NPC psychology, the town grid, Mørkyn's own window, engine-computed ability growth,
a death screen and Ironman, read-aloud narration, and playtest fixes #1-#99.

**0.9.x (2026-07-26 to 08-28)** The 0.9 line: beta, the 0.9.0 release (UI remodel, themes,
responsive layouts) and two hotfixes from the first external playtest.

**0.6.0 to 0.8.0 (2026-05-13 to 07-19)** First public pre-1.0 release, the rebrand to Mørkyn,
long-play memory tools, campaign slots, combat handoff.

**0.1.0 (2026-05-13)** First tracked release of the local AI RPG prototype.
