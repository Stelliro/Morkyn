# WF3 — Commit the setting corpus, then widen keywords against it

## Goal

The theme keyword table has been changed five times by hand this month, and twice a change had to be reverted because it broke a setting nobody was checking (`scavenger`, `after the collapse`). The 60-setting sweep that caught both was run ad hoc and **was never committed**, so the next person has no gate.

Commit the corpus as a fixture with its expected themes, wire it into the test suite, and only then add the small set of synonyms that the corpus proves are safe.

The corpus is the deliverable. The synonyms are the smaller half.

| ID | Severity | Domain | One-line defect |
|----|----------|--------|-----------------|
| 1 corpus-1 | high | tests_gaps | The 60-setting sweep that caught two bad keywords is not in the repo |
| 2 corpus-2 | med | tests_gaps | No test asserts a keyword change did not re-theme an existing setting |
| 3 kw-1 | low | correctness | `colony ship` is a keyword but `generation ship` is not |
| 4 kw-2 | low | correctness | `terraforming` matches nothing |
| 5 kw-3 | low | correctness | `survey world` / `survey vessel` match nothing |

**Findings 3-5 are candidates, not commitments.** Each one is accepted only if it changes exactly the settings it should and nothing else, judged against the Step 2 corpus. A candidate that moves an unrelated setting is dropped, the way `scavenger` was.

## Sources

| Source | Path | Role |
|--------|------|------|
| Keyword table | `app/setup_composer.py` `LOCATION_THEME_KEYWORDS` | The thing under change |
| Priority order | `app/setup_composer.py:4288` | Niche themes tested before fantasy; fantasy is last |
| Matcher | `app/setup_composer.py` `_theme_keyword_present` | Word-start anchored, suffixes allowed |
| Negation strip | `app/setup_composer.py` `_strip_negated_genre_words` | Drops "no X" / "without X" before matching |
| Existing tests | `tests/test_location_themes.py` | Per-case assertions; extend, do not replace |
| JS mirror | `static/app.js` `START_LOCATION_THEME_KEYWORDS` | Must stay in step with the Python table |
| Mirror harness | `tools/test_start_location_offline_theme.js` | 17 cases; the two tables are checked against each other here |
| Reverted precedent | `wasteland` block comments in `setup_composer.py` | Written record of why `scavenger` and `after the collapse` were removed |

## Context

- The matcher is already anchored at word starts, so `picking` no longer contains `king` and `sector` no longer contains `sect`. New keywords inherit that safety — but **not** safety against a word that legitimately appears in another genre. That is a semantic problem, and only the corpus catches it.
- Fantasy is tested **last**. A new fantasy keyword cannot steal a setting from another theme. A new keyword for any *other* theme can, and must be checked hardest.
- The negation strip runs first, so a keyword does not need a "no X" guard of its own.
- `sci-fi`, `scifi`, `science fiction`, `colony ship`, `interstellar`, `far-future` are **already** in the space list. The gaps are compositional phrases, not missing genre names — do not re-add what is there.
- There is a real ceiling here. Settings like "a courier with a cranial shunt and bad debts" name no genre at all. WF2 is the answer to those, not this workflow. **Do not chase them with keywords.**
- Anything the corpus cannot classify should stay `generic`. A placeless name is a recognisable miss; a wrong-genre name is a bug.

## Constraints

- **The corpus lands first, as its own commit.** Adding keywords in the same commit as the gate that judges them makes the gate meaningless.
- Each candidate keyword is judged individually. Batch additions hide which one broke something.
- A candidate is **rejected** if it changes any corpus setting other than its declared targets. No exceptions, no "close enough" — that is exactly how `scavenger` got in.
- Every keyword added to Python must be added to the JS mirror in the same commit, and `tools/test_start_location_offline_theme.js` must cover it.
- Do **not** add keywords for themes that have no bank. `tools/test_start_location_offline_theme.js` already asserts every keyword theme has one — keep that green.
- Do **not** loosen `_theme_keyword_present` back toward substring matching to make a phrase match.
- Corpus expectations are **recorded judgements**, not ground truth. Where a setting is genuinely ambiguous, mark it as such and assert only that it does not land somewhere clearly wrong.
- Touch map: `app/setup_composer.py`, `static/app.js`, `tests/`, `tools/`. No `llm.py`.

## Steps

### Step 1: Rebuild the corpus
- Status: done
- Actions:
  - Reconstruct the 60 hand-written settings used in the last sweep, spanning: high/low fantasy, space opera, hard sci-fi, cyberpunk, post-apocalyptic, western, gothic, noir, superhero, slice-of-life, historical, horror, xianxia/cultivation, undersea, arctic, desert.
  - Include the negation cases (`no magic`, `no fantasy at all`) and the false-positive traps (`picking`, `sector`, `after the collapse of the old empire`).
  - Include the seven known-unreachable settings, marked `expected: generic` with a comment saying **why** they are unreachable and that WF2 owns them.
- Acceptance: 60+ settings, each with an expected theme and a one-line note where the expectation is a judgement call.
- Verify: Manual read-through; every expectation defensible in one sentence.

### Step 2: Commit the corpus as a fixture
- Status: done
- Actions:
  - Write `tests/fixtures/setting_corpus.json` (or a Python module if that matches repo convention better — check the other fixtures first).
  - Shape: `{"setting": str, "expected_theme": str, "note": str, "ambiguous": bool}`.
  - Write `tests/test_setting_corpus.py` asserting `detect_location_theme` matches `expected_theme` for every non-ambiguous entry, and for ambiguous entries asserts only that the result is in an allowed set.
  - Failure output must name the setting, the expected theme, and the actual — a bare count is useless for diagnosis.
  - **Commit here, before any keyword edit.**
- Acceptance: Suite green against current `main`. Test count rises by the corpus size.
- Verify: `./.venv/Scripts/python.exe -m unittest tests.test_setting_corpus -v`

### Step 3: Add the JS mirror check
- Status: done
- Actions:
  - Extend `tools/test_start_location_offline_theme.js` to read the same fixture and run it through `detectStartLocationTheme`.
  - Any divergence between the Python and JS tables on any corpus setting is a failure.
  - The JS harness extracts source out of `static/app.js` with `extractConst` / `extractFunction`. Note: `extractConst` handles single-line declarations and bracket-walked ones; a new table shape may need it extended.
- Acceptance: Both tables judged by one corpus. Divergence is now impossible to miss.
- Verify: `node tools/test_start_location_offline_theme.js`

### Step 4: Evaluate each candidate keyword, one at a time
- Status: done
- Actions:
  - For each of `generation ship`, `terraforming`, `survey world` / `survey vessel`:
    1. Add only that keyword.
    2. Run the corpus.
    3. Record: settings whose theme changed, and whether each change was intended.
    4. Accept only if the changed set equals the intended set exactly. Otherwise revert it and record why.
  - Add accepted keywords to the JS mirror in the same edit.
  - Add a corpus entry for each newly-covered setting so the keyword has a permanent lock.
  - When rejecting one, leave a block comment next to the theme explaining the rejection — matching the existing `scavenger` / `after the collapse` comments.
- Acceptance: Each accepted keyword has a named corpus setting it fixes and zero collateral changes. Each rejected one has a comment.
- Verify: `./.venv/Scripts/python.exe -m unittest tests.test_setting_corpus -v` after each candidate.

### Step 5: Stop
- Status: done
- Actions:
  - Do not extend the candidate list. If the corpus reveals more gaps, record them in the Verification log as **input to WF2**, not as more keywords.
  - Confirm the remaining `generic` settings still get placeless names, not wrong ones.
- Acceptance: The list of still-unreachable settings is written down and handed to WF2.
- Verify: Verification log names them.

### Step 6: Regression + commit
- Status: done
- Actions:
  - Run Required and Prior-lock blocks.
  - Commit keywords separately from the corpus commit, with the accept/reject record for each candidate in the message.
- Acceptance: All green; the message says what was rejected and why, not only what was added.
- Verify: Full Required block re-run after the final edit.

## Done criteria

- [x] Corpus fixture committed **before** any keyword change
- [x] `tests/test_setting_corpus.py` green on unmodified `main`
- [x] Failure output names setting / expected / actual
- [x] Ambiguous entries marked and asserted loosely
- [x] JS mirror judged by the same corpus
- [x] Each candidate evaluated alone, accept or reject recorded
- [x] Rejected candidates carry an explanatory comment in the table — **vacuous:
  nothing was rejected.** All three moved exactly their declared target and
  nothing else. The existing `scavenger` / `after the collapse` rejection
  comments are untouched.
- [x] Every accepted keyword mirrored into `static/app.js`
- [x] Still-unreachable settings written down and handed to WF2
- [x] No loosening of `_theme_keyword_present`
- [x] Two commits: corpus, then keywords

## Test strategy

### Required (must pass after implement)

```text
./.venv/Scripts/python.exe -m unittest tests.test_setting_corpus -v
./.venv/Scripts/python.exe -m unittest tests.test_location_themes -v
node tools/test_start_location_offline_theme.js
```

### Prior locks (must stay green)

```text
./.venv/Scripts/python.exe -m unittest tests.test_theme_routing -v
./.venv/Scripts/python.exe -m unittest tests.test_start_location_default -v
./.venv/Scripts/python.exe -m unittest tests.test_prompt_exemplar_leak -v
./.venv/Scripts/python.exe tools/him_audit_checks.py
node --check static/app.js
```

### Broader (before commit)

```text
./.venv/Scripts/python.exe -m unittest discover -s tests -q
```

**Fastest meaningful check:** `tests.test_setting_corpus` plus the JS mirror. Run both after every single candidate keyword, not once at the end.

## Verification log

| Phase | Command / note | Exit / result |
|-------|----------------|---------------|
| Step 1-2 | Corpus written: 63 settings, 5 marked `known_failing` | fixture + `tests/test_setting_corpus.py`, 11 tests |
| Step 2 | `unittest tests.test_setting_corpus` on unmodified `main` | green, corpus commit `5f57435` |
| Step 3 | Same fixture through the JS table | **5 mismatches on first run** |
| Step 3 | Diffed the two tables directly | **10 of 11 themes had drifted** |
| Step 3 | Regenerated `static/app.js` from the Python table | 0 mismatches, `node --check` ok |
| Step 4 | `generation ship` alone, full corpus | ACCEPT — 1 setting moved, 0 collateral |
| Step 4 | `terraforming` alone, full corpus | ACCEPT — 1 setting moved, 0 collateral |
| Step 4 | `survey world` + `survey vessel` alone | ACCEPT — 1 setting moved, 0 collateral |
| Step 4 | `sect`+`or` and `heaven`+`ly` suffix guards | both misfires fixed, 0 collateral |
| Step 4 | JS mirror after the guards | **caught the guard missing in JS** — ported, then green |
| Step 6 | `unittest discover -s tests -q` | 678 OK |
| Step 6 | `tools/him_audit_checks.py`, `node tools/test_start_location_offline_theme.js` | exit 0, exit 0 |

## Outcome

**The corpus was the deliverable, and it paid for itself on day one.** Its first
run through the JS mirror found that `static/app.js` and `app/setup_composer.py`
had drifted apart on **ten of the eleven themes** — the JS copy still carried
`scavenger`, the keyword the server had dropped with a written comment
explaining why, and had independently broadened four others (`detective` for
`detective city`, `haunted` and `manor` for `haunted manor`) while missing 40+
the server had. Nothing had ever compared them.

All three candidate keywords were accepted; none was rejected. Two extra
misfires the corpus exposed were fixed with a narrow suffix guard: `sector` read
as `sect` (a fantasy gate-town for an industrial setting) and `heavenly` read as
`heaven` (the afterlife for a cultivation world).

Deviations from the plan, both deliberate:

- The corpus landed with five entries marked `known_failing`, asserted to *still
  fail*, rather than being written to pass. That kept the gate independent of
  the fixes it would later judge, and made removing each flag a visible one-line
  change in the fix commit.
- `LOCATION_THEME_PRIORITY` was hoisted out of `detect_location_theme` (it was a
  local tuple) and is now asserted to cover the keyword table in both
  directions. A theme added to one and not the other was a silent no-op.

Handed to WF2 as keyword-unreachable, per Step 5: *a derelict hauler drifting
past the third moon*, *a courier with a cranial shunt and bad debts*, *someone
wakes up and does not recognise their own hands*, *a letter arrives that should
have been delivered forty years ago*, *two rivals inherit the same failing
business*. WF2 measured them and did **not** improve them — see its own log.
