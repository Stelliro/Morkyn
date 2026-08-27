# WF2 — Ask the model for the theme instead of guessing it from prose

## Goal

`compose_setup_intent` already asks the model to classify the setting, but asks for **free text** (`"genre": "short genre/setting phrase"`), which is then fed back through the keyword table. Add a **closed-enum** `location_theme` to the same call, carry it through the intent plan, and let it override the keyword guess.

This fixes settings that describe a genre without naming it — "a generation ship three hundred years from landfall", "first contact goes badly on a survey world" — which a keyword table structurally cannot reach.

Do **not** remove or weaken the keyword table. It stays as the floor. Do **not** add a new model round-trip.

| ID | Severity | Domain | One-line defect |
|----|----------|--------|-----------------|
| 1 enum-1 | med | correctness | The theme is a closed set of 12, inferred from a free-text answer instead of being asked as an enum |
| 2 enum-2 | med | correctness | `merge_intent_plans` allowlists string keys; an unknown key is silently dropped |
| 3 enum-3 | med | correctness | `session_theme_from_intent` builds an explicit dict; an unknown key is silently dropped |

**Findings 2 and 3 are not separate bugs** — they are the two places a new plan key gets discarded if you forget them. They are listed so the implementer does not add `location_theme` in one place and watch it vanish.

## Sources

| Source | Path | Role |
|--------|------|------|
| The classify call | `app/llm.py:5774` `compose_setup_intent` | Already asks the model; already returns JSON |
| The free-text ask | `app/llm.py:5803` | `"genre": "short genre/setting phrase"` inside `return_shape` |
| Plan merge (gate 1) | `app/setup_composer.py:862` `merge_intent_plans` | String-key allowlist at the top of the function |
| Session theme (gate 2) | `app/setup_composer.py:1090` `session_theme_from_intent` | Explicit dict literal — unknown keys dropped |
| The consumer | `app/setup_composer.py:4264` `detect_location_theme` | Already reads `session_theme`; needs an explicit-override path |
| The picker | `app/setup_composer.py:4429` `pick_isekai_arrival_location` | **Already accepts `theme=`** — no signature change needed |
| Reachability | `app/main.py:2908` `api_compose_intent` | The only caller of `compose_setup_intent` |
| UI round-trip | `static/app.js:3946`, `static/app.js:4740` | Where `_compose_intent` is passed back into the roll |
| Enum precedent | `app/llm.py` `_field_contracts_for_prompt` docstring | Documents this exact fix: stop asking an enum an open question |

## Context

- **The precedent is in this file already.** `_field_contracts_for_prompt` was added because the group path asked `magic_level` — a five-value enum — an open question, and got back "low", "Low", "low-magic", "post", and "Limited to arcane crafters and guilds", every one of which fell through to the default. This is the same defect on `location_theme`.
- **Reachability is the main constraint, and it is real.** `compose_setup_intent` has **no in-process caller**. It is reached only through `POST /api/setup/compose-intent`, which the UI calls when the player typed an idea. `_resolve_setup_intent` (`app/llm.py:5861`) falls back to `apply_keyword_intent(idea)` — keywords only — when `_compose_intent` is absent. So this workflow improves the idea-driven path and does nothing for a bare randomize or an offline roll. **That is acceptable and must be stated in the commit message, not quietly implied.**
- `detect_location_theme` already accepts `session_theme` and reads `genre`, `adapter_hint`, `tone`, `style_notes`, `keywords` off it. Adding an explicit theme read is a small change at the top of the function, before the keyword loop.
- The valid theme ids are the keys of `LOCATION_SEEDS_BY_THEME`: celestial, cyberpunk, steampunk, wasteland, space, undersea, arctic, desert, gothic, noir, fantasy, generic.
- A model that answers with a theme outside that set must be **ignored**, not trusted. Unknown label falls back to the keyword result.

## Constraints

- **Do not add a model call.** This rides the existing `compose_setup_intent` request. If it needs a second call, the workflow is wrong — stop and re-scope.
- **Keywords stay as the floor.** `detect_location_theme` must keep working identically when no explicit theme is supplied. Every existing theme test must stay green unchanged.
- **Validate the enum server-side.** Unknown / empty / non-string `location_theme` falls back to keywords. Never let a model string index a dict directly.
- Do not let `location_theme` override a theme the player stated explicitly in prose. If keyword detection returns a **non-generic** theme and the model disagrees, prefer the keyword result — the player's own words outrank the classifier. The model's answer is for the case keywords found *nothing*.
- Touch map: `app/llm.py`, `app/setup_composer.py`. `static/app.js` only if the round-trip drops the key.
- `max_tokens=320` on the intent call is tight. Adding a field costs tokens — confirm the JSON still parses after the change, and raise the cap if it truncates.
- Do not change `merge_intent_plans` precedence semantics for existing keys while adding this one.

## Steps

### Step 1: Prove the two silent-drop gates
- Status: done
- Actions:
  - Before changing anything, write a test that injects a fake `llm_plan` containing `location_theme` into `merge_intent_plans` and asserts it survives; and one that asserts `session_theme_from_intent` carries it.
  - Both must be **red** at this point. This is what stops the "added it, it vanished" failure.
- Acceptance: Two red tests naming the two gates.
- Verify: `./.venv/Scripts/python.exe -m unittest tests.test_location_theme_enum -v` (expect failures)

### Step 2: Ask the enum
- Status: done
- Actions:
  - In `compose_setup_intent` `return_shape` (`app/llm.py:5803`), add alongside `genre`:
    - `"location_theme": "celestial | cyberpunk | steampunk | wasteland | space | undersea | arctic | desert | gothic | noir | fantasy | generic"`
  - Add one rule to the `rules` list: the value must be exactly one of those ids, and `generic` is the correct answer when none of the others fits — it is not a failure value.
  - Keep the free-text `genre` field. It feeds other consumers (`theme_prompt_block`, session theme display) and is not being replaced.
  - Check `max_tokens=320` still suffices; raise if the response truncates.
- Acceptance: The model is asked a closed question. Existing `genre` behaviour unchanged.
- Verify: One live call; confirm valid JSON and a legal `location_theme` value.

### Step 3: Carry it through both gates
- Status: done
- Actions:
  - `merge_intent_plans` (`app/setup_composer.py:862`): add `location_theme` to the string-key loop, but **validate it** — only accept a value in the legal set, lowercased and stripped. An illegal value is dropped, not stored.
  - `session_theme_from_intent` (`app/setup_composer.py:1090`): add `"location_theme": str(intent.get("location_theme") or "")[:40]`.
  - Add the legal-set constant next to `LOCATION_SEEDS_BY_THEME` and derive it from that dict's keys so the two cannot drift.
- Acceptance: Step 1's two tests go green.
- Verify: `./.venv/Scripts/python.exe -m unittest tests.test_location_theme_enum -v`

### Step 4: Let it override, but only where keywords found nothing
- Status: done
- Actions:
  - In `detect_location_theme` (`app/setup_composer.py:4264`), run the existing keyword resolution first.
  - If the keyword result is **not** `generic`, return it — the player named a genre and that wins.
  - If it is `generic`, and `session_theme["location_theme"]` holds a legal id, return that instead.
  - If neither, return `generic` as today.
  - Do not change the priority tuple or the keyword tables in this workflow.
- Acceptance: Keyword-detectable settings resolve exactly as before. Only previously-`generic` settings can change.
- Verify: `./.venv/Scripts/python.exe -m unittest tests.test_location_themes tests.test_theme_routing -v` — all green with **no edits to those files**.

### Step 5: Confirm the UI round-trip does not drop it
- Status: done
- Actions:
  - Trace `lastComposeIntent` from the `/api/setup/compose-intent` response through `static/app.js:3946` and `static/app.js:4740` into `_compose_intent`.
  - If the client copies specific keys rather than the whole object, add `location_theme`.
  - If it passes the object through whole, change nothing and record that.
- Acceptance: The theme the model chose reaches `detect_location_theme` in a real browser roll.
- Verify: One live randomize with an idea like "a generation ship three hundred years from landfall"; confirm the arrival name is a space name, not a placeless one.

### Step 6: Measure on the unnamed-genre set
- Status: done
- Actions:
  - Take the seven settings recorded as unreachable by keywords (WF3 owns the corpus file; use it if WF3 has landed, otherwise inline them).
  - Run each through the idea path and record the resolved theme before and after.
  - Record how many moved from `generic` to a correct theme, and **how many moved to a wrong one** — a confidently wrong classifier is worse than a placeless name.
- Acceptance: Both numbers logged. If wrong-theme count is non-zero, judge whether the trade is worth it and say so explicitly.
- Verify: Numbers in the Verification log.

### Step 7: Regression + commit
- Status: done
- Actions:
  - Run Required and Prior-lock blocks.
  - Commit stating plainly that this covers the **idea-driven path only**, and that bare randomize and offline rolls still use keywords.
- Acceptance: All green; the reachability limit is in the commit message.
- Verify: Full Required block re-run after the final edit.

## Done criteria

- [x] `location_theme` asked as a closed enum in `compose_setup_intent`
- [x] Legal set derived from `LOCATION_SEEDS_BY_THEME` keys, not hand-copied
- [x] Illegal / empty / non-string values rejected, falling back to keywords
- [x] `merge_intent_plans` carries it (test was red first)
- [x] `session_theme_from_intent` carries it (test was red first)
- [x] `detect_location_theme` uses it **only** when the caller's own text
  returned nothing — and, added beyond the plan, the model's free text is now
  ranked below it rather than above
- [x] Existing theme tests pass **unmodified**
- [~] UI round-trip verified end to end — **verified by code trace and an
  automated round-trip test, not by a browser roll.** `lastComposeIntent` is
  assigned whole from `payload.intent` and passed whole into `_compose_intent`;
  `test_it_survives_the_full_client_round_trip` drives the same path in-process.
  No browser was opened.
- [x] Unnamed-genre set measured: corrected count **and** wrong-theme count
- [x] Commit states the idea-path-only limit
- [x] No new model round-trip added

## Test strategy

### Required (must pass after implement)

```text
./.venv/Scripts/python.exe -m unittest tests.test_location_theme_enum -v
./.venv/Scripts/python.exe -m unittest tests.test_location_themes -v
./.venv/Scripts/python.exe -m unittest tests.test_theme_routing -v
./.venv/Scripts/python.exe -m unittest tests.test_start_location_default -v
```

### Prior locks (must stay green)

```text
node tools/test_start_location_offline_theme.js
./.venv/Scripts/python.exe -m unittest tests.test_prompt_exemplar_leak -v
./.venv/Scripts/python.exe tools/him_audit_checks.py
node --check static/app.js
```

### Broader (before commit)

```text
./.venv/Scripts/python.exe -m unittest discover -s tests -q
```

**Regression rule:** if a change here requires editing `tests/test_location_themes.py` or `tests/test_theme_routing.py`, the override is reaching too far. Those files encode the keyword floor and should not move.

## Verification log

Live numbers: `ollama:qwen3:8b`, shipped config, 19 settings per run.

| Phase | Command / note | Exit / result |
|-------|----------------|---------------|
| Step 1 | `tests/test_location_theme_enum.py` written first | red on both gates, as required |
| Step 3 | Same tests after wiring both gates | green |
| Step 5 | Traced `lastComposeIntent` through `app.js` | passes the object whole — **no JS change needed** |
| Step 5 | Found a **third** gate: `_resolve_setup_intent` → `apply_keyword_intent` | spreads the plan whole; survives, now locked |
| Step 6 | `tools/measure_location_theme_enum.py`, first run | enum moved **0** answers; free text moved **15 of 19** |
| Step 6 | Same run, control settings | **3 of 4 overridden** — a bug the enum did not cause |
| Step 6 | After source-authority ordering | control settings overridden: **0 of 7** |
| Step 6 | Unreachable settings, after | 6 right / 6 wrong — **unchanged from before** |
| Step 7 | `unittest discover -s tests -q` | 713 OK |
| Step 7 | `him_audit_checks.py`, JS harness, `node --check static/app.js` | exit 0, exit 0, ok |

## Outcome

**The enum works and did not help. The measurement found a different bug, and
that one was worth the workflow.**

`detect_location_theme` concatenated every source into one blob — the player's
`world_style` and `idea`, the caller's `genre`, and the model's `genre`,
`adapter_hint`, `tone`, `style_notes` and `keywords` — then keyword-matched the
lot and let the priority tuple decide. Priority order was therefore deciding
which **source** won, which is not a decision priority order should make. The
model's free text moved the answer on 15 of 19 settings, including turning "hard
sci-fi orbital station running out of water" into `celestial` on a setting where
the player had written "sci-fi" themselves.

Sources are now tried in order of authority: caller's text → validated enum →
model's free text → generic. Control settings moved off the keyword answer 3
times before and 0 times after.

**On the enum itself, plainly.** Over the 12 settings that resolved `generic` on
the player's text alone, the answer ended right 6 times and wrong 6 times —
exactly where it was before this workflow. The enum only fired 3 times (the
free-text floor took the other 11) and was right once. qwen3:8b also refuses to
answer `generic` for settings that genuinely have no genre: "two rivals inherit
the same failing business" came back `noir`, despite the rule saying `generic` is
a correct answer.

So this workflow does **not** claim better arrival names. Step 6's instruction
was to judge whether the trade is worth it and say so explicitly: on this model,
it is not. The enum is kept because it is cheap, validated, stored where it is
visible, and rides the existing call with no extra round-trip — and because the
numbers are now recorded for whoever revisits it on a larger model.

Deviations worth carrying forward:

- The plan named two silent-drop gates. There are **three**:
  `_resolve_setup_intent` feeds the returned plan back through
  `apply_keyword_intent`. It happens to spread the plan whole, so the key
  survived — but nothing asserted that, and the other two gates prove this
  codebase drops keys quietly.
- `tools/measure_location_theme_enum.py` derives keyword reachability from the
  run rather than from a hand label. The hand labels went stale the moment WF3
  added `generation ship` to the table, and a tool reporting against a stale
  label is worse than no tool.
- The reachability limit holds and is in the commit message:
  `compose_setup_intent` has no in-process caller, so this covers the
  idea-driven path only. A bare randomize or an offline roll still uses
  keywords.
