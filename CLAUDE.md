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
- **The full test suite** (`python -m unittest` in .venv) has 16 known failures as of
  2026-10-13 (batch5 x2, live_smoke_places, prompt_context_reachability cited keys, quest_live,
  quest_parser x3, quest_pipeline, skill_roster, town_ui x4, and the test_bare_assert_files and
  test_tts loader errors). Anything beyond those is new.
- **Evidence lives in model traces** (`data/model_traces/turn-*.json`): read them before the code.

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
