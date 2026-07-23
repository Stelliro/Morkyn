# Setup Composer Tree + Session Theme Bias

## Why

Full Randomize used to walk a flat field list and stamp the idea box onto every field. That produced slogan paste (`difficulty = "compounding edge"`) and weak isekai fidelity once play started.

Morkyn now treats setup generation as a **dependency tree**:

1. **Intent** (root) — compile the idea into a structured plan  
2. **World frame → peoples → difficulty → progression → people → identity → powers**  
3. **Session theme** — durable DM + genre lean for the whole playthrough  

## Composer load order

Source of truth: `app/setup_composer.py` (`SETUP_COMPOSER_PHASES`, `FIELD_CONTRACTS`).

| Phase | Depends on | Fields (summary) |
|-------|------------|------------------|
| intent | — | compiler only |
| world_frame | intent | world_style, tone, tech, magic, economy, custom_style |
| world_peoples | world_frame | races + race magic/ability rules |
| difficulty_edge | world_frame | difficulty, death, loot, inventory… |
| progression | difficulty + world | leveling, system UI, skill growth… |
| people | world + difficulty | npc density, quests, ranks… |
| identity | world + peoples | backstory, names, start location… |
| powers | identity + progression + peoples | ability origin + abilities |

API:

- `GET /api/setup/composer` — phases, field_order, contracts  
- `POST /api/setup/compose-intent` — `{ idea, current? }` → intent, session_theme, field_overrides  

Frontend `RANDOM_FIELD_ORDER` mirrors `field_order` and refreshes from the API.

## Field contracts

Each field has:

- `kind` — enum / short_phrase / prose / number / boolean / abilities  
- `intent_keys` — which intent plan keys may influence it  
- `forbidden` — e.g. never paste the full idea slogan into `difficulty`  
- `allowed_values` — for enums  

The randomizer prompt receives `field_contract` + `field_intent` (sliced keys only).

## Intent + keyword overrides

Before the LLM walk:

1. **Keyword pass** (always) — isekai, system UI, compounding, near-useless, easy/hard…  
2. **Optional LLM refine** — one short JSON plan  
3. **Deterministic field_overrides** — e.g. isekai → `game_system=true`, compounding → fast growth speeds, difficulty enum only  

Hard overrides are applied first; the tree walk then fills remaining fields without overwriting those enums/bools.

## Session theme bias (on-the-fly “weights”)

Stored in `playthrough_options.session_theme` at Start:

```json
{
  "adapter_hint": "isekai_rpg",
  "genre": "isekai dark fantasy",
  "isekai": true,
  "dm_stance": "fair pressure, player agency, no chosen-one autopilot",
  "power_fantasy": { "start_power": "near_useless", "growth": "compounding", "system_ui": true },
  "style_notes": "…",
  "theme_model": ""
}
```

On every turn, `app/llm.py` appends a **theme block** to the system / DSL prompts:

- DM fairness and `world_state` stay primary  
- Genre lean (isekai RPG texture, system windows when enabled) is secondary  
- No auto-win / chosen-one autopilot  

This is the practical “optimize thoughts on the fly per session” path for local models: **prompt soft-bias**, not training.

### Theme adapter routing (turn-time model swap)

Model settings may include an optional map:

```json
"theme_adapter_map": {
  "isekai_rpg": "morkyn-isekai-dm:latest",
  "system_rpg": "",
  "grimdark": "",
  "default": ""
}
```

At **turn** time (not setup Randomize), Morkyn resolves:

1. `session_theme.theme_model` if set (per-playthrough override)  
2. else `theme_adapter_map[session_theme.adapter_hint]` if non-empty  
3. else the main Ollama / API / GGUF model  

Provider behavior:

| Provider | Override applies to |
|----------|---------------------|
| Ollama | `ollama_model` |
| OpenAI-compatible | `api_model` |
| llama.cpp | `gguf_model_path` when the value looks like a path / `.gguf`; otherwise recorded as label only |

Empty map entries keep the main model. Routing is scoped to the turn so global settings stay unchanged. Traces record `theme_model_source` and `theme_model_active`.

Edit the map in the Model modal under **Theme adapter models (optional)**.

### Manual session theme model (t8)

In the same Model modal block:

- **This session theme model** — Ollama tag / API model / GGUF path for **this** playthrough only.  
- Wins over `theme_adapter_map`.  
- Setup: stored in client `lastSessionTheme` and sent at **Start**.  
- Mid-run: **Save Model** POSTs `/api/session-theme` `{ "theme_model": "…" }` (blank clears).

## Neural welding rig (offline weight shift)

Full pack: **[docs/WeldingRig.md](WeldingRig.md)** (merge map, dataset outline, adapter names, wiring).

[neural-welding-rig](https://github.com/Stelliro/neural-welding-rig) is the **offline Unsloth LoRA lab** (AI-OR Resonance Chamber). After the **2026-07-21** updates the **pipeline** (load → synth → weld → PEFT save → clean decode) is solid. It is **not** vendored into Morkyn.

| Approach | Feasible in Morkyn? |
|----------|---------------------|
| Full fine-tune per session | No |
| Train tiny LoRA mid-session | No (too slow) |
| Hot-swap prebuilt theme models via map | **Yes** (`theme_adapter_map` / `theme_model`) |
| Soft bias via session_theme prompt | **Yes** |
| Ship AI-OR Golden Record / EPC chamber data as DM voice | **No** — wrong dialect; keep research separate |

Recommended workflow:

1. Export / write Morkyn theme JSONL (`python tools/export_welding_jsonl.py`) — good setup fills + fair isekai DM turns (+ negatives).  
2. Train adapters **offline** with welding-rig LoRA mechanics (or any Unsloth SFT) on a base you already run — **do not** train default Golden/EPC shards into a shippable DM model.  
3. Name adapters e.g. `morkyn-isekai-dm`, `morkyn-setup-hygiene`.  
4. Register them in Model → **Theme adapter models** (e.g. `isekai_rpg` → `morkyn-isekai-dm`), or set **This session theme model**. Morkyn still injects `session_theme` so DM stance is explicit.

Morkyn does **not** depend on the welding repo at runtime.

## Opening / first-turn feel

At Start, when the setup is weak-start / compounding / system-ui:

1. **Weak skill seed** — one `player_skills` row (default `Observation`, or a name from `custom_skills`) with value `1`.
2. **Opening prompt block** — once-only diegetic system window (if `game_system`), seed visibility, stakes matched to difficulty/edge.
3. **Fallback opening** — if the model fails, still shows a short STATUS/SKILL window when game system is on.

Isekai + compounding intent also turns **dice checks** on with difficulty aligned to the run (Checks tab).

See `docs/PLAYTEST_SMOKE.md` and `python tools/smoke_isekai_open.py`.

## Consistency lint (cross-field)

After per-field contamination cleanup, `sanitize_setup_fields` runs a second pass:

| Check | Action |
|-------|--------|
| `race_magic_rules` / `race_ability_rules` invent peoples not in `world_races` | Rebuild rules from the listed races only |
| `memory_policy` vs `backstory_mode` / `character_backstory` wording | Prefer adjusting `memory_policy` (fragments ↔ known, former-life claims, etc.) |

## Anti-slogan post-lint

Structure fields (`quest_style`, `faction_pressure`, `economy`, `npc_stat_scaling`, `world_races`, race rules, …) reject:

- growth slogans (`compounding`, `near-useless skill`, `snowball`, …)
- growth timers (`1 hour per level`, `24-hour cooldown`, …)
- full idea paste
- power labels as races (`Low-Power Human`)

On contamination: one LLM repair attempt (single-field), then **deterministic structural fallback**.  
Isekai intent also **seeds** clean structure fields and the Randomize walk skips re-rolling those so the LLM cannot re-paste skill slogans into them.  
Skill fantasy belongs in `custom_skills` / growth speeds / abilities only.

## Success checks

- Idea mentions isekai + compounding + system → `difficulty` is easy/normal/hard/brutal (not a slogan); `game_system` tends on; growth fields accelerate; abilities start weak/locked.  
- `quest_style` / `rank_scale` / `economy` stay short structure fields — never skill essays.  
- During play, model receives theme bias while still following mechanics and player agency.
