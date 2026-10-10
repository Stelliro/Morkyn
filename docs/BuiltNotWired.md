# Built, not wired

Thirteen pieces of the work list (eleven Python modules, two browser files) are written, tested and parked. The live game does not call any of them, so the current build plays exactly as it did before they were added. This page is the one place a wiring pass needs: the rule they all follow, every hook point and Turn on checklist copied from the code, the shapes they agree on, and the decisions still open. The summary table with test counts is in `docs/TODO_NEXT.md` under "Built but not tied in"; the architecture entry is in `CODEBASE_INDEX.md` under "Built, not wired". When the code and this page differ, the code is the truth.

## The rule

1. **Nothing existing changed.** No file under `app/`, `static/`, `tests/` or `tools/` that existed before this pass was edited; only the docs were.
2. **Each new module is a leaf.** It may import existing modules read-only. No existing module imports it, no route exposes it, no prompt mentions it, no page loads it. `grep -rn "app\.<module>" app/ static/` hits only the module itself; `static/index.html` and `static/popout.html` do not name the two JS files.
3. **No schema change in `init_db`.** A module that needs tables ships `ensure_schema(conn)` (`CREATE TABLE IF NOT EXISTS`, one statement per `execute`, no commit inside), called by nothing but its own writers and tests. The tables are not in `WORLD_TABLES`, `RESTORE_ORDER`, `AUTOINC_TABLES`, `SNAPSHOT_SETTING_KEYS`, the export or the slots. Table names are final (no `unwired_` prefix). Modules with nothing to create (`currency`, `needs`, `scene_cast`, `wild_places`, `realtime_clock`) export `ensure_schema` as a documented no-op so one loop can call them all.
4. **Every module starts with a docstring** carrying `Status: built, not wired (TODO <id>).`, a purpose paragraph, `Wiring (not done):` (each hook as `file.py:function()` and the one call that hook would make), `Turn on:` (flag, schema and registry entries, routes, UI, prompt lines) and `Tests:`. The JS files carry the same block as a header comment.
5. **Pure where possible.** Functions take rows and dicts and return proposed changes (deltas, new rows, prose lines) in exactly the shape the existing writer accepts; writers take `conn` explicitly. Nothing in this pass applies a proposal.
6. **Tests ship with the code.** `tests/test_<module>.py` as `unittest.TestCase` classes with temp `AI_RPG_*` paths set at import and re-applied in `setUpModule()`, a fresh DB per writer test, no model, no network; `tools/test_<name>.js` for the JS files under node. Every test file has `test_module_is_a_leaf`, which reads every `.py`, `.js`, `.html` and `.css` file under `app/` and `static/` and fails when any file other than the module names it, and asserts the four docstring lines. A writer module also checks that `player`, `inventory`, `npcs`, `journal` and `settings` (other than its own key) have the same row counts after every write.
7. **Money is `units`.** Every amount in new code is an `int` of the active currency set's smallest unit, stored beside `currency_set`; `currency.from_legacy_gold()` and `to_legacy_gold()` are the only bridges to `player.gold`, and nothing in this pass reads or writes that column.

## Turning one on

Each module's Turn on list below is the checklist. The order that works: read the module's design in its docstring and the shared shapes here; add the `playthrough_options` flag (default off) and read it at the hook, never in the module; add the `ensure_schema` call to `app/db.py:_migrate_columns()` and the registry entries (`WORLD_TABLES`, `RESTORE_ORDER`, `AUTOINC_TABLES` or the `quest_clocks`-style snapshot for text-key tables, `_clear_playthrough`, `SNAPSHOT_SETTING_KEYS` for turn-state rows); add the hook lines; add the routes, UI and prompt lines; then replace `test_module_is_a_leaf` with the wiring's own test and update `CODEBASE_INDEX.md`, `docs/TODO_NEXT.md` and this page. Turn on one item at a time and play-test between.

Enable flags (all default off; read by the wiring, never by the module): `economy_sim_enabled` (economy), `trade_offers_enabled` (trade), `agreements_enabled` (agreements; needs `trade_offers_enabled`), `needs_enabled`, `body_health_enabled`, `restraint_enabled`, `scene_cast_enabled`. `realtime_clock` has its own `enabled` field in its settings row. g8, g17 and n22 are gap fixes with no flag: they turn on with their hook lines.

## Modules

| TODO | Module | Tests | Tables | Settings rows | Flag |
|---|---|---|---|---|---|
| n17 | `app/currency.py` | `tests/test_currency.py` | none | `currency_config` (rule) | none; `MIGRATION_PLAN` step 1 |
| n1 | `app/economy.py` | `tests/test_economy.py` | `market_state` (text key), `market_events` (autoinc) | `economy_config` (rule) | `economy_sim_enabled` |
| n15 | `app/trade.py` | `tests/test_trade.py` | `price_ledger` (autoinc), `price_index` (text key), `trade_offers` (autoinc) | none | `trade_offers_enabled` |
| n18 | `app/agreements.py` | `tests/test_agreements.py` | `agreements`, `agreement_events` (autoinc) | none | `agreements_enabled` |
| n16 | `app/needs.py` | `tests/test_needs.py` | none | `player_needs` (turn state) | `needs_enabled` |
| n23 | `app/body_health.py` | `tests/test_body_health.py` | `body_wounds`, `body_health_log` (autoinc; `body_wounds` needs a whole-table snapshot) | none | `body_health_enabled` |
| n13 | `app/restraint.py` | `tests/test_restraint.py` | `restraint_log` (autoinc) | `restraint` (turn state) | `restraint_enabled` |
| n14 | `app/scene_cast.py` | `tests/test_scene_cast.py` | none | none | `scene_cast_enabled` |
| g8 | `app/settlement_visits.py` | `tests/test_settlement_visits.py` | `settlement_visits` (text key, export by `map_id`) | none | none |
| n22 | `app/wild_places.py` | `tests/test_wild_places.py` | none | none | none |
| n2 | `app/realtime_clock.py` | `tests/test_realtime_clock.py` | none | `realtime_clock` (rule; its own `enabled`) | row field |
| g17 | `static/ui/scene_sequence.js` | `tools/test_scene_sequence.js` | none | none | none |
| n22 | `static/ui/destination_marker.js` | `tools/test_destination_marker.js` | none | none | none |

Text-key tables (`price_index`, `market_state`, `settlement_visits`) follow the `quest_clocks` precedent when wired: whole-table snapshot in `_save_snapshot`, delete and `INSERT OR REPLACE` in `_restore_snapshot_rows`, `_REPLACE_ONLY_WHEN_EXPORTED`, export filtered by `map_id` where the table has one. Autoinc tables join `AUTOINC_TABLES` and rewind by max id; `body_wounds` rows change in place, so it also needs the whole-table snapshot.

The sections below are copied from each file's docstring or header comment. Indentation is kept; a hook line is `file.py:function() -> the one call`.

### `app/currency.py` (TODO n17)

Currency sets by theme: smallest-unit storage, format, parse, convert.

Status: built, not wired (TODO n17).

A world's money is a currency set chosen from its theme: medieval or fantasy coin (100 copper = 1 silver, 100 silver = 1 gold, 100 gold = 1 platinum), sci-fi credits, modern cash, post-collapse scrip that leans on goods. Every amount this module handles is an int of the set's smallest unit. The only storage is the settings row `currency_config` (a world rule, not turn state, so it is not snapshotted), written by `update_currency_config` alone. The live game still keeps one unitless `player.gold` number; nothing here reads or writes it, and no function here touches any other table. The migration of that number is written down in `MIGRATION_PLAN` below and is not executed by this module. The live game does not call anything in this file.

```text
Wiring (not done):
  app/world.py:_apply_player() -> units = currency.from_legacy_gold(player_patch["gold_delta"], cset) before
      the gold clamp, once player.purse_units exists (MIGRATION_PLAN step 1).
  app/prose_state.py:stated_coin_amounts() -> currency.coin_pattern(cset) in place of _COIN inside _PAID_RE /
      _PRICED_RE / _RECEIVED_RE (they carry the pay / price / receive context and the quote split), and
      currency.parse_amount(match.group(0), cset)["units"] in place of _match_number so the lists hold units.
  app/world.py:_reconcile_prose_with_state() -> currency.format_amount(units, cset) for the "You have N gold"
      sentence and currency.coin_pattern(cset) for the clamp regex.
  app/world.py:resolve_turn_bands() -> money_delta = currency.from_legacy_gold(gold_delta, cset); the dice in
      app/rng.py DEFAULT_MAGNITUDE_TABLES["gold"] stay in the display denomination (step 3).
  app/quests.py:pay_quest_completion() / create_quest() -> reward_units = currency.from_legacy_gold(reward_gold, cset) (step 6).
  app/world.py:start_playthrough() -> cset["starting_purse"] instead of the literal 12 (step 7).
  app/world.py:get_state() -> state["purse"] = currency.purse_view(units, cset) for the UI and the prompt packet.
  app/world.py:build_prompt_context() -> one line naming the coin words, currency.coin_words(cset).

Turn on:
  [ ] settings row currency_config is read by get_state through currency.active_set(conn) (no snapshot:
      it is a world rule, not turn state)
  [ ] _clear_playthrough(): DELETE FROM settings WHERE key = 'currency_config' so a new world re-detects its
      set from its own playthrough_options instead of keeping the set the last world chose
  [ ] MIGRATION_PLAN steps 1-12 in order; step 1 is the only schema change (additive player columns);
      ensure_schema here is a no-op, so no WORLD_TABLES / AUTOINC_TABLES / snapshot / export entry is needed
  [ ] route GET/POST /api/currency-config (pattern: /api/tts-config) if the user should pick a set
  [ ] UI: purse display reads state.purse.display; the bands text in band_contract_block names the coin words
  [ ] prompt: the coin words line; nothing else
```

Tests: tests/test_currency.py

### `app/economy.py` (TODO n1)

Settlement market simulation: supply and demand, season, scarcity, a price multiplier per category.

Status: built, not wired (TODO n1).

Every settlement the map knows (a settlements_meta row or a tile_world.list_settlements row) gets one market_state row per goods category: stock in days of consumption, demand, production and consumption per day derived from its size and type, a season read from the world day, scarcity events rolled from the campaign seed and kept in market_events, and a small seeded drift so no two days are identical but a rewind replays the same market. settlement_multiplier() turns that into the one PriceMultiplier dict that app.trade reads; tick_day() advances the market by whole days. The module writes only its own two tables and its own economy_config settings row. It never reads the player, the inventory, prices or currency, never inserts into gm_events (it returns event proposals) and never touches the map. The live game does not call it.

```text
Wiring (not done):
  app/world.py:advance_world_time() -> on the days_add > 0 branch after tick_weather, beside the
      tick_quest_clocks call (same try/except shape), gated by
      _play_system_enabled(conn, "economy_enabled", True) and _play_system_enabled(conn, "economy_sim_enabled", False).
      Inside the try: from app.tile_world import get_map, list_settlements; map_data = get_map(None, conn);
      skip when map_data is None (no active map); else
      tick = economy.tick_day(conn, from_day=int(before["day"]), to_day=int(new_day),
      settlements=list_settlements(map_data), options=_settings(conn).get("playthrough_options") or {},
      weather_kind=get_weather(conn)["kind"]). Only before, new_day and conn are locals of that function;
      tile_world is not imported at module level in world.py, so the import is lazy.
  app/world.py:apply_map_travel_step() -> next to the ensure_settlement_ruler(conn, location_id=, settlement=)
      call: economy.ensure_settlement(conn, settlement, day=int(get_world_time(conn)["day"]),
      options=_settings(conn).get("playthrough_options") or {})
  app/world.py:queue_world_event() -> for each entry of tick_day(...)["event_proposals"]: queue_world_event(**entry).
      That loop may not run inside advance_world_time: queue_world_event opens its own connection and
      advance_world_time already holds an uncommitted write on conn, so a second writer would wait on the
      busy timeout. advance_world_time returns the proposals in its result dict (key "event_proposals",
      beside "weather") and the caller (play_wait_turn, apply_turn and the other advance_world_time callers)
      runs the loop after its with connect() block has committed.
  app/world.py:build_prompt_context() -> one or two world facts beside the location facts, read from the
      state dict (the function holds no connection and no sid, day or meta locals):
      meta = state.get("settlement_meta"); day = int((state.get("world_time") or {}).get("day") or 1);
      when meta carries an id: with connect() as c: lines = economy.market_lines(
      economy.market_snapshot(c, str(meta["id"]), day=day)["multipliers"], economy.settlement_profile(meta))
  app/trade.py:settlement_price() -> economy.settlement_multiplier(conn, settlement_id, category, day=day)
      (trade is a new module of this same pass; this is the one in-cluster consumer and the only call that
      exists in code today)

Turn on:
  [ ] playthrough_options.economy_sim_enabled (default off); read by the wiring, never by this module
  [ ] app/db.py:_migrate_columns(): try: from app.economy import ensure_schema; ensure_schema(conn) except Exception: pass
  [ ] app/world.py:WORLD_TABLES and RESTORE_ORDER gain market_state and market_events; AUTOINC_TABLES gains
      market_events; market_state (text key) joins _REPLACE_ONLY_WHEN_EXPORTED and the two quest_clocks
      snapshot sites in _save_snapshot and _restore_snapshot_rows; _clear_playthrough deletes from both
      (WORLD_TABLES membership also puts both tables into export_world / import of ai-rpg-world-v1; neither
      has a map_id, so no per-map export filter applies and nothing else is needed for export)
  [ ] settings row economy_config is read by the tick (not snapshotted: it is a world rule, not turn state)
  [ ] the tick call and the ensure call above; no route needed (GET /api/market/{settlement_id} optional for Tools)
  [ ] UI: none
  [ ] prompt: the market_lines facts; nothing else
```

Tests: tests/test_economy.py

### `app/trade.py` (TODO n15)

Price ledger, settlement prices, trade offers and haggling.

Status: built, not wired (TODO n15).

The first time an item is priced the engine records it in price_ledger and price_index; later sales of the same item in the same settlement start from that first price, other settlements start from the running average, and both are moved by app.economy's per-settlement multiplier. A purchase becomes a trade_offers row (status offered) that only accept_offer() turns into a purse and inventory proposal; haggling and alternatives are pure functions over the offer, the keeper's npcs row, the relationship summary and a skill check result. Every amount is an int of the active currency set's smallest unit (app.currency). The module writes only its own three tables and no settings row of its own; a seed=None default on settlement_price, run_haggle or alternatives_for lets app.economy fall back to the campaign seed, which creates the campaign_rng_seed settings row once when it is absent. Nothing here moves gold or items, inserts a journal line or touches the player, inventory, npcs or quests: fulfilment_proposal() returns the changes and the wiring pass applies them. The live game does not call anything in this file.

```text
Wiring (not done):
  app/world.py:apply_turn() -> between the gold_note = _settle_stated_gold(result, player_input) line and the
      resolve_turn_bands(...) call: trade.record_turn_prices(conn, result=result, narration=_narration_text(result),
      gold_note=gold_note, seller=seller, turn=turn, day=day, cset=cset) and, when the prose names no price,
      trade.settlement_price(conn, name, settlement_id, day=day, cset=cset) for the GOLD op's amount. Only conn,
      result, gold_note and turn are locals there; the hook adds cset = currency.active_set(conn),
      day = get_world_time(conn)["day"] and seller = {"settlement_id", "location_id", "npc_id"} built from the
      scene keeper (the npcs row the purchase names, or None when there is no keeper).
  app/world.py:_settle_purse() -> instead of applying a named purchase: trade.open_offer(conn, trade.make_offer(
      kind="buy", item_name=..., quantity=..., unit_price=..., cset=currency.active_set(conn), seller_npc_id=...,
      location_id=..., settlement_id=..., turn=_turn_value(conn))) and park result["player"]["gold_delta"] = 0 with
      gold_note["source"] = "offer_parked". That function has no turn or cset local; it already calls _turn_value(conn)
      for its journal line.
  app/world.py:get_state() -> beside state["open_quest_offers"]: state["open_trade_offers"] =
      trade.state_view(conn, cset=currency.active_set(conn))["open_trade_offers"].
  app/main.py:_answer_offer() -> the same shape for POST /api/trade/{id}/accept|decline|haggle|alternatives through
      trade.accept_offer / trade.decline_offer / trade.run_haggle / trade.alternatives_for, 409 when the helper returns None.
  app/world.py:apply_turn() -> beside the apply_turn_intel(conn, player_input, turn) call: answer =
      trade.answer_from_line(trade.open_offers(conn), player_input, cset=cset) and the accept / decline / run_haggle call it names.
  app/world.py:_apply_turn_npc_relationship_deltas() -> for a HaggleResult with relationship_event:
      relationships.update_relationship(conn, npc_id, reason="haggle", **RELATIONSHIP_EVENTS[result["relationship_event"]]).
  app/world.py:_apply_inventory() and _apply_player() -> fulfilment_proposal(offer, cset=cset): its inventory_changes go to
      _apply_inventory(conn, changes) and its gold_delta_legacy to result["player"]["gold_delta"]; then trade.mark_settled(conn, id, turn=turn).
  app/world.py:apply_turn() -> after the SELECT current_location_id FROM player WHERE id = 1 that sets _cur_loc_id
      (there is no player object in apply_turn): trade.expire_stale(conn, turn=turn, location_id=_cur_loc_id).

Turn on:
  [ ] playthrough_options.trade_offers_enabled (default off) gates all of it; read by the wiring, never here
  [ ] app/db.py:_migrate_columns(): try: from app.trade import ensure_schema; ensure_schema(conn) except Exception: pass
  [ ] app/world.py:WORLD_TABLES and RESTORE_ORDER gain price_ledger, price_index, trade_offers; AUTOINC_TABLES gains
      price_ledger and trade_offers; price_index (text key) joins _REPLACE_ONLY_WHEN_EXPORTED and the two quest_clocks
      snapshot sites in _save_snapshot and _restore_snapshot_rows; _clear_playthrough deletes from all three
  [ ] routes: POST /api/trade/{id}/accept, /decline, /haggle, /alternatives on the _answer_offer pattern
  [ ] UI: an offer strip in the renderOfferPrompt style with Accept / Refuse / Haggle / Other options cards
  [ ] prompt: one line in the DSL user prompt listing open trade offers; "a price only offered is not paid" is already there for GOLD
```

Tests: tests/test_trade.py

### `app/agreements.py` (TODO n18)

Goods-for-service agreements with terms, due times, leftovers and a lifecycle over world time.

Status: built, not wired (TODO n18).

"I'll give you these 15 iron ore if you forge me a blade; anything left over you keep." is an agreements row: what each side gives, the work owed, when it is due (absolute world minutes), the leftovers policy. It is proposed and haggled as an app.trade offer of kind "service" or "barter", so Accept / Refuse / Haggle are the same objects; agree() turns the accepted terms into a row. The module writes only its own two tables, agreements and agreement_events, and no settings row. Handing goods over, the work finishing and the delivery are proposals (inventory changes, a money delta in units, journal notes and world-event proposals) that a wiring pass applies; tick() only moves states when the clock says so. Nothing here touches the player, inventory, npcs, journal or trade tables, and the live game does not call anything in this file.

```text
Wiring (not done):
  app/world.py:advance_world_time() -> after the tick_weather call and before the return, in the shape of
      the tick_quest_clocks call (try/except, gated by playthrough_options.agreements_enabled):
      result = agreements.tick(conn, world_time=after, turn=_turn_value(conn)); its event_proposals go to
      queue_world_event(**proposal), its journal entries ({kind, content}, one per ready / lapsed / forfeit
      row) to INSERT INTO journal (turn, kind, content), and its lines (engine text and diagnostics) to the log.
  app/world.py:apply_turn() -> where an accepted trade offer of kind service or barter is settled:
      row = agreements.agree(conn, terms=terms, offer_id=offer["id"], turn=turn, world_time=get_world_time(conn)),
      then _apply_inventory(conn, agreements.hand_over_proposal(row)["inventory_changes"]) (engine-authored,
      so it bypasses _filter_inventory_changes) and agreements.mark_handed_over(conn, row["id"], world_time=..., turn=turn).
  app/world.py:apply_turn() -> after the clock has advanced, for each open row in ready or lapsed whose
      location_id is the player's: _apply_inventory(conn, agreements.delivery_proposal(row)["inventory_changes"])
      then agreements.mark_delivered(conn, row["id"], world_time=..., turn=turn).
  app/world.py:get_state() -> beside state["open_quest_offers"]:
      state["agreements"] = agreements.state_view(conn, world_time=state["world_time"], cset=currency.active_set(conn))["agreements"].
  app/world.py:build_prompt_context() -> beside the open_leads block, in its shape (try/except, a short-lived connection):
      with connect() as c_agr: block = agreements.prompt_block(agreements.open_agreements(c_agr), state["world_time"], currency.active_set(c_agr))
      stored as prompt_context["agreements_block"] when it is not ""; the prompt builder prints it where it prints open_leads.
  app/main.py:_answer_offer() -> the same shape for GET /api/agreements (open_agreements + state_view) and
      POST /api/agreements/{id}/cancel through agreements.cancel(conn, id, world_time=..., turn=turn, by="player"), 409 when None.

Turn on:
  [ ] playthrough_options.agreements_enabled (default off; needs trade_offers_enabled); read by the wiring, never here
  [ ] app/db.py:_migrate_columns(): try: from app.agreements import ensure_schema; ensure_schema(conn) except Exception: pass
  [ ] app/world.py:WORLD_TABLES + RESTORE_ORDER + AUTOINC_TABLES gain agreements and agreement_events;
      _clear_playthrough deletes from both; export/import carry them with the other WORLD_TABLES
  [ ] routes: GET /api/agreements, POST /api/agreements/{id}/cancel on the _answer_offer pattern
  [ ] UI: a list in the Quests tab (Offered / Active / Agreements); the offer strip already covers the trade offer
  [ ] prompt: the prompt_block line above; nothing else
```

Tests: tests/test_agreements.py

### `app/needs.py` (TODO n16)

Hunger and thirst over world time.

Status: built, not wired (TODO n16).

Two needs, hunger and thirst, as 0..100 values stored in one settings row (`player_needs`). They fall as world minutes pass (faster when travelling, slower asleep, thirst faster in heat) and rise when the player eats or drinks an inventory item the word tables recognise. Bands on each value map to effects: a recovery multiplier that slows energy, fatigue and wound recovery, fatigue gained per hour, energy and health lost per hour, and a sustained-low penalty once a need has sat under 25 for twelve hours. Every decision is a pure function over the state dict; the writers (`load_state`, `save_state`, `tick_and_save`, `consume_from_inventory`) touch only the `player_needs` row. Nothing here changes the player row, the inventory or any prompt, and the live game does not call this module.

```text
Wiring (not done):
  app/world.py:advance_world_time() after tick_weather() -> needs.tick_and_save(conn, minutes=add, world_time=after,
      activity="wait", weather=get_weather(conn)), mirroring the tick_quest_clocks call (try/except, gated by
      playthrough_options.needs_enabled).
  app/world.py:_spend_travel() after out["time"] = advance_world_time(conn, minutes) -> needs.tick_and_save(conn,
      minutes=minutes, world_time=out["time"]["after"], activity="travel", weather=out["weather"]), its deltas folded into
      out["resource_spend"].
  app/world.py:play_wait_turn() right after apply_regen -> needs.tick_and_save(..., activity=kind_l), its deltas folded
      into res_delta / res_block, and needs.prompt_block(result["state"]) appended to model_input next to resource_regen.
      Both callers already run advance_world_time themselves, so the tick must run once per span: either inside the
      advance_world_time hook with the activity passed through, or in these two callers, never both.
  app/world.py:play_turn() after advance_world_time(c_time, spent) -> intent = needs.detect_intent(player_line); when
      intent["action"]: needs.consume_from_inventory(conn, intent, rows=context.get("inventory") or [], world_time=...)
      (the game state local there is `context`) and append its consume InventoryChange to result["inventory_changes"],
      its line to mechanics_context["needs"].
  app/player_resources.py:apply_regen() -> multiply the *_exact regen values by
      needs.merge_recovery(needs.recovery_modifier(ns), body_health.recovery_modifier(body))["mult"] before settle_resource_carry.
  app/world.py:apply_turn() beside _apply_player() -> add tick deltas["health"] to result["player"]["health_delta"] and list
      "player.health_delta" in result["_server_authored"]; energy/fatigue deltas through
      player_resources.spend_resources(conn, energy=-d, fatigue=d).
  app/world.py:get_state() near the turn_prompts.state_view merge -> state["needs"] = needs.state_view(needs.load_state(conn)).
  app/world.py:_build_mechanics_context() -> mechanics["needs"] = needs.prompt_block(state.get("needs") or {}) beside
      mechanics["resources"], once the get_state hook above adds state["needs"] (the state_view output normalizes
      cleanly). The argument is the NeedsState, never the whole game state, which would read as the 85/85 default.

Turn on:
  [ ] playthrough_options.needs_enabled (default off), read by the wiring
  [ ] app/world.py:SNAPSHOT_SETTING_KEYS += "player_needs" (rewind and new game); no init_db change (settings row only)
  [ ] the advance_world_time tick; the eat/drink detection in play_turn; the apply_regen multiplier
  [ ] prompt: the prompt block line in _build_mechanics_context
  [ ] UI: two chips under the resource bars from state.needs
```

Tests: tests/test_needs.py

### `app/body_health.py` (TODO n23)

Per-location body health: wounds, engine-owned healing states, treatments, capability effects.

Status: built, not wired (TODO n23).

The player's body is a fixed set of locations (head, torso, left and right arm, left and right hand, left and right leg). A wound is a row on one location with a kind (cut, pierce, blunt, burn, bite), a damage amount, a severity 1..4 derived from damage against the location's share of max_health, and exactly one basic state from BASIC_STATES: bleeding, open, bandaged, broken, splinted, infected, healing, bruised. Each state is a data row that says what it does per world hour, what it rolls each world day, what it blocks, which treatments move it where, and when it moves on by itself. Treatments (bandage, splint, clean, salve, stitch) are engine facts: a bandage stops bleeding and does not heal. Modifier states are free text the model may attach to a wound ("poultice of yarrow", "stitched badly"); they are stored, shown in prose lines and never read by a rule, and they cannot name or negate a basic state. Capability effects (two-handed work, climbing, fine work, travel speed, combat penalties) come from a table over location, state and severity. The aggregate health_from_body() maps the body to the single player.health number, and wounds_from_health_delta() maps a health delta back into wounds, so the model can run beside HP. All rule functions are pure over the Body dict; the writers touch only the module's own tables body_wounds and body_health_log. The live game does not call anything here.

```text
Wiring (not done):
  app/db.py:_migrate_columns() tail -> try: from app.body_health import ensure_schema; ensure_schema(conn) except Exception: pass
  app/world.py:_apply_player() where health_delta is clamped -> body, wounds = body_health.wounds_from_health_delta(
      body_health.load_body(conn, max_health=max_health), delta, cause=..., turn=, abs_minute=); write
      body_health.health_from_body(body)["health"] instead of the raw sum and save_body(conn, body).
  app/world.py:play_turn() where injuries are copied into settings.player_conditions -> body_health.wounds_from_injury(body,
      check["injury"], ...) replaces the player_conditions append; body_health.conditions_view(body) feeds state["conditions"].
  app/world.py:advance_world_time() after tick_weather() -> body_health.tick_and_save(conn, minutes=add, world_time=after,
      max_health=..., rest_kind="none", recovery_mult=needs.recovery_modifier(...)["mult"]); the returned deltas["health"] go
      through the health_delta path (marked server-authored).
  app/world.py:play_wait_turn() after apply_regen() -> the same tick with rest_kind=kind_l; body_health.prompt_block(body)
      appended to model_input.
  app/world.py:play_turn() after advance_world_time(c_time, spent) -> t = body_health.detect_treatment(player_line); when
      t["treatment"]: body_health.treat_from_inventory(conn, t, rows=state["inventory"], world_time=, max_health=, turn=,
      skill_quality=body_health.quality_from_outcome(check["outcome"])), its consume proposal appended to result["inventory_changes"].
  app/world.py:_spend_travel() / app/tile_world.py:move_player() -> multiply minutes by the inverse of
      body_health.capabilities(body)["travel_speed_mult"]; OR body_health.move_verdict(body, kind) into the restraint guard line.
  app/skill_checks.py:resolve_check() -> situational_mod from capabilities(body)["check_mods"]; app/encounters.py:assess_danger()
      -> the "wounded" term from health_from_body(body)["ratio"].
  app/player_resources.py:apply_regen() -> body_health.recovery_modifier(body) merged with needs' through merge_recovery().
  app/turn_dsl.py:OPCODES -> a WOUND_NOTE op (not added) would call body_health.add_modifier(body, wound_id, name) for
      model-added modifier states; until then add_modifier is reachable only from tests.
  app/world.py:get_state() near the turn_prompts.state_view merge -> state["body"] = body_health.state_view(body).

Turn on:
  [ ] playthrough_options.body_health_enabled (default off), read by the wiring
  [ ] init_db: the ensure_schema call; app/world.py: WORLD_TABLES, AUTOINC_TABLES, RESTORE_ORDER and the tuple in
      _restore_snapshot_rows += "body_wounds", "body_health_log"; _clear_playthrough DELETE FROM both.
      The max-id entry only trims rows a turn created; wound rows are changed in place (state, damage, severity,
      dressing_age_minutes, status), so _save_snapshot also needs _snapshot_row(conn, "body_wounds", "id >= 0", (), rows)
      the way quests are captured, and "body_wounds" in the restore_order list inside _restore_snapshot_rows.
      body_health_log is append-only and needs the max-id entry alone.
  [ ] the _apply_player mapping; the advance_world_time tick; the treatment detection; the capability hooks in travel and checks
  [ ] prompt: the prompt block line
  [ ] UI: a body panel from state.body
```

Tests: tests/test_body_health.py

### `app/restraint.py` (TODO n13)

Capture and restraint: movement hard-block, in-place play, release conditions, trusted position set.

Status: built, not wired (TODO n13).

When the player is captured the engine, not the prose, must hold them: free steps, town walks, Travel presses and typed MOVE ops are refused with one verdict, in-place play (talk, wait, rest, train, look, status windows, escape attempts) stays open, and release comes from world time or a condition (a skill level, a quest stage, a payment, a world event, the captor letting go). Guards taking the player somewhere is a planned path over the existing map walkers, not a teleport, and the position write is a plan the engine applies with its own writers. A capture counts only when the prose signal is backed by an engine fact (a lost opposed check, a lost fight, an outnumbered ambush, the player's own surrender, or an engine event); flavour alone never locks anyone. State is one settings row (`restraint`) and one audit table (`restraint_log`); nothing here writes the player row, the map, town_position or the existing movement_locked / map_blank keys, and the live game does not call this module.

```text
Wiring (not done):
  app/db.py:_migrate_columns() tail -> try: restraint.ensure_schema(conn) except Exception: pass
  app/world.py:SNAPSHOT_SETTING_KEYS -> add "restraint" (rewind restores it; _clear_playthrough deletes it)
  app/world.py:WORLD_TABLES + RESTORE_ORDER + AUTOINC_TABLES + the tuple in _restore_snapshot_rows() -> "restraint_log"
  app/world.py:_clear_playthrough() -> DELETE FROM restraint_log (not keyed by campaign_id)
  app/main.py:_location_special_runtime() -> merge restraint.runtime_flags() (movement_locked |= flags["movement_locked"], label, hint, reason)
  app/world.py:_map_is_locked() -> `or restraint.is_locked(conn)` (covers the story walk and town_moves.plan_turn)
  app/world.py:_apply_player() before _find_location_id -> v = restraint.may_move(conn, "location_move", {"location_code": move_to}); blocked -> player_patch["move_to_location"] = player_patch["move_to_location_code"] = None, journal v["message"] (move_to is the place name or code the patch carried; any non-empty string refuses while locked)
  app/world.py:apply_turn() after resolve_movement -> when blocked set movement_report["status"] = "dropped" and movement_report["prose_mismatch"] = the refused destination (or "trim_from" = the move sentence) so _cut_prose_at_refused_move trims the prose; it only acts on status dropped | unresolved | dropped_unshown with one of those two keys, so a new status word alone trims nothing
  app/town_moves.py:plan_exit() / walk_out() / walk_to_cell() / click_walk() -> restraint.may_move(conn, "town_leave" | "town_walk", target); blocked -> raise PermissionError(v["message"]) (the "too tired" path)
  app/turn_prompts.py:walk_in_town() and app/main.py:_travel_press() -> restraint.may_move(conn, "travel_press", None) first
  app/main.py:api_tile_map_move() -> restraint.may_move(conn, "map_step", {"x": tx, "y": ty}) beside the 409 guard
  app/world.py:play_turn() before the prompt -> a = restraint.allowed_actions(restraint.load_state(conn), player_input); refused -> mechanics_context["restraint"] = a and the draft is told (the first argument is the RestraintState row, never the get_state() dict: a dict without a known mode normalises to free and would allow everything)
  app/world.py:build_prompt_context() -> restraint.prompt_block(state.get("restraint"), world_time) beside the resource lines (state["restraint"] is the RestraintState or None once the get_state() hook below merges state_view)
  app/world.py:play_wait_turn() -> restraint.wait_allowed(restraint.load_state(conn), minutes) (always allowed; clamps nothing today)
  app/world.py:advance_world_time() after tick_weather -> restraint.tick(conn, world_time=after) (time conditions)
  app/world.py:apply_turn() after quests are applied -> restraint.tick(conn) again (quest, skill, payment, event conditions change without minutes passing)
  app/world.py:play_turn() after the skill checks -> verdict = restraint.classify_capture(narration=..., checks=..., combat=..., player_input=...); verdict["verdict"] == "capture" -> restraint.capture(conn, restraint.propose_capture(verdict, ...), turn=, world_time=) with _capture_pre_turn_rows(..., setting_keys=("restraint",)) first
  app/world.py:apply_map_travel_step() encounter branch -> classify_capture(encounter=travel["encounter"], ...) for an ambush that takes the player
  app/world.py:play_world_event_turn() -> payload["restrain"] / payload["escort"] handled through capture() / plan_escort(); WORLD_EVENT_KINDS gains "restraint"
  app/turn_dsl.py:_apply_op() -> RESTRAIN / RELEASE / ESCORT lines parsed by restraint.parse_restraint_op(entry) into turn["_dsl"]["restraint"] once OPCODES lists them; apply_turn reads them as model assertions (prose signal, never corroboration)
  app/world.py:get_state() near the turn_prompts.state_view merge -> state.update(restraint.state_view(conn))
  escort apply: restraint.apply_position(conn, plan, writers={"location": ..., "token": ..., "town": ...}) with tile_world.restore_player_position / town_moves._set_marker / town_moves.enter_town / the player UPDATE as the writers; the leg loop copies main._travel_press and feeds restraint.escort_travel_dict(leg) to _spend_travel

Turn on:
  [ ] playthrough_options.restraint_enabled (default off), read by the wiring at every hook
  [ ] init_db: ensure_schema call in _migrate_columns; "restraint" in SNAPSHOT_SETTING_KEYS; "restraint_log" in WORLD_TABLES / RESTORE_ORDER / AUTOINC_TABLES and the rewind tuple; _clear_playthrough delete
  [ ] movement guards: _location_special_runtime, _map_is_locked, _apply_player, town_moves walks, walk_in_town / _travel_press, api_tile_map_move
  [ ] turn hooks: allowed_actions + prompt_block in play_turn / build_prompt_context; tick in advance_world_time and apply_turn; classify_capture after checks and in the encounter branch
  [ ] events: "restraint" kind in WORLD_EVENT_KINDS; play_world_event_turn payload lines for restrain / escort
  [ ] DSL: RESTRAIN / RELEASE / ESCORT in OPCODES and the legend; _apply_op writes _dsl.restraint
  [ ] routes: none new; GET /api/travel-status already returns the 409 fields (add label / hint from runtime_flags)
  [ ] UI: updateTravelStatus reads state.restraint.label for the banner; nothing else
  [ ] prompt lines: the three op legend lines; one SYSTEM_PROMPT rule that a capture is an outcome the engine confirms, not a choice the prose makes
```

Tests: tests/test_restraint.py

### `app/scene_cast.py` (TODO n14)

Scene cast with placeholder slots: who a draft may name, how slots bind, what the verifier rejects.

Status: built, not wired (TODO n14).

The draft flow trusts free-text names and gets `travel-stained coat's rebels` and `L1's allies`: gear and places used as people, while the npcs table stays empty. This module turns the cast into a fill-in map. Before the draft, build_involved() lists the people, items and places this beat may use as slots (NPC_1, ITEM_1, PLACE_1), reusing known codes and offering at most one new face. The draft writes {NPC_1} in prose and in ops; bind() maps every slot to `Name [[CODE]]` (people), `Name [[L#]]` (places) or object phrasing (`your coat [[I#]]`) and proposes the NPC_NEW rows for new faces with their drawn names. verify() runs gates (unbound placeholder, slot bound to gear, item or place as agent, clothing name, cast overflow, speaker outside the cast) and propose_repairs() answers with a deterministic refill or cut, or flags that one prose re-ask is needed. Reports ride on turn["_dsl"]["scene_cast"], the one turn carrier the handoff cleanup keeps. Nothing here touches the database, the prompts, or the DSL opcode table, and the live game does not call this module.

```text
Wiring (not done):
  app/llm.py:_try_dsl_draft() just before build_dsl_user_prompt(active_context, player_input) -> inv = scene_cast.build_involved(active_context, player_input, turn=...); active_context["involved"] = inv["involved"] (and app/turn_dsl.py:build_dsl_user_prompt() copies context["involved"] into the packet beside cast_options)
  app/turn_dsl.py:ops_to_turn() after the turn dict is built -> turn["_dsl"]["placeholders"] = scene_cast.find_placeholders(narration); scene_cast.slot_refs_in_ops(ops) for NPC_NEW / CAST / TALK lines that name a slot
  app/llm.py:_normalize_turn() just before _repair_entity_names_in_turn(result, context) -> b = scene_cast.bind(result, context.get("involved"), scene_cast.entity_map_from_context(context, result), seed=...); result = b["turn"]; scene_cast.attach_report(result, {"binding": b["binding"]})
  app/llm.py:_verification_policy() beside the unresolved_entity_references blocker -> v = scene_cast.verify(draft, involved, binding, entity_map); blockers += v["policy_blockers"]
  app/llm.py:generate_turn() at the _run_quest_parser seat (final prose) -> v2 = scene_cast.verify(...); r = scene_cast.propose_repairs(result, v2, binding, entity_map, seed=...); r["mode"] in ("refill", "cut") -> result = scene_cast.apply_repairs(result, r); r["needs_model_call"] -> one _retry_narration_prose-style call built by llm.py from r["reask_slots"] (that prompt text lives in llm.py)
  app/world.py:apply_turn() between the name repair and _collect_npcs_from_turn_result -> scene_cast.npc_rows_for_apply(result) gives the NPC_NEW-shaped rows for new slots so _npcs_shown_in_prose keeps them (a bound slot is shown by construction)
  app/world.py:apply_turn() at _apply_scene_cast(conn, result.get("scene_cast")) -> in the loop over collected_npcs keep ids = {npc["name"]: _upsert_npc(conn, npc)} (it returns the npcs row id, not the code), read code_by_name with one SELECT name, code FROM npcs WHERE id IN (...), then result["scene_cast"] = scene_cast.resolve_pending_cast(result, code_by_name) appends the codes minted this turn to scene_cast.present / interacting
  app/llm.py:_clean_turn_for_handoff() -> nothing: reports live under _dsl, which is already preserved
  app/turn_dsl.py:DSL_SYSTEM_PROMPT and app/prompts.py:SYSTEM_PROMPT / VERIFY_PROMPT -> the placeholder rule and the slot legend (prompt text, written there, not here)

Turn on:
  [ ] playthrough_options.scene_cast_enabled (default off), read by llm.py at the three seats
  [ ] packet: context["involved"] (HANDOFF_BASE_CONTEXT_KEYS gains "involved"; build_dsl_user_prompt copies it)
  [ ] draft: placeholder rule in DSL_SYSTEM_PROMPT; NPC_NEW / CAST / TALK accept a slot token
  [ ] bind at _normalize_turn; gates at _verification_policy; final-prose gate + repairs at the quest-parser seat
  [ ] apply: npc_rows_for_apply before _collect_npcs_from_turn_result; resolve_pending_cast before _apply_scene_cast
  [ ] no schema, no settings row, no route, no UI; trace shows _dsl.scene_cast in the turn file
```

Tests: tests/test_scene_cast.py

### `app/settlement_visits.py` (TODO g8)

Settlement visit journal: first visit, last visit, count, and the seeding proposal.

Status: built, not wired (TODO g8).

One row per settlement id (board "S3" or world city "C7") in the module's own table settlement_visits. record_enter() is the one writer: it upserts the row and returns whether this was a first visit, the row, a proposed journal line and, while no ruler exists yet (a first visit, or a later one whose seeding never ran), a seeding proposal listing the ruler, two officers and two workers with roles and power ranks. It never inserts npcs, never writes settings and never writes journal; the existing ensure_settlement_ruler (app/world.py) stays the one seeder. Re-entry within REENTRY_GRACE_MINUTES of the last visit on the same turn (stepping between cells of one city) is not a new visit. The live game does not call this module.

```text
Wiring (not done):
  app/world.py:apply_map_travel_step() (after _spend_travel, where settlement and loc_id are known) ->
      visit = settlement_visits.enter_from_travel(conn, travel, location_id=loc_id, turn=_turn_value(conn),
      world_time=(out.get("time") or {}).get("after")); then out["visit"] = visit, the journal INSERT from
      visit["journal"], and ensure_settlement_ruler only when visit["seed"] is not None (today it runs
      unconditionally and is idempotent, so the order does not matter).
  app/town_moves.py:enter_town() (after settlement_row(conn, city, create=True)) ->
      settlement_visits.enter_from_city(conn, city, location_id=settle, turn=turn, map_id=chart["id"],
      world_time=world.get_world_time(conn)) (the live map kind reaches a town only through this path).
      enter_town's turn defaults to 0 and the live travel route reaches it through
      app/main.py sync_after_world_move(conn, get_map(None, conn=conn), (px, py)) with no turn, so that
      call must pass turn=_turn_value(conn) as well; without the turn and the clock every entry to a city
      on that route looks like turn 0, minute 0 and re-entries are never counted.
  app/world.py:build_ambient_move_line() "You enter the bounds of" branch -> say "for the first time"
      when (travel_result.get("visit") or {}).get("first_visit").
  app/world.py:get_state() next to the turn_prompts.state_view merge -> state.update(settlement_visits.state_view(conn)).

Turn on:
  [ ] no playthrough_options flag: a gap fix that turns on with its hook lines
  [ ] app/db.py:_migrate_columns() tail: try: from app.settlement_visits import ensure_schema; ensure_schema(conn)
  [ ] app/world.py: WORLD_TABLES, RESTORE_ORDER, _REPLACE_ONLY_WHEN_EXPORTED += "settlement_visits";
      _save_snapshot / _restore_snapshot_rows: snapshot and replace whole like quest_clocks (text primary key);
      export filter by map_id like town_cells; _clear_playthrough: DELETE FROM settlement_visits
  [ ] the two hook calls above; the ambient line change
  [ ] UI: nothing required; optional "first visit" note in the travel banner from travel_result.visit
  [ ] prompt: nothing
```

Tests: tests/test_settlement_visits.py

### `app/wild_places.py` (TODO n22)

Where-questions about wild places, answered from the land around the player.

Status: built, not wired (TODO n22). This is the "hunting grounds get no engine answer" gap of that item.

parse_wild_question() recognises an ask ("where", "is there a", "know of", "nearest", "which way") about one of the FEATURES (hunting grounds, ford, cave, ruin, standing stones, fresh water, high ground, woods, marsh, road, hidden camp). scan() reads the tiles within WILD_HORIZON cells of the player (board grid cells, or world_scale.world_cell samples on a world chart) plus landmarks, hidden_bases and lived knowledge, and resolve_wild_question() turns the nearest match into the local_intel DirectionHint shape: told or not by local_intel.will_tell (public news for every feature; an undiscovered camp is forbidden news), the told cell blurred past 4 cells by local_intel.blur_cell, a compass word and one sentence of wording. Pure: nothing here writes the map, the journal or settings (on a world chart the first cell sample caches chart["cell_index"], as world_scale.world_cell does for every reader; nothing else on the chart is touched). No tables and no settings rows: ensure_schema() is a documented no-op. World charts have no landmarks or hidden bases, so caves, ruins, stones and camps are answered there only when a knowledge marker exists. The live game does not call this module.

```text
Wiring (not done):
  app/local_intel.py:turn_direction_hint() (line 1317) -> its first statement returns None when
      parse_direction_question(player_input) is None. Make that `asked = parse_direction_question(player_input)`
      and return None only when asked is None and not wild_places.is_wild_question(player_input). Then, after
      chart, speaker and day are built, the last line becomes
      `return resolve_direction(chart, player_input, speaker, day=day, gold=_player_gold(conn)) if asked is not
      None else wild_places.resolve_wild_question(chart, player_input, speaker, day=day, gold=_player_gold(conn))`.
      prompt_direction_hint and apply_hint_to_map then work unchanged.
  app/local_intel.py:apply_turn_intel() (line 1389) unresolved branch -> chart, speaker and gold are built
      inside `if asked is not None and not faction_held`; hoist that block out so it also runs when asked is
      None and wild_places.is_wild_question(player_input), and in that case call the same
      resolve_wild_question (day=_world_day(conn)) before _record_hint.
  app/local_intel.py:_record_hint() (line 1446) -> lift the `scale != "world"` early return for hints whose
      place["kind"] == "wild" (apply_hint_to_map already works on boards); town_moves.record_told returns ""
      for a wild place and needs no change. turn_direction_hint and apply_turn_intel keep their own
      `scale != "world"` early returns (lines 1333 and 1413), so board answers need those lifted as well.
  app/turn_prompts.py:gate_after_turn() (line 524) direction_hint branch -> when
      (hint.get("place") or {}).get("kind") == "wild", candidates.append(wild_places.travel_candidate(hint))
      in place of the inline tuple. The inline rule builds a blurred or forbidden label from hint["good"],
      which for a wild hint is the FEATURES key ("where you were pointed for hunting_grounds, north");
      travel_candidate reads the spoken label and carries the feature key in source["feature"].

Turn on:
  [ ] no playthrough_options flag: a gap fix that turns on with its hook lines
  [ ] the two local_intel calls, the _record_hint guard and the gate_after_turn candidate line
  [ ] no schema, no settings, no route, no UI
  [ ] prompt: none (the hint rides the existing direction_hint line)
```

Tests: tests/test_wild_places.py

### `app/realtime_clock.py` (TODO n2)

Wall clock to world clock: ratio, pause and resume, catch-up ticks in Wait-sized slices.

Status: built, not wired (TODO n2).

One settings row, realtime_clock, holds the ratio (world minutes per real minute), the enabled and paused flags and an anchor (a wall time and the abs world minute it corresponded to). No table is created; ensure_schema() is a documented no-op. elapsed_world_minutes() says how many world minutes real time owes the world since the anchor; plan_catch_up() turns the part not already covered by play into slices of slice_minutes, each listed with the effects a Wait of that length has (advance_world_time, apply_regen, roll_wait_events), capped at max_catch_up_minutes with the rest dropped and the anchor re-based. catch_up() without an apply callable only returns that plan and writes nothing; with one (the wiring passes wait_effects(conn), which calls the real advance_world_time, apply_regen and roll_wait_events) it runs the slices and moves the anchor. It never moves the clock while a turn is in flight (generation_progress / gpu_gate) or while travel_ready is false. The module writes only its own settings row: never pacing, never travel_ready, never journal. Non-goal: hosted multiplayer. This is one campaign's clock in one process; there is no networking, no session and no arbitration between players here, and none is planned by this item. The live game does not call this module.

```text
Wiring (not done):
  app/main.py:api_tts_config() / api_update_tts_config() -> the pattern for GET/POST /api/realtime-clock
      (realtime_clock.get_config() / realtime_clock.update_config(conn, payload)); a new POST
      /api/realtime-clock/tick calls realtime_clock.catch_up(conn, now_wall=time.time(),
      apply=realtime_clock.wait_effects(conn)) and returns the report plus state_view(conn).
  app/world.py:advance_world_time() -> the clock writer every slice uses, reached only through the apply
      callable (no change inside it).
  app/player_resources.py:apply_regen() and app/world.py:roll_wait_events() -> the other two slice effects,
      also reached only through the apply callable (wait_effects builds it).
  app/world.py:play_turn() / play_wait_turn() -> realtime_clock.pause(conn, reason="turn_in_flight") before
      the model call and realtime_clock.resume(conn, world_abs_now=world_abs_minutes(get_world_time(conn)))
      after apply_turn, so play minutes and real minutes never double count.
  app/world.py:start_playthrough() -> realtime_clock.reset_anchor(conn, world_abs_now=480) right after the
      init_world_clock call.
  app/world.py:rewind_last_turn() -> realtime_clock.resume(conn, world_abs_now=world_abs_minutes(get_world_time(conn)))
      when the clock is running, else realtime_clock.reset_anchor(conn, world_abs_now=...) with the same
      value, after the pacing rows are restored. The anchor is not in the snapshot (the row is a table rule,
      not turn state), so without this line a rewound turn's minutes would be owed again at the next tick.
  app/world.py:get_state() -> state.update(realtime_clock.state_view(conn)).
  static/app.js:startGenerationProgressPolling() -> the pattern for a poller hitting the tick route while the
      tab is visible and aiBusy is false; the wait summary line for each applied slice.

Turn on:
  [ ] settings row realtime_clock with enabled true (default off; AI_RPG_REALTIME_ENABLED overrides on read);
      not in SNAPSHOT_SETTING_KEYS (a table rule, like tts_config); no init_db / WORLD_TABLES / export entry
      because there is no table
  [ ] the tick route and the config routes
  [ ] pause/resume around play_turn, reset_anchor in start_playthrough, re-anchor in rewind_last_turn
  [ ] UI: ratio and pause controls in Settings; the poller
  [ ] prompt: none (the world_time line already carries the clock)
```

Tests: tests/test_realtime_clock.py

### `static/ui/scene_sequence.js` (TODO g17)

Mørkyn UI · scene_sequence.js  (display sequencing)

Status: built, not wired (TODO g17).

A queue for the one narration area. Scenes (turn payloads) are shown one at a time; an ambient line that arrives while a scene is streaming is held and shown when that stream has finished, or after the next waiting scene when the line was queued behind it (order is turn, then seq); an ambient line whose turn is older than the last scene shown is dropped. A second scene waits for the first; when a third arrives the current one is finished at once instead of being cut (requestWait fight scenes). Pure sequencing: callers pass render(done) and show(text) callbacks, so this file never touches the DOM. Nothing is persisted and nothing in the live page loads or calls this file.

```text
Wiring (not done):
  static/app.js:displayTurnPayload() -> MorkynSceneSequence.enqueueScene({token: MorkynSceneSequence.tokenOf(payload),
      label: payload.input_kind || "turn", render: (done) => <today's body, calling done() in the stream's onDone
      or right after the synchronous innerHTML path>, finishNow: () => <finish the stream instantly>})
  static/app.js:showAmbientMoveLine() -> MorkynSceneSequence.enqueueAmbient({token: MorkynSceneSequence.tokenOf({state}),
      text, show: (t) => <today's body>})
  static/app.js:streamTextToTargets() -> expose a finishNow (clearInterval + full text + onDone) for the scene's handle
  static/app.js:applyTravelMoveFeedback() and requestWait() fight_scenes loop -> nothing more once the two above are wrapped
  static/app.js:rewindTurn() / startGame() -> MorkynSceneSequence.reset()
  static/index.html -> <script src="/static/ui/scene_sequence.js?v=__BUNDLE__"> after app.js

Turn on:
  [ ] the script line in static/index.html (and static/popout.html if it shows narration)
  [ ] the two wraps in displayTurnPayload / showAmbientMoveLine
  [ ] reset() on rewind and new game
  [ ] no server change, no route, no prompt
```

Tests: tools/test_scene_sequence.js (node)

### `static/ui/destination_marker.js` (TODO n22)

Mørkyn UI · destination_marker.js  (the set destination on the maps)

Status: built, not wired (TODO n22). This is the "destination is not drawn on the map" gap of that item.

Draws state.travel_destination as a flag: on the lens and the Large map at the target world cell (or as a rim arrow when the cell is off the drawn window), on the Settlement canvas on the target city cell, and on the Streets canvas around the target plot (or the cell centre when the target is a cell). Reads only the canvas, the meta the painter stored on it (canvas._mapMeta / canvas._cityMeta) and the arguments it is given. The colour helper cssToken is read by bare name, guarded, wherever a painter needs a theme colour; settlementData, townData, townGeometry and townCellBox are read the same way only inside draw() for the two town modes. Nothing here fetches, stores or binds events, and nothing in the live page loads or calls this file.

```text
Wiring (not done):
  static/app.js:refreshLocalMap() -> after drawNpcMarkersOnCanvas(canvas, _lastNpcMarkers, data.player, "local"):
      window.MorkynDestinationMarker?.draw(canvas, state?.travel_destination, data.player, "local")
  static/app.js:refreshFullMap() -> after drawNpcMarkersOnCanvas(canvas, _lastNpcMarkers, data.player, "full"):
      window.MorkynDestinationMarker?.draw(canvas, state?.travel_destination, data.player, "full")
  static/app.js:paintSettlementCanvas() -> before the player ring (const you = city.player):
      window.MorkynDestinationMarker?.draw(canvas, state?.travel_destination, null, "settlement")
  static/app.js:paintTownCanvas() -> before the player ring (const you = townData.player):
      window.MorkynDestinationMarker?.draw(canvas, state?.travel_destination, null, "streets")
  static/app.js:repaintSettlementForSize() -> nothing more; it calls the two painters above
  static/app.js:renderMovePrompt() -> optional "shown on the map" note on the destination card
  static/index.html -> <script src="/static/ui/destination_marker.js?v=__BUNDLE__"> after app.js

Turn on:
  [ ] the script line in static/index.html
  [ ] the four draw() lines above (each after the painter's own markers, before the next repaint)
  [ ] no server change, no route, no prompt
```

Tests: tools/test_destination_marker.js (node)

## Shared shapes (short form)

Plain dicts, the repo style. `units` is an `int` of the active currency set's smallest unit. The full definitions with every key and type were reconciled across the four designs before the code was written; the code is the truth where they differ.

| Shape | Keys (short) | Producers | Consumers when wired |
|---|---|---|---|
| Money | `units: int` plus `currency_set: str` beside every stored amount; `CurrencySet` from `currency.theme_set(id)` (`id, label, smallest, denominations[], per_legacy_gold, decimal, symbol, accepts_goods, coin_acceptance, starting_purse`) | `currency` | every module that stores an amount; `format_amount` is the one money formatter |
| `PriceMultiplier` | `settlement_id, category, day, mult (0.40..3.00), supply, demand, season, season_mult, scarcity_mult, drift_mult, flavour_mult, events[], reason` (`ok`, `unknown_settlement`, `unknown_category`, `disabled`; not `ok` means use 1.0) | `economy.settlement_multiplier` | `trade.settlement_price` |
| `Offer` | the `trade_offers` row decoded: `id, code "T{id}", status, kind (buy, sell, service, barter), item_key, item_name, category, quantity, unit_price, total_price, asking_price, currency_set, seller_npc_id, location_id, settlement_id, offered_turn, answered_turn, expires_turn, rounds, max_rounds, last_player_bid, counter_price, goods_given[], terms_id, note, price_basis`; `OFFER_STATES` offered, countered, accepted, declined, refused, expired, settled | `trade.make_offer` (pure) / `open_offer` (insert); `agreements.terms_as_offer` | the offer routes and the apply hooks |
| `HaggleResult` | `decision (accept, counter, refuse, insulted), price, floor, ceiling_pct, mood, band, outcome, round, rounds_left, relationship_event, line` | `trade.resolve_haggle` | the haggle route; `agreements.haggle_terms`; `_apply_turn_npc_relationship_deltas` for `relationship_event` |
| `InventoryChange` | `name, quantity_delta, item_type?, description?, source (needs, body_health, trade, agreement), reason?`; exactly the `inventory_changes` entry `world._apply_inventory` accepts | `needs.eat/drink`, `body_health.treat_from_inventory`, `trade.fulfilment_proposal`, `agreements.hand_over_proposal/delivery_proposal` | `world._apply_inventory` |
| `JournalNote` | `kind (<= 40), content (<= 900)`; kinds `restrained, released, escort, system` (restraint), `trade`, `agreement`, `visit` | restraint, trade, agreements, settlement_visits | the caller's `INSERT INTO journal (turn, kind, content)` |
| `WorldEventProposal` | `kind "custom", summary, trigger, due_turn, force False, priority (0..10), payload`; triggers `economy:<kind>` (4), `agreement:<code>:due` (5), `body:bleeding` (6) | `economy.tick_day_proposal`, `agreements.tick`, `body_health.event_proposals` | `world.queue_world_event(**proposal)` after the commit |
| `SettlementRef` | `settlement_id ("S3" or "C7"), name, size (hamlet, village, town, city), type (city, town, village, harbor, station, colony, shipyard, farm, hamlet, ""), band_raw, population_band (tiny, small, medium, large), population_factor (1, 3, 10, 30), location_id` | `economy.settlement_profile` (the one producer; `settlement_visits.settlement_ref` delegates) | economy, trade, settlement_visits |
| `MoveVerdict` | `allowed, reason, message (<= 160), label, kind, movement_locked`; `message, movement_locked, label, reason` are the existing 409 detail keys; `kind` in `restraint.MOVE_KINDS`; reasons `restrained, custody, confined, escort_in_progress, unknown_target` (restraint) and `incapacitated, cannot_walk` (body_health) | `restraint.may_move` / `may_move_state`, `body_health.move_verdict` | every path that changes the player's position (restraint first, then body; the first refusal is the answer) |
| `StatusLine` and `prompt_block` | `key, severity (info, mild, serious, critical), line (<= 160), blocks[]`; `prompt_block()` joins the lines under `Player needs / body / restraint / agreements (server truth):` and returns `""` when empty | needs, body_health, restraint, agreements | `build_prompt_context` / `_build_mechanics_context` |
| `PlayerDeltas` | `energy, fatigue, health, energy_exact, fatigue_exact, health_exact, reasons[]`; `merge_deltas`, `zero_deltas` exported by both | `needs.tick`, `body_health.tick` | `player_resources.spend_resources` and the `health_delta` path (server-authored) |
| `RecoveryModifier` | `mult (0.1..1.25), factors[{source, band, mult}], label`; `merge_recovery(a, b)` multiplies and clamps | `needs.recovery_modifier`, `body_health.recovery_modifier` | `player_resources.apply_regen` (the merged product); `body_health.tick` takes the needs mult only |
| `Evidence` | `check, ok, evidence (<= 240), severity (block, warn, info), weight` | `scene_cast.verify` (weight 0.0), `restraint.classify_capture` | `llm._verification_policy` blockers; `restraint_log.detail` |
| `EntityRef` | `code ("" when none yet), name, kind (person, place, item, event), role` | `scene_cast.entity_map_from_context/rows`; restraint's captor | scene_cast bind and gates; restraint |
| `NpcRowProposal` | the `turn_dsl` NPC_NEW row plus `presence: "event_worthy"` and `_slot: "NPC_n"`; never a code | `scene_cast.bind` / `npc_rows_for_apply` | `world._upsert_npc` |
| `DirectionHint` | the `local_intel` shape (`told, specificity, good, label, name, distance, exact, compass, forbidden, reason, wording, place, x, y`); `place.kind` gains `wild` (`feature, x, y, state, label, name, fine_x, fine_y, discovered, source`) | `wild_places.resolve_wild_question` | `local_intel.prompt_direction_hint`, `apply_hint_to_map`, `_record_hint` |
| `Target` and `Destination` | `turn_prompts` shapes: `{x, y}`, `{x, y, city, location_code?}`, `{plot, city, x, y, location_code?}`; `Destination {target, label, enter, with[], set_turn, source?}` (settings row `travel_destination`) | `wild_places.travel_candidate` (the `gate_after_turn` candidate tuple); `restraint.place_from_target` / `target_from_place` | `turn_prompts.gate_after_turn`; `destination_marker.js` (all three Target forms); `restraint.plan_escort` |
| `Slice` | `minutes, kind "wait", effects [advance_world_time, apply_regen, roll_wait_events]` | `realtime_clock.plan_catch_up` | `realtime_clock.catch_up` with `wait_effects(conn)` |
| `DisplayToken` | `turn, step ("x,y" or ""), seq`; order `turn` then `seq`; an ambient line is stale when its `turn` is below the last scene shown | `MorkynSceneSequence.tokenOf(payload)` | the sequencer |

Conventions shared by all of them: world time reaches a pure function as `abs_minute: int` (`(day - 1) * 1440 + minute`, the clock after the span) and `minutes: int`, or `day: int`, or `turn: int`; writers take the `world.format_world_time()` dict and convert once with `player_resources.world_abs_minutes`; stored times are `*_abs_minute` ints or a `day INTEGER`; wall-clock time appears only in `realtime_clock` as `now_wall`, always passed in. Pure functions never read `rng.campaign_seed(conn)`: survival takes `rng` or builds a seeded one from the minute, economy takes an explicit `seed`, travel rolls through `local_intel.direction_roll`, trade's `run_haggle` takes the caller's rng, realtime_clock and scene_cast roll nothing. Relationship side effects are named (`relationship_event`), never applied.

## Position-changing order when wired

1. Guard: `restraint.may_move(conn, kind, target)`, then `body_health.move_verdict(body, kind)`; a refusing verdict ends the move (409 with its four keys, `movement_report["status"] = "blocked_restrained"`, or `PermissionError` on the town "too tired" path). `restraint.allowed_actions()` and `wait_allowed()` never block in-place play.
2. Apply: the existing writers move the player; an escort applies through `restraint.apply_position(conn, plan, writers=...)`, which bypasses the guard because the engine chose the move.
3. Record: `settlement_visits.enter_from_travel()` or `enter_from_city()` after the move, then `economy.ensure_settlement()`.
4. Propose: `wild_places.resolve_wild_question()` only proposes a `Destination`; the Travel press that follows is guarded at step 1.
5. Draw: `MorkynDestinationMarker.draw(...)` after the painter's own markers on each repaint.

Known gaps the wiring must mind: `tile_world.move_player` raises on every world-scale chart, so the g8 hook on the live map kind is `town_moves.enter_town`, and escort world legs apply through token moves; `local_intel._record_hint` returns `[]` when `scale != "world"`, so a wild hint on a board needs that guard lifted.

## Decisions to make when wiring

- Gold migration: `currency.MIGRATION_PLAN` moves the single `player.gold` number into smallest units in twelve steps (step 1 is the only schema change: additive player columns), and with `coin_medieval` one legacy gold becomes 10000 copper. `trade.REFERENCE_GOLD` is fitted to today's prose (a loaf is "a couple of coins", the player starts with 12), not to a realistic medieval price list; whether to re-fit the prose prices is a user decision.
- Escort legs on world-scale charts: `restraint.plan_escort` plans the path, but `tile_world.move_player` cannot step on a world chart, so the apply loop must use token moves (`walk_toward` / `_apply_story_map_walk` style); which existing walker it copies is a wiring choice.
- The "player down" combat outcome: the deterministic combat emits only `hit`, `glancing_hit`, `miss`, `resolved`, `unresolved`, so today only the health-ratio rule can corroborate a capture (`restraint.COMBAT_LOSS_OUTCOMES` lists the words it would accept); whether to add an outcome word to the deterministic path is for the wiring pass.
- Wild places on world charts: landmarks and hidden bases are always empty there, so caves, ruins, stones and camps are answered only where a knowledge marker exists; a later item would stamp landmarks from terrain.
- The `WOUND_NOTE` op: the name is reserved for `body_health.add_modifier`; its place in `turn_dsl.OPCODES` and its legend text need the draft-flow owner when a DSL change is allowed. `RESTRAIN`, `RELEASE` and `ESCORT` are reserved the same way.
- g8 power bands and re-entry grace: `ensure_settlement_ruler` uses power 50 for world cities and ignores bands; `settlement_visits.POWER_BY_BAND` takes effect only if the wiring passes the proposal's `ruler_power_rank`; and a `left_turn` column could replace the 30-minute `REENTRY_GRACE_MINUTES` once `sync_after_world_move` has a hook.
- `trade_drain` into `economy.advance_market_row` is 0 in this pass; feeding it from the ledger (`sold_quantity / population_factor`) is a later item.
- Body locations: feet are folded into legs (the existing injury vocabulary has "hand" but no "foot") and hands are included; adding feet is one row in `body_health.LOCATIONS` plus capability rules.
- `economy.market_lines()` stays a list of world facts, not `StatusLine` rows; revisit if the prompt wants one block for everything.
- Kept as designed after review, not open: hands in, feet folded into legs; `body_health_log` as a table; `REENTRY_GRACE_MINUTES = 30`; `finishCurrentAt = 2`; `max_catch_up_minutes = 1440`; `SLICE_KIND = "wait"`; restraint ticks in both `advance_world_time` and the end of `apply_turn`; the celestial confinement lock stays separate and is ORed; the hidden camp drops the bare word "camp".
