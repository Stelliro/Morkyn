# Benchmarks

Self-contained playthrough and pipeline benchmarks for **Mørkyn**.

Harnesses live here. Generated run output goes under `benchmarks/reports/` (gitignored). Unit tests live in `tests/`.

| Path | Purpose |
| --- | --- |
| `run_dual_role_playtest.py` | **Preferred:** dual-role GM + player over Mørkyn `apply_turn`/SQLite. No Ollama. Fast. |
| `run_long_playtest.py` | Optional stress path: real local LLM as GM, scripted player. Slow on 8B. |
| `compare_narration_pipeline.py` | Compare narration pipeline on / off |
| `reports/` | JSON + live logs from each run (gitignored artifacts) |

## Dual-role run (GM + player, no local model)

From the repo root:

```powershell
python benchmarks/run_dual_role_playtest.py
```

Defaults:

- **100 turns** after opening
- **Player role:** chooses actions from beat book + world state
- **GM role:** writes narration + structured turn JSON
- **Backend:** `start_playthrough` + `apply_turn` only (isolated temp DB)
- Reports under `benchmarks/reports/dual-*` (gitignored)
- **Also writes** the public showcase:
  - `docs/showcase/100-turn-lore-teaser.md`
  - `docs/showcase/100-turn-metrics.json`

Latest release snapshot: **100 turns · 0 errors · ~4.9 s · ~45 ms/apply**.

```powershell
$env:GROK_BENCH_TURNS = "20"
python benchmarks/run_dual_role_playtest.py
```

## Local-LLM run (optional / slow)

```powershell
python benchmarks/run_long_playtest.py
```

Uses Ollama as GM. On 8B, plan on multi-minute turns.

## Narration pipeline

Adaptive paragraph narration (packed context, model-tier budget, cascade coherence, attempt ledger):

- Design: [`docs/NarrationPipeline.md`](../docs/NarrationPipeline.md)
- Module: `app/narration_pipeline.py`
- Wired into `generate_turn` when `AI_RPG_NARRATION_PIPELINE=1` (default **off**)
- Unit tests:

```powershell
python tests/test_narration_pipeline.py
```

Comparison harness:

```powershell
python benchmarks/compare_narration_pipeline.py
```

## Attempt ledger

When the pipeline runs, each turn can write:

```text
data/model_traces/turn-000042-narration-ledger.json
```
