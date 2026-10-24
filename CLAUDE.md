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
- **Changelog and releases:** entries go under `## [Unreleased]` in CHANGELOG.md; the current batch
  is 0.11.x and the number only goes up. The full numbering, bump, tag and push procedure is the
  `release` skill (.claude/skills/release/SKILL.md): load it before touching CHANGELOG.md,
  APP_VERSION or a tag. Push, tag and release only on an explicit ask.
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

- **No GPL in published packs** (2026-10-23). Mørkyn is PolyForm Noncommercial and imports the
  runtime packs into its own process, so a pack uploaded to the release carries no GPL code:
  the Linux window is PySide6 (LGPL), not PyQt6. Piper (piper-tts 1.8.0, and espeak-ng inside
  every Piper) is GPL-3.0, so the speech pack is not uploaded until that is solved. Check each
  pack's dist-info licenses before an upload.
- **Linux: the game runs in a terminal you can close** (2026-10-23): "we just need a terminal
  we can close to ensure that the morkyn game is closed completely". The `morkyn` script opens
  a terminal when started without one (the menu's `Terminal=true` is up to each desktop, so it
  is not relied on). Cleaner
  closing comes later.

- **Where the player is, the people met are** (2026-10-24, #33): "play state needs to be in the
  same location as npc and hadded to the llm to ensure that the llm knows where the player is". A
  person the player meets is filed at the player's place, and the narrator is always told plainly
  where the player is. Stell, same day, on scenes drifting to other places: "the story should be
  told where the player is, fix the drift": the place is the first of the facts_to_keep (held like
  the hour), not only a field in the place data.
- **Death is a 0/1 state the narrator is told only when it is 1** (2026-10-24, #154): "npc death
  state needs to be changed from 0 to 1 ... if not the llm should assume all npc's state is 0 (we
  dont need to tell it that npc's are alive as it already asumes that, we just need to tell it
  characters are dead so add something like 'if state "dead = 1" character is dead')". The row
  holds dead 0/1; the narrator gets the dead=1 people at the player's place (and the turn a state
  changes), with one line saying dead = 1 means the character is dead; living people carry no
  flag. Stell asked for that line, so it is the one allowed addition to the narrator's text here.
- **The player is asked before a move they did not ask for** (2026-10-24, #46/#76): "the player
  should be asked if they wish to move unless a state forces them to (eg. the player gets pushed
  out a doorway or they player gets thrown or gets blown out a wall)". When the prose ends the
  scene somewhere the player's line did not go, the game offers the move instead of making it;
  a forced move (pushed, thrown, blown out) is applied.
- **Transactions and items are read by their own agent, before and after the act** (2026-10-24,
  #41/#85/#155/#152): "we likely need a seperate agent to parse transactions and items before and
  after actions, this includes but is not limited to items and gold". The interpreter's gold read
  grows into a transaction parser: what the player and the people here hold before the act, what
  the scene shows changing, applied by the engine. For attacks: "the llm should roll before they
  decide on how the player or an npc attacks and should be determined by the roll" (how the roll
  reaches the prose: Stell chose, the same day, "Engine writes the outcome line": the roll comes
  first, the engine writes the attack's result line itself from the roll and the weapon, the
  narrator writes the scene around it, and when the draft leaves the line out or contradicts it
  the engine puts its own line in; no model rewrite, no extra model call).
- **Money is copper, silver and gold, held as one number** (2026-10-24): "i want to add copper,
  silver and gold as the currency, that way we can translate the currency into 1 form ... we can
  use the $ symbol as a command for the llm, so $69420 will be translated as 6 gold 94 silver and
  20 copper, we should never rely on the llm to work out the item cost by coin, just a single
  value". One unit is a copper: 1 silver = 100, 1 gold = 10,000 (Stell's own figures: 2 copper =
  2, 3 silver = 300, 40 gold = 400,000). Purses, prices, rewards and payments are that single
  value, and the engine owns the math. The model writes an amount only as `$<number>` (a
  command, like the codes); the engine turns it into coins for the player ("$69420" -> "6 gold,
  94 silver and 20 copper") and reads coins in prose back into the one value. The model never
  splits a cost into coins. This is why the "silver" fault (F156: a pouch of "silver, copper"
  paid nothing) was held: it is fixed by this, built with the transaction parser. Open when
  building: what an old save's gold number becomes.
  Same day, Stell: "currency should not just be limited to those three, we need a way for
  different currencies to exist, for example credits, or bottle caps (if the player wants to
  play a fallout rpg for example)". So a world has its own **currency set**: one or more named
  denominations, each worth so many base units (copper / silver / gold at 1 / 100 / 10,000 is
  one set; bottle caps or credits can be a single unit). The set is chosen with the world at
  setup and stored with it; `$<number>` is always base units and the engine shows it in that
  world's coins. Bartering (trading goods for goods) is wanted too but is harder and comes
  after the currency work.
- **Transactions are settled before the draft, and the narrator is told the result** (2026-10-25,
  Stell: "what if we were to do the transactions and confirm them before we finish the draft?"
  ... "sounds good"). The attack line's pattern, applied to money and items. (1) Before the draft
  the engine reads the player's line for what it commits to (pay, offer, hand over, take, sell,
  buy; amount and item). (2) It confirms against its records: the item is held, the price matches
  an offer on record, the other side has the coin; one small ask only when the line is unclear.
  (3) The other side is settled by the engine: an offer on record is accepted, otherwise the
  haggle or persuasion check decides accept, counter or refuse. (4) Purse and inventory move
  before the narrator writes; the done fact is handed to it as a line it must show, and when the
  draft leaves it out or contradicts it the engine inserts its own line (no model rewrite).
  (5) After the draft the reader only looks for what the scene introduced (finds, a gift, a price
  quoted): those are proposals filed as records, applied when the player's next line acts on them
  or a quest step completes. Offers must therefore be held as records between turns (jobs need
  the same). Built as the first item of the money work (m1 currency set, `$<number>`), after the
  sonnet100 run.
- **#157's cross-reference is a system, not a fix** (2026-10-24): "this will be a big undertaking,
  as to do this we will need to ensure we build a cross referencing system between npc's and the
  llm, as well as what the player says and what the llm what the llm wants to say". Design it as
  one mechanism (the records the engine holds, checked against what the draft wants to say)
  before building.
- **The dead leave a body** (2026-10-24): "we shouldnt just remove dead npcs, as they should not
  just vanish, they should have a dead body". A dead person stays where they died as a body: in
  the place's records and the narrator's context as dead and present, never as someone who
  talks or acts; the body can be searched, moved or buried.
- **Unnamed NPCs are stored and numbered per kind** (2026-10-24): "hostile monster npc's should
  also be stored in the database, they should be provided an increasing id intiger per appearing
  non named npc". Every unnamed NPC that appears (monster, raider, guard) gets a row named by its
  kind and the next number for that kind (Ghoul 1, Ghoul 2, Raider 1; Stell chose per kind and
  every unnamed one); the code stays the engine's own (A, B, ...). A creature is a person row,
  not filtered out as a place.
  A plural with no count is rolled (Stell, 2026-10-24): "we should be looking at "'s" as if they
  account for many, and we should roll a dice on it and stick to it ie. "Gouls lunge at you" dice
  roll = 4 = "4 ghouls lunge at you"". The engine rolls the count, files that many rows, writes
  the number into the prose where the plural first appears, and keeps to it after.
- **Combat gets its own tab in place of the map** (2026-10-24): "the combat scene appears and is
  closed, for combat, i want to replace the map with a new tab labeled "combat" this way the
  player can actually view who they are in combat with, how much health they have and view more
  in depth infomation about them as well as selecting a target". While a fight is on, the map's
  place in the play panel is a **Combat** tab: who the player is fighting (the engine's rows,
  numbered unnamed ones too: Ghoul 1, Ghoul 2), each one's health, more detail on each, and a
  target the player selects (it reaches the turn as that person's code, like `@A`). It follows
  the engine's encounter state, never the prose. Not a future addition: it is the next job
  after the work in hand (the attack line, then the transaction parser and ask-to-move) is
  fixed; the theft and locked-places items in docs/TODO_NEXT.md come after it.
- **The Settlement map view is for the settlement you are in** (2026-10-23): "when the player is
  not in a town or settlemnet the player can still view the settlement tab". It was built for
  #19 as "the settlement you are in, or one you know"; outside a settlement it is not offered.

- **Narrator, interpreter, engine** (2026-10-23, planned; Stell's fix for prose and state
  disagreeing): the **narrator** only describes; it "cant make anything happen". The
  **interpreter** (Stell's name for it: not "translator") reads the player's line (what was
  tried) and the finished scene (what happened) in one small ask and states the outcome as
  plain events ("player gives 5 gold to merchant"); handing those to the engine is when
  anything happens. The **engine** checks each event against its records (purse, roster,
  places), applies or refuses it, and owns the math. The narrator stops writing state ops, so
  there is one source of truth. First step: gold only, in shadow mode beside
  `world._settle_stated_gold` on recorded 8B turns, logging disagreements before anything
  changes; items and moves follow if it wins, and the prose_state gold readers retire.
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

- **Models.** Stell (2026-10-23) chose **Hermes 3 (Llama 3.1 8B, Q4_K_M)** as the model to
  move to: "lets go with llama 3.1 ... expecting less and getting more is our goal anyway".
  It is the recommended entry of the one-click catalog (app/model_catalog.py), installed on the
  Pop!_OS machine in `~/.local/share/morkyn/data/mle-models/`. Its baseline is the 100-turn
  Saltmarrow run of 2026-10-24 (docs/showcase/hermes-base100-findings-2026-10-24.md): median turn
  11.0 s, no fallbacks, 176 fault rows in 100 turns, led by money read from the model's die rather
  than the prose, people rebound between rows, creatures never filed, and jobs never filed.
  The second run (2026-10-25, docs/showcase/hermes-sonnet100-findings-2026-10-25.md; Sonnet agents as
  the player, the creature fix merged): median turn 14.3 s, no fallbacks, 212 fault rows (counts are not
  comparable with the baseline: build and player changed at once; the families are); money never
  moved by a scene in 100 turns, jobs were filed and completed, creatures still got no row and two
  blows hit a bystander. Run it with `tools/harness_with_packs.py` (the Linux .venv has no llama_cpp;
  the wrapper puts the installed CUDA pack on the path) and watch at http://127.0.0.1:8790/.
  The earlier long runs were measured on Qwen3 8B (`D:\morkyn-stage-models\Qwen3-8B-Q4_K_M.gguf` on
  Windows; also in the catalog), so compare Hermes against that. Check `/api/model-status` →
  `file` to see which GGUF actually loaded. On the RTX 4070 Ti a turn takes about 10-40 s on the 8B and about 15 s on
  the 7B; a retry costs 30-80 s and usually returns nothing better.
- **Typical model faults** (handle them with the guiding rule above): acting or speaking for the
  player, prose and ops disagreeing (moves, places, people, items, gold), stock phrases, codes
  or op text in the prose, voice slipping to first or third person, retry prompts echoed back.
- **The full test suite** has 14 known failures and one known flake (as of 2026-10-18); the list and
  how to run it (`tools/run_suite.py`, never a bare `-m unittest`) are in the `run-suite` skill
  (.claude/skills/run-suite/SKILL.md). Anything beyond that list is new.
- **Evidence lives in model traces** (`data/model_traces/turn-*.json`): read them before the code.
  The model side is in `model_trace`; what the engine did is in `engine.ledger` (`delta` first,
  then `writes[i].at` for the code, `swallowed` for hidden failures).

## Environment rules that have bitten before

- **Database blocks are `with connect().closing() as conn:`** (2026-10-18). sqlite3's own
  context manager only commits; a bare `with connect() as conn:` leaked every connection and the
  live harness grew ~70 handles and 25 MB a turn until the machine ran dry. A held connection
  (`self.conn = connect()`, `with self.conn:` to commit) is untouched; never use `conn` after its
  `.closing()` block. tests/test_db_connections_close.py keeps bare blocks out of app/.
- **Never touch the live `data/`** from tests, probes or servers. There is no single data-dir
  setting; use `tools/playtest_setup_presets.isolated_data_env(dir)` with absolute paths.
- **Line endings are mixed.** (CHANGELOG.md is LF as of 2026-10-25.) README.md, docs/PLAYTEST_ISSUES.md, docs/TODO_NEXT.md,
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
