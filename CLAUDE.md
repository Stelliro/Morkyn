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
- **A task the model keeps failing is too hard: make that task simpler** (2026-10-17): "usually a
  task for an ai to commit that its having an issue with means that we need that specific task to
  be simpler." When the same call fails run after run (a field it fills wrong, a judgment it keeps
  getting backwards), split it, narrow what it is asked, or move the hard part to the engine,
  instead of adding another rule that catches its output afterwards.
- **Engine first; checkers, not narrator prompt lines** (2026-10-18): "fixes should be made with
  the game engine as a priority ... it's better to add more checkers or checkers with better rules
  that pass on instruction than editing the narrator's prompting as doing that dulls the responses
  on a small scale that could add up in the end." When a fact has to be decided (a job offered,
  a person present, a price agreed), the engine finds the candidate with keywords and its own
  records, one small model ask fills in the parameters from the one line found, and a second
  small ask checks the result against the turn's text (does this appear in the context, does it
  make sense to hand to the player). Only then does the engine act. The narrator's prompt stays
  as it is.
- **Stop loading the prompts; keep every ask simple and clear** (2026-10-21): "we really need to
  stop loading on the prompting of the agent however when we edit the promting or ask it
  something, we need to ensure that both are as simple but understood as possible". Prefer no
  new prompt text at all. When a prompt is edited or a small ask is written, use the fewest,
  plainest words that the model still gets right, one question per ask, and check it live on
  the 8B. Cut a line rather than add one.
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
- **Test on both the 7B and the 8B, 8B first** (2026-10-14): Qwen3 8B is the target; the 7B
  runs 30-43 were the wrong model to lead with. Next: a long 8B run logging faults by class instead
  of restarting on each one. The prompt review to act on next is
  docs/showcase/prompt-review-2026-10-14.md.
- **Baseline runs:** a 100-turn 7B run "with no issues" becomes the baseline. Run 5 (2026-10-14,
  docs/showcase/saltmarrow-7b-run5-findings.md) was not one.
- **Iterate until the playtest is complete** (2026-10-14): when a test run turns up issues, keep
  fixing and re-running without waiting to be asked, until the run is clean enough to call a
  baseline; only then hand over for Stell's own playtest. Issues Stell finds after that are
  learning material for the next patch, not failures; log them and fix them the usual way.
  Stell (same day, going to sleep): "go on for as long as it takes for no issues to occur ...
  go past 100 turns": runs may go longer than 100 turns, and the fix/re-run loop continues
  unattended. Still no push, tag or release without an explicit ask.
  Stell (2026-10-17): "keep going, dont stop until we hit 100 turns with the 8b model with no
  issues". The 8B loop does not pause for a report; it ends at a clean 100-turn 8B run.
  Stell (2026-10-18): "if something fails after it has continuously failed, skip it and continue
  the playthrough, skip smaller issues, but note them, and list them in severities and log what
  you done to attempt to fix them, we need to find out what worked, what did not work and what
  we could possibly do to fix or mitigate the issue". So: a fault class that has come back after
  repeated fixes no longer stops or restarts the run; smaller faults are logged, not fixed
  mid-run; every fault goes in the run fault log (docs/showcase/run-fault-log-2026-10-18.md)
  with a severity (state / player's agency / prose), the attempts so far, what worked, what did
  not, and what could still fix or mitigate it, including building something new for it
  (Stell's example: a dedicated new mechanism such as "the neural welding rig") rather than
  another rule.
- **Issues first, turn time later** (2026-10-22): "dont worry about how long the tunrs take for
  the time being as we can always attempt to fix turn time later after the issues are fixed and
  we have something more concrete". A mechanism that adds a small ask per turn is fine while the
  fault families are being fixed; log the timings, optimise afterwards. Work order: the five
  mechanisms (people sketches, places with insides, jobs filed as said with owed pay, pronoun
  repair limits, acts by grammar + energy rebalance), then 8B runs to see if they worked, then
  other fixes for what did not.
- **Roadmap:** stable 0.10 first, then 1.0 as an exe or package. Test saves can pile up until
  then; the cleanup and template saves happen at 1.0.
  Stell (2026-10-18, after 0.10.0-dev.14 was pushed and released): "we should probably leave a
  release here and start working on an exe and linux/mac equivalent." The 8B playtest loop
  pauses at run 151 T14; packaging is the work now: a Windows exe and the Linux/Mac equivalents,
  from the real launch path (Morkyn.bat / start.sh / morkyn_app.py), with the local model and the
  data folder outside the bundle.
  Stell (2026-10-19): "could we make the exe seperate from its dependancies so we dont ship them
  together? also, we will need a new method for updating, but we should probbaly make it so the
  user can select a version, this is a future proofing method i want to use." So: (1) the app
  build is small (Python, the game, the web files); heavy dependencies (llama-cpp-python CUDA /
  CPU, later others) are **runtime packs** downloaded from the releases into `runtime/` beside
  the exe and put on the path at start; (2) updates are a **version picker**: the app lists the
  releases, the user chooses one (newer or older), it downloads into `versions/<tag>/` beside
  the exe, and the exe hands over to the chosen version at start (`data/active_version.json`);
  `data/` and `runtime/` are shared by every version. docs/Packaging.md has the design.

## Design decisions

- **Prompts, not gates, for content fields.** A wrong-kind answer is fixed by changing the ask
  and shipping the context, never by a regex that refuses it.
- **No fixed examples in prompts.** The local models paste them verbatim. Draw 3-5 fresh ones per
  call from large, world-filtered pools; the engine rolls hard values itself.
- **Engine owns the math.** Dice, ability growth, costs and counts are engine-only; repair before
  a gate rather than retrying the model.
- **Rosters:** resolve model text against the roster and its synonyms; mint only on a genuine
  miss; ambiguous matches resolve to nothing.
- **Jobs bind by reference, not title** (2026-10-18): "a job being retold under a different
  name isnt the worst thing, however we should be using the references for it so for example
  '@Q'". Quests are referenced by code like everything else (`@Q1` in the player's line beside
  `@A`, `#L1`, `!I1`, `&E1`; `Q1` in ops). The offer check is shown the open jobs by code and
  names the one a line tells again; the parser binds that proposal to the referenced quest
  (`retells`) before any title rule. Title similarity is the fallback only.
- **Persuasion difficulty follows what is asked** (2026-10-21): "we need to give persuasion
  attempts at simpler questions a boost as people are more likely to answer simpler questions.
  this likely means we need to assign an agent to specifically clarify the difficulty of the
  persuasion attempt." A plain question rolling is fine; its difficulty is the fault. Planned: a
  small ask-weight agent rates the ask, the engine sets the DC from the rating.
  Same day, on persuasion, invented quest steps, ship parts as places and searches making
  places: "we should definetly still track them, however, we may need to think outside the box
  on how to fix them" (new mechanisms, not more rules).
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
- **The full test suite** (`tools/run_suite.py` in .venv) has 14 known failures as of
  2026-10-18 (3593 tests): batch5 x2 (unshown name bound to the one figure, role in the figure
  sentence), prompt_context_reachability x2 (cited world_state keys, packet keys), quest_live
  (paid request and assignment), quest_parser x2 (unknown giver vs board, accept then complete
  pays), op_list asks for a code or quoted name, layout and look stay in their files, town_ui x3
  (cell walk-out x2, arrow with no road), and the test_bare_assert_files and test_tts loader
  errors (httpx not installed). quest_pipeline's unready-parser test passes again since the
  hook rewrite. Anything beyond those is new, except the known flake
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

- **Database blocks are `with connect().closing() as conn:`** (2026-10-18). sqlite3's own
  context manager only commits; a bare `with connect() as conn:` leaked every connection and the
  live harness grew ~70 handles and 25 MB a turn until the machine ran dry. A held connection
  (`self.conn = connect()`, `with self.conn:` to commit) is untouched; never use `conn` after its
  `.closing()` block. tests/test_db_connections_close.py keeps bare blocks out of app/.
- **Never touch the live `data/`** from tests, probes or servers. There is no single data-dir
  setting; use `tools/playtest_setup_presets.isolated_data_env(dir)` with absolute paths.
- **Line endings are mixed.** CHANGELOG.md, README.md, docs/PLAYTEST_ISSUES.md, docs/TODO_NEXT.md,
  app/world.py, app/llm.py, app/main.py, app/skill_checks.py, app/conversation.py,
  app/narration_pipeline.py, app/turn_dsl.py, app/prompts.py, app/player_resources.py,
  app/quest_parser.py, static/styles.css and static/index.html are CRLF (checked 2026-10-18);
  static/app.js, CLAUDE.md, the showcase docs and most tests are LF. Check with `file` before a
  scripted edit; a file can have changed sides since this list was written. Edit with the Edit
  tool or a byte-level, EOL-preserving script that reads bytes and keeps the file's own EOL.
  Never sed, and never `git stash` (autocrlf rewrites files).
- **No heredocs into python**, and nothing backgrounded that reads stdin; they hang or mangle
  backslashes. Write scripts to a file first. After a scripted edit, check for stray control
  bytes.
- **Harnesses override defaults**, so add a test that the shipped default works when touching
  a default.
- Playtest tools: `tools/api_bridge_playtest.py` (agent as player; `--local-model <gguf>` makes a
  local model the GM), `tools/playtest_setup_presets.py` (setup through the real page).
