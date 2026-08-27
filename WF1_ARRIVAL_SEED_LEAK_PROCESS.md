# WF1 — Stop the arrival prompt handing the model its own answer

## Goal

Remove the literal arrival-name exemplars from the `start_location` randomizer prompt, so the model writes a name **from the setting** instead of returning one of ours. Measure the verbatim-copy rate before and after on the same model.

Do **not** widen the keyword table (that is WF3), do **not** touch the intent planner (that is WF2), and do **not** delete the seed banks — they remain the offline floor.

| ID | Severity | Domain | One-line defect |
|----|----------|--------|-----------------|
| 1 leak-1 | high | output quality | `prompt["arrival_location_seeds"]` ships 6 real bank names as a prompt key |
| 2 leak-2 | high | output quality | A rule restates 4 of them: `Example arrival names (adapt, invent similar)` |
| 3 leak-3 | **unproven** | output quality | `kit_seeds_inspiration_only` / `clothing_seeds_inspiration_only` use the identical shape — **measure before touching** |

**Measured:** ~44% of live arrival names across the last session's 80 rolls were verbatim members of the bank shown to the model. Findings 1 and 2 are one product bug with two injection points; fix them together.

**Finding 3 is a hypothesis, not a finding.** It is the same mechanism on two other fields, but no leak rate has been measured for them. Step 5 measures. Fix only what the measurement proves.

## Sources

| Source | Path | Role |
|--------|------|------|
| Leak site (key) | `app/llm.py:6586` | `arrival_location_seeds = random.sample(theme_pool, k=6)` |
| Leak site (rule) | `app/llm.py:6615` | `Example arrival names (adapt, invent similar): ...` |
| Shape hint (keep) | `app/llm.py:6595-6612` | `theme_hint` map — describes the *shape* without naming places |
| Offline floor (keep) | `app/llm.py:6622` | `_fallback_arrival_location` — computed separately, does not need the prompt |
| Seed banks | `app/setup_composer.py` `LOCATION_SEEDS_BY_THEME` | Stays; offline + fallback only |
| Sibling fields (measure) | `app/llm.py:6550`, `app/llm.py:6637` | kit / clothing seed injection |
| Established lesson | memory `prompt-examples-get-pasted-verbatim` | Concrete strings in Mørkyn prompts become the model output |
| Precedent | de-naming of `SYSTEM_PROMPT` / `VERIFY_PROMPT` | Same fix, same repo, already shipped |

## Context

- The instruction `(adapt, invent similar)` is an instruction **against** copying, sitting immediately next to four things to copy. This repo already has written evidence that this does not work: the fix is to remove the strings, not to argue with the model about them.
- `theme_hint` already carries the useful half — "station airlock / hab / docking ring arrival names" describes a shape without naming a place. That line stays and does the whole job.
- `_fallback_arrival_location` calls `pick_isekai_arrival_location(...)` directly with its own seed. It never read `prompt["arrival_location_seeds"]`. Removing the prompt key cannot weaken the offline path.
- This block only runs when `isekaiish` is true (`app/llm.py:6563`). Non-isekai rolls never saw the seeds and are out of scope — do not widen the scope to cover them.
- The `generic` theme hint was deliberately written to be place-free and needs no change.

## Constraints

- **Evidence-only.** Findings 1 and 2 are measured. Finding 3 is not — measure it in Step 5 and fix it only if the rate is material. Record a null result if it is not.
- Do **not** delete `LOCATION_SEEDS_BY_THEME` or any bank. They are load-bearing for offline, `structural_fallback`, and `static/app.js`.
- Do **not** replace the exemplars with different exemplars. The fix is removal, not rotation.
- Keep `theme_hint` descriptive; it may be lengthened, but it must not name a specific place.
- Touch map: `app/llm.py` only, plus one new harness under `tools/`. No `setup_composer.py` edits.
- Report the after-rate honestly, including if it fails to improve. A withdrawn claim is the house style (precedent: commit 59c92d8).

## Steps

### Step 1: Baseline the leak rate
- Status: pending
- Actions:
  - Write `tools/measure_arrival_seed_leak.py`: run N isekai randomizations against the live model and record `(theme_id, returned_name, bank_for_theme)` for each.
  - Report: total rolls, rolls whose name is a **case-insensitive exact member** of the theme bank, rolls sharing a distinctive multi-word span with a bank entry, and distinct names returned.
  - Use N of at least 20. Record the model id, and record that the run used shipped config rather than an overridden env (see memory `test-harnesses-mask-shipped-defaults`).
- Acceptance: A pre-fix verbatim rate is written into the Verification log with N and model id.
- Verify: Script runs to completion; no product edits in this step.

### Step 2: Remove the two injection points
- Status: pending
- Actions:
  - Delete the `prompt["arrival_location_seeds"] = random.sample(...)` assignment at `app/llm.py:6586`.
  - Delete the `Example arrival names (adapt, invent similar)` rule at `app/llm.py:6615`.
  - Keep `prompt["arrival_location_theme"] = theme_id` — a theme id is a label, not a name to copy.
  - Keep the `theme_hint` rule and the "NEVER Seoul/warehouse/office/apartment/hospital on Earth" rule.
  - Keep `_fallback_arrival_location` exactly as it is.
  - Confirm `theme_pool` is now unused in this block and remove it if so — do not leave a dead local.
- Acceptance: No literal bank name reaches the prompt for `start_location`. `theme_hint` still selects on `theme_id`.
- Verify: `grep -n "arrival_location_seeds" app/llm.py` returns nothing.

### Step 3: Lock it with a harness
- Status: pending
- Actions:
  - Write `tools/test_arrival_seed_leak.py`. Build the `start_location` prompt for several themes without calling the model, serialize it, and assert **no entry of any `LOCATION_SEEDS_BY_THEME` bank appears anywhere in it**.
  - Assert positively that `arrival_location_theme` and the `theme_hint` text are still present — this must fail if someone removes the shape hint along with the names.
  - Cover at least: `space`, `cyberpunk`, `wasteland`, `fantasy`, `generic`.
- Acceptance: Harness exits 1 against the pre-fix code and 0 after Step 2.
- Verify: `./.venv/Scripts/python.exe tools/test_arrival_seed_leak.py`

### Step 4: Re-measure the leak rate
- Status: pending
- Actions:
  - Re-run the Step 1 measurement with the same N and the same model.
  - Record before/after in the Verification log. Also record **distinct name count** — the fix must not reduce variety.
  - If the rate did not materially fall, say so and stop. Do not re-word the prompt repeatedly chasing a number.
- Acceptance: Post-fix rate recorded next to pre-fix rate, same N, same model.
- Verify: Both numbers in the Verification log with N and model id.

### Step 5: Measure the sibling fields (finding 3)
- Status: pending
- Actions:
  - Extend the measurement to `starter_equipment` (`kit_seeds_inspiration_only`, `app/llm.py:6550`) and `appearance` (`clothing_seeds_inspiration_only`, `app/llm.py:6637`).
  - Report their verbatim-copy rates.
  - **Only if a rate is material**, apply the same removal. If not, record the null result and close finding 3 as unproven.
  - These fields differ from `start_location`: a kit item is a common noun and legitimate overlap is expected. Judge on distinctive multi-word spans, not on single words like "satchel".
- Acceptance: Both rates recorded. Any fix applied is justified by its own number, not by the WF1 number.
- Verify: Numbers in the Verification log; note explicitly if no change was made and why.

### Step 6: Regression + commit
- Status: pending
- Actions:
  - Run the Required and Prior-lock blocks below.
  - Commit with the before/after numbers, N, and model id in the message. If finding 3 was closed unproven, say that in the message too.
- Acceptance: All green; commit carries evidence.
- Verify: Full Required block re-run after the final edit.

## Done criteria

- [ ] Pre-fix verbatim rate measured and logged (N, model id, shipped config)
- [ ] `arrival_location_seeds` key removed
- [ ] `Example arrival names` rule removed
- [ ] `theme_hint` and `arrival_location_theme` retained and asserted
- [ ] `tools/test_arrival_seed_leak.py` exists, was red pre-fix, green post-fix
- [ ] Post-fix rate measured at same N / same model and logged
- [ ] Distinct-name count did not fall
- [ ] Finding 3 measured and either fixed with its own evidence or closed as unproven
- [ ] Offline path untouched: banks intact, `_fallback_arrival_location` intact
- [ ] Prior locks green

## Test strategy

### Required (must pass after implement)

```text
./.venv/Scripts/python.exe tools/test_arrival_seed_leak.py
./.venv/Scripts/python.exe -m unittest tests.test_prompt_exemplar_leak -v
./.venv/Scripts/python.exe -m unittest tests.test_start_location_default -v
```

### Prior locks (must stay green)

```text
./.venv/Scripts/python.exe -m unittest tests.test_location_themes -v
./.venv/Scripts/python.exe -m unittest tests.test_theme_routing -v
node tools/test_start_location_offline_theme.js
./.venv/Scripts/python.exe tools/him_audit_checks.py
```

### Broader (before commit)

```text
./.venv/Scripts/python.exe -m unittest discover -s tests -q
```

**Note:** pytest is not installed in this venv — use `unittest`. `tests/test_bare_assert_files.py` wraps bare `def test_*` functions into TestCases; do not add bare asserts outside that mechanism or they pass vacuously.

## Verification log

| Phase | Command / note | Exit / result |
|-------|----------------|---------------|
| | | |
