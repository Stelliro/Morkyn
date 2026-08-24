# Changelog

All notable changes to **Mørkyn** (formerly Mørkyn) are documented here.

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

### Version Number Guide
- **MAJOR** (`x.0.0`) - Breaking changes to public APIs or saved data formats
- **MINOR** (`0.x.0`) - New features, backward-compatible
- **PATCH** (`0.0.x`) - Bug fixes, backward-compatible

### Entry Format

```text
- [AGENT_ID] Description of change - module/system name included
```

---

## [Unreleased]

> Changes after `0.9.0` live here.

### Added

- One-file bootstrappers `start.bat` (Windows) and `start.sh` (Linux / macOS), published as assets on the `v0.9.0` release. Dropped into an empty folder they clone the repo, build a private `.venv`, install dependencies and start the game; on later runs they check GitHub, **ask before updating**, and start the existing copy when the answer is no, when the machine is offline, or when the checkout has local changes. Flags: `--full`, `--update`, `--no-update`, `--help`; Windows passes anything else through to `Morkyn.bat`.
  - The default install filters `llama-cpp-python` out of `requirements.txt` rather than duplicating the pins. Its CUDA wheels are a large download that fails outright without a matching toolchain, and neither Ollama nor the cloud APIs need it. `--full` installs it.
- `.gitattributes` pinning `*.sh` to LF. The repo is developed with `core.autocrlf=true`, which would otherwise check `start.sh` out with CRLF and break its shebang on Linux and macOS.

### Added

- **Naming contract and repair** - `app/naming.py`, `name_ledger` table. When the player asks for a name, the world now answers with one: it reuses the name already committed in history, and mints a deterministic one when nothing was ever established. Either way the answer is written to `name_ledger` so the second asking matches the first, and the narration is repaired when the model dodges.
  - Found by the 100-turn continuity probe. "The sealed letter is addressed to Corvin Marrow" was planted on turn 2; asked to read it aloud on turn 26 the model answered plainly, and on turn 94 - the identical question - it wrote *"the name you read brings a weight to your chest"* and never said it. It knew the letter existed and volunteered an unrelated debt in the same paragraph. It simply would not commit.
  - Same shape as the movement and venue work: a contract in the turn packet plus deterministic post-turn repair, because prompt guidance alone has never been enough for this failure class here. The repair appends one plain sentence rather than rewriting the paragraph, and runs on the deterministic-fallback path too.
  - Detection is phrase-level. `name` is an ordinary English word - "a name for the road", "names carved in the post" - and triggering on it turned roughly every third turn into a naming demand during development.

- **Venues are visible in the browser at last.** `static/app.js` did not contain the word "venue": entering a shop only changed the location name, so a player could not see a smithy was on this square, could not tell it was shut, and had no sign that stepping outside was a move. `updateVenueLine()` renders the shops here as chips with open/closed state, names the bound keeper when you are inside one, and offers the way out. Clicking a chip drafts the action into the composer rather than sending it - the player still decides. Everything shown already rode in `current_location`; the UI was throwing it away.
- **NPC pronouns are pinned once and then stated.** New `npcs.pronouns` column, `infer_npc_pronouns()`, `bind_npc_pronouns()` and `cast_pronouns` in the voice contract. Over one 100-turn run the same bargeman was "he" 41 times and "they" 128 times - no gender flip, just nothing ever saying which was right, so the model re-decided every turn. Inference runs once, from the sentence that names the character plus the next one when it clearly continues about them, and never again. Replayed against that run's prose it pins all four recurring NPCs by turn 17.
- **Remembered specifics now have to be spoken.** `recall_contract()` / `check_recall_specifics()` in `app/world.py`, one prose-only retry in `app/llm.py`. Turn 88 of the second 100-turn probe asked "who I owe, how much, and when" and answered *"You answer honestly: who you owe, how much, and when"* - never naming the lender or the amount. It was the run's only recall miss, at 10/11.
  - This was **not** a retrieval failure. The record - "eleven silver to a lender called Hask, due at the next full moon" - was in that turn's own prompt six times over, plus a claims entry. Prompt text had already failed, so the fix is the established one: state the specifics as server truth, verify the prose, repair once with the record handed back verbatim.
  - Only proper nouns and amounts are demanded back, and stating *any one* of them passes. Requiring the topic words instead would fire on prose that answered in its own words, and rewriting a good scene is a loss. Scored against all 100 turns of that run it selects exactly one - the real failure - at every threshold from 0.3 to 0.5.

- **A promised explanation now has to appear.** `check_answer_act()` plus one prose-only retry (`AI_RPG_ANSWER_REPAIR=0` disables). Turn 66 of the probe asked the player to explain a fear of deep water; the narration described kneeling at a marked spot and never touched it. Scored against all 100 recorded turns the shipped detector fires exactly once - on turn 66 - with no false positives.
  - A broader "did the narration respond to the action at all?" detector was built and **rejected**. A category-overlap version flagged five turns of which at least three were plainly responsive (a line about listening for rumours answered with "You ask about...", another with "They mention a reward for a sealed letter"). Firing a rewrite on responsive prose makes the turn worse, so only a total miss on an explicit answer act counts.

### Fixed

- **A quarter of every place the game ever named came out of the prompt's own examples.** Two toponyms were hardcoded as worked examples in the movement rules -- "Riverbend Camp" in both `movement_contract()` and the DSL rule block, "Redmill Ford" in the DSL MOVE line -- and they shipped on every turn of every world - `app/world.py`, `app/turn_dsl.py`
  - Counted across the 42 recorded playtest databases still on disk: of 170 place names, **36 contain "Riverbend" and 8 contain "Redmill"**, and 21 of the 42 worlds carry at least one.
  - This is what made high fantasy the weakest genre in the matrix. A campaign set up for "high fantasy with open magic and old empires", opening at The Sunken Colonnade, spent its second half in **Riverbend Piers** and **Riverbend Village** and scored 1 of 8 on its own genre vocabulary. It was handed a river hamlet's name on every single turn.
  - Same failure as the idea-card titles above, one layer down: a 7B handed a concrete name inside an instruction does not read it as a placeholder. The rule still needs a worked example to land, so `_movement_rule_example()` builds one from the world's own map -- a known place, or on turn one the place the player is standing in, which is the name most likely to get a word bolted onto it. Copying that example now costs nothing: the move resolves to a row that already exists.
  - The DSL rules lost their exemplars outright and state the shape instead. The NPC-name examples ("Aria", "Captain Vesk") were measured too and left alone: 12 hits across 320 recorded NPCs, because they sit in a list of three against a counter-example, which reads as a class rather than a name.
  - `benchmarks/run_genre_variety.py` gained `GENRE_ONLY` so one genre can be re-checked without an hour-long full matrix.

- **Two cards out of 292 were pinned to the top of every randomization, forever.** The previous entry fixed the *no-query* branch and left `world_style` at 3/10 distinct, blaming the model for copying spark titles. That was the wrong diagnosis. `empty_intent()` fills its unset slots with sentinel *words* rather than blanks - `adapter_hint: "default"`, `start_power: "ordinary"`, `growth: "steady"` - and `build_query_from_setup()` fed all three to the search. A cold randomize therefore searched the bank for **`"default ordinary steady"`**, which matches exactly two cards, so `style.low_fantasy_mud` and `ability.pulse_count` led the spark list on every roll ever made - `app/idea_bank.py`
  - Same class of bug as the field-name leak fixed above: prompt input describing the *form* rather than the player's idea. Intent values are now compared per key against that key's own default, so a genuine tone of "steady" still counts (tone defaults to `""`); only a slot still holding its placeholder is dropped.
  - Measured live, 10 cold rolls before: `world_style` 3/10 distinct - 6x "low fantasy mud", 3x "Low fantasy mud and knives", 1x the raw id `low_fantasy_mud`. `start_location` was **"a broken cart axle starts the plot"** on 10 rolls out of 10 - the `examples` line of that same card, pasted into a place-name field.
  - The *scored* branch was equally fixed: `sort(...)[:limit]` returned the same four cards for the same idea every time, and a flat tie (a dozen cards all scoring 1.0) was broken by title, so the alphabetically-last twelve won forever. Selection is now weighted by score inside a relevance floor - only cards scoring at least half the best score are eligible, so a 0.35 substring match can never displace a direct keyword hit.
  - After: `world_style` **12/12** distinct, `tone` 12/12, `start_location` 12/12, `custom_style` 12/12, `tech_level` 12/12, `race_magic_rules` 12/12, `race_ability_rules` 12/12, `race_magic_rarity` 10/12, `economy` 9/12. No raw card ids.

- **Prompts no longer carry the three spark fields shaped like a finished answer.** `prompt_sparks()` sends `kind`, `text` and `keywords` only; `id`, `title` and `examples` stay in the package the search API and setup UI render - `app/idea_bank.py`
  - All three were measured being pasted straight into the form: `world_style: "low_fantasy_mud"` and `tone: "pastoral_curious"` (card ids), `world_style: "Low fantasy mud and knives"` (title), `start_location: "a broken cart axle starts the plot"` (examples).
  - The rules block has said *"Do not copy titles verbatim as final values"* the whole time. It did not work: **13 verbatim titles across 12 rolls**. Removing the field is the fix - the model cannot paste a string it was never shown. `text` and `keywords` carry the same idea without a ready-made label, so it has to write a phrase instead of lifting one.
  - After: **0 verbatim pastes across 12 rolls**, and the styles are synthesised rather than copied - "orbital station with customs as a religion", "war-torn cathedral republic", "post-apocalyptic cyberpunk with floating cities". Variety held or improved on every field measured (`world_races` 9/12 -> 12/12, `economy` 9/12 -> 11/12).
  - Backstop for anything that still arrives looking like a handle: `looks_like_card_slug()` flags a bare snake_case or dotted token in any enum/short_phrase/prose field, and `start_location` is now checked against `is_plausible_place_name()` at the setup layer - the map already refused that shape, but the form accepted it, so the repair pass never ran.

- **A multi-field randomize never told the model which fields were closed enums.** The group prompt shipped `return_fields` as a bare list of names - no `return_shape`, no contracts, nothing marking `magic_level` as one of five fixed strings. The contracts already existed and were already sent on the single-field and repair paths; the group path was the one caller asking a closed question in open form - `app/llm.py`
  - Measured over eight live rolls, the model answered `magic_level` with `"low"`, `"Low"`, `"low-magic"`, `"post"` and `"Limited to arcane crafters and guilds"`. Every one of those falls through `normalize_magic_level()` to its default, so the stored value was **"rare" on 12 rolls out of 12** - not a model preference, a silent default nobody could see.
  - With `field_contracts` attached the model returns canonical values verbatim - `common utility`, `cultivation`, `forbidden`, `none` - and normalization has nothing left to do. `magic_level` 1/12 -> 4/12 distinct.
  - `race_magic_enabled` moved off its stuck value too: 12/12 False before, 9 True / 3 False after. It is a boolean, so two distinct values is the whole range — the remaining question is the balance, and leaning True beside a `magic_level` of "common utility" is coherent rather than wrong.

- **`custom_style` was sometimes just `world_style` again.** Twice in twelve rolls one idea-card title filled both slots. `custom_style` is the prose field for world constraints and DM stance, so a verbatim restatement of the genre phrase leaves the setup with nothing where its stance should be. It now falls back to the structural value, which keeps the style as the setting frame and appends the stance the field exists to carry - `app/llm.py`

- **A location literally named `[[L1]]`.** A live space-opera run spent three of six turns there: the model answered a move with the entity-code wrapper instead of a name, and every guard read the wrapper as an ordinary word. `humanize_place_name()` now strips the brackets first - so `[[Mosswake Gate]]` also lands on the row that already holds it - and `is_plausible_place_name()` refuses bare codes (`L1`, `E3`, `NPC2`, `AA`) the way the person check already did. Short real names ("Ys", "Oz", "Rio") still pass. The predicate unwraps on its own rather than trusting the caller, because the setup form calls it on raw model output - `app/world.py`

- **The map grew copies of the place you were standing in.** Replaying the location tables six recorded 100-turn runs left behind, two shapes survived every existing guard - `app/world.py`
  - `Hills Beyond Mosswake Gate` was followed onto the map by **`Hills Beyond Mosswake Gate Eastward`**: `_place_extension_target()` already merged a generic tail noun onto a leading prefix, but its tail list held no bearings or storeys. Added, so `... Eastward` and `Abandoned Water Structure Lower Level` fold into their parents while `Mosswake Gate Market Square` keeps its own row - "market" is not generic.
  - Nothing looked the other way at all. When the model dropped a qualifier instead of adding one, the bare stem became its own place beside the full name: `Riverbend` after `Riverbend Camp`, `Mosswake` after `Mosswake Gate`. New `_place_stem_target()` is deliberately strict - exactly one existing place may match and the words it adds must all be generic, so "Riverbend" keeps its own row when the map holds both "Riverbend Camp" and "Riverbend Ford". There the stem names the area rather than either place, and guessing between them would move the player somewhere they never walked.
  - Replayed against the recorded names: 13 arrivals produced 10 rows, now 7, with every genuinely distinct place intact.

- **Randomize produced the same world nine times out of ten.** Ten live "world" randomizations returned `world_style: "Post-magic wasteland"` nine times, with `tone: "Intimate close"` and `custom_style: "Glow means leave"`. Those three strings are the title and example of two cards in `config/idea_bank/`, copied verbatim despite the spark rules telling the model not to - `app/idea_bank.py`
  - **Cause 1:** `build_query_from_setup()` appended the *field name* to the search query, so a cold randomize searched the bank for `"world style tone custom style"`. The literal word "tone" matches every `tone.*` card, so all five sparks came back as tone cards and `world_style` got no style spark at all. Relevance by field is already handled by `kinds_for_field()`; the name only caused collisions.
  - **Cause 2:** `search_idea_bank()`'s no-query branch promised "a small random-ish slice" and returned `pool[:limit]` - the first N cards in load order. It was also guarded by `and not kind and not kinds`, making its own kind-filtering unreachable, so a call *with* kinds fell through to the scoring loop and matched nothing.
  - Net effect: the same 5 cards out of **292**, on every call, forever. Fixed, sparks now vary (25 distinct across 5 calls, was 5). Measured live afterwards: `custom_style` 2/10 -> 9/10 distinct, `character_backstory` and `special_abilities` 8/10, and no two randomized setups identical.
  - **Follow-up:** every "still open" item here was root-caused above - the pinning was a sentinel-value leak in the query, not the model being lazy, and `magic_level` was a silent default, not a preference.

- **Every setting was staffed as though it were medieval.** `_SEED_ROLE_POOLS` held pre-industrial occupations only, and `_seed_role_pool()` chose between them using the location's *name* alone - genre never entered the function. This is the server's own invention for a face the prose mentions without naming a job, so no model is involved and it reproduces on demand - `app/world.py`
  - A futuristic world got: Docking Bay Seven -> **bargeman, boatwright, salt carrier**; Reactor Deck -> **scribe, weaver, tanner**; Neon Market District -> **scribe, scribe, well keeper**; Wreck Site Delta -> **roofer, toll keeper, roofer**.
  - It survived four 100-turn playtests because every one of them ran the same world: `world_style: "frontier dark fantasy"`. Nothing had ever asked the game for a different setting.
  - Pools are now indexed era-first (`preindustrial` / `industrial` / `modern` / `future`), then place. Era comes from the campaign's own `tech_level` - the canonical five-value vocabulary the setup UI offers - falling back to the style prose the player typed, so "far-future interstellar civilisation" and "cyberpunk megacity" both resolve without a tech_level set. Unknown worlds default to preindustrial, so existing campaigns produce byte-identical output.
  - The place axis is unchanged and now era-independent: a docking bay is "where things arrive" for the same reason a wharf is, so it draws cargo loaders and gantry hands instead of ferrymen.

- **The world's long-term memory of what the player said was truncated at 80 characters.** `parse_dsl_turn` synthesises a turn summary when the model emits no SUMMARY op, and that summary becomes the `turn_summaries` row and from there the consolidated fact - the durable memory. It cut the player's line at 80 characters, mid-word - `app/turn_dsl.py`
  - A 100-turn run stored `player: I tie a red ribbon around my left wrist and explain that it is a keepsake from m`, losing "y sister Neve". Sixty-four turns later the game was asked who the ribbon came from and could not say. A planted debt lost "comes due at the next full moon" the same way; the lender's name survived only by sitting at character 70.
  - The fact was destroyed at write time, so no amount of retrieval tuning could recover it. Raised to 400 (the field is capped at 700 downstream, so the 80 bought nothing).
- **Prose said the player pocketed something; the world never recorded it.** New `acquisition_claims()` / `ground_acquisitions()` in `app/world.py`. Over one 100-turn run the narration said the player picked up or pocketed a named object on seven turns and the ops emitted GRANT on one - so the same sign was "picked up" on turns 59, 69 and 94, because it never left the ground.
  - Same shape as the movement repair: the narration asserts a state change, the model emitted no op, and the server makes the world match the story. The grant is injected before `apply_turn`, so the ordinary inventory pipeline handles bands and weights.
  - The verb set is deliberately narrow, and **"you take" is excluded outright** - a probe run is full of "you take a slow breath", "you take stock", "you take the road", and an earlier grounding metric built on that verb was pure false positives. "You pocket it" is skipped too: the repair has to know what to grant, and guessing the referent is how a scene about a dagger grants an item called "it".
- **The recall benchmark counted accidental substrings.** `_token_present()` now requires a whole-word match. The planted name "Neve" was scoring hits inside the word "never" - on a turn whose prose actually said the keepsake came from "a lost love". Re-scoring both completed runs, the headline is unchanged at 10/11 either way (the same turn matched "ribbon" legitimately), but the measurement was reporting memory the game did not have - `benchmarks/run_continuity_playtest.py`

- **One fumbled op line discarded every other op in the turn.** Three of the four failed self-checks in the second 100-turn run were the same shape: `INDEX npc F "..."`, where `NPC` is also a flag key (`EVENT ... NPC <code>`), so the entity type `npc` swallowed the code `F`, left one positional, failed `INDEX`'s own arity check, raised, and threw away that turn's MOVEs, TALKs and JOURNAL lines with the message "Ignored unparseable model-proposed state changes." - `app/turn_dsl.py`
  - `_LEADING_POSITIONALS` marks the leading tokens of `FOCUS` (1) and `INDEX` (2) as positional by definition, so they are never read as flag keys. `EVENT ... NPC F` still parses `NPC` as a flag.
  - `ops_to_turn()` now applies each line through `_apply_op()` inside its own try: a malformed line is skipped, recorded in `self_check.issues_found` and `_dsl.malformed_ops`, and its neighbours survive. `parse_ops` already dropped unknown *opcodes* this way and said so in a comment; the arity checks simply bypassed that intent. A draft with no prose, or a block where nothing parses at all, is still fatal.
  - Replayed against the recorded failure, turn 84 goes from 0 ops applied to all 9.
- **NPC pronouns were pinned off the wrong character.** `infer_npc_pronouns()` documented that only sentences naming exactly one NPC count, but checked that for the lookahead sentence only - never for the naming sentence itself. So "A young boy, Liora, watches you ... and a weaver named Bellrow nods" pinned **Bellrow** masculine off the boy, and "Eldrin ... narrows his eyes ... around Cinderrow bundle" pinned **Cinderrow** off Eldrin's three "his" - `app/world.py`
  - Eight of nine pins in that run came out "he", including a weaver the prose called "her" seven times and "they" six times and never once "he". The harness metric, which implements the rule correctly, disagreed with the database - that mismatch is what exposed it.
  - `bind_npc_pronouns()` now passes the rest of the cast as `others`, because the capitalised-token heuristic cannot see a name at the start of a sentence, which is exactly where the second character often sits. Replayed over the run, correct pins go from 6/8 to 8/8, Bellrow flips to "she", and Pikerest gets pinned at all.

- **The shipped turn-draft timeout was inside the range real drafts take.** The Ollama default was 90s (llama_cpp already had 900s). Measured on an RTX 4070 Ti with qwen3:8b and a ~9k-token packet, the draft call takes 27-37s on an idle GPU and **75-100s under ordinary desktop load** - a second model runner, a recorder, a browser. A probe timed out at exactly 90s, and a 100-turn run measured a draft at 99.7s. Anyone on slower hardware, or merely watching a video, was falling back to canned deterministic prose every turn - `app/llm.py`
  - Raised to 300s (verify 45s -> 150s). A timeout is a ceiling, not a delay: nothing waits longer because of it, and the cost of hitting it is the worst failure this app has.
  - **Invisible for the same reason the context bug was.** `benchmarks/run_continuity_playtest.py` exports `AI_RPG_TURN_DRAFT_TIMEOUT=900`, so every 100-turn run reported zero fallbacks while a real player on that machine fell back constantly. That override is still there - the probe measures continuity, and a timeout would corrupt the result - but it is now documented as the trap it is, and the shipped defaults are pinned by `tests/test_context_budget.py`.

- **The shipped default configuration could not run a single turn through the model.** A default launch resolved `context_window=8192`, while `SYSTEM_PROMPT` alone estimates ~9143 tokens, so `enforce_token_budget` raised `Token budget exceeded: system prompt alone is ~9894 tokens for context_window=8192` on turn one and *every* turn fell back to deterministic prose. Players saw flat canned narration with nothing on screen explaining why. Every probe in `tools/` exports `OLLAMA_CONTEXT_TOKENS=32768`, which is precisely why no test ever caught it - `app/llm.py`, `app/launcher_prefs.py`
  - `DEFAULT_CONTEXT_TOKENS` and the launcher's `llama_cpp_context` default are now `32768`, matching the context the README benchmarks and the playtest tools already assumed.
  - New `fitting_system_prompts()` picks the largest system contract that fits the configured window, degrading to `COMPACT_SYSTEM_PROMPT` instead of hard-failing, so lowering the context costs richness rather than killing the turn. It says so once on the server console rather than degrading silently.
- **Every entity reference rendered twice**: "Ash Road Cut Ash Road Cut", "soft shoes soft shoes". The server appends the code after the name on purpose (`_inject_entity_codes_for_known_names` writes `Low Gate Timber Arch [[L1]]`), and `linkifyText` expanded the `[[code]]` into a labelled button *and* separately linkified the bare name beside it. New `collapseNameCodePairs()` folds `Name [[CODE]]` into one reference before escaping - `static/app.js`

---

## [0.9.0] - 2026-08-20

Everything below shipped in 0.9.0, on top of `0.9.0-beta`.

**Verified:** 355 unit/regression tests plus 7 behavior checks, all passing and order-independent;
live probes against a local `qwen2.5:7b-instruct` for narration quality, movement, continuity, and
venues. The schema migration was checked against a hand-built pre-venue database with its rows
intact.

**Not verified in this pass:** the browser UI was not exercised end to end, and it has no venue
awareness — entering a shop changes the location name the UI already displays, but there is no
"shops here" list and no open/closed indicator. Venues reach the player through prose and the
location name only.

### Added

- [CLAUDE] Dice authority (`app/rng.py`) — the server now decides every "how many" and "how much". The model writes a band (`none/trivial/small/moderate/large/huge`, `-` prefix for losses) and the app rolls the amount, scaled by player level, difficulty, and growth-speed settings. Deterministic blake2b seeding means rewind/regenerate reproduce identical dice.
- [CLAUDE] `dice_rolls` table plus `GET /api/dice/recent` — full audit trail for every rolled amount, also summarized into the turn journal under kind `dice`.
- [CLAUDE] Content packs (`app/content_packs.py`) — `morkyn-content-pack-v1` JSON files that add, retune, or remove skills, powers, items, encounter tables, and dice tables with no code changes. Drop a file in `data/packs/` or use the new `/api/content-packs/*` routes.
- [CLAUDE] `GET /api/content-packs/authoring-bundle` — a self-contained specification (schema, hard rules, field→database-column map, worked example, in-use codes) that can be handed to any LLM with no knowledge of Mørkyn to author content. Validation errors carry `{path, message, fix}` so the response can be fed straight back for self-correction.
- [CLAUDE] Danger model (`app/encounters.py`) — travel, wait, and rest risk now accounts for player stats, skills, level, wounds, fatigue, energy, carried load, karma, and area reputation alongside terrain, weather, clock, roads, and difficulty. Encounter participant counts and threat are rolled server-side; a passive awareness check decides `forewarned` vs `surprised`.
- [CLAUDE] `GET /api/danger` — current danger assessment with its full factor breakdown.
- [CLAUDE] Item→stat/power wiring — `inventory.stat_links`, `inventory.power_codes`, `inventory.roll_profile`, and `abilities.read_only/roll_profile/magnitude_kind/magnitude_band/activation`. Equipped gear and passive or item-granted powers now shift skill checks automatically, exposed as `state.gear_roll_modifiers`.
- [CLAUDE] `tests/test_dice_and_packs.py` — 39 regression tests covering dice notation, band monotonicity, negative bands, pack lifecycle, gear modifiers, and the danger curve.
- [CLAUDE] Docs: `docs/DiceAuthority.md`, `docs/ContentPacks.md`, `docs/Encounters.md`.

### Changed

- [CLAUDE] Turn contract slimmed — `prompts.py` and `turn_dsl.py` now ask for `xp_band`, `gold_band`, `health_band`, `karma_band`, `quantity_band`, `trust_band`, `fame_band`, and `delta_band` instead of the matching `*_delta` numeric fields. The required JSON is smaller and the model no longer does arithmetic.
- [CLAUDE] Raw numbers from a model are re-rolled rather than trusted or rejected: they are bucketed to the nearest band and rolled properly, so older prompts, cached clients, and third-party agents keep working. Controlled by `AI_RPG_BAND_AUTHORITY` (`rolled` default / `bands` / `off`).
- [CLAUDE] Skill catalog is now pack-overridable — packs can retune a built-in skill's DC or attribute by reusing its code, add regex `triggers` that route player input to their own skills, or remove a built-in with `"enabled": false`.
- [CLAUDE] `tile_world.roll_travel_encounter()` routes through the danger model, with the legacy terrain+weather roll retained as a fallback so movement never breaks.

### Fixed

- [CLAUDE] Negative magnitudes were clamped to zero on tables with a floor of 0 (`damage`, `heal`, `item_count`, `fame`), which would have made every band-expressed health loss, item loss, and cost a silent no-op. The magnitude is now clamped before negation.
- [CLAUDE] Band fields were stripped by the handoff cleanup allowlist (`HANDOFF_PLAYER_FIELDS`) before the world layer could roll them, so amounts the model asked for silently vanished. Found on a live Ollama 7B run: drafted-op survival was 20% against a 100% baseline; now 100%.
- [CLAUDE] Server-computed amounts were re-rolled as if the model had guessed them — a skill-check injury of −1 HP was re-read as a band hint and rolled into an unrelated number. Amounts the server already rolled are marked `_server_authored` and pass through untouched.
- [CLAUDE] An unrecognized band word (a 7B wrote `"health_band": "fresh"`) normalized to `none` and silently deleted the change. Unknown words now resolve as `small`, since the model clearly intended something to happen.
- [CLAUDE] Turn dice were attached to the discarded `result` dict rather than the returned state, so no caller could ever read them. They now surface as `state.dice_rolls` and at the top level of the `play_turn` payload beside `skill_checks`.

### Changed — local-model turn pipeline

Measured on Ollama `qwen2.5:7b-instruct` over 30-turn runs. The JSON verify and
depth-retry passes never once succeeded on a 7B, yet consumed 89% of wall-clock.

- [CLAUDE] Short narration no longer blocks the verification skip. The consistency verifier cannot lengthen prose — that is the depth retry's job — so forcing it there cost ~26s per turn to accomplish nothing. The certainty penalty is retained.
- [CLAUDE] The depth retry now asks for **prose only** and splices it into the existing turn, instead of requesting a whole replacement turn JSON. The old form truncated mid-object on 18/18 attempts (the full schema does not fit the response cap) and risked discarding the draft's structured ops. Prose cannot truncate into invalid JSON and leaves all state changes untouched. Output is clamped to `MAX_TURN_NARRATION_CHARS` on paragraph boundaries.
- [CLAUDE] Added a **verifier circuit breaker**: after `AI_RPG_VERIFY_FAILURE_LIMIT` (default 3) consecutive unusable verify results, the pass is skipped for the session. Detects the characteristic small-model failure — echoing the input `world_state` back as the answer, which parses as valid JSON. Resets on any success, so models where verification works are unaffected. Set the limit to `0` to never trip.
- [CLAUDE] `conversations` demoted from `HIGH_RISK_TURN_CHANGE_KEYS`: recording a topic and summary mints nothing and cannot unbalance a run, but it was the most common reason verification could not be skipped. Inventory, skills, events, and abilities remain high-risk.
- [CLAUDE] The skill catalog is now **searched, not dumped**. `search_skills()` ranks by trigger regex, name/code tokens, tags, and prefix stems; `gm_context_block(query=...)` ships only the matches plus a small always-valid fallback. Was 60 skills / ~6.4KB / ~1,600 tokens in every prompt, on a model that no longer picks skills because checks resolve server-side. The catalog is also no longer persisted into `playthrough_options`, which had been re-sending it inside every turn prompt indefinitely.

### Changed — turn-to-turn continuity

A qualitative audit of the 30-turn run found the prose good and NPC memory
excellent (149 code references, 100% name/code accuracy, four durable recurring
NPCs) but three kinds of state quietly not maintained. All three are server-known
facts, so all three moved to the server.

- [CLAUDE] **Movement is now a server contract, not a hope.** The model emitted **0 `MOVE` and 0 `LOC_NEW` ops across 30 turns** and eight explicit travel actions: prose described leaving town, the player never left the starting tile, and the world stayed one location wide (`visit_count` 1) forever. Added `movement_contract()` to the turn packet (current location, valid destination codes, and the required field, with the destination list only sent on travel turns) plus a required-op line in the DSL instruction block. Backed by `resolve_movement()`, which fills a missing `MOVE` from evidence the model itself produced this turn — a place it minted (`LOC_NEW`), a known place the player named in their own input, or an `[[L#]]` in the narration's tail alongside arrival language — and journals whichever rule fired. A travel turn that resolves nowhere is journaled too, rather than passing silently.
- [CLAUDE] Intent classification now stems inflected verbs and counts travel as a *secondary* intent. `"keep walking east"` scored zero for travel and classified as `general`; `"I keep walking east, watching the treeline"` ties into `investigation` because keyword-table order breaks ties. Both are travel turns, and both are exactly the input the movement contract needs.
- [CLAUDE] **Narration person and player pronouns are locked.** 22 of 30 turns opened in second person, 11 in third; the player character — declared sex `unspecified` — drew 21 he/his sentences against 12 she/her. `narrative_voice_contract()` states the point of view and the pronoun set (male/female when clearly stated, otherwise they/them) as server truth in every packet, with the long-form rule in the cached system prompt. `check_narrative_voice()` measures drift per turn and surfaces it as `state.voice_check`; a narration that never once says "you" triggers one prose-only rewrite (`AI_RPG_VOICE_REPAIR=0` to disable). Pronoun counts are reported but not auto-rewritten: NPCs have genders too, so a regex pass would break more prose than it fixed.
- [CLAUDE] **Description-only NPC names rejected.** One NPC was recorded with the literal name `"Woman"` (code `C`) and referred to as "a tall woman [[C]]" for the rest of the run. `is_generic_person_label()` now rejects article + modifier + generic-head labels ("Woman", "Old Man", "The Hooded Figure", "Guard", "Cloaked Stranger") while keeping any name carrying a real proper-noun token ("Old Mara", "Captain Vesk", "Guard Aria"). Existing repair machinery renames them and rewrites the prose.

### Added — venues

- [CLAUDE] **Shops are real places now.** A live probe (`tools/playtest_venues.py`) walked into an
  apothecary on a square, talked to the keeper, stepped out and went back in: the database recorded
  **one location and zero movement** across all four turns, because a shop was only ever prose.
  Walking two locations away and asking to return minted a **new top-level place** called
  "Apothecary", unrelated to the square, and put the player inside it in a single move, at night.
  The keeper was Jethook, then "a woman with a kind face", then "a man in worn clothes".
- [CLAUDE] A venue is a row in `locations` with `parent_id` (the place you enter it from), `kind`,
  `open_minute`/`close_minute`, `settlement_size` and `keeper_npc_id`. Keeping venues in the same
  table means movement, visit counts, entity codes, the map and export/import all keep working —
  entering a shop is an ordinary move. Existing saves migrate additively; verified against a
  hand-built pre-venue database with rows intact.
- [CLAUDE] **Containment.** `gate_venue_move()` runs at the one point a move is applied, so every
  path goes through it. Entering from anywhere but the parent redirects the move *to* the parent —
  the journey happens, and going inside costs the next turn. No more teleporting into an interior.
- [CLAUDE] **Opening hours** against the world clock, wrap-aware: a tavern open 11:00–02:00 is open
  at 01:00 and shut at 03:00. A closed venue leaves the player outside and journals the hours.
- [CLAUDE] **Commonality.** A hamlet has no apothecary and a town has no counting house; each kind
  is capped per settlement (two apothecaries, four taverns). A refused venue is never created — the
  player simply finds no such shop instead of one materialising on request.
- [CLAUDE] **Keeper identity** is pinned per venue and never reassigned, and rides in the turn packet
  with an explicit instruction not to introduce a different keeper.
- [CLAUDE] Interiors are excluded from `known_places` in the movement contract and listed separately
  under `venues_here` with their open/closed state. Listing them as travel destinations was itself an
  invitation to walk into a shop from across the map.
- [CLAUDE] **Trap:** `settlement_size_for()` must not write. It runs from `get_state`, a read path;
  persisting the inferred size there opened a write inside another transaction and deadlocked the
  database — the suite went 3s → 25s with four "database is locked" failures.
- [CLAUDE] **A doorway is a move, and the model does not record it.** Server-side containment alone
  left the shop unrecorded: across a scripted probe the model narrated stepping inside, talking to
  the keeper, stepping out and going back in, and emitted no MOVE for any of it — the same failure
  class as the original travel work, and prompt guidance alone did not fix it either.
  `venue_move_intent()` detects the doorway as a phrase, and `resolve_movement` gained four
  deterministic rules: `venue_enter` (a venue here that the player's line names, by proper name or
  by trade), `venue_exit` (out to the parent), `venue_opened` (open the requested kind when the
  settlement supports it and none exists yet), and `venue_return` — naming a venue from two locations
  away aims the move at the shop and lets the entry gate land the player at its door, so the journey
  home happens this turn and going inside costs the next. Only the player's own words can open a
  venue — letting the narration do it would drop a shop wherever the prose drifted.
- [CLAUDE] The doorway detector is phrase-level on purpose. Adding "in"/"out" to the travel keyword
  set turned "I put the coin in my pocket" and "I hand out the flyers" into travel turns; the phrase
  form scores 12/12 on those cases with no false positives.
- [CLAUDE] `tools/make_debug_save.py` + `data/debug-save.json` — an importable world with things
  already in it: level 5, 86 gold, 8 items (4 equipped, one 40 lb so carry limits are reachable),
  4 abilities including one locked behind a prerequisite, 5 skills, part-spent resources, and three
  venues on one square with bound keepers. Note that without `playthrough_options` in settings the
  mana pool is force-zeroed to 0/0 regardless of the player row, which is why the save writes them.
- [CLAUDE] `tests/test_venues.py` (30 tests) and `docs/Venues.md`.

### Fixed — test isolation, and what it was hiding

- [CLAUDE] **The test suite was writing into the player's real save.** Every runtime path
  (`app/db.py` `DB_PATH`, plus `HISTORY_SUMMARY_PATH`, `SOURCE_INDEX_DIR`, `MODEL_TRACE_DIR`,
  `CONSOLIDATED_FACTS_PATH`, `CAMPAIGN_SLOTS_DIR` in `app/world.py`, and the idea-bank and
  launcher-prefs paths) was a module-level `Path(os.getenv(...))` constant, frozen by whichever
  module imported it first. Tests set `AI_RPG_DB` at import time, but under
  `unittest discover` an alphabetically earlier test file imports `app.db` before they run, so
  the env var was ignored and fixtures landed in `data/world.db` — 26 locations and 180 NPCs of
  test data, including places literally named "Alpha Town" and "Beta Town". All of these are now
  functions (`db_path()`, `source_index_dir()`, `model_trace_dir()`, …) that re-read the
  environment per call. Do not reintroduce module-level path constants under `data/`.
- [CLAUDE] The env vars are process-global, so lazy resolution alone was not enough: the module
  imported *last* still owned the database while everyone's tests ran. Isolated test modules now
  re-apply their paths in `setUpModule()` and assert the resolved paths sit inside their temp dir,
  so a regression fails loudly instead of silently corrupting a save.
- [CLAUDE] **127 tests were passing vacuously.** Most files in `tests/` are bare
  `def test_*(): assert ...` functions with no `TestCase`, so `unittest discover` collected **zero**
  tests from them; pytest would collect them but is not installed here, and those files never
  isolate their paths either. `tests/test_bare_assert_files.py` imports them under isolated paths
  and wraps every zero-argument `test_*` in a generated `TestCase`. Suite went 170 → **297 tests**.
- [CLAUDE] **A non-isekai character was being rewritten into a transmigrated one.**
  `detect_origin_register()` tested modern markers *before* local ones, so one ambiguous word beat
  explicit local context: "a compound clerk who tallies grain fees at the gate office" matched
  "office", was classified Earth-modern, and came back as *"Death found them as a community theater
  stagehand … Arrival was Cragwatch Barracks Gate in another world"* — with `backstory_mode` flipped
  from `known` to `transmigrated`. Classification is now scored, with a decisive-marker set for
  terms that settle it alone ("smartphone", "salaryman", "truck-kun") and weight-of-evidence for
  ambiguous ones ("office", "chrome", "drone", "college").
- [CLAUDE] **The path named `stitch_arrival_keep_former_life` did not keep the former life.**
  `build_transmigration_backstory()` uses `old_story` only as a *ban list*, so the player's own
  history was the one thing it avoided reusing: "a maintenance technician in a near-future city"
  came back as "a kindergarten aide with glitter in every coat pocket". Added
  `former_life_phrase()` and a `keep_former_life` argument; when a story already establishes a
  former world life and only lacks the transport and arrival beats, those are appended and the
  person is kept. Native fantasy plots (disgraced noble / festival guest) are still fully rewritten.
- [CLAUDE] **The backstory gate failed the generator's own output.** `has_arrival_place` was a flat
  phrase list, so "when awareness returned they were at a lantern-lit market lane" — a phrase from
  the composer's own `_TX_ARRIVALS` bank — scored `missing_arrival_place`. Added a structural route:
  an awareness cue and a place in the same sentence. It does not fire on former-life place mentions
  ("they worked in a city office"), and the original phrase list still passes on its own.
- [CLAUDE] **Every repaired backstory was identical, and unreproducible.** The rewrite seed was
  `abs(hash(text))` — randomized per process, so a save could not reproduce its own backstory, and
  keyed on the story alone, so `idea` and `world_style` changed nothing: 1 distinct story in 14
  draws. Now a blake2b digest of story + idea + world style: **10/10 distinct**, and stable across
  `PYTHONHASHSEED`. The last three `hash()`-derived seeds in the codebase (wait-event rolls in
  `app/world.py`, idea-bank card ids) went with it — none remain.
- [CLAUDE] **Pocket contents did not belong to the job that produced them.** Job and pocket were
  drawn independently, so a public-library assistant arrived carrying "a red pen, lesson notes in a
  tote" — a teacher's kit. Pockets are now selected by job affinity, with job-neutral options always
  available so coherence costs no variety; all 30 jobs have a tailored match and no pocket text was
  dropped.
- [CLAUDE] Generated backstories had visible grammar faults: five former-life templates hardcoded
  `a {job}`, producing "a apartment-building super" / "a airport baggage handler" (and any
  vowel-initial life a player writes), and the localize path stripped the trailing period before
  appending, producing run-ons like "They kept to the yard gates Known locally as an ordinary
  compound laborer." Added `_article_for()` and `_sentence_join()`; the default vocation fallback
  is itself vowel-initial, so the article fault fired on the default path.
- [CLAUDE] `tests/test_setup_quality.py` — 19 regression tests covering all of the above: former
  life preserved vs. clichéd plots replaced, scored origin classification, arrival detection and
  its false-positive guard, seed variety and cross-process stability, an AST check that no
  `hash()`-derived seed returns, pocket/job coherence, article agreement, and run-on prevention.

- [CLAUDE] Five test assertions were stale rather than broken, and were updated to the contracts
  that actually hold: entity-name repair inserts an `[[A]]` tag between name and verb; the
  transmigration keyword list is superseded by the module's own scorer; `special_ability_origin` is
  legacy and popped before sanitization, so per-card locks pass through and locking is decided by
  `assign_ability_locks_after_creation` (probabilistic for mild powers, always for strong ones); and
  a stale `origin="none"` no longer wipes real ability cards, since list emptiness is now the source
  of truth.

### Fixed — found by live 7B testing

Six 24-turn runs on Ollama `qwen2.5:7b-instruct`. Every item below is a defect the
harness caught, not a speculative hardening.

- [CLAUDE] **`movement_contract` and `narrative_voice` never reached the model.** `HANDOFF_BASE_CONTEXT_KEYS` is an allowlist, and keys missing from it are nulled out of the packet — the prompt literally read `"movement_contract":null`. Identical in kind to the band-field bug fixed earlier in this release. Adding the two keys took model-emitted `MOVE` ops from 0 to 3 in a five-turn smoke test.
- [CLAUDE] **The model invented destination codes.** With only `L1` in the world it wrote `MOVE L2`; `_find_location_id()` resolves an unknown `L`-code back to the *current* location, so three consecutive travel turns reported success while the player never left the gate. Unknown and self-referential codes are now rejected before they reach the database, and the turn falls through to repair.
- [CLAUDE] **Movement now asks for place names, not codes.** Given a list of valid codes, the model reused the nearest one as a stand-in for anywhere new: it narrated a river valley while recording a move back to town, on 8 of 11 moves in one run. `move_to_location` already resolves by name against existing places, so codes only enabled the failure. Switching the contract to `known_places` (names) took locations-per-run from 2 to 4 and prose/state mismatches from 8 to **0**. `_match_location_by_name()` matches case- and article-insensitively so "the Redmill Ford" cannot mint a twin of "Redmill Ford".
- [CLAUDE] **The model narrated deliberation instead of the action.** Travel turns ended "Do you approach the figure, or continue toward the ruins? The choice is yours." — the player had already chosen, and the scene never moved. A resolve-the-action rule in `PROSE_VOICE` and the DSL prompt took travel turns that actually moved from 25% to 83%.
- [CLAUDE] Menu closers and trailing option lists are now trimmed deterministically (`_trim_menu_ending`, `_trim_option_list`). Prompting alone did not shift the behaviour; since the UI already asks the player what to do, these carry no information. Menu endings 25% → **8%**, bullet menus 21% → **0%**, at zero extra model passes. Perception phrasing ("you could hear the mill wheel") is explicitly excluded, lists with prose under them are left alone, and nothing is trimmed below the narration floor.
- [CLAUDE] **One typo'd opcode discarded the whole turn.** An unrecognized op raised, so a single `MOV` threw away every other op in that turn. `OPCODE_ALIASES` maps near-misses (`MOV`, `GOTO`, `LOCNEW`, `GIVE`, `EXP`, …) onto the closed list, unknown lines are skipped instead of fatal, and a block where *nothing* parses still raises so the wrong output format still retries.
- [CLAUDE] Slug destinations reached the player's map: a live run displayed a location named `east_road`. `humanize_place_name()` normalizes separators and case at both the upsert and lookup sites, so "east_road" and "East Road" are one place called **East Road**.
- [CLAUDE] Two repaired NPCs were both named "Saltbin" — the shell-name pool is 20x20 and collides readily. `unique_person_name()` re-rolls deterministically against live NPC names.
- [CLAUDE] `state.movement` and `state.voice_check` were dropped on roughly half of turns: `play_turn` re-reads state from the database on the injuries path, discarding what `apply_turn` had annotated. Telemetry is now carried across the refresh.

### Fixed — world variety (found by live 7B testing)

Prose read well but the *world* did not: the same person and the same place kept
being reinvented under slightly different labels.

- [CLAUDE] **Every NPC was a hooded stranger.** 24 of 27 NPCs across three runs had the role "hooded stranger" or "cloaked local", because the prose-seeded NPC roles came from a fixed four-item cycle starting with those two — and a scene rarely seeds more than two faces. It also fed back on itself: the seeder wrote hooded strangers into the cast, the cast went into the next prompt, and the model kept writing hooded figures for the seeder to catch. Roles now come from location-aware occupation pools (`_SEED_ROLE_POOLS`: indoor / water / wilderness / settlement, chosen by *scored* keyword match so a town summary mentioning "the road" no longer staffs a gate-town with charcoal burners), never repeat a role already standing in that place, and are seeded deterministically. Appearance moved to the summary where it belongs, so a baker can still be wearing a hood. Measured: appearance-as-role **24/27 → 0**, distinct roles **4/11 → 11/11**.
- [CLAUDE] **Duplicate people.** The shell-name pool is 20×20 and the collision check was scoped to one location, so a run produced three separate people called "Grainwick". All four name generators now go through `unique_person_name()` / `_person_name_taken()` against the whole world.
- [CLAUDE] **Duplicate people, model-supplied.** `_upsert_npc` matched existing NPCs by name *within a location*, so "Aria the baker" at the gate and "Aria the baker" at the camp became two characters. One name is one person; the match is now world-wide and moves them, since NPCs legitimately travel.
- [CLAUDE] **Compounding place names.** A run produced Riverbend Camp, Riverbend Hillcrest, Riverbend Hillcrest Camp and Riverbend Hillcrest Post — four map entries for one area the player cannot tell apart. `_place_extension_target()` folds a name that is an existing name plus one or two generic tail nouns ("Camp", "Post", "Road") back into the original, and `_match_location_by_name()` also strips leading descriptors so "Old Ruins by the River" is not a second "Ruins by the River". A distinctive addition ("Riverbend Chapel") is still its own place.
- [CLAUDE] **Directions recorded as places.** `MOVE East` put a location literally named "East" on the map. Bare headings and relative positions are rejected as place names; real names containing a direction ("East Road", "Northolt", "Eastern Reach") are unaffected.
- [CLAUDE] **The anti-repetition block was banning the cast.** It was built from raw word frequency, so a turn spent talking to Larkcoil at Redmill Ford came back instructing the model to avoid "larkcoil", "redmill", "ford" — telling the narrator to stop naming its own world, directly against the continuity work. Entity names are now protected at two layers, and `narration_tics()` adds run-wide tics: words like "hooded" recur just under once per turn, which never trips a single-turn threshold yet is exactly what makes twenty-four scenes read the same.
- [CLAUDE] Two more `hash()`-seeded name generators (the ruler spawner and the local-cast seeder) made deterministic. No randomized `hash()` seeds remain in `app/world.py` or `app/llm.py`.
- [CLAUDE] Prompt rules to stop the behaviour at source: NPC roles are occupations not appearances, at most one genuinely mysterious watcher on screen, and a new place needs its own name rather than a known one with a word bolted on.

### Fixed — continuity

- [CLAUDE] Replacement NPC names were seeded from Python's `hash()`, which is randomized per process — the same corrupt save renamed the same NPC to a different person on every reload, and a rewind could not reproduce a face. Now seeded through blake2b via `name_seed()`, matching the dice authority.
- [CLAUDE] The travel-ready heuristic only checked `move_to_location`, so a move expressed as `move_to_location_code` left travel unlocked during a walk.
- [CLAUDE] `tests/test_continuity.py` — 57 regression tests across generic-name rejection, cross-process seed stability, replacement-name collisions, travel-intent stemming, every `resolve_movement` outcome plus the invented-code / same-place / prose-mismatch guards, narration place extraction, place-name hygiene and duplicate prevention, opcode aliasing, menu and option-list trimming (including the prose it must *not* touch), pronoun defaults, drift detection, and the voice-repair gate.
- [CLAUDE] `tools/playtest_continuity.py` — live 7B harness measuring movement resolution, point-of-view drift, NPC name quality, menu endings, and opcode census alongside story health, so a continuity fix that flattened the prose would still show up.

### Verified

- [CLAUDE] Live run on Ollama `qwen2.5:7b-instruct` (7.6B Q4_K_M): opening + 6 turns, **0 fallbacks, 0 errors**, 100% band compliance across 80 emitted amount fields, 16 server rolls. Harnesses: `tools/playtest_7b_bands.py`, `tools/check_trace_ops_survival.py`, `tools/playtest_ops_baseline.py`.
- [CLAUDE] 30-turn consistency run, before → after the pipeline changes above:

  | metric | before | after |
  | --- | ---: | ---: |
  | median narration chars | 888 | **1993** |
  | turns below the 1000-char floor | 18/30 (60%) | **0/30 (0%)** |
  | narration trend | −3.6/turn (flat, n.s.) | **+22.5/turn, 95% CI [+5.4, +39.6]** |
  | mean turn time | ~53s | **~19s** |
  | wall clock for 30 turns | 27.5 min | **10.9 min** |
  | prompt tokens | ~7,400 | **~6,200** |
  | fallbacks / exceptions | 0 / 0 | 0 / 0 |

  The database was never the constraint: across the run DB rows grew 15 → 204 while prompt size stayed bounded (context caps hold; the shipped share of `prompt_context` falls as the world fills). Harness: `tools/playtest_7b_longrun.py`, analysis: `tools/analyze_prompt_budget.py`.

- [CLAUDE] Continuity, 30-turn baseline → 24-turn run after the fixes above, same model. Harness: `tools/playtest_continuity.py`.

  | metric | baseline | after |
  | --- | ---: | ---: |
  | travel turns that changed location | 0/8 (0%) | **10/12 (83%)** |
  | model-emitted `MOVE` ops | 0 | **10** |
  | locations in the world | 1 | **4** |
  | narration in third person | 11/30 (37%) | **0/24 (0%)** |
  | description-only NPC names | 1 ("Woman") | **0/11** |
  | turns ending in a choice menu | not measured | 3/24 (12%) |
  | turns ending in a bullet menu | not measured | **0/24** |
  | prose naming a place the state did not record | 8/11 moves | **0** |
  | narration below the 1000-char floor | 0/30 | **0/24** |
  | fallbacks / exceptions | 0 / 0 | **0 / 0** |
  | mean turn time | ~19s | **~13s** |

  Story health held while continuity was fixed: median narration 1993 → 1874 characters with no turn under the floor, and prose quality checked by reading full scenes rather than counting characters.

  World variety, before → after the variety fixes (24-turn runs):

  Aggregated over three 24-turn runs (72 turns) after all fixes, against the
  matching before-runs. The menu detector was itself corrected mid-testing — it
  had been counting NPC dialogue and descriptive prose — so both columns use the
  stricter one.

  | metric | before | after |
  | --- | ---: | ---: |
  | NPCs whose "role" was an appearance | 24/27 | **0/33** |
  | distinct NPC roles | 4/11 | **29/33** |
  | duplicate NPC names | 3 in one run | **0** |
  | turns ending in a choice menu | 6/24 (25%) | **6/72 (8%)** |
  | near-duplicate place names | 4 "Riverbend …" entries | **0** |
  | travel turns that moved | 0/8 | **28/36 (78%)** |
  | prose/state mismatches | 8/11 moves | **0** |
  | narrative person drift | 11/30 | **0/72** |
  | narration below the floor | 0/30 | **0/72** |
  | fallbacks / exceptions | 0 / 0 | **0 / 0** |

---

## [0.9.0-beta] - 2026-07-26

> **Beta** from branch `test/morkyn-0.9-wip`. Playable preview of the 0.9 line — expect rough edges and save-format evolution before a stable 0.9.0.

### Added
- [RULES] Player **mana / energy (stamina) / fatigue** pools: turn- and terrain-based drains, wait/meditate/sleep recovery, life-force–scaled fatigue cap, hard gates on power spend
- [RULES] Structured power **resource costs**, cost/prereq diversification, pure min–max **ability count RNG**, lock-after-create by strength with fair prereqs
- [FE] Resources UI + wait kinds; art path: Forge **LoRAs + hires** always visible (not Advanced-only), persist `forge_active_loras`
- [SETUP] Composer tree, starter-logic, idea bank seeds, setup crosscheck matrix
- [SETUP] **g13 sanitation**: post-randomize bool coercion, `magic_level` enum + aliases, instruction-echo strip, structure slogan clamps (`coerce_typed_setup_fields` + tests)
- [FE] Play layout stacks; Forge art gate polish

### Fixed
- [SETUP] Backstory self-contradictions (magic-as-tool vs not-wizardry) repaired by `magic_level`
- [WORLD] Entity name spam / scenery “Sky-crack first window” + button HTML strip
- [LLM] Ability cost/prereq clones and always-max count / all-locked defaults
- [FE] Missing LoRAs in simple art bar

### Changed
- [VER] App version **0.9.0-beta**
- [DOCS] `docs/TODO_NEXT.md` tracks remaining 0.9 backlog (g9/g10/g12 polish items, etc.)

### Note from 0.8.x Unreleased (still shipping in this beta line)
- [FE] Per-turn collapsed **Debug** panel; model traces under `data/model_traces/`
- [RULES] Optional **dice / skill checks** system + durable skill library
- [FE] Roll banners; color map canvas + mini-map

---

## [0.8.0] - 2026-07-19

### Added
- [FE] Calmer setup UI remodel — softer surfaces, pill controls, dim secondary buttons, corner decals, ambient background; playstyle themes (Dusk / Ember / Tide / Bloom / Ash)
- [FE] Responsive layouts: phone / tablet / desktop / wide (≥1500px step rail + side-by-side play)
- [MAP] Flat tile world v1: multi-age presets, elev 0/1 mountains, tile image archive + Forge/Comfy generate
- [IMG] Optional Forge/A1111 + ComfyUI image backends; portrait preview API
- [BILD] `Morkyn.bat` / `Morkyn.ps1` launcher (simple menu + Advanced Gatehouse); console mouse/keyboard polish
- [LLM] Cloud/agent OpenAI-compatible provider; agent bridge routes; narration pipeline quality hardens (no mid-word shreds)
- [BE] Live `GET /api/generation-progress` for splash/turn wait (phase lines + partial narration)
- [PRIV] Local-only privacy policy + optional GitHub-only updates/rollback
- [DOCS] Showcase: dual-role **100-turn** Mosswake lore teaser (`docs/showcase/`)
- [TOOLS] `benchmarks/run_dual_role_playtest.py` regenerates showcase metrics/markdown
- [FE] Release UI hides self-check / debug-trace panels (opt-in `?debug=1` or `AI_RPG_DEBUG=1`)

### Changed
- [BE] Model trace files and `debug_trace_path` are **off** unless `AI_RPG_DEBUG=1`
- [REPO] Housekeeping: root launchers/docs, `tests/`, `benchmarks/`, expanded `.gitignore`
- [VER] App version **0.8.0**

### Fixed
- [LLM] Narration pipeline no longer accepts truncated mid-word paragraphs or delete-span garbage fragments
- [BILD] Advanced menu click coordinate / jitter issues (raw INPUT_RECORD + no-scroll window size)

---

## Earlier (0.7.x summary)

Notes from the 0.7 line retained for history:

- [LLM] NAR+OPS draft DSL, adaptive narration pipeline design, Ollama `think: false`
- [DOCS] Turn metrics, ConnectAPIs, pipeline docs

### Changed
- [LLM] `generate_turn` prefers DSL draft then optional verify; depth retries only when narration is short
- [DOCS] Repository layout housekeeping: start scripts and project docs stay at root; tests → `tests/`; harnesses → `benchmarks/`; LICENSE copyright updated to Mørkyn / Stelliro
- [BILD] Launcher interactive input hardened so keyboard always works; mouse click path is best-effort without killing the menu

### Removed
- [DOCS] Transient local diagnostics (`temp_*`, empty `*_check.txt`, one-off `tools/write_readme.py` / branding fix scripts)
- [TOOLS] Renamed/removed `GROK BENCHMARK/` space-named folder in favor of `benchmarks/`

---

## [0.7.0] - 2026-07-17

> Rebrand to **Mørkyn**, long-play memory/token tools, campaign slots, combat handoff, verification memory, and UI polish.

### Added
- [BRAND] Rebranded product name, UI titles, API metadata, launchers, and documentation to **Mørkyn**
- [DOCS] Added `Media/` brand gallery (logo + key art) referenced from README
- [MEM] Hierarchical memory consolidation (`consolidate_memory`) into durable source-index facts
- [LLM] Pre-call `enforce_token_budget()` estimation and pruning
- [LLM] SQLite-backed verification memory and certainty-based selective verifier skipping
- [GPLAY] Deterministic NPC combat profiles and player-attack damage handoff before narration
- [GM] Lightweight deterministic off-screen GM event ticks (no extra LLM call)
- [BE] Named campaign save slots under `data/campaign_slots/` with list/save/load/delete APIs
- [FE] Context-health card, consolidate control, compact mode, campaign slot buttons
- [LLM] Managed llama.cpp startup from Model Settings test flow; per-turn model trace exports
- [FE] Startup heartbeat and turn wait timers for long local-model operations
- [TEST] Runnable `behavior_test.py` regression suite

### Changed
- [BE] App version metadata `V0.7.0`
- [LLM] Source-index scoring: keyword fit + recency + importance
- [LLM] Explicit agentic Observe ΓåÆ Plan GM events ΓåÆ Scene plan ΓåÆ Narrate ΓåÆ Self-check chain
- [FE] Model Settings exposes provider/URL fields; Soft Token Target naming
- [LLM] Handoff cleanup between planner, draft, verifier, and world application
- [SEC] Ignore rules exclude local saves, DB sidecars, traces, env variants, model binaries

### Fixed
- [LLM] Draft repair timeouts salvage narration instead of immediate fallback
- [FE] Fallback notices no longer claim missing narration when fallback prose exists
- [LLM] Refused model-server connections reported accurately
- [BILD] Launcher reuses saved GGUF paths on next launch
- [LLM] Default provider alignment and managed llama.cpp startup/status initialization
- [LLM] Setup/turn auto-start + retry when llama.cpp is not yet listening

---

## [0.6.0] - 2026-05-13

> Public pre-1.0 release. This is a featureful local prototype with durable state, focused LLM context, LAN/VPN launch options, regeneration, hidden GM context, setup persistence, and equipment-derived capabilities.

### Added
- [DOCS] Added a strict non-commercial license reference allowing non-commercial forks and modified uploads - licensing
- [GPLAY] Added equipped-item stat modifiers and item-granted abilities that derive into player stats and abilities only while equipped - equipment effects
- [LLM] Added action-specific context segments and focused player capability slices for movement, combat, abilities, and other turn intents - turn generation
- [FE] Added high-visibility turn reward banners for applied XP and item gains - browser UI
- [BILD] Added a VPN/private-overlay launch mode with port selection and VPN URL detection - startup
- [GPLAY] Added current and previous-life age/sex fields to character creation - setup identity
- [BILD] Added local-only and local-network launch modes for phone access - startup
- [FE] Added responsive phone, landscape mobile, and small-monitor layout rules - browser UI
- [GM] Added backend-only hidden GM events for between-turn consequences and off-screen reactions - hidden world context
- [FE] Added paged, collapsed visual history with persisted expansion choices - browser UI
- [UI] Added full-page start splash with progress lines and animated opening narration reveal - setup flow
- [FE] Added compact scene plan readout for high-level model focus points after generated turns - browser UI
- [GPLAY] Added event lifecycle metadata for temporary, recurring, traveling, background, and persistent location events - world events
- [LLM] Added deterministic turn context planning to focus prompts by intent, working set, and verifier risk checks - turn generation
- [FE] Added setup settings save/load with comma-separated Custom Proficiencies guidance and normalization - setup UI
- [GPLAY] Added latest-response regeneration for opening, continue, and player turns - turn tools

### Changed
- [BE] Changed app version metadata to `V0.6.0` for the public pre-1.0 release - API surface
- [BILD] Changed launcher and model defaults to avoid machine-specific GGUF paths and rely on `AI_RPG_GGUF_MODEL` or UI model selection - startup
- [DOCS] Reworked README for public release clarity while keeping setup, model, LAN/VPN, data, and license notes concise - documentation
- [LLM] Split response cap and hard cap token settings with editable model controls and larger repair defaults - model settings
- [LLM] Changed turn prompts and source-index generation so raw journal history stays visual-only and model memory uses structured records - prompt context
- [FE] Changed opening narration reveal timing to stay visible longer after setup generation completes - setup flow
- [LLM] Changed turn prompts to request a 1-6 focus point scene plan and continuous prose narration - prompt contract
- [FE] Changed current turn rendering to join model narration chunks into one continuous prose flow - browser UI
- [BILD] Changed managed llama.cpp launcher logs to quiet temp files by default with `AI_RPG_LLM_LOG_MODE=console` opt-in - startup
- [GPLAY] Changed new playthrough setup to stop seeding default player skills and let skills emerge through play or explicit custom rules - setup system
- [DOCS] Made `.github` Copilot instructions project-specific and referenced instruction files in the codebase index - AI workflow

### Fixed
- [BE] Fixed setup 422 responses from null or invalid mobile form values by normalizing setup payloads before validation - setup API
- [BILD] Fixed local-network launcher URL selection to prefer Wi-Fi/Ethernet over VPN or virtual adapter addresses - startup
- [LLM] Fixed local llama.cpp turn fallbacks from slow drafts by raising phase-specific timeouts and logging prompt diagnostics - model adapter
- [LLM] Fixed malformed turn JSON repair using too small a repair token budget before fallback - model adapter
- [LLM] Fixed setup randomizer 503s by returning deterministic backend fallback fields when model setup JSON is invalid or unavailable - setup randomization
- [BILD] Fixed launcher startup race by waiting for llama.cpp readiness before opening the app - startup
- [BE] Fixed `/api/version` health checks by returning local app and planner version metadata - API surface
- [LLM] Fixed the turn planner packet version string to use `V0.1.0` - turn generation
- [LLM] Fixed deterministic fallback when turn JSON contains salvageable or verifier-omitted narration - turn generation
- [LLM] Fixed context-length fallback by raising the managed llama.cpp default context and adding compact turn retries - model adapter

### Removed
- [GM] Removed the visible GM tab while keeping hidden GM context backend-only - browser UI

---

## [0.1.0] - 2026-05-13

> First tracked release. Establishes the current local AI RPG prototype baseline.

### Added
- [ARCH] Established FastAPI backend with plain browser UI served from `/` - app shell
- [DATA] Added SQLite world database with persistent locations, player, NPCs, relationships, inventory, skills, abilities, events, conversations, aliases, karma history, summaries, model logs, journal, settings, and GM notes - world state
- [LLM] Added local LLM integration for Ollama-compatible and llama.cpp-compatible JSON generation - model adapter
- [LLM] Added draft plus verifier turn flow with JSON repair and fallback narration - turn generation
- [GPLAY] Added configurable playthrough setup for character identity, backstory, world style, rules, abilities, economy, magic, tech, quests, NPC density, factions, skills, and progression - setup system
- [GPLAY] Added structured turn application for player stats, karma, skills, inventory, equipment, capacity modifiers, locations, NPCs, relationships, events, conversations, claim checks, and journal entries - world engine
- [DATA] Added stable entity references for NPCs, locations, items, and events with clickable UI references - indexing
- [DATA] Added compact turn summaries, source-index search, active-location relevance, and World Bible summary views - memory retrieval
- [GPLAY] Added player-created entity aliases and player identity aliases with activation and disguise state - alias system
- [GPLAY] Added one-turn rewind using delta snapshots plus export/import through `ai-rpg-world-v1` JSON - persistence tools
- [GM] Added hidden GM notes for model context and a GM tab for playtesting - GM tooling
- [FE] Added setup wizard, current turn view, history and index panes, inventory display, model settings, search, suggestions, rewind controls, import, and export - browser UI
- [BILD] Added Windows launch scripts that install missing dependencies, start a managed llama.cpp server when configured, start Uvicorn, and open the browser - local launcher
- [DOCS] Added README, CODEBASE_INDEX.md, CHANGELOG.md, and environment example documentation - project documentation

---

<!--
  HOW TO USE THIS FILE
  ====================

  1. Every functional code change gets one line under [Unreleased].
  2. Prefix each entry with the responsible agent ID in brackets, such as [ARCH], [FE], [BE], [DATA], [LLM], [GPLAY], [GM], [BILD], [DOCS], or [TEST].
  3. Use the correct category:
       Added   - new feature, system, file, endpoint, screen
       Changed - modified behavior, API, schema, config
       Fixed   - bug fix, crash fix, logic correction
       Removed - deletion, deprecation cleanup
  4. Skip formatting-only churn. Include docs when they change contributor workflow or project operation.
  5. When releasing: rename [Unreleased] to the new version and release date, then add a fresh [Unreleased] above it.
-->
