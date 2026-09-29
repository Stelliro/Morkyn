# HIM Implement Handoff

## Goal
Fix only the **8 proven HIM findings** below (Simple Start compose/fillTargets/weak-pass clobbers; art-quality debounce hang, network-fail swallow, LoRA wipe). Do **not** invent polish, redesign, or work outside this proven set. Prior-pass fixes (stash strip, hires dirty/token flush, face-ref post-hires, config-wins resolve) must **stay green** — do not re-open or regress them.

Branch context: uncommitted WIP on `test/morkyn-0.9-wip` (character-art hires/upscale + setup UI). Primary surface: `static/app.js` (`expandSimpleSetupDepth`, `persistArtQualitySettings` / `_flushArtQualitySettings`, LoRA collect/render). Prove harnesses under `tools/`. Staged empty; do not paste secrets; `data/image_presets.json` may hold local paths.

**Implementer consolidation note:** Findings **1, 5, and 8** are the same product bug (unfiltered `composed.field_overrides` after idea/compose) proven via three harnesses. One filter helper + three green tests. Findings **2** and **3** are additional Start clobber paths in the same function. Findings **4, 6, 7** are art-quality persist robustness.

## Proven findings

### 1. [high] correctness-1 — Simple Start re-compose applies unfiltered field_overrides and clobbers surface edits
- **File:** `D:\STELLIROS_WORKSHOP\Morkyn\static\app.js`
- **Severity / domain:** high / correctness
- **Hypothesis / evidence:** `expandSimpleSetupDepth()` now strips Simple keys from `_full_field_overrides` (stash path fixed; `test_simple_start_stash_overwrite.py` green), but when idea is present it re-calls `composeSetupIntent` and `applyRandomizedSetup({ fields: overrides })` with the **FULL** `field_overrides` object (comment claims Advanced-depth only; no `SIMPLE_INTENT_OVERRIDE_KEYS` / `SIMPLE_RANDOM_FIELD_ORDER` filter). `applyRandomizedSetup` in simple mode calls `pullFormToSimple()`, so composed `player_name`/`difficulty`/etc. overwrite form and `#simple*` controls; later `pushSimpleToForm` preserves the clobber. Sibling of the proven stash overwrite, not covered by the stash-only harness. Sim: `player_name='Kael Ashford'` overwrote `'User Edited Name'`; `difficulty='hard'` overwrote `'easy'`.
- **Repro:**
  1. Simple mode → enter idea → Confirm Randomize.
  2. Edit `#simplePlayerName` and `#simpleDifficulty` away from randomized values.
  3. Start game (triggers `expandSimpleSetupDepth`).
  4. Observe form / setup payload: `player_name` and `difficulty` match re-compose `field_overrides`, not post-randomize edits.
  - Automated: `python tools/test_simple_start_idea_recompose_clobber.py` (exit 1 while bug present).
- **Fix guidance:** In `expandSimpleSetupDepth` idea-block, do **not** pass raw `composed.field_overrides` to `applyRandomizedSetup`. Mirror the stash strip: drop keys in `SIMPLE_INTENT_OVERRIDE_KEYS` and `SIMPLE_RANDOM_FIELD_ORDER` (or apply only advanced-depth keys) so `pushSimpleToForm` user edits win; keep advanced-depth keys (tone, quest_style, …) for expand fill. Prefer a shared helper used by both stash and compose paths.
- **Tests to keep green:**
  - `python tools/test_simple_start_idea_recompose_clobber.py` (must pass after fix)
  - `python tools/test_simple_start_stash_overwrite.py` (must stay exit 0)
  - Also: compose sibling harnesses in findings 5 and 8

### 2. [high] correctness-2 — fillTargets always re-rolls Simple surface enums (magic_level, death_rules, world_style)
- **File:** `D:\STELLIROS_WORKSHOP\Morkyn\static\app.js`
- **Severity / domain:** high / correctness
- **Hypothesis / evidence:** After `pushSimpleToForm`, `expandSimpleSetupDepth`'s `fillTargets` loop includes `magic_level`, `death_rules`, and `world_style` (all Simple-visible / Simple-randomize surface). Substantial-skip exists only for prose-ish keys (backstory length, hair≥12, etc.); enums have no non-empty / user-preserve guard. `randomizeFieldApplies` always returns true for these names, so `randomizeField` always rewrites them on Start. `applyRandomizedSetup` then `pullFormToSimple` updates `#simpleMagicLevel` / `#simpleDeathRules` / `#simpleWorld`; `startGame` submits the re-rolled form values. Comment says fill thin defaults, but Simple selects are never empty. Sim: user `magic_level='none'`→`'rare'`, `death_rules` permadeath→downed, `world_style` user vibe→frontier dark fantasy.
- **Repro:**
  1. Open Simple setup.
  2. Set `#simpleMagicLevel=none`, `#simpleDeathRules=permadeath threat`, `#simpleWorld` to a non-empty vibe; leave locks off.
  3. Start playthrough (triggers `expandSimpleSetupDepth`).
  4. Observe fillTargets `randomizeField` on those enums with no non-empty skip; `pullFormToSimple` overwrites Simple selects.
  5. Submitted `setupPayload.magic_level` / `death_rules` / `world_style` differ from pre-Start Simple controls.
  - Automated: `python tools/test_simple_filltargets_surface_reroll.py` (exit 1 while bug present).
- **Fix guidance:** In `expandSimpleSetupDepth` fillTargets loop, skip Simple-surface keys (`magic_level`, `death_rules`, `world_style`, and ideally any `SIMPLE_RANDOM_FIELD_ORDER` / `SIMPLE_INTENT_OVERRIDE_KEYS` field already pushed from Simple UI) when non-empty **or** always treat them as user-owned after `pushSimpleToForm`. Prefer excluding Simple-surface enums from `fillTargets` entirely and only fill advanced-depth thin fields. Keep `applyRandomizedSetup` `pullFormToSimple`, but do **not** re-roll surface enums on Start.
- **Tests to keep green:**
  - `python tools/test_simple_filltargets_surface_reroll.py`

### 3. [med] correctness-3 — Depth weak-pass can re-roll user short hair/backstory after Simple push
- **File:** `D:\STELLIROS_WORKSHOP\Morkyn\static\app.js`
- **Severity / domain:** med / correctness
- **Hypothesis / evidence:** Near end of `expandSimpleSetupDepth`, `pushSimpleToForm()` restores Simple UI, then if `scoreSetupDepth()` total < 70% of target it re-`randomizeField`s every weak band (`character_backstory` min 200, hair min 8, facial_features min 12, appearance min 24, …). Intentional short user copy (e.g. hair `'black bob'`, brief backstory) is treated as weak and replaced; `pullFormToSimple` then rewrites Simple fields. Distinct from fillTargets enum re-roll; same Start clobber class for prose the user deliberately left short. Sim: hair=`'black'` and ~44-char backstory wholesale replaced under thin depth.
- **Repro:**
  1. Simple mode: set hair to short intentional copy (e.g. `'black'`), backstory ~40 chars, leave other depth fields thin so score ratio < 0.7.
  2. Start playthrough (`expandSimpleSetupDepth`).
  3. Observe second `pushSimpleToForm` re-applies shorts, score marks hair/backstory weak, weak-pass `randomizeField` replaces them, `pullFormToSimple` overwrites Simple fields.
  - Automated: `python tools/test_simple_depth_weak_pass_clobber.py` (exit 1 while bug live).
- **Fix guidance:** In `expandSimpleSetupDepth` weak-pass, do **not** full-`randomizeField` non-empty Simple-surface prose already present after `pushSimpleToForm` (hair, facial_features, appearance, character_backstory, and other `SIMPLE_RANDOM_FIELD_ORDER` / `SIMPLE_INTENT_OVERRIDE_KEYS`). Skip those names when form already has user text, or pad-only toward band min without wholesale replace. Keep weak re-roll for true empties / advanced-depth gaps only.
- **Tests to keep green:**
  - `python tools/test_simple_depth_weak_pass_clobber.py`
  - `python tools/test_simple_start_stash_overwrite.py` (must stay green)

### 4. [high] robustness-1 — Debounced art-quality pending Promise never resolves after clearTimeout
- **File:** `D:\STELLIROS_WORKSHOP\Morkyn\static\app.js`
- **Severity / domain:** high / robustness/persistence
- **Hypothesis / evidence:** `persistArtQualitySettings` debounced path creates `_persistArtQualityPending` that only `resolve()`s inside the `setTimeout` callback. A later debounce or `flush:true` calls `clearTimeout` without resolving/rejecting the prior Promise, then awaits that prior — permanently hanging the chain. Practical effect: typing hr scale/denoise within 280ms then Generate (`await persist` flush:true) never proceeds; repeated debounce also never runs `_flushArtQualitySettings`. Harness: static `hangShape=true`; debounce→flush hung TIMEOUT 600ms `flushBodyRuns=0`; re-debounce hung TIMEOUT 880ms `flushBodyRuns=0`.
- **Repro:**
  1. Read `static/app.js` `persistArtQualitySettings` (~12090–12123): debounce Promise only resolves inside setTimeout; flush clearTimeouts then await prior.
  2. `node tools/test_hires_debounce_flush_hang.js` — expects exit 1 with TIMEOUT and `flushBodyRuns=0` while bug present.
  3. Product: open setup art quality bar, edit `#setupArtHrScale` (starts 280ms debounce), within <280ms click character Generate (`await flush:true`); flush awaits unsettled debounce Promise and gen never proceeds.
- **Fix guidance:** When `clearTimeout(_persistArtQualityTimer)` runs, also **settle** the outstanding debounce Promise (keep resolve/reject on the pending object, or swap pending to a resolved/cancelled Promise). `flush:true` must not await a Promise whose only settle is a timer it just cancelled; re-debounce must not chain await on abandoned timer Promises. Minimal: store settle fn with the timer Promise and call `resolve()` (or reject with cancel) immediately before `clearTimeout`; optionally skip await of debounce-only priors that were cancelled. Coordinate with prior-pass flush serialization / `_artQualityFlushGen` so those locks stay green.
- **Tests to keep green:**
  - `node tools/test_hires_debounce_flush_hang.js` (must pass after fix)
  - `node tools/test_hires_flush_race.js` (prior lock)
  - `python tools/test_hires_dirty_race.py` / `test_hires_flush_dirty_race.py` / `test_hires_ui_reset.py` (prior locks)

### 5. [high] robustness-2 — Simple Start re-compose applies full field_overrides and can re-clobber surface edits
- **File:** `D:\STELLIROS_WORKSHOP\Morkyn\static\app.js`
- **Severity / domain:** high / robustness/persistence
- **Hypothesis / evidence:** `expandSimpleSetupDepth` strips Simple-surface keys from stashed `_full_field_overrides`, but after `pushSimpleToForm` it still calls `composeSetupIntent` and `applyRandomizedSetup({fields: overrides})` with raw `composed.field_overrides` (no `SIMPLE_INTENT_OVERRIDE_KEYS` / `SIMPLE_RANDOM_FIELD_ORDER` filter). On Start re-entry, async compose can overwrite user-edited `player_name`/`difficulty`/etc. that the stash guard just preserved. `tools/test_simple_start_stash_overwrite.py` can stay green while this second path still clobbers. Sim: after depth-only stash preserves user name/difficulty, raw compose overrides clobber to `'Compose Clobber Name'` / `'nightmare'`. Code: stash strip loop present then unfiltered `const overrides = composed.field_overrides || {}; applyRandomizedSetup({ fields: overrides });`. `applyRandomizedSetup` unconditionally setFields all keys including `player_name`.
- **Repro:**
  1. Open app Simple setup.
  2. Enter idea, Confirm Randomize.
  3. Edit simple name/difficulty away from randomized values.
  4. Click Start with network so `composeSetupIntent` succeeds.
  5. Inspect submitted setup (or form fields right after expand): `player_name`/`difficulty` match compose `field_overrides`, not post-randomize Simple UI edits.
  - Automated: `python tools/test_simple_start_compose_reentry.py` (exit 1 while unguarded).
- **Fix guidance:** **Same product fix as finding 1 / 8.** After `composeSetupIntent`, strip/filter `composed.field_overrides` the same way as stashed (skip keys in `SIMPLE_INTENT_OVERRIDE_KEYS` and `SIMPLE_RANDOM_FIELD_ORDER`) before `applyRandomizedSetup`; only apply advanced-depth overrides. Do not re-stamp Simple-surface keys from compose on Start.
- **Tests to keep green:**
  - `python tools/test_simple_start_stash_overwrite.py`
  - `python tools/test_simple_start_compose_reentry.py`
  - `python tools/test_simple_start_idea_recompose_clobber.py`
  - `python tools/test_simple_start_compose_clobber.py`

### 6. [med] robustness-3 — Art-quality flush swallows network failure after optimistic imageConfig write
- **File:** `D:\STELLIROS_WORKSHOP\Morkyn\static\app.js`
- **Severity / domain:** med / robustness/persistence
- **Hypothesis / evidence:** `_flushArtQualitySettings` mutates `imageConfig` (`enable_hr`/scale/denoise/upscaler/loras) **before** `await fetch`. On `!res.ok` there is no error path; `catch` is empty ignore. Dirty is only cleared on `res.ok`+`domMatches`, but client already looks saved and nothing re-queues persist or surfaces failure — network drop mid-save desyncs client memory vs server `/api/image-config` and next clean `loadImageConfig` restores stale server values. Runtime sim HTTP 500: client `forge_enable_hr=true` scale=2 vs server false/1.5, dirty=1, requeueCount=0, status=null. Network throw: same desync + empty catch.
- **Repro:**
  1. Open character-art quality bar; turn Hires ON / change scale so dirty=1 and debounced persist fires.
  2. Fail POST `/api/image-config` (DevTools Offline, or mock 500) during flush.
  3. Observe: no error status, no retry; in-memory `imageConfig` already has new hires.
  4. Reload / clean `loadImageConfig` → server stale values restore, user edits lost.
  - Automated: `node tools/test_hires_flush_network_fail.js` (exit 1 while bug present).
- **Fix guidance:** On `!res.ok` and in `catch` after optimistic write: keep/set `dataset.dirty='1'`, do not leave only pre-POST `imageConfig` as sole truth without recovery—either re-queue `persistArtQualitySettings` (debounced), rollback `imageConfig` hires fields from last-known-good/server, and/or `setSetupArtStatus` with a non-silent error. Prefer treating HTTP failure like the mid-flight diverge path (dirty+requeue) rather than empty swallow. Do not break prior-pass `domMatches` success path.
- **Tests to keep green:**
  - `node tools/test_hires_flush_network_fail.js`
  - Prior: `python tools/test_hires_dirty_race.py`, `test_hires_flush_dirty_race.py`, `test_hires_ui_reset.py`

### 7. [med] robustness-4 — Hires flush can wipe forge_active_loras when LoRA checks are not restored from config
- **File:** `D:\STELLIROS_WORKSHOP\Morkyn\static\app.js`
- **Severity / domain:** med / robustness/persistence
- **Hypothesis / evidence:** Every quality flush POSTs `forge_active_loras: collectSetupLoras()`. `renderSetupLoraList` never hydrates checkboxes from `imageConfig.forge_active_loras` (only live DOM checks). After reload/re-entry or before catalog paints rows, collect returns `[]` so a hires-only input/change/debounce flush persists empty LoRAs and clears the server stack used for shared/NPC gens — partial quality write clobbering unrelated persistence. Server sim: seed `forge_active_loras=[{character_lock_v1:0.8},{detail_tweaker:0.55}]` + hires-only patch with `forge_active_loras:[]` → `update_image_config` returns empty LoRAs while `forge_enable_hr=True`.
- **Repro:**
  1. Seed image config with non-empty `forge_active_loras` (2 entries).
  2. Open setup so `#setupArtLoraList` is empty or has no checked boxes (reload before catalog paint, or `renderSetupLoraList` without hydrating saved checks).
  3. Toggle/edit any hires control so `persistArtQualitySettings` → `_flushArtQualitySettings` runs.
  4. Observe POST `/api/image-config` body includes `forge_active_loras:[]`.
  5. GET `/api/image-config` → `forge_active_loras` is `[]`.
  - Automated: `python tools/test_hires_flush_lora_wipe.py` (exit 1 while bug present).
- **Fix guidance:** Do not always POST `forge_active_loras` from empty collect on hires-only flushes. Minimal fix options (pick one primary):
  - **(A)** omit `forge_active_loras` from the quality patch when `collectSetupLoras()` is `[]` and `imageConfig.forge_active_loras` is non-empty / LoRA UI not dirty; or
  - **(B)** hydrate checkbox state from `imageConfig.forge_active_loras` in `renderSetupLoraList`/`loadImageConfig` (match existing comment intent);
  - Prefer **(A)+(B)** so intentional clear still works when user unchecks all. Mirror hires resolve: config-wins until LoRA UI is mounted and hydrated.
- **Tests to keep green:**
  - `python tools/test_hires_flush_lora_wipe.py`
  - Prior quality flush suite must stay green (empty intentional clear should still be possible if UI is hydrated and user unchecked all)

### 8. [high] tests_gaps-1 — Expand Start compose re-apply unfiltered; stash-only prove stays green
- **File:** `D:\STELLIROS_WORKSHOP\Morkyn\static\app.js`
- **Severity / domain:** high / tests_gaps (product gap = unfiltered compose apply; harness gap = stash-only lock)
- **Hypothesis / evidence:** correctness-1 was locked only for `_full_field_overrides` depth filtering. `expandSimpleSetupDepth` still `applyRandomizedSetup({fields: composed.field_overrides})` with no `SIMPLE_INTENT_OVERRIDE_KEYS` / `SIMPLE_RANDOM_FIELD_ORDER` strip. `applyRandomizedSetup` then `pullFormToSimple()`, so composer `player_name`/`difficulty` overwrite post-randomize Simple UI + form. `tools/test_simple_start_stash_overwrite.py` stays OK because its sim never includes the compose re-apply path. Observed: stash exit 0; compose clobber exit 1 with sim `player_name='Kael'` (lost `'User Edited Name'`) and `difficulty='hard'` (lost `'easy'`).
- **Repro:**
  1. Open `static/app.js` `expandSimpleSetupDepth`.
  2. Confirm stashed loop strips `SIMPLE_INTENT_OVERRIDE_KEYS` / `SIMPLE_RANDOM_FIELD_ORDER` before `applyRandomizedSetup`.
  3. Confirm idea/compose branch applies `composed.field_overrides` unfiltered.
  4. Run: `python tools/test_simple_start_stash_overwrite.py` (exit 0).
  5. Run: `python tools/test_simple_start_compose_clobber.py` (exit 1; form/Simple surface becomes Kael/hard after compose re-apply).
- **Fix guidance:** **Same product fix as findings 1 and 5.** In `expandSimpleSetupDepth`'s compose branch, strip the same Simple-surface keys as the stash path before `applyRandomizedSetup` (loop skip `SIMPLE_INTENT_OVERRIDE_KEYS` + `SIMPLE_RANDOM_FIELD_ORDER`, or build a depth-only dict). Do not apply full `composed.field_overrides` onto the form after `pushSimpleToForm`; keep advanced-depth keys only. Keep all compose clobber harnesses as permanent regression locks (not stash-only).
- **Tests to keep green:**
  - `python tools/test_simple_start_stash_overwrite.py`
  - `python tools/test_simple_start_compose_clobber.py`
  - `python tools/test_simple_start_idea_recompose_clobber.py`
  - `python tools/test_simple_start_compose_reentry.py`

## Constraints
- **Evidence-only:** do not expand into polish, redesign, or full Simple/Advanced setup rewrite.
- Scope implement to this proven set only (plus necessary shared helpers for the compose strip / flush settle paths).
- Keep and extend tests created during Prove; add regression coverage for each fix (do not delete failing harnesses — make them pass).
- Match project conventions; atomic buildable changes in `static/app.js` (and only touch other files if a fix truly requires it).
- Low severity / report-only: none separate — all listed are in-scope implement items.
- Do not regress prior-pass locks: stash strip, hires dirty conditional clear, flush gen token/serialize, face-ref quality post-hires, config-wins `resolveArtHiresSettings`, `_as_bool` string false.
- Do not paste secrets; treat `data/image_presets.json` local paths carefully.
- No package.json / Makefile / pytest.ini / CI workflows — use tools harnesses and listed commands.

## Test strategy
Repo has no root pytest.ini/package.json CI; prefer focused prove harnesses under `tools/`, then broader suites if time allows.

### Required (must pass after implement)
```text
python tools/test_simple_start_idea_recompose_clobber.py
python tools/test_simple_start_compose_reentry.py
python tools/test_simple_start_compose_clobber.py
python tools/test_simple_start_stash_overwrite.py
python tools/test_simple_filltargets_surface_reroll.py
python tools/test_simple_depth_weak_pass_clobber.py
node tools/test_hires_debounce_flush_hang.js
node tools/test_hires_flush_network_fail.js
python tools/test_hires_flush_lora_wipe.py
```

### Prior locks (must stay green)
```text
python tools/test_hires_dirty_race.py
python tools/test_hires_flush_dirty_race.py
node tools/test_hires_flush_race.js
python tools/test_hires_ui_reset.py
python tools/test_hires_upscale_path.py
python tools/test_as_bool_hires.py
python tools/test_wardrobe_possessive.py
python tools/verify_setup_simple_vs_advanced.py
```

### Broader (when practical)
```text
python tools/him_audit_checks.py
python tools/test_play_systems.py
python -m unittest discover
python tests/behavior_test.py
python tests/test_narration_pipeline.py
```

Fastest meaningful check for this change: the Required block above (Simple expand + art-quality flush).

## Acceptance
- Each of the 8 proven findings fixed **OR** explicitly blocked with product reason in Codex Fixes.
- All prove tests for this session + prior hires/stash locks pass.
- Findings 1+5+8 may be one atomic strip helper; document as such in Codex Fixes.
- Codex Fixes section can be updated after implement (this handoff is implement-from-plan source until then).
- No drive-by changes outside `static/app.js` unless a finding's fix truly requires another file.

## DISPROVEN / not fixed
(none this pass)

## Stats
candidates=10 proven=8 disproven=0 hunt_fail=0 prove_unusable=0
