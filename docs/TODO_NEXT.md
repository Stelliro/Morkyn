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
| ~~1~~ | ~~**g1**~~ | ~~Wire `apply_event_help_reputation` into event resolution~~ | S | Done; see Recently closed. Function exists; **never called** when an event helper NPC aids the player. Hook from `play_world_event_turn` / apply_turn when narration/helpers flag help. |
| ~~2~~ | ~~**g2**~~ | ~~Weather extreme → shelter / force weather event~~ | M | Done; see Recently closed. Weather changes stats only. No auto `queue_world_event` for “must find shelter” at high strength. |
| ~~3~~ | ~~**g3**~~ | ~~Ambient move LLM micro-narration (optional)~~ | M | Done: `AI_RPG_AMBIENT_LLM` / `settings.ambient_llm`, template default, LLM polish optional |
| ~~4~~ | ~~**g4**~~ | ~~Wait duration “until dawn” / custom minutes~~ | S | Done; see Recently closed. Only fixed 1 / 10 / 60 / 360. |
| ~~5~~ | ~~**g5**~~ | ~~Player free-action minutes by action kind~~ | M | Done; see Recently closed. Wait/walk advance clock. Generic player turns do **not** spend minutes by verb (talk/search/fight). |
| ~~6~~ | ~~**g6**~~ | ~~`world_epoch_label` / calendar name~~ | S | Done; see Recently closed. Planned; not stored or shown. |
| ~~7~~ | ~~**g7**~~ | ~~Settlement crowd/danger feed Wait risk live from tile~~ | S | Done; see Recently closed. Wait uses density/difficulty + rough location name; not always current map tile + settlement_meta indices. |
| 8 | **g8** | Ruler seed on first **map** enter (not only DB location) | S | **Built, not wired** (2026-10-08): see Built but not tied in. Tied to location_id + settlement blob on step; no dedicated “first visit settlement_id” playthrough flag beyond ruler settings key (OK-ish but no visit journal always). |
| ~~9~~ | ~~**g9**~~ | ~~Social resolve UI chips after cold chat~~ | S | Done; see Recently closed. API + auto phrase detect only; no “Walk away / Keep talking” buttons in play UI. |
| ~~10~~ | ~~**g10**~~ | ~~Area rep / faction heat visible UI~~ | S | Done; see Recently closed. Stored in settings; not shown as chip near location/weather. |
| ~~11~~ | ~~**g11**~~ | ~~Association reverse fully via events~~ | M | Done; see Recently closed. `apply_event_help_reputation` exists; association penalty exists; **event help not hooked**; no “settlement liked-outcast” meter. |
| ~~12~~ | ~~**g12**~~ | ~~NPC tier enforcement on LLM apply path~~ | M | Done; see Recently closed. Shells created by server; apply_turn may still promote throwaways to full stats if model dumps rich NPC updates. |
| ~~13~~ | ~~**g13**~~ | ~~Randomize bool/enum sanitation after 8B rolls~~ | M | Done: `coerce_typed_setup_fields` + enum `magic_level`, wired through sanitize / LLM / crosscheck + `tests/test_setup_sanitation.py` |
| ~~14~~ | ~~**g14**~~ | ~~custom_skills ↔ special_abilities alignment~~ | M | Done; see Recently closed. Still can diverge (rope seed vs Footprint Echo). Coherence pass soft only. |
| ~~15~~ | ~~**g15**~~ | ~~Acquired origin → abilities locked by default in LLM path~~ | S | Done; see Recently closed. FE `applyOriginToAbility` does; model can still return unlocked acquired. |
| ~~16~~ | ~~**g16**~~ | ~~Simple depth scoring → user-visible Start splash score~~ | S | Done; see Recently closed. Logs `console.info` only. |
| 17 | **g17** | Travel scene + free-step concurrency polish | S | **Built, not wired** (2026-10-08): see Built but not tied in. Ambush locks long travel; ensure ambient never races scene display. |
| ~~18~~ | ~~**g18**~~ | ~~Prompt trim: fewer remaining examples~~ | M | Done: SYSTEM/COMPACT/DSL example lines tightened |

---

## Not implemented (explicit backlog)

> **Priority note (2026-07-26):** Do **not** start large new systems right now. Focus on fixing/polishing what already ships (setup, resources, art prompts, sanitation, play loop). New features below stay parked until that stabilizes.

| # | Id | Task | Size | Notes |
|---|-----|------|------|--------|
| 1 | **n1** | Full economy simulation | L | **Built, not wired** (2026-10-08): `app/economy.py`; see Built but not tied in. Out of scope for time/event arc |
| 2 | **n2** | Real-time multiplayer clock | L | **Built, not wired** (2026-10-08): `app/realtime_clock.py`; see Built but not tied in. |
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
| 13 | **n13** | **Capture / restraint: LLM can lock player in place** | L | **Built, not wired** (2026-10-08): `app/restraint.py`; see Built but not tied in. **Parked — design only.** When the player is **captured** (cell, bonds, custody), the GM/LLM must be able to: (1) **freeze map movement** so free-step/travel cannot walk out; (2) set a **stuck duration** (minutes/hours/days, or **indefinite** until a condition); (3) still allow in-place play (talk, wait, train, invent escape) when escape may require skill growth; (4) **move/set player map position** for escort-to-cell, drag-off, prison transfer (implies server-trusted position apply, not free player teleport spam); (5) **auto-pathing** for forced escorts / “guards take you there” so the map animates a path rather than a hard snap. Gate: only on real capture/restraint outcomes — never casual scene flavor. Depends on clear state (`restrained` / `custody` / location flags), travel hard-block, wait/train while locked, and optional unlock conditions. **Do not implement until current WIP is solid.** |
| 14 | **n14** | **Scene cast + `{NPC}` placeholders (anti gear-as-person)** | L | **Built, not wired** (2026-10-08): `app/scene_cast.py`; see Built but not tied in. **Parked — design approved in spirit; implement after integrity polish.** See design notes below. |
| 15 | **n15** | **Prices and trade (user request 2026-10-08, from playtest #69)** | L | **Built, not wired** (2026-10-08): `app/trade.py`; see Built but not tied in. (1) **Prices invented as play goes and then kept:** the first time an item is priced, the engine records it; later sales of that item use it, so base goods (bread, cheese, rope, a night's lodging) cost the same every time. (2) **Average rates and a fluctuating market:** each recorded price feeds a per-item running average; a settlement's price moves around that average with supply, season, scarcity and the setting's economy (barter-heavy worlds price in goods as well as coin). (3) **Prices stated clearly:** the seller names a price in the prose, and the gold the engine takes is that number, never a separately rolled band. (4) **Confirm / deny before paying:** a purchase is an offer the player accepts or refuses (buttons), not something the narration does for them. (5) **Haggle / barter option** on that offer, resolved by the engine (skill, relationship, the seller's mood), with a counter-offer. (6) **Ask for other options:** request different goods or a cheaper or better alternative from the same seller. Relates to n1 (full economy simulation); this is the smaller, per-item version. |
| 16 | **n16** | **Hunger and thirst (user request 2026-10-08; later, not now)** | M | **Built, not wired** (2026-10-08): `app/needs.py`; see Built but not tied in. Two needs that fall over world time and rise with food and drink. Low hunger slows recovery. Low hydration brings on fatigue and drains energy and health. Hunger and thirst held fairly low for a sustained time cut recovery substantially. Needs the world clock (w1), eating and drinking as engine actions (food items consumed from inventory), and status lines the prose must respect. |
| 17 | **n17** | **Currency by theme (user request 2026-10-08; major rework, not now)** | L | **Built, not wired** (2026-10-08): `app/currency.py`; see Built but not tied in. The money a world uses follows its theme, so there are several currencies, each with its own rules (denominations, conversion, what is accepted where). **Middle ages / fantasy:** 100 copper = 1 silver, 100 silver = 1 gold, 100 gold = 1 platinum. Other themes (sci-fi credits, modern cash, post-collapse scrip or goods) get their own sets. The engine stores money in the smallest unit and shows it in the theme's coins; prices (n15) are kept in that unit. Today a single `gold` number is used everywhere (player state, rewards, GOLD bands, UI), so every one of those needs moving. |
| 18 | **n18** | **Goods-for-service trade (user request 2026-10-08)** | L | **Built, not wired** (2026-10-08): `app/agreements.py`; see Built but not tied in. Deals that are not coin for goods, made by the engine as an agreement with terms. Example: "I'll give you these 15 iron ore if you forge me a blade; anything left over you keep." The agreement records what each side gives, the work owed, when it is due, and what happens to leftovers; the ore leaves the player's inventory when handed over, the blade arrives when the job is done (over world time), and the leftover goes to the smith. Shares the offer / accept / haggle flow with n15, and fits barter-heavy economies. |
| ~~19~~ | ~~**n19**~~ | ~~**Alleyways in town grids (user request 2026-10-08)**~~ | M | **Already exists** (the user found them; town_grid `_alleys`). Kept for the note below. | A lane class below the smallest road: narrow passages between and behind plots, connecting back streets and giving more ways through a block. Walkable, drawn thinner on the Streets map, slower or riskier at night, and a place for back doors, shady venues and short cuts. Goes with the cross-cell road fix (playtest #70). |
| ~~20~~ | ~~**n20**~~ | ~~**Accept / decline prompt for quests (user request 2026-10-08)**~~ | M | **Done** (2026-10-08): every quest the story offers is stored as an offer (quests.status 'offered'); a strip between the narration and the input shows the newest two with Accept, Decline and Ask about it (Ask only focuses the input). POST /api/quests/{id}/accept and /decline go through quests.accept_offered / decline_offered, the one place an offer changes; the parser's accept/decline updates and a typed 'I'll take the job' (only when it can mean one offer) use them too. Decline stores status 'declined', and the parser refuses the same job for 30 turns (declined_before). The narrator is told who offered what and that it waits for an answer. The Quests list has the same buttons. Not tested yet; user to test by hand. | When someone offers a job or quest, the engine makes it a pending offer and the player gets Accept / Decline buttons (and can ask more first). Only Accept creates the quest. Fixes offers that never become quests (#81) and quests that start without the player agreeing. |
| ~~21~~ | ~~**n21**~~ | ~~**Walk-with prompt (user request 2026-10-08)**~~ | M | **Done** (2026-10-08): the engine owns one fact, a lead on offer, and acts only on a button. A lead the town resolver read and did not walk (rule town_led_unasked, the T11 'Bertram leads you to the Blind Owl Forge'), or the new LEAD op (aliases FOLLOW_ME, INVITE, ESCORT, GUIDE) whose person is here, becomes Go with <name> / Stay under the narration (app/turn_prompts.py, settings row turn_prompts, snapshotted). Go walks the player through the streets and into the place (town_moves planner, whole-town budget) and the leader's row goes with them; a lead with no place named puts them on the scene thread and in the party, so later moves carry them; a lead to a place outside this town sets it as the destination and travels with them. Stay is remembered for 5 turns and the narrator is told (world_state.open_leads), so they do not ask again. A typed 'I go with him' answers the prompt, and a lead the player asked for now brings the leader along too. Idioms ('in the long run', 'run out of', 'run a shop') no longer make a line travel. Not done: a LEAD outside a plotted town does not trim prose that already walked the player. Not tested yet; user to test by hand. | When a person asks the player to come along, or offers to lead them ('follow me', 'I'll take you there'), the player gets Go with them / Stay. Going moves the player with that person (the state moves, not just the prose, #76); staying keeps them put. |
| 22 | **n22** | **Travel-to prompt for named places and quest markers (user request 2026-10-08)** | M | **Partial** (2026-10-08; fixed: travel prompts and the engine route; not fixed: questions about wild places such as hunting grounds still get no engine answer, and the destination is not drawn on the map). Travel there / Set as destination / Not now come only from engine facts: a direction the engine told (direction_hint), a [[L#]] place, a known plot, or a known person (by name, or 'the <job>' when one person has it) named in what someone here says, and the place of a quest step when the quest is taken. The direction hint is resolved once from the player's own line (the reference footer made 'I go into Blind Owl Forge' a question about tools) and the map records that same hint; a where-question needs a real ask ('where', 'is there a', 'know of', '?'). Travel walks the streets, leaves by the town exit planner (#71: a gate that must stop you does), then takes world-map steps as a map click does (4 tiles a press), stopping at a gate, exhaustion, a blocked way or an encounter (which plays its scene). A set destination keeps a Travel chip until you arrive or clear it (settings row travel_destination, snapshotted). Not tested yet; user to test by hand. Gaps built, not wired (2026-10-08): app/wild_places.py, static/ui/destination_marker.js. | When someone says where a person or place is ('she's at the mill', 'the camp is past the north road'), or a quest step has a marker, the player gets a prompt to travel there (or set it as the destination), routed by the engine through streets and the world map, and stopped only where the route really stops them (#71). |
| 23 | **n23** | **Body-location health and healing states (user request 2026-10-08; big overhaul, user will design in depth)** | XL | **Built, not wired** (2026-10-08): `app/body_health.py`; see Built but not tied in. Health tracked per body location (head, torso, each arm, each leg, ...) instead of one HP number, each wound with a severity and states such as bleeding, infected, broken, bandaged, splinted, healing. Treatment changes those states as engine facts: a bandage on a severely wounded arm stops that arm bleeding; it does not heal it outright. Wounds affect what the player can do (a bad arm hampers two-handed work and climbing, a bad leg slows travel), bleed or worsen over world time if untreated, and heal over time with rest and care. The prose must respect the current states. Ties to n16 (hunger and thirst slow recovery). **State model (user direction):** a fixed, pre-written set of basic states the engine owns and enforces (e.g. bleeding, bandaged, broken, infected, healing), each with its own rules; the model may add modifier states on top (a named, descriptive layer such as 'poultice of yarrow' or 'stitched badly') that refine a basic state but never replace it or bypass its rules. Parked until the user writes the design. |
| ~~24~~ | ~~**n24**~~ | ~~**Text to speech for the narration — TOP PRIORITY (user request 2026-10-08)**~~ | L | **Done** (2026-10-08): one setting, three backends: Local (Piper, the `piper-tts` package on the CPU), OpenAI-compatible API, ElevenLabs; off by default (settings row tts_config, env AI_RPG_TTS_*). app/tts.py owns the config, the preset catalog, text cleaning (no [[codes]], bare codes, markup, op or debug lines), sentence-aware chunking, the provider calls, the Piper install and voice download, and a status probe; routes GET/POST /api/tts-config, GET /api/tts-catalog, POST /api/tts-status, POST /api/tts/speak (one paragraph in, wav or mp3 out; 400 off / empty / not ready, 409 GPU busy, 503 unreachable), POST /api/tts/install. Controls: one Play / Pause / Stop bar under the turn's narration (paragraph by paragraph, the next paragraph fetched while one plays), right-click in the narration for Play selected text / Play this paragraph / Stop, no per-paragraph buttons; playback stops when a turn, Continue, Wait, Regenerate or Rewind is sent. Local synthesis takes the GPU gate and answers 409 instead of queueing while a turn or image job holds it; cloud calls skip the gate. Presets: six Piper voices (en_US lessac, amy, ryan, joe; en_GB alan, alba; 22050 Hz, about 63-115 MB each, downloaded on first use into data/tts-voices; the engine installs from a button), OpenAI gpt-4o-mini-tts / tts-1 / custom OpenAI-compatible URL (nine named voices), ElevenLabs Multilingual v2 / Turbo v2.5 / Flash v2.5 (five named voices). Settings (provider, voice or preset, speed, API key, Test, Install local speech engine) in the main-menu Settings panel and the play menu's Speech item. Kokoro and XTTS-v2 were evaluated and not shipped (docs/TextToSpeech.md). Not tested yet; user to test by hand. | Read the story aloud. Two backends behind one setting: a cloud TTS API, and a local TTS engine. They never run at the same time: the player listens, then decides, so speech never competes with a turn for the GPU or the model. Controls: no per-paragraph play buttons (they clutter the prose; user decision). Instead, select text in the narration and right-click: a custom context menu with **Play selected text**; a right-click inside a paragraph with no selection offers **Play this paragraph**. One **Play** button at the bottom of the turn's narration that plays the whole turn; pause/stop, and stop automatically when the player sends the next turn. Speak only the shipped narration text (no [[codes]], markup or debug lines), paragraph by paragraph so playback can start before the whole turn is synthesised. Provider, voice and speed in settings; off by default. **Base models (user request):** ship a short list of pre-configured, known-good TTS models and voices for both backends, so players do not have to hunt for one and each has working settings out of the box (sample rate, voice id, speed, chunking). Candidates to evaluate for local: Piper, Kokoro, XTTS-v2; for API: OpenAI-compatible TTS endpoints and ElevenLabs. Pick by quality, speed on a 12 GB GPU or CPU, licence, and install size; the local model downloads on first use like the LLM. |

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
| ~~n24~~ | Text to speech (2026-10-08): `app/tts.py`, `/api/tts-*`, Play bar and right-click read-aloud, Piper / OpenAI-compatible / ElevenLabs presets; not hand-tested yet |

## Priority queue (remaining)

| # | Id | Task | Size |
|---|-----|------|------|
| 1 | **n14** | Scene cast + `{NPC}` / `{ITEM}` placeholders + verifier | L |
| — | n1 / n2 / g17 | Optional later | — |

Everything else on the list is built and parked unwired (see below); the next step is to turn items on one at a time.

---

## Built but not tied in (2026-10-08)

These modules exist in the repo with tests, and nothing in the live game imports, loads or calls them: no table is created by `init_db`, and no route, prompt line or UI element exists for them, so the current build plays exactly as it did before they were added. The docstring at the top of each module names every hook point (as `file.py:function()` and the one call that hook would make) and carries a Turn on checklist; `docs/BuiltNotWired.md` collects all of them on one page with the shared shapes they agree on. Each test file has a `test_module_is_a_leaf` case that fails as soon as any file under `app/` or `static/` names the module, so an accidental wiring is caught by the suite.

| TODO id | Module and test | What exists | Not connected (hook points) | Turn on | Tests |
|---|---|---|---|---|---|
| **n17** | `app/currency.py`, `tests/test_currency.py` | Currency sets by theme (`theme_set`, `detect_theme_set`, `active_set`), every amount an int of the smallest unit, `format_amount` / `parse_amount` / `convert`, the legacy bridges `from_legacy_gold` / `to_legacy_gold`, the settings row `currency_config`, and `MIGRATION_PLAN` for the single `player.gold` number. | `app/world.py:_apply_player()`, `_reconcile_prose_with_state()`, `resolve_turn_bands()`, `start_playthrough()`, `get_state()`, `build_prompt_context()`; `app/prose_state.py:stated_coin_amounts()`; `app/quests.py:pay_quest_completion()` / `create_quest()` | read `currency_config` in `get_state`; delete it in `_clear_playthrough`; migration steps 1-12 (step 1 is the only schema change); optional `GET/POST /api/currency-config`; purse display; one coin-words prompt line | 34 |
| **n1** | `app/economy.py`, `tests/test_economy.py` | Tables `market_state` (one row per settlement and goods category) and `market_events`, settings row `economy_config`; `settlement_profile`, `settlement_multiplier` (the price multiplier trade reads), `tick_day` / `tick_day_proposal` (world-event proposals, never inserted), `ensure_settlement`, `market_lines`. | `app/world.py:advance_world_time()` (day boundary), `apply_map_travel_step()`, `queue_world_event()` (the proposals, run after the commit), `build_prompt_context()`; `app/trade.py:settlement_price()` (in-pass consumer) | flag `economy_sim_enabled`; `ensure_schema` in `_migrate_columns`; `WORLD_TABLES` / `RESTORE_ORDER` / `AUTOINC_TABLES`, `market_state` snapshot like `quest_clocks`, `_clear_playthrough`; the tick and ensure calls; market facts in the prompt | 35 |
| **n15** | `app/trade.py`, `tests/test_trade.py` | Tables `price_ledger`, `price_index`, `trade_offers`; `record_turn_prices` (first price kept), `settlement_price`, `make_offer` / `open_offer` / `accept_offer` / `decline_offer` / `counter_offer`, `resolve_haggle` / `run_haggle`, `alternatives_for`, `answer_from_line`, `fulfilment_proposal`, `state_view`. | `app/world.py:apply_turn()` (three seats), `_settle_purse()`, `get_state()`, `_apply_turn_npc_relationship_deltas()`, `_apply_inventory()` / `_apply_player()`; `app/main.py:_answer_offer()` | flag `trade_offers_enabled`; `ensure_schema`; table registry entries (`price_index` snapshot like `quest_clocks`); routes `POST /api/trade/{id}/accept`, `/decline`, `/haggle`, `/alternatives`; an offer strip in the `renderOfferPrompt` style; one open-offers prompt line | 49 |
| **n18** | `app/agreements.py`, `tests/test_agreements.py` | Tables `agreements`, `agreement_events`; `draft_terms`, `terms_as_offer` (a trade offer of kind service or barter), `haggle_terms`, `agree`, `tick` (lifecycle over world time), `hand_over_proposal` / `delivery_proposal` / `cancel_proposal`, `status_lines` / `prompt_block`, `state_view`. | `app/world.py:advance_world_time()`, `apply_turn()` (two seats), `get_state()`, `build_prompt_context()`; `app/main.py:_answer_offer()` | flag `agreements_enabled` (needs `trade_offers_enabled`); `ensure_schema`; table registry entries; routes `GET /api/agreements`, `POST /api/agreements/{id}/cancel`; a list in the Quests tab; the prompt block | 27 |
| **n16** | `app/needs.py`, `tests/test_needs.py` | Settings row `player_needs` (hunger and thirst 0..100); `tick` / `tick_and_save`, `detect_intent`, `eat` / `drink` / `consume_from_inventory` (inventory changes as proposals), `recovery_modifier` / `merge_recovery`, `status_lines` / `prompt_block`, `state_view`. | `app/world.py:advance_world_time()`, `_spend_travel()`, `play_wait_turn()`, `play_turn()`, `apply_turn()`, `get_state()`, `_build_mechanics_context()`; `app/player_resources.py:apply_regen()` | flag `needs_enabled`; `SNAPSHOT_SETTING_KEYS += "player_needs"` (no `init_db` change); the tick, the eat/drink detection, the regen multiplier; the prompt block; two chips under the resource bars | 46 |
| **n23** | `app/body_health.py`, `tests/test_body_health.py` | Tables `body_wounds`, `body_health_log`; `LOCATIONS` (head, torso, arms, hands, legs), `BASIC_STATES`, `TREATMENTS`; `add_wound`, `wounds_from_health_delta` / `wounds_from_injury`, `health_from_body`, `apply_treatment` / `treat_from_inventory`, `tick` / `tick_and_save`, `capabilities`, `move_verdict`, `recovery_modifier`, `add_modifier`, `status_lines` / `prompt_block`, `state_view`. | `app/db.py:_migrate_columns()`; `app/world.py:_apply_player()`, `play_turn()` (two seats), `advance_world_time()`, `play_wait_turn()`, `_spend_travel()`, `get_state()`; `app/tile_world.py:move_player()`; `app/skill_checks.py:resolve_check()`; `app/encounters.py:assess_danger()`; `app/player_resources.py:apply_regen()`; `app/turn_dsl.py:OPCODES` (`WOUND_NOTE`, reserved, not added) | flag `body_health_enabled`; `ensure_schema`; table registry with a whole-table snapshot of `body_wounds`; the health mapping, the tick, the treatment detection, the capability hooks in travel and checks; the prompt block; a body panel | 57 |
| **n13** | `app/restraint.py`, `tests/test_restraint.py` | Settings row `restraint`, table `restraint_log`; `may_move` / `may_move_state` (the travel hard-block verdict), `allowed_actions`, `classify_capture` / `propose_capture` / `capture` / `transfer` / `release`, `tick` (time and condition release), `plan_escort` / `apply_position` (server-trusted position set), `runtime_flags`, `parse_restraint_op`, `status_lines` / `prompt_block`, `state_view`. | `app/db.py:_migrate_columns()`; `app/main.py:_location_special_runtime()`, `_travel_press()`, `api_tile_map_move()`; `app/world.py:_map_is_locked()`, `_apply_player()`, `apply_turn()`, `play_turn()`, `build_prompt_context()`, `play_wait_turn()`, `advance_world_time()`, `apply_map_travel_step()`, `play_world_event_turn()`, `get_state()`; `app/town_moves.py:plan_exit()` / `walk_out()` / `walk_to_cell()` / `click_walk()`; `app/turn_prompts.py:walk_in_town()`; `app/turn_dsl.py:_apply_op()` | flag `restraint_enabled`; `ensure_schema`, `"restraint"` in `SNAPSHOT_SETTING_KEYS`, `restraint_log` registry entries; the movement guards; the turn hooks; a `restraint` world-event kind; `RESTRAIN` / `RELEASE` / `ESCORT` ops and legend; the travel-status label; one system prompt rule | 48 |
| **n14** | `app/scene_cast.py`, `tests/test_scene_cast.py` | No table, no settings row; `build_involved` (the cast as slots `NPC_1` / `ITEM_1` / `PLACE_1`), `find_placeholders`, `bind` (slots to `Name [[CODE]]`), `verify` (gates), `propose_repairs` / `apply_repairs`, `npc_rows_for_apply`, `resolve_pending_cast`, `entity_map_from_context`; reports ride on `turn["_dsl"]["scene_cast"]`. | `app/llm.py:_try_dsl_draft()`, `_normalize_turn()`, `_verification_policy()`, `generate_turn()`; `app/turn_dsl.py:ops_to_turn()`, `build_dsl_user_prompt()`; `app/world.py:apply_turn()` (two seats); prompt text in `app/turn_dsl.py:DSL_SYSTEM_PROMPT` and `app/prompts.py` | flag `scene_cast_enabled`; `involved` in the context packet; the placeholder rule in the DSL prompt; bind, gates and repairs at the three `llm.py` seats; the two apply hooks; no schema, route or UI | 53 |
| **g8** | `app/settlement_visits.py`, `tests/test_settlement_visits.py` | Table `settlement_visits` (one row per settlement id); `record_enter`, `enter_from_travel`, `enter_from_city`, `seed_proposal` (ruler, two officers, two workers), `journal_line`, `is_first_visit`, `state_view`; `REENTRY_GRACE_MINUTES = 30`. | `app/world.py:apply_map_travel_step()`, `build_ambient_move_line()`, `get_state()`; `app/town_moves.py:enter_town()` (and `sync_after_world_move` in `app/main.py` must pass the turn) | no flag; `ensure_schema`; `WORLD_TABLES` / `RESTORE_ORDER` / `_REPLACE_ONLY_WHEN_EXPORTED`, snapshot like `quest_clocks`, export by `map_id`, `_clear_playthrough`; the two hook calls; "for the first time" in the ambient line | 37 |
| **n22** (wild places) | `app/wild_places.py`, `tests/test_wild_places.py` | No table, no settings row; `parse_wild_question` / `is_wild_question` (hunting grounds, ford, cave, ruin, standing stones, fresh water, high ground, woods, marsh, road, hidden camp), `scan`, `nearest`, `resolve_wild_question` (a `local_intel` direction hint with `place.kind == "wild"`), `travel_candidate`. | `app/local_intel.py:turn_direction_hint()`, `apply_turn_intel()`, `_record_hint()`; `app/turn_prompts.py:gate_after_turn()` | no flag; the two `local_intel` calls, the `_record_hint` guard, the `gate_after_turn` candidate line; no schema, route, UI or prompt | 40 |
| **n2** | `app/realtime_clock.py`, `tests/test_realtime_clock.py` | Settings row `realtime_clock` (enabled, paused, ratio, preset, anchor, slice and cap); `elapsed_world_minutes`, `plan_catch_up` (Wait-sized slices), `catch_up`, `wait_effects`, `pause` / `resume` / `reset_anchor`, `get_config` / `update_config`, `state_view`. Hosted multiplayer is a documented non-goal. | `app/main.py` (the `api_tts_config` pattern for `GET/POST /api/realtime-clock` and `POST /api/realtime-clock/tick`); `app/world.py:play_turn()` / `play_wait_turn()`, `start_playthrough()`, `rewind_last_turn()`, `get_state()`; `static/app.js:startGenerationProgressPolling()` (the poller pattern) | `enabled` in its own row (no playthrough flag); the tick and config routes; pause / resume around a turn, `reset_anchor` on start, re-anchor on rewind; ratio and pause controls plus the poller; no prompt | 38 |
| **g17** | `static/ui/scene_sequence.js`, `tools/test_scene_sequence.js` | `window.MorkynSceneSequence`: `enqueueScene`, `enqueueAmbient`, `tokenOf`, `reset`, `create`; scenes show one at a time, an ambient line waits for the stream and is dropped when its turn is older than the last scene shown, a third scene finishes the current one. | `static/app.js:displayTurnPayload()`, `showAmbientMoveLine()`, `streamTextToTargets()`, `rewindTurn()` / `startGame()`; the script line in `static/index.html` | the script line; the two wraps; `reset()` on rewind and new game; no server change | 26 |
| **n22** (map marker) | `static/ui/destination_marker.js`, `tools/test_destination_marker.js` | `window.MorkynDestinationMarker.draw(canvas, destination, player, mode)` for the lens, the Large map, the Settlement canvas and Streets: a flag on the target cell, a rim arrow when it is off the window, a ring on the player's own cell, a box around a plot; reads only the canvas meta and the destination it is given. | `static/app.js:refreshLocalMap()`, `refreshFullMap()`, `paintSettlementCanvas()`, `paintTownCanvas()`, optional `renderMovePrompt()`; the script line in `static/index.html` | the script line; the four `draw()` lines after each painter's own markers; no server change | 20 |

Decisions to make when wiring (from the reconciled contracts; none of them blocks the parked code):

- Gold migration: `currency.MIGRATION_PLAN` moves the single `player.gold` number into smallest units in twelve steps, and with `coin_medieval` one legacy gold becomes 10000 copper. `trade.REFERENCE_GOLD` is fitted to today's prose (a loaf is "a couple of coins", the player starts with 12), not to a realistic medieval price list; whether to re-fit the prose prices is a user decision.
- Escort legs on world-scale charts: `restraint.plan_escort` plans the path, but `tile_world.move_player` cannot step on a world chart, so the apply loop must use token moves; which existing walker it copies is a wiring choice.
- The "player down" combat outcome: the deterministic combat emits only `hit`, `glancing_hit`, `miss`, `resolved`, `unresolved`, so today only the health-ratio rule can corroborate a capture; adding an outcome word to the deterministic path is for the wiring pass.
- Wild places on world charts: landmarks and hidden bases are always empty there, so caves, ruins, stones and camps are answered only where a knowledge marker exists; a later item would stamp landmarks from terrain.
- The `WOUND_NOTE` op: the name is reserved; its place in `turn_dsl.OPCODES` and its legend text need the draft-flow owner when a DSL change is allowed.
- g8 power bands and re-entry grace: `ensure_settlement_ruler` uses power 50 for world cities and ignores bands; `settlement_visits.POWER_BY_BAND` takes effect only if the wiring passes the proposal's `ruler_power_rank`; and a `left_turn` column could replace the 30-minute `REENTRY_GRACE_MINUTES` once `sync_after_world_move` has a hook.
- `trade_drain` into `economy.advance_market_row` is 0 in this pass; feeding it from the ledger (`sold_quantity / population_factor`) is a later item.
- Body locations: feet are folded into legs (the injury vocabulary has "hand" but no "foot") and hands are included; adding feet is one row in `body_health.LOCATIONS` plus capability rules.
- `economy.market_lines()` stays a list of world facts, not status lines; revisit if the prompt wants one block for everything.

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

Next optional backlog: none left unbuilt; n1 economy, n2 clock and g17 sequencing are built and parked (see Built but not tied in).

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
| Text to speech | `app/tts.py`, `/api/tts-config`, `/api/tts-catalog`, `/api/tts-status`, `/api/tts/speak`, `/api/tts/install`; `window.morkynSpeech`, `renderTtsPlayBar`, `renderTtsSettings` in `static/app.js`; `speechItems` in `static/ui/interact.js`; `docs/TextToSpeech.md` |
| Built, not wired | `app/currency.py` (n17), `app/economy.py` (n1), `app/trade.py` (n15), `app/agreements.py` (n18), `app/needs.py` (n16), `app/body_health.py` (n23), `app/restraint.py` (n13), `app/scene_cast.py` (n14), `app/settlement_visits.py` (g8), `app/wild_places.py` (n22), `app/realtime_clock.py` (n2), `static/ui/scene_sequence.js` (g17), `static/ui/destination_marker.js` (n22); tests `tests/test_<module>.py`, `tools/test_scene_sequence.js`, `tools/test_destination_marker.js`; nothing in the live game calls them; `docs/BuiltNotWired.md` |
