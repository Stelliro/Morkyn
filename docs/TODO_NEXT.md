# Morkyn — next work list

Go top-down. Send one item at a time (“send him in” = implement that id).

## Done recently (context)
- Composer tree + intent + session theme prompt bias
- Structure-field anti-slogan lint (quest/faction/economy/NPC…)
- Sex randomize weighted toward male/female
- **t1** Theme adapter routing (`theme_adapter_map` + `session_theme.theme_model` at turn time)
- **t2** Consistency lint (race rules ↔ `world_races`; memory_policy ↔ backstory)
- **t3** Export/import `session_theme` + compose intent in setup settings JSON
- **t4** Intent summary UI after Randomize / Load Settings
- **t6** Director presets (isekai compounding, grimdark, cozy, …)
- **t5** Opening feel: diegetic system window prompt, weak skill seed, stakes
- **t9** Isekai smoke tool + checklist (`tools/smoke_isekai_open.py`, `docs/PLAYTEST_SMOKE.md`)
- **t10** Dice-check defaults for system/isekai
- **t8** Session theme model field + `/api/session-theme`
- **t7** Welding-rig pack doc (`docs/WeldingRig.md`)

---

## Priority queue

| # | Id | Task | Size | Notes |
|---|-----|------|------|--------|
| 1 | ~~t1~~ | Theme adapter routing | M | **Done** |
| 2 | ~~t2~~ | Consistency lint | S | **Done** |
| 3 | ~~t3~~ | Export/import `session_theme` | S | **Done** |
| 4 | ~~t4~~ | Intent summary UI | S | **Done** |
| 5 | ~~t5~~ | Opening / first-turn feel | M | **Done** |
| 6 | ~~t6~~ | Director presets | S | **Done** |
| 7 | ~~t7~~ | Welding-rig offline pack | S/docs | **Done** — `docs/WeldingRig.md` |
| 8 | ~~t8~~ | Manual theme model override | S | **Done** |
| 9 | ~~t9~~ | Playtest smoke | S | **Done** |
| 10 | ~~t10~~ | Dice-check isekai defaults | S | **Done** |

---

## Suggested batches

**Batch A — clean Randomize (quick wins)**  
~~`t2` → `t3` → `t4` → `t6`~~ **done**

**Batch B — themed local models**  
~~`t1` → `t8` → `t7`~~ **done**

**Batch C — feel in play**  
~~`t5` → `t9` → `t10`~~ **done**

**All queued items complete.**

---

## How to dispatch

Reply with an id, e.g.:

- `t2` or `send him t2`
- `Batch A`
- `t1 then t8`

One id per send keeps diffs reviewable.
