# Neural welding rig — offline adapters for Morkyn

Morkyn does **not** train weights mid-session. Style / theme shifts come from:

1. **Prompt bias** — `session_theme` (always on for Randomize/Start)
2. **Model routing** — `theme_adapter_map` / `session_theme.theme_model` (turn-time swap)
3. **Offline LoRA / merges** — train **outside** Morkyn, then point Ollama or llama.cpp at the result

The offline trainer lives in a **separate repo**:
**[neural-welding-rig](https://github.com/Stelliro/neural-welding-rig)** (Unsloth LoRA, Gradio chamber).

This doc is the Morkyn-side pack: what that repo actually is after the **2026-07-21** updates, what we can reuse, what must **not** be merged into Morkyn, and how to wire finished adapters.

Morkyn never imports the welding-rig Python package at runtime.  
Both projects use **PolyForm Noncommercial 1.0.0** (compatible for personal / research use).

---

## What the welding rig is (today)

The public repo is an **AI-OR Resonance Chamber** research engine (`ai-or_simulation.py`), not a Morkyn-specific theme-pack factory.

| Capability (2026-07-21) | State |
|-------------------------|--------|
| Load 8B 4-bit (Unsloth) → synth → LoRA weld → save PEFT | **Works** (~8 min on 4070 Ti class) |
| Chat template + **new-token decode** (no prompt echo) | **Improved** |
| Synthetic JSON retries + seed concept shards | **Improved** |
| Explicit PEFT save (no TRL pickle abort) | **Improved** |
| Golden Record restore focus experiment | **Lab success** on dedicated probes (`tests/golden_hitrate.py`) |
| Default chamber base model | `unsloth/DeepSeek-R1-Distill-Llama-8B` |
| Training row shape | `{"instruction","output"}` JSONL |
| Gradio chamber + protocol key auth | Required for interactive use |
| Research-grade EPC package | **Not claimed complete** |

Benchmarks (incomplete engineering tests):  
`benchmarks/chamber-8b-2026-07-21*.md` in the welding-rig repo.

---

## Merge decision map

### Use (offline / patterns) — **yes**

| Piece | Why Morkyn cares |
|-------|------------------|
| Unsloth 4-bit LoRA train loop | Proven path to produce small adapters on consumer GPU |
| Chat-template formatting + decode-only-new-tokens | Avoids garbled “prompt echo” welds when you build Morkyn theme adapters |
| Explicit PEFT `adapter_model.safetensors` save | Reliable export into Ollama / llama.cpp workflow |
| JSONL validation (`min samples`, parse repair) | Reuse idea for theme datasets |
| Windows launcher pattern (`NeuralWeldingRig.bat/.ps1`) | Optional sibling launcher; do not fold into `Morkyn.ps1` game path |
| Short max_steps welds for experiment | Cheap smoke tests before long theme packs |
| Env workspace (`AI_OR_WORKSPACE`) | Keep lab artifacts out of the Morkyn repo |

### Do **not** merge into Morkyn runtime — **no**

| Piece | Why |
|-------|-----|
| Gradio AI-OR chamber UI | Wrong product surface; Morkyn is FastAPI + static RPG UI |
| Golden Record / termination stimuli | Security-research / identity-stress training — not RPG DM voice |
| EPC / Machine Fear / paper concept shards as play data | Will push narration into `[STATE]/[METRICS]` lab dialect, not prose |
| Protocol-key Gradio auth as Morkyn auth | Different threat model; Morkyn is local game |
| Forcing DeepSeek-R1-Distill as Morkyn’s only base | Morkyn already routes Ollama / API / GGUF; adapters must match **your** base |
| Live mid-session welding | Still too slow; keep offline |
| Tunnel (`AI_OR_ENABLE_TUNNEL`) | Lab opt-in only; never enable from Morkyn launcher |

### Conditional — **theme adapters only if you change the data**

The chamber’s **default** synth corpus teaches AI-OR functional metadata.  
That is **not** the same as:

- fair isekai DM openings  
- setup-field hygiene  
- clear `PROSE_VOICE` narration  

To get Morkyn adapters (`morkyn-isekai-dm`, etc.):

1. Build **Morkyn-shaped** JSONL (see dataset outline below).  
2. Train with the welding-rig **train mechanics** (or a thin theme-mode fork), **not** Golden/EPC injection.  
3. Export adapter → Ollama/Modelfile/GGUF matching the **same family** as your Morkyn base.  
4. Register in Morkyn Model → Theme adapter models / session theme model.

---

### Prose reset (read first)

If local narration starts to feel **inverted, hard to scan, or thesaurus-flipped**, do **not** stack more welding weights first.

1. **Clear theme model overrides** in LLM Settings (session theme model + adapter map blanks = base model).  
2. Prefer the **stock base** (e.g. `qwen3:8b` / your GGUF) until voice is readable again.  
3. Morkyn injects a shared **Prose voice** block (`app/prompts.py` → `PROSE_VOICE`): clear subject–verb–object English, varied but plain vocabulary, no literary flip. Theme bias is secondary to that.  
4. When re-welding for Morkyn, train on **clear good narration** you would ship — never AI-OR lab monologues, inverted word order, purple synonym chains, or ornamental templates.

---

## Adapter naming (recommended for Morkyn)

| Adapter tag | Role | When to route |
|-------------|------|----------------|
| `morkyn-isekai-dm` | Fair isekai DM: new-world texture, no chosen-one autopilot, short system windows | `adapter_hint=isekai_rpg` |
| `morkyn-system-rpg` | Status/skill UI framing, rank language, training pressure | `adapter_hint=system_rpg` |
| `morkyn-grimdark` | Harsh stakes, scarce loot, grounded voice | `adapter_hint=grimdark` |
| `morkyn-setup-hygiene` | Setup Randomize only: structure fields clean, no slogan paste | Optional dedicated setup model |
| `morkyn-cozy` | Soft pastoral / low stakes | custom map key or `theme_model` |

Ollama example after export:

```bash
# After welding-rig / Unsloth export to GGUF / Modelfile
ollama create morkyn-isekai-dm -f Modelfile
```

Then in Morkyn **Model → Theme adapter models**:

```
isekai_rpg → morkyn-isekai-dm
```

Or **This session theme model** → `morkyn-isekai-dm` (wins over the map).

---

## Dataset outline (Morkyn theme packs)

Keep JSONL rows small and task-shaped. Prefer **paired** good vs bad when teaching hygiene.

### Export helper

```bash
# From Morkyn repo root — writes welding-compatible instruction/output rows
python tools/export_welding_jsonl.py --out data/welding/morkyn_theme_seed.jsonl
```

That tool emits **seed templates + optional playtest harvest**. It does **not** call the welding chamber.

### A. Setup hygiene (`morkyn-setup-hygiene`)

**Goal:** structure fields stay structure; skill fantasy lives in `custom_skills` / ability `growth_math` only.

| Field class | Positive | Negative (reject / repair) |
|-------------|----------|----------------------------|
| `difficulty` | `normal`, `hard` | `compounding edge`, full idea paste |
| `quest_style` | `job board and personal mysteries` | skill essays, level timers |
| `economy` | `scarce coin markets` | “near-useless skill compounds…” |
| `world_races` | `human`, `human, elf` | `Low-Power Human`, power labels |
| `race_*_rules` | per-listed-race access | foreign races + growth slogans |
| `custom_skills` | seed / tracking / limits | long formula dumps (those go on ability `growth_math`) |
| ability `growth_math` | XP curves, rank thresholds, risk mult | empty slogans only |

Suggested row shape (welding-rig compatible):

```json
{
  "instruction": "Fill setup field quest_style for idea: isekai compounding skill system…",
  "output": "job board and personal mysteries"
}
```

### B. Isekai DM turns (`morkyn-isekai-dm`)

**Goal:** fair pressure, local stakes, optional short system window, no auto-win.  
**Voice:** clear, direct English first; diverse everyday wording; never inverted poetic templates; **never** AI-OR `[STATE]/[METRICS]` lab format.

| Slice | Content |
|-------|---------|
| Opening | New-world disorientation, 2–4 hooks, **one** short diegetic STATUS/SKILL window when `game_system` |
| Weak seed | Seed skill/ability nearly useless; growth math on the ability, not a full toolkit |
| Agency | Player choices not chosen for them; NPCs with local motives |
| Failure | Partial info, costs, lasting injury when edge says so |
| System spam negatives | Multi-window dumps, meta rules essays, free power spikes |

```json
{
  "instruction": "Write opening narration for weak-seed isekai, game_system on, local stakes only.",
  "output": "…short [ STATUS ] block… local hooks… clear prose…"
}
```

### C. System RPG / grimdark (optional packs)

- **system_rpg:** ranks, training gates, brief UI, check friction  
- **grimdark:** scarce loot, social knives, no blue-window fantasy unless requested  

### Volume targets (practical)

| Pack | Minimum useful | Comfortable |
|------|----------------|-------------|
| Setup hygiene | ~200 field pairs | 500–1k |
| Isekai DM openings | ~50 | 150+ |
| Isekai mid-turn | ~100 | 400+ |
| Negatives (auto-win / slogan) | ~50 | 150+ |

Quality beats volume: every positive should be something you would ship in Morkyn.

---

## Recommended workflow (welding-rig → Morkyn)

1. Keep **neural-welding-rig** checked out **beside** Morkyn (or any path outside the game server).  
2. Export / write Morkyn theme JSONL (`tools/export_welding_jsonl.py` + hand rows + playtests).  
3. In the welding-rig lab workspace, **replace** AI-OR synth data with your Morkyn JSONL (do not train Golden Record into a DM model you will ship).  
4. Weld LoRA on a base you already run in Ollama (match family: Qwen / Llama / etc.).  
5. Merge or serve adapter; create an Ollama model tag (`morkyn-isekai-dm`).  
6. In Morkyn Model modal:
   - set **Theme adapter models** map, and/or  
   - set **This session theme model** for one run.  
7. Keep **session_theme prompt bias** on — routing swaps weights; prompt still enforces DM fairness and `PROSE_VOICE`.

Optional later (not required now): a `theme_mode` fork of the chamber that skips Golden/EPC and only SFT-trains `instruction`/`output` theme rows. Until then, treat AI-OR chamber as **research**, Morkyn packs as **separate datasets**.

---

## Routing recap

```
session_theme.theme_model   → highest priority (manual / this session)
theme_adapter_map[hint]     → next
main ollama_model / api_model / gguf → default
```

See also: `docs/SetupComposer.md` (session theme + adapter map), `docs/PLAYTEST_SMOKE.md` (isekai smoke).

---

## Acceptance checks

- [ ] Isekai Randomize → map routes to `morkyn-isekai-dm` when tag exists  
- [ ] Blank map → main model still plays  
- [ ] Session theme model field overrides map for one playthrough  
- [ ] Setup fields never re-learn slogan paste after hygiene adapter  
- [ ] Openings: local stakes + optional one system window; no free god-mode  
- [ ] Theme adapters trained on **clear Morkyn prose**, not AI-OR lab dialect  
- [ ] No welding-rig Gradio / protocol key / tunnel wired into Morkyn start scripts  

---

## Bottom line

| Question | Answer |
|----------|--------|
| Did the welding rig get major useful updates? | **Yes** — train/save/decode/synth path is much healthier for offline LoRA work. |
| Should we vendor the chamber into Morkyn? | **No.** |
| Can we use it for Morkyn theme adapters? | **Yes, only with Morkyn datasets** and matching base model; not with default Golden/EPC data. |
| What “merge” means for Morkyn | Docs + export bridge + routing you already have — **not** runtime AI-OR. |
