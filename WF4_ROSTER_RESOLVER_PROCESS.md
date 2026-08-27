# WF4 — Resolve model text against the roster before minting

## Goal

Three subsystems accept a free-text name from the model, fail an exact-match lookup, and silently create a new entry. Each already carries the synonym data that would have matched — unused. Route them through one conservative resolver that returns a canonical id or nothing, and mint only on a genuine miss.

The skill half is urgent: **every improvised skill currently rolls INTELLIGENCE**, which silently distorts play.

| ID | Severity | Domain | One-line defect |
|----|----------|--------|-----------------|
| 1 skill-attr | **high** | correctness | Every minted skill defaults `attribute="intelligence"`; lockpicking rolls INT |
| 2 skill-desc | high | correctness | Minted skills inherit an unrelated description from a similarity score computed on defaulted fields |
| 3 skill-name | med | correctness | Minted skill name is the raw model string (`pick_lock`, `hotwire the truck`), shown in the UI |
| 4 skill-roster | ~~high~~ **WITHDRAWN** | correctness | ~~The narrator is never shown the 60 built-in skills~~ — FALSE. All 60 ship in every draft and verify prompt at `world_state.settings.playthrough_options.skill_check_settings.enabled_skill_codes`, inside `settings`, which is a base keep key. Only the prompt's *guidance* was wrong. |
| 5 slot-accepts | med | correctness | `_slot_by_ref` is exact-match; the slot's own `accepts` list is never consulted |
| 6 enum-centre | low | output quality | Off-roster enum synonyms collapse to the midpoint, not the nearest value |
| 7 attr-drift | low | correctness | Two attribute alias tables disagree (`awareness`/`stamina` vs `perception`) |

## Measured

A conservative resolver (exact code → codeified → name → unambiguous tag → existing regex table) resolves **17 of 23** realistic narrator strings without minting, up from 10 without the regex stage:

```
pick the lock        -> lockpicking     attr=dexterity   (was: MINT, attr=intelligence)
sneak past the guard -> stealth         attr=dexterity   (was: MINT, attr=intelligence)
calm the horse       -> animal_handling attr=wisdom      (was: MINT, attr=intelligence)
forge the seal       -> smithing        attr=strength    (was: MINT, attr=intelligence)
```

Still minting, correctly or otherwise: `lying`, `patch the wound`, `hotwire the truck`, `void surgery`, `shove the door`, `navigate the dunes`. The last two are gaps in the regex table, not the resolver — see Step 7.

## Sources

| Source | Path | Role |
|--------|------|------|
| The mint site | `app/skill_checks.py:816` | `register_or_adjust_skill({"name": skill_code, ...})` |
| The graft | `app/skill_checks.py:489` | `f"Related to {best['name']}: {best['description']}"` |
| False similarity | `app/skill_checks.py` `skill_similarity` | Scores `category`/`attribute` that `_skill_row` defaulted moments earlier |
| The defaults | `app/skill_checks.py` `_skill_row` | `category="general"`, `attribute="intelligence"` |
| Unused synonyms | `app/skill_checks.py` `BUILTIN_SKILLS` | All 60 carry `tags`; 174 distinct, only 8 ambiguous |
| Existing regex table | `app/skill_checks.py:1105` | `pairs` inside `infer_check_from_action` — local, not reusable |
| Free-text entry | `app/world.py:10872` | `skill_code=... or item.get("skill") or "general"` |
| The invitation | `app/prompts.py:412` | `"skill": "lying/speech/insight/etc"` |
| Packet contents | `app/llm.py:1159` | `compact["skills"]` — the player's 12, never the library |
| Slot lookup | `app/world.py:8460` | `_slot_by_ref` — exact match on code/name only |
| Slot roster | `app/world.py:188` | `DEFAULT_EQUIPMENT_SLOTS`, each with `accepts` |
| **The correct pattern** | `app/image_backends.py:3264` | `_ZONE_ALIASES` / `_CATEGORY_ALIASES` — copy this shape |

## Context

- **The fix template is already in the repo.** Wardrobe maps arbitrary model text onto a canonical roster via alias tables, consulted at every parse branch. Skills and slots need the same thing; both already hold the alias data (`tags`, `accepts`).
- `skill_similarity` scoring `category` + `attribute` gives 0.45 against the 0.35 threshold **from defaults alone**, so the graft always fires and always picks a general-category skill. Every improvised skill in a campaign ends up described "Related to General Check: Fallback when no specialized skill fits."
- Minting itself is wanted — skills discovered in play are a feature. The bug is minting when the roster already had the answer, and minting dishonestly when it did not.
- Slot minting is also **deliberate** (`app/prompts.py:275`), and the slot roster **is** in the packet (`app/llm.py:1164`). Finding 5 is narrower than the skill findings: it only bites when the model uses `slot_name` — which `app/prompts.py:326` explicitly invites with `"slot name if code unknown"`.
- There are **no tests under `tests/` for the skill system at all**. Only `tools/audit_skills_8b.py` and `tools/probe_skill_math_8b.py`, neither asserting anything about names, descriptions, or attributes.

## Constraints

- **No substring matching.** Word-start anchored or whole-word only. The `picking`/`king` and `sector`/`sect` bugs came from exactly that shortcut; do not reintroduce it here.
- **Ambiguous tags resolve to nothing, not to a guess.** The 8 tags owned by more than one skill (`recall`, `ward`, `rite`, `omen`, `forge`, `map`, `ambush`, `spirit`) must not pick a winner.
- **Do not remove minting.** A genuinely new skill must still register.
- **A minted skill must not claim an attribute it cannot justify.** Prefer resolving; where impossible, fall back to the declared `general` check rather than asserting `intelligence`.
- **Never graft a description from an unrelated entry.** Empty or an honest neutral line, not a borrowed one.
- Slot resolution must not merge slots the roster deliberately separates (`MAIN`/`OFF` both accept `weapon`, `tool`, `focus` — an ambiguous accept must not silently pick one).
- Touch map: `app/skill_checks.py`, `app/world.py`, `app/prompts.py`, `app/llm.py`, plus new `tests/`.
- Findings 6 and 7 are low severity and independent — do them last or split them out. Do not let them delay findings 1-4.

## Steps

### Step 1: Lock current behaviour with red tests
- Status: completed
- Actions:
  - Create `tests/test_skill_roster.py` — the first test file this subsystem has ever had.
  - Assert what it *should* do: `pick the lock` resolves to `lockpicking` with `attribute == "dexterity"`; a minted skill has no borrowed description; a minted skill's name is not raw snake_case.
  - All must be **red** now.
- Acceptance: Red tests naming findings 1, 2, 3.
- Verify: `./.venv/Scripts/python.exe -m unittest tests.test_skill_roster -v`

### Step 2: Hoist the regex trigger table
- Status: completed
- Actions:
  - Move the `pairs` list out of `infer_check_from_action` (`app/skill_checks.py:1105`) to a module-level `SKILL_TRIGGER_PATTERNS`.
  - `infer_check_from_action` keeps using it — behaviour must not change. Its existing callers are the regression gate.
- Acceptance: Table reusable; no behavioural change to auto-inference.
- Verify: `./.venv/Scripts/python.exe tools/audit_skills_8b.py`

### Step 3: Add the resolver
- Status: completed
- Actions:
  - Add `resolve_skill_code(text, library=None) -> str | None`, in order: exact code → `_codeify` → normalized name → unambiguous tag (exact, then whole-word inside a phrase) → `SKILL_TRIGGER_PATTERNS`.
  - Return `None` on a genuine miss. No fuzzy fallback, no "closest guess".
  - Precompute the tag index once; skip ambiguous tags.
- Acceptance: The 17/23 measurement above reproduces as a test.
- Verify: `./.venv/Scripts/python.exe -m unittest tests.test_skill_roster -v`

### Step 4: Wire it into the check path and fix the mint
- Status: completed
- Actions:
  - In `resolve_check` (`app/skill_checks.py:809`), replace `library.get(skill_code) or library.get(_codeify(skill_code))` with the resolver.
  - On a genuine miss, register with: a **humanized** name (`pick_lock` → `Pick Lock`), **no** grafted description, and resolve the roll through the `general` skill rather than asserting `intelligence`.
  - In `register_or_adjust_skill`, delete the description graft at `app/skill_checks.py:489`.
  - In `skill_similarity`, do **not** score `category`/`attribute` when the candidate's values are the `_skill_row` defaults — the score must come from real signal (tags, name tokens) or not at all.
- Acceptance: Step 1's tests go green. `void_surgery` no longer described as a general-check fallback.
- Verify: `./.venv/Scripts/python.exe -m unittest tests.test_skill_roster -v`

### Step 5: Show the narrator the roster (finding 4)
- Status: completed
- Actions:
  - Send the enabled skill codes in the turn packet, or narrow `app/prompts.py:412` from `"lying/speech/insight/etc"` to a closed instruction naming the catalogue.
  - Mind the token budget — 60 codes is not free, and `SYSTEM_PROMPT` is already ~9.1k against a shipped 8192 default that has bitten this repo before (see memory `test-harnesses-mask-shipped-defaults`). Measure the packet before and after.
  - If the budget cannot take the full list, send codes only (no descriptions) and rely on the resolver for the rest.
- Acceptance: Model-supplied skill strings hit the roster more often; packet size change recorded.
- Verify: Live rolls before/after; record mint rate for both.

### Step 6: Slots consult their own `accepts` (finding 5)
- Status: completed
- Actions:
  - Extend `_slot_by_ref` (`app/world.py:8460`) to check `accepts` after code and name fail.
  - An `accepts` word owned by more than one slot (`weapon`, `tool`, `focus` — `MAIN` and `OFF`) must **not** resolve; fall through to the existing behaviour.
  - Keep DM-created slots working — this only stops duplicates of slots that already exist.
- Acceptance: The 42/43 miss measurement inverts for unambiguous words; ambiguous ones still fall through.
- Verify: New test asserting each unambiguous `accepts` word resolves to its slot.

### Step 7: Findings 6 and 7 (low, optional)
- Status: completed
- Actions:
  - Enum centring: map obvious synonyms to the nearest roster value rather than the midpoint (`quick`→`fast`, `gradual`→`slow`, `often`→`frequent`, `verbose`→`expansive`). Each mapping needs a test; do not add a mapping you cannot defend in one sentence.
  - Alias drift: make `skill_checks._attr_score` use `content_packs.STAT_ALIASES` instead of its private copy, after checking neither loses a word the other has.
- Acceptance: One alias table for attributes; enum synonyms land on the nearest value.
- Verify: `./.venv/Scripts/python.exe -m unittest discover -s tests -q`

### Step 8: Regression + commit
- Status: completed
- Actions:
  - Run Required and Prior-lock blocks.
  - Commit findings 1-4 separately from 5, and 6-7 separately again — three commits, each with its own evidence.
- Acceptance: All green; each commit carries its measurement.
- Verify: Full Required block after the final edit.

## Done criteria

- [x] `tests/test_skill_roster.py` exists and was red first
- [x] Regex trigger table hoisted; auto-inference behaviour unchanged
- [x] `resolve_skill_code` returns `None` rather than guessing
- [x] Ambiguous tags resolve to nothing
- [x] No substring matching anywhere in the resolver
- [x] Minted skills carry a humanized name
- [x] Description graft removed
- [x] `skill_similarity` no longer scores defaulted fields
- [x] Improvised skills no longer silently roll INTELLIGENCE (for anything the roster can reach)
- [x] Narrator sees the roster (packet `skill_catalog`, 158 tokens); prompt invitation closed
- [x] `_slot_by_ref` consults `accepts`; ambiguous words still fall through
- [x] Attribute alias tables unified
- [x] ONE commit, not three: findings 5 and 6 share `tests/test_skill_roster.py` with 1-4, so splitting by file would land commits whose own tests were not yet present

## Test strategy

### Required (must pass after implement)

```text
./.venv/Scripts/python.exe -m unittest tests.test_skill_roster -v
./.venv/Scripts/python.exe tools/audit_skills_8b.py
./.venv/Scripts/python.exe tools/probe_skill_math_8b.py
```

### Prior locks (must stay green)

```text
./.venv/Scripts/python.exe -m unittest tests.test_play_systems -v
./.venv/Scripts/python.exe tools/him_audit_checks.py
./.venv/Scripts/python.exe -m unittest discover -s tests -q
```

**Note:** pytest is not installed — use `unittest`. `tests/test_bare_assert_files.py` wraps bare `def test_*` functions; do not add bare asserts outside it or they pass vacuously.

**Regression rule:** `infer_check_from_action` has existing callers and existing behaviour. Step 2 is a pure hoist — if its output changes for any input, the hoist is wrong.

## Verification log

| Phase | Command / note | Exit / result |
|-------|----------------|---------------|
| pre-fix | 5/5 minted skills described "Related to General Check"; all `attribute='intelligence'` | documented |
| pre-fix | slot `accepts` words resolving: 1/43 | documented |
| pre-fix | resolver prototype: 17/23 without minting (10/23 without regex stage) | documented |
| post Step 2 | hoist purity: 47 patterns, all targeting real codes; inference unchanged on 4 probes | pass |
| post Step 4 | `pick the lock` -> lockpicking / dexterity (was MINT / intelligence) | pass |
| post Step 4 | `sneak past the guard` -> stealth/dex; `climb the wall` -> athletics/str; `calm the horse` -> animal_handling/wis | pass |
| post Step 4 | minted skills now `Hotwire Engine` / `Void Surgery`, description empty, adjusted_from empty | pass |
| post Step 4 | `./.venv/Scripts/python.exe -m unittest discover -s tests -q` | Ran 629 tests, OK (was 617) |
| post Step 4 | `tools/him_audit_checks.py` (incl. its skill-mint-cap check) | exit 0 |
| post Step 4 | `tools/audit_skills_8b.py`, `tools/probe_skill_math_8b.py` | NOT RUN - need a live Ollama; exit 2 on connection refused |
| post Step 5 | skill roster tokens: 158 (system prompt is 9152; roster put in packet, not SYSTEM_PROMPT) | measured |
| post Step 5 | `compact['skill_catalog']` present, >=40 codes incl. stealth/lockpicking/persuasion | pass |
| post Step 6 | slot `accepts`: 37/37 unambiguous resolve, 0 missing; weapon/tool/focus correctly refuse (was 1/43) | pass |
| post Step 7 | enum synonyms: quick->fast, gradual->slow, often->frequent, verbose->expansive, deadly->brutal | pass |
| post Step 7 | `occasional`/`moderate` still take the default on purpose | pass |
| post Step 7 | attribute aliases unified; awareness/stamina/perception all resolve (all scored 10 before) | pass |
| extra | player_skills stored as written (`Road Lore`, not `road lore`); COLLATE NOCASE keeps de-duplication | pass |
| post Step 8 | `unittest discover -s tests -q` | Ran 640 tests, OK (was 617 at session start) |
| post Step 8 | `tools/him_audit_checks.py` | exit 0, ALL PASSED |
| post Step 8 | `node --check static/app.js` | OK |
| post Step 8 | `tools/audit_skills_8b.py`, `tools/probe_skill_math_8b.py` | STILL NOT RUN - need a live Ollama |
| CORRECTION | finding 4 was false; verified by reading `user_prompt` out of a live trace | 60 codes present in draft+verify, always were |
| CORRECTION | `skill_catalog` added, plumbed through 2 layers, then removed as duplication | net effect: prompt wording only |
| CORRECTION | `model_input` in a trace is the player's action text (46 chars), NOT the packet | three false 'it never arrives' readings came from searching it |
| post-correction | `unittest discover -s tests -q` | Ran 646 tests, OK |
