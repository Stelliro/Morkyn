# Implementation Process

## Goal

Fix **only** the eight proven HIM findings on branch `test/morkyn-0.9-wip` (Simple Start expand clobbers + art-quality flush robustness). Do **not** invent polish, redesign Simple/Advanced setup, re-open prior-pass locks, or work outside this proven set.

| ID | Severity | Domain | One-line defect |
|----|----------|--------|-----------------|
| 1 correctness-1 | high | correctness | Idea re-compose applies unfiltered `field_overrides` → clobbers Simple surface edits |
| 2 correctness-2 | high | correctness | `fillTargets` always re-rolls Simple surface enums (`magic_level`, `death_rules`, `world_style`) |
| 3 correctness-3 | med | correctness | Depth weak-pass full-`randomizeField`s intentional short hair/backstory |
| 4 robustness-1 | high | robustness | Debounced art-quality Promise never settles after `clearTimeout` → hang |
| 5 robustness-2 | high | robustness | Same compose unfiltered re-apply (sibling of #1) on Start re-entry |
| 6 robustness-3 | med | robustness | Flush swallows network failure after optimistic `imageConfig` write |
| 7 robustness-4 | med | robustness | Hires flush POSTs empty `forge_active_loras` and wipes server LoRA stack |
| 8 tests_gaps-1 | high | tests_gaps | Compose re-apply unfiltered; stash-only harness stays green |

**Consolidation:** Findings **1, 5, and 8** are one product bug (filter `composed.field_overrides` like stash). Ship one strip helper; keep all three compose harnesses + stash lock green.

Prior-pass fixes (stash strip, hires dirty/token flush, face-ref post-hires, config-wins `resolveArtHiresSettings`, `_as_bool`) must **stay green** — do not re-open or regress them.

## Sources

| Source | Path | Role |
|--------|------|------|
| Implement handoff (primary) | `HIM_IMPLEMENT_HANDOFF.md` | Scope, repros, fix guidance, required test commands |
| HIM codex | `.grok/him-codex.md` | Session prove notes; **Fixes** for this pass currently `None until implement` — update after code |
| Proven findings | This process + handoff list | Source of truth for scope |
| Product surface | `static/app.js` | Primary (and expected-only) touch file |
| Prove harnesses (this pass) | `tools/test_simple_start_*.py`, `tools/test_simple_filltargets_surface_reroll.py`, `tools/test_simple_depth_weak_pass_clobber.py`, `tools/test_hires_debounce_flush_hang.js`, `tools/test_hires_flush_network_fail.js`, `tools/test_hires_flush_lora_wipe.py` | Must go green; do not delete |
| Prior locks | stash overwrite, dirty/flush race, ui_reset, upscale path, as_bool, wardrobe, verify_setup | Must stay exit 0 |

## Context

- Dirty tree: character-art hires/upscale + setup UI WIP (`image_backends.py`, `static/*` ~1.2k net). Staged empty. Do not paste secrets; treat `data/image_presets.json` local paths carefully.
- **Primary function (Simple Start):** `expandSimpleSetupDepth` in `static/app.js` (~L14889+):
  - Stash path (~L14913+) already strips `SIMPLE_INTENT_OVERRIDE_KEYS` / `SIMPLE_RANDOM_FIELD_ORDER` — **keep green**.
  - Idea/compose branch still applies raw `composed.field_overrides` via `applyRandomizedSetup` — **findings 1/5/8**.
  - `fillTargets` loop (~L14937–14959+) includes Simple surface enums without user-preserve — **finding 2**.
  - End weak-pass after second `pushSimpleToForm` + `scoreSetupDepth` full-randomizes weak bands — **finding 3**.
- **Primary functions (art quality):** `persistArtQualitySettings` (~L12090), `_flushArtQualitySettings` (~L11988), `collectSetupLoras` / `renderSetupLoraList` (~L11819 / ~L12373).
- Constants for surface filtering already exist near top of `app.js`: `SIMPLE_INTENT_OVERRIDE_KEYS` (~L612), `SIMPLE_RANDOM_FIELD_ORDER`.
- `applyRandomizedSetup` in simple mode calls `pullFormToSimple()` — any unfiltered surface apply rewrites `#simple*` controls; later `pushSimpleToForm` preserves the clobber.
- No package.json / Makefile / pytest.ini / CI workflows for this surface — use `tools/` harnesses as the gate.
- Repo Python tests under `tests/` are secondary; run when practical after required harnesses pass.

## Constraints

- **Evidence-only:** fix the eight proven items only. No polish, full setup redesign, showcase JSON, wardrobe inventing, or architecture rewrites unless a finding truly requires it (none do).
- Prefer **smallest durable fix** matching each finding’s `fix_guidance`. Shared helper for compose strip is expected; do not invent a new setup architecture.
- Keep and run prove-created tests; make them pass — do not delete failing harnesses.
- Touch map: **`static/app.js` only** unless a fix truly needs another file (none of the eight require product changes outside `app.js`).
- Do not regress prior-pass locks: stash strip, dirty conditional clear, flush gen token/serialize, face-ref quality post-hires, config-wins `resolveArtHiresSettings`, `_as_bool` string false.
- Match existing style in `static/app.js` (plain DOM + fetch; no new framework).
- After product changes: append implement results under **Fixes** in `.grok/him-codex.md` (session “Simple expand clobber + art-quality flush prove”).
- Do not paste secrets; avoid drive-by edits to `data/image_presets.json` / model paths.
- Findings 1+5+8 may be one atomic strip helper; document as such in Codex Fixes.

## Steps

### Step 1: Baseline prove suite (document pre-fix state)
- Status: completed
- Actions:
  - From repo root, run this-pass harnesses and record exit codes in **Verification log**:
    - `python tools/test_simple_start_idea_recompose_clobber.py` (expect exit 1)
    - `python tools/test_simple_start_compose_reentry.py` (expect exit 1)
    - `python tools/test_simple_start_compose_clobber.py` (expect exit 1)
    - `python tools/test_simple_start_stash_overwrite.py` (expect exit 0 — prior lock)
    - `python tools/test_simple_filltargets_surface_reroll.py` (expect exit 1)
    - `python tools/test_simple_depth_weak_pass_clobber.py` (expect exit 1)
    - `node tools/test_hires_debounce_flush_hang.js` (expect exit 1 / TIMEOUT)
    - `node tools/test_hires_flush_network_fail.js` (expect exit 1)
    - `python tools/test_hires_flush_lora_wipe.py` (expect exit 1)
  - Spot-check code anchors still match handoff (no product edits this step):
    - Stash strip present; compose `applyRandomizedSetup({ fields: overrides })` unfiltered
    - `fillTargets` includes `magic_level`, `death_rules`, `world_style`
    - Weak-pass after `scoreSetupDepth` full-`randomizeField` on weak bands
    - Debounce Promise resolves only inside `setTimeout`; flush `clearTimeout` then `await` prior
    - `_flushArtQualitySettings` optimistic mutate pre-POST; empty catch; always POSTs `collectSetupLoras()`
  - Confirm prior locks still green if time: dirty race, flush race, ui_reset, upscale, as_bool.
- Acceptance: Verification log has pre-fix exit codes; no product edits in this step.
- Verify: Commands above completed; note any unexpected greens as “already fixed / re-check harness.”

### Step 2: Fix findings 1+5+8 — strip Simple-surface keys from composed field_overrides
- Status: completed
- Actions:
  - In `static/app.js` `expandSimpleSetupDepth`, locate the idea/compose branch that does:
    - `const overrides = composed.field_overrides || {};`
    - `applyRandomizedSetup({ fields: overrides });`
  - **Do not** pass raw `composed.field_overrides`. Mirror the stash strip:
    - Prefer a shared helper (e.g. `depthOnlyFieldOverrides(fields)` or inline same loop) used by **both** stash and compose paths.
    - Drop keys in `SIMPLE_INTENT_OVERRIDE_KEYS` **and** `SIMPLE_RANDOM_FIELD_ORDER` before apply.
    - Keep advanced-depth keys (tone, quest_style, and other non-Simple-surface) for expand fill.
  - Do not change `applyRandomizedSetup` global semantics unless strictly necessary (filter at expand call site).
  - Leave stash path behavior equivalent (already strips); refactor to helper only if both paths call the same filter.
  - Do not redesign Start flow or remove `composeSetupIntent` / idea re-compose entirely.
- Acceptance:
  - Compose re-apply cannot overwrite post-randomize Simple UI / form surface keys (`player_name`, `difficulty`, etc.).
  - Advanced-depth keys from compose can still apply.
  - All four Simple Start harnesses exit 0:
    - `python tools/test_simple_start_idea_recompose_clobber.py`
    - `python tools/test_simple_start_compose_reentry.py`
    - `python tools/test_simple_start_compose_clobber.py`
    - `python tools/test_simple_start_stash_overwrite.py`
- Verify: Run the four commands above; static assertions in compose harnesses must see surface filter on compose path.

### Step 3: Fix finding 2 — fillTargets must not re-roll Simple surface enums
- Status: completed
- Actions:
  - In `expandSimpleSetupDepth` `fillTargets` loop (`static/app.js` ~L14937–15000 area):
    - Prefer **excluding** Simple-surface enums from `fillTargets` entirely: at least `magic_level`, `death_rules`, `world_style`.
    - Ideally also exclude any key in `SIMPLE_RANDOM_FIELD_ORDER` / `SIMPLE_INTENT_OVERRIDE_KEYS` already owned by Simple UI after `pushSimpleToForm`.
    - Alternative acceptable: skip those names when non-empty / always treat as user-owned after push.
  - Keep filling advanced-depth thin fields only; do not remove substantial-skip for prose-ish keys.
  - Keep `applyRandomizedSetup` `pullFormToSimple` behavior; just **do not re-roll** surface enums on Start.
- Acceptance:
  - User-set `#simpleMagicLevel` / `#simpleDeathRules` / `#simpleWorld` survive Start expand.
  - `python tools/test_simple_filltargets_surface_reroll.py` exits 0.
  - Stash + compose harnesses from Step 2 still green.
- Verify:
  - `python tools/test_simple_filltargets_surface_reroll.py`
  - `python tools/test_simple_start_stash_overwrite.py`
  - `python tools/test_simple_start_compose_clobber.py` (or full compose trio if quick)

### Step 4: Fix finding 3 — weak-pass must not wholesale replace non-empty Simple-surface prose
- Status: completed
- Actions:
  - Near end of `expandSimpleSetupDepth`, after second `pushSimpleToForm` and `scoreSetupDepth()`, in the weak-pass loop over `score.weak`:
    - Do **not** full-`randomizeField` non-empty Simple-surface prose already present: at least `hair`, `facial_features`, `appearance`, `character_backstory`, and other keys in `SIMPLE_RANDOM_FIELD_ORDER` / `SIMPLE_INTENT_OVERRIDE_KEYS`.
    - Preferred: **skip** those names when form already has user text (trim non-empty).
    - Alternative: pad-only toward band min without wholesale replace (only if harness accepts; skip is simpler and matches guidance).
    - Keep weak re-roll for true empties and advanced-depth gaps only.
    - Retain `isSettingLocked` guard; add user-owned / non-empty surface guard.
- Acceptance:
  - Intentional short hair/backstory (e.g. `'black'`, ~40-char backstory) not replaced when score ratio < 0.7.
  - `python tools/test_simple_depth_weak_pass_clobber.py` exits 0.
  - Stash lock still green.
- Verify:
  - `python tools/test_simple_depth_weak_pass_clobber.py`
  - `python tools/test_simple_start_stash_overwrite.py`
  - Re-run fillTargets harness to ensure no interaction: `python tools/test_simple_filltargets_surface_reroll.py`

### Step 5: Fix finding 4 — settle debounced art-quality Promise on clearTimeout
- Status: completed
- Actions:
  - In `static/app.js` `persistArtQualitySettings` (~L12090–12123):
    - When `clearTimeout(_persistArtQualityTimer)` runs (flush:true **and** re-debounce), also **settle** the outstanding debounce Promise.
    - Minimal: store resolve (and optional reject) with the timer Promise; call `resolve()` (or reject with cancel) **immediately before** `clearTimeout`.
    - `flush:true` must not `await` a Promise whose only settle path is the timer it just cancelled.
    - Re-debounce must not chain `await` on abandoned timer Promises.
  - Coordinate with prior-pass flush serialization / `_artQualityFlushGen` — those locks must stay green; do not remove await-prior or gen token.
  - After settling cancelled debounce, flush path should still run `_flushArtQualitySettings` (or join serialize chain as before).
- Acceptance:
  - debounce → flush:true within 280ms settles and runs flush body (no TIMEOUT hang).
  - re-debounce does not hang; prior Promise settles.
  - `node tools/test_hires_debounce_flush_hang.js` exits 0.
  - Prior: `node tools/test_hires_flush_race.js` exits 0; dirty race Python harnesses stay green.
- Verify:
  - `node tools/test_hires_debounce_flush_hang.js`
  - `node tools/test_hires_flush_race.js`
  - `python tools/test_hires_dirty_race.py`
  - `python tools/test_hires_flush_dirty_race.py`

### Step 6: Fix finding 6 — recover from art-quality flush network failure
- Status: completed
- Actions:
  - In `_flushArtQualitySettings` after optimistic `imageConfig` mutate and `await fetch`:
    - On `!res.ok`: do **not** empty-swallow. Keep/set `dataset.dirty='1'`; re-queue `persistArtQualitySettings` (debounced) and/or `setSetupArtStatus` with a non-silent error; optionally rollback hires fields from last-known-good snapshot taken before mutate.
    - In `catch`: same recovery as HTTP failure (dirty + requeue/status); no empty `catch (_) { /* ignore */ }` without recovery.
  - Prefer treating failure like mid-flight diverge path (dirty + requeue) rather than silent success look.
  - Do **not** break prior-pass success path: clear dirty + merge only when `res.ok` and `domMatches`.
  - Do not invent multi-retry backoff beyond existing debounced requeue pattern.
- Acceptance:
  - HTTP 500 / network throw: dirty stays/set, requeue or status surfaces, client not left as sole “saved” truth with no recovery.
  - `node tools/test_hires_flush_network_fail.js` exits 0.
  - Dirty race / ui_reset / flush race still green.
- Verify:
  - `node tools/test_hires_flush_network_fail.js`
  - `python tools/test_hires_dirty_race.py`
  - `python tools/test_hires_flush_dirty_race.py`
  - `python tools/test_hires_ui_reset.py`
  - `node tools/test_hires_debounce_flush_hang.js` (still green after Step 5)

### Step 7: Fix finding 7 — do not wipe forge_active_loras on empty collect / unhydrated LoRA UI
- Status: completed
- Actions:
  - Primary (A): In `_flushArtQualitySettings`, **omit** `forge_active_loras` from the quality POST patch when `collectSetupLoras()` is `[]` **and** `imageConfig.forge_active_loras` is non-empty / LoRA UI not dirty (config-wins until LoRA UI mounted and hydrated).
  - Strongly prefer also (B): hydrate checkbox state from `imageConfig.forge_active_loras` in `renderSetupLoraList` and/or `loadImageConfig` so intentional clear (user unchecks all when UI is hydrated) still POSTs `[]`.
  - Mirror hires resolve pattern: config-wins until UI is ready; intentional empty only when UI owns the empty state.
  - Do not remove LoRA from patch when user has explicitly unchecked all on a hydrated list.
- Acceptance:
  - Hires-only flush with empty LoRA DOM cannot clear server non-empty `forge_active_loras`.
  - `python tools/test_hires_flush_lora_wipe.py` exits 0.
  - Prior quality flush suite still green (dirty, race, debounce hang, network fail).
- Verify:
  - `python tools/test_hires_flush_lora_wipe.py`
  - `node tools/test_hires_flush_network_fail.js`
  - `node tools/test_hires_debounce_flush_hang.js`
  - `node tools/test_hires_flush_race.js`

### Step 8: Full this-pass + prior-lock regression suite
- Status: completed
- Actions:
  - Run **Required** block (all must exit 0):
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
  - Run **Prior locks** (all must stay green):
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
    (verify_setup may skip if server not running — note, do not treat skip as fail unless harness fails hard.)
  - If any fail: fix product (or harness only if expectation inverted incorrectly) and re-run failed + adjacent locks; do not mark Done with red required tests.
- Acceptance: Required suite all exit 0; prior locks exit 0 (or documented skip for verify_setup without server).
- Verify: Paste/exit codes into **Verification log** post-fix section.

### Step 9: Update `.grok/him-codex.md` Fixes section
- Status: completed
- Actions:
  - Open `.grok/him-codex.md` session block **“Simple expand clobber + art-quality flush prove”** (Phase currently Prove complete).
  - Set Phase to **Implement complete** (or equivalent).
  - Replace `## Fixes` `None until implement` with concrete bullets:
    - **correctness-1 / robustness-2 / tests_gaps-1:** shared depth-only filter on composed `field_overrides` (same keys as stash strip).
    - **correctness-2:** fillTargets excludes / preserves Simple surface enums.
    - **correctness-3:** weak-pass skips non-empty Simple-surface prose.
    - **robustness-1:** debounce Promise settled on clearTimeout before flush/re-debounce await.
    - **robustness-3:** flush failure dirty + requeue/status (no empty swallow).
    - **robustness-4:** omit empty LoRA collect when config non-empty / hydrate checks.
  - Update Tests table: pre-fix exit 1 → post-fix exit 0 for this-pass harnesses; list prior locks still green.
  - Keep prior hires session Fixes intact; append only this session’s implement results.
- Acceptance: Codex documents all eight findings as fixed (or blocked with product reason); harness commands listed with post-fix green.
- Verify: Read back Fixes section; no “None until implement” for this session.

### Step 10: Broader touch-area checks (when practical) + Done gate
- Status: completed
- Actions:
  - Optional but recommended if time:
    - `python tools/him_audit_checks.py`
    - `python tools/test_play_systems.py`
    - `python -m unittest discover` (or targeted `tests/` if full suite is heavy)
  - Confirm no drive-by files outside `static/app.js` (+ codex/process docs) unless a fix required them.
  - Confirm no new polish, no deleted prove harnesses, no regression of prior Fixes.
  - Fill **Verification log** final row: all required green → process Done.
- Acceptance:
  - All Done criteria checkboxes can be marked complete.
  - Eight findings fixed or explicitly blocked in Codex.
  - Prove + prior lock tests pass.
- Verify: Re-scan Required command list one last time if any late edit landed after Step 8.

## Done criteria

- [x] Finding 1 (correctness-1) fixed — compose idea re-apply depth-only; harnesses green
- [x] Finding 2 (correctness-2) fixed — fillTargets does not re-roll Simple surface enums
- [x] Finding 3 (correctness-3) fixed — weak-pass preserves non-empty Simple-surface prose
- [x] Finding 4 (robustness-1) fixed — debounce Promise settles on clearTimeout; no flush hang
- [x] Finding 5 (robustness-2) fixed — same product fix as 1/8; compose reentry harness green
- [x] Finding 6 (robustness-3) fixed — flush network fail dirty+requeue/status
- [x] Finding 7 (robustness-4) fixed — empty collect does not wipe server LoRAs
- [x] Finding 8 (tests_gaps-1) fixed — compose clobber harness green; stash still green
- [x] All prove-created tests for this session still present and exit 0
- [x] Prior-pass hires/stash locks still exit 0
- [x] `.grok/him-codex.md` Fixes updated for this implement session
- [x] No scope creep outside proven set / no architecture rewrite

## Test strategy

Repo has no root pytest.ini / package.json CI for this surface. Gate on focused prove harnesses under `tools/`.

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

**Fastest meaningful check:** Required block (Simple expand + art-quality flush). Run after each step’s product edit when possible; full Required + Prior at Step 8.

**Regression rule:** Do not delete prove harnesses. Extend static asserts only if the fix shape needs them. Findings 1+5+8 share one helper — all three compose tests must remain permanent locks.

## Verification log

| Phase | Command / note | Exit / result |
|-------|----------------|---------------|
| pre-fix | idea/reentry/clobber/fill/weak/debounce/net/lora = 1; stash = 0 | documented |
| post Step 2 | compose trio + stash | all exit 0 |
| post Step 3 | fillTargets surface reroll | exit 0 |
| post Step 4 | weak-pass clobber | exit 0 |
| post Step 5 | debounce hang + flush race + dirty | all exit 0 |
| post Step 6 | network fail + dirty/ui | all exit 0 |
| post Step 7 | lora wipe + flush suite | all exit 0 |
| post Step 8 | full Required + Prior locks | Required all 0; prior all 0; verify_setup skip (no server) |
| post Step 9 | him-codex Fixes updated | Implement complete; all 8 fixed |
| final | Done criteria all checked | complete |
| **verify agent** | Spot-check app.js vs 8 findings; re-run Required + Prior | **passed=true** (2026-08-03) |
| verify | `python tools/test_simple_start_idea_recompose_clobber.py` | exit 0 — idea re-compose surface preserved |
| verify | `python tools/test_simple_start_compose_reentry.py` | exit 0 — compose re-entry no re-clobber |
| verify | `python tools/test_simple_start_compose_clobber.py` | exit 0 — compose re-apply depth-only |
| verify | `python tools/test_simple_start_stash_overwrite.py` | exit 0 — prior stash lock |
| verify | `python tools/test_simple_filltargets_surface_reroll.py` | exit 0 — surface enums not re-rolled |
| verify | `python tools/test_simple_depth_weak_pass_clobber.py` | exit 0 — short prose preserved |
| verify | `node tools/test_hires_debounce_flush_hang.js` | exit 0 — hangShape=false; flushBodyRuns=1 both scenarios |
| verify | `node tools/test_hires_flush_network_fail.js` | exit 0 — dirty=1 requeueCount=1 status set on 500/throw |
| verify | `python tools/test_hires_flush_lora_wipe.py` | exit 0 — omit+hydrate; always_posts_loras=False |
| verify | prior: dirty_race, flush_dirty_race, flush_race.js, ui_reset, upscale_path, as_bool, wardrobe | all exit 0 |
| verify | `python tools/verify_setup_simple_vs_advanced.py` | exit 2 skip — server not running (WinError 10061) |
| verify code | depthOnlyFieldOverrides on stash+compose; fillTargets surface skip; weak-pass non-empty skip; _persistArtQualitySettle on clear; !res.ok/catch dirty+requeue; omit empty LoRA when UI not ready | matches fix_guidance |

---

*Process file for hands-off implement/verify agents. Source of truth for scope: `HIM_IMPLEMENT_HANDOFF.md` + proven findings above. Update step Status from `pending` → `completed` (or `blocked`) as work proceeds.*
