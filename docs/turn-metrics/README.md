# Turn metrics (local models)

Measured wall-clock times for Mørkyn turns against a **local qwen3:8b**. Hardware and load vary; treat these as order-of-magnitude guidance, not guarantees.

## qwen3:8b (Q4_K_M) — 2026-07-17

| Setting | Value |
| --- | --- |
| Provider | local model |
| Model | `qwen3:8b` (8.2B, Q4_K_M) |
| Context | 32768 tokens |
| Draft mode at test time | Legacy JSON draft + verify + repair loops |
| Response caps | soft 1200 / hard 1800 tokens |

### Full multi-turn playtest (`playtest_timed_turns.py`)

Source report: [qwen3-8b-2026-07-17.json](qwen3-8b-2026-07-17.json)

| Step | Wall time | Fallback? |
| --- | ---: | --- |
| Opening | **185.9 s** (~3.1 min) | No |
| Turn 1 | **114.0 s** (~1.9 min) | Yes (missing narration in model JSON) |
| Turn 2 | **180.8 s** (~3.0 min) | No |
| Turn 3 | **193.5 s** (~3.2 min) | No |
| **Total (opening + 3 turns)** | **674 s** (~11.2 min) | 1 of 4 |
| **Mean per step** | **~169 s** (~2.8 min) | — |

Typical prompt sizes in that run (estimated tokens):

| Phase | Mean est. tokens | Max |
| --- | ---: | ---: |
| draft | ~9 200 | ~9 600 |
| verify | ~4 400 | ~4 700 |
| narration_depth_retry | ~10 300 | ~10 600 |

Most wall time is multi-call generation (draft → repair/salvage → verify → depth), not SQLite.

### Opening + one player turn (smoke)

| Step | Wall time | Fallback? |
| --- | ---: | --- |
| Opening | **98.3 s** | No |
| Turn 1 | **128.6 s** | No |
| Total | **~227 s** (~3.8 min) | No |

### What this means in practice

- On a local **8B** model with full draft+verify, expect **roughly 1.5–3.5 minutes per turn**.
- Faster paths after NAR+OPS draft mode (`AI_RPG_DRAFT_MODE=dsl`) aim to cut JSON repair loops; re-measure after major pipeline changes with:

```powershell
python tools/playtest_timed_turns.py
```

Reports write under local `data/playtest_reports/` (gitignored). Copy noteworthy runs into this folder when publishing.
