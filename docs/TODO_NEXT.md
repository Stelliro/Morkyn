# Morkyn — next work list

Go top-down. Send one item at a time (“send him in” = implement that id).

## Done (2026-07 play systems arc)

### Setup / powers / simple
| Id | Item | Notes |
|----|------|--------|
| ~~s1~~ | Powers collapsible dropdown (not always-open tips) | `#powersDropdown` starts collapsed |
| ~~s2~~ | Ability origin **Both** | UI + LLM + world + composer |
| ~~s3~~ | Ability count range 1–4 for randomize | min/max + lock count; shared Simple/Advanced |
| ~~s4~~ | Randomize count policy unified FE/BE | `rollAbilityCountForRandomize` / `_roll_ability_count` |
| ~~s5~~ | Compounding tip → “classic OP MC skill” | |
| ~~s6~~ | Simple Lock + AI on text fields | `data-setup-field`, decorateSimpleSetupFields |
| ~~s7~~ | Simple expand-on-start + depth scoring | `expandSimpleSetupDepth` / `scoreSetupDepth` |

### Clock / wait / weather
| Id | Item | Notes |
|----|------|--------|
| ~~w1~~ | In-world clock | `world_day` / `world_minute` in pacing; UI chip |
| ~~w2~~ | Wait button + `/api/wait` | 1m / 10m / 1h / 6h; RNG then narrate |
| ~~w3~~ | Weather system (server RNG) | start/strength/end; travel mult + event delta; UI line |
| ~~w4~~ | Weather announce for DM | pending → mechanics_context once |

### Map / travel / settlements
| Id | Item | Notes |
|----|------|--------|
| ~~m1~~ | Walk minutes by terrain | road fast, forest slow, etc. |
| ~~m2~~ | Path vs forest ambush tables | roads = safer overall, higher bandit share |
| ~~m3~~ | Multi-tile settlements (~city 48–64 tiles) | `settlements_meta`, roads between hubs |
| ~~m4~~ | Hidden bases (bandit/civilian) | map meta + encounter boost on tile |
| ~~m5~~ | Walk advances clock + weather tick | via `apply_map_travel_step` |
| ~~m6~~ | Settlement ruler seed on first visit | `ensure_settlement_ruler` |
| ~~m7~~ | Ambient move lines (non-blocking) | `build_ambient_move_line`; no scene lock |
| ~~m8~~ | Walk ambush → full scene turn | queue force event + `play_world_event_turn` |

### Events / NPC / social / inventory
| Id | Item | Notes |
|----|------|--------|
| ~~e1~~ | World-event bus | `gm_events` + kind/due/force/payload |
| ~~e2~~ | Quest stage force API | `/api/events/quest-stage`, queue, due |
| ~~e3~~ | NPC presence / power_rank / shell | DB cols + `create_shell_npc` |
| ~~e4~~ | Action skill checks before LLM | talk → persuasion; social attitudes |
| ~~e5~~ | Dice checks default on | `default_check_settings` |
| ~~e6~~ | Walk-away / persist reputation | auto phrases + `/api/social/resolve` |
| ~~e7~~ | Area reputation + association penalty | befriend disliked → others sour |
| ~~e8~~ | Inventory fidelity prompts | `player_inventory_codes` + hard rules |

### Playtest
| Id | Item | Notes |
|----|------|--------|
| ~~p1~~ | Full randomize + 5-turn 8B playtest script | `tools/playtest_full_random_play.py` |

---

## Partial / wired incompletely (do not lose)

| # | Id | Task | Size | Gap |
|---|-----|------|------|-----|
| 1 | **g1** | Wire `apply_event_help_reputation` into event resolution | S | Function exists; **never called** when an event helper NPC aids the player. Hook from `play_world_event_turn` / apply_turn when narration/helpers flag help. |
| 2 | **g2** | Weather extreme → shelter / force weather event | M | Weather changes stats only. No auto `queue_world_event` for “must find shelter” at high strength. |
| ~~3~~ | ~~**g3**~~ | ~~Ambient move LLM micro-narration (optional)~~ | M | Done: `AI_RPG_AMBIENT_LLM` / `settings.ambient_llm`, template default, LLM polish optional |
| 4 | **g4** | Wait duration “until dawn” / custom minutes | S | Only fixed 1 / 10 / 60 / 360. |
| 5 | **g5** | Player free-action minutes by action kind | M | Wait/walk advance clock. Generic player turns do **not** spend minutes by verb (talk/search/fight). |
| 6 | **g6** | `world_epoch_label` / calendar name | S | Planned; not stored or shown. |
| 7 | **g7** | Settlement crowd/danger feed Wait risk live from tile | S | Wait uses density/difficulty + rough location name; not always current map tile + settlement_meta indices. |
| 8 | **g8** | Ruler seed on first **map** enter (not only DB location) | S | Tied to location_id + settlement blob on step; no dedicated “first visit settlement_id” playthrough flag beyond ruler settings key (OK-ish but no visit journal always). |
| 9 | **g9** | Social resolve UI chips after cold chat | S | API + auto phrase detect only; no “Walk away / Keep talking” buttons in play UI. |
| 10 | **g10** | Area rep / faction heat visible UI | S | Stored in settings; not shown as chip near location/weather. |
| 11 | **g11** | Association reverse fully via events | M | `apply_event_help_reputation` exists; association penalty exists; **event help not hooked**; no “settlement liked-outcast” meter. |
| 12 | **g12** | NPC tier enforcement on LLM apply path | M | Shells created by server; apply_turn may still promote throwaways to full stats if model dumps rich NPC updates. |
| ~~13~~ | ~~**g13**~~ | ~~Randomize bool/enum sanitation after 8B rolls~~ | M | Done: `coerce_typed_setup_fields` + enum `magic_level`, wired through sanitize / LLM / crosscheck + `tests/test_setup_sanitation.py` |
| 14 | **g14** | custom_skills ↔ special_abilities alignment | M | Still can diverge (rope seed vs Footprint Echo). Coherence pass soft only. |
| 15 | **g15** | Acquired origin → abilities locked by default in LLM path | S | FE `applyOriginToAbility` does; model can still return unlocked acquired. |
| 16 | **g16** | Simple depth scoring → user-visible Start splash score | S | Logs `console.info` only. |
| 17 | **g17** | Travel scene + free-step concurrency polish | S | Ambush locks long travel; ensure ambient never races scene display. |
| ~~18~~ | ~~**g18**~~ | ~~Prompt trim: fewer remaining examples~~ | M | Done: SYSTEM/COMPACT/DSL example lines tightened |

---

## Not implemented (explicit backlog)

> **Priority note (2026-07-26):** Do **not** start large new systems right now. Focus on fixing/polishing what already ships (setup, resources, art prompts, sanitation, play loop). New features below stay parked until that stabilizes.

| # | Id | Task | Size | Notes |
|---|-----|------|------|--------|
| 1 | **n1** | Full economy simulation | L | Out of scope for time/event arc |
| 2 | **n2** | Real-time multiplayer clock | L | |
| 3 | **n3** | Portraits for nameless shells | S | Intentionally no |
| 4 | **n4** | Replace Continue with Wait | — | Keep both |
| ~~5~~ | ~~**n5**~~ | ~~Time-of-day crowd index (market day vs night)~~ | M | Done: hour bands modulate wait crowd/danger |
| 6 | **n6** | Settlement hierarchy chain officers/workers auto-seed | M | Only ruler seeded |
| ~~7~~ | ~~**n7**~~ | ~~Quest graph UI / stage editor~~ | L | Done: Tools → Quests tab + GET quest-stages / cancel |
| 8 | **n8** | Forced event “blocks player action entirely” mode | S | Force injects into turn; rarely replaces player intent entirely except Continue/Wait early exit |
| 9 | **n9** | Hidden base discovery → map POI reveal + quest hook | M | Encounter exists; no discovery flag progression UI |
| 10 | **n10** | Inventory hallucination hard reject in apply_turn | M | Prompts only; apply layer doesn’t strip invented items |
| 11 | **n11** | Automated regression for wait/weather/rep | S | Unit-ish scripts ad hoc; no CI suite |
| ~~12~~ | ~~**n12**~~ | ~~Playtest re-run after systems + fix 8B inventory~~ | M | Done 2026-07-25: 4/4 turns, solid, 0 hard issues |
| 13 | **n13** | **Capture / restraint: LLM can lock player in place** | L | **Parked — design only.** When the player is **captured** (cell, bonds, custody), the GM/LLM must be able to: (1) **freeze map movement** so free-step/travel cannot walk out; (2) set a **stuck duration** (minutes/hours/days, or **indefinite** until a condition); (3) still allow in-place play (talk, wait, train, invent escape) when escape may require skill growth; (4) **move/set player map position** for escort-to-cell, drag-off, prison transfer (implies server-trusted position apply, not free player teleport spam); (5) **auto-pathing** for forced escorts / “guards take you there” so the map animates a path rather than a hard snap. Gate: only on real capture/restraint outcomes — never casual scene flavor. Depends on clear state (`restrained` / `custody` / location flags), travel hard-block, wait/train while locked, and optional unlock conditions. **Do not implement until current WIP is solid.** |
| 14 | **n14** | **Scene cast + `{NPC}` placeholders (anti gear-as-person)** | L | **Parked — design approved in spirit; implement after integrity polish.** See design notes below. |

---

## Recently closed in autonomous pass

| Id | Status |
|----|--------|
| ~~g1~~ | Event help rep hooked after `play_world_event_turn` |
| ~~g9~~ | Social choice bar: Walk away / Keep talking |
| ~~g10~~ | Area rep line + weather strength % in header |
| ~~n10~~ | `_filter_inventory_changes` rejects invent-gains |
| ~~g13~~ | `_sanitize_setup_randomization_values` for 8B slop |
| ~~g5~~ | `estimate_action_minutes` on player turns |
| ~~g2~~ | Extreme storm/snow/fog queues shelter force event |
| ~~g12~~ | Shell NPC updates stripped of full-cast promotion |
| ~~g14~~ / ~~g15~~ | Sanitize aligns skills + locks acquired |
| ~~g16~~ | Setup depth % on Start splash |
| ~~g7~~ | Wait risk uses map tile + settlement_meta |
| ~~n9~~ | Hidden base discovery → map landmark POI + ambient |
| ~~n6~~ | Ruler + 2 officers + 2 workers on first settlement visit |
| ~~g4~~ | Wait until dawn (−1) + custom minutes UI |
| ~~g6~~ | `world_epoch_label` on clock (from world style) |
| ~~n8~~ | Force/quest events can fully replace player turn |
| ~~g11~~ | Association heat meter on area line; cools on event help |
| ~~n11~~ | `tools/test_play_systems.py` no-LLM regression |
| ~~g3~~ | Optional ambient LLM (`AI_RPG_AMBIENT_LLM=0` default; settings flag) |
| ~~g18~~ | Trimmed example-shaped blocks in SYSTEM / COMPACT / DSL prompts |
| ~~n7~~ | Tools → Quests stage editor + list/cancel APIs |
| ~~n12~~ | 8B full randomize playtest solid (0 hard / 1 soft name silence) |
| ~~n5~~ | Time-of-day crowd/danger bands (dawn/day/market/evening/night) |

## Priority queue (remaining)

| # | Id | Task | Size |
|---|-----|------|------|
| 1 | **n14** | Scene cast + `{NPC}` / `{ITEM}` placeholders + verifier | L |
| — | n1 / n2 / g17 | Optional later | — |

---

## n14 design (scene cast + placeholders) — parked

**Problem (seen in export `ai-rpg-world-1785072774757`):** 8B writes faction lines like  
`L1's allies or I1's rebels` / `travel-stained coat's rebels` — places and inventory used as people. NPCs appear in prose but `npcs` table stays empty.

**Server-first approach (do not trust freeform names):**

1. **`involved` / scene cast (structured, before or with ops)**  
   Deterministic-ish cast list for the beat, e.g.  
   `involved: { npcs: [{slot:"NPC_1", role_hint:"hooded broker", code:null}], items:[{slot:"ITEM_1", ref:"I1"|null}], places:[{slot:"PLACE_1", code:"L1"}] }`  
   Prefer reusing known codes from location/inventory; only invent slots for new faces.

2. **Draft narration with placeholders only**  
   Model (or NAR stage) must write agents as `{NPC_1}`, `{PLACE_1}`, `{ITEM_1}` — never free-text coat/inn as a person.  
   Example: `Choose your side—{NPC_1}'s allies or {NPC_2}'s rebels`.

3. **Bind pass (deterministic)**  
   Map slots → codes/names from `involved` + DB.  
   `{NPC_1}` → `Mara [[A]]`; `{PLACE_1}` → `Second Shadow Inn [[L1]]`; `{ITEM_1}` only for object phrasing (`your travel-stained coat [[I1]]`), never as faction head.

4. **Verifier gates (fail → re-fill placeholders or one repair call)**  
   - Every `{NPC_*}` bound to a **person** name/code (not inventory).  
   - Every `{ITEM_*}` bound to inventory/item type.  
   - Reject gear/place heads with agent verbs / faction possessives.  
   - If model filled a slot with clothing label → reject and re-roll name from `invent_person_name` or re-ask bind only.

5. **Why this works without full LLM trust**  
   Cast size and types are constrained by server; prose may only *refer* to slots; naming is a fill-in map, not free invention mid-sentence.

**Do not implement until:** export integrity fixes (ability codes, equip worn gear, starter item merge bugs, settings pollution) are stable.

---

## Export audit notes (`ai-rpg-world-1785072774757.json`, 2026-07-26)

Integrity / quality issues found (fix when touching apply/setup, not all blocking):

| Severity | Issue |
|----------|--------|
| High | Opening names figures but **`npcs` = 0**; conversation `npc_id` null |
| High | Narration agents as **`L1's` / `I1's`** (code-as-person) |
| High | Ability rows **`code`/`power_type` null** in export payload |
| Med | Item **`water skin [mixed] — stained coat`** (merge/corruption); type clothing |
| Med | Worn gear (coat/boots) **not equipped** into TORSO/FEET |
| Med | Player name **`Sweat Marker`** (setup 8B garbage) |
| Med | Location summary polluted with **setup slogans** (power fantasy / DM stance) |
| Med | **10× `settlement_ruler:Stest*`** + `quest_stages` test pollution in settings |
| Low | Turn summary / history_summaries are **pipeline stubs**, not real scene text |
| Low | Self-check `passed: true` despite short narration + name repairs |

Next optional backlog: n1 economy, n2 multiplayer clock, deeper g17 concurrency polish.

---

## How to dispatch

Reply with an id, e.g.:

- `g1` or `send him g1`
- `g9 then g10`
- `Priority queue top 3`

One id per send keeps diffs reviewable.

---

## File map (systems index)

| System | Primary files |
|--------|----------------|
| Clock / weather | `app/world.py` (`get_world_time`, `tick_weather`, …) |
| Wait | `app/world.py` `play_wait_turn`, `static` Wait UI |
| Map travel / ambush | `app/tile_world.py`, `apply_map_travel_step`, `/api/tiles/map/move` |
| Event bus | `queue_world_event`, `play_world_event_turn`, `/api/events/*` |
| Social / rep | `resolve_social_*`, `/api/social/resolve` |
| Skill checks | `app/skill_checks.py`, pre-resolve in `play_turn` |
| Simple depth | `expandSimpleSetupDepth`, `scoreSetupDepth` in `static/app.js` |
|
