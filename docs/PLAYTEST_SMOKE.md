# Isekai playtest smoke (t9)

## Automated

```bash
python tools/smoke_isekai_open.py
```

- Always checks **weak skill seed** + **dice defaults** after Start.
- If Ollama is up, runs **opening + 3 turns** with an isekai compounding setup.
- Writes `report.json` under a temp dir (path printed).

Env knobs: `OLLAMA_BASE_URL`, `PLAYTEST_OLLAMA_MODEL` / `OLLAMA_MODEL`.

## Manual checklist

1. New game → director seed **Isekai compounding** (or paste that idea) → **Randomize**.
2. Confirm **Compiled plan** shows isekai / growth / system UI.
3. Checks tab: dice **On**, difficulty aligned, unskilled mishaps sensible.
4. Skills / custom skills: weak seed **Observation** (or named seed).
5. **Start** → opening should include:
   - local playable hooks  
   - **one** short diegetic system window when game system is on  
   - weak skill visible once  
   - stakes matching difficulty (not world-ending, not free power)
6. Play **3 turns**: look around / ask directions / approach a board. Note:
   - no auto-win  
   - no full free skill toolkit  
   - system windows not spammed every paragraph  
   - dice friction only when risky (if checks on)

Log failures under `docs/TODO_NEXT.md` or a short issue note.
