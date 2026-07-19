# Adaptive Paragraph Narration Pipeline

## Problem

Local **8B** models often hit soft/hard response caps and context pressure, then produce short, repetitive, or shallow single-shot narration. The current pipeline drafts **one whole turn** (DSL or JSON), optionally verifies once, then may **retry the entire narration** if too short (`_ensure_narration_depth`). That is expensive and still fails at packing:

- One call must invent structure, facts, and prose together under a small token budget.
- Depth retries re-send the whole turn and invite **doubling** or drift.
- There is no durable **source of truth** for “what we already tried” vs “what the player has been told.”

## Goals

1. **Pack context** — feed each micro-call only what it needs.
2. **Adaptive length** — paragraph count from **scene density** (events, people, places, items, action intensity) **and model tier** (8B lean; larger models richer).
3. **Paragraph-at-a-time** — draft each paragraph alone against a fixed brief.
4. **Cascade coherence** — check Pₙ against Pₙ₋₁; on pass, check Pₙ₋₁ against Pₙ₋₂ (and so on) so no doubling and continuity holds.
5. **Whole-scene agent** — one pass that reads all paragraphs together and issues **surgical edits**, not full rewrites.
6. **Attempt ledger** — source of truth for attempted claims, said facts, failed edits, and final accepted text.

Non-goals (v1): replace OPS/state application; rewrite combat math; require cloud models.

## Roles

| Agent | Job | Must not |
| --- | --- | --- |
| **Budget planner** | Choose `paragraph_count`, per-paragraph max tokens, and which scene entities get a beat | Invent story facts |
| **Paragraph writer** | Write **one** paragraph for one beat | Re-open prior beats; rewrite whole scene |
| **Adjacent checker** | Compare pair (A, B): overlap, contradiction, timeline | Rewrite freely; only pass / fail + edit ops |
| **Cascade walker** | After Pₙ accepted, re-check (Pₙ₋₁, Pₙ₋₂) … | Skip when no edit touched earlier text |
| **Scene consolidator** | Read full stack: “same entity twice / two intents at once / fix or merge” | Dump a brand-new scene unless ledger says rewrite allowed |
| **Ledger** | Append-only log of attempts, accepts, rejects, said-facts | Be regenerated from memory each call without persistence |

## Adaptive budget

### Scene density score (deterministic)

```text
density =
  + active_npcs_in_location (cap 4)
  + distinct_locations_touched (cap 3)
  + inventory_or_item_focus (0–2)
  + event_pressure (0–3)
  + combat_or_high_risk_intent (0–3)
  + player_action_complexity (0–2)
```

### Model tier (from config / context window / response cap)

| Tier | Heuristic | Default paragraphs | Chars / paragraph | Total soft target |
| --- | --- | ---: | ---: | ---: |
| `small` | context ≤ 8k or soft cap ≤ 900 or name matches 7b/8b | 2–4 (openings ≥3) | 320–480 | **≥900** |
| `medium` | context ≤ 16k or soft cap ≤ 1500 | 3–4 | 320–480 | **≥1100** |
| `large` | else | 4–6 | 350–550 | **≥1400** |

**Density inputs** pull NPCs from `locations[].npcs` (get_state does not nest them on `current_location`), top-level `npcs`, and prompt working sets. Events and inventory use the same multi-shape collectors.

**Consolidator skip:** when paragraph count ≤ 2 **and** density score &lt; 7, the LLM consolidator is skipped (cheap heuristic de-dupe only) to save a call on lean turns.

Clamp with `narration_detail` (`concise` −1 para, `expansive` +1). Never below 1 or above 6.

8B should **prefer fewer packed paragraphs** over one long failed generation + depth retry.

## Per-paragraph brief (packed context)

Each writer call receives only:

```json
{
  "beat_index": 1,
  "beat_count": 3,
  "beat_role": "establish|act|react|consequence|choice",
  "must_cover": ["Eldrin warns about north road", "do not open letter"],
  "may_mention": ["[[N1]]", "[[L1]]", "[[I1]]"],
  "forbidden_repeat": ["facts already in said_facts"],
  "previous_paragraph_tail": "last 400 chars of accepted P_{n-1}",
  "player_intent": "...",
  "location_now": "Mosswake Gate",
  "model_limits": {"max_tokens": 220, "max_chars": 420}
}
```

State OPS remain outside this loop (DSL/JSON draft for deltas, or a separate compact OPS pass). **Narration pipeline owns prose segments only** in v1.

## Cascade check algorithm

```text
accepted = []
for i in 1..N:
  draft_i = write_paragraph(brief_i, ledger)
  ledger.record_attempt(draft_i)

  pair_ok = check_adjacent(accepted[-1], draft_i) if accepted else pass
  while not pair_ok and attempts < max:
    draft_i = apply_edit_ops(draft_i, pair_ok.ops)   # surgical
    ledger.record_attempt(draft_i)
    pair_ok = check_adjacent(accepted[-1], draft_i)

  if not pair_ok: salvage or shrink beat; continue

  accepted.append(draft_i)
  # Walk backward only if this draft required edits to earlier text (rare)
  # or consolidator requested cascade:
  for j from len(accepted)-1 down to 1:
    ok = check_adjacent(accepted[j-1], accepted[j])
    if not ok:
      accepted[j], accepted[j-1] = apply_pair_edits(...)  # prefer edit later para
      ledger.record_pair_fix(j-1, j, ok)

scene = consolidate(accepted, ledger)  # whole-stack agent
final_segments = scene.paragraphs
```

**Adjacent checker outputs** (structured, small):

```json
{
  "pass": false,
  "issues": [
    {"type": "double", "detail": "bandits mentioned twice with same wording"},
    {"type": "contradiction", "detail": "Eldrin left then is still present"},
    {"type": "dual_intent", "detail": "buying and fleeing treated as simultaneous without bridge"}
  ],
  "edit_ops": [
    {"target": "later", "op": "delete_span", "match": "..."},
    {"target": "later", "op": "replace_span", "match": "...", "with": "..."},
    {"target": "earlier", "op": "soft_bridge", "with": "Once the warning landed, ..."}
  ]
}
```

Prefer editing the **later** paragraph. Earlier text is frozen unless consolidator marks a hard conflict.

## Source of truth: attempt ledger

Persisted per turn under model traces / temp (same turn id as existing traces):

```text
data/model_traces/turn-000042-narration-ledger.json
```

Shape:

```json
{
  "turn": 42,
  "player_input": "...",
  "budget": {"tier": "small", "paragraphs": 3, "density": 7},
  "said_facts": [
    {"id": "f1", "text": "Eldrin warned of bandits on the north road", "para": 1, "status": "accepted"}
  ],
  "attempts": [
    {
      "id": "a1",
      "kind": "write|adjacent_check|edit|cascade|consolidate",
      "para_index": 1,
      "input_digest": "...",
      "output_text": "...",
      "status": "accepted|rejected|superseded",
      "issues": [],
      "edit_ops": [],
      "ts": "..."
    }
  ],
  "final_paragraphs": ["...", "..."],
  "final_narration": "joined..."
}
```

**said_facts** = what the player has effectively been told (accepted text claims).  
**attempts** = full history so agents do not re-try the same failed wording.

## Integration with current pipeline

```text
[existing] planner context + OPS/DSL draft (state deltas)
        ↓
[new, flag] narration_pipeline.build_segments(context, player_input, draft_ops_summary)
        ↓
merge narration_segments + narration into turn JSON
        ↓
[existing] verify (can stay lighter if ledger already pair-checked)
        ↓
apply_turn
```

Feature flag:

| Env | Default | Meaning |
| --- | --- | --- |
| `AI_RPG_NARRATION_PIPELINE` | `0` | `1` / `on` enables adaptive paragraph pipeline inside `generate_turn` |
| `AI_RPG_NARRATION_PIPELINE_MAX_EDITS` | `2` | Max surgical edit loops per pair |
| `AI_RPG_NARRATION_PIPELINE_CONSOLIDATE` | `1` | Run whole-scene consolidator (LLM when pipeline is on) |

When off, behavior is unchanged (DSL/JSON + depth retry).

### Wiring (current)

After DSL/JSON draft (+ optional verify), `generate_turn` calls `_ensure_narration_quality`:

1. If flag **off** → legacy `_ensure_narration_depth` only when under 1000 chars.  
2. If flag **on** → `run_narration_pipeline` with:
   - **writer** = packed `_chat_text` per paragraph  
   - **consolidator** = whole-stack `_chat_text` returning `===P1===` blocks  
   - **ledger** under `AI_RPG_MODEL_TRACE_DIR` / `turn-NNNNNN-narration-ledger.json`  
3. If pipeline output is still under ~65% of tier soft target, fall back to legacy depth retry.

OPS/state fields from the draft are kept; only `narration` / `narration_segments` are replaced.

## Why this helps 8B

- Each call is **small** (one paragraph, ~200 tokens out) → less soft-cap collapse.
- Context is **packed** (no full novel prompt every time).
- Doubling is caught **locally** before the whole scene is committed.
- Failed wording is recorded so the next attempt is not identical.
- Larger models simply get a **higher paragraph budget**, same machinery.

## Implementation map

| File | Responsibility |
| --- | --- |
| `docs/NarrationPipeline.md` | This design |
| `app/narration_pipeline.py` | Budget, ledger, cascade, edit apply, orchestrator |
| `app/llm.py` | Optional call sites behind flag (later PR) |
| `app/prompts.py` | Micro-prompts for writer / checker / consolidator (later PR) |
| Model traces dir | Ledger JSON persistence |

## Acceptance criteria

1. With flag on, a turn produces `narration_segments` length == planned budget (or budget−1 on salvage).
2. Ledger file exists for the turn with attempts + said_facts + final text.
3. Adjacent checker rejects deliberate double-paragraph fixtures in unit tests.
4. Surgical `replace_span` does not rewrite untouched paragraphs.
5. Flag off: existing smoke/playtest behavior unchanged.
6. Small tier plans ≤3 paragraphs for low-density scenes; large tier can plan ≥4 for high-density.

## Rollout

1. Land module + unit tests + design (this change).  
2. Wire `generate_turn` behind flag; dual-path metrics in `benchmarks/`.  
3. Tune prompts on qwen3:8b; measure chars, fallback rate, wall time vs baseline.  
4. Make default-on only after 8B playtests stay within time/quality targets.
