# Mørkyn: standing decisions, requests and what to expect

Claude Code reads this file at the start of every session in this repo. It records what Stell
(the owner) has decided and asked for, so no session has to rediscover it. When Stell makes a new
standing decision, add it here in the same session (newest decisions go in the section they
belong to, with the date).

## The guiding rule for fixes: middle ground, never limit the LLM (2026-10-13)

"Fix the issue, however we do not want to limit the llm."

- A fix is an *attempt at a middle ground*: the engine keeps its facts straight (state, places,
  people, items, gold, dice) while the model stays free to write, invent and surprise.
- Prefer, in this order:
  1. **Better context and a clearer ask** (ship the fact the model was missing, say what a field
     is for). See "Prompts, not gates" below.
  2. **Reconcile the state to the prose** when the prose is reasonable (adopt the place the prose
     entered, grant the item the prose shows taken), instead of cutting the prose.
  3. **A narrow repair** of one exact bad shape (an op line, a leaked code) that keeps the rest of
     the reply.
  4. Only last, a **gate** that refuses or trims, and only for things that break the game (engine
     text, the player's agency, facts that contradict the state). Never a gate on style or ideas.
- Do not shrink what the model may do to make a bug go away: no banning new places, people,
  items or events because some were bad. Fix how they are matched and recorded.
- **Fix by class, not by phrasing** (2026-10-14): "we should already be fixing by class rather
  than phrasing ... i do not want to bloat the prompting." Name the fault class and fix it at the
  one place it is decided (state change vs prose evidence; where a scene ends; whose words and acts
  are whose; what triggers a check; engine text in prose). A regex for the one phrasing a run
  produced is a last resort and must be called that. Keep prompt additions minimal. Runs 30-43
  added ~35 phrase-level rules that should be folded into these mechanisms.
- The player's own words and choices are theirs. The model must not act, speak or decide for the
  player, but it may describe the world reacting freely.

## Workflow decisions

- **Commit tested work every turn** without asking (2026-10-05). **Push, tag and release only on
  an explicit ask.** Commit messages end with the Co-Authored-By line from the session.
- **Changelog:** entries go under `## [Unreleased]` in CHANGELOG.md. A pushed batch becomes
  `0.10.0-dev.N`: rename the section with date and a `>` summary, set `APP_VERSION` in
  app/main.py, the two README version spots and changelogs/0.10.0-dev.md "Latest", tag
  `v0.10.0-dev.N`, push main and the tag. N only goes up.
- **Playtests: log only.** While Stell is playtesting, log each reported issue in
  docs/PLAYTEST_ISSUES.md (where, what, evidence, first guess at cause) and acknowledge. No fixes
  until Stell says testing is done (2026-10-05).
- **Issue log: no duplicates.** One row per root cause; a recurrence gets a dated "Reopened ..."
  note on the existing row (2026-10-13).
- **Report my own mistakes plainly**, with the facts and what I did instead. Say when something
  is unverified or a test fails.
- **Test runs are watchable live** (2026-10-14). Stell wants to open the game and see each new
  turn as it happens. Start agent-played runs with `tools/api_bridge_playtest.py --viewer-port 8790`
  and give Stell the address (http://127.0.0.1:8790/); the page is read-only and repaints per turn.
  After a run, scratchpad-style `viewer.py <run dir> 8790` can keep serving the finished save.
- **Log everything a bug needs** (2026-10-14): "ensure logging to ensure we can debug all of it",
  and time between turns and setup to first turn must be captured for time estimates. Each turn's
  trace (`data/model_traces/turn-*.json`) has an `engine` block (app/turn_ledger.py): every save
  write with the code that made it, every exception the engine swallowed, refusals as notes, the
  before/after delta, and the timing. `timings.jsonl` (per turn and setup: seconds, model, GPU
  wait, engine, gap since the last turn) and `requests.jsonl` (every POST, setup page included)
  sit beside the traces and are never pruned; `tools/timing_report.py <trace dir>` summarises
  them. New engine code that refuses or drops something calls `turn_ledger.note(...)`.
- **Baseline runs:** a 100-turn 7B run "with no issues" becomes the baseline. Run 5 (2026-10-14,
  docs/showcase/saltmarrow-7b-run5-findings.md) was not one.
- **Iterate until the playtest is complete** (2026-10-14): when a test run turns up issues, keep
  fixing and re-running without waiting to be asked, until the run is clean enough to call a
  baseline; only then hand over for Stell's own playtest. Issues Stell finds after that are
  learning material for the next patch, not failures; log them and fix them the usual way.
  Stell (same day, going to sleep): "go on for as long as it takes for no issues to occur ...
  go past 100 turns": runs may go longer than 100 turns, and the fix/re-run loop continues
  unattended. Still no push, tag or release without an explicit ask.
- **Roadmap:** stable 0.10 first, then 1.0 as an exe or package. Test saves can pile up until
  then; the cleanup and template saves happen at 1.0.

## Design decisions

- **Prompts, not gates, for content fields.** A wrong-kind answer is fixed by changing the ask
  and shipping the context, never by a regex that refuses it.
- **No fixed examples in prompts.** The local models paste them verbatim. Draw 3-5 fresh ones per
  call from large, world-filtered pools; the engine rolls hard values itself.
- **Engine owns the math.** Dice, ability growth, costs and counts are engine-only; repair before
  a gate rather than retrying the model.
- **Rosters:** resolve model text against the roster and its synonyms; mint only on a genuine
  miss; ambiguous matches resolve to nothing.
- **UI comes from the logo** (Media/ key art): black-violet void, one thread of light as a line,
  never a fill, cut-corner shards. Generic dark-fantasy chrome was rejected. Rules in
  docs/UI_RULEBOOK.md.
- **On/off duty** is derived from a per-job shift template plus the world seed, not stored as a
  role ("off-duty guard" is a state, the job is "guard") (#83).

## What to expect

- **Models.** The target is local Qwen3 8B (`D:\morkyn-stage-models\Qwen3-8B-Q4_K_M.gguf`) via
  MLE; `data/mle-models/` holds only Qwen2.5 7B. Check `/api/model-status` → `file` to see which
  GGUF actually loaded. On the RTX 4070 Ti a turn takes about 10-40 s on the 8B and about 15 s on
  the 7B; a retry costs 30-80 s and usually returns nothing better.
- **Typical model faults** (handle them with the guiding rule above): acting or speaking for the
  player, prose and ops disagreeing (moves, places, people, items, gold), stock phrases, codes
  or op text in the prose, voice slipping to first or third person, retry prompts echoed back.
- **The full test suite** (`python -m unittest` in .venv) has 15 known failures as of
  2026-10-14 (batch5 x2, live_smoke_places, prompt_context_reachability cited keys, quest_live,
  quest_parser x2, quest_pipeline, skill_roster, town_ui x4, and the test_bare_assert_files and
  test_tts loader errors). Anything beyond those is new, except the known flake
  `test_dice_rolls_mirror_applied_turns.test_the_check_is_in_the_dice_audit_for_its_turn`, which
  sometimes fails in the full run and passes alone (seen 2026-10-14 twice).
- **Evidence lives in model traces** (`data/model_traces/turn-*.json`): read them before the code.
  The model side is in `model_trace`; what the engine did is in `engine.ledger` (`delta` first,
  then `writes[i].at` for the code, `swallowed` for hidden failures).
- **Running the suite:** `.venv\Scripts\python.exe tools\run_suite.py [--out FILE]` (2026-10-14).
  It runs `unittest discover` in tests/ (no `__init__.py`, so a bare `-m unittest` from the root
  finds 0 tests) with TEMP pointed at `<drive>:\morkyn-suite-tmp` and deletes that folder after.
  Test modules never remove their `mkdtemp` dirs; in C:\%TEMP% they reached 14,000+ folders and
  about 20 GB and filled C: mid-run. Stell OK'd clearing old `morkyn-*` test dirs from %TEMP%.

## Environment rules that have bitten before

- **Never touch the live `data/`** from tests, probes or servers. There is no single data-dir
  setting; use `tools/playtest_setup_presets.isolated_data_env(dir)` with absolute paths.
- **Line endings are mixed.** CHANGELOG.md, README.md, docs/PLAYTEST_ISSUES.md, app/world.py,
  app/skill_checks.py, app/conversation.py, app/turn_dsl.py, app/prompts.py,
  app/player_resources.py, app/quest_parser.py and static/styles.css are CRLF; app/llm.py,
  app/main.py, static/app.js and most tests are LF. Edit with the Edit tool or a byte-level,
  EOL-preserving script. Never sed, and never `git stash` (autocrlf rewrites files).
- **No heredocs into python**, and nothing backgrounded that reads stdin; they hang or mangle
  backslashes. Write scripts to a file first. After a scripted edit, check for stray control
  bytes.
- **Harnesses override defaults**, so add a test that the shipped default works when touching
  a default.
- Playtest tools: `tools/api_bridge_playtest.py` (agent as player; `--local-model <gguf>` makes a
  local model the GM), `tools/playtest_setup_presets.py` (setup through the real page).
